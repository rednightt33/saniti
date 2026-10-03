"""M68 (ERRORS_AND_SOLUTIONS.md): the data record shows the scopes the sandbox returns. Those scopes are in the
sandbox's canonical form (``values``, NOT with ``children``), not the model's form, so this test builds them with the
sandbox's own canonical_scope instead of a hand-written sample: a rendering of another service's payload is tested
against that service's output."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from app.data_record import SCOPE_VALUES_MAX_CHARS, scope_text

SANDBOX = Path(__file__).resolve().parents[2] / "market-python-sandbox/app/data_need.py"
TYPES = {"Industry": "text", "Market Board": "text", "Investor Type": "text", "Company Name": "text",
         "Broker": "text", "close": "numeric", "date": "date", "volume": "bigint"}


def _canonical():
    spec = importlib.util.spec_from_file_location("sandbox_data_need_contract", SANDBOX)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve their module by name
    spec.loader.exec_module(module)
    return module.canonical_scope


def pred(column: str, operator: str, value):
    return {"type": "PREDICATE", "column": column, "operator": operator, "value": value}


def test_every_value_of_a_canonical_scope_is_in_the_note() -> None:
    canonical = _canonical()
    cases = [
        (pred("Industry", "EQ", "Banks"), ["Industry EQ Banks"]),
        ({"type": "AND", "children": [pred("Market Board", "EQ", "Nego"), pred("Investor Type", "EQ", "Foreign")]},
         ["Market Board EQ Nego", "Investor Type EQ Foreign"]),
        (pred("Broker", "IN", ["RB", "XL", "AK"]), ["Broker IN AK, RB, XL"]),
        ({"type": "NOT", "child": pred("Company Name", "IN", ["PT Bank Mandiri (Persero) Tbk"])},
         ["NOT Company Name IN PT Bank Mandiri (Persero) Tbk"]),
        ({"type": "OR", "children": [pred("close", "GT", 1000), pred("volume", "BETWEEN", [1, 5])]},
         ["close GT 1000", "volume BETWEEN 1, 5"]),
        (pred("date", "GTE", "2025-01-01"), ["date GTE 2025-01-01"]),
    ]
    for scope, expected in cases:
        text = scope_text(canonical(scope, TYPES))
        for part in expected:
            assert part in text, (text, part)


def test_the_model_form_still_reads() -> None:
    assert scope_text(pred("Industry", "EQ", "Banks")) == "Industry EQ Banks"
    assert scope_text({"type": "NOT", "child": pred("Industry", "EQ", "Banks")}) == "NOT Industry EQ Banks"


def test_a_long_value_list_states_how_many_were_left_out() -> None:
    canonical = _canonical()
    tickers = [f"T{i:03d}" for i in range(300)]
    text = scope_text(canonical(pred("Broker", "IN", tickers), TYPES))
    assert text.startswith("Broker IN T000, T001")
    assert "of 300 values" in text and len(text) < SCOPE_VALUES_MAX_CHARS + 80
