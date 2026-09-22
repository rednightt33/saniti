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
        r'(?:FROM|JOIN)\s+public\."Feature_0[123]_[^"]+"',
        re.IGNORECASE,
    )
    assert forbidden_scan.search(source) is None


def test_raw_source_mapping_is_explicit():
    assert set(coverage_job.RAW_SOURCES) == {
        "Price_Stock_Indonesia_IDX",
        "IDX_Broker_Summary",
    }
    assert coverage_job.RAW_SOURCES["Price_Stock_Indonesia_IDX"]["reference_for"] == (
        "Feature_01_Stock_Daily",
    )
    assert coverage_job.RAW_SOURCES["IDX_Broker_Summary"]["reference_for"] == (
        "Feature_02_Broker_Rolling",
        "Feature_03_Stock_Broker_Daily",
    )


def test_every_upsert_names_the_functional_identity_index_columns():
    source = Path(coverage_job.__file__).read_text(encoding="utf-8")
    assert "ON CONFLICT DO UPDATE" not in source
    assert source.count(
        "ON CONFLICT (dataset_name, coverage_scope, "
        "(COALESCE(entity_id, ''))) DO UPDATE"
    ) == 6
