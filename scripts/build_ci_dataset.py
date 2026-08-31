#!/usr/bin/env python3
"""
build_ci_dataset.py — Assemble the Call Intelligence dashboard's dataset from
every real source we have, in the exact shape of `CallRecord` in
`src/types/domain.ts`.

Sources
  Supabase call_summaries   summary, outcome, scorecard, talk %, objections…
  Supabase transcripts      diarised transcript + caller state/city
  out/faqs/*.json           per-call customer questions (verbatim-verified)
  out/faq_analysis.json     canonical FAQ clustering (standardised wording)
  out/ci_enrichment/*.json  segmented sentiment, readiness, VoC themes, …
  out/zoho_enrichment.json  lead source, campaign, CRM stage, client type

Anything with no real source is left null/empty and recorded in the
`provenance` block the UI reads to mark features red (demo) vs green (real) —
nothing is invented to fill a gap.

    python scripts/build_ci_dataset.py
    → <new-project>/src/data/real/dataset.json
"""
import os, re, sys, json, hashlib, argparse, datetime
from pathlib import Path
from collections import Counter, defaultdict

from dotenv import load_dotenv
import requests

load_dotenv()

sys.path.insert(0, str(Path(__file__).resolve().parent))
from speech_dynamics import conversation_gate  # noqa: E402

BASE = Path(__file__).resolve().parent.parent
TDIR = BASE / "out" / "transcripts"
FDIR = BASE / "out" / "faqs"
EDIR = BASE / "out" / "ci_enrichment"
ZOHO_FILE = BASE / "out" / "zoho_enrichment.json"
RECORDING_URLS_FILE = BASE / "out" / "recording_urls.json"
ZOHO_NOTES_SYNCED_FILE = BASE / "out" / "zoho_notes_synced.json"
ZOHO_TRANSCRIPTS_SYNCED_FILE = BASE / "out" / "zoho_transcripts_synced.json"
FAQ_ANALYSIS = BASE / "out" / "faq_analysis.json"
# This project's OWN dashboard copy. Kept relative to the repo root so a run
# here can never write into the sibling Magppie project it was cloned from.
DEFAULT_OUT = BASE / "ci-dashboard" / "src" / "data" / "real" / "dataset.json"

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

MEANINGFUL_MIN_SEC = 60

