import pytest

from contabilizador.invoices.application.assign_document_mapping import AssignDocumentMapping
from contabilizador.invoices.application.errors import (
    DocumentNotEditableError,
    InvoiceNotFoundError,
    LineNotFoundError,
)
from contabilizador.invoices.domain.mapping import LineMapping
from contabilizador.invoices.domain.normalization import mapping_key_for
from contabilizador.invoices.domain.status import InvoiceStatus
from contabilizador.invoices.domain.stored import StoredInvoice
from contabilizador.suppliers.domain.supplier_config import SupplierConfig
from tests.invoices.application.fakes import (
    FakeInvoiceRepository,
    FakeMappingMemory,
    FakeSupplierConfigs,
    FakeUnitOfWork,
)
from tests.invoices.factories import make_document

COMPANY = 1
NIT = "900123456"
UNCONFIGURED_NIT = "800987654"
RESMA = "RESMA PAPEL CARTA 75G"
TONER = "TONER IMPRESORA LASER"


class Context:
    def __init__(self) -> None:
        self.repo = FakeInvoiceRepository()
        self.memory = FakeMappingMemory()
        self.unit_of_work = FakeUnitOfWork()
        self.repo.unit_of_work = self.memory.unit_of_work = self.unit_of_work
        suppliers = FakeSupplierConfigs(
            SupplierConfig(COMPANY, NIT, "COMERCIALIZADORA", ("P-01", "P-02", "P-03"), "P-02")
        )
        self.use_case = AssignDocumentMapping(self.repo, self.memory, suppliers, self.unit_of_work)

    def add(self, cufe: str, **overrides: object) -> int:
        return self.repo.add(COMPANY, make_document(cufe=cufe, **overrides))

    def stored(self, invoice_id: int) -> StoredInvoice:
        stored = self.repo.get(COMPANY, invoice_id)
        assert stored is not None
        return stored

    def assigned(self, invoice_id: int) -> list[LineMapping | None]:
        return [line.assigned for line in self.stored(invoice_id).lines]


@pytest.fixture
def ctx() -> Context:
    return Context()


def test_cost_center_keeps_each_line_product_and_memory_stores_both(ctx: Context) -> None:
    invoice_id = ctx.add("a")
    ctx.memory.remember(mapping_key_for(COMPANY, NIT, RESMA), LineMapping("P-01", "CC-9"))

    ctx.use_case.execute(COMPANY, [invoice_id], cost_center_code="CC-1")

    # linea 1: producto de la memoria; linea 2: producto por defecto del proveedor
    assert ctx.assigned(invoice_id) == [LineMapping("P-01", "CC-1"), LineMapping("P-02", "CC-1")]
    assert ctx.memory.entries == {
        mapping_key_for(COMPANY, NIT, RESMA): LineMapping("P-01", "CC-1"),
        mapping_key_for(COMPANY, NIT, TONER): LineMapping("P-02", "CC-1"),
    }


def test_product_keeps_each_line_cost_center(ctx: Context) -> None:
    invoice_id = ctx.add("a")
    ctx.repo.assign_line(ctx.stored(invoice_id).lines[0].id, LineMapping("P-01", "CC-1"))

    ctx.use_case.execute(COMPANY, [invoice_id], product_code="P-03")

    assert ctx.assigned(invoice_id) == [LineMapping("P-03", "CC-1"), LineMapping("P-03", None)]
    assert ctx.memory.entries == {
        mapping_key_for(COMPANY, NIT, RESMA): LineMapping("P-03", "CC-1"),
        mapping_key_for(COMPANY, NIT, TONER): LineMapping("P-03", None),
    }


def test_both_values_apply_to_every_line_of_every_invoice(ctx: Context) -> None:
    first, second = ctx.add("a"), ctx.add("b")

    ctx.use_case.execute(COMPANY, [first, second], product_code="P-03", cost_center_code="CC-2")

    expected = LineMapping("P-03", "CC-2")
    assert ctx.assigned(first) == ctx.assigned(second) == [expected, expected]


def test_line_without_any_product_keeps_only_the_cost_center(ctx: Context) -> None:
    invoice_id = ctx.add("a", supplier_nit=UNCONFIGURED_NIT)

    ctx.use_case.execute(COMPANY, [invoice_id], cost_center_code="CC-1")

    assert ctx.assigned(invoice_id) == [LineMapping("", "CC-1"), LineMapping("", "CC-1")]
    assert ctx.memory.entries == {}


def test_writes_happen_in_one_transaction(ctx: Context) -> None:
    first, second = ctx.add("a"), ctx.add("b")
    ctx.unit_of_work.writes_outside_transaction.clear()  # solo cuenta el caso de uso

    ctx.use_case.execute(COMPANY, [first, second], cost_center_code="CC-1")

    assert ctx.unit_of_work.transactions == 1
    assert ctx.unit_of_work.writes_outside_transaction == []


def test_unknown_invoice_raises_and_changes_nothing(ctx: Context) -> None:
    invoice_id = ctx.add("a")

    with pytest.raises(InvoiceNotFoundError) as error:
        ctx.use_case.execute(COMPANY, [invoice_id, 999], cost_center_code="CC-1")

    assert error.value.invoice_id == 999
    assert ctx.assigned(invoice_id) == [None, None]
    assert ctx.memory.entries == {}


def test_invoice_of_another_company_is_not_found(ctx: Context) -> None:
    invoice_id = ctx.add("a")

    with pytest.raises(InvoiceNotFoundError):
        ctx.use_case.execute(2, [invoice_id], cost_center_code="CC-1")


