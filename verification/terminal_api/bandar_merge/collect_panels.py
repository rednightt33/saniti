"""User 2026-11-01 ("Kita kirimkan saya 10 opsi dalam satu HTML apabila bandar detector kita gabung ke top brokers"): the
figures the options page shows, read from the live Terminal (Railway dev) as its own panels show them. Read-only; signed
in as the owner (credentials read from edge-bff's Railway variables into memory, never printed).

For each ticker and period (1D, 5D, 20D): Top brokers (#accBody tooltips: net, lot, Domestic, Foreign per broker), the
Bandar detector at Top 3, 5 and 10 (#bdBody: Buy, Sell, Net, ratio to total buy, verdict, foreign share of buyers), and
Broker summary at top 10 (net, all investors, and Foreign and Domestic) for the ranks the Top brokers table does not show.

Usage: python3 collect_panels.py OUT.json TICKER ...   (build_options.py reads OUT.json)"""
import json, os, subprocess, sys
from playwright.sync_api import sync_playwright
v = json.loads(subprocess.run(['railway','variable','list','-s','edge-bff','-e','dev','--json'],capture_output=True,text=True,check=True).stdout)
base='https://'+v['RAILWAY_PUBLIC_DOMAIN']; login,pw=v.get('EDGE_LOGIN'),v.get('EDGE_INITIAL_PASSWORD'); del v
out={}
TICKERS=sys.argv[2:] or ['BBCA']
with sync_playwright() as p:
    proxy=os.environ.get('HTTPS_PROXY')
    b=p.chromium.launch(executable_path='/opt/pw-browsers/chromium', **({'proxy':{'server':proxy}} if proxy else {}))
    ctx=b.new_context(viewport={'width':1600,'height':1000})
    assert ctx.request.post(base+'/api/v1/auth/sign-in',data=json.dumps({'login':login,'password':pw}),headers={'Content-Type':'application/json','Origin':base}).status==200
    pg=ctx.new_page(); pg.goto(base+'/favicon.svg')
    for T in TICKERS:
     o={}; out[T]=o
     pg.evaluate("t=>{localStorage.setItem('ml.symbol',t);localStorage.setItem('ml.broker.collapsed','0');localStorage.setItem('ml.tf','D')}", T)
     pg.goto(base+'/terminal-app/')
     pg.wait_for_function("()=>window.__flowAll===true", timeout=90000); pg.wait_for_timeout(1500)
     for days in ('1','5','20'):
         pg.evaluate(f"()=>{{document.querySelector('#bdRange .seg button[data-n=\"{days}\"]').click();document.querySelector('#accRange .seg button[data-n=\"{days}\"]').click()}}")
         pg.wait_for_timeout(400)
         acc=pg.evaluate("()=>({hint:document.getElementById('accHint').textContent, rows:[...document.querySelectorAll('#accBody .pa-b[data-b]')].map(e=>e.dataset.tip)})")
         bd={}
         for n in ('3','5','10'):
             pg.evaluate(f"()=>document.querySelector('#bdTop button[data-n=\"{n}\"]').click()"); pg.wait_for_timeout(250)
             bd[n]=pg.evaluate("()=>({hint:document.getElementById('bdHint').textContent, text:document.getElementById('bdBody').innerText, tips:[...document.querySelectorAll('#bdBody [data-tip]')].map(e=>e.dataset.tip)})")
         pg.evaluate(f"()=>document.querySelector('#bsRange .seg button[data-n=\"{days}\"]').click()"); pg.wait_for_timeout(300)
         bs={}
         for inv in ('All','Foreign','Domestic'):
             pg.evaluate(f"()=>{{const s=document.getElementById('bsInv');s.value='{inv}';s.dispatchEvent(new Event('change'))}}"); pg.wait_for_timeout(300)
             if pg.evaluate("()=>document.querySelectorAll('#bsBody table')[0].querySelectorAll('tbody tr[data-b]').length") < 6:
                 pg.evaluate("()=>document.querySelector('#bsMore')?.click()"); pg.wait_for_timeout(300)
             bs[inv]=pg.evaluate("()=>({more:document.querySelector('#bsMore')?.textContent, tables:[...document.querySelectorAll('#bsBody table')].map(t=>[...t.querySelectorAll('tbody tr[data-b]')].map(r=>[...r.children].map(c=>c.textContent.trim())))})")
         pg.evaluate("()=>{const s=document.getElementById('bsInv');s.value='All';s.dispatchEvent(new Event('change'))}")
         o[days]={'acc':acc,'bd':bd,'bs':bs}
     o['sub']=pg.evaluate("()=>document.getElementById('rpSub').textContent")
    b.close()
json.dump(out,open(sys.argv[1],'w'),indent=1)
[print(T, out[T]['sub'], {d:[out[T][d]['bd'][n]['text'].split(chr(10))[1]+' '+out[T][d]['bd'][n]['text'].split(chr(10))[9] for n in ('3','5','10')] for d in ('1','5','20')}) for T in out]
