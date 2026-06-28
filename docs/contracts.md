# GermanTutor — Contracts

All Protocol definitions and shared dataclasses. Include this document in every LLM coding task — all components depend only on these interfaces, never on concrete implementations.

**Rule:** No component imports a concrete class from another component. Only contracts cross boundaries.

---

## Skill Contracts (`skills/protocols.py`)

Skills are the lowest grain — atomic, pure, no storage access.

```python
from typing import Protocol, Literal
from pydantic import BaseModel, field_validator

class SkillInput(BaseModel):
    """Base input for all skills. Each skill defines a typed subclass."""
    user_id: str
    level: str
    parameters: dict                      # skill-specific inputs

    @field_validator("level")
    @classmethod
    def validate_level(cls, v: str) -> str:
        valid_levels = {"a1", "a2", "b1", "b2", "c1", "c2"}
        if v.lower() not in valid_levels:
            raise ValueError(f"Invalid CEFR level: '{v}'. Allowed: {valid_levels}")
        return v.lower()

class SkillOutput(BaseModel):
    """Base output for all skills. Each skill defines a typed subclass."""
    skill_name: str
    success: bool
    metadata: dict                        # skill-specific outputs

class SkillProtocol(Protocol):
    name: str
    description: str
    skill_type: Literal["session", "utility"]
    # session  — full lifecycle, invoked by module, result persisted
    # utility  — invoked inline mid-session (e.g. btw_handler, explain_grammar)
    #            no session file written, returned in ModuleResult.metadata

    def run(self, input: SkillInput, llm: "BaseLLM") -> SkillOutput:
        """
        Execute skill. Pure — no storage calls, no provider SDK calls.
        LLM injected, not constructed inside.
        """
        ...
```

---

## Module Contracts (`modules/protocols.py`)

Modules are the middle grain — agents that compose skills to complete a session.

```python
from typing import Protocol
from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel

class ContextRequest(BaseModel):
    """Declares what a module needs from memory. Orchestrator fulfills it."""
    recent_sessions_n: int = 5
    module_filter: str | None = None      # restrict to sessions of this module
    include_error_frequency: bool = False
    include_recent_topics: bool = False
    include_vocab_flags: bool = False
    # language is always required — not optional, always passed from orchestrator

class ModuleContext(BaseModel):
    """Fulfilled by orchestrator from storage before module.run() is called."""
    user_id: str
    language: str                         # target language for this session
    level: str                            # level for this user+language combination
    recent_sessions: list                 # scoped to (user_id, language)
    error_frequency: dict[str, int]       # scoped to (user_id, language)
    recent_topics: list[str]              # scoped to (user_id, language)
    vocab_flags: list[dict]               # scoped to (user_id, language)
    parameters: dict                      # user overrides from confirmation step

class ModuleResult(BaseModel):
    session_id: str
    module: str
    task_label: str
    task_description: str
    errors: list[dict]                    # structured, fixed error taxonomy
    comment: str
    started_at: datetime
    completed_at: datetime
    duration_minutes: float
    metadata: dict
    # metadata carries:
    #   btw_entries: list[BtwEntry]       — for orchestrator to persist to btw_log
    #   vocab_signals: list[str]          — words for orchestrator to write to vocab_flags

class ModuleProtocol(Protocol):
    name: str
    description: str                      # injected into orchestrator prompt

    def context_request(self) -> ContextRequest:
        """Declare what memory context this module needs."""
        ...

    def run(
        self, ctx: ModuleContext, llm: "BaseLLM"
    ) -> tuple[ModuleResult, "SessionFileContent"]:
        """
        Execute interactive session. Pure — no storage calls.
        Returns structured result (for DB) and file content (for YAML).
        /btw handled inline — BtwEntry list in ModuleResult.metadata.
        Clock: started_at at first user interaction, completed_at on exit.
        """
        ...

    # Optional — implement for checkpoint resumption support (future)
    def save_checkpoint(self, state: dict, checkpoint_dir: str) -> None: ...
    def restore_checkpoint(self, checkpoint_path: str) -> ModuleContext: ...
```

---

## Session File Contracts (`memory/protocols.py`)

