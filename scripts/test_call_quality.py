#!/usr/bin/env python3
"""Offline checks for the call-quality scorer. No API calls, no network.

Run: .venv/bin/python scripts/test_call_quality.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from call_quality import SCORECARD, build_audit, validate  # noqa: E402

META = {"call_id": "1", "call_date": "2026-06-11", "call_owner": "Aanchal Ahuja",
        "city": "Delhi", "region": "Unknown", "lead_source": "Typeform"}

FAILURES = []


def check(name, condition, detail=""):
    if condition:
        print(f"  ✅ {name}")
    else:
        print(f"  ❌ {name} {detail}")
        FAILURES.append(name)


def judged(status="met", label="full", **over):
    """Every criterion at one status/label, then per-criterion overrides."""
    criteria = []
    for spec in SCORECARD:
        c = {"criterion_id": spec["id"], "applicability": "applicable",
             "score_label": label, "reason": "test",
             "subpoints": [{"subpoint_id": sid, "status": status, "evidence": []}
                           for sid, _, _ in spec["subpoints"]]}
        criteria.append(c)
    j = {"criteria": criteria,
         "critical_misses": [{"code": f"CM-{i}", "observed": "no"} for i in range(1, 6)],
         "red_flags": [{"code": f"RF-{i}", "observed": "no"} for i in range(1, 10)]}
    for cid, patch in over.items():
        c = j["criteria"][int(cid.lstrip("c")) - 1]
        for sp in patch.get("subpoints", []):
            for existing in c["subpoints"]:
                if existing["subpoint_id"] == sp["subpoint_id"]:
                    existing.update(sp)
        c.update({k: v for k, v in patch.items() if k != "subpoints"})
    return j


print("\n1. Perfect call")
a = build_audit(judged(), META)
check("final 100.0", a["score"]["final_score"] == 100.0, a["score"])
check("tier GOLD", a["score"]["tier"] == "GOLD")
check("adjusted max 100", a["score"]["adjusted_max_score"] == 100)
check("no validation errors", validate(a) == [], validate(a))

print("\n2. Mandatory sub-point not_met zeroes its criterion")
a = build_audit(judged(c9={"subpoints": [{"subpoint_id": "9.2", "status": "not_met"}]}), META)
c9 = next(c for c in a["criteria"] if c["criterion_id"] == 9)
check("C9 zero", c9["score_label"] == "zero" and c9["points_awarded"] == 0.0)
check("gate flagged", c9["mandatory_gate_passed"] is False)
check("final 90.0", a["score"]["final_score"] == 90.0, a["score"]["final_score"])
check("valid", validate(a) == [], validate(a))

print("\n3. Mandatory partial caps the criterion at half")
a = build_audit(judged(c6={"subpoints": [{"subpoint_id": "6.3", "status": "partial"}]}), META)
c6 = next(c for c in a["criteria"] if c["criterion_id"] == 6)
check("C6 half", c6["score_label"] == "half" and c6["points_awarded"] == 5.0, c6["points_awarded"])
check("final 95.0", a["score"]["final_score"] == 95.0)

print("\n4. Critical miss zeroes the whole call")
j = judged()
j["critical_misses"][0]["observed"] = "yes"
a = build_audit(j, META)
check("final 0", a["score"]["final_score"] == 0.0)
check("auto_zero true", a["score"]["auto_zero"] is True)
check("code recorded", a["score"]["auto_zero_codes"] == ["CM-1"])
check("tier AT_RISK", a["score"]["tier"] == "AT_RISK")
check("valid", validate(a) == [], validate(a))

print("\n5. N/A criterion leaves the adjusted maximum")
a = build_audit(judged(c8={"applicability": "not_applicable", "reason": "no objection raised"}), META)
check("adjusted max 90", a["score"]["adjusted_max_score"] == 90)
check("final 100.0", a["score"]["final_score"] == 100.0)
check("percentage null", a["analytics"]["criterion_score_percentages"]["objection_handling"] is None)
check("na counted", a["analytics"]["not_applicable_criteria_count"] == 1)
check("valid", validate(a) == [], validate(a))

print("\n6. Red-flag deductions subtract from the percentage")
j = judged()
j["red_flags"][0]["observed"] = "yes"   # RF-1, -15
j["red_flags"][6]["observed"] = "yes"   # RF-7, -5
a = build_audit(j, META)
check("deduction 20", a["score"]["red_flag_deduction_total"] == 20)
check("final 80.0", a["score"]["final_score"] == 80.0)
check("tier SILVER", a["score"]["tier"] == "SILVER")
check("valid", validate(a) == [], validate(a))

print("\n7. Missing install deadline auto-triggers CM-5")
a = build_audit(judged(c2={"subpoints": [{"subpoint_id": "2.4", "status": "not_met"}]}), META)
cm5 = next(c for c in a["critical_misses"] if c["code"] == "CM-5")
check("CM-5 yes", cm5["observed"] == "yes")
check("final 0", a["score"]["final_score"] == 0.0)
check("C2 zero", next(c for c in a["criteria"] if c["criterion_id"] == 2)["score_label"] == "zero")

print("\n8. CM-3 (Barton Bach) forces Criterion 3 to zero")
j = judged()
j["critical_misses"][2]["observed"] = "yes"
a = build_audit(j, META)
check("C3 zero", next(c for c in a["criteria"] if c["criterion_id"] == 3)["score_label"] == "zero")
check("final 0", a["score"]["final_score"] == 0.0)

print("\n9. Unknown forces human review without deducting")
j = judged()
j["critical_misses"][3]["observed"] = "unknown"   # CM-4, the real-world case
a = build_audit(j, META)
check("requires review", a["requires_human_review"] is True)
check("status human_review_required", a["audit_status"] == "human_review_required")
check("score unaffected", a["score"]["final_score"] == 100.0)
check("reason recorded", any("CM-4" in r for r in a["human_review_reasons"]))

print("\n10. Filter dimensions: derived dates, no invented values")
d = build_audit(judged(), META)["filter_dimensions"]
check("year", d["call_year"] == "2026")
check("quarter", d["call_quarter"] == "Q2")
check("month", d["call_month"] == "2026-06")
check("iso week", d["call_iso_week"] == "2026-W24", d["call_iso_week"])
check("weekday", d["call_day_of_week"] == "Thursday", d["call_day_of_week"])
check("'Unknown' region nulled", d["region"] is None)
check("city preserved", d["city"] == "Delhi")
check("branch stays null", d["branch"] is None)

print("\n11. All-zero call")
a = build_audit(judged(status="not_met", label="zero"), META)
check("final 0", a["score"]["final_score"] == 0.0)
check("tier AT_RISK", a["score"]["tier"] == "AT_RISK")
check("valid", validate(a) == [], validate(a))

print("\n12. Tier boundaries")
from call_quality import tier_for  # noqa: E402
for score, expected in [(100, "GOLD"), (85.0, "GOLD"), (84.9, "SILVER"), (75.0, "SILVER"),
                        (74.9, "BRONZE"), (60.0, "BRONZE"), (59.9, "DEVELOPING"),
                        (50.0, "DEVELOPING"), (49.9, "AT_RISK"), (0, "AT_RISK"),
                        (None, "NOT_SCORED")]:
    check(f"{score} -> {expected}", tier_for(score) == expected, tier_for(score))

print("\n" + "=" * 50)
if FAILURES:
    print(f"❌ {len(FAILURES)} check(s) failed: {FAILURES}")
    sys.exit(1)
print("✅ All scorer checks passed.")
