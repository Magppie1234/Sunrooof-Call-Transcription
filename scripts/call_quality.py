#!/usr/bin/env python3
"""SUNROOOF PSM call-quality scorecard — schema, deterministic scorer, validator.

Split of responsibility, and the reason for it:

  the model  → judgements only (subpoint status + evidence, CM/RF observations,
               qualitative ratings, coaching prose)
  this file  → every gate, every sum, every percentage, the tier, and the
               Section 13 self-checks

Section 8 and Section 13 of the master prompt are pure arithmetic and rule
application. An LLM asked to also do that arithmetic will occasionally return a
tier that disagrees with its own score, or a total that does not match its own
criteria — silently, on a minority of calls, which is the worst failure mode for
a QA system whose whole job is being trusted. Computing it here makes Section 13
rules 1-9 true by construction rather than by hope, and lets the scorer be tested
without spending an API call.

Source of truth for the wording: prompts/call_quality_audit.md
"""
from __future__ import annotations

import datetime as _dt
from typing import Any

SCHEMA_VERSION = "sunrooof_psm_call_quality_v3.0"

# ── Scorecard definition (Section 5) ───────────────────────────────────────
# mandatory=True subpoints drive the Zero/Half gates in Section 4.
SCORECARD: list[dict[str, Any]] = [
    {
        "id": 1, "name": "Greeting & Opening", "max": 5, "key": "greeting_opening",
        "subpoints": [
            ("1.1", "Well-paced clear ASSUMPTIVE opening: greets by name and proceeds WITHOUT verifying identity ('Is this X speaking?' is NOT assumptive), introduces self + Sunrooof, states the enquiry, and asserts 'let's talk for two minutes' rather than asking permission", False),
            ("1.2", "Upbeat and professional tone", False),
            ("1.3", "Lead source CONFIRMED (if already known to the PSM) or asked (only required when the source was unavailable)", False),
        ],
    },
    {
        "id": 2, "name": "KYC / Discovery", "max": 5, "key": "kyc_discovery",
        "subpoints": [
            ("2.1", "Identified customer type: architect / contractor / designer vs homeowner or property owner (do not expect the phrase 'end user')", False),
            ("2.2", "Identified project type and location", False),
            ("2.3", "Asked when the project will be ready", False),
            ("2.4", "MANDATORY: asked by when the customer needs SUNROOOF installed and ready, AND prompted with hints (Vastu date/muhurat, before school reopens, summer vacations) if the customer could not answer. Not met ONLY if the PSM never asked and never prompted", True),
            ("2.5", "Identified whether the customer is the decision maker", False),
            ("2.6", "If not, attempted to identify the decision maker", False),
        ],
    },
    {
        "id": 3, "name": "About SUNROOOF / Value Proposition", "max": 10, "key": "about_sunrooof",
        "subpoints": [
            ("3.1", "MANDATORY: explained uniqueness as the world's first wellness lighting technology", True),
            ("3.2", "MANDATORY: explained the five wellness benefits - open/airy/less cluttered space, better mood, lower stress, improved sleep via GPS circadian cycle, better focus/productivity/social interaction", True),
            ("3.3", "Explained history and patent", False),
            ("3.4", "Mentioned credibility - 1000+ homes/offices/retail spaces transformed (catalogue figure)", False),
            ("3.5", "PROHIBITED: mentioned the old brand name 'Barton Bach'", False),
        ],
    },
    {
        "id": 4, "name": "Requirement Gathering", "max": 5, "key": "requirement_gathering",
        "subpoints": [
            ("4.1", "MANDATORY: identified the areas where SUNROOOF is wanted", True),
            ("4.2", "MANDATORY: identified whether Window or Ceiling consoles are needed", True),
        ],
    },
    {
        "id": 5, "name": "Technical Details", "max": 10, "key": "technical_details",
        "subpoints": [
            ("5.1", "Explained console dimensions", False),
            ("5.2", "Explained design styles and size restrictions", False),
            ("5.3", "Explained the four-console minimum AND the reason: natural light reads as a cut-out, not a hole; four consoles ~8ft x 3ft reads as a cut-out", False),
            ("5.4", "Explained technology: LEDs, lenses, optics, Nano Tech Diffuser, GPS chip, drivers, controllers, app", False),
            ("5.5", "Covered ceiling height and drop, plus window protrusion as relevant", False),
            ("5.6", "Explained product life - catalogue states 12-14 years (12-15 as spoken in training is acceptable, not required)", False),
            ("5.7", "Explained power consumption - 20-40W per console, max 50W (0.03 kW ~ 30W is acceptable). The 'less than a 15W LED' claim is UNSUPPORTED and must not be required", False),
            ("5.8", "Provided timeline clarity", False),
            ("5.9", "Explained manufacturing - critical electronics in Germany, woodwork in Manesar, Haryana", False),
            ("5.10", "Clarified GPS-based preset, not sensor-based: customer presets their own daily sun cycle; the GPS chip supplies time of day", False),
        ],
    },
    {
        "id": 6, "name": "Pricing Communication & Console Specifications", "max": 10, "key": "pricing_console_specs",
        "subpoints": [
            ("6.1", "MANDATORY: gave pricing per console, not only a package total", True),
            ("6.2", "MANDATORY: gave the ceiling-console price range per console (currently Rs 39,000-45,000); mark unknown if the quoted figure cannot be verified", True),
            ("6.3", "MANDATORY: stated the complete window-console price range separately", True),
            ("6.4", "MANDATORY: gave console measurements in ANY TWO of four units - feet+inches, millimetres, centimetres, inches-only", True),
            ("6.5", "MANDATORY: gave coverage-based quantity per the minimum-console quantity chart", True),
            ("6.6", "MANDATORY/PROHIBITED: gave per-console price only - no GST, delivery, installation or total cost (a total needs ~Rs 50,000 delivery/assembly + 18% GST)", True),
        ],
    },
    {
        "id": 7, "name": "Hype & Aspiration Building", "max": 15, "key": "hype_aspiration",
        "subpoints": [
            ("7.1", "Positioned SUNROOOF as a need, not merely a want", False),
            ("7.2", "Reiterated health/wellness benefits per the approved script", False),
            ("7.3", "Positioned longevity and one-time investment value", False),
            ("7.4", "Explained lower power consumption versus regular lighting", False),
            ("7.5", "Explained modularity - consoles move with you to a new home, only frames (rafters) are rebought", False),
        ],
    },
    {
        "id": 8, "name": "Objection Handling", "max": 10, "key": "objection_handling",
        "subpoints": [
            ("8.1", "Answered all objections accurately", False),
            ("8.2", "Reframed price against health/wellness value", False),
            ("8.3", "Secured willingness/YES to explore or stretch", False),
        ],
    },
    {
        "id": 9, "name": "Priming Customer for Specialist", "max": 10, "key": "priming_for_specialist",
        "subpoints": [
            ("9.1", "MANDATORY: built the importance of the Wellness Specialist", True),
            ("9.2", "MANDATORY: explained the specialist is a helper, not a seller", True),
            ("9.3", "MANDATORY: explained the specialist is the pricing and design authority", True),
            ("9.4", "MANDATORY: explained the importance of answering the specialist", True),
        ],
    },
    {
        "id": 10, "name": "Process Clarity", "max": 5, "key": "process_clarity",
        "subpoints": [
            ("10.1", "Explained next steps: measure, design, cost, order, install", False),
            ("10.2", "Gave clarity on timelines and each step", False),
            ("10.3", "Explained when the specialist will call or message", False),
        ],
    },
    {
        "id": 11, "name": "FOMO Creation / Urgency", "max": 10, "key": "fomo_urgency",
        "subpoints": [
            ("11.1", "MANDATORY: used the customer's OWN stated deadline (from 2.4) to describe the package and price-locking timeline, and obtained a YES to explore", True),
            ("11.2", "Did not use fake deadlines or artificial scarcity", False),
        ],
    },
    {
        "id": 12, "name": "Zoho CRM Disposition", "max": 5, "key": "zoho_crm_disposition",
        "subpoints": [
            ("12.1", "Disposed correctly in Zoho CRM using the correct type", False),
            ("12.2", "Disposed on the correct date", False),
        ],
    },
]

