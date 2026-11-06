import io
import zipfile
from pathlib import Path

import pytest

from contabilizador.invoices.application.errors import ImportCancelledError
from contabilizador.invoices.domain.document import ParsedDocument
from contabilizador.invoices.infrastructure.dian_xml_parser import LxmlDianParser
from contabilizador.invoices.infrastructure.file_document_source import FileDocumentSource


@pytest.fixture
def source() -> FileDocumentSource:
    return FileDocumentSource(LxmlDianParser())


def test_single_xml_file(source: FileDocumentSource, xml_fixtures_dir: Path) -> None:
    result = source.load([xml_fixtures_dir / "invoice_plain.xml"])
    assert [doc.supplier_number for doc in result.parsed] == ["1001"]
    assert result.ignored == () and result.failed == ()


def test_unsupported_xml_is_ignored_with_reason(
    source: FileDocumentSource, xml_fixtures_dir: Path
) -> None:
    result = source.load([xml_fixtures_dir / "application_response.xml"])
    assert result.parsed == ()
    (ignored,) = result.ignored
    assert ignored.source == str(xml_fixtures_dir / "application_response.xml")
    assert "ApplicationResponse" in ignored.reason


def test_folder_is_read_recursively(
    source: FileDocumentSource, xml_fixtures_dir: Path, tmp_path: Path
) -> None:
    nested = tmp_path / "agosto" / "semana1"
    nested.mkdir(parents=True)
    (tmp_path / "plain.xml").write_bytes((xml_fixtures_dir / "invoice_plain.xml").read_bytes())
    (nested / "CREDIT.XML").write_bytes((xml_fixtures_dir / "credit_note.xml").read_bytes())
    (nested / "factura.pdf").write_bytes(b"%PDF-1.4")
    (tmp_path / "broken.xml").write_bytes(b"<Invoice>")
    result = source.load([tmp_path])
    assert sorted(doc.supplier_number for doc in result.parsed) == ["1001", "125"]
    (failed,) = result.failed
    assert failed.source == str(tmp_path / "broken.xml")
    assert failed.reason
    # Los PDF de la carpeta se omiten en silencio
    assert result.ignored == ()


def test_fixtures_folder_covers_every_fixture(
    source: FileDocumentSource, xml_fixtures_dir: Path
) -> None:
    result = source.load([xml_fixtures_dir])
    # 6 XML + 2 dentro del zip
    assert len(result.parsed) == 8
    assert [Path(item.source).name for item in result.ignored] == ["application_response.xml"]
    assert result.failed == ()


def test_zip_is_read_in_memory(source: FileDocumentSource, xml_fixtures_dir: Path) -> None:
    zip_path = xml_fixtures_dir / "invoices_bundle.zip"
    result = source.load([zip_path])
    assert sorted(doc.supplier_number for doc in result.parsed) == ["1001", "125"]
    assert all(doc.source_file == zip_path for doc in result.parsed)


def test_zip_skips_pdfs_and_reports_member_errors(
    source: FileDocumentSource, xml_fixtures_dir: Path, tmp_path: Path
) -> None:
    zip_path = tmp_path / "lote.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("factura.pdf", b"%PDF-1.4")
        archive.writestr("__MACOSX/._factura.xml", b"junk")
        archive.writestr("sub/", b"")
        archive.writestr("sub/factura.xml", (xml_fixtures_dir / "invoice_plain.xml").read_bytes())
        archive.writestr(
            "sub/respuesta.xml", (xml_fixtures_dir / "application_response.xml").read_bytes()
        )
        archive.writestr("roto.xml", b"<Invoice")
    result = source.load([zip_path])
    assert [doc.supplier_number for doc in result.parsed] == ["1001"]
    assert [item.source for item in result.ignored] == [f"{zip_path}::sub/respuesta.xml"]
    assert [item.source for item in result.failed] == [f"{zip_path}::roto.xml"]


def test_corrupt_zip_fails(source: FileDocumentSource, tmp_path: Path) -> None:
    zip_path = tmp_path / "corrupto.zip"
    zip_path.write_bytes(b"not a zip")
    result = source.load([zip_path])
    assert [item.source for item in result.failed] == [str(zip_path)]


