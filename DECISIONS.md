# Decision Records

Why Throughline is built the way it is. Numbered, append-only, and **including
the decisions that were later reversed or corrected** — a record that only keeps
the choices that worked is marketing, not engineering.

Working notes, schedules and research live outside this repository. This file is
the curated decision trail.

---

## DR-001 — The browser talks to AssemblyAI directly; the backend only mints tokens

**Context.** A voice agent needs a live audio stream. The obvious architecture is a server relaying audio between browser and provider.

**Decision.** The browser holds the websocket to AssemblyAI directly, authenticated with a short-lived token minted server-side. Our backend is request/response only and never touches audio.

**Consequences.** The backend is two small serverless functions with no persistent websockets, which is what makes Vercel viable with no Dockerfile and no always-on process. Lowest possible latency. The token endpoint becomes a public surface — see DR-002.

## DR-002 — Token endpoint hardening, decided before deploy

**Context.** A public `/api/session` on a public URL, in a public repo that documents it, will mint tokens for anyone who finds it.

**Decision.** Before deployment, not after: token expiry at the documented minimum, capped session duration, an `Origin` allowlist, usage alerts, and payload caps on all function inputs.

**Consequences.** Slightly more work in one function. The `Origin` check must be verified explicitly rather than assumed.

## DR-003 — `sessionConfig` is client-visible by design

**Decision.** The configuration blob returned to the browser carries only data the user already owns — no server-side secrets, no internal identifiers.

**Rationale.** It is inspectable by anyone who opens devtools. Better to make that a deliberate, enforced property than to discover a judge noticed it first.

## DR-004 — Product pivot to conversational integrity

**Context.** The first product was an oral-exam examiner. Two things killed it. The hackathon board already held two mock examiners, so it would have scored nothing on originality. More fundamentally, **it was a chatbot with a voice** — the same product could have been built as text with little loss, which is the opposite of what wins a voice hackathon.

**Decision.** Killed. Replaced with an agent that observes a multi-speaker human-to-human conversation, maintains temporal memory of claims, commitments and decisions, and intervenes when the conversation drifts from what was established.

**Rationale.** Voice is load-bearing here: the system needs live multi-speaker speech over time, with attribution. Removing voice does not degrade it, it destroys it.

**Consequences.** Roughly two days of design work discarded. The architecture, host and engineering discipline carried over unchanged, which limited the loss.

## DR-005 — The evidence gate: the LLM proposes, the engine decides

**Context.** The easy build is transcript → LLM → "this seems inconsistent." That produces a system whose alerts cannot be checked and whose false positives cannot be bounded.

**Decision.** The LLM only ever *proposes* a possible conflict. A deterministic engine then requires two utterances, two timestamps, two speaker labels, a conflict type and a confidence score, all resolved against the actual transcript. **No citable evidence, no alert.** The agent never invents the reason it intervened.

**Rationale.** It bounds false positives, makes every alert inspectable, and converts "trust the model" into "here are the two things you said."

**Consequences.** More engineering than a pure LLM approach. Deliberately biased toward missing conflicts rather than false-alarming. Ambiguity produces a clarification request, never an accusation. This decision is load-bearing for DR-017, DR-018 and DR-022.

## DR-006 — Credits are not a design constraint

**Context.** Early planning assumed a hard budget ceiling and imposed testing austerity.

**Decision.** Dropped. Verified pricing: realtime transcription at $0.45/hr, streaming diarization with revision at +$0.12/hr, billed per second, with 333 free streaming hours. A hundred hours of both costs roughly $57.

**Consequences.** Development can use genuine multi-speaker sessions. DR-002's controls remain, now protecting free-tier hours rather than a cash balance.

## DR-007 — Replay is a first-class deliverable, not a fallback

**Context.** The product's value is temporal — a constraint stated at minute two, contradicted at minute twenty. But a judge evaluating the live URL is alone and cannot produce a two-speaker conversation.

