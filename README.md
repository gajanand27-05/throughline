# Throughline

**An AI that remembers what was agreed, detects when the conversation drifts, and intervenes before mistakes become decisions.**

Every transcription product answers *"what was said?"*. Throughline answers **"what changed?"**

Built for the [AssemblyAI Voice Agent Hackathon](https://lablab.ai/ai-hackathons/assemblyai-voice-agent-hackathon) — team `tripod`.

---

## Status

Work in progress. The integrity engine is built and tested; realtime audio is not yet wired.

| | |
|---|---|
| ✅ | Temporal memory, conflict detectors, evidence gate — **32 tests, no network** |
| ⬜ | AssemblyAI realtime streaming + speaker attribution |
| ⬜ | Replay mode |
| ⬜ | CLARIFY intervention |

---

## The idea

Consequential conversations go wrong quietly. A constraint stated at minute two is forgotten by minute twenty. A rejection becomes a reluctant *"yeah, I guess"* and gets recorded as agreement. Nobody lies — the conversation drifts, and the outcome stops matching what was actually established.

Post-hoc analysis tells you what went wrong **after** it went wrong. By then the order is placed and the meeting is over.

Throughline listens to a live multi-speaker conversation, maintains structured memory of claims, commitments and decisions, and speaks up **while the outcome can still change**:

```
00:18  CUSTOMER   "Friday is a hard deadline. Monday won't work."
                  → constraint recorded

01:42  AGENT      "So Monday delivery works for you?"
01:47  CUSTOMER   "Yeah... I guess."

       🔴 COMMITMENT DRIFT
          Earlier:  Friday = hard deadline          00:18
          Current:  ambiguous acceptance of Monday  01:47
          Evidence: 2 utterances · Confidence: 94%
          [ CLARIFY ]                    [ DISMISS ]
```

Pressing **CLARIFY** makes the agent ask: *"Earlier you said Friday was a hard deadline. Are you changing that requirement to Monday?"*

## The engineering claim

**The LLM proposes. A deterministic engine decides.**

An LLM suggests that two statements might conflict. It does not get to raise an alert. `engine/evidence.py` demands two real utterances, two timestamps, two speaker labels, a conflict type and a confidence score — resolved against the actual transcript, in chronological order, non-empty, distinct.

**No citable evidence, no alert. The agent never invents the reason it intervened.**

That bounds false positives and makes every alert inspectable. An agent that cries wolf is worse than no agent.

## Run the engine

No API key, no network, no audio:

```bash
python run_fixtures.py     # acceptance report
python -m pytest tests -q  # 32 tests
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

## Scope

MVP detects **two** event types — contradiction and commitment drift. Two more (decision conflict, unresolved critical item) have fixtures proving the architecture generalises, but no detectors. Detecting everything is how solo projects die.

## Licence

MIT
