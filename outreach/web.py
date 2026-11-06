"""HTML for the dashboard (server-rendered, no build step). Every value is escaped."""
import json
from html import escape
from typing import Any, Dict, List, Optional

from .config import HARDCODED_RECIPIENT
from .models import STEP_ORDER

CSS = """
:root{--bg:#f7f7f5;--panel:#fff;--ink:#1d1d1b;--muted:#6b6b66;--line:#e4e3de;--accent:#3b5bdb;
--go:#2b8a3e;--gof:#a86b00;--no:#c92a2a;--mr:#5f3dc4;--chip:#f0efea}
@media (prefers-color-scheme:dark){:root{--bg:#141413;--panel:#1d1d1b;--ink:#ecebe6;--muted:#a3a29b;
--line:#33322f;--accent:#7b93ff;--go:#51cf66;--gof:#fcc419;--no:#ff6b6b;--mr:#b197fc;--chip:#2a2927}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
main{max-width:1080px;margin:0 auto;padding:24px 16px 64px}
a{color:var(--accent)}h1{font-size:22px;margin:0 0 4px}h2{font-size:17px;margin:28px 0 10px}
h3{font-size:15px;margin:18px 0 6px}.muted{color:var(--muted)}.small{font-size:13px}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px;margin:12px 0}
textarea,select,input{width:100%;font:inherit;padding:8px 10px;border:1px solid var(--line);border-radius:8px;
background:var(--bg);color:var(--ink)}textarea{min-height:120px;font-family:ui-monospace,Menlo,monospace}
button{font:inherit;padding:8px 16px;border:0;border-radius:8px;background:var(--accent);color:#fff;cursor:pointer}
button:disabled{opacity:.5}.row{display:flex;gap:12px;flex-wrap:wrap;align-items:end}.row>*{flex:1;min-width:160px}
table{width:100%;border-collapse:collapse;font-size:14px}th,td{text-align:left;padding:8px 6px;
border-bottom:1px solid var(--line);vertical-align:top}th{color:var(--muted);font-weight:500}
.badge{display:inline-block;padding:2px 8px;border-radius:999px;font-size:12px;font-weight:600;color:#fff}
.GO{background:var(--go)}.GO_FLAGGED{background:var(--gof)}.NO_GO{background:var(--no)}
.MANUAL_REVIEW{background:var(--mr)}.ERR{background:var(--muted)}
.chip{display:inline-block;background:var(--chip);border-radius:6px;padding:1px 6px;font-size:12px;margin:1px}
.met{color:var(--go)}.partial{color:var(--gof)}.not_met{color:var(--no)}.unknown{color:var(--muted)}
blockquote{margin:4px 0;padding:2px 10px;border-left:3px solid var(--line);color:var(--muted);font-size:13px}
.scroll{overflow-x:auto}details summary{cursor:pointer}
"""


def page(title: str, body: str) -> str:
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{escape(title)}</title><style>{CSS}</style></head>'
            f'<body><main>{body}</main></body></html>')


def header() -> str:
    return (f'<h1><a href="/" style="color:inherit;text-decoration:none">Sprinto Outreach Pipeline</a></h1>'
            f'<div class="muted small">MESA AI Case 2 &middot; emails go only to '
            f'<code>{escape(HARDCODED_RECIPIENT)}</code></div>')


