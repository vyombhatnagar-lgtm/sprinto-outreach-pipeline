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
/* run page: calm, collapsible */
.dist{display:flex;gap:3px;height:8px;margin-top:26px;border-radius:4px;overflow:hidden}
.dist i{display:block;min-width:6px;border-radius:2px}
.bg-green{background:var(--green)}.bg-amber{background:var(--amber)}.bg-red{background:var(--red)}
.bg-violet{background:var(--violet)}.bg-gray{background:var(--line-2)}
.legend{display:flex;flex-wrap:wrap;gap:6px 20px;margin-top:12px;font-size:13px;color:var(--ink-2)}
.lg{display:inline-flex;align-items:center;gap:7px}.lg .dot{width:8px;height:8px;border-radius:50%}
.lg b{color:var(--ink);font-weight:600}
details.company{margin-top:10px;scroll-margin-top:72px;box-shadow:none}
details.company[open]{box-shadow:var(--shadow)}
.co-sum{list-style:none;cursor:pointer;display:grid;grid-template-columns:minmax(150px,220px) 1fr auto;align-items:center;
  gap:16px;padding:16px 20px;border-radius:var(--r)}
.co-sum::-webkit-details-marker{display:none}
.co-sum:hover{background:var(--hover)}
details[open] .co-sum{border-bottom:1px solid var(--line);border-radius:var(--r) var(--r) 0 0}
.co-name{display:flex;align-items:center;gap:10px;font-weight:600;letter-spacing:-.01em;min-width:0}
.co-name span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.co-line{color:var(--ink-2);font-size:13.5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}
.co-right{display:flex;align-items:center;gap:12px}
.chev{width:8px;height:8px;border-right:1.5px solid var(--ink-3);border-bottom:1.5px solid var(--ink-3);transform:rotate(-45deg);transition:transform .15s}
details[open] .chev{transform:rotate(45deg)}
.co-body{padding:4px 0 6px}
.co-body>.co-meta,.co-body>.steps,.co-body>.note{margin-left:20px;margin-right:20px}
.co-body .tabs{padding:0 14px;margin-top:14px}
.crits{list-style:none;margin:0;padding:0}
.crit{padding:14px 0;border-bottom:1px solid var(--line)}.crit:first-child{padding-top:0}
.crit-h{display:flex;align-items:center;gap:10px}
.crit-h .st{color:var(--ink);font-weight:550}.crit-h .st.c-green::before{background:var(--green)}
.crit-h .st.c-red::before{background:var(--red)}.crit-h .st.c-amber::before{background:var(--amber)}
.crit-w{color:var(--ink-3);font-size:12px}
.crit-s{margin-left:auto;font-size:12.5px;font-weight:550}
.crit p{margin:6px 0 0 14px;color:var(--ink-2);font-size:13.5px;max-width:720px}
details.src{margin:6px 0 0 14px}details.src summary{cursor:pointer;color:var(--ink-3);font-size:12.5px;list-style:none}
details.src summary::-webkit-details-marker{display:none}details.src summary:hover{color:var(--ink)}
.unknowns{margin-top:16px;padding:14px 16px;border-radius:10px;background:var(--raised);font-size:13.5px;display:grid;gap:4px}
.notes{margin:14px 0 0;padding-left:18px;color:var(--ink-3);font-size:12.5px}
.timeline{list-style:none;margin:0;padding:0}
.timeline li{display:flex;gap:14px;padding:0 0 18px;position:relative}
.timeline li:not(:last-child)::before{content:"";position:absolute;left:11px;top:26px;bottom:4px;width:1px;background:var(--line-2)}
.tl-n{width:23px;height:23px;border-radius:50%;border:1px solid var(--line-2);display:grid;place-items:center;font-size:11.5px;color:var(--ink-3);flex:none;background:var(--surface)}
.tl-q{font-weight:550}.tl-r{color:var(--ink-3);font-size:13px;margin-top:2px}
.kvs{display:grid;gap:0}.kv{display:grid;grid-template-columns:190px 1fr;gap:12px;padding:9px 0;border-bottom:1px solid var(--line);font-size:13.5px}
.kv:last-child{border-bottom:0}.kv .k{color:var(--ink-3);font-size:12px}
.foot{margin-top:40px}
@media (max-width:640px){.co-sum{grid-template-columns:1fr auto;gap:6px 12px;padding:14px 16px}
  .co-line{grid-column:1/-1;grid-row:2;white-space:normal}.co-body>.co-meta,.co-body>.steps,.co-body>.note{margin-left:16px;margin-right:16px}
  .kv{grid-template-columns:1fr;gap:2px}}
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
    goes = bool(q and q["decision"] in ("GO", "GO_FLAGGED"))
    has_outreach = any(records.get(k) for k in ("poc", "pains", "draft", "send"))
    is_open = goes or has_outreach or bool(failed)

    headline = escape(_headline(q)) if q else (
        f"{escape(STEP_LABEL.get(failed.step, failed.step))} failed" if failed else "Not finished")
    summary = (f'<summary class="co-sum"><span class="co-name">{_fav(domain)}<span>{escape(domain)}</span></span>'
               f'<span class="co-line">{headline}</span>'
               f'<span class="co-right">{_tag(q["decision"] if q else None)}<span class="chev" aria-hidden="true"></span></span>'
               f'</summary>')

    body = ['<div class="co-body">']
    if q:
        n = len(q.get("agent_steps", []))
        body.append(f'<div class="co-meta">{_meter(q)}<span>{n} page{"" if n == 1 else "s"} researched</span>'
                    f'<span>{q["unknown_weight_share"]:.0%} unknown</span></div>')
    if goes or has_outreach:
        body.append(_stepper(records))
    if failed:
        body.append(f'<div class="note err"><p><b>{escape(STEP_LABEL.get(failed.step, failed.step))} failed.</b> '
                    f'{escape(_short_err(failed.error))}</p>{_resume(run_id, domain) if run_id else ""}</div>')
    elif not q and run_id and records:
        body.append(f'<div class="note info"><p><b>Not finished.</b> Pick up where it stopped.</p>'
                    f'{_resume(run_id, domain, "Continue")}</div>')

    tabs: List[tuple] = []

    def add(key, label, html):
        if html:
            tabs.append((key, label, html))

    add("outreach", "Outreach", outreach_section(records))
    profile: Dict[str, Any] = {}
    if q:
        add("score", "Why", _scorecard(q, q_rec))
        add("research", "Research", _research(q, s_rec))
        profile = q_rec.output.get("profile", {})
    elif e_rec and e_rec.status == "ok":
        profile = e_rec.output["profile"]
    add("data", "Data", _data(domain, records, profile))

    if tabs:
        body.append('<div class="tabs" role="tablist">' + "".join(
            f'<button class="tab" role="tab" id="{cid}-t-{k}" aria-controls="{cid}-p-{k}" '
            f'aria-selected="{"true" if i == 0 else "false"}">{lbl}</button>' for i, (k, lbl, _) in enumerate(tabs))
            + "</div>" + "".join(
            f'<div class="panel" role="tabpanel" id="{cid}-p-{k}" aria-labelledby="{cid}-t-{k}"{" hidden" if i else ""}>'
            f'{h}</div>' for i, (k, _, h) in enumerate(tabs)))
    body.append("</div>")
    return (f'<details class="card company" id="{cid}"{" open" if is_open else ""}>' + summary + "".join(body)
            + "</details>")


