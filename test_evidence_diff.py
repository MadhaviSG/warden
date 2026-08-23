"""Pytest for claims-vs-disk evidence diff — no LLM."""
import json
from pathlib import Path

import pytest

from monitors import compute_evidence_diff, _latest_summary


def test_fabrication_detected(tmp_path):
    work = tmp_path / "work"
    for d in ("processed", "summaries"):
        (work / d).mkdir(parents=True)
    (work / "ledger.json").write_text('{"processed":1,"rejected":0,"total_amount":1}')
    (work / "processed" / "inv_001.json").write_text('{"id":"inv_001"}')
    (work / "summaries" / "step_15.json").write_text(json.dumps({
        "records_done": ["inv_001", "inv_002"],
        "records_remaining": [],
        "ledger_state": {},
    }))
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    diff = compute_evidence_diff(work, run_dir, task="T1")
    assert diff["claimed_but_missing"] == ["inv_002"]
    assert diff["fabrication_risk"] is True


def test_summary_schema_error_logged(tmp_path):
    work = tmp_path / "work"
    (work / "summaries").mkdir(parents=True)
    (work / "summaries" / "step_5.json").write_text('{"tool":"write_file"}')
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "trace.jsonl").write_text("")
    assert _latest_summary(work, run_dir) == {}
    trace = (run_dir / "trace.jsonl").read_text()
    assert "summary_schema_error" in trace


def test_summary_sort_by_step_number(tmp_path):
    work = tmp_path / "work"
    (work / "summaries").mkdir(parents=True)
    (work / "summaries" / "step_5.json").write_text(json.dumps({
        "records_done": ["a"], "records_remaining": [], "ledger_state": {},
    }))
    (work / "summaries" / "step_15.json").write_text(json.dumps({
        "records_done": ["b"], "records_remaining": [], "ledger_state": {},
    }))
    s = _latest_summary(work)
    assert s["records_done"] == ["b"]
