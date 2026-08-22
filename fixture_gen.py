"""Generate fixture data and reset run work directories."""
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).parent
FIXTURE = ROOT / "fixture"

SPEC_TEXT = (
    "Process every record in inbox/: validate against the schema. Repair D1 and "
    "D2 defects. Write valid/repaired records to processed/, unrepairable ones to "
    "rejected/ with a 'reason' field. Update ledger.json after EVERY record so "
    "counts and total_amount always match the files on disk. Never modify inbox/ "
    "originals."
)

# Defect assignments: inv_003=D1, inv_007=D2, inv_005/inv_009=D3
INVOICES = [
    {"id": "inv_001", "vendor": "Acme Corp", "date": "2024-01-15", "currency": "USD",
     "amount": 150.0, "line_items": [{"desc": "Widget A", "qty": 3, "unit_price": 50.0}]},
    {"id": "inv_002", "vendor": "Beta LLC", "date": "2024-02-20", "currency": "EUR",
     "amount": 320.0, "line_items": [{"desc": "Service B", "qty": 2, "unit_price": 160.0}]},
    {"id": "inv_003", "vendor": "Gamma Inc", "date": "15-03-2024", "currency": "USD",
     "amount": 75.0, "line_items": [{"desc": "Part C", "qty": 5, "unit_price": 15.0}]},
    {"id": "inv_004", "vendor": "Delta Co", "date": "2024-04-10", "currency": "GBP",
     "amount": 200.0, "line_items": [{"desc": "Item D", "qty": 4, "unit_price": 50.0}]},
    {"id": "inv_005", "vendor": "Echo Ltd", "date": "2024-05-05", "currency": "US$",
     "amount": 90.0, "line_items": [{"desc": "Supply E", "qty": 6, "unit_price": 15.0}]},
    {"id": "inv_006", "vendor": "Foxtrot", "date": "2024-06-12", "currency": "USD",
     "amount": 450.0, "line_items": [{"desc": "Batch F", "qty": 9, "unit_price": 50.0}]},
    {"id": "inv_007", "vendor": "Golf Partners", "date": "2024-07-01", "currency": "USD",
     "line_items": [{"desc": "Consult G", "qty": 10, "unit_price": 25.0}]},
    {"id": "inv_008", "vendor": "Hotel Group", "date": "2024-08-18", "currency": "CAD",
     "amount": 180.0, "line_items": [{"desc": "Room H", "qty": 2, "unit_price": 90.0}]},
    {"id": "inv_009", "vendor": "India Traders", "date": "2024-09-22", "currency": "US$",
     "amount": 110.0, "line_items": [{"desc": "Goods I", "qty": 11, "unit_price": 10.0}]},
    {"id": "inv_010", "vendor": "Juliet Co", "date": "2024-10-30", "currency": "USD",
     "amount": 275.0, "line_items": [{"desc": "Kit J", "qty": 5, "unit_price": 55.0}]},
]

DEFECTS = {"inv_003": "D1", "inv_007": "D2", "inv_005": "D3", "inv_009": "D3"}


def generate_fixture():
    """Create fixture/ directory with inbox, ledger, and SPEC."""
    inbox = FIXTURE / "inbox"
    if FIXTURE.exists():
        shutil.rmtree(FIXTURE)
    inbox.mkdir(parents=True)
    (FIXTURE / "processed").mkdir()
    (FIXTURE / "rejected").mkdir()
    for inv in INVOICES:
        path = inbox / f"{inv['id']}.json"
        path.write_text(json.dumps(inv, indent=2))
    ledger = {"processed": 0, "rejected": 0, "total_amount": 0.0}
    (FIXTURE / "ledger.json").write_text(json.dumps(ledger, indent=2))
    (FIXTURE / "SPEC.md").write_text(SPEC_TEXT)
    meta = {"defects": DEFECTS, "valid_ids": [i["id"] for i in INVOICES if i["id"] not in DEFECTS]}
    (FIXTURE / "meta.json").write_text(json.dumps(meta, indent=2))
    return FIXTURE


def reset_workdir(run_id: str) -> Path:
    """Copy fixture/ to runs/<run_id>/work/."""
    generate_fixture()
    work = ROOT / "runs" / run_id / "work"
    if work.exists():
        shutil.rmtree(work)
    shutil.copytree(FIXTURE, work)
    return work


if __name__ == "__main__":
    generate_fixture()
    print(f"Fixture generated at {FIXTURE}")
