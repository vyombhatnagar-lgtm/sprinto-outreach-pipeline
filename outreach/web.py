"""HTML for the dashboard (server-rendered, no build step). Every value is escaped.

Reading order mirrors a reviewer's questions: what was decided (numbers, overview),
why (reasons), who and what we'd send (outreach), how we got there (research, data).
Sounds are synthesized in the browser (Web Audio, no files) and can be muted.
"""
from datetime import datetime
from html import escape
from typing import Any, Dict, List, Optional

from .config import HARDCODED_RECIPIENT
from .models import STEP_ORDER

VERDICTS = ("GO", "GO_FLAGGED", "NO_GO", "MANUAL_REVIEW")
VERDICT_LABEL = {"GO": "Go", "GO_FLAGGED": "Go, flagged", "NO_GO": "No go", "MANUAL_REVIEW": "Needs review",
                 "Incomplete": "Incomplete"}
VERDICT_TONE = {"GO": "green", "GO_FLAGGED": "amber", "NO_GO": "red", "MANUAL_REVIEW": "violet", "Incomplete": "gray"}
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
    "refresh": '<path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 4v7h-7"/>',
    "shield": '<path d="M12 3 4.5 6v5.5c0 4.6 3.2 8.3 7.5 9.5 4.3-1.2 7.5-4.9 7.5-9.5V6L12 3Z"/><path d="m8.8 12 2.2 2.2 4.2-4.4"/>',
    "search": '<circle cx="11" cy="11" r="6.5"/><path d="m20 20-4.2-4.2"/>',
    "target": '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="4"/><circle cx="12" cy="12" r=".8" fill="currentColor"/>',
    "send": '<path d="M21 3 10 14"/><path d="M21 3 14.5 21l-4.5-7-7-4.5L21 3Z"/>',
    "gauge": '<path d="M4.5 17a8.5 8.5 0 1 1 15 0"/><path d="m12 13 3.5-4"/>',
    "sound": '<path d="M4 9.5h3.5L12 6v12l-4.5-3.5H4z"/><path d="M15.5 9a4.2 4.2 0 0 1 0 6M18 6.5a8 8 0 0 1 0 11"/>',
    "mute": '<path d="M4 9.5h3.5L12 6v12l-4.5-3.5H4z"/><path d="m16 10 4 4M20 10l-4 4"/>',
    "user": '<circle cx="12" cy="8" r="3.5"/><path d="M5 20c1.2-3.5 4-5 7-5s5.8 1.5 7 5"/>',
}


