"""HTML for the dashboard (server-rendered, no build step). Every value is escaped.

Reading order mirrors a reviewer's questions: what was decided (overview), why
(summary + scorecard), who and what we'd send (outreach), how we got there
(research, data, raw trace).
"""
from datetime import datetime
from html import escape
from typing import Any, Dict, List, Optional

from .config import HARDCODED_RECIPIENT
from .models import STEP_ORDER

VERDICTS = ("GO", "GO_FLAGGED", "NO_GO", "MANUAL_REVIEW")
VERDICT_LABEL = {"GO": "Go", "GO_FLAGGED": "Go, flagged", "NO_GO": "No go", "MANUAL_REVIEW": "Needs review"}
VERDICT_TONE = {"GO": "green", "GO_FLAGGED": "amber", "NO_GO": "red", "MANUAL_REVIEW": "violet"}
CRITERIA = {  # label, weight (mirrors config/icp.yaml)
    "is_saas": ("SaaS company", "Gate"),
    "certification_gap": ("Not yet SOC 2 / ISO 27001", "Gate · 25"),
    "funding_stage": ("Series A–C", "20"),
    "employee_count": ("Team size", "10"),
    "compliance_hiring": ("Hiring for compliance", "20"),
    "enterprise_pressure": ("Selling to enterprise", "15"),
    "security_news": ("Security news", "10"),
}
STATUS = {"met": ("Met", "green"), "partial": ("Partial", "amber"), "not_met": ("Not met", "red"),
          "unknown": ("Unknown", "gray")}
STEP_LABEL = {"scrape": "Scrape", "extract": "Extract", "qualify": "Qualify", "poc": "Contact",
              "pains": "Pain points", "draft": "Draft", "send": "Send"}
GO_THRESHOLD = 55

ICON = {
    "mail": '<path d="M3 6.5h18v11H3z"/><path d="m3.5 7 8.5 6.5L20.5 7"/>',
    "arrow": '<path d="M5 12h14M13 6l6 6-6 6"/>',
    "back": '<path d="M19 12H5M11 6l-6 6 6 6"/>',
    "check": '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
    "x": '<path d="M6 6l12 12M18 6 6 18"/>',
    "flag": '<path d="M5 21V4M5 4h11l-2 4 2 4H5"/>',
    "refresh": '<path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 4v7h-7"/>',
}


