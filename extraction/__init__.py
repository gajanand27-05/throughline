"""Utterance -> Event extraction via AssemblyAI's LLM Gateway.

This package is the ONLY place a model is called. `engine/` stays pure; this
layer is where the network and the nondeterminism live, deliberately fenced
off so the detection logic can be tested without either.

Streaming by construction: extract() sees one utterance plus a bounded window
of prior context. It never receives the full transcript.
"""

import json
import os
import time
import urllib.error
import urllib.request

from engine.models import Event, Kind

from .prompt import CONTEXT_TURNS, build_messages
from .schema import response_format

GATEWAY_URL = "https://llm-gateway.assemblyai.com/v1/chat/completions"
DEFAULT_MODEL = os.environ.get("THROUGHLINE_MODEL", "gpt-4.1-mini")
TEMPERATURE = 0.0  # variance is the enemy; see extraction/schema.py
TIMEOUT_S = 12


class ExtractionError(Exception):
    pass


def extract(utterance, context_turns=(), known_topics=(), *, model=None,
            api_key=None, timeout=TIMEOUT_S):
    """Extract Events from ONE utterance. Returns (events, elapsed_seconds)."""
    key = api_key or os.environ.get("ASSEMBLYAI_API_KEY")
    if not key:
        raise ExtractionError("ASSEMBLYAI_API_KEY is not set")

    body = {
        "model": model or DEFAULT_MODEL,
        "messages": build_messages(
            utterance, list(context_turns)[-CONTEXT_TURNS:], list(known_topics)
        ),
        "temperature": TEMPERATURE,
        "max_tokens": 600,
        "response_format": response_format(),
    }

    request = urllib.request.Request(
        GATEWAY_URL,
        data=json.dumps(body).encode(),
        headers={"authorization": key, "content-type": "application/json"},
        method="POST",
    )

    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:400]
        raise ExtractionError(f"gateway {exc.code}: {detail}") from None
    except urllib.error.URLError as exc:
        raise ExtractionError(f"gateway unreachable: {exc.reason}") from None
    elapsed = time.perf_counter() - started

    try:
        content = payload["choices"][0]["message"]["content"]
        raw = json.loads(content)["events"]
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise ExtractionError(f"unparseable response: {exc}") from None

    return [_to_event(item, utterance) for item in raw], elapsed


def _to_event(item, utterance):
    """Map one schema object onto an engine Event.

    index/speaker/timestamp come from the utterance, never from the model -
    the model does not get to invent where evidence points (DR-005).
    """
    try:
        kind = Kind(item["kind"])
    except (KeyError, ValueError):
        raise ExtractionError(f"bad kind: {item.get('kind')!r}") from None

    value = item.get("value")
    if isinstance(value, str):
        value = value.strip().lower() or None

    return Event(
        kind=kind,
        speaker=utterance.speaker,
        utterance_index=utterance.index,
        t_ms=utterance.t_ms,
        topic=str(item.get("topic", "")).strip().lower(),
        text=str(item.get("text", ""))[:200],
        value=value,
        polarity=bool(item.get("polarity", True)),
        ambiguous=bool(item.get("ambiguous", False)),
        explicit_revision=bool(item.get("explicit_revision", False)),
    )
