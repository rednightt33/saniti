"""Read-only export of the active Feature_Catalog rows the vocabulary covers (the inventory of
scripts/sync_feature_vocabulary.py), plus the live Feature_Vocabulary and the AI/Column catalog copies of the fields
the corrections touch."""
import json, os, sys, psycopg
from psycopg.rows import dict_row
SOURCES = [t + s for t in ("Feature_01_Stock_Daily", "Feature_02_Broker_Rolling", "Feature_03_Stock_Broker_Daily",
                           "Feature_05_Foreign_Domestic_Broker_Detail", "Feature_06_Foreign_Domestic") for s in ("", "_INDEX")]
with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as db:
    db.execute("SET default_transaction_read_only = on")
    inv = db.execute('''SELECT f.*, c.ordinal_position FROM public."Feature_Catalog" f
        JOIN information_schema.columns c ON c.table_schema='public' AND c.table_name=f.feature_table AND c.column_name=f.feature_column
        WHERE f.is_active AND f.feature_table = ANY(%s) ORDER BY f.feature_table, c.ordinal_position''', (SOURCES,)).fetchall()
    vocab = db.execute('SELECT * FROM public."Feature_Vocabulary" ORDER BY source_table, display_order').fetchall()
    calc = db.execute('''SELECT calculation_name, version, target_table, definition, defaults, parameters, missing_data_policy, status
        FROM public."AI_calculation_catalog" WHERE status='ACTIVE' AND (target_table = ANY(%s) OR target_table LIKE 'Feature_0%%_Stock')''', (SOURCES,)).fetchall()
    col = db.execute('''SELECT table_name, column_name, null_rule FROM public."Column_Catalog" WHERE table_schema='public'
        AND table_name = ANY(%s)''', (SOURCES,)).fetchall()
    for name, rows in (("inventory", inv), ("vocabulary", vocab), ("calc", calc), ("column", col)):
        text = json.dumps(rows, default=str, ensure_ascii=False)
        for i in range(0, len(text), 60000):
            print("CHUNK", name, i // 60000, text[i:i + 60000], flush=True)
print("JOB_DONE", flush=True)
