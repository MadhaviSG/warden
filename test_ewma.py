"""Unit tests for WardenMonitor EWMA aggregation (no LLM)."""
import json
from pathlib import Path
from unittest.mock import patch

from monitors import WardenMonitor

ROOT = Path(__file__).parent
WORK = ROOT / "fixture"


def _checks(scores, start=10):
    m = WardenMonitor()
    events, ivs = [], []
    rd = ROOT / "runs" / "_ewma_test"
    rd.mkdir(parents=True, exist_ok=True)
    (rd / "trace.jsonl").write_text("")
    with patch.object(WardenMonitor, "_judge", side_effect=[{"score": s, "reason": "test"} for s in scores]):
        for i, _ in enumerate(scores):
            step = start + i * 5
            r = m.check(step, rd, WORK, "spec", events)
            ivs.append(r)
    return m, events, ivs


def test_aggregate_rising():
    m, events, ivs = _checks([40, 45, 50])
    assert len(events) == 3
    assert events[-1]["trigger"] == "aggregate"
    assert ivs[-1] is not None
    assert ivs[0] is None and ivs[1] is None


def test_single_spike():
    _, events, ivs = _checks([5, 5, 95])
    assert events[-1]["trigger"] == "single"
    assert ivs[-1] is not None


def test_cooldown_honored():
    m, _, ivs = _checks([95, 5])
    assert ivs[0] is not None
    assert ivs[1] is None  # cooldown skip — no judge call effect
    assert m.interventions == 1


if __name__ == "__main__":
    test_aggregate_rising()
    test_single_spike()
    test_cooldown_honored()
    print("All EWMA tests passed.")
