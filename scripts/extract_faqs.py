#!/usr/bin/env python3
"""
extract_faqs.py — Pull every question the CUSTOMER asked out of each call
transcript, with a verdict on how well the agent answered it.

One JSON file per call in out/faqs/{call_id}.json (mirrors out/transcripts/),
so the run is resumable and re-runs skip finished calls. Aggregation into
canonical FAQs happens later in scripts/aggregate_faqs.py — this script is
deliberately per-call only.

Speaker names come from `call_summaries` in Supabase (already CRM-verified by
summarize_calls.py) — no Zoho call needed here.

Requires OPENAI_API_KEY and SUPABASE_* in .env. Uses the same model as
summarize_calls.py (SUMMARY_MODEL, default gpt-4.1-mini).
"""
import os, sys, json, time, argparse, threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, List, Literal

from pydantic import BaseModel, Field, ValidationError
from dotenv import load_dotenv
import requests
from openai import OpenAI

sys.path.insert(0, str(Path(__file__).resolve().parent))
from summarize_calls import (  # noqa: E402
    agent_speaker_id, render_transcript, _norm, extract_json,
    MODEL, PROVIDER, API_KEY, BASE_URL, PRICING, token_limit_kwarg,
)

load_dotenv()

BASE = Path(__file__).resolve().parent.parent
TDIR = BASE / "out" / "transcripts"
FDIR = BASE / "out" / "faqs"

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

TOPICS = ["pricing", "product_specs", "materials", "design_options", "installation",
          "timeline", "service_area", "showroom_visit", "process", "warranty_service",
          "payment_terms", "company_info", "comparison", "maintenance", "other"]

class FAQItem(BaseModel):
    question: str = Field(description="the customer's question, paraphrased as one clear English question")
    topic: Literal["pricing", "product_specs", "materials", "design_options", "installation",
                   "timeline", "service_area", "showroom_visit", "process", "warranty_service",
                   "payment_terms", "company_info", "comparison", "maintenance", "other"]
    customer_quote: Optional[str] = Field(None, description="VERBATIM transcript quote where the customer asks it")
    answer_status: Literal["answered_clearly", "answered_partially", "deflected", "unanswered"] = Field(
        description="answered_clearly = direct, specific, complete; "
                    "answered_partially = vague, incomplete, or only half the question; "
                    "deflected = agent changed the subject or postponed without substance; "
                    "unanswered = agent never addressed it")
    agent_answer: Optional[str] = Field(None, description="short English summary of what the agent actually said in response; null if unanswered")
    agent_quote: Optional[str] = Field(None, description="VERBATIM quote of the agent's answer; null if none")
    notes: Optional[str] = Field(None, description="anything a sales trainer should know about how this was handled")

class CallFAQs(BaseModel):
    questions: List[FAQItem] = Field(description="every distinct information-seeking question the CUSTOMER asked; empty list if none")

PROMPT = """You are analysing a sales call transcript for Sunrooof, an Indian company selling patented "wellness lighting" — artificial-skylight LED ceilings that recreate natural daylight indoors, sold as ~4-foot consoles with console-based pricing (agents say "Sunrooof wellness lighting" on calls). The transcript is diarised and mostly romanised Hindi/Hinglish mixed with English.

Extract EVERY distinct information-seeking question the CUSTOMER asked the agent. Include questions asked indirectly ("aap log installation bhi karte ho kya" counts), but NOT small talk, call-logistics ("can you hear me"), or the agent's own questions.

CAUTION — speaker labels can be swapped by diarisation errors. Decide who is really the salesperson from CONTENT: the salesperson pitches Sunrooof daylight panels, asks about the customer's house/site/budget, offers visits and follow-ups; the customer is the person being sold to. A question like "what is the update on your house" is the SALESPERSON asking, never the customer, regardless of the label. Only extract questions genuinely asked BY the customer TO the salesperson. If the whole call contains none, return an empty list.

For each question judge how the AGENT handled it, using only what is actually in the transcript:
- answered_clearly: the agent gave a direct, specific, complete answer
- answered_partially: vague, incomplete, or answered only part of it
- deflected: changed the subject, said "I'll tell you later / someone will call you" with no substance
- unanswered: never addressed it at all

Quotes must be VERBATIM substrings of the transcript (romanised spelling and all). customer_quote is REQUIRED — a question without the verbatim line where the customer asks it will be discarded, so only extract questions you can quote. Never invent or clean up a quote.

Respond with ONLY a JSON object matching this schema:
{schema}

Transcript ({agent} = sales agent, {customer} = customer):
{transcript}"""

USAGE = {"in": 0, "out": 0}
_print_lock = threading.Lock()


def sb_headers():
    return {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}