def icon(name: str, size: int = 16) -> str:
    return (f'<svg class="i" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            f'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{ICON[name]}</svg>')


CSS = """
:root{color-scheme:light dark;
  --bg:#fbfbfa;--surface:#ffffff;--raised:#f7f7f5;--hover:#f2f2f0;
  --ink:#191918;--ink-2:#55534e;--ink-3:#8f8d87;--line:rgba(25,25,24,.09);--line-2:rgba(25,25,24,.15);
  --accent:#2f6fed;--btn:#191918;--btn-ink:#fff;
  --green:#1a7f45;--green-bg:#eaf6ee;--amber:#946000;--amber-bg:#fbf3df;--red:#c4372b;--red-bg:#fcecea;
  --violet:#6a46c9;--violet-bg:#f1edfc;--gray:#6f6d67;--gray-bg:#f0efec;
  --shadow:0 1px 2px rgba(25,25,24,.04),0 4px 16px rgba(25,25,24,.04);
  --r:14px;--r-sm:9px;
}
@media (prefers-color-scheme:dark){:root{
  --bg:#141414;--surface:#1c1c1c;--raised:#222221;--hover:#2a2a29;
  --ink:#ededeb;--ink-2:#b4b2ac;--ink-3:#8a8882;--line:rgba(255,255,255,.08);--line-2:rgba(255,255,255,.15);
  --accent:#6d9cff;--btn:#ededeb;--btn-ink:#141414;
  --green:#5fd08c;--green-bg:rgba(95,208,140,.12);--amber:#f0be57;--amber-bg:rgba(240,190,87,.12);
  --red:#ff8577;--red-bg:rgba(255,133,119,.12);--violet:#b9a3ff;--violet-bg:rgba(185,163,255,.13);
  --gray:#a3a19b;--gray-bg:rgba(255,255,255,.07);--shadow:0 1px 2px rgba(0,0,0,.3)}}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);
  font:14.5px/1.55 "Inter",-apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",sans-serif;
  font-feature-settings:"cv11","ss01";-webkit-font-smoothing:antialiased;letter-spacing:-.006em}
a{color:inherit;text-decoration:none}a.u{color:var(--accent)}a.u:hover{text-decoration:underline}
.i{flex:none;vertical-align:-3px}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:6px}
.num{font-variant-numeric:tabular-nums}code,.mono{font:12.5px/1.5 ui-monospace,"SF Mono",Menlo,monospace;overflow-wrap:anywhere}

.nav{position:sticky;top:0;z-index:10;background:color-mix(in srgb,var(--bg) 82%,transparent);
  backdrop-filter:saturate(180%) blur(14px);-webkit-backdrop-filter:saturate(180%) blur(14px);border-bottom:1px solid var(--line)}
.nav-in{max-width:1120px;margin:0 auto;padding:0 24px;height:56px;display:flex;align-items:center;gap:16px}
.logo{display:flex;align-items:center;gap:10px;font-weight:600;letter-spacing:-.01em}
.mark{width:22px;height:22px;border-radius:6px;background:var(--ink);display:grid;place-items:center;color:var(--bg);font-size:12px;font-weight:700}
.nav .sp{flex:1}
.recip{display:flex;align-items:center;gap:7px;color:var(--ink-3);font-size:12.5px;min-width:0}
.recip>span{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}

main{max-width:1120px;margin:0 auto;padding:40px 24px 96px}
.crumb{display:inline-flex;align-items:center;gap:6px;color:var(--ink-3);font-size:13px;margin-bottom:14px}
.crumb:hover{color:var(--ink)}
h1{font-size:30px;line-height:1.15;letter-spacing:-.025em;font-weight:650;margin:0}
.lede{color:var(--ink-2);font-size:15px;margin:8px 0 0;max-width:640px}
.meta{display:flex;flex-wrap:wrap;gap:6px 14px;color:var(--ink-3);font-size:12.5px;margin-top:10px}
h2{font-size:15px;font-weight:600;letter-spacing:-.01em;margin:0}
.section-h{display:flex;align-items:baseline;justify-content:space-between;gap:12px;margin:40px 0 12px}
.section-h .sub{color:var(--ink-3);font-size:13px}
.label{font-size:12px;color:var(--ink-3);font-weight:500}

.card{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);box-shadow:var(--shadow)}
.pad{padding:22px 24px}

.btn{appearance:none;font:inherit;font-weight:550;display:inline-flex;align-items:center;gap:8px;height:38px;padding:0 16px;
  border-radius:10px;border:1px solid transparent;background:var(--btn);color:var(--btn-ink);cursor:pointer;transition:opacity .15s,transform .05s}
.btn:hover{opacity:.88}.btn:active{transform:translateY(.5px)}.btn:disabled{opacity:.4;cursor:default}
.btn.quiet{background:var(--surface);color:var(--ink);border-color:var(--line-2);height:32px;padding:0 12px;font-size:13px}
.btn.quiet:hover{background:var(--hover);opacity:1}

textarea{width:100%;font:inherit;color:var(--ink);background:var(--raised);border:1px solid var(--line);
  border-radius:var(--r-sm);padding:12px 14px;transition:border-color .15s,background .15s;margin-top:8px;
  min-height:132px;resize:vertical;font-family:ui-monospace,"SF Mono",Menlo,monospace;font-size:13.5px;line-height:1.7}
textarea:focus{outline:none;border-color:var(--accent);background:var(--surface);box-shadow:0 0 0 3px color-mix(in srgb,var(--accent) 18%,transparent)}
.composer-foot{display:flex;align-items:flex-end;justify-content:space-between;gap:14px;flex-wrap:wrap;margin-top:16px}
.seg{display:inline-flex;background:var(--raised);border:1px solid var(--line);border-radius:10px;padding:3px;gap:2px;flex-wrap:wrap}
.seg input{position:absolute;opacity:0;pointer-events:none}
.seg label{font-size:12.5px;padding:5px 10px;border-radius:7px;color:var(--ink-2);cursor:pointer;white-space:nowrap}
.seg input:checked+label{background:var(--surface);color:var(--ink);box-shadow:0 1px 2px rgba(0,0,0,.08);font-weight:550}
.seg input:focus-visible+label{outline:2px solid var(--accent)}

.tag{display:inline-flex;align-items:center;gap:6px;min-height:24px;padding:2px 9px;border-radius:999px;font-size:12px;font-weight:550;white-space:nowrap}
.checks .tag{white-space:normal}
.tag::before{content:"";width:6px;height:6px;border-radius:50%;background:currentColor;flex:none}
.tag.plain::before{display:none}
.t-green{color:var(--green);background:var(--green-bg)}.t-amber{color:var(--amber);background:var(--amber-bg)}
.t-red{color:var(--red);background:var(--red-bg)}.t-violet{color:var(--violet);background:var(--violet-bg)}
.t-gray{color:var(--gray);background:var(--gray-bg)}
.st{display:inline-flex;align-items:center;gap:7px;font-size:13px;font-weight:550;white-space:nowrap}
.st::before{content:"";width:7px;height:7px;border-radius:50%;background:currentColor}
.c-green{color:var(--green)}.c-amber{color:var(--amber)}.c-red{color:var(--red)}.c-gray{color:var(--ink-3)}

.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));overflow:hidden;margin-top:28px}
.stat{padding:18px 20px;box-shadow:1px 0 0 var(--line),0 1px 0 var(--line)}
.stat b{display:block;font-size:26px;font-weight:600;letter-spacing:-.02em;line-height:1.1;margin-bottom:8px}

.tbl{width:100%;border-collapse:collapse}
.tbl th{font-size:12px;font-weight:500;color:var(--ink-3);text-align:left;padding:12px 16px;border-bottom:1px solid var(--line);white-space:nowrap}
.tbl td{padding:14px 16px;border-bottom:1px solid var(--line);vertical-align:top}
.tbl tr:last-child td{border-bottom:0}
.tbl.rows tbody tr{cursor:pointer;transition:background .12s}.tbl.rows tbody tr:hover{background:var(--hover)}
.scroll{overflow-x:auto}
.co{display:inline-flex;align-items:center;gap:10px;font-weight:550}
.fav{width:20px;height:20px;border-radius:5px;background:var(--raised);border:1px solid var(--line);flex:none;object-fit:cover}

.meter{display:inline-flex;align-items:center;gap:10px;white-space:nowrap}
.bar{position:relative;width:64px;height:4px;border-radius:2px;background:var(--gray-bg)}
.bar i{position:absolute;inset:0 auto 0 0;border-radius:2px;background:var(--ink)}
.bar u{position:absolute;top:-4px;bottom:-4px;width:1.5px;background:var(--ink-3);border-radius:1px}

.company{margin-top:16px;scroll-margin-top:72px}
.co-head{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;flex-wrap:wrap;padding:22px 24px 0}
.co-head h3{font-size:19px;letter-spacing:-.02em;font-weight:620;margin:0;display:flex;align-items:center;gap:10px}
.co-head .fav{width:26px;height:26px;border-radius:7px}
.headline{font-size:15px;color:var(--ink);margin:12px 0 0;max-width:760px}
.co-meta{display:flex;flex-wrap:wrap;align-items:center;gap:10px 18px;margin-top:14px;color:var(--ink-3);font-size:12.5px}
.tabs{display:flex;gap:2px;padding:0 18px;margin-top:20px;box-shadow:inset 0 -1px 0 var(--line);overflow-x:auto;overflow-y:hidden;scrollbar-width:none}
.tabs::-webkit-scrollbar{display:none}
.tab{appearance:none;background:none;border:0;font:inherit;font-size:13px;font-weight:550;color:var(--ink-3);
  padding:10px 8px 11px;margin:0 2px;cursor:pointer;border-bottom:2px solid transparent;white-space:nowrap}
.tab:hover{color:var(--ink)}.tab[aria-selected=true]{color:var(--ink);border-color:var(--ink)}
.panel{padding:22px 24px 24px}
.js .panel[hidden]{display:none}
.panel-h{font-size:12px;font-weight:550;color:var(--ink-3);margin:26px 0 10px}.panel-h:first-child{margin-top:0}

.steps{display:flex;align-items:center;margin-top:18px;flex-wrap:wrap;row-gap:8px}
.step{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--ink-3)}
.step .d{width:16px;height:16px;border-radius:50%;border:1.5px solid var(--line-2);display:grid;place-items:center}
.step.ok{color:var(--ink-2)}.step.ok .d{background:var(--ink);border-color:var(--ink);color:var(--bg)}
.step.error{color:var(--red)}.step.error .d{background:var(--red);border-color:var(--red);color:#fff}
.step.stopped .d,.step.skipped .d{border-color:var(--amber);background:var(--amber-bg)}
.step.stopped,.step.skipped{color:var(--amber)}
.step-ln{width:12px;height:1.5px;background:var(--line-2);margin:0 6px}

.note{display:flex;gap:12px;align-items:center;justify-content:space-between;flex-wrap:wrap;border-radius:var(--r-sm);
  padding:12px 14px;margin-top:16px;font-size:13px}
.note.err{background:var(--red-bg)}.note.info{background:var(--amber-bg)}
.note p{margin:0;color:var(--ink-2);flex:1;min-width:200px}.note.err b{color:var(--red)}.note.info b{color:var(--amber)}

.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px}
.tile{background:var(--raised);border:1px solid var(--line);border-radius:12px;padding:16px 18px}
.tile h4{margin:0 0 6px;font-size:14px;font-weight:600;letter-spacing:-.01em}
.tile p{margin:0;color:var(--ink-2);font-size:13.5px}
.tile .ans{margin-top:10px;font-size:13px;color:var(--ink)}
.person{display:flex;gap:14px;align-items:flex-start}
.avatar{width:40px;height:40px;border-radius:50%;background:var(--ink);color:var(--bg);display:grid;place-items:center;font-weight:600;flex:none}
.person .nm{font-weight:600}.person .rl{color:var(--ink-2);font-size:13.5px}
.person .why{color:var(--ink-3);font-size:12.5px;margin-top:6px}
.quote{display:block;margin-top:10px;padding-left:12px;border-left:2px solid var(--line-2);color:var(--ink-3);font-size:12.5px;line-height:1.5}
.quote a{color:var(--ink-3);text-decoration:underline;text-underline-offset:2px}

.mail{border:1px solid var(--line);border-radius:12px;overflow:hidden;background:var(--surface)}
.mail-h{padding:12px 18px;border-bottom:1px solid var(--line);background:var(--raised);display:grid;gap:3px;font-size:13px}
.mail-h .k{color:var(--ink-3);display:inline-block;width:76px}
.mail-subj{font-size:17px;font-weight:600;letter-spacing:-.015em;padding:20px 22px 0}
.mail-b{padding:12px 22px 24px;white-space:pre-wrap;font:inherit;font-size:14.5px;line-height:1.7;margin:0;color:var(--ink)}
.checks{display:flex;flex-wrap:wrap;gap:6px}
.sendline{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-top:12px;font-size:13px;color:var(--ink-3)}

details.fold{border-top:1px solid var(--line);margin-top:20px;padding-top:14px}
details.fold summary{cursor:pointer;font-size:13px;color:var(--ink-2);font-weight:550;list-style:none}
details.fold summary::-webkit-details-marker{display:none}
details.fold summary::before{content:"›";display:inline-block;width:14px;transition:transform .15s}
details.fold[open] summary::before{transform:rotate(90deg)}
.small{font-size:12.5px}.muted{color:var(--ink-3)}
.empty{padding:40px!important;text-align:center;color:var(--ink-3)}
.progress{list-style:none;margin:16px 0 0;padding:0;display:grid;gap:4px}
.progress:empty{display:none}
.progress li{display:flex;align-items:center;gap:10px;font-size:13px;padding:9px 12px;border-radius:8px;background:var(--raised)}
.progress .dot{width:7px;height:7px;border-radius:50%;background:var(--ink-3);flex:none}
.progress .run .dot{background:var(--accent);animation:pulse 1.2s ease-in-out infinite}
.progress .ok .dot{background:var(--green)}
@keyframes pulse{50%{opacity:.3}}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
@media (max-width:640px){main{padding:28px 16px 80px}.nav-in{padding:0 16px}h1{font-size:25px}
  .pad,.panel{padding-left:18px;padding-right:18px}.co-head{padding:18px 18px 0}.tabs{padding:0 10px}
  .recip .long{display:none}.hide-sm{display:none}.steps .step-ln{width:8px;margin:0 4px}}
"""

FONT = ('<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" '
        'href="https://fonts.gstatic.com" crossorigin><link rel="stylesheet" '
        'href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;550;600;650&display=swap">')


def page(title: str, body: str) -> str:
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{escape(title)}</title>{FONT}<style>{CSS}</style>'
            f'<script>document.documentElement.classList.add("js")</script></head>'
            f'<body>{nav()}<main>{body}</main></body></html>')


