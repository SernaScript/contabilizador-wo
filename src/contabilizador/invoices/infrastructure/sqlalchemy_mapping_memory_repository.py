"""SQLAlchemy implementation of ``MappingMemoryRepository``.

Reads and writes join the active ``SqlAlchemyUnitOfWork`` transaction (if any), so an
assignment and the memory it updates commit together.
"""

from collections.abc import Collection

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, sessionmaker

from contabilizador.invoices.domain.mapping import LineMapping, MappingKey
from contabilizador.invoices.infrastructure.orm import MappingMemoryRow
from contabilizador.shared.db import read_session, write_session


class SqlAlchemyMappingMemoryRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def get(self, key: MappingKey) -> LineMapping | None:
        with read_session(self._session_factory) as session:
            row = session.scalars(_select_key(key)).first()
            return _to_mapping(row) if row else None

    def get_many(
        self, company_id: int, keys: Collection[MappingKey]
    ) -> dict[MappingKey, LineMapping]:
        wanted = {key for key in keys if key.company_id == company_id}
        if not wanted:
            return {}
        # Una sola consulta filtrando por proveedor (pocos parametros); el resto en memoria
        nits = sorted({key.supplier_nit for key in wanted})
        query = select(MappingMemoryRow).where(
            MappingMemoryRow.company_id == company_id, MappingMemoryRow.supplier_nit.in_(nits)
        )
        found: dict[MappingKey, LineMapping] = {}
        with read_session(self._session_factory) as session:
            for row in session.scalars(query):
                key = MappingKey(row.company_id, row.supplier_nit, row.normalized_description)
                if key in wanted:
                    found[key] = _to_mapping(row)
        return found

    def remember(self, key: MappingKey, mapping: LineMapping) -> None:
        with write_session(self._session_factory) as session:
            row = session.scalars(_select_key(key)).first()
            if row is None:
                row = MappingMemoryRow(
                    company_id=key.company_id,
                    supplier_nit=key.supplier_nit,
                    normalized_description=key.normalized_description,
                )
                session.add(row)
            row.product_code = mapping.product_code
            row.cost_center_code = mapping.cost_center_code


def _to_mapping(row: MappingMemoryRow) -> LineMapping:
    return LineMapping(row.product_code, row.cost_center_code)


def _select_key(key: MappingKey) -> Select[MappingMemoryRow]:
    return select(MappingMemoryRow).where(
        MappingMemoryRow.company_id == key.company_id,
        MappingMemoryRow.supplier_nit == key.supplier_nit,
        MappingMemoryRow.normalized_description == key.normalized_description,
    )
