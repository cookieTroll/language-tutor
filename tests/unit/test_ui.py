import os
import subprocess
import threading
from unittest.mock import patch, MagicMock

import pytest
import yaml

import ui.app as _ui_mod
from shared.io import TerminalIOHandler, WebIOHandler
from orchestrator.protocols import ExerciseRecommendation

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

    def test_prompt_block_delegates_to_prompt(self):
        io = WebIOHandler()
        threading.Thread(target=lambda: io.send_input("line1\nline2"), daemon=True).start()
        val = io.prompt_block("Answers?")
        assert val == "line1\nline2"
        ev = io.get_event(timeout=1.0)
        assert ev == {"type": "prompt", "text": "Answers?"}

    def test_render_exercises_enqueues_event(self):
        io = WebIOHandler()
        groups = [{"exercise_type": "fill_blank", "instruction": "Fill in the blank.",
                   "exercises": [{"prompt": "Der ___ Mann"}]}]
        io.render_exercises({"groups": groups})
        ev = io.get_event(timeout=1.0)
        assert ev == {
            "type": "data",
            "payload": {"event": "exercises_ready", "groups": groups},
        }

    def test_render_results_enqueues_event(self):
        io = WebIOHandler()
        items = [{"prompt": "p", "user_answer": "a", "correct_answer": "a", "correct": True, "feedback": ""}]
        io.render_results({"items": items, "score": 1.0})
        ev = io.get_event(timeout=1.0)
        assert ev == {
            "type": "data",
            "payload": {"event": "grammar_results_complete", "items": items, "score": 1.0},
        }

    def test_render_progress_enqueues_event(self):
        io = WebIOHandler()
        modules = [{"module": "grammar", "mastery_ratio": 0.5}]
        io.render_progress({"current_level": "a1", "modules": modules, "trend": []})
        ev = io.get_event(timeout=1.0)
        assert ev == {
            "type": "data",
            "payload": {"event": "progress_ready", "current_level": "a1", "modules": modules, "trend": []},
        }


# ── TerminalIOHandler ───────────────────────────────────────────────────────────

