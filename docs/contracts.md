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

## IO Contracts (`shared/io.py`)

Thin I/O abstraction passed into modules and orchestrator — keeps storage-free components testable without patching `print`/`input`.

```python
from typing import Protocol

class IOHandler(Protocol):
    show_cli_hints: bool   # True in CLI; False in web/test — controls hint text in banners

    def output(self, text: str = "") -> None:
        """Display text to the user. Multi-line strings passed as a single block."""
        ...

    def prompt(self, text: str = "") -> str:
        """Display a prompt and return the user's input."""
        ...

    def prompt_block(self, text: str = "") -> str:
        """Collect a multi-line answer as one opaque string (e.g. grammar exercise
        block answers). TerminalIOHandler reads until a blank line; WebIOHandler
        just delegates to prompt() since the client already posts the full
        textarea value in one send_input() call."""
        ...

class TerminalIOHandler:
    """Concrete implementation for the local CLI."""
    show_cli_hints = True

    def output(self, text: str = "") -> None:
        print(text)

    def prompt(self, text: str = "") -> str:
        return input(text)
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
        self, ctx: ModuleContext, llm: "BaseLLM", io: "IOHandler"
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
from pydantic import BaseModel, Field, field_validator
from abc import ABC, abstractmethod
from typing import Literal

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
    next_actions: list[NextActionSignal] = Field(default_factory=list)  # set by SessionManager.finalize_session

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
    mistakes: list[dict]           # [{error_tag, fragment, correction, explanation, severity}]
    tips: list[str]                # actionable next-steps (formerly recommendations)
    corrected_text: str
    session_summary: str           # overall 1-2 sentence comment (formerly comment)
    btw_log: list[dict]            # [{question, answer, flagged_word, timestamp}]
    vocab_updates: list[dict]      # [{word, source, occurrence_count}]
    suggested_focus: str | None = None
    text_level_estimate: str | None = None   # CEFR band from Step 5 estimator

class GrammarSessionContent(SessionFileContent):  # Layer 2a
    topic: str
    scope: Literal["major", "minor"]
    explanation: str
    items: list[dict]         # [{prompt, exercise_type, grading, user_answer, correct_answer, correct, feedback, error_tag}]
    score: float
    btw_log: list[dict]       # [{question, answer, flagged_word, timestamp}]
```

---

## Storage Contracts (`memory/protocols.py`)

`StorageProtocol` is composed from five domain-specific sub-protocols. Each sub-protocol can be type-checked independently; the full interface inherits all five.

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
    text_level_estimate: str | None = None   # writing sessions only; None for other modules (Layer 2b)

class SessionAggregate(BaseModel):
    """Aggregated session profile for a (user, language) pair. Used by progress summariser."""
    sessions_by_module: dict[str, int]      # module → completed session count
    days_since_module: dict[str, float]     # module → days since last completed session
    total_time_by_module: dict[str, float]  # module → total minutes
    recurring_errors: list[str]             # error tags with freq >= 2, sorted by freq desc
    recent_topics: list[str]               # last 5 writing task_labels
    vocab_flag_count: int

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

# --- Sub-protocols ---

class SessionStore(Protocol):
    """Session lifecycle and reads — scoped to (user_id, language)."""
    def write_session(self, log: SessionLog) -> None: ...
    def update_session_status(self, session_id: str, status: str) -> None: ...
    def write_file(self, content: SessionFileContent, base_dir: str) -> str:
        """Write to temp path, atomic rename. Returns relative path."""
        ...
    def get_recent_sessions(self, user_id: str, language: str, n: int = 10) -> list[SessionLog]: ...
    def get_sessions_by_module(self, user_id: str, language: str, module: str) -> list[SessionLog]: ...
    def get_error_frequency(self, user_id: str, language: str, module: str | None = None) -> dict[str, int]: ...
    def get_recent_topics(self, user_id: str, language: str, module: str, n: int = 5) -> list[str]: ...
    def get_session_aggregate(self, user_id: str, language: str) -> SessionAggregate: ...
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
    def get_user_languages(self, user_id: str) -> list[str]: ...
    def get_active_language(self, user_id: str) -> str | None: ...

