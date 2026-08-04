#!/usr/bin/env python3
"""
enrich_for_ci.py — One LLM pass per call filling the Call-Intelligence fields
that neither `call_summaries` nor the FAQ extraction already carry:

  · segmented sentiment (opening / mid / closing, emotions, unresolved-negative)
  · purchase-readiness sub-scores (docs/08 weights)
  · Voice-of-Customer themes (appreciation / dissatisfaction / feature requests /
    expectations / pain points), topics, entities
  · objection classification into the dashboard taxonomy (type, intensity,
    technique, resolution, customer reaction)
  · per-FAQ sentiment-after + escalation-needed
  · quality dimensions the existing scorecard lacks (solution relevance,
    listening, script adherence) + compliance flags
  · outcome mapped to the dashboard's 10-value taxonomy, decision-maker,
    cross-sell, discount-requested, customer-type fallback

Existing extractions are passed in as context so the model classifies rather
than re-derives. Verbatim evidence is verified against the transcript and
dropped when unverifiable — same policy as summarize_calls.py.

    python scripts/enrich_for_ci.py --limit 5    # smoke test
    python scripts/enrich_for_ci.py              # all calls, resumable

Writes one file per call to out/ci_enrichment/{call_id}.json.
"""
import os, re, sys, json, time, argparse, threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, List, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator
from dotenv import load_dotenv
import requests
from openai import OpenAI

sys.path.insert(0, str(Path(__file__).resolve().parent))
from summarize_calls import (  # noqa: E402
    agent_speaker_id, _norm, extract_json,
    MODEL, PROVIDER, API_KEY, BASE_URL, PRICING,
)

load_dotenv()

BASE = Path(__file__).resolve().parent.parent
TDIR = BASE / "out" / "transcripts"
FDIR = BASE / "out" / "faqs"
EDIR = BASE / "out" / "ci_enrichment"

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

MAX_OUTPUT_TOKENS = 4000

OBJECTION_TYPES = ["Price / discount", "Budget", "Timing", "Product suitability",
                   "Product quality", "Trust", "Installation", "Warranty / service",
                   "Competitor preference", "Decision-maker unavailable", "Serviceability",
                   "Payment terms", "Not interested"]
OUTCOMES = ["Interested — follow-up", "Quotation requested", "Site visit scheduled",
            "Demo scheduled", "Order confirmed", "Callback requested", "Complaint raised",
            "Not interested", "No requirement", "Not connected"]
CUSTOMER_TYPES = ["New lead", "Existing customer", "Dealer", "Architect/Designer"]
EMOTIONS = ["frustration", "confusion", "hesitation", "urgency", "trust", "interest", "satisfaction"]


# The model is given the legacy call_outcome as context and sometimes echoes it
# instead of classifying into the dashboard taxonomy. Mapping it is strictly
# better than discarding an otherwise-good enrichment.
LEGACY_OUTCOME = {
    "interested": "Interested — follow-up",
    "follow_up_needed": "Interested — follow-up",
    "callback_requested": "Callback requested",
    "not_interested": "Not interested",
    "not_reachable": "Not connected",
    "wrong_number": "No requirement",
    "already_purchased": "Order confirmed",
    "unclear": "Interested — follow-up",
}


class Sentiment(BaseModel):
    opening: float = Field(description="customer sentiment in the first third, -1 (very negative) to 1 (very positive)")
    mid: float = Field(description="customer sentiment in the middle third, -1..1")
    closing: float = Field(description="customer sentiment in the final third, -1..1")
    emotions: List[str] = Field(default_factory=list, description=f"observed customer emotions, ONLY from this list: {', '.join(EMOTIONS)}")
    unresolved_negative: bool = Field(description="true if the call ended with the customer still negative and nothing resolved")

    @field_validator("opening", "mid", "closing")
    @classmethod
    def _clamp(cls, v):
        return max(-1.0, min(1.0, float(v)))

    @field_validator("emotions", mode="before")
    @classmethod
    def _known_only(cls, v):
        # Models volunteer "neutral", "curiosity" etc.; the UI only renders the
        # documented set, so silently drop anything outside it.
        if not isinstance(v, list):
            return []
        return [e for e in v if isinstance(e, str) and e.lower() in EMOTIONS]


