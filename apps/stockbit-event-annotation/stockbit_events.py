"""Stockbit corporate actions and insider movements for idx_event_annotation (EXEC-EVENT-ANNOTATION).

Endpoints were read from Stockbit's JS bundle (getAllCorpAction, getCompanyMajorholder):

    GET https://exodus.stockbit.com/corpaction/{slug}?year=<YYYY>          every symbol of one type and year
    GET https://exodus.stockbit.com/insider/company/majorholder?symbol=&page=   50 movements per page, data.is_more

Every update pulls the full source and reconciles it with the tables (job.py), so a late report with an old date
is never skipped. This module holds the pure parts: fetching, normalizing a source row to a table row, and the keys.
Standard library only, so the same code runs in the Railway job and in tests.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from typing import Any, Callable, Iterable
from urllib.parse import urlencode

HOST = "exodus.stockbit.com"
INSIDER_PATH = "/insider/company/majorholder"
FIRST_YEAR = 1995
# Stockbit encodes a percentage it could not compute (no share base) as an int64 overflow: +-922337203685477.62
SENTINEL = "922337203685477"


class StockbitError(RuntimeError):
    pass


class InvalidToken(StockbitError):
    pass


# slug -> response data key, event_type, id field, annotation field and role, and the date fields of the row.
# `economic` (macro calendar) and `ipo` are left out by user decision (PLAN.md EVENT-ANNOTATION).
CORP_TYPES: dict[str, dict[str, Any]] = {
    "dividend": {"key": "dividend", "type": "DIVIDEND", "id": "dividend_id", "ann": "dividend_exdate", "role": "EX_DATE",
                 "cum": "dividend_cumdate", "ex": "dividend_exdate", "record": "dividend_recdate", "pay": "dividend_paydate"},
    "stock_dividend": {"key": "stock_dividend", "type": "STOCK_DIVIDEND", "id": "dividend_id", "ann": "dividend_exdate",
                       "role": "EX_DATE", "cum": "dividend_cumdate", "ex": "dividend_exdate",
                       "record": "dividend_recdate", "pay": "dividend_paydate"},
    "stocksplit": {"key": "stocksplit", "type": "STOCK_SPLIT", "id": "stocksplit_id", "ann": "stocksplit_exdate",
                   "role": "EX_DATE", "cum": "stocksplit_cumdate", "ex": "stocksplit_exdate", "record": "stocksplit_recdate"},
    "reversesplit": {"key": "stock_reverse", "type": "REVERSE_SPLIT", "id": "stocksplit_id", "ann": "stocksplit_exdate",
                     "role": "EX_DATE", "cum": "stocksplit_cumdate", "ex": "stocksplit_exdate",
                     "record": "stocksplit_recdate"},
    "bonus": {"key": "bonus", "type": "BONUS_SHARE", "id": "sahambonus_id", "ann": "stocksplit_exdate", "role": "EX_DATE",
              "cum": "stocksplit_cumdate", "ex": "stocksplit_exdate", "record": "stocksplit_recdate",
              "pay": "stocksplit_paymentdate"},
    "rightissue": {"key": "rightissue", "type": "RIGHT_ISSUE", "id": "rightissue_id", "ann": "rightissue_exdate",
                   "role": "EX_DATE", "cum": "rightissue_cumdate", "ex": "rightissue_exdate", "record": "rightissue_recdate",
                   "start": "rightissue_trading_start", "end": "rightissue_trading_end"},
    "warrant": {"key": "warrant", "type": "WARRANT", "id": "wrant_id", "ann": "wrant_trading_from", "role": "TRADING_START",
                "start": "wrant_trading_from", "end": "wrant_trading_end"},
    "tenderoffer": {"key": "tender", "type": "TENDER_OFFER", "id": "tender_id", "ann": "tender_start", "role": "OFFER_START",
                    "start": "tender_start", "end": "tender_end", "pay": "tender_paydate"},
    "rups": {"key": "rups", "type": "RUPS", "id": "rups_id", "ann": "rups_date", "role": "MEETING_DATE",
             "record": "rups_eligible_date", "start": "rups_date"},
    "pubex": {"key": "pubex", "type": "PUBLIC_EXPOSE", "id": "puexp_id", "ann": "puexp_date", "role": "EXPOSE_DATE",
              "start": "puexp_date"},
}
DATE_FIELDS = ("cum", "ex", "record", "pay", "start", "end")
STRUCTURED_WARRANT = re.compile(r"^([A-Z]{4})[A-Z0-9]{6}$")
TICKER = re.compile(r"^[A-Z]{4}$")


# ---------------------------------------------------------------- fetching

class Fetcher:
    def __init__(self, token: str, timeout: float = 60.0, retries: int = 4) -> None:
        token = token.strip()
        if token.count(".") != 2:
            raise StockbitError("STOCKBIT_TOKEN is not a JWT")
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Origin": "https://stockbit.com",
            "Referer": "https://stockbit.com/",
            "Accept": "application/json",
            "User-Agent": "saniti-stockbit-event-annotation/1.0",
        }
        self.timeout = timeout
        self.retries = retries
        self.requests = 0

    def get(self, path: str) -> tuple[int, dict]:
        """(status, body). 401/403 raise InvalidToken; 429/5xx/network are retried, then the status is returned."""
        for attempt in range(1, self.retries + 1):
            try:
                conn = http.client.HTTPSConnection(HOST, timeout=self.timeout)
                conn.request("GET", path, headers=self._headers)
                resp = conn.getresponse()
                raw = resp.read()
                conn.close()
            except (OSError, http.client.HTTPException) as exc:
                if attempt == self.retries:
                    raise StockbitError(f"network failure on {path.split('?')[0]}: {type(exc).__name__}") from exc
                time.sleep(2 ** attempt)
                continue
            self.requests += 1
            if resp.status in (401, 403):
                raise InvalidToken(f"Stockbit refused the token (HTTP {resp.status}); give a fresh JWT and rerun")
            if resp.status == 429 or resp.status >= 500:
                if attempt == self.retries:
                    return resp.status, {}
                time.sleep(2 ** attempt)
                continue
            if resp.status != 200:
                return resp.status, {}
            try:
                return 200, json.loads(raw)
            except json.JSONDecodeError as exc:
                raise StockbitError(f"non-JSON body on {path.split('?')[0]}") from exc
        raise AssertionError("unreachable")


def pull_corporate_actions(f: Fetcher, last_year: int, empty_ok: Callable[[str, int], bool],
                           workers: int = 3) -> tuple[list[dict], list[tuple[str, int, int]]]:
    """Every (type, year) from FIRST_YEAR to last_year. A year that keeps failing with 5xx is accepted as empty only
    when empty_ok(slug, year) says the tables hold nothing for it (Stockbit answers 500 for years without data, e.g.
    dividend before 2009); otherwise the pull fails, so a temporary outage never reads as a deletion."""
    tasks = [(slug, y) for slug in CORP_TYPES for y in range(FIRST_YEAR, last_year + 1)]

    def one(task):
        slug, y = task
        status, body = f.get(f"/corpaction/{slug}?" + urlencode({"year": y}))
        if status != 200:
            if empty_ok(slug, y):
                return slug, y, [], status
            raise StockbitError(f"/corpaction/{slug} year {y}: HTTP {status} and the table holds rows for it")
        rows = (body.get("data") or {}).get(CORP_TYPES[slug]["key"])
        if not isinstance(rows, list):
            raise StockbitError(f"/corpaction/{slug} year {y}: no '{CORP_TYPES[slug]['key']}' array")
        return slug, y, rows, 200

    out, failed_empty = [], []
    with ThreadPoolExecutor(workers) as pool:
        for slug, y, rows, status in pool.map(one, tasks):
            if status != 200:
                failed_empty.append((slug, y, status))
            out.extend({"slug": slug, "year": y, "row": r} for r in rows)
    return out, failed_empty


def insider_ticker(f: Fetcher, ticker: str) -> list[dict]:
    rows, page = [], 1
    while True:
        status, body = f.get(INSIDER_PATH + "?" + urlencode({"symbol": ticker, "page": page}))
        if status != 200:
            raise StockbitError(f"insider {ticker} page {page}: HTTP {status}")
        data = body.get("data") or {}
        movement = data.get("movement")
        if not isinstance(movement, list):
            raise StockbitError(f"insider {ticker} page {page}: no movement array")
        rows.extend(movement)
        if not movement or not data.get("is_more"):
            return rows
        page += 1


def insider_market_tickers(f: Fetcher, workers: int = 3, batch: int = 12) -> tuple[set[str], int]:
    """Every ticker in the whole market-wide listing (about 2,100 pages), so a delisted ticker or one missing from
    IDX_Stock_Universe still gets its per-ticker pull. Returns (tickers, pages walked)."""
    seen: set[str] = set()
    page = 1

    def one(p):
        status, body = f.get(INSIDER_PATH + "?" + urlencode({"page": p}))
        if status != 200:
            raise StockbitError(f"insider market page {p}: HTTP {status}")
        movement = (body.get("data") or {}).get("movement")
        if not isinstance(movement, list):
            raise StockbitError(f"insider market page {p}: no movement array")
        return movement

    with ThreadPoolExecutor(workers) as pool:
        while True:
            pages = list(pool.map(one, range(page, page + batch)))
            for movement in pages:
                seen.update(str(m.get("symbol") or "").upper() for m in movement if m.get("symbol"))
            if any(not m for m in pages):
                return seen, page + batch - 1
            page += batch


def pull_insider(f: Fetcher, tickers: Iterable[str], workers: int = 3,
                 progress: Callable[[int, int], None] | None = None) -> dict[str, list[dict]]:
    """Per ticker: each ticker is paged in a few seconds, so a new movement during the pull cannot shift a page boundary
    across many pages the way a 2,100-page market-wide walk can."""
    tickers = sorted(set(tickers))
    out: dict[str, list[dict]] = {}
    with ThreadPoolExecutor(workers) as pool:
        for i, (t, rows) in enumerate(zip(tickers, pool.map(lambda t: insider_ticker(f, t), tickers)), 1):
            out[t] = rows
            if progress and (i % 100 == 0 or i == len(tickers)):
                progress(i, len(tickers))
    return out


# ---------------------------------------------------------------- normalizing

def parse_date(value) -> date | None:
    text = str(value or "").strip()[:10]
    if not text or text.startswith("0000"):
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def corp_ticker(symbol: str, known: set[str]) -> tuple[str, str | None]:
    """(ticker, instrument_code). A structured warrant (IDX code: 4-letter underlying + 6 characters, e.g.
    ACESYUCK7A) is shown on its underlying's chart when that underlying is a known stock; instrument_code keeps the
    original code. Anything else keeps its own symbol."""
    m = STRUCTURED_WARRANT.match(symbol)
    if m and m.group(1) in known:
        return m.group(1), symbol
    return symbol, None


def corp_row(slug: str, row: dict, known: set[str]) -> dict:
    spec = CORP_TYPES[slug]
    rid = str(row.get(spec["id"]) or "").strip()
    symbol = str(row.get("company_symbol") or "").strip().upper()
    if not rid or rid == "0":
        raise StockbitError(f"{slug}: row without {spec['id']}; a stable key needs it: {json.dumps(row)[:200]}")
    if not symbol:
        raise StockbitError(f"{slug} {rid}: row without company_symbol")
    ann = parse_date(row.get(spec["ann"]))
    if ann is None:
        raise StockbitError(f"{slug} {rid}: no valid {spec['ann']} (annotation date); map the type's date field in "
                            "CORP_TYPES before loading")
    ticker, instrument = corp_ticker(symbol, known)
    out = {"corporate_action_key": f"{slug}:{rid}", "action_type": spec["type"], "source_slug": slug,
           "source_record_id": rid, "symbol": symbol, "ticker": ticker, "instrument_code": instrument,
           "annotation_date": ann, "annotation_date_role": spec["role"]}
    for f in DATE_FIELDS:
        out[f"{f}_date"] = parse_date(row.get(spec[f])) if spec.get(f) else None
    out["source_payload"] = row
    return out


def shares(text) -> int | None:
    t = str(text or "").replace(",", "").replace("+", "").strip()
    if not t:
        return None
    if not re.fullmatch(r"-?\d+", t):
        raise StockbitError(f"share count is not an integer: {text!r}")
    return int(t)


def pct(text) -> float | None:
    t = str(text or "").strip()
    if not t or SENTINEL in t:
        return None
    return float(t.replace(",", ""))


def decimals(text) -> int:
    t = str(text or "")
    return len(t.split(".")[1]) if "." in t else 0


def pct_quality_flag(row: dict) -> str:
    """In-row check of the two percentages kept (PLAN.md EVENT-ANNOTATION, user 2026-10-25): both use the current share
    base, so change % = current % x shares_change / shares_after, within the rounding of the printed decimals."""
    pc, pg = row["current"]["percentage"], row["changes"]["percentage"]
    if SENTINEL in str(pc) or SENTINEL in str(pg):
        return "INVALID_SENTINEL"
    sa, sg = shares(row["current"]["value"]), shares(row["changes"]["value"])
    if not sa or not sg:
        return "NOT_CHECKABLE"
    q = decimals(pg)
    unit = 10 ** -q
    diff = abs(round(float(pc) * sg / sa, q) - float(pg))
    if diff <= unit / 2 + 1e-12:
        return "OK"
    bound = abs(float(pg)) * (0.5 * 10 ** -decimals(pc)) / float(pc) if float(pc) else 0.0
    if diff <= max(unit * 1.5, bound + unit):
        return "ROUNDING"
    return "INCONSISTENT"


def _strip(value: str, prefix: str) -> str | None:
    value = str(value or "")
    return value[len(prefix):] if value.startswith(prefix) else (value or None)


def insider_stable_fields(row: dict) -> tuple[str, ...]:
    """Fields that identify a movement. The API `id` is the holder's id, not the movement's, and percentages are left
    out because Stockbit flips the sign of its overflow value between pulls (D21)."""
    return (str(row.get("symbol") or ""), str(row.get("id") or ""), str(row.get("date") or ""),
            str(row.get("action_type") or ""), str(shares(row["previous"]["value"])),
            str(shares(row["current"]["value"])), str(shares(row["changes"]["value"])),
            str(((row.get("price") or {}).get("raw") or {}).get("value") or ""))


def insider_rows(ticker: str, movements: list[dict]) -> list[dict]:
    """Rows of one ticker's pull, one per distinct movement.

    - An exact copy of a movement (same payload; Stockbit lists about 950 twice, D21) is one row with
      `source_copies` > 1: the same before/after shares cannot be two real transactions in sequence.
    - The same movement reported by IDX and by KSEI stays two rows, told apart by `data_origin`.
    - Distinct payloads with equal identifying fields and origin (a differing `purpose` or broker) are numbered
      by payload hash, so the numbering does not depend on Stockbit's listing order.
    """
    groups: dict[tuple, dict[str, list]] = {}
    for m in movements:
        sym = str(m.get("symbol") or "").upper()
        if sym != ticker:
            raise StockbitError(f"insider pull for {ticker} returned symbol {sym!r}")
        source = _strip((m.get("data_source") or {}).get("type"), "SOURCE_TYPE_")
        ident = insider_stable_fields(m) + (str(source or ""),)
        body = json.dumps(m, sort_keys=True, ensure_ascii=False)
        groups.setdefault(ident, {}).setdefault(hashlib.sha256(body.encode()).hexdigest(), []).append(m)
    out = []
    for ident, variants in groups.items():
        digest = hashlib.sha256("|".join(ident).encode()).hexdigest()[:24]
        for n, payload_hash in enumerate(sorted(variants), 1):
            copies = variants[payload_hash]
            out.append(_insider_row(ticker, f"INS:{digest}:{n}", copies[0], len(copies)))
    return out


def _insider_row(ticker: str, key: str, m: dict, copies: int) -> dict:
    try:
        tdate = datetime.strptime(m["date"], "%d %b %y").date()
    except (KeyError, ValueError) as exc:
        raise StockbitError(f"insider {ticker}: date {m.get('date')!r} is not 'DD Mon YY'") from exc
    return {
        "insider_key": key,
        "ticker": ticker,
        "transaction_date": tdate,
        "action_type": _strip(m.get("action_type"), "ACTION_TYPE_"),
        "holder_id": str(m.get("id") or "") or None,
        "holder_name": (m.get("name") or "").strip() or None,
        "holder_roles": [_strip(b, "SHAREHOLDER_BADGE_") for b in (m.get("badges") or [])],
        "holder_nationality": _strip(m.get("nationality"), "NATIONALITY_TYPE_"),
        "broker_code": ((m.get("broker_detail") or {}).get("code") or "").strip() or None,
        "shares_before": shares(m["previous"]["value"]),
        "shares_after": shares(m["current"]["value"]),
        "shares_change": shares(m["changes"]["value"]),
        "pct_before": pct(m["previous"]["percentage"]),
        "pct_after": pct(m["current"]["percentage"]),
        "pct_change": pct(m["changes"]["percentage"]),
        "pct_quality_flag": pct_quality_flag(m),
        "price": shares(((m.get("price") or {}).get("raw") or {}).get("value")),
        "is_estimated_price": bool(m.get("is_estimated_price")),
        "value_idr": shares(((m.get("value") or {}).get("raw") or {}).get("value")),
        "data_origin": _strip((m.get("data_source") or {}).get("type"), "SOURCE_TYPE_"),
        "source_copies": copies,
        "source_payload": m,
    }


def dedupe_corp(pulled: list[dict], known: set[str]) -> list[dict]:
    """One row per key: a warrant is listed in every year it trades; the copies must agree, else the pull fails."""
    rows: dict[str, dict] = {}
    for item in pulled:
        r = corp_row(item["slug"], item["row"], known)
        prev = rows.get(r["corporate_action_key"])
        if prev is not None and prev["source_payload"] != r["source_payload"]:
            raise StockbitError(f"{r['corporate_action_key']}: copies in different years disagree")
        rows[r["corporate_action_key"]] = r
    return list(rows.values())
