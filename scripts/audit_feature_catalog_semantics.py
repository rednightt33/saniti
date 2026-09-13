#!/usr/bin/env python3
"""Fail closed when active Feature semantics are incomplete or drift from schema."""

from __future__ import annotations

import os

import psycopg
from psycopg.rows import dict_row


def main() -> None:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL is required")

    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        summary = connection.execute(
            '''SELECT count(*)::integer AS active,
                      count(*) FILTER (WHERE semantic_review_status='CALCULATION_VERIFIED')::integer AS verified,
                      count(*) FILTER (WHERE btrim(analytical_interpretation)='' OR btrim(recommended_use)=''
                        OR btrim(misuse_warning)='' OR cardinality(validation_evidence)=0)::integer AS incomplete,
                      count(DISTINCT feature_table)::integer AS feature_tables
               FROM public."Feature_Catalog" WHERE is_active'''
        ).fetchone()
        coverage = connection.execute(
            '''SELECT f.feature_table, count(*)::integer AS definitions,
                      count(c.column_name)::integer AS physical_columns
               FROM public."Feature_Catalog" f
               LEFT JOIN information_schema.columns c
                 ON c.table_schema='public' AND c.table_name=f.feature_table
                AND c.column_name=f.feature_column
               WHERE f.is_active GROUP BY f.feature_table ORDER BY f.feature_table'''
        ).fetchall()
        ambiguity = connection.execute(
            '''SELECT feature_table,feature_column FROM public."Feature_Catalog"
               WHERE is_active AND (
                    (feature_table='Feature_02_Broker_Rolling'
                     AND feature_column IN ('net_value_1d','net_lots_1d')
                     AND definition NOT ILIKE '%%positive%%negative%%')
                 OR (feature_table='Feature_03_Stock_Broker_Daily'
                     AND feature_column='ticker' AND null_rule NOT ILIKE '%%source symbol%%')
                 OR (feature_table='Feature_03_Stock_Broker_Daily'
                     AND feature_column='market_board' AND null_rule NOT ILIKE '%%never implicitly combined%%')
               )'''
        ).fetchall()
        usage_regressions = connection.execute(
            '''SELECT feature_table,feature_column FROM public."Feature_Catalog"
               WHERE is_active AND (
                    (feature_category='Price' AND recommended_use ILIKE '%%only for the operational%%')
                 OR (feature_column='calculated_at' AND recommended_use ILIKE '%%peer group%%')
                 OR (feature_table='Feature_03_Stock_Broker_Daily'
                     AND feature_column IN ('top_buyer','top_seller')
                     AND recommended_use NOT ILIKE '%%exact ticker and board%%')
               )'''
        ).fetchall()

    if summary != {"active": 91, "verified": 91, "incomplete": 0, "feature_tables": 3}:
        raise RuntimeError(f"Feature semantic summary mismatch: {summary}")
    if any(row["definitions"] != row["physical_columns"] for row in coverage):
        raise RuntimeError(f"Feature semantic coverage mismatch: {coverage}")
    if ambiguity:
        raise RuntimeError(f"Known clarity regressions returned: {ambiguity}")
    if usage_regressions:
        raise RuntimeError(f"Known usage-guidance regressions returned: {usage_regressions}")
    print({"overall": "PASS", "summary": summary, "coverage": coverage})


if __name__ == "__main__":
    main()
