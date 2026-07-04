import os
import shutil
import tempfile
import pytest
from datetime import datetime, timedelta
import yaml
from memory.sqlite_store import SQLiteSessionStore
from memory.json_store import JSONSessionStore
from memory.protocols import (
    SessionLog,
    BtwEntry,
    VocabFlag,
    UserProfile,
    SessionFileContent
)

# Dummy subclass for SessionFileContent to test file writing
class DummySessionContent(SessionFileContent):
    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "language": self.language,
            "module": self.module,
            "task_label": self.task_label,
            "date": self.date,
            "level": self.level,
            "status": self.status,
        }

@pytest.fixture(params=["sqlite", "json"])
def storage(request):
    # Setup temporary directory for testing storage
    temp_dir = tempfile.mkdtemp()
    
    if request.param == "sqlite":
        # SQLiteSessionStore uses the relative schema.sql file
        store = SQLiteSessionStore(data_root=temp_dir)
    else:
        store = JSONSessionStore(data_root=temp_dir)
        
    yield store
    
    # Tear down temp dir after test runs
    shutil.rmtree(temp_dir)

def test_user_profile_lifecycle(storage):
    user_id = "user1"
    profile = UserProfile(
        user_id=user_id,
        language="german",
        level="b1",
        level_source="stated",
        active=True,
        created_at=datetime.now(),
        updated_at=datetime.now()
    )
    
    storage.write_user_profile(profile)
    
    # Get active language
    assert storage.get_active_language(user_id) == "german"
    
    # Read back profile
    loaded = storage.get_user_profile(user_id, "german")
    assert loaded is not None
    assert loaded.user_id == user_id
    assert loaded.language == "german"
    assert loaded.level == "b1"
    assert loaded.level_source == "stated"
    assert loaded.active is True
    
    # Test level update
    storage.write_level(user_id, "b2", "estimated")
    assert storage.get_current_level(user_id) == "b2"
    
    # Add another language and mark it active
    profile_es = UserProfile(
        user_id=user_id,
        language="spanish",
        level="a1",
        level_source="stated",
        active=True, # Should deactivate German
        created_at=datetime.now(),
        updated_at=datetime.now()
    )
    storage.write_user_profile(profile_es)
    
    assert storage.get_active_language(user_id) == "spanish"
    assert storage.get_user_profile(user_id, "german").active is False
    assert storage.get_user_profile(user_id, "spanish").active is True

def test_session_lifecycle(storage):
    user_id = "user1"
    session_id = "sess1"
    date_now = datetime.now()
    
    # Write user profile first to satisfy SQLite FK constraints
    storage.write_user_profile(
        UserProfile(
            user_id=user_id, language="german", level="a1", level_source="stated",
            active=True, created_at=date_now, updated_at=date_now
        )
    )
    
    log = SessionLog(
        user_id=user_id,
        session_id=session_id,
        language="german",
        module="writing",
        task_label="writing_free",
        task_description="Write about your day",
        comment="Needs improvement",
        errors=[
            {"error_tag": "dative_case", "fragment": "mit meinen", "explanation": "mit takes dative"}
        ],
        level="a1",
        date=date_now,
        file_path="sessions/user1/german/sess1.yaml",
        status="in_progress",
        started_at=date_now
    )
    
    storage.write_session(log)
    
    # Verify update session status
    storage.update_session_status(session_id, "completed")
    
    # Test invalid status raises value error
    with pytest.raises(ValueError, match="Invalid status"):
        storage.update_session_status(session_id, "invalid_status")
        
    recent = storage.get_recent_sessions(user_id, "german", n=10)
    assert len(recent) == 1
    assert recent[0].session_id == session_id
    assert recent[0].status == "completed"
    assert len(recent[0].errors) == 1
    assert recent[0].errors[0]["error_tag"] == "dative_case"
    assert recent[0].errors[0]["fragment"] == "mit meinen"

def test_get_session_by_id(storage):
    user_id = "user1"
    date_now = datetime.now()

    storage.write_user_profile(
        UserProfile(
            user_id=user_id, language="german", level="a1", level_source="stated",
            active=True, created_at=date_now, updated_at=date_now
        )
    )
    log = SessionLog(
        user_id=user_id, session_id="sess1", language="german", module="writing",
        task_label="writing_free", task_description="Write about your day", comment="",
        errors=[{"error_tag": "dative_case", "fragment": "mit meinen", "explanation": "mit takes dative"}],
        level="a1", date=date_now, file_path="sessions/user1/german/sess1.yaml",
        status="completed", started_at=date_now, completed_at=date_now,
    )
    storage.write_session(log)

    found = storage.get_session_by_id("sess1")
    assert found is not None
    assert found.session_id == "sess1"
    assert found.user_id == user_id
    assert len(found.errors) == 1

    assert storage.get_session_by_id("does-not-exist") is None

def test_list_users(storage):
    date_now = datetime.now()
    for uid in ("zed", "alice"):
        storage.write_user_profile(
            UserProfile(
                user_id=uid, language="german", level="a1", level_source="stated",
                active=True, created_at=date_now, updated_at=date_now
            )
        )
    assert storage.list_users() == ["alice", "zed"]

