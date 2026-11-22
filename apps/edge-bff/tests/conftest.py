import os
from pathlib import Path
import uuid
from urllib.parse import urlsplit,urlunsplit
import psycopg
import pytest
from app.config import Settings
from app.security import password_verifier
from app.store import Store

def pytest_configure(config):
    # AGENTS.md "Generated files": .github/workflows/generated-files.yml runs the tests with this mark
    config.addinivalue_line('markers', 'generated_file: a generated file equals what its generator writes now')
    if browser_reruns() and not config.pluginmanager.hasplugin('rerunfailures'):
        raise pytest.UsageError('EDGE_TEST_BROWSER_RERUNS needs pytest-rerunfailures (requirements-dev.txt)')

# TEMPORARY (ERRORS M510; the user 2026-11-20, "1 A"): on GitHub's runner a few browser tests of the Monitor page fail,
# a different set each run, while every local run passes them (also with the page's CPU slowed six times). With
# EDGE_TEST_BROWSER_RERUNS=N, set only in .github/workflows/backend-tests.yml, a test that opens a browser (its own body
# or a fixture it uses starts Playwright) runs again up to N times after a failure, and pytest-rerunfailures prints
# every rerun ("R", "rerun" in the summary). Unset, as in every local run, nothing is rerun. It does not cover a test
# that fails every time (that stays red) and it can hide a fault that shows only sometimes, which is why the root cause
# is being found (M510) and this goes with its fix.
def browser_reruns():
    value=os.environ.get('EDGE_TEST_BROWSER_RERUNS','').strip()
    if not value:
        return 0
    if not value.isdigit() or not 1 <= int(value) <= 3:
        raise pytest.UsageError('EDGE_TEST_BROWSER_RERUNS is a whole number from 1 to 3')
    return int(value)

_SOURCES={}
def _starts_browser(func):
    if func not in _SOURCES:
        try:
            import inspect
            _SOURCES[func]='sync_playwright' in inspect.getsource(func)
        except (OSError,TypeError):
            _SOURCES[func]=False
    return _SOURCES[func]

def opens_browser(item):
    if _starts_browser(getattr(item,'function',None)):
        return True
    defs=getattr(getattr(item,'_fixtureinfo',None),'name2fixturedefs',{})
    return any(_starts_browser(d.func) for name in item.fixturenames for d in defs.get(name,()))

def pytest_collection_modifyitems(config, items):
    reruns=browser_reruns()
    if not reruns:
        return
    marked=[item for item in items if opens_browser(item)]
    for item in marked:
        item.add_marker(pytest.mark.flaky(reruns=reruns))
    config._edge_browser_reruns=(len(marked),reruns)

def pytest_report_collectionfinish(config, start_path, items):
    if getattr(config,'_edge_browser_reruns',None):
        n,reruns=config._edge_browser_reruns
        return f'TEMPORARY (ERRORS M510): {n} browser tests may run again up to {reruns} times after a failure'

