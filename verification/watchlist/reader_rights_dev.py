"""EXEC-WATCHLIST (ERRORS M466, release 2026-11-16): the publisher reads as terminal_market_reader, not as pgweb. Every
relation and function named in apps/terminal-publisher/watchlist.py's SQL must be readable by that role; the list is
taken from the module's own statements, so a new source is checked without editing this script.
Usage: python3 verification/watchlist/reader_rights_dev.py   (exit 1 when one is not readable)"""
import re
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'apps/terminal-publisher'))
import radar_formulas_doc as r  # noqa: E402
import watchlist as W  # noqa: E402

ROLE = 'terminal_market_reader'
sql = ' '.join(v for k, v in vars(W).items() if k.endswith('_SQL') and isinstance(v, str))
tables = sorted(set(re.findall(r'public\.(?:"[^"]+"|[a-z_][a-z0-9_]*\b(?!\())', sql)))
funcs = sorted(set(re.findall(r'public\.([a-z_][a-z0-9_]*)\(\)', sql)))
bad = []
for t in tables:
    ok = r.query(f"SELECT has_table_privilege('{ROLE}', '{t.replace(chr(39), chr(39) * 2)}', 'SELECT')")[0][0]
    print(('ok   ' if ok else 'FAIL ') + f'{ROLE} SELECT {t}')
    bad += [] if ok else [t]
for f in funcs:
    ok = r.query(f"SELECT has_function_privilege('{ROLE}', 'public.{f}()', 'EXECUTE')")[0][0]
    print(('ok   ' if ok else 'FAIL ') + f'{ROLE} EXECUTE public.{f}()')
    bad += [] if ok else [f]
print('READER_RIGHTS', 'OK' if not bad else 'MISSING ' + ', '.join(bad))
sys.exit(1 if bad else 0)
