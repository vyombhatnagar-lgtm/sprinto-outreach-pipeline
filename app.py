"""Web dashboard (Vercel entrypoint: Vercel looks for a FastAPI instance named `app` here).

If APP_PASSWORD is set, every page needs HTTP Basic auth (any username + that
password). If it is not set, the dashboard is open to anyone with the URL. Each domain runs in its own request so one request stays
well inside the function time limit; the browser walks the list.
"""
import os
import secrets

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel

from outreach import web
from outreach.config import HARDCODED_RECIPIENT, PROMPT_VERSION, load_settings
from outreach.domains import normalize_domain, normalize_domains
from outreach.models import STEP_ORDER
from outreach.pipeline import IMPLEMENTED_STEPS, build_pipeline
from outreach.trace import open_store

app = FastAPI(title="Sprinto Outreach Pipeline", docs_url=None, redoc_url=None)
basic = HTTPBasic(auto_error=False)
MAX_DOMAINS = 15  # the case: 8-15 companies a week


def require_auth(creds: HTTPBasicCredentials = Depends(basic)) -> None:
    password = os.getenv("APP_PASSWORD", "")
    if not password:
        return  # open dashboard (owner's choice); set APP_PASSWORD to lock it
    if creds is None or not secrets.compare_digest(creds.password.encode(), password.encode()):
        raise HTTPException(401, "Sign in with any username and the APP_PASSWORD.",
                            headers={"WWW-Authenticate": 'Basic realm="outreach"'})


@app.get("/healthz")
def healthz():
    s = load_settings()
    try:
        open_store(s).list_runs(limit=1)
        store_ok = True
    except Exception as e:  # report the failure class, never the connection string
        store_ok = f"error: {type(e).__name__}"
    return {"ok": True, "store": "postgres" if s.database_url else "files", "store_ok": store_ok,
            "app_password_set": bool(os.getenv("APP_PASSWORD")),
            "llm_provider": s.provider, "llm_key_set": s.llm_ready, "recipient": HARDCODED_RECIPIENT,
            "prompt_version": PROMPT_VERSION}


@app.get("/", response_class=HTMLResponse, dependencies=[Depends(require_auth)])
def home():
    s = load_settings()
    runs = open_store(s).list_runs()
    return web.home(runs, can_run=s.llm_ready, steps=IMPLEMENTED_STEPS)


class NewRun(BaseModel):
    domains: list
    until: str = "qualify"


@app.post("/api/runs", dependencies=[Depends(require_auth)])
def create_run(body: NewRun):
    if body.until not in IMPLEMENTED_STEPS:
        raise HTTPException(400, f"until must be one of {IMPLEMENTED_STEPS}")
    try:
        domains = normalize_domains([str(d) for d in body.domains])
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


@app.post("/api/runs/{run_id}/domains/{domain}", dependencies=[Depends(require_auth)])
def run_domain(run_id: str, domain: str, until: str = "qualify"):
    s = load_settings()
    store = open_store(s, run_id)
    manifest = store.read_manifest()
    domain = normalize_domain(domain)
    if not manifest or domain not in manifest["domains"]:
        raise HTTPException(404, "Unknown run or domain")
    if until not in IMPLEMENTED_STEPS:
        raise HTTPException(400, "bad step")
    try:
        pipe = build_pipeline(s, store, until=until)
    except Exception as e:
        raise HTTPException(503, f"Cannot create the LLM client: {e}")
    res = pipe.run_domain(domain, until)
    q = res.get("qualification")
    return {"domain": domain, "steps": {k: str(v) for k, v in res["steps"].items()},
            "decision": q.decision if q else None}


@app.get("/runs/{run_id}", response_class=HTMLResponse, dependencies=[Depends(require_auth)])
def run_view(run_id: str):
    store = open_store(load_settings(), run_id)
    manifest = store.read_manifest()
    if not manifest:
        raise HTTPException(404, "Unknown run")
    records = {d: {st: store.read_step(d, st) for st in store.completed_steps(d)} for d in manifest["domains"]}
    return web.run_page(manifest, records)


@app.get("/api/runs/{run_id}/domains/{domain}/steps/{step}", dependencies=[Depends(require_auth)])
def step_json(run_id: str, domain: str, step: str):
    if step not in STEP_ORDER:
        raise HTTPException(404, "Unknown step")
    rec = open_store(load_settings(), run_id).read_step(domain, step)
    if not rec:
        raise HTTPException(404, "No record")
    return JSONResponse(rec.model_dump(mode="json"))
