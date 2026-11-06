"""Export sheet view-model: pure translation of a preview into what the sheet shows."""

from collections import Counter
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from contabilizador.exports.application.plan_consecutives import ConsecutivePlan
from contabilizador.exports.application.preview_export import ExportPreview
from contabilizador.exports.domain.batch import Batch, BatchDocument
from contabilizador.exports.domain.consecutives import ConsecutiveRange
from contabilizador.exports.domain.errors import (
    ConsecutiveCollision,
    ConsecutiveCollisionError,
    ExportBlockedError,
    ExportProblem,
    ProblemKind,
    TotalsMismatch,
    TotalsMismatchError,
)
from contabilizador.exports.domain.readiness import DocumentAssessment
from contabilizador.exports.domain.world_office import DocumentType
from contabilizador.invoices.domain.document import DocumentKind
from contabilizador.ui.pages.export.model import (
    build_state,
    default_destination,
    labelled_error_message,
    success_summary,
    with_xlsx_suffix,
)
from tests.invoices.factories import make_document
from tests.ui.factories import MATCHING_PAYABLE

FC = DocumentType.FC
NC = DocumentType.NC


def assessed(
    cufe: str,
    number: str,
    *,
    supplier: str = "FERRETERIA CENTRAL",
    kind: DocumentKind = DocumentKind.INVOICE,
    payable: Decimal = MATCHING_PAYABLE,
) -> DocumentAssessment:
    document = make_document(
        cufe=cufe,
        kind=kind,
        supplier_prefix="FPI",
        supplier_number=number,
        supplier_name=supplier,
        payable_amount=payable,
    )
    return DocumentAssessment(cufe, document)


def preview_of(
    *documents: DocumentAssessment,
    ranges: dict[DocumentType, ConsecutiveRange],
    collisions: tuple[ConsecutiveCollision, ...] = (),
    mismatches: tuple[TotalsMismatch, ...] = (),
) -> ExportPreview:
    exportable = tuple(d for d in documents if d.exportable)
    counts = Counter(d.document_type for d in exportable if d.document_type is not None)
    return ExportPreview(
        documents=documents,
        plan=ConsecutivePlan(ranges=ranges, collisions=collisions),
        exportable_cufes=tuple(d.cufe for d in exportable),
        counts=dict(counts),
        mismatches=mismatches,
    )


def test_rows_show_each_exportable_type_with_its_count_and_first_consecutive() -> None:
    preview = preview_of(
        assessed("nc-1", "120", kind=DocumentKind.CREDIT_NOTE),
        assessed("fc-1", "5731"),
        assessed("fc-2", "5732"),
        ranges={FC: ConsecutiveRange(FC, 41, 42), NC: ConsecutiveRange(NC, 7, 7)},
    )

    state = build_state(preview)

    assert [(row.document_type, row.label, row.count, row.start) for row in state.rows] == [
        (FC, "Facturas de compra (FC)", 2, 41),
        (NC, "Notas crédito (NC)", 1, 7),
    ]
    assert state.exportable_count == 3
    assert state.skipped_text == ""


def test_documents_that_are_not_ready_are_announced_as_left_pending() -> None:
    def incomplete(cufe: str) -> DocumentAssessment:
        problem = ExportProblem(ProblemKind.MISSING_COST_CENTER, cufe, line_number=1)
        return DocumentAssessment(cufe, make_document(cufe=cufe), (problem,))

    ranges = {FC: ConsecutiveRange(FC, 1, 1)}
    gone = DocumentAssessment(
        "gone", None, (ExportProblem(ProblemKind.DOCUMENT_NOT_FOUND, "gone"),)
    )
    one_left = build_state(preview_of(assessed("fc-1", "1"), incomplete("x-1"), ranges=ranges))
    three_left = build_state(
        preview_of(assessed("fc-1", "1"), incomplete("x-1"), incomplete("x-2"), gone, ranges=ranges)
    )

    assert one_left.skipped_text == "1 factura no está lista y queda pendiente."
    assert three_left.skipped_text == "3 facturas no están listas y quedan pendientes."


def test_without_mismatches_there_is_nothing_to_confirm() -> None:
    state = build_state(
        preview_of(assessed("fc-1", "5731"), ranges={FC: ConsecutiveRange(FC, 1, 1)})
    )

    assert state.mismatches is None