def test_zip_member_too_large_fails(tmp_path: Path, xml_fixtures_dir: Path) -> None:
    zip_path = tmp_path / "grande.zip"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("big.xml", b" " * 2048)
    zip_path.write_bytes(buffer.getvalue())
    source = FileDocumentSource(LxmlDianParser(), max_member_bytes=1024)
    result = source.load([zip_path])
    assert [item.source for item in result.failed] == [f"{zip_path}::big.xml"]


def test_missing_path_fails(source: FileDocumentSource, tmp_path: Path) -> None:
    missing = tmp_path / "no-existe.xml"
    result = source.load([missing])
    assert [item.source for item in result.failed] == [str(missing)]


def test_explicit_unsupported_extension_is_ignored(
    source: FileDocumentSource, tmp_path: Path
) -> None:
    pdf = tmp_path / "factura.pdf"
    pdf.write_bytes(b"%PDF")
    result = source.load([pdf])
    assert [item.source for item in result.ignored] == [str(pdf)]


def test_multiple_paths_are_combined(source: FileDocumentSource, xml_fixtures_dir: Path) -> None:
    result = source.load(
        [xml_fixtures_dir / "invoice_mixed_iva.xml", xml_fixtures_dir / "credit_note.xml"]
    )
    assert [doc.supplier_number for doc in result.parsed] == ["1003", "125"]


class RecordingParser:
    """Wraps the real parser and records the order of events."""

    def __init__(self, events: list[tuple[object, ...]]) -> None:
        self._events = events
        self._parser = LxmlDianParser()

    def parse(self, content: bytes, source_file: Path) -> ParsedDocument:
        self._events.append(("parse", source_file.name))
        return self._parser.parse(content, source_file)


def mixed_folder(xml_fixtures_dir: Path, tmp_path: Path) -> Path:
    folder = tmp_path / "entrada"
    folder.mkdir()
    for name in ("invoice_plain.xml", "credit_note.xml", "invoices_bundle.zip"):
        (folder / name).write_bytes((xml_fixtures_dir / name).read_bytes())
    (folder / "factura.pdf").write_bytes(b"%PDF-1.4")
    return folder


def test_reports_progress_per_xml_including_zip_members(
    source: FileDocumentSource, xml_fixtures_dir: Path, tmp_path: Path
) -> None:
    progress: list[tuple[int, int]] = []

    result = source.load(
        [mixed_folder(xml_fixtures_dir, tmp_path)],
        on_progress=lambda done, total: progress.append((done, total)),
    )

    assert len(result.parsed) == 4
    assert progress == [(0, 4), (1, 4), (2, 4), (3, 4), (4, 4)]


def test_lists_every_file_before_parsing(xml_fixtures_dir: Path, tmp_path: Path) -> None:
    events: list[tuple[object, ...]] = []
    source = FileDocumentSource(RecordingParser(events))

    source.load(
        [mixed_folder(xml_fixtures_dir, tmp_path)],
        on_progress=lambda done, total: events.append(("progress", done, total)),
    )

    assert events[0] == ("progress", 0, 4)
    assert [event[0] for event in events[1:]] == ["parse", "progress"] * 4


def test_cancel_stops_before_the_next_file(xml_fixtures_dir: Path, tmp_path: Path) -> None:
    events: list[tuple[object, ...]] = []
    source = FileDocumentSource(RecordingParser(events))

    with pytest.raises(ImportCancelledError):
        source.load(
            [mixed_folder(xml_fixtures_dir, tmp_path)],
            is_cancelled=lambda: any(event[0] == "parse" for event in events),
        )

    assert [event for event in events if event[0] == "parse"] == [("parse", "credit_note.xml")]


def test_cancel_while_listing_parses_nothing(xml_fixtures_dir: Path, tmp_path: Path) -> None:
    events: list[tuple[object, ...]] = []
    source = FileDocumentSource(RecordingParser(events))

    with pytest.raises(ImportCancelledError):
        source.load([mixed_folder(xml_fixtures_dir, tmp_path)], is_cancelled=lambda: True)

    assert events == []


def test_unreadable_zip_counts_as_one_step(source: FileDocumentSource, tmp_path: Path) -> None:
    broken = tmp_path / "roto.zip"
    broken.write_bytes(b"not a zip")
    progress: list[tuple[int, int]] = []

    result = source.load([broken], on_progress=lambda done, total: progress.append((done, total)))

    assert [item.source for item in result.failed] == [str(broken)]
    assert progress == [(0, 1), (1, 1)]
