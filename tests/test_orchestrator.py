import os
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
from config import AppConfig, LLMConfig
from memory.json_store import JSONSessionStore
from llm.base import BaseLLM, LLMResponse
from orchestrator.orchestrator import Orchestrator, DEFAULT_RECOMMENDATION
from memory.protocols import UserProfile, SessionLog

@pytest.fixture
def store_and_llm(tmp_path):
    store = JSONSessionStore(data_root=str(tmp_path))
    llm = MagicMock(spec=BaseLLM)
    config = AppConfig(
        data_root=str(tmp_path),
        default_level="a1",
        cold_start_threshold=3,
        interruption_timeout_minutes=15,
        storage_backend="json",
        llm=LLMConfig(provider="openai_compat", base_url=None, api_key=None, model="model")
    )
    return store, llm, config

def test_cold_start_threshold(store_and_llm):
    store, llm, config = store_and_llm
    orchestrator = Orchestrator(store, llm, config)
    
    # 0 completed sessions -> should be cold start
    assert orchestrator.summarize_progress("user1", "german") is None
    assert orchestrator.recommend_exercise(None) == DEFAULT_RECOMMENDATION

    # Write profile
    date_now = datetime.now()
    store.write_user_profile(
        UserProfile(
            user_id="user1",
            language="german",
            level="a1",
            level_source="stated",
            active=True,
            created_at=date_now,
            updated_at=date_now
        )
    )

    # 2 completed sessions -> still cold start (threshold is 3)
    s1 = SessionLog(
        user_id="user1",
        session_id="s1",
        language="german",
        module="writing",
        task_label="t1",
        task_description="desc",
        comment="",
        errors=[],
        level="a1",
        date=date_now,
        file_path="path1",
        status="completed",
        started_at=date_now,
        completed_at=date_now,
        duration_minutes=5.0
    )
    s2 = SessionLog(
        user_id="user1",
        session_id="s2",
        language="german",
        module="writing",
        task_label="t2",
        task_description="desc",
        comment="",
        errors=[],
        level="a1",
        date=date_now,
        file_path="path2",
        status="completed",
        started_at=date_now,
        completed_at=date_now,
        duration_minutes=5.0
    )
    store.write_session(s1)
    store.write_session(s2)
    
    assert orchestrator.summarize_progress("user1", "german") is None

    # 3 completed sessions -> threshold reached, not cold start
    s3 = SessionLog(
        user_id="user1",
        session_id="s3",
        language="german",
        module="writing",
        task_label="t3",
        task_description="desc",
        comment="",
        errors=[],
        level="a1",
        date=date_now,
        file_path="path3",
        status="completed",
        started_at=date_now,
        completed_at=date_now,
        duration_minutes=5.0
    )
    store.write_session(s3)
    
    summary = orchestrator.summarize_progress("user1", "german")
    assert summary is not None
    assert summary.sessions_by_module["writing"] == 3
    assert orchestrator.recommend_exercise(summary).module == "writing"

@patch("orchestrator.orchestrator.input")
def test_interrupted_session_discard(mock_input, store_and_llm):
    store, llm, config = store_and_llm
    orchestrator = Orchestrator(store, llm, config)
    
    # Mock user input choosing 'd' for Discard
    mock_input.return_value = "d"
    
    # Setup an interrupted session log
    date_now = datetime.now()
    store.write_user_profile(
        UserProfile(
            user_id="user1",
            language="german",
            level="a1",
            level_source="stated",
            active=True,
            created_at=date_now,
            updated_at=date_now
        )
    )
    # started 20 minutes ago (timeout is 15)
    log = SessionLog(
        user_id="user1",
        session_id="sess_int",
        language="german",
        module="writing",
        task_label="t1",
        task_description="d1",
        comment="",
        errors=[],
        level="a1",
        date=date_now - timedelta(minutes=20),
        file_path="path",
        status="in_progress",
        started_at=date_now - timedelta(minutes=20)
    )
    store.write_session(log)

    # Setup checkpoint file
    checkpoint_dir = os.path.join(config.data_root, "checkpoints", "user1")
    os.makedirs(checkpoint_dir, exist_ok=True)
    checkpoint_path = os.path.join(checkpoint_dir, "sess_int.json")
    with open(checkpoint_path, "w") as f:
        f.write("[]")

    orchestrator._handle_interruption("user1")

    # Read back session log
    recent = store.get_recent_sessions("user1", "german")
    assert recent[0].status == "abandoned"
    assert not os.path.exists(checkpoint_path)

