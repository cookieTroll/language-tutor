import uuid
from dataclasses import dataclass, field
from datetime import datetime
from modules.protocols import ModuleProtocol, ContextRequest, ModuleContext, ModuleResult
from memory.protocols import WritingSessionContent, BtwEntry
from llm.base import BaseLLM
from skills.protocols import SkillInput
from modules.writing.skills import get_writing_skills
from shared.timer import SessionTimer


@dataclass
class _PipelineResult:
    detector_success: bool
    detector_error: str
    explained_mistakes: list[dict]
    corrected_text: str
    tips: list[str]
    session_summary: str
    text_level_estimate: str | None = None
    comparison_note: str | None = None


class WritingModule(ModuleProtocol):
    name = "writing"
    description = (
        "Conducts a writing session in the target language. Generates a prompt at the "
        "user's level, accepts their written response, identifies grammar and vocabulary "
        "errors, provides structured feedback with explanations, and produces a corrected version."
    )

    def __init__(self):
        self.skills = get_writing_skills()

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
        self, ctx: ModuleContext, llm: BaseLLM
    ) -> tuple[ModuleResult, WritingSessionContent]:
        session_id = str(uuid.uuid4())

        topic, requirements, writing_prompt = self._setup_topic()
        self._print_exercise_header(ctx, topic, requirements)

        started_at = datetime.now()  # writing clock starts after topic is shown
        timer = SessionTimer(label="Writing")
        timer.start()
        user_lines, btw_entries, vocab_signals = self._collect_input(
            ctx, topic, writing_prompt, llm
        )
        timer.stop()
        completed_at = datetime.now()  # clock stops at submission, not after pipeline
        duration_minutes = (completed_at - started_at).total_seconds() / 60.0

        print("\n[*] Evaluating your text. Please wait...")
        pipeline = self._run_pipeline(ctx, user_lines, writing_prompt, llm)
        self._print_evaluation(pipeline, stated_level=ctx.level)

        return self._build_results(
            ctx, session_id, topic, requirements, writing_prompt,
            user_lines, btw_entries, vocab_signals,
            pipeline, started_at, completed_at, duration_minutes,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _setup_topic(self) -> tuple[str, str, str]:
        # PoC: hardcoded — replaced by topic_picker in Layer 1b
        topic = "Describe your morning routine"
        requirements = "150-200 words, use Perfekt tense, include 3 separable verbs"
        return topic, requirements, f"Topic: {topic}\nRequirements: {requirements}"

    def _print_exercise_header(self, ctx: ModuleContext, topic: str, requirements: str) -> None:
        language_label = ctx.language.capitalize()
        print("\n==================================================")
        print(f"        {language_label.upper()} WRITING EXERCISE")
        print("==================================================")
        print(f"Target Level: {ctx.level.upper()}")
        print(f"Topic: {topic}")
        print(f"Requirements: {requirements}")
        print("--------------------------------------------------")
        print("Type your text below. To submit, press Enter on an empty line.")
        if ctx.parameters.get("ui_mode", "cli") == "cli":
            print("To ask a question mid-writing, prefix it with '/btw ' (e.g. /btw what does aufstehen mean?).")
            print("To quit or interrupt the session at any point, press Ctrl + C.")
        print("==================================================\n")

    def _collect_input(
        self,
        ctx: ModuleContext,
        topic: str,
        writing_prompt: str,
        llm: BaseLLM,
    ) -> tuple[list[str], list[BtwEntry], list[str]]:
        user_lines: list[str] = []
        btw_entries: list[BtwEntry] = []
        vocab_signals: list[str] = []

        while True:
            try:
                line = input("> ").strip()
            except EOFError:
                break

            if line.startswith("/btw "):
                entry = self._handle_btw(ctx, topic, user_lines, line[5:].strip(), llm)
                btw_entries.append(entry)
                if entry.flagged_word:
                    vocab_signals.append(entry.flagged_word)
                continue

            if line in ("/end", ""):
                if not user_lines:
                    print("Please write some text before submitting!")
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
    ) -> BtwEntry:
        print(f"[*] Asking tutor: '{question}'...")
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
        print(f"\nTutor: {answer}\n")
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

    def _run_pipeline(
        self,
        ctx: ModuleContext,
        user_lines: list[str],
        writing_prompt: str,
        llm: BaseLLM,
    ) -> _PipelineResult:
        user_text = "\n".join(user_lines)

        # Step 5: estimate text CEFR level — independent of error pipeline, run first
        level_output = self.skills["estimate_text_level"].run(
            SkillInput(
                user_id=ctx.user_id,
                level=ctx.level,
                parameters={
                    "user_text": user_text,
                    "writing_prompt": writing_prompt,
                    "language": ctx.language,
                },
            ),
            llm,
        )
        text_level_estimate = level_output.metadata.get("text_level_estimate")

        # Step 1: detect raw mistakes
        detector_output = self.skills["detect_mistakes"].run(
            SkillInput(
                user_id=ctx.user_id,
                level=ctx.level,
                parameters={
                    "user_text": user_text,
                    "writing_prompt": writing_prompt,
                    "recurring_errors": list(ctx.error_frequency.keys()),
                    "language": ctx.language,
                },
            ),
            llm,
        )
        if not detector_output.success:
            return _PipelineResult(
                detector_success=False,
                detector_error=detector_output.metadata.get("error", "Unknown error"),
                explained_mistakes=[],
                corrected_text=user_text,
                tips=[],
                session_summary="",
                text_level_estimate=text_level_estimate,
            )
        raw_mistakes = detector_output.metadata.get("raw_mistakes", [])

        # Step 2: classify against taxonomy
        classify_output = self.skills["classify_mistakes"].run(
            SkillInput(
                user_id=ctx.user_id,
                level=ctx.level,
                parameters={"raw_mistakes": raw_mistakes, "language": ctx.language},
            ),
            llm,
        )
        classified_mistakes = classify_output.metadata.get("classified_mistakes", [])

        # Step 3: add pedagogical explanations
        explain_output = self.skills["explain_mistakes"].run(
            SkillInput(
                user_id=ctx.user_id,
                level=ctx.level,
                parameters={"classified_mistakes": classified_mistakes, "language": ctx.language},
            ),
            llm,
        )
        explained_mistakes = explain_output.metadata.get("explained_mistakes", [])

        # Step 4: write corrected text
        correction_output = self.skills["write_correction"].run(
            SkillInput(
                user_id=ctx.user_id,
                level=ctx.level,
                parameters={
                    "user_text": user_text,
                    "explained_mistakes": explained_mistakes,
                    "language": ctx.language,
                },
            ),
            llm,
        )
        corrected_text = correction_output.metadata.get("corrected_text", user_text)

        # Step 6: enrich mistakes with severity, generate summary and tips
        summary_output = self.skills["summarise_writing_session"].run(
            SkillInput(
                user_id=ctx.user_id,
                level=ctx.level,
                parameters={
                    "explained_mistakes": explained_mistakes,
                    "text_level_estimate": text_level_estimate,
                    "writing_prompt": writing_prompt,
                    "language": ctx.language,
                },
            ),
            llm,
        )
        return _PipelineResult(
            detector_success=True,
            detector_error="",
            explained_mistakes=summary_output.metadata.get("mistakes", explained_mistakes),
            corrected_text=corrected_text,
            tips=summary_output.metadata.get("tips", []),
            session_summary=summary_output.metadata.get("session_summary", ""),
            text_level_estimate=text_level_estimate,
            comparison_note=summary_output.metadata.get("comparison_note"),
        )

    def _print_evaluation(self, pipeline: _PipelineResult, stated_level: str = "") -> None:
        # NOTE: rendering will move to ui/cli.py (Layer 1a checklist item).
        # This method is the extraction point for that future migration.
        print("\n==================================================")
        print("                 EVALUATION")
        print("==================================================")

        if not pipeline.detector_success:
            print("[!] Mistake detection failed.")
            print(f"    Error: {pipeline.detector_error}")
        elif pipeline.explained_mistakes:
            print(f"Found {len(pipeline.explained_mistakes)} mistake(s):\n")
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
                print(labels[sev])
                for m in groups[sev]:
                    counter += 1
                    print(f"{counter}. [{m['error_tag']}] '{m['fragment']}'")
                    print(f"   Correction : {m['correction']}")
                    print(f"   Explanation: {m['explanation']}")
                    print()
        else:
            print("Excellent! No mistakes were identified.")

        if pipeline.corrected_text:
            print("── Corrected text ────────────────────────────────")
            print(pipeline.corrected_text)
            print()

        if pipeline.session_summary:
            print("── Session summary ───────────────────────────────")
            print(f"  {pipeline.session_summary}")
            print()

        if pipeline.tips:
            print("── Tips ──────────────────────────────────────────")
            for tip in pipeline.tips:
                print(f"  • {tip}")
            print()

        if pipeline.text_level_estimate:
            estimate = pipeline.text_level_estimate.upper()
            print("── Text level ────────────────────────────────────")
            line = f"  Estimated: {estimate}"
            if stated_level:
                line += f"  (your stated level: {stated_level.upper()})"
            print(line)

        print("==================================================\n")

    def _build_results(
        self,
        ctx: ModuleContext,
        session_id: str,
        topic: str,
        requirements: str,
        writing_prompt: str,
        user_lines: list[str],
        btw_entries: list[BtwEntry],
        vocab_signals: list[str],
        pipeline: _PipelineResult,
        started_at: datetime,
        completed_at: datetime,
        duration_minutes: float,
    ) -> tuple[ModuleResult, WritingSessionContent]:
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
            task_label="writing_free",
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
            suggested_focus=None,
            text_level_estimate=pipeline.text_level_estimate,
            comparison_note=pipeline.comparison_note,
        )

        result = ModuleResult(
            session_id=session_id,
            module=self.name,
            task_label="writing_free",
            task_description=writing_prompt,
            errors=errors,
            comment=pipeline.session_summary,
            started_at=started_at,
            completed_at=completed_at,
            duration_minutes=duration_minutes,
            metadata={"btw_entries": btw_entries, "vocab_signals": vocab_signals},
        )

        return result, session_content
