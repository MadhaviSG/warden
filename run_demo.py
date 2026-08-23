"""Orchestrate demo runs and update charts + demo_state.json."""
import json
from pathlib import Path

from agent import run_agent
from charts import bar_chart
from faults import make_fault
from monitors import WardenMonitor, NaiveMonitor, GateOnlyMonitor

ROOT = Path(__file__).parent
STATE = ROOT / "demo_state.json"
REPEATS = 3  # P6: n>=3 per arm (budget/time constrained)


def _save_state(state: dict):
    STATE.write_text(json.dumps(state, indent=2))


def _load_state() -> dict:
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {"runs": {}, "repeats": {}}


def _chart(state: dict):
    runs = state["runs"]
    labels, scores = [], []
    for key, label in [("R1", "clean"), ("R2", "faulted-unmonitored"), ("R3", "faulted+Warden"),
                       ("R4", "adversary+naive"), ("R5", "adversary+Warden"),
                       ("R6", "clean+Warden"), ("R7", "fault+gate-only")]:
        if key in runs:
            labels.append(label)
            scores.append(runs[key]["score"])
    if labels:
        bar_chart(labels, scores, str(ROOT / "charts" / "results.png"))


def _run_with_repeats(arm: str, fn, run_id_base: str) -> dict:
    scores, steps_list, metas = [], [], []
    for k in range(REPEATS):
        rid = f"{run_id_base}_rep{k}"
        meta = fn(rid)
        scores.append(meta["verifier_score"])
        steps_list.append(meta["steps"])
        metas.append(meta)
    state = _load_state()
    state["repeats"][arm] = [{"run_id": f"{run_id_base}_rep{k}", "score": scores[k], "steps": steps_list[k]}
                             for k in range(REPEATS)]
    state["runs"][arm] = {
        "run_id": f"{run_id_base}_rep0",
        "score": sum(scores) / len(scores),
        "score_min": min(scores),
        "score_max": max(scores),
        "steps": sum(steps_list) / len(steps_list),
        "label": arm,
        "n": REPEATS,
    }
    _save_state(state)
    _chart(state)
    return metas[-1]


def run_clean(run_id="R1_clean"):
    meta = run_agent(run_id)
    state = _load_state()
    state["runs"]["R1"] = {"run_id": run_id, "score": meta["verifier_score"],
                           "steps": meta["steps"], "label": "clean"}
    _save_state(state)
    _chart(state)
    return meta


def run_clean_warden(run_id="R6_clean_warden"):
    return _run_with_repeats("R6", lambda rid: run_agent(rid, monitor=WardenMonitor()), run_id)


def run_fault(run_id="R2_fault"):
    meta = run_agent(run_id, fault=make_fault("F1"))
    state = _load_state()
    state["runs"]["R2"] = {"run_id": run_id, "score": meta["verifier_score"],
                           "steps": meta["steps"], "label": "faulted-unmonitored"}
    _save_state(state)
    _chart(state)
    return meta


def run_fault_gate(run_id="R7_fault_gate"):
    return _run_with_repeats("R7", lambda rid: run_agent(rid, fault=make_fault("F1"), monitor=GateOnlyMonitor()), run_id)


def run_warden(run_id="R3_warden"):
    meta = run_agent(run_id, fault=make_fault("F1"), monitor=WardenMonitor())
    state = _load_state()
    state["runs"]["R3"] = {"run_id": run_id, "score": meta["verifier_score"],
                           "steps": meta["steps"], "label": "faulted+Warden",
                           "monitor_events": meta["monitor_events"]}
    _save_state(state)
    _chart(state)
    return meta


def run_adversary_naive(run_id="R4_adv_naive"):
    meta = run_agent(run_id, monitor=NaiveMonitor(), adversarial=True, max_steps=20)
    state = _load_state()
    state["runs"]["R4"] = {"run_id": run_id, "score": meta["verifier_score"],
                           "steps": meta["steps"], "label": "adversary+naive",
                           "monitor_events": meta["monitor_events"]}
    _save_state(state)
    _chart(state)
    return meta


def run_adversary_warden(run_id="R5_adv_warden"):
    meta = run_agent(run_id, monitor=WardenMonitor(), adversarial=True, max_steps=20)
    state = _load_state()
    state["runs"]["R5"] = {"run_id": run_id, "score": meta["verifier_score"],
                           "steps": meta["steps"], "label": "adversary+Warden",
                           "monitor_events": meta["monitor_events"]}
    _save_state(state)
    _chart(state)
    return meta


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    cmds = {"clean": run_clean, "clean_warden": run_clean_warden, "fault": run_fault,
            "fault_gate": run_fault_gate, "warden": run_warden,
            "adv_naive": run_adversary_naive, "adv_warden": run_adversary_warden}
    if cmd == "all":
        for fn in [run_clean, run_fault, run_warden]:
            print(fn.__name__, fn())
    elif cmd in cmds:
        print(cmds[cmd]())
    else:
        print(f"Usage: python run_demo.py [{'|'.join(cmds)}|all]")
