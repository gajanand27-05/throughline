import pytest
from conftest import load, mvp_fixture_names

from engine import POST_MVP, run
from engine.conflicts import _decision_conflict, _unresolved_item


def check(name):
    data, utterances, events = load(name)
    _, alerts = run(utterances, events)
    return data, alerts


@pytest.mark.parametrize("name", mvp_fixture_names())
def test_mvp_fixture_matches_expectation(name):
    data, alerts = check(name)
    expected = data["expected_alerts"]

    assert len(alerts) == len(expected), (
        f"{name}: expected {len(expected)} alert(s), got {len(alerts)}: "
        f"{[a.event_type for a in alerts]}"
    )
    for got, want in zip(alerts, expected):
        assert got.event_type == want["event_type"]
        assert got.speaker == want["speaker"]
        assert [got.evidence_1.utterance_index, got.evidence_2.utterance_index] == \
            want["evidence_indices"]
        assert got.confidence >= want["min_confidence"]


def test_clean_control_produces_zero_alerts():
    """The false-positive guard (DR-010). This failing is worse than any
    positive fixture failing."""
    _, alerts = check("clean_control")
    assert alerts == [], (
        "clean control must be silent; fired: "
        + ", ".join(f"{a.event_type}@{a.evidence_2.utterance_index}" for a in alerts)
    )


def test_explicit_revision_is_not_a_contradiction():
    """Someone openly changing their mind is healthy, not a conflict."""
    _, alerts = check("clean_control")
    assert not any(a.event_type == "contradiction" for a in alerts)


def test_disagreement_between_speakers_is_not_self_contradiction():
    """Two speakers holding opposite views is disagreement (DR-008)."""
    data, alerts = check("clean_control")
    assert not any(a.speaker == "AGENT" for a in alerts)


def test_drift_confidence_rises_with_ambiguous_acceptance():
    """A hesitant 'yeah... I guess' to a changed term is the signal, not noise."""
    _, alerts = check("commitment_drift")
    assert alerts[0].confidence >= 0.9


def test_drift_does_not_fire_across_topics():
    """quantity and delivery_date both carry values; only one may conflict."""
    _, alerts = check("commitment_drift")
    assert len(alerts) == 1
    assert alerts[0].summary.count("delivery_date") == 1


@pytest.mark.parametrize("detector", [_decision_conflict, _unresolved_item])
def test_post_mvp_detectors_are_declared_but_not_built(detector):
    """DR-009 keeps the MVP at two event types. Their fixtures exist to prove
    the architecture; the detectors are deliberately absent."""
    with pytest.raises(NotImplementedError):
        detector()


@pytest.mark.parametrize("name", ["decision_conflict", "unresolved_item"])
def test_post_mvp_fixtures_are_silent_under_mvp_detectors(name):
    _, alerts = check(name)
    assert alerts == [], f"{name} is post-MVP and must not fire yet"
    assert name in POST_MVP