**Decision.** A replay mode that streams a prerecorded two-speaker conversation through **the exact same pipeline** as the microphone. Built from day one. Live mic mode exists alongside it to prove realtime is genuine.

**Consequences.** Both modes share one pipeline; replay pushes decoded audio frames through the same websocket path. Superseded in emphasis by DR-020.

## DR-008 — Two speakers is the core case, never self-contradiction

**Decision.** The core case is **two speakers with attribution** — who committed to what.

**Rationale.** If one person contradicts themselves, diarization is decorative and a judge will notice. Speaker attribution being load-bearing is the whole argument that AssemblyAI is structurally necessary rather than bolted on.

**Consequences.** Fixtures are multi-speaker throughout. Verified against the live API at 7/7 attribution (DR-013).

## DR-009 — Scope: exactly four event types

**Decision.** The MVP detects four and no more: contradiction, commitment drift, decision conflict, unresolved critical item. Two are implemented; two have fixtures proving the architecture generalises but no detectors.

**Rationale.** Detecting everything is how solo projects die.

## DR-010 — Claim discipline: no compliance, fraud or legal guarantees

**Decision.** Never claim those. The claim is *"detects conversational inconsistencies before they become decisions."* Then demonstrate it.

**Rationale.** Stronger claims import a validation burden that cannot be discharged, and invite exactly the attack a judge is best equipped to make. The weaker claim is both true and demonstrable.

## DR-011 — Do not pitch "the one that listens instead of answers"

**Context.** Early analysis framed "an agent that listens to humans talking to each other" as the differentiator. On closer inspection at least four projects in the same event shared it.

**Decision.** Pitch on the mechanism — temporal memory, detection of change, intervention before the outcome sets — not on scarcity.

**Rationale.** A pitch resting on "nobody else does this" can be destroyed by one late submission. A pitch resting on what the product *is* cannot.

## DR-012 — The engine is a reducer; the browser holds the memory

**Context.** Serverless functions are stateless and may cold-start per request. The detection layer needs memory of everything established earlier, and there is no database.

**Decision.** The engine's public entry point is a pure reducer, `step(memory, event, utterances) -> (memory, alerts)`. The **browser** owns the memory, serialises it, and posts it back with each call. A payload cap prunes oldest non-active events first; active events are never dropped, because losing one would silently disable detection.

**Rationale.** It is what makes "no database, no always-on server" true rather than aspirational. It also keeps `engine/` a pure function of its inputs, testable with no network and no API.

**Consequences.** Conversation state is client-side, so it is inspectable and forgeable — acceptable, because the evidence gate re-validates every proposal against the posted transcript. That purity later proved decisive (DR-015).

## DR-013 — Streaming STT with speaker labels, not the Voice Agent API

**Context.** A genuine architectural fork: Streaming STT with diarization, or the Voice Agent API alone if it exposed diarization.

**Decision.** **Streaming STT.** Verified against the live service on a temporary token, not merely documented:

| Item | Verified |
|---|---|
| Endpoint | `wss://streaming.assemblyai.com/v3/ws` |
| Audio | 16 kHz mono 16-bit PCM, `encoding=pcm_s16le` |
| Diarization | `speaker_labels=true`, `max_speakers=2`, on the browser token path |
| Attribution | **7 of 7 turns correct** on a two-voice conversation |

**Rationale.** Diarization on the browser token path is the whole DR-008 argument, now measured rather than assumed.

## DR-014 — Speaker labels are word-level, late, and revisable

**Context.** Discovered by actually streaming audio; none of it is on the documentation page.

**Decision.** Treat speaker attribution as **provisional until revised**.

1. Labels live on `words[].speaker`. The turn-level `speaker` field was `None` on every message.
2. Labels appear only on finalised turns. Partials carry no speaker at all.
3. `PENDING` is a real label value, and a `SpeakerRevision` message can retroactively reassign a turn — observed live.

