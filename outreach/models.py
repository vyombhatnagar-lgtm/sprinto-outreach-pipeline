"""Typed contracts for every pipeline step.

Each step consumes and produces one of these models, and the trace store
writes them verbatim to disk. Evidence (source URL + verbatim quote) is a
first-class field wherever the AI makes a claim, so every decision can be
traced back to something a human can open and read.

Kept Python 3.9-compatible (typing.Optional/List rather than `X | None`).
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Evidence(BaseModel):
    source_url: str
    quote: str = Field(description="Verbatim snippet from the source, not a paraphrase")
    source_type: Literal["website", "careers", "trust_page", "news", "web_search", "hunter", "manual"] = "website"


# ---------- Step 1: scrape ----------

class RawPage(BaseModel):
    url: str
    page_kind: Literal["home", "about", "product", "careers", "security", "pricing", "customers", "news", "other"]
    status_code: Optional[int] = None
    text: str = ""
    error: Optional[str] = None
    fetched_via: Literal["http", "jina_reader", "ats_api", "news_rss"] = "http"
    words: int = 0
    fetched_at: datetime = Field(default_factory=utcnow)


class ScrapeResult(BaseModel):
    domain: str
    pages: List[RawPage] = []
    links: Dict[str, str] = Field(default_factory=dict, description="page kind -> best link found on the homepage")
    ats: Optional[List[str]] = Field(None, description="[ats name, board slug] if the site links a job board")


# ---------- Step 2: extract ----------

class ExtractedFact(BaseModel):
    """A value plus where it came from. value=None means 'not found', never a guess."""
    value: Optional[Any] = None
    evidence: List[Evidence] = []


class CompanyProfile(BaseModel):
    domain: str
    company_name: ExtractedFact = ExtractedFact()
    one_liner: ExtractedFact = ExtractedFact()
    is_saas: ExtractedFact = ExtractedFact()
    funding_stage: ExtractedFact = ExtractedFact()
    employee_count: ExtractedFact = ExtractedFact()
    certifications_claimed: ExtractedFact = ExtractedFact()
    certification_status: ExtractedFact = ExtractedFact()
    compliance_job_postings: ExtractedFact = ExtractedFact()
    enterprise_signals: ExtractedFact = ExtractedFact()
    security_news: ExtractedFact = ExtractedFact()
    target_customers: ExtractedFact = ExtractedFact()


# ---------- Step 3: qualify (+ agent loop) ----------

CriterionStatus = Literal["met", "partial", "not_met", "unknown"]


class CriterionScore(BaseModel):
    criterion_id: str
    status: CriterionStatus
    reason: str
    evidence: List[Evidence] = []


class AgentStep(BaseModel):
    """One fetch of the research loop: which question was open, which page it fetched, what it filled."""
    round: int
    question: str
    missing_fields: List[str]
    page_kind: str
    urls: List[str] = []
    result_summary: str
    fields_filled: List[str] = []


Verdict = Literal["GO", "GO_FLAGGED", "NO_GO", "MANUAL_REVIEW"]


class Qualification(BaseModel):
    domain: str
    scores: List[CriterionScore]
    weighted_score: float
    unknown_weight_share: float
    decision: Verdict
    decision_rule: str = Field(description="Human-readable rule that produced the decision")
    flags: List[str] = Field(default_factory=list, description="What a human should double-check")
    short_circuit: Optional[str] = None
    unanswered_questions: List[str] = []
    agent_steps: List[AgentStep] = []


# ---------- Step 4: point of contact ----------

class Contact(BaseModel):
    first_name: str
    last_name: Optional[str] = None
    position: Optional[str] = None
    email: Optional[str] = None
    confidence: Optional[int] = None
    linkedin: Optional[str] = None
    source: Literal["hunter", "apollo_manual"] = "hunter"


class PocSelection(BaseModel):
    domain: str
    chosen: Optional[Contact] = None
    candidates: List[Contact] = []
    ranking_rule: str
    reason: str


# ---------- Step 5: pain points ----------

class PainPoint(BaseModel):
    title: str
    why_this_person: str
    sprinto_answer: str
    evidence: List[Evidence] = []


class PainPoints(BaseModel):
    domain: str
    contact_name: str
    pains: List[PainPoint] = Field(min_length=2, max_length=2)


# ---------- Step 6: draft ----------

class EmailDraft(BaseModel):
    domain: str
    to_name: str
    intended_address: Optional[str] = Field(None, description="PoC's real address, recorded only - never sent to")
    subject: str
    body: str
    hook: str
    hook_evidence: List[Evidence] = []
    pain_coverage: Dict[str, str] = Field(default_factory=dict, description="pain title -> sentence that addresses it")


# ---------- Step 7: send ----------

class SendResult(BaseModel):
    domain: str
    sent: bool
    recipient: str
    mode: str
    message_id: Optional[str] = None
    thread_id: Optional[str] = Field(None, description="Kept for the post-send workflow (reply handling)")
    error: Optional[str] = None
    sent_at: datetime = Field(default_factory=utcnow)


# ---------- Trace envelope ----------

StepName = Literal["scrape", "extract", "qualify", "poc", "pains", "draft", "send"]
STEP_ORDER: List[str] = ["scrape", "extract", "qualify", "poc", "pains", "draft", "send"]


class StepRecord(BaseModel):
    """What goes to disk for every step: inputs, output, and how it was produced."""
    run_id: str
    domain: str
    step: StepName
    status: Literal["ok", "skipped", "stopped", "error"]
    started_at: datetime
    finished_at: datetime = Field(default_factory=utcnow)
    model: Optional[str] = None
    prompt_version: Optional[str] = None
    inputs: Dict[str, Any] = Field(default_factory=dict)
    output: Optional[Dict[str, Any]] = None
    note: Optional[str] = None
    error: Optional[str] = None
