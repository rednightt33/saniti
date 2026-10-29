"""Read-only probe of the terminal-display bucket from the sandbox (EXEC-PUBLISHER-SPEED inspection): page time of a
listing per prefix, GET time of a few manifests, and the same GETs in parallel. Credentials are read from the
publisher's Railway variables into memory and never printed. Writes nothing to the bucket."""
import json, os, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
v = json.loads(subprocess.run(['railway', 'variable', 'list', '-s', 'terminal-publisher', '-e', 'dev', '--json'],
                              capture_output=True, text=True, timeout=60, check=True).stdout)
import boto3
from botocore.config import Config
s3 = boto3.client('s3', endpoint_url=v['TERMINAL_BUCKET_ENDPOINT'], region_name=v['TERMINAL_BUCKET_REGION'],
                  aws_access_key_id=v['TERMINAL_BUCKET_ACCESS_KEY_ID'], aws_secret_access_key=v['TERMINAL_BUCKET_SECRET_ACCESS_KEY'],
                  config=Config(s3={'addressing_style': 'virtual'}, signature_version='s3v4', max_pool_connections=32,
                                retries={'max_attempts': 2}))
B = v['TERMINAL_BUCKET_NAME']; del v
out = {}
def page(prefix, token=None):
    t = time.time()
    r = s3.list_objects_v2(Bucket=B, Prefix='v1/' + prefix, **({'ContinuationToken': token} if token else {}))
    return round(time.time() - t, 2), len(r.get('Contents', [])), r.get('NextContinuationToken') if r.get('IsTruncated') else None
for prefix in ('state.json', 'manifest/', 'xsection/', 'ref/', 'events/', 'pack/', 'price/BBCA/'):
    try:
        out[prefix] = page(prefix)[:2]
    except Exception as e:
        out[prefix] = type(e).__name__
print('first page (seconds, keys):', out, flush=True)
# full listing of price/ by pages
t0 = time.time(); pages = []; tok = None
try:
    while True:
        s, n, tok = page('price/', tok); pages.append((s, n))
        if not tok or time.time() - t0 > 240: break
except Exception as e:
    pages.append(type(e).__name__)
print('price/ pages:', pages, 'total', round(time.time() - t0, 1), flush=True)
keys = [o['Key'] for o in s3.list_objects_v2(Bucket=B, Prefix='v1/manifest/', MaxKeys=64).get('Contents', [])]
def get(k):
    t = time.time(); s3.get_object(Bucket=B, Key=k)['Body'].read(); return time.time() - t
seq = [round(get(k), 2) for k in keys[:8]]
print('sequential GET seconds:', seq, flush=True)
for n in (8, 16, 32):
    t = time.time()
    with ThreadPoolExecutor(n) as ex: list(ex.map(get, keys[:64]))
    print(f'64 GETs with {n} threads: {round(time.time() - t, 2)} s', flush=True)
