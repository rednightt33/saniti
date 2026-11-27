"""UD71 (the user 2026-11-27: "Untuk nama perusahaan PT, tambah satu aturan tampilan saja"; ERRORS M575 D-5): a company
name that IDX_Stock_Universe writes "Pt …" (AADI, DKHH, YUPI: 3 of 862) shows as "PT …" on every EDGE page, by one display
rule (shared/company-name.ts, its unit test overview/tests/shared-display.test.ts). The database and the publisher's files
keep the source's text. This test lists where each page reads a company name and requires the rule there, and finds a
new reader of the publisher's name fields that skips it. The Terminal (the user's "Terminal jangan disentuh") is not
changed."""
import re
from pathlib import Path

EDGE = Path(__file__).resolve().parents[1]
# where each page turns the files' (or the API's) company names into what it shows: every card, row, tooltip, search
# result and header of the page reads the name from there
READERS = {
    'overview/src/model.ts': 'name: companyName(meta.stocks.name[i])',
    'watchlist/src/model.ts': 'n: companyName(f.name[i])',
    'radar/src/model.ts': 'name: (t: string) => companyName(meta.names[t]) || t',
    'sector/src/model.ts': 'n: companyName(meta.stocks.name[i])',
    'screener/src/state.ts': 'name:companyName(u.name)',
    'screener/src/preview.ts': 'name:companyName(r.name)',
    'backtest/src/picker.ts': 'const nameOf = (s: Stock) => companyName(s.name)',
}
# a read of a publisher's name field: meta.stocks.name[...], meta.names[...], a stocks file's f.name[...]
RAW = re.compile(r'\b(?:meta\.stocks\.name|meta\.names|f\.name)\[')


def test_the_rule():
    src = (EDGE / 'shared/company-name.ts').read_text()
    assert "name.startsWith('Pt ') ? `PT ${name.slice(3)}`" in src


def test_every_page_reads_the_names_through_the_rule():
    for rel, line in READERS.items():
        text = (EDGE / rel).read_text()
        assert line in text, rel
        assert re.search(r"^import \{ companyName \} from '\.\./\.\./shared/company-name\.ts';", text, re.M), rel
    assert 'name = companyName(row?.name ?? urow?.name)' in (EDGE / 'screener/src/preview.ts').read_text()
    assert 'name:companyName(r.name)' in (EDGE / 'screener/src/state.ts').read_text()


def test_no_page_reads_a_raw_name_field_without_the_rule():
    for page in ('overview', 'watchlist', 'radar', 'sector', 'screener', 'backtest', 'admin'):
        for p in (EDGE / page / 'src').rglob('*.ts'):
            for n, line in enumerate(p.read_text().splitlines(), 1):
                if RAW.search(line) and 'companyName(' not in line:
                    raise AssertionError(f'{p.relative_to(EDGE)}:{n} reads a company name without shared/company-name.ts: {line.strip()[:120]}')
