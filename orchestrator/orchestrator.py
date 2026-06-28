import os
import json
import uuid
from datetime import datetime
from config import AppConfig
from memory.protocols import StorageProtocol, SessionLog, BtwEntry, VocabFlag, UserProfile
from modules.protocols import ModuleContext
from llm.base import BaseLLM, LLMMessage
from orchestrator.protocols import OrchestratorProtocol, ProgressSummary, ExerciseRecommendation
from orchestrator.prompts import INTERRUPTION_SUMMARY_PROMPT
from modules.registry import MODULE_REGISTRY, get_registry_description

DEFAULT_RECOMMENDATION = ExerciseRecommendation(
    module="writing",
    reason="Not enough session history yet — starting with writing.",
    suggested_focus=None
)

class Orchestrator(OrchestratorProtocol):
    def __init__(self, store: StorageProtocol, llm: BaseLLM, config: AppConfig):
        self.store = store
        self.llm = llm
        self.config = config

    def summarize_progress(self, user_id: str, language: str) -> ProgressSummary | None:
        """
        Summarizes progress. Returns None if completed sessions are below cold_start_threshold.
        """
        recent = self.store.get_recent_sessions(user_id, language, n=10)
        completed = [s for s in recent if s.status == "completed"]
        
        if len(completed) < self.config.cold_start_threshold:
            return None

        # Build basic summary structure for PoC
        error_freq = self.store.get_error_frequency(user_id, language)
        sorted_errors = sorted(error_freq.items(), key=lambda x: x[1], reverse=True)
        recurring_errors = [k for k, v in sorted_errors if v >= 2]
        
        vocab_flags = self.store.get_vocab_flags(user_id, language)
        recent_topics = self.store.get_recent_topics(user_id, language, module="writing", n=5)

        sessions_by_module = {}
        total_time_by_module = {}
        days_since_module = {}
        for s in completed:
            sessions_by_module[s.module] = sessions_by_module.get(s.module, 0) + 1
            total_time_by_module[s.module] = total_time_by_module.get(s.module, 0.0) + (s.duration_minutes or 0.0)
            
        return ProgressSummary(
            language=language,
            sessions_by_module=sessions_by_module,
            days_since_module=days_since_module,
            total_time_by_module=total_time_by_module,
            recurring_errors=recurring_errors,
            vocab_flag_count=len(vocab_flags),
            recent_topics=recent_topics,
            weakest_module="writing",
            recommendation_reason="PoC Mode Summary"
        )

    def recommend_exercise(
        self, summary: ProgressSummary | None
    ) -> ExerciseRecommendation:
        """
        Recommends next exercise. Defaults to writing under cold start.
        """
        if summary is None:
            return DEFAULT_RECOMMENDATION
            
        # PoC: just recommend writing if summary exists
        return ExerciseRecommendation(
            module="writing",
            reason="Continuing practice. Let's work on your writing output.",
            suggested_focus=summary.recurring_errors[0] if summary.recurring_errors else None
        )

    def _handle_interruption(self, user_id: str):
        """
        Step 0: Check for interrupted sessions and prompt user.
        """
        interrupted = self.store.get_interrupted_sessions(user_id, self.config.interruption_timeout_minutes)
        if not interrupted:
            return

        print("\n==================================================")
        print("          INTERRUPTED SESSION DETECTED")
        print("==================================================")
        for s in interrupted:
            print(f"- Session ID: {s.session_id} ({s.module} in {s.language}, started {s.started_at})")
        print("--------------------------------------------------")
        print("What would you like to do?")
        print("  [l] Log it   - Summarize what was completed and start fresh")
        print("  [d] Discard  - Delete the partial session and start fresh")
        print("  [r] Resume   - (Unavailable in PoC mode)")
        print("==================================================")

        while True:
            choice = input("Choice [l/d]: ").strip().lower()
            if choice == "l":
                for s in interrupted:
                    checkpoint_path = os.path.join(self.config.data_root, "checkpoints", user_id, f"{s.session_id}.json")
                    summary = "Interrupted session logged."
                    
                    if os.path.exists(checkpoint_path):
                        try:
                            with open(checkpoint_path, "r", encoding="utf-8") as f:
                                transcript = f.read()
                            prompt = INTERRUPTION_SUMMARY_PROMPT.format(transcript=transcript)
                            response = self.llm.complete([LLMMessage(role="user", content=prompt)])
                            summary = response.text.strip()
                        except Exception as e:
                            summary = f"Interrupted session. Error summarizing: {e}"
                            
                    # Update status to interrupted
                    self.store.update_session_status(s.session_id, "interrupted")
                    
                    # Create final session log entry
                    s.status = "interrupted"
                    s.comment = summary
                    s.completed_at = datetime.now()
                    s.duration_minutes = 0.0
                    self.store.write_session(s)
                    
                    # Clean up checkpoint
                    if os.path.exists(checkpoint_path):
                        os.remove(checkpoint_path)
                    print(f"Logged session {s.session_id}.")
                break
            elif choice == "d":
                for s in interrupted:
                    self.store.update_session_status(s.session_id, "abandoned")
                    checkpoint_path = os.path.join(self.config.data_root, "checkpoints", user_id, f"{s.session_id}.json")
                    if os.path.exists(checkpoint_path):
                        os.remove(checkpoint_path)
                    print(f"Discarded session {s.session_id}.")
                break

    def run_session(self, user_id: str, language: str) -> None:
        """
        Executes a full interactive session lifecycle.
        """
        # 0. Check interrupted sessions
        self._handle_interruption(user_id)

        # 1. Select language and user profile
        selected_lang, profile = self._select_language_and_profile(user_id, language)

        # 2 & 3. Summarize and recommend
        summary = self.summarize_progress(user_id, selected_lang)
        recommendation = self.recommend_exercise(summary)

        # 4. Present recommendation, confirm or override
        module_key = self._get_confirmed_module(recommendation)
        module = MODULE_REGISTRY[module_key]

        # 5. Write-ahead session initialization
        session_id = self._init_write_ahead_log(user_id, selected_lang, module_key, profile)

        # 6. ContextRequest fulfillment
        ctx = self._build_module_context(user_id, selected_lang, module_key, profile, module.context_request())

        # Create checkpoint directory & initial checkpoint setup
        checkpoint_dir = os.path.join(self.config.data_root, "checkpoints", user_id)
        os.makedirs(checkpoint_dir, exist_ok=True)
        checkpoint_path = os.path.join(checkpoint_dir, f"{session_id}.json")
        
        # Write initial empty checkpoint file
        with open(checkpoint_path, "w", encoding="utf-8") as f:
            json.dump([], f)

        # 7. Run module
        try:
            # We pass checkpoint path in ctx parameters for module to write if needed
            ctx.parameters["checkpoint_path"] = checkpoint_path
            
            result, file_content = module.run(ctx, self.llm)
            
            # Update result with actual session_id assigned by orchestrator write-ahead
            result.session_id = session_id
            file_content.session_id = session_id
            
        except KeyboardInterrupt:
            # Mark session as interrupted if aborted
            self.store.update_session_status(session_id, "in_progress") # Keep as in_progress to trigger step 0 check
            print("\n[!] Session interrupted. You can resume or log it next time.")
            return

        # 8-13. Finalize session (write YAML file, update DB log, BTW logs, vocab flags, delete checkpoint)
        self._finalize_session(user_id, selected_lang, module_key, session_id, profile, result, file_content, checkpoint_path)

    def _select_language_and_profile(self, user_id: str, language: str) -> tuple[str, UserProfile]:
        active_lang = self.store.get_active_language(user_id)
        selected_lang = language
        
        if active_lang:
            print(f"\nCurrently studying {active_lang.upper()}.")
            choice = input("Continue or switch language? [Press Enter to continue, or type new language]: ").strip().lower()
            if choice:
                selected_lang = choice
            else:
                selected_lang = active_lang
        else:
            if not selected_lang:
                selected_lang = input("\nWhich language would you like to study? ").strip().lower()

        # Load/Create user profile
        profile = self.store.get_user_profile(user_id, selected_lang)
        if not profile:
            level = input(f"Enter your CEFR level for {selected_lang.upper()} (A1-C2): ").strip().lower()
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
            profile.active = True
            profile.updated_at = datetime.now()
            self.store.write_user_profile(profile)
            
        return selected_lang, profile

    def _get_confirmed_module(self, recommendation: ExerciseRecommendation) -> str:
        print(f"\n[Recommendation]: We suggest using the '{recommendation.module.upper()}' module.")
        print(f"Reason: {recommendation.reason}")
        
        confirm = input("\nStart this module? [Y/n]: ").strip().lower()
        module_key = recommendation.module
        
        if confirm == "n":
            print(f"Available modules: {list(MODULE_REGISTRY.keys())}")
            override = input("Enter module name to run instead: ").strip().lower()
            if override in MODULE_REGISTRY:
                module_key = override
            else:
                print(f"[!] Invalid module. Falling back to suggested module '{module_key}'.")
                
        return module_key

    def _init_write_ahead_log(self, user_id: str, selected_lang: str, module_key: str, profile: UserProfile) -> str:
        session_id = str(uuid.uuid4())
        initial_log = SessionLog(
            user_id=user_id,
            session_id=session_id,
            language=selected_lang,
            module=module_key,
            task_label="writing_free",
            task_description="Initializing",
            comment="",
            errors=[],
            level=profile.level,
            date=datetime.now(),
            file_path="",
            status="in_progress",
            started_at=datetime.now()
        )
        self.store.write_session(initial_log)
        return session_id

    def _build_module_context(
        self, user_id: str, selected_lang: str, module_key: str, profile: UserProfile, req
    ) -> ModuleContext:
        recent_sessions = []
        if req.recent_sessions_n > 0:
            recent_sessions = self.store.get_recent_sessions(user_id, selected_lang, req.recent_sessions_n)
            if req.module_filter:
                recent_sessions = [s for s in recent_sessions if s.module == req.module_filter]
                
        error_frequency = {}
        if req.include_error_frequency:
            error_frequency = self.store.get_error_frequency(user_id, selected_lang, req.module_filter)
            
        recent_topics = []
        if req.include_recent_topics:
            recent_topics = self.store.get_recent_topics(user_id, selected_lang, module_key, n=5)
            
        vocab_flags = []
        if req.include_vocab_flags:
            vocab_flags = [
                {"word": f.word, "occurrence_count": f.occurrence_count}
                for f in self.store.get_vocab_flags(user_id, selected_lang)
            ]

        return ModuleContext(
            user_id=user_id,
            language=selected_lang,
            level=profile.level,
            recent_sessions=recent_sessions,
            error_frequency=error_frequency,
            recent_topics=recent_topics,
            vocab_flags=vocab_flags,
            parameters={"ui_mode": "cli"}
        )

    def _finalize_session(
        self, user_id: str, selected_lang: str, module_key: str, session_id: str,
        profile: UserProfile, result, file_content, checkpoint_path: str
    ) -> None:
        # 8. Write YAML session file
        rel_path = self.store.write_file(file_content, self.config.data_root)

        # 9 & 10. Update session state and write final session result
        result.file_path = rel_path
        self.store.update_session_status(session_id, "completed")
        
        final_log = SessionLog(
            user_id=user_id,
            session_id=session_id,
            language=selected_lang,
            module=module_key,
            task_label=result.task_label,
            task_description=result.task_description,
            comment=result.comment,
            errors=result.errors,
            level=profile.level,
            date=datetime.now(),
            file_path=rel_path,
            status="completed",
            started_at=result.started_at,
            completed_at=result.completed_at,
            duration_minutes=result.duration_minutes
        )
        self.store.write_session(final_log)

        # 11. Write BTW logs
        for entry in result.metadata.get("btw_entries", []):
            entry.session_id = session_id
            self.store.write_btw(entry)

        # 12. Write vocab flags
        for word in result.metadata.get("vocab_signals", []):
            flag = VocabFlag(
                flag_id=str(uuid.uuid4()),
                user_id=user_id,
                language=selected_lang,
                word=word.lower().strip(),
                translation=None,
                source="btw",
                first_seen=datetime.now(),
                last_seen=datetime.now(),
                occurrence_count=1
            )
            self.store.write_vocab_flag(flag)

        # 13. Delete checkpoint file
        if os.path.exists(checkpoint_path):
            os.remove(checkpoint_path)

        print("\n[*] Session successfully saved!")
