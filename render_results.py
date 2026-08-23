"""Regenerate README results tables from demo_state.json and sweep_results.json."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).parent
README = ROOT / "README.md"
STATE = ROOT / "demo_state.json"
SWEEP = ROOT / "sweep_results.json"
MARKER_START = "<!-- RESULTS:START -->"
MARKER_END = "<!-- RESULTS:END -->"
SWEEP_START = "<!-- SWEEP:START -->"
SWEEP_END = "<!-- SWEEP:END -->"


def render_table(state: dict) -> str:
    rows = []
    for key in ("R1", "R2", "R3", "R4", "R5", "R6", "R7"):
        if key not in state.get("runs", {}):
            continue
        r = state["runs"][key]
        score = r.get("score")
        if isinstance(score, float):
            score_str = f"{score:.0f}" if score == int(score) else f"{score:.1f}"
            if r.get("score_min") is not None:
                score_str = f"{score_str} ({r['score_min']}-{r['score_max']}, n={r.get('n', 1)})"
        else:
            score_str = str(score)
        rows.append(f"| {key} | {r.get('label', key)} | {score_str} | {r.get('steps', '—')} |")
    if not rows:
        return "| Run | Type | Verifier Score | Steps |\n|-----|------|---------------|-------|\n| (no runs) | — | — | — |"
    hdr = "| Run | Type | Verifier Score | Steps |\n|-----|------|---------------|-------|"
    return hdr + "\n" + "\n".join(rows)


def render_sweep_table(sweep: dict) -> str:
    results = sweep.get("results", {})
    if not results:
        return ("| Arm | N | Mean Score | Min | Max | Mean Steps |\n"
                "|-----|---|------------|-----|-----|------------|\n"
                "| (no sweep) | — | — | — | — | — |")
    hdr = "| Arm | N | Mean Score | Min | Max | Mean Steps |\n|-----|---|------------|-----|-----|------------|"
    rows = []
    for key in sorted(results, key=lambda k: (results[k]["arm"], results[k]["n"])):
        r = results[key]
        steps = r.get("steps_mean")
        steps_str = f"{steps:.0f}" if isinstance(steps, (int, float)) else "—"
        rows.append(
            f"| {r['arm']} | {r['n']} | {r['score_mean']} | {r['score_min']} | "
            f"{r['score_max']} | {steps_str} |"
        )
    return hdr + "\n" + "\n".join(rows)


def _replace_block(text: str, start: str, end: str, body: str) -> str:
    if start in text and end in text:
        return re.sub(rf"{re.escape(start)}.*?{re.escape(end)}",
                      f"{start}\n{body}\n{end}", text, flags=re.S)
    return text + f"\n\n{start}\n{body}\n{end}\n"


def main():
    state = json.loads(STATE.read_text()) if STATE.exists() else {"runs": {}}
    sweep = json.loads(SWEEP.read_text()) if SWEEP.exists() else {"results": {}}
    table = render_table(state)
    sweep_table = render_sweep_table(sweep)
    text = README.read_text()
    text = _replace_block(text, MARKER_START, MARKER_END, table)
    text = _replace_block(text, SWEEP_START, SWEEP_END, sweep_table)
    README.write_text(text)
    print("=== Demo runs ===")
    print(table)
    print("\n=== Horizon sweep ===")
    print(sweep_table)


if __name__ == "__main__":
    main()
