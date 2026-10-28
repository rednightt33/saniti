"""(c) terminal-api process baseline: the real app (app.main.create_app, with boto3/psycopg imported) on the tests'
in-memory FakeStore/FakeBucket (no database pool, no bucket call), one uvicorn process; or an empty FastAPI app.
Prints {"event":"ready"} once uvicorn has started. Usage: python tapi_base.py real|empty"""
import json, socket, sys, threading, time
mode = sys.argv[1]
sys.path[:0] = ['/home/user/saniti/apps/terminal-api', '/home/user/saniti/apps/terminal-api/tests']
import uvicorn
if mode == 'real':
    from app.main import create_app
    import app.bucket, app.store  # noqa: F401  (boto3, psycopg_pool as the image imports them)
    from test_api import FakeBucket, FakeStore, SETTINGS
    application = create_app(SETTINGS, FakeStore(), FakeBucket())
else:
    from fastapi import FastAPI
    application = FastAPI()
    application.get('/health')(lambda: {'ok': True})
s = socket.socket(); s.bind(('127.0.0.1', 0)); port = s.getsockname()[1]; s.close()
server = uvicorn.Server(uvicorn.Config(application, host='127.0.0.1', port=port, log_level='warning'))
def watch():
    while not server.started: time.sleep(0.005)
    print(json.dumps({'event': 'ready', 'port': port}), flush=True)
threading.Thread(target=watch, daemon=True).start()
server.run()
