#!/usr/bin/env python3
"""
summarize_calls.py — Generate a structured conversation summary + metrics for
each transcribed call, using an LLM.

- Reads transcripts from out/transcripts/{id}.mp3.json
- Pulls the REAL agent/customer names from Zoho CRM (never invented)
- Computes talk-ratio and turn count for free from the diarization
- Sends the transcript to the configured model with a
  JSON schema described in the prompt; the model is told to use ONLY the
  transcript and the CRM-provided names, and to NEVER invent a name —
  anything not in the data comes back null / "unknown"
- Upserts one row per call into Supabase `call_summaries`

Usage:
    python scripts/summarize_calls.py --limit 5        # prototype on 5 calls
    python scripts/summarize_calls.py --ids id1,id2
    python scripts/summarize_calls.py                  # all transcribed, unsummarized

Requires OPENAI_API_KEY in .env (platform.openai.com/api-keys) and
SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY (same as the rest of the pipeline).
Override the model with SUMMARY_MODEL.

If no OPENAI_API_KEY is set the script falls back to OPENROUTER_API_KEY and the
free Nemotron model, which is rate-limited to 50 requests/day and 20/minute —
it then paces itself under both limits and stops cleanly at the daily cap.
Either way, already-summarized calls (tracked in Supabase) are skipped, so
re-running picks up where it left off.
"""
import os, re, sys, json, time, argparse
import datetime as _dt
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional, List, Literal
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator
from dotenv import load_dotenv
import requests
from openai import OpenAI

load_dotenv()

BASE = Path(__file__).resolve().parent.parent
TDIR = BASE / "out" / "transcripts"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from call_quality import build_audit, validate as validate_audit  # noqa: E402
from speech_dynamics import conversation_gate  # noqa: E402

# One line per gated call, appended. Durable record of what was skipped and why,
# so a silent drop can always be audited after the fact.
GATED_LOG = BASE / "out" / "logs" / "gated-calls.jsonl"
_GATED_LOCK = threading.Lock()
GATED = {"no_contact": 0, "sparse": 0}   # run totals, for the closing readout


def record_gated(call_id, gate):
    """Append the gate's verdict for one call. Never raises — a logging failure
    must not lose a run."""
    try:
        GATED_LOG.parent.mkdir(parents=True, exist_ok=True)
        row = {"call_id": call_id, "at": _dt.datetime.now().isoformat(timespec="seconds"),
               **gate}
        with _GATED_LOCK:
            GATED[gate["verdict"]] = GATED.get(gate["verdict"], 0) + 1
            with GATED_LOG.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row) + "\n")
    except OSError:
        pass

ZOHO_API    = os.getenv("ZOHO_API_DOMAIN", "https://www.zohoapis.in")
ZOHO_ACC    = os.getenv("ZOHO_ACCOUNTS_DOMAIN", "https://accounts.zoho.in")
TOKEN_CACHE = BASE / ".zoho_token_cache.json"

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# ── LLM provider ───────────────────────────────────────────────────────────
# OpenAI is the default. OPENROUTER_API_KEY is still honoured as a fallback so
# the old free-tier path keeps working if no OpenAI key is present — the two
# speak the same wire protocol, only the base URL, model names and rate limits
# differ. Set SUMMARY_PROVIDER to force one when both keys are set.
OPENAI_KEY     = os.getenv("OPENAI_API_KEY")
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")
PROVIDER       = os.getenv("SUMMARY_PROVIDER") or ("openai" if OPENAI_KEY else "openrouter")

if PROVIDER == "openai":
    API_KEY  = OPENAI_KEY
    BASE_URL = None                       # SDK default: api.openai.com/v1
    MODEL    = os.getenv("SUMMARY_MODEL", "gpt-4.1-mini")
    # Paid, so no daily request cap and no free-tier pacing. The floor below
    # only exists to be polite to the API; the SDK retries 429s on its own.
    DAILY_LIMIT  = int(os.getenv("SUMMARY_DAILY_LIMIT", "10000"))
    MIN_INTERVAL = float(os.getenv("SUMMARY_MIN_INTERVAL", "0.2"))
else:
    API_KEY  = OPENROUTER_KEY
    BASE_URL = "https://openrouter.ai/api/v1"
    MODEL    = os.getenv("SUMMARY_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free")
    # Free-tier caps: 50 requests/day, 20/minute. Stay comfortably under both.
    DAILY_LIMIT  = int(os.getenv("SUMMARY_DAILY_LIMIT", "45"))
    MIN_INTERVAL = float(os.getenv("SUMMARY_MIN_INTERVAL", "4.0"))

