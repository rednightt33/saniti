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
    assert len(refused) == 1 and refused[0]["rejected_value"].startswith(
        "Bankz is not a stored value of IDX_Stock_Universe.Industry (likely stored values: Banks;")


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


# ---------------------------------------------------------------- EXEC-IMPL-1016 O1: entity codes come from the table

def prices_with(domain: dict, scope: dict) -> object:
    catalog = catalog_with_domains()
    catalog["value_domains"]["Price_Stock_Indonesia_IDX"] = {"ticker": domain}
    return run(ytd_spec(data_requests=[prices(scope=scope), classification()]), catalog)


REGISTERED = {"values": ["BBCA", "BBRI", "BMRI", "MAHA"], "source": "COVERAGE", "complete": True, "kind": "ENTITY",
              "aliases": {"bri": ["BBRI"], "bca": ["BBCA"]}}


def test_a_name_typed_as_a_code_is_refused_with_the_code_its_alias_names() -> None:
    outcome = prices_with(REGISTERED, {"type": "PREDICATE", "column": "ticker", "operator": "IN",
                                       "value": ["BRI", "bmri"]})
    assert outcome.status == "REVISION_REQUIRED"
    refused = [i for i in outcome.issues if i["code"] == "VALUE_NOT_FOUND"]
    assert len(refused) == 1
    assert refused[0]["rejected_value"].startswith("BRI is not a stored value of Price_Stock_Indonesia_IDX.ticker "
                                                   "(likely stored values: BBRI")
    assert "search_values(Price_Stock_Indonesia_IDX.ticker)" in refused[0]["rejected_value"]


def test_a_registered_code_in_another_case_resolves() -> None:
    outcome = prices_with(REGISTERED, {"type": "PREDICATE", "column": "ticker", "operator": "EQ", "value": " bbri"})
    assert outcome.status == "APPROVED", outcome.issues
    assert scope_of(outcome, "data_request_1_A")["values"] == ["BBRI"]
    assert any(w["code"] == "TEXT_VALUE_RESOLVED" and w["source"] == "COVERAGE" for w in outcome.warnings)


def test_an_unknown_code_has_no_invented_candidates() -> None:
    outcome = prices_with(REGISTERED, {"type": "PREDICATE", "column": "ticker", "operator": "EQ", "value": "QQQQ"})
    refused = [i for i in outcome.issues if i["code"] == "VALUE_NOT_FOUND"]
    assert "no stored value is close" in refused[0]["rejected_value"]


def test_a_code_missing_from_an_incomplete_reference_list_is_kept_with_a_warning() -> None:
    reference = {"values": ["BBCA", "BBRI"], "source": "REFERENCE_TABLE", "complete": False, "kind": "ENTITY"}
    outcome = prices_with(reference, {"type": "PREDICATE", "column": "ticker", "operator": "IN",
                                      "value": ["newx", "bbca"]})
    assert outcome.status == "APPROVED", outcome.issues
    assert scope_of(outcome, "data_request_1_A")["values"] == ["BBCA", "NEWX"]
    warned = [w for w in outcome.warnings if w["code"] == "VALUE_NOT_IN_REFERENCE"]
    assert [w["value"] for w in warned] == ["NEWX"] and warned[0]["source"] == "REFERENCE_TABLE"