def test_mismatches_are_named_by_label_with_the_difference_in_pesos() -> None:
    over = assessed("fc-1", "5731", payable=MATCHING_PAYABLE - Decimal(1500))
    under = assessed("fc-2", "88", supplier="PAPELERIA SUR", payable=MATCHING_PAYABLE + 250)
    preview = preview_of(
        over,
        under,
        ranges={FC: ConsecutiveRange(FC, 1, 2)},
        mismatches=(
            TotalsMismatch("fc-1", Decimal(1500)),
            TotalsMismatch("fc-2", Decimal("-250.50")),
        ),
    )

    notice = build_state(preview).mismatches

    assert notice is not None
    assert notice.title == "2 facturas tienen descuadre"
    assert notice.items == (
        "FPI-5731 · FERRETERIA CENTRAL: las líneas suman $ 1.500 más que el XML.",
        "FPI-88 · PAPELERIA SUR: las líneas suman $ 250,50 menos que el XML.",
    )
    assert all("fc-" not in item for item in notice.items)


def test_mismatched_invoices_held_back_are_announced_but_not_counted() -> None:
    clean = assessed("fc-1", "5731")
    off = assessed("fc-2", "5732", payable=MATCHING_PAYABLE - 3)
    everything = preview_of(
        clean,
        off,
        ranges={FC: ConsecutiveRange(FC, 41, 42)},
        mismatches=(TotalsMismatch("fc-2", Decimal(3)),),
    )
    without_them = preview_of(clean, ranges={FC: ConsecutiveRange(FC, 41, 41)})

    state = build_state(without_them, selection=everything)

    # las cuentas y los consecutivos son los de lo que se exportaria ahora
    assert state.exportable_count == 1
    assert [(row.count, row.start) for row in state.rows] == [(1, 41)]
    assert state.skipped_text == ""
    # el aviso y los mensajes siguen nombrando la factura que quedo fuera
    assert state.mismatches is not None
    assert state.mismatches.title == "1 factura tiene descuadre"
    assert state.mismatches.items == (
        "FPI-5732 · FERRETERIA CENTRAL: las líneas suman $ 3 más que el XML.",
    )
    assert state.labels == {
        "fc-1": "FPI-5731 · FERRETERIA CENTRAL",
        "fc-2": "FPI-5732 · FERRETERIA CENTRAL",
    }


def test_the_mismatch_copy_agrees_with_the_count() -> None:
    one = preview_of(
        assessed("fc-1", "5731", payable=MATCHING_PAYABLE - 3),
        ranges={FC: ConsecutiveRange(FC, 1, 1)},
        mismatches=(TotalsMismatch("fc-1", Decimal(3)),),
    )
    many = preview_of(
        assessed("fc-1", "5731", payable=MATCHING_PAYABLE - 3),
        assessed("fc-2", "5732", payable=MATCHING_PAYABLE - 3),
        ranges={FC: ConsecutiveRange(FC, 1, 2)},
        mismatches=(TotalsMismatch("fc-1", Decimal(3)), TotalsMismatch("fc-2", Decimal(3))),
    )

    single = build_state(one).mismatches
    plural = build_state(many).mismatches

    assert single is not None and plural is not None
    assert single.include_label == "Exportar también la factura con descuadre"
    assert single.explanation == (
        "El total de sus líneas no coincide con el total del XML. "
        "Queda fuera del lote si no la incluyes."
    )
    assert plural.include_label == "Exportar también las facturas con descuadre"
    assert plural.explanation == (
        "El total de sus líneas no coincide con el total del XML. "
        "Quedan fuera del lote si no las incluyes."
    )


def test_long_mismatch_lists_are_cut_with_a_count_of_the_rest() -> None:
    documents = [assessed(f"fc-{n}", str(n), payable=MATCHING_PAYABLE + 10) for n in range(1, 8)]
    preview = preview_of(
        *documents,
        ranges={FC: ConsecutiveRange(FC, 1, 7)},
        mismatches=tuple(TotalsMismatch(d.cufe, Decimal(-10)) for d in documents),
    )

    notice = build_state(preview).mismatches

    assert notice is not None
    assert notice.title == "7 facturas tienen descuadre"
    assert len(notice.items) == 6
    assert notice.items[-1] == "Y 2 más."


