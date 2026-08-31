# CLAUDE.md

Zoho call-transcription and call-intelligence pipeline for Sunrooof (wellness
lighting, India). Downloads sales-call recordings, transcribes them, extracts
structured intelligence with an LLM, audits call quality against a 100-point
scorecard, and serves it through a React dashboard.

`SETUP.md` covers Zoho credentials. `PLAN.md` is the original July design note —
historical, partly superseded.

## Commands

Always use the venv interpreter — a bare `python`/`python3` has none of the deps.
The one exception is the offline test suites, which import nothing outside the
stdlib and so run anywhere; see **Python — Windows** below.

**Node (works on both platforms).** Use `npm run`, not `npx`: `npm --prefix` runs the
script with the package as its working directory, while `npx --prefix` only changes
where the *package* is resolved from — so `npx --prefix ci-dashboard vite preview`
starts Vite at the repo root and dies with "directory dist does not exist".

```bash
npm --prefix ci-dashboard run build                  # rebuild the dashboard
npm --prefix ci-dashboard run preview -- --port 5199 # serve the build
node scripts/audio_proxy.mjs                         # audio proxy, port 3000
```

**Python — macOS** (the machine this pipeline was built and runs on):

```bash
.venv/bin/python scripts/<script>.py             # every Python entry point
.venv/bin/python scripts/test_call_quality.py    # scorer tests, no API calls
.venv/bin/python scripts/test_speech_dynamics.py # speech metrics + gate, no API calls
.venv/bin/python scripts/speech_dynamics.py --gate-scan   # dry-run the no_contact gate
```

**Python — Windows.** The committed `.venv` is a **macOS** venv: `pyvenv.cfg` says
`version = 3.10.11` with `home` under `/Library/Frameworks/...`, so `.venv/bin/python`
is a dead symlink here and exits 49. A venv is not portable across platforms; never
overwrite `.venv` or the Mac side breaks.

**The offline test suites run on Windows today, with no venv.** `call_quality` and
`speech_dynamics` are stdlib-only at import time, so a bare interpreter is enough:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_tests.ps1
```

Three traps that cost real time if you hit them raw, all handled by that script:

- **A real Python is installed but invisible.** `python`/`python3`/`py` on PATH are
  the Microsoft Store alias stubs, which exit without running anything. The genuine
  interpreter is `%LOCALAPPDATA%\Programs\Python\Python312\python.exe` (3.12.10), and
  the `py` launcher sits unregistered next to it in `...\Programs\Python\Launcher`.
  Call the full path; do not trust bare `python`.
- **The console is cp1252 and the scripts print emoji**, so output dies mid-run on
  `UnicodeEncodeError` — which looks like a test failure but is not one. Set
  `PYTHONUTF8=1`.
- Version skew is fine for the offline suites: they pass on 3.12 despite the venv
  being 3.10.

Anything touching OpenAI, Supabase, Zoho or Sarvam needs the dependencies. Build that
venv **outside the repo** — the working tree lives under OneDrive, so a venv inside it
is a few hundred MB of churn pushed to the cloud and re-synced on every package
change. `.venv-win/` is gitignored, but gitignored is not un-synced:

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m venv "$env:LOCALAPPDATA\sunrooof-venv"
& "$env:LOCALAPPDATA\sunrooof-venv\Scripts\python.exe" -m pip install -r requirements.txt
& "$env:LOCALAPPDATA\sunrooof-venv\Scripts\python.exe" scripts\<script>.py
```

From Git Bash, `PYTHONUTF8=1 "/c/Users/saura/AppData/Local/sunrooof-venv/Scripts/python.exe"`.
It already exists on this machine with `requirements.txt` installed.

## Pipeline order

Transcribe → sync → summarize → analytics → dashboard. `scripts/refresh_all.py`
drives the middle: `--only {regions,regions-apply,names,summaries,faqs,faq-agg,zoho,enrich,dataset}`.

| Stage | Script | Notes |
|---|---|---|
| Transcribe | `batch_transcribe.py` (Zoho audio) / `transcribe_ozonetel_july.py` (S3 via CSV match) | Sarvam Saaras v3; `--min-duration 30` |
| Sync | `sync_transcripts_to_supabase.py` | |
| Summarize + QA audit | `summarize_calls.py` | `--with-audit` adds the PSM scorecard |
| Analytics | `refresh_all.py` | enrich, FAQs, regions, dataset |
| Dashboard data | `build_ci_dataset.py`, `export_qa_audits_for_dashboard.py` | two separate files |

Long jobs run under supervisors that resume rather than restart:
`run_audit_all.zsh` (QA audit, `AUDIT_SINCE` env var scopes the window),
`sync_summarize_loop.sh`, `run_unattended_chain.zsh`, `refresh_advanced_qa.zsh`.
Logs in `out/logs/`, deferred failures in `out/logs/deferred-errors.log`.

## Architecture

- **Supabase `call_summaries`** is the system of record. The dashboard reads
  exported JSON snapshots, never Supabase directly.
- **`ci-dashboard/src/data/real/dataset.json`** (~55 MB) — the main dataset,
  rebuilt by `build_ci_dataset.py`.
- **`ci-dashboard/src/data/real/qa_audits.json`** — QA audits only, kept
  separate so it can be regenerated in seconds while the audit is still running
  and its rules unapproved.
- **`prompts/call_quality_audit.md`** is the single source of truth for the
  scorecard wording; `summarize_calls.py` reads it at runtime.