**Rationale.** Fact 3 is the dangerous one. If a label is revised after an alert has fired, a displayed alert can become factually wrong — attributing a quote to the wrong person. That is precisely the failure the evidence gate exists to prevent, arriving through a door the gate did not watch.

**Consequences.** Led directly to DR-018 and DR-022.

## DR-015 — The LLM Gateway was inaccessible; extraction blocked

**Context.** The extraction layer had never been run against a live model.

**Findings.** The configured default model did not exist on the gateway. Every model in the 37-entry catalogue returned *"Your account does not have access to this LLM Gateway model"* on a plain request. The same API key minted streaming tokens and hit the core API successfully — only the gateway was locked.

**Decision.** Recorded as an account-entitlement blocker, **not worked around in code.**

**Rationale.** A workaround would have meant either routing around the schema constraint or hand-rolling a parser for unconstrained text — both of which attack DR-005's discipline to solve a billing problem.

**Consequences.** **The engine's purity (DR-012) is what stopped this being fatal.** Detection, the evidence gate and the full test suite were unaffected, and the UI was built against fixture output while the gateway was blocked.

## DR-016 — The spoken intervention is cut from the MVP

**Context.** A spoken "CLARIFY" intervention was to close perceive → remember → reason → intervene.

**Decision.** **Cut.** The alert card detects and cites; it does not speak. The time was reallocated to hardening replay.

**Rationale.** It would have added a voice-output path and a second unverified integration in the week with least slack — and DR-015 had just demonstrated how unverified integrations go. Decisively: the pitch does not need it. An evidence-cited alert firing live demonstrates the claim completely, and AssemblyAI's necessity is already carried by streaming and diarization.

**Consequences.** Narration must not promise a talking agent. Both implementation options remain open post-freeze; nothing is foreclosed.

## DR-017 — Gateway fallback, with a decision deadline

**Context.** DR-015 left extraction blocked with no ETA. A blocker with no deadline silently becomes a blocker that eats the schedule.

**Decision.** A fixed deadline, after which extraction switches to a **direct model-provider call** — no further debate. The switch is cheap by construction: one module touches a model, it speaks OpenAI-shaped chat completions, and it already refuses to let the model supply index, speaker or timestamp.

**Structured-output support is not a requirement.** Ask for JSON in the prompt, validate locally against the schema, and drop anything malformed before it reaches the engine. A model without it yields a **higher rejection rate, not a correctness hole** — because the evidence gate, not the model, is the correctness guarantee. That is the entire point of DR-005.

**Consequences.** The LLM is a component, not the product. Worth saying plainly.

## DR-018 — The gate applies over time, not just once

**Context.** DR-014 found that a revision can reassign a turn *after* an alert citing it has fired.

**Decision.** Two parts. The gate **rejects any evidence utterance whose speaker is `PENDING`** — an alert cannot rest on an unstable label. And when a revision touches a cited utterance, **re-run the gate on that alert**, withdrawing it visibly if it now fails.

**Rationale.** A withdrawn alert is honest. Quietly misattributing a quote is precisely what this project exists to prevent, and shipping it would be indefensible. Refined by DR-022.

## DR-019 — Turn normalisation sits outside the engine

**Context.** Live turn segmentation splits one spoken sentence across two finalised turns. Evidence quotes citing half a sentence are weak.

**Decision.** Normalisation between the websocket and the engine merges consecutive same-speaker turns separated by under a second. **It does not live in `engine/`.**

**Rationale.** The engine's independence from transport is the property that let the detection layer be built and tested while the API was unverified — and, per DR-015, while half of it was unusable. Transport-shaped cleanup is a transport concern.

## DR-020 — Replay is the primary demo path; live is the bonus

**Context.** Extraction was gateway-blocked, speaker labels can revise mid-session, and per-utterance latency against the function timeout was unmeasured.