def icon(name: str, size: int = 16) -> str:
    return (f'<svg class="i" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            f'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{ICON[name]}</svg>')


CSS = """
:root{color-scheme:light dark;
  --bg:#f4f5fa;--surface:#ffffff;--raised:#f3f4f9;--hover:#eef0f7;
  --ink:#0e1430;--ink-2:#47506f;--ink-3:#8a91aa;--line:rgba(14,20,48,.08);--line-2:rgba(14,20,48,.15);
  --brand:#ff5a36;--brand-2:#ff8f3f;--brand-soft:rgba(255,90,54,.10);--accent:#4f46e5;--navy:#0c1330;
  --green:#16a34a;--green-bg:#e8f7ee;--amber:#c27803;--amber-bg:#fdf3dc;--red:#e0392b;--red-bg:#fdebe9;
  --violet:#6d4ae8;--violet-bg:#f0ebfe;--gray:#6f7590;--gray-bg:#eef0f5;
  --shadow:0 1px 2px rgba(14,20,48,.05),0 8px 24px rgba(14,20,48,.06);
  --shadow-lift:0 2px 4px rgba(14,20,48,.06),0 16px 40px rgba(14,20,48,.12);
  --r:16px;--r-sm:10px;
}
@media (prefers-color-scheme:dark){:root{
  --bg:#090d1d;--surface:#10162c;--raised:#151c36;--hover:#1a2242;
  --ink:#eef0f8;--ink-2:#b4bad2;--ink-3:#7c83a1;--line:rgba(255,255,255,.07);--line-2:rgba(255,255,255,.14);
  --brand-soft:rgba(255,90,54,.16);--accent:#8b85ff;
  --green:#4ade80;--green-bg:rgba(74,222,128,.12);--amber:#fbbf24;--amber-bg:rgba(251,191,36,.12);
  --red:#ff7a6b;--red-bg:rgba(255,122,107,.13);--violet:#a78bfa;--violet-bg:rgba(167,139,250,.14);
  --gray:#9aa0ba;--gray-bg:rgba(255,255,255,.06);--shadow:0 1px 2px rgba(0,0,0,.4);--shadow-lift:0 12px 36px rgba(0,0,0,.5)}}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%;scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--ink);
  font:14.5px/1.55 "Inter",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  font-feature-settings:"cv11","ss01";-webkit-font-smoothing:antialiased;letter-spacing:-.006em}
a{color:inherit;text-decoration:none}a.u{color:var(--accent)}a.u:hover{text-decoration:underline}
.i{flex:none;vertical-align:-3px}
:focus-visible{outline:2px solid var(--brand);outline-offset:2px;border-radius:6px}
.num{font-variant-numeric:tabular-nums}code,.mono{font:12.5px/1.5 ui-monospace,"SF Mono",Menlo,monospace;overflow-wrap:anywhere}
.small{font-size:12.5px}.muted{color:var(--ink-3)}

/* nav */
.nav{position:sticky;top:0;z-index:20;background:color-mix(in srgb,var(--navy) 88%,transparent);color:#fff;
  backdrop-filter:saturate(160%) blur(14px);-webkit-backdrop-filter:saturate(160%) blur(14px);border-bottom:1px solid rgba(255,255,255,.08)}
.nav-in{max-width:1160px;margin:0 auto;padding:0 24px;height:58px;display:flex;align-items:center;gap:14px}
.logo{display:flex;align-items:center;gap:10px;font-weight:650;letter-spacing:-.015em}
.mark{width:28px;height:28px;border-radius:8px;background:linear-gradient(135deg,var(--brand),var(--brand-2));display:grid;place-items:center;
  color:#fff;box-shadow:0 4px 14px rgba(255,90,54,.45)}
.logo small{font-weight:500;color:rgba(255,255,255,.55);margin-left:2px}
.nav .sp{flex:1}
.recip{display:flex;align-items:center;gap:7px;color:rgba(255,255,255,.62);font-size:12.5px;min-width:0}
.recip>span{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.iconbtn{appearance:none;border:1px solid rgba(255,255,255,.14);background:rgba(255,255,255,.06);color:#fff;width:34px;height:34px;
  border-radius:10px;display:grid;place-items:center;cursor:pointer;transition:background .15s,transform .1s}
.iconbtn:hover{background:rgba(255,255,255,.14)}.iconbtn:active{transform:scale(.94)}

main{max-width:1160px;margin:0 auto;padding:28px 24px 96px}

/* hero */
.hero{position:relative;overflow:hidden;border-radius:22px;color:#fff;padding:40px 40px 72px;
  background:radial-gradient(900px 380px at 90% -20%,rgba(255,90,54,.55),transparent 60%),
             radial-gradient(700px 320px at -10% 120%,rgba(99,80,255,.55),transparent 60%),var(--navy);
  box-shadow:0 20px 60px rgba(12,19,48,.25)}
.hero::before{content:"";position:absolute;inset:0;opacity:.18;pointer-events:none;
  background-image:linear-gradient(rgba(255,255,255,.12) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.12) 1px,transparent 1px);
  background-size:36px 36px;mask-image:radial-gradient(ellipse at 70% 0%,#000 20%,transparent 70%)}
.hero>*{position:relative}
.eyebrow{display:inline-flex;align-items:center;gap:8px;font-size:12px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;
  color:#ffd7cc;background:rgba(255,90,54,.18);border:1px solid rgba(255,140,110,.35);padding:5px 11px;border-radius:999px}
.hero h1{font-size:40px;line-height:1.08;letter-spacing:-.035em;font-weight:700;margin:16px 0 0;max-width:720px}
.hero h1 em{font-style:normal;background:linear-gradient(90deg,#ff8f6b,#ffc078);-webkit-background-clip:text;background-clip:text;color:transparent}
.hero p{color:rgba(255,255,255,.72);font-size:15.5px;margin:12px 0 0;max-width:620px}
.hero .crumb{color:rgba(255,255,255,.6)}.hero .crumb:hover{color:#fff}
.hero-meta{display:flex;flex-wrap:wrap;gap:6px 16px;color:rgba(255,255,255,.6);font-size:12.5px;margin-top:10px}

/* KPI tiles */
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-top:-34px;padding:0 18px;position:relative;z-index:2}
.kpi{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);padding:18px 18px 16px;box-shadow:var(--shadow);
  transition:transform .2s cubic-bezier(.2,.8,.2,1),box-shadow .2s}
.kpi:hover{transform:translateY(-3px);box-shadow:var(--shadow-lift)}
.kpi-top{display:flex;align-items:center;justify-content:space-between;color:var(--ink-3);font-size:12.5px;font-weight:550}
.kpi-ic{width:30px;height:30px;border-radius:9px;display:grid;place-items:center}
.kpi b{display:block;font-size:34px;line-height:1;font-weight:700;letter-spacing:-.035em;margin-top:14px}
.kpi b small{font-size:16px;color:var(--ink-3);font-weight:600;letter-spacing:-.01em;margin-left:2px}
.kpi .sub{font-size:12.5px;color:var(--ink-3);margin-top:8px}
.ic-brand{background:var(--brand-soft);color:var(--brand)}.ic-green{background:var(--green-bg);color:var(--green)}
.ic-violet{background:var(--violet-bg);color:var(--violet)}.ic-amber{background:var(--amber-bg);color:var(--amber)}
@media (max-width:860px){.kpis{grid-template-columns:repeat(2,1fr)}}

.section-h{display:flex;align-items:baseline;justify-content:space-between;gap:12px;margin:40px 0 14px}
h2{font-size:16px;font-weight:650;letter-spacing:-.015em;margin:0}
.section-h .sub{color:var(--ink-3);font-size:13px}
.label{font-size:12px;color:var(--ink-3);font-weight:550}
.card{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);box-shadow:var(--shadow)}
.pad{padding:24px}
.grid-main{display:grid;grid-template-columns:1.6fr 1fr;gap:16px;margin-top:28px}
@media (max-width:860px){.grid-main{grid-template-columns:1fr}}

/* buttons */
.btn{appearance:none;font:inherit;font-weight:600;display:inline-flex;align-items:center;gap:8px;height:42px;padding:0 18px;
  border-radius:12px;border:0;color:#fff;cursor:pointer;position:relative;overflow:hidden;
  background:linear-gradient(135deg,var(--brand),var(--brand-2));box-shadow:0 6px 18px rgba(255,90,54,.35);
  transition:transform .12s,box-shadow .2s,filter .2s}
.btn:hover{filter:brightness(1.05);box-shadow:0 10px 26px rgba(255,90,54,.45)}.btn:active{transform:scale(.97)}
.btn:disabled{opacity:.5;cursor:default;box-shadow:none}
.btn .kbd{font-size:11px;font-weight:600;opacity:.75;border:1px solid rgba(255,255,255,.4);border-radius:5px;padding:0 5px;margin-left:4px}
.btn.quiet{background:var(--surface);color:var(--ink);border:1px solid var(--line-2);height:34px;padding:0 12px;font-size:13px;box-shadow:none}
.btn.quiet:hover{background:var(--hover)}
.ripple{position:absolute;border-radius:50%;transform:scale(0);background:rgba(255,255,255,.45);animation:rip .6s ease-out forwards;pointer-events:none}
@keyframes rip{to{transform:scale(4);opacity:0}}

/* composer */
textarea{width:100%;font:inherit;color:var(--ink);background:var(--raised);border:1.5px solid var(--line);
  border-radius:12px;padding:14px 16px;transition:border-color .15s,background .15s,box-shadow .15s;margin-top:10px;
  min-height:150px;resize:vertical;font-family:ui-monospace,"SF Mono",Menlo,monospace;font-size:13.5px;line-height:1.75}
textarea:focus{outline:none;border-color:var(--brand);background:var(--surface);box-shadow:0 0 0 4px var(--brand-soft)}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px;min-height:26px}
.chip{display:inline-flex;align-items:center;gap:6px;font-size:12.5px;padding:3px 10px 3px 4px;border-radius:999px;background:var(--raised);
  border:1px solid var(--line);animation:pop .25s cubic-bezier(.2,1.4,.4,1)}
.chip img{width:16px;height:16px;border-radius:4px}
@keyframes pop{from{transform:scale(.6);opacity:0}}
.composer-foot{display:flex;align-items:flex-end;justify-content:space-between;gap:14px;flex-wrap:wrap;margin-top:16px}
.seg{display:inline-flex;background:var(--raised);border:1px solid var(--line);border-radius:12px;padding:3px;gap:2px;flex-wrap:wrap}
.seg input{position:absolute;opacity:0;pointer-events:none}
.seg label{font-size:12.5px;padding:6px 10px;border-radius:9px;color:var(--ink-2);cursor:pointer;white-space:nowrap;transition:background .15s}
.seg label:hover{background:var(--hover)}
.seg input:checked+label{background:var(--surface);color:var(--ink);box-shadow:0 1px 3px rgba(0,0,0,.12);font-weight:600}
.seg input:focus-visible+label{outline:2px solid var(--brand)}

/* live progress */
.live{list-style:none;margin:16px 0 0;padding:0;display:grid;gap:8px}
.live:empty{display:none}
.live li{display:grid;grid-template-columns:minmax(120px,190px) 1fr auto;align-items:center;gap:14px;padding:12px 14px;
  border-radius:12px;background:var(--raised);border:1px solid var(--line);font-size:13px;animation:pop .3s ease}
.live .nm{display:flex;align-items:center;gap:8px;font-weight:600;min-width:0}.live .nm span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.live .msg{color:var(--ink-3);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12.5px;min-width:0}
.pips{display:flex;gap:4px}.pips i{width:16px;height:6px;border-radius:3px;background:var(--line-2);transition:background .3s,transform .3s}
.pips i.on{background:linear-gradient(90deg,var(--brand),var(--brand-2))}.pips i.now{animation:pulse 1s ease-in-out infinite}
.live .msg-row{display:grid;gap:6px;min-width:0}
@keyframes pulse{50%{opacity:.35}}
@media (max-width:640px){.live li{grid-template-columns:1fr auto}.live .msg-row{grid-column:1/-1}}

/* donut */
.donut-wrap{display:flex;align-items:center;gap:22px;flex-wrap:wrap}
.donut{width:150px;height:150px;flex:none}
.donut circle{fill:none;stroke-width:16;transition:stroke-dasharray 1s cubic-bezier(.2,.8,.2,1)}
.donut text{fill:var(--ink);font-weight:700;font-size:26px;letter-spacing:-.03em}
.donut .lbl{fill:var(--ink-3);font-size:10px;font-weight:600;letter-spacing:.04em}
.leg{display:grid;gap:8px;font-size:13px;flex:1;min-width:150px}
.leg div{display:flex;align-items:center;gap:8px}.leg b{margin-left:auto;font-weight:650}
.dot{width:9px;height:9px;border-radius:50%;flex:none}
.bg-green{background:var(--green)}.bg-amber{background:var(--amber)}.bg-red{background:var(--red)}
.bg-violet{background:var(--violet)}.bg-gray{background:var(--line-2)}
.funnel{display:grid;gap:10px;margin-top:22px}
.fn{display:grid;grid-template-columns:110px 1fr 36px;align-items:center;gap:10px;font-size:12.5px;color:var(--ink-2)}
.fn .tr{height:8px;border-radius:4px;background:var(--raised);overflow:hidden}
.fn .tr i{display:block;height:100%;border-radius:4px;background:linear-gradient(90deg,var(--brand),var(--brand-2));width:0;transition:width 1s cubic-bezier(.2,.8,.2,1)}
.fn b{text-align:right;color:var(--ink)}

/* tags */
.tag{display:inline-flex;align-items:center;gap:6px;min-height:24px;padding:2px 10px;border-radius:999px;font-size:12px;font-weight:600;white-space:nowrap}
.tag::before{content:"";width:6px;height:6px;border-radius:50%;background:currentColor;flex:none}
.t-green{color:var(--green);background:var(--green-bg)}.t-amber{color:var(--amber);background:var(--amber-bg)}
.t-red{color:var(--red);background:var(--red-bg)}.t-violet{color:var(--violet);background:var(--violet-bg)}
.t-gray{color:var(--gray);background:var(--gray-bg)}
.checks{display:flex;flex-wrap:wrap;gap:6px}.checks .tag{white-space:normal}
.st{display:inline-flex;align-items:center;gap:7px;font-size:13px;font-weight:550;white-space:nowrap}
.st::before{content:"";width:7px;height:7px;border-radius:50%;background:currentColor}
.c-green{color:var(--green)}.c-amber{color:var(--amber)}.c-red{color:var(--red)}.c-gray{color:var(--ink-3)}

/* score ring */
.ring{--p:0;--c:var(--ink-3);width:var(--sz,40px);height:var(--sz,40px);border-radius:50%;display:grid;place-items:center;flex:none;
  background:conic-gradient(var(--c) calc(var(--p)*1%),var(--line) 0);position:relative;font-size:12px;font-weight:700}
.ring::before{content:"";position:absolute;inset:4px;border-radius:50%;background:var(--surface)}
.ring span{position:relative}
.ring.big{--sz:64px;font-size:18px}.ring.big::before{inset:6px}
@property --p{syntax:"<number>";inherits:false;initial-value:0}
.ring{transition:--p 1.1s cubic-bezier(.2,.8,.2,1)}
.r-green{--c:var(--green)}.r-amber{--c:var(--amber)}.r-red{--c:var(--red)}.r-violet{--c:var(--violet)}.r-gray{--c:var(--ink-3)}

/* tables */
.tbl{width:100%;border-collapse:collapse}
.tbl th{font-size:12px;font-weight:550;color:var(--ink-3);text-align:left;padding:12px 18px;border-bottom:1px solid var(--line);white-space:nowrap}
.tbl td{padding:14px 18px;border-bottom:1px solid var(--line);vertical-align:middle}
.tbl tr:last-child td{border-bottom:0}
.tbl.rows tbody tr{cursor:pointer;transition:background .12s}.tbl.rows tbody tr:hover{background:var(--hover)}
.scroll{overflow-x:auto}
.co{display:inline-flex;align-items:center;gap:10px;font-weight:600}
.fav{width:22px;height:22px;border-radius:6px;background:var(--raised);border:1px solid var(--line);flex:none;object-fit:cover}
.minibar{display:flex;gap:2px;height:6px;width:110px;border-radius:3px;overflow:hidden;background:var(--raised)}
.minibar i{display:block;height:100%}
.empty{padding:44px!important;text-align:center;color:var(--ink-3)}

/* run page: companies */
.dist{display:flex;gap:3px;height:10px;margin-top:24px;border-radius:5px;overflow:hidden;background:rgba(255,255,255,.1)}
.dist i{display:block;min-width:8px;border-radius:2px;transform-origin:left;animation:grow .9s cubic-bezier(.2,.8,.2,1) both}
@keyframes grow{from{transform:scaleX(0)}}
.legend{display:flex;flex-wrap:wrap;gap:6px 20px;margin-top:12px;font-size:13px;color:rgba(255,255,255,.75)}
.lg{display:inline-flex;align-items:center;gap:7px}.lg b{color:#fff;font-weight:650}
details.company{margin-top:10px;scroll-margin-top:76px;transition:box-shadow .2s,transform .2s}
details.company:not([open]):hover{transform:translateY(-2px);box-shadow:var(--shadow-lift)}
.co-sum{list-style:none;cursor:pointer;display:grid;grid-template-columns:auto minmax(140px,210px) 1fr auto;align-items:center;
  gap:16px;padding:14px 20px;border-radius:var(--r)}
.co-sum::-webkit-details-marker{display:none}
details[open] .co-sum{border-bottom:1px solid var(--line);border-radius:var(--r) var(--r) 0 0}
.co-name{display:flex;align-items:center;gap:10px;font-weight:650;letter-spacing:-.01em;min-width:0}
.co-name span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.co-line{color:var(--ink-2);font-size:13.5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}
.co-right{display:flex;align-items:center;gap:12px}
.chev{width:8px;height:8px;border-right:1.5px solid var(--ink-3);border-bottom:1.5px solid var(--ink-3);transform:rotate(-45deg);transition:transform .2s}
details[open] .chev{transform:rotate(45deg)}
.co-body{padding:4px 0 6px;animation:fade .25s ease}
@keyframes fade{from{opacity:0;transform:translateY(-4px)}}
.co-body>.co-meta,.co-body>.steps,.co-body>.note{margin-left:20px;margin-right:20px}
.co-meta{display:flex;flex-wrap:wrap;align-items:center;gap:10px 18px;margin-top:14px;color:var(--ink-3);font-size:12.5px}
.meter{display:inline-flex;align-items:center;gap:10px;white-space:nowrap}
.bar{position:relative;width:72px;height:5px;border-radius:3px;background:var(--gray-bg)}
.bar i{position:absolute;inset:0 auto 0 0;border-radius:3px;background:linear-gradient(90deg,var(--brand),var(--brand-2))}
.bar u{position:absolute;top:-4px;bottom:-4px;width:1.5px;background:var(--ink-3);border-radius:1px}
.tabs{display:flex;gap:2px;padding:0 14px;margin-top:14px;box-shadow:inset 0 -1px 0 var(--line);overflow-x:auto;overflow-y:hidden;scrollbar-width:none}
.tabs::-webkit-scrollbar{display:none}
.tab{appearance:none;background:none;border:0;font:inherit;font-size:13px;font-weight:600;color:var(--ink-3);
  padding:10px 8px 11px;margin:0 2px;cursor:pointer;border-bottom:2px solid transparent;white-space:nowrap;transition:color .15s}
.tab:hover{color:var(--ink)}.tab[aria-selected=true]{color:var(--ink);border-color:var(--brand)}
.panel{padding:22px 24px 24px;animation:fade .2s ease}
.js .panel[hidden]{display:none}
.panel-h{font-size:12px;font-weight:600;color:var(--ink-3);margin:26px 0 10px}.panel-h:first-child{margin-top:0}
.steps{display:flex;align-items:center;margin-top:16px;flex-wrap:wrap;row-gap:8px}
.step{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--ink-3)}
.step .d{width:17px;height:17px;border-radius:50%;border:1.5px solid var(--line-2);display:grid;place-items:center}
.step.ok{color:var(--ink-2)}.step.ok .d{background:linear-gradient(135deg,var(--brand),var(--brand-2));border:0;color:#fff}
.step.error{color:var(--red)}.step.error .d{background:var(--red);border-color:var(--red);color:#fff}
.step.stopped .d,.step.skipped .d{border-color:var(--amber);background:var(--amber-bg)}
.step.stopped,.step.skipped{color:var(--amber)}
.step-ln{width:12px;height:1.5px;background:var(--line-2);margin:0 6px}
.note{display:flex;gap:12px;align-items:center;justify-content:space-between;flex-wrap:wrap;border-radius:12px;padding:12px 14px;margin-top:16px;font-size:13px}
.note.err{background:var(--red-bg)}.note.info{background:var(--amber-bg)}
.note p{margin:0;color:var(--ink-2);flex:1;min-width:200px}.note.err b{color:var(--red)}.note.info b{color:var(--amber)}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px}
.tile{background:var(--raised);border:1px solid var(--line);border-radius:14px;padding:16px 18px;transition:transform .2s,box-shadow .2s}
.tile:hover{transform:translateY(-2px);box-shadow:var(--shadow)}
.tile h4{margin:0 0 6px;font-size:14px;font-weight:650;letter-spacing:-.01em}
.tile p{margin:0;color:var(--ink-2);font-size:13.5px}
.tile .ans{margin-top:10px;font-size:13px;color:var(--ink)}
.person{display:flex;gap:14px;align-items:flex-start}
.avatar{width:42px;height:42px;border-radius:50%;background:linear-gradient(135deg,var(--brand),var(--accent));color:#fff;display:grid;place-items:center;font-weight:700;flex:none}
.person .nm{font-weight:650}.person .rl{color:var(--ink-2);font-size:13.5px}
.person .why{color:var(--ink-3);font-size:12.5px;margin-top:6px}
.quote{display:block;margin-top:10px;padding-left:12px;border-left:2px solid var(--brand);color:var(--ink-3);font-size:12.5px;line-height:1.5}
.quote a{color:var(--ink-3);text-decoration:underline;text-underline-offset:2px}
.mail{border:1px solid var(--line);border-radius:14px;overflow:hidden;background:var(--surface);box-shadow:var(--shadow)}
.mail-h{padding:12px 18px;border-bottom:1px solid var(--line);background:var(--raised);display:grid;gap:3px;font-size:13px}
.mail-h .k{color:var(--ink-3);display:inline-block;width:82px}
.mail-subj{font-size:17px;font-weight:650;letter-spacing:-.015em;padding:20px 22px 0}
.mail-b{padding:12px 22px 24px;white-space:pre-wrap;font:inherit;font-size:14.5px;line-height:1.7;margin:0;color:var(--ink)}
.sendline{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-top:12px;font-size:13px;color:var(--ink-3)}
.copy{margin-left:auto}
details.fold{border-top:1px solid var(--line);margin-top:20px;padding-top:14px}
details.fold summary{cursor:pointer;font-size:13px;color:var(--ink-2);font-weight:550;list-style:none}
details.fold summary::-webkit-details-marker{display:none}
details.fold summary::before{content:"›";display:inline-block;width:14px;transition:transform .15s}
details.fold[open] summary::before{transform:rotate(90deg)}
.crits{list-style:none;margin:0;padding:0}
.crit{padding:14px 0;border-bottom:1px solid var(--line)}.crit:first-child{padding-top:0}
.crit-h{display:flex;align-items:center;gap:10px}
.crit-h .st{color:var(--ink);font-weight:600}.crit-h .st.c-green::before{background:var(--green)}
.crit-h .st.c-red::before{background:var(--red)}.crit-h .st.c-amber::before{background:var(--amber)}
.crit-w{color:var(--ink-3);font-size:12px}
.crit-s{margin-left:auto;font-size:12.5px;font-weight:600}
.crit p{margin:6px 0 0 14px;color:var(--ink-2);font-size:13.5px;max-width:720px}
details.src{margin:6px 0 0 14px}details.src summary{cursor:pointer;color:var(--ink-3);font-size:12.5px;list-style:none}
details.src summary::-webkit-details-marker{display:none}details.src summary:hover{color:var(--ink)}
.unknowns{margin-top:16px;padding:14px 16px;border-radius:12px;background:var(--raised);font-size:13.5px;display:grid;gap:4px}
.notes{margin:14px 0 0;padding-left:18px;color:var(--ink-3);font-size:12.5px}
.timeline{list-style:none;margin:0;padding:0}
.timeline li{display:flex;gap:14px;padding:0 0 18px;position:relative}
.timeline li:not(:last-child)::before{content:"";position:absolute;left:11px;top:26px;bottom:4px;width:1.5px;background:linear-gradient(var(--brand),var(--line-2))}
.tl-n{width:24px;height:24px;border-radius:50%;background:var(--brand-soft);color:var(--brand);display:grid;place-items:center;font-size:11.5px;font-weight:700;flex:none}
.tl-q{font-weight:600}.tl-r{color:var(--ink-3);font-size:13px;margin-top:2px}
.kvs{display:grid}.kv{display:grid;grid-template-columns:190px 1fr;gap:12px;padding:9px 0;border-bottom:1px solid var(--line);font-size:13.5px}
.kv:last-child{border-bottom:0}.kv .k{color:var(--ink-3);font-size:12px}
.foot{margin-top:40px}
#confetti{position:fixed;inset:0;pointer-events:none;z-index:50}
.toast{position:fixed;left:50%;bottom:28px;transform:translate(-50%,20px);opacity:0;background:var(--navy);color:#fff;font-size:13px;font-weight:550;
  padding:10px 16px;border-radius:12px;box-shadow:var(--shadow-lift);transition:all .3s cubic-bezier(.2,.8,.2,1);z-index:60;pointer-events:none}
.toast.show{opacity:1;transform:translate(-50%,0)}
.reveal{opacity:0;transform:translateY(10px);transition:opacity .5s ease,transform .5s cubic-bezier(.2,.8,.2,1)}
.reveal.in{opacity:1;transform:none}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}.reveal{opacity:1;transform:none}}
@media (max-width:640px){main{padding:16px 14px 80px}.nav-in{padding:0 14px}.hero{padding:28px 22px 50px;border-radius:18px}
  .hero h1{font-size:28px}.kpis{padding:0 8px;gap:10px}.kpi b{font-size:28px}.pad,.panel{padding-left:18px;padding-right:18px}
  .recip{display:none}.hide-sm{display:none}
  .co-sum{grid-template-columns:auto 1fr auto;gap:6px 12px;padding:14px 16px}
  .co-line{grid-column:1/-1;grid-row:2;white-space:normal}.co-body>.co-meta,.co-body>.steps,.co-body>.note{margin-left:16px;margin-right:16px}
  .kv{grid-template-columns:1fr;gap:2px}.steps .step-ln{width:8px;margin:0 4px}}
"""

FONT = ('<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" '
        'href="https://fonts.gstatic.com" crossorigin><link rel="stylesheet" '
        'href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;550;600;650;700&display=swap">')

FX_JS = r"""
<script>
const SFX = (() => {
  let ctx, on = true;
  try { on = localStorage.getItem('sfx') !== 'off'; } catch (e) {}
  const ac = () => { if (!ctx) { const A = window.AudioContext || window.webkitAudioContext; if (!A) return null; ctx = new A(); }
    if (ctx.state === 'suspended') ctx.resume(); return ctx; };
  const tone = (f, d = .08, type = 'sine', g = .05, t0 = 0, f2) => {
    if (!on) return; const a = ac(); if (!a) return; const t = a.currentTime + t0;
    const o = a.createOscillator(), v = a.createGain(); o.type = type; o.frequency.setValueAtTime(f, t);
    if (f2) o.frequency.exponentialRampToValueAtTime(f2, t + d);
    v.gain.setValueAtTime(.0001, t); v.gain.exponentialRampToValueAtTime(g, t + .012); v.gain.exponentialRampToValueAtTime(.0001, t + d);
    o.connect(v).connect(a.destination); o.start(t); o.stop(t + d + .03); };
  return {
    get on() { return on; },
    toggle() { on = !on; try { localStorage.setItem('sfx', on ? 'on' : 'off'); } catch (e) {} if (on) this.pop(); return on; },
    tick() { tone(1500, .03, 'sine', .025); },
    pop() { tone(480, .1, 'triangle', .07, 0, 900); },
    step() { tone(880, .07, 'sine', .04); tone(1320, .06, 'sine', .02, .04); },
    boom() { tone(150, .45, 'sine', .22, 0, 40); tone(70, .5, 'triangle', .14, 0, 32); tone(2400, .05, 'square', .015); },
    start() { [523, 659, 784].forEach((f, i) => tone(f, .14, 'triangle', .05, .12 + i * .07)); },
    success() { [523, 659, 784, 1047].forEach((f, i) => tone(f, .45, 'sine', .055, i * .09)); tone(1568, .6, 'sine', .02, .36); },
    nope() { tone(300, .2, 'triangle', .05, 0, 170); },
  };
})();
const FX = {
  reduced: matchMedia('(prefers-reduced-motion: reduce)').matches,
  confetti(x = innerWidth / 2, y = innerHeight / 3) {
    if (this.reduced) return; let c = document.getElementById('confetti');
    if (!c) { c = Object.assign(document.createElement('canvas'), {id: 'confetti'}); document.body.append(c); }
    const dpr = devicePixelRatio || 1; c.width = innerWidth * dpr; c.height = innerHeight * dpr; const g = c.getContext('2d'); g.scale(dpr, dpr);
    const cols = ['#ff5a36', '#ff8f3f', '#ffc078', '#6d4ae8', '#4ade80', '#ffffff'];
    const ps = Array.from({length: 110}, () => ({x, y, vx: (Math.random() - .5) * 13, vy: -Math.random() * 12 - 3,
      r: Math.random() * 6 + 3, c: cols[Math.random() * cols.length | 0], a: Math.random() * 6, s: Math.random() * .3 - .15}));
    let t = 0; const tick = () => { g.clearRect(0, 0, innerWidth, innerHeight); t++;
      ps.forEach(p => { p.vy += .32; p.vx *= .99; p.x += p.vx; p.y += p.vy; p.a += p.s; g.save(); g.translate(p.x, p.y); g.rotate(p.a);
        g.globalAlpha = Math.max(0, 1 - t / 120); g.fillStyle = p.c; g.fillRect(-p.r / 2, -p.r / 4, p.r, p.r / 2); g.restore(); });
      if (t < 120) requestAnimationFrame(tick); else g.clearRect(0, 0, innerWidth, innerHeight); };
    tick();
  },
  toast(msg) { let el = document.querySelector('.toast'); if (!el) { el = document.createElement('div'); el.className = 'toast'; document.body.append(el); }
    el.textContent = msg; el.classList.add('show'); clearTimeout(el._t); el._t = setTimeout(() => el.classList.remove('show'), 1800); },
  countUp(el) { const end = +el.dataset.count, dur = this.reduced ? 0 : 1100, t0 = performance.now();
    const f = now => { const k = dur ? Math.min(1, (now - t0) / dur) : 1; el.textContent = Math.round(end * (1 - Math.pow(1 - k, 3)));
      if (k < 1) requestAnimationFrame(f); }; requestAnimationFrame(f); },
};
document.addEventListener('DOMContentLoaded', () => {
  const io = new IntersectionObserver(es => es.forEach(e => { if (!e.isIntersecting) return; const el = e.target; io.unobserve(el);
    if (el.dataset.count !== undefined) FX.countUp(el);
    if (el.classList.contains('ring')) el.style.setProperty('--p', el.dataset.p);
    if (el.dataset.w) el.style.width = el.dataset.w;
    if (el.classList.contains('reveal')) el.classList.add('in'); }), {threshold: .2});
  document.querySelectorAll('[data-count],.ring[data-p],[data-w],.reveal').forEach(el => io.observe(el));
  const mute = document.getElementById('mute');
  const paint = () => { if (mute) { mute.innerHTML = SFX.on ? mute.dataset.on : mute.dataset.off; mute.title = SFX.on ? 'Sound on' : 'Sound off'; } };
  paint(); mute && mute.addEventListener('click', () => { SFX.toggle(); paint(); FX.toast(SFX.on ? 'Sound on' : 'Sound off'); });
  document.addEventListener('click', e => {
    const b = e.target.closest('.btn'); if (b && !b.disabled) { const r = b.getBoundingClientRect(), s = Math.max(r.width, r.height);
      const sp = Object.assign(document.createElement('span'), {className: 'ripple'});
      Object.assign(sp.style, {width: s + 'px', height: s + 'px', left: e.clientX - r.left - s / 2 + 'px', top: e.clientY - r.top - s / 2 + 'px'});
      b.append(sp); setTimeout(() => sp.remove(), 600); if (!b.dataset.sfx) SFX.pop(); }
    if (e.target.closest('.tab,.seg label,summary')) SFX.tick();
  });
});
</script>"""


def page(title: str, body: str) -> str:
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{escape(title)}</title>{FONT}<style>{CSS}</style>'
            f'<script>document.documentElement.classList.add("js")</script>{FX_JS}</head>'
            f'<body>{nav()}<main>{body}</main></body></html>')


