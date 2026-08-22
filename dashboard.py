"""Actor-critic mission control: dual live runs, fault injection, task launcher."""
import json
import re
import threading
from datetime import datetime
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from agent import run_agent
from faults import make_fault
from fixture_gen import ensure_snapshot
from monitors import WardenMonitor
from redteam import list_attacks, run_attacker
from tasks import PREFILLED_FAULTS, TASKS

ROOT = Path(__file__).parent
RUNS_DIR = ROOT / "runs"
STATIC = ROOT / "static"
RUN_ID_RE = re.compile(r"^[A-Za-z0-9_]{1,64}$")
_lock = threading.Lock()
_live = {
    "left": {"running": False, "run_id": None, "done": False, "warden": False, "task": "T1"},
    "right": {"running": False, "run_id": None, "done": False, "warden": False, "task": "T1"},
}


def _resolve_run_dir(run_id: str) -> Path | None:
    if not run_id or not RUN_ID_RE.match(run_id):
        return None
    rd = (RUNS_DIR / run_id).resolve()
    if not str(rd).startswith(str(RUNS_DIR.resolve())):
        return None
    return rd


def _run_bg(run_id: str, column: str, warden: bool, fault, task: str, custom_goal: str | None):
    try:
        run_agent(run_id, fault=fault, monitor=WardenMonitor() if warden else None,
                  task=task, custom_goal=custom_goal)
    finally:
        with _lock:
            _live[column]["running"] = False
            _live[column]["done"] = True


def launch(column: str, warden: bool, fault_name: str | None, task: str = "T1",
           custom_goal: str | None = None) -> dict:
    column = column if column in ("left", "right") else "left"
    with _lock:
        if _live[column]["running"]:
            return {"error": "busy", "status": 409, "column": column}
        tag = "warden" if warden else "solo"
        run_id = f"live_{datetime.now().strftime('%H%M%S')}_{tag}"
        _live[column].update(running=True, run_id=run_id, done=False, warden=warden, task=task)
    fault = make_fault(fault_name) if fault_name else None
    threading.Thread(target=_run_bg, args=(run_id, column, warden, fault, task, custom_goal),
                     daemon=True).start()
    return {"run_id": run_id, "column": column}


def launch_race(task: str = "T1", fault_name: str = "F1", custom_goal: str | None = None) -> dict:
    with _lock:
        if _live["left"]["running"] or _live["right"]["running"]:
            return {"error": "busy", "status": 409}
    left = launch("left", warden=False, fault_name=fault_name, task=task, custom_goal=custom_goal)
    right = launch("right", warden=True, fault_name=fault_name, task=task, custom_goal=custom_goal)
    return {"left": left, "right": right}


def inject_fault(run_id: str, message: str) -> dict:
    rd = _resolve_run_dir(run_id)
    if not rd:
        return {"error": "invalid run_id", "status": 400}
    with _lock:
        running = any(_live[c]["running"] and _live[c]["run_id"] == run_id for c in ("left", "right"))
    if not running:
        return {"error": "run not running", "status": 409}
    if not rd.exists():
        return {"error": "run not found", "status": 404}
    with open(rd / "inject.jsonl", "a") as f:
        f.write(json.dumps({"msg": message}) + "\n")
    return {"ok": True, "run_id": run_id}


def start_redteam(run_id: str) -> dict:
    rd = _resolve_run_dir(run_id)
    if not rd:
        return {"error": "invalid run_id", "status": 400}
    with _lock:
        running = any(_live[c]["running"] and _live[c]["run_id"] == run_id for c in ("left", "right"))
    if not running:
        return {"error": "run not running", "status": 409}
    return run_attacker(run_id)


def status() -> dict:
    with _lock:
        return {"left": dict(_live["left"]), "right": dict(_live["right"])}


