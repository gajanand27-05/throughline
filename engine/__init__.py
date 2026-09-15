"""Throughline integrity engine.

Pure logic: no network, no audio, no model calls. That is a hard property, not
a convention - it is what lets the whole engine be tested with zero credits and
zero working API (see the plan, steps 1-3).

The public entry point is a reducer (DR-012):

    memory', alerts = step(memory, event, utterances)

which the browser folds over the conversation, holding `memory` itself so the
serverless functions can stay stateless.
"""

from .conflicts import MVP, POST_MVP, detect
from .evidence import EvidenceError, gate
from .memory import Memory
from .models import Alert, EvidenceRef, Event, Kind, Status, Utterance

__all__ = [
    "Alert", "EvidenceError", "EvidenceRef", "Event", "Kind", "Memory",
    "Status", "Utterance", "MVP", "POST_MVP", "detect", "gate", "step", "run",
]


def step(memory: Memory, event: Event, utterances: list[Utterance]):
    """One reduction. Detect against prior memory, then record the event."""
    alerts = detect(memory, event, utterances)
    memory.apply(event)
    return memory, alerts


def run(utterances: list[Utterance], events: list[Event]):
    """Fold a whole conversation. Used by the fixtures and by replay."""
    memory, alerts = Memory(), []
    for event in events:
        _, new = step(memory, event, utterances)
        alerts.extend(new)
    return memory, alerts
