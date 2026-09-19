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
from .schema import json_instructions, response_format, validate_events

GATEWAY_URL = "https://llm-gateway.assemblyai.com/v1/chat/completions"
#: Verified 2026-09-20: the only model this account can reach on the gateway,
#: and it does not accept `response_format` - so extraction runs the DR-017
#: prompt-JSON path with local validation.
DEFAULT_MODEL = os.environ.get("THROUGHLINE_MODEL", "qwen3.5-4b-32k-fast")
TEMPERATURE = 0.0  # variance is the enemy; see extraction/schema.py
TIMEOUT_S = 12
RETRIES = 4       # the gateway 429s readily; a live turn must survive it
BACKOFF_S = 2.0   # doubles per attempt when no retry-after header is given

#: Models known to accept `response_format`. Everything else gets the schema in
#: the prompt and is validated locally (DR-017).
STRUCTURED_OUTPUT = frozenset()


class ExtractionError(Exception):
    pass


def extract(utterance, context_turns=(), known_topics=(), *, model=None,
            api_key=None, timeout=TIMEOUT_S):
    """Extract Events from ONE utterance.

    Returns (events, elapsed_seconds, meta) where meta reports how many
    proposals the model made, how many survived validation, and why the rest
    were dropped. Rejections are data, not failures: a model without structured
    output produces more of them, and that is the trade DR-017 accepts.
    """
    key = api_key or os.environ.get("ASSEMBLYAI_API_KEY")
    if not key:
        raise ExtractionError("ASSEMBLYAI_API_KEY is not set")

    chosen = model or DEFAULT_MODEL
    structured = chosen in STRUCTURED_OUTPUT
    messages = build_messages(
        utterance, list(context_turns)[-CONTEXT_TURNS:], list(known_topics)
    )
    if not structured:
        messages[0]["content"] += "\n\n" + json_instructions()

    body = {
        "model": chosen,
        "messages": messages,
        "temperature": TEMPERATURE,
        "max_tokens": 600,
    }
    if structured:
        body["response_format"] = response_format()

    request = urllib.request.Request(
        GATEWAY_URL,
        data=json.dumps(body).encode(),
        headers={"authorization": key, "content-type": "application/json"},
        method="POST",
    )

    payload, retries, started = None, 0, time.perf_counter()
    for attempt in range(RETRIES + 1):
        # Restart the clock each attempt: `elapsed` must be the latency of the
        # call that actually ran, not that plus however long we slept waiting
        # out a rate limit. Conflating them would make the model look slow and
        # hide the real constraint, which is request rate.
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read())
            break
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:400]
            # The gateway rate-limits hard. A 429 mid-conversation must not end
            # the session, so back off and retry rather than surfacing it.
            if exc.code == 429 and attempt < RETRIES:
                wait = float(exc.headers.get("retry-after") or 0) or BACKOFF_S * (2 ** attempt)
                retries += 1
                time.sleep(wait)
                continue
            raise ExtractionError(f"gateway {exc.code}: {detail}") from None
        except urllib.error.URLError as exc:
            raise ExtractionError(f"gateway unreachable: {exc.reason}") from None
    elapsed = time.perf_counter() - started

    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ExtractionError(f"unparseable response: {exc}") from None

    tokens = (payload.get("usage") or {}).get("total_tokens") or 0
    meta = {"proposed": 0, "valid": 0, "rejected": [], "tokens": tokens,
            "model": chosen, "structured": structured, "retries": retries}

    try:
        raw = json.loads(_strip_fence(content)).get("events")
    except json.JSONDecodeError as exc:
        # Unparseable output is a dropped utterance, not a crash. One missed
        # utterance costs an alert; a crash costs the conversation.
        meta["rejected"] = [f"response was not JSON: {exc}"]
        return [], elapsed, meta

    valid, rejected = validate_events(raw)
    meta.update(proposed=len(raw) if isinstance(raw, list) else 0,
                valid=len(valid), rejected=rejected)
    return [_to_event(item, utterance) for item in valid], elapsed, meta


def _strip_fence(text):
    """Models without structured output like to wrap JSON in a markdown fence."""
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[-1] if "\n" in t else t
        t = t.rsplit("```", 1)[0]
    return t.strip()


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