CRITICAL_MISSES = [
    ("CM-1", "Miss-sell: false information, unsupported health claims, or misrepresentation"),
    ("CM-2", "Short Dial: disconnected prematurely / insufficient engagement, not a genuine attempt"),
    ("CM-3", "The PSM mentioned 'Barton Bach', the old brand name"),
    ("CM-4", "Handover WhatsApp group created on the same date the lead was marked RAW quote"),
    ("CM-5", "Did not capture by when the customer needs SUNROOOF installed and ready to use"),
]

RED_FLAGS = [
    ("RF-1", "CRITICAL", 15, "Suggested a single console or two or fewer consoles could work"),
    ("RF-2", "CRITICAL", 15, "Wrong CRM disposition marked"),
    ("RF-3", "MAJOR", 10, "Decision maker not identified during the call"),
    ("RF-4", "MAJOR", 10, "Timeline vague or not discussed at all"),
    ("RF-5", "MAJOR", 10, "Ceiling height/type not verified (9 ft minimum)"),
    ("RF-6", "PROCESS", 10, "Artificial urgency or false deadlines"),
    ("RF-7", "MINOR", 5, "Mentioned GST, installation charges, or remote pricing"),
    # Conduct flags. A luxury sale is lost by not listening long before it is lost
    # on a checklist item, so these carry real weight rather than sitting in a
    # coaching note nobody scores.
    ("RF-8", "MAJOR", 10, "Did not listen — interrupted the customer, or repeated an "
                          "assumption the customer had already corrected"),
    ("RF-9", "MAJOR", 10, "Poor rapport — brusque, impatient or transactional with the customer"),
]