@pytest.fixture(scope='session')
def database():
    admin=os.environ.get('EDGE_TEST_POSTGRES_URL','')
    if not admin: pytest.skip('EDGE_TEST_POSTGRES_URL requires a disposable Postgres')
    name='edge_test_'+uuid.uuid4().hex[:12];p=urlsplit(admin);url=urlunsplit((p.scheme,p.netloc,'/'+name,p.query,p.fragment))
    with psycopg.connect(admin,autocommit=True) as c:c.execute(f'CREATE DATABASE "{name}"')
    try:
        with psycopg.connect(url,autocommit=True) as c:
            c.execute((Path(__file__).resolve().parents[3]/'database/migrations/20261008_002_create_edge_bff.sql').read_text())
            c.execute((Path(__file__).resolve().parents[3]/'database/migrations/20261012_008_edge_bff_conversation_hidden.sql').read_text())
            c.execute((Path(__file__).resolve().parents[3]/'database/migrations/20261024_002_edge_bff_conversation_branch.sql').read_text())
            c.execute((Path(__file__).resolve().parents[3]/'database/migrations/20261026_005_edge_bff_backtest.sql').read_text())
            c.execute((Path(__file__).resolve().parents[3]/'database/migrations/20261027_005_edge_bff_backtest_error_comment.sql').read_text())
            c.execute((Path(__file__).resolve().parents[3]/'database/migrations/20261028_001_edge_bff_screener.sql').read_text())
            c.execute((Path(__file__).resolve().parents[3]/'database/migrations/20261106_001_edge_bff_terminal_layouts.sql').read_text())
            c.execute((Path(__file__).resolve().parents[3]/'database/migrations/20261106_002_edge_bff_indicator_presets.sql').read_text())
            c.execute((Path(__file__).resolve().parents[3]/'database/migrations/20261107_001_edge_bff_terminal_drawings.sql').read_text())
            c.execute((Path(__file__).resolve().parents[3]/'database/migrations/20261116_001_edge_bff_watchlist_lists.sql').read_text())
            c.execute((Path(__file__).resolve().parents[3]/'database/migrations/20261116_002_edge_bff_accounts_auth_throttle.sql').read_text())
            c.execute((Path(__file__).resolve().parents[3]/'database/migrations/20261116_003_edge_bff_accounts_users.sql').read_text())
            c.execute((Path(__file__).resolve().parents[3]/'database/migrations/20261117_001_edge_bff_accounts_registration.sql').read_text())
            c.execute((Path(__file__).resolve().parents[3]/'database/migrations/20261117_002_edge_bff_accounts_registration_binding.sql').read_text())
            c.execute((Path(__file__).resolve().parents[3]/'database/migrations/20261117_003_edge_bff_accounts_catalog.sql').read_text())
            c.execute((Path(__file__).resolve().parents[3]/'database/migrations/20261117_004_edge_bff_catalog_phase3a.sql').read_text())
            c.execute((Path(__file__).resolve().parents[3]/'database/migrations/20261118_001_edge_bff_item_families_from_terminal.sql').read_text())
            c.execute((Path(__file__).resolve().parents[3]/'database/migrations/20261118_002_edge_bff_terminal_quota.sql').read_text())
            # the auth fix round of the re-check (verification/edge_multiuser/fix_round/auth.md)
            c.execute((Path(__file__).resolve().parents[3]/'database/migrations/20261119_010_edge_bff_password_identity.sql').read_text())
            c.execute((Path(__file__).resolve().parents[3]/'database/migrations/20261119_011_edge_bff_mfa_pending_enrolment.sql').read_text())
            c.execute((Path(__file__).resolve().parents[3]/'database/migrations/20261119_012_edge_bff_email_outbox_purge.sql').read_text())
            # EXEC-MU-ACCOUNTS beta/live fix round (track site): the queues' site, the seed's mark, the account indexes
            c.execute((Path(__file__).resolve().parents[3]/'database/migrations/20261119_020_edge_bff_jobs_site.sql').read_text())
            c.execute((Path(__file__).resolve().parents[3]/'database/migrations/20261119_021_edge_bff_backtest_jobs_site.sql').read_text())
            c.execute((Path(__file__).resolve().parents[3]/'database/migrations/20261119_022_edge_bff_seed_verifier_mark.sql').read_text())
            c.execute((Path(__file__).resolve().parents[3]/'database/migrations/20261119_023_edge_bff_account_reference_indexes.sql').read_text())
            # the plans fix round (verification/edge_multiuser/fix_round/plans.md, re-check R1-36, the user's "2a")
            c.execute((Path(__file__).resolve().parents[3]/'database/migrations/20261119_030_edge_bff_plan_data_scope.sql').read_text())
            # the records fix round (verification/edge_multiuser/fix_round/records.md, re-check R1-41..R1-46)
            c.execute((Path(__file__).resolve().parents[3]/'database/migrations/20261119_040_edge_bff_audit_ids_and_catalog_trace.sql').read_text())
            c.execute((Path(__file__).resolve().parents[3]/'database/migrations/20261119_050_edge_bff_capability_domains.sql').read_text())
            # the guest fix round (verification/edge_multiuser/fix_round/guest.md): the guest plan and the test-account mark
            c.execute((Path(__file__).resolve().parents[3]/'database/migrations/20261119_070_edge_bff_guest_plan_and_test_accounts.sql').read_text())
            # the 3c check's fixes: the scope of the ceiling of every visitor together (EDGE_GUEST_CALLS_PER_HOUR)
            c.execute((Path(__file__).resolve().parents[3]/'database/migrations/20261119_071_edge_bff_guest_total_scope.sql').read_text())
            # the A2 fix (ERRORS M517): a reset code bound to the browser that asked for it
            c.execute((Path(__file__).resolve().parents[3]/'database/migrations/20261120_001_edge_bff_reset_code_browser.sql').read_text())
            c.execute((Path(__file__).resolve().parents[3]/'database/migrations/20261120_002_edge_bff_registration_client.sql').read_text())
            # 3e, the example mode (ERRORS M527): the example files and the guest plan's example flags
            c.execute((Path(__file__).resolve().parents[3]/'database/migrations/20261121_001_edge_bff_example_files.sql').read_text())
            c.execute((Path(__file__).resolve().parents[3]/'database/migrations/20261121_002_edge_bff_guest_examples.sql').read_text())
            # Phase 4, the contact-support panel: support.send, the tickets and their images
            c.execute((Path(__file__).resolve().parents[3]/'database/migrations/20261122_001_edge_bff_support.sql').read_text())
            c.execute('CREATE TABLE public.market_private(secret text)')
        yield url
    finally:
        with psycopg.connect(admin,autocommit=True) as c:
            c.execute(f'DROP DATABASE "{name}" WITH (FORCE)');c.execute('DROP ROLE edge_bff_runtime')