def test_exported_invoice_is_not_editable_and_nothing_changes(ctx: Context) -> None:
    editable, exported = ctx.add("a"), ctx.add("b")
    ctx.repo.set_status(COMPANY, ["b"], InvoiceStatus.EXPORTED)

    with pytest.raises(DocumentNotEditableError):
        ctx.use_case.execute(COMPANY, [editable, exported], product_code="P-03")

    assert ctx.assigned(editable) == [None, None]


@pytest.mark.parametrize(
    "values", [{}, {"product_code": None}, {"product_code": "  ", "cost_center_code": ""}]
)
def test_without_values_nothing_happens(ctx: Context, values: dict[str, str | None]) -> None:
    invoice_id = ctx.add("a")

    ctx.use_case.execute(COMPANY, [invoice_id], **values)

    assert ctx.assigned(invoice_id) == [None, None]
    assert ctx.unit_of_work.transactions == 0


# --- una sola linea: el campo editado y lo que la linea tiene ahora en la base ----------


def line_ids(ctx: Context, invoice_id: int) -> list[int]:
    return [line.id for line in ctx.stored(invoice_id).lines]


def test_a_line_edit_keeps_the_other_field_stored_now_not_a_copy_from_the_screen(
    ctx: Context,
) -> None:
    invoice_id = ctx.add("a")
    first, _second = line_ids(ctx, invoice_id)
    # otra edicion ya guardo el producto aunque la pantalla aun no lo muestre
    ctx.repo.assign_line(first, LineMapping("P-01", None))

    ctx.use_case.execute_lines(COMPANY, [first], cost_center_code="CC-1")

    assert ctx.assigned(invoice_id) == [LineMapping("P-01", "CC-1"), None]
    assert ctx.memory.entries == {mapping_key_for(COMPANY, NIT, RESMA): LineMapping("P-01", "CC-1")}


def test_a_line_edit_keeps_the_suggested_values_of_the_other_field(ctx: Context) -> None:
    invoice_id = ctx.add("a")
    first, second = line_ids(ctx, invoice_id)
    ctx.memory.remember(mapping_key_for(COMPANY, NIT, RESMA), LineMapping("P-01", "CC-9"))

    ctx.use_case.execute_lines(COMPANY, [first], product_code="P-03")
    ctx.use_case.execute_lines(COMPANY, [second], cost_center_code="CC-1")

    # linea 1: centro de costo de la memoria; linea 2: producto por defecto del proveedor
    assert ctx.assigned(invoice_id) == [LineMapping("P-03", "CC-9"), LineMapping("P-02", "CC-1")]
    assert ctx.memory.entries == {
        mapping_key_for(COMPANY, NIT, RESMA): LineMapping("P-03", "CC-9"),
        mapping_key_for(COMPANY, NIT, TONER): LineMapping("P-02", "CC-1"),
    }


def test_a_line_without_any_product_keeps_only_the_cost_center(ctx: Context) -> None:
    invoice_id = ctx.add("a", supplier_nit=UNCONFIGURED_NIT)
    first, _second = line_ids(ctx, invoice_id)

    ctx.use_case.execute_lines(COMPANY, [first], cost_center_code="CC-1")

    assert ctx.assigned(invoice_id) == [LineMapping("", "CC-1"), None]
    assert ctx.memory.entries == {}


def test_line_edits_are_written_in_one_transaction(ctx: Context) -> None:
    first_invoice, second_invoice = ctx.add("a"), ctx.add("b")
    chosen = [line_ids(ctx, first_invoice)[0], line_ids(ctx, second_invoice)[1]]
    ctx.unit_of_work.writes_outside_transaction.clear()  # solo cuenta el caso de uso

    ctx.use_case.execute_lines(COMPANY, chosen, cost_center_code="CC-1")

    assert ctx.unit_of_work.transactions == 1
    assert ctx.unit_of_work.writes_outside_transaction == []
    assert ctx.assigned(first_invoice) == [LineMapping("P-02", "CC-1"), None]
    assert ctx.assigned(second_invoice) == [None, LineMapping("P-02", "CC-1")]


def test_an_unknown_line_raises_and_changes_nothing(ctx: Context) -> None:
    invoice_id = ctx.add("a")
    first, _second = line_ids(ctx, invoice_id)

    with pytest.raises(LineNotFoundError):
        ctx.use_case.execute_lines(COMPANY, [first, 999], cost_center_code="CC-1")

    assert ctx.assigned(invoice_id) == [None, None]
    assert ctx.memory.entries == {}


def test_a_line_of_another_company_is_not_found(ctx: Context) -> None:
    first, _second = line_ids(ctx, ctx.add("a"))

    with pytest.raises(LineNotFoundError):
        ctx.use_case.execute_lines(2, [first], cost_center_code="CC-1")


def test_a_line_of_an_exported_invoice_is_not_editable(ctx: Context) -> None:
    editable, exported = ctx.add("a"), ctx.add("b")
    ctx.repo.set_status(COMPANY, ["b"], InvoiceStatus.EXPORTED)
    chosen = [line_ids(ctx, editable)[0], line_ids(ctx, exported)[0]]

    with pytest.raises(DocumentNotEditableError):
        ctx.use_case.execute_lines(COMPANY, chosen, product_code="P-03")

    assert ctx.assigned(editable) == [None, None]


def test_a_line_edit_without_values_does_nothing(ctx: Context) -> None:
    invoice_id = ctx.add("a")

    ctx.use_case.execute_lines(COMPANY, line_ids(ctx, invoice_id), product_code="  ")

    assert ctx.assigned(invoice_id) == [None, None]
    assert ctx.unit_of_work.transactions == 0