# USD per 1M tokens, for the run-cost readout only. Unlisted models print no
# cost rather than a wrong one.
PRICING = {
    "gpt-5":       (1.25, 10.00),
    "gpt-5-mini":  (0.25,  2.00),
    "gpt-5-nano":  (0.05,  0.40),
    "gpt-4.1":      (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-4o":      (2.50, 10.00),
    "gpt-4o-mini": (0.15,  0.60),
}

# ── Structured schema the model must fill (all metrics) ────────────────────
class Requirements(BaseModel):
    room_type: Optional[str] = Field(None, description="which room/space the panels are for, e.g. living room, bedroom, basement; null if not mentioned")
    budget:       Optional[str] = Field(None, description="budget stated by customer; null if not mentioned")
    location:     Optional[str] = Field(None, description="city/area mentioned; null if not mentioned")
    timeline:     Optional[str] = Field(None, description="when they want it done; null if not mentioned")

class Extracted(BaseModel):
    """An inferred fact plus the evidence for it, so a manager can verify."""
    value:      Optional[str] = Field(None, description="the extracted value; null if never stated")
    evidence:   Optional[str] = Field(None, description="VERBATIM quote from the transcript; null if value is null")
    confidence: Literal["high", "medium", "low"] = Field(
        description="high = explicitly stated; medium = strongly implied; low = weak inference")

class Objection(BaseModel):
    objection: str = Field(description="the concern the CUSTOMER raised")
    evidence:  Optional[str] = Field(None, description="verbatim quote of the customer raising it")
    addressed: bool = Field(description="true only if the agent actually responded to it")

class Commitment(BaseModel):
    who:  Literal["agent", "customer"] = Field(description="who promised it")
    what: str = Field(description="what was promised")
    due:  Optional[str] = Field(None, description="deadline ONLY if one was stated, e.g. 'Friday'; else null")

class Dimension(BaseModel):
    applicable: bool = Field(
        description="false when the call gave no opportunity to demonstrate this. "
                    "Do NOT score low just because it did not occur.")
    score:      Optional[int] = Field(None, description="1 (poor) to 5 (excellent); null when not applicable")
    evidence:   Optional[str] = Field(None, description="verbatim quote supporting the score")
    missed:     Optional[str] = Field(None, description="what would have been better; null if nothing")

    # Weaker models emit contradictory pairs — applicable=true with no score, or
    # applicable=false alongside a score and a quote. Both render as nonsense in
    # the scorecard table, so collapse them to one consistent reading here rather
    # than letting the UI guess. A dimension the model could not put a number on
    # was, in effect, not assessed.
    @model_validator(mode="after")
    def _coherent(self):
        if self.score is not None and not 1 <= self.score <= 5:
            self.score = None
        if self.applicable and self.score is None:
            self.applicable = False
        if not self.applicable:
            self.score = None
            self.evidence = None
        return self

class Scorecard(BaseModel):
    opening_identification: Dimension = Field(description="named themselves, the company, and why they were calling")
    need_capture:           Dimension = Field(description="established new-build vs renovation, location, property details, requirements")
    objection_handling:     Dimension = Field(description="NOT applicable unless the customer raised an objection")
    next_step_secured:      Dimension = Field(description="agreed a concrete next action (visit, quote, catalogue, callback)")
    language_rapport:       Dimension = Field(description="matched the customer's language, let them speak, stayed courteous")

class CallSummary(BaseModel):
    summary: str = Field(
        description="What happened on this call, in 1-2 short sentences (35 words max). "
                    "State the outcome and the single most important detail. Do not "
                    "restate the agent/customer names, do not rate the agent's conduct, "
                    "and do not repeat information captured in the other fields.")
    call_outcome: Literal[
        "interested", "not_interested", "callback_requested", "follow_up_needed",
        "not_reachable", "wrong_number", "already_purchased", "unclear",
    ]
    next_action: Optional[str] = Field(None, description="concrete follow-up, incl. date if stated; null if none")
    customer_sentiment: Literal["positive", "neutral", "negative"]
    interest_level: Literal["hot", "warm", "cold", "unknown"]
    agent_politeness: int = Field(description="1 (rude) to 5 (very polite)")
    agent_professionalism: int = Field(description="1 (poor) to 5 (excellent): greeting, self-intro, clear close")

    # Models emit 0 on voicemails to mean "not applicable", but these two columns
    # are NOT NULL CHECK (between 1 and 5), so Postgres rejects the whole row and
    # the call is lost entirely — a 400 that cost us the summary, not just the
    # score. Clamp into range instead. Safe because nothing displays or averages
    # these for a call that never happened: the API only aggregates calls with
    # >= 8 turns, and both the list and detail pages render "—" for the rest.
    @field_validator("agent_politeness", "agent_professionalism")
    @classmethod
    def _in_range(cls, v):
        return v if v is None else min(5, max(1, v))
    professionalism_notes: Optional[str] = Field(None, description="brief note on agent conduct")
    customer_requirements: Requirements
    objections: List[str] = Field(default_factory=list, description="objections the customer raised")
    action_items: List[str] = Field(default_factory=list, description="things the agent should do next")
    red_flags: List[str] = Field(default_factory=list, description="rudeness, complaints, escalation; empty if none")
    language: str = Field(description="language(s) used, e.g. 'Hindi/English', 'Telugu'")

    # ── Classification ───────────────────────────────────────────────────
    # This field answers "what was the call ABOUT"; call_outcome above answers
    # "how did it END". An earlier version shared three values with call_outcome
    # (callback_requested, not_interested, wrong_number), so the model classified
    # into call_outcome, found this one redundant and sent 93% of calls to
    # "other". The values below deliberately do not overlap it.
    call_type: Literal[
        "product_introduction", "requirements_gathering", "quotation_discussion",
        "visit_coordination", "follow_up_check_in", "internal_admin",
        "no_contact", "other",
    ] = Field(description=(
        "The SUBJECT of the call - what was actually discussed. This is NOT the "
        "call's result; the result belongs in call_outcome and must never be "
        "duplicated here. Pick the ONE dominant subject:\n"
        "- product_introduction: explaining what Sunrooof sells (artificial-skylight "
        "LED panels, natural-daylight lighting, installation, warranty) to someone "
        "learning about it.\n"
        "- requirements_gathering: capturing the customer's room/ceiling details, "
        "property, measurements or lighting needs.\n"
        "- quotation_discussion: a specific price, per-sqft rate or quotation was "
        "the main thing discussed.\n"
        "- visit_coordination: arranging, confirming or chasing a showroom, "
        "experience-centre or site visit.\n"
        "- follow_up_check_in: chasing a previous enquiry with no substantive new "
        "discussion (customer busy, will revert, asked for a catalogue).\n"
        "- internal_admin: the other party is a Sunrooof colleague, or the call is "
        "CRM housekeeping (lead transfer, duplicate leads, verifying stored "
        "details) rather than selling.\n"
        "- no_contact: nothing was discussed at all - voicemail, IVR, no answer, "
        "or the wrong person picked up.\n"
        "- other: ONLY if none of the above can apply. Do NOT use 'other' just "
        "because several subjects were covered - pick the dominant one."))

    # ── Lead intelligence (null unless actually discussed) ───────────────
    property_context: Literal["new_build", "renovation", "not_discussed"] = Field(
        description="is the installation for a new property or an existing one being upgraded")
    property_details: Optional[str] = Field(
        None, description="size/type if stated, e.g. '3BHK flat, false-ceiling living room'; null otherwise")
    budget_detail: Extracted = Field(description=(
        "the budget figure THE CUSTOMER stated or agreed to — never the agent's "
        "quoted price or rate card; null if the customer named no budget"))
    timeline_detail: Extracted = Field(description="when they want it done, with the quote proving it")
    stakeholders: List[str] = Field(
        default_factory=list,
        description="others involved in deciding, e.g. 'wife', 'architect', 'builder'; empty if none named")
    competitor_mentioned: Optional[str] = Field(
        None, description="any other brand/vendor/carpenter the customer is considering; null if none")

    # ── Signals ──────────────────────────────────────────────────────────
    objections_detail: List[Objection] = Field(
        default_factory=list, description="each objection with evidence and whether the agent addressed it")
    buying_signals: List[str] = Field(
        default_factory=list,
        description="concrete interest signals, e.g. 'agreed to share floor plan', 'asked for quotation'")
    risk_flags: List[str] = Field(
        default_factory=list, description="reasons this could be lost; empty if none")
    conversion_likelihood: Literal["hot", "warm", "cold", "dead", "unknown"] = Field(
        description="likelihood this becomes a sale, based only on what was said")

    # ── Commitments ──────────────────────────────────────────────────────
    commitments: List[Commitment] = Field(
        default_factory=list, description="promises made by either side during the call")
    next_step_secured: bool = Field(
        description="true only if a concrete next action was agreed (not vague interest)")

    # ── Quality ──────────────────────────────────────────────────────────
    scorecard: Scorecard

    # ── Coaching ─────────────────────────────────────────────────────────
    did_well: List[str] = Field(default_factory=list, description="up to 3 specific things the agent did well")
    improvements: List[str] = Field(
        default_factory=list, description="up to 2 highest-impact things to improve next time")
    suggested_followup: Optional[str] = Field(
        None, description="a short follow-up message the agent could send; null if not applicable")

    # ── PSM call-quality audit (only requested when --with-audit is passed) ──
    # Deliberately untyped here: the model returns *judgements* only, and
    # scripts/call_quality.py expands them into the full Section 12 object and
    # computes every score. Validating the judgement shape twice would just
    # duplicate the gate logic that already lives in that module.
    call_quality_audit: Optional[dict] = Field(
        None, description="PSM scorecard judgements; omit entirely unless asked for")

SYSTEM = (
    "You analyse call-centre transcripts for Sunrooof, an Indian company selling patented "
    "'wellness lighting' — artificial-skylight LED ceilings that recreate natural daylight "
    "indoors, sold as ~4-foot consoles with console-based pricing. It makes outbound sales calls. You will be given the diarized transcript of ONE call, "
    "plus the REAL agent and customer names from the CRM.\n\n"
    "STRICT RULES:\n"
    "1. Base every field ONLY on the transcript content provided. Do not use outside knowledge.\n"
    "2. NEVER invent or guess a person's name. The agent and customer identities are given to "
    "you from the CRM — do not replace or 'correct' them. If a name is not present in the data, "
    "leave the relevant field null or say 'unknown'. Do not fabricate.\n"
    "3. The transcript is machine-generated (Hindi/English/Telugu, romanised) and may contain "
    "errors — interpret charitably but do not invent facts that aren't there.\n"
    "4. If the call has no real conversation (voicemail, immediate hang-up, no answer), reflect "
    "that honestly in the outcome and summary.\n"
    "5. Keep `summary` to 1-2 short sentences, 35 words maximum. Lead with what happened. "
    "Do not open with the agent's or customer's name (they are already shown alongside), do "
    "not judge or rate the agent's politeness/professionalism there (those are separate "
    "numeric fields), and do not repeat objections, action items or next steps that belong "
    "in their own fields. Be specific over general: prefer 'wants a quote for two panels in the living room' "
    "to 'discussed requirements'.\n"
    "6. NEVER infer a budget, timeline, stakeholder or requirement that was not actually said. "
    "A null with confidence 'low' is correct and useful; a plausible guess is harmful, because "
    "these fields are read as real pipeline facts. Most calls are short and will legitimately "
    "have many nulls — that is the expected result, not a failure.\n"
    "7. Every `evidence` field must be text COPIED CHARACTER-FOR-CHARACTER from the transcript. "
    "To quote two separate moments, join them with ' ... ' — each piece must still be copied "
    "exactly. Never describe, summarise, translate or tidy up the wording; if you cannot copy "
    "an exact span, set evidence to null. Quotes are automatically checked against the "
    "transcript and silently discarded if they do not match, so an invented quote just loses "
    "the evidence.\n"
    "8. In `scorecard`, set applicable=false when the call gave no opportunity to demonstrate "
    "that behaviour, and leave score null. Do NOT score a dimension low because it did not "
    "happen. A voicemail, wrong number or 20-second call must come back with applicable=false "
    "across the board — the agent cannot be judged on a conversation that never took place. "
    "`objection_handling` is applicable ONLY if the customer actually raised an objection.\n"
    "9. `commitments` records promises that were genuinely made ('I'll send the catalogue "
    "today'). Only set `due` when a time was actually stated. `next_step_secured` is true only "
    "for a concrete agreed action, not for polite interest.\n\n"
    "Respond with ONLY a single JSON object matching this schema — no prose, no markdown fences, "
    "no explanation before or after:\n\n"
    f"{json.dumps(CallSummary.model_json_schema(), indent=2)}"
)

# ── PSM call-quality audit (opt-in second half of the same request) ────────
# The master prompt in prompts/call_quality_audit.md is the single source of
# truth for the scorecard wording, so it is read from disk rather than copied
# here — editing that file changes the audit without touching this script.
#
# What the model is asked for is deliberately NARROWER than the document's
# Section 12: judgements only. Every score, percentage, deduction, tier and
# analytics count is computed in scripts/call_quality.py afterwards. That keeps
# the arithmetic deterministic and saves roughly 1k output tokens per call.
QA_PROMPT_FILE = BASE / "prompts" / "call_quality_audit.md"

QA_JUDGEMENT_CONTRACT = """
=== CALL QUALITY AUDIT — ADDITIONAL TASK ===

Also populate the `call_quality_audit` key of your JSON response, applying the
SUNROOOF PSM scorecard reproduced below. Leave every other field unchanged.

Return JUDGEMENTS ONLY. Do NOT compute scores, points, percentages, totals,
deductions, tiers or counts — those are calculated downstream and anything you
put there is discarded. Emit exactly this shape:

{
  "criteria": [
    {
      "criterion_id": 1,
      "applicability": "applicable" | "not_applicable",
      "score_label": "full" | "half" | "zero",
      "reason": "one sentence; REQUIRED when applicability is not_applicable",
      "subpoints": [
        {
          "subpoint_id": "1.1",
          "status": "met" | "partial" | "not_met" | "not_applicable" | "unknown",
          "evidence": [{"timestamp": "0:42", "speaker": "PSM", "quote": "exact short quote"}],
          "notes": ""
        }
      ]
    }
  ],
  "critical_misses": [{"code": "CM-1", "observed": "yes"|"no"|"unknown", "evidence": [], "notes": ""}],
  "red_flags":      [{"code": "RF-1", "observed": "yes"|"no"|"unknown", "evidence": [], "notes": ""}],
  "qualitative_assessment": { ... as in Section 9 ... },
  "coaching": { ... as in Section 10 ... }
}

The `subpoints` array above shows ONE entry only to illustrate the shape. It is
NOT the required length. You must return EVERY sub-point id listed in the
checklist below for EVERY criterion — 12 criteria, all 5 critical misses, all 7
red flags. An incomplete criteria list or a criterion missing sub-points makes
the whole audit unusable and it will be discarded.

REQUIRED SUB-POINT IDS (return all of them, exactly these ids):
{subpoint_checklist}

Reminders that override any contrary habit:
- Judge the PSM's conduct only, never the customer's.
- Silence is not credit: if a complete transcript shows no evidence the PSM
  covered a required point, that point is not_met — never not_applicable.
- Do not use not_applicable to protect a weak call from a low score.
- Use `unknown` when the evidence needed is genuinely absent from what you were
  given (for example a fact you cannot verify against approved product data).
- Quotes must be verbatim from the transcript. Never invent a quote or a
  timestamp. Timestamps are shown as [m:ss] at the start of each line.
- The customer saying "Barton Bach" does NOT trigger CM-3; only the PSM saying,
  repeating or endorsing it does. Note the customer mention instead.

""".strip()


CONDUCT_PROMPT = """You are an experienced quality analyst for SUNROOOF, a luxury
wellness-lighting brand in India. You are reviewing ONE sales call transcript.

Judge only how the agent CONDUCTED themselves. Someone else scores the checklist;
your job is the things a checklist misses. Be specific and quote the transcript.

1. CUSTOMER'S LANGUAGE — BE VERY CONSERVATIVE HERE.

   Indians mix Hindi and English constantly. A customer speaking mostly Hindi does
   NOT mean they cannot follow English, and you must not assume it.

   ONLY treat the customer as not understanding English when there is an explicit
   signal, such as:
     - they ask the agent to speak in Hindi
     - they say they do not understand / ask for something to be repeated in Hindi
     - the agent opens in English and the customer answers in Hindi in a way that
       clearly asks for the switch, and the agent switches
   If none of that happened, set language_fit.appropriate = true and return an
   EMPTY flagged_terms list. Do not raise a language improvement at all.

   NEVER flag these, even on a Hindi call. They are technical terms, proper nouns
   or company vocabulary with no sensible Hindi equivalent — saying them in Hindi
   would confuse the customer more, not less:
     SUNROOOF, wellness, console, GPS, app, remote, catalogue, quotation,
     serotonin, melatonin, circadian, optics, optic lens, diffuser, nano tech,
     LED, driver, controller, IP40, productivity, psychological, hormone,
     vitamin D, UV, ultraviolet, frequency, sensor, modular, warranty, guarantee

   Flag ONLY ordinary high-register English that has an easy everyday Hindi word
   and is nothing to do with the product — for example "subsequently",
   "accommodate", "irrespective", "prerequisite", "endeavour". These are rare. On
   most calls flagged_terms should be empty.

2. UNSUPPORTED CLAIMS. Be very precise. A false critical flag against an agent who
   said nothing wrong is far worse than missing a borderline one, and most calls
   should have NO claims flagged.

   There are exactly two shapes, and only the first is wrong:

     (1) WRONG — "our product PREVENTS cancer / cures illness / stops disease".
         The product is credited with a medical outcome.
     (2) CORRECT — any statement that a harmful thing is ABSENT from our product,
         however the agent phrases it. "Ordinary kitchens contain formaldehyde
         which causes cancer, ours does not", "isme woh chemical hai hi nahi",
         "hamare product mein yeh nuksan wali cheez nahi hoti", "there is no UV
         in our light". The exact wording does not matter and the customer may
         have raised the topic first. Absence of a harmful substance is a true
         product property and agents are trained to explain it.

   Flag shape (1) only. Never flag shape (2).

   Also NEVER flag, because these are the approved, trained pitch:
     - psychological benefits, better mood, lower stress, improved sleep and sleep
       cycle, better focus, better productivity
     - serotonin and melatonin, and the circadian / sun cycle explanation
     - the light emits no ultraviolet, filters or blocks harmful rays
       ("filter karta hai", "rokta hai")
     - the absence of formaldehyde or any other harmful material
     - agreeing with something the CUSTOMER said, unless the agent then adds a
       medical outcome of their own

   Read who said what. If the customer raises cancer and the agent says "haan,
   filter karega", the agent agreed about FILTERING — not a cancer claim.

   When you do flag one, quote the AGENT'S own words containing the medical
   outcome.

3. LISTENING. Two separate checks:
   a) Did the agent interrupt or talk over the customer?
   b) Did the agent repeat an assumption the customer had ALREADY corrected? For
      example the customer says the house needs eight to nine months and the agent
      later says "even if it takes a year or a year and a half". Compare every
      figure the agent states (timeline, budget, rooms, city) against what the
      customer actually said earlier.

4. OPENING. "warm" = greeted by name, introduced themselves and the brand with
   energy, sounded pleased to call. "robotic" = read like a script, went straight to
   business with no warmth (e.g. "I have to discuss about your project"), flat and
   transactional like a telemarketer. "acceptable" = in between.

5. RAPPORT. Was the agent patient, friendly, willing to explain, checking the
   customer understood? Credit genuine warmth. Mark down brusqueness or impatience.

6. CALLBACK. Did the customer ask to be called at a particular time, and what did
   the agent agree to?

7. RULE-BOOK CHECKS. Answer each one explicitly — do not skip any. These come from
   real corrections the business has made, so they matter more than your general
   impression of the call.

   a) PROJECT CITY. Did the agent establish where the PROJECT / property is, as
      well as where the customer lives? A customer can live in Amritsar and be
      building in Mohali. Asking only "aap kaun se city mein based hain?" is NOT
      enough. If the project city was never established, set
      project_city_asked = false and raise an improvement suggesting:
      "Aur sir, jahan sunroof lagwana hai, wo property kis city mein hai?"
   b) "END USER". Did the agent say the words "end user" TO the customer? That is
      internal office vocabulary and must never be said to the person themselves.
      Asking "are you an architect?" or "yeh aapka apna ghar hai?" is correct.
      If they said it, set said_end_user = true and raise an improvement.

8. CRITICAL CHECKS. These decide whether the whole call scores zero, so answer them
   carefully and quote the transcript.
   a) INSTALL DEADLINE. Did the agent ask by when the customer needs SUNROOOF
      installed and ready? Answer "asked" if they asked in any form. If the customer
      could not give a date, did the agent PROMPT them — muhurat, Vastu date, before
      school reopens, during summer vacations, festival, possession date? Answer
      "prompted". The requirement is on the AGENT'S behaviour: a customer who simply
      does not know is NOT the agent's failure. Only answer "neither" when the agent
      never raised the subject of when it must be ready at all.
   b) GENUINE ATTEMPT. Did the agent make a real attempt to engage, or did the call
      end with no meaningful attempt? A short call where the customer was busy and a
      callback was agreed IS a genuine attempt.
   c) OLD BRAND NAME. Did the AGENT say "Barton Bach"? The customer saying it does
      not count.

9. IMPROVEMENTS — THE MOST IMPORTANT PART OF YOUR ANSWER.
   This portal exists so agents and managers can see WHERE a call went wrong and
   WHAT TO DO INSTEAD. A score alone teaches nobody anything.

   List every concrete improvement for this call. For each one give:
     - area: short label, e.g. "Opening", "Language", "Listening", "Pricing",
       "Product claim", "Discovery", "Next step"
     - what_went_wrong: one plain sentence, factual, no jargon
     - what_they_said: the agent's actual words (verbatim, with timestamp)
     - what_to_say_instead: the better line, written out in full and in the
       customer's language, ready to be said aloud.
       TONE MATTERS AS MUCH AS CONTENT. SUNROOOF is a luxury brand and the agent
       should sound like a warm, confident person having a conversation — never
       like a telecaller reading a script. Write natural, casual, friendly
       Hinglish the way people actually speak on the phone.
       Do NOT write formal literary Hindi. "Ghar mein prakritik roshni ka anubhav
       deti hai" is exactly wrong: stiff, textbook, and it makes the agent sound
       scripted. Say it the way a person would: "ghar mein bilkul natural light
       jaisa feel aata hai".
       Everyday English words inside Hindi are completely normal and correct —
       "how are you", "sorry", "ok", "thank you", "site", "price", "size",
       "time" and the like. Indians speak this way; do not strip them out or
       treat them as a problem. "Hello Aviral sir, how are you?" is perfectly
       good. Only genuinely difficult English should be replaced.
       Keep openings short and human rather than one long scripted block —
       "Hello Viral, kaise hain aap?" then let the customer respond, then
       "Vanshika bol rahi hoon Sunrooof se" — a real exchange, not a monologue.
     - severity: "critical" (risk to the brand or a lost sale) |
                 "important" (cost them ground) | "minor" (polish)

   Write 3-8 improvements for a substantial call, 1-3 for a short one. If the agent
   genuinely did something well, record it in `did_well` so praise is specific too.
   Never invent a quote.

Coaching must be addressed to the agent and developmental in tone — what to do
next time, not an accusation.

Return ONLY this JSON:
{
 "customer_language": "hindi|english|mixed|other",
 "language_fit": {"appropriate": true,
   "flagged_terms": [{"term":"","quote":"","suggestion":""}], "coaching": ""},
 "unsupported_claims": [{"claim":"","quote":"","timestamp":"","risk_level":"high|medium|low","why":""}],
 "listening": {"interrupted": false, "ignored_stated_information": false,
   "evidence": [{"timestamp":"","quote":""}], "coaching": ""},
 "opening_quality": {"rating":"warm|acceptable|robotic","evidence":{"timestamp":"","quote":""},"coaching":""},
 "rapport": {"rating":"excellent|good|neutral|poor","evidence":{"timestamp":"","quote":""},"note":""},
 "callback_commitment": {"requested": false, "agreed_time": "", "quote": ""},
 "improvements": [{"area":"","what_went_wrong":"","what_they_said":"","timestamp":"",
                   "what_to_say_instead":"","severity":"critical|important|minor"}],
 "did_well": [{"what":"","quote":""}],
 "rulebook_checks": {
   "project_city_asked": true, "project_city_quote": "",
   "said_end_user": false, "end_user_quote": ""
 },
 "critical_checks": {
   "install_deadline": {"status": "asked|prompted|neither", "quote": "", "timestamp": ""},
   "genuine_attempt": true,
   "agent_said_old_brand_name": false
 }
}"""


def _psm_only_text(entries, agent_sid):
    """Everything the PSM said, normalised for containment checks."""
    return _norm_words(" ".join((e.get("transcript") or "")
                                for e in entries if e.get("speaker_id") == agent_sid))


def _norm_words(text):
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


# A medical claim needs a disease or a cure in the AGENT'S OWN words. Agreeing
# that the product "filters" or "blocks" rays is a product property, not a health
# outcome — the customer may have raised cancer, but echoing "haan, filter karega"
# is not claiming to prevent it. Without this check the tool told a manager that
# Aparna claimed the product prevents cancer, which she never said.
_DISEASE_RE = re.compile(
    r"cancer|bimari|bimaari|disease|tumour|tumor|illness|cure|ilaaj|ilaj|"
    r"theek\s*ho\s*ja|thik\s*ho\s*ja|treat(ment)?|heal\b|medicine|dawa",
    re.I)

_LABEL_RE = re.compile(r"\[\d+:\d+\]|\b(PSM|Customer|Agent)\s*(\([^)]*\))?\s*:", re.I)


def _clean_quote(q):
    """Strip the '[0:22] PSM:' scaffolding the model copies from the transcript.

    Returns (normalised_text, explicitly_customer). The label matters: a quote the
    model itself tagged `Customer:` is the customer's words no matter what the
    finding claims.
    """
    q = q or ""
    explicit_customer = bool(re.search(r"\bCustomer\b\s*(\([^)]*\))?\s*:", q, re.I))
    return _norm_words(_LABEL_RE.sub(" ", q)), explicit_customer


_END_USER_RE = re.compile(r"\bend[\s\-]?user", re.I)


def enforce_end_user_rule(conduct, entries, agent_sid):
    """R7: the agent must never say "end user" to the customer.

    Done in code, not left to the model, because the phrase is exactly detectable
    and the model got it both ways — it set the flag on one run without raising
    any coaching, and its companion booleans contradicted their own findings.
    A regex over the PSM's turns cannot be wrong about whether the words occurred.
    """
    said = None
    for e in entries:
        if e.get("speaker_id") != agent_sid:
            continue
        t = (e.get("transcript") or "")
        if _END_USER_RE.search(t):
            secs = e.get("start_time_seconds") or 0
            said = (f"{int(secs)//60}:{int(secs)%60:02d}", t.strip()[:200])
            break

    checks = conduct.setdefault("rulebook_checks", {})
    checks["said_end_user"] = bool(said)
    if not said:
        return
    checks["end_user_quote"] = said[1]

    imps = conduct.setdefault("improvements", [])
    if isinstance(imps, list) and not any(
            isinstance(i, dict) and _END_USER_RE.search(
                f"{i.get('area','')} {i.get('what_went_wrong','')}") for i in imps):
        imps.append({
            "area": "Customer wording",
            "what_went_wrong": "Said \"end user\" to the customer. That is internal "
                               "office vocabulary and sounds impersonal to the person "
                               "themselves.",
            "what_they_said": said[1],
            "timestamp": said[0],
            "what_to_say_instead": "Yeh aapka apna ghar hai, ya aap architect ya "
                                   "designer hain?",
            "severity": "important",
        })


def drop_customer_attributed(conduct, psm_text):
    """Remove findings whose quote is not something the PSM actually said.

    The model repeatedly attributed the CUSTOMER's words to the agent — on one
    call it raised a CRITICAL "agreed the product prevents cancer" while quoting a
    line the transcript labels `Customer:`. The agent had only agreed the product
    filters UV, which is true and approved. Telling a manager their agent made a
    medical claim they never made is the worst error this tool can make, so it is
    checked mechanically rather than left to the prompt.
    """
    dropped = 0
    claims = conduct.get("unsupported_claims")
    if isinstance(claims, list):
        keep = []
        for c in claims:
            if not isinstance(c, dict):
                continue
            q, is_cust = _clean_quote(c.get("quote", ""))
            if is_cust or (q and len(q) > 25 and q[:60] not in psm_text):
                dropped += 1
                continue
            keep.append(c)
        conduct["unsupported_claims"] = keep

    # Drop "medical claim" findings where the agent never used a disease word.
    claims = conduct.get("unsupported_claims")
    if isinstance(claims, list):
        keep = []
        for c in claims:
            if isinstance(c, dict) and not _DISEASE_RE.search(c.get("quote") or ""):
                text = f"{c.get('claim','')} {c.get('why','')}"
                if _DISEASE_RE.search(text):
                    dropped += 1
                    continue
            keep.append(c)
        conduct["unsupported_claims"] = keep

    imps = conduct.get("improvements")
    if isinstance(imps, list):
        keep = []
        for i in imps:
            if not isinstance(i, dict):
                continue
            q, is_cust = _clean_quote(i.get("what_they_said", ""))
            if is_cust or (q and len(q) > 25 and q[:60] not in psm_text):
                dropped += 1
                continue
            # Same rule for a coaching item dressed up as a medical claim.
            said = i.get("what_they_said") or ""
            described = f"{i.get('area','')} {i.get('what_went_wrong','')}"
            if _DISEASE_RE.search(described) and not _DISEASE_RE.search(said):
                dropped += 1
                continue
            keep.append(i)
        conduct["improvements"] = keep
    return dropped


RULEBOOK_FILE = BASE / "prompts" / "RULEBOOK.md"


def conduct_prompt():
    """CONDUCT_PROMPT plus the rule book, read fresh from disk each call.

    The rule book is the single source of truth for how calls are judged. Reading
    it at runtime means a rule the user adds takes effect on the next call with no
    code change and no redeploy.
    """
    try:
        rules = RULEBOOK_FILE.read_text(encoding="utf-8")
    except OSError:
        return CONDUCT_PROMPT
    return (f"{CONDUCT_PROMPT}\n\n"
            f"=== RULE BOOK — these rules OVERRIDE anything above ===\n{rules}")


def assess_conduct(client, meta, transcript_text, model=None):
    """Second, focused pass for conduct.

    Kept separate from the scorecard call on purpose: asked for alongside 12
    criteria, 5 critical misses and 7 red flags, the conduct block came back
    empty or half-filled on most calls — the jargon scan and the listening checks
    need the model's full attention on a much smaller task.
    """
    user = (f"Agent: {meta['agent']}\nCustomer: {meta['customer']}\n\n"
            f"{meta.get('sequence_note', '')}"
            f"Transcript:\n{transcript_text}")
    try:
        resp = client.chat.completions.create(
            model=model or MODEL,
            messages=[{"role": "system", "content": conduct_prompt()},
                      {"role": "user", "content": user}],
            response_format={"type": "json_object"},
            temperature=0,
            **{("max_completion_tokens" if PROVIDER == "openai" else "max_tokens"): 4000},
        )
        if getattr(resp, "usage", None):
            with _USAGE_LOCK:
                USAGE["in"] += resp.usage.prompt_tokens or 0
                USAGE["out"] += resp.usage.completion_tokens or 0
        return json.loads(extract_json(resp.choices[0].message.content or "{}"))
    except Exception as e:
        print(f"  ⚠ conduct pass failed: {type(e).__name__}: {e}")
        return {}


def _subpoint_checklist():
    """Explicit per-criterion sub-point ids, generated from the scorecard.

    Without this the model imitates the single-entry `subpoints` example in the
    contract and returns one sub-point per criterion — measured on a real call:
    12 criteria returned but criterion 1 carried 1 of its 3 sub-points, with
    finish_reason 'stop' and only 4.4k of 16k output tokens used. It was
    following the example's shape, not the instruction, so it gets a checklist.
    """
    from call_quality import SCORECARD as _SC
    lines = []
    for spec in _SC:
        ids = ", ".join(sid for sid, _, _ in spec["subpoints"])
        mand = [sid for sid, _, m in spec["subpoints"] if m]
        suffix = f"   (MANDATORY: {', '.join(mand)})" if mand else ""
        lines.append(f"  C{spec['id']} {spec['name']} [{spec['max']} pts] -> {ids}{suffix}")
    return "\n".join(lines)


def qa_system_prompt():
    """SYSTEM + the scorecard document + the judgement contract."""
    scorecard = QA_PROMPT_FILE.read_text(encoding="utf-8")
    contract = QA_JUDGEMENT_CONTRACT.replace("{subpoint_checklist}", _subpoint_checklist())
    return f"{SYSTEM}\n\n{contract}\n\n=== SCORECARD ===\n{scorecard}"


# Loaded once: enrichment carries lead_source / campaign / property_type and the
# linked Lead or Contact id, none of which live on the Zoho Calls module.
_ENRICHMENT = None


def enrichment_for(call_id):
    global _ENRICHMENT
    if _ENRICHMENT is None:
        path = BASE / "out" / "zoho_enrichment.json"
        try:
            raw = json.loads(path.read_text())
        except (OSError, ValueError):
            raw = {}
        _ENRICHMENT = raw if isinstance(raw, dict) else {
            str(r.get("call_id")): r for r in raw if isinstance(r, dict)}
    return _ENRICHMENT.get(str(call_id)) or {}


def build_call_quality_audit(result, meta, call_id):
    """Expand the model's judgements into the scored Section 12 object.

    Dimensions we genuinely do not have (zone, branch, team, department, queue,
    country, and the WhatsApp/RAW-quote dates behind CM-4) are left null on
    purpose — Section 2 forbids substituting 'Unknown' or a guess, and the
    resulting `unknown` verdicts are what raise requires_human_review.
    See prompts/MISSING_DATA_REQUEST.md for the full list.
    """
    judgements = result.call_quality_audit or {}
    enrich = enrichment_for(call_id)
    start = meta.get("start_time") or ""

    audit_meta = {
        "call_id": call_id,
        "crm_link": f"https://crm.zoho.in/crm/tab/Calls/{call_id}",
        "lead_id": enrich.get("linked_id"),
        "evaluator_id": f"ai-{MODEL}",
        "evaluator_name": "Automated QA v1.0",
        "evaluation_date": _dt.date.today().isoformat(),
        "call_owner": meta.get("agent"),
        "client_name": meta.get("customer"),
        "call_direction": meta.get("call_type"),
        "call_date": start[:10] if start else None,
        "call_duration_seconds": meta.get("duration_seconds"),
        "language": getattr(result, "language", None),
        "lead_source": enrich.get("lead_source"),
        "campaign": enrich.get("campaign"),
        "property_type": enrich.get("property_type"),
        "city": enrich.get("city"),
        "state": enrich.get("state"),
        "call_disposition": enrich.get("crm_stage"),
        "sentiment_label": getattr(result, "customer_sentiment", None),
    }

    audit = build_audit(judgements, audit_meta)
    problems = validate_audit(audit)
    if problems:
        # Should be unreachable: the scorer computes these itself. Surfaced
        # rather than swallowed so a scorer regression cannot ship silently.
        audit["requires_human_review"] = True
        audit["audit_status"] = "human_review_required"
        audit["human_review_reasons"] = sorted(
            set(audit["human_review_reasons"]) | {f"scorer self-check: {p}" for p in problems})
    return audit

# ── Zoho auth + metadata (real names) ──────────────────────────────────────
_TOKEN = {"value": None, "expires_at": 0}

def get_token(force=False):
    """Zoho access token, cached in-process and on disk.

    Call this every iteration rather than once per run: tokens last 3600s and a
    full backfill takes longer than that. The old code fetched once up front, and
    because fetch_meta() treats any non-OK response as "no metadata", an expired
    token silently skipped every remaining call while the run still reported
    success.
    """
    now = time.time()
    if not force and _TOKEN["value"] and _TOKEN["expires_at"] > now + 120:
        return _TOKEN["value"]
    if not force:
        try:
            c = json.loads(TOKEN_CACHE.read_text())
            if c.get("token") and c.get("expiresAt", 0) > now * 1000 + 120_000:
                _TOKEN.update(value=c["token"], expires_at=c["expiresAt"] / 1000)
                return c["token"]
        except Exception:
            pass

    # Zoho rate-limits token generation, and parallel processes with no cache file
    # can burst past it — that surfaced as a transient "invalid_code" that killed a
    # whole run. Back off and retry rather than exiting.
    last = None
    for attempt in range(4):
        if attempt:
            time.sleep(2 ** attempt)
        r = requests.post(f"{ZOHO_ACC}/oauth/v2/token", data={
            "refresh_token": os.getenv("ZOHO_REFRESH_TOKEN"),
            "client_id":     os.getenv("ZOHO_CLIENT_ID"),
            "client_secret": os.getenv("ZOHO_CLIENT_SECRET"),
            "grant_type":    "refresh_token",
        }, timeout=30)
        d = r.json()
        if d.get("access_token"):
            exp = now + int(d.get("expires_in", 3600))
            _TOKEN.update(value=d["access_token"], expires_at=exp)
            try:
                TOKEN_CACHE.write_text(json.dumps(
                    {"token": d["access_token"], "expiresAt": int(exp * 1000)}))
            except OSError:
                pass          # cache is an optimisation, not a requirement
            return d["access_token"]
        last = d
        print(f"  ⚠ Zoho token attempt {attempt + 1}/4 failed: {last}")
    print("❌ Zoho token failed after 4 attempts:", last); sys.exit(1)

# Local copy of the Calls-module metadata (written by batch_transcribe's CDR
# scan). Serving meta from here first means a re-summarization run doesn't
# need Zoho at all for already-known calls — repeated runs died mid-batch on
# Zoho's OAuth rate limit (2026-08-10/11) purely to re-fetch names that never
# change. Cache miss still falls through to the network path.
CALLS_CACHE_FILE = BASE / "out" / "zoho_calls_cache.json"
try:
    _CALLS_CACHE = json.loads(CALLS_CACHE_FILE.read_text()) if CALLS_CACHE_FILE.exists() else {}
except Exception:
    _CALLS_CACHE = {}


def meta_from_cache(call_id):
    rec = _CALLS_CACHE.get(call_id)
    if not rec:
        return None
    cust = rec.get("What_Id") or rec.get("Who_Id") or {}
    return {
        "agent":    (rec.get("Owner") or {}).get("name") or "Unknown Agent",
        "customer": (cust or {}).get("name") or "Unknown",
        "call_type": rec.get("Call_Type") or "",
        "duration_seconds": int(rec.get("Call_Duration_in_seconds") or 0),
        "start_time": rec.get("Call_Start_Time"),
    }


_SEQUENCE = None


def sequence_for(call_id):
    """Which contact this is with the customer, from out/call_sequence.json.

    Built by scripts/build_call_sequence.py from the CRM record each call is
    attached to. Without it the scorecard demands an introduction and the full
    product pitch on every call, which is wrong on the 24% that are follow-ups.
    """
    global _SEQUENCE
    if _SEQUENCE is None:
        try:
            _SEQUENCE = json.loads((BASE / "out" / "call_sequence.json").read_text())
        except (OSError, ValueError):
            _SEQUENCE = {}
    return _SEQUENCE.get(str(call_id)) or {}


def sequence_note(call_id):
    """A short briefing line for the model, or '' on a first contact."""
    q = sequence_for(call_id)
    n = q.get("contact_number")
    if not n or n <= 1:
        return ""
    bits = [f"CALL HISTORY: this is contact number {n} of {q.get('total_contacts')} "
            f"between this agent and this customer — it is a FOLLOW-UP, not a first call."]
    if q.get("previous_call_date"):
        bits.append(f"The previous call was on {q['previous_call_date']}: "
                    f"{(q.get('previous_call_summary') or '').strip()}")
    for h in (q.get("history") or []):
        bits.append(f"Earlier call on {h.get('date')} ({h.get('outcome')}): "
                    f"{(h.get('summary') or '').strip()}")
    if q.get("already_covered"):
        what = "; ".join(a["what"] for a in q["already_covered"])
        bits.append(f"Confirmed already delivered earlier: {what}.")
    bits.append("Read the earlier call(s) above and work out what was ALREADY "
                "covered — the introduction, the wellness benefits, the technical "
                "explanation, pricing. Anything covered before does not need "
                "repeating: mark those criteria not_applicable and say which call "
                "covered them.")
    bits.append("Therefore: do NOT expect a fresh introduction, and do NOT mark the "
                "agent down for not repeating material already covered — treat those "
                "criteria as not applicable, naming the earlier call. Judge only what "
                "this call needed to do.")
    return "\n".join(bits) + "\n\n"


_SUMMARY_META = {}


def meta_from_summary(call_id):
    """Recover CRM metadata from our own call_summaries row.

    Zoho answers 204 for a Call record that has since been deleted or merged, so
    a call transcribed weeks ago can become un-lookupable and be skipped forever
    — 74 July calls stalled the audit this way. The names in call_summaries were
    themselves fetched from Zoho at summary time, so this is cached CRM truth,
    not a fabrication. Only ever used after a live lookup fails.
    """
    global _SUMMARY_META
    if not _SUMMARY_META:
        rows, offset, page = [], 0, 1000
        while True:
            r = requests.get(f"{SUPABASE_URL}/rest/v1/call_summaries",
                             headers=sb_headers({"Range": f"{offset}-{offset + page - 1}"}),
                             params={"select": "call_id,agent,customer,call_type,"
                                               "duration_seconds,start_time",
                                     "order": "call_id.asc"}, timeout=90)
            if not r.ok:
                break
            batch = r.json()
            rows.extend(batch)
            if len(batch) < page:
                break
            offset += page
        _SUMMARY_META = {x["call_id"]: x for x in rows}
    rec = _SUMMARY_META.get(str(call_id))
    if not rec:
        return None
    return {
        "agent": rec.get("agent") or "Unknown Agent",
        "customer": rec.get("customer") or "Unknown",
        "call_type": rec.get("call_type") or "",
        "duration_seconds": int(rec.get("duration_seconds") or 0),
        "start_time": rec.get("start_time"),
    }


def fetch_meta(token, call_id, _retried=False):
    """Fetch the CRM-verified agent/customer names for one call. Never fabricated."""
    fields = "id,Subject,Owner,Who_Id,What_Id,Call_Type,Call_Duration_in_seconds,Call_Start_Time"
    r = requests.get(f"{ZOHO_API}/crm/v7/Calls/{call_id}",
                     params={"fields": fields},
                     headers={"Authorization": f"Zoho-oauthtoken {token}"}, timeout=30)
    # 401 means the token aged out mid-run. Without this the call would be
    # silently skipped as "no CRM metadata", which looks identical to a genuinely
    # missing record.
    if r.status_code == 401 and not _retried:
        return fetch_meta(get_token(force=True), call_id, _retried=True)
    # 204 is a "successful" status (r.ok is True) but has an empty body — Zoho's
    # answer when the Call record no longer exists (deleted/merged since it was
    # transcribed). r.json() on an empty body raises, not a clean "not found",
    # so it must be checked before r.ok lets it through to the json() call below.
    if r.status_code == 204 or not r.ok:
        return None
    rec = (r.json().get("data") or [{}])[0]
    cust = rec.get("What_Id") or rec.get("Who_Id") or {}
    return {
        "agent":    (rec.get("Owner") or {}).get("name") or "Unknown Agent",
        "customer": cust.get("name") or "Unknown",
        "call_type": rec.get("Call_Type") or "",
        "duration_seconds": int(rec.get("Call_Duration_in_seconds") or 0),
        "start_time": rec.get("Call_Start_Time"),
    }

# ── Transcript helpers ─────────────────────────────────────────────────────
COMPANY_RE = re.compile(r"sun\s*ro+f", re.I)

def agent_speaker_id(entries):
    """Same heuristic as the dashboard: the speaker who names the company is the agent."""
    if not entries:
        return None
    brand = next((e for e in entries if COMPANY_RE.search(e.get("transcript", "") or "")), None)
    if brand:
        return brand.get("speaker_id")
    longe = next((e for e in entries if len((e.get("transcript") or "").strip()) > 20), None)
    if longe:
        return longe.get("speaker_id")
    counts = {}
    for e in entries:
        counts[e.get("speaker_id")] = counts.get(e.get("speaker_id"), 0) + 1
    return max(counts, key=counts.get) if counts else None

def talk_ratio(entries, agent_sid):
    """Free metric from diarization: share of spoken characters per side."""
    ac = cc = 0
    for e in entries:
        n = len((e.get("transcript") or "").strip())
        if e.get("speaker_id") == agent_sid:
            ac += n
        else:
            cc += n
    total = ac + cc
    if not total:
        return None, None
    return round(100 * ac / total), round(100 * cc / total)

def render_transcript(entries, agent_sid, agent_name, customer_name):
    lines = []
    for e in entries:
        who = agent_name if e.get("speaker_id") == agent_sid else customer_name
        t = (e.get("transcript") or "").strip()
        if t:
            lines.append(f"{who}: {t}")
    return "\n".join(lines)


def render_transcript_timestamped(entries, agent_sid, agent_name, customer_name):
    """Same text with [m:ss] markers, for the audit's evidence requirement.

    Kept separate from render_transcript deliberately: verify_evidence() matches
    the model's quotes against the PLAIN render, so timestamps never become part
    of the haystack and cannot make a fabricated quote look verifiable.
    Speakers are labelled PSM/Customer because the scorecard is written in those
    terms, with the real CRM name alongside so the model still uses it.
    """
    lines = []
    for e in entries:
        is_agent = e.get("speaker_id") == agent_sid
        who = f"PSM ({agent_name})" if is_agent else f"Customer ({customer_name})"
        t = (e.get("transcript") or "").strip()
        if not t:
            continue
        secs = e.get("start_time_seconds")
        stamp = f"[{int(secs) // 60}:{int(secs) % 60:02d}] " if isinstance(secs, (int, float)) else ""
        lines.append(f"{stamp}{who}: {t}")
    return "\n".join(lines)

# ── JSON extraction (the model may wrap JSON in prose/fences despite instructions) ──
def _norm(s):
    """Compare on letters+digits only: the transcripts are messy romanised
    Hinglish, so punctuation/spacing differences are not real mismatches."""
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())

