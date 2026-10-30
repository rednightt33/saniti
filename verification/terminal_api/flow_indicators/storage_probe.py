"""Read-only: the current publication's broker files (state.json + every manifest): counts, bytes, years, through dates.
Credentials in memory only, never printed. Writes and deletes nothing."""
import json, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
import boto3
from botocore.config import Config

v = json.loads(subprocess.run(['railway', 'variable', 'list', '-s', 'terminal-publisher', '-e', 'dev', '--json'],
                              capture_output=True, text=True, timeout=60, check=True).stdout)
s3 = boto3.client('s3', endpoint_url=v['TERMINAL_BUCKET_ENDPOINT'], region_name=v['TERMINAL_BUCKET_REGION'],
                  aws_access_key_id=v['TERMINAL_BUCKET_ACCESS_KEY_ID'], aws_secret_access_key=v['TERMINAL_BUCKET_SECRET_ACCESS_KEY'],
                  config=Config(s3={'addressing_style': 'virtual'}, signature_version='s3v4', read_timeout=30, max_pool_connections=32))
B = v['TERMINAL_BUCKET_NAME']; del v
get = lambda k: json.loads(s3.get_object(Bucket=B, Key='v1/' + k)['Body'].read())
state = get('state.json')
print('state', {k: state.get(k) for k in ('schema_version', 'price_through', 'broker_through', 'finished_at', 'last_mode',
                                         'broker_first_year', 'price_first_year', 'broker_behind_sessions')})
tickers = json.loads(__import__('gzip').decompress(s3.get_object(Bucket=B, Key='v1/ref/tickers.json.gz')['Body'].read()))
names = tickers['ticker']; types = tickers['type']
brokers = json.loads(__import__('gzip').decompress(s3.get_object(Bucket=B, Key='v1/ref/brokers.json.gz')['Body'].read()))
print('ref/brokers columns', brokers['columns'], 'rows', len(brokers['code']))
def man(t):
    try: return t, get(f'manifest/{t}.json')
    except Exception as e: return t, None
with ThreadPoolExecutor(16) as ex: docs = dict(ex.map(man, names))
yearly_files = yearly_bytes = yearly_rows = arch_files = arch_bytes = arch_rows = 0
years = {}
for t, m in docs.items():
    if not m: continue
    b = m.get('datasets', {}).get('broker', {}).get('files', {})
    for y, f in b.items():
        yearly_files += 1; yearly_bytes += f['bytes']; yearly_rows += f['rows']; years[y] = years.get(y, 0) + 1
    a = m.get('packs', {}).get('broker-archive')
    if a: arch_files += 1; arch_bytes += a['bytes']; arch_rows += a['rows']
print(json.dumps({'tickers': len(names), 'stocks': sum(1 for x in types if x == 'stock'), 'manifests': sum(1 for m in docs.values() if m),
                  'broker_yearly_files': yearly_files, 'broker_yearly_mb': round(yearly_bytes / 1e6, 1), 'broker_yearly_rows': yearly_rows,
                  'broker_archive_packs': arch_files, 'broker_archive_mb': round(arch_bytes / 1e6, 1), 'broker_archive_rows': arch_rows,
                  'files_per_year': dict(sorted(years.items()))}, indent=1))
bbca = docs.get('BBCA')
print('BBCA broker', {y: (f['rows'], f['bytes']) for y, f in bbca['datasets']['broker']['files'].items()}, 'archive', {k: bbca['packs']['broker-archive'][k] for k in ('rows', 'bytes', 'years')})