def fetch_names():
    """call_id -> (agent, customer) from call_summaries, paged."""
    out, offset, page = {}, 0, 1000
    while True:
        r = requests.get(f"{SUPABASE_URL}/rest/v1/call_summaries",
                         headers={**sb_headers(), "Range": f"{offset}-{offset + page - 1}"},
                         params={"select": "call_id,agent,customer"}, timeout=30)
        r.raise_for_status()
        rows = r.json()
        for row in rows:
            out[row["call_id"]] = (row["agent"], row["customer"])
        if len(rows) < page:
            return out
        offset += page


def verify_quotes(result: CallFAQs, transcript_text: str) -> int:
    """Null out any quote that is not a verbatim substring (same policy as
    summarize_calls.verify_evidence: a missing quote is honest, an invented
    one is not). Returns count dropped."""
    tn = _norm(transcript_text)

    def is_real(q):
        import re
        frags = [f for f in re.split(r"\.\.\.|…", q) if _norm(f)]
        return bool(frags) and all(_norm(f) in tn for f in frags)

    dropped = 0
    for item in result.questions:
        if item.customer_quote and not is_real(item.customer_quote):
            item.customer_quote = None; dropped += 1
        if item.agent_quote and not is_real(item.agent_quote):
            item.agent_quote = None; dropped += 1
    return dropped


def extract_one(client, cid, names, retries=2):
    tpath = TDIR / f"{cid}.mp3.json"
    data = json.loads(tpath.read_text())
    entries = data.get("diarized_transcript", {}).get("entries", [])
    if not entries:
        return None, "empty transcript"

    agent, customer = names.get(cid, ("Agent", "Customer"))
    sid = agent_speaker_id(entries)
    transcript_text = render_transcript(entries, sid, agent, customer)
    if len(transcript_text.strip()) < 40:
        return None, "transcript too short"

    prompt = PROMPT.format(schema=json.dumps(CallFAQs.model_json_schema(), indent=1),
                           agent=agent, customer=customer, transcript=transcript_text)

    last = None
    for attempt in range(retries + 1):
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            **token_limit_kwarg())
        if resp.usage:
            USAGE["in"] += resp.usage.prompt_tokens or 0
            USAGE["out"] += resp.usage.completion_tokens or 0
        try:
            result = CallFAQs.model_validate_json(extract_json(resp.choices[0].message.content or ""))
            dropped = verify_quotes(result, transcript_text)
            return result, f"{dropped} quotes dropped" if dropped else None
        except (ValidationError, ValueError) as e:
            last = e
    return None, f"schema failure after retries: {last}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default="", help="comma-separated call IDs")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    if not API_KEY:
        print("❌ no LLM API key in .env"); sys.exit(1)
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("❌ Missing SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY in .env"); sys.exit(1)

    FDIR.mkdir(parents=True, exist_ok=True)
    print("☁️  loading CRM-verified names from call_summaries…")
    names = fetch_names()
    print(f"   {len(names)} calls have summaries (names available)")

    ids = list(filter(None, args.ids.split(",")))
    if not ids:
        ids = sorted(f.name.removesuffix(".mp3.json") for f in TDIR.glob("*.json"))
    if not args.force:
        ids = [i for i in ids if not (FDIR / f"{i}.json").exists()]
    if args.limit:
        ids = ids[:args.limit]
    if not ids:
        print("🎉 Nothing to extract."); return

    print(f"🧠 Extracting FAQs from {len(ids)} call(s) with {MODEL} via {PROVIDER}, "
          f"{args.workers} workers\n")

    client = OpenAI(api_key=API_KEY, base_url=BASE_URL, max_retries=5, timeout=180.0)
    done = failed = 0

    def work(cid):
        result, note = extract_one(client, cid, names)
        if result is None:
            return cid, None, note
        (FDIR / f"{cid}.json").write_text(
            json.dumps(result.model_dump(), indent=1, ensure_ascii=False))
        return cid, len(result.questions), note

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(work, cid): cid for cid in ids}
        for i, fut in enumerate(as_completed(futures), 1):
            cid = futures[fut]
            try:
                cid, nq, note = fut.result()
            except Exception as e:
                failed += 1
                with _print_lock:
                    print(f"  ❌ [{i}/{len(ids)}] {cid}: {e}")
                continue
            if nq is None:
                failed += 1
                with _print_lock:
                    print(f"  ⚠ [{i}/{len(ids)}] {cid}: {note}")
            else:
                done += 1
                with _print_lock:
                    print(f"  ✅ [{i}/{len(ids)}] {cid}: {nq} question(s)"
                          + (f"  ({note})" if note else ""))

    print(f"\n✅ {done} extracted, {failed} skipped/failed")
    price = PRICING.get(MODEL)
    if price and (USAGE["in"] or USAGE["out"]):
        cost = USAGE["in"] / 1e6 * price[0] + USAGE["out"] / 1e6 * price[1]
        print(f"💰 {USAGE['in']:,} in / {USAGE['out']:,} out tokens ≈ ${cost:.2f}")


if __name__ == "__main__":
    main()
