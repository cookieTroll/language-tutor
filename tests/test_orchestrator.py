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
        UserProfile("user1", "german", "a1", "stated", True, date_now, date_now)
    )

    # 2 completed sessions -> still cold start (threshold is 3)
    s1 = SessionLog("user1", "s1", "german", "writing", "t1", "desc", "", [], "a1", date_now, "path1", "completed", date_now, date_now, 5.0)
    s2 = SessionLog("user1", "s2", "german", "writing", "t2", "desc", "", [], "a1", date_now, "path2", "completed", date_now, date_now, 5.0)
    store.write_session(s1)
    store.write_session(s2)
    
    assert orchestrator.summarize_progress("user1", "german") is None

    # 3 completed sessions -> threshold reached, not cold start
    s3 = SessionLog("user1", "s3", "german", "writing", "t3", "desc", "", [], "a1", date_now, "path3", "completed", date_now, date_now, 5.0)
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
        UserProfile("user1", "german", "a1", "stated", True, date_now, date_now)
    )
    # started 20 minutes ago (timeout is 15)
    log = SessionLog("user1", "sess_int", "german", "writing", "t1", "d1", "", [], "a1", date_now - timedelta(minutes=20), "path", "in_progress", date_now - timedelta(minutes=20))
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
        UserProfile("user1", "german", "a1", "stated", True, date_now, date_now)
    )
    log = SessionLog("user1", "sess_int", "german", "writing", "t1", "d1", "", [], "a1", date_now - timedelta(minutes=20), "path", "in_progress", date_now - timedelta(minutes=20))
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
