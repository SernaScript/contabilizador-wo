import os
from pathlib import Path

import pytest

# Qt sin pantalla: debe definirse antes de crear QApplication (macOS/Windows/CI)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def xml_fixtures_dir() -> Path:
    return FIXTURES_DIR / "xml"


@pytest.fixture
def golden_workbook_path() -> Path:
    return FIXTURES_DIR / "world_office_golden.xlsx"