**Decision.** **Replay is primary.** Live mic mode remains and demonstrates that realtime is genuine, but the demo does not depend on it.

**Rationale.** It sidesteps all three risks at once. Betting a scored deliverable on the least-verified component, in the week with no slack, is the wrong bet.

**Consequences.** DR-007's constraint still holds — audio still traverses the real websocket. What is precomputed is stated plainly; a judge reading a public repo will find it, and framing it as an engineering decision is fine, while pretending it is live is not.

## DR-021 — Speakers are `A` / `B`; no role inference

**Context.** Fixtures used role names. Live diarization returns `A` / `B`.

**Decision.** `A` / `B` everywhere, mapped by order of first appearance. No role assignment, no first-speaker heuristic.

**Rationale.** The system does not detect roles and must not look as though it does. A first-speaker heuristic is an unstated assumption that breaks whenever a customer opens the call. Nothing in the pitch depends on roles.

**Consequences.** Demo vividness drops, which is the price of the demo and the live mode being the same thing.

## DR-022 — Alert identity is derived, and revision is just another event

**Context.** DR-018 established *what* must happen on a revision but not *how*. Assigning IDs from a counter and handling revisions in a side channel would have put mutable state and a second control path into a package whose purity is load-bearing.

**Decision.** Three parts.

1. **Identity is derived from the evidence**, `sha256(event_type|earlier_index|later_index)`. No counter, no clock. The reducer stays pure, replay produces identical IDs on every run, and the same evidence pair can never fire twice — deduplication falls out of the identity.
2. **Lifecycle** `active → withdrawn | updated`. Withdrawn alerts are **kept, not deleted**, so the UI renders a visible correction.
3. **Revisions are fed through `step()`** like any other input. No new control path, and it becomes fixture-testable.

**Rationale.** Deriving identity from evidence is DR-005's principle again — the alert *is* its evidence, so two alerts with the same evidence are the same alert. An agent that publicly corrects itself when attribution moves is demonstrating the gate working.

**Two corrections made during implementation, kept here deliberately:**

- **`updated` could not be terminal.** The lifecycle as first written meant an updated alert was no longer active, so a relabelled alert could never subsequently be withdrawn. **Withdrawn is the only terminal state.** Caught by writing the third revision case into the fixture.
- **`hashlib`, not the builtin `hash()`.** Python salts string hashing per process, which would have broken replay determinism *silently* — the failure mode with no symptom until replay stopped reproducing.

## DR-023 — Commitment drift is deliberately **not** same-speaker

**Context.** DR-022 made contradiction same-speaker, so that a revision splitting its two cited turns across two people withdraws it. That left the rule for commitment drift unstated: the detector never filtered by speaker, and the only drift fixture happened to have both utterances from one speaker — so the behaviour was implicit in test data rather than declared in code.

**Decision.** Commitment drift is **explicitly cross-speaker**, declared alongside the same-speaker set, with an assertion that the two partition the implemented detectors exactly.

**Rationale.** Cross-speaker drift is the *higher-value* case, not a leak:

> **B:** "Friday is a hard deadline, Monday won't work."
> **A:** "We'll ship it Monday then."

Nobody contradicted themselves; one party quietly overrode a constraint the other set. Contradiction is different because its claim is specifically *"you reversed yourself"* — which evaporates the moment the two turns belong to different people. The alert is attributed to whoever moved, which is what makes it actionable.

**Consequences.** A cross-speaker drift alert survives a revision, updated rather than withdrawn, because it never claimed one speaker. The partition assertion means **any new detector must declare its rule or fail the test suite** — silence is not a default, which is exactly the gap that let this stay implicit.

## DR-024 — Live extraction measured: the gate holds, the extractor does not

**Context.** Until this point every passing test used hand-authored events. This is the first end-to-end measurement of the whole claim: real model output, through the evidence gate, to the right alerts.

