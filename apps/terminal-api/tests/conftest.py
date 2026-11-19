import os
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# The real-server tests (TERMINAL_TEST_POSTGRES_URL) read the terminal schema: the owner rows, the visitor counts, the
# quota windows and the gateway row (tests/test_phase3c.py, test_terminal_fix_round.py, test_guest_tickers.py). CI gives
# them a bare PostgreSQL (.github/workflows/backend-tests.yml), so a server without the schema gets a disposable
# database built from the repository's own terminal migrations (integration fix-int2, ERRORS: the schema tests failed
# on a bare server): every database/migrations/*_terminal_*.sql that creates or alters a terminal.* object, in file
# order, after empty stand-ins of the public market tables they grant on (derived from the files, never listed here).
# A server that already holds the schema is used as it is.
MIGRATIONS = Path(__file__).resolve().parents[3] / 'database' / 'migrations'
TERMINAL_DDL = re.compile(r'\b(?:CREATE|ALTER)\s+(?:TABLE|(?:UNIQUE\s+)?INDEX|(?:OR\s+REPLACE\s+)?FUNCTION)\s+'
                          r'(?:IF\s+NOT\s+EXISTS\s+)?(?:\w+\s+ON\s+)?terminal\.', re.I)
PUBLIC_TABLE = re.compile(r'public\."([A-Za-z0-9_]+)"')
ROLES = ('terminal_runtime', 'terminal_market_reader')


def schema_migrations(folder=MIGRATIONS):
    """The migrations that build the terminal schema, in the order they apply (file name)."""
    return [p for p in sorted(folder.glob('*_terminal_*.sql'))
            if 'edge_bff' not in p.name and TERMINAL_DDL.search(p.read_text())]


def _has_schema(url):
    import psycopg
    with psycopg.connect(url) as c:
        return c.execute("SELECT to_regclass('terminal.subscriber') IS NOT NULL").fetchone()[0]


@pytest.fixture(scope='session', autouse=True)
def terminal_schema_database():
    url = os.environ.get('TERMINAL_TEST_POSTGRES_URL')
    if not url or _has_schema(url):
        yield
        return
    import psycopg
    from psycopg.conninfo import conninfo_to_dict, make_conninfo
    files = schema_migrations()
    name = f'terminal_test_{os.getpid()}'
    with psycopg.connect(url, autocommit=True) as admin:
        taken = [r[0] for r in admin.execute('SELECT rolname FROM pg_roles WHERE rolname = ANY(%s)', (list(ROLES),))]
        if taken:
            raise RuntimeError(f'TERMINAL_TEST_POSTGRES_URL has no terminal schema, but the roles {taken} exist on its '
                               'server, so the migrations cannot build one. Fix: point it at the database that holds '
                               'them, or at a server without them (a disposable one).')
        admin.execute(f'CREATE DATABASE "{name}"')
    built = make_conninfo(**{**conninfo_to_dict(url), 'dbname': name})
    try:
        with psycopg.connect(built, autocommit=True) as c:
            for table in sorted({t for p in files for t in PUBLIC_TABLE.findall(p.read_text())}):
                c.execute(f'CREATE TABLE public."{table}" (stand_in integer)')
            for p in files:
                c.execute(p.read_text())
        os.environ['TERMINAL_TEST_POSTGRES_URL'] = built
        yield
    finally:
        os.environ['TERMINAL_TEST_POSTGRES_URL'] = url
        with psycopg.connect(url, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
            for role in ROLES:
                admin.execute(f'DROP ROLE IF EXISTS {role}')