@pytest.fixture
def store(database):
    # EXEC-SCREENER (migration 20261028_001): with the saved screener items and the watchlist; EXEC-MU-ACCOUNTS: and the
    # sign-in throttle, so one test's wrong passwords never limit another's sign-in
    with psycopg.connect(database) as c:c.execute('TRUNCATE edge_bff.sessions,edge_bff.jobs,edge_bff.conversation_ui,edge_bff.screener_items,edge_bff.watchlist_items,edge_bff.watchlist_lists,edge_bff.terminal_layouts,edge_bff.indicator_presets,edge_bff.terminal_drawings,edge_bff.auth_throttle,edge_bff.users,edge_bff.user_preferences,edge_bff.email_outbox,edge_bff.email_suppression,edge_bff.email_hook_events,edge_bff.admin_audit CASCADE')  # admin_audit by name: 20261119_040 dropped its foreign keys to users, so the cascade no longer reaches it
    return Store(database)

@pytest.fixture
def settings(database):
    return Settings(database_url=database,orc_url='http://orc.invalid',orc_key='local-test-key',owner='local-test-owner',login='owner',password_verifier=password_verifier('local-test-password'),session_secret='local-test-secret-'*3,origin='http://testserver',environment='local',secure_cookie=False,worker_enabled=False,poll_seconds=0.005,admin_owners=('local-test-owner',))

