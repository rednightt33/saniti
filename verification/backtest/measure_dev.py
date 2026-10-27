#!/usr/bin/env python3
"""What the backtest worker did in Railway dev over a time window, from its own log lines and Railway's metrics.

Per job (job_start .. job_end of apps/backtest-worker/src/server.ts):
  - terminal-api /bundle calls (terminal.ts bundle: event terminal_bundle, its ms) - count, ms median / p95 / max, the
    distinct tickers and how many were asked again (load.ts loadMarket step 2: a manifest too old, or a 403);
  - files (terminal.ts fetchFile: event terminal_file) downloaded vs cached (memory / disk), their bytes, the download
    ms median / p95 / max, MB/s per file and over the job's download time, per dataset kind (price, broker year,
    broker pack, events);
  - retries (terminal_retry), cache write errors, the main thread's HTTP answers about the job (edge-bff's polls,
    the result fetch), and the job's state, code, duration and result size (job_end);
  - Railway CPU and memory: the peak within the job, give or take one sample interval (a sample's ts may mark
    either end of what it averages).
Over the window: Railway CPU and memory peaks, the same counts for the preview thread and the HTTP thread (the
catalog), and how many lines were not the worker's JSON. Lines of the jobs thread whose job_start is before the
window go to threads.jobs_thread_no_job_start_in_window.

Usage:
  RAILWAY_TOKEN=... python measure_dev.py --start 2026-10-27T03:00:00Z --end 2026-10-27T03:40:00Z
      [--service backtest-worker] [--deployment ID] [--sample-seconds 10] [--out REPORT.json] [--save-log LINES.jsonl]
  python measure_dev.py --log-file worker.log [--start ...] [--end ...]   (offline: a saved log, one JSON object a line)
  The window of an e2e_dev.py run: its report.json started_at and finished_at (its summary prints them too).

Railway (read only): GraphQL https://backboard.railway.com/graphql/v2 with the header Project-Access-Token (env
RAILWAY_TOKEN), project PID, environment EID. The service's latest deployment (serviceInstance.latestDeployment); when
it was created inside the window, the earlier deployments that were live in the window too (deployments). Their logs
(deploymentLogs, startDate / endDate): a window answered with --split-at lines or more is split in halves until each
answer is below it, each answer's two ends are asked again (a server cap below --split-at shows there), and the lines
are deduplicated (Railway.logs). Metrics (metrics: CPU_USAGE, MEMORY_USAGE_GB, then CPU_LIMIT,
MEMORY_LIMIT_GB, NETWORK_RX_GB), one query per measurement so one refused query does not hide the others: the report
names each query that failed and why.

Printed: aggregates only. Never a variable's value, never the token, never a log line's text (the 'start' line, which
describes the configuration, is only counted). --save-log keeps only the measurement events (the list MEASURED).

What the numbers mean (terminal.ts):
  - terminal_bundle ms: from before the call to the decoded answer, including the wait for a free connection slot
    (the gate, BACKTEST_TERMINAL_CONCURRENCY) and any retry with its back-off;
  - terminal_file ms (downloads only; a cached file has none): from before the request to the file decoded and
    checked (inflateVerified: inflate + sha256) and written to the disk cache, including the slot wait and retries.
    So MB/s per file is a lower bound on the transfer speed. bytes is the manifest size (the compressed file);
  - MB is 10^6 bytes; 'over the busy time' divides the bytes by the union of the files' [end - ms, end] intervals,
    'over the span' by first start .. last end; peak_overlapping is the most intervals open at once (a file waiting
    for a slot counts: its ms includes the wait, so this is not the connection count).
"""
import argparse
import json
import math
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

PID = '8aef1702-030b-49cb-9df7-5ac2e0a42691'
EID = '4d3e5af2-302b-4a2e-84e2-7d7476d6ff49'
GQL = 'https://backboard.railway.com/graphql/v2'
MEASURED = {'job_start', 'job_end', 'job_cancel', 'terminal_bundle', 'terminal_file', 'terminal_retry',
            'terminal_cache_error', 'http', 'compute_failed', 'compute_thread_error', 'thread_kill_failed',
            'job_settle_failed', 'request_failed'}
REQUIRED_METRICS = ('CPU_USAGE', 'MEMORY_USAGE_GB')
OPTIONAL_METRICS = ('CPU_LIMIT', 'MEMORY_LIMIT_GB', 'NETWORK_RX_GB')


