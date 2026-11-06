from decimal import Decimal

from contabilizador.invoices.application.list_pending_documents import ListPendingDocuments
from contabilizador.invoices.domain.document import DocumentKind, ParsedLine
from contabilizador.invoices.domain.mapping import LineMapping, MappingKey
from contabilizador.invoices.domain.status import InvoiceStatus
from contabilizador.invoices.domain.suggestion import MappingSource
from contabilizador.suppliers.domain.supplier_config import SupplierConfig
from tests.invoices.application.fakes import (
    FakeInvoiceRepository,
    FakeMappingMemory,
    FakeSupplierConfigs,
)
from tests.invoices.factories import make_document

COMPANY = 1
CONFIGURED_NIT = "900123456"
UNCONFIGURED_NIT = "800987654"


def build() -> tuple[ListPendingDocuments, FakeInvoiceRepository, FakeMappingMemory]:
    repo = FakeInvoiceRepository()
    memory = FakeMappingMemory()
    suppliers = FakeSupplierConfigs(
        SupplierConfig(COMPANY, CONFIGURED_NIT, "COMERCIALIZADORA", ("P-01", "P-02"), "P-02")
    )
    return ListPendingDocuments(repo, memory, suppliers), repo, memory


def test_lists_pending_and_released_only() -> None:
    use_case, repo, _ = build()
    repo.add(COMPANY, make_document(cufe="pending"))
    repo.add(COMPANY, make_document(cufe="exported"))
    repo.add(COMPANY, make_document(cufe="released"))
    repo.add(2, make_document(cufe="other-company"))
    repo.set_status(COMPANY, ["exported"], InvoiceStatus.EXPORTED)
    repo.set_status(COMPANY, ["released"], InvoiceStatus.RELEASED)
    result = use_case.execute(COMPANY)
    assert [d.invoice.document.cufe for d in result.documents] == ["pending", "released"]


def test_suggestions_follow_priority() -> None:
    use_case, repo, memory = build()
    document = make_document(
        cufe="a",
        lines=(
            ParsedLine("Resma Papel", Decimal("1"), Decimal("10"), Decimal("0")),
            ParsedLine("TONER", Decimal("1"), Decimal("10"), Decimal("0")),
            ParsedLine("SILLA", Decimal("1"), Decimal("10"), Decimal("0")),
        ),
        payable_amount=Decimal("30"),
    )
    invoice_id = repo.add(COMPANY, document)
    stored = repo.get(COMPANY, invoice_id)
    assert stored is not None
    repo.assign_line(stored.lines[2].id, LineMapping("P-01", "CC-1"))
    memory.remember(MappingKey(COMPANY, CONFIGURED_NIT, "resma papel"), LineMapping("P-01", "CC-9"))

    (pending,) = use_case.execute(COMPANY).documents
    assert pending.supplier_configured
    assert [(ln.suggestion.source, ln.suggestion.mapping) for ln in pending.lines] == [
        (MappingSource.MEMORY, LineMapping("P-01", "CC-9")),
        (MappingSource.SUPPLIER_DEFAULT, LineMapping("P-02", None)),
        (MappingSource.ASSIGNED, LineMapping("P-01", "CC-1")),
    ]
    assert pending.is_fully_mapped
    assert pending.totals.matches
    assert pending.header_note == "Resma Papel & TONER & SILLA"


def test_unconfigured_supplier_has_no_default_and_is_reported() -> None:
    use_case, repo, _ = build()
    repo.add(COMPANY, make_document(cufe="a", supplier_nit=UNCONFIGURED_NIT, supplier_name="DEMO"))
    repo.add(COMPANY, make_document(cufe="b", supplier_nit=UNCONFIGURED_NIT, supplier_name="DEMO"))
    repo.add(COMPANY, make_document(cufe="c"))
    result = use_case.execute(COMPANY)
    unconfigured = result.documents[0]
    assert not unconfigured.supplier_configured
    assert not unconfigured.is_fully_mapped
    assert {ln.suggestion.source for ln in unconfigured.lines} == {MappingSource.NONE}
    assert [(s.nit, s.name) for s in result.unconfigured_suppliers] == [(UNCONFIGURED_NIT, "DEMO")]


def test_totals_mismatch_is_exposed() -> None:
    use_case, repo, _ = build()
    repo.add(COMPANY, make_document(cufe="a", payable_amount=Decimal("1")))
    (pending,) = use_case.execute(COMPANY).documents
    assert not pending.totals.matches


def test_cost_center_only_assignment_falls_back_to_supplier_default_product() -> None:
    use_case, repo, _ = build()
    invoice_id = repo.add(COMPANY, make_document(cufe="a"))
    stored = repo.get(COMPANY, invoice_id)
    assert stored is not None
    repo.assign_line(stored.lines[0].id, LineMapping("", "CC-1"))

    (pending,) = use_case.execute(COMPANY).documents

    assert pending.lines[0].suggestion.mapping == LineMapping("P-02", "CC-1")


def test_cost_center_only_assignment_still_uses_mapping_memory() -> None:
    use_case, repo, memory = build()
    invoice_id = repo.add(COMPANY, make_document(cufe="a"))
    stored = repo.get(COMPANY, invoice_id)
    assert stored is not None
    repo.assign_line(stored.lines[0].id, LineMapping("", "CC-1"))
    memory.remember(
        MappingKey(COMPANY, CONFIGURED_NIT, "resma papel carta 75g"), LineMapping("P-01", "CC-9")
    )

    (pending,) = use_case.execute(COMPANY).documents

    assert pending.lines[0].suggestion.mapping == LineMapping("P-01", "CC-1")


def test_reads_the_mapping_memory_once() -> None:
    use_case, repo, memory = build()
    for cufe in ("a", "b", "c"):
        repo.add(COMPANY, make_document(cufe=cufe))

    use_case.execute(COMPANY)

    assert memory.get_many_calls == 1


def test_credit_notes_report_whether_their_original_invoice_is_stored() -> None:
    use_case, repo, _ = build()
    repo.add(COMPANY, make_document(cufe="inv-exported"))
    repo.set_status(COMPANY, ["inv-exported"], InvoiceStatus.EXPORTED)
    repo.add(COMPANY, make_document(cufe="inv-pending"))
    repo.add(2, make_document(cufe="inv-other-company"))
    for cufe, reference in (
        ("nc-exported", "inv-exported"),
        ("nc-pending", "inv-pending"),
        ("nc-missing", "missing"),
        ("nc-no-reference", None),
        ("nc-other-company", "inv-other-company"),
    ):
        repo.add(
            COMPANY,
            make_document(
                cufe=cufe, kind=DocumentKind.CREDIT_NOTE, billing_reference_cufe=reference
            ),
        )

    documents = use_case.execute(COMPANY).documents

    assert {d.invoice.document.cufe: d.original_found for d in documents} == {
        "inv-pending": None,
        "nc-exported": True,
        "nc-pending": True,
        "nc-missing": False,
        "nc-no-reference": False,
        "nc-other-company": False,
    }