**What gateway access actually meant.** Of 37 catalogued models, **exactly one was reachable**, and it does not support structured output. So the prompt-JSON + local-validation path from DR-017 was implemented not as a provider-switch contingency but because it was the only way to run extraction at all.

**Measured**

| Metric | Result |
|---|---|
| Model | 4B parameters, no structured output |
| Schema validity | **9/10 proposals validated (90%)**, 1 rejected locally |
| Latency, clean | **p50 ≈ 0.9–1.1 s** — comfortably inside the serverless limit |
| Rate limiting | **3–4 × HTTP 429 per short conversation** |
| Clean control | **PASS — zero alerts, zero false positives** |
| Commitment drift | **FAIL — no alert at all** |
| Contradiction | **FAIL — right type, wrong evidence pair** |

A measurement bug surfaced and was fixed: elapsed time spanned the retry loop, so backoff sleeps were being reported as model latency (an apparent p50 of 58 s). Restarting the clock per attempt exposed the true ~1 s figure. **The apparent latency problem was a rate-limit problem wearing a costume.**

**Diagnosed.** `"Yeah... I guess."` extracted **zero events** — the model did not recognise hedged acceptance as a commitment, and that single utterance is the entire flagship demo. Topic identifiers also drift between utterances, and the engine's collision detection depends on two statements sharing a topic string.

**Decision.** Record the results; do not paper over them. Extraction quality becomes the binding constraint and gets its own decision rather than a reflex fix.

**Rationale.** The result splits cleanly, and the split is the whole point:

- **The architecture held.** Local validation caught malformed output, latency was fine, and above all **the clean control produced zero alerts from real model output.** The false-positive guard survived contact with a weak model — the property DR-005 exists to protect.
- **The extractor did not.** A small model cannot reliably produce the proposals the engine needs.

This is the failure split the design was built for. The model is a proposer; a weak proposer yields *missed* alerts, not false ones. "Bias toward missing rather than false-alarming" stopped being a slogan and started being a measurement.

**Consequences.** The demo cannot currently run on live extraction, so replay with precomputed extraction becomes load-bearing rather than merely prudent. Rate limiting, not latency, is the real constraint on the token endpoint's design. Topic identity needs anchoring.

## DR-025 — Extraction timebox closed: drift is reliable, contradiction is a known limitation

**Context.** A timeboxed attempt to fix extraction, with **pass criteria fixed before running** rather than rationalised afterwards: clean control zero alerts 3/3 (hard requirement), commitment drift 3/3, contradiction ≥2/3 acceptable.

**What worked.** The flagship utterance `"Yeah... I guess."` extracted nothing, so drift never fired. The cause was **not** the context window, the topic vocabulary, or model size — all were already in place, and the model could see the question it was answering. Four variants were tested against the live model rather than reasoned about:

| Variant | Result |
|---|---|
| Baseline | nothing |
| Minus the "merely acknowledging" clause | nothing |
| **Baseline + explicit hedged-yes rule** | **commitment / monday / ambiguous=true** |

The model had the context and lacked the *rule*.

**What failed, and was reverted.** Contradiction fails because a rejection is extracted as `kind=commitment`, and that detector only fires on claim/preference/constraint. Sharpening the `kind` descriptions **made things worse**: contradiction stayed at 0/3, and drift *regressed* to firing a spurious second alert. Diagnosed rather than guessed — `"the quantity stays at two hundred units"` was being given the topic `delivery_date`, collapsing quantity into date, so the engine correctly flagged a drift from `friday` to `two_hundred_units`. **The engine did nothing wrong; the extractor handed it a false premise.** Reverted, and replaced with a narrower rule: reuse a topic only for the same subject, because a missed conflict costs one alert and a merged topic costs trust.

**Decision.** Contradiction is recorded as a **known limitation** — not fixed, not worked around.

**Explicitly rejected:** making contradiction fire on any same-speaker polarity reversal regardless of `kind`. That would change what the detector claims and erode the separation between detectors — bending the engine to fit a weak model. The engine is the part that works.

