# Contabilizador WO

Desktop tool (macOS and Windows) that reads DIAN electronic purchase documents (UBL 2.1
`Invoice`, `CreditNote`, and `AttachedDocument` wrappers), lets you map every XML line to
a World Office **product** and **cost center**, and generates the official World Office
purchase import workbook (`Encabezados` + `Movimiento inventarios`).

## Requirements

- Python 3.12 (pinned in `.python-version`)
- [uv](https://docs.astral.sh/uv/)

## Setup

```bash
uv sync            # installs runtime and dev dependencies into .venv
```

## Run

```bash
uv run contabilizador
```

The SQLite database lives in the per-user data directory (`platformdirs`), e.g.
`~/Library/Application Support/ContabilizadorWO/contabilizador.db` on macOS or
`%LOCALAPPDATA%\WeAreDev\ContabilizadorWO\contabilizador.db` on Windows. Set
`CONTABILIZADOR_DATA_DIR` to use another folder (portable installs, tests).
Migrations run automatically at startup.

Typical monthly flow (the window has a sidebar with **Facturas**, **Proveedores**,
**Catálogos**, **Lotes exportados** and **Empresa**; the company switcher sits on top of it):

1. First run opens **Primeros pasos**, a three-step checklist: create the company (name
   exactly as World Office expects it, internal third party; warehouse, unit and payment
   form stay editable later under *Valores por defecto* in **Empresa**), load the
   catalogs, import invoices. Until a company exists every action that needs one says so
   instead of doing nothing.
2. **Catálogos**: products and cost centers (segmented control), manual entry or
   *Importar desde Excel* (first sheet, header row, column A code, column B name);
   *Descargar plantilla* writes an empty workbook with the expected headers.
3. **Facturas**: *Importar* (XML files, zips or a folder; drag and drop anywhere on the
   window works too). The import runs in the background with progress and *Cancelar*
   (nothing is stored when cancelled) and ends with a toast plus a report of ignored or
   failed files.
4. The banner *Configurar proveedores* opens the supplier wizard: one supplier at a time,
   its pending lines as context, the allowed products and the default (star).
5. Complete product and cost center on the invoice row (applies to every line), on a
   single line, or for several invoices with the bulk bar. Manual choices are remembered
   per supplier item and suggested next time; *Restablecer sugerencia* undoes one.
6. The readiness footer counts ready, incomplete, blocked and mismatched invoices;
   *Exportar N facturas* exports only the exportable ones (or the exportable part of the
   selection). The export sheet shows each document type with its first consecutive
   (last used + 1), a live warning when the numbers collide with an earlier batch, a
   required confirmation for totals mismatches and the destination file.
7. **Lotes exportados** lists every batch; void a batch (the confirmation says whether the
   consecutives come back) or release selected invoices to export them again.

Keyboard: Ctrl/Cmd+O import files, Ctrl/Cmd+Shift+O import a folder, Ctrl/Cmd+E export,
Ctrl/Cmd+F search, Ctrl/Cmd+1..5 pages, Ctrl/Cmd+/ the shortcuts sheet, Space expands an
invoice, Esc clears the selection. Window size, last company, detail panel and splitters
are remembered (`QSettings`).

## Test and lint

```bash
uv run pytest            # unit, integration (SQLite in tmp), golden workbook, pytest-qt UI
uv run ruff check
uv run ruff format --check
uv run pyright
```

UI tests run headless (`QT_QPA_PLATFORM=offscreen` is set in `tests/conftest.py`).
`tests/ui/conftest.py` keeps widgets alive until each test is torn down and then deletes
them, and points `QSettings` at a temporary folder (tests never touch real preferences).

### Screenshots for visual review

```bash
QT_QPA_PLATFORM=offscreen uv run python scripts/render_screenshots.py --out shots/
```

Seeds a temporary database (catalogs, the XML fixtures plus generated variants with every
readiness state, one exported batch) and saves PNGs of the real window: first run, empty
and populated Facturas (also at 1024x700), detail panel, bulk selection, supplier wizard,
export sheet and its success state, and the other pages.

### Database migrations

```bash
uv run alembic -x db=/tmp/scratch.db upgrade head
uv run alembic -x db=/tmp/scratch.db revision --autogenerate -m "describe change"
```

`tests/shared/test_migrations.py` fails if the ORM metadata drifts from the migrations.

## Architecture

Screaming + hexagonal. Each business module has three layers; `domain/` is pure Python
(no Qt, SQLAlchemy, openpyxl, lxml; enforced by `tests/test_smoke.py`).

```
src/contabilizador/
  companies/   company and its World Office export defaults
  suppliers/   supplier configuration per company + NIT (allowed products, default)
  catalog/     products and cost centers, Excel import
  invoices/    DIAN XML parsing, CUFE dedup, line mapping memory, totals check
  exports/     consecutives, batches (void/release), World Office workbook writer
  shared/      SQLAlchemy base/engine, Alembic migrations, user paths, Spanish UI copy
  ui/          PySide6 shell, pages, widgets, theme (see below)
```

| Layer            | Contents                                                         |
| ---------------- | ---------------------------------------------------------------- |
| `domain/`        | entities, value objects, domain rules (`Decimal` money)          |
| `application/`   | use cases and ports (`typing.Protocol`)                          |
| `infrastructure/`| SQLAlchemy repositories/ORM, lxml parser, openpyxl reader/writer |

Cross-module seams:

- `exports/application/ports.py` declares narrow reader protocols that the companies,
  suppliers, catalog and invoices repositories satisfy structurally.
- `exports/infrastructure/invoice_candidate_source.py` adapts stored invoices (with their
  effective line mapping: manual > memory > supplier default) into export candidates.
- `ui/composition.py` (`build_services`) is the only place that picks adapters; it runs
  migrations and wires every use case into a `Services` object the window receives.

### UI

```
ui/
  app.py            entry point: translator (Spanish Qt buttons), fonts, theme, task runner
  composition.py    build_services: the only place that picks adapters
  main_window.py    shell: sidebar + company switcher, stacked pages, toasts, window-wide
                    drop overlay, global shortcuts; wires the pages to each other
  pages/<area>/     invoices, export (sheet), suppliers (page + wizard), catalogs, batches,
                    company (page + new company flow), onboarding (Primeros pasos)
                    container.py runs use cases; view.py and the other widgets only receive
                    data and emit signals; rows.py / model.py hold pure view models
  widgets/          presentational building blocks (sidebar, status pill, toast, banner,
                    empty state, overlays, readiness bar, chips, code combo, stepper, sheet)
  dialogs/          shortcuts sheet
  theme.py          design tokens and the stylesheet (white version, light forced); styling by
                    dynamic properties (variant, role, status), contrast tested (WCAG AA)
  tasks.py          QtTaskRunner: one background thread, so database access is serialized;
                    results come back on the GUI thread and are dropped when the asking
                    widget is gone. SyncTaskRunner runs inline for tests
  errors.py         ErrorPresenter: every application error as Spanish copy (what happened
                    and how to fix it); technical text only in the details
  settings.py, actions.py, icons.py, fonts.py, formatting.py
```

Pages never import each other: each container exposes `set_company`, `refresh` and
signals (`changed`, `badge_changed`, `navigate_requested` plus its own requests) and
`main_window.py` connects them. Readiness (pills, footer, export) has one source:
`PreviewExport`, the same assessment `ExportBatch` applies. Every result of a background
task carries a `(company, generation)` token so a late answer for another company is
dropped. All user-facing copy is Spanish and lives in `shared/strings/` (one module per
area, re-exported by the package; a test fails if a name is defined twice).

Bundled assets: IBM Plex Sans (`ui/assets/fonts`, SIL Open Font License, `OFL.txt`; the
system font is used if it cannot be registered) and a subset of Lucide icons
(`ui/assets/icons`, ISC license, `LICENSE`), tinted at runtime with the theme tokens.

Key rules encoded in the domain:

- `Valor = LineExtensionAmount / InvoicedQuantity`, `Iva % = Percent / 100`.
- Σ qty·valor·(1+iva) must match the XML `PayableAmount` within ±1 COP, otherwise the
  document is flagged and the export asks for confirmation.
- Credit notes are exported as `NC` with positive values; invoices as `FC`.
- Documents are unique per (company, CUFE); states `pending` → `exported` → `released`.
- Consecutives are per (company, document type); only voiding the **last** batch gives
  its numbers back.

## Fixtures

`tests/fixtures/xml/` holds synthetic, anonymized DIAN documents (see
`tests/fixtures/README.md` for the expected parse values) and
`tests/fixtures/world_office_golden.xlsx` is the official workbook the writer is compared
against cell by cell.