def test_a_single_mismatch_reads_in_singular() -> None:
    preview = preview_of(
        assessed("fc-1", "5731", payable=MATCHING_PAYABLE - 3),
        ranges={FC: ConsecutiveRange(FC, 1, 1)},
        mismatches=(TotalsMismatch("fc-1", Decimal(3)),),
    )

    notice = build_state(preview).mismatches

    assert notice is not None
    assert notice.title == "1 factura tiene descuadre"


def collision(
    batch_id: int, proposed: tuple[DocumentType, int, int], existing: tuple[int, int]
) -> ConsecutiveCollision:
    document_type, first, last = proposed
    return ConsecutiveCollision(
        batch_id=batch_id,
        proposed=ConsecutiveRange(document_type, first, last),
        existing=ConsecutiveRange(document_type, *existing),
    )


def test_free_consecutives_need_no_warning() -> None:
    state = build_state(
        preview_of(assessed("fc-1", "5731"), ranges={FC: ConsecutiveRange(FC, 1, 1)})
    )

    assert state.collisions is None


def test_collisions_name_the_batch_and_offer_the_next_free_consecutive() -> None:
    preview = preview_of(
        assessed("fc-1", "5731"),
        ranges={FC: ConsecutiveRange(FC, 5731, 5731)},
        collisions=(
            collision(12, (FC, 5731, 5748), (5740, 5760)),
            collision(9, (FC, 5731, 5748), (5700, 5735)),
        ),
    )

    notice = build_state(preview).collisions

    assert notice is not None
    assert notice.title == "Los consecutivos se cruzan con un lote anterior"
    assert notice.items == (
        "FC 5731 a 5748 se cruza con el lote 12, que ya usó FC 5740 a 5760.",
        "FC 5731 a 5748 se cruza con el lote 9, que ya usó FC 5700 a 5735.",
    )
    assert notice.suggested_starts == {FC: 5761}
    assert notice.action_label == "Empezar en 5761"


def test_collisions_in_both_types_offer_free_consecutives_for_each() -> None:
    preview = preview_of(
        assessed("fc-1", "5731"),
        assessed("nc-1", "120", kind=DocumentKind.CREDIT_NOTE),
        ranges={FC: ConsecutiveRange(FC, 40, 40), NC: ConsecutiveRange(NC, 7, 7)},
        collisions=(
            collision(3, (FC, 40, 40), (38, 41)),
            collision(3, (NC, 7, 7), (7, 7)),
        ),
    )

    notice = build_state(preview).collisions

    assert notice is not None
    assert notice.items[1] == "NC 7 se cruza con el lote 3, que ya usó NC 7."
    assert notice.suggested_starts == {FC: 42, NC: 8}
    assert notice.action_label == "Usar consecutivos libres"


def test_collisions_hidden_behind_the_capped_list_still_change_the_notice() -> None:
    # Con mas de cinco cruces solo se listan cinco: un cruce oculto distinto debe pedir
    # de nuevo la confirmacion, aunque el texto visible sea identico
    listed = tuple(collision(i, (FC, 1, 60), (10 * i, 10 * i + 5)) for i in range(1, 6))
    ranges = {FC: ConsecutiveRange(FC, 1, 60), NC: ConsecutiveRange(NC, 7, 7)}
    documents = (
        assessed("fc-1", "5731"),
        assessed("nc-1", "120", kind=DocumentKind.CREDIT_NOTE),
    )
    before = build_state(
        preview_of(
            *documents, ranges=ranges, collisions=(*listed, collision(6, (NC, 7, 7), (7, 7)))
        )
    ).collisions
    after = build_state(
        preview_of(
            *documents, ranges=ranges, collisions=(*listed, collision(8, (NC, 7, 7), (7, 7)))
        )
    ).collisions

    assert before is not None and after is not None
    assert before.items == after.items  # lo visible no cambia
    assert before != after


LABELS = {"fc-1": "FPI-5731 · FERRETERIA CENTRAL", "fc-2": "FPI-88 · PAPELERIA SUR"}