def home(runs: List[Dict[str, Any]], can_run: bool, steps: List[str]) -> str:
    opts = "".join(f'<option value="{s}"{" selected" if s == steps[-1] else ""}>{s}</option>' for s in steps)
    form = f"""
<div class="panel">
  <h2 style="margin-top:0">New run</h2>
  {'' if can_run else '<p class="NO_GO badge">Runs are disabled: add GEMINI_API_KEY to the Vercel environment variables, then redeploy.</p>'}
  <label class="small muted">One domain per line</label>
  <textarea id="domains" placeholder="acme.io&#10;example-saas.com"></textarea>
  <div class="row" style="margin-top:10px">
    <div><label class="small muted">Run up to step</label><select id="until">{opts}</select></div>
    <div style="flex:0"><button id="go" {'disabled' if not can_run else ''}>Run</button></div>
  </div>
  <div id="progress" class="small" style="margin-top:10px"></div>
</div>"""
    rows = "".join(
        f'<tr><td><a href="/runs/{escape(r["run_id"])}">{escape(r["run_id"])}</a></td>'
        f'<td>{len(r.get("domains", []))}</td><td>{escape(", ".join(r.get("domains", [])[:4]))}'
        f'{"…" if len(r.get("domains", [])) > 4 else ""}</td>'
        f'<td class="muted">{escape(str(r.get("settings", {}).get("until", "")))}</td></tr>'
        for r in runs)
    table = (f'<h2>Runs</h2><div class="panel scroll"><table><tr><th>Run</th><th>Domains</th><th></th>'
             f'<th>Up to</th></tr>{rows or "<tr><td colspan=4 class=muted>No runs yet</td></tr>"}</table></div>')
    script = """
<script>
const go = document.getElementById('go'), prog = document.getElementById('progress');
go && go.addEventListener('click', async () => {
  const domains = document.getElementById('domains').value.split('\\n').map(s => s.trim()).filter(Boolean);
  const until = document.getElementById('until').value;
  if (!domains.length) return;
  go.disabled = true; prog.textContent = 'Creating run…';
  const r = await fetch('/api/runs', {method: 'POST', headers: {'Content-Type': 'application/json'},
                                      body: JSON.stringify({domains, until})});
  const run = await r.json();
  if (!r.ok) { prog.textContent = run.detail || 'Error'; go.disabled = false; return; }
  for (const [i, d] of run.domains.entries()) {
    const tag = `(${i + 1}/${run.domains.length}) ${d}`;
    for (let unit = 0; unit < 30; unit++) {
      let r;
      try {
        const res = await fetch(`/api/runs/${run.run_id}/domains/${encodeURIComponent(d)}/advance?until=${until}`, {method: 'POST'});
        r = await res.json();
        if (!res.ok) { prog.textContent = `${tag}: ${r.detail || res.status}`; break; }
      } catch (e) { prog.textContent = `${tag}: network error, retrying…`; await new Promise(z => setTimeout(z, 5000)); continue; }
      prog.textContent = `${tag}: ${r.stage} - ${r.message || ''}`;
      if (r.done) break;
      if (r.retry) { prog.textContent += ' (model busy, retrying in 10s)'; await new Promise(z => setTimeout(z, 10000)); }
    }
  }
  location.href = `/runs/${run.run_id}`;
});
</script>"""
    return page("Sprinto Outreach", header() + form + table + script)


def _ev(evidence: List[Dict[str, Any]], limit: int = 2) -> str:
    return "".join(f'<blockquote>“{escape(e["quote"])}” <a href="{escape(e["source_url"])}" '
                   f'target="_blank" rel="noopener">source</a></blockquote>' for e in evidence[:limit])