def verify_evidence(result, transcript_text):
    """Delete any `evidence` string that isn't actually in the transcript.

    The whole point of evidence is that a manager can verify a claim, so it has
    to be checked rather than trusted. Measured on real calls, the model gets
    this right about 3/4 of the time: most quotes are verbatim or several real
    spans joined with "..." (fine, kept), but it sometimes writes a description
    instead of a quote ("Matched Hindi/English mix; courteous throughout") or
    reconstructs Hinglish it can't reproduce exactly. Those are dropped — a
    missing quote is honest, an invented one is not.

    Returns the number of quotes dropped.
    """
    tn = _norm(transcript_text)

    def is_real(quote):
        frags = [f for f in re.split(r"\.\.\.|…", quote) if _norm(f)]
        return bool(frags) and all(_norm(f) in tn for f in frags)

    dropped = 0
    def scrub(obj):
        nonlocal dropped
        if getattr(obj, "evidence", None) and not is_real(obj.evidence):
            obj.evidence = None
            dropped += 1

    scrub(result.budget_detail)
    scrub(result.timeline_detail)
    for o in result.objections_detail:
        scrub(o)
    for name in type(result.scorecard).model_fields:
        scrub(getattr(result.scorecard, name))
    return dropped

def extract_json(text):
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        return fence.group(1)
    start = text.find("{")
    if start == -1:
        raise ValueError("no JSON object found in response")
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == "{": depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    raise ValueError("unbalanced JSON object in response")

