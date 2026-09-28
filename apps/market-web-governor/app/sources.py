"""Default source policy: official domains, trusted media, the blocklist, and verbatim-copy detection. Decided by
code, never by a model."""
from __future__ import annotations

import os
import re
from collections.abc import Iterable
from typing import Any

UNVERIFIED_NOTE = "Sumber ini belum diverifikasi"

BUILT_IN_PRIMARY = ("idx.co.id", "ojk.go.id", "bi.go.id", "bps.go.id", "ksei.co.id", "kppu.go.id", "sec.gov")

DEFAULT_TRUSTED_MEDIA = (
    "bisnis.com", "kontan.co.id", "cnbcindonesia.com", "kompas.com", "katadata.co.id", "investor.id",
    "idxchannel.com", "idnfinancials.com", "tempo.co", "antaranews.com", "thejakartapost.com", "reuters.com",
    "bloomberg.com", "bloombergtechnoz.com", "dealstreetasia.com", "asia.nikkei.com", "ft.com", "wsj.com",
)


def domain_matches(domain: str, rule: str) -> bool:
    rule = rule.lower()
    if rule.startswith("*."):
        rule = rule[2:]
    return domain == rule or domain.endswith("." + rule)


def _env_list(name: str) -> tuple[str, ...]:
    return tuple(item.strip().lower() for item in os.environ.get(name, "").split(",") if item.strip())


def trusted_media() -> tuple[str, ...]:
    return DEFAULT_TRUSTED_MEDIA + _env_list("WEB_TRUSTED_MEDIA_EXTRA")


def blocklist() -> tuple[str, ...]:
    return _env_list("WEB_SOURCE_BLOCKLIST")


def source_tier(domain: str, primary_domains: Iterable[str], trusted_domains: Iterable[str]) -> str:
    if domain.endswith(".go.id") or domain.endswith(".gov") or any(
        domain_matches(domain, rule) for rule in (*BUILT_IN_PRIMARY, *primary_domains)
    ):
        return "PRIMARY"
    if any(domain_matches(domain, rule) for rule in (*trusted_domains, *trusted_media())):
        return "TRUSTED_SECONDARY"
    return "SECONDARY"


def is_blocklisted(domain: str) -> bool:
    return any(domain_matches(domain, rule) for rule in blocklist())


def _comparable(text: str | None) -> str:
    return re.sub(r"[^0-9a-z]+", " ", (text or "").lower()).strip()


TIER_RANK = {"PRIMARY": 0, "TRUSTED_SECONDARY": 1, "SECONDARY": 2, "UNKNOWN": 3}


def mark_copies(evidence: list[dict[str, Any]], minimum: int = 200) -> int:
    """Mark an excerpt that repeats, word for word, an excerpt from another domain. The copy is the item from the
    lower tier (then the later one); it stays in the results but is unverified. Returns the number marked."""
    marked = 0
    comparable = [_comparable(item.get("excerpt")) for item in evidence]
    for index, item in enumerate(evidence):
        if len(comparable[index]) < minimum or item.get("copy_of"):
            continue
        for other_index, other in enumerate(evidence):
            if other_index == index or other["domain"] == item["domain"] or len(comparable[other_index]) < minimum:
                continue
            a, b = comparable[index], comparable[other_index]
            if not (a in b or b in a):
                continue
            item_rank = (TIER_RANK.get(item["source_tier"], 3), index)
            other_rank = (TIER_RANK.get(other["source_tier"], 3), other_index)
            if item_rank > other_rank and not other.get("copy_of"):
                item["copy_of"] = other["evidence_id"]
                item["source_verified"] = False
                item["source_note"] = f"{UNVERIFIED_NOTE}: teksnya sama dengan sumber {other['domain']}"
                marked += 1
                break
    return marked
