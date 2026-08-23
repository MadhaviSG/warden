"""Regenerate README results table from demo_state.json."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).parent
README = ROOT / "README.md"
STATE = ROOT / "demo_state.json"
MARKER_START = "<!-- RESULTS:START -->"
MARKER_END = "<!-- RESULTS:END -->"


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


def main():
    state = json.loads(STATE.read_text()) if STATE.exists() else {"runs": {}}
    table = render_table(state)
    text = README.read_text()
    if MARKER_START in text and MARKER_END in text:
        new_text = re.sub(
            rf"{re.escape(MARKER_START)}.*?{re.escape(MARKER_END)}",
            f"{MARKER_START}\n{table}\n{MARKER_END}",
            text,
            flags=re.S,
        )
    else:
        new_text = text + f"\n\n{MARKER_START}\n{table}\n{MARKER_END}\n"
    README.write_text(new_text)
    print(table)


if __name__ == "__main__":
    main()
