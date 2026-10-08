"""Consume a response produced by the real Orc HTTP/storage implementation (M68)."""
import json
import os
from pathlib import Path
import subprocess
import sys
import httpx
from fastapi.testclient import TestClient
from app.client import OrcClient
from app.main import create_app
from app.worker import Worker
import asyncio


def test_current_orc_saved_response_contract(settings,store):
    repo=Path(__file__).resolve().parents[3]
    orc_root=repo/'apps/market-ai-orc'
    source='''
import json
from test_conversations import databases,store_for,Api,answer,server,AUTH
fixture=databases.__wrapped__()
try:
    _,url=next(fixture)
    api=Api(store_for(url),[answer("Canonical Orc answer")])
    posted=api.post(server("edge-contract","Current contract"),owner="local-test-owner").json()
    headers={**AUTH,"X-Saniti-Owner":"local-test-owner"}
    saved=api.client.get("/v1/agent/requests/edge-contract",headers=headers).json()
    history=api.client.get("/v1/conversations/"+posted["conversation"]["conversation_id"]+"/messages",headers=headers).json()
    print("EDGE_CONTRACT:"+json.dumps({"posted":posted,"saved":saved,"history":history}))
finally:
    try: next(fixture)
    except StopIteration: pass
'''
    env={**os.environ,'ORC_TEST_POSTGRES_URL':os.environ['EDGE_TEST_POSTGRES_URL'],'PYTHONPATH':str(orc_root)+':'+str(orc_root/'tests')}
    completed=subprocess.run([sys.executable,'-c',source],cwd=orc_root,env=env,capture_output=True,text=True,timeout=30)
    assert completed.returncode==0,completed.stderr
    contract=json.loads(next(line[len('EDGE_CONTRACT:'):] for line in completed.stdout.splitlines() if line.startswith('EDGE_CONTRACT:')))
    def handler(req):
        data=contract['saved'] if '/requests/' in req.url.path else contract['history']
        return httpx.Response(200,json=data)
    client=OrcClient(settings,httpx.Client(base_url=settings.orc_url,transport=httpx.MockTransport(handler)))
    job,_=store.submit(settings.owner,'canonical',{'message':'Current contract'})
    row=store.claim(90)
    # Read-side recovery consumes the saved canonical envelope, which excludes POST's conversation decoration.
    asyncio.run(Worker(settings,store,client).process(row))
    with TestClient(create_app(settings,store,client)) as api:
        sign=api.post('/api/v1/auth/sign-in',headers={'Origin':settings.origin},json={'login':settings.login,'password':'local-test-password'}).json()
        snapshot=api.get('/api/v1/runs/'+job['request_id']).json()
        assert snapshot['response']==contract['saved']['response']
        assert 'conversation' not in snapshot['response']
        assert snapshot['state']=='FINISHED' and snapshot['response']['response']['answer']=='Canonical Orc answer'
        conv=snapshot['conversation_id']
        assert api.get('/api/v1/conversations/'+conv+'/messages').json()['messages']==contract['history']['messages']