def nav() -> str:
    return (f'<nav class="nav"><div class="nav-in"><a class="logo" href="/"><span class="mark">S</span>Outreach</a>'
            f'<span class="sp"></span><span class="recip" title="send_email() can only address this inbox">'
            f'{icon("mail", 15)}<span><span class="long">Delivers only to </span>{escape(HARDCODED_RECIPIENT)}</span></span>'
            f'</div></nav>')


def _when(ts: Any, short: bool = False) -> str:
    try:
        d = datetime.fromisoformat(str(ts))
    except ValueError:
        return str(ts or "")
    return f"{d.day} {d.strftime('%b, %H:%M')}" if short else f"{d.day} {d.strftime('%B %Y, %H:%M UTC')}"


def _tag(v: Optional[str]) -> str:
    if v in VERDICTS:
        return f'<span class="tag t-{VERDICT_TONE[v]}">{VERDICT_LABEL[v]}</span>'
    return f'<span class="tag t-gray">{escape(v or "Incomplete")}</span>'


def _fav(domain: str) -> str:
    return (f'<img class="fav" alt="" loading="lazy" referrerpolicy="no-referrer" '
            f'src="https://www.google.com/s2/favicons?domain={escape(domain)}&amp;sz=64">')


def _meter(q: Dict[str, Any]) -> str:
    pct = round(float(q.get("weighted_score", 0)) * 100)
    return (f'<span class="meter" title="Go at {GO_THRESHOLD}"><span class="bar" aria-hidden="true"><i style="width:{pct}%">'
            f'</i><u style="left:{GO_THRESHOLD}%"></u></span><span class="num"><b>{pct}</b>'
            f'<span class="muted"> / 100</span></span></span>')


