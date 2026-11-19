"""EXEC-MU-ACCOUNTS fix round (records track, re-check R2-27 and R2-28): two records of the contract that must follow the
code, checked against it so a new store or a new third party cannot be added without its line.

- R2-27: an account deletion must reach every store that names the account. Owner-keyed tables have no foreign key to
  edge_bff.users (CONTRACT section 1), so deleting the users row alone leaves them orphaned. CONTRACT section 10
  "Account deletion" lists the stores; this walks every migration for a table with an owner key or a user id (edge_bff,
  Orc's conversations, terminal's owner rows) and fails on one the list does not name.
- R2-28: every EDGE page, the sign-in page included, sent each visitor's IP address and user agent to Google Fonts, and
  no record listed this or the other recipients (Resend, the bucket host) for the Privacy text. CONTRACT section 18
  lists them; this collects every third-party https host edge-bff's server code names (its page policies and its own
  calls) and every one a page loads (link, script and img tags), and fails on one the list does not name.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
EDGE = ROOT / 'apps/edge-bff'
CONTRACT = (ROOT / 'verification/edge_multiuser/access_tiers/CONTRACT.md').read_text()
MIGRATIONS = sorted((ROOT / 'database/migrations').glob('*.sql'))
OWNER_COLUMN = re.compile(r'^\s*"?(owner_key|edge_owner_key|user_id|actor_user_id|target_user_id)"?\s', re.M)
CREATE = re.compile(r'CREATE TABLE (?:IF NOT EXISTS )?([a-z_]+)\.("?[A-Za-z_]+"?)\s*\((.*?)\n\);', re.S)
ADD = re.compile(r'ALTER TABLE (?:IF EXISTS )?([a-z_]+)\.("?[A-Za-z_]+"?)\s+ADD COLUMN (?:IF NOT EXISTS )?'
                 r'"?(owner_key|edge_owner_key|user_id)"?')


def section(number):
    start = CONTRACT.index(f'\n## {number}. ')
    end = CONTRACT.find('\n## ', start + 5)
    return CONTRACT[start:end if end > 0 else len(CONTRACT)]


def owner_keyed_tables():
    found = set()
    for path in MIGRATIONS:
        text = path.read_text()
        found |= {f'{schema}.{table.strip(chr(34))}' for schema, table, body in CREATE.findall(text)
                  if OWNER_COLUMN.search(body)}
        found |= {f'{schema}.{table.strip(chr(34))}' for schema, table, _ in ADD.findall(text)}
    return found


def test_the_deletion_procedure_names_every_store_that_names_an_account():
    tables = owner_keyed_tables()
    # the walk sees the kinds the finding listed (a regex that stops matching would pass anything)
    assert {'edge_bff.jobs', 'edge_bff.users', 'edge_bff.terminal_drawings', 'public.AI_conversation',
            'terminal.subscriber'} <= tables, sorted(tables)
    listed = section(10).replace('"', '')
    assert 'Account deletion' in listed
    missing = sorted(t for t in tables if t not in listed and f'`{t.split(".", 1)[1]}`' not in listed)
    assert missing == [], (f'CONTRACT section 10 "Account deletion" does not name {missing}: add a row with its key and '
                           'the step a deletion takes for it (delete, keep pseudonymous, or open for the user)')


def third_party_hosts():
    hosts = set()
    for path in sorted((EDGE / 'app').glob('*.py')):
        hosts |= set(re.findall(r'https://([A-Za-z0-9*.-]+)', path.read_text()))
    for page in [EDGE / 'static/index.html', *sorted(EDGE.glob('*/index.html'))]:
        for tag in re.findall(r'<(?:link|script|img)\b[^>]*>', page.read_text()):
            hosts |= set(re.findall(r'(?:href|src)="https://([A-Za-z0-9*.-]+)', tag))
    return hosts


def test_every_third_party_host_is_a_recorded_recipient_of_personal_data():
    hosts = third_party_hosts()
    assert {'fonts.googleapis.com', 'api.resend.com'} <= hosts, sorted(hosts)
    recipients = section(18)
    missing = sorted(h for h in hosts if f'`{h}`' not in recipients)
    assert missing == [], (f'CONTRACT section 18 does not name {missing}: a page or a server call sends the visitor\'s '
                           'address (and more) there; add its row (what it receives and when), or stop the request')
