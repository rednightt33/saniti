"""P14 (user decision 2026-10-01): a text filter value matches its stored spelling regardless of letter case.

Found 2026-10-01: the Governor compares text exactly and the sandbox never checked that a filter value exists, so
"regular" for "Regular" was approved and selected no rows, silently. The approval now matches every text value to the
stored values the Governor's contract lists (`value_domains`: a CHECK list, or a static category column), refuses a
value with no stored match before any extraction, and upper-cases and trims entity codes (Part A A1.2).
"""
from __future__ import annotations

import copy

from app.data_need import validate
from dataneed_fixtures import classification, data_need_catalog, prices, subset, ytd_spec
from test_dataneed_validator import REF

CATALOG = data_need_catalog()


def catalog_with_domains() -> dict:
    catalog = copy.deepcopy(CATALOG)
    catalog["value_domains"] = {"IDX_Stock_Universe": {
        "Industry": {"values": ["Banks", "Coal", "Telecommunication"], "source": "STATIC_TABLE", "complete": True},
        "Sector": {"values": [], "source": "STATIC_TABLE", "complete": False}}}
    return catalog


def run(spec, catalog=None):
    catalog = catalog or catalog_with_domains()
    tables = sorted({r["source_table"] for r in spec["data_requests"]})
    return validate(spec, subset(catalog, tables), REF)


def scope_of(outcome, rid):
    return outcome.approved["requests"][rid]["scope"]


def with_scope(scope: dict) -> dict:
    return ytd_spec(data_requests=[prices(), classification(scope=scope)])


def test_a_value_in_another_case_selects_the_stored_value() -> None:
    outcome = run(with_scope({"type": "PREDICATE", "column": "Industry", "operator": "EQ", "value": "banks"}))
    assert outcome.status == "APPROVED", outcome.issues
    assert scope_of(outcome, "data_request_1_B")["values"] == ["Banks"]
    assert {"code": "TEXT_VALUE_RESOLVED", "data_request_id": "data_request_1_B",
            "field_path": "data_requests[1].scope", "from": "banks", "to": "Banks",
            "source": "STATIC_TABLE"} in outcome.warnings
    # the approved scope (and its hash) is the same as for the stored spelling
    exact = run(with_scope({"type": "PREDICATE", "column": "Industry", "operator": "EQ", "value": "Banks"}))
    assert scope_of(exact, "data_request_1_B") == scope_of(outcome, "data_request_1_B")
    assert not [w for w in exact.warnings if w["code"] == "TEXT_VALUE_RESOLVED"]


def test_a_value_that_is_not_stored_is_refused_before_extraction_with_the_stored_values() -> None:
    outcome = run(with_scope({"type": "PREDICATE", "column": "Industry", "operator": "IN",
                              "value": ["BANKS", "Bankz"]}))
    assert outcome.status == "REVISION_REQUIRED"
    refused = [i for i in outcome.issues if i["code"] == "VALUE_NOT_FOUND"]
    assert len(refused) == 1 and refused[0]["rejected_value"].startswith("Bankz (stored values: Banks, Coal")


def test_two_stored_values_that_differ_only_in_case_are_ambiguous() -> None:
    catalog = catalog_with_domains()
    catalog["value_domains"]["IDX_Stock_Universe"]["Industry"]["values"] = ["BANKS", "Banks"]
    outcome = run(with_scope({"type": "PREDICATE", "column": "Industry", "operator": "EQ", "value": "banks"}),
                  catalog)
    assert [i["code"] for i in outcome.issues] == ["VALUE_AMBIGUOUS"]


def test_entity_codes_are_upper_cased_and_an_incomplete_list_keeps_the_value() -> None:
    entities = {"type": "PREDICATE", "column": "ticker", "operator": "IN", "value": [" bbca", "BBRI"]}
    outcome = run(ytd_spec(data_requests=[prices(scope=entities), classification()]))
    assert outcome.status == "APPROVED", outcome.issues
    assert scope_of(outcome, "data_request_1_A")["values"] == ["BBCA", "BBRI"]
    sector = run(with_scope({"type": "PREDICATE", "column": "Sector", "operator": "EQ", "value": "financials"}))
    assert sector.status == "APPROVED" and scope_of(sector, "data_request_1_B")["values"] == ["financials"]


def test_a_contract_without_value_domains_keeps_todays_behaviour() -> None:
    outcome = run(with_scope({"type": "PREDICATE", "column": "Industry", "operator": "EQ", "value": "banks"}),
                  copy.deepcopy(CATALOG))
    assert outcome.status == "APPROVED" and scope_of(outcome, "data_request_1_B")["values"] == ["banks"]