def test_blocked_export_names_every_problem_by_document_label() -> None:
    error = ExportBlockedError(
        [
            ExportProblem(ProblemKind.DOCUMENT_NOT_FOUND, "gone-cufe"),
            ExportProblem(ProblemKind.ALREADY_EXPORTED, "fc-2"),
            ExportProblem(ProblemKind.UNCONFIGURED_SUPPLIER, "fc-1", detail="900123456"),
            ExportProblem(ProblemKind.MISSING_PRODUCT, "fc-1", line_number=1),
            ExportProblem(ProblemKind.UNKNOWN_PRODUCT, "fc-1", line_number=2, detail="P-OLD"),
            ExportProblem(ProblemKind.MISSING_COST_CENTER, "fc-2", line_number=1),
        ]
    )

    message = labelled_error_message(error, LABELS)

    assert message == "\n".join(
        [
            "Algunas facturas no están listas.",
            "Una de las facturas ya no está guardada.",
            "FPI-88 · PAPELERIA SUR: ya se exportó en otro lote.",
            "FPI-5731 · FERRETERIA CENTRAL: el proveedor no está configurado.",
            "FPI-5731 · FERRETERIA CENTRAL: falta el producto en la línea 1.",
            "FPI-5731 · FERRETERIA CENTRAL: el producto P-OLD de la línea 2 ya no está en el "
            "catálogo.",
            "Y 1 más.",
        ]
    )
    assert message is not None
    assert not any(cufe in message for cufe in ("gone-cufe", "fc-1", "fc-2"))


def test_totals_and_collision_errors_name_documents_and_batches() -> None:
    mismatch = TotalsMismatchError([TotalsMismatch("fc-2", Decimal("-250.50"))])
    taken = ConsecutiveCollisionError([collision(4, (FC, 10, 12), (12, 15))])

    assert labelled_error_message(mismatch, LABELS) == (
        "FPI-88 · PAPELERIA SUR: las líneas suman $ 250,50 menos que el XML."
    )
    assert labelled_error_message(taken, LABELS) == (
        "FC 10 a 12 se cruza con el lote 4, que ya usó FC 12 a 15."
    )


def test_errors_that_name_no_document_keep_the_presenter_copy() -> None:
    assert labelled_error_message(PermissionError("locked"), LABELS) is None


def exported(document_type: DocumentType, number: int) -> BatchDocument:
    return BatchDocument(
        cufe=f"{document_type.value}-{number}",
        document_type=document_type,
        number=number,
        supplier_nit="900123456",
        supplier_name="FERRETERIA CENTRAL",
        external_prefix="FPI",
        external_number=str(number),
        issue_date=date(2026, 9, 1),
    )


def test_success_summary_says_how_many_where_and_which_consecutives() -> None:
    batch = Batch(
        id=7,
        company_id=1,
        file_path=Path("salidas") / "compras.xlsx",
        created_at=datetime(2026, 10, 3, 10, 15, tzinfo=UTC),
        documents=(exported(FC, 41), exported(NC, 7), exported(FC, 42)),
    )

    summary = success_summary(batch)

    assert summary.title == "3 facturas exportadas"
    assert summary.saved_text == "Se guardó compras.xlsx en salidas."
    assert summary.ranges_text == "Consecutivos usados: FC 41 a 42 y NC 7."


def test_default_destination_is_a_dated_file_in_the_remembered_folder(tmp_path: Path) -> None:
    moment = datetime(2026, 10, 3, 10, 15, 0, tzinfo=UTC)
    remembered = tmp_path / "exportaciones"
    remembered.mkdir()
    fallback = tmp_path / "Documentos"

    assert default_destination(remembered, fallback, moment) == (
        remembered / "world-office-compras-20261003-101500.xlsx"
    )
    # una carpeta recordada que ya no existe no se propone
    assert default_destination(tmp_path / "borrada", fallback, moment).parent == fallback
    assert default_destination(None, fallback, moment).parent == fallback


def test_a_remembered_folder_that_cannot_be_read_falls_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    moment = datetime(2026, 10, 3, 10, 15, 0, tzinfo=UTC)
    unreachable = tmp_path / "servidor"
    fallback = tmp_path / "Documentos"
    real_is_dir = Path.is_dir

    def failing_is_dir(path: Path) -> bool:
        if path == unreachable:
            raise TimeoutError(60, "Operation timed out")  # recurso de red caido
        return real_is_dir(path)

    monkeypatch.setattr(Path, "is_dir", failing_is_dir)

    assert default_destination(unreachable, fallback, moment).parent == fallback


def test_destination_always_ends_in_xlsx() -> None:
    folder = Path("salidas")

    assert with_xlsx_suffix(folder / "lote") == folder / "lote.xlsx"
    assert with_xlsx_suffix(folder / "lote.XLSX") == folder / "lote.XLSX"
    assert with_xlsx_suffix(folder / "lote.v2") == folder / "lote.v2.xlsx"