def nav() -> str:
    on, off = escape(icon("sound", 17)), escape(icon("mute", 17))
    return (f'<nav class="nav"><div class="nav-in"><a class="logo" href="/"><span class="mark">{icon("shield", 17)}</span>'
            f'Outreach<small>for Sprinto</small></a><span class="sp"></span>'
            f'<span class="recip" title="send_email() can only address this inbox">{icon("mail", 15)}'
            f'<span>{escape(HARDCODED_RECIPIENT)}</span></span>'
            f'<button id="mute" class="iconbtn" aria-label="Toggle sound" data-on="{on}" data-off="{off}">{icon("sound", 17)}</button>'
            f'</div></nav>')


def _when(ts: Any, short: bool = False) -> str:
    try:
        d = datetime.fromisoformat(str(ts))
    except ValueError:
        return str(ts or "")
    return f"{d.day} {d.strftime('%b, %H:%M')}" if short else f"{d.day} {d.strftime('%B %Y, %H:%M UTC')}"


def _tag(v: Optional[str]) -> str:
    if v in VERDICTS:
        return f'<span class="tag t-{VERDICT_TONE[v]}" data-verdict="{v}">{VERDICT_LABEL[v]}</span>'
    return f'<span class="tag t-gray">{escape(v or "Incomplete")}</span>'


