"""Persisted UI preferences over an injectable ``QSettings`` (tests use a temp INI)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QByteArray, QSettings

ORGANIZATION = "While Corp"
APPLICATION = "Contabilizador WO"

KEY_LAST_COMPANY = "app/last_company_id"
KEY_WINDOW_GEOMETRY = "window/geometry"
KEY_WINDOW_STATE = "window/state"
KEY_DETAIL_VISIBLE = "invoices/detail_panel_visible"
KEY_SPLITTER_PREFIX = "splitters/"
KEY_LAST_EXPORT_FOLDER = "export/last_folder"
KEY_LAST_IMPORT_FOLDER = "import/last_folder"


class AppSettings:
    def __init__(self, settings: QSettings | None = None) -> None:
        # defaultFormat(): nativo en la app; las pruebas lo cambian por INI en una carpeta
        # temporal (el constructor de dos argumentos siempre usaria el formato nativo)
        self._settings = settings or QSettings(
            QSettings.defaultFormat(), QSettings.Scope.UserScope, ORGANIZATION, APPLICATION
        )

    @classmethod
    def in_file(cls, path: Path) -> AppSettings:
        return cls(QSettings(str(path), QSettings.Format.IniFormat))

    @property
    def qsettings(self) -> QSettings:
        return self._settings

    def sync(self) -> None:
        self._settings.sync()

    # --- helpers -----------------------------------------------------------
    def _set_or_remove(self, key: str, value: object | None) -> None:
        if value is None:
            self._settings.remove(key)
        else:
            self._settings.setValue(key, value)

    def _bytes(self, key: str) -> QByteArray | None:
        value = self._settings.value(key)
        if isinstance(value, QByteArray) and not value.isEmpty():
            return value
        if isinstance(value, bytes | bytearray) and value:
            return QByteArray(bytes(value))
        return None

    def _path(self, key: str) -> Path | None:
        value = self._settings.value(key)
        return Path(str(value)) if isinstance(value, str) and value else None

    # --- valores -----------------------------------------------------------
    @property
    def last_company_id(self) -> int | None:
        value = self._settings.value(KEY_LAST_COMPANY)
        try:
            return int(value) if value not in (None, "") else None
        except (TypeError, ValueError):
            return None

    @last_company_id.setter
    def last_company_id(self, value: int | None) -> None:
        self._set_or_remove(KEY_LAST_COMPANY, value)

    @property
    def window_geometry(self) -> QByteArray | None:
        return self._bytes(KEY_WINDOW_GEOMETRY)

    @window_geometry.setter
    def window_geometry(self, value: QByteArray | None) -> None:
        self._set_or_remove(KEY_WINDOW_GEOMETRY, value)

    @property
    def window_state(self) -> QByteArray | None:
        return self._bytes(KEY_WINDOW_STATE)

    @window_state.setter
    def window_state(self, value: QByteArray | None) -> None:
        self._set_or_remove(KEY_WINDOW_STATE, value)

    @property
    def detail_panel_visible(self) -> bool:
        # Cerrado al empezar: la lista de facturas necesita el ancho hasta elegir una
        value = self._settings.value(KEY_DETAIL_VISIBLE, False)
        if isinstance(value, str):
            return value.lower() not in ("false", "0", "")
        return bool(value)

    @detail_panel_visible.setter
    def detail_panel_visible(self, value: bool) -> None:
        self._settings.setValue(KEY_DETAIL_VISIBLE, bool(value))

    def splitter_state(self, name: str) -> QByteArray | None:
        return self._bytes(f"{KEY_SPLITTER_PREFIX}{name}")

    def set_splitter_state(self, name: str, state: QByteArray | None) -> None:
        self._set_or_remove(f"{KEY_SPLITTER_PREFIX}{name}", state)

    @property
    def last_export_folder(self) -> Path | None:
        return self._path(KEY_LAST_EXPORT_FOLDER)

    @last_export_folder.setter
    def last_export_folder(self, value: Path | None) -> None:
        self._set_or_remove(KEY_LAST_EXPORT_FOLDER, str(value) if value is not None else None)

    @property
    def last_import_folder(self) -> Path | None:
        return self._path(KEY_LAST_IMPORT_FOLDER)

    @last_import_folder.setter
    def last_import_folder(self, value: Path | None) -> None:
        self._set_or_remove(KEY_LAST_IMPORT_FOLDER, str(value) if value is not None else None)
