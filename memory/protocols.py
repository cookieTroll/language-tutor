from abc import ABC, abstractmethod
import os
from typing import Protocol, Literal
from datetime import datetime
import yaml
from pydantic import BaseModel, Field, field_validator

class NextActionSignal(BaseModel):
    """Cross-module recommendation signal, e.g. writing -> grammar on a recurring error.

    Kept separate from orchestrator.protocols.ExerciseRecommendation to respect the
    memory -> orchestrator dependency direction, despite the shape overlap.
    """
    module: str
    reason: str
    suggested_focus: str | None = None
    accepted: bool | None = None  # None until the end-of-session prompt is answered


class SessionFileContent(BaseModel, ABC):
    """Abstract base. Each module defines a typed subclass."""
    session_id: str
    user_id: str
    language: str                         # target language for this session
    module: str
    task_label: str
    date: str
    level: str
    status: Literal["completed", "interrupted"]
    next_actions: list[NextActionSignal] = Field(default_factory=list)

    @field_validator("level")
    @classmethod
    def validate_level(cls, v: str) -> str:
        valid_levels = {"a1", "a2", "b1", "b2", "c1", "c2"}
        if v.lower() not in valid_levels:
            raise ValueError(f"Invalid CEFR level: '{v}'. Allowed: {valid_levels}")
        return v.lower()

    def to_dict(self) -> dict:
        """Serialize to dict for YAML write. Storage calls this — modules don't."""
        return self.model_dump()

class WritingSessionContent(SessionFileContent):
    topic: str
    requirements: str
    user_text: str
    mistakes: list[dict]      # [{error_tag, fragment, correction, explanation, severity}]
    tips: list[str]
    corrected_text: str
    session_summary: str
    btw_log: list[dict]       # [{question, answer, flagged_word, timestamp}]
    vocab_updates: list[dict] # [{word, source, occurrence_count}]
    suggested_focus: str | None = None
    text_level_estimate: str | None = None
    word_count: int | None = None  # computed at submission (Layer 2c); progress-bar flavor stat

class GrammarSessionContent(SessionFileContent):  # Layer 2a
    topic: str
    scope: Literal["major", "minor"]
    explanation: str
    items: list[dict]         # [{prompt, exercise_type, grading, user_answer, correct_answer, correct, feedback, error_tag}]
    score: float
    btw_log: list[dict]       # [{question, answer, flagged_word, timestamp}]

class SessionLog(BaseModel):
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
    status: Literal["in_progress", "completed", "abandoned", "interrupted"]
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_minutes: float | None = None
    text_level_estimate: str | None = None  # writing sessions only; None for other modules
    word_count: int | None = None  # writing sessions only; None for other modules (Layer 2c)
    score: float | None = None     # grammar sessions only; None for other modules (Layer 2c)

    @field_validator("level")
    @classmethod
    def validate_level(cls, v: str) -> str:
        valid_levels = {"a1", "a2", "b1", "b2", "c1", "c2"}
        if v.lower() not in valid_levels:
            raise ValueError(f"Invalid CEFR level: '{v}'. Allowed: {valid_levels}")
        return v.lower()

class BtwEntry(BaseModel):
    btw_id: str
    session_id: str
    user_id: str
    language: str                         # denormalized from session
    question: str
    answer: str
    flagged_word: str | None = None
    timestamp: datetime

class VocabFlag(BaseModel):
    flag_id: str
    user_id: str
    language: str                         # which language this word belongs to
    word: str
    translation: str | None = None
    source: Literal["btw", "evaluator", "manual"]
    first_seen: datetime
    last_seen: datetime
    occurrence_count: int

class UserProfile(BaseModel):
    user_id: str
    language: str
    level: str
    level_source: Literal["stated", "estimated", "cefr_module"]
    active: bool                          # last language selected by user
    created_at: datetime
    updated_at: datetime

    @field_validator("level")
    @classmethod
    def validate_level(cls, v: str) -> str:
        valid_levels = {"a1", "a2", "b1", "b2", "c1", "c2"}
        if v.lower() not in valid_levels:
            raise ValueError(f"Invalid CEFR level: '{v}'. Allowed: {valid_levels}")
        return v.lower()

class SessionAggregate(BaseModel):
    """Aggregated session profile for a (user, language) pair. Used by progress summariser."""
    sessions_by_module: dict[str, int]      # module → completed session count
    days_since_module: dict[str, float]     # module → days since last completed session
    total_time_by_module: dict[str, float]  # module → total minutes
    recurring_errors: list[str]             # error tags with freq >= 2, sorted by freq desc
    recent_topics: list[str]               # last 5 writing task_labels
    vocab_flag_count: int


class SessionStore(Protocol):
    """Session lifecycle and reads — scoped to (user_id, language)."""

    def write_session(self, log: SessionLog) -> None: ...
    def update_session_status(self, session_id: str, status: str) -> None: ...
    def write_file(self, content: SessionFileContent, base_dir: str) -> str:
        """Write to temp path, atomic rename. Returns relative path."""
        ...
    def get_recent_sessions(self, user_id: str, language: str, n: int = 10) -> list[SessionLog]: ...
    def get_sessions_by_module(self, user_id: str, language: str, module: str) -> list[SessionLog]: ...
    def get_session_by_id(self, session_id: str) -> "SessionLog | None": ...
    def get_error_frequency(self, user_id: str, language: str, module: str | None = None) -> dict[str, int]: ...
    def get_recent_topics(self, user_id: str, language: str, module: str, n: int = 5) -> list[str]: ...
    def get_session_aggregate(self, user_id: str, language: str) -> "SessionAggregate":
        """Return a structured profile bundling session counts, error frequency, topics, and vocab flags."""
        ...
    def get_interrupted_sessions(self, user_id: str, timeout_minutes: int) -> list[SessionLog]:
        """Not language-scoped — surface all interrupted sessions regardless of language."""
        ...


