"""Offline tests for step 3 (research loop + qualification), the Postgres store and the web app."""
import sqlite3

import pytest
from fastapi.testclient import TestClient

from outreach.config import load_settings
from outreach.extract import Extractor
from outreach.icp import load_scorecard
from outreach.models import StepRecord, utcnow
from outreach.pipeline import Pipeline
from outreach.research import Researcher, _Score, _Scores, short_circuit
from outreach.trace import PgTraceStore, TraceStore
from tests.test_phase1 import SITE, F, FakeLLM, empty_extraction, home_extraction, scraper

CARD = load_scorecard(load_settings().icp_path)


def page_aware_extraction(kw):
    """Fake extractor: returns facts depending on which page it was shown."""
    user = kw["user"]
    if 'kind="home"' in user:
        return home_extraction()
    if "Series B" in user:
        return empty_extraction(funding_stage=F("Series B", ("https://acme.io/company/about-us", "We raised a $30M Series B in 2025")),
                                employee_count=F("180", ("https://acme.io/company/about-us", "We are 180 employees")))
    if "GRC Manager" in user:
        return empty_extraction(compliance_job_postings=F("GRC Manager", ("https://acme.io/careers", "GRC Manager")))
    if "SOC 2 Type II audit" in user:
        return empty_extraction(
            certifications_claimed=F("SOC 2 Type II in progress", ("https://acme.io/trust", "Our SOC 2 Type II audit is in progress")),
            certification_status=F("in_progress", ("https://acme.io/trust", "Our SOC 2 Type II audit is in progress")))
    return empty_extraction()


def qualifier(status_by_id=None, fields=("is_saas",)):
    status_by_id = status_by_id or {}

    def out(kw):
        return _Scores(scores=[_Score(criterion_id=c.id, status=status_by_id.get(c.id, "met"), reason="r",
                                      supporting_fields=list(fields)) for c in CARD.criteria])
    return FakeLLM(out)


def run(site=SITE, qual=None, max_fetches=None):
    sc = scraper(site)
    ex = Extractor(FakeLLM(page_aware_extraction))
    res = sc.scrape("acme.io")
    profile, _ = ex.extract(res)
    r = Researcher(CARD, sc, ex, qual or qualifier(), max_fetches=max_fetches)
    return r.research(res, profile), sc


def test_loop_fetches_named_pages_for_open_questions_only():
    out, sc = run()
    steps = out["qualification"].agent_steps
    # homepage answered SaaS and stage (enterprise_signals), so only the certification question is open
    assert [(s.question, s.page_kind) for s in steps] == [("certified", "security")]
    assert steps[0].fields_filled == ["certifications_claimed", "certification_status"]
    assert out["qualification"].decision == "GO"


def test_loop_respects_the_fetch_cap():
    out, _ = run(max_fetches=0)
    q = out["qualification"]
    assert q.agent_steps == [] and "certified" in q.unanswered_questions
    assert any("treated as not certified" in f for f in q.flags)


def test_stage_question_walks_its_ladder_careers_first():
    site = dict(SITE)
    home = site["https://acme.io"][1].replace("Enterprise plan includes SSO and SAML.", "")
    site["https://acme.io"] = (200, home)

    def ext(kw):
        e = page_aware_extraction(kw)
        if 'kind="home"' in kw["user"]:
            e = e.model_copy(update={"enterprise_signals": F()})
        return e
    sc = scraper(site)
    ex = Extractor(FakeLLM(ext))
    res = sc.scrape("acme.io")
    profile, _ = ex.extract(res)
    out = Researcher(CARD, sc, ex, qualifier()).research(res, profile)
    kinds = [(s.question, s.page_kind) for s in out["qualification"].agent_steps]
    assert ("stage", "careers") in kinds and kinds.index(("stage", "careers")) < len(kinds)
    assert out["profile"].compliance_job_postings.value == "GRC Manager"


def test_not_saas_short_circuits_without_fetching():
    sc = scraper()
    ex = Extractor(FakeLLM(lambda kw: empty_extraction(
        is_saas=F("no", ("https://acme.io", "Acme is the cloud platform for invoice automation")))))
    res = sc.scrape("acme.io")
    profile, _ = ex.extract(res)
    assert short_circuit(profile)
    out = Researcher(CARD, sc, ex, qualifier()).research(res, profile)
    assert out["qualification"].decision == "NO_GO" and out["qualification"].agent_steps == []


def test_met_without_evidence_is_downgraded():
    out, _ = run(qual=qualifier(fields=("security_news",)))  # security_news is empty -> no evidence
    assert out["downgraded"]
    assert all(s.status == "unknown" for s in out["qualification"].scores)
    assert out["qualification"].decision == "MANUAL_REVIEW"


