"""The evidence gate (DR-005).

A detector proposes a conflict. This module is the only thing that can turn a
proposal into an Alert, and it refuses unless the proposal points at two real,
distinct, correctly-ordered utterances in the actual transcript.

No citable evidence, no alert. The agent never invents the reason it intervened.
"""

import hashlib

from .models import PENDING, Alert, EvidenceRef, Utterance


class EvidenceError(Exception):
    """Raised only by `explain`; `gate` returns None instead."""


def alert_id(event_type: str, earlier_index: int, later_index: int) -> str:
    """Identity derived from the evidence, not assigned (DR-022).

    An alert *is* its evidence, so the same evidence pair is the same alert.
    That gives free deduplication and, because nothing here depends on a counter
    or a clock, replay produces identical ids on every run.

    `hashlib`, not the builtin `hash()`: Python salts string hashing per process,
    which would silently break that determinism across runs.
    """
    key = f"{event_type}|{earlier_index}|{later_index}".encode()
    return hashlib.sha256(key).hexdigest()[:12]


def gate(
    event_type: str,
    speaker: str,
    earlier_index: int,
    later_index: int,
    confidence: float,
    summary: str,
    utterances: list[Utterance],
) -> Alert | None:
    """Return an Alert, or None if the proposal cannot justify itself."""
    try:
        return explain(
            event_type, speaker, earlier_index, later_index,
            confidence, summary, utterances,
        )
    except EvidenceError:
        return None


def explain(
    event_type: str,
    speaker: str,
    earlier_index: int,
    later_index: int,
    confidence: float,
    summary: str,
    utterances: list[Utterance],
) -> Alert:
    """Same as `gate` but raises with the reason - used by tests."""
    if not event_type:
        raise EvidenceError("no event_type")
    if not speaker:
        raise EvidenceError("no speaker")
    if earlier_index == later_index:
        raise EvidenceError("evidence must be two distinct utterances")
    if not 0.0 < confidence <= 1.0:
        raise EvidenceError(f"confidence {confidence} out of range")

    by_index = {u.index: u for u in utterances}
    earlier = by_index.get(earlier_index)
    later = by_index.get(later_index)
    if earlier is None or later is None:
        raise EvidenceError("evidence does not resolve to a real utterance")
    if earlier.t_ms >= later.t_ms:
        raise EvidenceError("evidence is not in chronological order")
    if not earlier.text.strip() or not later.text.strip():
        raise EvidenceError("evidence utterance is empty")
    if PENDING in (earlier.speaker, later.speaker):
        raise EvidenceError("evidence speaker is unresolved (PENDING)")

    return Alert(
        event_type=event_type,
        speaker=speaker,
        t_ms=later.t_ms,
        evidence_1=EvidenceRef.of(earlier),
        evidence_2=EvidenceRef.of(later),
        confidence=round(confidence, 2),
        summary=summary,
        id=alert_id(event_type, earlier_index, later_index),
    )