# ---------------- home ----------------

def home(runs: List[Dict[str, Any]], can_run: bool, steps: List[str]) -> str:
    seg = "".join(f'<input type="radio" name="until" id="u-{s}" value="{s}"{" checked" if s == steps[-1] else ""}>'
                  f'<label for="u-{s}">{STEP_LABEL.get(s, s)}</label>' for s in steps)
    disabled = ('' if can_run else '<div class="note err" style="margin:0 0 16px"><p><b>Runs are paused.</b> Add '
                '<code>GEMINI_API_KEY</code> in Vercel, then redeploy.</p></div>')
    composer = f"""
<h1>Outreach</h1>
<p class="lede">Paste the companies you want to look at. Each one is researched, scored against Sprinto's ICP and, if it
qualifies, gets the right contact, two pain points and a checked first email.</p>
<section class="card pad" style="margin-top:28px">
  {disabled}
  <label for="domains" class="label">Company domains, one per line (up to 15)</label>
  <textarea id="domains" placeholder="acme.io&#10;example-saas.com" spellcheck="false"></textarea>
  <div class="composer-foot">
    <div><div class="label" style="margin-bottom:6px">Run until</div><div class="seg" role="radiogroup" aria-label="Run until">{seg}</div></div>
    <button id="go" class="btn" {'disabled' if not can_run else ''}>Run pipeline {icon("arrow")}</button>
  </div>
  <ul id="progress" class="progress" aria-live="polite"></ul>
</section>"""
    rows = []
    for r in runs:
        ds = r.get("domains", [])
        companies = "".join(f'<span class="co" style="font-weight:450">{_fav(d)}{escape(d)}</span>' for d in ds[:3])
        more = f'<span class="muted small">+{len(ds) - 3} more</span>' if len(ds) > 3 else ""
        until = STEP_LABEL.get(str(r.get("settings", {}).get("until", "")), "")
        rows.append(f'<tr data-href="/runs/{escape(r["run_id"])}"><td style="white-space:nowrap">'
                    f'<a href="/runs/{escape(r["run_id"])}" style="font-weight:550">{escape(_when(r.get("created_at"), True) or r["run_id"])}</a>'
                    f'<div class="mono muted" style="font-size:11.5px">{escape(r["run_id"])}</div></td>'
                    f'<td><div style="display:flex;gap:6px 14px;flex-wrap:wrap;align-items:center">{companies}{more}</div></td>'
                    f'<td class="num hide-sm">{len(ds)}</td><td class="muted hide-sm">{escape(until)}</td></tr>')
    table = (f'<div class="section-h"><h2>Recent runs</h2><span class="sub">{len(runs)} shown</span></div>'
             f'<section class="card scroll"><table class="tbl rows"><thead><tr><th>Started</th><th>Companies</th>'
             f'<th class="hide-sm">Count</th><th class="hide-sm">Until</th></tr></thead><tbody>'
             f'{"".join(rows) or "<tr><td colspan=4 class=empty>No runs yet. Paste a few domains above to start.</td></tr>"}'
             f'</tbody></table></section>')
    return page("Outreach · Sprinto", composer + table + ADVANCE_JS + HOME_JS + ROW_JS)


