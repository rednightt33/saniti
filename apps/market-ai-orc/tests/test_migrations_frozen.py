"""An applied migration never changes (AGENTS.md history rules). database/migrations/APPLIED.sha256 holds the hash of
every applied migration; a file listed there that changed, or disappeared, fails here.

Found 2026-10-03 (round phase B): the drift tests of generated Tool_Catalog migrations compared each applied file with
the code, so a later, correct contract change made them fail and invited editing an applied migration. Those tests
now check only each tool's newest registration; this test keeps the earlier files frozen."""
from __future__ import annotations

import hashlib
from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parents[3] / "database/migrations"


def applied() -> dict[str, str]:
    lines = (MIGRATIONS / "APPLIED.sha256").read_text(encoding="utf-8").splitlines()
    return {name: digest for digest, name in (line.split("  ", 1) for line in lines if line and not line.startswith("#"))}


def test_applied_migrations_are_unchanged() -> None:
    changed = {name for name, digest in applied().items()
               if not (MIGRATIONS / name).exists()
               or hashlib.sha256((MIGRATIONS / name).read_bytes()).hexdigest() != digest}
    assert not changed, f"applied migrations changed or missing: {sorted(changed)} (add a new migration instead)"


def test_the_manifest_lists_existing_sql_files_only() -> None:
    assert all(name.endswith(".sql") for name in applied())
