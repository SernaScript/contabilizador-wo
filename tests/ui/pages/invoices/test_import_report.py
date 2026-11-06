"""Import report dialog: duplicates, ignored and failed files, orphan credit notes."""

from contabilizador.invoices.application.import_invoice_files import (
    ImportedDocument,
    ImportReport,
)
from contabilizador.invoices.domain.document import DocumentKind
from contabilizador.invoices.domain.source import SkippedFile
from contabilizador.shared import strings
from contabilizador.ui.pages.invoices.import_report import ImportReportDialog, has_details
from tests.invoices.factories import make_document


def _full_report() -> ImportReport:
    imported = make_document(cufe="cufe-new", supplier_number="001010")
    duplicate = make_document(cufe="cufe-dup", supplier_number="001001")
    orphan = make_document(
        cufe="cude-9",
        kind=DocumentKind.CREDIT_NOTE,
        supplier_prefix="NC",
        supplier_number="9",
        billing_reference_cufe="718b2e03aaaabbbb",
    )
    return ImportReport(
        imported=(ImportedDocument(1, imported), ImportedDocument(2, orphan)),
        duplicates=(duplicate,),
        ignored=(SkippedFile("respuesta.xml", "No es una factura ni una nota crédito"),),
        failed=(SkippedFile("roto.xml", "XML incompleto"),),
        credit_notes_without_original=(orphan,),
    )


def test_report_dialog_lists_every_section_with_reasons(qtbot) -> None:
    report = _full_report()
    assert has_details(report) is True
    dialog = ImportReportDialog(report)
    qtbot.addWidget(dialog)

    assert dialog.windowTitle() == strings.IMPORT_REPORT_TITLE
    assert dialog.summary_label.text() == strings.import_result_sentence(2, 1, 1, 1)
    assert list(dialog.sections) == [
        strings.IMPORT_REPORT_DUPLICATES,
        strings.IMPORT_REPORT_IGNORED,
        strings.IMPORT_REPORT_FAILED,
        strings.IMPORT_REPORT_ORPHANS,
    ]
    assert dialog.sections[strings.IMPORT_REPORT_DUPLICATES].text() == strings.duplicate_detail(
        "FEV-001001", "COMERCIALIZADORA EJEMPLO S.A.S."
    )
    assert dialog.sections[strings.IMPORT_REPORT_IGNORED].text() == (
        "respuesta.xml: No es una factura ni una nota crédito"
    )
    assert dialog.sections[strings.IMPORT_REPORT_FAILED].text() == "roto.xml: XML incompleto"
    assert dialog.sections[strings.IMPORT_REPORT_ORPHANS].text() == (
        strings.orphan_credit_note_detail("NC-9", "718b2e03aaaabbbb")
    )
    assert dialog.primary_button.text() == strings.ACTION_CLOSE
    assert dialog.cancel_button.isHidden()


def test_report_without_incidents_says_so(qtbot) -> None:
    report = ImportReport(
        imported=(ImportedDocument(1, make_document()),),
        duplicates=(),
        ignored=(),
        failed=(),
        credit_notes_without_original=(),
    )
    assert has_details(report) is False
    dialog = ImportReportDialog(report)
    qtbot.addWidget(dialog)

    assert dialog.sections == {}
    assert dialog.empty_label.text() == strings.IMPORT_REPORT_EMPTY
