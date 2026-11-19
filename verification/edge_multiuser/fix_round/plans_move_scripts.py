"""Re-check R2-19: the shell's two inline scripts become files, so the shell's policy can drop script-src
'unsafe-inline'. Mechanical and idempotent: run from anywhere; it moves the head script (the iOS viewport) to
static/edge-boot.js and the app script to static/edge-app.js, each replaced by its <script src>. Re-run it after a merge
that changed the inline scripts of static/index.html (it refuses when the files already exist and index.html has no
inline script left, which is the done state)."""
import re
import sys
from pathlib import Path

STATIC = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[3] / 'apps/edge-bff/static'
page = (STATIC / 'index.html').read_text(encoding='utf-8')
inline = list(re.finditer(r'<script>(.*?)</script>', page, re.S))
if not inline:
    print('no inline script left: nothing to move'); sys.exit(0)
if len(inline) != 2:
    sys.exit(f'expected 2 inline scripts, found {len(inline)}: move them by hand')
boot, app = inline
assert 'EXEC-Y' in boot.group(1) and 'Edge Workstation' in app.group(1), 'the inline scripts are not the expected two'
HEAD = ('/* EDGE shell, loaded in the head of static/index.html (re-check R2-19: no inline script, so the policy keeps\n'
        "   script-src 'self' without 'unsafe-inline'). */\n")
APP = ('/* EDGE shell app, loaded at the end of static/index.html after edge-session.js, edge-client.js, edge-labels.js and\n'
       "   edge-view.js (re-check R2-19: the shell has no inline script, so its policy keeps script-src 'self' without\n"
       "   'unsafe-inline'). The look stays in index.html; the preview tool inlines this file like the others. */\n")
(STATIC / 'edge-boot.js').write_text(HEAD + boot.group(1).strip('\n') + '\n', encoding='utf-8')
(STATIC / 'edge-app.js').write_text(APP + app.group(1).lstrip('\n'), encoding='utf-8')
page = page[:app.start()] + '<script src="/edge-app.js"></script>' + page[app.end():]
page = page[:boot.start()] + '<script src="/edge-boot.js"></script>' + page[boot.end():]
(STATIC / 'index.html').write_text(page, encoding='utf-8')
print('moved: static/edge-boot.js', len(boot.group(1)), 'chars; static/edge-app.js', len(app.group(1)), 'chars')
