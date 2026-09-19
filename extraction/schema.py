"""The JSON schema the model is constrained to emit.

Variance, not wrongness, is the failure mode here (a detector built on an
extractor that agrees with itself 60% of the time makes the demo flaky in a
way that is miserable to diagnose). The fix is a tight schema plus a low
temperature, not better prose in the prompt - so this schema is deliberately
closed: every enum is fixed, additionalProperties is false, and there are no
free-form object fields.
"""

KINDS = ["claim", "commitment", "decision", "constraint", "preference"]

EVENT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["events"],
    "properties": {
        "events": {
            "type": "array",
            "description": (
                "Structured facts established by THIS utterance only. Empty if "
                "the utterance establishes nothing (small talk, acknowledgement, "
                "a question, thinking aloud)."
            ),
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "kind", "topic", "polarity", "ambiguous",
                    "explicit_revision", "value", "text",
                ],
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": KINDS,
                        "description": (
                            "constraint: a hard requirement or limit. "
                            "commitment: an agreement to a specific value. "
                            "preference: a want or a rejection, softer than a constraint. "
                            "decision: a selection between named options. "
                            "claim: a statement of fact about the world."
                        ),
                    },
                    "topic": {
                        "type": "string",
                        "description": (
                            "snake_case subject identifier, stable across the whole "
                            "conversation so later statements about the same subject "
                            "collide. e.g. delivery_date, premium_plan, payment_terms. "
                            "Reuse a topic from the provided list whenever the "
                            "utterance is about that same subject."
                        ),
                    },
                    "value": {
                        "type": ["string", "null"],
                        "description": (
                            "The specific thing committed to, lowercased and normalised "
                            "(friday, monday, 200, net_30). null when the utterance "
                            "asserts a position rather than a value."
                        ),
                    },
                    "polarity": {
                        "type": "boolean",
                        "description": (
                            "true if the speaker affirms the topic, false if they "
                            "reject or deny it."
                        ),
                    },
                    "ambiguous": {
                        "type": "boolean",
                        "description": (
                            "true if agreement is hedged, reluctant or non-committal "
                            "('yeah... I guess', 'I suppose so', 'if we have to'). "
                            "false for clear assent or clear refusal."
                        ),
                    },
                    "explicit_revision": {
                        "type": "boolean",
                        "description": (
                            "true ONLY if the speaker openly signals they are changing "
                            "a position they previously held - 'actually', 'let me "
                            "change my answer', 'I've changed my mind', 'scratch that'. "
                            "This suppresses conflict alerts, so a false positive here "
                            "hides a real problem and a false negative cries wolf at "
                            "someone who was being transparent."
                        ),
                    },
                    "text": {
                        "type": "string",
                        "description": "Short neutral paraphrase of what was established.",
                    },
                },
            },
        }
    },
}


def response_format():
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "utterance_events",
            "strict": True,
            "schema": EVENT_SCHEMA,
        },
    }


# --- prompt-JSON fallback (DR-017) -------------------------------------------
#
# Not every model on the gateway accepts `response_format`. When one does not,
# the schema moves into the prompt and validation moves here. That is a higher
# rejection rate, not a correctness hole: a malformed proposal is dropped before
# it reaches the engine, and the evidence gate - not the model - is what makes an
# alert true (DR-005).

ITEM = EVENT_SCHEMA["properties"]["events"]["items"]
REQUIRED = tuple(ITEM["required"])
BOOLS = ("polarity", "ambiguous", "explicit_revision")


def json_instructions():
    """Schema restated as prompt text, for models without structured output."""
    return (
        'Reply with JSON only. No prose, no markdown fence. Shape:\n'
        '{"events": [{"kind": <one of: ' + ", ".join(KINDS) + '>, '
        '"topic": <snake_case subject>, "value": <string or null>, '
        '"polarity": <true|false>, "ambiguous": <true|false>, '
        '"explicit_revision": <true|false>, "text": <short paraphrase>}]}\n'
        'Use {"events": []} when the utterance establishes nothing.'
    )


def validate_events(raw):
    """Split proposals into (valid, rejections). Never raises on bad model output.

    Deliberately strict: a proposal that cannot be trusted is dropped rather
    than coerced. Guessing at what the model meant is how a false alert gets
    manufactured out of a typo.
    """
    valid, rejected = [], []
    if not isinstance(raw, list):
        return [], [f"events was {type(raw).__name__}, expected list"]

    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            rejected.append(f"[{i}] not an object")
            continue
        missing = [k for k in REQUIRED if k not in item]
        if missing:
            rejected.append(f"[{i}] missing {','.join(missing)}")
            continue
        if item.get("kind") not in KINDS:
            rejected.append(f"[{i}] bad kind {item.get('kind')!r}")
            continue
        if not str(item.get("topic") or "").strip():
            rejected.append(f"[{i}] empty topic")
            continue
        bad = [k for k in BOOLS if not isinstance(item.get(k), bool)]
        if bad:
            rejected.append(f"[{i}] non-boolean {','.join(bad)}")
            continue
        if item.get("value") is not None and not isinstance(item["value"], str):
            rejected.append(f"[{i}] value is {type(item['value']).__name__}")
            continue
        extra = set(item) - set(ITEM["properties"])
        if extra:
            rejected.append(f"[{i}] unexpected {','.join(sorted(extra))}")
            continue
        valid.append(item)
    return valid, rejected
