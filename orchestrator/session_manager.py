import os
import uuid
from datetime import datetime
from config import AppConfig
from memory.protocols import (
    StorageProtocol, SessionLog, BtwEntry, VocabFlag, UserProfile, NextActionSignal, GrammarSessionContent,
)
from modules.protocols import ModuleContext, ContextRequest
from llm.base import BaseLLM, LLMMessage
from shared.io import IOHandler
from orchestrator.prompts import INTERRUPTION_SUMMARY_PROMPT
from lang.loader import get_grammar_topics

RECURRING_ERROR_THRESHOLD = 2  # matches SessionAggregate.recurring_errors' own threshold
GRAMMAR_MASTERY_THRESHOLD = 0.8  # score at/above this counts as "topic successfully covered"


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

        merged_parameters = {"explanation_language": profile.explanation_language, **(parameters or {})}
        return ModuleContext(
            user_id=user_id,
            language=language,
            level=profile.level,
            recent_sessions=recent_sessions,
            error_frequency=error_frequency,
            recent_topics=recent_topics,
            vocab_flags=vocab_flags,
            parameters=merged_parameters,
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
        error_frequency: dict[str, int],
    ) -> None:
        file_content.next_actions = self._compute_next_actions(
            module_key, language, result, file_content, error_frequency
        )

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
            text_level_estimate=getattr(file_content, "text_level_estimate", None),
            word_count=getattr(file_content, "word_count", None),
            score=getattr(file_content, "score", None),
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

    def record_next_action_decision(self, file_content, accepted: bool, index: int = 0) -> None:
        """Persist whether the user accepted the end-of-session next_actions suggestion.

        finalize_session() already wrote the session file before the orchestrator asks
        this question (the prompt is interactive and lives in orchestrator.py, not here
        — SessionManager only ever informs via io.output, never prompts). This is a
        small follow-up rewrite of the same file, not a new write path. index picks
        which signal was answered — normally 0, but a declined explicit /btw practice
        request can offer a second, alternative signal (see
        _writing_error_recurrence_signal's requested_topic branch).
        """
        if not file_content.next_actions or index >= len(file_content.next_actions):
            return
        file_content.next_actions[index].accepted = accepted
        self.store.write_file(file_content, self.config.data_root)

    def _compute_next_actions(
        self, module_key: str, language: str, result, file_content, error_frequency: dict[str, int]
    ) -> list[NextActionSignal]:
        """Dispatches to the direction-specific gate for the module that just ran.
        Each direction uses a different signal shape, so it isn't one shared check —
        see the two helpers below."""
        if module_key == "writing":
            return self._writing_error_recurrence_signal(
                language, result.errors, error_frequency,
                requested_topic=result.metadata.get("practice_requested_topic"),
            )
        if module_key == "grammar":
            return self._grammar_mastery_signal(file_content)
        return []

    def _writing_error_recurrence_signal(
        self, language: str, errors: list[dict], error_frequency: dict[str, int],
        requested_topic: str | None = None,
    ) -> list[NextActionSignal]:
        """Suggest a grammar session when a mistake from *this* session both maps to a
        curated grammar topic (existence check via errors) and is already recurring
        (judgment check via error_frequency, freq >= RECURRING_ERROR_THRESHOLD).

        suggested_focus carries the error tag, not a resolved topic name — several
        topics can share a tag (e.g. 12 topics all tag verb_tense) and this check has
        no way to pick the right one for the user's level. Naming a specific topic
        here would risk promising something select_grammar (which does the real,
        level-aware pick when the grammar module actually runs) doesn't deliver.

        requested_topic (from an explicit /btw "help me practice" ask during this
        session's follow-up phase) bypasses the recurring-threshold gate entirely —
        the user already asked, so recency/frequency judgment isn't needed — and,
        unlike the automatic path, returns a second alternative signal too, so the
        orchestrator can offer a different topic if the first is declined.
        """
        topics_map = get_grammar_topics(language.capitalize())
        if topics_map is None:
            return []

        def maps_to_curated_topic(tag: str) -> bool:
            return any(tag in topic.related_error_tags for topic in topics_map.topics)

        if requested_topic is not None:
            ranked = [requested_topic] + sorted(error_frequency, key=lambda t: -error_frequency[t])
            candidates = [t for t in dict.fromkeys(ranked) if maps_to_curated_topic(t)]
            if not candidates:
                return []
            signals = [NextActionSignal(
                module="grammar",
                reason=f"You asked to practice after this session — let's work on '{candidates[0]}'.",
                suggested_focus=candidates[0],
            )]
            if len(candidates) > 1:
                signals.append(NextActionSignal(
                    module="grammar",
                    reason=f"Or how about focusing on '{candidates[1]}' instead?",
                    suggested_focus=candidates[1],
                ))
            return signals

        session_tags = {e.get("error_tag") for e in errors if e.get("error_tag")}
        for tag in session_tags:
            if error_frequency.get(tag, 0) < RECURRING_ERROR_THRESHOLD:
                continue
            if maps_to_curated_topic(tag):
                reason = f"You've repeatedly made '{tag}' mistakes ({error_frequency[tag]}x)."
                return [NextActionSignal(module="grammar", reason=reason, suggested_focus=tag)]
        return []

    def _grammar_mastery_signal(self, file_content) -> list[NextActionSignal]:
        """Suggest a writing session once a grammar topic is successfully covered
        (score >= GRAMMAR_MASTERY_THRESHOLD), to reinforce it in free production.

        Unlike the writing->grammar direction, suggested_focus here is the actual
        topic name, not a tag: WritingModule._pick_topic already reads
        ctx.parameters["suggested_focus"] and works it into the topic-picker prompt
        as "try to practise: {suggested_focus}" — a phrase, not a hard contract like
        generate_exercises' topic — so there's no precision/promise mismatch risk.
        """
        if not isinstance(file_content, GrammarSessionContent):
            return []
        if file_content.score < GRAMMAR_MASTERY_THRESHOLD:
            return []
        reason = f"You scored {file_content.score:.0%} on '{file_content.topic}' — write something using it to lock it in."
        return [NextActionSignal(module="writing", reason=reason, suggested_focus=file_content.topic)]

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
