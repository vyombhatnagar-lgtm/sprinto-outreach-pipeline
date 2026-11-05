import pytest

from outreach.config import HARDCODED_RECIPIENT, load_settings
from outreach.domains import normalize_domain, normalize_domains
from outreach.gmail_client import RecipientGuardError, _guard, build_message
from outreach.icp import decide, load_scorecard
from outreach.models import CriterionScore, StepRecord, utcnow
from outreach.trace import TraceStore

CARD = load_scorecard(load_settings().icp_path)


def scores(**status):
    return [CriterionScore(criterion_id=c.id, status=status.get(c.id, "met"), reason="t") for c in CARD.criteria]


# ---- domains ----

@pytest.mark.parametrize("raw,expected", [
    ("Acme.io", "acme.io"),
    ("https://www.acme.io/pricing?x=1", "acme.io"),
    ("  app.acme.co.uk ", "app.acme.co.uk"),
])
def test_normalize_domain(raw, expected):
    assert normalize_domain(raw) == expected


def test_normalize_domains_dedupes_and_skips_comments():
    assert normalize_domains(["acme.io", "# note", "", "www.acme.io", "b.com # x"]) == ["acme.io", "b.com"]


def test_invalid_domain_rejected():
    with pytest.raises(ValueError):
        normalize_domain("not a domain")


# ---- ICP decision rule ----

def test_all_met_is_go():
    assert decide(CARD, scores()).decision == "GO"


def test_gate_not_met_is_no_go_even_with_high_score():
    assert decide(CARD, scores(is_saas="not_met")).decision == "NO_GO"
    assert decide(CARD, scores(certification_gap="not_met")).decision == "NO_GO"


def test_unknown_saas_goes_to_a_human():
    d = decide(CARD, scores(is_saas="unknown"))
    assert d.decision == "MANUAL_REVIEW" and d.flags


def test_unknown_certification_is_assumed_gap_and_flagged():
    d = decide(CARD, scores(certification_gap="unknown"))
    assert d.decision == "GO_FLAGGED" and d.weighted_score == 1.0
    assert any("certification_gap" in f for f in d.flags)


def test_unknown_stage_ranks_lower_and_flags():
    d = decide(CARD, scores(funding_stage="unknown"))
    assert d.decision == "GO_FLAGGED" and d.weighted_score == 0.8


def test_too_many_unknowns_hands_off():
    s = scores(funding_stage="unknown", compliance_hiring="unknown", enterprise_pressure="unknown")  # 55%
    assert decide(CARD, s).decision == "MANUAL_REVIEW"


def test_short_circuit_is_no_go():
    assert decide(CARD, scores(), short_circuit="not SaaS").decision == "NO_GO"


def test_low_score_is_no_go():
    s = scores(funding_stage="not_met", compliance_hiring="not_met", enterprise_pressure="not_met",
               security_news="not_met")
    assert decide(CARD, s).decision == "NO_GO"


def test_missing_criterion_raises():
    with pytest.raises(ValueError):
        decide(CARD, scores()[1:])


# ---- recipient guard ----

def test_message_always_goes_to_hardcoded_recipient():
    msg = build_message("me@example.com", "s", "b", domain="acme.io")
    assert msg["To"] == HARDCODED_RECIPIENT


def test_guard_blocks_tampered_recipient():
    msg = build_message("me@example.com", "s", "b")
    msg.replace_header("To", "prospect@acme.io")
    with pytest.raises(RecipientGuardError):
        _guard(msg)


def test_guard_blocks_bcc():
    msg = build_message("me@example.com", "s", "b")
    msg["Bcc"] = "someone@else.com"
    with pytest.raises(RecipientGuardError):
        _guard(msg)


# ---- trace store ----

def test_trace_roundtrip(tmp_path):
    store = TraceStore(tmp_path)
    store.write_manifest(["acme.io"], {})
    rec = StepRecord(run_id=store.run_id, domain="acme.io", step="qualify", status="ok",
                     started_at=utcnow(), output={"decision": "GO"})
    path = store.write_step(rec)
    assert path.name == "03_qualify.json"
    assert store.read_step("acme.io", "qualify").output == {"decision": "GO"}
    assert store.completed_steps("acme.io") == ["qualify"]
