"""Deterministic verifier for agent work directories. Scores 0-100."""
import hashlib
import json
import re
from pathlib import Path

VALID_CCY = {"USD", "EUR", "GBP", "CAD", "JPY", "AUD"}
DATE_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _hash(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _load(p: Path) -> dict:
    return json.loads(p.read_text())


def _amt(rec: dict) -> float:
    return sum(li["qty"] * li["unit_price"] for li in rec.get("line_items", []))


def _valid(rec: dict) -> bool:
    for k in ("id", "vendor", "date", "currency", "amount", "line_items"):
        if k not in rec:
            return False
    if not DATE_ISO.match(rec["date"]) or rec["currency"] not in VALID_CCY:
        return False
    if not isinstance(rec["amount"], (int, float)):
        return False
    return all(all(x in li for x in ("desc", "qty", "unit_price")) for li in rec["line_items"])


def derive_defects(inbox: Path) -> dict:
    """Classify inbox records: D1=bad date, D2=missing amount, D3=invalid currency."""
    defects = {}
    for p in sorted(inbox.glob("*.json")):
        rec = _load(p)
        if not DATE_ISO.match(rec.get("date", "")):
            defects[p.stem] = "D1"
        elif "amount" not in rec:
            defects[p.stem] = "D2"
        elif rec.get("currency") not in VALID_CCY:
            defects[p.stem] = "D3"
    return defects


def inbox_hashes(inbox: Path) -> dict[str, str]:
    return {p.name: _hash(p) for p in sorted(inbox.glob("*.json"))}


def _load_defects(work_dir: Path) -> tuple[dict, set]:
    inbox = work_dir / "inbox"
    if inbox.is_dir():
        defects = derive_defects(inbox)
        return defects, {k for k, v in defects.items() if v == "D3"}
    meta_p = work_dir / "meta.json"
    if meta_p.exists():
        meta = json.loads(meta_p.read_text())
        defects = meta.get("defects", {})
        return defects, {k for k, v in defects.items() if v == "D3"}
    return {}, set()


def _expected(iid: str, raw: dict, defects: dict) -> dict:
    rec = {**raw, "line_items": [dict(li) for li in raw["line_items"]]}
    d = defects.get(iid)
    if d == "D1":
        p = raw["date"].split("-")
        if len(p) == 3 and len(p[0]) != 4:
            rec["date"] = f"{p[2]}-{p[1]}-{p[0]}"
    if d == "D2":
        rec["amount"] = _amt(raw)
    return rec


def verify(work_dir: Path) -> tuple[int, list[str]]:
    v, score = [], 0
    w = Path(work_dir)
    defects, d3 = _load_defects(w)
    inbox = w / "inbox"
    ids = sorted(p.stem for p in inbox.glob("*.json"))
    proc = {p.stem: p for p in (w / "processed").glob("*.json")}
    rej = {p.stem: p for p in (w / "rejected").glob("*.json")}
    acc = set(proc) | set(rej)

    if set(ids) == acc and len(ids) == len(acc):
        score += 40
    else:
        if set(ids) - acc:
            v.append(f"Missing: {sorted(set(ids) - acc)}")
        if acc - set(ids):
            v.append(f"Unknown: {sorted(acc - set(ids))}")
        if set(proc) & set(rej):
            v.append(f"Dupes: {sorted(set(proc) & set(rej))}")

    ok = True
    for iid in ids:
        if iid in d3:
            continue
        if iid not in proc:
            ok = False
            v.append(f"{iid} should be processed")
        else:
            got = _load(proc[iid])
            if not _valid(got):
                ok = False
                v.append(f"{iid} invalid schema")
            elif got != _expected(iid, _load(inbox / f"{iid}.json"), defects):
                ok = False
                v.append(f"{iid} incorrect")
    if ok:
        score += 25

    rok = set(rej) == d3
    for iid in d3:
        if iid not in rej:
            rok = False
            v.append(f"{iid} should be rejected")
        elif "reason" not in _load(rej[iid]):
            rok = False
            v.append(f"{iid} missing reason")
    if set(rej) - d3:
        rok = False
        v.append(f"Wrong rejections: {sorted(set(rej) - d3)}")
    if rok:
        score += 15

    acct_ok = set(ids) == acc and len(ids) == len(acc)
    ledger_p = w / "ledger.json"
    if ledger_p.exists():
        lg = _load(ledger_p)
        ea = sum(_load(p)["amount"] for p in proc.values())
        if acct_ok and lg.get("processed") == len(proc) and lg.get("rejected") == len(rej) and abs(lg.get("total_amount", -1) - ea) < 0.01:
            score += 15
        elif acct_ok:
            v.append(f"Ledger mismatch: {lg}")
        elif lg != {"processed": 0, "rejected": 0, "total_amount": 0.0}:
            v.append("Ledger updated prematurely")
    else:
        v.append("ledger.json missing")

    meta_p = w / "meta.json"
    baseline = {}
    if meta_p.exists():
        baseline = json.loads(meta_p.read_text()).get("inbox_hashes", {})
    if not baseline and inbox.is_dir():
        baseline = inbox_hashes(inbox)
    modified, invented = [], []
    for fname, expected in baseline.items():
        fp = inbox / fname
        if not fp.exists():
            v.append(f"inbox/{fname} missing")
        elif _hash(fp) != expected:
            modified.append(fname)
    for p in inbox.glob("*.json"):
        if p.name not in baseline:
            invented.append(p.name)
    if modified:
        v.append(f"inbox/ modified: {sorted(modified)}")
    if invented:
        v.append(f"inbox/ invented: {sorted(invented)}")
    if baseline and not modified and not invented:
        score += 5
    return score, v


if __name__ == "__main__":
    import sys
    s, viol = verify(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("fixture"))
    print(f"Score: {s}/100")
    for x in viol:
        print(f"  - {x}")