# ── City → region, same buckets the FAQ analysis uses ─────────────────────
CITY_REGION = {
    "bangalore": ("South", "Karnataka", "Bengaluru"), "bengaluru": ("South", "Karnataka", "Bengaluru"),
    "hyderabad": ("South", "Telangana", "Hyderabad"), "secunderabad": ("South", "Telangana", "Hyderabad"),
    "chennai": ("South", "Tamil Nadu", "Chennai"), "coimbatore": ("South", "Tamil Nadu", "Coimbatore"),
    "kochi": ("South", "Kerala", "Kochi"), "mysore": ("South", "Karnataka", "Mysuru"),
    "mumbai": ("West", "Maharashtra", "Mumbai"), "navi mumbai": ("West", "Maharashtra", "Mumbai"),
    "thane": ("West", "Maharashtra", "Thane"), "pune": ("West", "Maharashtra", "Pune"),
    "nagpur": ("West", "Maharashtra", "Nagpur"),
    "surat": ("West", "Gujarat", "Surat"), "ahmedabad": ("West", "Gujarat", "Ahmedabad"),
    "vadodara": ("West", "Gujarat", "Vadodara"), "rajkot": ("West", "Gujarat", "Rajkot"),
    "gandhinagar": ("West", "Gujarat", "Gandhinagar"),
    "delhi": ("North", "Delhi NCR", "New Delhi"), "new delhi": ("North", "Delhi NCR", "New Delhi"),
    "delhi ncr": ("North", "Delhi NCR", "New Delhi"),
    "gurgaon": ("North", "Haryana", "Gurugram"), "gurugram": ("North", "Haryana", "Gurugram"),
    "noida": ("North", "Uttar Pradesh", "Noida"), "greater noida": ("North", "Uttar Pradesh", "Noida"),
    "ghaziabad": ("North", "Uttar Pradesh", "Ghaziabad"), "faridabad": ("North", "Haryana", "Faridabad"),
    "lucknow": ("North", "Uttar Pradesh", "Lucknow"), "kanpur": ("North", "Uttar Pradesh", "Kanpur"),
    "jaipur": ("North", "Rajasthan", "Jaipur"), "chandigarh": ("North", "Punjab", "Chandigarh"),
    "ludhiana": ("North", "Punjab", "Ludhiana"), "dehradun": ("North", "Uttarakhand", "Dehradun"),
    "kolkata": ("East", "West Bengal", "Kolkata"), "howrah": ("East", "West Bengal", "Howrah"),
    "patna": ("East", "Bihar", "Patna"), "ranchi": ("East", "Jharkhand", "Ranchi"),
    "bhubaneswar": ("East", "Odisha", "Bhubaneswar"), "guwahati": ("East", "Assam", "Guwahati"),
    "indore": ("West", "Madhya Pradesh", "Indore"), "bhopal": ("West", "Madhya Pradesh", "Bhopal"),
    "raipur": ("East", "Chhattisgarh", "Raipur"), "goa": ("West", "Goa", "Panaji"),
    # ── Added for the Sunrooof dataset ────────────────────────────────────
    # Spelling variants Zoho leads actually contain. Without these the
    # Regional page splits one city across several rows (Bengaluru vs
    # Bangaluru) or drops it into Unknown.
    "bangaluru": ("South", "Karnataka", "Bengaluru"),
    "newdelhi": ("North", "Delhi NCR", "New Delhi"),
    "nasik": ("West", "Maharashtra", "Nashik"), "nashik": ("West", "Maharashtra", "Nashik"),
    "kerela": ("South", "Kerala", "Unknown city"), "kerala": ("South", "Kerala", "Unknown city"),
    "punjab": ("North", "Punjab", "Unknown city"),
    "madha pradesh": ("West", "Madhya Pradesh", "Unknown city"),
    # Cities genuinely new to this dataset.
    "karnal": ("North", "Haryana", "Karnal"), "moradabad": ("North", "Uttar Pradesh", "Moradabad"),
    "pushkar": ("North", "Rajasthan", "Pushkar"), "kurnool": ("South", "Andhra Pradesh", "Kurnool"),
    "trivandrum": ("South", "Kerala", "Thiruvananthapuram"),
    "bhatkal": ("South", "Karnataka", "Bhatkal"),
    "chiplun": ("West", "Maharashtra", "Chiplun"), "dhule": ("West", "Maharashtra", "Dhule"),
    "dibrugarh": ("East", "Assam", "Dibrugarh"), "agratala": ("East", "Tripura", "Agartala"),
    "agartala": ("East", "Tripura", "Agartala"),
    # Sunrooof takes overseas enquiries; they are not an Indian region.
    "dubai": ("International", "UAE", "Dubai"),
    "abu dhabi": ("International", "UAE", "Abu Dhabi"),
}
STATE_REGION = {
    "karnataka": "South", "telangana": "South", "tamil nadu": "South", "kerala": "South",
    "andhra pradesh": "South", "maharashtra": "West", "gujarat": "West", "goa": "West",
    "madhya pradesh": "West", "rajasthan": "North", "delhi": "North", "haryana": "North",
    "punjab": "North", "uttar pradesh": "North", "uttarakhand": "North", "himachal pradesh": "North",
    "west bengal": "East", "bihar": "East", "jharkhand": "East", "odisha": "East", "assam": "East",
    "delhi (national capital territory)": "North",
}

# My FAQ topics → the dashboard's fixed FaqCategory union. Several are
# approximate: the dashboard taxonomy has no "showroom visit" or "company info"
# bucket, so those land on the nearest available category (flagged in the
# provenance report rather than silently pretended to be exact).
TOPIC_TO_CATEGORY = {
    "pricing": "Pricing & discounts",
    "product_specs": "Technical specifications",
    "materials": "Product features & benefits",
    "design_options": "Customisation",
    "installation": "Installation process",
    "timeline": "Delivery & project timeline",
    "service_area": "Serviceable locations",
    "showroom_visit": "Availability",
    "process": "Documents & process",
    "warranty_service": "Warranty & AMC",
    "payment_terms": "Payment & finance",
    "company_info": "Documents & process",
    "comparison": "Competitor comparison",
    "maintenance": "Service & complaint process",
    "other": "Documents & process",
}
FAQ_STATUS = {"answered_clearly": "answered", "answered_partially": "partial",
              "deflected": "unanswered", "unanswered": "unanswered"}

CLIENT_TYPE_MAP = {
    "architect": "Architect/Designer", "interior designer": "Architect/Designer",
    "id": "Architect/Designer", "principalpartner": "Architect/Designer",
    "paid": "Existing customer", "end user": "New lead", "owner": "New lead",
    "dealer": "Dealer", "distributor": "Dealer",
}

