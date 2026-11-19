"""HTML for the dashboard (server-rendered, no build step). Every value is escaped.

Layout follows what a reviewer asks, in order: what was decided (overview), why
(verdict line + scorecard), who and what we'd send (outreach), and how we got
there (research loop, rule, raw trace).
"""
from datetime import datetime
from html import escape
from typing import Any, Dict, List, Optional

from .config import HARDCODED_RECIPIENT
from .models import STEP_ORDER

VERDICTS = ("GO", "GO_FLAGGED", "NO_GO", "MANUAL_REVIEW")
VERDICT_LABEL = {"GO": "Go", "GO_FLAGGED": "Go (flagged)", "NO_GO": "No go", "MANUAL_REVIEW": "Manual review"}
CRITERIA = {  # label, weight (mirrors config/icp.yaml; weight 0 = gate only)
    "is_saas": ("Is a SaaS company", "gate"),
    "certification_gap": ("Not yet SOC 2 / ISO 27001 certified", "gate · 25"),
    "funding_stage": ("Funding stage (Series A-C)", "20"),
    "employee_count": ("Team size", "10"),
    "compliance_hiring": ("Hiring for security / compliance", "20"),
    "enterprise_pressure": ("Selling to enterprise", "15"),
    "security_news": ("Security / compliance news", "10"),
}
STATUS_ICON = {"met": "✓", "partial": "◐", "not_met": "✕", "unknown": "?"}
GO_THRESHOLD = 55