# ── LLM call with schema-validation retry ──────────────────────────────────
# Reasoning models (gpt-5*, gpt-oss) spend tokens "thinking" before writing the
# final answer, and that comes out of the same budget — so this needs real
# headroom or content comes back empty. The 30-field schema with evidence
# quotes is a much larger payload than the original, hence the extra room.
MAX_OUTPUT_TOKENS = 8000

USAGE = {"in": 0, "out": 0}  # accumulated across the run, for the cost readout

# ── Concurrency primitives ────────────────────────────────────────────────
# Wall-clock per call is dominated by generation latency (~15-20s), not by the
# inter-request delay, so throughput comes from running calls in parallel. The
# throttle below still spaces request *starts* across all workers so a large
# --workers value cannot burst past the account's per-minute limits.
_TOKEN_LOCK = threading.Lock()   # serialises Zoho token refresh across workers
_USAGE_LOCK = threading.Lock()
_THROTTLE_LOCK = threading.Lock()
_last_request_at = [0.0]


def _throttle():
    """Space request starts by MIN_INTERVAL, globally across all workers."""
    if MIN_INTERVAL <= 0:
        return
    with _THROTTLE_LOCK:
        wait = _last_request_at[0] + MIN_INTERVAL - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_request_at[0] = time.monotonic()


