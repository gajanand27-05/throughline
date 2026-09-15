"""Data shapes for the integrity engine.

Pure data. No network, no audio, no LLM. See DR-005: the LLM proposes
Events; this engine decides whether a proposal survives into an Alert.
"""

from dataclasses import dataclass
from enum import Enum


class Kind(str, Enum):
    CLAIM = "claim"
    COMMITMENT = "commitment"
    DECISION = "decision"
    CONSTRAINT = "constraint"
    PREFERENCE = "preference"


class Status(str, Enum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    RESOLVED = "resolved"


@dataclass(frozen=True)
class Utterance:
    """One speaker-attributed turn from the transcript."""

    index: int
    speaker: str
    t_ms: int
    text: str

    @staticmethod
    def from_dict(d):
        return Utterance(d["index"], d["speaker"], d["t_ms"], d["text"])


@dataclass(frozen=True)
class Event:
    """What extraction proposes about an utterance.

    In production an LLM produces these. In tests the fixture supplies them,
    which is what keeps this package free of network and model dependencies.
    """

    kind: Kind
    speaker: str
    utterance_index: int
    t_ms: int
    topic: str
    text: str = ""
    value: str | None = None  # e.g. "friday" - the thing committed to
    polarity: bool = True  # True = affirms, False = negates
    ambiguous: bool = False  # "yeah... I guess"
    explicit_revision: bool = False  # speaker openly changed their position

    @staticmethod
    def from_dict(d):
        return Event(
            kind=Kind(d["kind"]),
            speaker=d["speaker"],
            utterance_index=d["utterance_index"],
            t_ms=d["t_ms"],
            topic=d["topic"],
            text=d.get("text", ""),
            value=d.get("value"),
            polarity=d.get("polarity", True),
            ambiguous=d.get("ambiguous", False),
            explicit_revision=d.get("explicit_revision", False),
        )


@dataclass(frozen=True)
class EvidenceRef:
    """A pointer back into the transcript. An alert that cannot produce two
    of these does not exist (DR-005)."""

    utterance_index: int
    speaker: str
    t_ms: int
    text: str

    @staticmethod
    def of(u: Utterance):
        return EvidenceRef(u.index, u.speaker, u.t_ms, u.text)

    def to_dict(self):
        return {
            "utterance_index": self.utterance_index,
            "speaker": self.speaker,
            "t_ms": self.t_ms,
            "text": self.text,
        }


@dataclass(frozen=True)
class Alert:
    event_type: str
    speaker: str
    t_ms: int
    evidence_1: EvidenceRef
    evidence_2: EvidenceRef
    confidence: float
    summary: str

    def to_dict(self):
        return {
            "event_type": self.event_type,
            "speaker": self.speaker,
            "t_ms": self.t_ms,
            "evidence_1": self.evidence_1.to_dict(),
            "evidence_2": self.evidence_2.to_dict(),
            "confidence": self.confidence,
            "summary": self.summary,
        }
