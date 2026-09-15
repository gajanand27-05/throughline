"""The gate is the project's main technical claim (DR-005). These tests are the
proof that an alert cannot exist without citable evidence."""

import pytest
from conftest import load

from engine import Utterance, gate
from engine.evidence import EvidenceError, explain

U = [
    Utterance(0, "A", 1000, "Friday is a hard deadline."),
    Utterance(1, "B", 5000, "So Monday works?"),
    Utterance(2, "A", 7000, "Yeah... I guess."),
    Utterance(3, "A", 9000, "   "),
]


def ok(**over):
    kw = dict(
        event_type="commitment_drift", speaker="A", earlier_index=0, later_index=2,
        confidence=0.94, summary="drift", utterances=U,
    )
    kw.update(over)
    return kw


def test_valid_proposal_produces_an_alert_with_two_citations():
    alert = gate(**ok())
    assert alert is not None
    assert alert.evidence_1.utterance_index == 0
    assert alert.evidence_2.utterance_index == 2
    assert alert.evidence_1.text == "Friday is a hard deadline."
    assert alert.t_ms == 7000, "alert is stamped at the later utterance"
    assert alert.confidence == 0.94


@pytest.mark.parametrize(
    "bad,reason",
    [
        (dict(earlier_index=2, later_index=2), "two distinct"),
        (dict(earlier_index=2, later_index=0), "chronological"),
        (dict(earlier_index=99), "real utterance"),
        (dict(later_index=99), "real utterance"),
        (dict(confidence=0.0), "out of range"),
        (dict(confidence=1.5), "out of range"),
        (dict(confidence=-0.5), "out of range"),
        (dict(speaker=""), "no speaker"),
        (dict(event_type=""), "no event_type"),
        (dict(later_index=3), "empty"),
    ],
)
def test_gate_refuses_unjustified_proposals(bad, reason):
    assert gate(**ok(**bad)) is None, f"gate should have refused: {reason}"
    with pytest.raises(EvidenceError, match=reason):
        explain(**ok(**bad))


def test_every_alert_from_every_mvp_fixture_carries_full_evidence():
    """No alert anywhere may lack any required field."""
    from engine import run

    for name in ("contradiction", "commitment_drift", "clean_control"):
        _, utterances, events = load(name)
        _, alerts = run(utterances, events)
        by_index = {u.index: u for u in utterances}
        for a in alerts:
            assert a.event_type and a.speaker
            assert 0.0 < a.confidence <= 1.0
            assert a.evidence_1.utterance_index != a.evidence_2.utterance_index
            assert a.evidence_1.t_ms < a.evidence_2.t_ms
            for ref in (a.evidence_1, a.evidence_2):
                assert ref.text == by_index[ref.utterance_index].text, (
                    "evidence text must match the real transcript, not a paraphrase"
                )