CSS = """
:root{--bg:#f6f6f3;--panel:#fff;--sunk:#f1f0ec;--ink:#1c1c1a;--muted:#66655f;--line:#e3e2dc;--accent:#3651d4;
--go:#1f7a35;--go-bg:#e3f4e7;--gof:#8a5a00;--gof-bg:#fbf0d4;--no:#b42323;--no-bg:#fbe4e2;
--mr:#5b3bb8;--mr-bg:#ece6fb;--na:#5d5c57;--na-bg:#ecebe6;--focus:#3651d4}
@media (prefers-color-scheme:dark){:root{--bg:#121211;--panel:#1b1b19;--sunk:#232321;--ink:#ecebe6;--muted:#a3a29b;
--line:#32312e;--accent:#8fa2ff;--go:#6fdc8c;--go-bg:#16301d;--gof:#f5c451;--gof-bg:#33280e;--no:#ff8a80;--no-bg:#3a1714;
--mr:#bba6ff;--mr-bg:#261d40;--na:#b9b8b1;--na-bg:#2a2927;--focus:#8fa2ff}}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
main{max-width:1040px;margin:0 auto;padding:0 16px 72px}
a{color:var(--accent)}a:focus-visible,button:focus-visible,summary:focus-visible,textarea:focus-visible,select:focus-visible{outline:2px solid var(--focus);outline-offset:2px}
h1,h2,h3{line-height:1.25}h2{font-size:18px;margin:0}h3{font-size:12px;margin:22px 0 8px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}
code{font:13px ui-monospace,Menlo,monospace;overflow-wrap:anywhere}.muted{color:var(--muted)}.small{font-size:13px}
.top{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;padding:18px 0;border-bottom:1px solid var(--line);margin-bottom:24px}
.brand{font-weight:700;font-size:17px;color:inherit;text-decoration:none}.brand span{color:var(--muted);font-weight:400}
.pill{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--line);border-radius:999px;padding:3px 10px;font-size:12px;color:var(--muted);background:var(--panel)}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:20px;margin:16px 0}
.sunk{background:var(--sunk);border-radius:10px;padding:14px 16px}
textarea,select{width:100%;font:inherit;padding:10px 12px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--ink)}
textarea{min-height:130px;font-family:ui-monospace,Menlo,monospace;font-size:14px}
button,.btn{font:inherit;font-weight:600;padding:10px 18px;min-height:44px;border:0;border-radius:8px;background:var(--accent);color:#fff;cursor:pointer;text-decoration:none;display:inline-flex;align-items:center}
button.ghost{background:transparent;color:var(--accent);border:1px solid var(--line);min-height:36px;padding:6px 12px}
button:disabled{opacity:.5;cursor:default}
.row{display:flex;gap:12px;flex-wrap:wrap;align-items:end}.row>*{flex:1;min-width:160px}
table{width:100%;border-collapse:collapse;font-size:14px}th,td{text-align:left;padding:10px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-weight:500;font-size:12px;text-transform:uppercase;letter-spacing:.04em}tr:last-child td{border-bottom:0}
.scroll{overflow-x:auto}
.v{display:inline-block;padding:3px 10px;border-radius:999px;font-size:12px;font-weight:700;white-space:nowrap}
.v-GO{color:var(--go);background:var(--go-bg)}.v-GO_FLAGGED{color:var(--gof);background:var(--gof-bg)}
.v-NO_GO{color:var(--no);background:var(--no-bg)}.v-MANUAL_REVIEW{color:var(--mr);background:var(--mr-bg)}.v-NA{color:var(--na);background:var(--na-bg)}
.s{display:inline-flex;gap:5px;align-items:center;font-weight:600;font-size:13px;white-space:nowrap}
.s-met{color:var(--go)}.s-partial{color:var(--gof)}.s-not_met{color:var(--no)}.s-unknown{color:var(--muted)}
.chip{display:inline-block;background:var(--sunk);border-radius:6px;padding:2px 8px;font-size:12px;margin:2px 4px 2px 0}
.chip.ok{color:var(--go)}.chip.warn{color:var(--gof)}.chip.fail{color:var(--no)}
.quote{margin:6px 0 0;padding:2px 0 2px 10px;border-left:3px solid var(--line);color:var(--muted);font-size:13px}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px;margin:16px 0}
.stat{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px 14px}.stat b{display:block;font-size:24px}
.card-head{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;align-items:flex-start}
.why{font-size:16px;margin:10px 0 0}
.bar{height:6px;border-radius:3px;background:var(--sunk);position:relative;width:120px;display:inline-block;vertical-align:middle;margin-right:6px}
.bar i{position:absolute;inset:0 auto 0 0;border-radius:3px;background:var(--accent)}
.bar u{position:absolute;top:-3px;bottom:-3px;width:2px;background:var(--muted)}
.steps{display:flex;flex-wrap:wrap;gap:4px;margin-top:14px;list-style:none;padding:0}
.steps li{font-size:12px;padding:3px 9px;border-radius:999px;background:var(--sunk);color:var(--muted)}
.steps .ok{color:var(--go);background:var(--go-bg)}.steps .error{color:var(--no);background:var(--no-bg)}
.steps .stopped,.steps .skipped{color:var(--gof);background:var(--gof-bg)}
.callout{border-left:3px solid var(--no);background:var(--no-bg);padding:10px 14px;border-radius:6px;margin-top:12px}
.callout.info{border-color:var(--gof);background:var(--gof-bg)}
.email{border:1px solid var(--line);border-radius:10px;overflow:hidden;background:var(--panel)}
.email-h{background:var(--sunk);padding:10px 14px;font-size:13px}.email-h div{margin:2px 0}
.email-b{padding:14px;white-space:pre-wrap;font:inherit;margin:0}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}
details{margin-top:14px}summary{cursor:pointer;font-weight:600;font-size:14px;padding:4px 0}
.progress{list-style:none;padding:0;margin:12px 0 0}.progress li{padding:6px 0;border-bottom:1px solid var(--line);font-size:14px}
"""


def page(title: str, body: str) -> str:
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{escape(title)}</title><style>{CSS}</style></head>'
            f'<body><main>{body}</main></body></html>')


def header() -> str:
    return (f'<header class="top"><a class="brand" href="/">Sprinto Outreach <span>· MESA AI Case 2</span></a>'
            f'<span class="pill" title="send_email() can only address this inbox">✉ Emails go only to '
            f'<code>{escape(HARDCODED_RECIPIENT)}</code></span></header>')


def _when(ts: Any) -> str:
    try:
        return datetime.fromisoformat(str(ts)).strftime("%d %b %Y, %H:%M UTC")
    except ValueError:
        return str(ts or "")


def _verdict(v: Optional[str]) -> str:
    if v in VERDICTS:
        return f'<span class="v v-{v}">{VERDICT_LABEL[v]}</span>'
    return f'<span class="v v-NA">{escape(v or "Incomplete")}</span>'


def _score(q: Dict[str, Any]) -> str:
    pct = round(float(q.get("weighted_score", 0)) * 100)
    return (f'<span class="bar" aria-hidden="true"><i style="width:{pct}%"></i><u style="left:{GO_THRESHOLD}%"></u></span>'
            f'<span class="small"><b>{pct}</b>/100 <span class="muted">(Go at {GO_THRESHOLD})</span></span>')