class Readiness(BaseModel):
    need_fit: int = Field(description="0-100: how well a stated need matches what Sunrooof sells")
    explicit_intent: int = Field(description="0-100: explicit buying intent expressed")
    timeline: int = Field(description="0-100: how near-term the stated purchase timeline is; 0 if none stated")
    next_step_commitment: int = Field(description="0-100: strength of the agreed next step")
    authority: int = Field(description="0-100: evidence the speaker can decide")
    budget: int = Field(description="0-100: budget clarity/readiness; 0 if never discussed")
    sentiment: int = Field(description="0-100: customer sentiment as a readiness signal")


class ObjectionOut(BaseModel):
    type: Literal[tuple(OBJECTION_TYPES)] = Field(description="closest matching objection type")  # type: ignore
    intensity: Literal["low", "medium", "high"]
    statement: Optional[str] = Field(None, description="VERBATIM customer quote raising it; null if not quotable")
    employee_response: str = Field(description="short English summary of how the agent responded; '' if no response")
    technique: str = Field(description="short label for the technique the agent used, e.g. 'Value reframing'; 'None' if unaddressed")
    resolution: Literal["resolved", "partial", "unresolved"]
    customer_reaction: Literal["positive", "neutral", "negative"]


class FaqExtra(BaseModel):
    question: str = Field(description="the question text, copied EXACTLY from the provided list")
    sentiment_after: Literal["positive", "neutral", "negative"] = Field(description="customer's reaction right after the answer")
    escalation_needed: bool = Field(description="true if this needed a specialist/manager the agent could not provide")


class QualityExtra(BaseModel):
    solution_relevance: int = Field(description="0-100: how well the pitch matched the stated need; 0 if no pitch happened")
    listening: int = Field(description="0-100: listening behaviour — not interrupting, acknowledging, building on answers")
    script_adherence: int = Field(description="0-100: adherence to a standard sales-call structure")
    compliance_flags: List[str] = Field(default_factory=list, description="specific policy breaches actually observed (unapproved discount, overstated warranty, unverified delivery promise, payment to personal number, PII mishandling). Empty when none.")


class Enrichment(BaseModel):
    sentiment: Sentiment
    readiness: Readiness
    topics: List[str] = Field(default_factory=list, description="3-6 short business topics discussed")
    appreciation_themes: List[str] = Field(default_factory=list, description="things the customer praised; empty if none")
    dissatisfaction_themes: List[str] = Field(default_factory=list, description="things the customer complained about; empty if none")
    feature_requests: List[str] = Field(default_factory=list)
    expectations: List[str] = Field(default_factory=list, description="what the customer expects from the company")
    pain_points: List[str] = Field(default_factory=list)
    entities: List[dict] = Field(default_factory=list, description="[{text, type}] with type in: person, place, product, brand, money, date, measurement")
    decision_maker: Literal["yes", "no", "unknown"]
    cross_sell: Optional[str] = Field(None, description="cross-sell/upsell opportunity evident in the call; null if none")
    discount_requested: bool
    # Optional: on a handful of very short calls the model omits these. The
    # builder then falls back to real CRM values (Zoho client type, legacy
    # call_outcome) rather than this pass guessing one.
    customer_type: Optional[Literal[tuple(CUSTOMER_TYPES)]] = None  # type: ignore
    outcome: Optional[Literal[tuple(OUTCOMES)]] = Field(None, description="best-fitting call outcome")  # type: ignore
    product_mentioned: Optional[str] = Field(None, description="Sunrooof product/range/console type actually named in the call; null if none")
    objections: List[ObjectionOut] = Field(default_factory=list)
    faq_extras: List[FaqExtra] = Field(default_factory=list)
    quality: QualityExtra

    @field_validator("outcome", mode="before")
    @classmethod
    def _map_legacy(cls, v):
        return LEGACY_OUTCOME.get(v, v) if isinstance(v, str) else v

    @field_validator("readiness", mode="after")
    @classmethod
    def _clamp_scores(cls, v):
        for name in Readiness.model_fields:
            setattr(v, name, max(0, min(100, int(getattr(v, name)))))
        return v


