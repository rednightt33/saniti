from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

import psycopg
from psycopg.rows import dict_row

from .tools.registry import ToolError


QueryRunner = Callable[[Any, tuple[Any, ...]], list[dict[str, Any]]]


class CatalogStore:
    """Read-only database access for the catalog and preview tools.

    Every tool call opens one short read-only transaction with connect and statement
    timeouts. Only fixed SQL composed in app/tools/ is executed, with identifiers from
    closed allowlists and values as parameters; the model never supplies SQL text.
    """

    def __init__(self, dsn: str, *, connect_timeout_seconds: int, statement_timeout_ms: int) -> None:
        self._dsn = dsn
        self._connect_timeout = connect_timeout_seconds
        self._statement_timeout_ms = statement_timeout_ms

    @contextmanager
    def read_only(self) -> Iterator[QueryRunner]:
        try:
            with psycopg.connect(
                self._dsn,
                connect_timeout=self._connect_timeout,
                row_factory=dict_row,
                application_name="market-ai-orc-catalog",
                options=(
                    f"-c statement_timeout={self._statement_timeout_ms}"
                    " -c default_transaction_read_only=on"
                    " -c idle_in_transaction_session_timeout=15000"
                ),
            ) as connection:
                connection.read_only = True
                # One consistent snapshot for all statements of a tool call (e.g. page + counts).
                connection.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ

                def run(statement: Any, params: tuple[Any, ...]) -> list[dict[str, Any]]:
                    return list(connection.execute(statement, params).fetchall())

                yield run
                connection.rollback()
        except psycopg.errors.QueryCanceled as exc:
            raise ToolError("The catalog query exceeded its time limit. Narrow the request.") from exc
        except psycopg.errors.UndefinedFunction as exc:
            raise ToolError("The required read-only database interface is not installed.") from exc
        except psycopg.errors.InsufficientPrivilege as exc:
            raise ToolError("The service is not permitted to perform this read.") from exc
        except psycopg.Error as exc:
            # Deliberately generic: connection details and server messages are not exposed.
            raise ToolError("The catalog database is currently unavailable.") from exc
