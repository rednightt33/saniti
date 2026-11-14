#!/usr/bin/env python3
"""Event-driven Telegram notifications for completed Railway data jobs."""

from __future__ import annotations

import hmac
import json
import os
import re
import socket
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import psycopg
from psycopg.types.json import Jsonb


MONITORING_TABLE = 'public."Monitoring_Price_ALL"'
LOG_TABLE = 'public."Telegram_Notification_Log"'
PRICE_MONITORING_SOURCES = {"Monitoring_Price_ALL", "Monitoring_Fixed_Income"}
STOCKBIT_SOURCE = "Monitoring_Stockbit_Update"
# EXEC-TERMINAL-FRESH (user 2026-10-27): terminal-publisher asks after its evening run; the numbers are read here from
# the tables themselves, not taken from the request
FRESHNESS_SOURCE = "Terminal_Broker_Freshness"
# EXEC-PUBLISHER-SPEED (user go 2026-10-29, ERRORS M303): terminal-publisher reports a failed, slow, partial or missing
# publication. These facts exist only in the publisher (its run, the bucket's state.json), so they come with the request,
# from the service holding TELEGRAM_NOTIFY_SECRET, and are accepted only in the fixed shapes parse_publisher_health
# checks: enumerations, timestamps, numbers and file names, never free text.
HEALTH_SOURCE = "Terminal_Publisher_Health"
# EXEC-FI-DATE B (user go 2026-11-01, ERRORS M324): the weekly fixed-income consensus check
# (apps/fixed-income-price-cron/consensus_check.py) reports what only it measured, fresh source pulls, in a fixed shape
# that parse_consensus_report checks: counts, series codes, dates and an error class, never free text.
CONSENSUS_SOURCE = "Fixed_Income_Consensus_Check"
# EXEC-M334-ALERT (user go 2026-11-02: "OK A, Jalankan"; ERRORS M334): the three audit archive queues (market-audit-store,
# market-python-sandbox, market-sql-governor, each app/queue_alarm.py) report a queue stuck past the limit, items that
# stopped retrying, and the recovery. Only they see their queues, so the facts come with the request, accepted only in
# the fixed shapes parse_audit_queue checks: an enumeration, counts, minutes and an error class, never free text.
AUDIT_QUEUE_SOURCE = "Audit_Queue_Health"
# EXEC-PG-RESTART-CRON (user go 2026-11-03: "Go langkah 1–9, tafsiran toggle benar, setuju"): postgres-memory-cron
# (scripts/restart_postgres.py --cron) reports a manual request, a restart started, succeeded, failed or refused, and a
# check run. Only it knows these facts, so they come with the request, accepted only in the fixed shapes
# parse_postgres_restart checks: enumerations, numbers, times and reason codes, never free text.
POSTGRES_RESTART_SOURCE = "Postgres_Restart"
# EXEC-PUBLISH-FLOW (user go 2026-11-05: "kalau cron selesai, dia trigger ke publisher"): a loader's completion notice
# (sent after its commit) records one row in public.terminal_publish_signal and presses Run Now on terminal-publisher.
# The loaders that already notify (price DAILY/RECOVERY, fixed income, broker round) are read from their monitoring
# rows; a loader without a monitoring notice on a clean run (idx-intraday-cron) sends Terminal_Publish_Request.
PUBLISH_REQUEST_SOURCE = "Terminal_Publish_Request"
PUBLISH_SIGNAL_TABLE = "public.terminal_publish_signal"
PUBLISH_TRIGGER_SOURCES = PRICE_MONITORING_SOURCES | {STOCKBIT_SOURCE, PUBLISH_REQUEST_SOURCE}
RAILWAY_API_URL = "https://backboard.railway.com/graphql/v2"
RUN_NOW_MUTATION = """
mutation RunCronNow($input: DeploymentInstanceExecutionCreateInput!) {
  deploymentInstanceExecutionCreate(input: $input)
}
"""
SUPPORTED_SOURCES = PRICE_MONITORING_SOURCES | {"Monitoring_Feature04", STOCKBIT_SOURCE, FRESHNESS_SOURCE, HEALTH_SOURCE,
                                                CONSENSUS_SOURCE, AUDIT_QUEUE_SOURCE, POSTGRES_RESTART_SOURCE,
                                                PUBLISH_REQUEST_SOURCE}
MAX_REQUEST_BYTES = 16_384
MAX_TELEGRAM_TEXT = 4_000
JAKARTA_TZ = ZoneInfo("Asia/Jakarta")
EXECUTION_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,200}$")
STATUS_PRIORITY = {
    "FAILED": 5,
    "NEEDS_REVIEW": 4,
    "PARTIAL": 3,
    "SKIPPED": 2,
    "SUCCESS": 1,
}
STATUS_EMOJI = {
    "SUCCESS": "✅",
    "PARTIAL": "⚠️",
    "FAILED": "❌",
    "NEEDS_REVIEW": "❌",
    "SKIPPED": "⏭️",
}


@dataclass(frozen=True)
class MonitoringSummary:
    execution_id: str
    exchange: str
    run_type: str
    trigger_source: str
    update_for_date: date
    expected_symbols: int
    queried_symbols: int
    updated_symbols: int
    missing_symbols: int
    missing_tickers: tuple[str, ...]
    status: str
    started_at: datetime
    finished_at: datetime
    duration_seconds: float
    last_error: str | None
    no_trade_tickers: tuple[str, ...] = ()        # EXEC-UNIVERSE-BROKER P2: answered, no bar: no trade, not missing
    price_gaps: tuple[str, ...] = ()              # earlier no-trade pairs the broker summary shows traded (Regular)


@dataclass(frozen=True)
class Feature04Summary:
    execution_id: str
    delivery_key: str
    market_key: str
    run_type: str
    trigger_source: str
    update_for_date: date | None
    eligible_tickers: int
    completed_tickers: int
    failed_tickers: int
    blocked_tickers: int
    failed_details: tuple[str, ...]
    status: str
    started_at: datetime
    finished_at: datetime
    duration_seconds: float
    last_error: str | None
    retry_ack_message_id: int | None = None


def env_flag(name: str, default: bool = True) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def aggregate_status(statuses: list[str]) -> str:
    if not statuses:
        return "FAILED"
    return max(statuses, key=lambda item: STATUS_PRIORITY.get(item, 99))


def fetch_monitoring_summary(
    connection: psycopg.Connection, execution_id: str
) -> MonitoringSummary | None:
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT exchange, run_type, trigger_source, update_for_date,
                   expected_symbols, queried_symbols, updated_symbols,
                   missing_symbols, missing_symbol_list, status,
                   run_time, finished_at, last_error, no_trade_symbol_list, no_trade_contradicted
            FROM {MONITORING_TABLE}
            WHERE execution_id = %s
            ORDER BY exchange, asset_type, timeframe
            """,
            (execution_id,),
        )
        rows = cursor.fetchall()

    if not rows:
        return None

    missing_tickers = sorted(
        {
            str(ticker).strip().upper()
            for row in rows
            for ticker in (row[8] or [])
            if str(ticker).strip()
        }
    )
    no_trade = sorted({str(t).strip().upper() for row in rows for t in (row[13] or []) if str(t).strip()})
    gaps = sorted({f"{g.get('ticker')} {g.get('date')}" for row in rows for g in (row[14] or []) if isinstance(g, dict)})
    started_at = min(row[10] for row in rows if row[10] is not None)
    finished_at = max((row[11] or datetime.now(timezone.utc)) for row in rows)
    errors = [str(row[12]).strip() for row in rows if row[12]]

    return MonitoringSummary(
        execution_id=execution_id,
        exchange="/".join(sorted({str(row[0]) for row in rows})),
        run_type=str(rows[0][1]),
        trigger_source=str(rows[0][2]),
        update_for_date=rows[0][3],
        expected_symbols=sum(int(row[4]) for row in rows),
        queried_symbols=sum(int(row[5]) for row in rows),
        updated_symbols=sum(int(row[6]) for row in rows),
        missing_symbols=sum(int(row[7]) for row in rows),
        missing_tickers=tuple(missing_tickers),
        status=aggregate_status([str(row[9]) for row in rows]),
        started_at=started_at,
        finished_at=finished_at,
        duration_seconds=max(0.0, (finished_at - started_at).total_seconds()),
        last_error=errors[0] if errors else None,
        no_trade_tickers=tuple(no_trade),
        price_gaps=tuple(gaps),
    )


def fetch_fixed_income_summary(
    connection: psycopg.Connection, execution_id: str
) -> MonitoringSummary | None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT run_type,trigger_source,target_date,expected_series,queried_series,
                   updated_series,missing_series,missing_series_list,status,
                   started_at,finished_at,last_error,market_code
            FROM public."Monitoring_Fixed_Income" WHERE execution_id=%s::uuid
            """,
            (execution_id,),
        )
        row = cursor.fetchone()
    if row is None:
        return None
    missing = tuple(sorted(
        f"{item.get('ticker', '?')}/{item.get('metric_type', '?')}"
        for item in (row[7] or []) if isinstance(item, dict)
    ))
    return MonitoringSummary(
        execution_id=execution_id,
        exchange=f"FIXED INCOME/{row[12] or 'LEGACY'}",
        run_type=str(row[0]),
        trigger_source=str(row[1]), update_for_date=row[2], expected_symbols=int(row[3]),
        queried_symbols=int(row[4]), updated_symbols=int(row[5]), missing_symbols=int(row[6]),
        missing_tickers=missing, status=str(row[8]), started_at=row[9], finished_at=row[10],
        duration_seconds=max(0.0, (row[10] - row[9]).total_seconds()), last_error=row[11],
    )