def domain_card(domain: str, records: Dict[str, Any]) -> str:
    q_rec = records.get("qualify")
    s_rec = records.get("scrape")
    e_rec = records.get("extract")
    parts = [f'<div class="panel"><h2 style="margin-top:0">{escape(domain)} ']
    failed = next((r for r in records.values() if r and r.status == "error"), None)
    if q_rec and q_rec.status == "ok":
        q = q_rec.output["qualification"]
        parts.append(f'<span class="badge {q["decision"]}">{q["decision"]}</span> '
                     f'<span class="muted small">score {q["weighted_score"]} &middot; '
                     f'unknown {q["unknown_weight_share"]:.0%}</span></h2>')
        if q.get("short_circuit"):
            parts.append(f'<p><b>Stopped early:</b> {escape(q["short_circuit"])}</p>')
        if q.get("flags"):
            parts.append("<p>" + "".join(f'<span class="chip">⚑ {escape(f)}</span>' for f in q["flags"]) + "</p>")
        parts.append('<h3>Why: scorecard</h3><div class="scroll"><table><tr><th>Criterion</th><th>Status</th>'
                     '<th>Reason and evidence</th></tr>')
        for sc in q["scores"]:
            parts.append(f'<tr><td>{escape(sc["criterion_id"])}</td><td class="{sc["status"]}">{sc["status"]}</td>'
                         f'<td>{escape(sc["reason"])}{_ev(sc.get("evidence", []))}</td></tr>')
        parts.append("</table></div>")
        parts.append('<h3>Research loop</h3><div class="scroll"><table><tr><th>#</th><th>Open question</th>'
                     '<th>Fetched</th><th>Result</th></tr>')
        parts.append(f'<tr><td>0</td><td class="muted">start</td><td>homepage</td>'
                     f'<td>{escape(s_rec.note or "") if s_rec else ""}</td></tr>')
        for st in q["agent_steps"]:
            urls = " ".join(f'<a href="{escape(u)}" target="_blank" rel="noopener" class="small">{escape(u[:60])}</a>'
                            for u in st["urls"])
            parts.append(f'<tr><td>{st["round"]}</td><td>{escape(st["question"])}<div class="muted small">missing '
                         f'{escape(", ".join(st["missing_fields"]))}</div></td><td>{escape(st["page_kind"])}<br>{urls}</td>'
                         f'<td>{escape(st["result_summary"])}</td></tr>')
        parts.append(f'</table></div><p class="small muted">{escape(q_rec.note or "")}. Rule: {escape(q["decision_rule"])}</p>')
        profile = q_rec.output.get("profile", {})
    else:
        if failed:
            parts.append(f'<span class="badge ERR">{escape(failed.step)} failed</span></h2>'
                         f'<p class="small">{escape(failed.error or "")}</p>')
        else:
            parts.append('</h2>')
        profile = e_rec.output["profile"] if e_rec and e_rec.status == "ok" else {}
    if profile:
        rows = "".join(
            f'<tr><td>{escape(k)}</td><td>{escape(str(v["value"]))}{_ev(v.get("evidence", []), 1)}</td></tr>'
            for k, v in profile.items() if k != "domain" and isinstance(v, dict) and v.get("value") is not None)
        parts.append(f'<details><summary>Extracted facts</summary><div class="scroll"><table>{rows}</table></div></details>')
    links = " · ".join(f'<a href="/api/runs/{escape(r.run_id)}/domains/{escape(domain)}/steps/{s}" target="_blank">'
                       f'{s}.json</a>' for s, r in records.items() if r)
    parts.append(f'<p class="small muted">Raw trace: {links}</p></div>')
    return "".join(parts)


def run_page(manifest: Dict[str, Any], records_by_domain: Dict[str, Dict[str, Any]]) -> str:
    counts: Dict[str, int] = {}
    for recs in records_by_domain.values():
        q = recs.get("qualify")
        key = q.output["qualification"]["decision"] if q and q.status == "ok" else "pending/error"
        counts[key] = counts.get(key, 0) + 1
    summary = " ".join(f'<span class="badge {k if k in ("GO","GO_FLAGGED","NO_GO","MANUAL_REVIEW") else "ERR"}">'
                       f'{escape(k)}: {v}</span>' for k, v in counts.items())
    s = manifest.get("settings", {})
    body = (header() + f'<h2>Run {escape(manifest["run_id"])}</h2>'
            f'<p class="small muted">{escape(manifest.get("created_at", ""))} &middot; {escape(str(s.get("provider", "anthropic")))} &middot; qualify model '
            f'{escape(str(s.get("model")))} &middot; extract model {escape(str(s.get("extract_model")))} &middot; '
            f'prompt {escape(str(s.get("prompt_version")))}</p><p>{summary}</p>')
    body += "".join(domain_card(d, records_by_domain.get(d, {})) for d in manifest.get("domains", []))
    return page(f"Run {manifest['run_id']}", body)
