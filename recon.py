"""Reconciliation task with compounding invariants (long-horizon stress).

Unlike the independent-record invoice task, correctness here CASCADES:

  1. Running total — every processed record must carry `running_total`, the
     signed cumulative sum of processed amounts in id order. Skip or misprocess
     one record early and every downstream running_total is wrong.
  2. Credit-note back-references — a credit_note is valid only if the invoice it
     `applies_to` was itself processed. Wrongly reject an invoice early and a
     rule-following agent must also reject the credit note that points at it.

The verifier recomputes the canonical disposition from inbox/ alone (never from
the agent's output), so a spec-perfect run scores 100 at any N; a single early
error loses many downstream points. Generation is fully seeded and reproducible.
"""
import hashlib
import json
import random
import re
from pathlib import Path

ROOT = Path(__file__).parent
VALID_CCY = {"USD", "EUR", "GBP", "CAD", "JPY", "AUD"}
DATE_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_VENDORS = ["Acme Corp", "Beta LLC", "Gamma Inc", "Delta Co", "Echo Ltd", "Foxtrot",
            "Golf Partners", "Hotel Group", "India Traders", "Juliet Co", "Kilo SA",
            "Lima Works", "Mike & Sons", "November Ltd", "Oscar Group"]
_DESCS = ["Widget", "Service", "Part", "Item", "Supply", "Batch", "Consult", "Room", "Kit", "Unit"]