def token_limit_kwarg(with_audit=False):
    """OpenAI renamed max_tokens -> max_completion_tokens and rejects the old
    name on gpt-5*/o-series. OpenRouter still expects max_tokens.

    The audit roughly triples the output: 12 criteria x up to 10 sub-points,
    each with evidence quotes, plus 5 critical misses and 7 red flags. Running
    out mid-object costs the whole call, so it gets a much larger ceiling.
    """
    key = "max_completion_tokens" if PROVIDER == "openai" else "max_tokens"
    # 12000, not 16000: OpenAI reserves the FULL max_completion_tokens against
    # the account's tokens-per-minute limit whether or not the model uses it, so
    # an inflated ceiling directly costs throughput. Measured audit outputs on
    # real calls ran 4.4k-9.4k tokens, so this keeps ~28% headroom over the
    # largest observed while freeing 4k of TPM per request.
    return {key: 12000 if with_audit else MAX_OUTPUT_TOKENS}


def summarize(client, meta, transcript_text, retries=2, with_audit=False, model=None):
    user = (
        f"CRM-verified names (use these exactly, do not change or invent):\n"
        f"- Agent (Sunrooof): {meta['agent']}\n"
        f"- Customer: {meta['customer']}\n"
        f"- Call type: {meta['call_type']}\n\n"
        f"{meta.get('sequence_note', '')}"
        f"Transcript:\n{transcript_text if transcript_text.strip() else '(no speech detected)'}"
    )
    system = qa_system_prompt() if with_audit else SYSTEM
    model = model or MODEL
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]

    last_err = None
    for attempt in range(retries + 1):
        # temperature=0 for the audit. Without it the SDK default of 1.0 applies,
        # and a QA score is not a creative task: re-scoring the same 30 calls
        # twice moved them by a mean of 18.8 points and changed 40% of tiers,
        # with one call swinging 0 -> 63.5. That is unusable for grading an agent.
        # Only applied on the audit path so the summary-only pass — whose
        # sentiment output is frozen pending sign-off — is left untouched.
        extra = {"temperature": 0} if with_audit else {}
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            response_format={"type": "json_object"},
            **token_limit_kwarg(with_audit),
            **extra,
        )
        if getattr(resp, "usage", None):
            with _USAGE_LOCK:
                USAGE["in"]  += resp.usage.prompt_tokens or 0
                USAGE["out"] += resp.usage.completion_tokens or 0
        if not resp.choices:
            last_err = f"empty response from provider (no choices): {resp.model_dump()}"
            continue
        content = resp.choices[0].message.content
        if not content:
            last_err = "model returned no content (likely ran out of tokens mid-reasoning)"
            continue
        try:
            raw = extract_json(content)
            return CallSummary.model_validate(json.loads(raw))
        except (ValueError, json.JSONDecodeError, ValidationError) as e:
            last_err = e
            messages.append({"role": "assistant", "content": content})
            messages.append({"role": "user", "content":
                f"That response was not valid JSON matching the schema ({e}). "
                f"Respond again with ONLY the corrected JSON object."})
    raise RuntimeError(f"failed to get valid JSON after {retries + 1} attempts: {last_err}")

