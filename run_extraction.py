"""Extraction consistency + end-to-end harness.

    python run_extraction.py [--runs 5] [--model gpt-4.1-mini] [--fixture NAME]

Answers four questions in one pass:

  1. END-TO-END   Do the engine's alerts come out right when events come from a
                  real model instead of the fixture? This is the assertion that
                  matters - 4/4 and 0 false alarms through the full pipeline.
  2. CONSISTENCY  Run N times. Does the extractor agree with itself? The failure
                  mode here is variance, not wrongness.
  3. CONTROL      Does extraction over-produce on the clean control? If it emits
                  a spurious constraint from "actually, let me reconsider", then
                  explicit_revision suppression has to move to extraction time.
  4. LATENCY      Per-call timing vs the Vercel function limit.

Exact-match against fixture events is reported as a DIAGNOSTIC only. The
fixtures encode the shape the engine wanted; a real model may split one event
into two or call a constraint a preference and still produce correct alerts.

Spends credits. Requires ASSEMBLYAI_API_KEY (code/.env or environment).
"""

import argparse
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from engine import Event, Memory, Utterance, step  # noqa: E402
from extraction import DEFAULT_MODEL, ExtractionError, extract  # noqa: E402

FIXTURES = ROOT / "fixtures"
VERCEL_LIMIT_S = 30


def load_env():
    """Read code/.env without adding a dependency."""
    import os

    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def signature(events):
    """Order-insensitive fingerprint of one utterance's extraction."""
    return tuple(sorted(
        (e.kind.value, e.topic, e.value, e.polarity, e.ambiguous, e.explicit_revision)
        for e in events
    ))


def one_pass(fixture, model):
    """Fold the conversation ONE UTTERANCE AT A TIME, as it runs live."""
    utterances = [Utterance.from_dict(u) for u in fixture["utterances"]]
    memory, alerts, timings = Memory(), [], []
    per_utterance, known_topics, seen = [], set(), []

    proposed = valid = tokens = 0
    rejections = []

    for utterance in utterances:
        events, elapsed, meta = extract(
            utterance, context_turns=seen, known_topics=known_topics, model=model
        )
        timings.append(elapsed)
        per_utterance.append(signature(events))
        proposed += meta["proposed"]
        valid += meta["valid"]
        tokens += meta["tokens"]
        rejections.extend(meta["rejected"])
        for event in events:
            known_topics.add(event.topic)
            _, new_alerts = step(memory, event, utterances)
            alerts.extend(new_alerts)
        seen.append(utterance)

    return {
        "alerts": alerts,
        "timings": timings,
        "signatures": per_utterance,
        "event_count": sum(len(s) for s in per_utterance),
        "proposed": proposed,
        "valid": valid,
        "tokens": tokens,
        "rejections": rejections,
    }


