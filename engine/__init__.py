"""Throughline integrity engine.

Pure logic: no network, no audio, no model calls. That is a hard property, not
a convention - it is what lets the whole engine be tested with zero credits and
zero working API (see the plan, steps 1-3).

The public entry point is a reducer (DR-012):

    memory', alerts = step(memory, event, utterances)

which the browser folds over the conversation, holding `memory` itself so the
serverless functions can stay stateless.
"""

from dataclasses import replace

from .conflicts import MVP, POST_MVP, detect, revalidate
from .evidence import EvidenceError, alert_id, gate
from .memory import Memory
from .models import (
    PENDING, Alert, AlertStatus, EvidenceRef, Event, Kind, Revision, Status, Utterance,
)

__all__ = [
    "Alert", "AlertStatus", "EvidenceError", "EvidenceRef", "Event", "Kind",
    "Memory", "PENDING", "Revision", "Status", "Utterance", "MVP", "POST_MVP",
    "alert_id", "detect", "gate", "revalidate", "step", "run",
]


def step(memory: Memory, item, utterances: list[Utterance]):
    """One reduction. Returns (memory, alerts changed by this step).

    `item` is an Event, or a Revision when diarization has changed its mind
    (DR-022). Both go through the same door: revision handling is not a second
    control path bolted onto the side.
    """
    if isinstance(item, Revision):
        return memory, _revise(memory, item, utterances)

    alerts = detect(memory, item, utterances)
    memory.apply(item)
    # Derived identity makes this dedup free: the same evidence pair is the
    # same alert and can never fire twice.
    return memory, [a for a in alerts if memory.record_alert(a)]


def _revise(memory: Memory, revision: Revision, utterances: list[Utterance]):
    """Relabel, then re-run the gate on every active alert that cited a changed
    utterance. An alert whose evidence no longer supports it is withdrawn."""
    mapping = revision.as_map()
    memory.relabel(mapping)

    changed = []
    for alert in memory.alerts(live_only=True):
        cited = {alert.evidence_1.utterance_index, alert.evidence_2.utterance_index}
        if cited.isdisjoint(mapping):
            continue
        fresh = revalidate(alert, utterances)
        if fresh is None:
            changed.append(memory.set_alert(alert, AlertStatus.WITHDRAWN))
        elif (fresh.evidence_1.speaker != alert.evidence_1.speaker
              or fresh.evidence_2.speaker != alert.evidence_2.speaker):
            changed.append(memory.set_alert(fresh, AlertStatus.UPDATED))
    return changed


def run(utterances: list[Utterance], items):
    """Fold a whole conversation. Used by the fixtures and by replay.

    Returns (memory, all alerts in their final state) - including withdrawn
    ones, because a withdrawal is a result, not an absence.
    """
    memory = Memory()
    current = list(utterances)
    for item in items:
        if isinstance(item, Revision):
            # The transcript layer applies the revision, then tells the engine.
            mapping = item.as_map()
            current = [
                replace(u, speaker=mapping.get(u.index, u.speaker)) for u in current
            ]
        step(memory, item, current)
    return memory, memory.alerts()
