"""Table of the screener cold-start runs (raw/screener_k*_r*.json written by run_proc.mjs + screener_cold.mts)."""
import glob, json, sys
B = sys.argv[1]
rows = []
for p in sorted(glob.glob(f'{B}/raw/screener_k*_r*.json')):
    if 'try' in p:
        continue
    d = json.load(open(p))
    ready = next((l for l in d['lines'] if l.get('event') == 'ready'), {})
    served = next((l for l in d['lines'] if l.get('event') == 'served'), {})
    idle = {l['after_s']: l['rss_mb'] for l in d['lines'] if l.get('event') == 'idle'}
    g = lambda k, f='wall_ms': (ready.get(k) or {}).get(f)
    rows.append({
        'run': p.rsplit('/', 1)[1][:-5], 'threads': ready.get('threads'), 'spawn_to_ready_ms': d['spawn_to_ready_ms'],
        'boot_ms': ready.get('boot_ms'), 'inflate_verify_parse_ms': g('inflate_verify_parse'), 'slice_priceSeries_ms': g('slice_priceSeries'),
        'prewarm_ms': g('prewarm_53'), 'prewarm_cpu_ms': g('prewarm_53', 'cpu_ms'), 'rss_after_decode_mb': g('slice_priceSeries', 'rss_mb'),
        'rss_ready_mb': ready.get('rss_mb'), 'heap_ready_mb': ready.get('heap_mb'), 'peak_rss_mb': d['peak_rss_mb'],
        'tails': ready.get('tails'), 'errors': ready.get('errors'), 'snapshot_tail_mb': round((ready.get('cache_bytes') or {}).get('total', 0) / 1048576, 1),
        'per_thread': ready.get('per_thread'),
        'default_screen_first_ms': (served.get('default_screen_1') or {}).get('wall_ms'), 'default_screen_again_ms': (served.get('default_screen_2') or {}).get('wall_ms'),
        'custom_screen_first_ms': (served.get('custom_screen_cold') or {}).get('wall_ms'), 'custom_screen_first_cpu_ms': (served.get('custom_screen_cold') or {}).get('cpu_ms'),
        'custom_screen_repeat_ms': (served.get('custom_screen_repeat') or {}).get('wall_ms'),
        'total_cpu_ms_to_served': served.get('total_cpu_ms'), 'idle_rss_mb': idle,
    })
json.dump(rows, open(f'{B}/raw/screener_summary.json', 'w'), indent=1)
for r in rows:
    print(json.dumps(r))
