"""Dashboard numbers and themed pages."""
from outreach import web
from outreach.models import StepRecord, utcnow
from outreach.stats import summarize
from outreach.trace import TraceStore


def _rec(run, domain, step, status="ok", output=None):
    return StepRecord(run_id=run, domain=domain, step=step, status=status, started_at=utcnow(), output=output)


def _q(decision, score):
    return {"qualification": {"decision": decision, "weighted_score": score}}


def test_summarize_counts_verdicts_scores_and_drafts():
    recs = [_rec("r1", "a.io", "qualify", output=_q("GO", .7)), _rec("r1", "b.io", "qualify", output=_q("NO_GO", .1)),
            _rec("r1", "a.io", "poc", output={"chosen": {"first_name": "Ana"}}), _rec("r1", "a.io", "draft", output={}),
            _rec("r2", "c.io", "qualify", output=_q("MANUAL_REVIEW", .4)), _rec("r2", "c.io", "qualify", "error")]
    s = summarize(recs)
    assert (s["analysed"], s["go"], s["go_rate"], s["avg_score"], s["contacts"], s["drafts"]) == (3, 1, 33, 40, 1, 1)
    assert s["per_run"]["r1"] == {"GO": 1, "NO_GO": 1, "drafts": 1}


def test_file_store_outcome_records(tmp_path):
    st = TraceStore(tmp_path)
    st.write_manifest(["a.io"], {})
    st.write_step(_rec(st.run_id, "a.io", "qualify", output=_q("GO", .6)))
    st.write_step(_rec(st.run_id, "a.io", "scrape"))
    assert [r.step for r in st.outcome_records()] == ["qualify"]


def test_home_renders_numbers_and_sound_toggle():
    html = web.home([], True, ["qualify", "send"], stats=summarize([_rec("r", "a.io", "qualify", output=_q("GO", .7))]))
    assert 'data-count="1"' in html and 'id="mute"' in html and "Verdict mix" in html


def test_pg_store_outcome_records_one_query(tmp_path):
    import sqlite3
    from tests.test_phase2 import SqliteStore
    db = str(tmp_path / "t.db")
    st = SqliteStore(lambda: sqlite3.connect(db))
    st.write_manifest(["a.io"], {})
    st.write_step(_rec(st.run_id, "a.io", "qualify", output=_q("NO_GO", .1)))
    st.write_step(_rec(st.run_id, "a.io", "extract"))
    recs = st.outcome_records()
    assert [r.step for r in recs] == ["qualify"] and summarize(recs)["no_go"] == 1
