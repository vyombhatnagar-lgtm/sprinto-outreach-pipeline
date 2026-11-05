# Sprinto Cold Outreach Pipeline (MESA AI Case 2)

You give it a list of company domains. For each one it scrapes the site, extracts company data, qualifies it against Sprinto's ICP (with an agent loop when data is thin), finds the PoC, picks two pain points, drafts an email, and sends it through Gmail.
The recipient is **hardcoded** to `vyom_bhatnagar@pg27.mesaschool.co`, as the case requires.

## Status
| Phase | Scope | State |
|---|---|---|
| 0 | Skeleton, typed step contracts, ICP scorecard and decision rule, trace store, Gmail transport with recipient guard, CLI | done |
| 1 | Steps 1-2: scrape and extract | done |
| 2 | Step 3: qualify with the L4 evidence-map research loop | done (offline tests; live run needs an Anthropic key) |
| - | Web dashboard (Vercel) + Postgres trace store (Neon) | done |
| 3 | Step 4: Hunter PoC and Apollo fallback | next |
| 4 | Steps 5-6: pain points and draft | |
| 5 | Step 7 wired into the pipeline | |
| 6 | Batch hardening | |

## How steps 1-3 work (follows MESA L4, "Data Acquisition & Agent Loops")
1. **Scrape** - a single-fetch scraper: the homepage only. Request-based first; if the cleaned text is under 200 words (usually a JavaScript-rendered page) it is re-read through Jina Reader. Cleaning drops nav/footers, lines under 8 words unless they carry a buying signal ("SOC 2 Type II"), and duplicates, and caps each page at ~1,500 tokens. robots.txt is respected and requests are spaced out. A blocked site (403/429) is logged and skipped, never worked around.
**Models:** Gemini (`GEMINI_MODEL`, default `gemini-3.8-flash`) when `GEMINI_API_KEY` is set, otherwise Anthropic (Haiku for extraction, Opus for qualifying). Set `LLM_PROVIDER` to force one.
2. **Extract** - the extraction model fills named fields; every value needs a verbatim quote that is then checked against the page text.
3. **Qualify** - the evidence map in `config/icp.yaml`:

   | Question | Filled when any of | Pages fetched, in order | Fetches | If still unanswered | Stops the run |
   |---|---|---|---|---|---|
   | Already certified? | certifications_claimed, certification_status | /security, /trust | 1 | treat as not certified, flag | holds SOC 2 **and** ISO 27001 -> NO_GO |
   | B2B SaaS? | is_saas | /about, /product | 1 | hand to a human | not SaaS -> NO_GO |
   | Right stage? | funding_stage, employee_count, enterprise_signals, compliance_job_postings | /careers (+ job board API), Google News, /pricing, /customers | 2 | rank lower, flag | - |

   **Code** checks whether fields are filled; the model is never asked "do you know enough". At most 4 fetches beyond the homepage. Then the qualifying model (`OUTREACH_MODEL`, Opus) gives each criterion a status backed by profile fields (a "met" with no evidence is downgraded to unknown), and `outreach/icp.py::decide` computes **GO / GO_FLAGGED / NO_GO / MANUAL_REVIEW**.

## Setup
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env            # fill in keys
.venv/bin/python -m outreach doctor
```

### Gmail (step 7)
- **OAuth (default):** in Google Cloud, enable the Gmail API and create an OAuth client of type *Desktop*. Save its JSON as `secrets/credentials.json`, then run `python -m outreach gmail-auth` once.
- **SMTP fallback:** use this if your school Workspace blocks OAuth. Set `GMAIL_MODE=smtp`, `GMAIL_SENDER` and `GMAIL_APP_PASSWORD` (this needs 2-Step Verification).
- `python -m outreach gmail-test` sends one test email to the hardcoded address.

## Commands
| Command | What it does |
|---|---|
| `doctor` | Checks dependencies, the ICP config, credentials and the recipient |
| `init-run FILE` | Normalises and dedupes domains, and creates `runs/<run_id>/` |
| `run FILE [--until scrape\|extract\|qualify]` | Runs the pipeline on each domain. `--until scrape` needs no API key |

| `gmail-auth` / `gmail-test` | Authorises Gmail once / sends a self-test email |

## Web dashboard (Vercel + Neon)
`app.py` is a FastAPI app. Vercel deploys it as one function (`vercel.json` allows 300 s per request; each domain is its own request).
Environment variables on Vercel: `GEMINI_API_KEY` (or `ANTHROPIC_API_KEY`), `DATABASE_URL` (set by the Neon integration), and optionally `APP_PASSWORD` to lock the dashboard (HTTP Basic, any username). Without `APP_PASSWORD` the dashboard is open to anyone with the URL.
With `DATABASE_URL` set, traces go to Postgres tables `runs` and `steps`; without it, to `runs/` on disk.
Run it locally with `.venv/bin/uvicorn app:app --reload` and `APP_PASSWORD=...` in `.env`.

## How decisions stay traceable
- `config/icp.yaml` is the scorecard. Each criterion is tagged with its origin (case, whiteboard or recommendation).
- The LLM only assigns a status and evidence per criterion. `outreach/icp.py::decide` computes GO / NO_GO from fixed weights and stores the rule text alongside the result.
- Every claim carries `Evidence(source_url, quote)`.
- Every step writes a trace record (inputs, output, model, prompt version): `runs/<run_id>/<domain>/NN_<step>.json`, or the `steps` table in Postgres. The qualify record lists each loop fetch: which question was open, which page was read, which fields it filled.
- `send_email()` has no `to` parameter, and a guard rejects any message whose To/Cc/Bcc is not the hardcoded address.
