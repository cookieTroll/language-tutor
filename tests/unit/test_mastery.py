import pytest
from unittest.mock import patch
from datetime import datetime, timedelta

from memory.json_store import JSONSessionStore
from memory.protocols import UserProfile, SessionLog
from orchestrator.mastery import get_module_mastery, get_level_trend, TEXTS_PER_LEVEL_FOR_MASTERY
from lang.models import GrammarTopicsMap, GrammarTopic, TaxonomyMap
from shared.slugify import slugify_topic

_GRAMMAR_TOPICS = GrammarTopicsMap(topics=[
    GrammarTopic(
        topic="Present tense — regular verbs",
        difficulty="a1",
        scope="major",
        related_error_tags=["verb_conjugation"],
    ),
    GrammarTopic(
        topic="Dative case — prepositions",
        difficulty="a1",
        scope="major",
        related_error_tags=["dative_case"],
    ),
    GrammarTopic(
        topic="Subjunctive II",
        difficulty="b2",
        scope="major",
        related_error_tags=["mood"],
    ),
])

_TAXONOMY = TaxonomyMap(tags={"dative_case": "Dative case errors", "other": "Other"})


@pytest.fixture
def store(tmp_path):
    s = JSONSessionStore(data_root=str(tmp_path))
    now = datetime.now()
    s.write_user_profile(UserProfile(
        user_id="user1", language="german", level="a1", level_source="stated",
        active=True, created_at=now, updated_at=now,
    ))
    return s


def _grammar_log(session_id, topic, score, level="a1", date=None):
    return SessionLog(
        user_id="user1", session_id=session_id, language="german", module="grammar",
        task_label=slugify_topic(topic), task_description="d", comment="", errors=[],
        level=level, date=date or datetime.now(), file_path="p", status="completed",
        started_at=datetime.now(), completed_at=datetime.now(), duration_minutes=5.0,
        score=score,
    )


def _writing_log(session_id, word_count, level="a1", text_level_estimate=None, date=None):
    return SessionLog(
        user_id="user1", session_id=session_id, language="german", module="writing",
        task_label="t", task_description="d", comment="", errors=[],
        level=level, date=date or datetime.now(), file_path="p", status="completed",
        started_at=datetime.now(), completed_at=datetime.now(), duration_minutes=5.0,
        word_count=word_count, text_level_estimate=text_level_estimate,
    )


@patch("orchestrator.mastery.get_taxonomy", return_value=_TAXONOMY)
@patch("orchestrator.mastery.get_grammar_topics", return_value=_GRAMMAR_TOPICS)
def test_grammar_mastery_scoped_to_current_level(mock_topics, mock_tax, store):
    """Only a1 topics count toward topics_total/mastered — b2's Subjunctive II is excluded
    even though it's in the curated map, because the user's current level is a1."""
    store.write_session(_grammar_log("s1", "Present tense — regular verbs", 0.9))
    store.write_session(_grammar_log("s2", "Dative case — prepositions", 0.5))

    mastery = get_module_mastery(store, "user1", "german", "grammar")

    assert mastery.topics_total == 2  # only the two a1 topics
    assert mastery.topics_mastered == 1  # only present tense scored >= 0.8
    assert mastery.mastery_ratio == 0.5
    assert mastery.strong_tags == ["Present tense — regular verbs"]


@patch("orchestrator.mastery.get_taxonomy", return_value=_TAXONOMY)
@patch("orchestrator.mastery.get_grammar_topics", return_value=_GRAMMAR_TOPICS)
def test_grammar_mastery_takes_best_score_across_attempts(mock_topics, mock_tax, store):
    """Two attempts at the same topic: mastery uses the best score, not the latest."""
    store.write_session(_grammar_log("s1", "Present tense — regular verbs", 0.9))
    store.write_session(_grammar_log("s2", "Present tense — regular verbs", 0.3))

    mastery = get_module_mastery(store, "user1", "german", "grammar")
    assert mastery.topics_mastered == 1


@patch("orchestrator.mastery.get_taxonomy", return_value=_TAXONOMY)
@patch("orchestrator.mastery.get_grammar_topics", return_value=None)
def test_grammar_mastery_no_topics_map_configured(mock_topics, mock_tax, store):
    """Language with no grammar_topics map configured -> zero totals, no crash."""
    mastery = get_module_mastery(store, "user1", "german", "grammar")
    assert mastery.topics_total == 0
    assert mastery.mastery_ratio == 0.0


@patch("orchestrator.mastery.get_taxonomy", return_value=_TAXONOMY)
@patch("orchestrator.mastery.get_grammar_topics", return_value=_GRAMMAR_TOPICS)
def test_writing_mastery_word_counts_and_ratio(mock_topics, mock_tax, store):
    store.write_session(_writing_log("w1", word_count=50, level="a1"))
    store.write_session(_writing_log("w2", word_count=70, level="a1"))
    store.write_session(_writing_log("w3", word_count=200, level="a2"))  # different level

    mastery = get_module_mastery(store, "user1", "german", "writing")

    assert mastery.texts_written == 3  # all-time total, unlike the ratio below
    assert mastery.total_words == 320
    assert mastery.words_at_current_level == 120  # only the two a1 sessions (current level)
    assert mastery.mastery_ratio == 2 / TEXTS_PER_LEVEL_FOR_MASTERY  # only the two a1 sessions count


@patch("orchestrator.mastery.get_taxonomy", return_value=_TAXONOMY)
@patch("orchestrator.mastery.get_grammar_topics", return_value=_GRAMMAR_TOPICS)
def test_writing_mastery_ratio_caps_at_one(mock_topics, mock_tax, store):
    for i in range(TEXTS_PER_LEVEL_FOR_MASTERY + 3):
        store.write_session(_writing_log(f"w{i}", word_count=10))  # default level="a1" == current level

    mastery = get_module_mastery(store, "user1", "german", "writing")
    assert mastery.mastery_ratio == 1.0


@patch("orchestrator.mastery.get_taxonomy", return_value=_TAXONOMY)
@patch("orchestrator.mastery.get_grammar_topics", return_value=_GRAMMAR_TOPICS)
def test_weak_tags_require_recurrence_and_use_human_labels(mock_topics, mock_tax, store):
    log1 = _grammar_log("s1", "Dative case — prepositions", 0.5)
    log1.errors = [{"error_tag": "dative_case", "fragment": "x", "explanation": "y"}]
    store.write_session(log1)
    log2 = _grammar_log("s2", "Present tense — regular verbs", 0.9)
    log2.errors = [{"error_tag": "dative_case", "fragment": "x", "explanation": "y"}]
    store.write_session(log2)

    mastery = get_module_mastery(store, "user1", "german", "grammar")
    assert mastery.weak_tags == ["Dative case errors"]


def test_level_trend_chronological_and_skips_missing_estimates(store):
    old = datetime.now() - timedelta(days=2)
    new = datetime.now() - timedelta(days=1)
    store.write_session(_writing_log("w1", word_count=10, text_level_estimate="a2", date=new))
    store.write_session(_writing_log("w2", word_count=10, text_level_estimate="a1", date=old))
    store.write_session(_writing_log("w3", word_count=10, text_level_estimate=None))

    trend = get_level_trend(store, "user1", "german", module="writing")
    assert [t["level"] for t in trend] == ["a1", "a2"]
