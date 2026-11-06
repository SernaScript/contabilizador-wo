"""World Office consecutives, kept per (company, document type)."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from contabilizador.exports.domain.world_office import DocumentType


def suggest_start(last_used: int | None) -> int:
    """Default first number for the next export: last used + 1 (1 without history)."""
    return (last_used or 0) + 1


@dataclass(frozen=True, slots=True)
class ConsecutiveRange:
    """Inclusive range of document numbers of one type."""

    document_type: DocumentType
    first: int
    last: int

    def __post_init__(self) -> None:
        if self.first < 1:
            raise ValueError("consecutives start at 1")
        if self.last < self.first:
            raise ValueError("range end must not be lower than its start")

    @classmethod
    def from_start(cls, document_type: DocumentType, *, start: int, count: int) -> ConsecutiveRange:
        if count < 1:
            raise ValueError("a range needs at least one number")
        return cls(document_type, start, start + count - 1)

    @property
    def count(self) -> int:
        return self.last - self.first + 1

    def numbers(self) -> Iterator[int]:
        return iter(range(self.first, self.last + 1))

    def overlaps(self, other: ConsecutiveRange) -> bool:
        return (
            self.document_type is other.document_type
            and self.first <= other.last
            and other.first <= self.last
        )
