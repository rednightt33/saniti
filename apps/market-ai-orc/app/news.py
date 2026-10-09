"""EXEC-Y Fase 2 (user decisions 2026-10-09: "untuk jalur explore ... jawaban selain menjawab tapi juga ngomong history,
serta forward event terkait pertanyaan. konsep mirip v1/ask"; "explore pakai B").

The first round of EXPLORE asks market-web-governor POST /v1/ask (news research: dated headlines over the last two years,
seven years for a when/how-often question, upcoming events, follow-up questions; its own budget and deadline) next to
the database analysis. The backend writes two sections from its structured result, never the model:
  - history and news context: the /v1/ask answer without its source numbers; a line with a figure and no source is
    dropped first, so no unsourced figure reaches the reader (user decision 2026-10-09 "B semua link web hilang pindah
    ke source": the sources are listed in the answer's Sources panel as NEWS evidence, not in the text);
  - upcoming events: the /v1/ask timeline (an event without a source is dropped), whose time is copied verbatim from a
    source title or excerpt.
Its follow-up questions are candidates for app/follow_ups.py. Any failure leaves the answer without the sections.
"""
from __future__ import annotations

import re
import time
from typing import Any
from urllib.parse import urlsplit

import httpx

from . import user_texts as texts

ASK_SECONDS = 200  # /v1/ask stops itself at 180 seconds (WEB_ASK_MAX_SECONDS)
CUT_RE = re.compile(r"^\s*##\s*(Implikasi|Pertanyaan lanjutan|Implications|Follow-up)", re.I | re.M)
CITE_RUN_RE = re.compile(r"(?:\s*[,;]?\s*\[\d+\])+")
HEADING_RE = re.compile(r"^\s*#{1,6}\s*(.+?)\s*$")


class NewsClient:
    def __init__(self, base_url: str, api_key: str, timeout_seconds: float = ASK_SECONDS,
                 transport: httpx.BaseTransport | None = None) -> None:
        self.client = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout_seconds, transport=transport,
                                   headers={"Authorization": f"Bearer {api_key}"})

    def ask(self, request_id: str, question: str, as_of: str | None) -> dict[str, Any]:
        response = self.client.post("/v1/ask", json={"request_id": request_id[:128], "question": question[:1000],
                                                     **({"as_of": as_of} if as_of else {})})
        response.raise_for_status()
        return response.json()


def _safe(url: Any) -> bool:
    return urlsplit(str(url or "")).scheme in ("http", "https")


def _plain(line: str) -> str:
    """A line without its source numbers (they move to the Sources panel)."""
    return re.sub(r"[ \t]+([.,;:])", r"\1", CITE_RUN_RE.sub("", line)).rstrip()


def sections(result: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """The backend-written sections from a /v1/ask result, and a summary for the mode4 block (the follow-up questions
    for app/follow_ups.py and the cited sources as NEWS evidence for the Sources panel). Empty text when the result
    holds nothing citable."""
    cited = {int(c["n"]): c for c in result.get("citations") or [] if isinstance(c, dict)
             and str(c.get("n", "")).isdigit() and _safe(c.get("url"))}
    body = str(result.get("answer_cited") or "")
    cut = CUT_RE.search(body)
    body = body[:cut.start()] if cut else body
    kept, dropped, used = [], 0, set()
    for line in body.splitlines():
        heading = HEADING_RE.match(line)
        numbers = [n for n in map(int, re.findall(r"\[(\d+)\]", line)) if n in cited]
        if heading:
            kept.append(f"**{heading.group(1)}**")
        elif numbers:
            used.update(numbers)
            kept.append(_plain(line))
        elif re.search(r"\d", line):
            dropped += 1  # a figure without a source never reaches the reader
        else:
            kept.append(_plain(line))
    news = re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()
    plan = result.get("plan") or {}
    timeline = []
    for entry in ((plan.get("implications") or {}).get("timeline") or []):
        numbers = [n for n in entry.get("sources") or [] if n in cited]
        if not numbers or not entry.get("event"):
            continue
        used.update(numbers)
        when = str(entry.get("when_text") or "").strip() or texts.NEWS_DATE_UNKNOWN
        status = f" ({entry['status']})" if entry.get("status") else ""
        timeline.append(f"- {when}: {str(entry['event']).strip()}{status}")
    parts = []
    if news and used:
        parts.append(f"**{texts.NEWS_TITLE}**\n\n_{texts.NEWS_NOTE.format(count=len(used))}_\n\n{news}")
    if timeline:
        parts.append(f"**{texts.FORWARD_TITLE}**\n\n" + "\n".join(timeline))
    evidence = [{"kind": "NEWS", "label": str(cited[n].get("title") or cited[n].get("publisher") or "")[:300],
                 "source": {"url": cited[n]["url"], "publisher": cited[n].get("publisher"), "date": cited[n].get("date")}}
                for n in sorted(used)] if parts else []
    summary = {"status": result.get("status"), "sources": len(used) if parts else 0, "lines_dropped": dropped,
               "timeline": len(timeline), "cost": (result.get("usage") or {}).get("cost_usd"),
               "seconds": result.get("seconds"),
               "follow_ups": [str(q.get("question"))[:300] for q in plan.get("follow_ups") or []
                              if isinstance(q, dict) and q.get("question")][:5],
               "evidence": evidence}
    return "\n\n".join(parts), summary


def run(client: NewsClient, request_id: str, question: str, as_of: str | None) -> tuple[str, dict[str, Any]]:
    """One /v1/ask call; ("", {status: FAILED ...}) on any failure (the answer goes on without the sections)."""
    started = time.monotonic()
    try:
        return sections(client.ask(request_id, question, as_of))
    except Exception as exc:  # noqa: BLE001 - the answer never depends on the news call
        return "", {"status": "FAILED", "error": type(exc).__name__, "seconds": round(time.monotonic() - started, 1),
                    "follow_ups": []}
