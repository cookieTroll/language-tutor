"""Unit tests for shared/error_log.py — writes to a tmp_path-patched log file,
never the real data/logs/ directory."""
import json

import shared.error_log as error_log_module
from shared.error_log import log_skill_error


def _patch_log_path(tmp_path, monkeypatch):
    log_path = tmp_path / "skill_errors.jsonl"
    monkeypatch.setattr(error_log_module, "_LOG_DIR", str(tmp_path))
    monkeypatch.setattr(error_log_module, "_LOG_PATH", str(log_path))
    return log_path


def test_writes_one_json_line_with_expected_fields(tmp_path, monkeypatch):
    log_path = _patch_log_path(tmp_path, monkeypatch)

    log_skill_error("grammar", "generate_exercises", "boom", {"level": "a1", "topic": "Dative case"})

    lines = log_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["module"] == "grammar"
    assert record["skill"] == "generate_exercises"
    assert record["error"] == "boom"
    assert record["level"] == "a1"
    assert record["topic"] == "Dative case"
    assert "timestamp" in record


def test_appends_multiple_calls(tmp_path, monkeypatch):
    log_path = _patch_log_path(tmp_path, monkeypatch)

    log_skill_error("writing", "detect_mistakes", "err1")
    log_skill_error("writing", "classify_mistakes", "err2")

    lines = log_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2
    assert json.loads(lines[0])["skill"] == "detect_mistakes"
    assert json.loads(lines[1])["skill"] == "classify_mistakes"


def test_works_without_context(tmp_path, monkeypatch):
    log_path = _patch_log_path(tmp_path, monkeypatch)

    log_skill_error("grammar", "select_grammar", "no context here")

    record = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert record["error"] == "no context here"
