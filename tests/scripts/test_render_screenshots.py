"""The screenshot script renders every reviewed state of the real window from a seeded
temporary database (offscreen, synchronous task runner)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "render_screenshots.py"

EXPECTED = {
    "01-first-run.png": (1280, 820),
    "02-invoices-empty.png": (1280, 820),
    "03-invoices-with-data.png": (1280, 820),
    "03-invoices-with-data-1024.png": (1024, 700),
    "03b-invoices-hover-affordance.png": (1280, 820),
    "04-invoices-expanded-with-detail-panel.png": (1280, 820),
    "05-invoices-bulk-selection.png": (1280, 820),
    "06-supplier-wizard.png": (1280, 820),
    "07-export-sheet.png": (1280, 820),
    "07b-export-sheet-with-mismatch.png": (1280, 820),
    "08-export-success.png": (1280, 820),
    "09-suppliers.png": (1280, 820),
    "10-catalogs.png": (1280, 820),
    "11-batches.png": (1280, 820),
    "12-company.png": (1280, 820),
    "13-shortcuts.png": (1280, 820),
}


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("render_screenshots", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_renders_every_state_at_its_size(qapp: QApplication, tmp_path: Path) -> None:
    script = _load_script()

    written = script.render(tmp_path / "shots")

    assert sorted(path.name for path in written) == sorted(EXPECTED)
    for path in written:
        image = QImage(str(path))
        assert not image.isNull(), path.name
        assert (image.width(), image.height()) == EXPECTED[path.name], path.name


def test_main_writes_into_the_folder_it_gets(qapp: QApplication, tmp_path: Path) -> None:
    script = _load_script()

    assert script.main(["--out", str(tmp_path / "out")]) == 0
    assert len(list((tmp_path / "out").glob("*.png"))) == len(EXPECTED)