# ── Supabase persistence (raw REST, same pattern as sync_transcripts_to_supabase.py) ──
def sb_headers(extra=None):
    h = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    if extra:
        h.update(extra)
    return h

def fetch_summarized_ids():
    """Fetch every summarized ID despite the project's 100-row API cap."""
    ids, offset, page = set(), 0, 100
    while True:
        r = requests.get(f"{SUPABASE_URL}/rest/v1/call_summaries",
                          headers=sb_headers({"Range": f"{offset}-{offset + page - 1}"}),
                          params={"select": "call_id", "order": "call_id.asc"}, timeout=30)
        r.raise_for_status()
        rows = r.json()
        ids.update(row["call_id"] for row in rows)
        if len(rows) < page:
            break
        offset += page
    return ids

def fetch_ids_in_range(since=None, until=None):
    """Call IDs whose Zoho start_time falls in [since, until].

    Sourced from Supabase rather than the transcript filenames, which carry no
    date. Returns None when no bound is given so callers can skip filtering
    entirely rather than treating "no filter" as "no matches".
    """
    if not since and not until:
        return None
    # Explicit order is not cosmetic: PostgREST paging without ORDER BY has no
    # stable row order, so while the audit run is UPDATE-ing rows concurrently,
    # rows shift between pages and some are silently never returned. That is how
    # a July filter came back with 4,072 of ~5,004 calls.
    params = {"select": "call_id", "order": "call_id.asc"}
    if since:
        params["start_time"] = f"gte.{since}T00:00:00"
    if until:
        # PostgREST takes one value per key, so a two-sided range goes through
        # `and=(...)` instead of two conflicting start_time params.
        params.pop("start_time", None)
        clauses = []
        if since:
            clauses.append(f"start_time.gte.{since}T00:00:00")
        clauses.append(f"start_time.lte.{until}T23:59:59")
        params["and"] = f"({','.join(clauses)})"

    ids, offset, page = set(), 0, 1000
    while True:
        r = requests.get(f"{SUPABASE_URL}/rest/v1/call_summaries",
                          headers=sb_headers({"Range": f"{offset}-{offset + page - 1}"}),
                          params=params, timeout=60)
        if not r.ok:
            print(f"⚠ date filter query failed ({r.status_code}) — running unfiltered")
            return None
        rows = r.json()
        ids.update(row["call_id"] for row in rows)
        if len(rows) < page:
            return ids
        offset += page


