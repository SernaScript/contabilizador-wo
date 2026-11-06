import pytest

from contabilizador.invoices.application.assign_line_mapping import (
    AssignLineMapping,
    LineAssignment,
)
from contabilizador.invoices.application.errors import (
    DocumentNotEditableError,
    LineNotFoundError,
)
from contabilizador.invoices.domain.mapping import LineMapping, MappingKey
from contabilizador.invoices.domain.status import InvoiceStatus
from tests.invoices.application.fakes import (
    FakeInvoiceRepository,
    FakeMappingMemory,
    FakeUnitOfWork,
)
from tests.invoices.factories import make_document

COMPANY = 1


@pytest.fixture
def repo() -> FakeInvoiceRepository:
    repo = FakeInvoiceRepository()
    repo.add(COMPANY, make_document(cufe="a"))
    return repo


def assign_use_case(
    repo: FakeInvoiceRepository,
    memory: FakeMappingMemory,
    unit_of_work: FakeUnitOfWork | None = None,
) -> AssignLineMapping:
    return AssignLineMapping(repo, memory, unit_of_work or FakeUnitOfWork())


def line_ids(repo: FakeInvoiceRepository) -> list[int]:
    stored = repo.get_by_cufe(COMPANY, "a")
    assert stored is not None
    return [line.id for line in stored.lines]


def test_assigns_and_remembers_manual_mapping(repo: FakeInvoiceRepository) -> None:
    memory = FakeMappingMemory()
    first, _ = line_ids(repo)
    assign_use_case(repo, memory).execute(
        COMPANY, [LineAssignment(first, LineMapping("P-01", "CC-ADM"))]
    )
    stored = repo.get_by_cufe(COMPANY, "a")
    assert stored is not None
    assert stored.lines[0].assigned == LineMapping("P-01", "CC-ADM")
    assert stored.lines[1].assigned is None
    assert memory.entries == {
        MappingKey(COMPANY, "900123456", "resma papel carta 75g"): LineMapping("P-01", "CC-ADM")
    }


def test_bulk_assignment(repo: FakeInvoiceRepository) -> None:
    memory = FakeMappingMemory()
    ids = line_ids(repo)
    mapping = LineMapping("P-02", None)
    assign_use_case(repo, memory).execute(COMPANY, [LineAssignment(i, mapping) for i in ids])
    stored = repo.get_by_cufe(COMPANY, "a")
    assert stored is not None
    assert [line.assigned for line in stored.lines] == [mapping, mapping]
    assert len(memory.entries) == 2


def test_does_not_remember_when_not_manual(repo: FakeInvoiceRepository) -> None:
    memory = FakeMappingMemory()
    first, _ = line_ids(repo)
    assign_use_case(repo, memory).execute(
        COMPANY, [LineAssignment(first, LineMapping("P-01", None))], remember=False
    )
    assert memory.entries == {}
    stored = repo.get_by_cufe(COMPANY, "a")
    assert stored is not None and stored.lines[0].assigned == LineMapping("P-01", None)


def test_unknown_line_raises_and_changes_nothing(repo: FakeInvoiceRepository) -> None:
    memory = FakeMappingMemory()
    first, _ = line_ids(repo)
    with pytest.raises(LineNotFoundError):
        assign_use_case(repo, memory).execute(
            COMPANY,
            [
                LineAssignment(first, LineMapping("P", None)),
                LineAssignment(999, LineMapping("P", None)),
            ],
        )
    stored = repo.get_by_cufe(COMPANY, "a")
    assert stored is not None and stored.lines[0].assigned is None
    assert memory.entries == {}


def test_line_of_another_company_is_not_found(repo: FakeInvoiceRepository) -> None:
    first, _ = line_ids(repo)
    with pytest.raises(LineNotFoundError):
        assign_use_case(repo, FakeMappingMemory()).execute(
            2, [LineAssignment(first, LineMapping("P", None))]
        )


def test_exported_document_is_not_editable(repo: FakeInvoiceRepository) -> None:
    repo.set_status(COMPANY, ["a"], InvoiceStatus.EXPORTED)
    first, _ = line_ids(repo)
    with pytest.raises(DocumentNotEditableError):
        assign_use_case(repo, FakeMappingMemory()).execute(
            COMPANY, [LineAssignment(first, LineMapping("P", None))]
        )


def test_released_document_is_editable(repo: FakeInvoiceRepository) -> None:
    repo.set_status(COMPANY, ["a"], InvoiceStatus.RELEASED)
    first, _ = line_ids(repo)
    assign_use_case(repo, FakeMappingMemory()).execute(
        COMPANY, [LineAssignment(first, LineMapping("P", None))]
    )


def test_does_not_remember_a_mapping_without_product(repo: FakeInvoiceRepository) -> None:
    memory = FakeMappingMemory()
    first, _ = line_ids(repo)

    assign_use_case(repo, memory).execute(COMPANY, [LineAssignment(first, LineMapping("", "CC"))])

    stored = repo.get_by_cufe(COMPANY, "a")
    assert stored is not None
    assert stored.lines[0].assigned == LineMapping("", "CC")
    assert memory.entries == {}


def test_lines_and_memory_are_written_in_one_transaction(repo: FakeInvoiceRepository) -> None:
    memory = FakeMappingMemory()
    unit_of_work = FakeUnitOfWork()
    repo.unit_of_work = memory.unit_of_work = unit_of_work
    ids = line_ids(repo)

    assign_use_case(repo, memory, unit_of_work).execute(
        COMPANY, [LineAssignment(i, LineMapping("P-01", "CC-ADM")) for i in ids]
    )

    assert unit_of_work.transactions == 1
    assert unit_of_work.writes_outside_transaction == []
    assert len(memory.entries) == 2


def test_none_mapping_restores_the_suggestion_without_touching_memory(
    repo: FakeInvoiceRepository,
) -> None:
    memory = FakeMappingMemory()
    first, _ = line_ids(repo)
    use_case = assign_use_case(repo, memory)
    use_case.execute(COMPANY, [LineAssignment(first, LineMapping("P-01", "CC-ADM"))])
    remembered = dict(memory.entries)

    use_case.execute(COMPANY, [LineAssignment(first, None)])

    stored = repo.get_by_cufe(COMPANY, "a")
    assert stored is not None and stored.lines[0].assigned is None
    assert memory.entries == remembered


def test_lines_of_the_same_document_load_it_once(repo: FakeInvoiceRepository) -> None:
    ids = line_ids(repo)

    assign_use_case(repo, FakeMappingMemory()).execute(
        COMPANY, [LineAssignment(i, LineMapping("P-01", None)) for i in ids]
    )

    assert repo.get_by_line_calls == 1
