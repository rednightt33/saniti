"""Governor-side fetch with verified quotes, model slots, shared evidence budget, and full stored excerpts."""
from __future__ import annotations

import hashlib
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import ConfigError, Settings
from app.fetcher import DocumentFetcher, FetchError, verify_quotes
from app.governor import _allocate_evidence, _sha256_json
from app.main import create_app
from app.provider import OpenRouterProvider
from app.store import SqliteStore

from conftest import API_KEY, fake_fetcher, public_resolver
from test_api import request_body

URL = "https://www.bi.go.id/id/statistik/indikator/bi-rate.aspx"
HTML = (
    "<html><head><title>BI-Rate</title><script>var secret = 'ignore me';</script></head><body>"
    "<nav>Menu</nav><h1>BI-Rate</h1><p>Rapat Dewan Gubernur Bank Indonesia pada 22-23 September 2026 memutuskan "
    "untuk mempertahankan BI-Rate sebesar 5,75%.</p><table><tr><td>23 September 2026</td><td>5,75 %</td></tr>"
    "</table><p>" + "Keterangan tambahan tentang kebijakan moneter. " * 8 + "</p></body></html>"
).encode()


def make_pdf(text: str) -> bytes:
    """A minimal one-page PDF with one line of text, built by hand so tests need no PDF writer."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


def settings_for(tmp_path, **extra):
    env = {
        "WEB_GOVERNOR_API_KEY": API_KEY,
        "OPENROUTER_API_KEY": "provider-key",
        "WEB_GOVERNOR_STORE_PATH": str(tmp_path / "web.sqlite3"),
        "WEB_OPENROUTER_MODEL": "deepseek/deepseek-v4.1-flash",
        "WEB_SLOT_2_MODEL": "xiaomi/mimo-v2.5",
        "WEB_SLOT_3_MODEL": "z-ai/glm-5.3-flashx",
        "WEB_SLOT_3_ENABLED": "false",
        "WEB_SLOT_2_REASONING_EFFORT": "low",
        "WEB_MAX_RESULTS_PER_SEARCH": "30",
    }
    env.update(extra)
    return Settings.from_env(env)


def model_reply(text, annotations=()):
    return {
        "id": "resp", "status": "completed",
        "output": [{"type": "message", "content": [
            {"type": "output_text", "text": text, "annotations": list(annotations)}]}],
        "usage": {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150, "cost": 0.001},
    }


def app_client(tmp_path, replies, pages, captured=None, **extra):
    settings = settings_for(tmp_path, **extra)
    queue = list(replies)

    def handler(request: httpx.Request) -> httpx.Response:
        if captured is not None:
            captured.append(json.loads(request.content))
        return httpx.Response(200, request=request, json=queue.pop(0))

    provider = OpenRouterProvider(settings, client=httpx.Client(transport=httpx.MockTransport(handler)))
    app = create_app(settings=settings, store=SqliteStore(settings.store_path), provider=provider,
                     fetcher=fake_fetcher(settings, pages))
    return TestClient(app)


@pytest.fixture
def auth():
    return {"Authorization": f"Bearer {API_KEY}"}


# --- fetcher -----------------------------------------------------------------------------------------------------

def test_private_address_and_private_redirect_are_blocked(tmp_path):
    settings = settings_for(tmp_path)
    blocked = DocumentFetcher(settings, client=httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(200, request=r, content=b"x"))), resolver=lambda host, port: ["10.1.2.3"])
    with pytest.raises(FetchError) as exc:
        blocked.fetch(URL)
    assert exc.value.code == "PRIVATE_ADDRESS_BLOCKED"

    def resolver(host, port):
        return ["169.254.169.254"] if host == "evil.example.com" else ["93.184.216.34"]

    redirecting = DocumentFetcher(settings, client=httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(302, request=r, headers={"location": "https://evil.example.com/meta"}))),
        resolver=resolver)
    with pytest.raises(FetchError) as exc:
        redirecting.fetch(URL)
    assert exc.value.code == "PRIVATE_ADDRESS_BLOCKED"


def test_redirect_limit_size_limit_and_content_type(tmp_path):
    settings = settings_for(tmp_path, WEB_FETCH_MAX_BYTES="10000", WEB_FETCH_MAX_REDIRECTS="1")
    loop = fake_fetcher(settings, {
        URL: (302, {"location": URL + "?a=1"}, b""), URL + "?a=1": (302, {"location": URL}, b"")})
    with pytest.raises(FetchError) as exc:
        loop.fetch(URL)
    assert exc.value.code == "TOO_MANY_REDIRECTS"
    big = fake_fetcher(settings, {URL: (200, {"content-type": "text/html"}, b"a" * 20000)})
    with pytest.raises(FetchError) as exc:
        big.fetch(URL)
    assert exc.value.code == "SOURCE_TOO_LARGE"
    image = fake_fetcher(settings, {URL: (200, {"content-type": "image/png"}, b"\x89PNG")})
    with pytest.raises(FetchError) as exc:
        image.fetch(URL)
    assert exc.value.code == "UNSUPPORTED_CONTENT_TYPE"


def test_html_and_pdf_text_extraction(tmp_path):
    settings = settings_for(tmp_path)
    html = fake_fetcher(settings, {URL: (200, {"content-type": "text/html; charset=utf-8"}, HTML)}).fetch(URL)
    assert html.content_type == "WEB_PAGE" and html.title == "BI-Rate"
    assert "mempertahankan BI-Rate sebesar 5,75%" in html.text
    assert "ignore me" not in html.text
    assert "23 September 2026 | 5,75 %" in html.text
    assert html.raw_sha256 == hashlib.sha256(HTML).hexdigest()
    pdf_url = "https://www.idx.co.id/a.pdf"
    pdf = fake_fetcher(settings, {pdf_url: (200, {"content-type": "application/pdf"},
                                            make_pdf("Dividen tunai Rp25 per saham"))}).fetch(pdf_url)
    assert pdf.content_type == "PDF" and pdf.page_count == 1
    assert "Dividen tunai Rp25 per saham" in pdf.text


def test_quotes_must_appear_verbatim():
    text = "Rapat memutuskan untuk mempertahankan   BI-Rate sebesar 5,75%.\nLain-lain."
    verified, rejected = verify_quotes(text, [
        "“mempertahankan BI-Rate sebesar 5,75%.”",  # typography and whitespace differ, words do not
        "Rapat memutuskan menaikkan BI-Rate menjadi 6,00%.",  # fabricated
        "5,75%",  # too short to be evidence
    ])
    assert [item["text"] for item in verified] == ["mempertahankan BI-Rate sebesar 5,75%."]
    assert len(rejected) == 2


# --- fetch through the API ---------------------------------------------------------------------------------------

def test_fetch_records_only_verified_quotes_and_stores_the_document(tmp_path, auth):
    reply = model_reply(
        "ASSESSMENT: SUPPORTED\nSUMMARY: BI kept the BI-Rate at 5.75% on 22-23 September 2026.\n"
        "QUOTE: Rapat Dewan Gubernur Bank Indonesia pada 22-23 September 2026 memutuskan untuk mempertahankan "
        "BI-Rate sebesar 5,75%.\nQUOTE: Bank Indonesia menaikkan BI-Rate menjadi 6,25% pada September 2026."
    )
    captured = []
    pages = {URL: (200, {"content-type": "text/html"}, HTML)}
    with app_client(tmp_path, [reply], pages, captured) as client:
        result = client.post("/v1/fetch", headers=auth, json={
            "contract_version": "v1", "request_id": "fetch-1", "url": URL, "objective": "Latest BI-Rate"}).json()
        assert result["status"] == "EVIDENCE_READY"
        assert [item["excerpt_kind"] for item in result["evidence"]] == ["VERIFIED_QUOTE"]
        assert "6,25" not in json.dumps(result["evidence"])
        assert "QUOTE_NOT_IN_SOURCE" in {w["code"] for w in result["warnings"]}
        assert "QUOTE:" not in result["coverage"][0]["summary"]
        document = result["documents"][0]
        stored = client.get(f"/v1/documents/{document['document_id']}", headers=auth).json()
        assert stored["raw_sha256"] == hashlib.sha256(HTML).hexdigest()
        evidence = client.get(f"/v1/evidence/{result['evidence'][0]['evidence_id']}", headers=auth).json()
        start, end = evidence["quote_start"], evidence["quote_end"]
        assert evidence["document_id"] == document["document_id"] and end > start
    assert "tools" not in captured[0]
    assert "mempertahankan BI-Rate sebesar 5,75%" in captured[0]["input"]
    assert result["applied_policy"][0]["fetched_by"] == "governor"


def test_fetch_failures_are_reported_without_a_model_call(tmp_path, auth):
    pages = {
        URL: (404, {}, b""),
        "https://www.bi.go.id/empty": (200, {"content-type": "text/html"}, b"<html><body>Loading...</body></html>"),
        "https://www.bi.go.id/moved": (301, {"location": "https://other.example.com/x"}, b""),
        "https://other.example.com/x": (200, {"content-type": "text/html"}, HTML),
    }
    with app_client(tmp_path, [], pages) as client:
        missing = client.post("/v1/fetch", headers=auth, json={
            "contract_version": "v1", "request_id": "f-404", "url": URL, "objective": "rate"}).json()
        empty = client.post("/v1/fetch", headers=auth, json={
            "contract_version": "v1", "request_id": "f-empty", "url": "https://www.bi.go.id/empty",
            "objective": "rate"}).json()
        moved = client.post("/v1/fetch", headers=auth, json={
            "contract_version": "v1", "request_id": "f-moved", "url": "https://www.bi.go.id/moved",
            "objective": "rate"}).json()
    assert (missing["status"], missing["coverage"][0]["gaps"], missing["next_action"]) == (
        "BLOCKED", ["SOURCE_HTTP_ERROR"], "REVIEW_FETCH")
    assert missing["execution"]["provider_call_count"] == 0
    assert empty["coverage"][0]["gaps"] == ["DYNAMIC_PAGE_OR_EMPTY"] and empty["evidence"] == []
    assert moved["coverage"][0]["gaps"] == ["REDIRECTED_TO_OTHER_DOMAIN"]


# --- model slots -------------------------------------------------------------------------------------------------

def test_slots_configuration_and_capabilities(tmp_path, auth):
    settings = settings_for(tmp_path)
    assert settings.slot(1).model == "deepseek/deepseek-v4.1-flash"
    assert settings.slot(2).model == "xiaomi/mimo-v2.5" and settings.slot(2).reasoning_effort == "low"
    assert settings.slot(3).enabled is False
    assert [slot.enabled for slot in settings.slots[3:]] == [False] * 4
    with pytest.raises(ConfigError):
        settings_for(tmp_path, WEB_SLOT_4_ENABLED="true")  # enabled without a model
    with app_client(tmp_path, [], {}) as client:
        capabilities = client.get("/v1/capabilities", headers=auth).json()
    assert len(capabilities["model_slots"]) == 7
    assert capabilities["limits"]["max_results_per_search"] == 30
    assert "provider-key" not in json.dumps(capabilities)


def test_search_uses_the_requested_slot_and_rejects_a_disabled_one(tmp_path, auth):
    captured = []
    reply = model_reply("ASSESSMENT: SUPPORTED\nSUMMARY: Found.", [
        {"type": "url_citation", "url": "https://www.bi.go.id/a", "title": "A", "content": "BI-Rate 5,75%"}])
    with app_client(tmp_path, [reply], {}, captured) as client:
        ok = client.post("/v1/search", headers=auth, json={
            "contract_version": "v1", "request_id": "s-slot2", "query": "BI rate", "model_slot": 2,
            "budget": {"max_searches": 1, "max_results_per_search": 30}})
        disabled = client.post("/v1/search", headers=auth, json={
            "contract_version": "v1", "request_id": "s-slot3", "query": "BI rate", "model_slot": 3})
        too_many = client.post("/v1/search", headers=auth, json={
            "contract_version": "v1", "request_id": "s-31", "query": "BI rate",
            "budget": {"max_searches": 1, "max_results_per_search": 31}})
    assert ok.status_code == 200
    assert captured[0]["model"] == "xiaomi/mimo-v2.5"
    assert captured[0]["reasoning"] == {"effort": "low"}
    assert captured[0]["tools"][0]["parameters"]["max_results"] == 30
    assert ok.json()["execution"]["model_slot"] == 2
    assert disabled.status_code == 422 and disabled.json()["code"] == "MODEL_SLOT_UNAVAILABLE"
    assert too_many.status_code == 422


def test_requests_without_a_slot_keep_their_earlier_fingerprint(tmp_path, auth):
    body = request_body("fp-1")
    expected = _sha256_json(json.loads(json.dumps(body)))  # the pre-slot body had no model_slot key
    settings = settings_for(tmp_path)
    store = SqliteStore(settings.store_path)
    with TestClient(create_app(settings=settings, store=store, provider=OpenRouterProvider(settings),
                               fetcher=fake_fetcher(settings))) as client:
        planned = client.post("/v1/web-needs", headers=auth, json=body).json()
    assert store.get_need(planned["web_need_id"])["request_fingerprint"] == expected
    assert planned["plan"]["model_slot"] == 1


# --- evidence budget and stored excerpts ---------------------------------------------------------------------------

def test_evidence_budget_is_shared_across_criteria():
    def item(criterion, index, url=None):
        return {"evidence_id": f"{criterion}-{index}", "canonical_url": url or f"https://x/{criterion}/{index}",
                "content_sha256": f"{criterion}{index}" if not url else "same"}

    shared = item("a", 0, url="https://x/shared")
    candidates = {
        "a": [shared] + [item("a", i) for i in range(1, 5)],
        "b": [dict(shared, evidence_id="b-dup")] + [item("b", i) for i in range(1, 5)],
        "c": [item("c", i) for i in range(5)],
    }
    evidence, links, per_criterion, dropped = _allocate_evidence(candidates, 6)
    assert len(evidence) == 6
    assert {key: len(value) for key, value in per_criterion.items()} == {"a": 2, "b": 3, "c": 2}
    assert per_criterion["b"][0]["evidence_id"] == "a-0"  # the duplicate was linked, not stored twice
    assert set(dropped) == {"a", "b", "c"}


def test_full_excerpt_stays_stored_when_the_response_is_compacted(tmp_path, auth):
    long_excerpt = "Kalimat bukti yang panjang. " * 150
    annotations = [{"type": "url_citation", "url": f"https://www.bi.go.id/{i}", "title": "A",
                    "content": long_excerpt + str(i)} for i in range(4)]
    reply = model_reply("ASSESSMENT: SUPPORTED\nSUMMARY: Found.", annotations)
    with app_client(tmp_path, [reply], {}) as client:
        result = client.post("/v1/search", headers=auth, json={
            "contract_version": "v1", "request_id": "compact", "query": "q",
            "budget": {"max_searches": 1, "max_results_per_search": 5, "max_output_characters": 4000}}).json()
        codes = {w["code"] for w in result["warnings"]}
        # Four 2,500-character excerpts cannot fit 4,000 characters; even the bare response is larger (W10).
        assert {"RESPONSE_COMPACTED", "RESPONSE_BUDGET_EXCEEDED"} <= codes
        first = result["evidence"][0]
        assert first["excerpt_kind"] in {"TRUNCATED_IN_RESPONSE", "NOT_INCLUDED_IN_RESPONSE"}
        stored = client.get(f"/v1/evidence/{first['evidence_id']}", headers=auth).json()
    assert stored["excerpt_kind"] == "SOURCE_EXCERPT"
    assert len(stored["excerpt"]) == 2500  # the full excerpt, capped only by WEB_MAX_EXCERPT_CHARACTERS
