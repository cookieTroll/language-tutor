"""Layer 2c — Level & Progress.

Merges the former "CEFR estimator" and "level progression tracking" plans: both
turned out to be renderings of the same mastery data, not independent features
(see docs/CHECKLIST.md). Everything here is derived from data already stored
per session (memory/schema.sql's `sessions` table) — no new history table.
"""
from dataclasses import dataclass, field

from memory.protocols import StorageProtocol
from orchestrator.session_manager import GRAMMAR_MASTERY_THRESHOLD
from lang.loader import get_taxonomy, get_grammar_topics
from shared.slugify import slugify_topic

TEXTS_PER_LEVEL_FOR_MASTERY = 25  # completed writing sessions at the current level for a full bar
WEAK_TAG_THRESHOLD = 2  # matches SessionAggregate.recurring_errors' own threshold
TOP_TAG_COUNT = 3


@dataclass
class ModuleMastery:
    module: str
    topics_total: int = 0        # curated grammar topics at the user's current level
    topics_mastered: int = 0     # of those, best score >= GRAMMAR_MASTERY_THRESHOLD
    texts_written: int = 0       # completed writing sessions
    total_words: int = 0
    words_at_current_level: int = 0
    weak_tags: list[str] = field(default_factory=list)
    strong_tags: list[str] = field(default_factory=list)
    mastery_ratio: float = 0.0


def get_module_mastery(store: StorageProtocol, user_id: str, language: str, module: str) -> ModuleMastery:
    """Aggregate mastery stats for one module, scoped to the user's current level.

    Grammar's ratio is topics_mastered / topics_total *for the current level* (from
    the curated map), not topics attempted — this is the same number that gates the
    level-up decision in skills/cefr_estimator, and what the progress bar renders.
    Writing has no discrete topic unit, so its ratio instead mirrors that per-level
    scoping via session count: completed writing sessions *at the current level*
    against TEXTS_PER_LEVEL_FOR_MASTERY, capped at 1.0. texts_written itself stays
    an all-time total (it's just a display stat), unlike the ratio.
    """
    current_level = store.get_current_level(user_id)
    sessions = [s for s in store.get_sessions_by_module(user_id, language, module) if s.status == "completed"]
    mastery = ModuleMastery(module=module)

    if module == "grammar":
        # task_label is a slugified topic (see modules/grammar/agent.py::_task_label) —
        # slugify the curated topic names the same way to match sessions back to them.
        best_score_by_slug: dict[str, float] = {}
        for s in sessions:
            if s.score is not None:
                best_score_by_slug[s.task_label] = max(best_score_by_slug.get(s.task_label, 0.0), s.score)

        topics_map = get_grammar_topics(language.capitalize())
        topics_for_level = (
            [t.topic for t in topics_map.topics if t.difficulty == current_level and t.scope == "major"]
            if topics_map else []
        )
        mastery.topics_total = len(topics_for_level)
        mastered_topics = [
            topic for topic in topics_for_level
            if best_score_by_slug.get(slugify_topic(topic), 0.0) >= GRAMMAR_MASTERY_THRESHOLD
        ]
        mastery.topics_mastered = len(mastered_topics)
        mastery.mastery_ratio = (
            mastery.topics_mastered / mastery.topics_total if mastery.topics_total else 0.0
        )
        mastery.strong_tags = sorted(
            mastered_topics, key=lambda t: -best_score_by_slug[slugify_topic(t)]
        )[:TOP_TAG_COUNT]

    if module == "writing":
        mastery.texts_written = len(sessions)
        mastery.total_words = sum(s.word_count or 0 for s in sessions)
        texts_at_current_level = sum(1 for s in sessions if s.level == current_level)
        mastery.words_at_current_level = sum(
            s.word_count or 0 for s in sessions if s.level == current_level
        )
        mastery.mastery_ratio = min(texts_at_current_level / TEXTS_PER_LEVEL_FOR_MASTERY, 1.0)

    error_freq = store.get_error_frequency(user_id, language, module)
    taxonomy = get_taxonomy(language)
    tag_labels = taxonomy.tags if taxonomy else {}
    mastery.weak_tags = [
        tag_labels.get(tag, tag)
        for tag, freq in sorted(error_freq.items(), key=lambda x: -x[1])
        if freq >= WEAK_TAG_THRESHOLD
    ][:TOP_TAG_COUNT]

    return mastery


def get_level_trend(store: StorageProtocol, user_id: str, language: str, module: str = "writing") -> list[dict]:
    """Chronological (date, text_level_estimate) pairs — no new computation, pulled
    straight from Layer 2b's per-session field."""
    sessions = [
        s for s in store.get_sessions_by_module(user_id, language, module)
        if s.status == "completed" and s.text_level_estimate
    ]
    sessions.sort(key=lambda s: s.date)
    return [{"date": s.date.strftime("%Y-%m-%d"), "level": s.text_level_estimate} for s in sessions]