TIERS = [(85.0, "GOLD"), (75.0, "SILVER"), (60.0, "BRONZE"), (50.0, "DEVELOPING")]

# The only two criteria the scorecard sanctions marking N/A (Section 3 rule 7):
# Objection Handling when the customer raised none, and CRM Disposition when the
# disposition data is unavailable. Everything else is governed by rule 5 — "a
# complete transcript with no evidence that the PSM covered a required point
# means the point was NOT MET" — and rule 8, "do not use N/A to protect a poor
# call from a low score".
#
# Enforced because the model does exactly what those rules forbid: on a real
# 40-second call it marked 11 of 12 criteria N/A ("No pricing discussed", "No
# priming occurred"), leaving Greeting alone scored 5/5 = 100% GOLD. Excluding
# unmet criteria from the denominator turns a call where nothing happened into a
# perfect score, which is far more damaging than an unfair zero.
NA_ALLOWED = {8, 12}

# A short call is not automatically a bad call. When the customer was unavailable,
# never enquired, or ended it early, the consultative criteria never had a chance
# to happen — scoring them zero blames the agent for the customer's situation.
# These contexts widen what may legitimately be marked N/A.
LIMITED_CONTEXTS = {
    "callback_scheduling": {1, 10},      # greeting + what happens next
    "not_a_lead":          {1},          # greeting and a graceful close
    "customer_declined_early": {1, 2, 10},
    "no_contact":          set(),
}

# Below this, too little of the scorecard remains to call the result a grade.
MIN_SCOREABLE_MAX = 50

_BY_ID = {c["id"]: c for c in SCORECARD}


def tier_for(score: float | None) -> str:
    if score is None:
        return "NOT_SCORED"
    for floor, name in TIERS:
        if score >= floor:
            return name
    return "AT_RISK"


# ── Filter dimensions (Section 11) ─────────────────────────────────────────
def _clean(value: Any) -> Any:
    """Section 2 forbids turning a missing dimension into 'All'/'Unknown'.

    Our own region backfill writes the literal string 'Unknown' for calls it
    could not place, so that placeholder is normalised back to null here rather
    than leaking into the audit as if it were a real location.
    """
    if value is None:
        return None
    if isinstance(value, str):
        v = value.strip()
        if not v or v.lower() in {"all", "unknown", "n/a", "na", "none", "null"}:
            return None
        return v
    return value


def derive_filter_dimensions(meta: dict) -> dict:
    """Copy supplied dimensions verbatim; derive date parts only from a valid date.

    Nothing here infers: no region-from-city, no city-from-phone, no owner-from-
    speaker. A dimension we were not given stays null.
    """
    dims = {k: _clean(meta.get(k)) for k in (
        "call_owner_id", "call_owner", "evaluator_id", "evaluator_name",
        "evaluation_date", "region", "zone", "state", "city", "country",
        "branch", "team", "department", "campaign", "queue", "language",
        "call_date", "lead_source", "property_type", "call_direction",
        "call_disposition", "sentiment_label",
    )}
    dims.update(call_year=None, call_quarter=None, call_month=None,
                call_iso_week=None, call_day_of_week=None)

    raw = meta.get("call_date")
    if raw:
        try:
            d = _dt.date.fromisoformat(str(raw)[:10])
        except (TypeError, ValueError):
            d = None
        if d:
            iso = d.isocalendar()
            dims.update(
                call_year=f"{d.year:04d}",
                call_quarter=f"Q{(d.month - 1) // 3 + 1}",
                call_month=f"{d.year:04d}-{d.month:02d}",
                call_iso_week=f"{iso[0]:04d}-W{iso[1]:02d}",
                call_day_of_week=d.strftime("%A"),
            )
    dims["custom_dimensions"] = meta.get("custom_dimensions") or {}
    return dims


