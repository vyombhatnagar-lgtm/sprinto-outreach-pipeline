"""Offline tests for steps 1-2: a fake website and a fake LLM, no network."""
import json

import httpx

from outreach.config import load_settings
from outreach.extract import Extractor, _Extraction, _Fact, _Quote, build_user_prompt, merge
from outreach.models import CompanyProfile, ExtractedFact, RawPage, ScrapeResult
from outreach.pipeline import Pipeline
from outreach.scrape import Scraper, clean_text, find_ats, find_links
from outreach.trace import TraceStore

FILLER = "\n".join(f"Line {i}: our team ships reliable invoice tooling for finance teams around the world." for i in range(30))

HOME = f"""<html><body>
<nav><a href="/company/about-us">About</a> <a href="https://acme.io/careers">Careers</a>
<a href="/trust">Trust Center</a> <a href="https://twitter.com/acme">Twitter</a></nav>
<main><h1>Acme is the cloud platform for invoice automation</h1>
<p>Acme is a SaaS platform trusted by finance teams. Enterprise plan includes SSO and SAML.</p>
<p>{FILLER}</p></main></body></html>"""
ABOUT = f"<html><body><main><p>We raised a $30M Series B in 2025. We are 180 employees across three offices.</p><p>{FILLER}</p></main></body></html>"
CAREERS = f'<html><body><main><p>Join us and help finance teams everywhere close their books faster.</p><p>{FILLER}</p><a href="https://boards.greenhouse.io/acme">See open roles</a></main></body></html>'
TRUST = f"<html><body><main><p>Our SOC 2 Type II audit is in progress and expected in Q1.</p><p>{FILLER}</p></main></body></html>"
GREENHOUSE = json.dumps({"jobs": [{"title": "GRC Manager"}, {"title": "Senior Backend Engineer"}]})

SITE = {
    "https://acme.io/robots.txt": (404, ""),
    "https://acme.io": (200, HOME),
    "https://acme.io/company/about-us": (200, ABOUT),
    "https://acme.io/careers": (200, CAREERS),
    "https://acme.io/trust": (200, TRUST),
    "https://boards-api.greenhouse.io/robots.txt": (404, ""),
    "https://boards-api.greenhouse.io/v1/boards/acme/jobs": (200, GREENHOUSE),
}


def make_fetch(site):
    calls = []

    def fetch(url):
        calls.append(url)
        status, body = site.get(url, (404, "not found"))
        return httpx.Response(status, text=body, request=httpx.Request("GET", url))
    fetch.calls = calls
    return fetch


fake_fetch = make_fetch(SITE)


def scraper(site=SITE, **kw):
    kw.setdefault("delay", 0)
    kw.setdefault("jina_fallback", False)
    return Scraper(fetch=make_fetch(site), **kw)


# ---- step 1: cleaning ----

def test_clean_text_drops_short_noise_and_duplicates_but_keeps_signals():
    raw = "Home\nPricing\nLogin\nSOC 2 Type II\nWe help finance teams automate every invoice they receive.\n" \
          "We help finance teams automate every invoice they receive.\nAccept cookies"
    out = clean_text(raw).split("\n")
    assert out == ["Pricing", "SOC 2 Type II", "We help finance teams automate every invoice they receive."]


# ---- step 1: homepage-only scrape ----

def test_find_links_picks_same_site_pages_only():
    links = find_links(HOME, "https://acme.io", "acme.io")
    assert links == {"about": "https://acme.io/company/about-us", "careers": "https://acme.io/careers",
                     "security": "https://acme.io/trust"}


def test_find_ats_greenhouse():
    assert find_ats(CAREERS) == ("greenhouse", "acme")


def test_scrape_reads_only_the_homepage():
    s = scraper()
    res = s.scrape("acme.io")
    assert [p.page_kind for p in res.pages] == ["home"]
    assert res.links["careers"] == "https://acme.io/careers"
    assert [u for u in s.fetch.calls if "robots" not in u] == ["https://acme.io"]


def test_fetch_kind_careers_adds_ats_roles():
    s = scraper()
    res = s.scrape("acme.io")
    pages = s.fetch_kind("acme.io", "careers", res.links, res.ats)
    ats = [p for p in pages if p.fetched_via == "ats_api"][0]
    assert "GRC Manager" in ats.text


def test_blocked_homepage_is_not_retried_elsewhere():
    s = scraper({"https://blocked.io/robots.txt": (404, ""), "https://blocked.io": (403, "no bots")})
    res = s.scrape("blocked.io")
    assert res.pages[0].error == "HTTP 403"
    assert not any("www.blocked.io" in u or u.startswith("http://") for u in s.fetch.calls)


