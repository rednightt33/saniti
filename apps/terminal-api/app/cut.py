"""EXEC-MU-ACCOUNTS Phase 3c (decision D2 = A): the "cut" of one ticker's dataset for an owner whose plan caps the
history at N calendar days: exactly the rows dated after data_through - N days (entitlements.window_after), built here
from the published files read server-side from the bucket, so a capped owner never receives a presigned URL to a
file that holds older rows.

Sources: the dataset's manifest files (`datasets.<name>.files`, a yearly file or the one `all` file) whose `last` date
is after the window start, oldest first; a dataset that lists no file but has a pack (`packs.<name>`) is read from the
pack. Each source's bytes must have the sha256 its manifest entry announces (else CutError: never a cut of other bytes).

A cut keeps the shape every reader of a published file takes (worker.ts priceRows/brokerData/rowsOf read `columns` by
name): `columns` (the union of the sources' columns, in their order; a column a source lacks is null on its rows) with
one array per column, the newest source's scalar and object fields (units, means, ...), `dataset` "<name>-cut", `year`
null and `cut` {history_days, after, through}. The date column is `d`. A source's other row lists are cut by their own
date too (CUT_LISTS: broker `gap` [[date, board], ...]; CUT_BLOCKS: the events file's `basis` block by `ex`); any other
list, a block without its date column, or columns of unequal length is a file this module cannot cut correctly
(CutError), so the dataset is refused rather than served whole.

Bytes: gzip level 9 with mtime 0 of compact JSON (the publisher's encode), so the same sources and N give the same
sha256 every time and the browser's cache (by sha256) keeps working. Built cuts are kept in a bounded in-memory cache
keyed by (ticker, dataset, N, data_through, the sources' sha256s)."""
import gzip
import hashlib
import json
import threading
from collections import OrderedDict
from dataclasses import dataclass

from .entitlements import window_after

DATE = 'd'
CUT_LISTS = {'gap': 0}          # a list of rows whose element at this index is the row's date
CUT_BLOCKS = {'basis': 'ex'}    # a nested columnar block ({columns, <col>: [...]}) cut by this date column
DROP = ('columns', 'year', 'dataset', 'years')
MAX_CACHE_BYTES = 64_000_000
MAX_CACHE_ENTRIES = 2048


class CutError(Exception):
    """The dataset cannot be cut correctly; `reason` says why (for the refusal)."""
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class Cut:
    body: bytes
    sha256: str
    rows: int

    @property
    def bytes(self):
        return len(self.body)


def encode(doc):
    raw = json.dumps(doc, separators=(',', ':'), allow_nan=False).encode()
    body = gzip.compress(raw, compresslevel=9, mtime=0)
    return body, hashlib.sha256(body).hexdigest()


def sources(manifest, dataset, after):
    """The manifest entries the cut of `dataset` reads (oldest first), [] when none holds a row after `after`."""
    ds = (manifest.get('datasets') or {}).get(dataset) or {}
    files = [f for f in (ds.get('files') or {}).values() if isinstance(f, dict)]
    if not files:
        pack = (manifest.get('packs') or {}).get(dataset)
        files = [pack] if isinstance(pack, dict) else []
    keep = [f for f in files if not isinstance(f.get('last'), str) or f['last'][:10] > after.isoformat()]
    return sorted(keep, key=lambda f: str(f.get('first') or ''))


def _date_ok(value, after):
    return isinstance(value, str) and value[:10] > after.isoformat()


def _cut_block(block, column, after, where):
    cols = block.get('columns') if isinstance(block, dict) else None
    if not isinstance(cols, list) or column not in cols or any(not isinstance(block.get(c), list) for c in cols):
        raise CutError(f'{where} has no columnar date column {column!r}')
    n = len(block[column])
    if any(len(block[c]) != n for c in cols):
        raise CutError(f'{where}: its columns have unequal lengths')
    keep = [k for k in range(n) if _date_ok(block[column][k], after)]
    return {**{k: v for k, v in block.items() if k not in cols}, **{c: [block[c][k] for k in keep] for c in cols}}


