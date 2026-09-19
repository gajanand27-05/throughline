"""Prompt construction for per-utterance extraction.

STREAMING CONSTRAINT: extraction runs mid-conversation, one utterance at a
time, and can only ever see what has already been said. Nothing here may
depend on the full transcript - an extractor that needs the ending cannot
work at minute three of a live call.

Context passed in is therefore bounded: a short window of recent turns for
pronoun resolution, plus the list of topics already established so the model
reuses identifiers instead of inventing synonyms (delivery_date vs
delivery_deadline never collide, and a collision is what a conflict IS).
"""

CONTEXT_TURNS = 6  # recent turns shown for reference; not analysed

SYSTEM = """\
You extract structured facts from ONE utterance in a live, ongoing conversation.

You are given earlier turns for context only. Extract facts from the LAST
utterance alone. Never emit events for the context turns - they have already
been processed.

Emit an empty list whenever the utterance establishes nothing. Most utterances
establish nothing: questions, acknowledgements, greetings, thinking aloud,
restating what the other person just said. Over-extraction is the expensive
failure here. A spurious event creates a false alarm that destroys the user's
trust; a missed one costs a single alert.

Specifically DO NOT emit an event when:
- The speaker is asking a question rather than asserting something.
- The speaker is merely acknowledging ("got it", "noted", "sure", "okay").
- The speaker is repeating a value already established without changing it.
- The speaker is describing a situation rather than committing to anything.

ONE EXCEPTION, and it matters more than any other rule here. A hedged,
reluctant or half-hearted YES to a value someone just proposed is a COMMITMENT,
not an acknowledgement. It looks like agreement and it reads like filler, but it
is the moment a term actually changes. Record it, take the value from the
question being answered, and set ambiguous=true.

  context   A: "Can you live with the smaller unit then?"
  utterance B: "Yeah... I suppose."
  -> {"kind": "commitment", "topic": "<existing key for that subject>",
      "value": "smaller_unit", "polarity": true, "ambiguous": true,
      "explicit_revision": false, "text": "hedged acceptance of the smaller unit"}

Answering a question with a bare "yes", "fine", "okay then" or "if we have to"
is the same case whenever a specific value is on the table. Without the value
from the question the utterance means nothing, so read the question to find it.

Reuse an existing topic identifier whenever the utterance concerns that same
subject. Two statements about the same subject MUST share a topic string, or
the conflict between them becomes invisible.

Reuse it ONLY for the same subject, though. A delivery date and an order
quantity are different subjects even in the same sentence, and collapsing them
into one topic invents a conflict where none exists. When in doubt, mint a new
identifier: a missed conflict costs one alert, a merged topic costs trust.

Judge only what this speaker said. Do not infer intent, do not resolve
disagreements, do not decide who is right.\
"""


def build_messages(utterance, context_turns, known_topics):
    """Returns OpenAI-shaped messages for one utterance.

    context_turns: prior Utterance objects, most recent last (already capped).
    known_topics:  topic strings established so far.
    """
    lines = []
    if known_topics:
        lines.append("Topics already established in this conversation:")
        lines.append(", ".join(sorted(known_topics)))
        lines.append("")
    if context_turns:
        lines.append("Earlier turns (context only - do NOT extract from these):")
        for turn in context_turns:
            lines.append(f"  {turn.speaker}: {turn.text}")
        lines.append("")
    lines.append("Extract from THIS utterance only:")
    lines.append(f"  {utterance.speaker}: {utterance.text}")

    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": "\n".join(lines)},
    ]
