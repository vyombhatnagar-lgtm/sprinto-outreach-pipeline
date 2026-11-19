import dataclasses
"""Offline tests for steps 4-7: contact ranking, pain points, draft checks, send guard."""
import httpx
import pytest

from outreach.config import HARDCODED_RECIPIENT, load_settings
from outreach.extract import Extractor
from outreach.llm import LLMError
from outreach.messaging import Messenger, _Coverage, _Draft, _Pain, _Pains, check_draft
from outreach.models import Contact, PainPoints, PainPoint, SendResult
from outreach.pipeline import Pipeline
from outreach.poc import PocFinder, score_contact
from outreach.research import Researcher
from outreach.trace import TraceStore
from tests.test_phase1 import FakeLLM, scraper
from tests.test_phase2 import CARD, page_aware_extraction, qualifier

HUNTER = {"data": {"emails": [
    {"value": "sam@acme.io", "first_name": "Sam", "last_name": "Lee", "position": "Sales Manager",
     "seniority": "senior", "confidence": 99, "verification": {"status": "valid"}},
    {"value": "ana@acme.io", "first_name": "Ana", "last_name": "Ruiz", "position": "VP Engineering",
     "seniority": "executive", "confidence": 90, "verification": {"status": "valid"}},
    {"value": "kim@acme.io", "first_name": "Kim", "last_name": "Ito", "position": "Co-founder & CEO",
     "seniority": "executive", "confidence": 95},
    {"value": "x@acme.io", "first_name": None, "position": "Head of Security"},
]}}


def hunter(payload=HUNTER, status=200):
    return httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(status, json=payload)))


# ---- step 4 ----

def test_ranking_prefers_buyer_persona_over_nearest_manager():
    sel = PocFinder("k", load_settings().manual_pocs_path, http=hunter()).find("acme.io")
    assert sel.chosen.first_name == "Ana" and "engineering" in sel.reason
    assert "Sales Manager" not in sel.reason


def test_security_owner_beats_cto():
    sec = Contact(first_name="Lia", position="Head of Security & Compliance", confidence=70)
    cto = Contact(first_name="Max", position="CTO", confidence=99)
    assert score_contact(sec)[0] > score_contact(cto, "executive", True)[0]


def test_no_persona_falls_back_to_manual_apollo(monkeypatch):
    monkeypatch.setenv("MANUAL_POCS_JSON", '{"acme.io": {"first_name": "Jo", "position": "CTO", "email": "jo@acme.io"}}')
    sel = PocFinder("k", load_settings().manual_pocs_path, http=hunter({"data": {"emails": []}})).find("acme.io")
    assert sel.chosen.first_name == "Jo" and sel.chosen.source == "apollo_manual"


def test_hunter_quota_and_no_fallback_means_no_contact(monkeypatch):
    monkeypatch.delenv("MANUAL_POCS_JSON", raising=False)
    sel = PocFinder("k", load_settings().manual_pocs_path, http=hunter({}, 429)).find("nobody.io")
    assert sel.chosen is None and "quota" in sel.reason


# ---- steps 5-6 ----

ANA = Contact(first_name="Ana", last_name="Ruiz", position="VP Engineering", email="ana@acme.io")


def pains_out(fields=("certifications_claimed",)):
    return _Pains(pains=[_Pain(title=f"Pain {i}", why_this_person="w", sprinto_answer="a",
                               supporting_fields=list(fields)) for i in range(2)])


BODY = ("Hi Ana,\n\nI saw your trust page says the SOC 2 Type II audit is in progress.\n\n"
        "Evidence collection for a first audit usually lands on engineering and eats sprint time. "
        "Enterprise buyers also send security questionnaires before they sign, and those slow deals down.\n\n"
        "Sprinto connects to your cloud, collects that evidence continuously and keeps questionnaire answers ready.\n\n"
        "Would a 15-minute call next week be useful to compare notes on your audit plan?\n\n"
        "Best,\nThe Sprinto team")


def draft_out(body=BODY, hook_field="certifications_claimed"):
    return _Draft(subject="Your SOC 2 audit in progress", body=body, hook="SOC 2 Type II audit in progress",
                  hook_field=hook_field, pain_coverage=[
                      _Coverage(pain_title="Pain 0", sentence="Evidence collection for a first audit usually lands on engineering"),
                      _Coverage(pain_title="Pain 1", sentence="Enterprise buyers also send security questionnaires")])


def profile_and_qual():
    sc = scraper()
    ex = Extractor(FakeLLM(page_aware_extraction))
    res = sc.scrape("acme.io")
    prof, _ = ex.extract(res)
    out = Researcher(CARD, sc, ex, qualifier()).research(res, prof)
    return out["profile"], out["qualification"]


def test_pains_need_evidence():
    prof, qual = profile_and_qual()
    pains, _ = Messenger(FakeLLM(pains_out())).pains(prof, qual, ANA)
    assert len(pains.pains) == 2 and pains.pains[0].evidence[0].source_url == "https://acme.io/trust"
    with pytest.raises(LLMError) as e:
        Messenger(FakeLLM(pains_out(("security_news",)))).pains(prof, qual, ANA)
    assert e.value.retryable