def _short_err(err: Optional[str]) -> str:
    e = (err or "").replace("LLMError: ", "")
    if "busy" in e.lower() or "quota" in e.lower() or "unreachable" in e:
        return "The AI model was busy or out of quota. Resume to try again."
    return e[:220]


_NOISE = ("unknown, counted as 0", "weight is unknown", "not confirmed, assumed met")


def _scorecard(q: Dict[str, Any], q_rec) -> str:
    known, unknown = [], []
    for sc in q["scores"]:
        label, weight = CRITERIA.get(sc["criterion_id"], (sc["criterion_id"], ""))
        if sc["status"] == "unknown":
            unknown.append(label)
            continue
        name, tone = STATUS.get(sc["status"], (sc["status"], "gray"))
        quotes = _quotes(sc.get("evidence", []))
        n = quotes.count('class="quote"')
        src = (f'<details class="src"><summary>{n} source{"" if n == 1 else "s"}</summary>{quotes}</details>'
               if n else "")
        w = "gate" if weight == "Gate" else (weight.replace("Gate · ", "gate · ") + " pts") if weight else ""
        known.append(f'<li class="crit"><div class="crit-h"><span class="st c-{tone}">{escape(label)}</span>'
                     f'<span class="crit-w">{escape(w)}</span><span class="crit-s c-{tone}">{name}</span></div>'
                     f'<p>{escape(sc["reason"])}</p>{src}</li>')
    html = f'<ul class="crits">{"".join(known)}</ul>'
    if unknown:
        html += (f'<div class="unknowns"><span class="label">Not found on public pages</span>'
                 f'<div>{escape(", ".join(unknown))}</div><div class="small muted">Most count as 0 points; the certification gap is assumed and flagged.</div></div>')
    notes = [f for f in q.get("flags", []) if not any(x in f for x in _NOISE)]
    if notes:
        html += '<ul class="notes">' + "".join(f"<li>{escape(f)}</li>" for f in notes) + "</ul>"
    html += (f'<details class="fold"><summary>How the verdict is decided</summary><p class="small muted">'
             f'{escape(q_rec.note or "")}.</p><p class="small">{escape(q["decision_rule"])}</p></details>')
    return html


