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

## The wedge

Plenty of systems check what a speaker says against a **rulebook** — a regulation, a
required disclosure, a policy.

**Throughline checks a conversation against itself.**

There is no rulebook for *"you said Friday was a hard deadline, and you just accepted
Monday."* That conflict only exists relative to what this conversation established
twenty minutes earlier, which is why it needs memory rather than a policy engine.

Hedged agreement is where the difference shows. *"Yeah... I guess."* can be caught
acoustically — a pause, a filler, a wavering tone — and caught that way it means
*this person sounds unsure right now*. Throughline catches it **semantically**, against a
constraint stated at minute two, and that means something stronger: **the deal just
changed and nobody said so.**

## Where this bites: order and deal calls

A delivery date, a quantity, a discount, payment terms. Terms move during a call, the
call ends, and operations ships, invoices or quotes against a version nobody agreed to.
The cost is ordinary and expensive: disputes, rework, chargebacks, re-quotes.

No regulator is involved. Nothing was mis-sold. The deal simply stopped matching itself.

## The engineering claim

**The LLM proposes. A deterministic engine decides.**

An LLM suggests that two statements might conflict. It does not get to raise an alert. `engine/evidence.py` demands two real utterances, two timestamps, two speaker labels, a conflict type and a confidence score — resolved against the actual transcript, in chronological order, non-empty, distinct.

**No citable evidence, no alert. The agent never invents the reason it intervened.**

That bounds false positives and makes every alert inspectable. An agent that cries wolf is worse than no agent.

**And an alert is never settled.** Diarization can reassign a speaker after an alert has
fired. When that happens the gate re-runs, and an alert whose evidence no longer supports
it is **withdrawn on screen** rather than left standing. Quietly misattributing a quote is
the exact failure this project exists to prevent — shipping it would be indefensible.

### The measurement that matters

Live extraction was run against every fixture, in four different prompt
configurations — including one that was actively broken and regressed the
flagship case.

**The clean control produced zero false positives in every single configuration.**

`clean_control` is a healthy conversation deliberately loaded with the near-misses
a naive detector fires on: an openly changed mind, two speakers disagreeing, a
restated commitment, different topics carrying different values. Correct output
is nothing at all — and it stayed nothing even while the extractor feeding it was
misbehaving.

That is the design working as intended. The model is a proposer, and a weak
proposer yields **missed alerts, never false ones**. Measured over 3 runs:
commitment drift fired 3/3, the clean control stayed silent 3/3, contradiction
missed 0/3. All three rates are published, including the one that fails —
see [DR-024 and DR-025](DECISIONS.md).

The same principle applies upstream in the extraction prompt, where topics must
not be merged: *a missed conflict costs one alert, a merged topic costs trust.*

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
