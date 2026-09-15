from conftest import load

from engine import Kind, Memory, Status
from engine.memory import MAX_EVENTS
from engine.models import Event


def test_apply_records_event_as_active():
    m = Memory()
    e = Event(Kind.CLAIM, "A", 0, 1000, "topic_x")
    m.apply(e)
    assert m.active(topic="topic_x") == [e]


def test_explicit_revision_supersedes_same_speaker_same_topic():
    m = Memory()
    first = Event(Kind.PREFERENCE, "A", 0, 1000, "warranty", polarity=False)
    revised = Event(Kind.PREFERENCE, "A", 1, 2000, "warranty", polarity=True,
                    explicit_revision=True)
    m.apply(first)
    m.apply(revised)
    active = m.active(topic="warranty")
    assert active == [revised], "the superseded position must no longer be active"


def test_revision_does_not_supersede_other_speakers():
    m = Memory()
    theirs = Event(Kind.PREFERENCE, "B", 0, 1000, "warranty", polarity=False)
    mine = Event(Kind.PREFERENCE, "A", 1, 2000, "warranty", polarity=True,
                 explicit_revision=True)
    m.apply(theirs)
    m.apply(mine)
    assert theirs in m.active(topic="warranty")


def test_revision_does_not_supersede_other_topics():
    m = Memory()
    other = Event(Kind.COMMITMENT, "A", 0, 1000, "delivery_date", value="friday")
    revision = Event(Kind.PREFERENCE, "A", 1, 2000, "warranty", polarity=True,
                     explicit_revision=True)
    m.apply(other)
    m.apply(revision)
    assert other in m.active(topic="delivery_date")


def test_filters_compose():
    m = Memory()
    m.apply(Event(Kind.COMMITMENT, "A", 0, 1000, "t", value="x"))
    m.apply(Event(Kind.CLAIM, "B", 1, 2000, "t"))
    assert len(m.active(topic="t")) == 2
    assert len(m.active(topic="t", speaker="A")) == 1
    assert len(m.active(topic="t", kind=Kind.CLAIM)) == 1


def test_prune_never_drops_active_events():
    """The payload cap must not silently disable detection (DR-012)."""
    m = Memory()
    for i in range(MAX_EVENTS + 50):
        m.apply(Event(Kind.CLAIM, "A", i, i * 10 + 1, f"topic_{i}"))
    assert len(m.active()) == MAX_EVENTS + 50, "active events must survive pruning"


def test_round_trips_through_dict():
    """The browser holds this state and posts it back (DR-012)."""
    _, _, events = load("commitment_drift")
    m = Memory()
    for e in events:
        m.apply(e)
    restored = Memory.from_dict(m.to_dict())
    assert [e.topic for e in restored.all_events()] == [e.topic for e in m.all_events()]
    assert len(restored.active()) == len(m.active())


def test_resolve_marks_topic_resolved():
    m = Memory()
    m.apply(Event(Kind.COMMITMENT, "A", 0, 1000, "final_price", value="deferred"))
    m.resolve("final_price")
    assert m.active(topic="final_price") == []
    assert len(m.all_events()) == 1, "resolved events are retained, not deleted"
