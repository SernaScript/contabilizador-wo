"""Errors raised by the companies use cases."""


class DuplicateCompanyNameError(ValueError):
    """Another company already uses this name (ignoring case and repeated spaces)."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"a company named {name!r} already exists")