def _fav(domain: str) -> str:
    return (f'<img class="fav" alt="" loading="lazy" referrerpolicy="no-referrer" '
            f'src="https://www.google.com/s2/favicons?domain={escape(domain)}&amp;sz=64">')


def _ring(q: Optional[Dict[str, Any]], big: bool = False) -> str:
    if not q:
        return '<span class="ring r-gray" data-p="0"><span class="muted">—</span></span>'
    pct = round(float(q.get("weighted_score", 0)) * 100)
    tone = VERDICT_TONE.get(q.get("decision"), "gray")
    return (f'<span class="ring r-{tone}{" big" if big else ""}" data-p="{pct}" title="ICP score {pct}/100, Go at {GO_THRESHOLD}">'
            f'<span class="num">{pct}</span></span>')


def _meter(q: Dict[str, Any]) -> str:
    pct = round(float(q.get("weighted_score", 0)) * 100)
    return (f'<span class="meter" title="Go at {GO_THRESHOLD}"><span class="bar" aria-hidden="true"><i style="width:{pct}%">'
            f'</i><u style="left:{GO_THRESHOLD}%"></u></span><span class="num"><b>{pct}</b>'
            f'<span class="muted"> / 100</span></span></span>')


def _kpi(label: str, value: int, ic: str, tone: str, sub: str = "", suffix: str = "") -> str:
    return (f'<div class="kpi"><div class="kpi-top">{escape(label)}<span class="kpi-ic ic-{tone}">{icon(ic, 16)}</span></div>'
            f'<b class="num"><span data-count="{int(value)}">0</span>{f"<small>{suffix}</small>" if suffix else ""}</b>'
            f'<div class="sub">{sub}</div></div>')


