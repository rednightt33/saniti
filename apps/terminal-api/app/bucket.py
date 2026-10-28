"""Private bucket terminal-display: manifests are read server-side (cached briefly); data files are only ever handed
out as short-lived presigned GET URLs for one exact key."""
import gzip
import json
import re
import time

PREFIX = 'v1'
# EXEC-SCREENER (P1 a, user 2026-10-28): `xsection` is the index of the run's cross-sectional files (xsection_index)
STATE_FIELDS = ('finished_at', 'price_through', 'broker_through', 'broker_behind_sessions', 'xsection')
MAX_CACHED = 4000   # manifests (a few KB each) and the logo index: a few MB at most
XSECTION_NAME = re.compile(r'^[a-z0-9][a-z0-9_-]{0,31}$')
XSECTION_FIELDS = ('key', 'sha256', 'bytes', 'rows', 'as_of')
SHA256 = re.compile(r'^[0-9a-f]{64}$')


def _count(v, least):
    return isinstance(v, int) and not isinstance(v, bool) and v >= least


def xsection_index(raw):
    """EXEC-SCREENER (P1 a): state.json `xsection` = {name: {key, sha256, bytes, rows, as_of}}, the cross-sectional
    files of the publication (written by the publisher before state.json, content-addressed keys
    v1/xsection/<name>.<16 hex>.json.gz that are never overwritten). This is the index /state shows and /xsection
    grants from: only well-formed entries, each with exactly those five fields, so /state never names a file
    /xsection would refuse and a key outside the xsection family is never presigned. None when state.json holds no
    index (a publisher before the xsection writer)."""
    if not isinstance(raw, dict):
        return None
    out = {}
    for name, e in raw.items():
        if not (isinstance(name, str) and XSECTION_NAME.fullmatch(name) and isinstance(e, dict)):
            continue
        key, sha, size, rows, as_of = (e.get(k) for k in XSECTION_FIELDS)
        if not (isinstance(key, str) and re.fullmatch(rf'{PREFIX}/xsection/{re.escape(name)}\.[0-9a-f]{{16}}\.json\.gz', key)
                and isinstance(sha, str) and SHA256.fullmatch(sha) and _count(size, 1) and _count(rows, 0)):
            continue
        out[name] = {'key': key, 'sha256': sha, 'bytes': size, 'rows': rows,
                     'as_of': as_of if isinstance(as_of, str) and len(as_of) <= 64 else None}
    return out


class Bucket:
    def __init__(self, settings):
        import boto3
        from botocore.config import Config
        self.name = settings.bucket_name
        self.s3 = boto3.client(
            's3', endpoint_url=settings.bucket_endpoint, region_name=settings.bucket_region,
            aws_access_key_id=settings.bucket_access_key_id,
            aws_secret_access_key=settings.bucket_secret_access_key,
            config=Config(s3={'addressing_style': 'virtual'}, signature_version='s3v4', retries={'max_attempts': 3}))
        self.cache_seconds = settings.manifest_cache_seconds
        self._cache = {}
        self._version, self._checked = None, None
        self._state = None                                  # the last state.json read (state())

    def _fresh(self):
        """EXEC-TERMINAL-SPEED step 4: the cache holds until the publisher finishes a run (state.json `finished_at`),
        checked at most every cache_seconds; the bucket is in another region (sin vs sfo), so a manifest read costs ~1 s
        and is now paid once per publication instead of once a minute per ticker."""
        now = time.monotonic()
        if self._checked is not None and now - self._checked < self.cache_seconds:
            return
        self._checked = now
        try:
            state = json.loads(self.s3.get_object(Bucket=self.name, Key=f'{PREFIX}/state.json')['Body'].read())
            version = state.get('finished_at')
        except Exception:  # noqa: BLE001 - unreadable state: keep what is cached rather than fail every request
            return
        self._state = state
        if version != self._version or len(self._cache) > MAX_CACHED:
            self._version = version
            self._cache.clear()

    def state(self):
        """EXEC-BACKTEST-LOAD (user 2026-10-27, K1): the publisher's last finished run, as read for the manifest cache
        (at most cache_seconds old): which publication the files belong to and the newest date of each dataset. None
        while state.json was never readable. EXEC-SCREENER: plus `xsection`, the run's cross-sectional file index
        (xsection_index; null when the run wrote none), taken from the same read as `finished_at`."""
        self._fresh()
        s = self._state
        if not isinstance(s, dict):
            return None
        out = {k: s.get(k) for k in STATE_FIELDS}
        out['xsection'] = xsection_index(out['xsection'])
        return out

    def manifest(self, ticker):
        self._fresh()
        if ticker in self._cache:
            return self._cache[ticker]
        try:
            body = self.s3.get_object(Bucket=self.name, Key=f'{PREFIX}/manifest/{ticker}.json')['Body'].read()
            value = json.loads(body)
        except self.s3.exceptions.NoSuchKey:
            value = None
        self._cache[ticker] = value
        return value

    def logo(self, ticker):
        """(body, content type, sha256) of the ticker's logo, or None (EXEC-TERMINAL-LOGO). The logo index is cached like
        a manifest."""
        self._fresh()
        if '#logos' not in self._cache:
            try:
                doc = json.loads(gzip.decompress(self.s3.get_object(Bucket=self.name, Key=f'{PREFIX}/ref/logos.json.gz')['Body'].read()))
                self._cache['#logos'] = {t: (f, h) for t, f, h in zip(doc['ticker'], doc['file'], doc['sha256'])}
            except self.s3.exceptions.NoSuchKey:
                self._cache['#logos'] = {}
        entry = self._cache['#logos'].get(ticker)
        if not entry:
            return None
        name, sha = entry
        body = self.s3.get_object(Bucket=self.name, Key=f'{PREFIX}/logo/{name}')['Body'].read()
        return body, 'image/svg+xml' if name.endswith('.svg') else 'image/png', sha

    def presign(self, key, ttl):
        return self.s3.generate_presigned_url('get_object', Params={'Bucket': self.name, 'Key': key}, ExpiresIn=ttl)

    def head(self, key):
        try:
            return self.s3.head_object(Bucket=self.name, Key=key)['ContentLength']
        except Exception:  # noqa: BLE001 - absent or unreadable: the caller answers 404
            return None
