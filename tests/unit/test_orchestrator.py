import os
import json
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

    llm.complete.return_value = LLMResponse(
        text=json.dumps({
            "weakest_module": "grammar",
            "recommendation_reason": "You've written a lot lately but haven't practiced grammar.",
        }),
        model="test-model",
    )

    summary = orchestrator.summarize_progress("user1", "german")
    assert summary is not None
    assert summary.sessions_by_module["writing"] == 3
    # weakest_module/recommendation_reason must come from the real LLM response
    # (SummarizeProgressSkill), not an unconfigured-mock fallback default.
    assert summary.weakest_module == "grammar"
    assert summary.recommendation_reason == "You've written a lot lately but haven't practiced grammar."
    recommendation = orchestrator.recommend_exercise(summary)
    assert recommendation.module == "grammar"
    assert recommendation.reason == summary.recommendation_reason

def test_summarize_progress_falls_back_to_writing_on_unregistered_module(store_and_llm):
    # If the LLM names a module that isn't in MODULE_REGISTRY (hallucination, typo,
    # future-module drift), summarize_progress must correct it to "writing" rather
    # than propagate an invalid module downstream.
    store, llm, config, io = store_and_llm
    orchestrator = Orchestrator(store, llm, config, io=io)

    date_now = datetime.now()
    store.write_user_profile(
        UserProfile(
            user_id="user1", language="german", level="a1", level_source="stated",
            active=True, created_at=date_now, updated_at=date_now,
        )
    )
    for i in range(3):
        store.write_session(SessionLog(
            user_id="user1", session_id=f"s{i}", language="german", module="writing",
            task_label=f"t{i}", task_description="desc", comment="", errors=[],
            level="a1", date=date_now, file_path=f"path{i}", status="completed",
            started_at=date_now, completed_at=date_now, duration_minutes=5.0,
        ))

    llm.complete.return_value = LLMResponse(
        text=json.dumps({
            "weakest_module": "vocab",  # not yet registered
            "recommendation_reason": "Focus on vocabulary.",
        }),
        model="test-model",
    )

    summary = orchestrator.summarize_progress("user1", "german")
    assert summary is not None
    assert summary.weakest_module == "writing"

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

    # Simulate: no active language → type "german", then level "b1" (config default is "a1"),
    # then Enter for explanation_language (default: english)
    io.prompt.side_effect = ["german", "b1", ""]

    _, profile = orchestrator._select_language_and_profile("user1", language=None)

    assert profile.level == "b1"
    assert store.get_current_level("user1") == "b1"


def test_new_user_enter_uses_config_default(store_and_llm):
    """Pressing Enter at the level prompt falls back to config.default_level."""
    store, llm, config, io = store_and_llm
    orchestrator = Orchestrator(store, llm, config, io=io)

    # Simulate: no active language → type "german", then Enter (empty) for level,
    # then Enter for explanation_language (default: english)
    io.prompt.side_effect = ["german", "", ""]

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

    # Simulate: continue german, then override level to "b1", then Enter to keep
    # explanation_language default
    io.prompt.side_effect = ["", "b1", ""]

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

    # Simulate: continue german, then Enter (keep level), then Enter (keep
    # explanation_language default)
    io.prompt.side_effect = ["", "", ""]

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


_GRAMMAR_TOPICS_TWO_TAGS = GrammarTopicsMap(topics=[
    GrammarTopic(
        topic="Present tense — regular verbs", difficulty="a1", scope="major",
        related_error_tags=["verb_conjugation"],
    ),
    GrammarTopic(
        topic="Dative case — prepositions", difficulty="a1", scope="major",
        related_error_tags=["dative_case"],
    ),
])


@patch("orchestrator.session_manager.get_grammar_topics", return_value=_GRAMMAR_TOPICS)
def test_requested_topic_bypasses_recurring_threshold(mock_topics, store_and_llm):
    """An explicit /btw practice request (requested_topic) skips the recurring-count
    gate entirely — freq=1 would normally fail RECURRING_ERROR_THRESHOLD (2)."""
    store, llm, config, io = store_and_llm
    orchestrator = Orchestrator(store, llm, config, io=io)

    signals = orchestrator._session_manager._writing_error_recurrence_signal(
        language="german", errors=[], error_frequency={"verb_conjugation": 1},
        requested_topic="verb_conjugation",
    )
    assert len(signals) == 1
    assert signals[0].suggested_focus == "verb_conjugation"
    assert "asked to practice" in signals[0].reason