@dataclass(frozen=True)
class StockbitUpdateSummary:
    execution_id: str
    mode: str
    status: str
    started_at: datetime
    finished_at: datetime
    token_expires_at: datetime | None
    broker_dates: tuple[str, ...]
    broker_rows: int | None
    features: dict
    index_result: dict
    events: dict
    verify: dict
    last_error: str | None
    # EXEC-LOADER-M217: the round's broker dates that broker_summary_date_quality marks INCOMPLETE, with their remark
    incomplete: tuple[tuple[str, str], ...] = ()
    # EXEC-STOCK-CATALOG: the stock list step's result (stock_lists.run); a FAILED step is a warning of the round
    stock_lists: dict = field(default_factory=dict)


def fetch_stockbit_update_summary(
    connection: psycopg.Connection, execution_id: str
) -> StockbitUpdateSummary | None:
    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT mode,status,started_at,finished_at,token_expires_at,broker_dates,broker_rows,
                      features,index_result,events,broker,last_error,stock_lists
               FROM public."Monitoring_Stockbit_Update" WHERE execution_id=%s::uuid""",
            (execution_id,),
        )
        row = cursor.fetchone()
        incomplete: tuple[tuple[str, str], ...] = ()
        if row is not None and row[5]:
            cursor.execute("SELECT to_regclass('public.broker_summary_date_quality') IS NOT NULL")
            if cursor.fetchone()[0]:
                cursor.execute(
                    """SELECT trade_date::text, remark FROM public.broker_summary_date_quality
                       WHERE trade_date = ANY(%s::date[]) AND status = 'INCOMPLETE' ORDER BY trade_date""",
                    (list(row[5]),),
                )
                incomplete = tuple((str(d), str(r or "")) for d, r in cursor.fetchall())
    if row is None or row[3] is None:
        return None
    return StockbitUpdateSummary(
        execution_id=execution_id, mode=str(row[0]), status=str(row[1]), started_at=row[2], finished_at=row[3],
        token_expires_at=row[4], broker_dates=tuple(row[5] or ()), broker_rows=row[6], features=row[7] or {},
        index_result=row[8] or {}, events=row[9] or {}, verify=(row[10] or {}).get("verify") or {},
        last_error=row[11], incomplete=incomplete, stock_lists=row[12] or {},
    )


@dataclass(frozen=True)
class BrokerFreshnessSummary:
    execution_id: str
    broker_through: date | None
    price_through: date | None
    behind_sessions: int


@dataclass(frozen=True)
class PublisherHealth:
    execution_id: str
    status: str
    run_time: datetime
    manual: bool
    stage: str | None
    error: str | None
    minutes: int | None
    last_published: datetime | None
    files: tuple[str, ...]


HEALTH_ID = re.compile(r"^terminal-publish-(manual-)?\d{4}-\d{2}-\d{2}-\d{4}(-slow|-partial|-waiting)?$")
HEALTH_STAGES = {
    "connect": "koneksi database", "start": "persiapan", "plan": "perencanaan", "files": "menulis file data",
    "packs": "menulis paket harga", "intraday": "menulis harga intraday", "xsection": "file Screener", "radar": "file Radar", "manifests": "menulis daftar isi",
    "refs": "file referensi", "state": "menulis state.json", "cleanup": "bersih-bersih",
    "loaders": "menunggu cron data selesai menulis",
}
HEALTH_FILES = {
    "price": "harga lintas-saham (Screener)", "actions": "aksi korporasi lintas-saham (Screener)",
    "tickers": "daftar saham", "brokers": "daftar broker", "logos": "daftar logo",
}
ERROR_CLASS = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]{0,80}$")
FILE_NAME = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")


def parse_publisher_health(execution_id: str, details: object) -> PublisherHealth:
    """The publisher's alert, checked field by field; anything else is a ValueError (400)."""
    if not HEALTH_ID.fullmatch(execution_id) or not isinstance(details, dict):
        raise ValueError("invalid publisher alert")
    status = details.get("status")
    suffix = {"slow": "-slow", "partial": "-partial", "waiting": "-waiting"}.get(status, "")
    if status not in ("failed", "missing", "slow", "partial", "waiting") or not execution_id.endswith(suffix) or (
            not suffix and execution_id.endswith(("-slow", "-partial", "-waiting"))):
        raise ValueError("invalid publisher alert status")
    manual = details.get("manual", False)
    if not isinstance(manual, bool) or manual != ("-manual-" in execution_id):
        raise ValueError("invalid publisher alert run")
    try:
        run_time = datetime.strptime(str(details.get("run_time")), "%Y-%m-%d %H:%M").replace(tzinfo=JAKARTA_TZ)
        last = details.get("last_published")
        last_published = datetime.fromisoformat(last) if last is not None else None
    except (TypeError, ValueError):
        raise ValueError("invalid publisher alert time") from None
    if last is not None and (len(last) > 40 or last_published.tzinfo is None):
        raise ValueError("invalid publisher alert time")
    stage, error, minutes = details.get("stage"), details.get("error"), details.get("minutes")
    files = details.get("files", [])
    if (stage is not None and stage not in HEALTH_STAGES) or (error is not None and not (isinstance(error, str) and ERROR_CLASS.fullmatch(error))):
        raise ValueError("invalid publisher alert detail")
    if minutes is not None and (isinstance(minutes, bool) or not isinstance(minutes, int) or not 0 <= minutes <= 10_000):
        raise ValueError("invalid publisher alert detail")
    if not isinstance(files, list) or len(files) > 10 or not all(isinstance(f, str) and FILE_NAME.fullmatch(f) for f in files):
        raise ValueError("invalid publisher alert detail")
    unknown = set(details) - {"status", "run_time", "manual", "stage", "error", "minutes", "last_published", "files"}
    if unknown:
        raise ValueError("invalid publisher alert detail")
    return PublisherHealth(execution_id, status, run_time, manual, stage, error, minutes, last_published, tuple(files))


def build_publisher_message(health: PublisherHealth) -> str:
    when = lambda d: d.astimezone(JAKARTA_TZ).strftime("%a %d %b %Y %H:%M WIB") if d else "-"
    run = f"{'run di luar jadwal (dipicu cron data atau manual)' if health.manual else 'publikasi'} {when(health.run_time)}"
    stage = HEALTH_STAGES.get(health.stage or "", "-")
    last = when(health.last_published)
    if health.status == "failed":
        return (f"❌ Terminal publisher: {run} gagal\n"
                f"Tahap: {stage} • galat: {health.error or '-'}\n"
                f"Terminal, Backtest dan Screener tetap memakai publikasi {last}.\n"
                "Lihat log terminal-publisher di Railway.")
    if health.status == "missing":
        return (f"❌ Terminal publisher: {run} belum terbit\n"
                f"Publikasi terakhir: {last}; Terminal, Backtest dan Screener memakai publikasi itu.\n"
                "Lihat terminal-publisher di Railway: run gagal, terhenti, atau tidak berjalan.")
    if health.status == "waiting":
        return (f"⏳ Terminal publisher: {run} menunggu cron data selesai lebih dari {health.minutes} menit\n"
                "Belum ada yang diterbitkan. Cron yang masih menulis akan memicu publikasi lagi begitu selesai; "
                f"Terminal, Backtest dan Screener tetap memakai publikasi {last}.")
    if health.status == "slow":
        return (f"⏳ Terminal publisher: {run} masih berjalan setelah {health.minutes} menit\n"
                f"Tahap: {stage}. Sampai selesai, Terminal, Backtest dan Screener memakai publikasi {last}.")
    files = ", ".join(HEALTH_FILES.get(f, f) for f in health.files) or "-"
    return (f"⚠️ Terminal publisher: {run} terbit tanpa file {files}\n"
            "File itu tetap versi sebelumnya; lihat log terminal-publisher di Railway.")


