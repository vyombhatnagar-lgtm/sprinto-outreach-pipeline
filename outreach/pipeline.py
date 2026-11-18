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

IMPLEMENTED_STEPS = ["scrape", "extract", "qualify", "poc", "pains", "draft", "send"]
OUTREACH_DECISIONS = ("GO", "GO_FLAGGED")
MAX_UNIT_RETRIES = 3


def _page_summary(p) -> Dict[str, Any]:
    return {"url": p.url, "kind": p.page_kind, "status": p.status_code, "words": p.words,
            "via": p.fetched_via, "error": p.error}


class Pipeline:
    def __init__(self, settings: Settings, store, scraper: Optional[Scraper] = None,
                 extractor=None, researcher=None, poc_finder=None, messenger=None, sender=None):
        self.settings = settings
        self.store = store
        self.scraper = scraper or Scraper(delay=settings.scrape_delay, jina_fallback=settings.jina_fallback)
        self.extractor = extractor    # created lazily so `--until scrape` needs no API key
        self.researcher = researcher
        self.poc_finder = poc_finder
        self.messenger = messenger
        self.sender = sender          # callable(subject, body, domain) -> SendResult; default: Gmail

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

    def advance(self, domain: str, until: str = "send") -> Dict[str, Any]:
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
            if stop_at == 2:
                return {"stage": "qualify", "done": True, "message": q_rec.note}
            return self._outreach(domain, stop_at, q_rec)
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
        return {"stage": "qualify", "done": stop_at == 2 or q.decision not in OUTREACH_DECISIONS,
                "message": f"{q.decision} (score {q.weighted_score})", "decision": q.decision}

    # ------------------------------------------------------------------ steps 4-7

    def _outreach(self, domain: str, stop_at: int, q_rec: StepRecord) -> Dict[str, Any]:
        from .messaging import send_footer
        from .models import Contact, EmailDraft, PainPoints, PocSelection
        qual = Qualification.model_validate(q_rec.output["qualification"])
        profile = CompanyProfile.model_validate(q_rec.output["profile"])
        if qual.decision not in OUTREACH_DECISIONS:
            return {"stage": "qualify", "done": True, "message": f"{qual.decision}: no outreach"}

        # Step 4 - point of contact (deterministic ranking, no model)
        poc_rec = self.store.read_step(domain, "poc")
        if poc_rec is None:
            started = utcnow()
            sel = self.poc_finder.find(domain)
            self._record(domain, "poc", "ok" if sel.chosen else "stopped", started,
                         inputs={"source": "hunter domain-search, then manual Apollo list"},
                         output=sel.model_dump(mode="json"), note=sel.reason)
            return {"stage": "poc", "done": sel.chosen is None or stop_at == 3, "message": sel.reason}
        if poc_rec.status != "ok" or stop_at == 3:
            return {"stage": "poc", "done": True, "message": poc_rec.note}
        contact = Contact.model_validate(poc_rec.output["chosen"])

        # Step 5 - two pain points
        pains_rec = self.store.read_step(domain, "pains")
        if pains_rec is None or pains_rec.status == "error":
            if pains_rec is not None and self._retry_info(pains_rec) >= MAX_UNIT_RETRIES:
                return {"stage": "pains", "done": True, "message": pains_rec.error}
            started = utcnow()
            try:
                pains, report = self.messenger.pains(profile, qual, contact)
            except Exception as e:
                return self._llm_failure(domain, "pains", started, e, pains_rec)
            self._record(domain, "pains", "ok", started, model=report["llm"]["model"], prompt_version=PROMPT_VERSION,
                         inputs={"contact": contact.model_dump(mode="json")},
                         output={"pains": pains.model_dump(mode="json"), "report": report},
                         note="; ".join(p.title for p in pains.pains))
            return {"stage": "pains", "done": stop_at == 4, "message": "; ".join(p.title for p in pains.pains)}
        if stop_at == 4:
            return {"stage": "pains", "done": True, "message": pains_rec.note}
        pains = PainPoints.model_validate(pains_rec.output["pains"])

        # Step 6 - draft
        draft_rec = self.store.read_step(domain, "draft")
        if draft_rec is None or draft_rec.status == "error":
            if draft_rec is not None and self._retry_info(draft_rec) >= MAX_UNIT_RETRIES:
                return {"stage": "draft", "done": True, "message": draft_rec.error}
            started = utcnow()
            try:
                draft, report = self.messenger.draft(profile, contact, pains)
            except Exception as e:
                return self._llm_failure(domain, "draft", started, e, draft_rec)
            warns = [c["check"] for c in report["checks"] if c["severity"] == "warn"]
            self._record(domain, "draft", "ok", started, model=report["llm"]["model"], prompt_version=PROMPT_VERSION,
                         inputs={"contact": contact.first_name, "pains": [p.title for p in pains.pains]},
                         output={"draft": draft.model_dump(mode="json"), "report": report},
                         note=f"subject: {draft.subject}" + (f"; warnings: {warns}" if warns else ""))
            return {"stage": "draft", "done": stop_at == 5, "message": f"subject: {draft.subject}"}
        if stop_at == 5:
            return {"stage": "draft", "done": True, "message": draft_rec.note}
        draft = EmailDraft.model_validate(draft_rec.output["draft"])

        # Step 7 - send (to the hardcoded recipient only; never twice)
        send_rec = self.store.read_step(domain, "send")
        if send_rec is not None and send_rec.status == "ok":
            return {"stage": "send", "done": True, "message": send_rec.note}
        started = utcnow()
        if self.settings.review_before_send:
            self._record(domain, "send", "skipped", started, note="REVIEW_BEFORE_SEND=true: draft held for review")
            return {"stage": "send", "done": True, "message": "held for review"}
        if self.sender is None and not self.settings.gmail_ready:
            self._record(domain, "send", "skipped", started,
                         note="Gmail is not configured (GMAIL_TOKEN_JSON or SMTP app password); draft ready, not sent")
            return {"stage": "send", "done": True, "message": "draft ready; Gmail not configured, not sent"}
        send = self.sender or self._gmail_send
        res = send(draft.subject, draft.body + send_footer(draft, contact), domain)
        self._record(domain, "send", "ok" if res.sent else "error", started,
                     inputs={"subject": draft.subject, "intended_for": draft.to_name},
                     output=res.model_dump(mode="json"), error=res.error,
                     note=f"sent to {res.recipient} ({res.mode})" if res.sent else None)
        return {"stage": "send", "done": True,
                "message": f"sent to {res.recipient}" if res.sent else f"send failed: {res.error}"}

    def _gmail_send(self, subject: str, body: str, domain: str):
        from .gmail_client import send_email
        return send_email(self.settings, subject, body, domain=domain)

    # ------------------------------------------------------------------ whole domain

    def run_domain(self, domain: str, until: str = "send", retry_wait: float = 5.0,
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
            if step == "draft" and rec.status == "ok":
                out["draft"] = rec.output["draft"]
        return out

    def run(self, domains: List[str], until: str = "send") -> List[Dict[str, Any]]:
        return [self.run_domain(d, until) for d in domains]


def build_pipeline(settings: Settings, store, until: str = "send", client=None) -> Pipeline:
    """Wire the real components. Raises if the LLM client cannot be created."""
    scraper = Scraper(delay=settings.scrape_delay, jina_fallback=settings.jina_fallback)
    extractor = researcher = messenger = None
    if until != "scrape":
        from .extract import Extractor
        from .llm import make_llm
        from .messaging import Messenger
        from .research import Researcher
        extractor = Extractor(make_llm(settings, "extract", client=client))
        qualify_llm = make_llm(settings, "qualify", client=client)
        researcher = Researcher(load_scorecard(settings.icp_path), scraper, extractor,
                                qualify_llm, max_fetches=settings.agent_max_rounds)
        messenger = Messenger(qualify_llm)
    from .poc import PocFinder
    return Pipeline(settings, store, scraper=scraper, extractor=extractor, researcher=researcher,
                    poc_finder=PocFinder(settings.hunter_api_key, settings.manual_pocs_path), messenger=messenger)
