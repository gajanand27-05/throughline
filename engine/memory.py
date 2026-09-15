"""Temporal memory: what has been established so far, and what is still standing.

The browser holds this state and posts it back with each new utterance (DR-012),
so Memory must be cheap to serialise and must never grow without bound.
"""

from .models import Event, Kind, Status

MAX_EVENTS = 200  # payload cap (DR-012); oldest resolved events pruned first


class Memory:
    def __init__(self, events=None):
        # (Event, Status) pairs, in the order they were established
        self._rows: list[list] = [[e, Status.ACTIVE] for e in (events or [])]

    def apply(self, event: Event) -> None:
        """Record a new event, superseding any it explicitly revises."""
        if event.explicit_revision:
            for row in self._rows:
                prior, status = row
                if (
                    status is Status.ACTIVE
                    and prior.topic == event.topic
                    and prior.speaker == event.speaker
                ):
                    row[1] = Status.SUPERSEDED
        self._rows.append([event, Status.ACTIVE])
        self._prune()

    def active(self, kind: Kind = None, topic: str = None, speaker: str = None):
        out = []
        for event, status in self._rows:
            if status is not Status.ACTIVE:
                continue
            if kind is not None and event.kind is not kind:
                continue
            if topic is not None and event.topic != topic:
                continue
            if speaker is not None and event.speaker != speaker:
                continue
            out.append(event)
        return out

    def resolve(self, topic: str) -> None:
        for row in self._rows:
            if row[0].topic == topic:
                row[1] = Status.RESOLVED

    def all_events(self):
        return [event for event, _ in self._rows]

    def _prune(self):
        """Drop oldest non-active events once over the cap. Active events are
        never dropped - losing one would silently disable detection."""
        if len(self._rows) <= MAX_EVENTS:
            return
        keep, dropped = [], 0
        over = len(self._rows) - MAX_EVENTS
        for row in self._rows:
            if dropped < over and row[1] is not Status.ACTIVE:
                dropped += 1
                continue
            keep.append(row)
        self._rows = keep

    # --- serialisation: the browser round-trips this ---

    def to_dict(self):
        return {
            "events": [
                {
                    "kind": e.kind.value,
                    "speaker": e.speaker,
                    "utterance_index": e.utterance_index,
                    "t_ms": e.t_ms,
                    "topic": e.topic,
                    "text": e.text,
                    "value": e.value,
                    "polarity": e.polarity,
                    "ambiguous": e.ambiguous,
                    "explicit_revision": e.explicit_revision,
                    "status": s.value,
                }
                for e, s in self._rows
            ]
        }

    @staticmethod
    def from_dict(d):
        m = Memory()
        for row in d.get("events", []):
            m._rows.append([Event.from_dict(row), Status(row.get("status", "active"))])
        return m