def test_draft_checks():
    prof, _ = profile_and_qual()
    pp = PainPoints(domain="acme.io", contact_name="Ana", pains=[PainPoint(title=f"Pain {i}", why_this_person="w",
                                                                             sprinto_answer="a") for i in range(2)])
    checks = {c["check"]: c["severity"] for c in check_draft(draft_out(), ANA, prof, pp)}
    assert set(checks.values()) == {"pass"}
    bad = {c["check"]: c["severity"] for c in check_draft(draft_out(body="Hello [Name], ..."), ANA, prof, pp)}
    assert bad["greets the contact by first name"] == "fail" and bad["no placeholders"] == "fail"
    with pytest.raises(LLMError):
        Messenger(FakeLLM(draft_out(hook_field="security_news"))).draft(prof, ANA, pp)


# ---- full pipeline to send ----

class Seq(FakeLLM):
    """Returns qualifier scores, then pains, then the draft, by output model."""
    def __init__(self):
        super().__init__(None)

    def structured(self, **kw):
        self.calls.append(kw)
        name = kw["output_model"].__name__
        out = {"_Scores": qualifier().out(kw), "_Pains": pains_out(), "_Draft": draft_out()}[name]
        return out, {"model": "fake", "stop_reason": "end_turn"}


def full_pipe(tmp_path, sender):
    store = TraceStore(tmp_path)
    store.write_manifest(["acme.io"], {})
    sc = scraper()
    ex = Extractor(FakeLLM(page_aware_extraction))
    llm = Seq()
    return Pipeline(load_settings(), store, scraper=sc, extractor=ex, researcher=Researcher(CARD, sc, ex, llm),
                    poc_finder=PocFinder("k", load_settings().manual_pocs_path, http=hunter()),
                    messenger=Messenger(llm), sender=sender), store


def test_end_to_end_sends_once_to_hardcoded_inbox(tmp_path):
    sent = []

    def sender(subject, body, domain):
        sent.append((subject, body, domain))
        return SendResult(domain=domain, sent=True, recipient=HARDCODED_RECIPIENT, mode="fake", message_id="m1")
    pipe, store = full_pipe(tmp_path, sender)
    res = pipe.run_domain("acme.io")
    assert store.completed_steps("acme.io") == ["scrape", "extract", "qualify", "poc", "pains", "draft", "send"]
    assert len(sent) == 1 and sent[0][1].startswith("Hi Ana,") and "intended for Ana Ruiz" in sent[0][1]
    assert res["draft"]["intended_address"] == "ana@acme.io"
    pipe.advance("acme.io")                     # running again never re-sends
    assert len(sent) == 1


def test_no_go_spends_no_hunter_search(tmp_path):
    calls = []

    def hunter_spy(req):
        calls.append(req)
        return httpx.Response(200, json=HUNTER)
    store = TraceStore(tmp_path)
    store.write_manifest(["acme.io"], {})
    sc = scraper()
    ex = Extractor(FakeLLM(page_aware_extraction))
    pipe = Pipeline(load_settings(), store, scraper=sc, extractor=ex,
                    researcher=Researcher(CARD, sc, ex, qualifier({"is_saas": "not_met"})),
                    poc_finder=PocFinder("k", load_settings().manual_pocs_path,
                                         http=httpx.Client(transport=httpx.MockTransport(hunter_spy))))
    pipe.run_domain("acme.io")
    assert calls == [] and "poc" not in store.completed_steps("acme.io")


def test_unconfigured_gmail_keeps_the_draft_and_skips_send(tmp_path, monkeypatch):
    monkeypatch.delenv("GMAIL_TOKEN_JSON", raising=False)
    pipe, store = full_pipe(tmp_path, None)
    pipe.settings = dataclasses.replace(load_settings(), secrets_dir=tmp_path / "no-secrets")
    pipe.run_domain("acme.io")
    assert store.read_step("acme.io", "send").status == "skipped"
    assert store.read_step("acme.io", "draft").status == "ok"


def test_gemini_schema_keeps_a_field_named_title():
    from outreach.llm import gemini_schema
    from outreach.messaging import _Draft, _Pains
    item = gemini_schema(_Pains)["properties"]["pains"]["items"]
    assert "title" in item["properties"] and set(item["required"]) <= set(item["properties"])
    assert "title" not in gemini_schema(_Draft)  # the model-level label is still dropped


def test_shape_body_puts_greeting_and_signoff_on_their_own_lines():
    from outreach.messaging import shape_body
    out = shape_body("Hi Ana, I saw X. Pain one. Pain two. Sprinto helps. Call? Best, The Sprinto team", "Ana",
                     "The Sprinto team")
    assert out.startswith("Hi Ana,\n\nI saw X.") and out.endswith("Call?\n\nBest,\nThe Sprinto team")
    assert shape_body("Hi Ana,\n\nBody.\n\nThe Sprinto team", "Ana", "The Sprinto team") == "Hi Ana,\n\nBody.\n\nThe Sprinto team"


def test_draft_checks_flag_guesses_one_block_and_unsupported_hook():
    prof, _ = profile_and_qual()
    pp = PainPoints(domain="acme.io", contact_name="Ana", pains=[PainPoint(title=f"Pain {i}", why_this_person="w",
                                                                             sprinto_answer="a") for i in range(2)])
    bad = draft_out(body=BODY.replace("usually lands", "is likely landing").replace("\n\n", " "))
    bad.hook = "password protection and custom roles for teams"
    checks = {c["check"]: c["severity"] for c in check_draft(bad, ANA, prof, pp)}
    assert checks["no guesses stated as fact"] == "warn"
    assert checks["split into paragraphs"] == "warn"
    assert checks["hook matches its evidence"] == "warn"