ADVANCE_JS = """
<script>
async function advanceDomain(runId, d, until, report) {
  for (let unit = 0, busy = 0; unit < 30; unit++) {
    let r;
    try {
      const res = await fetch(`/api/runs/${runId}/domains/${encodeURIComponent(d)}/advance?until=${until}`, {method: 'POST'});
      r = await res.json();
      if (!res.ok) { report(`Error: ${r.detail || res.status}`); return; }
    } catch (e) { report('Network error, retrying…'); await new Promise(z => setTimeout(z, 5000)); continue; }
    report(`${r.stage}: ${r.message || ''}`);
    if (r.done) return;
    if (r.retry) {
      if (++busy > 6) { report(`${r.stage}: model still busy. Use Resume later.`); return; }
      report(`${r.stage}: model busy, retrying in 30s`);
      await new Promise(z => setTimeout(z, 30000));
    }
  }
}
</script>"""

HOME_JS = """
<script>
const go = document.getElementById('go'), prog = document.getElementById('progress');
const row = (cls, text) => { const li = document.createElement('li'); li.className = cls;
  li.innerHTML = '<span class="dot"></span><span></span>'; li.lastChild.textContent = text; return li; };
go && go.addEventListener('click', async () => {
  const domains = document.getElementById('domains').value.split('\\n').map(s => s.trim()).filter(Boolean);
  const until = (document.querySelector('input[name=until]:checked') || {}).value || 'send';
  if (!domains.length) { document.getElementById('domains').focus(); return; }
  go.disabled = true; prog.replaceChildren(row('run', 'Creating run…'));
  const r = await fetch('/api/runs', {method: 'POST', headers: {'Content-Type': 'application/json'},
                                      body: JSON.stringify({domains, until})});
  const run = await r.json();
  if (!r.ok) { prog.replaceChildren(row('', run.detail || 'Error')); go.disabled = false; return; }
  const items = run.domains.map(d => row('', `${d} · waiting`));
  prog.replaceChildren(...items);
  for (const [i, d] of run.domains.entries()) {
    items[i].className = 'run';
    await advanceDomain(run.run_id, d, until, msg => { items[i].lastChild.textContent = `${d} · ${msg}`; });
    items[i].className = 'ok';
  }
  location.href = `/runs/${run.run_id}`;
});
</script>"""

ROW_JS = """
<script>
document.querySelectorAll('tr[data-href]').forEach(tr => tr.addEventListener('click', e => {
  if (!e.target.closest('a,button')) location.href = tr.dataset.href; }));
</script>"""


# ---------------- run page ----------------