PROMPT = """You are analysing one sales call for Sunrooof, an Indian company selling patented "wellness lighting" — artificial-skylight LED ceiling consoles (~4 ft each, console-based pricing) that recreate natural daylight indoors. The diarised transcript is romanised Hindi/Hinglish mixed with English.

Speaker roles are decided by CONTENT, not by label: the SALESPERSON pitches Sunrooof, asks about the customer's house/site/budget and offers visits; the CUSTOMER is being sold to.

Previously extracted facts for this call (use as context — classify, do not contradict):
{context}

Fill ONLY the requested fields, grounded strictly in the transcript:
- Sentiment is about the CUSTOMER's feelings, judged from words alone (no voice-tone claims). Score the first/middle/final third separately.
- Purchase-readiness sub-scores are 0-100 each. Score 0 for anything never discussed — do NOT infer a budget or timeline that was never mentioned.
- Classify each objection listed above into the fixed type list. If the list is empty, return an empty objections array — do not invent objections.
- For faq_extras, copy each question EXACTLY as given and judge only the customer's reaction and whether escalation was needed. If no questions were listed, return an empty array.
- compliance_flags: only breaches you can actually observe. Empty list is the correct answer for most calls.
- `outcome` MUST be copied exactly from the dashboard's ten allowed values in the schema. The `existing_outcome` in the context above uses a DIFFERENT, older vocabulary — translate it, never echo it.
- Any verbatim quote must be an EXACT substring of the transcript. If you cannot quote exactly, use null.

Respond with ONLY a JSON object matching this schema:
{schema}

Transcript ({agent} = salesperson, {customer} = customer):
{transcript}"""

USAGE = {"in": 0, "out": 0}
_lock = threading.Lock()


def sb_headers():
    return {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}


def fetch_summaries():
    out, offset, page = {}, 0, 1000
    cols = ("call_id,agent,customer,call_outcome,customer_sentiment,interest_level,summary,"
            "objections,buying_signals,risk_flags,red_flags,competitor_mentioned,budget,"
            "timeline,room_type,stakeholders,action_items,analysis,duration_seconds")
    while True:
        r = requests.get(f"{SUPABASE_URL}/rest/v1/call_summaries",
                         headers={**sb_headers(), "Range": f"{offset}-{offset+page-1}"},
                         params={"select": cols}, timeout=30)
        r.raise_for_status()
        rows = r.json()
        for row in rows:
            out[row["call_id"]] = row
        if len(rows) < page:
            return out
        offset += page


def render_transcript_ts(entries, agent_sid, agent_name, customer_name):
    """Same as summarize_calls.render_transcript but keeps the timestamp, which
    the model needs to place sentiment across the call's thirds."""
    lines = []
    for e in entries:
        who = agent_name if e.get("speaker_id") == agent_sid else customer_name
        t = (e.get("transcript") or "").strip()
        if t:
            lines.append(f"[{int(e.get('start_time_seconds') or 0)}s] {who}: {t}")
    return "\n".join(lines)


def verify(result: Enrichment, transcript_text: str) -> int:
    tn = _norm(transcript_text)

    def is_real(q):
        frags = [f for f in re.split(r"\.\.\.|…", q) if _norm(f)]
        return bool(frags) and all(_norm(f) in tn for f in frags)

    dropped = 0
    for o in result.objections:
        if o.statement and not is_real(o.statement):
            o.statement = None
            dropped += 1
    return dropped


def build_context(summ, faq_questions):
    a = summ.get("analysis") or {}
    return json.dumps({
        "summary": summ.get("summary"),
        "existing_outcome": summ.get("call_outcome"),
        "overall_sentiment": summ.get("customer_sentiment"),
        "interest_level": summ.get("interest_level"),
        "objections_found": summ.get("objections") or [],
        "objection_detail": a.get("objections") or [],
        "buying_signals": summ.get("buying_signals") or [],
        "risk_flags": (summ.get("risk_flags") or []) + (summ.get("red_flags") or []),
        "competitor": summ.get("competitor_mentioned"),
        "budget": summ.get("budget"),
        "timeline": summ.get("timeline"),
        "room_type": summ.get("room_type"),
        "stakeholders": summ.get("stakeholders") or [],
        "questions_customer_asked": faq_questions,
    }, ensure_ascii=False, indent=1)