# ── Gate application (Section 4) ───────────────────────────────────────────
def _apply_gates(criterion: dict, judged: dict) -> tuple[str, bool | None]:
    """Resolve the model's proposed label against the mandatory-subpoint gates.

    The model proposes full/half/zero from its reading of the call; the gates can
    only ever push that *down*, never up. Returns (label, gate_passed).
    """
    spec = _BY_ID[criterion["criterion_id"]]
    mandatory = {sid for sid, _, m in spec["subpoints"] if m}
    if not mandatory:
        return judged.get("score_label", "zero"), None

    statuses = {s.get("subpoint_id"): s.get("status") for s in judged.get("subpoints", [])}
    mand_statuses = [statuses.get(sid) for sid in mandatory]

    if any(s == "not_met" for s in mand_statuses):
        return "zero", False
    proposed = judged.get("score_label", "zero")
    if any(s == "partial" for s in mand_statuses) and proposed == "full":
        return "half", False
    return proposed, all(s == "met" for s in mand_statuses)


def _points(max_points: int, label: str) -> float:
    return {"full": float(max_points), "half": max_points / 2.0, "zero": 0.0}.get(label, 0.0)


def _has_unknown(judged: dict) -> bool:
    return any(s.get("status") == "unknown" for s in judged.get("subpoints", []))


def _as_dict(raw) -> dict:
    """Return a dict whatever the model sent. A bare string becomes {'summary': ...}."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        return {"summary": raw.strip()}
    return {}


def _norm_evidence(raw) -> list[dict]:
    """Force evidence into [{timestamp, speaker, quote}] whatever the model sent.

    The contract asks for objects, but the model intermittently returns a bare
    string ("agent said X") or a single object instead of a list. Storing those
    shapes unchanged pushes the problem downstream, where a consumer doing
    entry.get("quote") hits AttributeError on a str — which is exactly how the
    dashboard export broke.
    """
    if raw is None:
        return []
    if isinstance(raw, (str, dict)):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    out = []
    for e in raw:
        if isinstance(e, str):
            out.append({"timestamp": None, "speaker": None, "quote": e})
        elif isinstance(e, dict):
            out.append({"timestamp": e.get("timestamp"),
                        "speaker": e.get("speaker"),
                        "quote": e.get("quote") or e.get("text") or ""})
    return out


def _not_scored(meta: dict, reason: str, context: str = "", conduct: dict | None = None) -> dict:
    """A structurally valid audit that records 'we could not assess this call'.

    Every criterion is present and marked n_a so downstream consumers and the
    Section 13 validator still work, but nothing is scored and the tier is
    NOT_SCORED — never 0/AT_RISK, which would read as a real failing grade.
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "audit_status": "not_scored",
        "requires_human_review": True,
        "human_review_reasons": [reason],
        "call_context": context or "unknown",
        "context_reason": "",
        "conduct": conduct or {},
        "call_information": {
            k: _clean(meta.get(k)) for k in (
                "call_id", "crm_link", "lead_id", "evaluation_date", "evaluator_id",
                "evaluator_name", "call_date", "call_duration_seconds", "client_name",
                "lead_source", "property_type", "call_disposition", "disposition_date")
        },
        "filter_dimensions": derive_filter_dimensions(meta),
        "score": {
            "full_max_score": 100, "adjusted_max_score": 0, "earned_score": 0.0,
            "pre_deduction_percentage": None, "red_flag_deduction_total": 0,
            "auto_zero": False, "auto_zero_codes": [], "final_score": None,
            "tier": "NOT_SCORED",
        },
        "criteria": [{
            "criterion_id": s["id"], "criterion_name": s["name"], "max_points": s["max"],
            "applicability": "not_applicable", "score_label": "n_a", "points_awarded": 0.0,
            "mandatory_gate_passed": None,
            "subpoints": [{"subpoint_id": sid, "requirement": req, "mandatory": m,
                           "status": "unknown", "evidence": [], "notes": ""}
                          for sid, req, m in s["subpoints"]],
            "reason": reason,
        } for s in SCORECARD],
        "critical_misses": [{"code": c, "description": d, "observed": "unknown",
                             "evidence": [], "notes": reason} for c, d in CRITICAL_MISSES],
        "red_flags": [{"code": c, "category": cat, "description": d,
                       "deduction_if_observed": ded, "observed": "unknown",
                       "points_deducted": 0, "evidence": [], "notes": reason}
                      for c, cat, ded, d in RED_FLAGS],
        "qualitative_assessment": {},
        "coaching": {},
        "analytics": {
            "critical_miss_present": False, "critical_miss_codes": [],
            "red_flag_present": False, "red_flag_codes": [],
            "applicable_criteria_count": 0,
            "not_applicable_criteria_count": len(SCORECARD),
            "full_criteria_count": 0, "half_criteria_count": 0, "zero_criteria_count": 0,
            "criterion_score_percentages": {s["key"]: None for s in SCORECARD},
        },
    }


