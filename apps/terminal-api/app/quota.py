"""Quota decisions (DESIGN.md 3.1). The limits come from terminal.quota (+ terminal.quota_override); the usage is read
from terminal.access_log under a per-subscriber lock, so concurrent requests cannot both pass one remaining slot.

Service accounts (EXEC-MU-RUNTIME T1, migration 20261028_100) are not people: their grants are counted per clock hour
in terminal.usage_hour (one UPSERT that returns the hour's totals, inside the grant's transaction) and held to a
ceiling, a runaway guard (a caller stuck in a loop), not a person's quota (check_service)."""
import datetime as dt
import math
from dataclasses import dataclass

REF = 'REF'  # reference files (ticker list, broker list) do not count as an opened ticker


@dataclass(frozen=True)
class Usage:
    files_hour: int
    tickers_hour: frozenset
    tickers_day: frozenset
    bytes_day: int
    history_hour: int


@dataclass(frozen=True)
class Refusal:
    quota: str
    limit: int
    window: str

    def message(self):
        return (f'Quota {self.quota} reached ({self.limit} per {self.window}). It frees up as older requests leave the '
                f'rolling {self.window}; ask the administrator if you need a higher limit.')


def check(limits: dict, usage: Usage, *, files: int = 0, ticker: str | None = None, bytes_: int = 0,
          history: int = 0) -> Refusal | None:
    if files and usage.files_hour + files > limits['files_per_hour']:
        return Refusal('files_per_hour', limits['files_per_hour'], 'hour')
    if history and usage.history_hour + history > limits['history_per_hour']:
        return Refusal('history_per_hour', limits['history_per_hour'], 'hour')
    if ticker and ticker != REF:
        if ticker not in usage.tickers_hour and len(usage.tickers_hour) + 1 > limits['tickers_per_hour']:
            return Refusal('tickers_per_hour', limits['tickers_per_hour'], 'hour')
        if ticker not in usage.tickers_day and len(usage.tickers_day) + 1 > limits['tickers_per_day']:
            return Refusal('tickers_per_day', limits['tickers_per_day'], '24 hours')
    if bytes_ and usage.bytes_day + bytes_ > limits['megabytes_per_day'] * 1_000_000:
        return Refusal('megabytes_per_day', limits['megabytes_per_day'], '24 hours')
    return None


# EXEC-MU-RUNTIME T1: the three ceilings of a service account per clock hour (UTC), terminal.quota rows of migration
# 20261028_100 (a service's own value: terminal.quota_override). (quota name, counter, unit, scale of the counter)
SERVICE_CEILINGS = (('service_grants_per_hour', 'grants', 'grants', 1),
                    ('service_files_per_hour', 'files', 'files', 1),
                    ('service_megabytes_per_hour', 'bytes', 'MB', 1_000_000))
SERVICE_EXAMPLE = 'a 12-stock backtest job takes about 16 grants and 60 files; a screener refresh 2 grants'


@dataclass(frozen=True)
class ServiceRefusal:
    service: str
    quota: str
    limit: int
    unit: str
    used: int | float         # megabytes keep their fraction (check_service)
    hour_start: dt.datetime

    def message(self):
        reset = (self.hour_start + dt.timedelta(hours=1)).astimezone(dt.timezone.utc).strftime('%H:%M UTC')
        used = f'{self.used:,.2f}'.rstrip('0').rstrip('.') if isinstance(self.used, float) else f'{self.used:,}'
        return (f'Service account {self.service}: ceiling {self.quota} reached ({used} of {self.limit:,} {self.unit} '
                f'in the clock hour from {self.hour_start.astimezone(dt.timezone.utc).strftime("%H:%M UTC")}). This '
                f'runaway guard refuses the service\'s grants until {reset}, when the next hour starts. Fix: look for a '
                f'loop in the {self.service} logs (the same request repeated); if the volume is real, the administrator '
                f'raises terminal.quota_override {self.quota} for this account. Example of normal use: {SERVICE_EXAMPLE}.')


def check_service(service: str, limits: dict, used: dict) -> ServiceRefusal | None:
    """`used`: the hour's totals after this grant (terminal.usage_hour, RETURNING hour_start, grants, files, bytes)."""
    for name, counter, unit, scale in SERVICE_CEILINGS:
        if used[counter] > limits[name] * scale:
            # megabytes with their fraction: 1,521,000 bytes over a 1 MB ceiling reads "1.52 of 1 MB", never "1 of 1";
            # an overshoot below 0.005 MB is rounded up, so the message never reads as within the ceiling
            # ("100,000.01 of 100,000 MB", not "100,000 of 100,000 MB")
            amount = used[counter] if scale == 1 else round(used[counter] / scale, 2)
            if scale != 1 and amount <= limits[name]:
                amount = math.ceil(used[counter] * 100 / scale) / 100
            return ServiceRefusal(service, name, limits[name], unit, amount, used['hour_start'])
    return None