def fetch_audited_ids():
    """IDs that already carry a call-quality audit, for resuming a long run."""
    ids, offset, page = set(), 0, 100
    while True:
        r = requests.get(f"{SUPABASE_URL}/rest/v1/call_summaries",
                          headers=sb_headers({"Range": f"{offset}-{offset + page - 1}"}),
                          params={"select": "call_id", "order": "call_id.asc",
                                  "call_quality_audit": "not.is.null"}, timeout=30)
        if not r.ok:      # column may not exist yet on an un-migrated database
            return set()
        rows = r.json()
        ids.update(row["call_id"] for row in rows)
        if len(rows) < page:
            break
        offset += page
    return ids


def save_summary(call_id, meta, a_pct, c_pct, num_turns, result: CallSummary, audit=None):
    row = {
        "call_id": call_id,
        "agent": meta["agent"], "customer": meta["customer"], "call_type": meta["call_type"],
        "start_time": meta["start_time"], "duration_seconds": meta["duration_seconds"],
        "agent_talk_pct": a_pct, "customer_talk_pct": c_pct, "num_turns": num_turns,
        "summary": result.summary, "call_outcome": result.call_outcome,
        "next_action": result.next_action, "customer_sentiment": result.customer_sentiment,
        "interest_level": result.interest_level, "agent_politeness": result.agent_politeness,
        "agent_professionalism": result.agent_professionalism,
        "professionalism_notes": result.professionalism_notes,
        "room_type": result.customer_requirements.room_type,
        "budget": result.customer_requirements.budget,
        "location": result.customer_requirements.location,
        "timeline": result.customer_requirements.timeline,
        "objections": result.objections, "action_items": result.action_items,
        "red_flags": result.red_flags, "language": result.language,
        "model": MODEL,

        # Flat columns — what the list view filters and aggregates on.
        # NB: `call_type` already holds Zoho's Inbound/Outbound direction, so
        # the model's classification goes to `call_category` to avoid clobbering it.
        "call_category": result.call_type,
        "property_context": result.property_context,
        "property_details": result.property_details,
        "conversion_likelihood": result.conversion_likelihood,
        "next_step_secured": result.next_step_secured,
        # Flattened so the list view can flag it without fetching `analysis`.
        "agent_commitment_due": any(
            c.who == "agent" and c.due for c in result.commitments),
        "competitor_mentioned": result.competitor_mentioned,
        "stakeholders": result.stakeholders,
        "buying_signals": result.buying_signals,
        "risk_flags": result.risk_flags,

        # Nested structures — only ever rendered on a single call's page, so
        # they live in one jsonb column rather than a dozen more columns.
        "analysis": {
            "budget": result.budget_detail.model_dump(),
            "timeline": result.timeline_detail.model_dump(),
            "objections": [o.model_dump() for o in result.objections_detail],
            "commitments": [c.model_dump() for c in result.commitments],
            "scorecard": result.scorecard.model_dump(),
            "coaching": {
                "did_well": result.did_well,
                "improvements": result.improvements,
                "suggested_followup": result.suggested_followup,
            },
        },
    }
    if audit is not None:
        # One jsonb column, plus the handful of fields the dashboard filters and
        # sorts on lifted flat so a list view never has to open the blob.
        score = audit.get("score", {})
        row.update({
            "call_quality_audit": audit,
            "qa_final_score": score.get("final_score"),
            "qa_tier": score.get("tier"),
            "qa_auto_zero": score.get("auto_zero"),
            "qa_requires_human_review": audit.get("requires_human_review"),
            "qa_critical_miss_codes": audit.get("analytics", {}).get("critical_miss_codes"),
            "qa_red_flag_codes": audit.get("analytics", {}).get("red_flag_codes"),
        })
    r = requests.post(f"{SUPABASE_URL}/rest/v1/call_summaries",
                       headers=sb_headers({"Prefer": "resolution=merge-duplicates,return=minimal"}),
                       data=json.dumps(row), timeout=30)
    if not r.ok:
        raise requests.HTTPError(
            f"{r.status_code} {r.reason}: {r.text[:1000]}", response=r)