def _donut(verdicts: Dict[str, int]) -> str:
    total = sum(verdicts.values())
    circ = 2 * 3.14159 * 54
    segs, off = [], 0.0
    for v in VERDICTS:
        n = verdicts.get(v, 0)
        if not n:
            continue
        ln = circ * n / total
        segs.append(f'<circle r="54" cx="75" cy="75" stroke="var(--{VERDICT_TONE[v]})" stroke-dasharray="{ln - 2:.1f} {circ:.1f}" '
                    f'stroke-dashoffset="{-off:.1f}" transform="rotate(-90 75 75)"><title>{n} {VERDICT_LABEL[v]}</title></circle>')
        off += ln
    if not segs:
        segs.append(f'<circle r="54" cx="75" cy="75" stroke="var(--line)"/>')
    legend = "".join(f'<div><span class="dot bg-{VERDICT_TONE[v]}"></span>{VERDICT_LABEL[v]}<b class="num">{verdicts.get(v, 0)}</b></div>'
                     for v in VERDICTS)
    return (f'<div class="donut-wrap"><svg class="donut" viewBox="0 0 150 150" role="img" aria-label="Verdict mix">'
            f'{"".join(segs)}<text x="75" y="80" text-anchor="middle">{total}</text>'
            f'<text class="lbl" x="75" y="98" text-anchor="middle">SCORED</text></svg><div class="leg">{legend}</div></div>')