CONSENSUS_ID = re.compile(r"^fi-consensus-(manual-)?([A-Z]{2,8})-\d{4}-\d{2}-\d{2}-\d{4}$")
CONSENSUS_KINDS = {
    "revised": "nilai beda dari sumber",
    "missing": "tanggal tidak ada di database",
    "extra": "tanggal tidak ada di sumber",
    "unstable": "sumber berubah-ubah antar tarikan",
}
SERIES_CODE = re.compile(r"^[A-Z0-9]{2,16}/[a-z_]{1,32}$")


@dataclass(frozen=True)
class ConsensusReport:
    execution_id: str
    manual: bool
    market: str
    run_time: datetime
    pulls: int
    minutes: int
    series: int | None
    counts: dict
    items: tuple
    more_items: int
    failed: tuple
    error: str | None


def parse_consensus_report(execution_id: str, details: object) -> ConsensusReport:
    """The weekly consensus check's report, checked field by field; anything else is a ValueError (400)."""
    match = CONSENSUS_ID.fullmatch(execution_id)
    if not match or not isinstance(details, dict) or details.get("market") != match.group(2):
        raise ValueError("invalid consensus report")
    whole = lambda v, top: not isinstance(v, bool) and isinstance(v, int) and 0 <= v <= top
    try:
        run_time = datetime.strptime(str(details.get("run_time")), "%Y-%m-%d %H:%M").replace(tzinfo=JAKARTA_TZ)
    except ValueError:
        raise ValueError("invalid consensus report time") from None
    error = details.get("error")
    if error is not None and not (isinstance(error, str) and ERROR_CLASS.fullmatch(error)):
        raise ValueError("invalid consensus report detail")
    if not whole(details.get("pulls"), 10) or not whole(details.get("minutes"), 10_000):
        raise ValueError("invalid consensus report detail")
    counts, items, failed, series, more = {}, [], [], None, 0
    if error is None:
        series, more = details.get("series"), details.get("more_items", 0)
        counts = {kind: details.get(kind) for kind in CONSENSUS_KINDS}
        if not whole(series, 10_000) or not whole(more, 10_000) or not all(whole(v, 1_000_000) for v in counts.values()):
            raise ValueError("invalid consensus report detail")
        raw_items, failed = details.get("items", []), details.get("failed_series", [])
        if not isinstance(raw_items, list) or len(raw_items) > 25 or not isinstance(failed, list) or len(failed) > 20:
            raise ValueError("invalid consensus report detail")
        for item in raw_items:
            try:
                ok = (isinstance(item, dict) and set(item) == {"series", "kind", "count", "first", "last"}
                      and SERIES_CODE.fullmatch(str(item["series"])) and item["kind"] in CONSENSUS_KINDS
                      and whole(item["count"], 1_000_000))
                first, last = date.fromisoformat(str(item["first"])), date.fromisoformat(str(item["last"]))
            except (TypeError, ValueError):
                ok = False
            if not ok:
                raise ValueError("invalid consensus report item")
            items.append((item["series"], item["kind"], item["count"], first, last))
        if not all(isinstance(name, str) and SERIES_CODE.fullmatch(name) for name in failed):
            raise ValueError("invalid consensus report detail")
    allowed = {"market", "run_time", "pulls", "minutes", "error", "series", "more_items", "items", "failed_series",
               *CONSENSUS_KINDS}
    if set(details) - allowed:
        raise ValueError("invalid consensus report detail")
    return ConsensusReport(execution_id, bool(match.group(1)), match.group(2), run_time, details["pulls"],
                           details["minutes"], series, counts, tuple(items), more, tuple(failed), error)


def build_consensus_message(report: ConsensusReport) -> str:
    when = report.run_time.strftime("%a %d %b %Y %H:%M WIB")
    name = lambda code: code.replace("/yield_to_maturity", " yield").replace("/", " ")
    day = lambda d: d.strftime("%d %b %Y")
    head = f"Cek konsensus fixed income {'(manual)' if report.manual else 'mingguan'} — {report.market}, {when}"
    if report.error:
        return (f"❌ {head}\nGagal: {report.error}. Tidak ada data yang ditulis.\n"
                "Lihat log layanan fixed income recovery di Railway.")
    action = sum(report.counts[k] for k in ("revised", "missing", "extra"))
    lines = [f"{'⚠️' if action or report.failed else '✅'} {head}",
             f"{report.series} seri dibandingkan dengan {report.pulls} tarikan ulang TradingView ({report.minutes} menit). "
             "Tidak ada data yang ditulis."]
    if action:
        lines.append("Perlu keputusan: " + ", ".join(
            f"{report.counts[k]} {CONSENSUS_KINDS[k]}" for k in ("revised", "missing", "extra") if report.counts[k]))
    if report.counts.get("unstable"):
        lines.append(f"Info: {report.counts['unstable']} tanggal {CONSENSUS_KINDS['unstable']}; data tersimpan dibiarkan.")
    if not action and not report.counts.get("unstable") and not report.failed:
        lines.append("Semua seri sama dengan sumber.")
    for series, kind, count, first, last in report.items:
        span = day(first) if first == last else f"{day(first)} – {day(last)}"
        lines.append(f"• {name(series)}: {count} {CONSENSUS_KINDS[kind]} ({span})")
    if report.more_items:
        lines.append(f"… dan {report.more_items} baris lain di log.")
    if report.failed:
        lines.append("Gagal ditarik: " + ", ".join(name(code) for code in report.failed))
    if action:
        lines.append("Koreksi hanya dengan persetujuan Anda (ERRORS M324).")
    return "\n".join(lines)[:MAX_TELEGRAM_TEXT]


AUDIT_QUEUE_ID = re.compile(r"^audit-queue-(audit-store|sandbox|sql-governor)-(stuck|gaveup|recovered)-\d{4}-\d{2}-\d{2}$")
AUDIT_QUEUES = {
    "audit-store": ("jejak setiap jawaban EDGE AI", "market-audit-store"),
    "sandbox": ("kode dan hasil analisis Python EDGE AI", "market-python-sandbox"),
    "sql-governor": ("data yang diambil EDGE AI dari database", "market-sql-governor"),
}


@dataclass(frozen=True)
class AuditQueueHealth:
    execution_id: str
    service: str
    status: str
    waiting: int | None
    oldest_minutes: int | None
    gave_up: int
    error: str | None
    limit_minutes: int


def parse_audit_queue(execution_id: str, details: object) -> AuditQueueHealth:
    """An audit queue's alarm, checked field by field; anything else is a ValueError (400)."""
    match = AUDIT_QUEUE_ID.fullmatch(execution_id)
    if not match or not isinstance(details, dict) or set(details) - {"service", "status", "waiting", "oldest_minutes",
                                                                      "gave_up", "error", "limit_minutes"}:
        raise ValueError("invalid audit queue alarm")
    service, status = details.get("service"), details.get("status")
    if service != match.group(1) or status not in ("stuck", "gave_up", "recovered") or status.replace("_", "") != match.group(2):
        raise ValueError("invalid audit queue alarm")
    whole = lambda v, top: not isinstance(v, bool) and isinstance(v, int) and 0 <= v <= top
    waiting, oldest, gave_up = details.get("waiting"), details.get("oldest_minutes"), details.get("gave_up", 0)
    error, limit = details.get("error"), details.get("limit_minutes")
    if ((waiting is not None and not whole(waiting, 10_000_000)) or (oldest is not None and not whole(oldest, 10_000_000))
            or not whole(gave_up, 10_000_000) or not whole(limit, 10_080)
            or (error is not None and not (isinstance(error, str) and ERROR_CLASS.fullmatch(error)))):
        raise ValueError("invalid audit queue alarm detail")
    if (status == "stuck" and oldest is None) or (status == "gave_up" and gave_up < 1):
        raise ValueError("invalid audit queue alarm detail")
    return AuditQueueHealth(execution_id, service, status, waiting, oldest, gave_up, error, limit)


