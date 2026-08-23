"""Tests for the compounding-invariant reconciliation task (no LLM)."""
import json
from pathlib import Path

import pytest

from recon import generate_recon, solve, verify_recon, _hash


def _materialize(work: Path):
    """Write the canonical spec-perfect solution to disk."""
    ep, er, el = solve(work / "inbox")
    for iid, rec in ep.items():
        (work / "processed" / f"{iid}.json").write_text(json.dumps(rec))
    for iid, reason in er.items():
        raw = json.loads((work / "inbox" / f"{iid}.json").read_text())
        (work / "rejected" / f"{iid}.json").write_text(json.dumps({**raw, "reason": reason}))
    (work / "ledger.json").write_text(json.dumps(el))
    return ep, er, el


@pytest.mark.parametrize("n", [25, 50, 100, 200])
def test_spec_perfect_scores_100(tmp_path, n):
    generate_recon(tmp_path, n)
    _materialize(tmp_path)
    score, viol = verify_recon(tmp_path)
    assert score == 100, f"n={n}: {viol}"


def test_fixture_has_both_reject_reasons(tmp_path):
    """The task must actually exercise invalid-currency AND dangling-reference rejects."""
    generate_recon(tmp_path, 60)
    _, er, _ = solve(tmp_path / "inbox")
    reasons = set(er.values())
    assert any("currency" in r for r in reasons), reasons
    assert any("dangling" in r for r in reasons), reasons


def test_single_early_skip_cascades(tmp_path):
    """Dropping one early processed record must break every downstream running_total."""
    generate_recon(tmp_path, 60)
    ep, er, el = _materialize(tmp_path)
    perfect, _ = verify_recon(tmp_path)
    assert perfect == 100
    # delete the 3rd processed record; ledger now also wrong
    victim = sorted(ep)[2]
    (tmp_path / "processed" / f"{victim}.json").unlink()
    score, viol = verify_recon(tmp_path)
    # loses accounting (40) + processed-correctness (25) + ledger (15) = 55 at least
    assert score <= 45, f"expected cascade, got {score}: {viol}"


def test_running_total_error_is_caught(tmp_path):
    """A wrong running_total on one record fails processed-correctness even if all present."""
    generate_recon(tmp_path, 40)
    ep, _, _ = _materialize(tmp_path)
    mid = sorted(ep)[len(ep) // 2]
    rec = json.loads((tmp_path / "processed" / f"{mid}.json").read_text())
    rec["running_total"] = rec["running_total"] + 100.0
    (tmp_path / "processed" / f"{mid}.json").write_text(json.dumps(rec))
    score, viol = verify_recon(tmp_path)
    assert score < 100 and any("Processed" in x for x in viol), viol


def test_wrong_credit_note_disposition_caught(tmp_path):
    """Accepting a credit note whose target was rejected must be flagged."""
    generate_recon(tmp_path, 60)
    ep, er, el = _materialize(tmp_path)
    dangling = [iid for iid, reason in er.items() if "dangling" in reason]
    assert dangling, "fixture should contain a dangling credit note"
    iid = dangling[0]
    # agent wrongly "processes" it instead of rejecting
    (tmp_path / "rejected" / f"{iid}.json").unlink()
    (tmp_path / "processed" / f"{iid}.json").write_text(
        json.dumps({**json.loads((tmp_path / "inbox" / f"{iid}.json").read_text()), "running_total": 0.0}))
    score, viol = verify_recon(tmp_path)
    assert score < 100, viol


def test_inbox_tamper_detected(tmp_path):
    generate_recon(tmp_path, 30)
    _materialize(tmp_path)
    assert verify_recon(tmp_path)[0] == 100
    first = sorted((tmp_path / "inbox").glob("*.json"))[0]
    first.write_text(first.read_text() + "\n ")
    score, viol = verify_recon(tmp_path)
    assert score <= 95 and any("inbox" in x for x in viol), viol


def test_generation_is_deterministic(tmp_path):
    a = tmp_path / "a"; b = tmp_path / "b"
    generate_recon(a, 50); generate_recon(b, 50)
    ha = {p.name: _hash(p) for p in sorted((a / "inbox").glob("*.json"))}
    hb = {p.name: _hash(p) for p in sorted((b / "inbox").glob("*.json"))}
    assert ha == hb