# ---------------------------------------------------------------- time

def epoch(s):
    """ISO 8601 (Z or an offset, any number of fractional digits) -> seconds since the epoch"""
    s = s.strip().replace('Z', '+00:00')
    s = re.sub(r'(\.\d{6})\d+', r'\1', s)
    d = datetime.fromisoformat(s)
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.timestamp()


def iso(t, rounding=None):
    """UTC ISO 8601 with milliseconds; 'floor' / 'ceil' round outwards for a query window"""
    if rounding:
        t = (math.floor if rounding == 'floor' else math.ceil)(t * 1000) / 1000
    return datetime.fromtimestamp(t, timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


# ---------------------------------------------------------------- numbers

def pct(xs, p):
    """nearest-rank percentile of a sorted list"""
    if not xs:
        return None
    k = max(0, min(len(xs) - 1, -(-len(xs) * p // 100) - 1))
    return xs[int(k)]


def dist(values):
    xs = sorted(v for v in values if v is not None)
    if not xs:
        return {'n': 0}
    return {'n': len(xs), 'median': pct(xs, 50), 'p95': pct(xs, 95), 'max': xs[-1]}


def rnd(x, k=3):
    return None if x is None else round(x, k)


def intervals(spans):
    """union length and the most open at once of [a, b] intervals"""
    spans = sorted(spans)
    union, cur = 0.0, None
    for a, b in spans:
        if cur is None or a > cur[1]:
            if cur:
                union += cur[1] - cur[0]
            cur = [a, b]
        else:
            cur[1] = max(cur[1], b)
    if cur:
        union += cur[1] - cur[0]
    ev = sorted([(a, 1) for a, _ in spans] + [(b, -1) for _, b in spans], key=lambda e: (e[0], e[1]))
    peak = run = 0
    for _, d in ev:
        run += d
        peak = max(peak, run)
    return union, peak


# ---------------------------------------------------------------- the worker's lines

def file_kind(what):
    """terminal.ts loadTicker: label `${ticker} ${dataset} ${pack ?? year ?? 'all'}`; a reference file:
    `The ${name} reference` (catalog.ts)"""
    p = (what or '').split(' ')
    if len(p) == 3 and p[0] == 'The' and p[2] == 'reference':
        return 'reference'
    if len(p) != 3:
        return 'other'
    if p[2].isdigit():
        return f'{p[1]}/year'
    return f'{p[1]}/all' if p[2] == 'all' else f'{p[1]}/pack:{p[2]}'


def ticker_of(what):
    p = (what or '').split(' ')
    return p[0] if len(p) == 3 and p[0] != 'The' else None


def bucket():
    return {'bundles': [], 'files': [], 'retries': [], 'cache_errors': 0, 'errors': []}


def add_line(b, o):
    ev = o.get('event')
    if ev == 'terminal_bundle':
        b['bundles'].append(o)
    elif ev == 'terminal_file':
        b['files'].append(o)
    elif ev == 'terminal_retry':
        b['retries'].append(o)
    elif ev == 'terminal_cache_error':
        b['cache_errors'] += 1
    elif ev in ('compute_failed', 'compute_thread_error'):
        b['errors'].append(ev)


def summarize(b):
    """the aggregates of one bucket of terminal lines"""
    bundles, files = b['bundles'], b['files']
    per_ticker = {}
    for x in bundles:
        per_ticker[x.get('ticker')] = per_ticker.get(x.get('ticker'), 0) + 1
    down = [f for f in files if f.get('cached') is False]
    mem = [f for f in files if f.get('cached') == 'memory']
    disk = [f for f in files if f.get('cached') == 'disk']
    spans = [(f['_t'] - (f.get('ms') or 0) / 1000, f['_t']) for f in down]
    busy, parallel = intervals(spans)
    span = (max(e for _, e in spans) - min(a for a, _ in spans)) if spans else 0.0
    dbytes = sum(f.get('bytes') or 0 for f in down)
    rates = [(f.get('bytes') or 0) / 1e6 / (f['ms'] / 1000) for f in down if f.get('ms')]
    kinds = {}
    for f in files:
        k = kinds.setdefault(file_kind(f.get('what')), {'downloaded': 0, 'cached': 0, 'downloaded_bytes': 0, 'cached_bytes': 0})
        key = 'downloaded' if f.get('cached') is False else 'cached'
        k[key] += 1
        k[key + '_bytes'] += f.get('bytes') or 0
    tickers_files = {ticker_of(f.get('what')) for f in files} - {None}
    retry_kinds = {}
    for r in b['retries']:
        what = r.get('what') or ''
        k = ('bundle' if what.startswith('The data of ') else 'reference' if what.endswith(' reference') else 'file') \
            + ' ' + (f"status {r['status']}" if 'status' in r else f"{r.get('error')}")
        retry_kinds[k] = retry_kinds.get(k, 0) + 1
    rs = sorted(rates)
    return {
        'bundle_calls': len(bundles),
        'bundle_ms': dist(x.get('ms') for x in bundles),
        'bundle_tickers': len(per_ticker),
        'bundle_tickers_asked_again': sum(1 for n in per_ticker.values() if n > 1),
        'bundle_files_listed': sum(x.get('files') or 0 for x in bundles),
        'files': {'downloaded': len(down), 'cached_memory': len(mem), 'cached_disk': len(disk),
                  'downloaded_bytes': dbytes, 'cached_bytes': sum(f.get('bytes') or 0 for f in mem + disk),
                  'tickers': len(tickers_files)},
        'download_ms': dist(f.get('ms') for f in down),
        'download_mb_per_s': {'per_file': {'n': len(rs), 'median': rnd(pct(rs, 50)), 'p05': rnd(pct(rs, 5)), 'max': rnd(rs[-1] if rs else None)},
                              'files_with_0_ms': sum(1 for f in down if not f.get('ms')),
                              'over_busy_time': rnd(dbytes / 1e6 / busy) if busy > 0 else None,
                              'over_span': rnd(dbytes / 1e6 / span) if span > 0 else None,
                              'busy_s': rnd(busy), 'span_s': rnd(span), 'peak_overlapping': parallel},
        'by_kind': dict(sorted(kinds.items())),
        'retries': len(b['retries']), 'retry_kinds': retry_kinds,
        'cache_write_errors': b['cache_errors'],
        'compute_errors': len(b['errors']),
    }


JOB_PATH = re.compile(r'^/v1/jobs/(bt_[0-9a-f]+)(/[a-z]+)?$')


def analyse(records, metrics=None):
    """records: the worker's JSON lines (dicts with '_t'), in time order"""
    jobs, order = {}, []
    current = last = None
    threads = {'previews': bucket(), 'http': bucket(), 'jobs_thread_no_job_start_in_window': bucket()}
    http_other, events = {}, {}
    for o in records:
        ev = o.get('event')
        events[ev] = events.get(ev, 0) + 1
        if ev == 'job_start':
            j = {'job_id': o.get('job_id'), 't0': o['_t'], 'prior_trials': o.get('prior_trials'), 'in': bucket(),
                 'after_end': bucket(), 'end': None, 'cancel_t': None, 'http': {}}
            jobs[j['job_id']] = j
            order.append(j['job_id'])
            current = last = j
            continue
        if ev == 'job_end':
            j = jobs.get(o.get('job_id'))
            if j:
                j['end'] = o
                if current is j:
                    current = None
            continue
        if ev == 'job_cancel':
            j = jobs.get(o.get('job_id'))
            if j:
                j['cancel_t'] = o['_t']
            continue
        if ev == 'http':
            path, m = o.get('path') or '', JOB_PATH.match(o.get('path') or '')
            if m and m.group(1) in jobs:
                key = f"{o.get('method')} {'/v1/jobs/{id}' + (m.group(2) or '')}"
                jobs[m.group(1)]['http'].setdefault(key, []).append(o)
            elif o.get('method') == 'POST' and path == '/v1/jobs' and last and o['_t'] - last['t0'] < 10 \
                    and 'POST /v1/jobs' not in last['http'] and o.get('status') == 202:
                last['http']['POST /v1/jobs'] = [o]            # server.ts: job_start is logged before the answer closes
            else:
                key = f"{o.get('method')} {'/v1/jobs/{id}' + (m.group(2) or '') if m else path}"
                http_other.setdefault(key, []).append(o)
            continue
        if ev not in MEASURED:
            continue
        th = o.get('thread')
        if th == 'jobs':
            if current:
                add_line(current['in'], o)
            elif last:
                add_line(last['after_end'], o)     # a cancelled or timed-out job's thread ending its current step
            else:
                add_line(threads['jobs_thread_no_job_start_in_window'], o)
        elif th in threads:
            add_line(threads[th], o)

    out_jobs = []
    for jid in order:
        j = jobs[jid]
        end = j['end'] or {}
        t_end = end.get('_t')
        lines = j['in']['bundles'] + j['in']['files']
        first_file_start = min((f['_t'] - (f.get('ms') or 0) / 1000 for f in j['in']['files']), default=None)
        step1 = [x['_t'] for x in j['in']['bundles'] if first_file_start is None or x['_t'] <= first_file_start]
        last_line = max((x['_t'] for x in lines), default=None)
        r = {'job_id': jid, 'started': iso(j['t0']), 'state': end.get('state'), 'code': end.get('code'),
             'ms': end.get('ms'), 'result_bytes': end.get('result_bytes'), 'json_bytes': end.get('json_bytes'),
             'prior_trials': j['prior_trials'],
             'from_the_log': {   # approximate: the log has no phase lines; see the header
                 'manifests_s': rnd(max(step1) - j['t0']) if step1 else None,
                 'bundles_after_the_first_download': sum(1 for x in j['in']['bundles'] if first_file_start is not None and x['_t'] > first_file_start),
                 'last_terminal_line_s': rnd(last_line - j['t0']) if last_line else None,
                 'after_the_last_terminal_line_s': rnd(t_end - last_line) if t_end and last_line else None,
                 'cancel_to_end_s': rnd(t_end - j['cancel_t']) if t_end and j['cancel_t'] else None},
             **summarize(j['in'])}
        tail = summarize(j['after_end'])
        if tail['bundle_calls'] or sum(tail['files'][k] for k in ('downloaded', 'cached_memory', 'cached_disk')) or tail['retries']:
            r['after_job_end'] = {k: tail[k] for k in ('bundle_calls', 'files', 'download_ms', 'retries')}
        r['http'] = {k: {'n': len(v), 'ms': dist(x.get('ms') for x in v),
                         'statuses': sorted({x.get('status') for x in v}, key=str)} for k, v in sorted(j['http'].items())}
        if metrics:
            r['railway_peaks'] = peaks_between(metrics, j['t0'], t_end if t_end else j['t0'])
        out_jobs.append(r)
    return {'jobs': out_jobs,
            'threads': {k: summarize(v) if (v['bundles'] or v['files'] or v['retries']) else 'no terminal lines'
                        for k, v in threads.items()},
            'http_other': {k: {'n': len(v), 'ms': dist(x.get('ms') for x in v), 'statuses': sorted({x.get('status') for x in v}, key=str)}
                           for k, v in sorted(http_other.items())},
            'events': dict(sorted(events.items(), key=lambda kv: str(kv[0])))}


# ---------------------------------------------------------------- a saved log

def read_log_file(path, t_from, t_to):
    recs, stats = [], {'lines': 0, 'json': 0, 'not_json': 0, 'outside_window': 0, 'no_ts': 0}
    with open(path, encoding='utf-8', errors='replace') as f:
        for k, line in enumerate(f):
            stats['lines'] += 1
            try:
                o = json.loads(line)
            except ValueError:
                o = None
            if not isinstance(o, dict) or 'event' not in o:
                stats['not_json'] += 1
                continue
            stats['json'] += 1
            try:
                o['_t'] = epoch(o['ts'])
            except Exception:
                stats['no_ts'] += 1
                continue
            if (t_from is not None and o['_t'] < t_from) or (t_to is not None and o['_t'] > t_to):
                stats['outside_window'] += 1
                continue
            o['_k'] = k
            recs.append(o)
    recs.sort(key=lambda o: (o['_t'], o['_k']))
    return recs, stats


# ---------------------------------------------------------------- Railway

class Railway:
    def __init__(self, token):
        self.token = token

    def scrub(self, s):
        return str(s).replace(self.token, '<token>')[:300]

    def q(self, query, variables=None):
        """the data, or raises RuntimeError with GraphQL's messages (never the token)"""
        req = urllib.request.Request(GQL, json.dumps({'query': query, 'variables': variables or {}}).encode(),
                                     {'Content-Type': 'application/json', 'Project-Access-Token': self.token,
                                      'User-Agent': 'saniti-backtest-measure/1'})
        try:
            body = json.loads(urllib.request.urlopen(req, timeout=90).read())
        except urllib.error.HTTPError as e:
            try:
                body = json.loads(e.read())
            except Exception:
                raise RuntimeError(f'HTTP {e.code}') from None
        except Exception as e:
            raise RuntimeError(self.scrub(f'{type(e).__name__}: {e}')) from None
        if body.get('errors') or body.get('data') is None:
            raise RuntimeError(self.scrub('; '.join(str(x.get('message')) for x in body.get('errors') or [{'message': 'no data'}])))
        return body['data']

    def service_id(self, name):
        edges = self.q('query($id:String!){project(id:$id){services{edges{node{id name}}}}}', {'id': PID})['project']['services']['edges']
        ids = {e['node']['name']: e['node']['id'] for e in edges}
        if name not in ids:
            raise SystemExit(f'no service {name!r} in the project; services: {sorted(ids)}')
        return ids[name]

    def deployments(self, sid, t_from, t_to):
        """the deployments to read: the latest; when it was created inside the window, also the earlier ones live in it"""
        notes = []
        latest = self.q('query($s:String!,$e:String!){serviceInstance(serviceId:$s,environmentId:$e){latestDeployment{id status createdAt}}}',
                        {'s': sid, 'e': EID})['serviceInstance']['latestDeployment']
        if not latest:
            raise SystemExit('the service has no deployment')
        chosen = [latest]
        if epoch(latest['createdAt']) > t_from:
            try:
                edges = self.q('query($p:String!,$e:String!,$s:String!){deployments(first:20,input:{projectId:$p,environmentId:$e,serviceId:$s})'
                               '{edges{node{id status createdAt}}}}', {'p': PID, 'e': EID, 's': sid})['deployments']['edges']
                hist = sorted((e['node'] for e in edges), key=lambda d: epoch(d['createdAt']))
                live = []
                for k, d in enumerate(hist):
                    nxt = epoch(hist[k + 1]['createdAt']) if k + 1 < len(hist) else float('inf')
                    if epoch(d['createdAt']) <= t_to and nxt > t_from:
                        live.append(d)
                chosen = live or chosen
                notes.append(f'the latest deployment was created inside the window: read {len(chosen)} deployment(s) live in it')
            except RuntimeError as e:
                notes.append(f'deployments (history) failed: {e}; read the latest deployment only, lines before it was created are missing')
        return chosen, notes

    def logs(self, dep, t_from, t_to, limit, split_at, max_queries, min_span=0.5):
        """deploymentLogs over [t_from, t_to]. A window answered with split_at lines or more is split in halves. A
        window answered with fewer is checked at both ends: [start, its first line] and [its last line, end] are asked
        again, and any new line there (a server cap below split_at, which keeps the newest or the oldest lines) makes
        that piece a window of its own. The windows overlap at their ends (milliseconds rounded outwards), so lines
        are deduplicated by (timestamp, message, attributes)."""
        seen, out = set(), []
        info = {'queries': 0, 'max_lines_in_one_answer': 0, 'windows_still_full': 0, 'end_checks_with_new_lines': 0,
                'smallest_answer_with_more_behind_it': None, 'stopped_at_max_queries': False}
        key = lambda r: (r.get('timestamp'), r.get('message'), tuple((x.get('key'), x.get('value')) for x in r.get('attributes') or []))
        todo = [(t_from, t_to, None)]
        while todo:
            a, b, parent_count = todo.pop()
            if info['queries'] >= max_queries:
                info['stopped_at_max_queries'] = True
                break
            info['queries'] += 1
            q = ('query{deploymentLogs(deploymentId:%s,startDate:%s,endDate:%s,limit:%d){timestamp message severity attributes{key value}}}'
                 % (json.dumps(dep), json.dumps(iso(a, 'floor')), json.dumps(iso(b, 'ceil')), limit))
            rows = self.q(q)['deploymentLogs']
            info['max_lines_in_one_answer'] = max(info['max_lines_in_one_answer'], len(rows))
            if len(rows) >= split_at and b - a > min_span:
                m = (a + b) / 2
                todo += [(a, m, None), (m, b, None)]
                continue
            if len(rows) >= split_at:
                info['windows_still_full'] += 1
            new = [r for r in rows if key(r) not in seen]
            for r in new:
                seen.add(key(r))
                out.append(r)
            if parent_count is not None and new:
                info['end_checks_with_new_lines'] += 1
                c = info['smallest_answer_with_more_behind_it']
                info['smallest_answer_with_more_behind_it'] = parent_count if c is None else min(c, parent_count)
            if not new:
                continue
            ts = [epoch(r['timestamp']) for r in rows]
            if min(ts) - a >= 0.001:
                todo.append((a, min(ts), len(rows)))
            if b - max(ts) >= 0.001:
                todo.append((max(ts), b, len(rows)))
        return out, info

    def metric(self, sid, name, t_from, t_to, rate):
        q = ('query{metrics(projectId:%s,environmentId:%s,serviceId:%s,startDate:%s,endDate:%s,measurements:[%s],'
             'sampleRateSeconds:%d,averagingWindowSeconds:%d){measurement values{ts value}}}'
             % (json.dumps(PID), json.dumps(EID), json.dumps(sid), json.dumps(iso(t_from)), json.dumps(iso(t_to)), name, rate, rate))
        res = self.q(q)['metrics']
        return [(float(v['ts']), float(v['value'])) for r in res for v in r.get('values') or []]


def decode_attr(v):
    try:
        return json.loads(v)
    except (TypeError, ValueError):
        return v


def railway_record(r, stats):
    """a Railway log row -> the worker's JSON object: the message itself when it is the JSON line, else Railway's
    attributes (Railway keeps a structured line's fields as attributes, their values JSON-encoded or plain)"""
    msg = r.get('message') or ''
    o = None
    try:
        o = json.loads(msg)
    except ValueError:
        pass
    attrs = {a.get('key'): decode_attr(a.get('value')) for a in r.get('attributes') or []}
    if isinstance(o, dict) and 'event' in o:
        stats['from_message'] += 1
        for k, v in attrs.items():
            o.setdefault(k, v)
    elif 'event' in attrs:
        stats['from_attributes'] += 1
        o = attrs
        if msg and 'message' not in o:
            o['message'] = msg
    else:
        stats['not_worker_json'] += 1
        return None
    try:
        o['_t'] = epoch(o['ts']) if isinstance(o.get('ts'), str) else epoch(r['timestamp'])
    except Exception:
        stats['no_ts'] += 1
        return None
    for k in ('ms', 'bytes', 'files', 'status', 'attempt', 'result_bytes', 'json_bytes', 'prior_trials'):
        if isinstance(o.get(k), str) and re.fullmatch(r'-?\d+(\.\d+)?', o[k]):
            o[k] = float(o[k]) if '.' in o[k] else int(o[k])
    if o.get('cached') in ('false', 'False'):
        o['cached'] = False
    return o


def peaks_between(metrics, a, b):
    out = {}
    for name, m in metrics.items():
        if 'samples' not in m:
            continue
        rate = m['sample_seconds']
        xs = [(t, v) for t, v in m['samples'] if a - rate <= t <= b + rate]
        if xs:
            t, v = max(xs, key=lambda x: x[1])
            out[name] = {'peak': rnd(v, 4), 'at': iso(t), 'samples': len(xs)}
    return out


def metric_summary(m):
    if 'samples' not in m:
        return m
    xs = m['samples']
    if not xs:
        return {'samples': 0, 'sample_seconds': m['sample_seconds']}
    t, v = max(xs, key=lambda x: x[1])
    return {'samples': len(xs), 'sample_seconds': m['sample_seconds'], 'peak': rnd(v, 4), 'peak_at': iso(t),
            'mean': rnd(sum(x for _, x in xs) / len(xs), 4), 'first_at': iso(min(x for x, _ in xs)), 'last_at': iso(max(x for x, _ in xs))}


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--start', help='window start, UTC ISO 8601 (required with Railway)')
    ap.add_argument('--end', help='window end, UTC ISO 8601 (default: now)')
    ap.add_argument('--service', default='backtest-worker')
    ap.add_argument('--deployment', help='read this deployment instead of the latest')
    ap.add_argument('--log-file', help='offline: a saved worker log instead of Railway')
    ap.add_argument('--limit', type=int, default=5000, help='deploymentLogs limit per query')
    ap.add_argument('--split-at', type=int, default=1000, help='split a log window answered with this many lines or more')
    ap.add_argument('--max-queries', type=int, default=3000, help='deploymentLogs queries per deployment at most')
    ap.add_argument('--sample-seconds', type=int, default=10, help='metrics sampleRateSeconds (and averagingWindowSeconds)')
    ap.add_argument('--out', help='also write the report here')
    ap.add_argument('--save-log', help='Railway: write the measurement events (MEASURED) as JSON lines, for --log-file')
    a = ap.parse_args()

    t_from = epoch(a.start) if a.start else None
    t_to = epoch(a.end) if a.end else None
    report = {'window': {'start': a.start, 'end': a.end}, 'service': a.service}
    metrics = None
    if a.log_file:
        recs, stats = read_log_file(a.log_file, t_from, t_to)
        report['source'] = {'log_file': os.path.basename(a.log_file), **stats}
        report['railway_metrics'] = 'not available offline (--log-file)'
    else:
        token = os.environ.get('RAILWAY_TOKEN')
        if not token:
            raise SystemExit('RAILWAY_TOKEN is not set')
        if t_from is None:
            raise SystemExit('--start is required with Railway')
        if t_to is None:
            t_to = datetime.now(timezone.utc).timestamp()
            report['window']['end'] = iso(t_to)
        rw = Railway(token)
        del token
        sid = rw.service_id(a.service)
        src = {'deployments': [], 'notes': []}
        if a.deployment:
            deps = [{'id': a.deployment, 'status': None, 'createdAt': None}]
        else:
            deps, src['notes'] = rw.deployments(sid, t_from, t_to)
        rows_all = []
        for d in deps:
            try:
                rows, info = rw.logs(d['id'], t_from, t_to, a.limit, a.split_at, a.max_queries)
            except RuntimeError as e:
                src['deployments'].append({'id': d['id'], 'status': d['status'], 'created_at': d['createdAt'], 'logs_failed': str(e)})
                continue
            src['deployments'].append({'id': d['id'], 'status': d['status'], 'created_at': d['createdAt'], 'rows': len(rows), **info})
            rows_all += rows
        stats = {'rows': len(rows_all), 'from_message': 0, 'from_attributes': 0, 'not_worker_json': 0, 'no_ts': 0, 'outside_window': 0}
        recs = []
        for r in rows_all:
            o = railway_record(r, stats)
            if o is None:
                continue
            if not (t_from <= o['_t'] <= t_to):
                stats['outside_window'] += 1
                continue
            o['_k'] = len(recs)
            recs.append(o)
        recs.sort(key=lambda o: (o['_t'], o['_k']))
        report['source'] = {**src, **stats}
        if a.save_log:
            with open(a.save_log, 'w') as f:
                for o in recs:
                    if o.get('event') in MEASURED:
                        f.write(json.dumps({k: v for k, v in o.items() if not k.startswith('_') and k != 'message'}) + '\n')
        metrics, failed = {}, {}
        for name in REQUIRED_METRICS + OPTIONAL_METRICS:
            rate = a.sample_seconds
            for attempt_rate in (rate, 60) if rate != 60 else (rate,):
                try:
                    metrics[name] = {'samples': rw.metric(sid, name, t_from, t_to, attempt_rate), 'sample_seconds': attempt_rate}
                    if attempt_rate != rate:
                        metrics[name]['note'] = f'sampleRateSeconds {rate} was refused; {attempt_rate} answered'
                    break
                except RuntimeError as e:
                    failed.setdefault(name, []).append(f'sampleRateSeconds {attempt_rate}: {e}')
            if name not in metrics:
                metrics[name] = {'query_failed': failed[name], 'required': name in REQUIRED_METRICS}
        report['railway_metrics'] = {k: metric_summary(v) for k, v in metrics.items()}
        report['railway_metrics_failed'] = sorted(k for k, v in metrics.items() if 'query_failed' in v)
    report.update(analyse(recs, metrics))
    text = json.dumps(report, indent=1, default=str)
    if a.out:
        with open(a.out, 'w') as f:
            f.write(text + '\n')
    print(text)
    if isinstance(report.get('railway_metrics_failed'), list) and set(report['railway_metrics_failed']) & set(REQUIRED_METRICS):
        sys.exit(2)


if __name__ == '__main__':
    main()
