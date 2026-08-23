"""Dashboard security validation tests — no network server."""
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from dashboard import Handler, RUN_ID_RE, _resolve_run_dir, MAX_BODY


def test_run_id_regex_rejects_traversal():
    assert RUN_ID_RE.match("live_123_solo")
    assert not RUN_ID_RE.match("../etc")
    assert not RUN_ID_RE.match("/etc")


def test_resolve_run_dir_blocks_escape(tmp_path, monkeypatch):
    import dashboard
    monkeypatch.setattr(dashboard, "RUNS_DIR", tmp_path / "runs")
    (tmp_path / "runs").mkdir()
    assert _resolve_run_dir("valid_run_1") is not None
    assert _resolve_run_dir("../../etc") is None


def _handler_with_headers(headers: dict):
    h = Handler.__new__(Handler)
    h.headers = headers
    h.rfile = MagicMock()
    return h


def test_post_rejects_foreign_origin():
    h = _handler_with_headers({"Host": "127.0.0.1:8765", "Origin": "http://evil.example"})
    assert h._allowed_origin() is False


def test_post_rejects_missing_origin():
    h = _handler_with_headers({"Host": "127.0.0.1:8765"})
    assert h._allowed_origin() is False


def test_read_json_body_cap():
    h = _handler_with_headers({"Content-Length": str(MAX_BODY + 1)})
    with pytest.raises(ValueError):
        h._read_json()
