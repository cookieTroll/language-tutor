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

    def run_session(self, user_id: str, language: str, on_language_warning=None, extra_parameters: dict | None = None) -> None:
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