@patch("orchestrator.orchestrator.input")
def test_interrupted_session_log(mock_input, store_and_llm):
    store, llm, config = store_and_llm
    orchestrator = Orchestrator(store, llm, config)
    
    # Mock user input choosing 'l' for Log it
    mock_input.return_value = "l"
    llm.complete.return_value = LLMResponse(text="Practiced daily routines and discussed separable verbs.", model="test-model")
    
    # Setup an interrupted session log
    date_now = datetime.now()
    store.write_user_profile(
        UserProfile(
            user_id="user1",
            language="german",
            level="a1",
            level_source="stated",
            active=True,
            created_at=date_now,
            updated_at=date_now
        )
    )
    log = SessionLog(
        user_id="user1",
        session_id="sess_int",
        language="german",
        module="writing",
        task_label="t1",
        task_description="d1",
        comment="",
        errors=[],
        level="a1",
        date=date_now - timedelta(minutes=20),
        file_path="path",
        status="in_progress",
        started_at=date_now - timedelta(minutes=20)
    )
    store.write_session(log)

    # Setup checkpoint file
    checkpoint_dir = os.path.join(config.data_root, "checkpoints", "user1")
    os.makedirs(checkpoint_dir, exist_ok=True)
    checkpoint_path = os.path.join(checkpoint_dir, "sess_int.json")
    with open(checkpoint_path, "w") as f:
        f.write("[{\"user\": \"hello\"}]")

    orchestrator._handle_interruption("user1")

    recent = store.get_recent_sessions("user1", "german")
    assert recent[0].status == "interrupted"
    assert recent[0].comment == "Practiced daily routines and discussed separable verbs."
    assert not os.path.exists(checkpoint_path)

@patch("orchestrator.orchestrator.input")
@patch("orchestrator.orchestrator.print")
def test_interrupted_session_invalid_choice_retry(mock_print, mock_input, store_and_llm):
    store, llm, config = store_and_llm
    orchestrator = Orchestrator(store, llm, config)
    
    # Mock user input choosing 'r' (unsupported), then 'invalid' (invalid), then 'd' (discard)
    mock_input.side_effect = ["r", "invalid", "d"]
    
    # Setup an interrupted session log
    date_now = datetime.now()
    log = SessionLog(
        user_id="user1",
        session_id="sess_int",
        language="german",
        module="writing",
        task_label="t1",
        task_description="d1",
        comment="",
        errors=[],
        level="a1",
        date=date_now - timedelta(minutes=20),
        file_path="path",
        status="in_progress",
        started_at=date_now - timedelta(minutes=20)
    )
    store.write_session(log)

    orchestrator._handle_interruption("user1")

    # Assert correct warning prints were outputted
    mock_print.assert_any_call("[!] Resume option is currently unavailable in PoC mode. Please select 'l' to log or 'd' to discard.")
    mock_print.assert_any_call("[!] Invalid option 'invalid'. Please enter 'l' to log or 'd' to discard.")
    
    recent = store.get_recent_sessions("user1", "german")
    assert recent[0].status == "abandoned"

def test_finalize_session_success(store_and_llm):
    from modules.protocols import ModuleResult
    store, llm, config = store_and_llm
    orchestrator = Orchestrator(store, llm, config)
    
    profile = UserProfile(
        user_id="user1",
        language="german",
        level="a1",
        level_source="stated",
        active=True,
        created_at=datetime.now(),
        updated_at=datetime.now()
    )
    store.write_user_profile(profile)
    
    result = ModuleResult(
        session_id="session123",
        module="writing",
        task_label="writing_free",
        task_description="Free writing task",
        errors=[],
        comment="Great job",
        started_at=datetime.now(),
        completed_at=datetime.now(),
        duration_minutes=2.5,
        metadata={}
    )
    
    from memory.protocols import WritingSessionContent
    file_content = WritingSessionContent(
        user_id="user1",
        session_id="session123",
        language="german",
        module="writing",
        level="a1",
        date=datetime.now().isoformat(),
        task_label="writing_free",
        status="completed",
        topic="My day",
        requirements="Write about your day.",
        user_text="Ich bin student.",
        mistakes=[],
        tips=[],
        corrected_text="Ich bin Student.",
        session_summary="Great job",
        btw_log=[],
        vocab_updates=[]
    )
    
    initial_log = SessionLog(
        user_id="user1",
        session_id="session123",
        language="german",
        module="writing",
        task_label="writing_free",
        task_description="Initializing",
        comment="",
        errors=[],
        level="a1",
        date=datetime.now(),
        file_path="",
        status="in_progress",
        started_at=datetime.now()
    )
    store.write_session(initial_log)

    orchestrator._finalize_session(
        user_id="user1",
        selected_lang="german",
        module_key="writing",
        session_id="session123",
        profile=profile,
        result=result,
        file_content=file_content,
        checkpoint_path=os.path.join(config.data_root, "checkpoints", "user1", "session123.json")
    )
    
    recent = store.get_recent_sessions("user1", "german")
    assert recent[0].status == "completed"
    assert recent[0].file_path != ""
    assert recent[0].comment == "Great job"
