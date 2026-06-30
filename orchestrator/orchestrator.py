import os
from datetime import datetime
from config import AppConfig
from memory.protocols import StorageProtocol, SessionLog, UserProfile
from llm.base import BaseLLM
from orchestrator.protocols import OrchestratorProtocol, ProgressSummary, ExerciseRecommendation
from orchestrator.session_manager import SessionManager
from skills.summarize_progress.skill import SummarizeProgressSkill
from skills.protocols import SkillInput
from modules.registry import MODULE_REGISTRY
from shared.io import IOHandler
from lang.loader import using_defaults

DEFAULT_RECOMMENDATION = ExerciseRecommendation(
    module="writing",
    reason="Not enough session history yet — starting with writing.",
    suggested_focus=None
)

class Orchestrator(OrchestratorProtocol):
    def __init__(self, store: StorageProtocol, llm: BaseLLM, config: AppConfig, io: IOHandler):
        self.store = store
        self.llm = llm
        self.config = config
        self.io = io
        self._warned_languages: set[str] = set()
        self._session_manager = SessionManager(store, config, llm, io)

    def summarize_progress(self, user_id: str, language: str) -> ProgressSummary | None:
        """Returns None if below cold_start_threshold; otherwise calls SummarizeProgressSkill."""
        agg = self.store.get_session_aggregate(user_id, language)
        total_completed = sum(agg.sessions_by_module.values())

        if total_completed < self.config.cold_start_threshold:
            return None

        level = self.store.get_current_level(user_id)
        available_modules = list(MODULE_REGISTRY.keys())

        skill = SummarizeProgressSkill()
        out = skill.run(
            SkillInput(
                user_id=user_id,
                level=level,
                parameters={
                    "aggregate": agg.model_dump(),
                    "modules": available_modules,
                },
            ),
            self.llm,
        )

        weakest_module = out.metadata.get("weakest_module", "writing")
        if weakest_module not in MODULE_REGISTRY:
            weakest_module = "writing"
        reason = out.metadata.get("recommendation_reason", "")

        return ProgressSummary(
            language=language,
            sessions_by_module=agg.sessions_by_module,
            days_since_module={k: int(v) for k, v in agg.days_since_module.items()},
            total_time_by_module=agg.total_time_by_module,
            recurring_errors=agg.recurring_errors,
            vocab_flag_count=agg.vocab_flag_count,
            recent_topics=agg.recent_topics,
            weakest_module=weakest_module,
            recommendation_reason=reason,
        )

    def recommend_exercise(self, summary: ProgressSummary | None) -> ExerciseRecommendation:
        if summary is None:
            return DEFAULT_RECOMMENDATION

        return ExerciseRecommendation(
            module=summary.weakest_module,
            reason=summary.recommendation_reason,
            suggested_focus=summary.recurring_errors[0] if summary.recurring_errors else None,
        )

    def _handle_interruption(self, user_id: str):
        """Step 0: Check for interrupted sessions and prompt user."""
        interrupted = self.store.get_interrupted_sessions(user_id, self.config.interruption_timeout_minutes)
        if not interrupted:
            return

        self._print_interruption_banner(interrupted)

        while True:
            choice = self.io.prompt("Choice [l/d]: ").strip().lower()
            if choice == "l":
                for s in interrupted:
                    self._session_manager.log_interrupted_session(s, user_id)
                break
            elif choice == "d":
                for s in interrupted:
                    self._session_manager.discard_interrupted_session(s, user_id)
                break
            elif choice == "r":
                self.io.output("[!] Resume option is currently unavailable in PoC mode. Please select 'l' to log or 'd' to discard.")
            else:
                self.io.output(f"[!] Invalid option '{choice}'. Please enter 'l' to log or 'd' to discard.")

    def _print_interruption_banner(self, interrupted: list[SessionLog]) -> None:
        session_lines = "\n".join(
            f"- Session ID: {s.session_id} ({s.module} in {s.language}, started {s.started_at})"
            for s in interrupted
        )
        self.io.output(
            "\n=================================================="
            "\n          INTERRUPTED SESSION DETECTED"
            "\n=================================================="
            f"\n{session_lines}"
            "\n--------------------------------------------------"
            "\nWhat would you like to do?"
            "\n  [l] Log it   - Summarize what was completed and start fresh"
            "\n  [d] Discard  - Delete the partial session and start fresh"
            "\n  [r] Resume   - (Unavailable in PoC mode)"
            "\n=================================================="
        )

    def run_session(self, user_id: str, language: str, on_language_warning=None) -> None:
        """Executes a full interactive session lifecycle.
        on_language_warning: optional callable(language, missing_maps) for UI to display config warnings.
        """
        # 0. Check interrupted sessions
        self._handle_interruption(user_id)

        # 1. Select language and user profile
        selected_lang, profile = self._select_language_and_profile(user_id, language)
        self._check_language_config(selected_lang, on_warn=on_language_warning)

        # 2 & 3. Summarize and recommend
        summary = self.summarize_progress(user_id, selected_lang)
        recommendation = self.recommend_exercise(summary)

        # 4. Present recommendation, confirm or override
        module_key = self._get_confirmed_module(recommendation)
        module = MODULE_REGISTRY[module_key]

        # 5. Write-ahead log + checkpoint creation
        session_id, checkpoint_path = self._session_manager.init_write_ahead_log(
            user_id, selected_lang, module_key, profile
        )

        # 6. ContextRequest fulfillment
        parameters = {"suggested_focus": recommendation.suggested_focus} if recommendation.suggested_focus else {}
        ctx = self._session_manager.build_module_context(
            user_id, selected_lang, module_key, profile, module.context_request(), parameters
        )

        # 7. Run module
        try:
            ctx.parameters["checkpoint_path"] = checkpoint_path

            result, file_content = module.run(ctx, self.llm, self.io)

            result.session_id = session_id
            file_content.session_id = session_id

        except KeyboardInterrupt:
            self.io.output("\n[!] Session interrupted. You can resume or log it next time.")
            return

        # 8-13. Finalize session
        self._session_manager.finalize_session(
            user_id, selected_lang, module_key, session_id, profile, result, file_content, checkpoint_path
        )

    def _check_language_config(self, language: str, on_warn=None) -> None:
        if language in self._warned_languages:
            return
        self._warned_languages.add(language)
        defaults = using_defaults(language)
        missing = [k.replace("_", " ") for k, v in defaults.items() if v]
        if missing and on_warn:
            on_warn(language, missing)

    def _confirm_or_update_level(self, user_id: str, profile: UserProfile) -> None:
        self.io.output(f"\nYour current CEFR level: {profile.level.upper()}")
        choice = self.io.prompt("Press Enter to keep, or type a new level (A1–C2): ").strip().lower()
        if choice and choice != profile.level:
            self.store.write_level(user_id, choice, "stated")
            profile.level = choice

    def _select_language_and_profile(self, user_id: str, language: str) -> tuple[str, UserProfile]:
        active_lang = self.store.get_active_language(user_id)
        selected_lang = language

        if active_lang:
            self.io.output(f"\nCurrently studying {active_lang.upper()}.")
            choice = self.io.prompt("Continue or switch language? [Press Enter to continue, or type new language]: ").strip().lower()
            if choice:
                selected_lang = choice
            else:
                selected_lang = active_lang
        else:
            if not selected_lang:
                selected_lang = self.io.prompt("\nWhich language would you like to study? ").strip().lower()

        profile = self.store.get_user_profile(user_id, selected_lang)
        if not profile:
            default = self.config.default_level
            level_input = self.io.prompt(
                f"Enter your CEFR level for {selected_lang.upper()} [default: {default.upper()}]: "
            ).strip().lower()
            level = level_input if level_input else default
            profile = UserProfile(
                user_id=user_id,
                language=selected_lang,
                level=level,
                level_source="stated",
                active=True,
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            self.store.write_user_profile(profile)
        else:
            self._confirm_or_update_level(user_id, profile)
            profile.active = True
            profile.updated_at = datetime.now()
            self.store.write_user_profile(profile)

        return selected_lang, profile

    def _get_confirmed_module(self, recommendation: ExerciseRecommendation) -> str:
        focus_line = f"\nSuggested focus: {recommendation.suggested_focus}" if recommendation.suggested_focus else ""
        self.io.output(
            f"\n[Recommendation]: We suggest using the '{recommendation.module.upper()}' module."
            f"\nReason: {recommendation.reason}"
            f"{focus_line}"
        )

        confirm = self.io.prompt("\nStart this module? [Y/n]: ").strip().lower()
        module_key = recommendation.module

        if confirm == "n":
            self.io.output(f"Available modules: {list(MODULE_REGISTRY.keys())}")
            override = self.io.prompt("Enter module name to run instead: ").strip().lower()
            if override in MODULE_REGISTRY:
                module_key = override
            else:
                self.io.output(f"[!] Invalid module. Falling back to suggested module '{module_key}'.")

        return module_key
