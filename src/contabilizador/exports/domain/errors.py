"""Errors of the exports module. Messages are technical (English); the UI maps the
structured data (problem kinds, cufes, ranges) to Spanish copy."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from contabilizador.exports.domain.consecutives import ConsecutiveRange


class ExportError(Exception):
    """Base error of the exports module."""


class ProblemKind(StrEnum):
    DOCUMENT_NOT_FOUND = "document_not_found"
    ALREADY_EXPORTED = "already_exported"
    UNCONFIGURED_SUPPLIER = "unconfigured_supplier"
    MISSING_PRODUCT = "missing_product"
    # el codigo de producto ya no existe en el catalogo (World Office lo rechazaria)
    UNKNOWN_PRODUCT = "unknown_product"
    MISSING_COST_CENTER = "missing_cost_center"
    UNKNOWN_COST_CENTER = "unknown_cost_center"


@dataclass(frozen=True, slots=True)
class ExportProblem:
    """Why a document cannot be exported. ``line_number`` is 1-based when the problem
    belongs to one line; ``detail`` carries the offending value (NIT, code...)."""

    kind: ProblemKind
    cufe: str
    line_number: int | None = None
    detail: str = ""


class ExportBlockedError(ExportError):
    """The selection has problems that must be fixed before exporting."""

    def __init__(self, problems: Sequence[ExportProblem]) -> None:
        self.problems = tuple(problems)
        super().__init__(f"export blocked by {len(self.problems)} problem(s)")


@dataclass(frozen=True, slots=True)
class TotalsMismatch:
    cufe: str
    difference: Decimal


class TotalsMismatchError(ExportError):
    """Line totals differ from the XML payable amount; requires explicit confirmation."""

    def __init__(self, mismatches: Sequence[TotalsMismatch]) -> None:
        self.mismatches = tuple(mismatches)
        super().__init__(f"{len(self.mismatches)} document(s) with mismatched totals")


@dataclass(frozen=True, slots=True)
class ConsecutiveCollision:
    batch_id: int
    proposed: ConsecutiveRange
    existing: ConsecutiveRange


class ConsecutiveCollisionError(ExportError):
    """Proposed numbers overlap an existing batch; requires explicit confirmation."""

    def __init__(self, collisions: Sequence[ConsecutiveCollision]) -> None:
        self.collisions = tuple(collisions)
        super().__init__(f"{len(self.collisions)} consecutive collision(s)")


class NothingToExportError(ExportError):
    """No documents were selected."""


class CompanyNotFoundError(ExportError):
    def __init__(self, company_id: int) -> None:
        self.company_id = company_id
        super().__init__(f"company {company_id} not found")


class BatchNotFoundError(ExportError):
    def __init__(self, batch_id: int) -> None:
        self.batch_id = batch_id
        super().__init__(f"batch {batch_id} not found")


class BatchAlreadyVoidedError(ExportError):
    """The batch was voided; it cannot be voided again nor release documents."""


class DocumentNotInBatchError(ExportError):
    def __init__(self, cufes: Sequence[str]) -> None:
        self.cufes = tuple(cufes)
        super().__init__(f"documents not in batch: {', '.join(self.cufes)}")


class DocumentAlreadyReleasedError(ExportError):
    def __init__(self, cufes: Sequence[str]) -> None:
        self.cufes = tuple(cufes)
        super().__init__(f"documents already released: {', '.join(self.cufes)}")
