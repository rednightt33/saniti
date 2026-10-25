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
        missing_definitions = connection.execute(
            """SELECT c.table_name, c.column_name
               FROM information_schema.columns c
               JOIN public."Table_Catalog" t
                 ON t.table_schema=c.table_schema AND t.table_name=c.table_name
               WHERE t.category='Feature' AND NOT EXISTS (
                 SELECT 1 FROM public."Feature_Catalog" f
                 WHERE f.feature_table=c.table_name AND f.feature_column=c.column_name
                   AND f.is_active)
               -- a view exposing a Feature table (the *_Stock views) is covered by the definition of the base
               -- column of the same name that it reads
               AND NOT EXISTS (
                 SELECT 1 FROM information_schema.view_column_usage u
                 JOIN public."Feature_Catalog" f
                   ON f.feature_table=u.table_name AND f.feature_column=u.column_name AND f.is_active
                 WHERE u.view_schema=c.table_schema AND u.view_name=c.table_name
                   AND u.table_schema='public' AND u.column_name=c.column_name)
               ORDER BY c.table_name,c.ordinal_position"""
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

    if summary["active"] == 0 or summary["active"] != summary["verified"] or summary["incomplete"] != 0:
        raise RuntimeError(f"Feature semantic summary mismatch: {summary}")
    if any(row["definitions"] != row["physical_columns"] for row in coverage):
        raise RuntimeError(f"Feature semantic coverage mismatch: {coverage}")
    if missing_definitions:
        raise RuntimeError(f"Feature columns without active definitions: {missing_definitions}")
    if ambiguity:
        raise RuntimeError(f"Known clarity regressions returned: {ambiguity}")
    if usage_regressions:
        raise RuntimeError(f"Known usage-guidance regressions returned: {usage_regressions}")
    print({"overall": "PASS", "summary": summary, "coverage": coverage})


if __name__ == "__main__":
    main()