def list_runs() -> list:
    out = []
    if not RUNS_DIR.exists():
        return out
    for d in sorted(RUNS_DIR.iterdir()):
        if d.name.startswith("_"):
            continue
        meta = d / "meta.json"
        if meta.exists():
            m = json.loads(meta.read_text())
            out.append({
                "run_id": d.name,
                "verifier_score": m.get("verifier_score"),
                "score_label": m.get("score_label"),
                "steps": m.get("steps"),
                "monitor": m.get("monitor"),
                "fault": m.get("fault"),
                "task": m.get("task"),
                "live": d.name.startswith("live_"),
            })
    return out


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def _json(self, code: int, obj: dict):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n)) if n else {}

    def _require_local(self) -> bool:
        return self.headers.get("X-Warden-Local") == "1"

    def _serve_static(self, path: str):
        rel = path.lstrip("/") or "index.html"
        fp = (STATIC / rel).resolve()
        if not fp.exists() or not str(fp).startswith(str(STATIC.resolve())):
            self.send_error(404)
            return
        ct = "text/html" if fp.suffix == ".html" else "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ct)
        self.end_headers()
        self.wfile.write(fp.read_bytes())

    def do_GET(self):
        path = urlparse(self.path).path
        qs = parse_qs(urlparse(self.path).query)
        if path == "/api/status":
            return self._json(200, status())
        if path == "/api/runs":
            return self._json(200, list_runs())
        if path == "/api/tasks":
            return self._json(200, {"tasks": TASKS, "faults": {k: v[:80] + "…" for k, v in PREFILLED_FAULTS.items()}})
        if path == "/api/meta":
            rid = qs.get("run_id", [None])[0]
            rd = _resolve_run_dir(rid) if rid else None
            p = rd / "meta.json" if rd else None
            if not p or not p.exists():
                return self._json(400 if rid and not rd else 404, {"error": "not found"})
            return self._json(200, json.loads(p.read_text()))
        if path == "/api/trace":
            rid = qs.get("run_id", [None])[0]
            rd = _resolve_run_dir(rid) if rid else None
            if rid and not rd:
                return self._json(400, {"error": "invalid run_id"})
            p = rd / "trace.jsonl" if rd else None
            body = p.read_text() if p and p.exists() else ""
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
            self.end_headers()
            self.wfile.write(body.encode())
            return
        if path == "/api/attacks":
            rid = qs.get("run_id", [None])[0]
            rd = _resolve_run_dir(rid) if rid else None
            if not rid or not rd:
                return self._json(400, {"error": "invalid run_id"})
            return self._json(200, {"attacks": list_attacks(rid)})
        if path == "/api/incidents":
            rid = qs.get("run_id", [None])[0]
            rd = _resolve_run_dir(rid) if rid else None
            if not rid or not rd:
                return self._json(400, {"error": "invalid run_id"})
            inc_p = rd / "incidents.jsonl"
            incidents = []
            if inc_p.exists():
                for line in inc_p.read_text().strip().split("\n"):
                    if line:
                        try:
                            incidents.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
            return self._json(200, {"incidents": incidents, "count": len(incidents)})
        return self._serve_static(path)

    def do_POST(self):
        if not self._require_local():
            return self._json(403, {"error": "X-Warden-Local header required"})
        path = urlparse(self.path).path
        body = self._read_json()
        if path == "/api/launch":
            col = body.get("column", "left")
            r = launch(col, bool(body.get("warden")), body.get("fault") or None,
                       body.get("task", "T1"), body.get("custom_goal"))
            if r.get("status") == 409:
                return self._json(409, r)
            return self._json(200, r)
        if path == "/api/race":
            r = launch_race(body.get("task", "T1"), body.get("fault", "F1"), body.get("custom_goal"))
            if r.get("status") == 409:
                return self._json(409, r)
            return self._json(200, r)
        if path == "/api/inject":
            r = inject_fault(body.get("run_id", ""), body.get("message", ""))
            if r.get("status") in (400, 409, 404):
                return self._json(r["status"], r)
            return self._json(200, r)
        if path == "/api/redteam":
            r = start_redteam(body.get("run_id", ""))
            if r.get("status") in (400, 409, 404):
                return self._json(r["status"], r)
            return self._json(200, r)
        return self.send_error(404)


def main():
    ensure_snapshot()
    port = 8765
    print(f"WARDEN dashboard http://127.0.0.1:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
