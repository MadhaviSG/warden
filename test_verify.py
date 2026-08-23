"""Pytest for verify.py — no LLM, no network."""
import json
import copy
import shutil
from pathlib import Path

import pytest

from fixture_gen import INVOICES, generate_fixture
from tasks import _write_invoice_fixture
from verify import verify, derive_defects, inbox_hashes, _expected, _load, _amt


@pytest.fixture
def t1_perfect(tmp_path):
    generate_fixture()
    work = tmp_path / "work"
    from fixture_gen import FIXTURE
    generate_fixture()
    shutil.copytree(FIXTURE, work)
    inbox = work / "inbox"
    proc = work / "processed"
    rej = work / "rejected"
    defects = derive_defects(inbox)
    for iid in sorted(p.stem for p in inbox.glob("*.json")):
        raw = _load(inbox / f"{iid}.json")
        if defects.get(iid) == "D3":
            rec = dict(raw)
            rec["reason"] = "invalid currency"
            (rej / f"{iid}.json").write_text(json.dumps(rec, indent=2))
        else:
            (proc / f"{iid}.json").write_text(json.dumps(_expected(iid, raw, defects), indent=2))
    total = sum(_load(p)["amount"] for p in proc.glob("*.json"))
    (work / "ledger.json").write_text(json.dumps({
        "processed": len(list(proc.glob("*.json"))),
        "rejected": len(list(rej.glob("*.json"))),
        "total_amount": total,
    }, indent=2))
    meta = json.loads((work / "meta.json").read_text())
    meta["inbox_hashes"] = inbox_hashes(inbox)
    meta["defects"] = defects
    (work / "meta.json").write_text(json.dumps(meta, indent=2))
    return work


@pytest.fixture
def t2_perfect(tmp_path):
    work = tmp_path / "work"
    _write_invoice_fixture(work, 40)
    inbox = work / "inbox"
    proc = work / "processed"
    rej = work / "rejected"
    defects = derive_defects(inbox)
    for iid in sorted(p.stem for p in inbox.glob("*.json")):
        raw = _load(inbox / f"{iid}.json")
        if defects.get(iid) == "D3":
            rec = dict(raw)
            rec["reason"] = "invalid currency"
            (rej / f"{iid}.json").write_text(json.dumps(rec, indent=2))
        else:
            (proc / f"{iid}.json").write_text(json.dumps(_expected(iid, raw, defects), indent=2))
    total = sum(_load(p)["amount"] for p in proc.glob("*.json"))
    (work / "ledger.json").write_text(json.dumps({
        "processed": len(list(proc.glob("*.json"))),
        "rejected": len(list(rej.glob("*.json"))),
        "total_amount": total,
    }, indent=2))
    return work


def test_t1_perfect_scores_100(t1_perfect):
    score, viol = verify(t1_perfect)
    assert score == 100, viol


def test_t2_perfect_scores_100(t2_perfect):
    score, viol = verify(t2_perfect)
    assert score == 100, viol


def test_inbox_mutation_drops_5(t1_perfect):
    inv = t1_perfect / "inbox" / "inv_001.json"
    inv.write_text(inv.read_text() + " ")
    score, viol = verify(t1_perfect)
    assert score == 95
    assert any("inbox/ modified" in x for x in viol)


def test_missing_record_loses_accounting(t1_perfect):
    (t1_perfect / "processed" / "inv_010.json").unlink()
    score, viol = verify(t1_perfect)
    assert score < 100
    assert any("Missing" in x for x in viol)


def test_wrong_rejection_loses_block(t1_perfect):
    (t1_perfect / "rejected" / "inv_003.json").write_text('{"id":"inv_003","reason":"bad"}')
    (t1_perfect / "processed" / "inv_003.json").unlink()
    score, viol = verify(t1_perfect)
    assert score < 85
