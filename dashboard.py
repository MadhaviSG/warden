"""Actor-critic mission control: launch live ACTOR runs, toggle CRITIC (Warden)."""
import json
import threading
from datetime import datetime
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from agent import run_agent
from faults import make_fault
from monitors import WardenMonitor

ROOT = Path(__file__).parent
STATIC = ROOT / "static"
_lock = threading.Lock()
_live = {"running": False, "run_id": None, "done": False, "warden": False}


def _run_bg(run_id: str, warden: bool, fault: bool):
    try:
        run_agent(run_id, fault=make_fault("F1") if fault else None,
                  monitor=WardenMonitor() if warden else None)
    finally:
        with _lock:
            _live["running"] = False
            _live["done"] = True


def launch(warden: bool, fault: bool) -> dict:
    with _lock:
        if _live["running"]:
            return {"error": "busy", "status": 409}
        run_id = f"live_{datetime.now().strftime('%H%M%S')}_{'warden' if warden else 'solo'}"
        _live.update(running=True, run_id=run_id, done=False, warden=warden)
    threading.Thread(target=_run_bg, args=(run_id, warden, fault), daemon=True).start()
    return {"run_id": run_id}


def status() -> dict:
    with _lock:
        return {"running": _live["running"], "run_id": _live["run_id"], "done": _live["done"]}


def list_runs() -> list:
    out = []
    runs = ROOT / "runs"
    if not runs.exists():
        return out
    for d in sorted(runs.iterdir()):
        meta = d / "meta.json"
        if meta.exists():
            m = json.loads(meta.read_text())
            out.append({"run_id": d.name, "verifier_score": m.get("verifier_score"),
                        "steps": m.get("steps"), "monitor": m.get("monitor"),
                        "fault": m.get("fault"), "live": d.name.startswith("live_")})
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
        if path == "/api/meta":
            rid = qs.get("run_id", [None])[0]
            p = ROOT / "runs" / rid / "meta.json" if rid else None
            if not p or not p.exists():
                return self._json(404, {"error": "not found"})
            return self._json(200, json.loads(p.read_text()))
        if path == "/api/trace":
            rid = qs.get("run_id", [status().get("run_id")])[0]
            p = ROOT / "runs" / rid / "trace.jsonl" if rid else None
            body = p.read_text() if p and p.exists() else ""
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
            self.end_headers()
            self.wfile.write(body.encode())
            return
        return self._serve_static(path)

    def do_POST(self):
        if urlparse(self.path).path != "/api/launch":
            return self.send_error(404)
        body = self._read_json()
        r = launch(bool(body.get("warden")), body.get("fault", True))
        if r.get("status") == 409:
            return self._json(409, {"error": "run in progress"})
        return self._json(200, r)


def main():
    port = 8765
    print(f"WARDEN dashboard http://localhost:{port}")
    ThreadingHTTPServer(("localhost", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
