"""The four detectors. Two are MVP (DR-009); two are declared but not built.

Every detector is a pure function of (Memory, new Event, transcript) and must
route its proposal through evidence.gate - nothing else may construct an Alert.
"""

from .evidence import gate
from .memory import Memory
from .models import Event, Kind, Utterance

MVP = ("contradiction", "commitment_drift")
POST_MVP = ("decision_conflict", "unresolved_item")

#: Event types whose claim only holds if both cited utterances are the same
#: speaker. Contradiction means "you reversed yourself" - if diarization later
#: splits those two turns across two people, there is no contradiction, just two
#: people disagreeing, which is normal conversation.
SAME_SPEAKER = frozenset({"contradiction"})

#: Event types that are deliberately NOT same-speaker (DR-023). Commitment drift
#: across speakers is the higher-value case, not a leak: one party quietly
#: overriding a constraint the other party set is the whole point. "Friday is a
#: hard deadline" (B) ... "We'll ship Monday" (A) is a real drift, and requiring
#: one speaker would discard it.
CROSS_SPEAKER = frozenset({"commitment_drift"})

# Every detector must declare which it is. A new detector that forgets to
# choose fails test_speaker_rule_is_declared_for_every_detector rather than
# silently inheriting whichever behaviour the code happens to have.
assert SAME_SPEAKER | CROSS_SPEAKER == frozenset(MVP)


def revalidate(alert, utterances):
    """Re-run the gate on an existing alert against a relabelled transcript.

    Returns a fresh Alert (same id, current speakers) if the alert still stands,
    or None if it must be withdrawn. This is DR-005 applied over time: evidence
    that stops supporting the claim stops being an alert.
    """
    by_index = {u.index: u for u in utterances}
    earlier = by_index.get(alert.evidence_1.utterance_index)
    later = by_index.get(alert.evidence_2.utterance_index)
    if earlier is None or later is None:
        return None
    if alert.event_type in SAME_SPEAKER and earlier.speaker != later.speaker:
        return None
    return gate(
        event_type=alert.event_type,
        speaker=later.speaker,
        earlier_index=earlier.index,
        later_index=later.index,
        confidence=alert.confidence,
        summary=alert.summary,
        utterances=utterances,
    )


def detect(memory: Memory, event: Event, utterances: list[Utterance]) -> list:
    """Run the MVP detectors against one newly extracted event.

    Returns alerts that survived the evidence gate. Order is stable.
    """
    alerts = []
    for detector in (_contradiction, _commitment_drift):
        alert = detector(memory, event, utterances)
        if alert is not None:
            alerts.append(alert)
    return alerts


def _contradiction(memory: Memory, event: Event, utterances) -> object:
    """Same speaker, same topic, opposite polarity, no explicit revision.

    "I don't need the premium plan." ... "We need the premium plan."
    """
    if event.kind not in (Kind.CLAIM, Kind.PREFERENCE, Kind.CONSTRAINT):
        return None
    if event.explicit_revision:
        return None  # they said they were changing their mind; that is not a contradiction

    for prior in memory.active(topic=event.topic, speaker=event.speaker):
        if prior.utterance_index == event.utterance_index:
            continue
        if prior.polarity == event.polarity:
            continue

        confidence = 0.9
        if prior.ambiguous or event.ambiguous:
            confidence -= 0.15

        return gate(
            event_type="contradiction",
            speaker=event.speaker,
            earlier_index=prior.utterance_index,
            later_index=event.utterance_index,
            confidence=confidence,
            summary=(
                f"Earlier position on '{event.topic}' was "
                f"{'affirmed' if prior.polarity else 'denied'}; "
                f"now {'affirmed' if event.polarity else 'denied'}."
            ),
            utterances=utterances,
        )
    return None


def _commitment_drift(memory: Memory, event: Event, utterances) -> object:
    """A standing commitment has a value; the conversation moves to a different
    value without anyone explicitly revising it.

    "Friday is a hard deadline." ... "So Monday works?" ... "Yeah... I guess."

    Ambiguity raises confidence rather than lowering it: a hesitant acceptance
    of a changed term is precisely the signal, not noise.
    """
    if event.value is None or event.explicit_revision:
        return None

    for prior in memory.active(topic=event.topic):
        if prior.kind not in (Kind.COMMITMENT, Kind.CONSTRAINT):
            continue
        if prior.value is None or prior.value == event.value:
            continue
        if prior.utterance_index == event.utterance_index:
            continue

        confidence = 0.85
        if event.ambiguous:
            confidence += 0.09

        return gate(
            event_type="commitment_drift",
            speaker=event.speaker,
            earlier_index=prior.utterance_index,
            later_index=event.utterance_index,
            confidence=confidence,
            summary=(
                f"Earlier commitment on '{event.topic}' was '{prior.value}'; "
                f"current statement moves to '{event.value}'"
                + (" with ambiguous acceptance." if event.ambiguous else ".")
            ),
            utterances=utterances,
        )
    return None


# --- Declared, deliberately not implemented (DR-009) -------------------------
# Fixtures exist for both so the architecture is proven against them, but
# building them now would expand the MVP surface. Post-freeze work.

def _decision_conflict(*_args, **_kwargs):
    raise NotImplementedError("post-MVP (DR-009)")


def _unresolved_item(*_args, **_kwargs):
    raise NotImplementedError("post-MVP (DR-009)")
