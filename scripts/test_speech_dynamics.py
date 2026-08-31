#!/usr/bin/env python3
"""Offline checks for the speech-dynamics metrics. No API calls, no network.

Run: .venv/bin/python scripts/test_speech_dynamics.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from speech_dynamics import (  # noqa: E402
    conversation_gate, dynamics, turns, utterances,
)

FAILURES = []


def check(name, condition, detail=""):
    if condition:
        print(f"  ✅ {name}")
    else:
        print(f"  ❌ {name} {detail}")
        FAILURES.append(name)


def e(sid, start, end, text):
    return {"speaker_id": sid, "start_time_seconds": start,
            "end_time_seconds": end, "transcript": text}


AGENT, CUST = "1", "2"
SIX = "one two three four five six"


print("\n1. Parsing")
raw = [e(AGENT, 0, 2, SIX),
       e(CUST, 5, 4, "backwards timestamps"),   # end <= start
       e(CUST, 6, None, "missing end"),
       e(CUST, 7, 9, "haan ji")]
u = utterances(raw)
check("bad timestamps dropped", len(u) == 2, [x["start"] for x in u])
check("6 words counted", u[0]["words"] == 6, u[0]["words"])
check("6 words is substantive", u[0]["substantive"] is True)
check("2 words is a backchannel", u[1]["substantive"] is False)
check("empty call returns None", dynamics([]) is None)

print("\n2. Articulation rate excludes pauses")
# 12 words of speech in 6s of speech, spread over a 60s call.
d = dynamics([e(AGENT, 0, 3, SIX), e(AGENT, 57, 60, SIX)], agent_sid=AGENT)
check("120 wpm of speech, not 12 of call", d["agent"]["articulation_wpm"] == 120.0,
      d["agent"]["articulation_wpm"])
check("speech_sec is 6", d["speech_sec"] == 6.0, d["speech_sec"])
check("silence_sec is 54", d["silence_sec"] == 54.0, d["silence_sec"])
check("one long pause", d["long_pauses"]["count"] == 1, d["long_pauses"])
check("longest pause 54s", d["long_pauses"]["longest_sec"] == 54.0, d["long_pauses"])

print("\n3. Overlapping speech is counted once in the union")
d = dynamics([e(AGENT, 0, 10, SIX), e(CUST, 5, 15, SIX)], agent_sid=AGENT)
check("speech_sec is the union (15)", d["speech_sec"] == 15.0, d["speech_sec"])
check("overlap_sec is 5", d["overlap_sec"] == 5.0, d["overlap_sec"])
check("agent speech_sec is 10", d["agent"]["speech_sec"] == 10.0)
check("talk share 10/20", d["agent_talk_share"] == 0.5, d["agent_talk_share"])

print("\n4. Backchannels do not break a turn")
# The customer says "haan ji" twice while the agent talks straight through.
d = dynamics([e(AGENT, 0, 10, SIX), e(CUST, 4, 5, "haan ji"),
              e(AGENT, 10, 20, SIX), e(CUST, 14, 15, "ji ji"),
              e(AGENT, 20, 30, SIX)], agent_sid=AGENT)
check("one agent turn, not three", d["agent"]["turns"] == 1, d["agent"]["turns"])
check("monologue runs the full 30s", d["agent"]["longest_monologue_sec"] == 30.0,
      d["agent"]["longest_monologue_sec"])
check("customer opens no turn", d["customer"]["turns"] == 0, d["customer"]["turns"])
check("backchannel time still counts", d["customer"]["speech_sec"] == 2.0,
      d["customer"]["speech_sec"])
check("backchannels are not interruptions", d["interruptions"]["by_customer"] == 0,
      d["interruptions"])

print("\n5. Interruptions are directional")
# Agent starts 2s before the customer finishes.
d = dynamics([e(CUST, 0, 10, SIX), e(AGENT, 8, 15, SIX)], agent_sid=AGENT)
check("agent interrupted once", d["interruptions"]["by_agent"] == 1, d["interruptions"])
check("customer interrupted none", d["interruptions"]["by_customer"] == 0, d["interruptions"])
# Same call from the other side.
d = dynamics([e(AGENT, 0, 10, SIX), e(CUST, 8, 15, SIX)], agent_sid=AGENT)
check("customer interrupted once", d["interruptions"]["by_customer"] == 1, d["interruptions"])
check("agent interrupted none", d["interruptions"]["by_agent"] == 0, d["interruptions"])
# A 0.1s overlap is diarisation jitter, not an interruption (OVERLAP_TOL 0.15).
d = dynamics([e(CUST, 0, 10, SIX), e(AGENT, 9.9, 15, SIX)], agent_sid=AGENT)
check("sub-tolerance overlap ignored", d["interruptions"]["by_agent"] == 0, d["interruptions"])

print("\n6. Several short turns overlapping one long turn all count")
d = dynamics([e(AGENT, 0, 30, SIX), e(CUST, 5, 9, SIX), e(CUST, 15, 19, SIX)],
             agent_sid=AGENT)
check("both customer overlaps counted", d["interruptions"]["by_customer"] == 2,
      d["interruptions"])

print("\n7. Response latency is the gap before taking the floor")
d = dynamics([e(CUST, 0, 10, SIX), e(AGENT, 13, 20, SIX),
              e(CUST, 25, 30, SIX), e(AGENT, 31, 40, SIX)], agent_sid=AGENT)
check("agent median reply 2.0s", d["response_latency_sec"]["agent_median"] == 2.0,
      d["response_latency_sec"])
check("two samples", d["response_latency_sec"]["agent_samples"] == 2,
      d["response_latency_sec"])

print("\n8. Speaker identification")
d = dynamics([e(AGENT, 0, 10, SIX), e(CUST, 11, 30, SIX), e("3", 31, 32, SIX)],
             agent_sid=AGENT)
check("busiest non-agent is the customer", d["customer_speaker_id"] == CUST,
      d["customer_speaker_id"])
check("third speaker reported, not folded in", d["extra_speaker_ids"] == ["3"],
      d["extra_speaker_ids"])
check("customer speech excludes the third", d["customer"]["speech_sec"] == 19.0,
      d["customer"]["speech_sec"])

print("\n9. A side that never speaks")
d = dynamics([e(AGENT, 0, 10, SIX)], agent_sid=AGENT)
check("customer sid is None", d["customer_speaker_id"] is None)
check("customer speech 0", d["customer"]["speech_sec"] == 0.0)
check("customer wpm None", d["customer"]["articulation_wpm"] is None)
check("agent share 100%", d["agent_talk_share"] == 1.0, d["agent_talk_share"])
check("no reply latency", d["response_latency_sec"]["agent_median"] is None)

print("\n10. Turn merging is on substantive speech only")
t = turns(utterances([e(AGENT, 0, 5, SIX), e(AGENT, 6, 10, SIX), e(CUST, 11, 15, SIX)]))
check("two turns", len(t) == 2, t)
check("agent turn spans the gap", (t[0]["start"], t[0]["end"]) == (0.0, 10.0), t[0])

print("\n11. Conversation gate — no_contact")
# A 10-minute recording containing one word. The real failure mode: the model
# graded exactly this shape as "polite 4/5".
g = conversation_gate([e(AGENT, 0.1, 0.6, "Hello")])
check("one word in a recording is no_contact", g["verdict"] == "no_contact", g)
check("reason names the word count", "1 substantive words" in g["reason"]
      or "0 substantive words" in g["reason"], g["reason"])
check("empty entries is no_contact", conversation_gate([])["verdict"] == "no_contact")
# Ambient chatter: minutes of recording, a handful of words, mostly silence.
ambient = [e(AGENT, 0, 4, SIX), e(CUST, 300, 304, SIX), e(AGENT, 600, 604, SIX)]
check("ambient chatter is no_contact",
      conversation_gate(ambient)["verdict"] == "no_contact", conversation_gate(ambient))

print("\n12. Conversation gate — sparse, not dropped")
# 18 substantive words over 4 minutes: past the word floor, under the density
# floor. Must NOT be no_contact — a real call can hide behind hold music.
long_words = " ".join(["word"] * 30)
sparse = [e(AGENT, 0, 10, long_words), e(CUST, 200, 210, long_words)]
g = conversation_gate(sparse)
check("long and mostly silent is sparse", g["verdict"] == "sparse", g)
check("sparse reports its density", g["density"] < 0.35, g)
check("reason names the silence", "silence" in g["reason"], g["reason"])

print("\n13. Conversation gate — ordinary calls pass")
# A short but genuine call must not be gated: 'not interested, goodbye' is a
# real call and belongs in review, not in the skip pile.
short_real = [e(AGENT, 0, 6, long_words), e(CUST, 6.5, 12, long_words)]
check("short dense call is ok", conversation_gate(short_real)["verdict"] == "ok",
      conversation_gate(short_real))
# Sparse only applies past GATE_MIN_SPAN; under two minutes it is just short.
brief_gappy = [e(AGENT, 0, 5, long_words), e(CUST, 100, 105, long_words)]
check("under 120s is never sparse", conversation_gate(brief_gappy)["verdict"] == "ok",
      conversation_gate(brief_gappy))
# Backchannels must not lift a dead call over the word floor.
noise = [e(AGENT, 0, 1, "haan ji"), e(CUST, 2, 3, "ji ji"), e(AGENT, 4, 5, "hmm ok")] * 8
check("backchannels alone stay no_contact",
      conversation_gate(noise)["verdict"] == "no_contact", conversation_gate(noise))

print("\n" + "=" * 50)
if FAILURES:
    print(f"❌ {len(FAILURES)} check(s) failed: {FAILURES}")
    sys.exit(1)
print("✅ All speech-dynamics checks passed.")
