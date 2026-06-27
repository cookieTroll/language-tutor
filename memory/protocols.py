from dataclasses import dataclass
from abc import ABC, abstractmethod
from typing import Protocol
from datetime import datetime

@dataclass
class SessionFileContent(ABC):
    """Abstract base. Each module defines a typed subclass."""
    session_id: str
    user_id: str
    language: str                         # target language for this session
    module: str
    task_label: str
    date: str
    level: str
    status: str                           # completed | interrupted

    @abstractmethod
    def to_dict(self) -> dict:
        """Serialize to dict for YAML write. Storage calls this — modules don't."""
        ...

@dataclass
class WritingSessionContent(SessionFileContent):
    topic: str
    requirements: str
    user_text: str
    mistakes: list[dict]      # [{error_tag, fragment, correction, explanation}]
    recommendations: list[str]
    corrected_text: str
    comment: str
    btw_log: list[dict]       # [{question, answer, flagged_word, timestamp}]
    vocab_updates: list[dict] # [{word, source, occurrence_count}]
    suggested_focus: str | None

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
            "topic": self.topic,
            "requirements": self.requirements,
            "user_text": self.user_text,
            "mistakes": self.mistakes,
            "recommendations": self.recommendations,
            "corrected_text": self.corrected_text,
            "comment": self.comment,
            "btw_log": self.btw_log,
            "vocab_updates": self.vocab_updates,
            "suggested_focus": self.suggested_focus,
        }

@dataclass
class GrammarSessionContent(SessionFileContent):  # Layer 2a
    topic: str
    exercise_type: str
    items: list[dict]         # [{prompt, user_answer, correct, correction, error_tag}]
    score: float
    btw_log: list[dict]

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
            "topic": self.topic,
            "exercise_type": self.exercise_type,
            "items": self.items,
            "score": self.score,
            "btw_log": self.btw_log,
        }

@dataclass
class SessionLog:
    user_id: str
    session_id: str
    language: str                         # target language for this session
    module: str
    task_label: str
    task_description: str
    comment: str
    errors: list[dict]
    level: str
    date: datetime
    file_path: str                        # relative to data_root
    status: str                           # in_progress|completed|abandoned|interrupted
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_minutes: float | None = None

@dataclass
class BtwEntry:
    btw_id: str
    session_id: str
    user_id: str
    language: str                         # denormalized from session
    question: str
    answer: str
    flagged_word: str | None
    timestamp: datetime

@dataclass
class VocabFlag:
    flag_id: str
    user_id: str
    language: str                         # which language this word belongs to
    word: str
    translation: str | None
    source: str                           # btw | evaluator | manual
    first_seen: datetime
    last_seen: datetime
    occurrence_count: int

@dataclass
class UserProfile:
    user_id: str
    language: str
    level: str
    level_source: str                     # stated | estimated | cefr_module
    active: bool                          # last language selected by user
    created_at: datetime
    updated_at: datetime

class StorageProtocol(Protocol):
    # Session lifecycle
    def write_session(self, log: SessionLog) -> None: ...
    def update_session_status(self, session_id: str, status: str) -> None: ...
    def write_file(self, content: SessionFileContent, base_dir: str) -> str:
        """Write to temp path, atomic rename. Returns relative path."""
        ...

    # Session reads — all scoped to (user_id, language)
    def get_recent_sessions(self, user_id: str, language: str, n: int = 10) -> list[SessionLog]: ...
    def get_sessions_by_module(self, user_id: str, language: str, module: str) -> list[SessionLog]: ...
    def get_error_frequency(self, user_id: str, language: str, module: str | None = None) -> dict[str, int]: ...
    def get_recent_topics(self, user_id: str, language: str, module: str, n: int = 5) -> list[str]: ...
    def get_interrupted_sessions(self, user_id: str, timeout_minutes: int) -> list[SessionLog]:
        """Not language-scoped — surface all interrupted sessions regardless of language."""
        ...

    # Level
    def get_current_level(self, user_id: str) -> str: ...
    def write_level(self, user_id: str, level: str, source: str) -> None:
        """source: stated | estimated | cefr_module"""
        ...

    # /btw log
    def write_btw(self, entry: BtwEntry) -> None: ...
    def get_btw_log(self, user_id: str, language: str, session_id: str | None = None) -> list[BtwEntry]: ...

    # Negative vocab list — scoped to (user_id, language)
    def get_vocab_flags(self, user_id: str, language: str) -> list[VocabFlag]: ...
    def write_vocab_flag(self, flag: VocabFlag) -> None:
        """Insert or increment occurrence_count + update last_seen.
        Unique constraint on (user_id, language, word)."""
        ...

    # User profiles — one row per (user_id, language)
    def get_user_profile(self, user_id: str, language: str) -> UserProfile | None: ...
    def write_user_profile(self, profile: UserProfile) -> None:
        """Insert or update. Sets active=True, sets active=False on all other languages for this user."""
        ...
    def get_user_languages(self, user_id: str) -> list[str]:
        """Return all languages this user has a profile for."""
        ...
    def get_active_language(self, user_id: str) -> str | None:
        """Return the language where active=True, or None if no profile exists."""
        ...