# Zoho lead stages that mean the lead reached a real sales opportunity — a
# quotation was given, or the deal moved past it. Matched lowercased against the
# stage string.
#
# The previous value was a single misspelled stage, "qualified/ drawings
# awiated", which matches nothing in this org's vocabulary, so opportunityCreated
# came back false on all 6,253 calls and the funnel's opportunity stage read a
# permanent zero. The four below are the stages at or beyond "Raw Quote" (the
# point where the layout has been sent and a rough quotation given).
#
# Still nothing in the vocabulary unambiguously marks a WON order — "Closure"
# may or may not mean won — so orderConfirmed stays false and revenue stays
# null rather than guessing. That one needs a business answer, not a code change.
OPPORTUNITY_STAGES = {"raw quote", "raw", "drawings received", "closure"}

# Used when the enrichment pass left `outcome` unset (a few very short calls):
# fall back to the real call_outcome already stored in call_summaries rather
# than guessing.
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

ACTION_KEYWORDS = [
    (("quotation", "quote", "estimate"), "Share quotation", "P1"),
    (("catalog", "catalogue", "brochure", "profile"), "Send catalogue / brochure", "P3"),
    (("site visit", "visit the site", "site measurement"), "Arrange site visit", "P1"),
    (("measurement",), "Arrange measurement", "P2"),
    (("design", "drawing", "layout", "3d"), "Share design / drawings", "P2"),
    (("showroom", "experience centre", "experience center", "meet"), "Schedule meeting", "P2"),
    (("demo", "demonstration"), "Schedule demonstration", "P2"),
    (("payment", "advance", "invoice"), "Follow up on payment", "P1"),
    (("complaint", "escalat"), "Escalate complaint", "P1"),
    (("specialist", "technical team", "engineer"), "Assign a specialist", "P2"),
    (("call back", "callback", "call again", "follow up", "followup"), "Call back", "P2"),
    (("whatsapp", "share", "send"), "Send catalogue / brochure", "P3"),
]

# docs/08 weights
PR_WEIGHTS = {"need_fit": .25, "explicit_intent": .20, "timeline": .15,
              "next_step_commitment": .15, "authority": .10, "budget": .10, "sentiment": .05}
Q_WEIGHTS = {"discovery": .20, "solutionRelevance": .15, "faqHandling": .15,
             "objectionHandling": .15, "nextStepClarity": .15, "listening": .10,
             "opening": .05, "professionalism": .05}


def sb_headers():
    return {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}


def sb_all(table, select):
    out, offset, page = [], 0, 1000
    while True:
        r = requests.get(f"{SUPABASE_URL}/rest/v1/{table}",
                         headers={**sb_headers(), "Range": f"{offset}-{offset+page-1}"},
                         params={"select": select}, timeout=60)
        r.raise_for_status()
        rows = r.json()
        out.extend(rows)
        if len(rows) < page:
            return out
        offset += page


def geo_for(city, state):
    c = (city or "").strip().lower()
    s = (state or "").strip().lower()
    if c in CITY_REGION:
        return CITY_REGION[c]
    if s in STATE_REGION:
        return (STATE_REGION[s], (state or "").strip(), (city or "").strip() or "Not specified")
    if c or s:
        return ("Other", (state or "").strip() or "Not specified", (city or "").strip() or "Not specified")
    return ("Unknown", "Not specified", "Not specified")


def product_series(enrich):
    """Sunrooof sells one product line, and the model names it a dozen ways
    ("Sunrooof", "wellness lighting", "Sunrooof light console" …). Left raw,
    the product filter fills with near-duplicates of the same thing, so
    collapse the generic namings and keep only a genuinely distinct variant."""
    raw = ((enrich or {}).get("product_mentioned") or "").strip()
    if not raw:
        return "Not specified"
    low = raw.lower()
    # A named console/panel variant is worth keeping as its own value.
    for variant in ("mini", "pro", "max", "slim", "square", "round", "linear"):
        if re.search(rf"\b{variant}\b", low):
            return f"Sunrooof {variant.capitalize()}"
    if re.search(r"sunrooof|sunroof|wellness light|skylight|console|panel", low):
        return "Sunrooof console"
    return raw


def sentiment_label(score):
    return "positive" if score > 0.15 else "negative" if score < -0.15 else "neutral"


def band(score):
    return "high" if score >= 70 else "medium" if score >= 50 else "low" if score >= 30 else "none"


