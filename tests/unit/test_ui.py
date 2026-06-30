import os
import subprocess
import threading

import pytest

import ui.app as _ui_mod
from shared.io import WebIOHandler

_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture()
def client():
    _ui_mod.app.config["TESTING"] = True
    with _ui_mod.app.test_client() as c:
        yield c


# ── WebIOHandler ──────────────────────────────────────────────────────────────

class TestWebIOHandler:
    def test_output_enqueues_event(self):
        io = WebIOHandler()
        io.output("hello")
        ev = io.get_event(timeout=1.0)
        assert ev == {"type": "output", "text": "hello"}

    def test_prompt_enqueues_prompt_event(self):
        io = WebIOHandler()
        threading.Thread(target=lambda: io.send_input(""), daemon=True).start()
        io.prompt("Question?")
        ev = io.get_event(timeout=1.0)
        assert ev == {"type": "prompt", "text": "Question?"}

    def test_prompt_returns_sent_input(self):
        io = WebIOHandler()
        threading.Thread(target=lambda: io.send_input("my answer"), daemon=True).start()
        val = io.prompt("Q?")
        assert val == "my answer"

    def test_end_enqueues_done(self):
        io = WebIOHandler()
        io.end()
        ev = io.get_event(timeout=1.0)
        assert ev["type"] == "done"

    def test_show_cli_hints_false(self):
        assert WebIOHandler().show_cli_hints is False


# ── Routes ────────────────────────────────────────────────────────────────────

class TestRoutes:
    def test_index_returns_200(self, client):
        r = client.get("/")
        assert r.status_code == 200

    def test_index_has_key_landmarks(self, client):
        body = client.get("/").data.decode()
        assert 'id="user-id"' in body
        assert "/static/style.css" in body
        assert "/static/app.js" in body

    def test_sessions_returns_200(self, client):
        assert client.get("/sessions").status_code == 200

    def test_sessions_user_filter(self, client):
        assert client.get("/sessions?user=nobody").status_code == 200

    def test_sessions_7day_filter(self, client):
        assert client.get("/sessions?days7=1").status_code == 200

    def test_sessions_combined_filter(self, client):
        assert client.get("/sessions?user=nobody&days7=1").status_code == 200

    def test_api_start_returns_session_id(self, client):
        r = client.post("/api/start", json={"user_id": "test"})
        assert r.status_code == 200
        data = r.get_json()
        assert "session_id" in data
        assert len(data["session_id"]) == 36  # UUID4

    def test_api_start_defaults_to_student(self, client):
        r = client.post("/api/start", json={})
        assert r.status_code == 200
        assert "session_id" in r.get_json()

    def test_api_stream_unknown_sid_returns_404(self, client):
        assert client.get("/api/stream/no-such-id").status_code == 404

    def test_api_input_unknown_sid_returns_404(self, client):
        r = client.post("/api/input/no-such-id", json={"text": "hi"})
        assert r.status_code == 404

    def test_session_view_nonexistent_returns_404(self, client):
        assert client.get("/sessions/sessions/no-such-file.yaml").status_code == 404

    def test_session_view_path_traversal_blocked(self, client):
        with _ui_mod.app.test_request_context():
            from flask import request as _req
        # Call the view function directly with a path that escapes data_root
        with _ui_mod.app.test_client() as c:
            r = c.get("/sessions/sessions/%2F..%2F..%2Fetc%2Fpasswd")
            assert r.status_code in (400, 403, 404)


# ── Static assets ─────────────────────────────────────────────────────────────

class TestStaticAssets:
    def test_style_css_served(self, client):
        r = client.get("/static/style.css")
        assert r.status_code == 200
        assert b"--bg:" in r.data

    def test_app_js_served(self, client):
        r = client.get("/static/app.js")
        assert r.status_code == 200
        assert b"startSession" in r.data

    def test_diff_js_served(self, client):
        r = client.get("/static/diff.js")
        assert r.status_code == 200
        assert b"renderDiff" in r.data


# ── JS syntax ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def node_available():
    result = subprocess.run(["node", "--version"], capture_output=True)
    if result.returncode != 0:
        pytest.skip("node not available")


class TestJSSyntax:
    def _check(self, rel_path):
        path = os.path.join(_project_root, rel_path)
        result = subprocess.run(["node", "--check", path], capture_output=True, text=True)
        assert result.returncode == 0, f"{rel_path}: {result.stderr.strip()}"

    def test_app_js_syntax(self, node_available):
        self._check("ui/static/app.js")

    def test_diff_js_syntax(self, node_available):
        self._check("ui/static/diff.js")
