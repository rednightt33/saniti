"""Independent 3c checker, lens "terminal" (EXEC-MU-ACCOUNTS; CONTRACT.md 8b "3c in detail"): failing tests of the
defects found on the session branch dec1cfef.

/bundle's own rule (main.py bundle docstring): "a dataset the ticker does not have (broker for an index, events for a
ticker without events) answers with no files". For a capped owner every asked dataset goes to the cut (`capped`), and
cut.make_cut raises CutError when the manifest has no data_through for it (no such dataset), which /bundle answers
{"locked": true, "capability": "terminal.history_days", "reason": ...}: a history lock, which the page reads as "upgrade
for more history" (CONTRACT 8b, 3e), for data that does not exist at any plan. An uncapped owner gets no files for the
same request.
"""
from app.main import API
from test_phase3c import caps, make, owner


def bundle(client, headers, ticker, datasets):
    r = client.post(f'{API}/bundle', headers=headers, json={'ticker': ticker, 'datasets': datasets})
    assert r.status_code == 200, r.text
    return r.json()['datasets']


def test_a_capped_plan_gets_no_files_not_a_history_lock_for_a_dataset_the_ticker_does_not_have():
    client, _, _ = make()
    # the test bucket's BBRI has price only (no broker, no events), like an index has no broker data
    uncapped = bundle(client, owner(capabilities=caps(tickers=['BBRI'], datasets=['price', 'broker'],
                                                       history_days=None)), 'BBRI', ['price', 'broker'])
    assert uncapped['broker']['files'] == [] and 'locked' not in uncapped['broker']
    capped = bundle(client, owner('u_000000000000000000000002', caps(tickers=['BBRI'], datasets=['price', 'broker'],
                                                                    history_days=730)), 'BBRI', ['price', 'broker'])
    assert capped['price']['files'] and capped['price']['files'][0]['pack'] == 'cut'
    assert capped['broker'].get('files') == [] and 'locked' not in capped['broker'], capped['broker']
