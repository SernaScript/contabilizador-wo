"""SQLAlchemy implementation of ``InvoiceRepository``."""

from collections.abc import Collection
from pathlib import Path

from sqlalchemy import Select, exists, select, update
from sqlalchemy.orm import Session, sessionmaker

from contabilizador.invoices.domain.document import DocumentKind, ParsedDocument, ParsedLine
from contabilizador.invoices.domain.mapping import LineMapping
from contabilizador.invoices.domain.status import InvoiceStatus
from contabilizador.invoices.domain.stored import StoredInvoice, StoredLine
from contabilizador.invoices.infrastructure.orm import InvoiceLineRow, InvoiceRow
from contabilizador.shared.db import read_session, write_session


class SqlAlchemyInvoiceRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def exists(self, company_id: int, cufe: str) -> bool:
        query = select(exists().where(InvoiceRow.company_id == company_id, InvoiceRow.cufe == cufe))
        with read_session(self._session_factory) as session:
            return bool(session.scalar(query))

    def add(self, company_id: int, document: ParsedDocument) -> int:
        row = _to_row(company_id, document)
        with write_session(self._session_factory) as session:
            session.add(row)
            session.flush()
            return row.id

    def set_status(self, company_id: int, cufes: list[str], status: InvoiceStatus) -> None:
        if not cufes:
            return
        statement = (
            update(InvoiceRow)
            .where(InvoiceRow.company_id == company_id, InvoiceRow.cufe.in_(cufes))
            .values(status=status.value)
        )
        with write_session(self._session_factory) as session:
            session.execute(statement)

    def get(self, company_id: int, invoice_id: int) -> StoredInvoice | None:
        return self._first(
            select(InvoiceRow).where(
                InvoiceRow.company_id == company_id, InvoiceRow.id == invoice_id
            )
        )

    def get_by_cufe(self, company_id: int, cufe: str) -> StoredInvoice | None:
        return self._first(
            select(InvoiceRow).where(InvoiceRow.company_id == company_id, InvoiceRow.cufe == cufe)
        )

    def get_by_line(self, company_id: int, line_id: int) -> StoredInvoice | None:
        return self._first(
            select(InvoiceRow)
            .join(InvoiceLineRow)
            .where(InvoiceRow.company_id == company_id, InvoiceLineRow.id == line_id)
        )

    def list_by_status(
        self, company_id: int, statuses: Collection[InvoiceStatus]
    ) -> list[StoredInvoice]:
        query = (
            select(InvoiceRow)
            .where(
                InvoiceRow.company_id == company_id,
                InvoiceRow.status.in_([status.value for status in statuses]),
            )
            .order_by(InvoiceRow.issue_date, InvoiceRow.id)
        )
        with read_session(self._session_factory) as session:
            return [_to_stored(row) for row in session.scalars(query)]

    def list_by_cufes(self, company_id: int, cufes: Collection[str]) -> list[StoredInvoice]:
        wanted = sorted(set(cufes))
        if not wanted:
            return []
        # Documentos + lineas (selectin): cantidad de consultas constante
        query = (
            select(InvoiceRow)
            .where(InvoiceRow.company_id == company_id, InvoiceRow.cufe.in_(wanted))
            .order_by(InvoiceRow.issue_date, InvoiceRow.id)
        )
        with read_session(self._session_factory) as session:
            return [_to_stored(row) for row in session.scalars(query)]

    def assign_line(self, line_id: int, mapping: LineMapping | None) -> None:
        statement = (
            update(InvoiceLineRow)
            .where(InvoiceLineRow.id == line_id)
            .values(
                product_code=mapping.product_code if mapping else None,
                cost_center_code=mapping.cost_center_code if mapping else None,
            )
        )
        with write_session(self._session_factory) as session:
            session.execute(statement)

    def _first(self, query: Select[InvoiceRow]) -> StoredInvoice | None:
        with read_session(self._session_factory) as session:
            row = session.scalars(query).first()
            return _to_stored(row) if row is not None else None


def _to_row(company_id: int, document: ParsedDocument) -> InvoiceRow:
    return InvoiceRow(
        company_id=company_id,
        cufe=document.cufe,
        kind=document.kind.value,
        status=InvoiceStatus.PENDING.value,
        supplier_nit=document.supplier_nit,
        supplier_name=document.supplier_name,
        supplier_prefix=document.supplier_prefix,
        supplier_number=document.supplier_number,
        issue_date=document.issue_date,
        due_date=document.due_date,
        payable_amount=document.payable_amount,
        billing_reference_cufe=document.billing_reference_cufe,
        # Ruta en formato POSIX para que la BD sea portable entre macOS y Windows
        source_file=document.source_file.as_posix(),
        lines=[
            InvoiceLineRow(
                position=position,
                description=line.description,
                quantity=line.quantity,
                line_extension_amount=line.line_extension_amount,
                tax_percent=line.tax_percent,
            )
            for position, line in enumerate(document.lines)
        ],
    )


def _to_stored(row: InvoiceRow) -> StoredInvoice:
    parsed_lines = tuple(
        ParsedLine(
            description=line.description,
            quantity=line.quantity,
            line_extension_amount=line.line_extension_amount,
            tax_percent=line.tax_percent,
        )
        for line in row.lines
    )
    document = ParsedDocument(
        cufe=row.cufe,
        kind=DocumentKind(row.kind),
        supplier_nit=row.supplier_nit,
        supplier_name=row.supplier_name,
        supplier_prefix=row.supplier_prefix,
        supplier_number=row.supplier_number,
        issue_date=row.issue_date,
        due_date=row.due_date,
        lines=parsed_lines,
        payable_amount=row.payable_amount,
        billing_reference_cufe=row.billing_reference_cufe,
        source_file=Path(row.source_file),
    )
    lines = tuple(
        StoredLine(
            id=line_row.id,
            position=line_row.position,
            line=parsed,
            assigned=(
                LineMapping(line_row.product_code, line_row.cost_center_code)
                if line_row.product_code is not None
                else None
            ),
        )
        for line_row, parsed in zip(row.lines, parsed_lines, strict=True)
    )
    return StoredInvoice(
        id=row.id,
        company_id=row.company_id,
        status=InvoiceStatus(row.status),
        document=document,
        lines=lines,
    )