def test_thin_page_is_reread_through_jina():
    site = dict(SITE)
    site["https://thin.io/robots.txt"] = (404, "")
    site["https://thin.io"] = (200, "<html><body><div id=root></div></body></html>")
    site["https://r.jina.ai/https://thin.io"] = (200, FILLER + "\nThin is a SaaS platform for HR teams.")
    s = scraper(site, jina_fallback=True)
    home = s.scrape("thin.io").pages[0]
    assert home.fetched_via == "jina_reader" and home.words > 200


def test_scrape_unreachable_site_returns_home_error():
    def down(url):
        raise httpx.ConnectError("boom")
    res = Scraper(fetch=down, delay=0, jina_fallback=False).scrape("nowhere.io")
    assert len(res.pages) == 1 and res.pages[0].error and not res.pages[0].text


def test_robots_disallow_is_respected():
    site = dict(SITE)
    site["https://acme.io/robots.txt"] = (200, "User-agent: *\nDisallow: /trust\n")
    s = scraper(site)
    res = s.scrape("acme.io")
    pages = s.fetch_kind("acme.io", "security", res.links)
    assert pages[0].error == "disallowed by robots.txt" and not pages[0].text


# ---- step 2 ----

def F(value=None, *quotes):
    return _Fact(value=value, quotes=[_Quote(url=u, quote=q) for u, q in quotes])


class FakeLLM:
    def __init__(self, out):
        self.out = out
        self.calls = []

    def structured(self, **kw):
        self.calls.append(kw)
        out = self.out(kw) if callable(self.out) else self.out
        return out, {"model": "fake-model", "stop_reason": "end_turn", "input_tokens": 1, "output_tokens": 1}


def empty_extraction(**fields):
    base = {f: F() for f in _Extraction.model_fields}
    base.update(fields)
    return _Extraction(**base)


def home_extraction():
    return empty_extraction(
        company_name=F("Acme", ("https://acme.io", "Acme is the cloud platform for invoice automation")),
        one_liner=F("Invoice automation SaaS", ("https://acme.io", "the cloud platform for invoice automation")),
        is_saas=F("yes", ("https://acme.io", "Acme is a SaaS platform trusted by finance teams")),
        enterprise_signals=F("SSO, SAML on enterprise plan",
                             ("https://acme.io", "Enterprise plan includes SSO and SAML")),
        # fabricated quote -> value must be dropped
        security_news=F("Breach in 2024", ("https://acme.io", "We disclosed a breach in 2024")),
        target_customers=F("finance teams", ("https://acme.io", "trusted by finance teams")),
    )


def test_extract_verifies_quotes_and_drops_unsupported_values():
    profile, report = Extractor(FakeLLM(home_extraction())).extract(scraper().scrape("acme.io"))
    assert profile.is_saas.value is True
    assert profile.enterprise_signals.evidence[0].source_url == "https://acme.io"
    assert profile.security_news.value is None
    assert {d["field"] for d in report["dropped_unverified"]} == {"security_news"}


def test_merge_fills_only_empty_fields():
    a = CompanyProfile(domain="x", company_name=ExtractedFact(value="A"))
    b = CompanyProfile(domain="x", company_name=ExtractedFact(value="B"), funding_stage=ExtractedFact(value="Series A"))
    assert merge(a, b) == ["funding_stage"] and a.company_name.value == "A"


def test_prompt_marks_pages_untrusted():
    prompt = build_user_prompt(ScrapeResult(domain="x.io", pages=[RawPage(url="https://x.io", page_kind="home", text="hi")]))
    assert '<untrusted_page url="https://x.io" kind="home">' in prompt


def test_llm_schema_is_strict():
    schema = _Extraction.model_json_schema()
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])
    fact = schema["$defs"]["_Fact"]
    assert fact["additionalProperties"] is False and set(fact["required"]) == {"value", "quotes"}


# ---- pipeline ----

def test_pipeline_writes_trace_for_steps_1_and_2(tmp_path):
    store = TraceStore(tmp_path)
    pipe = Pipeline(load_settings(), store, scraper=scraper(), extractor=Extractor(FakeLLM(home_extraction())))
    res = pipe.run_domain("acme.io", until="extract")
    assert store.completed_steps("acme.io") == ["scrape", "extract"]
    rec = store.read_step("acme.io", "extract")
    assert rec.status == "ok" and rec.model == "fake-model" and rec.prompt_version
    assert res["profile"].company_name.value == "Acme"


def test_pipeline_records_unreachable_site_and_stops(tmp_path):
    store = TraceStore(tmp_path)

    def down(url):
        raise httpx.ConnectError("boom")
    res = Pipeline(load_settings(), store, scraper=Scraper(fetch=down, delay=0)).run_domain("nowhere.io")
    assert store.read_step("nowhere.io", "scrape").status == "error"
    assert store.completed_steps("nowhere.io") == ["scrape"]
    assert "error" in res["steps"]["scrape"]