def _funnel(st: Dict[str, Any]) -> str:
    rows = [("Scored", st["analysed"]), ("Qualified", st["go"]), ("Contact found", st["contacts"]),
            ("Email drafted", st["drafts"]), ("Sent", st["sent"])]
    top = max(st["analysed"], 1)
    return '<div class="funnel">' + "".join(
        f'<div class="fn"><span>{lbl}</span><span class="tr"><i data-w="{max(2, round(100 * n / top)) if n else 0}%"></i></span>'
        f'<b class="num">{n}</b></div>' for lbl, n in rows) + "</div>"


# ---------------- home ----------------

def home(runs: List[Dict[str, Any]], can_run: bool, steps: List[str], stats: Optional[Dict[str, Any]] = None) -> str:
    st = stats or {"analysed": 0, "go": 0, "go_rate": 0, "review": 0, "no_go": 0, "avg_score": 0, "contacts": 0,
                   "drafts": 0, "sent": 0, "verdicts": {v: 0 for v in VERDICTS}, "per_run": {}}
    hero = (f'<section class="hero"><span class="eyebrow">{icon("shield", 13)} Compliance outreach engine</span>'
            f'<h1>Find the companies that <em>need SOC 2 next</em>, and the person to tell.</h1>'
            f'<p>Paste domains. Each one is researched, scored against Sprinto\'s ICP, matched to the right buyer, '
            f'and gets a first email built only on evidence from their own pages.</p></section>')
    kpis = ('<div class="kpis">'
            + _kpi("Companies scored", st["analysed"], "search", "brand", f'{st["review"]} need review')
            + _kpi("Qualified", st["go"], "target", "green", f'{st["go_rate"]}% go rate')
            + _kpi("Avg ICP score", st["avg_score"], "gauge", "violet", f"Go at {GO_THRESHOLD}", "/100")
            + _kpi("Emails drafted", st["drafts"], "send", "amber", f'{st["sent"]} sent · {st["contacts"]} contacts')
            + "</div>")
    seg = "".join(f'<input type="radio" name="until" id="u-{s}" value="{s}"{" checked" if s == steps[-1] else ""}>'
                  f'<label for="u-{s}">{STEP_LABEL.get(s, s)}</label>' for s in steps)
    disabled = ('' if can_run else '<div class="note err" style="margin:0 0 16px"><p><b>Runs are paused.</b> Add '
                '<code>GEMINI_API_KEY</code> in Vercel, then redeploy.</p></div>')
    composer = f"""
<section class="card pad reveal">
  {disabled}
  <div style="display:flex;justify-content:space-between;align-items:baseline;gap:10px"><h2>New run</h2>
  <span class="label" id="count">Up to 15 companies</span></div>
  <textarea id="domains" aria-label="Company domains, one per line" placeholder="acme.io&#10;example-saas.com&#10;startup.dev" spellcheck="false"></textarea>
  <div class="chips" id="chips"></div>
  <div class="composer-foot">
    <div><div class="label" style="margin-bottom:6px">Run until</div><div class="seg" role="radiogroup" aria-label="Run until">{seg}</div></div>
    <button id="go" class="btn" data-sfx="custom" {'disabled' if not can_run else ''}>Run pipeline {icon("arrow")}<span class="kbd">⌘↵</span></button>
  </div>
  <ul id="live" class="live" aria-live="polite"></ul>
</section>"""
    insight = (f'<section class="card pad reveal"><h2>Verdict mix</h2><div style="margin-top:18px">{_donut(st["verdicts"])}</div>'
               f'{_funnel(st)}</section>')
    rows = []
    for r in runs:
        ds = r.get("domains", [])
        pr = st["per_run"].get(r["run_id"], {})
        n_scored = sum(pr.get(v, 0) for v in VERDICTS) or 1
        bar = "".join(f'<i class="bg-{VERDICT_TONE[v]}" style="width:{100 * pr.get(v, 0) / n_scored:.0f}%" title="{pr.get(v, 0)} {VERDICT_LABEL[v]}"></i>'
                      for v in VERDICTS if pr.get(v))
        companies = "".join(f'<span class="co" style="font-weight:500">{_fav(d)}{escape(d)}</span>' for d in ds[:3])
        more = f'<span class="muted small">+{len(ds) - 3}</span>' if len(ds) > 3 else ""
        rows.append(f'<tr data-href="/runs/{escape(r["run_id"])}"><td style="white-space:nowrap">'
                    f'<a href="/runs/{escape(r["run_id"])}" style="font-weight:600">{escape(_when(r.get("created_at"), True) or r["run_id"])}</a>'
                    f'<div class="muted small">{len(ds)} compan{"y" if len(ds) == 1 else "ies"}</div></td>'
                    f'<td><div style="display:flex;gap:6px 14px;flex-wrap:wrap;align-items:center">{companies}{more}</div></td>'
                    f'<td class="hide-sm"><div class="minibar">{bar}</div></td>'
                    f'<td class="num hide-sm">{pr.get("drafts", 0)}</td></tr>')
    table = (f'<div class="section-h"><h2>Recent runs</h2><span class="sub">{len(runs)} shown</span></div>'
             f'<section class="card scroll reveal"><table class="tbl rows"><thead><tr><th>Started</th><th>Companies</th>'
             f'<th class="hide-sm">Verdicts</th><th class="hide-sm">Emails</th></tr></thead><tbody>'
             f'{"".join(rows) or "<tr><td colspan=4 class=empty>No runs yet. Paste a few domains above to start.</td></tr>"}'
             f'</tbody></table></section>')
    body = hero + kpis + f'<div class="grid-main">{composer}{insight}</div>' + table
    return page("Outreach · Sprinto", body + ADVANCE_JS + HOME_JS + ROW_JS)