class StorageProtocol(SessionStore, LevelStore, BtwLogStore, VocabStore, ProfileStore, Protocol):
    """Full storage interface — composed from domain-specific sub-protocols."""
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

    def run_session(
        self,
        user_id: str,
        language: str,
        on_language_warning=None,
        forced_recommendation: ExerciseRecommendation | None = None,
    ) -> ExerciseRecommendation | None:
        """
        0.  Check interrupted sessions → resume / log / discard (SessionManager)
        1.  Language selection + user profile (get/create)
        2.  summarize_progress(user_id, language) — may return None
        3.  recommend_exercise
        4.  Present to user, await confirmation or override
              └─ steps 2–4 skipped when forced_recommendation is set — used as-is instead
        5.  Write-ahead: write_session(status='in_progress') + create checkpoint file (SessionManager)
        6.  Fulfill module's ContextRequest from storage (SessionManager)
        7.  module.run(ctx, llm, io) → (ModuleResult, SessionFileContent)
              └─ clock runs; checkpoint transcript written per turn
              └─ /btw handled inline inside module
        8.  write_file() → temp → atomic rename
        9.  update_session_status('completed')
        10. write_session() → full result update
        11. write_btw() for each entry in result.metadata['btw_entries']
        12. write_vocab_flag() for each signal in result.metadata['vocab_signals']
        13. Delete checkpoint file
        14. If file_content.next_actions is set, prompt to start it now; return the
            accepted ExerciseRecommendation for the caller to re-invoke run_session
            with as forced_recommendation, or None if declined / not offered.
        Steps 5, 6, 8–13 delegated to SessionManager.
        """
        ...
```

---

## LLM Contracts (`llm/base.py`)

```python
from dataclasses import dataclass
from abc import ABC, abstractmethod
from config import LLMConfig

@dataclass
class LLMMessage:
    role: str        # system | user | assistant
    content: str

@dataclass
class LLMResponse:
    text: str
    model: str       # actual model used, logged for observability
    truncated: bool = False  # True when finish_reason == length/MAX_TOKENS

class LLMError(Exception):
    """Raised on provider errors, timeouts, or malformed responses."""
    pass

class BaseLLM(ABC):
    config: LLMConfig

    def __init__(self, config: LLMConfig): ...

    @abstractmethod
    def complete(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.2,
        max_tokens: int | None = None,  # None → uses config.max_tokens
    ) -> LLMResponse:
        """Send messages, return response. Raises LLMError on failure."""
        ...

    def check_health(self) -> bool:
        """Returns True if the backend is reachable. Default: True."""
        ...
```

---

## Error Taxonomy (`lang/maps/taxonomy/german_taxonomy_v1.yaml`)

Canonical set of `error_tag` values for German. Loaded at runtime by skills and judge tests.

```yaml
tags:
  noun_declension:      "Noun case endings — nominative, accusative, dative, or genitive inflection"
  adjective_declension: "Adjective endings — strong, weak, or mixed inflection after articles"
  article:              "Article error — wrong gender, wrong case, or missing article"
  verb_conjugation:     "Verb conjugation error — person/number agreement, separable verb splitting, modal verb usage"
  verb_tense:           "Wrong tense selection or auxiliary — e.g. Perfekt vs Präteritum, haben vs sein, Konjunktiv, Futur"
  word_order:           "Word order error — verb-second rule violated, subordinate clause verb placement, adverb fronting"
  vocabulary:           "Wrong word choice, false friend, or register mismatch"
  spelling:             "Spelling error — capitalisation, umlauts, compound words"
  other:                "Error does not clearly fit any category above — use as last resort"
```

The language config (`lang/languages/german.yaml`) points to the active taxonomy version. To add tags without breaking existing fixtures, create `german_taxonomy_v2.yaml` and update the language config — do not edit the v1 file in place.
