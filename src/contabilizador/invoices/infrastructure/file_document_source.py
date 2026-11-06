"""Reads DIAN XML documents from files, folders (recursive) and zip archives.

Every input is listed first (so the total is known), then each XML is read reporting
progress; zip members count as one step each.
"""

import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import TracebackType

from contabilizador.invoices.application.errors import ImportCancelledError
from contabilizador.invoices.application.ports import (
    CancelCheck,
    DocumentParser,
    ProgressCallback,
)
from contabilizador.invoices.domain.document import ParsedDocument
from contabilizador.invoices.domain.errors import DocumentError, UnsupportedDocumentError
from contabilizador.invoices.domain.source import LoadResult, SkippedFile

XML_SUFFIX = ".xml"
ZIP_SUFFIX = ".zip"
# Límite por miembro del zip para evitar zip bombs (los XML DIAN pesan KB)
DEFAULT_MAX_MEMBER_BYTES = 50 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class _XmlFile:
    path: Path


@dataclass(frozen=True, slots=True)
class _ZipMember:
    zip_path: Path
    info: zipfile.ZipInfo


@dataclass(frozen=True, slots=True)
class _Skip:
    file: SkippedFile
    failed: bool  # False = ignorado (otro tipo de archivo)


type _Step = _XmlFile | _ZipMember | _Skip


def _never_cancelled() -> bool:
    return False


def _no_progress(_done: int, _total: int) -> None:
    return None


class FileDocumentSource:
    """Implements ``DocumentSource`` on the local file system."""

    def __init__(
        self, parser: DocumentParser, max_member_bytes: int = DEFAULT_MAX_MEMBER_BYTES
    ) -> None:
        self._parser = parser
        self._max_member_bytes = max_member_bytes

    def load(
        self,
        paths: Iterable[Path],
        *,
        on_progress: ProgressCallback | None = None,
        is_cancelled: CancelCheck | None = None,
    ) -> LoadResult:
        cancelled = is_cancelled or _never_cancelled
        report = on_progress or _no_progress
        steps = self._list(paths, cancelled)
        report(0, len(steps))
        collector = _Collector()
        with _OpenZip() as archives:
            for done, step in enumerate(steps, start=1):
                if cancelled():
                    raise ImportCancelledError()
                self._run(step, archives, collector)
                report(done, len(steps))
        return collector.result()

    # --- listado -----------------------------------------------------------
    def _list(self, paths: Iterable[Path], cancelled: CancelCheck) -> list[_Step]:
        steps: list[_Step] = []
        for path in paths:
            if cancelled():
                raise ImportCancelledError()
            if path.is_dir():
                # En carpetas solo se leen .xml y .zip; el resto (PDF...) se omite en silencio
                for child in sorted(path.rglob("*")):
                    if cancelled():
                        raise ImportCancelledError()
                    if child.is_file() and _suffix(child.name) in (XML_SUFFIX, ZIP_SUFFIX):
                        steps.extend(self._list_file(child))
            else:
                steps.extend(self._list_file(path))
        return steps

    def _list_file(self, path: Path) -> list[_Step]:
        suffix = _suffix(path.name)
        if suffix == ZIP_SUFFIX:
            return self._list_zip(path)
        if suffix == XML_SUFFIX:
            return [_XmlFile(path)]
        return [_Skip(SkippedFile(str(path), "Extensión no soportada (solo .xml o .zip)"), False)]

    @staticmethod
    def _list_zip(path: Path) -> list[_Step]:
        try:
            with zipfile.ZipFile(path) as archive:
                members = [info for info in archive.infolist() if _is_xml_member(info)]
        except (zipfile.BadZipFile, OSError) as error:
            return [_Skip(SkippedFile(str(path), f"Zip inválido o ilegible: {error}"), True)]
        return [_ZipMember(path, info) for info in members]

    # --- lectura -----------------------------------------------------------
    def _run(self, step: _Step, archives: "_OpenZip", collector: "_Collector") -> None:
        match step:
            case _Skip(file=file, failed=True):
                collector.failed.append(file)
            case _Skip(file=file):
                collector.ignored.append(file)
            case _XmlFile(path=path):
                try:
                    content = path.read_bytes()
                except OSError as error:
                    collector.fail(str(path), f"No se pudo leer el archivo: {error}")
                    return
                self._parse(content, path, str(path), collector)
            case _ZipMember(zip_path=zip_path, info=info):
                self._read_member(zip_path, info, archives, collector)

    def _read_member(
        self,
        zip_path: Path,
        info: zipfile.ZipInfo,
        archives: "_OpenZip",
        collector: "_Collector",
    ) -> None:
        label = f"{zip_path}::{info.filename}"
        if info.file_size > self._max_member_bytes:
            collector.fail(label, "Archivo demasiado grande dentro del zip")
            return
        try:
            content = archives.read(zip_path, info)
        except (zipfile.BadZipFile, OSError, RuntimeError) as error:
            collector.fail(label, f"No se pudo leer del zip: {error}")
            return
        self._parse(content, zip_path, label, collector)

    def _parse(
        self, content: bytes, source_file: Path, label: str, collector: "_Collector"
    ) -> None:
        try:
            collector.parsed.append(self._parser.parse(content, source_file))
        except UnsupportedDocumentError as error:
            collector.ignore(label, str(error))
        except DocumentError as error:
            collector.fail(label, str(error))


class _OpenZip:
    """Keeps the current zip open while its members are read (one open per zip)."""

    def __init__(self) -> None:
        self._path: Path | None = None
        self._archive: zipfile.ZipFile | None = None

    def read(self, path: Path, info: zipfile.ZipInfo) -> bytes:
        if self._archive is None or self._path != path:
            self.close()
            self._archive = zipfile.ZipFile(path)
            self._path = path
        return self._archive.read(info)

    def close(self) -> None:
        if self._archive is not None:
            self._archive.close()
        self._archive = None
        self._path = None

    def __enter__(self) -> "_OpenZip":
        return self

    def __exit__(
        self,
        _type: type[BaseException] | None,
        _value: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        self.close()


class _Collector:
    def __init__(self) -> None:
        self.parsed: list[ParsedDocument] = []
        self.ignored: list[SkippedFile] = []
        self.failed: list[SkippedFile] = []

    def ignore(self, source: str, reason: str) -> None:
        self.ignored.append(SkippedFile(source, reason))

    def fail(self, source: str, reason: str) -> None:
        self.failed.append(SkippedFile(source, reason))

    def result(self) -> LoadResult:
        return LoadResult(tuple(self.parsed), tuple(self.ignored), tuple(self.failed))


def _suffix(name: str) -> str:
    return PurePosixPath(name).suffix.lower()


def _is_xml_member(info: zipfile.ZipInfo) -> bool:
    if info.is_dir():
        return False
    member = PurePosixPath(info.filename)
    # Metadatos de macOS (__MACOSX, ._archivo) no son documentos
    if "__MACOSX" in member.parts or member.name.startswith("._"):
        return False
    return member.suffix.lower() == XML_SUFFIX
