import os
import yaml
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
from config import AppConfig, LLMConfig
from memory.json_store import JSONSessionStore
from llm.base import BaseLLM, LLMResponse
from orchestrator.orchestrator import Orchestrator, DEFAULT_RECOMMENDATION
from memory.protocols import UserProfile, SessionLog, GrammarSessionContent, NextActionSignal
from lang.models import GrammarTopicsMap, GrammarTopic

@pytest.fixture
def store_and_llm(tmp_path):
    store = JSONSessionStore(data_root=str(tmp_path))
    llm = MagicMock(spec=BaseLLM)
    io = MagicMock()
    io.prompt.return_value = ""
    config = AppConfig(
        data_root=str(tmp_path),
        default_level="a1",
        cold_start_threshold=3,
        interruption_timeout_minutes=15,
        storage_backend="json",
        llm=LLMConfig(provider="openai_compat", base_url=None, api_key=None, model="model")
    )
    return store, llm, config, io

def test_cold_start_threshold(store_and_llm):
    store, llm, config, io = store_and_llm
    orchestrator = Orchestrator(store, llm, config, io=io)
    
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

def test_interrupted_session_discard(store_and_llm):
    store, llm, config, io = store_and_llm
    orchestrator = Orchestrator(store, llm, config, io=io)

    io.prompt.return_value = "d"
    
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

def test_interrupted_session_log(store_and_llm):
    store, llm, config, io = store_and_llm
    orchestrator = Orchestrator(store, llm, config, io=io)

    io.prompt.return_value = "l"
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

def test_interrupted_session_invalid_choice_retry(store_and_llm):
    store, llm, config, io = store_and_llm
    orchestrator = Orchestrator(store, llm, config, io=io)

    io.prompt.side_effect = ["r", "invalid", "d"]
    
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
    io.output.assert_any_call("[!] Resume option is currently unavailable in PoC mode. Please select 'l' to log or 'd' to discard.")
    io.output.assert_any_call("[!] Invalid option 'invalid'. Please enter 'l' to log or 'd' to discard.")
    
    recent = store.get_recent_sessions("user1", "german")
    assert recent[0].status == "abandoned"

def test_new_user_stated_level_overrides_config_default(store_and_llm):
    """Typing a level at the prompt saves it; config default is not used."""
    store, llm, config, io = store_and_llm
    orchestrator = Orchestrator(store, llm, config, io=io)

    # Simulate: no active language → type "german", then level "b1" (config default is "a1")
    io.prompt.side_effect = ["german", "b1"]

    _, profile = orchestrator._select_language_and_profile("user1", language=None)

    assert profile.level == "b1"
    assert store.get_current_level("user1") == "b1"


def test_new_user_enter_uses_config_default(store_and_llm):
    """Pressing Enter at the level prompt falls back to config.default_level."""
    store, llm, config, io = store_and_llm
    orchestrator = Orchestrator(store, llm, config, io=io)

    # Simulate: no active language → type "german", then Enter (empty) for level
    io.prompt.side_effect = ["german", ""]

    _, profile = orchestrator._select_language_and_profile("user1", language=None)

    assert profile.level == config.default_level


def test_existing_user_level_override(store_and_llm):
    """Returning user who types a new level updates storage via write_level."""
    store, llm, config, io = store_and_llm
    orchestrator = Orchestrator(store, llm, config, io=io)

    date_now = datetime.now()
    store.write_user_profile(UserProfile(
        user_id="user1", language="german", level="a2",
        level_source="stated", active=True,
        created_at=date_now, updated_at=date_now,
    ))

    # Simulate: continue german, then override level to "b1"
    io.prompt.side_effect = ["", "b1"]

    _, profile = orchestrator._select_language_and_profile("user1", language=None)

    assert profile.level == "b1"
    assert store.get_current_level("user1") == "b1"


def test_existing_user_level_kept_on_enter(store_and_llm):
    """Returning user who presses Enter keeps the stored level unchanged."""
    store, llm, config, io = store_and_llm
    orchestrator = Orchestrator(store, llm, config, io=io)

    date_now = datetime.now()
    store.write_user_profile(UserProfile(
        user_id="user1", language="german", level="b2",
        level_source="stated", active=True,
        created_at=date_now, updated_at=date_now,
    ))

    # Simulate: continue german, then Enter (keep level)
    io.prompt.side_effect = ["", ""]

    _, profile = orchestrator._select_language_and_profile("user1", language=None)

    assert profile.level == "b2"


def test_finalize_session_success(store_and_llm):
    from modules.protocols import ModuleResult
    store, llm, config, io = store_and_llm
    orchestrator = Orchestrator(store, llm, config, io=io)
    
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

    orchestrator._session_manager.finalize_session(
        user_id="user1",
        language="german",
        module_key="writing",
        session_id="session123",
        profile=profile,
        result=result,
        file_content=file_content,
        checkpoint_path=os.path.join(config.data_root, "checkpoints", "user1", "session123.json"),
        error_frequency={},
    )
    
    recent = store.get_recent_sessions("user1", "german")
    assert recent[0].status == "completed"
    assert recent[0].file_path != ""
    assert recent[0].comment == "Great job"


# ── 2a-vii: next_actions gate (writing <-> grammar bridge, both directions) ────────

_GRAMMAR_TOPICS = GrammarTopicsMap(topics=[
    GrammarTopic(
        topic="Present tense — regular verbs",
        difficulty="a1",
        scope="major",
        related_error_tags=["verb_conjugation"],
    ),
])