@patch("orchestrator.session_manager.get_grammar_topics", return_value=_GRAMMAR_TOPICS)
def test_requested_topic_not_curated_returns_empty(mock_topics, store_and_llm):
    """requested_topic that maps to no curated topic at all, with no other recurring
    mapped tag available either -> no signal (nothing sensible to promise)."""
    store, llm, config, io = store_and_llm
    orchestrator = Orchestrator(store, llm, config, io=io)

    signals = orchestrator._session_manager._writing_error_recurrence_signal(
        language="german", errors=[], error_frequency={},
        requested_topic="word_order",  # not in any curated topic's related_error_tags
    )
    assert signals == []


@patch("orchestrator.session_manager.get_grammar_topics", return_value=_GRAMMAR_TOPICS_TWO_TAGS)
def test_requested_topic_offers_alternative_when_available(mock_topics, store_and_llm):
    """A second, different curated-mapped tag in error_frequency becomes an
    alternative signal — used by orchestrator.run_session to offer a fallback
    if the first suggestion is declined."""
    store, llm, config, io = store_and_llm
    orchestrator = Orchestrator(store, llm, config, io=io)

    signals = orchestrator._session_manager._writing_error_recurrence_signal(
        language="german", errors=[], error_frequency={"dative_case": 5},
        requested_topic="verb_conjugation",
    )
    assert len(signals) == 2
    assert signals[0].suggested_focus == "verb_conjugation"
    assert signals[1].suggested_focus == "dative_case"


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


def test_record_next_action_decision_by_index(store_and_llm):
    """A declined first (explicit-request) signal followed by an accepted second/
    alternative signal — the index picks which entry gets the accepted flag,
    leaving the other untouched."""
    store, llm, config, io = store_and_llm
    orchestrator = Orchestrator(store, llm, config, io=io)

    file_content = _grammar_session_content(score=1.0)
    file_content.next_actions = [
        NextActionSignal(module="grammar", reason="first", suggested_focus="verb_conjugation"),
        NextActionSignal(module="grammar", reason="alternative", suggested_focus="dative_case"),
    ]
    orchestrator._session_manager.store.write_file(file_content, config.data_root)

    orchestrator._session_manager.record_next_action_decision(file_content, accepted=False, index=0)
    orchestrator._session_manager.record_next_action_decision(file_content, accepted=True, index=1)

    assert file_content.next_actions[0].accepted is False
    assert file_content.next_actions[1].accepted is True


def test_record_next_action_decision_index_out_of_range_is_noop(store_and_llm):
    """Index beyond the list (e.g. no alternative existed) doesn't raise or write."""
    store, llm, config, io = store_and_llm
    orchestrator = Orchestrator(store, llm, config, io=io)

    file_content = _grammar_session_content(score=1.0)
    file_content.next_actions = [
        NextActionSignal(module="grammar", reason="first", suggested_focus="verb_conjugation"),
    ]
    orchestrator._session_manager.record_next_action_decision(file_content, accepted=True, index=1)
    assert file_content.next_actions[0].accepted is None

    written_path = os.path.join(
        config.data_root, "sessions", file_content.user_id, file_content.language, f"{file_content.session_id}.yaml"
    )
    assert not os.path.exists(written_path)


# ── 2b: on-demand /history command ──────────────────────────────────────────────

def _writing_session_log(session_id, days_ago, error_tags, text_level_estimate=None, task_label="daily_routine"):
    when = datetime.now() - timedelta(days=days_ago)
    return SessionLog(
        user_id="user1", session_id=session_id, language="german", module="writing",
        task_label=task_label, task_description="desc", comment="ok",
        errors=[{"error_tag": tag, "fragment": "x", "explanation": "y"} for tag in error_tags],
        level="a2", date=when, file_path=f"sessions/user1/german/{session_id}.yaml",
        status="completed", started_at=when, completed_at=when, duration_minutes=5.0,
        text_level_estimate=text_level_estimate,
    )


def test_parse_history_scope_default(store_and_llm):
    store, llm, config, io = store_and_llm
    orchestrator = Orchestrator(store, llm, config, io=io)

    from orchestrator.orchestrator import DEFAULT_HISTORY_SESSIONS
    assert orchestrator._parse_history_scope("") == ("sessions", DEFAULT_HISTORY_SESSIONS)


