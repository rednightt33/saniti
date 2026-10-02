"""The one way a migration generator writes text into a single-quoted SQL literal (ERRORS_AND_SOLUTIONS.md R27: a
generator that escaped each place by hand left an apostrophe unescaped and broke the migration)."""
from __future__ import annotations

import json
from typing import Any


def sql_literal(text: str) -> str:
    """The body of a single-quoted SQL literal: every ' doubled. The caller writes the surrounding quotes."""
    return text.replace("'", "''")


def sql_json(value: Any, **dumps: Any) -> str:
    """A JSON document as the body of a single-quoted SQL literal (for '...'::jsonb)."""
    return sql_literal(json.dumps(value, **dumps))
