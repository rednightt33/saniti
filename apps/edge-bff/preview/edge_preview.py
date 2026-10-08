"""EDGE page preview, both ways (EXEC-X, user decision 2026-10-08: the edited HTML is the main source).

build  : static/index.html and every script it loads from /<name>.js become one HTML file that opens without a server.
         The scripts are inlined between markers, and the BFF is replaced by saved dev responses
         (tests/fixtures/orc_responses.json, served by preview/preview_mock.js).
import : an edited preview goes back to the sources. Each inlined script returns to static/<name>.js and the page to
         static/index.html; the fixtures and the mock are dropped. A preview that was not built by this tool is
         refused rather than guessed.

    python preview/edge_preview.py build  [out.html]
    python preview/edge_preview.py import edited.html
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"
FIXTURES = ROOT / "tests" / "fixtures" / "orc_responses.json"
MOCK = ROOT / "preview" / "preview_mock.js"
TITLE_PREFIX = "Pratinjau · "
EXTERNAL = re.compile(r'<script src="/([A-Za-z0-9_-]+\.js)"></script>')
INLINED = re.compile(r'<script data-edge-file="([A-Za-z0-9_-]+\.js)">(.*?)</script>', re.S)
PREVIEW_ONLY = re.compile(r'<script data-edge-preview="[a-z]+">.*?</script>\n?', re.S)


def escape(source: str, name: str) -> str:
    if "<\\/" in source:
        raise SystemExit(f"{name} already holds '<\\/'; the inline round trip would change it")
    return source.replace("</", "<\\/")


def build(out: Path) -> None:
    page = (STATIC / "index.html").read_text(encoding="utf-8")
    names = EXTERNAL.findall(page)
    if not names:
        raise SystemExit("static/index.html loads no /<name>.js script")
    fixtures = json.dumps(json.loads(FIXTURES.read_text(encoding="utf-8")), ensure_ascii=False)
    first = True
    def inline(match: re.Match[str]) -> str:
        nonlocal first
        name = match.group(1)
        script = f'<script data-edge-file="{name}">{escape((STATIC / name).read_text(encoding="utf-8"), name)}</script>'
        if first:  # the preview's data and mock run before the page's own scripts
            first = False
            script = (f'<script data-edge-preview="fixtures">window.__EDGE_FIXTURES__={escape(fixtures, "fixtures")};'
                      f'</script>\n<script data-edge-preview="mock">{escape(MOCK.read_text(encoding="utf-8"), "mock")}'
                      f'</script>\n' + script)
        return script
    built = EXTERNAL.sub(inline, page).replace("<title>", "<title>" + TITLE_PREFIX, 1)
    out.write_text(built, encoding="utf-8")
    print(f"built {out} ({len(built):,} bytes; scripts inlined: {', '.join(names)})")


def import_preview(edited: Path) -> None:
    text = edited.read_text(encoding="utf-8").replace("\r\n", "\n")
    if 'data-edge-preview="mock"' not in text or not INLINED.search(text):
        raise SystemExit("not a preview built by preview/edge_preview.py build (markers missing); nothing written")
    changed = []
    def restore(match: re.Match[str]) -> str:
        name, body = match.group(1), match.group(2).replace("<\\/", "</")
        target = STATIC / name
        if not target.exists() or target.read_text(encoding="utf-8") != body:
            target.write_text(body, encoding="utf-8")
            changed.append(f"static/{name}")
        return f'<script src="/{name}"></script>'
    page = INLINED.sub(restore, PREVIEW_ONLY.sub("", text)).replace("<title>" + TITLE_PREFIX, "<title>", 1)
    if "__EDGE_FIXTURES__" in page or "data-edge-" in page:
        raise SystemExit("preview markers remain after import; nothing written to static/index.html")
    if (STATIC / "index.html").read_text(encoding="utf-8") != page:
        (STATIC / "index.html").write_text(page, encoding="utf-8")
        changed.append("static/index.html")
    print("imported: " + (", ".join(changed) if changed else "no change"))


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "build":
        build(Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "preview" / "edge_preview.html")
    elif len(sys.argv) == 3 and sys.argv[1] == "import":
        import_preview(Path(sys.argv[2]))
    else:
        raise SystemExit(__doc__)
