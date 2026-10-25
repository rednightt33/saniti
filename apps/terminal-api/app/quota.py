"""Quota decisions (DESIGN.md 3.1). The limits come from terminal.quota (+ terminal.quota_override); the usage is read
from terminal.access_log under a per-subscriber lock, so concurrent requests cannot both pass one remaining slot."""
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
