"""Horizon sweep: measure verifier score vs task length, solo vs Warden.

Produces the data behind the drift-free-horizon chart. Runs each (arm, N)
several times and aggregates mean / min / max. Real runs need OPENAI_API_KEY
(or ANTHROPIC_API_KEY) and AGENT_MODEL / JUDGE_MODEL set.

    python sweep.py --dry-run                 # validate pipeline, no LLM calls, cost estimate
    python sweep.py --n 25,50,100,200 --reps 3 --fault F1 --yes

Writes sweep_results.json (aggregates) and per-run artifacts under
runs/sweep_<arm>_n<N>_r<k>/. The dashboard reads sweep_results.json for the
horizon chart.
"""
import argparse
import json
import statistics
import time
from pathlib import Path

ROOT = Path(__file__).parent
OUT = ROOT / "sweep_results.json"

# N -> recon task id; any N maps to R{n} via tasks.setup_task
_TASK_FOR_N = {25: "R25", 50: "R50", 100: "R100", 200: "R200"}


def _task_for(n: int) -> str:
    return _TASK_FOR_N.get(n, f"R{n}")


def _ensure_task(n: int):
    """Register an ad-hoc recon task id (RN) so any N is runnable."""
    from tasks import TASKS
    tid = _task_for(n)
    if tid not in TASKS:
        TASKS[tid] = {"label": f"reconciliation n={n}", "deterministic": True,
                      "max_steps": max(80, n * 4 + 40), "n": n}
    return tid


def _horizon_chart(results: dict, path: Path):
    """Score vs N line chart: solo vs warden from sweep_results."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ns = sorted({r["n"] for r in results.values()})
    if not ns:
        return
    solo, warden = [], []
    for n in ns:
        solo.append(results.get(f"solo_n{n}", {}).get("score_mean"))
        warden.append(results.get(f"warden_n{n}", {}).get("score_mean"))
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(ns, solo, "o-", color="#e74c3c", linewidth=2, markersize=8, label="solo")
    ax.plot(ns, warden, "s-", color="#3498db", linewidth=2, markersize=8, label="warden")
    ax.set_xlabel("Horizon N (records)", fontsize=13)
    ax.set_ylabel("Verifier score", fontsize=13)
    ax.set_title("Drift-free horizon: score vs task length", fontsize=15, fontweight="bold")
    ax.set_ylim(0, 105)
    ax.legend(fontsize=12)
    ax.grid(True, alpha=0.3)
    for x, ys, yw in zip(ns, solo, warden):
        if ys is not None:
            ax.annotate(f"{ys:.0f}", (x, ys), textcoords="offset points", xytext=(0, 8), ha="center", fontsize=10)
        if yw is not None:
            ax.annotate(f"{yw:.0f}", (x, yw), textcoords="offset points", xytext=(0, -12), ha="center", fontsize=10)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def _estimate_cost(ns, reps) -> float:
    # rough: worker ~ 3 calls/record, judge ~ 1/5 steps; gpt-4o-mini worker + gpt-4o judge
    total = 0.0
    for n in ns:
        steps = n * 3
        worker_tok = steps * 1500            # ctx grows; conservative avg
        judge_tok = (steps / 5) * 1200
        per_run = worker_tok / 1e6 * 0.60 + judge_tok / 1e6 * 5.0   # $/M in+out blended
        total += per_run * reps * 2          # two arms
    return total


def run_sweep(ns, reps, fault_name, dry_run):
    from tasks import task_info
    arms = [("solo", False), ("warden", True)]
    results = {}
    for n in ns:
        tid = _ensure_task(n)
        for arm, warden in arms:
            scores, steps_list = [], []
            for k in range(reps):
                run_id = f"sweep_{arm}_n{n}_r{k}"
                if dry_run:
                    from tasks import setup_task
                    from recon import solve, verify_recon
                    work = setup_task(run_id, tid)
                    # score a spec-perfect solution to prove the pipeline end-to-end
                    ep, er, el = solve(work / "inbox")
                    for iid, rec in ep.items():
                        (work / "processed" / f"{iid}.json").write_text(json.dumps(rec))
                    for iid, reason in er.items():
                        raw = json.loads((work / "inbox" / f"{iid}.json").read_text())
                        (work / "rejected" / f"{iid}.json").write_text(json.dumps({**raw, "reason": reason}))
                    (work / "ledger.json").write_text(json.dumps(el))
                    sc, _ = verify_recon(work)
                    scores.append(sc); steps_list.append(el["processed"] + el["rejected"])
                    import shutil
                    shutil.rmtree(ROOT / "runs" / run_id, ignore_errors=True)
                else:
                    from agent import run_agent
                    fault = None
                    if fault_name and warden is not None:
                        from faults import make_fault
                        try:
                            fault = make_fault(fault_name)
                        except Exception:
                            fault = None
                    from monitors import WardenMonitor
                    t0 = time.time()
                    meta = run_agent(run_id, fault=fault,
                                     monitor=WardenMonitor() if warden else None, task=tid)
                    scores.append(meta["verifier_score"])
                    steps_list.append(meta["steps"])
                    print(f"  {run_id}: score={meta['verifier_score']} steps={meta['steps']} "
                          f"({time.time()-t0:.0f}s)")
            results[f"{arm}_n{n}"] = {
                "arm": arm, "n": n, "reps": reps,
                "score_mean": round(statistics.mean(scores), 1),
                "score_min": min(scores), "score_max": max(scores),
                "scores": scores,
                "steps_mean": round(statistics.mean(steps_list), 1) if steps_list else None,
            }
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", default="25,50,100,200", help="comma-separated record counts")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--fault", default="F1", help="fault to inject on runs (or 'none')")
    ap.add_argument("--dry-run", action="store_true", help="no LLM calls; validate pipeline + estimate cost")
    ap.add_argument("--yes", action="store_true", help="skip the cost confirmation prompt")
    a = ap.parse_args()
    ns = [int(x) for x in a.n.split(",") if x.strip()]
    fault = None if a.fault.lower() == "none" else a.fault

    if a.dry_run:
        print("DRY RUN — no LLM calls. Validating the sweep pipeline with spec-perfect solutions.\n")
    else:
        est = _estimate_cost(ns, a.reps)
        print(f"Planned: N={ns} x {a.reps} reps x 2 arms = {len(ns)*a.reps*2} real runs.")
        print(f"Rough cost estimate: ${est:.2f} (gpt-4o-mini worker + gpt-4o judge).")
        if not a.yes:
            if input("Proceed? [y/N] ").strip().lower() != "y":
                print("Aborted."); return

    results = run_sweep(ns, a.reps, fault, a.dry_run)
    OUT.write_text(json.dumps({"generated": time.strftime("%Y-%m-%d %H:%M"),
                               "fault": fault, "results": results}, indent=2))
    chart_path = ROOT / "static" / "horizon_chart.png"
    _horizon_chart(results, chart_path)

    print(f"\n{'arm':7} {'N':>5} {'mean':>6} {'min':>4} {'max':>4}")
    print("-" * 32)
    for key in sorted(results, key=lambda k: (results[k]["arm"], results[k]["n"])):
        r = results[key]
        print(f"{r['arm']:7} {r['n']:>5} {r['score_mean']:>6} {r['score_min']:>4} {r['score_max']:>4}")
    print(f"\nWrote {OUT}" + ("  (dry-run: spec-perfect baseline, all 100)" if a.dry_run else ""))


if __name__ == "__main__":
    main()
