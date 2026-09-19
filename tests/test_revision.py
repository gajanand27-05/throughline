"""Speaker revision: the gate applied over time (DR-018, DR-022).

An alert that has already fired is not settled. If diarization later reassigns a
cited utterance, the alert must be re-checked and withdrawn if it no longer
holds - misattributing a quote is precisely the failure this project claims to
prevent, so shipping it would be indefensible.
"""

import json
from pathlib import Path

import pytest

from engine import (
    MVP, PENDING, AlertStatus, Event, Memory, Revision, Utterance, alert_id, run, step,
)
from engine.conflicts import CROSS_SPEAKER, SAME_SPEAKER

FIXTURE = Path(__file__).parent.parent / "fixtures" / "speaker_revision.json"


@pytest.fixture
def data():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _load(data):
    return (
        [Utterance.from_dict(u) for u in data["utterances"]],
        [Event.from_dict(e) for e in data["events"]],
    )


def _by_evidence(alerts, pair):
    return next(
        a for a in alerts
        if [a.evidence_1.utterance_index, a.evidence_2.utterance_index] == pair
    )


# --- identity is derived, not assigned ---------------------------------------

def test_alert_id_is_deterministic_across_processes():
    """Not Python's builtin hash(): it is salted per process, which would break
    replay determinism silently."""
    assert alert_id("contradiction", 1, 3) == alert_id("contradiction", 1, 3)
    assert alert_id("contradiction", 1, 3) != alert_id("commitment_drift", 1, 3)
    assert alert_id("contradiction", 1, 3) != alert_id("contradiction", 1, 4)
    # Pinned: a change here silently breaks replay id stability.
    assert alert_id("contradiction", 1, 3) == "8230081780dc"


def test_replay_produces_identical_ids(data):
    utterances, events = _load(data)
    first = [a.id for a in run(utterances, events)[1]]
    second = [a.id for a in run(utterances, events)[1]]
    assert first == second and all(first)


def test_same_evidence_pair_cannot_fire_twice(data):
    utterances, events = _load(data)
    memory = Memory()
    _, first = step(memory, events[0], utterances)
    _, second = step(memory, events[1], utterances)
    assert len(second) == 1
    # Replaying the same event yields no new alert - dedup falls out of identity.
    _, again = step(memory, events[1], utterances)
    assert again == []
    assert len(memory.alerts()) == 1


# --- the lifecycle ------------------------------------------------------------

def test_fixture_alerts_fire_before_any_revision(data):
    utterances, events = _load(data)
    _, alerts = run(utterances, events)
    assert len(alerts) == len(data["expected_alerts"])
    assert all(a.status is AlertStatus.ACTIVE for a in alerts)


def test_revision_withdraws_a_contradiction_across_two_speakers(data):
    """Two people disagreeing is not one person contradicting themselves."""
    utterances, events = _load(data)
    rev = Revision.from_dict(data["revisions"][0])
    _, alerts = run(utterances, events + [rev])

    withdrawn = _by_evidence(alerts, [1, 3])
    assert withdrawn.status is AlertStatus.WITHDRAWN
    # Kept, not deleted - the UI shows a visible correction.
    assert withdrawn in alerts
    # The unrelated alert is untouched.
    assert _by_evidence(alerts, [4, 6]).status is AlertStatus.ACTIVE


def test_revision_updates_an_alert_that_still_holds(data):
    """Commitment drift makes no same-speaker claim, so it survives relabelling."""
    utterances, events = _load(data)
    rev = Revision.from_dict(data["revisions"][1])
    _, alerts = run(utterances, events + [rev])

    updated = _by_evidence(alerts, [4, 6])
    assert updated.status is AlertStatus.UPDATED
    assert updated.evidence_2.speaker == "C"
    assert updated.speaker == "C"


def test_identity_survives_the_lifecycle(data):
    """The id is derived from the evidence, so relabelling never re-keys it."""
    utterances, events = _load(data)
    before = _by_evidence(run(utterances, events)[1], [4, 6])
    after = _by_evidence(
        run(utterances, events + [Revision.from_dict(data["revisions"][1])])[1], [4, 6]
    )
    assert before.id == after.id


def test_updated_alert_is_still_revisable(data):
    """An updated alert is still on screen, so withdrawal must still reach it."""
    utterances, events = _load(data)
    revs = [Revision.from_dict(r) for r in data["revisions"][1:3]]
    _, alerts = run(utterances, events + revs)
    assert _by_evidence(alerts, [4, 6]).status is AlertStatus.WITHDRAWN


