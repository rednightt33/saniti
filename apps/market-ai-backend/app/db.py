from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


class Database:
    def __init__(self, database_url: str, query_timeout_seconds: int) -> None:
        self.timeout_ms = query_timeout_seconds * 1000
        self.pool = ConnectionPool(
            conninfo=database_url,
            min_size=1,
            max_size=6,
            kwargs={"row_factory": dict_row, "application_name": "market-ai-backend"},
            open=False,
        )

    def open(self) -> None:
        self.pool.open(wait=True)

    def close(self) -> None:
        self.pool.close()

    @contextmanager
    def connection(self) -> Iterator[Any]:
        with self.pool.connection() as connection:
            yield connection

    @contextmanager
    def query_transaction(self) -> Iterator[Any]:
        with self.pool.connection() as connection, connection.transaction():
            connection.execute("SET LOCAL TRANSACTION READ ONLY")
            connection.execute("SELECT set_config('statement_timeout', %s, true)", (f"{self.timeout_ms}ms",))
            yield connection

    @contextmanager
    def bounded_read_transaction(self, timeout_seconds: int) -> Iterator[Any]:
        with self.pool.connection() as connection, connection.transaction():
            connection.execute("SET LOCAL TRANSACTION READ ONLY")
            connection.execute(
                "SELECT set_config('statement_timeout', %s, true)",
                (f"{timeout_seconds * 1000}ms",),
            )
            yield connection
