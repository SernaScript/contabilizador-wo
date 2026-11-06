"""AppSettings over an injectable QSettings (tests use a temporary INI file)."""

from pathlib import Path

from PySide6.QtCore import QByteArray, QSettings

from contabilizador.ui.settings import AppSettings


def test_defaults_when_nothing_is_stored(tmp_path: Path, qapp) -> None:
    settings = AppSettings.in_file(tmp_path / "settings.ini")

    assert settings.last_company_id is None
    assert settings.window_geometry is None
    assert settings.window_state is None
    assert settings.detail_panel_visible is False
    assert settings.splitter_state("main") is None
    assert settings.last_export_folder is None
    assert settings.last_import_folder is None


def test_values_round_trip_through_the_ini_file(tmp_path: Path, qapp) -> None:
    path = tmp_path / "settings.ini"
    first = AppSettings.in_file(path)
    first.last_company_id = 7
    first.window_geometry = QByteArray(b"geom")
    first.window_state = QByteArray(b"state")
    first.detail_panel_visible = True
    first.set_splitter_state("main", QByteArray(b"split"))
    first.last_export_folder = tmp_path / "exports"
    first.last_import_folder = tmp_path / "xml"
    first.sync()

    second = AppSettings.in_file(path)

    assert second.last_company_id == 7
    assert second.window_geometry == QByteArray(b"geom")
    assert second.window_state == QByteArray(b"state")
    assert second.detail_panel_visible is True
    assert second.splitter_state("main") == QByteArray(b"split")
    assert second.last_export_folder == tmp_path / "exports"
    assert second.last_import_folder == tmp_path / "xml"
    assert path.is_file()


def test_setting_none_clears_the_key(tmp_path: Path, qapp) -> None:
    settings = AppSettings.in_file(tmp_path / "settings.ini")
    settings.last_company_id = 3
    settings.last_company_id = None
    settings.last_export_folder = tmp_path
    settings.last_export_folder = None

    assert settings.last_company_id is None
    assert settings.last_export_folder is None


def test_corrupt_company_id_reads_as_none(tmp_path: Path, qapp) -> None:
    path = tmp_path / "settings.ini"
    path.write_text("[app]\nlast_company_id=abc\n", encoding="utf-8")

    assert AppSettings.in_file(path).last_company_id is None


def test_default_settings_follow_the_default_format_and_path(qapp, qsettings_dir: Path) -> None:
    # Las pruebas cambian el formato y la ruta por defecto: nunca se tocan las preferencias
    # reales de quien las ejecuta (la app sigue usando el formato nativo)
    settings = AppSettings()

    assert settings.qsettings.format() == QSettings.defaultFormat()
    assert settings.qsettings.scope() == QSettings.Scope.UserScope
    assert Path(settings.qsettings.fileName()).is_relative_to(qsettings_dir)