def test_parse_history_scope_session_count_arg(store_and_llm):
    store, llm, config, io = store_and_llm
    orchestrator = Orchestrator(store, llm, config, io=io)
    assert orchestrator._parse_history_scope("5") == ("sessions", 5)


def test_parse_history_scope_days_arg(store_and_llm):
    store, llm, config, io = store_and_llm
    orchestrator = Orchestrator(store, llm, config, io=io)
    assert orchestrator._parse_history_scope("30d") == ("days", 30)


@pytest.mark.parametrize("arg", ["abc", "0", "-5d", "5x", "0d"])
def test_parse_history_scope_invalid(store_and_llm, arg):
    store, llm, config, io = store_and_llm
    orchestrator = Orchestrator(store, llm, config, io=io)
    assert orchestrator._parse_history_scope(arg) is None


def test_handle_history_command_invalid_arg_skips_skill_call(store_and_llm):
    store, llm, config, io = store_and_llm
    orchestrator = Orchestrator(store, llm, config, io=io)

    with patch("orchestrator.orchestrator.SummarizeWritingHistorySkill") as mock_skill_cls:
        orchestrator._handle_history_command("user1", "german", "/history abc")
        mock_skill_cls.assert_not_called()

    assert any("Invalid /history" in call.args[0] for call in io.output.call_args_list)


def test_handle_history_command_no_sessions_skips_skill_call(store_and_llm):
    store, llm, config, io = store_and_llm
    orchestrator = Orchestrator(store, llm, config, io=io)

    with patch("orchestrator.orchestrator.SummarizeWritingHistorySkill") as mock_skill_cls:
        orchestrator._handle_history_command("user1", "german", "/history")
        mock_skill_cls.assert_not_called()

    assert any("No completed writing sessions" in call.args[0] for call in io.output.call_args_list)