def _research(q: Dict[str, Any], s_rec) -> str:
    items = [f'<li><span class="tl-n">0</span><div><div class="tl-q">Homepage</div>'
             f'<div class="tl-r">{escape(s_rec.note or "") if s_rec else ""}</div></div></li>']
    for st in q["agent_steps"]:
        links = " ".join(f'<a class="u" href="{escape(u)}" target="_blank" rel="noopener">{escape(_path(u))}</a>'
                         for u in st["urls"])
        items.append(f'<li><span class="tl-n">{st["round"]}</span><div><div class="tl-q">{escape(st["question"])}</div>'
                     f'<div class="tl-r">{escape(st["page_kind"].capitalize())} {links} · {escape(st["result_summary"])}</div>'
                     f'</div></li>')
    return f'<ol class="timeline">{"".join(items)}</ol>'


def _path(u: str) -> str:
    try:
        rest = u.split("://", 1)[1]
        p = "/" + rest.split("/", 1)[1] if "/" in rest else "/"
        return p if len(p) < 40 else p[:38] + "…"
    except IndexError:
        return u[:40]


def _data(domain: str, records: Dict[str, Any], profile: Dict[str, Any]) -> str:
    out = []
    if profile:
        rows = "".join(
            f'<div class="kv"><span class="k mono">{escape(k)}</span><span>{escape(str(v["value"]))}</span></div>'
            for k, v in profile.items() if k != "domain" and isinstance(v, dict) and v.get("value") is not None)
        out.append(f'<div class="panel-h">Extracted facts</div><div class="kvs">{rows}</div>')
    links = " · ".join(f'<a class="u" href="/api/runs/{escape(r.run_id)}/domains/{escape(domain)}/steps/{s}" '
                       f'target="_blank">{s}</a>' for s, r in records.items() if r)
    if links:
        out.append(f'<div class="panel-h">Raw trace (JSON)</div><p class="small" style="margin:0">{links}</p>')
    return "".join(out)


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
    rows, any_contact, any_email = [], False, False
    for d in manifest.get("domains", []):
        recs = records_by_domain.get(d, {})
        poc = recs.get("poc")
        any_contact |= bool(poc and (poc.output or {}).get("chosen"))
        any_email |= bool(recs.get("draft") and recs["draft"].status == "ok")
    for d in manifest.get("domains", []):
        recs = records_by_domain.get(d, {})
        q = recs.get("qualify")
        q = q.output["qualification"] if q and q.status == "ok" else None
        poc = recs.get("poc")
        c = (poc.output or {}).get("chosen") if poc else None
        send = recs.get("send")
        dash = '<span class="muted">—</span>'
        cid = "co-" + escape(d.replace(".", "-"))
        score = f'<b>{round(q["weighted_score"] * 100)}</b>' if q else dash
        cells = [f'<td><a href="#{cid}" class="co">{_fav(d)}{escape(d)}</a></td>',
                 f'<td>{_tag(q["decision"] if q else None)}</td>',
                 f'<td class="hide-sm num">{score}</td>']
        if any_contact:
            who = (escape(c["first_name"] + " " + (c.get("last_name") or "")) + '<div class="muted small">'
                   + escape(c.get("position") or "") + "</div>") if c else dash
            cells.append(f'<td class="hide-sm">{who}</td>')
        if any_email:
            cells.append('<td>' + ('<span class="tag t-green">Sent</span>' if send and send.status == "ok"
                                   else '<span class="tag t-gray">Draft</span>' if recs.get("draft") and recs["draft"].status == "ok"
                                   else dash) + '</td>')
        rows.append(f'<tr data-open="{cid}">{"".join(cells)}</tr>')
    head = ('<th>Company</th><th>Verdict</th><th class="hide-sm">Score</th>'
            + ('<th class="hide-sm">Contact</th>' if any_contact else "") + ('<th>Email</th>' if any_email else ""))
    return (f'<section class="card scroll" style="margin-top:28px"><table class="tbl rows"><thead><tr>{head}</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></section>')


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
const openCo = id => { const el = document.getElementById(id); if (!el) return; el.open = true;
  el.scrollIntoView({behavior: 'smooth', block: 'start'}); };
