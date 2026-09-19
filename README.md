# Throughline

**An AI that remembers what was agreed, detects when the conversation drifts, and intervenes before mistakes become decisions.**

Every transcription product answers *"what was said?"*. Throughline answers **"what changed?"**

Built for the [AssemblyAI Voice Agent Hackathon](https://lablab.ai/ai-hackathons/assemblyai-voice-agent-hackathon) — team `tripod`.

---

## Status

Work in progress. The integrity engine is built and tested, and the demo renders live
from its output. Realtime audio is verified but not yet wired.

| | |
|---|---|
| ✅ | Temporal memory, conflict detectors, evidence gate — **43 tests, no network** |
| ✅ | LLM extraction layer — utterance → proposed events, strict JSON schema |
| ✅ | Demo UI rendering real engine output, with cited evidence |
| ✅ | Streaming + diarization verified against the live API — **7/7 speaker attribution** |
| ⬜ | AssemblyAI realtime wiring (mic → worklet → websocket → engine) |
| ⬜ | Replay mode, through the same pipeline |

The extraction layer is written and schema-constrained but **cannot currently run**: the
AssemblyAI LLM Gateway returns *"Your account does not have access to this LLM Gateway
model"* for every model in its catalogue, while streaming and the core API work on the same
key. The engine's independence from it (see Architecture) is why this blocks one half of the
system rather than all of it.

---

## The idea

Consequential conversations go wrong quietly. A constraint stated at minute two is forgotten by minute twenty. A rejection becomes a reluctant *"yeah, I guess"* and gets recorded as agreement. Nobody lies — the conversation drifts, and the outcome stops matching what was actually established.

Post-hoc analysis tells you what went wrong **after** it went wrong. By then the order is placed and the meeting is over.

Throughline listens to a live multi-speaker conversation, maintains structured memory of claims, commitments and decisions, and speaks up **while the outcome can still change**:

```
00:18  SPEAKER B  "Friday is a hard deadline. Monday won't work."
                  → constraint recorded

01:42  SPEAKER A  "So Monday delivery works for you?"
01:47  SPEAKER B  "Yeah... I guess."

       🔴 COMMITMENT DRIFT — Speaker B
          Hedged acceptance of a changed term.
          Confirm before this is recorded as agreement.

          Earlier      00:18  "Friday is a hard deadline..."
          in reply to  01:42  "So Monday delivery works for you?"
          Now          01:47  "Yeah... I guess."

          ✓ Evidence verified — 2 utterances in this transcript
                                             [ DISMISS ]
```

Speakers are `A` / `B`, not roles. That is what diarization actually returns, and
the system does not infer who is the agent and who is the customer — claiming
otherwise would be role detection we haven't built.

The alert names what changed and cites both utterances that prove it, while the delivery
date is still negotiable.

> **Scope note.** A spoken **CLARIFY** intervention — the agent asking *"Earlier you said
> Friday was a hard deadline. Are you changing that requirement to Monday?"* — is **not in
> this build.** It was cut to protect replay mode, which is what makes the demo work for a
> judge evaluating the live URL alone. The claim here is detection with citable evidence,
> and that is what the demo shows.

## The engineering claim

**The LLM proposes. A deterministic engine decides.**

An LLM suggests that two statements might conflict. It does not get to raise an alert. `engine/evidence.py` demands two real utterances, two timestamps, two speaker labels, a conflict type and a confidence score — resolved against the actual transcript, in chronological order, non-empty, distinct.

**No citable evidence, no alert. The agent never invents the reason it intervened.**

That bounds false positives and makes every alert inspectable. An agent that cries wolf is worse than no agent.

## Run the engine

No API key, no network, no audio:

```bash
python run_fixtures.py      # acceptance report
python -m pytest tests -q   # 43 tests
python build_demo.py        # regenerate public/demo.json from engine output
```

```
5 fixtures processed

  clean_control      PASS - 0 alerts
  commitment_drift   PASS
  contradiction      PASS
  decision_conflict  SKIPPED - post-MVP
  unresolved_item    SKIPPED - post-MVP

  False-positive guard: PASS
  Evidence gate:        PASS
```

`clean_control` is the most important fixture in the suite. It is a healthy conversation deliberately loaded with near-misses a naive detector fires on — an openly changed mind, two speakers disagreeing, a restated commitment, different topics with different values. **Correct output is zero alerts.**

## Architecture

The engine is a **pure reducer**:

```python
memory, alerts = step(memory, event, utterances)
```

`engine/` imports nothing that touches a socket, a microphone or a model. That is a hard property — it is what let the whole detection layer be built and tested before any API was wired.

The browser holds the memory and posts it back with each extraction call, so the serverless functions stay stateless.

```
engine/
  models.py     Utterance · Event · EvidenceRef · Alert
  memory.py     temporal store, supersession, payload cap
  conflicts.py  the detectors
  evidence.py   the gate
```

## Why it's built this way

[`DECISIONS.md`](DECISIONS.md) is the decision trail — 23 numbered records covering
the architecture, the scope cuts, and the things that turned out to be wrong.

A few worth reading if you only read three:

- **DR-005** — the evidence gate, and why the LLM is not the final authority.
- **DR-015** — the LLM Gateway locked us out mid-build. The engine's purity meant
  it blocked one half of the system instead of all of it.
- **DR-022** — an alert that has already fired is not settled. Diarization can
  reassign a speaker afterwards, so the gate re-runs and **withdraws its own
  alert** rather than leaving a misattributed quote on screen.

It includes the decisions that were reversed and the two bugs found while
implementing DR-022, because a record that only keeps the choices that worked is
marketing, not engineering.

## Scope

MVP detects **two** event types — contradiction and commitment drift. Two more (decision conflict, unresolved critical item) have fixtures proving the architecture generalises, but no detectors. Detecting everything is how solo projects die.

## Licence

MIT
