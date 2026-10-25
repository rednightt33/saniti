#!/usr/bin/env python3
"""Phase 7 live quota check: the test subscriber opens 31 distinct tickers; tickers_per_hour (30) must stop the 31st,
and an already opened ticker must stay available. Re-enables, then disables validator@terminal.test."""
import json
import secrets
import sys

import validate as v

adm = {'x-terminal-admin-key': v.admin_key()}
c = v.Client()
s, d, _, _ = c.call('GET', f'{v.BASE}/admin/subscribers', headers=adm)
sid = [x for x in d['subscribers'] if x['email'] == v.EMAIL][0]['subscriber_id']
pw = secrets.token_urlsafe(18)
c.call('POST', f'{v.BASE}/admin/subscribers/{sid}', {'password': pw, 'active': True}, headers=adm)
c.call('POST', f'{v.BASE}/auth/sign-in', {'email': v.EMAIL, 'password': pw})
tickers = [r[0] for r in v.sql_one('SELECT "Ticker" FROM "IDX_Stock_Universe" WHERE "Security Type"=\'stock\' '
                                   "AND \"Ticker\" NOT IN ('BBCA','ASII','TLKM','BBRI') ORDER BY 1 LIMIT 40")]
codes = []
for t in tickers:
    s, d, _, _ = c.call('POST', f'{v.BASE}/files', {'ticker': t, 'dataset': 'price', 'years': [2026]})
    codes.append(s)
    if s == 429:
        print('REFUSED at ticker', len(codes), d['message'])
        break
# BBCA, opened by validate.py earlier in the same hour, counts as one of the 30 distinct tickers
again, _, _, _ = c.call('POST', f'{v.BASE}/files', {'ticker': tickers[0], 'dataset': 'price', 'years': [2025]})
c.call('POST', f'{v.BASE}/admin/subscribers/{sid}', {'active': False, 'disabled_reason': 'Phase 7 validator, done'},
       headers=adm)
print(json.dumps({'accepted': codes.count(200), 'refused_at': len(codes) if 429 in codes else None,
                  'already_opened_ticker_again': again}))
print('PASS' if 429 in codes and again == 200 else 'FAIL', 'tickers_per_hour enforced live')
sys.exit(0 if 429 in codes and again == 200 else 1)