def test_full_fixture_matches_declared_expectations(data):
    """Walk every declared revision in order and check each stated outcome."""
    utterances, events = _load(data)
    items = list(events)
    for spec in data["revisions"]:
        items.append(Revision.from_dict(spec))
        _, alerts = run(utterances, items)
        for want in spec["expect"]:
            got = _by_evidence(alerts, want["evidence_indices"])
            assert got.status.value == want["status"], spec["why"]
            if "speaker" in want:
                assert got.speaker == want["speaker"]


# --- every detector declares its speaker rule (DR-023) ------------------------

def test_speaker_rule_is_declared_for_every_detector():
    """A new detector must choose. Silence is not a default."""
    assert SAME_SPEAKER | CROSS_SPEAKER == frozenset(MVP)
    assert not (SAME_SPEAKER & CROSS_SPEAKER)


def test_commitment_drift_fires_across_speakers():
    """One party overriding a constraint the other set is the higher-value case,
    not a leak. Requiring a single speaker would discard it."""
    utterances = [
        Utterance(0, "B", 18000, "Friday is a hard deadline, Monday won't work."),
        Utterance(1, "A", 95000, "We'll ship it Monday then."),
    ]
    events = [
        Event.from_dict({"kind": "constraint", "speaker": "B", "utterance_index": 0,
                         "t_ms": 18000, "topic": "delivery_date", "value": "friday"}),
        Event.from_dict({"kind": "commitment", "speaker": "A", "utterance_index": 1,
                         "t_ms": 95000, "topic": "delivery_date", "value": "monday"}),
    ]
    _, alerts = run(utterances, events)
    assert len(alerts) == 1
    assert alerts[0].event_type == "commitment_drift"
    # Attributed to whoever moved, which is the agent here.
    assert alerts[0].speaker == "A"
    assert alerts[0].evidence_1.speaker == "B"


def test_cross_speaker_drift_survives_a_revision():
    """Relabelling must not withdraw an alert that never claimed one speaker."""
    utterances = [
        Utterance(0, "B", 18000, "Friday is a hard deadline, Monday won't work."),
        Utterance(1, "A", 95000, "We'll ship it Monday then."),
    ]
    events = [
        Event.from_dict({"kind": "constraint", "speaker": "B", "utterance_index": 0,
                         "t_ms": 18000, "topic": "delivery_date", "value": "friday"}),
        Event.from_dict({"kind": "commitment", "speaker": "A", "utterance_index": 1,
                         "t_ms": 95000, "topic": "delivery_date", "value": "monday"}),
    ]
    _, alerts = run(utterances, events + [Revision.of({1: "C"})])
    assert alerts[0].status is AlertStatus.UPDATED
    assert alerts[0].speaker == "C"


# --- PENDING is inadmissible --------------------------------------------------

def test_pending_speaker_never_produces_an_alert():
    """A conflict cannot be attributed to nobody (DR-018)."""
    utterances = [
        Utterance(0, PENDING, 1000, "Friday is a hard deadline."),
        Utterance(1, "B", 9000, "Yeah... I guess."),
    ]
    events = [
        Event.from_dict({"kind": "constraint", "speaker": PENDING, "utterance_index": 0,
                         "t_ms": 1000, "topic": "delivery_date", "value": "friday"}),
        Event.from_dict({"kind": "commitment", "speaker": "B", "utterance_index": 1,
                         "t_ms": 9000, "topic": "delivery_date", "value": "monday",
                         "ambiguous": True}),
    ]
    _, alerts = run(utterances, events)
    assert alerts == []


def test_revision_to_pending_withdraws(data):
    utterances, events = _load(data)
    _, alerts = run(utterances, events + [Revision.of({6: PENDING})])
    assert _by_evidence(alerts, [4, 6]).status is AlertStatus.WITHDRAWN


# --- the browser round-trip still works (DR-012) ------------------------------

def test_alerts_survive_serialisation(data):
    utterances, events = _load(data)
    memory, _ = run(utterances, events + [Revision.from_dict(data["revisions"][0])])
    restored = Memory.from_dict(json.loads(json.dumps(memory.to_dict())))

    before = {a.id: (a.status, a.speaker) for a in memory.alerts()}
    after = {a.id: (a.status, a.speaker) for a in restored.alerts()}
    assert before == after