# ── Main scorer ────────────────────────────────────────────────────────────
def build_audit(judgements: dict, meta: dict) -> dict:
    """Turn model judgements + call metadata into the complete Section 12 object.

    `judgements` is what the model returns: per-criterion applicability,
    score_label, subpoint statuses with evidence, plus critical_misses,
    red_flags, qualitative_assessment and coaching.
    """
    j_criteria = {c.get("criterion_id"): c for c in judgements.get("criteria", [])}
    j_cm = {c.get("code"): c for c in judgements.get("critical_misses", [])}
    j_rf = {r.get("code"): r for r in judgements.get("red_flags", [])}

    review_reasons: list[str] = []
    context = (judgements.get("call_context") or "full_consultation").strip()
    conduct = _as_dict(judgements.get("conduct"))

    # "The model returned nothing" and "the agent did everything wrong" are the
    # same shape once defaults are applied — every criterion falls through to
    # score_label 'zero' and the call reads as a genuine 0/100. That is a false
    # accusation against an agent, so an absent judgement is scored NOT_SCORED
    # instead, and criteria the model simply never mentioned are excluded from
    # the maximum rather than being awarded zero.
    if not j_criteria:
        return _not_scored(meta, "model returned no call_quality_audit judgements",
                           context, conduct)
    unjudged = {spec["id"] for spec in SCORECARD
                if not (j_criteria.get(spec["id"]) or {}).get("subpoints")}

    # Excluding unjudged criteria shrinks the denominator, which cuts the other
    # way: judge only Criterion 1 well and the call scores 5/5 = 100% GOLD off a
    # single criterion. An inflated grade is more damaging than a zero, so a
    # mostly-absent judgement set is refused outright rather than scored on a
    # denominator too small to mean anything.
    # A callback request, a wrong number or a customer who declined early cannot
    # carry a 100-point consultative grade — there was no consultation. Scoring
    # them on a 5- or 10-point denominator produced numbers that swung 0 to 40
    # between identical runs, and grading an agent on that is indefensible. They
    # get the conduct assessment instead, which is the part that actually applies.
    if context in LIMITED_CONTEXTS:
        return _not_scored(
            meta,
            f"{context.replace('_', ' ')} — no consultation took place, so the "
            f"100-point scorecard does not apply. Judged on conduct instead.",
            context, conduct)

    if len(unjudged) > 3:
        return _not_scored(
            meta, f"only {len(SCORECARD) - len(unjudged)} of {len(SCORECARD)} criteria "
                  f"were judged — too few to score", context, conduct)

    # The auto-zero decision comes from the focused conduct pass, not the big
    # scorecard call. Asked alongside 12 criteria it flipped between runs and took
    # the whole score with it — the same call scored 87.1 and then 0.0. Answered on
    # its own it is stable, and it is the single decision that matters most.
    checks = _as_dict(conduct.get("critical_checks"))
    deadline = _as_dict(checks.get("install_deadline")).get("status")
    if deadline in ("asked", "prompted"):
        j_cm.setdefault("CM-5", {"code": "CM-5"})["observed"] = "no"
        j_cm["CM-5"]["notes"] = f"Agent {deadline} for the install deadline."
    elif deadline == "neither":
        j_cm.setdefault("CM-5", {"code": "CM-5"})["observed"] = "yes"
        j_cm["CM-5"]["notes"] = "Agent never raised when it must be ready."
    if checks.get("genuine_attempt") is True:
        j_cm.setdefault("CM-2", {"code": "CM-2"})["observed"] = "no"
    if checks.get("agent_said_old_brand_name") is False:
        j_cm.setdefault("CM-3", {"code": "CM-3"})["observed"] = "no"

    # Cross-rule linkages the spec defines between criteria and CM/RF codes.
    # Resolved before scoring so a linked flag cannot disagree with its criterion.
    def _cm_observed(code: str) -> str:
        return (j_cm.get(code) or {}).get("observed", "unknown")

    c2 = j_criteria.get(2, {})
    deadline_missed = any(
        s.get("subpoint_id") == "2.4" and s.get("status") == "not_met"
        for s in c2.get("subpoints", [])
    )
    if context in LIMITED_CONTEXTS and _cm_observed("CM-5") == "yes":
        # The agent cannot capture an install deadline on a call the customer
        # ended before discovery. Zeroing the call for it punishes the wrong party.
        j_cm.setdefault("CM-5", {"code": "CM-5"})["observed"] = "no"
        j_cm["CM-5"]["notes"] = (j_cm["CM-5"].get("notes") or "") + \
            f" Not applicable on a {context.replace('_', ' ')} call."
        deadline_missed = False
    if deadline in ("asked", "prompted"):
        deadline_missed = False
    if deadline_missed and _cm_observed("CM-5") != "yes":
        j_cm.setdefault("CM-5", {"code": "CM-5"})["observed"] = "yes"
        j_cm["CM-5"].setdefault("notes", "")
        j_cm["CM-5"]["notes"] += " Auto-set: KYC subpoint 2.4 marked not_met (Criterion 2 rule)."

    if _cm_observed("CM-3") == "yes" and 3 in j_criteria:
        j_criteria[3]["score_label"] = "zero"

    # C6.6 (GST / installation / remote pricing) and RF-7 are the same event.
    c6_gst = any(
        s.get("subpoint_id") == "6.6" and s.get("status") == "not_met"
        for s in j_criteria.get(6, {}).get("subpoints", [])
    )
    if c6_gst and (j_rf.get("RF-7") or {}).get("observed") != "yes":
        j_rf.setdefault("RF-7", {"code": "RF-7"})["observed"] = "yes"

    # Artificial urgency zeroes C11 and fires RF-6.
    if (j_rf.get("RF-6") or {}).get("observed") == "yes" and 11 in j_criteria:
        j_criteria[11]["score_label"] = "zero"

    # ── Criteria ──
    criteria_out, earned, adjusted_max = [], 0.0, 0.0
    label_counts = {"full": 0, "half": 0, "zero": 0}
    na_count = 0
    percentages: dict[str, float | None] = {}

    for spec in SCORECARD:
        cid = spec["id"]
        judged = j_criteria.get(cid, {}) or {}
        judged.setdefault("criterion_id", cid)
        applicable = judged.get("applicability", "applicable") != "not_applicable"

        # In a limited-context call only the criteria the call could actually
        # reach stay applicable; the rest are legitimately N/A.
        limited = LIMITED_CONTEXTS.get(context)
        if limited is not None and cid not in limited:
            na_count += 1
            percentages[spec["key"]] = None
            criteria_out.append({
                "criterion_id": cid, "criterion_name": spec["name"],
                "max_points": spec["max"], "applicability": "not_applicable",
                "score_label": "n_a", "points_awarded": 0.0,
                "mandatory_gate_passed": None, "subpoints": subpoints_out,
                "reason": judged.get("reason") or f"not assessable on a {context.replace('_',' ')} call",
            })
            continue

        # Rules 5 and 8: "not discussed" is not-met, not not-applicable.
        if not applicable and cid not in NA_ALLOWED:
            applicable = True
            judged["score_label"] = "zero"
            review_reasons.append(
                f"Criterion {cid} was marked N/A by the model but N/A is not permitted "
                f"there — scored zero per scorecard rule 5")

        subpoints_out = []
        judged_subs = {s.get("subpoint_id"): s for s in judged.get("subpoints", [])}
        for sid, requirement, mandatory in spec["subpoints"]:
            s = judged_subs.get(sid, {}) or {}
            subpoints_out.append({
                "subpoint_id": sid,
                "requirement": requirement,
                "mandatory": mandatory,
                "status": s.get("status", "unknown"),
                "evidence": _norm_evidence(s.get("evidence")),
                "notes": s.get("notes", "") or "",
            })

        if cid in unjudged:
            applicable = False
            judged["reason"] = (judged.get("reason")
                                or "not assessed — the model returned no judgement for this criterion")
            review_reasons.append(f"Criterion {cid} was not assessed by the model")

        if not applicable:
            na_count += 1
            percentages[spec["key"]] = None
            criteria_out.append({
                "criterion_id": cid, "criterion_name": spec["name"],
                "max_points": spec["max"], "applicability": "not_applicable",
                "score_label": "n_a", "points_awarded": 0.0,
                "mandatory_gate_passed": None, "subpoints": subpoints_out,
                "reason": judged.get("reason", "") or "",
            })
            if not (judged.get("reason") or "").strip():
                review_reasons.append(f"Criterion {cid} marked N/A without an explanation")
            continue

        label, gate = _apply_gates({"criterion_id": cid}, {**judged, "subpoints": subpoints_out})
        if label not in ("full", "half", "zero"):
            label = "zero"
        pts = _points(spec["max"], label)

        earned += pts
        adjusted_max += spec["max"]
        label_counts[label] += 1
        percentages[spec["key"]] = round(pts / spec["max"] * 100, 1)

        if _has_unknown({"subpoints": subpoints_out}):
            review_reasons.append(f"Criterion {cid} has an unknown sub-point status")

        criteria_out.append({
            "criterion_id": cid, "criterion_name": spec["name"],
            "max_points": spec["max"], "applicability": "applicable",
            "score_label": label, "points_awarded": round(pts, 1),
            "mandatory_gate_passed": gate, "subpoints": subpoints_out,
            "reason": judged.get("reason", "") or "",
        })

    health_risk = [c for c in (conduct.get("unsupported_claims") or [])
                   if isinstance(c, dict) and c.get("risk_level") == "high"]
    if health_risk and (j_cm.get("CM-1") or {}).get("observed") == "yes":
        j_cm["CM-1"]["observed"] = "unknown"
        j_cm["CM-1"]["notes"] = ((j_cm["CM-1"].get("notes") or "") +
                                 " Health-claim overreach recorded as a risk for human "
                                 "review rather than an automatic miss-sell.").strip()
        review_reasons.append(
            "unsupported health claim flagged as a risk — needs a human decision "
            "before it counts as miss-sell")

    # Conduct findings drive marks, not just commentary.
    #
    # The conduct pass is the only judge of RF-8/RF-9 — the scorecard contract
    # asks the model for RF-1..RF-7 only — so a clean call has to record the
    # negative here as well as the positive. Writing "yes" and nothing else left
    # both flags at "unknown" on every well-conducted call, and each unknown
    # raises requires_human_review: on a 16-call sample it produced 28 review
    # flags against conduct blocks that plainly said interrupted=false and
    # rapport=good. Absent or malformed conduct still leaves them unknown — a
    # missing answer is not a negative one, and inventing "no" here would clear
    # a flag the pass never actually judged.
    listening = _as_dict(conduct.get("listening"))
    interrupted = listening.get("interrupted")
    ignored = listening.get("ignored_stated_information")
    if interrupted or ignored:
        j_rf.setdefault("RF-8", {"code": "RF-8"})["observed"] = "yes"
        j_rf["RF-8"]["notes"] = (listening.get("coaching") or "")[:400]
        j_rf["RF-8"]["evidence"] = _norm_evidence(listening.get("evidence"))
    elif isinstance(interrupted, bool) and isinstance(ignored, bool):
        j_rf.setdefault("RF-8", {"code": "RF-8"})["observed"] = "no"

    rapport = _as_dict(conduct.get("rapport"))
    rapport_rating = rapport.get("rating")
    if rapport_rating == "poor":
        j_rf.setdefault("RF-9", {"code": "RF-9"})["observed"] = "yes"
        j_rf["RF-9"]["notes"] = (rapport.get("note") or "")[:400]
    elif rapport_rating in ("excellent", "good", "neutral"):
        j_rf.setdefault("RF-9", {"code": "RF-9"})["observed"] = "no"

    # A script-read opening is the first thing a luxury customer notices, so it
    # takes Criterion 1 to zero rather than merely losing a sub-point.
    opening = _as_dict(conduct.get("opening_quality"))
    if opening.get("rating") == "robotic" and 1 in j_criteria:
        j_criteria[1]["score_label"] = "zero"
        j_criteria[1]["reason"] = ((j_criteria[1].get("reason") or "") +
                                   " Opening was read like a script, without warmth.").strip()

    # ── Critical misses ──
    cm_out, auto_zero_codes = [], []
    for code, description in CRITICAL_MISSES:
        j = j_cm.get(code, {}) or {}
        observed = j.get("observed", "unknown")
        if observed not in ("yes", "no", "unknown"):
            observed = "unknown"
        if observed == "yes":
            auto_zero_codes.append(code)
        if observed == "unknown":
            review_reasons.append(f"{code} could not be determined")
        cm_out.append({
            "code": code, "description": description, "observed": observed,
            "evidence": _norm_evidence(j.get("evidence")),
            "notes": (j.get("notes", "") or "").strip(),
        })

    # ── Red flags ──
    rf_out, deduction_total, rf_codes = [], 0, []
    for code, category, deduction, description in RED_FLAGS:
        j = j_rf.get(code, {}) or {}
        observed = j.get("observed", "unknown")
        if observed not in ("yes", "no", "unknown"):
            observed = "unknown"
        applied = deduction if observed == "yes" else 0
        if observed == "yes":
            deduction_total += deduction
            rf_codes.append(code)
        if observed == "unknown":
            review_reasons.append(f"{code} could not be determined")
        rf_out.append({
            "code": code, "category": category, "description": description,
            "deduction_if_observed": deduction, "observed": observed,
            "points_deducted": applied,
            "evidence": _norm_evidence(j.get("evidence")),
            "notes": (j.get("notes", "") or "").strip(),
        })

    # ── Score (Section 8) ──
    # Backstop against a shrunken denominator: even with N/A restricted, a call
    # scored on a handful of points is not a grade worth publishing.
    if 0 < adjusted_max < MIN_SCOREABLE_MAX:
        return _not_scored(
            meta, f"only {int(adjusted_max)} of 100 points were applicable — "
                  f"too little of the scorecard to grade", context, conduct)

    auto_zero = bool(auto_zero_codes)
    if adjusted_max > 0:
        pre = round(earned / adjusted_max * 100, 1)
    else:
        pre = None
        review_reasons.append("No applicable criteria — nothing could be scored")

    if pre is None:
        final = None
    elif auto_zero:
        final = 0.0
    else:
        final = round(max(0.0, pre - deduction_total), 1)

    tier = tier_for(final)

    if pre is None:
        audit_status = "not_scored"
    elif review_reasons:
        audit_status = "human_review_required"
    else:
        audit_status = "completed"

    return {
        "schema_version": SCHEMA_VERSION,
        "audit_status": audit_status,
        "requires_human_review": bool(review_reasons),
        "human_review_reasons": sorted(set(review_reasons)),
        "call_information": {
            k: _clean(meta.get(k)) for k in (
                "call_id", "crm_link", "lead_id", "evaluation_date", "evaluator_id",
                "evaluator_name", "call_date", "call_duration_seconds", "client_name",
                "lead_source", "property_type", "call_disposition", "disposition_date")
        },
        "filter_dimensions": derive_filter_dimensions(meta),
        "score": {
            "full_max_score": 100,
            "adjusted_max_score": int(adjusted_max),
            "earned_score": round(earned, 1),
            "pre_deduction_percentage": pre,
            "red_flag_deduction_total": deduction_total,
            "auto_zero": auto_zero,
            "auto_zero_codes": auto_zero_codes,
            "final_score": final,
            "tier": tier,
        },
        "criteria": criteria_out,
        "critical_misses": cm_out,
        "red_flags": rf_out,
        # _as_dict, not `or {}`: the model sometimes returns these as a plain
        # string of prose. Storing that shape breaks every consumer that does
        # .get() on it — which is how the dashboard export died twice.
        "call_context": context,
        "context_reason": judgements.get("context_reason") or "",
        "conduct": conduct,
        "qualitative_assessment": _as_dict(judgements.get("qualitative_assessment")),
        "coaching": _as_dict(judgements.get("coaching")),
        "analytics": {
            "critical_miss_present": auto_zero,
            "critical_miss_codes": auto_zero_codes,
            "red_flag_present": bool(rf_codes),
            "red_flag_codes": rf_codes,
            "applicable_criteria_count": len(SCORECARD) - na_count,
            "not_applicable_criteria_count": na_count,
            "full_criteria_count": label_counts["full"],
            "half_criteria_count": label_counts["half"],
            "zero_criteria_count": label_counts["zero"],
            "criterion_score_percentages": percentages,
        },
    }


