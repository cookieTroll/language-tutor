from typing import Protocol
from dataclasses import dataclass
from datetime import datetime
from llm.base import BaseLLM
from memory.protocols import SessionFileContent

@dataclass
class ContextRequest:
    """Declares what a module needs from memory. Orchestrator fulfills it."""
    recent_sessions_n: int = 5
    module_filter: str | None = None      # restrict to sessions of this module
    include_error_frequency: bool = False
    include_recent_topics: bool = False
    include_vocab_flags: bool = False
    # language is always required — not optional, always passed from orchestrator

@dataclass
class ModuleContext:
    """Fulfilled by orchestrator from storage before module.run() is called."""
    user_id: str
    language: str                         # target language for this session
    level: str                            # level for this user+language combination
    recent_sessions: list                 # scoped to (user_id, language)
    error_frequency: dict[str, int]       # scoped to (user_id, language)
    recent_topics: list[str]              # scoped to (user_id, language)
    vocab_flags: list[dict]               # scoped to (user_id, language)
    parameters: dict                      # user overrides from confirmation step

@dataclass
class ModuleResult:
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
        self, ctx: ModuleContext, llm: BaseLLM
    ) -> tuple[ModuleResult, SessionFileContent]:
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
