"""G25: the catalog's request_key_columns and the sandbox DataNeedValidator apply one rule (the key pairs without the
time pair). The sandbox module is loaded from the repository when it is present."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from app.tools.catalog import entity_key_pairs

SANDBOX = Path(__file__).resolve().parents[2] / "market-python-sandbox/app/data_need.py"
CASES = [
    (["ticker", "date"], ["ticker", "date"], "date", "date"),
    (["Date", "Symbol", "Broker"], ["date", "ticker", "broker"], "Date", "date"),
    (["ticker"], ["Ticker"], None, None),
    (["ticker", "date"], ["ticker", "trade_date"], "date", "date"),  # not the catalog's time pair: kept
    (["date", "ticker"], ["date", "ticker"], "date", None),
]


def test_the_time_pair_is_dropped_and_nothing_else() -> None:
    assert entity_key_pairs(*CASES[0]) == [("ticker", "ticker")]
    assert entity_key_pairs(*CASES[1]) == [("Symbol", "ticker"), ("Broker", "broker")]
    assert entity_key_pairs(*CASES[3]) == [("ticker", "ticker"), ("date", "trade_date")]


def test_the_catalog_rule_equals_the_validator_rule() -> None:
    if not SANDBOX.exists():
        pytest.skip("market-python-sandbox is not in this checkout")
    spec = importlib.util.spec_from_file_location("sandbox_data_need", SANDBOX)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # its dataclasses look the module up by name
    try:
        spec.loader.exec_module(module)
    except ImportError as exc:  # its package-relative imports need the sandbox's app package
        pytest.skip(f"sandbox module not importable here: {exc}")
    finally:
        sys.modules.pop(spec.name, None)
    for case in CASES:
        assert entity_key_pairs(*case) == module.entity_key_pairs(*case)
