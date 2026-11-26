"""EXEC-SECTOR-ANALYSIS S3 (the user's go 2026-11-26: "1A 2A 3 go"; decisions UD66 A-J): the Sector Analysis page's
data, relayed by the page-files mechanism (app/pages.py) as /api/v1/sector/index and /api/v1/sector/file/<name>, behind
the capability sector.view; the example of one day for sector.example is app/examples.py (decision J).

The files are the publisher's family sector/ (verification/sector_analysis/CONTRACT.md section 3): sector-meta,
sector-series, one sector-day-YYYY-MM-DD per date of the date picker (decision I: the 20 newest market dates) and one
sector-stocks-<index> per sector, its index ticker lowercased (sector-stocks-idxfinance): terminal-api keeps only index
names of lowercase letters, digits, '_' and '-', at most 32 characters (apps/terminal-api/app/bucket.py XSECTION_NAME),
as the publisher's own key rule (publisher.py), so 'sector-stocks-' leaves at most 18 characters for the index."""
from __future__ import annotations

import re

from .pages import PageFiles

NAME = re.compile(r'sector-(?:meta|series|day-[0-9]{4}-[0-9]{2}-[0-9]{2}|stocks-[a-z0-9]{1,18})')   # publisher sector.NAME


def Sector(settings, clock=None):
    kw = {'clock': clock} if clock else {}
    return PageFiles(settings, 'sector', NAME, 'Sector Analysis',
                     'sector-meta, sector-series, sector-day-YYYY-MM-DD, sector-stocks-<index> (lowercase, e.g. '
                     'sector-stocks-idxfinance)', **kw)
