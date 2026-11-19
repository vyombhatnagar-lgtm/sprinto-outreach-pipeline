"""Web dashboard (Vercel entrypoint: Vercel looks for a FastAPI instance named `app` here).

No passwords: the dashboard is open to anyone with the URL (owner's choice). Each domain
runs in its own request so one request stays well inside the function time limit; the
browser walks the list.
"""
import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from outreach import web
from outreach.config import HARDCODED_RECIPIENT, PROMPT_VERSION, load_settings
from outreach.domains import normalize_domain, normalize_domains
from outreach.models import STEP_ORDER
from outreach.pipeline import IMPLEMENTED_STEPS, build_pipeline
from outreach.stats import summarize
from outreach.trace import open_store

app = FastAPI(title="Sprinto Outreach Pipeline", docs_url=None, redoc_url=None)
MAX_DOMAINS = 15  # the case: 8-15 companies a week


@app.get("/healthz")
def healthz():
    s = load_settings()
    try:
        open_store(s).list_runs(limit=1)
        store_ok = True
    except Exception as e:  # report the failure class, never the connection string
        store_ok = f"error: {type(e).__name__}"
    return {"ok": True, "store": "postgres" if s.database_url else "files", "store_ok": store_ok,
            "llm_provider": s.provider, "llm_key_set": s.llm_ready,
            "hunter_key_set": bool(s.hunter_api_key), "gmail_ready": s.gmail_ready, "gmail_mode": s.gmail_mode, "recipient": HARDCODED_RECIPIENT,
            "prompt_version": PROMPT_VERSION}


@app.get("/api/models")
def gemini_models():
    """Which Gemini models this key can call (names only), to pick a model or fallback."""
    import httpx
    s = load_settings()
    if not s.gemini_api_key:
        raise HTTPException(400, "GEMINI_API_KEY is not set")
    r = httpx.get("https://generativelanguage.googleapis.com/v1beta/models", params={"pageSize": 200},
                  headers={"x-goog-api-key": s.gemini_api_key}, timeout=20)
    if r.status_code != 200:
        raise HTTPException(502, f"Gemini models list failed: HTTP {r.status_code}")
    models = [m["name"].split("/", 1)[-1] for m in r.json().get("models", [])
              if "generateContent" in m.get("supportedGenerationMethods", [])]
    return {"current": s.gemini_model, "fallback": s.gemini_fallback_model or None, "models": models}


@app.get("/", response_class=HTMLResponse)
def home():
    s = load_settings()
    store = open_store(s)
    runs = store.list_runs()
    try:
        numbers = summarize(store.outcome_records())
    except Exception:  # stats are decoration; never block the page
        numbers = None
    return web.home(runs, can_run=s.llm_ready, steps=IMPLEMENTED_STEPS, stats=numbers)


class NewRun(BaseModel):
    domains: list
    until: str = "send"


@app.post("/api/runs")
def create_run(body: NewRun):
    if body.until not in IMPLEMENTED_STEPS:
        raise HTTPException(400, f"until must be one of {IMPLEMENTED_STEPS}")
    if len(body.domains) > 4 * MAX_DOMAINS:
        raise HTTPException(400, f"Give 1-{MAX_DOMAINS} domains")
    if not all(isinstance(d, str) for d in body.domains):
        raise HTTPException(400, "domains must be a list of strings")
    try:
        domains = normalize_domains(body.domains)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not domains or len(domains) > MAX_DOMAINS:
        raise HTTPException(400, f"Give 1-{MAX_DOMAINS} domains")
    s = load_settings()
    store = open_store(s)
    store.write_manifest(domains, {**s.models_summary,
                                   "prompt_version": PROMPT_VERSION, "recipient": HARDCODED_RECIPIENT,
                                   "until": body.until, "source": "web"})
    return {"run_id": store.run_id, "domains": domains}


@app.post("/api/runs/{run_id}/domains/{domain}/advance")
def advance_domain(run_id: str, domain: str, until: str = "send", retry_failed: bool = False):
    """Do one unit of work for one domain (scrape, extract, one loop fetch, or final scoring)."""
    s = load_settings()
    if len(run_id) > 64:
        raise HTTPException(404, "Unknown run or domain")
    try:
        domain = normalize_domain(domain)
    except ValueError:
        raise HTTPException(404, "Unknown run or domain")
    store = open_store(s, run_id)
    manifest = store.read_manifest()
    if not manifest or domain not in manifest["domains"]:
        raise HTTPException(404, "Unknown run or domain")
    if until not in IMPLEMENTED_STEPS:
        raise HTTPException(400, "bad step")
    try:
        pipe = build_pipeline(s, store, until=until)
    except Exception as e:
        raise HTTPException(503, f"Cannot create the LLM client: {e}")
    return {"domain": domain, **pipe.advance(domain, until, retry_failed=retry_failed)}


@app.get("/runs/{run_id}", response_class=HTMLResponse)
def run_view(run_id: str):
    store = open_store(load_settings(), run_id)
    manifest = store.read_manifest()
    if not manifest:
        raise HTTPException(404, "Unknown run")
    records = {d: {st: store.read_step(d, st) for st in store.completed_steps(d)} for d in manifest["domains"]}
    return web.run_page(manifest, records)


@app.get("/api/runs/{run_id}/domains/{domain}/steps/{step}")
def step_json(run_id: str, domain: str, step: str):
    if step not in STEP_ORDER or len(run_id) > 64:
        raise HTTPException(404, "Unknown step")
    try:
        domain = normalize_domain(domain)
    except ValueError:
        raise HTTPException(404, "No record")
    rec = open_store(load_settings(), run_id).read_step(domain, step)
    if not rec:
        raise HTTPException(404, "No record")
    return JSONResponse(rec.model_dump(mode="json"))
