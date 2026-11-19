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
| 3 | Step 4: Hunter PoC (code-ranked buyer persona) and Apollo fallback | done |
| 4 | Steps 5-6: evidence-backed pain points and checked draft | done |
| 5 | Step 7: Gmail send to the hardcoded inbox, once per domain | done |

## How steps 1-3 work (follows MESA L4, "Data Acquisition & Agent Loops")
1. **Scrape** - a single-fetch scraper: the homepage only. Request-based first; if the cleaned text is under 200 words (usually a JavaScript-rendered page) it is re-read through Jina Reader. Cleaning drops nav/footers, lines under 8 words unless they carry a buying signal ("SOC 2 Type II"), and duplicates, and caps each page at ~1,500 tokens. robots.txt is respected and requests are spaced out. A blocked site (403/429) is logged and skipped, never worked around.
**Models:** Gemini (`GEMINI_MODEL`, default `gemini-3.5-flash-lite`, falling back to 3.8-flash, 3.5-flash, 3.7-flash when busy or out of quota) when `GEMINI_API_KEY` is set, otherwise Anthropic (Haiku for extraction, Opus for qualifying). Set `LLM_PROVIDER` to force one.
2. **Extract** - the extraction model fills named fields; every value needs a verbatim quote that is then checked against the page text.
3. **Qualify** - the evidence map in `config/icp.yaml`:

   | Question | Filled when any of | Pages fetched, in order | Fetches | If still unanswered | Stops the run |
   |---|---|---|---|---|---|
   | Already certified? | certifications_claimed, certification_status | /security, /trust | 1 | treat as not certified, flag | holds SOC 2 **and** ISO 27001 -> NO_GO |
   | B2B SaaS? | is_saas | /about, /product | 1 | hand to a human | not SaaS -> NO_GO |
   | Hiring for security / compliance? | compliance_job_postings, employee_count | /careers (+ job board API) | 1 | rank lower, flag | - |
   | Right stage (Series A-C)? | funding_stage | Google News, /about, /customers | 1 | rank lower, flag | - |

   **Code** checks whether fields are filled; the model is never asked "do you know enough". At most 4 fetches beyond the homepage. Then the qualifying model (`OUTREACH_MODEL`, Opus) gives each criterion a status backed by profile fields (a "met" with no evidence is downgraded to unknown), and `outreach/icp.py::decide` computes **GO / GO_FLAGGED / NO_GO / MANUAL_REVIEW**. The score is taken over the weight public pages could confirm (`score_on: known` in `config/icp.yaml`); what could not be checked is left out and flagged, so the verdict becomes GO_FLAGGED. Under 30% confirmed goes to MANUAL_REVIEW. Set `score_on: all` for the stricter rule (unknowns count 0).

## Setup
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env            # fill in keys
.venv/bin/python -m outreach doctor
```

### Gmail (step 7)
- **OAuth (default):** in Google Cloud, enable the Gmail API and create an OAuth client of type *Desktop*. Save its JSON as `secrets/credentials.json`, then run `python -m outreach gmail-auth` once.
- No passwords anywhere: there is no SMTP/app-password mode and no dashboard password.
- `python -m outreach gmail-test` sends one test email to the hardcoded address.

## Commands
| Command | What it does |
|---|---|
| `doctor` | Checks dependencies, the ICP config, credentials and the recipient |
| `init-run FILE` | Normalises and dedupes domains, and creates `runs/<run_id>/` |
| `run FILE [--until scrape\|extract\|qualify]` | Runs the pipeline on each domain. `--until scrape` needs no API key |

| `gmail-auth` / `gmail-test` | Authorises Gmail once / sends a self-test email |

## Steps 4-7 (only for GO / GO_FLAGGED, so a NO_GO never spends a Hunter search)
4. **Point of contact** (`outreach/poc.py`) - Hunter Domain Search, then a manual Apollo contact (`MANUAL_POCS_JSON`). A fixed rule in code picks the buyer: security/compliance owner > CTO/VP Eng > founder/CEO > other senior eng leader; sales/marketing/HR/support never. The reason is stored.
5. **Pain points** (`outreach/messaging.py`) - two, each tied to profile fields with verified quotes; unsupported ones are rejected.
6. **Draft** - greets the contact by first name, opens with a hook the company itself published, covers both pains. Code checks: name, no placeholders, hook has evidence (blocking); length, pain coverage, subject (warnings).
7. **Send** - `send_email()` can only address `HARDCODED_RECIPIENT`; a footer says who the email was intended for; a domain is never sent twice. Without Gmail configured the draft is kept and the send is marked skipped.

## Web dashboard (Vercel + Neon)
`app.py` is a FastAPI app. Vercel deploys it as one function (`vercel.json` allows 300 s per request; each domain is its own request).
Environment variables on Vercel: `GEMINI_API_KEY` (or `ANTHROPIC_API_KEY`), `HUNTER_API_KEY`, `GMAIL_TOKEN_JSON` (contents of `secrets/token.json` after `gmail-auth`; without it drafts are kept and not sent), optional `MANUAL_POCS_JSON`, and `DATABASE_URL` (set by the Neon integration). The dashboard has no password and is open to anyone with the URL.
With `DATABASE_URL` set, traces go to Postgres tables `runs` and `steps`; without it, to `runs/` on disk.
Run it locally with `.venv/bin/uvicorn app:app --reload`.

## How decisions stay traceable
- `config/icp.yaml` is the scorecard. Each criterion is tagged with its origin (case, whiteboard or recommendation).
- The LLM only assigns a status and evidence per criterion. `outreach/icp.py::decide` computes GO / NO_GO from fixed weights and stores the rule text alongside the result.
- Every claim carries `Evidence(source_url, quote)`.
- Every step writes a trace record (inputs, output, model, prompt version): `runs/<run_id>/<domain>/NN_<step>.json`, or the `steps` table in Postgres. The qualify record lists each loop fetch: which question was open, which page was read, which fields it filled.
- `send_email()` has no `to` parameter, and a guard rejects any message whose To/Cc/Bcc is not the hardcoded address.
