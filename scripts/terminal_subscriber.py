#!/usr/bin/env python3
"""Manage terminal subscribers (EXEC-TERMINAL-API, option A: accounts kept by the administrator).

Calls terminal-api's admin routes. Environment: TERMINAL_API_URL (e.g. https://terminal-api-dev.up.railway.app) and
TERMINAL_ADMIN_KEY (the Railway variable of terminal-api; never printed). Passwords are read from a prompt, not argv.

  terminal_subscriber.py list
  terminal_subscriber.py add EMAIL "NAME" --until 2026-12-31
  terminal_subscriber.py extend ID --until 2027-06-30
  terminal_subscriber.py disable ID --reason "unpaid"
  terminal_subscriber.py enable ID
  terminal_subscriber.py reset-password ID
"""
import argparse
import datetime as dt
import getpass
import json
import os
import sys
import urllib.error
import urllib.request

BASE = '/api/terminal/v1/admin/subscribers'


def call(method, path, body=None):
    url = os.environ['TERMINAL_API_URL'].rstrip('/') + path
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={'x-terminal-admin-key': os.environ['TERMINAL_ADMIN_KEY'],
                                          'content-type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        sys.exit(f'{e.code}: {e.read().decode()[:500]}')


def until(value):
    day = dt.date.fromisoformat(value)
    # the subscription runs through the end of that day, Jakarta time
    return dt.datetime.combine(day, dt.time(23, 59, 59), dt.timezone(dt.timedelta(hours=7))).isoformat()


def new_password():
    first = getpass.getpass('New password (min 12 characters): ')
    if first != getpass.getpass('Repeat: '):
        sys.exit('Passwords differ.')
    return first


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest='cmd', required=True)
    sub.add_parser('list')
    a = sub.add_parser('add'); a.add_argument('email'); a.add_argument('name'); a.add_argument('--until', required=True)
    e = sub.add_parser('extend'); e.add_argument('id', type=int); e.add_argument('--until', required=True)
    d = sub.add_parser('disable'); d.add_argument('id', type=int); d.add_argument('--reason', default=None)
    n = sub.add_parser('enable'); n.add_argument('id', type=int)
    r = sub.add_parser('reset-password'); r.add_argument('id', type=int)
    args = p.parse_args()
    if args.cmd == 'list':
        out = call('GET', BASE)
    elif args.cmd == 'add':
        out = call('POST', BASE, {'email': args.email, 'display_name': args.name, 'password': new_password(),
                                  'expires_at': until(args.until)})
    elif args.cmd == 'extend':
        out = call('POST', f'{BASE}/{args.id}', {'expires_at': until(args.until), 'active': True})
    elif args.cmd == 'disable':
        out = call('POST', f'{BASE}/{args.id}', {'active': False, 'disabled_reason': args.reason})
    elif args.cmd == 'enable':
        out = call('POST', f'{BASE}/{args.id}', {'active': True})
    else:
        out = call('POST', f'{BASE}/{args.id}', {'password': new_password()})
    print(json.dumps(out, indent=2))


if __name__ == '__main__':
    main()
