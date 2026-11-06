"""Use case: propose consecutive ranges for an export and detect collisions."""

from collections.abc import Mapping
from dataclasses import dataclass

from contabilizador.exports.application.ports import BatchRepository, ConsecutiveRepository
from contabilizador.exports.domain.batch import find_collisions
from contabilizador.exports.domain.consecutives import ConsecutiveRange, suggest_start
from contabilizador.exports.domain.errors import ConsecutiveCollision
from contabilizador.exports.domain.world_office import DocumentType


@dataclass(frozen=True, slots=True)
class ConsecutivePlan:
    ranges: dict[DocumentType, ConsecutiveRange]
    collisions: tuple[ConsecutiveCollision, ...]


class PlanConsecutives:
    def __init__(self, *, consecutives: ConsecutiveRepository, batches: BatchRepository) -> None:
        self._consecutives = consecutives
        self._batches = batches

    def suggest(self, company_id: int, document_type: DocumentType) -> int:
        return suggest_start(self._consecutives.last_used(company_id, document_type))

    def execute(
        self,
        company_id: int,
        counts: Mapping[DocumentType, int],
        starts: Mapping[DocumentType, int] | None = None,
    ) -> ConsecutivePlan:
        """``counts``: documents per type; ``starts``: user-chosen first numbers
        (types left out get last used + 1)."""
        chosen = starts or {}
        ranges = {
            document_type: ConsecutiveRange.from_start(
                document_type,
                start=(
                    chosen[document_type]
                    if document_type in chosen
                    else self.suggest(company_id, document_type)
                ),
                count=count,
            )
            for document_type, count in counts.items()
            if count > 0
        }
        collisions = find_collisions(ranges.values(), self._batches.list_by_company(company_id))
        return ConsecutivePlan(ranges=ranges, collisions=tuple(collisions))
