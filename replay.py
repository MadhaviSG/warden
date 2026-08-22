"""Pretty-print trace.jsonl with monitor events highlighted."""
import json
import sys
from pathlib import Path


def replay(run_id: str):
    trace = Path(__file__).parent / "runs" / run_id / "trace.jsonl"
    if not trace.exists():
        print(f"No trace at {trace}")
        return
    print(f"\n=== Replay: {run_id} ===\n")
    for line in trace.read_text().splitlines():
        if not line.strip():
            continue
        e = json.loads(line)
        if "monitor_check" in e:
            mc = e["monitor_check"]
            print(f"  *** MONITOR step={mc.get('step')} score={mc.get('score')} "
                  f"reason={mc.get('reason', '')[:80]}")
        elif "fault_injected" in e:
            print(f"  !!! FAULT {e['fault_injected']} injected at step {e['step']}")
        elif "step" in e:
            tool = e.get("tool", e.get("error", "?"))
            args = e.get("args", {})
            snippet = e.get("result_snippet", "")[:60]
            print(f"  step {e['step']:>2}: {tool} {args} -> {snippet}")
    print()


if __name__ == "__main__":
    rid = sys.argv[1] if len(sys.argv) > 1 else "R3_warden_v4"
    replay(rid)
