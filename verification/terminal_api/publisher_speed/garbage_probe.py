"""Read-only: how many objects in terminal-display are named by no current manifest or state.json index (what the
cleanup would consider), how many bytes, and how old. Credentials in memory only, never printed. Deletes nothing."""
import gzip, json, subprocess, sys, time, datetime as dt
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[3] / 'apps' / 'terminal-publisher'))
import publisher as pub
v = json.loads(subprocess.run(['railway', 'variable', 'list', '-s', 'terminal-publisher', '-e', 'dev', '--json'],
                              capture_output=True, text=True, timeout=60, check=True).stdout)
import boto3
from botocore.config import Config
s3 = boto3.client('s3', endpoint_url=v['TERMINAL_BUCKET_ENDPOINT'], region_name=v['TERMINAL_BUCKET_REGION'],
                  aws_access_key_id=v['TERMINAL_BUCKET_ACCESS_KEY_ID'], aws_secret_access_key=v['TERMINAL_BUCKET_SECRET_ACCESS_KEY'],
                  config=Config(s3={'addressing_style': 'virtual'}, signature_version='s3v4', read_timeout=30, max_pool_connections=32))
B = v['TERMINAL_BUCKET_NAME']; del v
objs, tok = {}, None
while True:
    r = s3.list_objects_v2(Bucket=B, Prefix='v1/', **({'ContinuationToken': tok} if tok else {}))
    for o in r.get('Contents', []): objs[o['Key'][3:]] = (o['LastModified'], o['Size'])
    tok = r.get('NextContinuationToken') if r.get('IsTruncated') else None
    if not tok: break
get = lambda k: json.loads(s3.get_object(Bucket=B, Key='v1/' + k)['Body'].read())
state = get('state.json')
manifests = [k for k in objs if k.startswith('manifest/') and k.endswith('.json')]
with ThreadPoolExecutor(16) as ex: docs = list(ex.map(get, manifests))
named = set().union(*(pub.named_keys(d) for d in docs))
for field, read in (('xsection', pub.xsection_entries), ('refs', pub.ref_entries)):
    named |= {e['key'][3:] for e in read(state.get(field)).values()}
families = {k.split('/')[0] for k in named}
now = dt.datetime.now(dt.timezone.utc)
total = sum(s for _, s in objs.values())
unused = {k: (at, s) for k, (at, s) in objs.items()
          if (k.split('/')[0] in families and k.count('/') == 2 and k not in named)
          or ((pub.XSECTION_KEY.fullmatch(k) or pub.REF_KEY.fullmatch(k)) and k not in named)}
by = {}
for k, (at, s) in unused.items():
    f = k.split('/')[0]; n, b = by.get(f, (0, 0)); by[f] = (n + 1, b + s)
old = [at for at, _ in unused.values()]
print(json.dumps({'objects': len(objs), 'bytes_mb': round(total / 1e6, 1), 'named_by_current_publication': len(named),
                  'unused_objects': len(unused), 'unused_mb': round(sum(s for _, s in unused.values()) / 1e6, 1),
                  'unused_by_family': {f: {'objects': n, 'mb': round(b / 1e6, 1)} for f, (n, b) in sorted(by.items())},
                  'unused_oldest': min(old).isoformat() if old else None, 'unused_newest': max(old).isoformat() if old else None,
                  'state_finished_at': state.get('finished_at')}, indent=1))