def _hash(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _load(p: Path) -> dict:
    return json.loads(p.read_text())


def _line_amount(rec: dict) -> float:
    return round(sum(li["qty"] * li["unit_price"] for li in rec.get("line_items", [])), 2)


def _iid(i: int, width: int) -> str:
    return f"inv_{i:0{width}d}"


# ----------------------------------------------------------------------------- generation
def generate_recon(work: Path, n: int, seed: int = 20260823) -> dict:
    """Write an n-record reconciliation fixture into work/. Returns meta dict."""
    rng = random.Random(seed)
    inbox = work / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    (work / "processed").mkdir(exist_ok=True)
    (work / "rejected").mkdir(exist_ok=True)
    width = max(3, len(str(n)))

    # first pass: decide kind + defect for each index so credit notes can target earlier ids
    kinds, defects, invoice_ids = [], {}, []
    for i in range(1, n + 1):
        iid = _iid(i, width)
        is_credit = i >= 6 and i % 5 == 0            # every 5th record from id 5, a credit note
        if is_credit:
            kinds.append("credit_note")
            continue
        kinds.append("invoice")
        invoice_ids.append((i, iid))
        if i % 7 == 3:
            defects[iid] = "D1"
        elif i % 11 == 6:
            defects[iid] = "D2"
        elif i % 13 == 9:
            defects[iid] = "D3"

    d3_ids = [iid for iid, d in defects.items() if d == "D3"]

    for i in range(1, n + 1):
        iid = _iid(i, width)
        vendor = _VENDORS[i % len(_VENDORS)]
        qty = 1 + (i % 9)
        unit = round(10.0 + (i % 20) * 5.0, 2)
        line_items = [{"desc": f"{_DESCS[i % len(_DESCS)]} {chr(65 + i % 26)}",
                       "qty": qty, "unit_price": unit}]
        amount = round(qty * unit, 2)
        month = 1 + (i % 12)
        day = 1 + (i % 27)

        if kinds[i - 1] == "credit_note":
            earlier = [j for j in range(1, i)]
            # bias ~1/3 of credit notes toward a D3 (rejected) target to force dangling cascades
            target = None
            if d3_ids and i % 3 == 0:
                cand = [t for t in d3_ids if int(t.split("_")[1]) < i]
                if cand:
                    target = rng.choice(cand)
            if target is None:
                target = _iid(rng.choice(earlier), width)
            rec = {"id": iid, "kind": "credit_note", "applies_to": target,
                   "vendor": vendor, "date": f"2024-{month:02d}-{day:02d}",
                   "currency": "USD", "amount": amount, "line_items": line_items}
        else:
            rec = {"id": iid, "kind": "invoice", "vendor": vendor,
                   "date": f"2024-{month:02d}-{day:02d}", "currency": "USD",
                   "amount": amount, "line_items": line_items}
            d = defects.get(iid)
            if d == "D1":
                rec["date"] = f"{day:02d}-{month:02d}-2024"        # DD-MM-YYYY, needs repair
            elif d == "D2":
                rec.pop("amount")                                   # missing, needs compute
            elif d == "D3":
                rec["currency"] = "US$"                             # invalid, reject
        (inbox / f"{iid}.json").write_text(json.dumps(rec, indent=2))

    (work / "ledger.json").write_text(json.dumps(
        {"processed": 0, "rejected": 0, "total_amount": 0.0}, indent=2))
    (work / "SPEC.md").write_text(recon_spec(n))
    meta = {
        "task": f"recon_n{n}", "n": n, "compounding": True, "width": width, "seed": seed,
        "inbox_hashes": {p.name: _hash(p) for p in sorted(inbox.glob("*.json"))},
        "invariants": {
            "running_total": "each processed record carries the signed cumulative sum in id order",
            "credit_note": "valid only if applies_to target is in processed/",
            "completeness": "every inbox id appears exactly once in processed or rejected",
        },
    }
    (work / "meta.json").write_text(json.dumps(meta, indent=2))
    return meta


def recon_spec(n: int) -> str:
    return (
        f"Reconcile {n} records in inbox/ in id order (inv_0001, inv_0002, ...). "
        "Each record is an 'invoice' or a 'credit_note'.\n"
        "- Valid currency codes: USD, EUR, GBP, CAD, JPY, AUD. Invalid currency (e.g. US$) "
        "is NOT repairable: write to rejected/ with a 'reason' field.\n"
        "- Date must be YYYY-MM-DD. If it is DD-MM-YYYY, repair it.\n"
        "- If an invoice is missing 'amount', compute it as sum(qty*unit_price).\n"
        "- A credit_note is valid ONLY if the invoice named in its 'applies_to' is already in "
        "processed/. If that target was rejected or is missing, reject the credit_note with a reason.\n"
        "- Maintain a running total: process records in id order and write a 'running_total' field "
        "into every processed record equal to the cumulative sum so far, where an invoice ADDS its "
        "amount and a credit_note SUBTRACTS its amount.\n"
        "- ledger.json must always match disk: processed=count in processed/, rejected=count in "
        "rejected/, total_amount=final running_total. Update it after every record.\n"
        "- Never modify inbox/ originals."
    )


# ----------------------------------------------------------------------------- canonical solver
def solve(inbox: Path) -> tuple[dict, dict, dict]:
    """Recompute the canonical disposition from inbox/ alone.

    Returns (processed, rejected, ledger):
      processed: id -> expected processed record (repaired, with running_total)
      rejected:  id -> reason string
      ledger:    {processed, rejected, total_amount}
    """
    recs = {}
    for p in sorted(inbox.glob("*.json")):
        recs[p.stem] = _load(p)
    order = sorted(recs)                                   # id order == string order (zero-padded)
    processed, rejected, running = {}, {}, 0.0
    for iid in order:
        raw = recs[iid]
        kind = raw.get("kind", "invoice")
        if kind == "credit_note":
            target = raw.get("applies_to")
            if target in processed:                         # target accepted earlier
                amount = round(_line_amount(raw) if "amount" not in raw else raw["amount"], 2)
                running = round(running - amount, 2)
                rec = {**raw, "running_total": running}
                processed[iid] = rec
            else:
                rejected[iid] = f"dangling credit reference to {target}"
            continue
        # invoice
        if raw.get("currency") not in VALID_CCY:
            rejected[iid] = "invalid currency"
            continue
        rec = {**raw, "line_items": [dict(li) for li in raw["line_items"]]}
        if not DATE_ISO.match(rec.get("date", "")):
            d = rec["date"].split("-")
            if len(d) == 3 and len(d[0]) != 4:
                rec["date"] = f"{d[2]}-{d[1]}-{d[0]}"
        if "amount" not in rec:
            rec["amount"] = _line_amount(raw)
        running = round(running + rec["amount"], 2)
        rec["running_total"] = running
        processed[iid] = rec
    ledger = {"processed": len(processed), "rejected": len(rejected),
              "total_amount": round(running, 2)}
    return processed, rejected, ledger


def _rec_matches(got: dict, exp: dict) -> bool:
    keys = set(exp) | set(got)
    for k in keys:
        if k not in got or k not in exp:
            return False
        a, b = got[k], exp[k]
        if isinstance(b, float) or isinstance(a, float):
            try:
                if abs(float(a) - float(b)) > 0.01:
                    return False
            except (TypeError, ValueError):
                return False
        elif a != b:
            return False
    return True


# ----------------------------------------------------------------------------- verifier
def verify_recon(work_dir: Path) -> tuple[int, list[str]]:
    w = Path(work_dir)
    inbox = w / "inbox"
    exp_proc, exp_rej, exp_ledger = solve(inbox)
    ids = sorted(p.stem for p in inbox.glob("*.json"))
    proc = {p.stem: p for p in (w / "processed").glob("*.json")}
    rej = {p.stem: p for p in (w / "rejected").glob("*.json")}
    acc = set(proc) | set(rej)
    v, score = [], 0

    # 40 — accounting: every id disposed exactly once
    if set(ids) == acc and len(ids) == len(acc) and not (set(proc) & set(rej)):
        score += 40
    else:
        if set(ids) - acc:
            v.append(f"Missing: {sorted(set(ids) - acc)[:8]}")
        if acc - set(ids):
            v.append(f"Unknown: {sorted(acc - set(ids))[:8]}")
        if set(proc) & set(rej):
            v.append(f"Dupes: {sorted(set(proc) & set(rej))[:8]}")

    # 25 — processed correctness (repairs + running_total cascade)
    bad = []
    for iid, ep in exp_proc.items():
        if iid not in proc:
            bad.append(iid)
        elif not _rec_matches(_load(proc[iid]), ep):
            bad.append(iid)
    if not bad and set(proc) == set(exp_proc):
        score += 25
    elif bad:
        v.append(f"Processed wrong ({len(bad)}): {sorted(bad)[:8]}")
    else:
        v.append(f"Processed set mismatch: extra {sorted(set(proc) - set(exp_proc))[:8]}")

    # 15 — rejections correct (right set, with reasons)
    rok = set(rej) == set(exp_rej)
    if not rok:
        v.append(f"Rejected set mismatch: want {sorted(exp_rej)[:6]}, got {sorted(rej)[:6]}")
    for iid in exp_rej:
        if iid in rej and "reason" not in _load(rej[iid]):
            rok = False
            v.append(f"{iid} missing reason")
    if rok:
        score += 15

    # 15 — ledger matches final canonical state
    ledger_p = w / "ledger.json"
    if ledger_p.exists():
        lg = _load(ledger_p)
        if (lg.get("processed") == exp_ledger["processed"]
                and lg.get("rejected") == exp_ledger["rejected"]
                and abs(lg.get("total_amount", -1e9) - exp_ledger["total_amount"]) < 0.01):
            score += 15
        else:
            v.append(f"Ledger mismatch: want {exp_ledger}, got {lg}")
    else:
        v.append("ledger.json missing")

    # 5 — inbox untouched
    meta_p = w / "meta.json"
    baseline = json.loads(meta_p.read_text()).get("inbox_hashes", {}) if meta_p.exists() else {}
    if not baseline:
        baseline = {p.name: _hash(p) for p in sorted(inbox.glob("*.json"))}
    modified = [f for f, h in baseline.items() if not (inbox / f).exists() or _hash(inbox / f) != h]
    invented = [p.name for p in inbox.glob("*.json") if p.name not in baseline]
    if modified:
        v.append(f"inbox/ modified: {sorted(modified)[:6]}")
    if invented:
        v.append(f"inbox/ invented: {sorted(invented)[:6]}")
    if baseline and not modified and not invented:
        score += 5

    return score, v


if __name__ == "__main__":
    import sys, shutil, tempfile
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    d = Path(tempfile.mkdtemp())
    generate_recon(d, n)
    ep, er, el = solve(d / "inbox")
    for iid, rec in ep.items():
        (d / "processed" / f"{iid}.json").write_text(json.dumps(rec))
    for iid, reason in er.items():
        raw = _load(d / "inbox" / f"{iid}.json")
        (d / "rejected" / f"{iid}.json").write_text(json.dumps({**raw, "reason": reason}))
    (d / "ledger.json").write_text(json.dumps(el))
    s, viol = verify_recon(d)
    print(f"n={n}  spec-perfect score = {s}/100  (processed={el['processed']} rejected={el['rejected']} total={el['total_amount']})")
    for x in viol:
        print("  -", x)
    shutil.rmtree(d, ignore_errors=True)