ADVANCE_JS = """
<script>
const STAGE_IX = {scrape: 0, extract: 1, research: 2, qualify: 2, poc: 3, pains: 4, draft: 5, send: 6};
async function advanceDomain(runId, d, until, report) {
  let last = null;
  for (let unit = 0, busy = 0; unit < 30; unit++) {
    let r;
    try {
      const res = await fetch(`/api/runs/${runId}/domains/${encodeURIComponent(d)}/advance?until=${until}`, {method: 'POST'});
      r = await res.json();
      if (!res.ok) { report(`Error: ${r.detail || res.status}`, null, r); return r; }
    } catch (e) { report('Network error, retrying…'); await new Promise(z => setTimeout(z, 5000)); continue; }
    last = r; report(`${r.stage}: ${r.message || ''}`, r.stage, r);
    if (r.done) return r;
    if (r.retry) {
      if (++busy > 6) { report(`${r.stage}: model still busy. Use Resume later.`, r.stage, r); return r; }
      report(`${r.stage}: model busy, retrying in 30s`, r.stage, r);
      await new Promise(z => setTimeout(z, 30000));
    }
  }
  return last;
}
</script>"""

HOME_JS = """
<script>
const go = document.getElementById('go'), live = document.getElementById('live'), ta = document.getElementById('domains');
const chips = document.getElementById('chips'), count = document.getElementById('count');
const parse = () => [...new Set(ta.value.split(/[\\s,]+/).map(s => s.trim().replace(/^https?:\\/\\//, '').replace(/^www\\./, '').replace(/\\/.*$/, '').toLowerCase()).filter(s => s.includes('.')))];
let lastN = 0;
ta && ta.addEventListener('input', () => {
  const ds = parse(); chips.replaceChildren(...ds.slice(0, 15).map(d => { const c = document.createElement('span'); c.className = 'chip';
    const img = new Image(); img.src = `https://www.google.com/s2/favicons?domain=${encodeURIComponent(d)}&sz=32`; img.alt = '';
    img.referrerPolicy = 'no-referrer'; c.append(img, d); return c; }));
  count.textContent = ds.length ? `${ds.length} compan${ds.length === 1 ? 'y' : 'ies'} ready` : 'Up to 15 companies';
  if (ds.length > lastN) SFX.tick(); lastN = ds.length;
});
ta && ta.addEventListener('keydown', e => { if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') { e.preventDefault(); go.click(); } });
const row = d => { const li = document.createElement('li');
  li.innerHTML = '<span class="nm"><img class="fav" alt=""><span></span></span><span class="msg-row"><span class="pips">' +
    '<i></i><i></i><i></i><i></i><i></i><i></i><i></i></span><span class="msg">Waiting…</span></span><span class="res"></span>';
  li.querySelector('.nm span').textContent = d; const im = li.querySelector('img'); im.referrerPolicy = 'no-referrer';
  im.src = `https://www.google.com/s2/favicons?domain=${encodeURIComponent(d)}&sz=32`; return li; };
const LABEL = {GO: ['Go', 'green'], GO_FLAGGED: ['Go, flagged', 'amber'], NO_GO: ['No go', 'red'], MANUAL_REVIEW: ['Needs review', 'violet']};
go && go.addEventListener('click', async () => {
  const domains = parse();
  if (!domains.length) { ta.focus(); SFX.nope(); FX.toast('Paste at least one domain'); return; }
  const until = (document.querySelector('input[name=until]:checked') || {}).value || 'send';
  SFX.boom(); SFX.start(); go.disabled = true;
  const r = await fetch('/api/runs', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({domains, until})});
  const run = await r.json();
  if (!r.ok) { FX.toast(run.detail || 'Error'); go.disabled = false; return; }
  const items = run.domains.map(row); live.replaceChildren(...items);
  let wins = 0;
  for (const [i, d] of run.domains.entries()) {
    const li = items[i], pips = [...li.querySelectorAll('.pips i')], msg = li.querySelector('.msg');
    let seen = -1, decision = null;
    await advanceDomain(run.run_id, d, until, (m, stage, res) => {
      msg.textContent = m; const ix = STAGE_IX[stage];
      if (res && res.decision) decision = res.decision;
      if (ix !== undefined && ix > seen) { seen = ix; SFX.step(); }
      pips.forEach((p, k) => { p.classList.toggle('on', k < seen || (k === seen && res && !res.retry)); p.classList.toggle('now', k === seen + 1 && !(res && res.done)); });
    });
    pips.forEach(p => p.classList.remove('now'));
    if (decision) { const [lbl, tone] = LABEL[decision] || [decision, 'gray'];
      li.querySelector('.res').innerHTML = `<span class="tag t-${tone}">${lbl}</span>`;
      if (decision.startsWith('GO')) { wins++; SFX.success(); const b = li.getBoundingClientRect(); FX.confetti(b.left + 60, b.top); } else SFX.nope(); }
  }
  FX.toast(wins ? `${wins} compan${wins === 1 ? 'y' : 'ies'} qualified` : 'Run finished');
  setTimeout(() => location.href = `/runs/${run.run_id}`, 1400);
});
</script>"""