def build(docs, dataset, days, data_through):
    """The cut document of the source documents `docs` (oldest first): see the module docstring."""
    after = window_after(data_through, days)
    if after is None:
        raise CutError(f'the manifest gives {dataset} no data_through date to count {days} days back from')
    columns, meta, lists, blocks = [], {}, {k: [] for k in CUT_LISTS}, {}
    parts = []
    for n, doc in enumerate(docs):
        where = f'{dataset} source file {n + 1}'
        cols = doc.get('columns') if isinstance(doc, dict) else None
        if not isinstance(cols, list) or DATE not in cols or any(not isinstance(doc.get(c), list) for c in cols):
            raise CutError(f'{where} has no columnar date column {DATE!r}')
        size = len(doc[DATE])
        if any(len(doc[c]) != size for c in cols):
            raise CutError(f'{where}: its columns have unequal lengths')
        for c in cols:
            if c not in columns:
                columns.append(c)
        keep = [k for k in range(size) if _date_ok(doc[DATE][k], after)]
        parts.append((cols, doc, keep))
        for key, value in doc.items():
            if key in cols or key in DROP:
                continue
            if key in CUT_LISTS:
                if not isinstance(value, list) or any(not isinstance(r, list) or not r for r in value):
                    raise CutError(f'{where}: {key!r} is not a list of rows')
                lists[key] += [r for r in value if _date_ok(r[CUT_LISTS[key]], after)]
            elif key in CUT_BLOCKS:
                blocks[key] = _cut_block(value, CUT_BLOCKS[key], after, f'{where} {key!r}')   # the newest file's
            elif isinstance(value, list):
                raise CutError(f'{where}: the list {key!r} has no date rule, so it cannot be cut')
            else:
                meta[key] = value                                  # the newest source's scalar and object fields
    out = {**meta, 'dataset': f'{dataset}-cut', 'year': None,
           'cut': {'history_days': days, 'after': after.isoformat(), 'through': str(data_through)[:10]},
           **{k: v for k, v in blocks.items()}, 'columns': columns}
    for c in columns:
        out[c] = [doc[c][k] if c in cols else None for cols, doc, keep in parts for k in keep]
    for key in CUT_LISTS:
        if any(key in doc for _, doc, _ in parts):
            out[key] = lists[key]
    return out


class CutCache:
    """Built cuts, the least recently used going first above MAX_CACHE_BYTES or MAX_CACHE_ENTRIES."""
    def __init__(self, max_bytes=MAX_CACHE_BYTES, max_entries=MAX_CACHE_ENTRIES):
        self.max_bytes, self.max_entries = max_bytes, max_entries
        self._items, self._size = OrderedDict(), 0
        self._lock = threading.Lock()
        self.builds = 0

    def get_or_build(self, key, make):
        with self._lock:
            hit = self._items.get(key)
            if hit is not None:
                self._items.move_to_end(key)
                return hit
        cut = make()                                               # outside the lock: bucket reads take a while
        with self._lock:
            self.builds += 1
            if key not in self._items:
                self._items[key] = cut
                self._size += cut.bytes
            while self._items and (self._size > self.max_bytes or len(self._items) > self.max_entries):
                _, old = self._items.popitem(last=False)
                self._size -= old.bytes
            return self._items.get(key, cut)


def make_cut(read, manifest, ticker, dataset, days, cache):
    """The Cut of `dataset` of `ticker` for N = `days`, or None when no source holds a row in the window. `read(key)`
    returns a source's gzip bytes from the bucket."""
    through = ((manifest.get('datasets') or {}).get(dataset) or {}).get('data_through')
    after = window_after(through, days)
    if after is None:
        raise CutError(f'the manifest gives {dataset} no data_through date to count {days} days back from')
    entries = sources(manifest, dataset, after)
    if not entries:
        return None
    for f in entries:
        if not isinstance(f.get('key'), str) or not isinstance(f.get('sha256'), str):
            raise CutError(f'a {dataset} manifest entry names no key and sha256')
    key = (ticker, dataset, days, str(through), tuple(f['sha256'] for f in entries))

    def make():
        docs = []
        for f in entries:
            body = read(f['key'])
            if body is None or hashlib.sha256(body).hexdigest() != f['sha256']:
                raise CutError(f'the published {dataset} file {f["key"]} is not the one its manifest announces')
            try:
                docs.append(json.loads(gzip.decompress(body)))
            except (OSError, EOFError, ValueError):
                raise CutError(f'the published {dataset} file {f["key"]} is not gzip JSON') from None
        doc = build(docs, dataset, days, through)
        body, sha = encode(doc)
        return Cut(body, sha, len(doc[DATE]))
    return cache.get_or_build(key, make)
