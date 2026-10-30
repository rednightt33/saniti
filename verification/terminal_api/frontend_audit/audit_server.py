"""Front-end audit (EXEC-TERMINAL-FLOW-IND, user 2026-10-30: "Lakukan audit Front end, minta 2 agent ..."): a local
edge-bff serving the built Terminal (apps/edge-bff/static/terminal-app) with dev data, kept running for the auditors.
Set-up of flow_indicators_live_check.py: a disposable database, owner `owner` / `local-live-check`, terminal-api dev
through TERMINAL_PROXY_KEY (read from Railway into memory only). The auditors open pages with audit_page.py and never
see a secret.

Environment: EDGE_TEST_POSTGRES_URL (disposable server), the Railway CLI logged in.
Usage: python audit_server.py [port]   (stops on SIGTERM / Ctrl-C and drops its database)
"""
import json
import os
import signal
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg
import uvicorn

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'apps/edge-bff'))
from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from app.security import password_verifier  # noqa: E402

port = int(sys.argv[1]) if len(sys.argv) > 1 else 18770
v = json.loads(subprocess.run(['railway', 'variable', 'list', '-s', 'terminal-api', '-e', 'dev', '--json'],
                              capture_output=True, text=True, timeout=60, check=True).stdout)
admin = os.environ['EDGE_TEST_POSTGRES_URL']
name = 'edge_audit_' + uuid.uuid4().hex[:10]
p = urlsplit(admin); db = urlunsplit((p.scheme, p.netloc, '/' + name, p.query, p.fragment))
with psycopg.connect(admin, autocommit=True) as c:
    c.execute(f'CREATE DATABASE "{name}"')
with psycopg.connect(db, autocommit=True) as c:
    for m in ('20261008_002_create_edge_bff.sql', '20261012_008_edge_bff_conversation_hidden.sql',
              '20261024_002_edge_bff_conversation_branch.sql'):
        c.execute((ROOT / 'database/migrations' / m).read_text())

settings = Settings(database_url=db, orc_url='http://orc.invalid', orc_key='local', owner='local-owner', login='owner',
                    password_verifier=password_verifier('local-live-check'), session_secret='local-live-secret-' * 3,
                    origin=f'http://127.0.0.1:{port}', environment='local', secure_cookie=False, worker_enabled=False,
                    terminal_url='https://' + v['RAILWAY_PUBLIC_DOMAIN'], terminal_proxy_key=v['TERMINAL_PROXY_KEY'])
del v
server = uvicorn.Server(uvicorn.Config(create_app(settings), host='127.0.0.1', port=port, log_level='warning'))


def stop(*_):
    server.should_exit = True


signal.signal(signal.SIGTERM, stop)
threading.Thread(target=server.run, daemon=True).start()
while not server.started:
    time.sleep(.05)
print(f'ready http://127.0.0.1:{port}/terminal-app/', flush=True)
try:
    while not server.should_exit:
        time.sleep(1)
finally:
    time.sleep(.5)
    with psycopg.connect(admin, autocommit=True) as c:
        c.execute(f'DROP DATABASE "{name}" WITH (FORCE)'); c.execute('DROP ROLE IF EXISTS edge_bff_runtime')
    print('stopped', flush=True)
