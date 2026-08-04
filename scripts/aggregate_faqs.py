#!/usr/bin/env python3
"""
aggregate_faqs.py — Turn the per-call question extractions (out/faqs/*.json,
written by extract_faqs.py) into the dashboard's FAQ analysis:

1. Cluster near-duplicate questions into canonical FAQs (LLM, per topic —
   diarised Hinglish phrasings of "do you do installation?" vary wildly).
2. Compute per-FAQ stats in code: ask counts, per-region counts, how often it
   was answered clearly / partially / deflected / never.
3. Regional contrast: which FAQs are over-represented in each region vs the
   overall distribution (lift), plus a topic × region matrix.
4. "Needs clarification" set: FAQs that mostly go unanswered or vague. For each,
   draft a suggested canonical answer USING ONLY facts agents actually gave in
   well-answered instances of the same question elsewhere; where no such source
   exists the draft is guidance-only and flagged needs_confirmation so the
   business supplies the real facts before anyone trains on it.
5. Publish to out/faq_analysis.json AND Supabase app_kv (key 'faq_analysis'),
   which /api/faqs serves. app_kv is used because this Supabase project's DDL
   is outside our reach — no new tables needed.

Regions come from transcripts.state/city (backfill_call_states.py).
"""
import os, sys, json, argparse, datetime
from pathlib import Path
from collections import Counter, defaultdict

from dotenv import load_dotenv
import requests
from openai import OpenAI

sys.path.insert(0, str(Path(__file__).resolve().parent))
from summarize_calls import extract_json, MODEL, PROVIDER, API_KEY, BASE_URL, PRICING  # noqa: E402

load_dotenv()

BASE = Path(__file__).resolve().parent.parent
FDIR = BASE / "out" / "faqs"
OUT_FILE = BASE / "out" / "faq_analysis.json"

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# City → region buckets. City is the deciding field; a state-only row can still
# be bucketed when the state implies the metro (Delhi). Everything else with
# any location at all is "Other", no location is "Unknown".
CITY_REGION = {
    "bangalore": "Bengaluru", "bengaluru": "Bengaluru",
    "hyderabad": "Hyderabad", "secunderabad": "Hyderabad",
    "mumbai": "Mumbai", "navi mumbai": "Mumbai", "thane": "Mumbai",
    "pune": "Pune",
    "delhi ncr": "Delhi NCR", "delhi": "Delhi NCR", "new delhi": "Delhi NCR",
    "gurgaon": "Delhi NCR", "gurugram": "Delhi NCR", "noida": "Delhi NCR",
    "greater noida": "Delhi NCR", "ghaziabad": "Delhi NCR", "faridabad": "Delhi NCR",
    "surat": "Gujarat", "ahmedabad": "Gujarat", "vadodara": "Gujarat",
    "rajkot": "Gujarat", "gandhinagar": "Gujarat",
    "kolkata": "Kolkata", "howrah": "Kolkata",
    "chennai": "Chennai",
}
STATE_REGION = {"delhi": "Delhi NCR", "delhi (national capital territory)": "Delhi NCR"}

USAGE = {"in": 0, "out": 0}


def region_of(city, state):
    c = (city or "").strip().lower()
    s = (state or "").strip().lower()
    if c in CITY_REGION:
        return CITY_REGION[c]
    if s in STATE_REGION:
        return STATE_REGION[s]
    if c or s:
        return "Other"
    return "Unknown"


def sb_headers(extra=None):
    h = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
         "Content-Type": "application/json"}
    if extra:
        h.update(extra)
    return h


def fetch_locations():
    out, offset, page = {}, 0, 1000
    while True:
        r = requests.get(f"{SUPABASE_URL}/rest/v1/transcripts",
                         headers=sb_headers({"Range": f"{offset}-{offset + page - 1}"}),
                         params={"select": "call_id,state,city"}, timeout=30)
        r.raise_for_status()
        rows = r.json()
        for row in rows:
            out[row["call_id"]] = region_of(row.get("city"), row.get("state"))
        if len(rows) < page:
            return out
        offset += page


def fetch_agents():
    out, offset, page = {}, 0, 1000
    while True:
        r = requests.get(f"{SUPABASE_URL}/rest/v1/call_summaries",
                         headers=sb_headers({"Range": f"{offset}-{offset + page - 1}"}),
                         params={"select": "call_id,agent"}, timeout=30)
        r.raise_for_status()
        rows = r.json()
        for row in rows:
            out[row["call_id"]] = row["agent"]
        if len(rows) < page:
            return out
        offset += page