### The model judges, Python scores

`scripts/call_quality.py` owns every gate, sum, percentage and tier. The model
returns judgements and evidence only. Two reasons this matters:

1. An LLM asked to total its own scorecard occasionally returns a tier that
   disagrees with its own score — silently, on a minority of calls.
2. **Scoring-rule changes replay over stored data for free.** Run
   `rescore_audits.py` — no API calls. Only changes to *what the model looks
   for* need a re-run.

## Gotchas that cost real time

- **PostgREST paging needs a `order=` that is UNIQUE**, not merely present.
  Without any order there is no stable row order and pages shift under a
  concurrent writer — that lost ~930 calls from a date filter. But an order on a
  *tied* column fails exactly the same way with nothing writing at all: Postgres
  may return tied rows in any order per page, so some repeat and others are never
  returned. `export_qa_audits_for_dashboard.py` ordered on `qa_final_score`, where
  thousands of calls sit on 0 and ~1,900 are null, and shipped a "6,260-row"
  dashboard file holding 4,965 unique calls — 1,295 duplicated, ~1,295 missing,
  and the omission is invisible because the row count looks right. Always append
  `,call_id.asc`. If a paged export can lose rows, dedupe and warn as well.
- **OpenAI reserves the full `max_completion_tokens` against the 200k/min TPM
  limit**, used or not. It is the main throughput lever — an inflated ceiling
  costs speed directly. Concurrency is set via `--workers`; ~12 is the knee of
  the curve (~490 audits/hour, ~6% retryable 429s).
- **Exit code 0 does not mean success.** `enrich` once exited 0 having failed
  47% of its work to rate limits. Check the stage's own output counts.
- **`load_dotenv()` dies inside a heredoc** — it finds `.env` by walking the call
  stack, and piped-in scripts have no calling frame. Pass an explicit path.
- **Zoho recording retention is a rolling ~3 months.** Past the cliff,
  phonebridge returns HTTP 200 with an empty body — indistinguishable from
  attrition. HTTP 400 means the `ZOHO_COOKIE` is dead, not that audio is gone.
  Probe ≥30s calls only; short calls legitimately have no recording.
- **The Ozonetel CDR API no longer authenticates** with key+username. A CSV
  export from CloudAgent is the only route for windows past the Zoho cliff.
- **The dashboard date filter defaults to the last 30 days**, and the data is
  June–July 2026 — so pages look empty until the range is widened. Advanced QA
  deliberately ignores the global filter for this reason.
- **Audio downloads need the local proxy** (`node scripts/audio_proxy.mjs`,
  port 3000) plus a live `ZOHO_COOKIE`. The OAuth token does not work for
  recordings.
- **`review_scenarios.json` bakes a QA snapshot at build time.** Any audit that
  runs afterwards leaves it stale, silently — the set built at 15:16 on
  2026-08-26 and re-audited at 15:51 had 8 of 16 calls showing scores that no
  longer existed, four of them a whole tier out. Fix with
  `build_review_scenarios.py --refresh-qa`, which refreshes the numbers without
  re-running the selection. Do **not** reach for `--only-outliers`: it re-picks
  the cohorts, so which calls are under review changes and a reviewer part-way
  through the set loses their place.
- **A long recording is not a conversation.** Ambient noise and hold music get
  diarised into several speaker ids, so `customer_spoke` is true for a phone
  left on a desk and the model will grade it — it returned "polite 4/5" for
  office chatter. `speech_dynamics.conversation_gate()` decides this from speech
  density before the model is called; `summarize_calls.py` skips `no_contact`
  outright and logs every verdict to `out/logs/gated-calls.jsonl`. The `sparse`
  verdict is flag-only and must not be auto-dropped — one member of that class
  is a real inbound call sitting behind 90s of hold music.

## Conventions

- **Never invent a name, quote, date or CRM value.** Agent/customer names come
  from Zoho; anything absent is null or "unknown", never a guess. Evidence
  quotes are verified verbatim against the transcript and dropped if they do not
  match (`verify_evidence`).
- **Ask before changing the LLM model.** Model choice is the user's cost
  decision, including for test runs. Default is `gpt-4.1-mini` via
  `SUMMARY_MODEL`.
- **Transcripts contain real customer PII.** Any new vendor or destination needs
  explicit approval.
- **Sentiment prompts are frozen** in `summarize_calls.py`, `enrich_for_ci.py`
  and `build_ci_dataset.py` pending sign-off of
  `docs/sentiment_definition_for_review.md`.
- **Zoho write-back is an external action** — pushing AI notes to live customer
  records needs explicit go-ahead each time, not standing consent.
- Prefer fixing root causes in the scripts over working around them in a shell.
  Failing stages should log to `deferred-errors.log` and let the chain continue.

## Open items

- `prompts/SCORECARD_QUESTIONS.md` — 7 scorecard ambiguities awaiting sign-off.
  CM-5 is the big one: it decides every auto-zero and is undefined, so ~76% of
  audited calls currently auto-zero on it.
- `prompts/MISSING_DATA_REQUEST.md` — approved product facts, price ranges and
  the console quantity chart, without which criteria 5, 6 and CM-1 cannot be
  fact-checked.
- Sarvam credits are exhausted; ~5,400 calls remain untranscribed.
- The QA audit's `qa_*` columns are **not** in `dataset.json` — only in Supabase
  and the Advanced QA page.
