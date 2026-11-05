"""Step 1 - scrape. A single-fetch scraper (L4, slide 14): narrowest scope, lowest cost.

`Scraper.scrape(domain)` reads only the homepage. It also records the best
link for each page kind, so the research loop (outreach/research.py) can later
fetch exactly one named page when a specific fact is missing, instead of
crawling everything up front.

Fetching (L4 slide 13): request-based first. If the cleaned text is thin
(< THIN_WORDS words, usually a JavaScript-rendered page), re-read it through
Jina Reader, which renders the page and returns text. A blocked request
(403/429, bot detection) is NOT retried through another service: the site's
owner asked for no automated traffic, so we log it and move on (slides 21-22).

Cleaning (slide 10): drop nav/footer/scripts, drop lines under 8 words unless
they carry a buying signal (e.g. "SOC 2 Type II"), drop duplicate lines, cap.
"""
import re
import time
from typing import Callable, Dict, List, Optional, Tuple
from urllib import robotparser
from urllib.parse import quote, urljoin, urlparse

import feedparser
import httpx
import trafilatura
from bs4 import BeautifulSoup

from .models import RawPage, ScrapeResult

USER_AGENT = "Mozilla/5.0 (compatible; OutreachResearchBot/0.2; +case-study)"
MAX_CHARS_PER_PAGE = 6000      # ~1,500 tokens; L4 slide 10 says cap around 2,000 tokens
THIN_WORDS = 200               # L4 slide 30: "fewer than 200 words - fetch it with a browser"
MIN_LINE_WORDS = 8             # L4 slide 7: "drop anything under eight words"
TIMEOUT = 15.0
JINA_READER = "https://r.jina.ai/"

# Short lines are kept when they carry one of these signals.
SIGNAL_WORDS = re.compile(
    r"soc ?2|iso ?27001|iso|gdpr|hipaa|pci|compliance|complian|security|trust|audit|certif|"
    r"series [a-e]|seed|raised|funding|employees|team of|enterprise|sso|saml|sla|"
    r"customers|trusted by|pricing|per month|/mo|plan|manager|engineer|head of|director|"
    r"grc|privacy|careers|hiring|open roles|saas|platform|software",
    re.I,
)

PAGE_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    "about": ("about", "company", "who-we-are", "our-story"),
    "product": ("product", "platform", "features", "how-it-works"),
    "careers": ("careers", "jobs", "join-us", "work-with-us", "open-positions"),
    "security": ("trust", "security", "compliance", "soc-2", "soc2", "iso"),
    "pricing": ("pricing", "plans"),
    "customers": ("customers", "case-studies", "case-study", "success-stories"),
}
COMMON_PATHS: Dict[str, Tuple[str, ...]] = {
    "about": ("/about", "/about-us", "/company"),
    "product": ("/product", "/platform", "/features"),
    "careers": ("/careers", "/jobs"),
    "security": ("/security", "/trust"),
    "pricing": ("/pricing",),
    "customers": ("/customers",),
}
ATS_PATTERNS = [
    ("greenhouse", re.compile(r"(?:boards|job-boards)\.greenhouse\.io/(?:embed/job_board\?for=)?([\w-]+)")),
    ("lever", re.compile(r"jobs\.lever\.co/([\w-]+)")),
    ("ashby", re.compile(r"jobs\.ashbyhq\.com/([\w.-]+)")),
]

Fetcher = Callable[[str], httpx.Response]


def clean_text(text: str) -> str:
    """Line-level cleaning rules from L4: short lines go unless they carry a signal; no duplicates."""
    seen = set()
    kept: List[str] = []
    for line in re.split(r"[\r\n]+", text):
        line = re.sub(r"[ \t]+", " ", line).strip(" |·-•\t")
        if not line:
            continue
        key = line.lower()
        if key in seen:
            continue
        if len(line.split()) < MIN_LINE_WORDS and not SIGNAL_WORDS.search(line):
            continue
        seen.add(key)
        kept.append(line)
    return "\n".join(kept)[:MAX_CHARS_PER_PAGE]


def html_to_text(html: str) -> str:
    """Heuristic extraction (L4 slide 13, option 2): main content region, nav and footers dropped."""
    text = trafilatura.extract(html, include_comments=False, include_tables=True, favor_recall=True)
    if not text or len(text) < 200:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "header", "form"]):
            tag.decompose()
        text = soup.get_text("\n", strip=True)
    return clean_text(text or "")


def word_count(text: str) -> int:
    return len(text.split())