def test_full_pipeline_writes_three_steps(tmp_path):
    store = TraceStore(tmp_path)
    sc = scraper()
    ex = Extractor(FakeLLM(page_aware_extraction))
    pipe = Pipeline(load_settings(), store, scraper=sc, extractor=ex, researcher=Researcher(CARD, sc, ex, qualifier()))
    res = pipe.run_domain("acme.io")
    assert store.completed_steps("acme.io") == ["scrape", "extract", "qualify"]
    rec = store.read_step("acme.io", "qualify")
    assert rec.output["qualification"]["decision"] == res["qualification"].decision
    assert "https://acme.io/trust" in rec.output["page_text"]


# ---- Postgres store, exercised through sqlite with the same SQL ----

class SqliteStore(PgTraceStore):
    placeholder = "?"


def test_pg_store_roundtrip(tmp_path):
    db = str(tmp_path / "t.db")
    store = SqliteStore(lambda: sqlite3.connect(db))
    store.write_manifest(["acme.io"], {"until": "qualify"})
    rec = StepRecord(run_id=store.run_id, domain="acme.io", step="extract", status="ok", started_at=utcnow(),
                     output={"x": 1})
    store.write_step(rec)
    store.write_step(rec.model_copy(update={"output": {"x": 2}}))  # upsert
    again = SqliteStore(lambda: sqlite3.connect(db), run_id=store.run_id)
    assert again.read_step("acme.io", "extract").output == {"x": 2}
    assert again.completed_steps("acme.io") == ["extract"]
    assert again.list_runs()[0]["run_id"] == store.run_id


# ---- web app ----

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "pw")
    monkeypatch.setenv("RUNS_DIR", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("POSTGRES_URL", raising=False)
    import app as webapp
    return TestClient(webapp.app)


def test_web_requires_password(client):
    assert client.get("/").status_code == 401
    assert client.get("/", auth=("x", "wrong")).status_code == 401
    assert client.get("/", auth=("x", "pw")).status_code == 200
    assert client.get("/healthz").json()["ok"] is True


def test_web_open_without_password(client, monkeypatch):
    monkeypatch.delenv("APP_PASSWORD")
    assert client.get("/").status_code == 200


def test_web_creates_run_and_renders_trace(client, tmp_path):
    r = client.post("/api/runs", json={"domains": ["https://www.Acme.io/", "acme.io"], "until": "qualify"},
                    auth=("x", "pw"))
    assert r.status_code == 200 and r.json()["domains"] == ["acme.io"]
    run_id = r.json()["run_id"]
    # write a qualify record as the pipeline would, then render
    out, _ = run()
    store = TraceStore(tmp_path, run_id)
    store.write_step(StepRecord(run_id=run_id, domain="acme.io", step="qualify", status="ok", started_at=utcnow(),
                                output={"qualification": out["qualification"].model_dump(mode="json"),
                                        "profile": out["profile"].model_dump(mode="json")}))
    page = client.get(f"/runs/{run_id}", auth=("x", "pw"))
    assert page.status_code == 200 and "GO" in page.text and "Research loop" in page.text
    assert client.get(f"/api/runs/{run_id}/domains/acme.io/steps/qualify", auth=("x", "pw")).status_code == 200


def test_web_rejects_too_many_domains(client):
    r = client.post("/api/runs", json={"domains": [f"d{i}.com" for i in range(16)]}, auth=("x", "pw"))
    assert r.status_code == 400


# ---- Gemini client (mocked HTTP) ----

import httpx  # noqa: E402

from outreach.extract import _Extraction  # noqa: E402
from outreach.llm import GeminiLLM, LLMError, gemini_schema  # noqa: E402


def test_gemini_schema_inlines_refs_and_nullables():
    sch = gemini_schema(_Extraction)
    assert "$defs" not in str(sch) and "$ref" not in str(sch)
    assert sch["properties"]["is_saas"]["properties"]["value"]["type"] == ["string", "null"]
    assert sch["additionalProperties"] is False


def _gemini(handler, **kw):
    return GeminiLLM("k", "gemini-test", http=httpx.Client(transport=httpx.MockTransport(handler)),
                     sleep=lambda s: None, **kw)


def test_gemini_structured_parses_json_and_records_usage():
    seen = {}

    def handler(req):
        seen["key"] = req.headers["x-goog-api-key"]
        seen["body"] = req.read()
        out = _Scores(scores=[_Score(criterion_id="is_saas", status="met", reason="r", supporting_fields=[])])
        return httpx.Response(200, json={"candidates": [{"finishReason": "STOP", "content": {"parts": [
            {"text": "thinking...", "thought": True}, {"text": out.model_dump_json()}]}}],
            "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5}, "modelVersion": "gemini-test-001"})
    parsed, meta = _gemini(handler).structured(system="s", user="u", output_model=_Scores)
    assert parsed.scores[0].status == "met" and meta["model"] == "gemini-test-001" and meta["input_tokens"] == 10
    assert seen["key"] == "k" and b"responseJsonSchema" in seen["body"] and b"systemInstruction" in seen["body"]


@pytest.mark.parametrize("resp,msg", [
    (httpx.Response(403, json={"error": {"message": "bad key"}}), "authentication"),
    (httpx.Response(429, json={}), "busy"),
    (httpx.Response(503, json={}), "busy"),
    (httpx.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}}), "blocked"),
    (httpx.Response(200, json={"candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": []}}]}), "max"),
])
def test_gemini_errors_are_clear(resp, msg):
    with pytest.raises(LLMError, match=msg):
        _gemini(lambda req: resp).structured(system="s", user="u", output_model=_Scores)


