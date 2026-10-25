#!/usr/bin/env python3
"""EXEC-TERMINAL-API: set (or show) the CORS rule of the private bucket terminal-display.

Browsers may only GET objects, only from the terminal's origins (DESIGN.md 3.1); no listing, no writes.
Environment: TERMINAL_BUCKET_NAME, _ENDPOINT, _REGION, _ACCESS_KEY_ID, _SECRET_ACCESS_KEY (never printed).

  terminal_bucket_cors.py show
  terminal_bucket_cors.py set https://terminal-api-dev.up.railway.app [more origins...]
"""
import json
import os
import sys

import boto3
from botocore.config import Config


def client():
    return boto3.client('s3', endpoint_url=os.environ['TERMINAL_BUCKET_ENDPOINT'],
                        region_name=os.environ['TERMINAL_BUCKET_REGION'],
                        aws_access_key_id=os.environ['TERMINAL_BUCKET_ACCESS_KEY_ID'],
                        aws_secret_access_key=os.environ['TERMINAL_BUCKET_SECRET_ACCESS_KEY'],
                        config=Config(s3={'addressing_style': 'virtual'}, signature_version='s3v4'))


def main(argv):
    s3, bucket = client(), os.environ['TERMINAL_BUCKET_NAME']
    if len(argv) > 2 and argv[1] == 'set':
        origins = [o.rstrip('/') for o in argv[2:]]
        if not all(o.startswith('https://') for o in origins):
            sys.exit('origins must be https://')
        s3.put_bucket_cors(Bucket=bucket, CORSConfiguration={'CORSRules': [{
            'AllowedMethods': ['GET', 'HEAD'], 'AllowedOrigins': origins, 'AllowedHeaders': ['*'],
            'ExposeHeaders': ['Content-Length', 'Content-Type', 'ETag'], 'MaxAgeSeconds': 600}]})
    try:
        print(json.dumps(s3.get_bucket_cors(Bucket=bucket).get('CORSRules'), indent=2))
    except s3.exceptions.ClientError as e:
        print('no CORS rule:', e.response['Error']['Code'])


if __name__ == '__main__':
    main(sys.argv)