def test_handle_history_command_aggregates_and_calls_skill(store_and_llm):
    """Recurring-mistake threshold (>=2) filters out one-off tags; topics and a
    chronological level trend are built from the filtered sessions."""
    store, llm, config, io = store_and_llm
    orchestrator = Orchestrator(store, llm, config, io=io)

    store.write_session(_writing_session_log("s1", days_ago=3, error_tags=["dative_case", "word_order"],
                                              text_level_estimate="a2", task_label="daily_routine"))
    store.write_session(_writing_session_log("s2", days_ago=2, error_tags=["dative_case"],
                                              text_level_estimate="a2", task_label="holiday_trip"))
    store.write_session(_writing_session_log("s3", days_ago=1, error_tags=["dative_case"],
                                              text_level_estimate="b1", task_label="daily_routine"))

    from skills.protocols import SkillOutput
    with patch("orchestrator.orchestrator.SummarizeWritingHistorySkill") as mock_skill_cls:
        mock_skill_cls.return_value.run.return_value = SkillOutput(
            skill_name="summarize_writing_history", success=True,
            metadata={"history_summary": "You've been practicing daily routines and improved to B1."},
        )
        orchestrator._handle_history_command("user1", "german", "/history")

        call_kwargs = mock_skill_cls.return_value.run.call_args
        skill_input = call_kwargs.args[0]
        assert skill_input.parameters["topics"] == ["daily_routine", "holiday_trip"]
        assert skill_input.parameters["recurring_mistakes"] == [{"error_tag": "dative_case", "count": 3}]
        assert skill_input.parameters["level_trend"] == [
            {"date": (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d"), "level": "a2"},
            {"date": (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d"), "level": "a2"},
            {"date": (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"), "level": "b1"},
        ]

    assert any("You've been practicing" in call.args[0] for call in io.output.call_args_list)


def test_handle_history_command_days_arg_filters_by_date(store_and_llm):
    store, llm, config, io = store_and_llm
    orchestrator = Orchestrator(store, llm, config, io=io)

    store.write_session(_writing_session_log("old", days_ago=60, error_tags=["word_order"]))
    store.write_session(_writing_session_log("recent", days_ago=1, error_tags=["word_order"]))

    from skills.protocols import SkillOutput
    with patch("orchestrator.orchestrator.SummarizeWritingHistorySkill") as mock_skill_cls:
        mock_skill_cls.return_value.run.return_value = SkillOutput(
            skill_name="summarize_writing_history", success=True, metadata={"history_summary": "..."},
        )
        orchestrator._handle_history_command("user1", "german", "/history 7d")

        skill_input = mock_skill_cls.return_value.run.call_args.args[0]
        assert skill_input.parameters["topics"] == ["daily_routine"]  # only the recent session


def test_handle_history_command_skill_failure_logged_not_crashed(store_and_llm):
    store, llm, config, io = store_and_llm
    orchestrator = Orchestrator(store, llm, config, io=io)
    store.write_session(_writing_session_log("s1", days_ago=1, error_tags=["word_order"]))

    from skills.protocols import SkillOutput
    with patch("orchestrator.orchestrator.SummarizeWritingHistorySkill") as mock_skill_cls, \
         patch("orchestrator.orchestrator.log_skill_error") as mock_log:
        mock_skill_cls.return_value.run.return_value = SkillOutput(
            skill_name="summarize_writing_history", success=False, metadata={"error": "boom"},
        )
        orchestrator._handle_history_command("user1", "german", "/history")
        mock_log.assert_called_once()

    assert any("Could not generate" in call.args[0] for call in io.output.call_args_list)


# ── Layer 2c: /progress command ────────────────────────────────────────────

_PROGRESS_TOPICS = GrammarTopicsMap(topics=[
    GrammarTopic(
        topic="Present tense — regular verbs",
        difficulty="a1",
        scope="major",
        related_error_tags=["verb_conjugation"],
    ),
])


@patch("orchestrator.mastery.get_taxonomy", return_value=None)
@patch("orchestrator.mastery.get_grammar_topics", return_value=_PROGRESS_TOPICS)
def test_handle_progress_command_no_sessions_no_crash(mock_topics, mock_tax, store_and_llm):
    store, llm, config, io = store_and_llm
    now = datetime.now()
    store.write_user_profile(UserProfile(
        user_id="user1", language="german", level="a1", level_source="stated",
        active=True, created_at=now, updated_at=now,
    ))
    orchestrator = Orchestrator(store, llm, config, io=io)

    orchestrator._handle_progress_command("user1", "german")

    io.render_progress.assert_called_once()
    data = io.render_progress.call_args.args[0]
    assert data["current_level"] == "a1"
    assert {m["module"] for m in data["modules"]} == {"grammar", "writing"}
    assert data["trend"] == []


@patch("orchestrator.mastery.get_taxonomy", return_value=None)
@patch("orchestrator.mastery.get_grammar_topics", return_value=_PROGRESS_TOPICS)
def test_handle_progress_command_confirmed_level_up_writes_level(mock_topics, mock_tax, store_and_llm):
    """All curated a1 topics mastered -> user confirms -> level actually advances to a2."""
    store, llm, config, io = store_and_llm
    now = datetime.now()
    store.write_user_profile(UserProfile(
        user_id="user1", language="german", level="a1", level_source="stated",
        active=True, created_at=now, updated_at=now,
    ))
    store.write_session(SessionLog(
        user_id="user1", session_id="g1", language="german", module="grammar",
        task_label="present_tense_regular_verbs", task_description="d", comment="", errors=[],
        level="a1", date=now, file_path="p", status="completed",
        started_at=now, completed_at=now, duration_minutes=5.0, score=0.9,
    ))
    io.prompt.return_value = "y"
    orchestrator = Orchestrator(store, llm, config, io=io)

    orchestrator._handle_progress_command("user1", "german")

    profile = store.get_user_profile("user1", "german")
    assert profile.level == "a2"
    assert profile.level_source == "estimated"


@patch("orchestrator.mastery.get_taxonomy", return_value=None)
@patch("orchestrator.mastery.get_grammar_topics", return_value=_PROGRESS_TOPICS)
def test_handle_progress_command_declined_level_up_does_not_write(mock_topics, mock_tax, store_and_llm):
    store, llm, config, io = store_and_llm
    now = datetime.now()
    store.write_user_profile(UserProfile(
        user_id="user1", language="german", level="a1", level_source="stated",
        active=True, created_at=now, updated_at=now,
    ))
    store.write_session(SessionLog(
        user_id="user1", session_id="g1", language="german", module="grammar",
        task_label="present_tense_regular_verbs", task_description="d", comment="", errors=[],
        level="a1", date=now, file_path="p", status="completed",
        started_at=now, completed_at=now, duration_minutes=5.0, score=0.9,
    ))
    io.prompt.return_value = "n"
    orchestrator = Orchestrator(store, llm, config, io=io)

    orchestrator._handle_progress_command("user1", "german")

    profile = store.get_user_profile("user1", "german")
    assert profile.level == "a1"
    assert profile.level_source == "stated"


def test_get_confirmed_module_loops_on_history_then_confirms_normally(store_and_llm):
    """/history re-prompts instead of starting a module; a normal answer afterward
    is unaffected — the existing [Y/n] / override flow still works."""
    store, llm, config, io = store_and_llm
    orchestrator = Orchestrator(store, llm, config, io=io)
    io.prompt.side_effect = ["/history", "y"]

    with patch.object(orchestrator, "_handle_history_command") as mock_handle:
        module_key = orchestrator._get_confirmed_module(DEFAULT_RECOMMENDATION, "user1", "german")

    mock_handle.assert_called_once_with("user1", "german", "/history", "english")
    assert module_key == "writing"
    assert io.prompt.call_count == 2


def test_get_confirmed_module_language_command_updates_profile(store_and_llm):
    """/language <lang> persists the new explanation_language on the profile and
    re-prompts instead of starting a module."""
    store, llm, config, io = store_and_llm
    orchestrator = Orchestrator(store, llm, config, io=io)
    io.prompt.side_effect = ["/language german", "y"]

    date_now = datetime.now()
    profile = UserProfile(
        user_id="user1", language="german", level="a1", level_source="stated",
        active=True, created_at=date_now, updated_at=date_now,
    )

    module_key = orchestrator._get_confirmed_module(DEFAULT_RECOMMENDATION, "user1", "german", profile)

    assert module_key == "writing"
    assert profile.explanation_language == "german"
    stored = store.get_user_profile("user1", "german")
    assert stored.explanation_language == "german"


def test_get_confirmed_module_language_command_no_arg_reports_current(store_and_llm):
    """/language with no argument just reports the current setting, doesn't change it."""
    store, llm, config, io = store_and_llm
    orchestrator = Orchestrator(store, llm, config, io=io)
    io.prompt.side_effect = ["/language", "y"]

    date_now = datetime.now()
    profile = UserProfile(
        user_id="user1", language="german", level="a1", level_source="stated",
        active=True, created_at=date_now, updated_at=date_now, explanation_language="french",
    )

    orchestrator._get_confirmed_module(DEFAULT_RECOMMENDATION, "user1", "german", profile)

    assert profile.explanation_language == "french"
    assert any("French" in call.args[0] for call in io.output.call_args_list)


def test_check_language_config_no_warning_when_fully_configured(store_and_llm):
    """No maps defaulted -> on_warn is never called, regardless of configured status."""
    store, llm, config, io = store_and_llm
    orchestrator = Orchestrator(store, llm, config, io=io)
    on_warn = MagicMock()

    with patch("orchestrator.orchestrator.using_defaults", return_value={"cefr_hints": False, "taxonomy": False}), \
         patch("orchestrator.orchestrator.is_configured", return_value=True):
        orchestrator._check_language_config("german", on_warn=on_warn)

    on_warn.assert_not_called()


def test_check_language_config_warns_configured_true_when_partially_defaulted(store_and_llm):
    """A language with its own config file, but some maps still generic-defaulted,
    is reported as configured=True — 'has content, just incomplete'."""
    store, llm, config, io = store_and_llm
    orchestrator = Orchestrator(store, llm, config, io=io)
    on_warn = MagicMock()

    with patch("orchestrator.orchestrator.using_defaults", return_value={"cefr_hints": False, "taxonomy": True}), \
         patch("orchestrator.orchestrator.is_configured", return_value=True):
        orchestrator._check_language_config("spanish", on_warn=on_warn)

    on_warn.assert_called_once_with("spanish", ["taxonomy"], True)


def test_check_language_config_warns_configured_false_when_unconfigured(store_and_llm):
    """A language with no lang/languages/{name}.yaml at all is reported as
    configured=False -- distinct signal telling the caller to generate it,
    not just accept the generic-default fallback."""
    store, llm, config, io = store_and_llm
    orchestrator = Orchestrator(store, llm, config, io=io)
    on_warn = MagicMock()

    with patch("orchestrator.orchestrator.using_defaults", return_value={"cefr_hints": True, "taxonomy": True}), \
         patch("orchestrator.orchestrator.is_configured", return_value=False):
        orchestrator._check_language_config("klingon", on_warn=on_warn)

    on_warn.assert_called_once_with("klingon", ["cefr hints", "taxonomy"], False)
