"""Offline tests for the extraction layer. No API calls, no credits.

These enforce the properties that must not silently regress: the engine stays
pure, extraction stays streaming-shaped, and the model never gets to decide
where evidence points.
"""

import ast
import inspect
from pathlib import Path

import pytest

from engine import Kind, Utterance
from extraction import ExtractionError, _to_event, extract
from extraction.prompt import CONTEXT_TURNS, build_messages
from extraction.schema import EVENT_SCHEMA, response_format

ROOT = Path(__file__).resolve().parents[1]

U = Utterance(4, "CUSTOMER", 107000, "Yeah... I guess.")


def test_engine_package_imports_nothing_networked():
    """engine/ purity is a hard property, not a convention (CLAUDE.md §7).
    It is what makes the detection layer testable with zero credits."""
    banned = {"urllib", "requests", "http", "socket", "httpx", "openai", "aiohttp"}
    for path in (ROOT / "engine").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [(node.module or "").split(".")[0]]
            else:
                continue
            leaked = banned.intersection(names)
            assert not leaked, f"{path.name} imports {leaked}; engine/ must stay pure"


def test_extract_takes_one_utterance_not_a_transcript():
    """Streaming constraint: an extractor that needs the ending cannot work at
    minute three of a live call."""
    params = inspect.signature(extract).parameters
    assert "utterance" in params
    assert "utterances" not in params, "extract() must take ONE utterance"
    assert "transcript" not in params


def test_context_window_is_bounded():
    turns = [Utterance(i, "A", i * 1000, f"turn {i}") for i in range(40)]
    messages = build_messages(U, turns[-CONTEXT_TURNS:], [])
    assert messages[1]["content"].count("turn ") <= CONTEXT_TURNS


def test_prompt_marks_context_as_non_extractable():
    turns = [Utterance(0, "AGENT", 1000, "When do you need it?")]
    content = build_messages(U, turns, ["delivery_date"])[1]["content"]
    assert "do NOT extract from these" in content
    assert "THIS utterance only" in content
    assert "delivery_date" in content, "known topics must be offered for reuse"


def test_schema_is_closed():
    """Variance is the failure mode; a closed schema is the fix."""
    assert EVENT_SCHEMA["additionalProperties"] is False
    item = EVENT_SCHEMA["properties"]["events"]["items"]
    assert item["additionalProperties"] is False
    assert set(item["required"]) == set(item["properties"]), (
        "every field must be required, or the model may omit fields inconsistently"
    )
    assert response_format()["json_schema"]["strict"] is True


def test_model_cannot_choose_where_evidence_points():
    """index/speaker/timestamp come from the transcript, never the model (DR-005).
    A model that could set these could fabricate a citation."""
    event = _to_event(
        {
            "kind": "commitment", "topic": "Delivery_Date", "value": "  MONDAY ",
            "polarity": True, "ambiguous": True, "explicit_revision": False,
            "text": "accepts monday",
            # hostile extras the model might emit:
            "utterance_index": 999, "speaker": "SOMEONE_ELSE", "t_ms": 1,
        },
        U,
    )
    assert event.utterance_index == U.index == 4
    assert event.speaker == U.speaker == "CUSTOMER"
    assert event.t_ms == U.t_ms == 107000


def test_value_and_topic_are_normalised():
    """delivery_date and Delivery_Date must collide, or the conflict is invisible."""
    event = _to_event(
        {"kind": "commitment", "topic": "  Delivery_Date ", "value": "  MONDAY ",
         "polarity": True, "ambiguous": False, "explicit_revision": False, "text": ""},
        U,
    )
    assert event.topic == "delivery_date"
    assert event.value == "monday"


def test_empty_value_becomes_none_not_empty_string():
    event = _to_event(
        {"kind": "preference", "topic": "premium_plan", "value": "   ",
         "polarity": False, "ambiguous": False, "explicit_revision": False, "text": ""},
        U,
    )
    assert event.value is None, "empty string would never match, but also never be None"


def test_bad_kind_is_rejected_loudly():
    with pytest.raises(ExtractionError, match="bad kind"):
        _to_event({"kind": "vibes", "topic": "t", "polarity": True}, U)


def test_missing_key_raises_rather_than_defaulting_silently():
    with pytest.raises(ExtractionError):
        _to_event({"topic": "t"}, U)


def test_extract_without_api_key_fails_closed(monkeypatch):
    monkeypatch.delenv("ASSEMBLYAI_API_KEY", raising=False)
    with pytest.raises(ExtractionError, match="not set"):
        extract(U, api_key=None)