def build_audit_queue_message(alarm: AuditQueueHealth) -> str:
    what, service = AUDIT_QUEUES[alarm.service]
    age = lambda m: f"{m // 60} jam {m % 60} menit" if m >= 60 else f"{m} menit"
    waiting = "jumlahnya tidak terbaca" if alarm.waiting is None else f"{alarm.waiting} item"
    if alarm.status == "stuck":
        return (f"❌ Arsip audit macet: {what}\n"
                f"{waiting} menunggu; yang tertua sudah {age(alarm.oldest_minutes)} "
                f"(batas {age(alarm.limit_minutes)}). Galat terakhir: {alarm.error or '-'}.\n"
                "Arsipnya belum hilang dan terus dicoba ulang. Cek log "
                f"{service} di Railway. Bila sebuah kunci baru diganti, deploy ulang semua pemakainya (ERRORS M334).")
    if alarm.status == "gave_up":
        return (f"⚠️ Arsip audit: {alarm.gave_up} item berhenti dicoba ({what})\n"
                f"Galat: {alarm.error or '-'}. Arsip item itu tidak tersimpan; rinciannya di log {service} "
                "dan di run audit-nya. Pesan ini paling banyak sekali sehari.")
    return (f"✅ Arsip audit pulih: {what}\n"
            f"Item yang tertahan lebih dari {age(alarm.limit_minutes)} sudah tersimpan; "
            f"{'tidak ada' if not alarm.waiting else waiting} yang masih menunggu.")


POSTGRES_RESTART_ID = re.compile(
    r"^pg-restart-(scheduled|manual-telegram|manual-railway)-\d{8}T\d{4}-(manual|started|success|failed|refused|check)$")
POSTGRES_RESTART_KINDS = {
    "scheduled": "terjadwal",
    "manual-telegram": "manual dari tombol Telegram",
    "manual-railway": "manual dari dashboard Railway",
}
POSTGRES_RESTART_REASONS = {
    "cron_due": "ada cron lain dalam 45 menit",
    "b6_window": "di dalam jendela B6 (07.00-08.45 dan 19.00-20.20 WIB)",
    "active_statements": "ada query yang sedang berjalan",
    "user_runs": "ada pertanyaan user yang sedang berjalan di EDGE",
    "runs_unreadable": "pertanyaan user yang berjalan tidak bisa dibaca",
    "memory_low": "memori rendah, tidak ada yang perlu dibersihkan",
    "auto_off": "restart otomatis sedang OFF",
    "postgres_not_back": "Postgres tidak hidup kembali dalam 10 menit",
    "edge_not_ready": "EDGE belum siap sesudah restart",
}
POSTGRES_RESTART_FIELDS = {"kind", "event", "mode", "auto", "times_wib", "memory_gb", "waited_minutes", "would_restart",
                           "reasons", "seconds", "edge_ready", "memory_after_gb"}
TIMES_WIB = re.compile(r"^([01]\d|2[0-3]):[0-5]\d(,([01]\d|2[0-3]):[0-5]\d){0,7}$")


@dataclass(frozen=True)
class PostgresRestart:
    execution_id: str
    kind: str
    event: str
    mode: str
    auto: bool
    times_wib: str
    memory_gb: float | None
    waited_minutes: int
    would_restart: bool | None
    reasons: tuple[str, ...]
    seconds: int | None
    edge_ready: int | None
    memory_after_gb: float | None


def parse_postgres_restart(execution_id: str, details: object) -> PostgresRestart:
    """A postgres-memory-cron report, checked field by field; anything else is a ValueError (400)."""
    match = POSTGRES_RESTART_ID.fullmatch(execution_id)
    if not match or not isinstance(details, dict) or set(details) - POSTGRES_RESTART_FIELDS:
        raise ValueError("invalid postgres restart report")
    kind, event = match.group(1), match.group(2)
    if details.get("kind") != kind or details.get("event") != event or details.get("mode") not in ("check", "apply"):
        raise ValueError("invalid postgres restart report")
    whole = lambda v, top: not isinstance(v, bool) and isinstance(v, int) and 0 <= v <= top
    gb = lambda v: v is None or (not isinstance(v, bool) and isinstance(v, (int, float)) and 0 <= v <= 64)
    reasons = details.get("reasons", [])
    auto, would = details.get("auto"), details.get("would_restart")
    seconds, ready, waited = details.get("seconds"), details.get("edge_ready"), details.get("waited_minutes", 0)
    if (not isinstance(auto, bool) or not TIMES_WIB.fullmatch(str(details.get("times_wib", "")))
            or not gb(details.get("memory_gb")) or not gb(details.get("memory_after_gb"))
            or not whole(waited, 1440) or (would is not None and not isinstance(would, bool))
            or not isinstance(reasons, list) or any(r not in POSTGRES_RESTART_REASONS for r in reasons)
            or (seconds is not None and not whole(seconds, 3600))
            or (ready is not None and not whole(ready, 599))):
        raise ValueError("invalid postgres restart detail")
    if (event in ("refused", "failed") and not reasons) or (event == "check" and would is None):
        raise ValueError("invalid postgres restart detail")
    return PostgresRestart(execution_id, kind, event, details["mode"], auto, details["times_wib"],
                           details.get("memory_gb"), waited, would, tuple(reasons), seconds, ready,
                           details.get("memory_after_gb"))


def build_postgres_restart_message(report: PostgresRestart) -> str:
    gb = lambda v: "tidak terbaca" if v is None else f"{v:.2f} GB"
    kind = POSTGRES_RESTART_KINDS[report.kind]
    why = "; ".join(POSTGRES_RESTART_REASONS[r] for r in report.reasons)
    auto = f"Restart otomatis {'ON' if report.auto else 'OFF'}, jam {report.times_wib.replace(',', ' dan ')} WIB."
    wait = f" Sudah menunggu {report.waited_minutes} menit." if report.waited_minutes else ""
    if report.event == "manual":
        return (f"🔔 Permintaan restart Postgres diterima ({kind}).\n"
                f"Memori sekarang {gb(report.memory_gb)}. Pengaman dicek dulu; hasilnya menyusul.\n{auto}")
    if report.event == "started":
        return (f"⏳ Restart Postgres dimulai ({kind}).\n"
                f"Memori sebelum restart {gb(report.memory_gb)}. Database mati sekitar 12 detik.{wait}")
    if report.event == "success":
        return (f"✅ Restart Postgres sukses ({kind}).\n"
                f"Database kembali dalam {report.seconds} detik, EDGE siap. Memori {gb(report.memory_gb)} → "
                f"{gb(report.memory_after_gb)}.\n{auto}")
    if report.event == "failed":
        return (f"❌ Restart Postgres bermasalah ({kind}): {why}.\n"
                "Cek Railway (Postgres dan edge-bff) sekarang; lihat log postgres-memory-cron.")
    if report.event == "refused":
        return (f"⚠️ Restart Postgres tidak dijalankan ({kind}): {why}.{wait}\n"
                "Database tidak disentuh. Coba lagi nanti, atau tunggu jadwal berikutnya.\n" + auto)
    verdict = "akan dijalankan" if report.would_restart else f"tidak akan dijalankan ({why})"
    return (f"🧪 Uji restart Postgres ({kind}, mode check, tanpa restart): restart {verdict}.\n"
            f"Memori {gb(report.memory_gb)}.{wait}\n{auto}")


LOADER_NAME = re.compile(r"^[a-z][a-z0-9-]{0,63}$")


def parse_publish_request(execution_id: str, details: object) -> tuple[str, int]:
    """Terminal_Publish_Request: (loader, changed) in a fixed shape; anything else is a ValueError (400)."""
    if not isinstance(details, dict) or set(details) != {"loader", "changed"}:
        raise ValueError("invalid publish request")
    loader, changed = details.get("loader"), details.get("changed")
    if not (isinstance(loader, str) and LOADER_NAME.fullmatch(loader)) or isinstance(changed, bool) or \
            not isinstance(changed, int) or not 0 <= changed <= 1_000_000_000:
        raise ValueError("invalid publish request detail")
    return loader, changed


def publish_changed(connection: psycopg.Connection, source_table: str, execution_id: str, summary) -> tuple[int, str | None]:
    """How much a finished loader run changed, and its run type, from the facts the monitor already reads: a price run's
    updated symbols, a fixed-income run's changed series (its own column; a recovery that changed nothing is 0), a
    broker round's rows (a round that did not fail counts at least 1: its events may have changed)."""
    if source_table == "Monitoring_Fixed_Income":
        with connection.cursor() as cursor:
            cursor.execute('SELECT changed_series FROM public."Monitoring_Fixed_Income" WHERE execution_id=%s::uuid',
                           (execution_id,))
            row = cursor.fetchone()
        return int((row or [0])[0] or 0), summary.run_type
    if source_table == "Monitoring_Price_ALL":
        return int(summary.updated_symbols or 0), summary.run_type
    if source_table == STOCKBIT_SOURCE:
        if summary.status == "FAILED":
            return 0, None
        return max(1, int(summary.broker_rows or 0)), None
    return 0, None


