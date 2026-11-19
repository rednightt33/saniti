"""EXEC-MU-ACCOUNTS re-check R2-32 (fix round, track terminal; verification/edge_multiuser/fix_round/terminal.md): the
reference files (the ticker list, the broker list, the logos, the bonds, the stock lists) of an EDGE owner whose plan
does not hold the dataset `reference` (the reference lists in full) are served as the plan's own copy, built here from
the published file read server-side, so the plan never receives a presigned URL to a list that carries other tickers'
data.

Decision 1 of 2026-11-19 (EXEC.md EXEC-MU-ACCOUNTS "Decisions from the fix round": "user tetap bisa search ticker, tapi
ketika dia klik ticker selain bbca maka akan keluar pop up box"; track guest, verification/edge_multiuser/fix_round/
guest.md): every plan that holds terminal.view (every owner edge-bff forwards: its Terminal routes need it) and the
guest see and search the whole ticker list; the files that carry data per ticker keep the plan's filter. It replaces
the reading of D3 that served the free plan a ticker list of BBCA alone.

Which rows a plan keeps is read from each file's own columns, never from a list of files:
- a file whose `columns` include TICKER_COLUMN (`ticker`, the publisher's name for the instrument in every file keyed by
  one) and that only names the instruments (names_only: every other column holds text or nothing, no column is named
  after a dataset terminal-api serves, and none is a column of published objects' digests) keeps every row: the ticker
  list (ticker, name, type, sector, industry, instrument) today;
- any other file with that column keeps the rows of the plan's tickers (every row when the plan's tickers are "*"): the
  logos (an index of published images: `sha256` holds 64-hex digests, and each image follows the plan's tickers) and
  the bonds (`yield_first` ... `price_last`: the dates of the datasets `yield` and `price`) today;
- a file without that column lists the keys of one dataset's rows (BY_DATASET: the broker list names the brokers of the
  broker data): every row when the plan holds that dataset, none otherwise;
- any other file has no rows (fail closed): stock_lists today, whose members are lists of tickers no rule above reads.
  A new reference file is served to such a plan only once its rule is decided here (tests/test_terminal_fix_round.py
  walks the publisher's REF_NAMES, tests/test_guest_tickers.py the publisher's own columns).

The copy keeps the file's scalar and object fields and its `columns`, each column cut to the kept rows; a list outside
`columns` is left out (it could name anything). A file whose columns are not lists of one length cannot be filtered
correctly (RefError), so it is refused rather than served whole. Bytes: gzip level 9 with mtime 0 of compact JSON (the
publisher's encode), so one source and one plan give one sha256 and the browser's cache keeps working; built copies are
kept in the bounded CutCache keyed by (name, the source's sha256 or key, the plan's filter)."""
import gzip
import hashlib
import json
import re

from .cut import Cut, encode

TICKER_COLUMN = 'ticker'
BY_DATASET = {'brokers': 'broker'}
# a published object's digest (the publisher's sha256 of a file it wrote): a column of these makes a file an index of
# published objects, whose rows follow what the plan may read
DIGEST = re.compile(r'[0-9a-f]{64}')


class RefError(Exception):
    """The reference file cannot be filtered correctly; `reason` says why (for the refusal)."""
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def names_only(doc, columns, datasets):
    """Whether a ticker-keyed reference document only names its instruments (module docstring): every column but the
    ticker holds text or null (a number or a list is data), none is named `<dataset>_...` after a dataset terminal-api
    serves (`datasets`), and none holds only 64-hex digests (an index of published objects)."""
    for c in columns:
        if c == TICKER_COLUMN:
            continue
        if any(c.startswith(d + '_') for d in datasets):
            return False
        values = [v for v in doc[c] if v is not None]
        if any(not isinstance(v, str) for v in values):
            return False
        if values and all(DIGEST.fullmatch(v) for v in values):
            return False
    return True


def keep(doc, name, caps, datasets=()):
    """The row indices of the columnar reference document `doc` the plan `caps` may see (module docstring). `datasets`:
    the dataset ids terminal-api serves (main.py DATASETS), which names_only reads."""
    columns = doc.get('columns') if isinstance(doc, dict) else None
    if not isinstance(columns, list) or not columns or any(not isinstance(doc.get(c), list) for c in columns):
        raise RefError(f'the reference file {name} is not columnar (columns with one list each)')
    size = len(doc[columns[0]])
    if any(len(doc[c]) != size for c in columns):
        raise RefError(f'the reference file {name}: its columns have unequal lengths')
    if TICKER_COLUMN in columns:
        if names_only(doc, columns, datasets):
            return list(range(size))
        return [k for k, t in enumerate(doc[TICKER_COLUMN]) if isinstance(t, str) and caps.ticker_ok(t)]
    dataset = BY_DATASET.get(name)
    return list(range(size)) if dataset is not None and caps.dataset_ok(dataset) else []


def build(doc, name, caps, datasets=()):
    """The plan's copy of the reference document `doc`."""
    rows = keep(doc, name, caps, datasets)
    columns = doc['columns']
    meta = {k: v for k, v in doc.items() if k not in columns and k != 'columns' and not isinstance(v, list)}
    return {**meta, 'columns': columns, **{c: [doc[c][k] for k in rows] for c in columns}}


def filter_key(name, caps):
    """What decides the copy, beside the source: the plan's tickers, or for a file without a ticker column the one
    dataset it needs."""
    tickers = '*' if caps.tickers is None else tuple(sorted(caps.tickers))
    return (tickers, caps.dataset_ok(BY_DATASET[name]) if name in BY_DATASET else None)


def make_copy(read, name, source, caps, cache, datasets=()):
    """The Cut of the plan's copy of the reference file `name`. `source`: its index entry {key, sha256} or, for a
    publication before the refs index, {key} of its fixed key (read as it is). `read(key)` returns the gzip bytes.
    `datasets`: the dataset ids terminal-api serves (names_only)."""
    key = (name, source.get('sha256') or source['key'], filter_key(name, caps))

    def make():
        body = read(source['key'])
        if body is None:
            raise RefError(f'the published reference file {name} could not be read')
        if source.get('sha256') and hashlib.sha256(body).hexdigest() != source['sha256']:
            raise RefError(f'the published reference file {name} is not the one the publication announces')
        try:
            doc = json.loads(gzip.decompress(body))
        except (OSError, EOFError, ValueError):
            raise RefError(f'the published reference file {name} is not gzip JSON') from None
        copy = build(doc, name, caps, datasets)
        out, sha = encode(copy)
        return Cut(out, sha, len(copy[copy['columns'][0]]))
    return cache.get_or_build(key, make)