@patch("orchestrator.session_manager.get_grammar_topics", return_value=_GRAMMAR_TOPICS)
def test_next_actions_no_signal_when_not_recurring(mock_topics, store_and_llm):
    """Tag present in this session's errors but not yet recurring -> no signal."""
    store, llm, config, io = store_and_llm
    orchestrator = Orchestrator(store, llm, config, io=io)

    signals = orchestrator._session_manager._writing_error_recurrence_signal(
        language="german",
        errors=[{"error_tag": "verb_conjugation", "fragment": "x", "explanation": "y"}],
        error_frequency={"verb_conjugation": 1},
    )
    assert signals == []


@patch("orchestrator.session_manager.get_grammar_topics", return_value=_GRAMMAR_TOPICS)
def test_next_actions_no_signal_when_absent_from_session(mock_topics, store_and_llm):
    """Tag recurring in the aggregate but not among this session's own errors -> no signal."""
    store, llm, config, io = store_and_llm
    orchestrator = Orchestrator(store, llm, config, io=io)

    signals = orchestrator._session_manager._writing_error_recurrence_signal(
        language="german",
        errors=[],
        error_frequency={"verb_conjugation": 5},
    )
    assert signals == []


@patch("orchestrator.session_manager.get_grammar_topics", return_value=_GRAMMAR_TOPICS)
def test_next_actions_signal_when_both_present(mock_topics, store_and_llm):
    """Tag both present this session and recurring -> signal set, focused on the tag
    (not a resolved topic name — select_grammar does the level-aware topic pick later)."""
    store, llm, config, io = store_and_llm
    orchestrator = Orchestrator(store, llm, config, io=io)

    signals = orchestrator._session_manager._writing_error_recurrence_signal(
        language="german",
        errors=[{"error_tag": "verb_conjugation", "fragment": "x", "explanation": "y"}],
        error_frequency={"verb_conjugation": 2},
    )
    assert len(signals) == 1
    assert signals[0].module == "grammar"
    assert signals[0].suggested_focus == "verb_conjugation"


def _grammar_session_content(score: float, topic: str = "Present tense — regular verbs"):
    return GrammarSessionContent(
        session_id="s1", user_id="user1", language="german", module="grammar",
        task_label="grammar_practice", date=datetime.now().isoformat(), level="a1",
        status="completed", topic=topic, scope="major", explanation="...",
        items=[], score=score, btw_log=[],
    )


def test_grammar_mastery_no_signal_below_threshold(store_and_llm):
    """Score below GRAMMAR_MASTERY_THRESHOLD -> no writing suggestion."""
    store, llm, config, io = store_and_llm
    orchestrator = Orchestrator(store, llm, config, io=io)

    signals = orchestrator._session_manager._grammar_mastery_signal(_grammar_session_content(score=0.5))
    assert signals == []


def test_grammar_mastery_signal_at_threshold(store_and_llm):
    """Score at/above GRAMMAR_MASTERY_THRESHOLD -> writing suggestion, focused on the topic name."""
    store, llm, config, io = store_and_llm
    orchestrator = Orchestrator(store, llm, config, io=io)

    signals = orchestrator._session_manager._grammar_mastery_signal(
        _grammar_session_content(score=1.0, topic="Perfekt tense — regular and common irregular verbs")
    )
    assert len(signals) == 1
    assert signals[0].module == "writing"
    assert signals[0].suggested_focus == "Perfekt tense — regular and common irregular verbs"


def test_compute_next_actions_dispatches_by_module(store_and_llm):
    """The generic dispatcher routes to the right direction-specific gate."""
    store, llm, config, io = store_and_llm
    orchestrator = Orchestrator(store, llm, config, io=io)

    class _Result:
        errors: list = []

    signals = orchestrator._session_manager._compute_next_actions(
        module_key="grammar",
        language="german",
        result=_Result(),
        file_content=_grammar_session_content(score=1.0),
        error_frequency={},
    )
    assert len(signals) == 1
    assert signals[0].module == "writing"

    signals = orchestrator._session_manager._compute_next_actions(
        module_key="vocab",
        language="german",
        result=_Result(),
        file_content=_grammar_session_content(score=1.0),
        error_frequency={},
    )
    assert signals == []


def test_record_next_action_decision_persists_accepted_flag(store_and_llm):
    """The accept/decline answer is written back to the session file — the file is
    already on disk (finalize_session wrote it) by the time this is called, so this
    exercises the follow-up rewrite path, not the original write."""
    store, llm, config, io = store_and_llm
    orchestrator = Orchestrator(store, llm, config, io=io)

    file_content = _grammar_session_content(score=1.0)
    file_content.next_actions = [
        NextActionSignal(module="writing", reason="you nailed it", suggested_focus="Perfekt tense")
    ]
    orchestrator._session_manager.store.write_file(file_content, config.data_root)

    orchestrator._session_manager.record_next_action_decision(file_content, accepted=True)

    assert file_content.next_actions[0].accepted is True

    written_path = os.path.join(
        config.data_root, "sessions", file_content.user_id, file_content.language, f"{file_content.session_id}.yaml"
    )
    with open(written_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    assert data["next_actions"][0]["accepted"] is True


def test_record_next_action_decision_noop_without_next_actions(store_and_llm):
    """No next_actions on the file -> nothing to record, and no spurious rewrite."""
    store, llm, config, io = store_and_llm
    orchestrator = Orchestrator(store, llm, config, io=io)

    file_content = _grammar_session_content(score=0.0)  # next_actions defaults to []
    orchestrator._session_manager.record_next_action_decision(file_content, accepted=True)

    written_path = os.path.join(
        config.data_root, "sessions", file_content.user_id, file_content.language, f"{file_content.session_id}.yaml"
    )
    assert not os.path.exists(written_path)