# ── Section 13 self-check ──────────────────────────────────────────────────
def validate(audit: dict) -> list[str]:
    """Return a list of Section 13 violations; empty means the object is sound."""
    errors: list[str] = []
    criteria = audit.get("criteria", [])

    if len(criteria) != 12:
        errors.append(f"expected 12 criteria, found {len(criteria)}")
    if sum(c["max_points"] for c in criteria) != 100:
        errors.append("criterion maximums do not total 100")
    if len({c["criterion_id"] for c in criteria}) != len(criteria):
        errors.append("duplicate criterion ids")
    if len(audit.get("critical_misses", [])) != 5:
        errors.append("expected 5 critical misses")
    if len(audit.get("red_flags", [])) != 9:
        errors.append("expected 9 red flags")

    score = audit.get("score", {})
    applicable = [c for c in criteria if c["applicability"] == "applicable"]
    if score.get("adjusted_max_score") != sum(c["max_points"] for c in applicable):
        errors.append("adjusted_max_score does not match applicable criteria")
    if abs(score.get("earned_score", 0) - sum(c["points_awarded"] for c in applicable)) > 0.05:
        errors.append("earned_score does not match sum of criterion points")

    expected_ded = sum(r["deduction_if_observed"] for r in audit.get("red_flags", [])
                       if r["observed"] == "yes")
    if score.get("red_flag_deduction_total") != expected_ded:
        errors.append("red_flag_deduction_total does not match observed red flags")

    if any(c["observed"] == "yes" for c in audit.get("critical_misses", [])):
        if score.get("final_score") != 0:
            errors.append("critical miss observed but final_score is not 0")
        if not score.get("auto_zero"):
            errors.append("critical miss observed but auto_zero is false")

    if score.get("tier") != tier_for(score.get("final_score")):
        errors.append("tier does not match final_score")

    for c in applicable:
        allowed = {c["max_points"], c["max_points"] / 2.0, 0.0}
        if c["points_awarded"] not in allowed:
            errors.append(f"criterion {c['criterion_id']} has an illegal point value")

    return errors
