"""Orchestrator: moves each domain through the steps, writing a trace record per step.

`advance()` does ONE unit of work and saves it: scrape, extract, one research-loop fetch,
or the final scoring. The web app calls it once per request, so no request comes near the
serverless time limit even when the model provider is slow, and a failed unit is retried
without redoing earlier ones. `run_domain()` simply calls advance() until done (CLI, tests).

A failure on one domain is recorded and the batch moves on (L4 slide 22, "degrade gracefully").
"""
import time
from typing import Any, Dict, List, Optional

from .config import PROMPT_VERSION, Settings
from .icp import load_scorecard
from .llm import LLMError
from .models import STEP_ORDER, CompanyProfile, Qualification, ScrapeResult, StepRecord, utcnow
from .scrape import Scraper

IMPLEMENTED_STEPS = ["scrape", "extract", "qualify"]
MAX_UNIT_RETRIES = 3


def _page_summary(p) -> Dict[str, Any]:
    return {"url": p.url, "kind": p.page_kind, "status": p.status_code, "words": p.words,
            "via": p.fetched_via, "error": p.error}


class Pipeline:
    def __init__(self, settings: Settings, store, scraper: Optional[Scraper] = None,
                 extractor=None, researcher=None):
        self.settings = settings
        self.store = store
        self.scraper = scraper or Scraper(delay=settings.scrape_delay, jina_fallback=settings.jina_fallback)
        self.extractor = extractor    # created lazily so `--until scrape` needs no API key
        self.researcher = researcher

    def _record(self, domain: str, step: str, status: str, started, **kw) -> StepRecord:
        rec = StepRecord(run_id=self.store.run_id, domain=domain, step=step, status=status,
                         started_at=started, **kw)
        self.store.write_step(rec)
        return rec

    @staticmethod
    def _retry_info(prev: Optional[StepRecord]) -> int:
        return int(((prev.output or {}).get("retries", 0)) if prev else 0)

    def _llm_failure(self, domain, step, started, e, prev, **kw) -> Dict[str, Any]:
        retries = self._retry_info(prev) + 1
        retry = isinstance(e, LLMError) and e.retryable and retries < MAX_UNIT_RETRIES
        out = dict(kw.pop("output", None) or {})
        out["retries"] = retries
        self._record(domain, step, "error", started, prompt_version=PROMPT_VERSION, output=out,
                     error=f"{type(e).__name__}: {e}" + (" (will retry)" if retry else ""), **kw)
        return {"stage": step, "done": not retry, "retry": retry, "message": str(e)}

    # ------------------------------------------------------------------ one unit of work

    def advance(self, domain: str, until: str = "qualify") -> Dict[str, Any]:
        stop_at = STEP_ORDER.index(until)
        scrape_rec = self.store.read_step(domain, "scrape")

        # Step 1 - scrape (homepage only; the loop fetches more on demand)
        if scrape_rec is None:
            started = utcnow()
            scrape = self.scraper.scrape(domain)
            home = scrape.pages[0] if scrape.pages else None
            if not home or not home.text:
                reason = (home.error if home else None) or "empty page"
                self._record(domain, "scrape", "error", started, inputs={"domain": domain},
                             output=scrape.model_dump(mode="json"),
                             error=f"homepage unreadable ({reason}); skipped, not retried around a block")
                return {"stage": "scrape", "done": True, "message": f"homepage unreadable ({reason})"}
            self._record(domain, "scrape", "ok", started, inputs={"domain": domain},
                         output=scrape.model_dump(mode="json"),
                         note=f"homepage {home.words} words via {home.fetched_via}; links found: "
                              f"{', '.join(sorted(scrape.links)) or 'none'}")
            return {"stage": "scrape", "done": stop_at == 0, "message": f"homepage {home.words} words"}
        if scrape_rec.status != "ok" or stop_at == 0:
            return {"stage": "scrape", "done": True, "message": scrape_rec.note or scrape_rec.error}
        scrape = ScrapeResult.model_validate(scrape_rec.output)
        home = scrape.pages[0]

        # Step 2 - extract (homepage)
        ext_rec = self.store.read_step(domain, "extract")
        if ext_rec is None or ext_rec.status == "error":
            if ext_rec is not None and self._retry_info(ext_rec) >= MAX_UNIT_RETRIES:
                return {"stage": "extract", "done": True, "message": ext_rec.error}
            started = utcnow()
            try:
                profile, report = self.extractor.extract(scrape)
            except Exception as e:
                return self._llm_failure(domain, "extract", started, e, ext_rec, inputs={"pages": [home.url]})
            self._record(domain, "extract", "ok", started, model=report["llm"]["model"],
                         prompt_version=PROMPT_VERSION, inputs={"pages": [home.url]},
                         output={"profile": profile.model_dump(mode="json"), "report": report},
                         note=f"{len(report['facts_found'])}/{len(report['facts_found']) + len(report['facts_missing'])} "
                              f"facts from the homepage, {len(report['dropped_unverified'])} unverified claim(s) dropped")
            return {"stage": "extract", "done": stop_at == 1,
                    "message": f"{len(report['facts_found'])} facts from the homepage"}
        if stop_at == 1:
            return {"stage": "extract", "done": True, "message": ext_rec.note}
        profile = CompanyProfile.model_validate(ext_rec.output["profile"])

        # Step 3 - qualify: start, one loop fetch per call, then final scoring
        from .research import LoopState
        q_rec = self.store.read_step(domain, "qualify")
        if q_rec is not None and q_rec.status == "ok":
            return {"stage": "qualify", "done": True, "message": q_rec.note}
        if q_rec is not None and q_rec.status == "error" and self._retry_info(q_rec) >= MAX_UNIT_RETRIES:
            return {"stage": "qualify", "done": True, "message": q_rec.error}
        state_json = (q_rec.output or {}).get("state") if q_rec else None
        st = LoopState.model_validate(state_json) if state_json else self.researcher.start(scrape, profile)
        started = utcnow()
        inputs = {"fetch_cap": self.researcher.max_fetches}

        if not st.done_fetching:
            try:
                did = self.researcher.step(scrape, st)
            except Exception as e:
                return self._llm_failure(domain, "qualify", started, e, q_rec, inputs=inputs,
                                         output={"state": st.model_dump(mode="json")})
            msg = (f"fetch {len(st.steps)}: {st.steps[-1].question} -> {st.steps[-1].page_kind}: "
                   f"{st.steps[-1].result_summary}") if did else "research done, scoring next"
            self._record(domain, "qualify", "stopped", started, prompt_version=PROMPT_VERSION, inputs=inputs,
                         output={"state": st.model_dump(mode="json")},
                         note=f"in progress: {len(st.steps)}/{self.researcher.max_fetches} fetches")
            return {"stage": "research", "done": False, "message": msg}

        try:
            res = self.researcher.finish(scrape, st)
        except Exception as e:
            return self._llm_failure(domain, "qualify", started, e, q_rec, inputs=inputs,
                                     output={"state": st.model_dump(mode="json")})
        q = res["qualification"]
        self._record(domain, "qualify", "ok", started, model=res["llm_calls"][-1]["model"],
                     prompt_version=PROMPT_VERSION, inputs=inputs,
                     output={"qualification": q.model_dump(mode="json"),
                             "profile": res["profile"].model_dump(mode="json"),
                             "pages": [_page_summary(p) for p in res["pages"]],
                             "page_text": {p.url: p.text for p in res["pages"] if p.text},
                             "llm_calls": res["llm_calls"], "downgraded": res["downgraded"]},
                     note=f"{q.decision} (score {q.weighted_score}) after {res['fetches_used']}/{res['fetch_cap']} "
                          f"fetches" + (f"; stopped: {q.short_circuit}" if q.short_circuit else ""))
        return {"stage": "qualify", "done": True, "message": f"{q.decision} (score {q.weighted_score})",
                "decision": q.decision}

    # ------------------------------------------------------------------ whole domain

    def run_domain(self, domain: str, until: str = "qualify", retry_wait: float = 5.0,
                   max_units: int = 30) -> Dict[str, Any]:
        for _ in range(max_units):
            r = self.advance(domain, until)
            if r["done"]:
                break
            if r.get("retry"):
                time.sleep(retry_wait)
        return self.summary(domain)

    def summary(self, domain: str) -> Dict[str, Any]:
        out: Dict[str, Any] = {"domain": domain, "steps": {}}
        for step in self.store.completed_steps(domain):
            rec = self.store.read_step(domain, step)
            out["steps"][step] = (f"error: {rec.error}" if rec.status == "error" else rec.note or rec.status)
            if step == "extract" and rec.status == "ok":
                out["profile"] = CompanyProfile.model_validate(rec.output["profile"])
            if step == "qualify" and rec.status == "ok":
                out["profile"] = CompanyProfile.model_validate(rec.output["profile"])
                out["qualification"] = Qualification.model_validate(rec.output["qualification"])
        return out

    def run(self, domains: List[str], until: str = "qualify") -> List[Dict[str, Any]]:
        return [self.run_domain(d, until) for d in domains]


def build_pipeline(settings: Settings, store, until: str = "qualify", client=None) -> Pipeline:
    """Wire the real components. Raises if the LLM client cannot be created."""
    scraper = Scraper(delay=settings.scrape_delay, jina_fallback=settings.jina_fallback)
    extractor = researcher = None
    if until != "scrape":
        from .extract import Extractor
        from .llm import make_llm
        from .research import Researcher
        extractor = Extractor(make_llm(settings, "extract", client=client))
        researcher = Researcher(load_scorecard(settings.icp_path), scraper, extractor,
                                make_llm(settings, "qualify", client=client), max_fetches=settings.agent_max_rounds)
    return Pipeline(settings, store, scraper=scraper, extractor=extractor, researcher=researcher)