**Measured, final** (3 runs each): clean control **3/3 zero alerts**; commitment drift **3/3**; contradiction **0/3**; schema validity **33/33**; p50 ≈ 1.1 s.

**Rationale.** The failure mode is consistent with the whole design: a weak proposer produces *missed* alerts, never false ones. Across every configuration tried — including the one that regressed — the clean control never once produced a false positive.

**Consequences.** The demo page states these rates rather than showing a good run silently; publishing `contradiction 0/3` is evidence of discipline and matches the "misses, not false alarms" claim. The demo's events stay hand-authored, because regenerating from live extraction would silently drop the contradiction scenario, and the page says so plainly.

## DR-026 — Field survey: reframe the pitch, name the vertical, restore CLARIFY

**Context.** The full field was enumerated for the first time — **all 86 submissions**, after the live board proved to render only its top 10. **16 were read in full**, selected by overlap risk. Three earlier decisions rest on claims the field contradicts.

**DR-005, DR-010 and DR-016 are deliberately NOT edited.** They were right on what was known at the time, and rewriting them would destroy the trail that makes them worth reading. This record supersedes the specific claims below.

**1. Supersedes DR-005's "single strongest technical talking point."** Eight of the sixteen are built on citable or verifiable evidence — one mints an action credential only when *"every argument is grounded in a witness drawn from word-level transcript"*, returning `UNDECODABLE` rather than guessing; others use hash-chained tamper-evident records and append-only audits. **The gate stays exactly as built; only its role in the pitch changes** — it is the credibility layer, not the headline. What remains genuinely uncommon is **self-withdrawal**: an alert that retracts itself when attribution is revised (DR-022).

**2. Supersedes DR-010's candidate vertical.** Two submissions already occupy regulated sales / consent, both listening to advisor↔customer calls with live diarization and real-time correction. Entering it means being third — the DR-004 mistake repeated.

**New vertical: B2B order and deal negotiation** — where terms quietly change mid-call and operations then ships, invoices or quotes the wrong thing. Cost is concrete: disputes, rework, chargebacks.

**It required zero rework, because it was already there.** Verified across all six fixtures: topics are `delivery_date`, `quantity`, `premium_plan`, `extended_warranty`, `bulk_discount`, `payment_terms`, `final_price`, `platform_choice`; the language is *"leave it off the quote"*, *"check what the warehouse can do"*, *"confirm the final price with my manager"*. The vertical was chosen implicitly on day one and only named now. Decisively, it involves **no regulation and no compliance rulebook** — which is exactly what separates it from both competitors.

**3. Reverses DR-016 — CLARIFY returns.** DR-016 cut the spoken intervention, and was correct on the information available: the risk was schedule. The field survey is new information. In a *Voice Agent* hackathon **both closest competitors speak back**, while Throughline only listened and displayed — which risks reading as not a voice agent at all.

CLARIFY returns **minimal**: when an alert fires the agent speaks one short line — *"Earlier, Friday was a hard deadline. Is Monday confirmed?"* — via browser `speechSynthesis`, built **after** realtime wiring. DR-016's scope discipline carries over: one line, no dialogue, no turn-taking, no second integration.

**The reframed pitch.** Headline: *others check speech against a rulebook; Throughline checks a conversation against itself.* Credibility: every alert cites two real utterances and withdraws itself if attribution changes. Contrast: others catch hedged agreement by **prosody, in the moment**; we catch it **semantically, against something said twenty minutes earlier**.

**Rationale.** Across all sixteen read, **nobody detects conflict between what a conversation established earlier and what it does later** — one competitor names that exact gap as its own stated limitation. Temporal memory is the differentiator; the gate is what makes it trustworthy.

**Consequences.** README, deck and video lead with temporal memory, not the evidence gate. 61 drafts remain hidden, so this supports no whitespace claim — only that the lane was open among the 16 read.
