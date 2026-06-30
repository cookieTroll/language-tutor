import os
import uuid
from datetime import datetime
from config import AppConfig
from memory.protocols import StorageProtocol, SessionLog, BtwEntry, VocabFlag, UserProfile
from modules.protocols import ModuleContext, ContextRequest
from llm.base import BaseLLM, LLMMessage
from shared.io import IOHandler
from orchestrator.prompts import INTERRUPTION_SUMMARY_PROMPT


class SessionManager:
    """Owns session lifecycle operations: write-ahead init, context fulfillment, finalization."""

    def __init__(self, store: StorageProtocol, config: AppConfig, llm: BaseLLM, io: IOHandler):
        self.store = store
        self.config = config
        self.llm = llm
        self.io = io

    # ------------------------------------------------------------------
    # Write-ahead log
    # ------------------------------------------------------------------

    def init_write_ahead_log(
        self, user_id: str, language: str, module_key: str, profile: UserProfile
    ) -> tuple[str, str]:
        """Create WAL session record and empty checkpoint file. Returns (session_id, checkpoint_path)."""
        session_id = str(uuid.uuid4())
        initial_log = SessionLog(
            user_id=user_id,
            session_id=session_id,
            language=language,
            module=module_key,
            task_label="initializing",
            task_description="Initializing",
            comment="",
            errors=[],
            level=profile.level,
            date=datetime.now(),
            file_path="",
            status="in_progress",
            started_at=datetime.now(),
        )
        self.store.write_session(initial_log)

        checkpoint_dir = os.path.join(self.config.data_root, "checkpoints", user_id)
        os.makedirs(checkpoint_dir, exist_ok=True)
        checkpoint_path = os.path.join(checkpoint_dir, f"{session_id}.json")
        with open(checkpoint_path, "w", encoding="utf-8") as f:
            import json
            json.dump([], f)

        return session_id, checkpoint_path

    # ------------------------------------------------------------------
    # Context fulfillment
    # ------------------------------------------------------------------

    def build_module_context(
        self,
        user_id: str,
        language: str,
        module_key: str,
        profile: UserProfile,
        req: ContextRequest,
        parameters: dict | None = None,
    ) -> ModuleContext:
        recent_sessions = []
        if req.recent_sessions_n > 0:
            recent_sessions = self.store.get_recent_sessions(user_id, language, req.recent_sessions_n)
            if req.module_filter:
                recent_sessions = [s for s in recent_sessions if s.module == req.module_filter]

        error_frequency = {}
        if req.include_error_frequency:
            error_frequency = self.store.get_error_frequency(user_id, language, req.module_filter)

        recent_topics = []
        if req.include_recent_topics:
            recent_topics = self.store.get_recent_topics(user_id, language, module_key, n=5)

        vocab_flags = []
        if req.include_vocab_flags:
            vocab_flags = [
                {"word": f.word, "occurrence_count": f.occurrence_count}
                for f in self.store.get_vocab_flags(user_id, language)
            ]

        return ModuleContext(
            user_id=user_id,
            language=language,
            level=profile.level,
            recent_sessions=recent_sessions,
            error_frequency=error_frequency,
            recent_topics=recent_topics,
            vocab_flags=vocab_flags,
            parameters=parameters or {},
        )

    # ------------------------------------------------------------------
    # Finalization
    # ------------------------------------------------------------------

    def finalize_session(
        self,
        user_id: str,
        language: str,
        module_key: str,
        session_id: str,
        profile: UserProfile,
        result,
        file_content,
        checkpoint_path: str,
    ) -> None:
        rel_path = self.store.write_file(file_content, self.config.data_root)

        self.store.update_session_status(session_id, "completed")

        final_log = SessionLog(
            user_id=user_id,
            session_id=session_id,
            language=language,
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
            duration_minutes=result.duration_minutes,
        )
        self.store.write_session(final_log)

        for entry in result.metadata.get("btw_entries", []):
            entry.session_id = session_id
            self.store.write_btw(entry)

        for word in result.metadata.get("vocab_signals", []):
            flag = VocabFlag(
                flag_id=str(uuid.uuid4()),
                user_id=user_id,
                language=language,
                word=word.lower().strip(),
                translation=None,
                source="btw",
                first_seen=datetime.now(),
                last_seen=datetime.now(),
                occurrence_count=1,
            )
            self.store.write_vocab_flag(flag)

        if os.path.exists(checkpoint_path):
            os.remove(checkpoint_path)

        self.io.output("\n[*] Session successfully saved!")

    # ------------------------------------------------------------------
    # Interruption helpers
    # ------------------------------------------------------------------

    def summarize_interrupted_transcript(self, session_id: str, user_id: str) -> str:
        checkpoint_path = os.path.join(
            self.config.data_root, "checkpoints", user_id, f"{session_id}.json"
        )
        if not os.path.exists(checkpoint_path):
            return "Interrupted session logged."
        try:
            with open(checkpoint_path, "r", encoding="utf-8") as f:
                transcript = f.read()
            prompt = INTERRUPTION_SUMMARY_PROMPT.format(transcript=transcript)
            response = self.llm.complete([LLMMessage(role="user", content=prompt)])
            return response.text.strip()
        except Exception as e:
            return f"Interrupted session. Error summarizing: {e}"

    def log_interrupted_session(self, session: SessionLog, user_id: str) -> None:
        summary = self.summarize_interrupted_transcript(session.session_id, user_id)
        self.store.update_session_status(session.session_id, "interrupted")
        session.status = "interrupted"
        session.comment = summary
        session.completed_at = datetime.now()
        session.duration_minutes = 0.0
        self.store.write_session(session)
        self._cleanup_checkpoint(session.session_id, user_id)
        self.io.output(f"Logged session {session.session_id}.")

    def discard_interrupted_session(self, session: SessionLog, user_id: str) -> None:
        self.store.update_session_status(session.session_id, "abandoned")
        self._cleanup_checkpoint(session.session_id, user_id)
        self.io.output(f"Discarded session {session.session_id}.")

    def _cleanup_checkpoint(self, session_id: str, user_id: str) -> None:
        checkpoint_path = os.path.join(
            self.config.data_root, "checkpoints", user_id, f"{session_id}.json"
        )
        if os.path.exists(checkpoint_path):
            os.remove(checkpoint_path)
