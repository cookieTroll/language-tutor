# LanguageTutor — Contracts

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

### Self-correction retry contract (`skills/protocols.py`)

Every skill that asks the LLM for structured (JSON) output parses/validates that output
through `call_with_self_correction()` rather than parsing inline. This is the retry
contract every skill depends on — not just an implementation detail of one skill.

```python
class SelfCorrectionError(Exception):
    def __init__(self, message: str, raw_response: str | None = None):
        super().__init__(message)
        self.raw_response = raw_response

def call_with_self_correction(
    llm: BaseLLM,
    messages: list[LLMMessage],
    parse_fn: Callable[[str], T],
    temperature: float = 0.1,
) -> T:
    """
    Calls llm.complete(), then parse_fn(response.text) — parse_fn does both JSON
    parsing and schema/business-rule validation, so a raise from either failure
    mode gives the model the same chance to self-correct.

    On failure, appends the bad assistant response plus a user message describing
    the error and retries, up to `llm.config.max_skill_retries` attempts (default 3).
    On final failure, raises SelfCorrectionError — the caller (skill) catches this
    and returns SkillOutput(success=False, ...), never lets it propagate raw.
    """
    ...
```

Callers (e.g. `skills/detect_mistakes/skill.py`, `skills/grade_exercises/skill.py`) follow
the same shape: define a local `parse_fn` that parses and validates the LLM's JSON, call
`call_with_self_correction(llm, messages, parse_fn, temperature=...)`, and catch
`SelfCorrectionError` around it to produce a `SkillOutput(success=False, metadata={"error": ...})`
instead of raising.

---

## IO Contracts (`shared/io.py`)

Thin I/O abstraction passed into modules and orchestrator — keeps storage-free components testable without patching `print`/`input`.

```python
from typing import Protocol, Literal

# Reserved WebIOHandler.prompt()/prompt_block() inputs — never valid answers to any real
# prompt — used by the web UI's "Return to Menu"/"Switch User" buttons to interrupt
# whatever the session thread is currently blocked on.
ABANDON_SESSION_SENTINEL = "__abandon_session__"
SWITCH_USER_SENTINEL = "__switch_user__"

class SessionAbortRequested(Exception):
    """Raised by WebIOHandler when a reserved sentinel input is received instead of a
    real answer. action="restart" (Return to Menu): abandon the in-progress session
    if any, then go back to the module chooser for the same user. action="end"
    (Switch User): abandon the in-progress session if any, then end the whole
    session thread so the browser can log in as someone else."""
    def __init__(self, action: Literal["restart", "end"]):
        self.action = action

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

    def reset_for_new_activity(self) -> None:
        """Signal that the session is returning to the module chooser for a fresh
        activity — a no-op everywhere except WebIOHandler, which tells the browser
        to switch panels back to the setup/chooser view."""
        ...

    def render_evaluation(self, data: dict) -> None:
        """Render writing-session evaluation output (mistakes, corrected text, tips,
        text-level estimate)."""
        ...

    def render_exercises(self, data: dict) -> None:
        """Render a generated exercise list, batched by type.
        data: {"groups": [{"exercise_type", "instruction", "exercises": [{"prompt"}, ...]}, ...]}."""
        ...

    def render_results(self, data: dict) -> None:
        """Render graded exercise results. data: {"items": [...], "score": float}."""
        ...

    def render_progress(self, data: dict) -> None:
        """Render mastery/level-progress data (Layer 2c /progress command).
        data: {"current_level": str, "modules": [asdict(ModuleMastery), ...], "trend": [{"date", "level"}, ...]}."""
        ...

    def start_timer(self, label: str = "Writing") -> None: ...
    def stop_timer(self) -> None: ...

class TerminalIOHandler:
    """Concrete implementation for the local CLI."""
    show_cli_hints = True

    def output(self, text: str = "") -> None:
        print(text)

    def prompt(self, text: str = "") -> str:
        return input(text)

class WebIOHandler:
    """Bridges a blocking session thread to an HTTP/SSE client via two queues — the
    session thread calls output()/prompt() normally, the Flask layer reads events via
    get_event() and posts replies via send_input(). prompt()/prompt_block() raise
    SessionAbortRequested when the client sends one of the reserved sentinels above
    instead of a real answer."""
    show_cli_hints = False
```

---

## Module Contracts (`modules/protocols.py`)

Modules are the middle grain — agents that compose skills to complete a session.

