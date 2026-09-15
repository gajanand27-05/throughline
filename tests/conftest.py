import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FIXTURES = ROOT / "fixtures"

from engine import Event, Utterance  # noqa: E402


def load(name):
    data = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    return (
        data,
        [Utterance.from_dict(u) for u in data["utterances"]],
        [Event.from_dict(e) for e in data["events"]],
    )


def all_fixture_names():
    return sorted(p.stem for p in FIXTURES.glob("*.json"))


def mvp_fixture_names():
    out = []
    for name in all_fixture_names():
        data = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
        if data.get("mvp"):
            out.append(name)
    return out


@pytest.fixture
def fixtures_dir():
    return FIXTURES
