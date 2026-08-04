# 7 · AI Extraction Schema

One extraction call per transcribed conversation. Input: speaker-separated transcript (original
language), call metadata, taxonomy version. Output (JSON, all insights carry `confidence` 0–1
and `evidence` transcript offsets):

```jsonc
{
  "schema_version": "2026.07.1",
  "model_version": "extraction-v3.2",
  "call_id": "CALL-0001",
  "language": "Hinglish",
  "sentiment": {                       // TEXT-BASED — no acoustic features
    "opening": -0.2, "mid": 0.1, "closing": 0.4,
    "label": "positive", "shift": 0.6,
    "emotions": ["interest", "hesitation"],
    "unresolved_negative": false,
    "confidence": 0.86
  },
  "customer_need": { "value": "Kitchen renovation", "confidence": 0.9, "evidence_t": 84 },
  "budget":   { "value": "₹5–7 lakh" | null },      // null ⇒ "Not mentioned"
  "timeline": { "value": "1–3 months" | null },
  "decision_maker": "yes" | "no" | "unknown",
  "buying_signals": [ { "value": "Asked for quotation", "evidence_t": 312, "confidence": 0.92 } ],
  "faqs": [ {
    "category": "Pricing & discounts",              // 16-value taxonomy (src/types/domain.ts)
    "standardized": "What is the price range for a modular kitchen?",
    "original_question": "Kitna price hoga approximately?",
    "status": "answered" | "partial" | "unanswered",
    "response_time_sec": 12,
    "sentiment_after": "positive",
    "escalation_needed": false,
    "evidence_t": 145, "confidence": 0.88
  } ],
  "objections": [ {
    "type": "Price / discount",                     // 13-value taxonomy
    "intensity": "high",
    "statement": "…customer's words…",
    "employee_response": "…", "technique": "Value reframing",
    "resolution": "resolved" | "partial" | "unresolved",
    "customer_reaction": "positive" | "neutral" | "negative",
    "evidence_t": 402, "confidence": 0.8
  } ],
  "purchase_readiness": { "score": 72, "components": { "need_fit": 80, "explicit_intent": 70,
    "timeline": 60, "next_step_commitment": 85, "authority": 100, "budget": 50, "sentiment": 70 } },
  "quality": { "opening": 82, "discovery": 71, "solution_relevance": 75, "faq_handling": 78,
    "objection_handling": 66, "next_step_clarity": 80, "listening": 74, "professionalism": 88,
    "script_adherence": 79, "compliance_fail": false, "compliance_notes": null,
    "coaching_note": null },
  "talk": { "agent_talk_pct": 54, "interruptions": 1, "longest_silence_sec": 9 } | null,
  "actions": [ {
    "action": "Share quotation",                    // 14-value taxonomy
    "source": "committed" | "ai_recommended",
    "committed_by": "employee" | "customer" | null,
    "due_hint": "2026-08-02", "channel": "WhatsApp",
    "reason": "…", "evidence_t": 512, "confidence": 0.9
  } ],
  "themes": { "appreciation": [], "dissatisfaction": [], "feature_requests": [],
    "expectations": [], "pain_points": [], "topics": [] },
  "competitors": ["HomeLane"],
  "risks": ["Mentioned cancelling if delivery slips"],
  "compliance_flags": [],
  "entities": [ { "text": "Essenza Kitchen", "type": "Product series" } ],
  "summary": "…3–4 sentences…"
}
```

## Extraction rules (contractual)

1. Never output a value that is not supported by transcript evidence — use `null` /
   `"unknown"`; UI renders "Not mentioned".
2. Politeness ≠ intent: buying signals must be explicit behaviours (asked for quote, timeline,
   payment terms), not tone.
3. Customer and agent utterances are scored separately; agent speech never feeds customer
   sentiment.
4. One FAQ per standardised question per call (dedupe before output).
5. No demographic, accent, gender or community inference — prohibited feature set.
6. `talk` block only when diarisation quality ≥ threshold; else null.
7. Every array item carries `evidence_t` so the UI can deep-link to transcript + audio.
8. Below overall confidence 0.6 the call is flagged and excluded from management aggregates.
9. Taxonomies (FAQ 16, objections 13, actions 14) are versioned; outputs carry
   `schema_version` + `model_version` for auditability.
