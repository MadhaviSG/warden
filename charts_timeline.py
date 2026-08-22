"""Monitor drift-score timeline chart for a run."""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def timeline(run_id: str, out_path: str):
    meta = json.loads((Path(__file__).parent / "runs" / run_id / "meta.json").read_text())
    events = meta.get("monitor_events", [])
    if not events:
        print("No monitor events")
        return
    steps = [e["step"] for e in events]
    scores = [e["score"] for e in events]
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(steps, scores, "o-", color="#3498db", linewidth=2, markersize=10)
    ax.axhline(60, color="#e74c3c", linestyle="--", label="Threshold (60)")
    fault_step = 18
    for line in (Path(__file__).parent / "runs" / run_id / "trace.jsonl").read_text().splitlines():
        e = json.loads(line)
        if "fault_injected" in e:
            fault_step = e["step"]
    ax.axvline(fault_step, color="#f39c12", linestyle=":", linewidth=2, label=f"Fault (step {fault_step})")
    iv = [e["step"] for e in events if e.get("score", 0) >= 60]
    for s in iv:
        ax.axvline(s, color="#2ecc71", linestyle="-.", linewidth=2, alpha=0.7)
    if iv:
        ax.plot([], [], color="#2ecc71", linestyle="-.", label="Intervention")
    ax.set_xlabel("Agent Step", fontsize=14)
    ax.set_ylabel("Drift Score", fontsize=14)
    ax.set_title(f"Warden Drift Timeline — {run_id}", fontsize=16)
    ax.legend(fontsize=12)
    ax.set_ylim(-5, 105)
    ax.tick_params(labelsize=12)
    plt.tight_layout()
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"Saved {out_path}")


if __name__ == "__main__":
    rid = sys.argv[1] if len(sys.argv) > 1 else "R3_warden_v4"
    timeline(rid, f"charts/timeline_{rid}.png")
