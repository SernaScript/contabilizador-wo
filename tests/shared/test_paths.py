from pathlib import Path

import pytest

from contabilizador.shared import paths


def test_data_dir_can_be_overridden_by_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "datos"
    monkeypatch.setenv(paths.DATA_DIR_ENV_VAR, str(target))
    assert paths.user_data_dir() == target
    assert target.is_dir()


def test_default_database_lives_in_data_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(paths.DATA_DIR_ENV_VAR, str(tmp_path))
    assert paths.default_database_path() == tmp_path / paths.DATABASE_FILENAME


def test_default_data_dir_uses_platformdirs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(paths.DATA_DIR_ENV_VAR, raising=False)
    monkeypatch.setattr(paths, "_ensure_dir", lambda path: path)
    assert paths.user_data_dir().name == paths.APP_NAME
