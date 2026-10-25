"""Read-only: stream idx_event_annotation (without source_payload) and its Column_Catalog definitions out of the Railway
job log as gzip+base64 chunks, so build_excel.py can rebuild the exact table locally (the agent container has no
direct PostgreSQL route). Lines: `EXP <seq> <chunk>`, then `EXP_END <chunks> <sha256 of the gzip bytes> <rows>`.
"""
import base64
import csv
import gzip
import hashlib
import io
import json
import os
import time

import psycopg

COLS = ["event_key", "event_family", "event_type", "ticker", "instrument_code", "annotation_date",
        "annotation_date_role", "action", "holder_name", "holder_role", "holder_nationality", "broker_code",
        "shares_before", "shares_after", "shares_change", "pct_after", "pct_change", "pct_quality_flag", "price",
        "is_estimated_price", "value_idr", "data_origin", "source_endpoint", "source_fetched_at", "ingestion_time"]
CHUNK = 3000

with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=30, application_name="stockbit-event-export") as c:
    c.execute("SET TRANSACTION READ ONLY")
    defs = c.execute("""SELECT column_name, data_type, unit, definition, null_rule FROM public."Column_Catalog"
        WHERE table_schema = 'public' AND table_name = 'idx_event_annotation' ORDER BY ordinal_position""").fetchall()
    print("DEFS " + json.dumps([list(d) for d in defs if d[0] in COLS]), flush=True)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(COLS)
    rows = 0
    for r in c.execute(f"SELECT {', '.join(COLS)} FROM public.idx_event_annotation "
                       "ORDER BY annotation_date DESC, ticker, event_key"):
        w.writerow(r)
        rows += 1
data = gzip.compress(buf.getvalue().encode(), 9)
text = base64.b64encode(data).decode()
chunks = [text[i:i + CHUNK] for i in range(0, len(text), CHUNK)]
for i, ch in enumerate(chunks):
    print(f"EXP {i} {ch}", flush=True)
    if i % 40 == 39:
        time.sleep(1)  # stay under the log rate limit
print(f"EXP_END {len(chunks)} {hashlib.sha256(data).hexdigest()} {rows}", flush=True)
print("JOB_DONE", flush=True)
