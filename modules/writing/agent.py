import json
import os
import re
import uuid
from collections import Counter
from datetime import datetime
from modules.protocols import ModuleProtocol, ContextRequest, ModuleContext, ModuleResult, WritingPrompt
from memory.protocols import WritingSessionContent, BtwEntry
from llm.base import BaseLLM
from shared.io import IOHandler
from shared.error_log import log_skill_error
from lang.loader import get_writing_min_words
from skills.protocols import SkillInput
from skills.topic_picker.skill import TopicPickerSkill
from modules.writing.skills import get_writing_skills
from modules.writing.pipeline import WritingPipeline, PipelineResult

_PRACTICE_REQUEST_RE = re.compile(r"practi[cs]e|exercise|drill", re.IGNORECASE)


class WritingModule(ModuleProtocol):
    name = "writing"
    description = (
        "Conducts a writing session in the target language. Generates a prompt at the "
        "user's level, accepts their written response, identifies grammar and vocabulary "
        "errors, provides structured feedback with explanations, and produces a corrected version."
    )

    def __init__(self):
        skills = get_writing_skills()
        self.skills = skills
        self._pipeline = WritingPipeline(skills)

    def context_request(self) -> ContextRequest:
        return ContextRequest(
            recent_sessions_n=5,
            module_filter="writing",
            include_error_frequency=True,
            include_recent_topics=True,
            include_vocab_flags=True,
        )

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(
        self, ctx: ModuleContext, llm: BaseLLM, io: IOHandler
    ) -> tuple[ModuleResult, WritingSessionContent]:
        session_id = str(uuid.uuid4())

        wp = self._pick_topic(ctx, llm, io)
        topic, requirements, writing_prompt, min_words = (
            wp.topic, wp.requirements,
            f"Topic: {wp.topic}\nRequirements: {wp.requirements}",
            wp.min_words,
        )
        self._print_exercise_header(ctx, topic, requirements, io)

        started_at = datetime.now()
        io.start_timer(label="Writing")
        user_lines, btw_entries, vocab_signals = self._collect_input(
            ctx, topic, writing_prompt, llm, io
        )
        io.stop_timer()
        completed_at = datetime.now()
        duration_minutes = (completed_at - started_at).total_seconds() / 60.0

        user_text = "\n".join(user_lines)
        pipeline = self._pipeline.run(
            ctx, user_text, writing_prompt, min_words, llm, io=io,
            enable_timing=not bool(os.environ.get("PYTEST_CURRENT_TEST")),
        )
        self._write_latency_log(pipeline, ctx, session_id)
        io.render_evaluation({
            "detector_success":   pipeline.detector_success,
            "detector_error":     pipeline.detector_error,
            "explained_mistakes": pipeline.explained_mistakes,
            "corrected_text":     pipeline.corrected_text,
            "session_summary":    pipeline.session_summary,
            "tips":               pipeline.tips,
            "text_level_estimate": pipeline.text_level_estimate,
            "stated_level":       ctx.level,
            "user_text":          user_text,
            "mistakes": [
                {
                    "fragment":   m.get("fragment", ""),
                    "error_tag":  m.get("error_tag", ""),
                    "correction": m.get("correction", ""),
                }
                for m in pipeline.explained_mistakes
            ],
        })

        practice_requested_topic = self._follow_up_phase(ctx, topic, user_lines, pipeline, llm, io)

        return self._build_results(
            ctx, session_id, wp, writing_prompt,
            user_lines, btw_entries, vocab_signals,
            pipeline, started_at, completed_at, duration_minutes,
            practice_requested_topic,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _pick_topic(self, ctx: ModuleContext, llm: BaseLLM, io: IOHandler) -> WritingPrompt:
        min_words = get_writing_min_words(ctx.language, ctx.level)
        suggested_focus: str | None = ctx.parameters.get("suggested_focus")

        io.output("\nEnter your own topic, or press Enter for a suggestion:")
        user_input = io.prompt("> ").strip()

        if user_input:
            requirements = f"Minimum {min_words} words."
            if suggested_focus:
                requirements += f" Try to practise: {suggested_focus}."
            return WritingPrompt(
                topic=user_input,
                requirements=requirements,
                min_words=min_words,
                suggested_focus=suggested_focus,
            )

        skill = TopicPickerSkill()
        out = skill.run(
            SkillInput(
                user_id=ctx.user_id,
                level=ctx.level,
                parameters={
                    "language": ctx.language,
                    "recent_topics": ctx.recent_topics,
                    "error_tags": list(ctx.error_frequency.keys())[:5],
                    "suggested_focus": suggested_focus,
                    "min_words": min_words,
                },
            ),
            llm,
        )

        if out.success:
            return WritingPrompt(
                topic=out.metadata["topic"],
                requirements=out.metadata["requirements"],
                min_words=min_words,
                task_label=out.metadata.get("task_label", "writing_free"),
                suggested_focus=suggested_focus,
            )

        log_skill_error(
            self.name, "topic_picker", out.metadata.get("error", ""),
            {"level": ctx.level, "language": ctx.language},
        )
        return WritingPrompt(
            topic="Describe your day",
            requirements=f"Minimum {min_words} words.",
            min_words=min_words,
            suggested_focus=suggested_focus,
        )

    def _print_exercise_header(self, ctx: ModuleContext, topic: str, requirements: str, io: IOHandler) -> None:
        language_label = ctx.language.upper()
        cli_hints = (
            "\nTo ask a question mid-writing, prefix it with '/btw ' (e.g. /btw what does aufstehen mean?)."
            "\nType /word_count to see your current word count."
            "\nTo quit or interrupt the session at any point, press Ctrl + C."
        ) if io.show_cli_hints else ""
        io.output(
            f"\n=================================================="
            f"\n        {language_label} WRITING EXERCISE"
            f"\n=================================================="
            f"\nTarget Level: {ctx.level.upper()}"
            f"\nTopic: {topic}"
            f"\nRequirements: {requirements}"
            f"\n--------------------------------------------------"
            f"\nType your text below. To submit, press Enter on an empty line."
            f"{cli_hints}"
            f"\n=================================================="
        )

    def _collect_input(
        self,
        ctx: ModuleContext,
        topic: str,
        writing_prompt: str,
        llm: BaseLLM,
        io: IOHandler,
    ) -> tuple[list[str], list[BtwEntry], list[str]]:
        user_lines: list[str] = []
        btw_entries: list[BtwEntry] = []
        vocab_signals: list[str] = []

        while True:
            try:
                line = io.prompt("> ").strip()
            except EOFError:
                break

            if line.startswith("/btw "):
                entry = self._handle_btw(ctx, topic, user_lines, line[5:].strip(), llm, io, pipeline=None)
                btw_entries.append(entry)
                if entry.flagged_word:
                    vocab_signals.append(entry.flagged_word)
                continue

            if line == "/word_count":
                count = sum(len(l.split()) for l in user_lines)
                io.output(f"[Word count: {count}]")
                continue

            if line in ("/end", ""):
                if not user_lines:
                    io.output("Please write some text before submitting!")
                    continue
                break

            user_lines.append(line)

        return user_lines, btw_entries, vocab_signals

    def _handle_btw(
        self,
        ctx: ModuleContext,
        topic: str,
        user_lines: list[str],
        question: str,
        llm: BaseLLM,
        io: IOHandler,
        pipeline: PipelineResult | None = None,
    ) -> BtwEntry:
        io.output(f"[*] Asking tutor: '{question}'...")
        session_context = {
            "module": self.name,
            "topic": topic,
            "user_text_so_far": "\n".join(user_lines),
            "level": ctx.level,
            "language": ctx.language,
        }
        if pipeline is not None:
            session_context.update({
                "explained_mistakes": pipeline.explained_mistakes,
                "corrected_text": pipeline.corrected_text,
                "tips": pipeline.tips,
                "session_summary": pipeline.session_summary,
            })
        output = self.skills["btw_handler"].run(
            SkillInput(
                user_id=ctx.user_id,
                level=ctx.level,
                parameters={"question": question, "session_context": session_context},
            ),
            llm,
        )
        if not output.success:
            # btw_handler's failure path puts the error text in "answer" itself, not "error"
            log_skill_error(
                self.name, "btw_handler", output.metadata.get("answer", ""),
                {"level": ctx.level, "language": ctx.language, "topic": topic},
            )
        answer = output.metadata.get("answer", "No answer received.")
        io.output(f"\nTutor: {answer}\n")
        return BtwEntry(
            btw_id=str(uuid.uuid4()),
            session_id="",  # session_id not yet assigned at this point
            user_id=ctx.user_id,
            language=ctx.language,
            question=question,
            answer=answer,
            flagged_word=output.metadata.get("flagged_word"),
            timestamp=datetime.now(),
        )

    def _follow_up_phase(
        self,
        ctx: ModuleContext,
        topic: str,
        user_lines: list[str],
        pipeline: PipelineResult,
        llm: BaseLLM,
        io: IOHandler,
    ) -> str | None:
        """Returns an error_tag to prioritize for a grammar next_action, if the user
        asked (via /btw) to practice — None otherwise. The actual "Start grammar
        practice now?" offer still happens at the orchestrator's normal end-of-session
        chaining point (session_manager._writing_error_recurrence_signal), not here —
        this only records the intent + a same-session mistake to focus it on."""
        io.output("\n💬 Unsure about a mistake? Ask me here — or press Enter to finish.")
        practice_requested_topic: str | None = None
        while True:
            try:
                line = io.prompt("> ").strip()
            except EOFError:
                break
            if not line:
                break
            if _PRACTICE_REQUEST_RE.search(line):
                if practice_requested_topic is None:
                    practice_requested_topic = self._offer_practice_topic(pipeline, io)
                else:
                    io.output("[*] Already noted — I'll suggest grammar practice once you finish here.")
                continue
            self._handle_btw(ctx, topic, user_lines, line, llm, io, pipeline=pipeline)
        return practice_requested_topic

    def _offer_practice_topic(self, pipeline: PipelineResult, io: IOHandler) -> str | None:
        tags = [m.get("error_tag") for m in pipeline.explained_mistakes if m.get("error_tag")]
        if not tags:
            io.output(
                "[*] No specific mistakes from this session to focus on — "
                "I'll pass along a general grammar suggestion instead."
            )
            return None
        top_tag, _ = Counter(tags).most_common(1)[0]
        io.output(f"[*] Got it — I'll suggest a grammar session focused on '{top_tag}' once you're done here.")
        return top_tag

    def _write_latency_log(self, pipeline, ctx: ModuleContext, session_id: str) -> None:
        if not pipeline.step_timings:
            return
        if os.environ.get("PYTEST_CURRENT_TEST"):
            return
        log_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "data", "logs",
        )
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, "skill_latency.jsonl")
        ts = datetime.now().isoformat(timespec="seconds")
        base = {
            "timestamp":  ts,
            "session_id": session_id[:8],
            "user_id":    ctx.user_id,
            "language":   ctx.language,
            "level":      ctx.level,
        }
        with open(log_path, "a", encoding="utf-8") as f:
            for t in pipeline.step_timings:
                f.write(json.dumps({**base, "step": t.step, "skill": t.skill, "duration_s": t.duration_s}) + "\n")
            if pipeline.total_wall_s is not None:
                f.write(json.dumps({**base, "step": "total", "skill": "pipeline", "duration_s": pipeline.total_wall_s}) + "\n")

    def _build_results(
        self,
        ctx: ModuleContext,
        session_id: str,
        wp: WritingPrompt,
        writing_prompt: str,
        user_lines: list[str],
        btw_entries: list[BtwEntry],
        vocab_signals: list[str],
        pipeline: PipelineResult,
        started_at: datetime,
        completed_at: datetime,
        duration_minutes: float,
        practice_requested_topic: str | None = None,
    ) -> tuple[ModuleResult, WritingSessionContent]:
        topic, requirements = wp.topic, wp.requirements
        user_text = "\n".join(user_lines)
        errors = [
            {"error_tag": m["error_tag"], "fragment": m["fragment"], "explanation": m["explanation"]}
            for m in pipeline.explained_mistakes
        ]

        session_content = WritingSessionContent(
            session_id=session_id,
            user_id=ctx.user_id,
            language=ctx.language,
            module=self.name,
            task_label=wp.task_label,
            date=started_at.strftime("%Y-%m-%dT%H:%M:%S"),
            level=ctx.level,
            status="completed",
            topic=topic,
            requirements=requirements,
            user_text=user_text,
            mistakes=pipeline.explained_mistakes,
            tips=pipeline.tips,
            corrected_text=pipeline.corrected_text,
            session_summary=pipeline.session_summary,
            btw_log=[
                {
                    "question": e.question,
                    "answer": e.answer,
                    "flagged_word": e.flagged_word,
                    "timestamp": e.timestamp.strftime("%Y-%m-%dT%H:%M:%S"),
                }
                for e in btw_entries
            ],
            vocab_updates=[
                {"word": word, "source": "btw", "occurrence_count": 1}
                for word in vocab_signals
            ],
            suggested_focus=wp.suggested_focus,
            text_level_estimate=pipeline.text_level_estimate,
            word_count=sum(len(l.split()) for l in user_lines),
        )

        result = ModuleResult(
            session_id=session_id,
            module=self.name,
            task_label=wp.task_label,
            task_description=writing_prompt,
            errors=errors,
            comment=pipeline.session_summary,
            started_at=started_at,
            completed_at=completed_at,
            duration_minutes=duration_minutes,
            metadata={
                "btw_entries": btw_entries,
                "vocab_signals": vocab_signals,
                "practice_requested_topic": practice_requested_topic,
            },
        )

        return result, session_content