```python
from pydantic import BaseModel, field_validator
from abc import ABC, abstractmethod
from typing import Literal

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
    mistakes: list[dict]      # [{error_tag, fragment, correction, explanation}]
    recommendations: list[str]
    corrected_text: str
    comment: str
    btw_log: list[dict]       # [{question, answer, flagged_word, timestamp}]
    vocab_updates: list[dict] # [{word, source, occurrence_count}]
    suggested_focus: str | None = None

class GrammarSessionContent(SessionFileContent):  # Layer 2a
    topic: str
    exercise_type: str
    items: list[dict]         # [{prompt, user_answer, correct, correction, error_tag}]
    score: float
    btw_log: list[dict]
```

---

## Storage Contracts (`memory/protocols.py`)

```python
from typing import Protocol, Literal
from pydantic import BaseModel, field_validator
from datetime import datetime

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
```

---

## Orchestrator Contracts (`orchestrator/protocols.py`)

```python
from typing import Protocol
from pydantic import BaseModel

class ProgressSummary(BaseModel):
    language: str                            # which language this summary covers
    sessions_by_module: dict[str, int]
    days_since_module: dict[str, int]
    total_time_by_module: dict[str, float]   # minutes
    recurring_errors: list[str]
    vocab_flag_count: int
    recent_topics: list[str]
    weakest_module: str                      # validated against MODULE_REGISTRY
    recommendation_reason: str

class ExerciseRecommendation(BaseModel):
    module: str                              # validated against MODULE_REGISTRY
    reason: str
    suggested_focus: str | None = None

class OrchestratorProtocol(Protocol):
    def summarize_progress(self, user_id: str, language: str) -> ProgressSummary | None:
        """None if below cold start threshold for this (user, language) pair.
        weakest_module validated against registry."""
        ...

    def recommend_exercise(
        self, summary: ProgressSummary | None
    ) -> ExerciseRecommendation:
        """Cold start → DEFAULT_RECOMMENDATION. Otherwise LLM over summary."""
        ...

    def run_session(self, user_id: str, language: str) -> None:
        """
        0.  Check interrupted sessions → resume / log / discard
        1.  summarize_progress(user_id, language) — may return None
        2.  recommend_exercise
        3.  Present to user, await confirmation or override
        4.  Write-ahead: write_session(status='in_progress')
        5.  Fulfill module's ContextRequest from storage (all queries scoped to language)
        6.  module.run() → (ModuleResult, SessionFileContent)
              └─ clock runs; checkpoint transcript written per turn
              └─ /btw handled inline inside module
        7.  write_file() → temp → atomic rename
        8.  update_session_status('completed')
        9.  write_session() → full result update
        10. write_btw() for each entry in result.metadata['btw_entries']
        11. write_vocab_flag() for each signal in result.metadata['vocab_signals']
        12. Delete checkpoint file
        """
        ...
              └─ /btw handled inline inside module
        7.  write_file() → temp → atomic rename
        8.  update_session_status('completed')
        9.  write_session() → full result update
        10. write_btw() for each entry in result.metadata['btw_entries']
        11. write_vocab_flag() for each signal in result.metadata['vocab_signals']
        12. Delete checkpoint file
        """
        ...
```

---

## LLM Contracts (`llm/base.py`)

```python
from dataclasses import dataclass
from abc import ABC, abstractmethod

@dataclass
class LLMMessage:
    role: str        # system | user | assistant
    content: str

@dataclass
class LLMResponse:
    text: str
    model: str       # actual model used, logged for observability

class BaseLLM(ABC):
    @abstractmethod
    def complete(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.2,
        max_tokens: int = 1000,
    ) -> LLMResponse:
        """Send messages, return response. Raises LLMError on failure."""
        ...
```

---

## Error Taxonomy (`skills/detect_mistakes/taxonomy.py`)

Fixed set of `error_tag` values. Enforced after mistake processing — unknown tags raise `TaxonomyError`.

```python
ERROR_TAXONOMY: set[str] = {
    # Cases
    "dative_case", "accusative_case", "genitive_case",
    # Word order
    "word_order", "verb_position", "separable_verb",
    # Agreement
    "article_gender", "adjective_ending",
    # Verbs
    "verb_conjugation", "tense_usage",
    # Other
    "vocabulary", "spelling",
}

def validate_error_tag(tag: str) -> str:
    if tag not in ERROR_TAXONOMY:
        raise TaxonomyError(f"Unknown error_tag: '{tag}'. Must be one of {ERROR_TAXONOMY}")
    return tag
```