def enrich_one(client, cid, summ, retries=2):
    tpath = TDIR / f"{cid}.mp3.json"
    if not tpath.exists():
        return None, "no transcript"
    data = json.loads(tpath.read_text())
    entries = data.get("diarized_transcript", {}).get("entries", [])
    if not entries:
        return None, "empty transcript"

    agent = summ.get("agent") or "Agent"
    customer = summ.get("customer") or "Customer"
    sid = agent_speaker_id(entries)
    transcript_text = render_transcript_ts(entries, sid, agent, customer)
    if len(transcript_text.strip()) < 40:
        return None, "transcript too short"

    fpath = FDIR / f"{cid}.json"
    faq_questions = []
    if fpath.exists():
        faq_questions = [q["question"] for q in json.loads(fpath.read_text()).get("questions", [])]

    prompt = PROMPT.format(
        context=build_context(summ, faq_questions),
        schema=json.dumps(Enrichment.model_json_schema(), indent=1),
        agent=agent, customer=customer, transcript=transcript_text)

    key = "max_completion_tokens" if PROVIDER == "openai" else "max_tokens"
    last = None
    for _ in range(retries + 1):
        resp = client.chat.completions.create(
            model=MODEL, messages=[{"role": "user", "content": prompt}],
            temperature=0.1, **{key: MAX_OUTPUT_TOKENS})
        if resp.usage:
            with _lock:
                USAGE["in"] += resp.usage.prompt_tokens or 0
                USAGE["out"] += resp.usage.completion_tokens or 0
        try:
            result = Enrichment.model_validate_json(
                extract_json(resp.choices[0].message.content or ""))
            dropped = verify(result, transcript_text)
            payload = result.model_dump()
            # Diarisation-derived, no LLM needed: real interruption and silence
            # metrics straight off the Sarvam timestamps.
            payload["talk_metrics"] = talk_metrics(entries, sid)
            payload["asr_confidence"] = data.get("language_probability")
            return payload, (f"{dropped} quotes dropped" if dropped else None)
        except (ValidationError, ValueError) as e:
            last = e
    return None, f"schema failure: {last}"


def talk_metrics(entries, agent_sid):
    """Interruptions = a turn starting before the previous one ended.
    Longest silence = biggest gap between consecutive turns."""
    interruptions, longest = 0, 0.0
    prev_end, prev_spk = None, None
    for e in entries:
        s = e.get("start_time_seconds")
        en = e.get("end_time_seconds")
        if s is None or en is None:
            continue
        if prev_end is not None:
            if s < prev_end - 0.15 and e.get("speaker_id") != prev_spk:
                interruptions += 1
            longest = max(longest, s - prev_end)
        prev_end, prev_spk = en, e.get("speaker_id")
    return {"interruptions": interruptions, "longest_silence_sec": round(max(0.0, longest), 1)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default="")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    if not API_KEY:
        sys.exit("❌ no LLM API key in .env")
    if not SUPABASE_URL or not SUPABASE_KEY:
        sys.exit("❌ Missing SUPABASE_* in .env")

    EDIR.mkdir(parents=True, exist_ok=True)
    print("☁️  loading call_summaries…")
    summaries = fetch_summaries()
    print(f"   {len(summaries)} summarised calls")

    ids = list(filter(None, args.ids.split(","))) or sorted(summaries.keys())
    if not args.force:
        ids = [i for i in ids if not (EDIR / f"{i}.json").exists()]
    if args.limit:
        ids = ids[:args.limit]
    if not ids:
        print("🎉 Nothing to enrich."); return

    print(f"🧠 Enriching {len(ids)} call(s) with {MODEL} via {PROVIDER}, {args.workers} workers\n")
    client = OpenAI(api_key=API_KEY, base_url=BASE_URL, max_retries=5, timeout=240.0)
    done = failed = 0

    def work(cid):
        payload, note = enrich_one(client, cid, summaries.get(cid, {}))
        if payload is None:
            return cid, False, note
        (EDIR / f"{cid}.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))
        return cid, True, note

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(work, cid): cid for cid in ids}
        for i, fut in enumerate(as_completed(futs), 1):
            cid = futs[fut]
            try:
                cid, ok, note = fut.result()
            except Exception as e:
                failed += 1
                with _lock:
                    print(f"  ❌ [{i}/{len(ids)}] {cid}: {e}")
                continue
            if ok:
                done += 1
                with _lock:
                    print(f"  ✅ [{i}/{len(ids)}] {cid}" + (f"  ({note})" if note else ""))
            else:
                failed += 1
                with _lock:
                    print(f"  ⚠ [{i}/{len(ids)}] {cid}: {note}")

    print(f"\n✅ {done} enriched, {failed} skipped/failed")
    price = PRICING.get(MODEL)
    if price and (USAGE["in"] or USAGE["out"]):
        cost = USAGE["in"] / 1e6 * price[0] + USAGE["out"] / 1e6 * price[1]
        print(f"💰 {USAGE['in']:,} in / {USAGE['out']:,} out tokens ≈ ${cost:.2f}")


if __name__ == "__main__":
    main()