def test_error_frequency(storage):
    user_id = "user1"
    date_now = datetime.now()
    storage.write_user_profile(
        UserProfile(
            user_id=user_id, language="german", level="a1", level_source="stated",
            active=True, created_at=date_now, updated_at=date_now
        )
    )
    
    log1 = SessionLog(
        user_id=user_id, session_id="sess1", language="german", module="writing",
        task_label="t1", task_description="d1", comment="",
        errors=[
            {"error_tag": "dative_case", "fragment": "f1", "explanation": "e1"},
            {"error_tag": "word_order", "fragment": "f2", "explanation": "e2"}
        ],
        level="a1", date=date_now, file_path="path1", status="completed"
    )
    log2 = SessionLog(
        user_id=user_id, session_id="sess2", language="german", module="writing",
        task_label="t2", task_description="d2", comment="",
        errors=[
            {"error_tag": "dative_case", "fragment": "f3", "explanation": "e3"}
        ],
        level="a1", date=date_now + timedelta(seconds=1), file_path="path2", status="completed"
    )
    
    storage.write_session(log1)
    storage.write_session(log2)
    
    freq = storage.get_error_frequency(user_id, "german")
    assert freq.get("dative_case") == 2
    assert freq.get("word_order") == 1

    topics = storage.get_recent_topics(user_id, "german", "writing", n=5)
    assert len(topics) == 2
    assert topics[0] == "t2"  # Should sort most recent first
    assert topics[1] == "t1"

def test_error_frequency_module_filter(storage):
    user_id = "user1"
    date_now = datetime.now()
    storage.write_user_profile(
        UserProfile(
            user_id=user_id, language="german", level="a1", level_source="stated",
            active=True, created_at=date_now, updated_at=date_now
        )
    )

    log_writing = SessionLog(
        user_id=user_id, session_id="sess_w", language="german", module="writing",
        task_label="t1", task_description="d1", comment="",
        errors=[{"error_tag": "dative_case", "fragment": "f1", "explanation": "e1"}],
        level="a1", date=date_now, file_path="path1", status="completed"
    )
    log_grammar = SessionLog(
        user_id=user_id, session_id="sess_g", language="german", module="grammar",
        task_label="t2", task_description="d2", comment="",
        errors=[
            {"error_tag": "dative_case", "fragment": "f2", "explanation": "e2"},
            {"error_tag": "word_order", "fragment": "f3", "explanation": "e3"},
        ],
        level="a1", date=date_now + timedelta(seconds=1), file_path="path2", status="completed"
    )
    storage.write_session(log_writing)
    storage.write_session(log_grammar)

    writing_freq = storage.get_error_frequency(user_id, "german", module="writing")
    assert writing_freq == {"dative_case": 1}

    grammar_freq = storage.get_error_frequency(user_id, "german", module="grammar")
    assert grammar_freq == {"dative_case": 1, "word_order": 1}

    total_freq = storage.get_error_frequency(user_id, "german")
    assert total_freq == {"dative_case": 2, "word_order": 1}

def test_interrupted_sessions(storage):
    user_id = "user1"
    date_now = datetime.now()
    storage.write_user_profile(
        UserProfile(
            user_id=user_id, language="german", level="a1", level_source="stated",
            active=True, created_at=date_now, updated_at=date_now
        )
    )
    
    # Active session (started 2 minutes ago, timeout is 15 minutes)
    log_active = SessionLog(
        user_id=user_id, session_id="sess_active", language="german", module="writing",
        task_label="t1", task_description="d1", comment="", errors=[],
        level="a1", date=date_now - timedelta(minutes=2), file_path="path1",
        status="in_progress", started_at=date_now - timedelta(minutes=2)
    )
    # Timed out session (started 20 minutes ago)
    log_timeout = SessionLog(
        user_id=user_id, session_id="sess_timeout", language="german", module="writing",
        task_label="t2", task_description="d2", comment="", errors=[],
        level="a1", date=date_now - timedelta(minutes=20), file_path="path2",
        status="in_progress", started_at=date_now - timedelta(minutes=20)
    )
    
    storage.write_session(log_active)
    storage.write_session(log_timeout)
    
    interrupted = storage.get_interrupted_sessions(user_id, timeout_minutes=15)
    assert len(interrupted) == 1
    assert interrupted[0].session_id == "sess_timeout"
    assert interrupted[0].status == "interrupted"

