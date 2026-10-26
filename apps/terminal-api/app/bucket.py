"""Private bucket terminal-display: manifests are read server-side (cached briefly); data files are only ever handed
out as short-lived presigned GET URLs for one exact key."""
import gzip
import json
import time

PREFIX = 'v1'


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

    def manifest(self, ticker):
        hit = self._cache.get(ticker)
        if hit and hit[0] > time.monotonic():
            return hit[1]
        try:
            body = self.s3.get_object(Bucket=self.name, Key=f'{PREFIX}/manifest/{ticker}.json')['Body'].read()
            value = json.loads(body)
        except self.s3.exceptions.NoSuchKey:
            value = None
        self._cache[ticker] = (time.monotonic() + self.cache_seconds, value)
        return value

    def logo(self, ticker):
        """(body, content type, sha256) of the ticker's logo, or None (EXEC-TERMINAL-LOGO). The logo index is cached like
        a manifest."""
        hit = self._cache.get('#logos')
        if not (hit and hit[0] > time.monotonic()):
            try:
                doc = json.loads(gzip.decompress(self.s3.get_object(Bucket=self.name, Key=f'{PREFIX}/ref/logos.json.gz')['Body'].read()))
                index = {t: (f, h) for t, f, h in zip(doc['ticker'], doc['file'], doc['sha256'])}
            except self.s3.exceptions.NoSuchKey:
                index = {}
            hit = self._cache['#logos'] = (time.monotonic() + self.cache_seconds, index)
        entry = hit[1].get(ticker)
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