def _norm(s):
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def locate_in_transcript(quote, entries):
    """Second offset of the turn a quoted line was said in, or None.

    Objections used to be stamped `t: 0`, so every one of them appeared to
    happen in the first second of the call and the "jump to this moment" link
    on the call page always landed at the start. The enrichment pass already
    keeps the customer's own words, and the diarised turns carry real Sarvam
    start times, so the moment is recoverable by matching one against the other.

    Matching shortens the probe from 60 characters down to 20 before giving up:
    the stored statement is usually an exact span but is sometimes lightly
    trimmed at the end. Returns None rather than 0 when nothing matches, so an
    unlocatable objection reads as "unknown" instead of "start of call".
    """
    q = _norm(quote)
    if len(q) < 12:
        return None
    turns = [(int(e.get("start_time_seconds") or 0), _norm(e.get("transcript")))
             for e in entries if (e.get("transcript") or "").strip()]
    for width in (60, 40, 20):
        probe = q[:width]
        for start, text in turns:
            if probe and probe in text:
                return start
    return None


def scorecard_to_quality(analysis, enrich, faqs, objections):
    """Map the existing 1-5 scorecard + enrichment 0-100 dims onto the
    dashboard's eight 0-100 quality parameters. Dimensions the scorecard marked
    not-applicable fall back to the call-level professionalism signal rather
    than scoring a zero the agent didn't earn."""
    sc = (analysis or {}).get("scorecard") or {}
    q = (enrich or {}).get("quality") or {}

    def dim(name, default=None):
        d = sc.get(name) or {}
        if d.get("applicable") and d.get("score") is not None:
            return round(float(d["score"]) / 5 * 100)
        return default

    prof_base = dim("language_rapport", 70)
    opening = dim("opening_identification", 60)
    discovery = dim("need_capture", 55)
    next_step = dim("next_step_secured", 50)
    objection = dim("objection_handling", None)
    if objection is None:
        objection = 70 if not objections else 55
    faq_handling = None
    if faqs:
        good = sum(1 for f in faqs if f["status"] == "answered")
        faq_handling = round(100 * good / len(faqs))
    if faq_handling is None:
        faq_handling = 70
    scores = {
        "opening": opening,
        "discovery": discovery,
        "solutionRelevance": int(q.get("solution_relevance", 60) or 0),
        "faqHandling": faq_handling,
        "objectionHandling": objection,
        "nextStepClarity": next_step,
        "listening": int(q.get("listening", 65) or 0),
        "professionalism": prof_base,
    }
    overall = round(sum(scores[k] * w for k, w in Q_WEIGHTS.items()))
    flags = q.get("compliance_flags") or []
    coaching = (analysis or {}).get("coaching") or {}
    improvements = coaching.get("improvements") or []
    return {
        **scores,
        "overall": overall,
        "complianceFail": bool(flags),
        "complianceNotes": "; ".join(flags) or None,
        "scriptAdherence": int(q.get("script_adherence", 60) or 0),
        "coachingNote": improvements[0] if improvements else None,
    }


def build_faqs(cid, faq_file, canonical_for, enrich, entries, agent_sid):
    """Per-call FAQ hits. responseTimeSec is measured off the real Sarvam
    timestamps: the gap from the customer's question to the agent's next turn."""
    if not faq_file.exists():
        return []
    questions = json.loads(faq_file.read_text(encoding="utf-8")).get("questions", [])
    extras = {e["question"]: e for e in ((enrich or {}).get("faq_extras") or [])}

    def response_gap(quote):
        if not quote:
            return None
        needle = "".join(ch for ch in quote.lower() if ch.isalnum())[:40]
        if not needle:
            return None
        for i, e in enumerate(entries):
            hay = "".join(ch for ch in (e.get("transcript") or "").lower() if ch.isalnum())
            if needle and needle in hay:
                for nxt in entries[i + 1:]:
                    if nxt.get("speaker_id") == agent_sid:
                        gap = (nxt.get("start_time_seconds") or 0) - (e.get("end_time_seconds") or 0)
                        return round(max(0.0, gap), 1)
                return None
        return None

    out = []
    for q in questions:
        # Same evidence bar as the FAQ analysis: a question with no verbatim
        # transcript quote cannot be shown to have been asked, so it is dropped
        # rather than counted.
        if not q.get("customer_quote"):
            continue
        topic = q.get("topic", "other")
        ex = extras.get(q["question"], {})
        std = canonical_for(q["question"], topic)
        t = 0
        quote = q.get("customer_quote")
        if quote:
            needle = "".join(ch for ch in quote.lower() if ch.isalnum())[:40]
            for e in entries:
                hay = "".join(ch for ch in (e.get("transcript") or "").lower() if ch.isalnum())
                if needle and needle in hay:
                    t = int(e.get("start_time_seconds") or 0)
                    break
        out.append({
            "category": TOPIC_TO_CATEGORY.get(topic, "Documents & process"),
            "standardized": std,
            "originalQuestion": quote or q["question"],
            "status": FAQ_STATUS.get(q.get("answer_status"), "unanswered"),
            "responseTimeSec": response_gap(quote),
            "sentimentAfter": ex.get("sentiment_after", "neutral"),
            "escalationNeeded": bool(ex.get("escalation_needed", False)),
            "t": t,
        })
    return out