def test_btw_and_vocab_flags(storage):
    user_id = "user1"
    btw_id = "btw1"
    session_id = "sess1"
    date_now = datetime.now()
    
    # Test btw write
    entry = BtwEntry(
        btw_id=btw_id,
        session_id=session_id,
        user_id=user_id,
        language="german",
        question="What is this?",
        answer="It is a book",
        flagged_word="Buch",
        timestamp=date_now
    )
    storage.write_btw(entry)
    
    btw_list = storage.get_btw_log(user_id, "german")
    assert len(btw_list) == 1
    assert btw_list[0].question == "What is this?"
    assert btw_list[0].flagged_word == "Buch"
    
    # Test vocab flag insert
    flag = VocabFlag(
        flag_id="flag1",
        user_id=user_id,
        language="german",
        word="buch",
        translation="book",
        source="btw",
        first_seen=date_now,
        last_seen=date_now,
        occurrence_count=1
    )
    storage.write_vocab_flag(flag)
    
    # Test duplicates increment count instead of duplicate row insertion
    storage.write_vocab_flag(flag)
    
    flags = storage.get_vocab_flags(user_id, "german")
    assert len(flags) == 1
    assert flags[0].word == "buch"
    assert flags[0].occurrence_count == 2

def test_write_file_atomic(storage):
    content = DummySessionContent(
        session_id="sess_f1",
        user_id="user1",
        language="german",
        module="writing",
        task_label="writing_free",
        date="2026-06-27T18:00:00",
        level="a1",
        status="completed"
    )
    
    rel_path = storage.write_file(content, storage.data_root)
    abs_path = os.path.join(storage.data_root, rel_path)
    
    # Verify file exists
    assert os.path.exists(abs_path)
    # Verify no tmp file remains
    assert not os.path.exists(abs_path + ".tmp")
    
    # Read back YAML content
    with open(abs_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    assert data["session_id"] == "sess_f1"
    assert data["user_id"] == "user1"

def test_session_aggregate():
    import shutil, tempfile
    temp_dir = tempfile.mkdtemp()
    try:
        store = SQLiteSessionStore(data_root=temp_dir)
        user_id = "u1"
        now = datetime.now()

        store.write_user_profile(UserProfile(
            user_id=user_id, language="german", level="b1", level_source="stated",
            active=True, created_at=now, updated_at=now,
        ))

        def _make_session(sid, module, task_label, errors, days_ago, status="completed", minutes=30.0):
            dt = now - timedelta(days=days_ago)
            return SessionLog(
                user_id=user_id, session_id=sid, language="german", module=module,
                task_label=task_label, task_description="", comment="", errors=errors,
                level="b1", date=dt, file_path=f"p/{sid}.yaml", status=status,
                started_at=dt, completed_at=dt if status == "completed" else None,
                duration_minutes=minutes,
            )

        store.write_session(_make_session("s1", "writing", "daily_routine", [
            {"error_tag": "dative_case", "fragment": "f", "explanation": "e"},
            {"error_tag": "word_order",  "fragment": "f", "explanation": "e"},
        ], days_ago=5))
        store.write_session(_make_session("s2", "writing", "holiday_trip", [
            {"error_tag": "dative_case", "fragment": "f", "explanation": "e"},
        ], days_ago=2))
        store.write_session(_make_session("s3", "grammar", "adjective_endings", [], days_ago=1))
        store.write_session(_make_session("s4", "writing", "pending", [], days_ago=0, status="in_progress"))

        store.write_vocab_flag(VocabFlag(
            flag_id="v1", user_id=user_id, language="german", word="buch", translation="book",
            source="btw", first_seen=now, last_seen=now, occurrence_count=1,
        ))
        store.write_vocab_flag(VocabFlag(
            flag_id="v2", user_id=user_id, language="german", word="haus", translation="house",
            source="btw", first_seen=now, last_seen=now, occurrence_count=1,
        ))

        agg = store.get_session_aggregate(user_id, "german")

        assert agg.sessions_by_module == {"writing": 2, "grammar": 1}
        assert agg.total_time_by_module["writing"] == pytest.approx(60.0)
        assert agg.total_time_by_module["grammar"] == pytest.approx(30.0)
        assert agg.days_since_module["writing"] == pytest.approx(2.0, abs=0.1)
        assert agg.days_since_module["grammar"] == pytest.approx(1.0, abs=0.1)
        assert agg.recurring_errors == ["dative_case"]   # freq=2; word_order freq=1 excluded
        assert agg.recent_topics == ["holiday_trip", "daily_routine"]
        assert agg.vocab_flag_count == 2
    finally:
        shutil.rmtree(temp_dir)


def test_pydantic_contract_validation():
    from pydantic import ValidationError
    
    # Invalid level raises ValidationError
    with pytest.raises(ValidationError):
        UserProfile(
            user_id="u1",
            language="german",
            level="z1", # Invalid CEFR level
            level_source="stated",
            active=True,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )

    # Invalid status raises ValidationError
    with pytest.raises(ValidationError):
        SessionLog(
            user_id="user1", session_id="sess1", language="german", module="writing",
            task_label="t1", task_description="d1", comment="", errors=[],
            level="a1", date=datetime.now(), file_path="path1", status="invalid_status"
        )

    # Invalid vocab source raises ValidationError
    with pytest.raises(ValidationError):
        VocabFlag(
            flag_id="flag1",
            user_id="user1",
            language="german",
            word="buch",
            translation="book",
            source="invalid_source", # type: ignore
            first_seen=datetime.now(),
            last_seen=datetime.now(),
            occurrence_count=1
        )