```python
from typing import Protocol
from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel

class WritingPrompt(BaseModel):
    """Exercise specification returned by topic_picker and consumed by WritingModule."""
    topic: str
    requirements: str
    min_words: int
    task_label: str = "writing_free"
    suggested_focus: str | None = None

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
    word_count: int | None = None            # computed at submission (Layer 2c); used for progress-bar flavor stats

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
    word_count: int | None = None            # writing sessions only; None for other modules (Layer 2c)
    score: float | None = None               # grammar sessions only; None for other modules (Layer 2c)

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
    explanation_language: str = "english"  # meta-commentary language (dump_grammar,
                                            # /history) — distinct from `language`,
                                            # the target study language

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
    def get_session_by_id(self, session_id: str) -> SessionLog | None:
        """Look up a single session directly, not scoped to (user_id, language) — added for Layer 3d (MCP server)."""
        ...
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
    def list_users(self) -> list[str]:
        """Return all distinct user_ids with at least one profile — added for Layer 3d (MCP server)."""
        ...

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
        0.  Check interrupted sessions → resume / log / discard
        1.  summarize_progress(user_id, language) — may return None
        2.  recommend_exercise
        3.  Present to user, await confirmation or override
              └─ skipped when forced_recommendation is set — used as-is instead
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
        13. If file_content.next_actions is set, prompt to start it now. Returns the
            accepted recommendation (for the caller to re-invoke run_session with as
            forced_recommendation) or None if declined / not offered.
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

## Language Contracts (`lang/models.py`)

See `docs/lang.md` for the architecture (registry, cross-validation, which maps are
per-language vs. default) and `docs/lang_generation.md` for the LLM generation utility.
This section is the raw shapes only.

```python
class CEFRMap(BaseModel):
    """lang/maps/cefr/*.yaml — one pedagogical focus hint per CEFR level."""
    a1: str = ""
    a2: str = ""
    b1: str = ""
    b2: str = ""
    c1: str = ""
    c2: str = ""
    default: str = "Identify all grammatical, lexical, and spelling errors."

    def get(self, level: str) -> str: ...

class TaxonomyMap(BaseModel):
    """lang/maps/taxonomy/*.yaml — error tag → human-readable description.
    'other' must always be present (enforced by a model validator)."""
    tags: dict[str, str]

    def validate_tag(self, tag: str) -> str:
        """Raises TaxonomyError if tag not in self.tags."""
        ...
    def format_for_prompt(self) -> str: ...
    @property
    def tag_set(self) -> frozenset[str]: ...

class CEFRDescriptorMap(BaseModel):
    """lang/maps/cefr_descriptors/*.yaml — per-level text-complexity descriptions,
    used to ground estimate_text_level. Language-agnostic by default (CEFR is an
    international standard); every language today uses default.yaml."""
    a1: str = ""; a2: str = ""; b1: str = ""; b2: str = ""; c1: str = ""; c2: str = ""
    default: str = "Assess overall text complexity, vocabulary range, grammatical accuracy, and coherence."

    def format_for_prompt(self) -> str: ...

class WritingMinWordsMap(BaseModel):
    """lang/maps/writing_word_ranges/*.yaml — minimum word count per CEFR level."""
    a1: int = 40; a2: int = 60; b1: int = 100; b2: int = 150; c1: int = 200; c2: int = 250

    def get(self, level: str) -> int: ...

class GrammarTopic(BaseModel):
    """One curated syllabus entry. scope='minor' never appears in a loaded map —
    reserved for topics select_grammar proposes on the fly."""
    topic: str
    difficulty: str                      # validated against a1..c2
    scope: Literal["major", "minor"]
    related_error_tags: list[str]        # cross-validated against the language's TaxonomyMap at load time
    in_scope: list[str] = []
    out_of_scope: list[str] = []

class GrammarTopicsMap(BaseModel):
    """lang/maps/grammar_topics/*.yaml (flat YAML list at file root) —
    the syllabus backbone select_grammar picks major topics from."""
    topics: list[GrammarTopic]

    def scope_for(self, topic: str) -> GrammarTopic | None: ...

class ExerciseType(BaseModel):
    """grading is fixed per type, never chosen by the LLM."""
    type: str
    grading: Literal["exact", "llm"]
    description: str
    student_instruction: str

class ExerciseTypesMap(BaseModel):
    """lang/maps/exercise_types/*.yaml (flat YAML list) — exercise-type vocabulary
    for generate_exercises. Pedagogically universal; every language today uses default.yaml."""
    types: list[ExerciseType]

    @property
    def type_names(self) -> frozenset[str]: ...
    def grading_for(self, exercise_type: str) -> str | None: ...
    def instruction_for(self, exercise_type: str) -> str | None: ...
    def format_for_prompt(self) -> str: ...
    def describe_one(self, exercise_type: str) -> str | None:
        """Same one-line format as format_for_prompt, for a single pre-chosen type —
        used when the caller (not the LLM) has already picked the exercise type."""
        ...

class LanguageConfig(BaseModel):
    """lang/languages/{name}.yaml — wires a language to its versioned maps by name."""
    name: str
    cefr_hints: str
    taxonomy: str
    cefr_descriptors: str = "default"
    writing_word_ranges: str = "default"
    grammar_topics: str | None = None    # None → language has no grammar syllabus yet
    exercise_types: str = "default"
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
