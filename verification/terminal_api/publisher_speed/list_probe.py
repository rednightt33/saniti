"""Read-only: time every page of a listing of the whole terminal-display prefix v1/ (what collect_garbage lists), with
a 30 s read timeout and no retries, to find a page that hangs. Credentials in memory only, never printed."""
import json, subprocess, time
v = json.loads(subprocess.run(['railway', 'variable', 'list', '-s', 'terminal-publisher', '-e', 'dev', '--json'],
                              capture_output=True, text=True, timeout=60, check=True).stdout)
import boto3
from botocore.config import Config
s3 = boto3.client('s3', endpoint_url=v['TERMINAL_BUCKET_ENDPOINT'], region_name=v['TERMINAL_BUCKET_REGION'],
                  aws_access_key_id=v['TERMINAL_BUCKET_ACCESS_KEY_ID'], aws_secret_access_key=v['TERMINAL_BUCKET_SECRET_ACCESS_KEY'],
                  config=Config(s3={'addressing_style': 'virtual'}, signature_version='s3v4', read_timeout=30, connect_timeout=10,
                                retries={'max_attempts': 1}))
B = v['TERMINAL_BUCKET_NAME']; del v
tok, n, t0 = None, 0, time.time()
while True:
    t = time.time()
    try:
        r = s3.list_objects_v2(Bucket=B, Prefix='v1/', **({'ContinuationToken': tok} if tok else {}))
    except Exception as e:
        print(f'page {n}: {type(e).__name__} after {time.time() - t:.1f} s', flush=True); break
    keys = r.get('Contents', [])
    print(f'page {n}: {len(keys)} keys {time.time() - t:.2f} s first={keys[0]["Key"][:40] if keys else None}', flush=True)
    n += 1
    tok = r.get('NextContinuationToken') if r.get('IsTruncated') else None
    if not tok: break
print(f'total {time.time() - t0:.1f} s, {n} pages', flush=True)