def llm(client, prompt, max_out=16000):
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        **{("max_completion_tokens" if PROVIDER == "openai" else "max_tokens"): max_out})
    if resp.usage:
        USAGE["in"] += resp.usage.prompt_tokens or 0
        USAGE["out"] += resp.usage.completion_tokens or 0
    return resp.choices[0].message.content or ""


CLUSTER_PROMPT = """These are questions customers asked on sales calls for Sunrooof, an Indian company selling patented "wellness lighting" — artificial-skylight LED ceilings that recreate natural daylight indoors, sold as ~4-foot consoles with console-based pricing (agents say "Sunrooof wellness lighting" on calls). All are on the topic "{topic}". Many are the same underlying question phrased differently.

Group them so that each group would be answered by ONE canonical answer in a sales-training FAQ. Groups of one are fine. Write the canonical question as a clear, specific English question a trainer would put in an FAQ document.

Questions (number: text):
{questions}

Respond with ONLY JSON:
{{"clusters": [{{"canonical_question": "...", "members": [numbers]}}]}}
Every number 0..{max_idx} must appear in exactly one cluster."""

DRAFT_PROMPT = """You are preparing a sales-training answer bank for Sunrooof, an Indian company selling patented "wellness lighting" — artificial-skylight LED ceilings that recreate natural daylight indoors, sold as ~4-foot consoles with console-based pricing (agents say "Sunrooof wellness lighting" on calls). Below are customer FAQs that agents frequently failed to answer clearly on real calls, each with whatever GOOD answers other agents did give elsewhere (verbatim or summarised from real calls).

For each FAQ write a "suggested_answer" for the training document:
- If good source answers exist, synthesise them into one crisp, complete answer. Set "grounded": true.
- If there is NO source material with the actual facts (price figures, warranty terms, service areas etc.), do NOT invent facts. Instead write the best handling guidance you can (acknowledge, what to say, what to promise) with the factual gap marked like [CONFIRM: exact warranty period], and set "grounded": false.

FAQs:
{faqs}

Respond with ONLY JSON:
{{"answers": [{{"faq_id": n, "suggested_answer": "...", "grounded": true/false}}]}}"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-publish", action="store_true", help="skip the app_kv upsert")
    args = ap.parse_args()

    if not API_KEY:
        print("❌ no LLM API key in .env"); sys.exit(1)

    print("📄 loading per-call extractions…")
    items = []          # flat: one per asked question
    calls_seen = unverified = 0
    for f in sorted(FDIR.glob("*.json")):
        cid = f.name.removesuffix(".json")
        data = json.loads(f.read_text())
        calls_seen += 1
        for q in data.get("questions", []):
            # A question with no verified customer quote cannot be shown to
            # have been asked at all — spot-checks found the model inventing
            # plausible FAQs ("do you do installation?") on calls where the
            # customer never asked. No quote, no row.
            if not q.get("customer_quote"):
                unverified += 1
                continue
            items.append({"call_id": cid, **q})
    print(f"   {calls_seen} calls, {len(items)} verified questions "
          f"({unverified} dropped — no verifiable customer quote)")

    print("☁️  loading regions + agents from Supabase…")
    regions = fetch_locations()
    agents = fetch_agents()
    for it in items:
        it["region"] = regions.get(it["call_id"], "Unknown")
        it["agent"] = agents.get(it["call_id"], "Unknown")

    client = OpenAI(api_key=API_KEY, base_url=BASE_URL, max_retries=5, timeout=300.0)

    # ── 1. cluster per topic ────────────────────────────────────────────────
    by_topic = defaultdict(list)
    for i, it in enumerate(items):
        by_topic[it["topic"]].append(i)

    faqs = []
    for topic, idxs in sorted(by_topic.items(), key=lambda kv: -len(kv[1])):
        print(f"🧩 clustering {len(idxs)} question(s) in '{topic}'…")
        if len(idxs) == 1:
            i = idxs[0]
            faqs.append({"canonical_question": items[i]["question"], "topic": topic, "members": [i]})
            continue
        qlist = "\n".join(f"{n}: {items[i]['question']}" for n, i in enumerate(idxs))
        # 30k output headroom: the biggest topics truncate at anything less and
        # a truncated response costs the whole topic its clustering.
        clusters = None
        for attempt in range(2):
            raw = llm(client, CLUSTER_PROMPT.format(topic=topic, questions=qlist, max_idx=len(idxs) - 1),
                      max_out=30000)
            try:
                clusters = json.loads(extract_json(raw))["clusters"]
                break
            except Exception as e:
                print(f"  ⚠ cluster parse failed for {topic} (attempt {attempt + 1}): {e}")
        if clusters is None:
            print(f"  ⚠ giving up on {topic}; falling back to singletons")
            clusters = [{"canonical_question": items[i]["question"], "members": [n]}
                        for n, i in enumerate(idxs)]
        assigned = set()
        for c in clusters:
            members = [idxs[n] for n in c.get("members", [])
                       if isinstance(n, int) and 0 <= n < len(idxs) and n not in assigned]
            assigned.update(n for n in c.get("members", []) if isinstance(n, int))
            if members:
                faqs.append({"canonical_question": c["canonical_question"], "topic": topic,
                             "members": members})
        for n, i in enumerate(idxs):        # anything the model dropped
            if n not in assigned:
                faqs.append({"canonical_question": items[i]["question"], "topic": topic, "members": [i]})

    # Persist raw-question -> canonical-question so downstream consumers (the
    # Call Intelligence dataset) reuse this exact clustering instead of
    # re-deriving it with fuzzy word-overlap matching.
    question_map = {}
    for f in faqs:
        for i in f["members"]:
            question_map[items[i]["question"]] = f["canonical_question"]
    (BASE / "out" / "faq_question_map.json").write_text(
        json.dumps(question_map, indent=1, ensure_ascii=False))
    print(f"🔗 wrote raw→canonical map for {len(question_map)} question wordings")

    # ── 2. per-FAQ stats ────────────────────────────────────────────────────
    STATUSES = ["answered_clearly", "answered_partially", "deflected", "unanswered"]
    for fid, f in enumerate(faqs):
        f["id"] = fid
        member_items = [items[i] for i in f["members"]]
        f["total_asks"] = len(member_items)
        f["by_region"] = dict(Counter(m["region"] for m in member_items))
        f["status_counts"] = {s: sum(1 for m in member_items if m["answer_status"] == s)
                              for s in STATUSES}
        clear = f["status_counts"]["answered_clearly"]
        f["pct_answered_clearly"] = round(100 * clear / len(member_items))
        good = [m for m in member_items
                if m["answer_status"] == "answered_clearly" and (m.get("agent_quote") or m.get("agent_answer"))]
        good.sort(key=lambda m: len(m.get("agent_quote") or ""), reverse=True)
        f["best_answer"] = ({"call_id": good[0]["call_id"], "agent": good[0]["agent"],
                             "quote": good[0].get("agent_quote"),
                             "summary": good[0].get("agent_answer")} if good else None)
        f["examples"] = [{"call_id": m["call_id"], "region": m["region"], "agent": m["agent"],
                          "status": m["answer_status"], "customer_quote": m.get("customer_quote"),
                          "agent_answer": m.get("agent_answer")}
                         for m in member_items[:5]]
        del f["members"]

    faqs.sort(key=lambda f: -f["total_asks"])

    # ── 3. regional contrast ────────────────────────────────────────────────
    total_q = len(items)
    region_q = Counter(it["region"] for it in items)
    topic_region = defaultdict(lambda: defaultdict(int))
    for it in items:
        topic_region[it["topic"]][it["region"]] += 1

    region_insights = []
    for region, rq in sorted(region_q.items(), key=lambda kv: -kv[1]):
        if region == "Unknown" or rq < 10:
            continue
        distinctive = []
        for f in faqs:
            in_region = f["by_region"].get(region, 0)
            if in_region < 3:
                continue
            share_region = in_region / rq
            share_overall = f["total_asks"] / total_q
            lift = share_region / share_overall if share_overall else 0
            if lift >= 1.5:
                distinctive.append({"faq_id": f["id"], "canonical_question": f["canonical_question"],
                                    "asks_in_region": in_region, "lift": round(lift, 1)})
        distinctive.sort(key=lambda d: -d["lift"])
        region_insights.append({"region": region, "questions": rq,
                                "calls": sum(1 for c, r in regions.items() if r == region),
                                "distinctive_faqs": distinctive[:8]})

    # ── 4. needs-clarification set + drafted answers ───────────────────────
    problems = [f for f in faqs
                if f["total_asks"] >= 2 and f["pct_answered_clearly"] < 50]
    print(f"⚠️  {len(problems)} FAQ(s) qualify as poorly answered (≥2 asks, <50% clear)")

    drafts = {}
    CHUNK = 20
    for start in range(0, len(problems), CHUNK):
        chunk = problems[start:start + CHUNK]
        payload = []
        for f in chunk:
            payload.append({
                "faq_id": f["id"],
                "question": f["canonical_question"],
                "asks": f["total_asks"],
                "status_counts": f["status_counts"],
                "good_answers_from_other_calls":
                    ([{"quote": f["best_answer"]["quote"], "summary": f["best_answer"]["summary"]}]
                     if f["best_answer"] else []) +
                    [{"summary": e["agent_answer"]} for e in f["examples"]
                     if e["status"] == "answered_partially" and e.get("agent_answer")][:2],
            })
        print(f"✍️  drafting suggested answers {start + 1}–{start + len(chunk)}…")
        raw = llm(client, DRAFT_PROMPT.format(faqs=json.dumps(payload, indent=1, ensure_ascii=False)))
        try:
            for a in json.loads(extract_json(raw))["answers"]:
                drafts[a["faq_id"]] = a
        except Exception as e:
            print(f"  ⚠ draft parse failed for chunk at {start}: {e}")

    needs_clarification = []
    for f in problems:
        d = drafts.get(f["id"], {})
        sc = f["status_counts"]
        why = []
        if sc["unanswered"]:
            why.append(f"unanswered {sc['unanswered']}×")
        if sc["deflected"]:
            why.append(f"deflected {sc['deflected']}×")
        if sc["answered_partially"]:
            why.append(f"only vague/partial answers {sc['answered_partially']}×")
        needs_clarification.append({
            "faq_id": f["id"],
            "canonical_question": f["canonical_question"],
            "topic": f["topic"],
            "total_asks": f["total_asks"],
            "pct_answered_clearly": f["pct_answered_clearly"],
            "why": ", ".join(why) or "low clear-answer rate",
            "by_region": f["by_region"],
            "suggested_answer": d.get("suggested_answer"),
            "grounded_in_calls": bool(d.get("grounded")),
            "status": "pending_review",
        })
    needs_clarification.sort(key=lambda n: -n["total_asks"])

    # ── 5. publish ──────────────────────────────────────────────────────────
    analysis = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "model": MODEL,
        "calls_analyzed": calls_seen,
        "calls_with_questions": len({it["call_id"] for it in items}),
        "total_questions": total_q,
        "regions": [{"region": r, "questions": n,
                     "calls": sum(1 for c, reg in regions.items() if reg == r)}
                    for r, n in region_q.most_common()],
        "topic_by_region": {t: dict(rs) for t, rs in topic_region.items()},
        "faqs": faqs,
        "region_insights": region_insights,
        "needs_clarification": needs_clarification,
    }
    OUT_FILE.write_text(json.dumps(analysis, indent=1, ensure_ascii=False))
    print(f"\n💾 wrote {OUT_FILE}")
    print(f"   {len(faqs)} canonical FAQs, {len(needs_clarification)} need clarification")

    if not args.no_publish:
        r = requests.post(f"{SUPABASE_URL}/rest/v1/app_kv",
                          headers=sb_headers({"Prefer": "resolution=merge-duplicates,return=minimal"}),
                          data=json.dumps({"key": "faq_analysis", "value": analysis,
                                           "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()}),
                          timeout=60)
        if r.ok:
            print("☁️  published to app_kv key 'faq_analysis'")
        else:
            print(f"❌ app_kv upsert failed: {r.status_code} {r.text[:300]}")

    price = PRICING.get(MODEL)
    if price and (USAGE["in"] or USAGE["out"]):
        cost = USAGE["in"] / 1e6 * price[0] + USAGE["out"] / 1e6 * price[1]
        print(f"💰 {USAGE['in']:,} in / {USAGE['out']:,} out tokens ≈ ${cost:.2f}")


if __name__ == "__main__":
    main()
