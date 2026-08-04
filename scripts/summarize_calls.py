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
from pathlib import Path
from typing import Optional, List, Literal
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator
from dotenv import load_dotenv
import requests
from openai import OpenAI

load_dotenv()

BASE = Path(__file__).resolve().parent.parent
TDIR = BASE / "out" / "transcripts"

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
    if not r.ok:
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
COMPANY_RE = re.compile(r"\bmag+p+ie|magpp?ie|mac ?pie|magpai|magpy\b", re.I)

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


def token_limit_kwarg():
    """OpenAI renamed max_tokens -> max_completion_tokens and rejects the old
    name on gpt-5*/o-series. OpenRouter still expects max_tokens."""
    key = "max_completion_tokens" if PROVIDER == "openai" else "max_tokens"
    return {key: MAX_OUTPUT_TOKENS}


def summarize(client, meta, transcript_text, retries=2):
    user = (
        f"CRM-verified names (use these exactly, do not change or invent):\n"
        f"- Agent (Sunrooof): {meta['agent']}\n"
        f"- Customer: {meta['customer']}\n"
        f"- Call type: {meta['call_type']}\n\n"
        f"Transcript:\n{transcript_text if transcript_text.strip() else '(no speech detected)'}"
    )
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]

    last_err = None
    for attempt in range(retries + 1):
        resp = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            response_format={"type": "json_object"},
            **token_limit_kwarg(),
        )
        if getattr(resp, "usage", None):
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
    """Paginated — PostgREST caps at 1000 rows/request by default."""
    ids, offset, page = set(), 0, 1000
    while True:
        r = requests.get(f"{SUPABASE_URL}/rest/v1/call_summaries",
                          headers=sb_headers({"Range": f"{offset}-{offset + page - 1}"}),
                          params={"select": "call_id"}, timeout=30)
        r.raise_for_status()
        rows = r.json()
        ids.update(row["call_id"] for row in rows)
        if len(rows) < page:
            break
        offset += page
    return ids

def save_summary(call_id, meta, a_pct, c_pct, num_turns, result: CallSummary):
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
    r = requests.post(f"{SUPABASE_URL}/rest/v1/call_summaries",
                       headers=sb_headers({"Prefer": "resolution=merge-duplicates,return=minimal"}),
                       data=json.dumps(row), timeout=30)
    r.raise_for_status()

# ── Main ───────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default="", help="comma-separated call IDs")
    ap.add_argument("--limit", type=int, default=0, help="cap this run (0 = no cap, but daily-limit still applies)")
    ap.add_argument("--daily-limit", type=int, default=DAILY_LIMIT,
                     help=f"max requests this run (default {DAILY_LIMIT} for {PROVIDER})")
    ap.add_argument("--force", action="store_true",
                     help="re-summarize calls that already have a summary (e.g. after a prompt change)")
    args = ap.parse_args()

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
    if args.limit:
        ids = ids[:args.limit]
    if len(ids) > args.daily_limit:
        print(f"🔒 Capping this run at {args.daily_limit} calls "
              f"({len(ids) - args.daily_limit} remain for a future run)")
        ids = ids[:args.daily_limit]
    if not ids:
        print("🎉 Nothing to summarize."); return

    print(f"🧠 Summarizing {len(ids)} call(s) with {MODEL} via {PROVIDER} "
          f"(paced at {MIN_INTERVAL}s/request)\n")
    get_token()   # fail fast on bad credentials before spending on the LLM
    saved = 0
    for i, cid in enumerate(ids, 1):
        if i > 1:
            time.sleep(MIN_INTERVAL)

        tpath = TDIR / f"{cid}.mp3.json"
        if not tpath.exists():
            print(f"  ⚠ [{i}] no transcript for {cid}"); continue
        data = json.loads(tpath.read_text())
        entries = data.get("diarized_transcript", {}).get("entries", [])

        # Per-iteration, not hoisted: cached in-process, so this is free until
        # the token nears expiry, at which point it transparently refreshes.
        meta = fetch_meta(get_token(), cid)
        if meta is None:
            print(f"  ⚠ [{i}] could not fetch CRM meta for {cid}, skipping"); continue

        agent_sid = agent_speaker_id(entries)
        a_pct, c_pct = talk_ratio(entries, agent_sid)
        transcript_text = render_transcript(entries, agent_sid, meta["agent"], meta["customer"])

        try:
            result = summarize(client, meta, transcript_text)
        except Exception as e:
            print(f"  ❌ [{i}] {cid}: {e}"); continue

        # Never store a quote that isn't in the transcript.
        dropped = verify_evidence(result, transcript_text)

        try:
            save_summary(cid, meta, a_pct, c_pct, len(entries), result)
        except requests.RequestException as e:
            print(f"  ❌ [{i}] {cid}: Supabase write failed: {e}"); continue

        saved += 1
        note = f"  ({dropped} unverifiable quote{'s' if dropped != 1 else ''} dropped)" if dropped else ""
        print(f"  ✅ [{i}] {meta['agent']} → {meta['customer']}: "
              f"{result.call_outcome} / {result.customer_sentiment} / polite {result.agent_politeness}/5{note}")

    print(f"\n✅ Saved {saved} summaries to Supabase.")

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
