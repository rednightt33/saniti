import copy
from datetime import date

import pytest

import stockbit_events as se


def movement(**over):
    m = {
        "id": "1000000439", "name": "HENDRA TANUMIHARDJA", "symbol": "BBCA", "date": "25 Mar 26",
        "previous": {"value": "193,206", "percentage": "0.0002"},
        "current": {"value": "341,139", "percentage": "0.0003"},
        "changes": {"value": "+147,933", "percentage": "+0.0001"},
        "nationality": "NATIONALITY_TYPE_LOCAL", "action_type": "ACTION_TYPE_BUY",
        "data_source": {"label": "Sumber: IDX", "type": "SOURCE_TYPE_IDX"},
        "broker_detail": {"code": "", "group": "BROKER_GROUP_UNSPECIFIED"},
        "badges": ["SHAREHOLDER_BADGE_DIREKTUR"], "price": {"raw": {"value": "6982"}},
        "value": {"raw": {"value": "1032868206"}}, "is_estimated_price": False, "purpose": "",
    }
    m.update(over)
    return m


def test_insider_row_fields():
    (r,) = se.insider_rows("BBCA", [movement()])
    assert r["transaction_date"] == date(2026, 3, 25)
    assert (r["shares_before"], r["shares_after"], r["shares_change"]) == (193206, 341139, 147933)
    assert r["action_type"] == "BUY" and r["holder_nationality"] == "LOCAL" and r["data_origin"] == "IDX"
    assert r["holder_roles"] == ["DIREKTUR"] and r["broker_code"] is None
    assert r["insider_key"].startswith("INS:") and r["insider_key"].endswith(":1")
    assert r["source_copies"] == 1


def test_exact_copy_is_one_row_with_count():
    rows = se.insider_rows("BBCA", [movement(), movement()])
    assert len(rows) == 1 and rows[0]["source_copies"] == 2


def test_same_movement_from_idx_and_ksei_stays_two_rows():
    ksei = movement(data_source={"label": "Sumber: KSEI", "type": "SOURCE_TYPE_KSEI"})
    rows = se.insider_rows("BBCA", [movement(), ksei])
    assert {r["data_origin"] for r in rows} == {"IDX", "KSEI"}
    assert len({r["insider_key"] for r in rows}) == 2


def test_key_ignores_percent_and_listing_order():
    a = movement(purpose="x")
    b = movement(purpose="y")
    k1 = sorted(r["insider_key"] for r in se.insider_rows("BBCA", [a, b]))
    k2 = sorted(r["insider_key"] for r in se.insider_rows("BBCA", [b, a]))
    assert k1 == k2 and len(k1) == 2
    flipped = movement(current={"value": "341,139", "percentage": "-922337203685477.62"})
    sentinel = movement(current={"value": "341,139", "percentage": "922337203685477.62"})
    assert se.insider_rows("BBCA", [flipped])[0]["insider_key"] == se.insider_rows("BBCA", [sentinel])[0]["insider_key"]


def test_wrong_symbol_in_ticker_pull_stops():
    with pytest.raises(se.StockbitError):
        se.insider_rows("TLKM", [movement()])


@pytest.mark.parametrize("cur,chg,shares_after,shares_change,flag", [
    ("33.47", "-1.43", "1,000,000", "-42,725", "OK"),          # 33.47 x 42,725 / 1,000,000 = 1.43
    ("0.73", "+0.0017", "209,889,470", "+470,000", "ROUNDING"),  # ADRO 2026-10-19: current % has two decimals
    ("5.60", "+0.0022", "154,165,300", "+50,000", "INCONSISTENT"),  # ABMM 2026-01-09: 5.60 x 50,000 / 154,165,300 = 0.0018
    ("66.87", "+3.98", "884,634,253", "+485,436,893", "INCONSISTENT"),  # share base changed (rights issue)
    ("5.60", "0.00", "154,165,300", "0", "NOT_CHECKABLE"),
    ("922337203685477.62", "0.00", "2,300", "+2,300", "INVALID_SENTINEL"),
])
def test_pct_quality_flag(cur, chg, shares_after, shares_change, flag):
    m = movement(current={"value": shares_after, "percentage": cur}, changes={"value": shares_change, "percentage": chg})
    assert se.pct_quality_flag(m) == flag


def test_sentinel_percent_is_null():
    m = movement(current={"value": "341,139", "percentage": "-922337203685477.62"})
    assert se.insider_rows("BBCA", [m])[0]["pct_after"] is None


def corp(slug, **row):
    base = {"company_symbol": "BBCA", "company_id": "1"}
    base.update(row)
    return {"slug": slug, "year": 2026, "row": base}


def test_corporate_action_dates_and_key():
    (r,) = se.dedupe_corp([corp("dividend", dividend_id="77", dividend_cumdate="2026-03-30", dividend_exdate="2026-03-31",
                                dividend_recdate="2026-04-01", dividend_paydate="2026-04-20")], {"BBCA"})
    assert r["corporate_action_key"] == "dividend:77" and r["action_type"] == "DIVIDEND"
    assert r["annotation_date"] == date(2026, 3, 31) and r["annotation_date_role"] == "EX_DATE"
    assert (r["cum_date"], r["pay_date"]) == (date(2026, 3, 30), date(2026, 4, 20))


def test_structured_warrant_goes_to_underlying():
    (r,) = se.dedupe_corp([corp("warrant", company_symbol="ACESYUCK7A", wrant_id="3586",
                                wrant_trading_from="2026-10-14", wrant_trading_end="2027-05-25")], {"ACES"})
    assert (r["ticker"], r["instrument_code"]) == ("ACES", "ACESYUCK7A")
    (u,) = se.dedupe_corp([corp("warrant", company_symbol="ZZZZYUCK7A", wrant_id="1", wrant_trading_from="2026-10-14")],
                          {"ACES"})
    assert (u["ticker"], u["instrument_code"]) == ("ZZZZYUCK7A", None)


def test_same_event_in_two_years_is_one_row_and_must_agree():
    a = corp("warrant", wrant_id="9", wrant_trading_from="2026-01-02")
    b = copy.deepcopy(a)
    b["year"] = 2027
    assert len(se.dedupe_corp([a, b], {"BBCA"})) == 1
    b["row"]["wrant_trading_end"] = "2027-12-31"
    with pytest.raises(se.StockbitError):
        se.dedupe_corp([a, b], {"BBCA"})


def test_missing_annotation_date_or_id_stops():
    with pytest.raises(se.StockbitError):
        se.dedupe_corp([corp("rups", rups_id="5", rups_date="0000-00-00")], {"BBCA"})
    with pytest.raises(se.StockbitError):
        se.dedupe_corp([corp("rups", rups_date="2026-01-01")], {"BBCA"})


def test_every_type_maps_its_date_fields():
    for slug, spec in se.CORP_TYPES.items():
        assert spec["ann"] and spec["role"] and spec["id"], slug
        assert spec["ann"] in [spec.get(f) for f in se.DATE_FIELDS] or slug in ("dividend", "stock_dividend",
                                                                                 "stocksplit", "reversesplit",
                                                                                 "bonus", "rightissue"), slug
