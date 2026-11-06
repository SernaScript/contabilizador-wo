"""Counts the SQL statements an engine executes (constant query count tests)."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import Engine, event


class QueryCounter:
    def __init__(self) -> None:
        self.statements: list[str] = []

    @property
    def count(self) -> int:
        return len(self.statements)

    def _record(self, _conn: Any, _cursor: Any, statement: str, *_args: Any) -> None:
        self.statements.append(statement)


@contextmanager
def count_queries(engine: Engine) -> Iterator[QueryCounter]:
    counter = QueryCounter()
    event.listen(engine, "before_cursor_execute", counter._record)
    try:
        yield counter
    finally:
        event.remove(engine, "before_cursor_execute", counter._record)
