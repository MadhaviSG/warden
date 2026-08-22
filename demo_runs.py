"""Print final results table from demo_state.json (no re-runs)."""
import json
from pathlib import Path

ROOT = Path(__file__).parent
STATE = ROOT / "demo_state.json"


def main():
    if not STATE.exists():
        print("No demo_state.json found. Run run_demo.py first.")
        return
    state = json.loads(STATE.read_text())
    runs = state.get("runs", {})
    print("\n=== WARDEN Demo Results ===\n")
    print(f"{'Run':<6} {'Type':<25} {'Score':<8} {'Steps':<8} {'Run ID'}")
    print("-" * 70)
    for key in ["R1", "R2", "R3", "R4", "R5"]:
        if key not in runs:
            continue
        r = runs[key]
        print(f"{key:<6} {r.get('label', ''):<25} {r.get('score', '?'):<8} "
              f"{r.get('steps', '?'):<8} {r.get('run_id', '')}")
    if (ROOT / "charts" / "results.png").exists():
        print(f"\nChart: charts/results.png")
    print()


if __name__ == "__main__":
    main()
