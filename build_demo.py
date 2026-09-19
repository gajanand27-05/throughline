"""Render the fixtures through the engine and emit public/demo.json.

    python build_demo.py

The page never contains hand-written alerts. Every alert it displays came out
of `engine.run()` and therefore through the evidence gate (DR-005) - which is
the only reason the UI is worth showing a judge. If the detectors regress, the
demo visibly breaks rather than quietly lying.

Zero network, zero audio, zero credits. Safe to run in CI.
"""

import json
import sys
from pathlib import Path

from engine import Event, Utterance, run

ROOT = Path(__file__).parent
FIXTURES = ROOT / "fixtures"
OUT = ROOT / "public" / "demo.json"

# Order matters: this is the order the judge clicks through. Drift first
# (it is the pitch), then contradiction, then the control that proves restraint.
ORDER = ["commitment_drift", "contradiction", "clean_control"]

TITLES = {
    "commitment_drift": "Commitment drift",
    "contradiction": "Contradiction",
    "clean_control": "Clean control",
}

BLURBS = {
    "commitment_drift": "A hard constraint set at 00:18 quietly becomes a hedged "
                        "yes to the opposite at 01:47.",
    "contradiction": "A position stated in minute one is reversed twenty minutes "
                     "later, with no acknowledgement that anything changed.",
    "clean_control": "A healthy conversation loaded with near-misses a naive "
                     "detector fires on. Correct output is nothing at all.",
}


def build(name):
    data = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    utterances = [Utterance.from_dict(u) for u in data["utterances"]]
    events = [Event.from_dict(e) for e in data["events"]]
    _, alerts = run(utterances, events)

    expected = len(data["expected_alerts"])
    if len(alerts) != expected:
        raise SystemExit(
            f"{name}: engine produced {len(alerts)} alert(s), fixture expects "
            f"{expected}. Refusing to write a demo that misrepresents the engine."
        )
    # The page renders whatever status the engine emits; anything it cannot
    # render must not reach it silently.
    unknown = {a.status.value for a in alerts} - {"active", "withdrawn", "updated"}
    if unknown:
        raise SystemExit(f"{name}: page cannot render alert status {unknown}")

    return {
        "name": name,
        "title": TITLES[name],
        "blurb": BLURBS[name],
        "utterances": [
            {"index": u.index, "speaker": u.speaker, "t_ms": u.t_ms, "text": u.text}
            for u in utterances
        ],
        # Keyed to the later cited utterance: an alert cannot fire before the
        # evidence that justifies it exists.
        "alerts": [dict(a.to_dict(), fires_at=a.evidence_2.utterance_index)
                   for a in alerts],
    }


def main():
    scenarios = [build(name) for name in ORDER]
    OUT.write_text(
        json.dumps({"scenarios": scenarios}, indent=2), encoding="utf-8"
    )
    total = sum(len(s["alerts"]) for s in scenarios)
    print(f"wrote {OUT.relative_to(ROOT)}")
    for s in scenarios:
        print(f"  {s['name']:<18}{len(s['utterances']):>3} utterances  "
              f"{len(s['alerts'])} alert(s)")
    print(f"\n{total} alert(s) total, all via engine.run() -> evidence gate")
    return 0


if __name__ == "__main__":
    sys.exit(main())
