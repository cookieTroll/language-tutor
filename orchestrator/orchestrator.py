import os
from dataclasses import asdict
from datetime import datetime, timedelta
from config import AppConfig
from memory.protocols import StorageProtocol, SessionLog, UserProfile
from llm.base import BaseLLM
from orchestrator.protocols import OrchestratorProtocol, ProgressSummary, ExerciseRecommendation
from orchestrator.session_manager import SessionManager
from skills.summarize_progress.skill import SummarizeProgressSkill
from skills.summarize_writing_history.skill import SummarizeWritingHistorySkill
from skills.cefr_estimator.skill import CefrEstimatorSkill
from skills.protocols import SkillInput
from modules.registry import MODULE_REGISTRY
from shared.io import IOHandler
from shared.error_log import log_skill_error
from lang.loader import using_defaults
from orchestrator.mastery import get_module_mastery, get_level_trend

DEFAULT_RECOMMENDATION = ExerciseRecommendation(
    module="writing",
    reason="Not enough session history yet — starting with writing.",
    suggested_focus=None
)

DEFAULT_HISTORY_SESSIONS = 10  # /history with no argument: how many past writing sessions to summarise
RECURRING_MISTAKE_THRESHOLD = 2  # matches SessionAggregate.recurring_errors' own threshold

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

    def run_session(
        self,
        user_id: str,
        language: str,
        on_language_warning=None,
        forced_recommendation: ExerciseRecommendation | None = None,
    ) -> ExerciseRecommendation | None:
        """Executes a full interactive session lifecycle.
        on_language_warning: optional callable(language, missing_maps) for UI to display config warnings.
        forced_recommendation: when set, skips summarize/recommend/confirm and runs this
        module directly — used to chain straight into a session accepted from the
        previous session's next_actions prompt.
        Returns the ExerciseRecommendation the user accepted from the end-of-session
        prompt (for the caller to re-invoke run_session with), or None otherwise.
        """
        # 0. Check interrupted sessions
        self._handle_interruption(user_id)

        # 1. Select language and user profile
        selected_lang, profile = self._select_language_and_profile(user_id, language)
        self._check_language_config(selected_lang, on_warn=on_language_warning)

        if forced_recommendation is not None:
            recommendation = forced_recommendation
            module_key = recommendation.module
        else:
            # 2 & 3. Summarize and recommend
            summary = self.summarize_progress(user_id, selected_lang)
            recommendation = self.recommend_exercise(summary)

            # 4. Present recommendation, confirm or override
            module_key = self._get_confirmed_module(recommendation, user_id, selected_lang, profile)
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
            return None

        # 8-13. Finalize session
        self._session_manager.finalize_session(
            user_id, selected_lang, module_key, session_id, profile, result, file_content, checkpoint_path,
            error_frequency=ctx.error_frequency,
        )

        # 14. Offer to chain straight into a suggested next action, if any
        if file_content.next_actions:
            signal = file_content.next_actions[0]
            focus_label = f" on '{signal.suggested_focus}'" if signal.suggested_focus else ""
            choice = self.io.prompt(
                f"\nSession complete. Start {signal.module} practice{focus_label} now? "
                f"This will begin a new session. [Y/n]: "
            ).strip().lower()
            accepted = choice != "n"
            self._session_manager.record_next_action_decision(file_content, accepted)
            if accepted:
                return ExerciseRecommendation(
                    module=signal.module, reason=signal.reason, suggested_focus=signal.suggested_focus
                )

        return None

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

    def _confirm_or_update_explanation_language(self, profile: UserProfile) -> None:
        """Explanations/summaries (dump_grammar, /history) are written in this
        language, not necessarily the target study language — e.g. a German
        learner may still want grammar explained in English. Reconfirmed each
        session like level, so it's easy to change without a dedicated command."""
        self.io.output(f"Explanations/summaries language: {profile.explanation_language.capitalize()}")
        choice = self.io.prompt("Press Enter to keep, or type a new language: ").strip().lower()
        if choice and choice != profile.explanation_language:
            profile.explanation_language = choice

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
            explanation_language = self.io.prompt(
                "Which language should explanations/summaries be written in? [default: English]: "
            ).strip().lower() or "english"
            profile = UserProfile(
                user_id=user_id,
                language=selected_lang,
                level=level,
                level_source="stated",
                active=True,
                created_at=datetime.now(),
                updated_at=datetime.now(),
                explanation_language=explanation_language,
            )
            self.store.write_user_profile(profile)
        else:
            self._confirm_or_update_level(user_id, profile)
            self._confirm_or_update_explanation_language(profile)
            profile.active = True
            profile.updated_at = datetime.now()
            self.store.write_user_profile(profile)

        return selected_lang, profile

    def _get_confirmed_module(
        self, recommendation: ExerciseRecommendation, user_id: str, language: str,
        profile: UserProfile | None = None,
    ) -> str:
        focus_line = f"\nSuggested focus: {recommendation.suggested_focus}" if recommendation.suggested_focus else ""
        self.io.output(
            f"\n[Recommendation]: We suggest using the '{recommendation.module.upper()}' module."
            f"\nReason: {recommendation.reason}"
            f"{focus_line}"
        )

        history_hint = (
            " (writing-history report: /history for last 10 sessions,"
            " /history <n> e.g. /history 5 for last n sessions,"
            " /history <n>d e.g. /history 7d for last n days,"
            " add lang:<language> e.g. /history 5 lang:german to change the"
            " report's language (default: your explanation-language setting),"
            " /progress for mastery + level progress)"
        ) if self.io.show_cli_hints else ""
        available = ", ".join(MODULE_REGISTRY.keys())
        default_report_language = profile.explanation_language if profile else "english"

        while True:
            choice = self.io.prompt(
                f"\nAccept suggestion? [Y/Enter to accept, or type a module name to switch]"
                f"\nAvailable modules: {available}{history_hint}"
                f"\n> "
            ).strip().lower()

            if choice.startswith("/history"):
                self._handle_history_command(user_id, language, choice, default_report_language)
                continue

            if choice == "/progress":
                self._handle_progress_command(user_id, language)
                continue

            if choice in ("", "y"):
                return recommendation.module

            if choice in MODULE_REGISTRY:
                return choice

            self.io.output(
                f"[!] Invalid module. Falling back to suggested module '{recommendation.module}'."
            )
            return recommendation.module

    def _parse_history_scope(self, arg: str) -> tuple[str, int] | None:
        """Returns (kind, n) where kind is 'sessions' or 'days'. None if arg is malformed."""
        if not arg:
            return "sessions", DEFAULT_HISTORY_SESSIONS
        if arg.endswith("d") and arg[:-1].isdigit() and int(arg[:-1]) > 0:
            return "days", int(arg[:-1])
        if arg.isdigit() and int(arg) > 0:
            return "sessions", int(arg)
        return None

    def _split_history_args(self, arg: str, default_report_language: str = "english") -> tuple[str, str]:
        """Splits raw /history args into (scope_arg, report_language).

        A token prefixed 'lang:' (e.g. 'lang:german') overrides the report's
        output language for this one call; every other token is passed through
        unchanged to _parse_history_scope. Explicit prefix rather than "any
        non-numeric token is a language" so a genuinely malformed scope arg
        (e.g. 'abc') still fails validation instead of being silently
        reinterpreted. Absent an override, report_language falls back to the
        caller-supplied default (the user's profile explanation_language) —
        recurring_mistakes/topics are about {language} content, but the report
        itself is meta-commentary the learner reads."""
        report_language = default_report_language
        scope_tokens = []
        for token in arg.split():
            if token.lower().startswith("lang:"):
                report_language = token.split(":", 1)[1] or report_language
            else:
                scope_tokens.append(token)
        return " ".join(scope_tokens), report_language

    def _handle_history_command(
        self, user_id: str, language: str, raw_command: str, default_report_language: str = "english",
    ) -> None:
        """On-demand writing-history report (Layer 2b). Not tied to any specific session;
        nothing here is written back to storage — regenerated fresh on every request.

        Currently does arg validation, window filtering, and all three aggregations
        (topics/recurring mistakes/level trend) in one method — acceptable at this size,
        but if /history grows more scope (more aggregations, other modules, etc.) split
        the window-filtering and aggregation-building into their own helpers first.
        """
        raw_arg = raw_command[len("/history"):].strip()
        scope_arg, report_language = self._split_history_args(raw_arg, default_report_language)
        scope = self._parse_history_scope(scope_arg)
        if scope is None:
            self.io.output(
                "[!] Invalid /history argument. Use '/history', '/history <n>' (sessions), "
                "or '/history <n>d' (days)."
            )
            return
        kind, n = scope

        completed = [
            s for s in self.store.get_sessions_by_module(user_id, language, "writing")
            if s.status == "completed"
        ]
        if kind == "sessions":
            window = completed[:n]
            scope_label = f"last {n} session{'s' if n != 1 else ''}"
        else:
            cutoff = datetime.now() - timedelta(days=n)
            window = [s for s in completed if s.date >= cutoff]
            scope_label = f"last {n} day{'s' if n != 1 else ''}"

        if not window:
            self.io.output("\nNo completed writing sessions in that window yet.")
            return

        topics = list(dict.fromkeys(s.task_label for s in window if s.task_label))

        tag_counts: dict[str, int] = {}
        for s in window:
            for e in s.errors:
                tag = e.get("error_tag")
                if tag:
                    tag_counts[tag] = tag_counts.get(tag, 0) + 1
        recurring_mistakes = [
            {"error_tag": tag, "count": count}
            for tag, count in sorted(tag_counts.items(), key=lambda x: -x[1])
            if count >= RECURRING_MISTAKE_THRESHOLD
        ]

        level_trend = [
            {"date": s.date.strftime("%Y-%m-%d"), "level": s.text_level_estimate}
            for s in reversed(window)  # window is newest-first; trend reads oldest-to-newest
            if s.text_level_estimate
        ]

        skill = SummarizeWritingHistorySkill()
        out = skill.run(
            SkillInput(
                user_id=user_id,
                level=self.store.get_current_level(user_id),
                parameters={
                    "language": language,
                    "report_language": report_language,
                    "scope_label": scope_label,
                    "topics": topics,
                    "recurring_mistakes": recurring_mistakes,
                    "level_trend": level_trend,
                },
            ),
            self.llm,
        )
        if not out.success:
            log_skill_error(
                "orchestrator", "summarize_writing_history", out.metadata.get("error", ""),
                {"user_id": user_id, "language": language},
            )
            self.io.output("\n[!] Could not generate a history summary right now.")
            return

        self.io.output(f"\n--- Writing History ({scope_label}) ---\n{out.metadata['history_summary']}")

    def _handle_progress_command(self, user_id: str, language: str) -> None:
        """On-demand mastery + level progress report (Layer 2c). Same on-demand shape
        as /history: nothing is written back to storage except the optional,
        user-confirmed level-up at the end.

        Rendering itself is delegated to the IOHandler (io.render_progress), the same
        way render_evaluation/render_exercises/render_results work — this method only
        gathers structured data, so TerminalIOHandler can draw ASCII bars while the web
        UI renders an actual dial (see ui/static/progress-ui.js)."""
        profile = self.store.get_user_profile(user_id, language)
        current_level = profile.level if profile else self.store.get_current_level(user_id)

        grammar_mastery = get_module_mastery(self.store, user_id, language, "grammar")
        writing_mastery = get_module_mastery(self.store, user_id, language, "writing")
        trend = get_level_trend(self.store, user_id, language, module="writing")

        self.io.render_progress({
            "current_level": current_level,
            "modules": [asdict(grammar_mastery), asdict(writing_mastery)],
            "trend": trend,
        })

        skill = CefrEstimatorSkill()
        out = skill.run(
            SkillInput(user_id=user_id, level=current_level, parameters={"mastery": grammar_mastery}),
            self.llm,
        )
        if out.metadata.get("should_level_up"):
            next_level = out.metadata["next_level"]
            choice = self.io.prompt(
                f"\nYou've mastered all curated grammar topics for {current_level.upper()}. "
                f"Advance to {next_level.upper()}? [Y/n]: "
            ).strip().lower()
            if choice != "n":
                self.store.write_level(user_id, next_level, "estimated")
                self.io.output(f"[*] Level updated to {next_level.upper()}.")
