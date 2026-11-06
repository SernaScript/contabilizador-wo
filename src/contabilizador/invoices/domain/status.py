"""Lifecycle of an imported document."""

from enum import StrEnum


class InvoiceStatus(StrEnum):
    """`pending` -> `exported` (-> `released` when freed from a batch)."""

    PENDING = "pending"
    EXPORTED = "exported"
    RELEASED = "released"