def evaluate(name, fixture, runs, model):
    expected = fixture["expected_alerts"]
    results, errors = [], []
    for i in range(runs):
        try:
            results.append(one_pass(fixture, model))
        except ExtractionError as exc:
            errors.append(f"run {i + 1}: {exc}")

    if not results:
        return {"name": name, "fatal": errors}

    # 1. end-to-end
    correct = 0
    for result in results:
        got = [(a.event_type, a.speaker,
                a.evidence_1.utterance_index, a.evidence_2.utterance_index)
               for a in result["alerts"]]
        want = [(e["event_type"], e["speaker"], *e["evidence_indices"])
                for e in expected]
        if got == want:
            correct += 1

    # 2. consistency: how often the whole conversation extracts identically
    whole = Counter(tuple(r["signatures"]) for r in results)
    modal = whole.most_common(1)[0][1]

    per_utterance_agreement = []
    for i in range(len(results[0]["signatures"])):
        counts = Counter(r["signatures"][i] for r in results)
        per_utterance_agreement.append(counts.most_common(1)[0][1] / len(results))

    timings = [t for r in results for t in r["timings"]]
    proposed = sum(r["proposed"] for r in results)
    valid = sum(r["valid"] for r in results)
    return {
        "name": name,
        "runs": len(results),
        "expected_alerts": len(expected),
        "end_to_end_correct": correct,
        "identical_runs": modal,
        "min_utterance_agreement": min(per_utterance_agreement),
        "events_per_run": [r["event_count"] for r in results],
        "p50_ms": round(statistics.median(timings) * 1000),
        "max_ms": round(max(timings) * 1000),
        "worst_conversation_s": round(max(sum(r["timings"]) for r in results), 1),
        "proposed": proposed,
        "valid": valid,
        "schema_validity": (valid / proposed) if proposed else 1.0,
        "tokens": sum(r["tokens"] for r in results),
        "rejections": [x for r in results for x in r["rejections"]],
        "errors": errors,
        "sample_alerts": [a.to_dict() for a in results[0]["alerts"]],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--fixture", default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    load_env()

    names = [args.fixture] if args.fixture else ["contradiction", "commitment_drift",
                                                 "clean_control"]
    reports = []
    for name in names:
        fixture = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
        print(f"  extracting {name} x{args.runs} ...", file=sys.stderr)
        reports.append(evaluate(name, fixture, args.runs, args.model))

    if args.json:
        print(json.dumps(reports, indent=2))
        return 0

    print(f"\nmodel: {args.model}   runs per fixture: {args.runs}\n")
    fatal = [r for r in reports if r.get("fatal")]
    if fatal:
        for r in fatal:
            print(f"  {r['name']}: FATAL")
            for err in r["fatal"][:3]:
                print(f"      {err}")
        return 1

    header = (f"  {'fixture':<18}{'end-to-end':<13}{'identical':<12}{'min agree':<12}"
              f"{'schema':<10}{'p50':<10}{'max'}")
    print(header)
    print("  " + "-" * (len(header) - 2))
    for r in reports:
        e2e = f"{r['end_to_end_correct']}/{r['runs']}"
        idn = f"{r['identical_runs']}/{r['runs']}"
        agree = f"{r['min_utterance_agreement']:.0%}"
        sch = f"{r['valid']}/{r['proposed']}"
        print(f"  {r['name']:<18}{e2e:<13}{idn:<12}{agree:<12}{sch:<10}"
              f"{str(r['p50_ms'])+'ms':<10}{r['max_ms']}ms")

    tokens = sum(r["tokens"] for r in reports)
    prop = sum(r["proposed"] for r in reports)
    val = sum(r["valid"] for r in reports)
    print(f"\n  Schema validity: {val}/{prop} proposals validated"
          f"{'' if not prop else f' ({val/prop:.0%})'}"
          f"  ·  tokens used: {tokens:,}")
    rej = [x for r in reports for x in r["rejections"]]
    if rej:
        from collections import Counter as _C
        print(f"  Rejected {len(rej)}: " + "; ".join(
            f"{n}x {reason}" for reason, n in _C(
                x.split("] ", 1)[-1] for x in rej).most_common(4)))

    control = next((r for r in reports if r["name"] == "clean_control"), None)
    if control:
        clean = control["end_to_end_correct"] == control["runs"]
        print(f"\n  False-positive guard (clean_control): "
              f"{'PASS' if clean else 'FAIL'}  "
              f"events extracted per run: {control['events_per_run']}")

    worst = max(r["worst_conversation_s"] for r in reports)
    print(f"  Latency: worst full conversation {worst}s vs Vercel limit "
          f"{VERCEL_LIMIT_S}s (per-call is what ships; this is the batch total)")

    weak = [r for r in reports if r["end_to_end_correct"] < r["runs"]]
    flaky = [r for r in reports if r["min_utterance_agreement"] < 0.8]
    print()
    if weak:
        print(f"  END-TO-END NOT CLEAN: {', '.join(r['name'] for r in weak)}")
    if flaky:
        print(f"  HIGH VARIANCE: {', '.join(r['name'] for r in flaky)} "
              f"- tighten the schema or lower temperature, do not reword the prompt")
    if not weak and not flaky:
        print("  OK - extraction is accurate and stable enough to build on")
    print()
    return 1 if weak else 0


if __name__ == "__main__":
    sys.exit(main())
