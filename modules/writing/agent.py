import json
import os
import uuid
from datetime import datetime
from modules.protocols import ModuleProtocol, ContextRequest, ModuleContext, ModuleResult, WritingPrompt
from memory.protocols import WritingSessionContent, BtwEntry
from llm.base import BaseLLM
from shared.io import IOHandler
from lang.loader import get_writing_min_words
from skills.protocols import SkillInput
from skills.topic_picker.skill import TopicPickerSkill
from modules.writing.skills import get_writing_skills
from modules.writing.pipeline import WritingPipeline, PipelineResult
from shared.timer import SessionTimer


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
        timer = SessionTimer(label="Writing")
        timer.start()
        user_lines, btw_entries, vocab_signals = self._collect_input(
            ctx, topic, writing_prompt, llm, io
        )
        timer.stop()
        completed_at = datetime.now()
        duration_minutes = (completed_at - started_at).total_seconds() / 60.0

        user_text = "\n".join(user_lines)
        pipeline = self._pipeline.run(
            ctx, user_text, writing_prompt, min_words, llm, io=io,
            enable_timing=not bool(os.environ.get("PYTEST_CURRENT_TEST")),
        )
        self._write_latency_log(pipeline, ctx, session_id)
        self._print_evaluation(pipeline, stated_level=ctx.level, io=io)

        # Send structured evaluation data for client-side annotated view
        if hasattr(io, "data"):
            io.data({
                "event": "evaluation_complete",
                "user_text": user_text,
                "corrected_text": pipeline.corrected_text,
                "mistakes": [
                    {
                        "fragment":   m.get("fragment", ""),
                        "error_tag":  m.get("error_tag", ""),
                        "correction": m.get("correction", ""),
                    }
                    for m in pipeline.explained_mistakes
                ],
            })

        self._follow_up_phase(ctx, topic, user_lines, llm, io)

        return self._build_results(
            ctx, session_id, wp, writing_prompt,
            user_lines, btw_entries, vocab_signals,
            pipeline, started_at, completed_at, duration_minutes,
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
                entry = self._handle_btw(ctx, topic, user_lines, line[5:].strip(), llm, io)
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
    ) -> BtwEntry:
        io.output(f"[*] Asking tutor: '{question}'...")
        session_context = {
            "module": self.name,
            "topic": topic,
            "user_text_so_far": "\n".join(user_lines),
            "level": ctx.level,
            "language": ctx.language,
        }
        output = self.skills["btw_handler"].run(
            SkillInput(
                user_id=ctx.user_id,
                level=ctx.level,
                parameters={"question": question, "session_context": session_context},
            ),
            llm,
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

    def _print_evaluation(self, pipeline: PipelineResult, stated_level: str = "", io: IOHandler = None) -> None:
        # NOTE: this method will move to ui/ layer (Layer 1c) once IOHandler is fully wired.
        io.output(
            "\n=================================================="
            "\n                 EVALUATION"
            "\n=================================================="
        )

        if not pipeline.detector_success:
            io.output(
                f"[!] Mistake detection failed."
                f"\n    Error: {pipeline.detector_error}"
            )
        elif pipeline.explained_mistakes:
            io.output(f"Found {len(pipeline.explained_mistakes)} mistake(s):\n")
            groups: dict[str, list[dict]] = {"critical": [], "expected": [], "minor": [], "": []}
            for m in pipeline.explained_mistakes:
                groups.setdefault(m.get("severity", ""), []).append(m)
            labels = {
                "critical": "── Critical ──────────────────────────────────────",
                "expected": "── Expected at this level ────────────────────────",
                "minor":    "── Minor / stylistic ─────────────────────────────",
                "":         "── Mistakes ──────────────────────────────────────",
            }
            counter = 0
            for sev in ("critical", "expected", "minor", ""):
                if not groups.get(sev):
                    continue
                io.output(labels[sev])
                for m in groups[sev]:
                    counter += 1
                    io.output(
                        f"{counter}. [{m['error_tag']}] '{m['fragment']}'"
                        f"\n   Correction : {m['correction']}"
                        f"\n   Explanation: {m['explanation']}\n"
                    )
        else:
            io.output("Excellent! No mistakes were identified.")

        if pipeline.corrected_text:
            io.output(
                f"── Corrected text ────────────────────────────────"
                f"\n{pipeline.corrected_text}\n"
            )

        if pipeline.session_summary:
            io.output(
                f"── Session summary ───────────────────────────────"
                f"\n  {pipeline.session_summary}\n"
            )

        if pipeline.tips:
            tips_text = "\n".join(f"  • {tip}" for tip in pipeline.tips)
            io.output(f"── Tips ──────────────────────────────────────────\n{tips_text}\n")

        if pipeline.text_level_estimate:
            estimate = pipeline.text_level_estimate.upper()
            level_line = f"  Estimated: {estimate}"
            if stated_level:
                level_line += f"  (your stated level: {stated_level.upper()})"
            io.output(
                f"── Text level ────────────────────────────────────"
                f"\n{level_line}"
            )

        io.output("==================================================\n")

    def _follow_up_phase(
        self, ctx: ModuleContext, topic: str, user_lines: list[str], llm: BaseLLM, io: IOHandler
    ) -> None:
        io.output("\n💬 Unsure about a mistake? Ask me here — or press Enter to finish.")
        while True:
            try:
                line = io.prompt("> ").strip()
            except EOFError:
                break
            if not line:
                break
            self._handle_btw(ctx, topic, user_lines, line, llm, io)

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
        with open(log_path, "a", encoding="utf-8") as f:
            for t in pipeline.step_timings:
                f.write(json.dumps({
                    "timestamp":   ts,
                    "session_id":  session_id[:8],
                    "user_id":     ctx.user_id,
                    "language":    ctx.language,
                    "level":       ctx.level,
                    "step":        t.step,
                    "skill":       t.skill,
                    "duration_s":  t.duration_s,
                }) + "\n")

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
            comparison_note=pipeline.comparison_note,
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
            metadata={"btw_entries": btw_entries, "vocab_signals": vocab_signals},
        )

        return result, session_content
