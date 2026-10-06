"""Multiple-testing correction across variants and turns (user decision 2026-10-06, "2+5 Varian + koreksi", merged into
EXEC-3 and EXEC-A; AI_ENABLE_ASK_BACK).

Every hypothesis test and research angle that ran in a conversation is in its data record's findings (the trial
ledger, data_record.add_finding). A user who tests several variants (two thresholds, two horizons) or tests again in a
later turn has run several tests of one question, so a p-value below 0.05 in one of them says less than it seems. The
backend corrects the p-values of every test in the ledger together: Holm (family-wise error) by default, Benjamini-
Hochberg (false discovery rate) when a test's own multiple_testing_policy asks for it. The family is the whole ledger
of the conversation, which is conservative when a conversation tests unrelated questions. The correction is shown
next to the raw p-values for every test, also the ones that do not pass; it never changes a verdict (each test's own
policy inside the sandbox stays as it is).

The p-value of a hypothesis test is its angle A (the mean difference whose interval decides the verdict); of a
research angle, its primary estimate's raw p-value.
"""
from __future__ import annotations

from typing import Any

ALPHA = 0.05
MIN_FAMILY = 2
CORRECTION_KEY = "conversation_correction"


def holm(p_values: list[float]) -> list[float]:
    """Holm step-down adjusted p-values (monotone, at most 1)."""
    m = len(p_values)
    adjusted = [0.0] * m
    running = 0.0
    for rank, index in enumerate(sorted(range(m), key=p_values.__getitem__)):
        running = max(running, min(1.0, (m - rank) * p_values[index]))
        adjusted[index] = running
    return adjusted


def benjamini_hochberg(p_values: list[float]) -> list[float]:
    """Benjamini-Hochberg step-up adjusted p-values (monotone, at most 1)."""
    m = len(p_values)
    adjusted = [0.0] * m
    running = 1.0
    for position, index in enumerate(sorted(range(m), key=p_values.__getitem__, reverse=True)):
        rank = m - position
        running = min(running, p_values[index] * m / rank)
        adjusted[index] = min(1.0, running)
    return adjusted


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if 0.0 <= number <= 1.0 else None


def tests(record: dict[str, Any] | None) -> list[dict[str, Any]]:
    """The tests of the conversation's trial ledger that have a p-value, oldest first."""
    found = []
    for entry in (record or {}).get("findings") or []:
        finding = entry.get("finding") or {}
        if entry.get("kind") == "HYPOTHESIS":
            p_value = _number((finding.get("angle_a") or {}).get("p_value"))
            policy = (finding.get("parameters") or {}).get("multiple_testing_policy")
        elif entry.get("kind") == "ANGLE":
            p_value = _number(((finding.get("estimates") or {}).get("primary") or {}).get("p_value"))
            policy = (finding.get("multiple_testing") or {}).get("policy") \
                if isinstance(finding.get("multiple_testing"), dict) else None
        else:
            continue
        if p_value is not None:
            found.append({"id": str(entry.get("id")), "kind": entry["kind"], "request_id": entry.get("request_id"),
                          "p_value": p_value, "policy": policy})
    return found


def correct(record: dict[str, Any] | None) -> dict[str, Any] | None:
    """The correction over every test of the ledger ({policy, family_size, alpha, tests: [{id, p_value, p_adjusted,
    below_alpha}]}), written into each test's finding as conversation_correction; None with fewer than two tests."""
    found = tests(record)
    if len(found) < MIN_FAMILY:
        return None
    policy = "BENJAMINI_HOCHBERG" if any(t["policy"] == "BENJAMINI_HOCHBERG" for t in found) else "HOLM"
    adjusted = (benjamini_hochberg if policy == "BENJAMINI_HOCHBERG" else holm)([t["p_value"] for t in found])
    result = {"policy": policy, "family_size": len(found), "alpha": ALPHA, "tests": [
        {"id": t["id"], "kind": t["kind"], "request_id": t["request_id"], "p_value": t["p_value"],
         "p_adjusted": round(p, 6), "below_alpha": p < ALPHA} for t, p in zip(found, adjusted)]}
    by_id = {t["id"]: t for t in result["tests"]}
    for entry in (record or {}).get("findings") or []:
        test = by_id.get(str(entry.get("id")))
        if test is not None and isinstance(entry.get("finding"), dict):
            entry["finding"][CORRECTION_KEY] = {"policy": policy, "family_size": len(found),
                                                "p_adjusted": test["p_adjusted"]}
    return result


def _decimal(value: float) -> str:
    return f"{value:.3g}".replace(".", ",")


def line(correction: dict[str, Any]) -> str:
    """The answer's limitation line: every test with its raw and corrected p-value, also the ones that do not pass."""
    name = "Holm" if correction["policy"] == "HOLM" else "Benjamini-Hochberg"
    items = "; ".join(f"{t['id']} p {_decimal(t['p_value'])} → {_decimal(t['p_adjusted'])}"
                      + ("" if t["below_alpha"] else " (tidak lolos)") for t in correction["tests"])
    return (f"Koreksi uji berganda untuk semua uji di percakapan ini ({name}, {correction['family_size']} uji, "
            f"alpha {_decimal(correction['alpha'])}): {items}. Semua uji ditampilkan, juga yang tidak lolos; "
            "putusan tiap uji tidak berubah.")
