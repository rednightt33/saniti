import re
from pathlib import Path

import coverage_job


def test_access_contract_allows_only_coverage_writes():
    coverage_job.validate_access_contract()
    assert coverage_job.WRITE_TABLES == {"AI_data_coverage"}
    assert not (
        coverage_job.READ_TABLES & coverage_job.FORBIDDEN_FEATURE_TABLES
    )


def test_source_contains_no_feature_table_from_or_join():
    source = Path(coverage_job.__file__).read_text(encoding="utf-8")
    forbidden_scan = re.compile(
        r'(?:FROM|JOIN)\s+public\."Feature_[0-9]{2}_[^"]+"',
        re.IGNORECASE,
    )
    assert forbidden_scan.search(source) is None


def test_raw_source_mapping_is_explicit():
    assert set(coverage_job.RAW_SOURCES) == {
        "Price_Stock_Indonesia_IDX",
        "IDX_Broker_Summary",
        "Price_Fixed_Income_Final",
        "idx_event_annotation",
    }
    # EXEC-GO-1025: the event table is its own coverage source, read but never a dependent Feature
    assert coverage_job.RAW_SOURCES["idx_event_annotation"]["reference_for"] == ()
    assert "idx_event_annotation" in coverage_job.READ_TABLES
    assert coverage_job.RAW_SOURCES["Price_Stock_Indonesia_IDX"]["reference_for"] == (
        "Feature_01_Stock_Daily",
        "Feature_04_Technical_Indicator",
        "Feature_01_Stock_Daily_INDEX",
        "Feature_04_Technical_Indicator_INDEX",
    )
    # EXEC-ONBOARD-1: Feature 04 is derived from two raw sources (stock prices, bond price series)
    assert coverage_job.RAW_SOURCES["Price_Fixed_Income_Final"]["reference_for"] == (
        "Feature_04_Technical_Indicator",
    )
    assert "Feature_04_Technical_Indicator" in coverage_job.FORBIDDEN_FEATURE_TABLES
    assert "Universe_Fixed_income" in coverage_job.SNAPSHOTS
    assert coverage_job.RAW_SOURCES["IDX_Broker_Summary"]["reference_for"] == (
        "Feature_02_Broker_Rolling",
        "Feature_03_Stock_Broker_Daily",
        "Feature_05_Foreign_Domestic_Broker_Detail_Stock",
        "Feature_06_Foreign_Domestic_Stock",
        "Feature_02_Broker_Rolling_INDEX",
        "Feature_03_Stock_Broker_Daily_INDEX",
        "Feature_05_Foreign_Domestic_Broker_Detail_INDEX",
        "Feature_06_Foreign_Domestic_INDEX",
    )


def test_the_feature_05_06_stock_views_take_the_stock_universe_coverage():
    """EXEC-M204: the stock views' expected coverage is Broker Summary coverage of the current stock universe (the
    views' own filter, read from IDX_Stock_Universe); Feature 02/03 keep every code; base tables and views are never
    read by the job."""
    for view in ("Feature_05_Foreign_Domestic_Broker_Detail_Stock", "Feature_06_Foreign_Domestic_Stock"):
        assert '"Security Type" = \'stock\'' in coverage_job.BROKER_SUMMARY_FEATURES[view]
        assert view in coverage_job.FORBIDDEN_FEATURE_TABLES
    assert coverage_job.BROKER_SUMMARY_FEATURES["Feature_02_Broker_Rolling"] == ""
    assert {"Feature_05_Foreign_Domestic_Broker_Detail", "Feature_06_Foreign_Domestic"} <= \
        coverage_job.FORBIDDEN_FEATURE_TABLES
    assert "IDX_Stock_Universe" in coverage_job.READ_TABLES


def test_every_upsert_names_the_functional_identity_index_columns():
    source = Path(coverage_job.__file__).read_text(encoding="utf-8")
    assert "ON CONFLICT DO UPDATE" not in source
    assert source.count(
        "ON CONFLICT (dataset_name, coverage_scope, "
        "(COALESCE(entity_id, ''))) DO UPDATE"
    ) == 9


def test_index_codes_come_from_the_universe_and_stock_features_leave_them_out():
    """EXEC-INDEX-1: the index codes are the universe rows of Security Type index, read at run time; the stock Feature
    01/04 expectations exclude them (the INDEX tables hold them); every INDEX table is never read by the job."""
    assert '"Security Type" = \'index\'' in coverage_job.INDEX_CODES
    assert "IHSG" not in Path(coverage_job.__file__).read_text(encoding="utf-8")
    source = Path(coverage_job.__file__).read_text(encoding="utf-8")
    one = source[source.index("def upsert_feature_one_expectations"):source.index("def upsert_manual_feature_expectations")]
    four = source[source.index("def upsert_feature_four_expectations"):source.index("def prune_feature_four_entities")]
    assert "NOT_INDEX_FILTER" in one and "NOT_INDEX_FILTER" in four
    for table in coverage_job.PRICE_INDEX_FEATURES + coverage_job.MARKET_WIDE_INDEX_FEATURES:
        assert table.endswith("_INDEX") and table in coverage_job.FORBIDDEN_FEATURE_TABLES
