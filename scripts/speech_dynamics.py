#!/usr/bin/env python3
"""Speech dynamics from Sarvam diarisation timestamps — no audio, no API calls.

Every metric here comes from `diarized_transcript.entries`, which already carries
`speaker_id`, `start_time_seconds` and `end_time_seconds` for every utterance. So
the whole module is free and replayable over stored transcripts — the property
that makes `rescore_audits.py` worth having. Changing a definition costs a re-run
of this script, not a re-transcription and not an API bill.

What this deliberately does NOT do:

  * No thresholds, tiers or pass/fail. "180 wpm is too fast" is a scorecard rule,
    and the scorecard has seven open questions already. This emits measurements;
    what counts as good is a separate decision that needs sign-off.
  * No acoustic features. Volume, pitch and warmth need the mp3, and audio
    survives for only ~1,093 of 6,260 calls.

Two definitions carry most of the weight, and both exist because these are
Hindi/Hinglish sales calls:

  Backchannels are not turns. A Sunrooof customer says "haan ji" every few
  seconds while listening. Counted as turns they wreck turn counts, monologue
  detection and response latency alike, so utterances of <= BACKCHANNEL_WORDS
  words are treated as listening noise: they neither end the other side's turn
  nor open one of their own. They still count toward speech time and overlap,
  because the mouth was in fact moving.

  Speaking speed is words per second of SPEECH, not per second of call. Pauses
  belong to dead air; mixing them in measures how MUCH someone talks rather than
  how FAST. The unit is romanised-Hinglish whitespace tokens, so the absolute
  number is not comparable to an English wpm benchmark — compare an agent
  against the cohort, never against 150.

Note `interruptions` here will not match `enrich_for_ci.talk_metrics`: that one
counts any overlapping entry, including the constant "haan ji" backchannels, so
it runs high. This counts only substantive speech starting over substantive
speech.

Usage:
    .venv/bin/python scripts/speech_dynamics.py --review-set
    .venv/bin/python scripts/speech_dynamics.py --review-set --report out/speech_dynamics.md
    .venv/bin/python scripts/speech_dynamics.py --ids 887064000042097434,887064000044322645
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Nothing from summarize_calls is imported at module level, deliberately.
# summarize_calls imports THIS module for the gate, and it defines
# agent_speaker_id near the end of the file, so a module-level import here would
# be a circular import that fails on name resolution. Keeping the dependency
# lazy also lets the gate and the test suite run on a bare stdlib interpreter.
BASE = Path(__file__).resolve().parent.parent
TDIR = BASE / "out" / "transcripts"
OUTDIR = BASE / "out" / "speech_dynamics"
REVIEW_SET = BASE / "ci-dashboard" / "src" / "data" / "real" / "review_scenarios.json"

SCHEMA_VERSION = "speech_dynamics_v1"

BACKCHANNEL_WORDS = 3    # "haan ji haan ji" is listening, not a turn
OVERLAP_TOL = 0.15       # same tolerance enrich_for_ci.talk_metrics uses
LONG_PAUSE = 3.0         # a gap a listener would notice as dead air
MIN_PACE_SEC = 1.5       # utterances shorter than this give unstable wpm
MIN_PACE_WORDS = 4


# ── parsing ────────────────────────────────────────────────────────────────
def _words(text):
    """Whitespace tokens containing at least one alphanumeric character."""
    return [w for w in (text or "").split() if any(ch.isalnum() for ch in w)]


def utterances(entries):
    """Clean, sorted utterances. Drops entries with unusable timestamps."""
    out = []
    for e in entries or []:
        start, end = e.get("start_time_seconds"), e.get("end_time_seconds")
        if start is None or end is None or end <= start:
            continue
        w = _words(e.get("transcript"))
        out.append({
            "sid": e.get("speaker_id"),
            "start": float(start),
            "end": float(end),
            "words": len(w),
            "substantive": len(w) > BACKCHANNEL_WORDS,
        })
    out.sort(key=lambda u: (u["start"], u["end"]))
    return out


def _union(spans):
    """Merged (start, end) spans, so overlapping speech is never counted twice."""
    merged = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged


def _total(spans):
    return sum(end - start for start, end in spans)


def turns(utts):
    """Consecutive substantive speech by one side, merged into a single turn."""
    out = []
    for u in utts:
        if not u["substantive"]:
            continue
        if out and out[-1]["sid"] == u["sid"]:
            out[-1]["end"] = max(out[-1]["end"], u["end"])
        else:
            out.append({"sid": u["sid"], "start": u["start"], "end": u["end"]})
    return out


# ── metrics ────────────────────────────────────────────────────────────────
def _side(utts, turns_, sid):
    """Per-speaker metrics. A `sid` that never spoke yields zeros and Nones."""
    mine = [u for u in utts if u["sid"] == sid]
    speech = _total(_union([(u["start"], u["end"]) for u in mine]))
    words = sum(u["words"] for u in mine)
    my_turns = [t for t in turns_ if t["sid"] == sid]

    paces = [u["words"] / (u["end"] - u["start"]) * 60 for u in mine
             if u["end"] - u["start"] >= MIN_PACE_SEC and u["words"] >= MIN_PACE_WORDS]

    return {
        "speech_sec": round(speech, 1),
        "words": words,
        "utterances": len(mine),
        # How fast the mouth moves, pauses excluded.
        "articulation_wpm": round(words / speech * 60, 1) if speech else None,
        # Median is the typical pace; the spread says whether delivery varies or
        # runs flat at one speed for the whole call.
        "pace_median_wpm": round(statistics.median(paces), 1) if paces else None,
        "pace_stdev_wpm": round(statistics.stdev(paces), 1) if len(paces) > 1 else None,
        "pace_samples": len(paces),
        "turns": len(my_turns),
        "avg_turn_sec": round(sum(t["end"] - t["start"] for t in my_turns) / len(my_turns), 1)
                        if my_turns else None,
        "longest_monologue_sec": round(max((t["end"] - t["start"] for t in my_turns), default=0.0), 1),
    }


def _latencies(turns_, responder_sid):
    """Gaps before `responder_sid` takes the floor from the other side."""
    gaps = []
    for prev, cur in zip(turns_, turns_[1:]):
        if cur["sid"] == responder_sid and prev["sid"] != responder_sid:
            gap = cur["start"] - prev["end"]
            if gap >= 0:
                gaps.append(gap)
    return gaps


def _interruptions(utts):
    """Substantive speech starting before the other side's substantive speech ended.

    `prev` tracks the furthest-reaching substantive utterance so far, not simply
    the previous one: a long turn that several short ones overlap should count
    each of them.
    """
    counts = {}
    prev = None
    for u in utts:
        if not u["substantive"]:
            continue
        if prev and u["sid"] != prev["sid"] and u["start"] < prev["end"] - OVERLAP_TOL:
            counts[u["sid"]] = counts.get(u["sid"], 0) + 1
        if prev is None or u["end"] > prev["end"]:
            prev = u
    return counts


def dynamics(entries, agent_sid=None):
    """All speech-dynamics metrics for one call. Pure function, no I/O."""
    utts = utterances(entries)
    if not utts:
        return None
    if agent_sid is None:
        # Lazy, and only on this path: identifying the agent must use the same
        # heuristic as the rest of the pipeline or metrics land on the wrong
        # person, but the gate and the tests must not drag in openai/pydantic.
        from summarize_calls import agent_speaker_id  # noqa: PLC0415
        agent_sid = agent_speaker_id(entries)

    sids = {u["sid"] for u in utts}
    other = sids - {agent_sid}
    # Sarvam occasionally splits one side across ids. The busiest non-agent id is
    # the customer; any remainder is reported in `extra_speaker_ids` rather than
    # being silently folded into one of the two sides.
    customer_sid = max(
        other,
        key=lambda s: sum(u["end"] - u["start"] for u in utts if u["sid"] == s),
        default=None)

    span_start = min(u["start"] for u in utts)
    span_end = max(u["end"] for u in utts)
    span = span_end - span_start

    all_speech = _union([(u["start"], u["end"]) for u in utts])
    speech_sec = _total(all_speech)
    raw_sec = sum(u["end"] - u["start"] for u in utts)

    pauses = [b[0] - a[1] for a, b in zip(all_speech, all_speech[1:])]
    long_pauses = [g for g in pauses if g > LONG_PAUSE]

    turns_ = turns(utts)
    agent = _side(utts, turns_, agent_sid)
    customer = _side(utts, turns_, customer_sid)

    interrupts = _interruptions(utts)
    minutes = span / 60 if span else 0
    talk_total = agent["speech_sec"] + customer["speech_sec"]

    agent_lat = _latencies(turns_, agent_sid)
    cust_lat = _latencies(turns_, customer_sid)

    return {
        "schema_version": SCHEMA_VERSION,
        "agent_speaker_id": agent_sid,
        "customer_speaker_id": customer_sid,
        "extra_speaker_ids": sorted(s for s in other if s != customer_sid),
        "utterances": len(utts),
        "call_span_sec": round(span, 1),
        "speech_sec": round(speech_sec, 1),
        "silence_sec": round(max(0.0, span - speech_sec), 1),
        "silence_share": round(max(0.0, span - speech_sec) / span, 3) if span else None,
        # Both sides talking at once: per-side time summed, minus the union.
        "overlap_sec": round(max(0.0, raw_sec - speech_sec), 1),
        "long_pauses": {
            "count": len(long_pauses),
            "total_sec": round(sum(long_pauses), 1),
            "longest_sec": round(max(pauses, default=0.0), 1),
        },
        "agent": agent,
        "customer": customer,
        "agent_talk_share": round(agent["speech_sec"] / talk_total, 3) if talk_total else None,
        "interruptions": {
            "by_agent": interrupts.get(agent_sid, 0),
            "by_customer": interrupts.get(customer_sid, 0),
            "by_agent_per_min": round(interrupts.get(agent_sid, 0) / minutes, 2) if minutes else None,
            "by_customer_per_min": round(interrupts.get(customer_sid, 0) / minutes, 2) if minutes else None,
        },
        "response_latency_sec": {
            "agent_median": round(statistics.median(agent_lat), 2) if agent_lat else None,
            "customer_median": round(statistics.median(cust_lat), 2) if cust_lat else None,
            "agent_samples": len(agent_lat),
            "customer_samples": len(cust_lat),
        },
    }


# ── Conversation gate ──────────────────────────────────────────────────────
# "Did a conversation happen at all" is arithmetic on timestamps, not judgement,
# so it belongs here rather than in the prompt — the same argument that put
# scoring in call_quality.py. The model gets this wrong: on the four confirmed
# dead recordings in the review set it returned `not_reachable` for two and
# `follow_up_needed` with politeness grades of 3/5 and 4/5 for the other two.
# A recording of an empty room cannot be a polite call.
#
# Thresholds come from measuring all 6,253 stored transcripts, not from feel:
#
#   speech density (speech ÷ span)   p1 0.32   p5 0.58   p25 0.80   p50 0.88
#   substantive words                p1 27     p5 43     p25 96     p50 201
#
# `no_contact` is the existing scorecard context for "voicemail, IVR, no answer"
# (prompts/call_quality_audit.md) and is already in call_quality.LIMITED_CONTEXTS,
# so nothing downstream needs a new category.
GATE_MIN_WORDS = 20      # corpus p1 is 27; below 20 nobody held a conversation
GATE_MIN_SPAN = 120.0    # under two minutes, sparse just means a short call
GATE_MAX_DENSITY = 0.35  # corpus p1 is 0.32 against a median of 0.88


def conversation_gate(entries):
    """Deterministic verdict on whether a call is worth assessing.

    Returns a dict with `verdict`:

      "no_contact" — no conversation took place. Safe to skip before the model
                     is ever called. Flags 34 of 6,253 (0.5%); every one that
                     was read is hold music, a dropped line, or voicemail.
      "sparse"     — a long recording that is mostly silence. Flags 6 of 6,253
                     (0.1%). NOT safe to drop: one member is a real inbound call
                     sitting behind 90 seconds of hold music, and no word-count
                     floor separates it from genuine ambient noise (119 / 143 /
                     150 substantive words for dead / real / dead). Needs an eye.
      "ok"         — assess normally.

    Stripping IVR and hold-music segments before measuring density would make
    the sparse arm safe to drop, but the boilerplate cannot itself be the rule:
    777 transcripts contain it and 178 of those are real calls.
    """
    utts = utterances(entries)
    substantive = [u for u in utts if u["substantive"]]
    words = sum(u["words"] for u in substantive)

    if not utts:
        return {"verdict": "no_contact", "reason": "no usable timestamps",
                "substantive_words": 0, "span_sec": 0.0, "density": None}

    span = max(u["end"] for u in utts) - min(u["start"] for u in utts)
    speech = _total(_union([(u["start"], u["end"]) for u in utts]))
    density = speech / span if span else None

    out = {"substantive_words": words, "span_sec": round(span, 1),
           "density": round(density, 3) if density is not None else None}

    if words < GATE_MIN_WORDS:
        return {**out, "verdict": "no_contact",
                "reason": f"only {words} substantive words in "
                          f"{span / 60:.1f} min of recording — no conversation took place"}

    if span >= GATE_MIN_SPAN and density is not None and density < GATE_MAX_DENSITY:
        return {**out, "verdict": "sparse",
                "reason": f"{span / 60:.1f} min recording is {(1 - density) * 100:.0f}% "
                          f"silence — may be ambient noise rather than a call"}

    return {**out, "verdict": "ok", "reason": ""}


def for_call(call_id):
    """(metrics, error) for one call id, read from the stored transcript."""
    path = TDIR / f"{call_id}.mp3.json"
    if not path.exists():
        return None, "no transcript"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return None, f"unreadable transcript: {e}"
    result = dynamics(data.get("diarized_transcript", {}).get("entries", []))
    if result is None:
        return None, "no usable timestamps"
    result["call_id"] = call_id
    return result, None


# ── call selection ─────────────────────────────────────────────────────────
def review_set_calls():
    """The contradiction cohorts from review_scenarios.json, as (cohort, id, meta).

    One row per group — the cohorts are call-level, so `calls[0]` is the call the
    cohort was selected on.
    """
    if not REVIEW_SET.exists():
        sys.exit(f"❌ {REVIEW_SET} not found — run build_review_scenarios.py first")
    data = json.loads(REVIEW_SET.read_text(encoding="utf-8"))
    out = []
    for key in sorted(k for k in data if k.startswith("outlier_")):
        for group in data[key]:
            calls = group.get("calls") or []
            if not calls:
                continue
            out.append((group.get("title") or key, calls[0]["call_id"], calls[0]))
    return out


# ── reporting ──────────────────────────────────────────────────────────────
def _cell(value, suffix=""):
    return "—" if value is None else f"{value}{suffix}"


def report(rows):
    """Markdown, grouped by cohort. Deliberately no verdict column."""
    md = ["# Speech dynamics — review-set contradiction cohorts", "",
          "Measured from Sarvam diarisation timestamps. No audio, no API calls.",
          "",
          "`wpm` is romanised-Hinglish whitespace tokens per minute of speech "
          "(pauses excluded), so it is comparable between these agents but not "
          "to an English benchmark. `share` is the agent's portion of total "
          "speech time. `mono` is the longest uninterrupted agent turn.",
          ""]
    cohorts = {}
    for cohort, meta, m in rows:
        cohorts.setdefault(cohort, []).append((meta, m))

    for cohort, items in cohorts.items():
        md += [f"\n## {cohort}", "",
               "| Call ID | Agent | Min | Agent wpm | Cust wpm | Pace σ | Share | Mono | Silence | Int A/C | Reply |",
               "|---|---|---|---|---|---|---|---|---|---|---|"]
        for meta, m in items:
            a, c = m["agent"], m["customer"]
            md.append(
                f"| `{m['call_id']}` | {meta.get('agent') or '—'} "
                f"| {m['call_span_sec'] / 60:.1f} "
                f"| {_cell(a['articulation_wpm'])} "
                f"| {_cell(c['articulation_wpm'])} "
                f"| {_cell(a['pace_stdev_wpm'])} "
                f"| {_cell(round(m['agent_talk_share'] * 100) if m['agent_talk_share'] is not None else None, '%')} "
                f"| {_cell(a['longest_monologue_sec'], 's')} "
                f"| {_cell(round(m['silence_share'] * 100) if m['silence_share'] is not None else None, '%')} "
                f"| {m['interruptions']['by_agent']}/{m['interruptions']['by_customer']} "
                f"| {_cell(m['response_latency_sec']['agent_median'], 's')} |")
    return "\n".join(md) + "\n"


def gate_scan():
    """Dry run of the gate over every stored transcript. Read-only.

    Worth running before trusting the gate and after any threshold change: the
    sparse arm has a known false-positive mode, so the list matters more than
    the count.
    """
    dropped, sparse, ok, unreadable = [], [], 0, 0
    for path in sorted(TDIR.glob("*.json")):
        cid = path.name.removesuffix(".mp3.json")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            unreadable += 1
            continue
        g = conversation_gate(data.get("diarized_transcript", {}).get("entries", []))
        if g["verdict"] == "no_contact":
            dropped.append((cid, g))
        elif g["verdict"] == "sparse":
            sparse.append((cid, g))
        else:
            ok += 1

    total = len(dropped) + len(sparse) + ok
    print(f"\nScanned {total} transcript(s)"
          + (f", {unreadable} unreadable" if unreadable else ""))
    print(f"  no_contact (skip before the model): {len(dropped)}"
          f"  ({len(dropped) / total * 100:.2f}%)" if total else "")
    print(f"  sparse (needs a human eye):         {len(sparse)}"
          f"  ({len(sparse) / total * 100:.2f}%)" if total else "")
    print(f"  ok:                                 {ok}")

    if sparse:
        print("\nSparse — review these individually, do not bulk-drop them:")
        for cid, g in sorted(sparse, key=lambda x: -x[1]["span_sec"]):
            print(f"  {cid}  {g['span_sec'] / 60:5.1f} min  density {g['density']:.2f}  "
                  f"{g['substantive_words']:>4} words")
    if dropped:
        print(f"\nno_contact — longest {min(15, len(dropped))} of {len(dropped)}:")
        for cid, g in sorted(dropped, key=lambda x: -x[1]["span_sec"])[:15]:
            print(f"  {cid}  {g['span_sec'] / 60:5.1f} min  "
                  f"{g['substantive_words']:>4} words")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ids", default="", help="comma-separated call ids")
    ap.add_argument("--review-set", action="store_true",
                    help="the contradiction cohorts from review_scenarios.json")
    ap.add_argument("--out", default=str(OUTDIR), help=f"output dir (default {OUTDIR})")
    ap.add_argument("--report", default="", help="also write a markdown table here")
    ap.add_argument("--gate-scan", action="store_true",
                    help="run the conversation gate over every stored transcript "
                         "and list what it would drop or flag. Writes nothing.")
    args = ap.parse_args()

    if args.gate_scan:
        return gate_scan()

    if args.review_set:
        selected = review_set_calls()
    elif args.ids:
        selected = [("", cid.strip(), {}) for cid in args.ids.split(",") if cid.strip()]
    else:
        ap.error("pass --review-set or --ids")

    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)

    rows, failed = [], []
    for cohort, cid, meta in selected:
        m, err = for_call(cid)
        if err:
            failed.append((cid, err))
            print(f"  ⚠️  {cid}: {err}")
            continue
        (outdir / f"{cid}.json").write_text(json.dumps(m, indent=2), encoding="utf-8")
        rows.append((cohort, meta, m))
        a = m["agent"]
        print(f"  ✅ {cid}  {m['call_span_sec'] / 60:5.1f} min  "
              f"agent {_cell(a['articulation_wpm']):>6} wpm  "
              f"share {_cell(round(m['agent_talk_share'] * 100) if m['agent_talk_share'] is not None else None)}%  "
              f"mono {a['longest_monologue_sec']:.0f}s")

    print(f"\n{len(rows)} call(s) written to {outdir}")
    if failed:
        print(f"{len(failed)} failed: {failed}")

    if args.report and rows:
        rp = Path(args.report)
        rp.parent.mkdir(parents=True, exist_ok=True)
        rp.write_text(report(rows), encoding="utf-8")
        print(f"report: {rp}")

    return 1 if failed and not rows else 0


if __name__ == "__main__":
    sys.exit(main())