def _quotes(evidence: List[Dict[str, Any]], limit: int = 2) -> str:
    seen, out = set(), []
    for e in evidence:
        key = (e.get("quote") or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(f'<span class="quote">“{escape(key)}” <a href="{escape(e["source_url"])}" target="_blank" '
                   f'rel="noopener">Source</a></span>')
        if len(out) >= limit:
            break
    return "".join(out)


def _stepper(records: Dict[str, Any]) -> str:
    out = []
    for n, s in enumerate(STEP_ORDER):
        r = records.get(s)
        st = r.status if r else "todo"
        mark = icon("check", 10) if st == "ok" else icon("x", 10) if st == "error" else ""
        if n:
            out.append('<span class="step-ln" aria-hidden="true"></span>')
        out.append(f'<span class="step {st}" title="{STEP_LABEL[s]}: {st}"><span class="d">{mark}</span>{STEP_LABEL[s]}</span>')
    return f'<div class="steps" aria-label="Pipeline steps">{"".join(out)}</div>'


def _labels(scores, status):
    return [CRITERIA.get(s["criterion_id"], (s["criterion_id"],))[0] for s in scores if s["status"] == status]


def _headline(q: Dict[str, Any]) -> str:
    if q.get("short_circuit"):
        sc = q["short_circuit"].rstrip(".")
        return f"Stopped early: {sc[:1].lower() + sc[1:]}."
    scores = q.get("scores", [])
    if q["decision"] in ("GO", "GO_FLAGGED"):
        met = _labels(scores, "met")
        return "Qualifies: " + (", ".join(met[:4]) if met else "meets the threshold") + "."
    if q["decision"] == "MANUAL_REVIEW":
        return "Not enough public evidence to decide. Unknown: " + ", ".join(_labels(scores, "unknown")[:4]) + "."
    miss = _labels(scores, "not_met")
    return "Does not qualify: " + (", ".join(miss[:3]) if miss else "score is below the threshold") + "."


def _resume(run_id: str, domain: str, label: str = "Resume") -> str:
    return (f'<button class="btn quiet" data-resume="{escape(domain)}" data-run="{escape(run_id)}">'
            f'{icon("refresh", 14)}<span>{label}</span></button>')


def domain_card(domain: str, records: Dict[str, Any], run_id: str = "") -> str:
    q_rec, s_rec, e_rec = records.get("qualify"), records.get("scrape"), records.get("extract")
    failed = next((r for r in records.values() if r and r.status == "error"), None)
    q = q_rec.output["qualification"] if q_rec and q_rec.status == "ok" else None
    cid = "co-" + escape(domain.replace(".", "-"))

    head = [f'<div class="co-head"><div style="min-width:0;flex:1"><h3>{_fav(domain)}{escape(domain)}</h3>']
    if q:
        n = len(q.get("agent_steps", []))
        head.append(f'<p class="headline">{escape(_headline(q))}</p><div class="co-meta">{_meter(q)}'
                    f'<span>{q["unknown_weight_share"]:.0%} of weight unknown</span>'
                    f'<span>{n} page{"" if n == 1 else "s"} researched</span></div>')
    head.append(f'</div><div>{_tag(q["decision"] if q else None)}</div></div>')

    status = [f'<div style="padding:0 24px">{_stepper(records)}']
    if failed:
        status.append(f'<div class="note err"><p><b>{escape(STEP_LABEL.get(failed.step, failed.step))} failed.</b> '
                      f'{escape(failed.error or "")}</p>{_resume(run_id, domain) if run_id else ""}</div>')
    elif not q and run_id and records:
        status.append(f'<div class="note info"><p><b>Not finished.</b> Pick up where it stopped.</p>'
                      f'{_resume(run_id, domain, "Continue")}</div>')
    status.append("</div>")

    tabs: List[tuple] = []

    def add(key, label, html):
        if html:
            tabs.append((key, label, html))

    add("outreach", "Outreach", outreach_section(records))
    profile: Dict[str, Any] = {}
    if q:
        flags = ""
        if q.get("flags"):
            flags = ('<div class="panel-h">To double-check</div><div class="checks">' + "".join(
                f'<span class="tag t-amber plain">{icon("flag", 12)}{escape(f)}</span>' for f in q["flags"]) + "</div>")
        rows = []
        for sc in q["scores"]:
            label, weight = CRITERIA.get(sc["criterion_id"], (sc["criterion_id"], ""))
            name, tone = STATUS.get(sc["status"], (sc["status"], "gray"))
            rows.append(f'<tr><td style="min-width:170px"><div style="font-weight:550">{escape(label)}</div>'
                        f'<div class="mono muted" style="font-size:11px">{escape(sc["criterion_id"])}</div></td>'
                        f'<td class="muted num small" style="white-space:nowrap">{escape(weight)}</td>'
                        f'<td><span class="st c-{tone}">{name}</span></td>'
                        f'<td style="min-width:260px">{escape(sc["reason"])}{_quotes(sc.get("evidence", []))}</td></tr>')
        add("score", "Scorecard", '<div class="panel-h">Why: scorecard</div>'
            '<div class="scroll"><table class="tbl"><thead><tr><th>Criterion</th><th>Weight</th><th>Status</th>'
            '<th>Reason and evidence</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table></div>" + flags
            + f'<details class="fold"><summary>Decision rule</summary><p class="small muted">{escape(q_rec.note or "")}.</p>'
              f'<p class="small">{escape(q["decision_rule"])}</p></details>')
        loop = [f'<tr><td class="num muted">0</td><td class="muted">Start</td><td>Homepage</td>'
                f'<td>{escape(s_rec.note or "") if s_rec else ""}</td></tr>']
        for st in q["agent_steps"]:
            urls = "".join(f'<div><a class="u small" href="{escape(u)}" target="_blank" rel="noopener">{escape(u[:56])}</a></div>'
                           for u in st["urls"])
            loop.append(f'<tr><td class="num muted">{st["round"]}</td><td style="min-width:180px">{escape(st["question"])}'
                        f'<div class="muted small">Missing {escape(", ".join(st["missing_fields"]))}</div></td>'
                        f'<td style="min-width:140px">{escape(st["page_kind"].capitalize())}{urls}</td>'
                        f'<td style="min-width:220px">{escape(st["result_summary"])}</td></tr>')
        add("research", "Research", '<div class="panel-h">Research loop</div><div class="scroll"><table class="tbl">'
            '<thead><tr><th>#</th><th>Open question</th><th>Fetched</th><th>Result</th></tr></thead><tbody>'
            + "".join(loop) + "</tbody></table></div>")
        profile = q_rec.output.get("profile", {})
    elif e_rec and e_rec.status == "ok":
        profile = e_rec.output["profile"]
    data = []
    if profile:
        rows = "".join(
            f'<tr><td class="mono" style="font-size:12px">{escape(k)}</td><td>{escape(str(v["value"]))}'
            f'{_quotes(v.get("evidence", []), 1)}</td></tr>'
            for k, v in profile.items() if k != "domain" and isinstance(v, dict) and v.get("value") is not None)
        data.append(f'<div class="panel-h">Extracted facts</div><div class="scroll"><table class="tbl"><tbody>{rows}'
                    f'</tbody></table></div>')
    links = " · ".join(f'<a class="u" href="/api/runs/{escape(r.run_id)}/domains/{escape(domain)}/steps/{s}" '
                       f'target="_blank">{s}.json</a>' for s, r in records.items() if r)
    if links:
        data.append(f'<div class="panel-h">Raw trace</div><p class="small" style="margin:0">{links}</p>')
    add("data", "Data", "".join(data))

    if tabs:
        tab_html = ('<div class="tabs" role="tablist">' + "".join(
            f'<button class="tab" role="tab" id="{cid}-t-{k}" aria-controls="{cid}-p-{k}" '
            f'aria-selected="{"true" if i == 0 else "false"}">{lbl}</button>' for i, (k, lbl, _) in enumerate(tabs))
            + "</div>" + "".join(
            f'<div class="panel" role="tabpanel" id="{cid}-p-{k}" aria-labelledby="{cid}-t-{k}"{" hidden" if i else ""}>'
            f'{h}</div>' for i, (k, _, h) in enumerate(tabs)))
    else:
        tab_html = '<div style="height:22px"></div>'
    return f'<section class="card company" id="{cid}">' + "".join(head) + "".join(status) + tab_html + "</section>"


def outreach_section(records: Dict[str, Any]) -> str:
    """Steps 4-7: who, why them, the two pains, the email, and whether it was sent."""
    poc, pains, draft, send = (records.get(k) for k in ("poc", "pains", "draft", "send"))
    if not any((poc, pains, draft, send)):
        return ""
    out = []
    if draft and draft.status == "ok":
        d = draft.output["draft"]
        checks = draft.output.get("report", {}).get("checks", [])
        chips = "".join(
            f'<span class="tag {"t-green" if c["severity"] == "pass" else "t-amber" if c["severity"] == "warn" else "t-red"}">'
            f'{escape(c["check"])}</span>' for c in checks)
        send_html = ""
        if send:
            tone, label = {"ok": ("green", "Sent"), "skipped": ("gray", "Draft only"),
                           "error": ("red", "Send failed")}.get(send.status, ("gray", send.status))
            send_html = (f'<div class="sendline"><span class="tag t-{tone}">{label}</span>'
                         f'<span>{escape(send.note or send.error or "")}</span></div>')
        out.append(f'<div class="panel-h">Email draft</div><div class="mail"><div class="mail-h">'
                   f'<div><span class="k">To</span>{escape(d["to_name"])} '
                   f'<span class="muted">&lt;{escape(d.get("intended_address") or "n/a")}&gt;</span></div>'
                   f'<div><span class="k">Delivered to</span><span class="muted">{escape(HARDCODED_RECIPIENT)} only</span></div></div>'
                   f'<div class="mail-subj">{escape(d["subject"])}</div><pre class="mail-b">{escape(d["body"])}</pre></div>'
                   f'{send_html}<div class="panel-h">Checks</div><div class="checks">{chips}</div>'
                   f'<div class="panel-h">Hook</div><div class="small">{escape(d["hook"])}'
                   f'{_quotes(d.get("hook_evidence", []), 1)}</div>')
    elif draft and draft.status == "error":
        out.append(f'<div class="note err" style="margin-top:0"><p><b>Draft failed.</b> {escape(draft.error or "")}</p></div>')
    if poc:
        c = (poc.output or {}).get("chosen")
        out.append('<div class="panel-h">Contact</div>')
        if c:
            initials = (c["first_name"][:1] + (c.get("last_name") or "")[:1]).upper()
            out.append(f'<div class="tile person"><span class="avatar">{escape(initials)}</span><div style="min-width:0">'
                       f'<div class="nm">{escape(c["first_name"])} {escape(c.get("last_name") or "")}</div>'
                       f'<div class="rl">{escape(c.get("position") or "")}</div>'
                       f'<div class="small muted mono">{escape(c.get("email") or "")} · {escape(c.get("source", ""))}</div>'
                       f'<div class="why">{escape(poc.note or "")}</div></div></div>')
        else:
            out.append(f'<div class="note info" style="margin-top:0"><p>{escape(poc.note or "No contact found")}</p></div>')
    if pains and pains.status == "ok":
        cards = "".join(
            f'<div class="tile"><h4>{escape(pp["title"])}</h4><p>{escape(pp["why_this_person"])}</p>'
            f'<div class="ans"><span class="muted">Sprinto: </span>{escape(pp["sprinto_answer"])}</div>'
            f'{_quotes(pp.get("evidence", []), 1)}</div>'
            for pp in pains.output["pains"]["pains"])
        out.append(f'<div class="panel-h">Two pain points</div><div class="grid2">{cards}</div>')
    elif pains and pains.status == "error":
        out.append(f'<div class="note err"><p><b>Pain points failed.</b> {escape(pains.error or "")}</p></div>')
    if send and not (draft and draft.status == "ok"):
        out.append(f'<p class="small muted">{escape(send.note or send.error or send.status)}</p>')
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
        dash = '<span class="muted">—</span>'
        email = ('<span class="tag t-green">Sent</span>' if send and send.status == "ok"
                 else '<span class="tag t-gray">Draft ready</span>' if recs.get("draft") and recs["draft"].status == "ok"
                 else dash)
        who = (f'{escape(c["first_name"])} {escape(c.get("last_name") or "")}<div class="muted small">'
               f'{escape(c.get("position") or "")}</div>') if c else dash
        cid = "co-" + escape(d.replace(".", "-"))
        rows.append(f'<tr data-href="#{cid}"><td><a href="#{cid}" class="co">{_fav(d)}{escape(d)}</a></td>'
                    f'<td>{_tag(q["decision"] if q else None)}</td><td class="hide-sm">{_meter(q) if q else dash}</td>'
                    f'<td class="hide-sm">{who}</td><td>{email}</td></tr>')
    return (f'<div class="section-h"><h2>Overview</h2><span class="sub">Go at {GO_THRESHOLD} / 100</span></div>'
            f'<section class="card scroll"><table class="tbl rows"><thead><tr><th>Company</th><th>Verdict</th>'
            f'<th class="hide-sm">Score</th><th class="hide-sm">Contact</th><th>Email</th></tr></thead><tbody>{"".join(rows)}</tbody></table></section>')


RUN_JS = """
<script>
document.querySelectorAll('[role=tablist]').forEach(list => {
  const tabs = [...list.querySelectorAll('[role=tab]')];
  const pick = t => tabs.forEach(x => { const on = x === t; x.setAttribute('aria-selected', on);
    document.getElementById(x.getAttribute('aria-controls')).hidden = !on; });
  tabs.forEach((t, i) => { t.addEventListener('click', () => pick(t));
    t.addEventListener('keydown', e => { const k = {ArrowRight: 1, ArrowLeft: -1}[e.key];
      if (k) { const n = tabs[(i + k + tabs.length) % tabs.length]; n.focus(); pick(n); } }); });
});
document.querySelectorAll('[data-resume]').forEach(b => b.addEventListener('click', async () => {
  document.querySelectorAll('[data-resume]').forEach(x => x.disabled = true);
  const label = b.querySelector('span');
  await advanceDomain(b.dataset.run, b.dataset.resume, 'send', msg => { label.textContent = msg.slice(0, 60); });
  location.reload();
}));
</script>"""


def run_page(manifest: Dict[str, Any], records_by_domain: Dict[str, Dict[str, Any]]) -> str:
    counts = {k: 0 for k in (*VERDICTS, "Incomplete")}
    for recs in records_by_domain.values():
        q = recs.get("qualify")
        counts[q.output["qualification"]["decision"] if q and q.status == "ok" else "Incomplete"] += 1
    stats = "".join(f'<div class="stat"><b class="num">{n}</b>{_tag(k)}</div>' for k, n in counts.items())
    s = manifest.get("settings", {})
    run_id = manifest["run_id"]
    n = len(manifest.get("domains", []))
    body = (f'<a class="crumb" href="/">{icon("back", 14)}All runs</a>'
            f'<h1>{n} compan{"y" if n == 1 else "ies"}</h1>'
            f'<div class="meta"><span>{escape(_when(manifest.get("created_at")))}</span>'
            f'<span>{escape(str(s.get("provider", "anthropic")).capitalize())} · {escape(str(s.get("model")))}</span>'
            f'<span>Prompt {escape(str(s.get("prompt_version")))}</span><span class="mono">{escape(run_id)}</span></div>'
            f'<section class="card stats">{stats}</section>' + _overview(manifest, records_by_domain)
            + '<div class="section-h"><h2>Companies</h2><span class="sub">Verdict, reasons, contact and email</span></div>')
    body += "".join(domain_card(d, records_by_domain.get(d, {}), run_id) for d in manifest.get("domains", []))
    return page(f"Run · {_when(manifest.get('created_at'), short=True)}", body + ADVANCE_JS + RUN_JS + ROW_JS)