# ---------------- home ----------------

def home(runs: List[Dict[str, Any]], can_run: bool, steps: List[str]) -> str:
    opts = "".join(f'<option value="{s}"{" selected" if s == steps[-1] else ""}>{s}</option>' for s in steps)
    disabled = ('' if can_run else '<div class="callout">Runs are disabled: add <code>GEMINI_API_KEY</code> '
                'to the Vercel environment variables, then redeploy.</div>')
    form = f"""
<section class="panel">
  <h2>New run</h2>
  <p class="muted small" style="margin:4px 0 14px">Paste 1-15 company domains. Each one is scraped, qualified against the
  ICP, and if it qualifies, gets a contact, two pain points and a checked email draft.</p>
  {disabled}
  <label for="domains" class="small muted">One domain per line</label>
  <textarea id="domains" placeholder="acme.io&#10;example-saas.com"></textarea>
  <div class="row" style="margin-top:12px">
    <div><label for="until" class="small muted">Run up to step</label><select id="until">{opts}</select></div>
    <div style="flex:0"><button id="go" {'disabled' if not can_run else ''}>Run pipeline</button></div>
  </div>
  <ul id="progress" class="progress" aria-live="polite"></ul>
</section>"""
    rows = "".join(
        f'<tr><td><a href="/runs/{escape(r["run_id"])}">{escape(_when(r.get("created_at")) or r["run_id"])}</a>'
        f'<div class="muted small"><code>{escape(r["run_id"])}</code></div></td>'
        f'<td>{len(r.get("domains", []))}</td><td>{escape(", ".join(r.get("domains", [])[:4]))}'
        f'{"…" if len(r.get("domains", [])) > 4 else ""}</td>'
        f'<td class="muted">{escape(str(r.get("settings", {}).get("until", "")))}</td></tr>'
        for r in runs)
    table = (f'<section class="panel"><h2>Past runs</h2><div class="scroll"><table><tr><th>Run</th><th>Domains</th>'
             f'<th>Companies</th><th>Up to</th></tr>{rows or "<tr><td colspan=4 class=muted>No runs yet</td></tr>"}'
             f'</table></div></section>')
    return page("Sprinto Outreach", header() + form + table + ADVANCE_JS + HOME_JS)


ADVANCE_JS = """
<script>
async function advanceDomain(runId, d, until, report) {
  for (let unit = 0, busy = 0; unit < 30; unit++) {
    let r;
    try {
      const res = await fetch(`/api/runs/${runId}/domains/${encodeURIComponent(d)}/advance?until=${until}`, {method: 'POST'});
      r = await res.json();
      if (!res.ok) { report(`error: ${r.detail || res.status}`); return; }
    } catch (e) { report('network error, retrying…'); await new Promise(z => setTimeout(z, 5000)); continue; }
    report(`${r.stage}: ${r.message || ''}`);
    if (r.done) return;
    if (r.retry) {
      if (++busy > 6) { report(`${r.stage}: the model is still busy; use Resume later`); return; }
      report(`${r.stage}: model busy or rate-limited, retrying in 30s`);
      await new Promise(z => setTimeout(z, 30000));
    }
  }
}
</script>"""

HOME_JS = """
<script>
const go = document.getElementById('go'), prog = document.getElementById('progress');
go && go.addEventListener('click', async () => {
  const domains = document.getElementById('domains').value.split('\\n').map(s => s.trim()).filter(Boolean);
  const until = document.getElementById('until').value;
  if (!domains.length) return;
  go.disabled = true; prog.innerHTML = '<li>Creating run…</li>';
  const r = await fetch('/api/runs', {method: 'POST', headers: {'Content-Type': 'application/json'},
                                      body: JSON.stringify({domains, until})});
  const run = await r.json();
  if (!r.ok) { prog.innerHTML = ''; prog.append(Object.assign(document.createElement('li'), {textContent: run.detail || 'Error'})); go.disabled = false; return; }
  prog.innerHTML = '';
  const items = run.domains.map(d => { const li = document.createElement('li'); li.textContent = `${d}: waiting`; prog.append(li); return li; });
  for (const [i, d] of run.domains.entries()) {
    await advanceDomain(run.run_id, d, until, msg => { items[i].textContent = `${d}: ${msg}`; });
    items[i].textContent = '✓ ' + items[i].textContent;
  }
  location.href = `/runs/${run.run_id}`;
});
</script>"""