def _same_site(url: str, domain: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host == domain or host.endswith("." + domain)


def _link_score(path: str, label: str, words: Tuple[str, ...]) -> float:
    """3 = last path segment is the keyword (/careers), 2 = a segment starts with it
    (/company/about-us) or the link text is exactly it. Deeper paths lose a little,
    so an index page (/customers) beats a single case study (/customers/deel)."""
    segments = [s for s in path.split("/") if s]
    best = 0.0
    for w in words:
        if segments and segments[-1] == w:
            best = max(best, 3.0)
        elif any(s.startswith(w) for s in segments):
            best = max(best, 2.0)
        if label == w.replace("-", " "):
            best = max(best, 2.0)
    return best - 0.1 * len(segments) if best else 0.0


def find_links(html: str, base_url: str, domain: str) -> Dict[str, str]:
    """Pick the best same-site link for each page kind from the homepage."""
    soup = BeautifulSoup(html, "html.parser")
    best: Dict[str, Tuple[float, str]] = {}
    for a in soup.find_all("a", href=True):
        url = urljoin(base_url, a["href"]).split("#", 1)[0].split("?", 1)[0]
        if not url.startswith("http") or not _same_site(url, domain):
            continue
        path = urlparse(url).path.lower()
        label = a.get_text(" ", strip=True).lower()
        for kind, words in PAGE_KEYWORDS.items():
            score = _link_score(path, label, words)
            if score >= 1.5 and score > best.get(kind, (0.0, ""))[0]:
                best[kind] = (score, url)
    return {kind: url for kind, (_, url) in best.items()}


def find_ats(html: str) -> Optional[Tuple[str, str]]:
    for name, pattern in ATS_PATTERNS:
        m = pattern.search(html)
        if m:
            return name, m.group(1)
    return None


def ats_jobs_url(ats: str, slug: str) -> str:
    return {
        "greenhouse": f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
        "lever": f"https://api.lever.co/v0/postings/{slug}?mode=json",
        "ashby": f"https://api.ashbyhq.com/posting-api/job-board/{slug}",
    }[ats]


def ats_titles(ats: str, payload) -> List[str]:
    if ats == "greenhouse":
        return [j.get("title", "") for j in payload.get("jobs", [])]
    if ats == "lever":
        return [j.get("text", "") for j in payload]
    if ats == "ashby":
        return [j.get("title", "") for j in payload.get("jobs", [])]
    return []


def news_rss_url(company: str) -> str:
    q = f'"{company}" (funding OR raises OR "Series" OR breach OR SOC 2 OR compliance)'
    return f"https://news.google.com/rss/search?q={quote(q)}&hl=en-US&gl=US&ceid=US:en"


class Scraper:
    def __init__(self, fetch: Optional[Fetcher] = None, respect_robots: bool = True,
                 delay: float = 1.0, jina_fallback: bool = True):
        self._client = None
        self.fetch = fetch or self._http_get
        self.respect_robots = respect_robots
        self.delay = delay                    # polite pause between requests to the same host
        self.jina_fallback = jina_fallback
        self._robots: Dict[str, Optional[robotparser.RobotFileParser]] = {}
        self._last_hit: Dict[str, float] = {}

    # ---- transport ----

    def _http_get(self, url: str) -> httpx.Response:
        if self._client is None:
            self._client = httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT,
                                        follow_redirects=True)
        return self._client.get(url)

    def _get(self, url: str) -> httpx.Response:
        host = urlparse(url).netloc
        wait = self.delay - (time.monotonic() - self._last_hit.get(host, -1e9))
        if wait > 0:
            time.sleep(wait)
        try:
            return self.fetch(url)
        finally:
            self._last_hit[host] = time.monotonic()

    def _allowed(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        origin = "{0.scheme}://{0.netloc}".format(urlparse(url))
        if origin not in self._robots:
            rp = robotparser.RobotFileParser()
            try:
                r = self._get(origin + "/robots.txt")
                rp.parse(r.text.splitlines() if r.status_code == 200 else [])
                self._robots[origin] = rp
            except Exception:
                self._robots[origin] = None  # unreachable robots.txt -> allowed
        rp = self._robots[origin]
        return rp is None or rp.can_fetch(USER_AGENT, url)

    def _get_page(self, url: str, kind: str) -> Tuple[RawPage, str]:
        if not self._allowed(url):
            return RawPage(url=url, page_kind=kind, error="disallowed by robots.txt"), ""
        try:
            r = self._get(url)
        except Exception as e:
            return RawPage(url=url, page_kind=kind, error=f"{type(e).__name__}: {e}"), ""
        html = r.text if r.status_code == 200 else ""
        final_url = str(r.url) if getattr(r, "url", None) else url
        text = html_to_text(html) if html else ""
        page = RawPage(url=final_url, page_kind=kind, status_code=r.status_code, text=text,
                       words=word_count(text),
                       error=None if r.status_code == 200 else f"HTTP {r.status_code}")
        if page.status_code == 200 and page.words < THIN_WORDS and self.jina_fallback:
            page = self._jina(page)
        return page, html

    def _jina(self, page: RawPage) -> RawPage:
        """Thin page (usually rendered by JavaScript): read it through a rendering service."""
        try:
            r = self._get(JINA_READER + page.url)
        except Exception:
            return page
        if r.status_code != 200:
            return page
        text = clean_text(r.text)
        if word_count(text) <= page.words:
            return page
        return page.model_copy(update={"text": text, "words": word_count(text), "fetched_via": "jina_reader"})

    # ---- step 1: homepage only ----

    def scrape(self, domain: str) -> ScrapeResult:
        result = ScrapeResult(domain=domain)
        home, home_html = None, ""
        for url in (f"https://{domain}", f"https://www.{domain}", f"http://{domain}"):
            home, home_html = self._get_page(url, "home")
            if home.status_code == 200 and home.text:
                break
            if home.status_code in (401, 403, 429):
                break  # blocked: respect it, don't hammer other variants
        result.pages.append(home)
        if home_html:
            result.links = find_links(home_html, home.url, domain)
            ats = find_ats(home_html)
            result.ats = list(ats) if ats else None
        return result

    # ---- used by the research loop: one named page at a time ----

    def fetch_kind(self, domain: str, kind: str, links: Dict[str, str],
                   ats: Optional[List[str]] = None, company: Optional[str] = None) -> List[RawPage]:
        """Fetch one page kind. Tries the homepage link first, then common paths.
        Returns every attempt that matters for the trace; the first page with text wins."""
        if kind == "news":
            return [self._news_page(company or domain)]
        candidates = ([links[kind]] if kind in links else []) + \
            [f"https://{domain}{p}" for p in COMMON_PATHS.get(kind, ())]
        pages: List[RawPage] = []
        tried = set()
        for url in candidates:
            if url.rstrip("/") in tried:
                continue
            tried.add(url.rstrip("/"))
            page, html = self._get_page(url, kind)
            if page.status_code == 200 and page.text:
                pages.append(page)
                if kind == "careers":
                    found = find_ats(html) or (tuple(ats) if ats else None)
                    if found:
                        pages.append(self._ats_page(*found))
                return pages
            if kind in links and url == links[kind]:
                pages.append(page)  # keep the failure of a linked page in the trace
        if kind == "careers" and ats:
            pages.append(self._ats_page(*ats))
        if not pages:
            pages.append(RawPage(url=candidates[0] if candidates else f"https://{domain}", page_kind=kind,
                                 error="no page found at linked or common paths"))
        return pages

    def _ats_page(self, ats: str, slug: str) -> RawPage:
        url = ats_jobs_url(ats, slug)
        try:
            r = self._get(url)
            if r.status_code != 200:
                return RawPage(url=url, page_kind="careers", status_code=r.status_code,
                               error=f"HTTP {r.status_code}", fetched_via="ats_api")
            titles = [t for t in ats_titles(ats, r.json()) if t]
            text = f"Open roles on {ats} job board ({len(titles)}):\n" + "\n".join(f"- {t}" for t in titles)
            text = text[:MAX_CHARS_PER_PAGE]
            return RawPage(url=url, page_kind="careers", status_code=200, text=text,
                           words=word_count(text), fetched_via="ats_api")
        except Exception as e:
            return RawPage(url=url, page_kind="careers", error=f"{type(e).__name__}: {e}", fetched_via="ats_api")

    def _news_page(self, company: str) -> RawPage:
        """Google News RSS (whiteboard: funding stage and negative news come from Google News)."""
        url = news_rss_url(company)
        try:
            r = self._get(url)
            if r.status_code != 200:
                return RawPage(url=url, page_kind="news", status_code=r.status_code,
                               error=f"HTTP {r.status_code}", fetched_via="news_rss")
            feed = feedparser.parse(r.text)
            lines = [f"{e.get('title', '').strip()} ({e.get('published', '')[:16]})"
                     for e in feed.entries[:15] if e.get("title")]
            text = f"Google News results for {company}:\n" + "\n".join(lines) if lines else ""
            return RawPage(url=url, page_kind="news", status_code=200, text=text[:MAX_CHARS_PER_PAGE],
                           words=word_count(text), fetched_via="news_rss",
                           error=None if lines else "no news results")
        except Exception as e:
            return RawPage(url=url, page_kind="news", error=f"{type(e).__name__}: {e}", fetched_via="news_rss")