class FakeOrc:
    # EXEC-MU-ACCOUNTS fix round (re-check R1-21): owner-aware as Orc is. A run, its conversation and a branch belong to
    # the owner that made them; another owner's read answers as Orc does (not found: None, or NOT_RUNNING for a stop),
    # so a route that relies on Orc alone for isolation is tested by edge-bff's suite too. A row a test puts into
    # `saved` itself, without an owner, stays readable by every owner (the single-owner tests).
    def __init__(self,status='COMPLETED'):self.status=status;self.saved={};self.calls=[];self.conversation_owner={}
    def mine(self,t,owner):return t.get('owner') in (None,owner)
    def conv_mine(self,conv,owner):return self.conversation_owner.get(conv) in (None,owner)
    def run(self,owner,id,payload):
        self.calls.append((owner,id,payload.copy()));conv=payload.get('conversation_id') or 'conv_'+uuid.uuid4().hex
        result={'request_id':id,'status':self.status,'response':{'response_type':'ANSWER','answer':'Saved answer <script>window.pwned=true</script>','assumptions':[],'limitations':[],'clarification_question':None,'research_plan':None},'execution':{'model':payload.get('model') or 'fixture-model','cost':0.001,'total_tokens':42,**({'reasoning_level':payload['reasoning_level']} if payload.get('reasoning_level') else {}),**({'lane':payload['lane']} if payload.get('lane') else {})},'conversation':{'conversation_id':conv,'persistence':'SAVED'},'options':[{'label':'Quick summary','route':'QUICK_SUMMARY'}]}
        if not self.conv_mine(conv,owner):
            from app.client import OrcError
            raise OrcError('CONVERSATION_NOT_FOUND',404)
        self.conversation_owner.setdefault(conv,owner)
        self.saved[id]={'request_id':id,'conversation_id':conv,'turn_status':'COMPLETED','run_status':self.status,'response':result,'user_message':payload['message'],'owner':owner};return result
    def stop(self,owner,id):
        if id in self.saved and not self.mine(self.saved[id],owner):return 'NOT_RUNNING'
        self.stopped=getattr(self,'stopped',[])+[id];return 'NOT_RUNNING' if id in self.saved else 'STOPPING'
    def request(self,owner,id):
        t=self.saved.get(id)
        if t is None or not self.mine(t,owner):return None
        same=[k for k,v in self.saved.items() if v['conversation_id']==t['conversation_id']]
        return dict(t,turn_index=same.index(id))
    # EXEC-ASK-BRANCH: Orc's branch (a new conversation continuing conv up to through_turn) and its lineage
    lineages={}
    def branch(self,owner,conv,through_turn):
        if not self.conv_mine(conv,owner):
            from app.client import OrcError
            raise OrcError('CONVERSATION_NOT_FOUND',404)
        new='conv_'+uuid.uuid4().hex;self.lineages=dict(self.lineages);self.conversation_owner[new]=owner
        self.lineages[new]=[*self.lineages.get(conv,[]),{'conversation_id':conv,'through_turn':through_turn}]
        self.branched=getattr(self,'branched',[])+[(conv,through_turn)]
        return {'conversation_id':new,'lineage':self.lineages[new]}
    def execution_ready(self,owner):return True
    def messages(self,owner,conv,after=-1,limit=20,through=None):
        if not self.conv_mine(conv,owner):return None
        turns=[dict(t,turn_index=i,status=t['turn_status'],created_at='2026-10-08T00:00:00+00:00',completed_at='2026-10-08T00:00:01+00:00') for i,t in enumerate(t for t in self.saved.values() if t['conversation_id']==conv)];turns=[t for t in turns if t['turn_index']>after and (through is None or t['turn_index']<=through)]
        if not turns and conv not in self.lineages and not any(t['conversation_id']==conv for t in self.saved.values()):return None
        return {'conversation_id':conv,'messages':turns[:limit],'has_more':len(turns)>limit,'next_after':turns[limit-1]['turn_index'] if len(turns)>limit else None,'research_plan':None,'lineage':self.lineages.get(conv,[])}
    # EXEC-MODELS: Orc's GET /v1/models (prices per one million tokens; Orc strips nothing, the BFF drops 'reasoning')
    MODELS={'models':[{'model':'deepseek/deepseek-v4.1-flash','label':'DeepSeek V4.1 Flash','reasoning_levels':['low','high','max'],'input_per_million':0.0441,'output_per_million':0.63,'cache_read_per_million':0.0054},
                      {'model':'z-ai/glm-5.3-flash','label':'GLM 5.3 Flash','reasoning_levels':['low','high','max'],'input_per_million':0.0261,'output_per_million':0.9,'cache_read_per_million':0.0108},
                      {'model':'xiaomi/mimo-v2.6-flash','label':'MiMo V2.6 Flash','reasoning_levels':['off','on'],'input_per_million':0.14,'output_per_million':0.28,'cache_read_per_million':0.0028},
                      {'model':'qwen/qwen3.8-flash','label':'Qwen3.8 Flash','reasoning_levels':['off','on'],'input_per_million':0.15,'output_per_million':0.47,'cache_read_per_million':0.016}],
            'prices_fetched_at':'2026-10-13T10:25:31+00:00','edge_default':{'model':'deepseek/deepseek-v4.1-flash','reasoning_level':'high'},
            'server_default':{'model':'deepseek/deepseek-v4.1-flash'}}
    def models(self,owner):self.model_reads=getattr(self,'model_reads',0)+1;return self.MODELS
    def progress(self,owner,id):return getattr(self,"PROGRESS",{}).get(id)
    def close(self):pass
