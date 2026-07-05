from datetime import datetime, timedelta

import pytest

import ui.mcp_server as srv
from memory.sqlite_store import SQLiteSessionStore
from memory.protocols import UserProfile, SessionLog, VocabFlag, WritingSessionContent


@pytest.fixture
def seeded(tmp_path, monkeypatch):
    """Point the module's module-level _store/_config at an isolated temp store,
    seeded with one writing session, one profile, and one vocab flag for 'alice'."""
    temp_dir = str(tmp_path)
    store = SQLiteSessionStore(data_root=temp_dir)
    monkeypatch.setattr(srv, "_store", store)
    monkeypatch.setattr(srv._config, "data_root", temp_dir)

    now = datetime.now()
    store.write_user_profile(
        UserProfile(user_id="alice", language="german", level="b1", level_source="stated",
                    active=True, created_at=now, updated_at=now)
    )
    content = WritingSessionContent(
        session_id="s1", user_id="alice", language="german", module="writing",
        task_label="Meine Familie", date=now.isoformat(), level="b1", status="completed",
        topic="Meine Familie", requirements="write about your family",
        user_text="Ich habe ein Katze.",
        mistakes=[{"error_tag": "article_gender", "fragment": "ein Katze",
                   "correction": "eine Katze", "explanation": "Katze is feminine", "severity": "minor"}],
        tips=["Watch noun genders"], corrected_text="Ich habe eine Katze.",
        session_summary="Good effort", btw_log=[], vocab_updates=[],
    )
    rel_path = store.write_file(content, temp_dir)
    log = SessionLog(
        user_id="alice", session_id="s1", language="german", module="writing",
        task_label="Meine Familie", task_description="write about your family", comment="",
        errors=content.mistakes, level="b1", date=now, file_path=rel_path, status="completed",
        started_at=now, completed_at=now, duration_minutes=12.5, text_level_estimate="b1",
    )
    store.write_session(log)
    store.write_vocab_flag(
        VocabFlag(flag_id="", user_id="alice", language="german", word="Katze",
                  translation="cat", source="manual", first_seen=now, last_seen=now, occurrence_count=1)
    )
    yield store


def test_list_users_and_languages(seeded):
    assert srv.list_users() == ["alice"]
    assert srv.list_languages("alice") == ["german"]


def test_get_progress_defaults_to_active_language(seeded):
    progress = srv.get_progress("alice")
    assert progress["language"] == "german"
    assert progress["level"] == "b1"
    assert progress["sessions_by_module"] == {"writing": 1}
    assert progress["vocab_flag_count"] == 1


def test_get_progress_no_active_language_raises(seeded):
    with pytest.raises(ValueError, match="No active language"):
        srv.get_progress("nobody")


def test_list_sessions_and_get_session(seeded):
    sessions = srv.list_sessions("alice")
    assert len(sessions) == 1
    assert sessions[0]["session_id"] == "s1"

    detail = srv.get_session("alice", "s1")
    assert detail["user_text"] == "Ich habe ein Katze."
    assert detail["corrected_text"] == "Ich habe eine Katze."


def test_get_session_wrong_user_raises(seeded):
    with pytest.raises(ValueError, match="No session"):
        srv.get_session("someone_else", "s1")


def test_get_recurring_errors_and_vocab_flags(seeded):
    assert srv.get_recurring_errors("alice") == {"article_gender": 1}
    flags = srv.get_vocab_flags("alice")
    assert len(flags) == 1
    assert flags[0]["word"] == "Katze"


def test_export_writing_history_contains_texts(seeded):
    text = srv.export_writing_history("alice")
    assert "Ich habe ein Katze." in text
    assert "Ich habe eine Katze." in text
    assert "Meine Familie" in text


def test_export_writing_history_days_filter_excludes_old_session(seeded):
    old = datetime.now() - timedelta(days=30)
    old_content = WritingSessionContent(
        session_id="s_old", user_id="alice", language="german", module="writing",
        task_label="Alter Urlaub", date=old.isoformat(), level="b1", status="completed",
        topic="Alter Urlaub", requirements="write about an old trip",
        user_text="Das war alt.", mistakes=[], tips=[], corrected_text="Das war alt.",
        session_summary="ok", btw_log=[], vocab_updates=[],
    )
    rel_path = seeded.write_file(old_content, seeded.data_root)
    seeded.write_session(SessionLog(
        user_id="alice", session_id="s_old", language="german", module="writing",
        task_label="Alter Urlaub", task_description="write about an old trip", comment="",
        errors=[], level="b1", date=old, file_path=rel_path, status="completed",
        started_at=old, completed_at=old, duration_minutes=10.0, text_level_estimate="b1",
    ))

    text = srv.export_writing_history("alice", days=7)
    assert "Das war alt." not in text
    assert "Ich habe ein Katze." in text


def test_export_writing_history_no_sessions_returns_message(seeded):
    assert srv.export_writing_history("alice", language="french") == "No completed writing sessions found."


def test_get_error_taxonomy_returns_tag_descriptions(seeded):
    taxonomy = srv.get_error_taxonomy("german")
    assert "other" in taxonomy
    assert isinstance(taxonomy["other"], str)


def test_get_grammar_topic_list_returns_topics(seeded):
    topics = srv.get_grammar_topic_list("german")
    assert len(topics) > 0
    assert {"topic", "difficulty", "related_error_tags"} <= topics[0].keys()