class LevelStore(Protocol):
    """User CEFR level tracking."""

    def get_current_level(self, user_id: str) -> str: ...
    def write_level(self, user_id: str, level: str, source: str) -> None:
        """source: stated | estimated | cefr_module"""
        ...


class BtwLogStore(Protocol):
    """By-the-way question/answer log."""

    def write_btw(self, entry: BtwEntry) -> None: ...
    def get_btw_log(self, user_id: str, language: str, session_id: str | None = None) -> list[BtwEntry]: ...


class VocabStore(Protocol):
    """Negative vocab list — scoped to (user_id, language)."""

    def get_vocab_flags(self, user_id: str, language: str) -> list[VocabFlag]: ...
    def write_vocab_flag(self, flag: VocabFlag) -> None:
        """Insert or increment occurrence_count + update last_seen.
        Unique constraint on (user_id, language, word)."""
        ...


class ProfileStore(Protocol):
    """User profiles — one row per (user_id, language)."""

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
    def list_users(self) -> list[str]:
        """Return all distinct user_ids with at least one profile."""
        ...


class StorageProtocol(SessionStore, LevelStore, BtwLogStore, VocabStore, ProfileStore, Protocol):
    """Full storage interface — composed from domain-specific sub-protocols."""

class BaseSessionStore(StorageProtocol, ABC):
    def __init__(self, data_root: str):
        self.data_root = data_root

    def get_session_aggregate(self, user_id: str, language: str) -> "SessionAggregate":
        from datetime import datetime as _dt
        now = _dt.now()

        all_sessions = self.get_recent_sessions(user_id, language, n=10_000)
        by_module: dict[str, list] = {}
        for s in all_sessions:
            if s.status == "completed":
                by_module.setdefault(s.module, []).append(s)

        sessions_by_module: dict[str, int] = {}
        days_since_module: dict[str, float] = {}
        total_time_by_module: dict[str, float] = {}
        for mod, logs in by_module.items():
            sessions_by_module[mod] = len(logs)
            total_time_by_module[mod] = sum(s.duration_minutes or 0.0 for s in logs)
            latest = max((s.completed_at for s in logs if s.completed_at), default=None)
            if latest:
                days_since_module[mod] = (now - latest).total_seconds() / 86400.0

        error_freq = self.get_error_frequency(user_id, language)
        recurring_errors = [
            tag for tag, freq in sorted(error_freq.items(), key=lambda x: -x[1]) if freq >= 2
        ]
        recent_topics = self.get_recent_topics(user_id, language, module="writing", n=5)
        vocab_flag_count = len(self.get_vocab_flags(user_id, language))

        return SessionAggregate(
            sessions_by_module=sessions_by_module,
            days_since_module=days_since_module,
            total_time_by_module=total_time_by_module,
            recurring_errors=recurring_errors,
            recent_topics=recent_topics,
            vocab_flag_count=vocab_flag_count,
        )

    def write_file(self, content: SessionFileContent, base_dir: str) -> str:
        # Determine paths
        # Relative file_path schema: sessions/{user_id}/{language}/{session_id}.yaml
        rel_dir = os.path.join("sessions", content.user_id, content.language)
        abs_dir = os.path.join(base_dir, rel_dir)
        os.makedirs(abs_dir, exist_ok=True)
        
        filename = f"{content.session_id}.yaml"
        tmp_filename = f"{content.session_id}.yaml.tmp"
        
        abs_path = os.path.join(abs_dir, filename)
        tmp_path = os.path.join(abs_dir, tmp_filename)
        
        yaml_content = yaml.dump(content.to_dict(), sort_keys=False, allow_unicode=True)
        
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(yaml_content)
            
        if os.path.exists(abs_path):
            os.remove(abs_path)
        os.rename(tmp_path, abs_path)
        
        return os.path.join(rel_dir, filename).replace("\\", "/")

    def update_session_status(self, session_id: str, status: str) -> None:
        allowed_status = {"in_progress", "completed", "abandoned", "interrupted"}
        if status not in allowed_status:
            raise ValueError(f"Invalid status: '{status}'. Allowed: {allowed_status}")
        self._update_session_status(session_id, status)

    @abstractmethod
    def _update_session_status(self, session_id: str, status: str) -> None:
        """Subclasses implement backend-specific write of session status."""
        pass

    def _dt_to_str(self, dt: datetime | None) -> str | None:
        if dt is None:
            return None
        return dt.isoformat()

    def _str_to_dt(self, dt_str: str | None) -> datetime | None:
        if not dt_str:
            return None
        try:
            return datetime.fromisoformat(dt_str)
        except ValueError:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
                try:
                    return datetime.strptime(dt_str, fmt)
                except ValueError:
                    continue
            raise
