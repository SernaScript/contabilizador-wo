"""Rows of the Proveedores page and the wizard context (pure, no Qt)."""

from decimal import Decimal

from contabilizador.invoices.application.list_pending_documents import PendingDocument
from contabilizador.suppliers.domain.supplier_config import SupplierConfig
from contabilizador.ui.pages.suppliers.rows import (
    ContextLine,
    SupplierRow,
    build_context,
    build_rows,
    fold,
)
from tests.ui.factories import make_pending_document, make_pending_documents

COMPANY = 1


def config(
    nit: str, name: str, codes: tuple[str, ...] = ("P-1",), default: str | None = None
) -> SupplierConfig:
    return SupplierConfig(COMPANY, nit, name, codes, default or codes[0])


def pending(
    invoice_id: int, nit: str, name: str, *, configured: bool, cufe: str | None = None
) -> PendingDocument:
    return make_pending_document(
        invoice_id=invoice_id,
        cufe=cufe or f"cufe-{invoice_id}",
        supplier_configured=configured,
        supplier_nit=nit,
        supplier_name=name,
    )


def test_fold_ignores_case_and_accents() -> None:
    assert fold("Papelería ÁBC") == fold("papeleria abc")


def test_unconfigured_suppliers_come_first_then_configured_by_name() -> None:
    documents = make_pending_documents(
        pending(1, "900", "Zeta S.A.S.", configured=False),
        pending(2, "800", "Alfa Ltda.", configured=False),
    )
    configs = [config("700", "Beta Ltda."), config("600", "Álamo S.A.S.")]

    rows = build_rows(configs, documents, {"P-1"})

    assert [(row.nit, row.configured) for row in rows] == [
        ("800", False),
        ("900", False),
        ("600", True),
        ("700", True),
    ]


def test_pending_invoices_are_counted_per_supplier_in_both_states() -> None:
    documents = make_pending_documents(
        pending(1, "900", "Zeta", configured=False),
        pending(2, "900", "Zeta", configured=False),
        pending(3, "700", "Beta", configured=True),
    )

    rows = {
        row.nit: row
        for row in build_rows([config("700", "Beta"), config("600", "Alfa")], documents, {"P-1"})
    }

    assert rows["900"].pending_invoices == 2
    assert rows["700"].pending_invoices == 1
    assert rows["600"].pending_invoices == 0


def test_configured_row_keeps_products_default_and_flags_missing_codes() -> None:
    configs = [config("700", "Beta", ("P-1", "P-2", "P-3"), default="P-2")]

    (row,) = build_rows(configs, make_pending_documents(), {"P-1", "P-3"})

    assert row.configured
    assert row.product_codes == ("P-1", "P-2", "P-3")
    assert row.default_product_code == "P-2"
    assert row.missing_codes == ("P-2",)


def test_supplier_configured_after_the_pending_read_is_listed_once() -> None:
    documents = make_pending_documents(pending(1, "700", "Beta", configured=False))

    rows = build_rows([config("700", "Beta")], documents, {"P-1"})

    assert [(row.nit, row.configured) for row in rows] == [("700", True)]


def test_unconfigured_row_has_no_products() -> None:
    documents = make_pending_documents(pending(1, "900", "Zeta", configured=False))

    (row,) = build_rows([], documents, set())

    assert row == SupplierRow("900", "Zeta", configured=False, pending_invoices=1)


def test_row_matches_nit_or_name_ignoring_case_and_accents() -> None:
    row = SupplierRow("900123456", "Papelería del Norte", configured=True)

    assert row.matches("")
    assert row.matches("  ")
    assert row.matches("9001")
    assert row.matches("PAPELERIA")
    assert row.matches("del norte")
    assert not row.matches("aseo")


def test_context_lists_the_pending_lines_of_one_supplier_only() -> None:
    documents = make_pending_documents(
        pending(1, "900", "Zeta", configured=False),
        pending(2, "700", "Beta", configured=True),
    )

    context = build_context(documents, "900")

    assert [item.description for item in context] == [
        "RESMA PAPEL CARTA 75G",
        "TONER IMPRESORA LASER",
    ]
    assert context[0] == ContextLine(
        document="FEV-001001", description="RESMA PAPEL CARTA 75G", amount=Decimal("30000.00")
    )


def test_context_of_unknown_supplier_is_empty() -> None:
    documents = make_pending_documents(pending(1, "900", "Zeta", configured=False))

    assert build_context(documents, "123") == ()
