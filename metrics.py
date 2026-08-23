"""Aggregate run metrics from demo_state.json and run traces."""
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent


def _parse_ts(ts: str) -> datetime | None:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _parse_check(entry: dict) -> dict | None:
    mc = entry.get("monitor_check")
    if isinstance(mc, dict):
        return mc
    if isinstance(mc, str):
        try:
            return json.loads(mc)
        except json.JSONDecodeError:
            return None
    return None


def _read_trace(run_dir: Path) -> tuple[list[dict], list[dict], int | None, float | None]:
    p = run_dir / "trace.jsonl"
    if not p.exists():
        return [], [], None, None
    lines, checks, fault_step, t0, t1 = [], [], None, None, None
    for line in p.read_text().strip().splitlines():
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        lines.append(entry)
        if "fault_injected" in entry:
            fault_step = entry.get("step")
        chk = _parse_check(entry)
        if chk:
            checks.append(chk)
        ts = entry.get("ts") or (chk or {}).get("ts")
        if ts and (t := _parse_ts(ts)):
            t0 = t if t0 is None else min(t0, t)
            t1 = t if t1 is None else max(t1, t)
    wall = (t1 - t0).total_seconds() if t0 and t1 else None
    return lines, checks, fault_step, wall


def compute_run(key: str, info: dict) -> dict:
    run_dir = ROOT / "runs" / info["run_id"]
    meta = json.loads((run_dir / "meta.json").read_text()) if (run_dir / "meta.json").exists() else {}
    _, checks, fault_step, wall = _read_trace(run_dir)
    interventions = [c for c in checks if c.get("score", 0) >= 60]
    detect_step = interventions[0]["step"] if interventions else None
    lat_steps = (detect_step - fault_step) if detect_step and fault_step else None
    lat_s = None
    if detect_step and fault_step:
        fs = next((c.get("ts") for c in checks if c.get("step") == detect_step), None)
        ft = next((l.get("ts") for l in _read_trace(run_dir)[0] if l.get("step") == fault_step), None)
        if fs and ft and (a := _parse_ts(fs)) and (b := _parse_ts(ft)):
            lat_s = (a - b).total_seconds()
    if fault_step is None:
        fps = len(interventions)
    else:
        fps = sum(1 for c in checks if c.get("score", 0) >= 60 and c.get("step", 0) < fault_step)
    return {"run": key, "run_id": info["run_id"], "verifier_score": meta.get("verifier_score"),
            "steps": meta.get("steps"), "wall_clock_s": wall, "monitor_checks": len(checks),
            "interventions": len(interventions), "fault_step": fault_step, "detect_step": detect_step,
            "detect_latency_steps": lat_steps, "detect_latency_s": lat_s, "false_positives": fps,
            "violations": len(meta.get("violations", []))}


def _fmt(v, w=8):
    if v is None:
        return f"{'—':>{w}}"
    if isinstance(v, float):
        return f"{v:>{w}.1f}"
    return f"{v!s:>{w}}"


def main():
    state = json.loads((ROOT / "demo_state.json").read_text())
    rows = [compute_run(k, v) for k, v in state.get("runs", {}).items()]
    cols = ["run", "verifier_score", "steps", "wall_clock_s", "monitor_checks", "interventions",
            "fault_step", "detect_step", "detect_latency_steps", "false_positives", "violations"]
    widths = {c: max(len(c), max(len(_fmt(r.get(c)).strip()) for r in rows)) for c in cols}
    hdr = " ".join(c.rjust(widths[c]) for c in cols)
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        print(" ".join(_fmt(r.get(c), widths[c]) for c in cols))
    out = ROOT / "metrics.json"
    out.write_text(json.dumps(rows, indent=2))
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