# ---------------- run page ----------------

def _quotes(evidence: List[Dict[str, Any]], limit: int = 2) -> str:
    seen, out = set(), []
    for e in evidence:
        key = (e.get("quote") or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(f'<div class="quote">“{escape(key)}” <a href="{escape(e["source_url"])}" target="_blank" '
                   f'rel="noopener">source</a></div>')
        if len(out) >= limit:
            break
    return "".join(out)


def _stepper(records: Dict[str, Any]) -> str:
    items = []
    for s in STEP_ORDER:
        r = records.get(s)
        st = r.status if r else "todo"
        mark = {"ok": "✓", "error": "✕", "stopped": "■", "skipped": "–"}.get(st, "·")
        items.append(f'<li class="{st}" title="{s}: {st}">{mark} {s}</li>')
    return f'<ol class="steps" aria-label="Pipeline steps">{"".join(items)}</ol>'


def _headline(q: Dict[str, Any]) -> str:
    if q.get("short_circuit"):
        return f'Stopped early: {q["short_circuit"]}'
    scores = q.get("scores", [])
    if q["decision"] in ("GO", "GO_FLAGGED"):
        met = [CRITERIA.get(s["criterion_id"], (s["criterion_id"],))[0] for s in scores if s["status"] == "met"]
        return "Qualifies: " + ("; ".join(met[:4]) if met else "meets the threshold")
    if q["decision"] == "MANUAL_REVIEW":
        unk = [CRITERIA.get(s["criterion_id"], (s["criterion_id"],))[0] for s in scores if s["status"] == "unknown"]
        return "Not enough public evidence to decide: " + "; ".join(unk[:4])
    miss = [CRITERIA.get(s["criterion_id"], (s["criterion_id"],))[0] for s in scores if s["status"] == "not_met"]
    return "Does not qualify: " + ("; ".join(miss[:3]) if miss else "score below the threshold")


def _resume(run_id: str, domain: str, label: str = "Resume") -> str:
    return (f'<button class="ghost" data-resume="{escape(domain)}" data-run="{escape(run_id)}">{label}</button>')


def domain_card(domain: str, records: Dict[str, Any], run_id: str = "") -> str:
    q_rec, s_rec, e_rec = records.get("qualify"), records.get("scrape"), records.get("extract")
    failed = next((r for r in records.values() if r and r.status == "error"), None)
    q = q_rec.output["qualification"] if q_rec and q_rec.status == "ok" else None
    anchor = escape(domain.replace(".", "-"))
    head = (f'<div class="card-head"><div><h2>{escape(domain)}</h2></div>'
            f'<div>{_verdict(q["decision"] if q else None)}</div></div>')
    parts = [f'<section class="panel" id="{anchor}">', head]
    if q:
        parts.append(f'<p class="why">{escape(_headline(q))}</p><div style="margin-top:8px">{_score(q)} '
                     f'<span class="muted small">· {q["unknown_weight_share"]:.0%} of weight unknown</span></div>')
        if q.get("flags"):
            parts.append('<div style="margin-top:10px">' + "".join(
                f'<span class="chip warn">⚑ {escape(f)}</span>' for f in q["flags"]) + "</div>")
    parts.append(_stepper(records))
    if failed:
        parts.append(f'<div class="callout"><b>{escape(failed.step)} failed.</b> <span class="small">'
                     f'{escape(failed.error or "")}</span><div style="margin-top:8px">{_resume(run_id, domain)}</div></div>')
    elif not q and run_id:
        stopped = next((r for r in records.values() if r and r.status == "stopped"), None)
        if stopped or not records:
            parts.append(f'<div class="callout info">Not finished.<div style="margin-top:8px">'
                         f'{_resume(run_id, domain, "Continue")}</div></div>')

    parts.append(outreach_section(records))

    if q:
        parts.append('<h3>Why: scorecard</h3><div class="scroll"><table><tr><th>Criterion</th><th>Weight</th>'
                     '<th>Status</th><th>Reason and evidence</th></tr>')
        for sc in q["scores"]:
            label, weight = CRITERIA.get(sc["criterion_id"], (sc["criterion_id"], ""))
            st = sc["status"]
            parts.append(f'<tr><td>{escape(label)}<div class="muted small"><code>{escape(sc["criterion_id"])}</code></div></td>'
                         f'<td class="muted small">{escape(weight)}</td>'
                         f'<td><span class="s s-{st}">{STATUS_ICON.get(st, "")} {escape(st.replace("_", " "))}</span></td>'
                         f'<td>{escape(sc["reason"])}{_quotes(sc.get("evidence", []))}</td></tr>')
        parts.append("</table></div>")
        parts.append('<h3>Research loop</h3><div class="scroll"><table><tr><th>#</th><th>Open question</th>'
                     '<th>Fetched</th><th>Result</th></tr>')
        parts.append(f'<tr><td>0</td><td class="muted">start</td><td>homepage</td>'
                     f'<td>{escape(s_rec.note or "") if s_rec else ""}</td></tr>')
        for st in q["agent_steps"]:
            urls = " ".join(f'<div><a href="{escape(u)}" target="_blank" rel="noopener" class="small">{escape(u[:60])}</a></div>'
                            for u in st["urls"])
            parts.append(f'<tr><td>{st["round"]}</td><td>{escape(st["question"])}<div class="muted small">missing '
                         f'{escape(", ".join(st["missing_fields"]))}</div></td><td>{escape(st["page_kind"])}{urls}</td>'
                         f'<td>{escape(st["result_summary"])}</td></tr>')
        parts.append(f'</table></div><details><summary>Decision rule</summary><p class="small muted">'
                     f'{escape(q_rec.note or "")}.</p><p class="small">{escape(q["decision_rule"])}</p></details>')
        profile = q_rec.output.get("profile", {})
    else:
        profile = e_rec.output["profile"] if e_rec and e_rec.status == "ok" else {}
    if profile:
        rows = "".join(
            f'<tr><td><code>{escape(k)}</code></td><td>{escape(str(v["value"]))}{_quotes(v.get("evidence", []), 1)}</td></tr>'
            for k, v in profile.items() if k != "domain" and isinstance(v, dict) and v.get("value") is not None)
        parts.append(f'<details><summary>Extracted facts</summary><div class="scroll"><table>{rows}</table></div></details>')
    links = " · ".join(f'<a href="/api/runs/{escape(r.run_id)}/domains/{escape(domain)}/steps/{s}" target="_blank">'
                       f'{s}.json</a>' for s, r in records.items() if r)
    if links:
        parts.append(f'<p class="small muted" style="margin-top:14px">Raw trace: {links}</p>')
    parts.append("</section>")
    return "".join(parts)


def outreach_section(records: Dict[str, Any]) -> str:
    """Steps 4-7: who, why them, the two pains, the email, and whether it was sent."""
    poc, pains, draft, send = (records.get(k) for k in ("poc", "pains", "draft", "send"))
    if not any((poc, pains, draft, send)):
        return ""
    out = ['<h3>Outreach</h3>']
    if poc:
        c = (poc.output or {}).get("chosen")
        if c:
            out.append(f'<div class="sunk"><b>{escape(c["first_name"])} {escape(c.get("last_name") or "")}</b> · '
                       f'{escape(c.get("position") or "")} <span class="chip">{escape(c.get("source", ""))}</span>'
                       f'<div class="small muted">{escape(c.get("email") or "")}</div>'
                       f'<div class="small" style="margin-top:6px">Why this person: {escape(poc.note or "")}</div></div>')
        else:
            out.append(f'<div class="callout info small">No contact: {escape(poc.note or "")}</div>')
    if pains and pains.status == "ok":
        cards = "".join(
            f'<div class="sunk"><b>{escape(pp["title"])}</b><p class="small" style="margin:6px 0">'
            f'{escape(pp["why_this_person"])}</p><div class="small"><b>Sprinto:</b> {escape(pp["sprinto_answer"])}</div>'
            f'{_quotes(pp.get("evidence", []), 1)}</div>'
            for pp in pains.output["pains"]["pains"])
        out.append(f'<h3>Two pain points</h3><div class="grid2">{cards}</div>')
    elif pains and pains.status == "error":
        out.append(f'<div class="callout small">Pain points failed: {escape(pains.error or "")}</div>')
    if draft and draft.status == "ok":
        d = draft.output["draft"]
        checks = draft.output.get("report", {}).get("checks", [])
        chips = "".join(
            f'<span class="chip {"ok" if c["severity"] == "pass" else c["severity"]}">'
            f'{"✓" if c["severity"] == "pass" else "⚠"} {escape(c["check"])}</span>' for c in checks)
        sent = ""
        if send:
            label = {"ok": "✉ Sent", "skipped": "Draft only, not sent", "error": "Send failed"}.get(send.status, send.status)
            sent = f'<div><b>Status:</b> {label} <span class="muted">{escape(send.note or send.error or "")}</span></div>'
        out.append(f'<h3>Email draft</h3><div class="email"><div class="email-h">'
                   f'<div><b>To:</b> {escape(d["to_name"])} <span class="muted">(intended '
                   f'{escape(d.get("intended_address") or "n/a")}; delivered only to {escape(HARDCODED_RECIPIENT)})</span></div>'
                   f'<div><b>Subject:</b> {escape(d["subject"])}</div>{sent}</div>'
                   f'<pre class="email-b">{escape(d["body"])}</pre></div>'
                   f'<div class="small" style="margin-top:8px"><b>Hook:</b> {escape(d["hook"])}</div>'
                   f'{_quotes(d.get("hook_evidence", []), 1)}<div style="margin-top:8px">{chips}</div>')
    elif draft and draft.status == "error":
        out.append(f'<div class="callout small">Draft failed: {escape(draft.error or "")}</div>')
    elif send:
        out.append(f'<p class="small"><b>Send:</b> {escape(send.note or send.error or send.status)}</p>')
    return "".join(out)


def _overview(manifest: Dict[str, Any], records_by_domain: Dict[str, Dict[str, Any]]) -> str:
    rows = []
    for d in manifest.get("domains", []):
        recs = records_by_domain.get(d, {})
        q = recs.get("qualify")
        q = q.output["qualification"] if q and q.status == "ok" else None
        poc = recs.get("poc")
        c = (poc.output or {}).get("chosen") if poc else None
        send = recs.get("send")
        email = ("✉ sent" if send and send.status == "ok" else "draft ready" if recs.get("draft") and recs["draft"].status == "ok"
                 else "—")
        rows.append(f'<tr><td><a href="#{escape(d.replace(".", "-"))}">{escape(d)}</a></td>'
                    f'<td>{_verdict(q["decision"] if q else None)}</td>'
                    f'<td>{round(q["weighted_score"] * 100) if q else "—"}</td>'
                    f'<td>{escape(c["first_name"] + " · " + (c.get("position") or "")) if c else "—"}</td>'
                    f'<td>{email}</td></tr>')
    return (f'<section class="panel"><h2>Overview</h2><div class="scroll"><table><tr><th>Company</th><th>Verdict</th>'
            f'<th>Score</th><th>Contact</th><th>Email</th></tr>{"".join(rows)}</table></div></section>')


RUN_JS = """
<script>
document.querySelectorAll('[data-resume]').forEach(b => b.addEventListener('click', async () => {
  document.querySelectorAll('[data-resume]').forEach(x => x.disabled = true);
  await advanceDomain(b.dataset.run, b.dataset.resume, 'send', msg => { b.textContent = msg; });
  location.reload();
}));
</script>"""


def run_page(manifest: Dict[str, Any], records_by_domain: Dict[str, Dict[str, Any]]) -> str:
    counts = {k: 0 for k in (*VERDICTS, "Incomplete")}
    for recs in records_by_domain.values():
        q = recs.get("qualify")
        counts[q.output["qualification"]["decision"] if q and q.status == "ok" else "Incomplete"] += 1
    stats = "".join(f'<div class="stat"><b>{n}</b>{_verdict(k)}</div>' for k, n in counts.items()
                    if n or k in ("GO", "NO_GO"))
    s = manifest.get("settings", {})
    run_id = manifest["run_id"]
    body = (header() + f'<h1 style="font-size:24px;margin:0">Run of {escape(_when(manifest.get("created_at")))}</h1>'
            f'<p class="small muted" style="margin:6px 0 0"><code>{escape(run_id)}</code> · '
            f'{escape(str(s.get("provider", "anthropic")))} · qualify {escape(str(s.get("model")))} · extract '
            f'{escape(str(s.get("extract_model")))} · prompt {escape(str(s.get("prompt_version")))}</p>'
            f'<div class="stats">{stats}</div>' + _overview(manifest, records_by_domain))
    body += "".join(domain_card(d, records_by_domain.get(d, {}), run_id) for d in manifest.get("domains", []))
    return page(f"Run {run_id}", body + ADVANCE_JS + RUN_JS)