def test_provider_defaults_to_gemini_when_key_present(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    s = load_settings()
    assert s.provider == "gemini" and s.llm_ready


def _ok_scores():
    out = _Scores(scores=[_Score(criterion_id="is_saas", status="met", reason="r", supporting_fields=[])])
    return {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": out.model_dump_json()}]}}]}


def test_gemini_retries_busy_then_succeeds_and_can_fall_back():
    calls = []

    def handler(req):
        calls.append(req.url.path)
        if len(calls) < 3:
            return httpx.Response(503, json={"error": {"message": "high demand"}})
        return httpx.Response(200, json=_ok_scores())
    parsed, meta = _gemini(handler, fallback_model="gemini-backup").structured(system="s", user="u", output_model=_Scores)
    assert meta["attempts"] == 3 and meta["fallback_ran"] is True
    assert calls[0].endswith("gemini-test:generateContent") and calls[2].endswith("gemini-backup:generateContent")


def test_busy_error_is_retryable():
    with pytest.raises(LLMError) as ei:
        _gemini(lambda req: httpx.Response(503, json={})).structured(system="s", user="u", output_model=_Scores)
    assert ei.value.retryable


# ---- resumable pipeline: one unit of work per call ----

def _pipe(tmp_path, qual=None, extract_fn=page_aware_extraction):
    store = TraceStore(tmp_path)
    store.write_manifest(["acme.io"], {})
    sc = scraper()
    ex = Extractor(FakeLLM(extract_fn))
    return Pipeline(load_settings(), store, scraper=sc, extractor=ex,
                    researcher=Researcher(CARD, sc, ex, qual or qualifier())), store


def test_advance_does_one_unit_per_call(tmp_path):
    pipe, store = _pipe(tmp_path)
    stages = []
    for _ in range(10):
        r = pipe.advance("acme.io")
        stages.append(r["stage"])
        if r["done"]:
            break
    assert stages == ["scrape", "extract", "research", "research", "qualify"]
    assert store.read_step("acme.io", "qualify").output["qualification"]["decision"] == "GO"


def test_busy_model_mid_loop_resumes_without_losing_state(tmp_path):
    state = {"busy": True}

    def flaky(kw):
        if "SOC 2 Type II audit" in kw["user"] and state["busy"]:
            raise LLMError("Gemini is busy", retryable=True)
        return page_aware_extraction(kw)
    pipe, store = _pipe(tmp_path, extract_fn=flaky)
    pipe.advance("acme.io"); pipe.advance("acme.io")         # scrape, extract
    r = pipe.advance("acme.io")                               # loop fetch hits a busy model
    assert r["retry"] and not r["done"]
    assert store.read_step("acme.io", "qualify").status == "error"
    state["busy"] = False
    r = pipe.advance("acme.io")                               # same fetch again, succeeds
    assert r["stage"] == "research"
    st = store.read_step("acme.io", "qualify").output["state"]
    assert [s["page_kind"] for s in st["steps"]] == ["security"]


def test_retries_are_capped(tmp_path):
    def always_busy(kw):
        raise LLMError("busy", retryable=True)
    pipe, store = _pipe(tmp_path, extract_fn=always_busy)
    res = pipe.run_domain("acme.io", retry_wait=0)
    assert "error" in res["steps"]["extract"] and "qualification" not in res


def test_gemini_honours_retry_delay():
    waits, calls = [], []

    def handler(req):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, json={"error": {"details": [
                {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "21s"}]}})
        return httpx.Response(200, json=_ok_scores())
    llm = GeminiLLM("k", "m", http=httpx.Client(transport=httpx.MockTransport(handler)), sleep=waits.append)
    llm.structured(system="s", user="u", output_model=_Scores)
    assert waits == [21.0]