def press_run_now(token: str, service_instance_id: str, *, opener=urlopen) -> bool:
    """Railway Run Now of terminal-publisher's cron service (the mutation telegram-trigger uses)."""
    payload = json.dumps({"query": RUN_NOW_MUTATION, "variables": {"input": {"serviceInstanceId": service_instance_id}}}).encode()
    request = Request(RAILWAY_API_URL, data=payload, method="POST",
                      headers={"Content-Type": "application/json", "Project-Access-Token": token,
                               "User-Agent": "Saniti-Telegram-Monitor/1.0"})
    with opener(request, timeout=20) as response:
        result = json.loads(response.read().decode("utf-8"))
    if result.get("errors"):
        raise RuntimeError("Railway API refused the Run Now request")
    return bool(result.get("data", {}).get("deploymentInstanceExecutionCreate"))


def fetch_broker_freshness(connection: psycopg.Connection, execution_id: str) -> BrokerFreshnessSummary:
    """The broker data (Feature 05, what the terminal publishes) against the final daily prices: how many price sessions
    have no broker data yet."""
    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT b.through, p.through,
                      (SELECT count(DISTINCT date) FROM public."Price_Stock_Indonesia_IDX"
                        WHERE timeframe = 'Daily' AND is_final AND date > b.through)
               FROM (SELECT max(trade_date) AS through FROM public."Feature_05_Foreign_Domestic_Broker_Detail") b,
                    (SELECT max(date) AS through FROM public."Price_Stock_Indonesia_IDX"
                      WHERE timeframe = 'Daily' AND is_final) p"""
        )
        broker, price, behind = cursor.fetchone()
    return BrokerFreshnessSummary(execution_id, broker, price, int(behind or 0))


def build_freshness_message(summary: BrokerFreshnessSummary) -> str:
    day = lambda d: d.strftime("%a %d %b %Y") if d else "-"
    return (f"⚠️ Terminal: data broker tertinggal {summary.behind_sessions} sesi dari harga\n"
            f"Broker sampai {day(summary.broker_through)} • harga sampai {day(summary.price_through)}\n"
            "Flow dan Broker activity menandai sesi itu \"No broker data yet\". Untuk memuat: pasang token Stockbit "
            "baru di service stockbit-updater (UPDATE_TABLE.md bagian 0).")


STOCK_LIST_CHANGES_SHOWN = 8


def stock_list_lines(result: dict) -> list[str]:
    """EXEC-STOCK-CATALOG: the indices and groups of the round (decision D2: a failure is a warning, the round stands)."""
    if not result:
        return []
    if result.get("status") == "FAILED":
        return ["⚠️ Indeks & grup tidak diperbarui (data lama tetap; Broker Summary tidak terpengaruh): "
                + str(result.get("warning") or "-")[:400]]
    lines = [f"Indeks & grup: {result.get('lists')} daftar, {result.get('members')} anggota • "
             f"masuk {result.get('added')}, keluar {result.get('removed')}"]
    changes = result.get("changes") or {}
    first = [v for v in changes.values() if v.get("first_capture")]
    if first:
        lines.append(f"Muatan pertama: {len(first)} daftar")
    moved = [v for v in changes.values() if not v.get("first_capture")]
    for item in moved[:STOCK_LIST_CHANGES_SHOWN]:
        parts = [f"+{t}" for t in item.get("added") or []] + [f"−{t}" for t in item.get("removed") or []]
        lines.append(f"• {item.get('name')}: " + " ".join(parts[:12]) + (" …" if len(parts) > 12 else ""))
    if len(moved) > STOCK_LIST_CHANGES_SHOWN:
        lines.append(f"…dan {len(moved) - STOCK_LIST_CHANGES_SHOWN} daftar lain berubah")
    new = result.get("unlisted_new") or []
    if new:
        names = ", ".join(str(x.get("name") or x.get("list_key")) for x in new[:10])
        lines.append(f"ℹ️ Daftar baru di Stockbit (tidak dimuat): {names}" + (" …" if len(new) > 10 else ""))
    return lines


def build_stockbit_messages(summary: StockbitUpdateSummary, max_length: int = MAX_TELEGRAM_TEXT) -> list[str]:
    emoji = STATUS_EMOJI.get(summary.status, "ℹ️")
    duration = format_duration(max(0.0, (summary.finished_at - summary.started_at).total_seconds()))
    lines = [f"{emoji} Stockbit update {summary.mode} {summary.status} • {duration}"]
    if summary.mode == "VERIFY" and summary.verify:
        v = summary.verify
        lines.append(f"Verify {v.get('date')}: fetched {v.get('fetched_rows')} • stored {v.get('stored_rows')} • "
                     f"different {v.get('different')} • missing {v.get('missing_in_fetch')} • new {v.get('new_in_fetch')}")
    elif summary.mode == "APPLY":
        dates = ", ".join(summary.broker_dates) if summary.broker_dates else "tidak ada tanggal baru"
        lines.append(f"Broker Summary: {dates} • rows {summary.broker_rows or 0}")
        for day, remark in summary.incomplete:  # EXEC-LOADER-M217: loaded, but remarked by the database
            lines.append(f"⚠️ {day}: {remark}")
        changed = summary.features.get("changed_dates")
        if changed is not None:
            lines.append(f"Feature 02/03/05/06: {len(changed)} tanggal di-refresh" + (f" (dari {changed[0]})" if changed else ""))
        if summary.features.get("plan_shadow_equal") is False:  # EXEC-INDEX-INCREMENTAL: the bounded plan differs
            other = summary.features.get("plan_shadow_bounded") or {}
            lines.append("⚠️ Rencana refresh terbatas beda dari rencana penuh (penuh dipakai): terbatas "
                         f"{other.get('changed')} / INDEX {other.get('index')}")
        if summary.index_result:
            frm = summary.index_result.get("from_date")
            lines.append("INDEX: " + ("dilewati" if "skipped" in summary.index_result
                                      else f"di-refresh dari {frm}" if frm else "di-refresh"))
        ca, ins = summary.events.get("reconcile_corporate_action"), summary.events.get("reconcile_insider")
        if ca and ins:
            lines.append(f"Corporate action: baru {ca.get('new')}, berubah {ca.get('changed')}, hilang {ca.get('removed')} • "
                         f"Insider: baru {ins.get('new')}, berubah {ins.get('changed')}, hilang {ins.get('removed')}")
        lines += stock_list_lines(summary.stock_lists)
    if summary.token_expires_at:
        lines.append("Token berlaku sampai " + summary.token_expires_at.astimezone(JAKARTA_TZ).strftime("%d %b %Y %H:%M") + " WIB")
    if summary.last_error:
        lines.append("Error: " + summary.last_error)
    lines.append("Triggered at: " + summary.started_at.astimezone(JAKARTA_TZ).strftime("%d %b %Y %H:%M") + " WIB")
    return ["\n".join(lines)[:max_length]]


def fetch_feature04_summary(
    connection: psycopg.Connection, execution_id: str
) -> Feature04Summary | None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT run_type,trigger_source,update_for_date,eligible_tickers,completed_tickers,
                   failed_tickers,blocked_tickers,status,started_at,finished_at,last_error,
                   source_monitor_table,source_execution_id
            FROM public."Monitoring_Feature04" WHERE execution_id=%s
            """,
            (execution_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        cursor.execute(
            """SELECT acknowledgement_message_id
               FROM public."Feature04_Retry_Request" WHERE child_execution_id=%s""",
            (execution_id,),
        )
        retry = cursor.fetchone()
        retry_ack = int(retry[0]) if retry and retry[0] is not None else None

        market_key = "ADHOC"
        if row[11] == "Monitoring_Fixed_Income" and row[12]:
            cursor.execute(
                """SELECT market_code FROM public."Monitoring_Fixed_Income"
                   WHERE execution_id=%s::uuid""",
                (row[12],),
            )
            market = cursor.fetchone()
            market_key = f"{market[0]}_BONDS" if market and market[0] else "BONDS"
        else:
            cursor.execute(
                """SELECT array_agg(DISTINCT asset_type ORDER BY asset_type)
                   FROM public."Monitoring_Feature04_Ticker" WHERE execution_id=%s""",
                (execution_id,),
            )
            asset_types = (cursor.fetchone() or [None])[0] or []
            market_key = "IDX_EQUITY" if asset_types == ["equity"] else (
                "BONDS" if asset_types == ["bonds"] else "ADHOC"
            )

        aggregate = row[1] == "SCHEDULED" and row[2] is not None and market_key != "ADHOC"
        if aggregate:
            if row[11] == "Monitoring_Fixed_Income":
                cursor.execute(
                    """
                    SELECT m.execution_id,m.run_type,m.status,m.started_at,m.finished_at,m.last_error
                    FROM public."Monitoring_Feature04" m
                    JOIN public."Monitoring_Fixed_Income" f
                      ON m.source_monitor_table='Monitoring_Fixed_Income'
                     AND m.source_execution_id=f.execution_id::text
                    WHERE m.trigger_source='SCHEDULED' AND m.update_for_date=%s
                      AND f.market_code=%s
                      AND m.status IN ('SUCCESS','PARTIAL','FAILED','SKIPPED','NEEDS_REVIEW')
                    """,
                    (row[2], market_key.removesuffix("_BONDS")),
                )
            else:
                cursor.execute(
                    """
                    SELECT m.execution_id,m.run_type,m.status,m.started_at,m.finished_at,m.last_error
                    FROM public."Monitoring_Feature04" m
                    WHERE m.trigger_source='SCHEDULED' AND m.update_for_date=%s
                      AND m.source_monitor_table='Monitoring_Price_ALL'
                      AND m.status IN ('SUCCESS','PARTIAL','FAILED','SKIPPED','NEEDS_REVIEW')
                    """,
                    (row[2],),
                )
            executions = cursor.fetchall()
        else:
            executions = [(execution_id,row[0],row[7],row[8],row[9],row[10])]

        execution_ids = [item[0] for item in executions]
        cursor.execute(
            """
            SELECT execution_id,asset_type,ticker,requested_columns,status,last_error_code,
                   required_generation,updated_at
            FROM public."Monitoring_Feature04_Ticker"
            WHERE execution_id=ANY(%s)
            ORDER BY asset_type,ticker,required_generation DESC,updated_at DESC
            """,
            (execution_ids,),
        )
        latest: dict[tuple[str, str], tuple] = {}
        for member in cursor.fetchall():
            latest.setdefault((str(member[1]), str(member[2])), member)

    statuses = [str(member[4]) for member in latest.values()]
    completed = sum(status == "SUCCESS" for status in statuses)
    failed = sum(status == "FAILED" for status in statuses)
    blocked = sum(status == "BLOCKED" for status in statuses)
    if latest:
        status = "SUCCESS" if failed + blocked == 0 else ("PARTIAL" if completed else "FAILED")
    else:
        status = aggregate_status([str(item[2]) for item in executions])
    failures = tuple(
        f"{member[1]}/{member[2]}"
        + (f" [{','.join(member[3])}]" if member[3] else "")
        + (f" ({member[5]})" if member[5] else "")
        for member in latest.values() if member[4] in ("FAILED", "BLOCKED")
    )
    started = min(item[3] for item in executions if item[3] is not None)
    finished = max((item[4] or datetime.now(timezone.utc)) for item in executions)
    run_types = [name for name in ("DAILY", "RECOVERY", "RETRY_TICKER", "RETRY_COLUMN", "ADHOC", "RECONCILIATION")
                 if any(str(item[1]) == name for item in executions)]
    delivery_key = (
        f"scheduled:{market_key}:{row[2].isoformat()}" if aggregate else execution_id
    )
    return Feature04Summary(
        execution_id=execution_id, delivery_key=delivery_key, market_key=market_key,
        run_type="+".join(run_types) or str(row[0]), trigger_source=str(row[1]),
        update_for_date=row[2], eligible_tickers=len(latest), completed_tickers=completed,
        failed_tickers=failed, blocked_tickers=blocked, failed_details=failures,
        status=status, started_at=started, finished_at=finished,
        duration_seconds=max(0.0, (finished-started).total_seconds()),
        last_error=next((str(item[5]) for item in executions if item[5]), None),
        retry_ack_message_id=retry_ack,
    )


def format_duration(seconds: float) -> str:
    total = max(0, round(seconds))
    minutes, remainder = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h{minutes:02d}m{remainder:02d}s"
    if minutes:
        return f"{minutes}m{remainder:02d}s"
    return f"{remainder}s"


def format_header(summary: MonitoringSummary) -> str:
    emoji = STATUS_EMOJI.get(summary.status, "ℹ️")
    source = summary.run_type
    if summary.trigger_source == "MANUAL":
        source += " MANUAL"
    date_text = summary.update_for_date.strftime("%d %b %Y")
    duration = format_duration(summary.duration_seconds)

    if summary.run_type == "RECOVERY":
        denominator = summary.queried_symbols
        progress = f"{summary.updated_symbols}/{denominator} recovered"
        missing = f"{summary.missing_symbols} still missing"
    else:
        progress = f"{summary.updated_symbols}/{summary.expected_symbols} updated"
        missing = f"{summary.missing_symbols} missing"

    no_trade = f" • {len(summary.no_trade_tickers)} tanpa transaksi" if summary.no_trade_tickers else ""
    header = (
        f"{emoji} {summary.exchange} {source} {summary.status} • {date_text} • "
        f"{progress} • {missing}{no_trade} • {duration}"
    )
    if summary.status == "SKIPPED" and summary.last_error:
        reason = summary.last_error.split(":", 1)[-1].strip()
        header += f" • {reason[:180]}"
    return header


def format_timing(summary: MonitoringSummary) -> str:
    started = summary.started_at.astimezone(JAKARTA_TZ).strftime("%d %b %Y %H:%M")
    finished = summary.finished_at.astimezone(JAKARTA_TZ).strftime("%d %b %Y %H:%M")
    return f"Triggered at: {started} WIB • Finished at: {finished} WIB"


def build_messages(
    summary: MonitoringSummary, max_length: int = MAX_TELEGRAM_TEXT
) -> list[str]:
    header = format_header(summary)
    header_with_timing = header + "\n\n" + format_timing(summary)
    if summary.price_gaps:   # P2: a real gap, found after the broker round; shown before the lists
        shown = ", ".join(summary.price_gaps[:20])
        more = f" (+{len(summary.price_gaps) - 20})" if len(summary.price_gaps) > 20 else ""
        header_with_timing += f"\n\nAda transaksi reguler tapi harga tidak ada: {shown}{more}"
    if summary.no_trade_tickers:   # P2: no trade that day, not an error
        shown = ", ".join(summary.no_trade_tickers[:40])
        more = f" (+{len(summary.no_trade_tickers) - 40})" if len(summary.no_trade_tickers) > 40 else ""
        header_with_timing += f"\n\nTanpa transaksi (bukan error): {shown}{more}"
    if not summary.missing_tickers:
        return [header_with_timing]

    prefixes = ["Missing: ", "Missing (cont.): "]
    messages: list[str] = []
    remaining = list(summary.missing_tickers)
    first = True
    while remaining:
        prefix = prefixes[0] if first else prefixes[1]
        base = header_with_timing + "\n\n" + prefix if first else prefix
        included: list[str] = []
        while remaining:
            candidate = ", ".join(included + [remaining[0]])
            if len(base) + len(candidate) > max_length and included:
                break
            if len(base) + len(candidate) > max_length:
                candidate = remaining[0][: max(1, max_length - len(base))]
                included.append(candidate)
                remaining.pop(0)
                break
            included.append(remaining.pop(0))
        messages.append(base + ", ".join(included))
        first = False
    return messages


def build_feature04_messages(
    summary: Feature04Summary, max_length: int = MAX_TELEGRAM_TEXT
) -> list[str]:
    emoji = STATUS_EMOJI.get(summary.status, "ℹ️")
    date_text = summary.update_for_date.strftime("%d %b %Y") if summary.update_for_date else "ad hoc"
    header = (
        f"{emoji} Feature04 {summary.market_key} {summary.run_type} {summary.status} • {date_text} • FINAL\n"
        f"Eligible: {summary.eligible_tickers} • Success: {summary.completed_tickers} • "
        f"Failed: {summary.failed_tickers} • Blocked: {summary.blocked_tickers} • "
        f"{format_duration(summary.duration_seconds)}"
    )
    timing = (
        f"Triggered at: {summary.started_at.astimezone(JAKARTA_TZ).strftime('%d %b %Y %H:%M')} WIB • "
        f"Finished at: {summary.finished_at.astimezone(JAKARTA_TZ).strftime('%d %b %Y %H:%M')} WIB"
    )
    base = header + "\n\n" + timing
    if summary.failed_details:
        shown = list(summary.failed_details[:10])
        suffix = f"\n…and {len(summary.failed_details)-10} more" if len(summary.failed_details) > 10 else ""
        base += "\n\nFailed:\n" + "\n".join(f"• {item}" for item in shown) + suffix
    return [base[:max_length]]


def feature04_markup(summary: Feature04Summary) -> dict | None:
    if summary.failed_tickers + summary.blocked_tickers == 0:
        return None
    return {"inline_keyboard": [[{
        "text": "📊 View / Retry failures", "callback_data": "f04:status"
    }]]}


def send_telegram_message(
    token: str,
    chat_id: str,
    text: str,
    reply_markup: dict | None = None,
    *,
    opener=urlopen,
) -> int:
    body = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
    if reply_markup is not None:
        body["reply_markup"] = reply_markup
    payload = json.dumps(body).encode("utf-8")
    request = Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with opener(request, timeout=20) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"Telegram HTTP {exc.code}: {detail}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"Telegram connection failed: {exc}") from exc
    if not result.get("ok"):
        raise RuntimeError(f"Telegram rejected message: {result}")
    return int(result["result"]["message_id"])


def edit_telegram_message(
    token: str, chat_id: str, message_id: int, text: str,
    reply_markup: dict | None = None, *, opener=urlopen,
) -> int:
    body = {
        "chat_id": chat_id, "message_id": message_id, "text": text,
        "disable_web_page_preview": True,
    }
    if reply_markup is not None:
        body["reply_markup"] = reply_markup
    request = Request(
        f"https://api.telegram.org/bot{token}/editMessageText",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with opener(request, timeout=20) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"Telegram HTTP {exc.code}: {detail}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"Telegram connection failed: {exc}") from exc
    if not result.get("ok"):
        raise RuntimeError(f"Telegram rejected edit: {result}")
    return int(result["result"]["message_id"])


def claim_delivery(
    connection: psycopg.Connection, source_table: str, execution_id: str
) -> tuple[str, int]:
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            INSERT INTO {LOG_TABLE} (
                source_table, source_execution_id, notification_type,
                send_status, attempt_count, updated_at
            )
            VALUES (%s, %s, 'COMPLETED', 'SENDING', 1, CURRENT_TIMESTAMP)
            ON CONFLICT (source_table, source_execution_id, notification_type)
            DO NOTHING
            RETURNING id
            """,
            (source_table, execution_id),
        )
        inserted = cursor.fetchone()
        if inserted:
            connection.commit()
            return "claimed", int(inserted[0])

        cursor.execute(
            f"""
            SELECT id, send_status,
                   updated_at > CURRENT_TIMESTAMP - INTERVAL '10 minutes' AS is_fresh
            FROM {LOG_TABLE}
            WHERE source_table = %s
              AND source_execution_id = %s
              AND notification_type = 'COMPLETED'
            FOR UPDATE
            """,
            (source_table, execution_id),
        )
        log_id, status, is_fresh = cursor.fetchone()
        if status == "SENT":
            connection.commit()
            return "duplicate", int(log_id)
        if status == "SENDING" and is_fresh:
            connection.commit()
            return "in_progress", int(log_id)
        cursor.execute(
            f"""
            UPDATE {LOG_TABLE}
            SET send_status = 'SENDING',
                attempt_count = attempt_count + 1,
                last_error = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (log_id,),
        )
        connection.commit()
        return "claimed", int(log_id)


def claim_feature04_delivery(
    connection: psycopg.Connection, delivery_key: str
) -> tuple[str, int, int | None]:
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            INSERT INTO {LOG_TABLE}(
                source_table,source_execution_id,notification_type,
                send_status,attempt_count,updated_at
            ) VALUES('Monitoring_Feature04',%s,'COMPLETED','SENDING',1,CURRENT_TIMESTAMP)
            ON CONFLICT(source_table,source_execution_id,notification_type) DO NOTHING
            RETURNING id
            """,
            (delivery_key,),
        )
        inserted = cursor.fetchone()
        if inserted:
            connection.commit()
            return "send", int(inserted[0]), None
        cursor.execute(
            f"""
            SELECT id,send_status,telegram_message_ids,
                   updated_at>CURRENT_TIMESTAMP-INTERVAL '10 minutes' AS is_fresh
            FROM {LOG_TABLE}
            WHERE source_table='Monitoring_Feature04' AND source_execution_id=%s
              AND notification_type='COMPLETED' FOR UPDATE
            """,
            (delivery_key,),
        )
        log_id,status,message_ids,is_fresh = cursor.fetchone()
        if status == "SENDING" and is_fresh:
            connection.commit()
            return "in_progress",int(log_id),None
        target = int(message_ids[-1]) if message_ids else None
        cursor.execute(
            f"""UPDATE {LOG_TABLE} SET send_status='SENDING',attempt_count=attempt_count+1,
                last_error=NULL,updated_at=CURRENT_TIMESTAMP WHERE id=%s""",
            (log_id,),
        )
        connection.commit()
        return ("edit" if target is not None else "send"),int(log_id),target


def mark_sent(
    connection: psycopg.Connection, log_id: int, message_ids: list[int]
) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            UPDATE {LOG_TABLE}
            SET send_status = 'SENT', telegram_message_ids = %s,
                sent_at = CURRENT_TIMESTAMP, last_error = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (Jsonb(message_ids), log_id),
        )
    connection.commit()


def mark_failed(connection: psycopg.Connection, log_id: int, error: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            UPDATE {LOG_TABLE}
            SET send_status = 'FAILED', last_error = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (error[:4000], log_id),
        )
    connection.commit()


class TelegramMonitor:
    def __init__(
        self,
        database_url: str,
        token: str,
        chat_id: str,
        send_message: Callable[..., int] = send_telegram_message,
        edit_message: Callable[..., int] = edit_telegram_message,
        run_now: Callable[..., bool] = press_run_now,
    ) -> None:
        self.database_url = database_url
        self.token = token
        self.chat_id = chat_id
        self.send_message = send_message
        self.edit_message = edit_message
        self.run_now = run_now

    def request_publication(self, connection: psycopg.Connection, source_table: str, execution_id: str,
                            run_type: str | None, changed: int) -> str:
        """EXEC-PUBLISH-FLOW: one signal per finished loader run that changed data, then Run Now of terminal-publisher.
        A run that changed nothing, a signal already recorded (the loader's notice repeated), or the switch
        PUBLISH_TRIGGER_ENABLED=false starts nothing. Never raises: the loader's own message is not held up by it; a
        Run Now that fails is told on Telegram at once (the data is in the database; the 07:30 WIB safety run publishes
        it otherwise)."""
        if changed <= 0:
            return "not_needed"
        if not env_flag("PUBLISH_TRIGGER_ENABLED"):
            return "disabled"
        try:
            row = connection.execute(
                f"""INSERT INTO {PUBLISH_SIGNAL_TABLE} (source, execution_id, run_type, changed)
                    VALUES (%s, %s, %s, %s) ON CONFLICT (source, execution_id) DO NOTHING RETURNING signal_id""",
                (source_table, execution_id, run_type, changed)).fetchone()
            connection.commit()
            if row is None:
                return "duplicate"
            token = os.environ.get("PUBLISH_RAILWAY_TOKEN", "").strip()
            instance = os.environ.get("TERMINAL_PUBLISHER_SERVICE_INSTANCE_ID", "").strip()
            if not token or not instance:
                status, error = "NOT_CONFIGURED", None
            else:
                try:
                    status, error = ("TRIGGERED" if self.run_now(token, instance) else "FAILED"), None
                except Exception as exc:  # noqa: BLE001 - the class only; the token is never printed
                    status, error = "FAILED", type(exc).__name__
                if status == "FAILED":
                    error = error or "NotAccepted"
            connection.execute(
                f"""UPDATE {PUBLISH_SIGNAL_TABLE} SET trigger_status=%s, trigger_error=%s,
                    triggered_at=CASE WHEN %s = 'TRIGGERED' THEN CURRENT_TIMESTAMP END WHERE signal_id=%s""",
                (status, error, status, row[0]))
            connection.commit()
            print(json.dumps({"event": "publish_signal", "source": source_table, "execution_id": execution_id,
                              "changed": changed, "status": status, "error": error}), flush=True)
            if status == "FAILED":
                self.send_message(self.token, self.chat_id,
                                  "⚠️ Pemicu Terminal publisher gagal\n"
                                  f"Cron data ({source_table}) sudah selesai dan datanya ada di database, tetapi Run Now "
                                  f"publisher ditolak ({error}). Publikasi menyusul pada run pengaman 07:30 WIB, atau "
                                  "jalankan publisher manual.")
            return status.lower()
        except Exception as exc:  # noqa: BLE001 - never let the trigger break the notification
            connection.rollback()
            print(json.dumps({"event": "publish_signal_failed", "source": source_table,
                              "error": f"{type(exc).__name__}"}), flush=True)
            return "error"

    def notify(self, source_table: str, execution_id: str, details: object = None) -> tuple[str, int]:
        if source_table not in SUPPORTED_SOURCES:
            raise ValueError("unsupported source_table")
        if not EXECUTION_ID_PATTERN.fullmatch(execution_id):
            raise ValueError("invalid execution_id")
        health = parse_publisher_health(execution_id, details) if source_table == HEALTH_SOURCE else None
        if source_table == CONSENSUS_SOURCE:
            health = parse_consensus_report(execution_id, details)
        if source_table == AUDIT_QUEUE_SOURCE:
            health = parse_audit_queue(execution_id, details)
        if source_table == POSTGRES_RESTART_SOURCE:
            health = parse_postgres_restart(execution_id, details)
        if source_table == PUBLISH_REQUEST_SOURCE:
            loader, changed = parse_publish_request(execution_id, details)
            with psycopg.connect(self.database_url) as connection:
                return self.request_publication(connection, source_table, execution_id, None, changed), 0

        with psycopg.connect(self.database_url) as connection:
            if health is not None:
                summary = health
            elif source_table == "Monitoring_Price_ALL":
                summary = fetch_monitoring_summary(connection, execution_id)
            elif source_table == "Monitoring_Fixed_Income":
                summary = fetch_fixed_income_summary(connection, execution_id)
            elif source_table == STOCKBIT_SOURCE:
                summary = fetch_stockbit_update_summary(connection, execution_id)
            elif source_table == FRESHNESS_SOURCE:
                summary = fetch_broker_freshness(connection, execution_id)
                if summary.behind_sessions < 1:
                    return "not_needed", 0                         # nothing behind: nothing sent, nothing logged
            else:
                summary = fetch_feature04_summary(connection, execution_id)
            if summary is None:
                raise KeyError("execution_id not found")
            if source_table in PUBLISH_TRIGGER_SOURCES:
                changed, run_type = publish_changed(connection, source_table, execution_id, summary)
                self.request_publication(connection, source_table, execution_id, run_type, changed)
            if isinstance(summary, Feature04Summary):
                state, log_id, edit_target = claim_feature04_delivery(
                    connection, summary.delivery_key
                )
                if state == "in_progress":
                    return state, log_id
                if summary.retry_ack_message_id is not None:
                    edit_target = summary.retry_ack_message_id or None
                    state = "edit" if edit_target is not None else "send"
            else:
                state, log_id = claim_delivery(connection, source_table, execution_id)
                edit_target = None
            if state not in ("claimed", "send", "edit"):
                if state == "duplicate" and source_table in PRICE_MONITORING_SOURCES:
                    connection.execute(
                        """UPDATE public."Monitoring_Feature04"
                           SET price_notification_sent_at=coalesce(price_notification_sent_at,CURRENT_TIMESTAMP),
                               updated_at=CURRENT_TIMESTAMP
                           WHERE source_monitor_table=%s AND source_execution_id=%s""",
                        (source_table, execution_id),
                    )
                    connection.commit()
                return state, log_id

            message_ids: list[int] = []
            try:
                if isinstance(summary, BrokerFreshnessSummary):
                    message_ids.append(self.send_message(self.token, self.chat_id, build_freshness_message(summary)))
                elif isinstance(summary, PublisherHealth):
                    message_ids.append(self.send_message(self.token, self.chat_id, build_publisher_message(summary)))
                elif isinstance(summary, AuditQueueHealth):
                    message_ids.append(self.send_message(self.token, self.chat_id, build_audit_queue_message(summary)))
                elif isinstance(summary, PostgresRestart):        # every report is sent, a success included
                    message_ids.append(self.send_message(self.token, self.chat_id,
                                                         build_postgres_restart_message(summary)))
                elif isinstance(summary, ConsensusReport):       # every weekly report is sent, a clean one included
                    message_ids.append(self.send_message(self.token, self.chat_id, build_consensus_message(summary)))
                elif isinstance(summary, StockbitUpdateSummary):
                    # every round is reported, success included (EXEC-STOCKBIT-UPDATER, decision K5)
                    for message in build_stockbit_messages(summary):
                        message_ids.append(self.send_message(self.token, self.chat_id, message))
                elif (summary.status != "SUCCESS" or env_flag("TELEGRAM_NOTIFY_SUCCESS")
                        or (isinstance(summary, Feature04Summary) and state == "edit")):
                    if isinstance(summary, Feature04Summary):
                        message = build_feature04_messages(summary)[0]
                        markup = feature04_markup(summary)
                        if state == "edit" and edit_target is not None:
                            message_ids.append(self.edit_message(
                                self.token,self.chat_id,edit_target,message,markup
                            ))
                        else:
                            message_ids.append(self.send_message(
                                self.token,self.chat_id,message,markup
                            ))
                    else:
                        for message in build_messages(summary):
                            message_ids.append(
                                self.send_message(self.token, self.chat_id, message)
                            )
                mark_sent(connection, log_id, message_ids)
                if source_table in PRICE_MONITORING_SOURCES:
                    connection.execute(
                        """UPDATE public."Monitoring_Feature04"
                           SET price_notification_sent_at=coalesce(price_notification_sent_at,CURRENT_TIMESTAMP),
                               updated_at=CURRENT_TIMESTAMP
                           WHERE source_monitor_table=%s AND source_execution_id=%s""",
                        (source_table, execution_id),
                    )
                    connection.commit()
                return ("edited" if state == "edit" else "sent"), log_id
            except Exception as exc:
                mark_failed(connection, log_id, f"{type(exc).__name__}: {exc}")
                raise


class Handler(BaseHTTPRequestHandler):
    server_version = "SanitiTelegramMonitor/1.0"

    def log_message(self, format: str, *args) -> None:
        print(json.dumps({"event": "http", "message": format % args}), flush=True)

    def send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/health":
            self.send_json(200, {"status": "ok"})
        else:
            self.send_json(404, {"error": "not_found"})

    def do_POST(self) -> None:
        if self.path != "/notify":
            self.send_json(404, {"error": "not_found"})
            return
        expected_secret = self.server.notify_secret
        supplied_secret = self.headers.get("X-Notify-Secret", "")
        if not supplied_secret or not hmac.compare_digest(supplied_secret, expected_secret):
            self.send_json(401, {"error": "unauthorized"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_REQUEST_BYTES:
                raise ValueError("invalid request size")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            state, log_id = self.server.monitor.notify(
                str(payload.get("source_table", "")),
                str(payload.get("execution_id", "")),
                payload.get("details"),
            )
            code = 202 if state == "in_progress" else 200
            self.send_json(code, {"status": state, "log_id": log_id})
        except ValueError as exc:
            self.send_json(400, {"error": str(exc)})
        except KeyError as exc:
            self.send_json(404, {"error": str(exc)})
        except Exception as exc:
            print(
                json.dumps(
                    {"event": "notification_failed", "error": f"{type(exc).__name__}: {exc}"}
                ),
                flush=True,
            )
            self.send_json(500, {"error": "notification_failed"})


class RailwayPrivateHTTPServer(ThreadingHTTPServer):
    """Listen on Railway private IPv6 networking, with IPv4 compatibility."""

    address_family = socket.AF_INET6

    def server_bind(self) -> None:
        try:
            self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        except OSError:
            pass
        super().server_bind()


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"{name} is required")
    return value


def main() -> None:
    monitor = TelegramMonitor(
        required_env("DATABASE_URL"),
        required_env("TELEGRAM_BOT_TOKEN"),
        required_env("TELEGRAM_CHAT_ID"),
    )
    server = RailwayPrivateHTTPServer(("::", int(os.environ.get("PORT", "8080"))), Handler)
    server.monitor = monitor
    server.notify_secret = required_env("TELEGRAM_NOTIFY_SECRET")
    print(json.dumps({"event": "server_started", "port": server.server_port}), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
