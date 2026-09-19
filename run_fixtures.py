"""Acceptance report for the integrity engine.

    python run_fixtures.py

Zero network, zero audio, zero credits. Exit code 1 if anything fails.
"""

import json
import sys
from pathlib import Path

from engine import POST_MVP, AlertStatus, Event, Revision, Utterance, run

FIXTURES = Path(__file__).parent / "fixtures"


def check(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    utterances = [Utterance.from_dict(u) for u in data["utterances"]]
    events = [Event.from_dict(e) for e in data["events"]]
    _, alerts = run(utterances, events)
    expected = data["expected_alerts"]

    if not data.get("mvp"):
        return "SKIPPED", "post-MVP", alerts

    if len(alerts) != len(expected):
        return "FAIL", f"expected {len(expected)} alert(s), got {len(alerts)}", alerts

    for got, want in zip(alerts, expected):
        pair = [got.evidence_1.utterance_index, got.evidence_2.utterance_index]
        if got.event_type != want["event_type"]:
            return "FAIL", f"type {got.event_type} != {want['event_type']}", alerts
        if pair != want["evidence_indices"]:
            return "FAIL", f"evidence {pair} != {want['evidence_indices']}", alerts
        if got.confidence < want["min_confidence"]:
            return "FAIL", f"confidence {got.confidence} < {want['min_confidence']}", alerts

    # Replay each declared revision in order and check the stated outcome
    # (DR-022). A fixture that fires an alert but never re-checks it would let
    # the exact misattribution this project claims to prevent pass silently.
    items = list(events)
    for spec in data.get("revisions", []):
        items.append(Revision.from_dict(spec))
        _, alerts = run(utterances, items)
        for want in spec["expect"]:
            match = [a for a in alerts
                     if [a.evidence_1.utterance_index,
                         a.evidence_2.utterance_index] == want["evidence_indices"]]
            if not match:
                return "FAIL", f"revision target {want['evidence_indices']} vanished", alerts
            if match[0].status.value != want["status"]:
                return ("FAIL",
                        f"after revision {spec['relabels']}: "
                        f"{match[0].status.value} != {want['status']}", alerts)

    revs = len(data.get("revisions", []))
    note = "0 alerts" if not expected else f"{len(alerts)} alert(s)"
    if revs:
        live = sum(1 for a in alerts if a.status is not AlertStatus.WITHDRAWN)
        note = f"{len(alerts)} alert(s), {revs} revision(s) -> {live} still standing"
    return "PASS", note, alerts


def main():
    paths = sorted(FIXTURES.glob("*.json"))
    results, all_alerts = [], []
    for path in paths:
        status, note, alerts = check(path)
        results.append((path.stem, status, note))
        all_alerts.extend(alerts)

    width = max(len(n) for n, _, _ in results)
    print(f"\n{len(paths)} fixtures processed\n")
    for name, status, note in results:
        show = status != "PASS" or "0 alerts" in note or "revision" in note
        suffix = f" - {note}" if show else ""
        print(f"  {name:<{width}}  {status}{suffix}")

    control = dict((n, s) for n, s, _ in results).get("clean_control")
    gated = all(
        a.event_type and a.speaker and 0.0 < a.confidence <= 1.0
        and a.evidence_1.utterance_index != a.evidence_2.utterance_index
        and a.evidence_1.t_ms < a.evidence_2.t_ms
        for a in all_alerts
    )

    print()
    print(f"  False-positive guard: {'PASS' if control == 'PASS' else 'FAIL'}")
    print(f"  Evidence gate:        {'PASS' if gated else 'FAIL'}")

    if all_alerts:
        print("\n  Alerts raised:")
        for a in all_alerts:
            print(f"\n    {a.event_type}  speaker={a.speaker}  t={a.t_ms}ms  "
                  f"confidence={a.confidence}")
            print(f"      evidence_1  [{a.evidence_1.t_ms:>7}ms] "
                  f"{a.evidence_1.speaker}: {a.evidence_1.text}")
            print(f"      evidence_2  [{a.evidence_2.t_ms:>7}ms] "
                  f"{a.evidence_2.speaker}: {a.evidence_2.text}")

    failed = [n for n, s, _ in results if s == "FAIL"]
    print()
    if failed:
        print(f"FAILED: {', '.join(failed)}\n")
        return 1
    skipped = [n for n, s, _ in results if s == "SKIPPED"]
    print(f"OK - {len(results) - len(skipped)} MVP fixtures passed, "
          f"{len(skipped)} post-MVP skipped ({', '.join(POST_MVP)})\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
