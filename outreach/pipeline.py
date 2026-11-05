"""Orchestrator: runs each domain through the steps, writing a trace record per step.

A failure on one domain is recorded and the batch moves on (L4 slide 22, "degrade
gracefully"), so a run over a list of domains never needs a human to intervene.
"""
from typing import Any, Dict, List, Optional

from .config import PROMPT_VERSION, Settings
from .icp import load_scorecard
from .models import STEP_ORDER, StepRecord, utcnow
from .scrape import Scraper

IMPLEMENTED_STEPS = ["scrape", "extract", "qualify"]


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

    def run_domain(self, domain: str, until: str = "qualify") -> Dict[str, Any]:
        stop_at = STEP_ORDER.index(until)
        summary: Dict[str, Any] = {"domain": domain, "steps": {}}

        # Step 1 - scrape (homepage only; the loop fetches more on demand)
        started = utcnow()
        scrape = self.scraper.scrape(domain)
        home = scrape.pages[0] if scrape.pages else None
        if not home or not home.text:
            reason = (home.error if home else None) or "empty page"
            self._record(domain, "scrape", "error", started, inputs={"domain": domain},
                         output=scrape.model_dump(mode="json"),
                         error=f"homepage unreadable ({reason}); skipped, not retried around a block")
            summary["steps"]["scrape"] = f"error: homepage unreadable ({reason})"
            return summary
        self._record(domain, "scrape", "ok", started, inputs={"domain": domain},
                     output=scrape.model_dump(mode="json"),
                     note=f"homepage {home.words} words via {home.fetched_via}; links found: "
                          f"{', '.join(sorted(scrape.links)) or 'none'}")
        summary["steps"]["scrape"] = f"homepage {home.words} words via {home.fetched_via}"
        if stop_at < STEP_ORDER.index("extract"):
            return summary

        # Step 2 - extract (homepage)
        started = utcnow()
        try:
            profile, report = self.extractor.extract(scrape)
        except Exception as e:
            self._record(domain, "extract", "error", started, model=self.settings.extract_model,
                         prompt_version=PROMPT_VERSION, inputs={"pages": [home.url]},
                         error=f"{type(e).__name__}: {e}")
            summary["steps"]["extract"] = f"error: {e}"
            return summary
        self._record(domain, "extract", "ok", started, model=report["llm"]["model"],
                     prompt_version=PROMPT_VERSION, inputs={"pages": [home.url]},
                     output={"profile": profile.model_dump(mode="json"), "report": report},
                     note=f"{len(report['facts_found'])}/{len(report['facts_found']) + len(report['facts_missing'])} "
                          f"facts from the homepage, {len(report['dropped_unverified'])} unverified claim(s) dropped")
        summary["steps"]["extract"] = f"{len(report['facts_found'])} facts from homepage"
        summary["profile"] = profile
        if stop_at < STEP_ORDER.index("qualify"):
            return summary

        # Step 3 - qualify (research loop + scorecard)
        started = utcnow()
        try:
            res = self.researcher.research(scrape, profile)
        except Exception as e:
            self._record(domain, "qualify", "error", started, model=self.settings.model,
                         prompt_version=PROMPT_VERSION, error=f"{type(e).__name__}: {e}")
            summary["steps"]["qualify"] = f"error: {e}"
            return summary
        q = res["qualification"]
        self._record(domain, "qualify", "ok", started, model=res["llm_calls"][-1]["model"],
                     prompt_version=PROMPT_VERSION,
                     inputs={"homepage_facts": report["facts_found"], "fetch_cap": res["fetch_cap"]},
                     output={"qualification": q.model_dump(mode="json"),
                             "profile": res["profile"].model_dump(mode="json"),
                             "pages": [_page_summary(p) for p in res["pages"]],
                             "page_text": {p.url: p.text for p in res["pages"] if p.text},
                             "llm_calls": res["llm_calls"], "downgraded": res["downgraded"]},
                     note=f"{q.decision} (score {q.weighted_score}) after {res['fetches_used']}/{res['fetch_cap']} "
                          f"fetches" + (f"; stopped: {q.short_circuit}" if q.short_circuit else ""))
        summary["steps"]["qualify"] = f"{q.decision} score={q.weighted_score} fetches={res['fetches_used']}"
        summary["profile"] = res["profile"]
        summary["qualification"] = q
        return summary

    def run(self, domains: List[str], until: str = "qualify") -> List[Dict[str, Any]]:
        return [self.run_domain(d, until) for d in domains]


def build_pipeline(settings: Settings, store, until: str = "qualify", client=None) -> Pipeline:
    """Wire the real components. Raises if the Anthropic client cannot be created."""
    scraper = Scraper(delay=settings.scrape_delay, jina_fallback=settings.jina_fallback)
    extractor = researcher = None
    if until != "scrape":
        from .extract import Extractor
        from .llm import LLM
        from .research import Researcher
        extractor = Extractor(LLM(settings, client=client, model=settings.extract_model))
        researcher = Researcher(load_scorecard(settings.icp_path), scraper, extractor,
                                LLM(settings, client=client), max_fetches=settings.agent_max_rounds)
    return Pipeline(settings, store, scraper=scraper, extractor=extractor, researcher=researcher)