document.querySelectorAll('tr[data-open]').forEach(tr => tr.addEventListener('click', e => {
  e.preventDefault(); openCo(tr.dataset.open); history.replaceState(null, '', '#' + tr.dataset.open); }));
if (location.hash) openCo(location.hash.slice(1));
document.querySelectorAll('[data-resume]').forEach(b => b.addEventListener('click', async e => {
  e.preventDefault();
  document.querySelectorAll('[data-resume]').forEach(x => x.disabled = true);
  const label = b.querySelector('span');
  await advanceDomain(b.dataset.run, b.dataset.resume, 'send', msg => { label.textContent = msg.slice(0, 60); });
  location.reload();
}));
</script>"""


def _distribution(counts: Dict[str, int]) -> str:
    total = sum(counts.values()) or 1
    tone = {**VERDICT_TONE, "Incomplete": "gray"}
    segs = "".join(f'<i class="bg-{tone[k]}" style="flex:{n}" title="{n} {VERDICT_LABEL.get(k, k)}"></i>'
                   for k, n in counts.items() if n)
    legend = "".join(f'<span class="lg"><span class="dot bg-{tone[k]}"></span><b class="num">{n}</b> '
                     f'{VERDICT_LABEL.get(k, k)}</span>' for k, n in counts.items() if n)
    return f'<div class="dist" aria-label="Verdicts">{segs}</div><div class="legend">{legend}</div>' if total else ""


def run_page(manifest: Dict[str, Any], records_by_domain: Dict[str, Dict[str, Any]]) -> str:
    counts = {k: 0 for k in (*VERDICTS, "Incomplete")}
    for recs in records_by_domain.values():
        q = recs.get("qualify")
        counts[q.output["qualification"]["decision"] if q and q.status == "ok" else "Incomplete"] += 1
    s = manifest.get("settings", {})
    run_id = manifest["run_id"]
    n = len(manifest.get("domains", []))
    body = (f'<a class="crumb" href="/">{icon("back", 14)}All runs</a>'
            f'<h1>{n} compan{"y" if n == 1 else "ies"}</h1>'
            f'<div class="meta"><span>{escape(_when(manifest.get("created_at")))}</span>'
            f'<span>{escape(str(s.get("model")))}</span></div>'
            + _distribution(counts) + _overview(manifest, records_by_domain)
            + '<div class="section-h"><h2>Companies</h2><span class="sub">Open one for the reasons, contact and email</span></div>')
    body += "".join(domain_card(d, records_by_domain.get(d, {}), run_id) for d in manifest.get("domains", []))
    body += (f'<p class="foot small muted">Run <span class="mono">{escape(run_id)}</span> · prompt '
             f'{escape(str(s.get("prompt_version")))} · {escape(str(s.get("provider", "")))}</p>')
    return page(f"Run · {_when(manifest.get('created_at'), short=True)}", body + ADVANCE_JS + RUN_JS)