class TestTerminalIOHandler:
    def test_prompt_block_reads_until_blank_line(self, monkeypatch, capsys):
        io = TerminalIOHandler()
        lines = iter(["first", "second", ""])
        monkeypatch.setattr("builtins.input", lambda: next(lines))
        result = io.prompt_block("Enter answers:")
        assert result == "first\nsecond"
        assert "Enter answers:" in capsys.readouterr().out

    def test_prompt_block_empty_first_line_returns_empty_string(self, monkeypatch):
        io = TerminalIOHandler()
        monkeypatch.setattr("builtins.input", lambda: "")
        assert io.prompt_block() == ""

    def test_render_exercises_matches_prior_grammar_module_format(self, capsys):
        io = TerminalIOHandler()
        io.render_exercises({"groups": [
            {"exercise_type": "fill_blank", "instruction": None, "exercises": [
                {"prompt": "Der ___ Mann"},
                {"prompt": "Die ___ Frau"},
            ]},
        ]})
        out = capsys.readouterr().out
        assert "1. Der ___ Mann" in out
        assert "2. Die ___ Frau" in out

    def test_render_exercises_empty_list_prints_nothing(self, capsys):
        io = TerminalIOHandler()
        io.render_exercises({"groups": []})
        assert capsys.readouterr().out == ""

    def test_render_exercises_includes_instruction_once_per_group(self, capsys):
        io = TerminalIOHandler()
        io.render_exercises({"groups": [
            {"exercise_type": "true_false", "instruction": "Answer richtig or falsch.", "exercises": [
                {"prompt": "Es ist wichtig, gegen den Wind zu kämpfen."},
                {"prompt": "Der Hund ist blau."},
            ]},
        ]})
        out = capsys.readouterr().out
        assert out.count("Answer richtig or falsch.") == 1
        assert "1. Es ist wichtig" in out
        assert "2. Der Hund ist blau." in out

    def test_render_exercises_numbers_continue_across_groups(self, capsys):
        io = TerminalIOHandler()
        io.render_exercises({"groups": [
            {"exercise_type": "fill_in_the_blank", "instruction": "Fill in the blank.", "exercises": [
                {"prompt": "p1"}, {"prompt": "p2"},
            ]},
            {"exercise_type": "error_correction", "instruction": "Find and fix.", "exercises": [
                {"prompt": "p3"},
            ]},
        ]})
        out = capsys.readouterr().out
        assert "1. p1" in out
        assert "2. p2" in out
        assert "3. p3" in out

    def test_render_results_matches_prior_grammar_module_format(self, capsys):
        io = TerminalIOHandler()
        items = [
            {"prompt": "p1", "user_answer": "a1", "correct_answer": "a1", "correct": True, "feedback": ""},
            {"prompt": "p2", "user_answer": "wrong", "correct_answer": "right", "correct": False, "feedback": "nope"},
        ]
        io.render_results({"items": items, "score": 0.5})
        out = capsys.readouterr().out
        assert "RESULTS" in out
        assert "1. [correct] p1" in out
        assert "2. [incorrect] p2" in out
        assert "Correct answer: right" in out
        assert "Feedback: nope" in out
        assert "Score: 50% (1/2)" in out

    def test_render_progress_shows_bar_and_stats(self, capsys):
        io = TerminalIOHandler()
        io.render_progress({
            "current_level": "a1",
            "modules": [
                {"module": "grammar", "mastery_ratio": 0.5, "topics_mastered": 1, "topics_total": 2,
                 "weak_tags": ["Dative case errors"], "strong_tags": ["Present tense"]},
                {"module": "writing", "mastery_ratio": 0.4, "texts_written": 2, "total_words": 120,
                 "words_at_current_level": 120, "weak_tags": [], "strong_tags": []},
            ],
            "trend": [{"date": "2026-07-01", "level": "a1"}, {"date": "2026-07-02", "level": "a2"}],
        })
        out = capsys.readouterr().out
        assert "LEVEL & PROGRESS (A1)" in out
        assert "Grammar:" in out and "50%" in out
        assert "Topics mastered: 1/2" in out
        assert "Strong: Present tense" in out
        assert "Weak: Dative case errors" in out
        assert "Texts written: 2" in out
        assert "Words written: 120 total, 120 at current level" in out
        assert "Recent text-level trend: A1 -> A2" in out

    def test_render_progress_no_trend_omits_trend_line(self, capsys):
        io = TerminalIOHandler()
        io.render_progress({"current_level": "a1", "modules": [], "trend": []})
        out = capsys.readouterr().out
        assert "trend" not in out.lower()


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

    def test_session_view_renders_grammar_session(self, client, monkeypatch, tmp_path):
        """A grammar-shaped session file renders explanation/exercises/score, and its
        next_actions (any session type can carry one — not grammar-specific)."""
        monkeypatch.setattr(_ui_mod._config, "data_root", str(tmp_path))
        session_dir = tmp_path / "sessions" / "u1" / "german"
        session_dir.mkdir(parents=True)
        session_data = {
            "session_id": "abc123", "user_id": "u1", "language": "german", "module": "grammar",
            "task_label": "articles", "date": "2026-07-02T10:00:00", "level": "a1", "status": "completed",
            "topic": "Articles", "scope": "major", "explanation": "Articles explain gender and case.",
            "items": [
                {"prompt": "Der ___ Mann", "user_answer": "der", "correct_answer": "der",
                 "correct": True, "feedback": "", "exercise_type": "fill_blank", "error_tag": "article"},
            ],
            "score": 1.0, "btw_log": [],
            "next_actions": [
                {"module": "writing", "reason": "you nailed it", "suggested_focus": "Articles", "accepted": None}
            ],
        }
        with open(session_dir / "abc123.yaml", "w", encoding="utf-8") as f:
            yaml.dump(session_data, f)

        r = client.get("/sessions/sessions/u1/german/abc123.yaml")
        assert r.status_code == 200
        body = r.data.decode()
        assert "Articles explain gender and case." in body
        assert "Der ___ Mann" in body
        assert "100%" in body
        assert "you nailed it" in body

    def test_api_start_chains_forced_recommendation(self, client):
        """/api/start's background run() must loop with forced_recommendation, mirroring
        the ui/cli.py chaining loop from 2a-vii — mocks Orchestrator entirely."""
        recommendation = ExerciseRecommendation(module="grammar", reason="recurring error", suggested_focus="verb_tense")
        mock_orch = MagicMock()
        mock_orch.run_session.side_effect = [recommendation, None]

        with patch("ui.app.Orchestrator", return_value=mock_orch):
            r = client.post("/api/start", json={"user_id": "test"})
            sid = r.get_json()["session_id"]
            with _ui_mod._sessions_lock:
                thread = _ui_mod._sessions[sid]["thread"]
            thread.join(timeout=5)

        assert mock_orch.run_session.call_count == 2
        first_call, second_call = mock_orch.run_session.call_args_list
        assert first_call.kwargs["forced_recommendation"] is None
        assert second_call.kwargs["forced_recommendation"] is recommendation


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

    def test_writing_ui_js_served(self, client):
        r = client.get("/static/writing-ui.js")
        assert r.status_code == 200
        assert b"submitWriting" in r.data

    def test_grammar_ui_js_served(self, client):
        r = client.get("/static/grammar-ui.js")
        assert r.status_code == 200
        assert b"submitGrammarAnswers" in r.data

    def test_decor_js_served(self, client):
        r = client.get("/static/decor.js")
        assert r.status_code == 200
        assert b"cycleTheme" in r.data


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

    def test_writing_ui_js_syntax(self, node_available):
        self._check("ui/static/writing-ui.js")

    def test_grammar_ui_js_syntax(self, node_available):
        self._check("ui/static/grammar-ui.js")

    def test_decor_js_syntax(self, node_available):
        self._check("ui/static/decor.js")