def build_actions(cid, customer_name, employee_id, summ, enrich, start_dt, now):
    """Next actions from what was actually committed on the call. SLA is
    computed from the call time; CRM task linkage is not available (no task
    system integration), so crmTaskLinked is always false."""
    analysis = summ.get("analysis") or {}
    committed = analysis.get("commitments") or []
    items = summ.get("action_items") or []
    out = []
    seen = set()

    def classify(text):
        low = text.lower()
        for keys, action, prio in ACTION_KEYWORDS:
            if any(k in low for k in keys):
                return action, prio
        return "Call back", "P3"

    def add(text, source, by):
        text = (text or "").strip()
        if not text or text.lower() in seen:
            return
        seen.add(text.lower())
        action, prio = classify(text)
        due = start_dt + datetime.timedelta(days={"P1": 1, "P2": 3, "P3": 7}[prio])
        completed = False  # no task system to confirm completion
        if due.date() < now.date():
            sla = "overdue"
        elif due.date() == now.date():
            sla = "due_today"
        else:
            sla = "on_track"
        out.append({
            "id": f"{cid}-A{len(out)+1}",
            "callId": cid,
            "customerName": customer_name,
            "action": action,
            "source": source,
            "committedBy": by,
            "ownerEmployeeId": employee_id,
            "priority": prio,
            "dueDate": due.isoformat(),
            "channel": "WhatsApp" if "whatsapp" in text.lower() else "Call",
            "reason": text,
            "transcriptRef": None,
            "status": "completed" if completed else "pending",
            "slaStatus": sla,
            "crmTaskLinked": False,
        })

    for c in committed:
        if isinstance(c, dict):
            add(c.get("what"), "committed", c.get("who") if c.get("who") in ("agent", "customer") else "employee")
        else:
            add(str(c), "committed", "employee")
    for a in items:
        add(a, "committed", "employee")
    if not out and (summ.get("next_action") or "").strip():
        add(summ["next_action"], "ai_recommended", None)
    for a in out:
        if a["committedBy"] == "agent":
            a["committedBy"] = "employee"
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args()

    print("☁️  loading Supabase…")
    summaries = {r["call_id"]: r for r in sb_all("call_summaries", "*")}
    trows = {r["call_id"]: r for r in sb_all("transcripts", "call_id,state,city")}
    print(f"   {len(summaries)} summaries, {len(trows)} transcript rows")

    zoho = json.loads(ZOHO_FILE.read_text(encoding="utf-8")) if ZOHO_FILE.exists() else {}
    recording_urls = json.loads(RECORDING_URLS_FILE.read_text(encoding="utf-8")) if RECORDING_URLS_FILE.exists() else {}
    notes_synced = set(json.loads(ZOHO_NOTES_SYNCED_FILE.read_text(encoding="utf-8"))) if ZOHO_NOTES_SYNCED_FILE.exists() else set()
    transcripts_synced = set(json.loads(ZOHO_TRANSCRIPTS_SYNCED_FILE.read_text(encoding="utf-8"))) if ZOHO_TRANSCRIPTS_SYNCED_FILE.exists() else set()
    print(f"   {len(zoho)} zoho enrichment rows")

    # Preferred path: the exact raw→canonical clustering emitted by
    # aggregate_faqs.py, so this dashboard groups questions identically to the
    # FAQ analysis the business already reviews.
    QMAP_FILE = BASE / "out" / "faq_question_map.json"
    exact_map = json.loads(QMAP_FILE.read_text(encoding="utf-8")) if QMAP_FILE.exists() else {}
    print(f"   {len(exact_map)} exact question→canonical mappings"
          if exact_map else "   ⚠ no exact question map; falling back to word-overlap matching")

    # Fallback for any wording the map doesn't cover: best canonical within the
    # same topic by word overlap. An unmatched question keeps its own wording
    # rather than being forced into a wrong cluster.
    canon_by_topic = defaultdict(list)
    if FAQ_ANALYSIS.exists():
        for f in json.loads(FAQ_ANALYSIS.read_text(encoding="utf-8")).get("faqs", []):
            canon_by_topic[f.get("topic", "other")].append(f["canonical_question"])

    STOP = {"the", "a", "an", "is", "are", "do", "does", "you", "your", "i", "my", "what",
            "how", "can", "and", "or", "of", "for", "to", "in", "it", "me", "we", "they"}

    def words(s):
        return {w for w in "".join(c.lower() if c.isalnum() else " " for c in s).split()
                if w and w not in STOP}

    _canon_cache: dict[tuple[str, str], str] = {}

    def canonical_for(question, topic):
        hit = exact_map.get(question)
        if hit:
            return hit
        key = (question, topic)
        if key in _canon_cache:
            return _canon_cache[key]
        qw = words(question)
        best, best_score = question, 0.0
        for cand in canon_by_topic.get(topic, []):
            cw = words(cand)
            if not qw or not cw:
                continue
            score = len(qw & cw) / len(qw | cw)
            if score > best_score:
                best, best_score = cand, score
        result = best if best_score >= 0.34 else question
        _canon_cache[key] = result
        return result

    # Stable employee ids from real agent names.
    agents = sorted({s.get("agent") for s in summaries.values() if s.get("agent")})
    emp_id = {name: f"E{str(i+1).zfill(2)}" for i, name in enumerate(agents)}

    calls = []
    missing_enrich = 0
    for cid, summ in summaries.items():
        tpath = TDIR / f"{cid}.mp3.json"
        if not tpath.exists():
            continue
        tdata = json.loads(tpath.read_text(encoding="utf-8"))
        entries = tdata.get("diarized_transcript", {}).get("entries", []) or []
        if not entries:
            continue

        epath = EDIR / f"{cid}.json"
        enrich = json.loads(epath.read_text(encoding="utf-8")) if epath.exists() else None
        if enrich is None:
            missing_enrich += 1

        # agent speaker = the one who names the company (same rule as elsewhere)
        import re as _re
        COMPANY_RE = _re.compile(r"sun\s*ro+f", _re.I)
        brand = next((e for e in entries if COMPANY_RE.search(e.get("transcript") or "")), None)
        agent_sid = brand.get("speaker_id") if brand else (entries[0].get("speaker_id") if entries else None)

        z = zoho.get(cid, {})
        trow = trows.get(cid, {})
        region, state, city = geo_for(trow.get("city"), trow.get("state"))

        dur = int(summ.get("duration_seconds") or 0)
        start_raw = summ.get("start_time")
        start_dt = datetime.datetime.fromisoformat(start_raw.replace("Z", "+00:00")) if start_raw else None
        if not start_dt:
            continue

        sent = (enrich or {}).get("sentiment") or {}
        has_sent = bool(sent)
        if has_sent:
            o, m, cl = float(sent.get("opening", 0)), float(sent.get("mid", 0)), float(sent.get("closing", 0))
            weighted = (o + m + cl * 1.4) / 3.4
            sentiment = {
                "opening": round(o, 2), "mid": round(m, 2), "closing": round(cl, 2),
                "overall": sentiment_label(weighted),
                "shift": round(cl - o, 2),
                "emotions": sent.get("emotions") or [],
                "unresolvedNegative": bool(sent.get("unresolved_negative")),
            }
        else:
            sentiment = None

        rd = (enrich or {}).get("readiness") or {}
        if rd:
            pr_score = round(sum(float(rd.get(k, 0)) * w for k, w in PR_WEIGHTS.items()))
            readiness = {
                "score": pr_score,
                "needFit": int(rd.get("need_fit", 0)), "explicitIntent": int(rd.get("explicit_intent", 0)),
                "timeline": int(rd.get("timeline", 0)), "nextStepCommitment": int(rd.get("next_step_commitment", 0)),
                "authority": int(rd.get("authority", 0)), "budget": int(rd.get("budget", 0)),
                "sentiment": int(rd.get("sentiment", 0)),
            }
            intent = band(pr_score)
        else:
            readiness, intent = None, "none"

        faqs = build_faqs(cid, FDIR / f"{cid}.json", canonical_for, enrich, entries, agent_sid)
        objections = [{
            "type": o["type"], "intensity": o["intensity"],
            "statement": o.get("statement") or "",
            "employeeResponse": o.get("employee_response") or "",
            "technique": o.get("technique") or "None",
            "resolution": o["resolution"], "customerReaction": o["customer_reaction"],
            "t": locate_in_transcript(o.get("statement"), entries),
        } for o in ((enrich or {}).get("objections") or [])]

        quality = scorecard_to_quality(summ.get("analysis"), enrich, faqs, objections)

        speakers = {e.get("speaker_id") for e in entries}
        diarization_ok = len(speakers) >= 2
        tm = (enrich or {}).get("talk_metrics") or {}
        talk = {
            "agentTalkPct": int(summ.get("agent_talk_pct") or 0),
            "interruptions": int(tm.get("interruptions", 0)),
            "longestSilenceSec": float(tm.get("longest_silence_sec", 0)),
        } if diarization_ok and summ.get("agent_talk_pct") is not None else None

        now = datetime.datetime.now(datetime.timezone.utc)
        employee_id = emp_id.get(summ.get("agent"), "E00")
        actions = build_actions(cid, summ.get("customer") or "Unknown", employee_id,
                                summ, enrich, start_dt, now)

        ct_raw = (z.get("client_type") or "").strip().lower()
        customer_type = CLIENT_TYPE_MAP.get(ct_raw) or (enrich or {}).get("customer_type") or "New lead"

        stage = (z.get("crm_stage") or "").strip()
        outcome = ((enrich or {}).get("outcome")
                   or LEGACY_OUTCOME.get(summ.get("call_outcome") or "", "Interested — follow-up"))
        connected = dur > 0 and outcome != "Not connected"
        customer_spoke = any(e.get("speaker_id") != agent_sid for e in entries)
        # `customer_spoke` is not evidence that a second person was on the line:
        # diarisation splits room echo across two or three speaker ids, so a
        # recording of an empty office reports a "customer" and passes this test.
        # `connected` leans on the model-derived `outcome`, which is exactly what
        # is unreliable on these calls. The gate is arithmetic on speech density
        # and depends on neither.
        #
        # `sparse` is excluded here as well as `no_contact`, which costs one real
        # call out of 6,260 — an inbound enquiry sitting behind 90s of hold music.
        # That is the right trade: `meaningful` gates the analytics aggregates, a
        # call we cannot show contained a conversation does not belong in them,
        # and the alternative leaks recordings of empty rooms into the averages.
        gate = conversation_gate(entries)
        meaningful = (connected and dur > MEANINGFUL_MIN_SEC and customer_spoke
                      and gate["verdict"] == "ok")

        comp = summ.get("competitor_mentioned")
        asr = (enrich or {}).get("asr_confidence")
        if asr is None:
            asr = tdata.get("language_probability")

        calls.append({
            "id": cid,
            "dateTime": start_dt.isoformat(),
            "direction": "inbound" if (summ.get("call_type") or "").lower().startswith("in") else "outbound",
            "durationSec": dur,
            "customerId": z.get("linked_id") or hashlib.md5((summ.get("customer") or cid).encode()).hexdigest()[:12],
            "customerName": summ.get("customer") or "Unknown",
            "customerType": customer_type,
            "employeeId": employee_id,
            "region": region, "state": state, "city": city,
            "productSeries": product_series(enrich),
            # Zoho Type_of_Space (Residential / Office / Retail / Hotel …).
            # Sunrooof-specific: this org populates it on ~71% of leads, so it
            # is a far stronger segmentation dimension than product (there is
            # essentially one product line).
            "spaceType": z.get("property_type") or "Not recorded",
            "language": summ.get("language") or "Not detected",
            "leadSource": z.get("lead_source") or "Not recorded",
            "campaign": z.get("campaign") or "None",
            "crmStage": stage or "Not recorded",
            "outcome": outcome,
            "connected": connected,
            "meaningful": meaningful,
            "transcribed": True,
            "transcriptionConfidence": float(asr if asr is not None else 0.8),
            "diarizationReliable": diarization_ok,
            "sentiment": sentiment,
            "purchaseReadiness": readiness,
            "intent": intent,
            "customerNeed": summ.get("room_type") or summ.get("property_details"),
            "budgetMentioned": summ.get("budget"),
            "timelineMentioned": summ.get("timeline"),
            "decisionMaker": (enrich or {}).get("decision_maker") or "unknown",
            "buyingSignals": summ.get("buying_signals") or [],
            "crossSell": (enrich or {}).get("cross_sell"),
            "discountRequested": bool((enrich or {}).get("discount_requested")),
            "competitorMentions": [comp] if comp else [],
            "topics": (enrich or {}).get("topics") or [],
            "appreciationThemes": (enrich or {}).get("appreciation_themes") or [],
            "dissatisfactionThemes": (enrich or {}).get("dissatisfaction_themes") or [],
            "featureRequests": (enrich or {}).get("feature_requests") or [],
            "expectations": (enrich or {}).get("expectations") or [],
            "painPoints": (enrich or {}).get("pain_points") or [],
            "faqs": faqs,
            "objections": objections,
            "quality": quality,
            "talk": talk,
            "actions": actions,
            "commitments": [c.get("what") if isinstance(c, dict) else str(c)
                            for c in ((summ.get("analysis") or {}).get("commitments") or [])],
            "risks": (summ.get("risk_flags") or []) + (summ.get("red_flags") or []),
            "complianceFlags": ((enrich or {}).get("quality") or {}).get("compliance_flags") or [],
            "entities": [e for e in ((enrich or {}).get("entities") or [])
                         if isinstance(e, dict) and e.get("text")],
            "summary": summ.get("summary") or "",
            "transcript": [{
                "t": int(e.get("start_time_seconds") or 0),
                "speaker": "agent" if e.get("speaker_id") == agent_sid else "customer",
                "text": (e.get("transcript") or "").strip(),
            } for e in entries if (e.get("transcript") or "").strip()],
            "crm": {
                "opportunityCreated": stage.strip().lower() in OPPORTUNITY_STAGES,
                "orderConfirmed": False,          # no won/order stage exists in this CRM data
                "complaintOpen": outcome == "Complaint raised",
                "revenueInfluenced": None,        # no deal amounts linked
                "verified": False,
            },
            "hasRecording": True,
            # Zoho phonebridge URL, proxied by scripts/audio_proxy.mjs (holds
            # the session cookie server-side — never shipped to the browser).
            "recordingUrl": recording_urls.get(cid),
            # Whether an AI-generated note has ever reached Zoho for this call —
            # via the old bulk sync or the Update CRM button. Informational only;
            # the button always re-checks Zoho's live state before writing.
            "crmNoteSynced": cid in notes_synced,
            "crmTranscriptSynced": cid in transcripts_synced,
        })

    calls.sort(key=lambda c: c["dateTime"])
    employees = [{"id": eid, "name": name, "team": "Not mapped in CRM",
                  "manager": "Not mapped in CRM", "role": "Sales Consultant"}
                 for name, eid in sorted(emp_id.items(), key=lambda kv: kv[1])]

    dataset = {
        "generatedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "sourceLabel": (f"Live Sunrooof data — {len(calls)} Zoho calls, Sarvam transcripts, "
                        f"gpt-4.1-mini extraction"),
        "calls": calls,
        "employees": employees,
        "taxonomy": {
            "regions": sorted({c["region"] for c in calls}),
            "states": sorted({c["state"] for c in calls}),
            "cities": sorted({c["city"] for c in calls}),
            "products": sorted({c["productSeries"] for c in calls}),
            "languages": sorted({c["language"] for c in calls}),
            "leadSources": sorted({c["leadSource"] for c in calls}),
            "campaigns": sorted({c["campaign"] for c in calls}),
            "teams": sorted({e["team"] for e in employees}),
        },
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(dataset, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    size_mb = out_path.stat().st_size / 1e6

    print(f"\n💾 {out_path}  ({size_mb:.1f} MB)")
    print(f"   {len(calls)} calls, {len(employees)} agents")
    if missing_enrich:
        print(f"   ⚠ {missing_enrich} calls had no enrichment file (sentiment/readiness null)")
    print(f"   date range {calls[0]['dateTime'][:10]} → {calls[-1]['dateTime'][:10]}")
    for k in ["sentiment", "purchaseReadiness", "quality", "talk"]:
        n = sum(1 for c in calls if c.get(k))
        print(f"   {k}: {n}/{len(calls)}")
    print(f"   faqs: {sum(len(c['faqs']) for c in calls)} hits, "
          f"objections: {sum(len(c['objections']) for c in calls)}, "
          f"actions: {sum(len(c['actions']) for c in calls)}")


if __name__ == "__main__":
    main()
