"""Per-user application paths (macOS/Windows/Linux) via platformdirs."""

import os
from pathlib import Path

import platformdirs

APP_NAME = "ContabilizadorWO"
APP_AUTHOR = "WeAreDev"
DATABASE_FILENAME = "contabilizador.db"
# Permite apuntar a otra carpeta (pruebas, instalaciones portables)
DATA_DIR_ENV_VAR = "CONTABILIZADOR_DATA_DIR"


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def user_data_dir() -> Path:
    override = os.environ.get(DATA_DIR_ENV_VAR)
    if override:
        return _ensure_dir(Path(override))
    return _ensure_dir(Path(platformdirs.user_data_dir(APP_NAME, APP_AUTHOR)))


def default_database_path() -> Path:
    return user_data_dir() / DATABASE_FILENAME
