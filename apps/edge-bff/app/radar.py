"""EXEC-RADAR R6 (user go 2026-11-14: "Ok go"; the Radar is an admin page, the owner's only): the Radar page's data,
relayed by the page-files mechanism (app/pages.py) as /api/v1/radar/index and /api/v1/radar/file/<name>."""
from __future__ import annotations

import re

import httpx  # noqa: F401  (tests replace its client here)

from .pages import CACHE_BYTES as RADAR_CACHE_BYTES, INDEX_SECONDS, SHA, PageFiles  # noqa: F401

NAME = re.compile(r'radar-(?:meta|days|board-[0-9]{4}-[0-9]{2}-[0-9]{2}|f-[a-z0-9_]{1,24})')   # publisher radar.NAME


def Radar(settings, clock=None):
    kw = {'clock': clock} if clock else {}
    return PageFiles(settings, 'radar', NAME, 'Radar', 'radar-meta, radar-days, radar-board-YYYY-MM-DD, radar-f-<filter>', **kw)
