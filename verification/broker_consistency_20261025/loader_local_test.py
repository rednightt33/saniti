"""Local test of the user's importer: fake Stockbit responses, local PostgreSQL with the live IDX_Broker_Summary schema."""
import json, os, sys, tempfile, shutil
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, sys.argv[1])
import psycopg
import stockbit_ihsg_daily as source
import import_full_broker_summary as imp

URL = os.environ["DATABASE_URL"]
SYMS = [f"{a}{b}{c}{d}" for a in "AB" for b in "ABCDEFGHIJ" for c in "ABCDE" for d in "ABCDEF"][:520]
STATE = {"variant": 0}

def setup():
    with psycopg.connect(URL, autocommit=True) as db:
        db.execute("DROP TABLE IF EXISTS public.\"IDX_Broker_Summary\", public.\"Price_Stock_Indonesia_IDX\", "
                   "public.\"IDX_Stock_Universe\", public.stockbit_full_broker_import_status")
        db.execute('''CREATE TABLE public."IDX_Broker_Summary" ("Date" date NOT NULL, "Symbol" varchar NOT NULL,
            "Broker" varchar NOT NULL CHECK ("Broker" ~ '^[A-Z0-9]{2}$'), "Investor Type" varchar NOT NULL,
            "Market Board" varchar NOT NULL, "Buy Value" numeric NOT NULL CHECK ("Buy Value">=0),
            "Sell Value" numeric NOT NULL CHECK ("Sell Value">=0), "Net Value" numeric NOT NULL,
            "Buy Lots" numeric NOT NULL, "Sell Lots" numeric NOT NULL, "Net Lots" numeric NOT NULL,
            "Avg Buy" numeric, "Avg Sell" numeric, buy_freq bigint, sell_freq bigint,
            CHECK ("Net Value" = "Buy Value" - "Sell Value"), CHECK ("Net Lots" = "Buy Lots" - "Sell Lots"),
            PRIMARY KEY ("Date","Symbol","Broker","Investor Type","Market Board"))''')
        db.execute('CREATE TABLE public."Price_Stock_Indonesia_IDX" (date date, ticker text, timeframe text)')
        db.execute('CREATE TABLE public."IDX_Stock_Universe" ("Ticker" text)')
        for d in ("2026-10-26", "2026-10-27"):
            for s in SYMS:
                db.execute('INSERT INTO public."Price_Stock_Indonesia_IDX" VALUES (%s,%s,%s)', (d, s, "daily"))
        db.cursor().executemany('INSERT INTO public."IDX_Stock_Universe" VALUES (%s)', [(s,) for s in SYMS])
        # a warrant row and an old-format 4-letter row already in the table
        db.execute('''INSERT INTO public."IDX_Broker_Summary" VALUES ('2026-10-26','AAAA-W','YP','Domestic','Regular',
            10,0,10,1,0,1,100,NULL,NULL,NULL)''')

class FakeFetcher:
    def __init__(self, *a): pass
    def get_json(self, path):
        sym = path.split("/")[2].split("?")[0]
        q = dict(p.split("=") for p in path.split("?")[1].split("&"))
        day = q["from"]; inv = q["investor_type"]; board = q["market_board"]
        buys, sells = [], []
        if board.endswith("REGULER") and sym in SYMS[:200]:
            v = Decimal(1000 + STATE["variant"])
            buys = [{"netbs_broker_code": "YP", "netbs_stock_code": sym, "netbs_date": day.replace("-", ""),
                     "bval": v, "blot": Decimal("1.5"), "netbs_buy_avg_price": Decimal(100), "freq": Decimal(3)}]
            sells = [{"netbs_broker_code": "CC", "netbs_stock_code": sym, "netbs_date": day.replace("-", ""),
                      "sval": v, "slot": Decimal("1.5"), "netbs_sell_avg_price": Decimal(100), "freq": Decimal(2)}]
        body = {"data": {"from": day, "to": day, "broker_summary": {"brokers_buy": buys, "brokers_sell": sells}}}
        return body, json.dumps(body, default=str).encode(), 1

def run(state_dir, start="2026-10-26", end="2026-10-27"):
    imp.STOP.clear()
    source.StockbitFetcher = FakeFetcher
    args = SimpleNamespace(start=__import__("datetime").date.fromisoformat(start), end=__import__("datetime").date.fromisoformat(end),
                           state_dir=Path(state_dir), historical_state=Path(tempfile.mkdtemp()), workers=4)
    app = imp.Importer(args)
    try: app.run()
    finally: app.db.close(); app.pg.close()

def q(sql):
    with psycopg.connect(URL) as db: return db.execute(sql).fetchall()

os.environ["STOCKBIT_TOKEN"] = "x.y.z"
setup()
st = tempfile.mkdtemp()
run(st)
print("RUN1", q('SELECT "Date"::text, count(*), sum(buy_freq), sum("Buy Value") FROM public."IDX_Broker_Summary" GROUP BY 1 ORDER BY 1'))
print("STATUS", q("SELECT trade_date::text, state, row_count FROM public.stockbit_full_broker_import_status ORDER BY 1"))
run(st)  # resume: both dates skipped after a count check
print("RUN2_same_state_ok")
STATE["variant"] = 5; st2 = tempfile.mkdtemp()  # new state dir, source values corrected
try:
    run(st2); print("RUN3_corrected", q('SELECT sum("Buy Value") FROM public."IDX_Broker_Summary" WHERE "Symbol" ~ \'^[A-Z]{4}$\''))
except Exception as e: print("RUN3_ERR", type(e).__name__, str(e)[:200])
print("WARRANT_KEPT", q('SELECT count(*) FROM public."IDX_Broker_Summary" WHERE "Symbol"=\'AAAA-W\''))
try:
    run(tempfile.mkdtemp(), start="2026-10-25", end="2026-10-27")
except Exception as e: print("NON_TRADING_START", type(e).__name__, str(e)[:120])