# ── Main ───────────────────────────────────────────────────────────────────
def main():
    global MIN_INTERVAL
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default="", help="comma-separated call IDs")
    ap.add_argument("--limit", type=int, default=0, help="cap this run (0 = no cap, but daily-limit still applies)")
    ap.add_argument("--daily-limit", type=int, default=DAILY_LIMIT,
                     help=f"max requests this run (default {DAILY_LIMIT} for {PROVIDER})")
    ap.add_argument("--force", action="store_true",
                     help="re-summarize calls that already have a summary (e.g. after a prompt change)")
    ap.add_argument("--workers", type=int, default=1,
                     help="calls to process in parallel (default 1). Generation latency "
                          "dominates per-call time, so this is the real throughput lever; "
                          "--min-interval still spaces request starts across all workers")
    ap.add_argument("--min-interval", type=float, default=None,
                     help=f"seconds between request starts (default {MIN_INTERVAL} from env)")
    ap.add_argument("--since", default="", help="only calls on/after this date, YYYY-MM-DD")
    ap.add_argument("--until", default="", help="only calls on/before this date, YYYY-MM-DD")
    ap.add_argument("--redo-audited", action="store_true",
                     help="with --with-audit, re-audit calls that already have one "
                          "(e.g. after a scorer change)")
    ap.add_argument("--with-audit", action="store_true",
                     help="also produce the PSM call-quality audit (prompts/call_quality_audit.md). "
                          "Roughly 3x the cost per call — see prompts/MISSING_DATA_REQUEST.md for "
                          "what is still unverifiable")
    args = ap.parse_args()

    if args.min_interval is not None:
        MIN_INTERVAL = max(0.0, args.min_interval)

    if not API_KEY:
        if PROVIDER == "openai":
            print("❌ Missing OPENAI_API_KEY in .env — get one at platform.openai.com/api-keys")
        else:
            print("❌ Missing OPENROUTER_API_KEY in .env — get one at openrouter.ai/keys")
        sys.exit(1)
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("❌ Missing SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY in .env")
        sys.exit(1)

    # max_retries covers 429s and transient 5xxs with backoff, which matters on
    # a several-hundred-call run.
    client = OpenAI(api_key=API_KEY, base_url=BASE_URL, max_retries=5, timeout=180.0)

    done = fetch_summarized_ids()
    print(f"☁️  {len(done)} calls already summarized in Supabase"
          f"{' (--force: they will be redone)' if args.force else ''}")

    ids = list(filter(None, args.ids.split(",")))
    if not ids:
        if args.force:
            # Redo the already-summarized ones first (e.g. after a prompt change).
            ids = [f.name.removesuffix(".mp3.json") for f in sorted(TDIR.glob("*.json"))
                   if f.name.removesuffix(".mp3.json") in done]
        else:
            ids = [f.name.removesuffix(".mp3.json") for f in sorted(TDIR.glob("*.json"))
                   if f.name.removesuffix(".mp3.json") not in done]
    if args.since or args.until:
        in_range = fetch_ids_in_range(args.since or None, args.until or None)
        if in_range is not None:
            before = len(ids)
            ids = [i for i in ids if i in in_range]
            print(f"📅 date filter {args.since or 'start'} → {args.until or 'now'}: "
                  f"{len(ids)} of {before} call(s) in range")

    # --with-audit runs are long and expensive, so they resume rather than
    # restart: anything that already carries an audit is skipped even under
    # --force, which otherwise means "redo every summary".
    if args.with_audit and not args.redo_audited:
        audited = fetch_audited_ids()
        if audited:
            before = len(ids)
            ids = [i for i in ids if i not in audited]
            print(f"🔁 {before - len(ids)} call(s) already audited — skipping "
                  f"(use --redo-audited to force)")

    if args.limit:
        ids = ids[:args.limit]
    if len(ids) > args.daily_limit:
        print(f"🔒 Capping this run at {args.daily_limit} calls "
              f"({len(ids) - args.daily_limit} remain for a future run)")
        ids = ids[:args.daily_limit]
    if not ids:
        print("🎉 Nothing to summarize."); return

    print(f"🧠 Summarizing {len(ids)} call(s) with {MODEL} via {PROVIDER} "
          f"({args.workers} worker(s), {MIN_INTERVAL}s between request starts)\n")
    get_token()   # fail fast on bad credentials before spending on the LLM
    saved = 0

    def process_one(i, cid):
        """Handle one call end to end. Returns True if a summary was stored.

        Every failure path returns False rather than raising: one bad call must
        never take down a run of several hundred.
        """
        tpath = TDIR / f"{cid}.mp3.json"
        if not tpath.exists():
            print(f"  ⚠ [{i}] no transcript for {cid}"); return False
        data = json.loads(tpath.read_text())
        entries = data.get("diarized_transcript", {}).get("entries", [])

        # Deterministic pre-flight, before the CRM fetch and before the model.
        # A recording of an empty room is not a call, and the model does not
        # reliably say so: on the four confirmed dead recordings in the review
        # set it returned `not_reachable` for two and `follow_up_needed` with
        # politeness grades of 3/5 and 4/5 for the other two. Asking it to grade
        # ambient noise invites a fabricated grade, so it is never asked.
        gate = conversation_gate(entries)
        if gate["verdict"] == "no_contact":
            record_gated(cid, gate)
            print(f"  ⏭ [{i}] {cid}: {gate['reason']} — skipped, no model call",
                  flush=True)
            return False
        if gate["verdict"] == "sparse":
            # Not dropped: one member of this class is a real inbound call
            # behind 90s of hold music, and no word-count floor separates it
            # from genuine ambient noise. Assessed normally, logged for a human.
            record_gated(cid, gate)
            print(f"  ⚠ [{i}] {cid}: {gate['reason']} — assessed, flagged for review",
                  flush=True)

        # Throttled here rather than on entry: the limiter paces request STARTS,
        # and a call the gate just dropped makes no request. Sleeping before the
        # gate would spend MIN_INTERVAL per skipped call for nothing.
        _throttle()

        # Per-iteration, not hoisted: cached in-process, so this is free until
        # the token nears expiry, at which point it transparently refreshes.
        # A transient network blip (DNS hiccup, connection reset) here must
        # not kill the whole batch — it crashed a several-hundred-call run
        # outright on 2026-08-10 because this call had no try/except at all.
        try:
            with _TOKEN_LOCK:
                token = get_token()
            meta = (meta_from_cache(cid) or fetch_meta(token, cid)
                    or meta_from_summary(cid))
        except (Exception, SystemExit) as e:
            print(f"  ⚠ [{i}] network error fetching CRM meta for {cid}, skipping: {e}"); return False
        if meta is None:
            print(f"  ⚠ [{i}] could not fetch CRM meta for {cid}, skipping"); return False

        meta["sequence_note"] = sequence_note(cid)
        agent_sid = agent_speaker_id(entries)
        a_pct, c_pct = talk_ratio(entries, agent_sid)
        transcript_text = render_transcript(entries, agent_sid, meta["agent"], meta["customer"])
        prompt_text = (
            render_transcript_timestamped(entries, agent_sid, meta["agent"], meta["customer"])
            if args.with_audit else transcript_text
        )

        try:
            result = summarize(client, meta, prompt_text, with_audit=args.with_audit)
        except Exception as e:
            print(f"  ❌ [{i}] {cid}: {e}"); return False

        # Never store a quote that isn't in the transcript. Verified against the
        # plain render so the [m:ss] markers can't validate a fabricated quote.
        dropped = verify_evidence(result, transcript_text)

        audit = None
        if args.with_audit:
            try:
                conduct = assess_conduct(client, meta, prompt_text)
                if conduct:
                    enforce_end_user_rule(conduct, entries, agent_sid)
                    n = drop_customer_attributed(conduct, _psm_only_text(entries, agent_sid))
                    if n:
                        print(f"  ⚠ [{i}] dropped {n} finding(s) quoting the customer, "
                              f"not the agent", flush=True)
                    existing = result.call_quality_audit or {}
                    merged = dict(existing.get("conduct") or {})
                    merged.update(conduct)          # dedicated pass wins
                    existing["conduct"] = merged
                    result.call_quality_audit = existing
                audit = build_call_quality_audit(result, meta, cid)
            except Exception as e:
                print(f"  ⚠ [{i}] {cid}: audit scoring failed ({type(e).__name__}: {e})")

        try:
            save_summary(cid, meta, a_pct, c_pct, len(entries), result, audit)
        except requests.RequestException as e:
            print(f"  ❌ [{i}] {cid}: Supabase write failed: {e}"); return False

        note = f"  ({dropped} unverifiable quote{'s' if dropped != 1 else ''} dropped)" if dropped else ""
        print(f"  ✅ [{i}] {meta['agent']} → {meta['customer']}: "
              f"{result.call_outcome} / {result.customer_sentiment} / polite {result.agent_politeness}/5{note}",
              flush=True)
        return True

    if args.workers > 1:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(process_one, i, cid) for i, cid in enumerate(ids, 1)]
            for f in as_completed(futures):
                # process_one swallows its own errors; this guards against an
                # unforeseen one escaping and silently losing the rest of the run.
                try:
                    if f.result():
                        saved += 1
                except Exception as e:
                    print(f"  ❌ worker crashed: {type(e).__name__}: {e}", flush=True)
    else:
        for i, cid in enumerate(ids, 1):
            if process_one(i, cid):
                saved += 1

    print(f"\n✅ Saved {saved} summaries to Supabase.")

    if GATED["no_contact"] or GATED["sparse"]:
        print(f"   🚧 gate: {GATED['no_contact']} skipped as no_contact "
              f"(never sent to the model), {GATED['sparse']} flagged sparse "
              f"→ {GATED_LOG.relative_to(BASE)}")

    if USAGE["in"] or USAGE["out"]:
        line = f"   {USAGE['in']:,} input + {USAGE['out']:,} output tokens"
        rate = PRICING.get(MODEL)
        if rate:
            cost = USAGE["in"] / 1e6 * rate[0] + USAGE["out"] / 1e6 * rate[1]
            line += f" ≈ ${cost:.2f}"
        print(line)

    remaining = len([f for f in TDIR.glob("*.json")
                     if f.name.removesuffix(".mp3.json") not in done]) - saved
    if remaining > 0:
        tail = " — re-run tomorrow (free-tier daily cap)." if PROVIDER == "openrouter" else " — re-run to continue."
        print(f"   {remaining} calls still unsummarized{tail}")

if __name__ == "__main__":
    main()
