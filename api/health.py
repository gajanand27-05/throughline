"""Pipeline proof, not a feature.

This endpoint exists to answer questions that are cheap now and expensive on
the 26th: does the Python runtime work, which version is it, does `engine/`
resolve from inside a serverless function, and is the API key wired into the
environment. It deliberately imports the engine and runs it, because
`includeFiles` in vercel.json is exactly the kind of thing that silently
works locally and fails in the deployed function.

It never reveals the key - only whether one is present.
"""

import json
import os
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from engine import Event, Kind, Memory, Utterance, run

    _engine_import_error = None
except Exception as exc:  # pragma: no cover - only fires on a broken deploy
    _engine_import_error = f"{type(exc).__name__}: {exc}"


def _engine_selftest():
    """Run the smallest real detection. If this returns ok, the engine is
    genuinely executing inside the function, not merely importable."""
    if _engine_import_error:
        return {"ok": False, "error": _engine_import_error}
    try:
        utterances = [
            Utterance(0, "CUSTOMER", 18000, "Friday is a hard deadline."),
            Utterance(1, "CUSTOMER", 107000, "Yeah... I guess."),
        ]
        events = [
            Event(Kind.CONSTRAINT, "CUSTOMER", 0, 18000, "delivery_date", value="friday"),
            Event(Kind.COMMITMENT, "CUSTOMER", 1, 107000, "delivery_date",
                  value="monday", ambiguous=True),
        ]
        _, alerts = run(utterances, events)
        return {
            "ok": len(alerts) == 1 and alerts[0].event_type == "commitment_drift",
            "alerts": len(alerts),
            "evidence_cited": len(alerts) > 0
            and bool(alerts[0].evidence_1.text and alerts[0].evidence_2.text),
        }
    except Exception as exc:  # pragma: no cover
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        engine = _engine_selftest()
        body = {
            "service": "throughline",
            "python": sys.version.split()[0],
            "engine": engine,
            "assemblyai_key_present": bool(os.environ.get("ASSEMBLYAI_API_KEY")),
            "region": os.environ.get("VERCEL_REGION"),
            "commit": (os.environ.get("VERCEL_GIT_COMMIT_SHA") or "")[:7] or None,
        }
        status = 200 if engine.get("ok") else 500

        payload = json.dumps(body, indent=2).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
