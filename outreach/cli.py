"""Command line entry point: `python -m outreach <command>`."""
import argparse
import importlib
import sys
from pathlib import Path

from .config import HARDCODED_RECIPIENT, PROMPT_VERSION, load_settings
from .domains import read_domains_file
from .icp import load_scorecard
from .trace import open_store

OK, WARN, FAIL = "  [ok]  ", "  [warn]", "  [FAIL]"


def cmd_doctor(_args) -> int:
    """Check everything Phase 0 promises: deps, config, credentials, recipient."""
    s = load_settings()
    failures = 0
    print("Python", sys.version.split()[0])
    if sys.version_info < (3, 10):
        print(WARN, "Python 3.9 is end-of-life; works today, but 3.10+ is recommended (newer SDK releases drop 3.9)")

    for mod in ["pydantic", "dotenv", "yaml", "googleapiclient", "google_auth_oauthlib",
                "anthropic", "httpx", "trafilatura", "bs4", "feedparser", "psycopg", "fastapi"]:
        try:
            importlib.import_module(mod)
            print(OK, f"import {mod}")
        except ImportError:
            print(FAIL, f"import {mod}  (pip install -r requirements.txt)")
            failures += 1

    try:
        card = load_scorecard(s.icp_path)
        gates = [c.id for c in card.criteria if c.gate]
        print(OK, f"ICP scorecard: {len(card.criteria)} criteria, gates={gates}, GO >= {card.go_threshold}")
        print(OK, f"evidence map: {[q.id for q in card.questions]}, max {card.max_fetches} fetches beyond the homepage")
    except Exception as e:
        print(FAIL, f"ICP scorecard: {e}")
        failures += 1

    print(OK, f"recipient hardcoded -> {HARDCODED_RECIPIENT}")
    print(OK, f"models -> qualify {s.model}, extract {s.extract_model}   prompt_version -> {PROMPT_VERSION}")
    print(OK, "trace store -> " + ("Postgres (DATABASE_URL)" if s.database_url else f"files in {s.runs_dir}"))
    print(OK if not s.review_before_send else WARN,
          f"review_before_send={s.review_before_send} (case wants no manual decisions)")

    print(OK if s.anthropic_api_key else WARN, "ANTHROPIC_API_KEY " + ("set" if s.anthropic_api_key else "missing (needed from Phase 1)"))
    print(OK if s.hunter_api_key else WARN, "HUNTER_API_KEY " + ("set" if s.hunter_api_key else "missing (needed in Phase 3, or use data/manual_pocs.json)"))

    if s.gmail_mode == "oauth":
        has_client = (s.secrets_dir / "credentials.json").exists()
        has_token = (s.secrets_dir / "token.json").exists()
        print(OK if has_client else WARN, "Gmail OAuth client secrets/credentials.json " + ("found" if has_client else "missing"))
        print(OK if has_token else WARN, "Gmail token " + ("found" if has_token else "missing - run: python -m outreach gmail-auth"))
    elif s.gmail_mode == "smtp":
        ready = bool(s.gmail_sender and s.gmail_app_password)
        print(OK if ready else WARN, "Gmail SMTP " + ("configured" if ready else "needs GMAIL_SENDER + GMAIL_APP_PASSWORD"))
    else:
        print(FAIL, f"GMAIL_MODE must be oauth or smtp, got {s.gmail_mode!r}")
        failures += 1

    print("\nDoctor:", "FAILED" if failures else "OK (warnings are setup still to do)")
    return 1 if failures else 0


def cmd_init_run(args) -> int:
    s = load_settings()
    domains = read_domains_file(Path(args.domains))
    store = open_store(s)
    store.write_manifest(domains, {"model": s.model, "prompt_version": PROMPT_VERSION,
                                   "recipient": HARDCODED_RECIPIENT})
    for d in domains:
        store.domain_dir(d)
    print(f"run {store.run_id}: {len(domains)} domain(s) -> {store.location}")
    for d in domains:
        print("  -", d)
    return 0


def cmd_gmail_auth(_args) -> int:
    from .gmail_client import authorize
    print(authorize(load_settings()))
    return 0


def cmd_gmail_test(_args) -> int:
    from .gmail_client import send_email
    res = send_email(load_settings(), "[outreach] Gmail connection test",
                     "If you can read this, step 7 (Gmail send) is wired up.\n", domain="selftest")
    print(res.model_dump_json(indent=2))
    return 0 if res.sent else 1


def _print_profile(profile) -> None:
    for field, fact in profile:
        if field == "domain" or fact.value is None:
            continue
        src = fact.evidence[0].source_url if fact.evidence else ""
        print(f"      {field:<24} {str(fact.value)[:70]:<70}  <- {src}")


def _print_qualification(q) -> None:
    print(f"      decision {q.decision}  score {q.weighted_score}  unknown {q.unknown_weight_share:.0%}")
    if q.short_circuit:
        print(f"      stopped early: {q.short_circuit}")
    for st in q.agent_steps:
        print(f"      fetch {st.round}: {st.question:<9} -> {st.page_kind:<9} {st.result_summary[:80]}")
    for sc in q.scores:
        print(f"      {sc.criterion_id:<20} {sc.status:<8} {sc.reason[:90]}")
    for f in q.flags:
        print(f"      flag: {f}")


def cmd_run(args) -> int:
    from .pipeline import IMPLEMENTED_STEPS, build_pipeline

    s = load_settings()
    domains = read_domains_file(Path(args.domains))
    store = open_store(s)
    store.write_manifest(domains, {"model": s.model, "extract_model": s.extract_model,
                                   "prompt_version": PROMPT_VERSION, "recipient": HARDCODED_RECIPIENT,
                                   "until": args.until})
    try:
        pipe = build_pipeline(s, store, until=args.until)
    except Exception as e:
        print(f"Cannot create the Anthropic client ({e}).\n"
              "Set ANTHROPIC_API_KEY in .env, or run with --until scrape.")
        return 1
    print(f"run {store.run_id}: {len(domains)} domain(s), steps up to '{args.until}' "
          f"(implemented: {', '.join(IMPLEMENTED_STEPS)})\n")
    for d in domains:
        res = pipe.run_domain(d, args.until)
        print(f"  {d}")
        for step, outcome in res["steps"].items():
            print(f"    {step:<8} {outcome}")
        if "profile" in res:
            _print_profile(res["profile"])
        if "qualification" in res:
            _print_qualification(res["qualification"])
        print()
    print(f"Trace: {store.location}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="outreach", description="Sprinto cold-outreach pipeline")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor", help="check deps, config and credentials").set_defaults(fn=cmd_doctor)
    r = sub.add_parser("init-run", help="normalise a domains file and create a run folder")
    r.add_argument("domains")
    r.set_defaults(fn=cmd_init_run)
    sub.add_parser("gmail-auth", help="one-time Gmail authorisation").set_defaults(fn=cmd_gmail_auth)
    sub.add_parser("gmail-test", help=f"send a test email to {HARDCODED_RECIPIENT}").set_defaults(fn=cmd_gmail_test)
    rr = sub.add_parser("run", help="run the pipeline on a domains file")
    rr.add_argument("domains")
    rr.add_argument("--until", choices=["scrape", "extract", "qualify"], default="qualify",
                    help="last step to run (more steps land in later phases)")
    rr.set_defaults(fn=cmd_run)
    args = p.parse_args(argv)
    return args.fn(args)
