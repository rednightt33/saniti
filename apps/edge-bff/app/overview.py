"""EXEC-OVERVIEW O4 (user go 2026-11-15: "1 ok, 2 ok, 3 ok, go"; decision 7: the owner's only, as the Radar): the
Market Overview page's data, relayed by the page-files mechanism (app/pages.py) as /api/v1/overview/index and
/api/v1/overview/file/<name>."""
from __future__ import annotations

import re

from .pages import PageFiles

NAME = re.compile(r'overview-(?:meta|series|day-[0-9]{4}-[0-9]{2}-[0-9]{2})')   # publisher overview.NAME


def Overview(settings, clock=None):
    kw = {'clock': clock} if clock else {}
    return PageFiles(settings, 'overview', NAME, 'Market Overview', 'overview-meta, overview-series, overview-day-YYYY-MM-DD', **kw)