ROW_JS = """
<script>
document.querySelectorAll('tr[data-href]').forEach(tr => tr.addEventListener('click', e => {
  if (!e.target.closest('a,button')) { SFX.tick(); location.href = tr.dataset.href; } }));
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
    summary = (f'<summary class="co-sum">{_ring(q)}<span class="co-name">{_fav(domain)}<span>{escape(domain)}</span></span>'
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
    verdict = q["decision"] if q else ""
    return (f'<details class="card company" id="{cid}" data-verdict="{verdict}"{" open" if is_open else ""}>' + summary + "".join(body)
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
        mid = escape(str(d.get("domain") or d.get("to_name") or "draft").replace(".", "-").replace(" ", "-"))
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
        send_html += (f'<div class="sendline"><button class="btn quiet copy" data-copy="mail-{mid}">'
                      f'{icon("check", 14)}Copy email</button></div>')
        out.append(f'<div class="panel-h">Email draft</div><div class="mail"><div class="mail-h">'
                   f'<div><span class="k">To</span>{escape(d["to_name"])} '
                   f'<span class="muted">&lt;{escape(d.get("intended_address") or "n/a")}&gt;</span></div>'
                   f'<div><span class="k">Delivered to</span><span class="muted">{escape(HARDCODED_RECIPIENT)} only</span></div></div>'
                   f'<div class="mail-subj">{escape(d["subject"])}</div><pre class="mail-b" id="mail-{mid}">'
                   f'{escape(d["body"])}</pre></div>'
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
        cells = [f'<td><span class="co">{_ring(q)}{_fav(d)}{escape(d)}</span></td>',
                 f'<td>{_tag(q["decision"] if q else None)}</td>']
        if any_contact:
            who = (escape(c["first_name"] + " " + (c.get("last_name") or "")) + '<div class="muted small">'
                   + escape(c.get("position") or "") + "</div>") if c else dash
            cells.append(f'<td class="hide-sm">{who}</td>')
        if any_email:
            cells.append('<td>' + ('<span class="tag t-green">Sent</span>' if send and send.status == "ok"
                                   else '<span class="tag t-amber">Draft ready</span>' if recs.get("draft") and recs["draft"].status == "ok"
                                   else dash) + '</td>')
        rows.append(f'<tr data-open="{cid}">{"".join(cells)}</tr>')
    head = ('<th>Company · score</th><th>Verdict</th>'
            + ('<th class="hide-sm">Contact</th>' if any_contact else "") + ('<th>Email</th>' if any_email else ""))
    return (f'<div class="section-h"><h2>Overview</h2><span class="sub">Ring = ICP score out of 100 · Go at {GO_THRESHOLD}</span></div>'
            f'<section class="card scroll reveal"><table class="tbl rows"><thead><tr>{head}</tr></thead>'
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
  e.preventDefault(); SFX.tick(); openCo(tr.dataset.open); history.replaceState(null, '', '#' + tr.dataset.open); }));
if (location.hash) openCo(location.hash.slice(1));
document.querySelectorAll('details.company').forEach(d => d.addEventListener('toggle', () => {
  if (d.open) d.querySelectorAll('.ring[data-p]').forEach(r => r.style.setProperty('--p', r.dataset.p));
  if (d.open && d.dataset.verdict && d.dataset.verdict.startsWith('GO') && !d._cheered) { d._cheered = true; SFX.success();
    const b = d.getBoundingClientRect(); FX.confetti(b.left + 80, b.top + 30); } }));
document.querySelectorAll('[data-copy]').forEach(b => b.addEventListener('click', async () => {
  const el = document.getElementById(b.dataset.copy);
  try { await navigator.clipboard.writeText('Subject: ' + el.previousElementSibling.innerText + '\\n\\n' + el.innerText); FX.toast('Email copied'); } catch (e) { FX.toast('Copy failed'); } }));
document.querySelectorAll('[data-resume]').forEach(b => b.addEventListener('click', async e => {
  e.preventDefault(); SFX.start();
  document.querySelectorAll('[data-resume]').forEach(x => x.disabled = true);
  const label = b.querySelector('span');
  await advanceDomain(b.dataset.run, b.dataset.resume, 'send', (msg, stage) => { label.textContent = msg.slice(0, 60); if (stage) SFX.step(); });
  location.reload();
}));
if ([...document.querySelectorAll('details.company')].some(d => (d.dataset.verdict || '').startsWith('GO')))
  setTimeout(() => FX.confetti(innerWidth / 2, 120), 500);
</script>"""


def run_page(manifest: Dict[str, Any], records_by_domain: Dict[str, Dict[str, Any]]) -> str:
    counts = {k: 0 for k in (*VERDICTS, "Incomplete")}
    scores, drafts, contacts = [], 0, 0
    for recs in records_by_domain.values():
        q = recs.get("qualify")
        if q and q.status == "ok":
            qq = q.output["qualification"]
            counts[qq["decision"]] += 1
            scores.append(float(qq.get("weighted_score", 0)))
        else:
            counts["Incomplete"] += 1
        drafts += bool(recs.get("draft") and recs["draft"].status == "ok")
        p = recs.get("poc")
        contacts += bool(p and (p.output or {}).get("chosen"))
    s = manifest.get("settings", {})
    run_id = manifest["run_id"]
    n = len(manifest.get("domains", []))
    go = counts["GO"] + counts["GO_FLAGGED"]
    avg = round(100 * sum(scores) / len(scores)) if scores else 0
    segs = "".join(f'<i class="bg-{VERDICT_TONE[k]}" style="flex:{v};animation-delay:{i * 0.12:.2f}s" title="{v} {VERDICT_LABEL[k]}"></i>'
                   for i, (k, v) in enumerate((k, v) for k, v in counts.items() if v))
    legend = "".join(f'<span class="lg"><span class="dot bg-{VERDICT_TONE[k]}"></span><b class="num">{v}</b> {VERDICT_LABEL[k]}</span>'
                     for k, v in counts.items() if v)
    hero = (f'<section class="hero"><a class="crumb" href="/" style="display:inline-flex;gap:6px;align-items:center;font-size:13px">'
            f'{icon("back", 14)}All runs</a>'
            f'<h1 style="font-size:34px">{n} compan{"y" if n == 1 else "ies"}, <em>{go} qualified</em></h1>'
            f'<div class="hero-meta"><span>{escape(_when(manifest.get("created_at")))}</span><span>{escape(str(s.get("model")))}</span></div>'
            f'<div class="dist" aria-label="Verdicts">{segs}</div><div class="legend">{legend}</div></section>')
    kpis = ('<div class="kpis">' + _kpi("Companies", n, "search", "brand", f'{counts["Incomplete"]} incomplete')
            + _kpi("Qualified", go, "target", "green", f'{round(100 * go / n) if n else 0}% of this run')
            + _kpi("Avg ICP score", avg, "gauge", "violet", f"Go at {GO_THRESHOLD}", "/100")
            + _kpi("Emails drafted", drafts, "send", "amber", f"{contacts} contact{'' if contacts == 1 else 's'} found") + "</div>")
    body = hero + kpis + _overview(manifest, records_by_domain)
    body += '<div class="section-h"><h2>Companies</h2><span class="sub">Open one for the reasons, contact and email</span></div>'
    body += "".join(domain_card(d, records_by_domain.get(d, {}), run_id) for d in manifest.get("domains", []))
    body += (f'<p class="foot small muted">Run <span class="mono">{escape(run_id)}</span> · prompt '
             f'{escape(str(s.get("prompt_version")))} · {escape(str(s.get("provider", "")))}</p>')
    return page(f"Run · {_when(manifest.get('created_at'), short=True)}", body + ADVANCE_JS + RUN_JS)
