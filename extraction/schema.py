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
