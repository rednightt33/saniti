"""C2 re-check (EXEC-MU-ACCOUNTS Phase 0 fix round; CONTRACT.md sections 12 and 13.8; M473): on the 'cleared' broadcast
(another tab signed out, or another account signed in) shared/edge-session.ts runs the page's onReset callbacks and then
reloads the page. The reload fires the page's pagehide handlers after clearUserState() has already removed the `user`
keys, so a handler that writes a `user` key there puts the previous account's state back for the next account. Every
page with a pagehide handler that writes browser storage must register onReset (to drop what it would write), as
terminal/src/data/drawingsApi.ts does.

Today screener/src/app.ts flushes its pending `remember()` on pagehide (saveLast -> scr.last, a `user` key) and has no
onReset: the previous account's last screen definition survives into the next account's Screener."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# every page folder the app serves (main.py's <NAME>_APP; the Phase 4 checker's page-tests-records-1: a hand list left
# the admin page out), so the next page is scanned without an edit here
from app import main as _main
APPS = tuple(sorted(name.removesuffix('_APP').lower() for name in vars(_main)
                    if name.endswith('_APP') and not name.endswith('_LAB_APP')))
# a pagehide handler in this file that ends in a browser-storage write of a `user` key (found by reading the code)
WRITES_ON_PAGEHIDE = {
    'screener/src/app.ts': "remember(true) -> saveLast -> scr.last",
    'terminal/src/data/drawingsApi.ts': "keepCopy -> ml.drawings.*",
}
# files with a pagehide handler and storage writes elsewhere whose handler itself writes no storage (read 2026-11-16)
PAGEHIDE_WITHOUT_STORAGE = {
    'terminal/src/app/layouts.ts': 'putOnLeave (a keepalive PUT with edge.current?.csrf, dropped after a reset)',
    'overview/src/app.ts': 'removes a listener from the shell',
}


def test_the_listed_pagehide_writers_are_the_ones_in_the_code():
    found = set()
    for app in APPS:
        for f in (ROOT / app / 'src').rglob('*.ts'):
            text = f.read_text()
            if re.search(r"addEventListener\('pagehide'", text) and re.search(
                    r"store\.set\(|localStorage\.setItem\(|saveLast\(|keepCopy\(|remember\(true\)", text):
                found.add(str(f.relative_to(ROOT)))
    assert found == set(WRITES_ON_PAGEHIDE) | set(PAGEHIDE_WITHOUT_STORAGE), found


def test_every_page_that_writes_storage_on_pagehide_drops_it_on_reset():
    missing = [f'{name}: {what}' for name, what in WRITES_ON_PAGEHIDE.items()
               if 'onReset(' not in (ROOT / name).read_text()]
    assert not missing, ('a pagehide handler writes a user key after the clean-up of a change of user, with no onReset '
                         'to drop it first:\n' + '\n'.join(missing))
