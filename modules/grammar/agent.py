import re
import uuid
from datetime import datetime

from modules.protocols import ModuleProtocol, ContextRequest, ModuleContext, ModuleResult
from memory.protocols import GrammarSessionContent, BtwEntry
from llm.base import BaseLLM
from shared.io import IOHandler
from shared.error_log import log_skill_error
from skills.protocols import SkillInput
from skills.select_grammar.skill import resolve_manual_topic
from modules.grammar.skills import get_grammar_skills


def parse_answer_block(raw_block: str, exercise_count: int) -> tuple[list[str], list[str]]:
    """Splits a submitted answer block into (answer_lines, btw_questions).

    /btw-prefixed lines are pulled out — handled inline, not counted as an
    answer — and the remaining lines are padded/truncated to exactly
    exercise_count, preserving order, so each line still lines up with its
    exercise index by position.
    """
    btw_questions: list[str] = []
    answer_lines: list[str] = []
    for line in raw_block.split("\n"):
        stripped = line.strip()
        if stripped.startswith("/btw "):
            btw_questions.append(stripped[5:].strip())
        else:
            answer_lines.append(line)

    if len(answer_lines) < exercise_count:
        answer_lines = answer_lines + [""] * (exercise_count - len(answer_lines))
    else:
        answer_lines = answer_lines[:exercise_count]

    return answer_lines, btw_questions


def _normalize(text: str) -> str:
    return text.strip().lower()


class GrammarModule(ModuleProtocol):
    name = "grammar"
    description = (
        "Conducts a German grammar session. Selects a topic based on "
        "recurring errors and recency, provides an explanation at the "
        "user's level, generates targeted exercises, validates answers, "
        "and logs error patterns for future routing."
    )

    def __init__(self):
        self.skills = get_grammar_skills()

    def context_request(self) -> ContextRequest:
        return ContextRequest(
            recent_sessions_n=10,
            module_filter="grammar",
            include_error_frequency=True,
            include_recent_topics=True,
            include_vocab_flags=False,
        )

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(
        self, ctx: ModuleContext, llm: BaseLLM, io: IOHandler
    ) -> tuple[ModuleResult, GrammarSessionContent]:
        session_id = str(uuid.uuid4())
        started_at = datetime.now()

        topic_info = self._pick_topic(ctx, llm, io)
        explanation = self._dump_grammar(ctx, topic_info, llm, io)
        self._display_explanation(ctx, topic_info, explanation, io)

        exercises = self._generate_exercises(ctx, topic_info, llm, io)
        self._display_exercises(exercises, io)

        if exercises:
            raw_block = io.prompt_block(
                "\nEnter your answers below, one per line, in the same order as the exercises."
                "\nTo ask a question first, prefix a line with '/btw ' (e.g. /btw what does Perfekt mean?)."
                "\nPress Enter on an empty line to submit."
            )
            answer_lines, btw_questions = parse_answer_block(raw_block, len(exercises))
        else:
            answer_lines, btw_questions = [], []

        btw_entries = [
            self._handle_btw(ctx, topic_info["topic"], q, llm, io) for q in btw_questions
        ]

        items, errors, score = self._grade_and_score(ctx, topic_info, exercises, answer_lines, llm)
        self._display_results(items, score, io)

        completed_at = datetime.now()
        duration_minutes = (completed_at - started_at).total_seconds() / 60.0
        task_label = self._task_label(topic_info)

        result = ModuleResult(
            session_id=session_id,
            module=self.name,
            task_label=task_label,
            task_description=f"Topic: {topic_info['topic']}",
            errors=errors,
            comment=f"Grammar session on '{topic_info['topic']}' — score {score:.0%}.",
            started_at=started_at,
            completed_at=completed_at,
            duration_minutes=duration_minutes,
            metadata={"btw_entries": btw_entries},
        )

        session_content = GrammarSessionContent(
            session_id=session_id,
            user_id=ctx.user_id,
            language=ctx.language,
            module=self.name,
            task_label=task_label,
            date=started_at.strftime("%Y-%m-%dT%H:%M:%S"),
            level=ctx.level,
            status="completed",
            topic=topic_info["topic"],
            scope=topic_info["scope"],
            explanation=explanation,
            items=items,
            score=score,
            btw_log=[
                {
                    "question": e.question,
                    "answer": e.answer,
                    "flagged_word": e.flagged_word,
                    "timestamp": e.timestamp.strftime("%Y-%m-%dT%H:%M:%S"),
                }
                for e in btw_entries
            ],
        )

        return result, session_content

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _task_label(self, topic_info: dict) -> str:
        slug = re.sub(r"[^a-z0-9]+", "_", topic_info["topic"].lower()).strip("_")
        return slug or "grammar_practice"

    def _pick_topic(self, ctx: ModuleContext, llm: BaseLLM, io: IOHandler) -> dict:
        io.output("\nEnter your own grammar topic, or press Enter for a suggestion:")
        user_input = io.prompt("> ").strip()

        if user_input:
            return resolve_manual_topic(user_input, level=ctx.level, language=ctx.language)

        out = self.skills["select_grammar"].run(
            SkillInput(
                user_id=ctx.user_id,
                level=ctx.level,
                parameters={
                    "language": ctx.language,
                    "error_frequency": ctx.error_frequency,
                    "recent_topics": ctx.recent_topics,
                },
            ),
            llm,
        )
        if out.success:
            return out.metadata

        log_skill_error(
            self.name, "select_grammar", out.metadata.get("error", ""),
            {"level": ctx.level, "language": ctx.language},
        )
        return {
            "topic": "General grammar review",
            "difficulty": ctx.level,
            "scope": "minor",
            "reason": "Topic selection failed — falling back to a general review.",
        }

    def _dump_grammar(self, ctx: ModuleContext, topic_info: dict, llm: BaseLLM, io: IOHandler) -> str:
        out = self.skills["dump_grammar"].run(
            SkillInput(
                user_id=ctx.user_id,
                level=ctx.level,
                parameters={"topic": topic_info["topic"], "language": ctx.language},
            ),
            llm,
        )
        if out.success:
            return out.metadata["explanation"]
        log_skill_error(
            self.name, "dump_grammar", out.metadata.get("error", ""),
            {"level": ctx.level, "language": ctx.language, "topic": topic_info["topic"]},
        )
        return "(Explanation unavailable — proceeding directly to exercises.)"

    def _display_explanation(
        self, ctx: ModuleContext, topic_info: dict, explanation: str, io: IOHandler
    ) -> None:
        io.output(
            f"\n=================================================="
            f"\n        {ctx.language.upper()} GRAMMAR SESSION"
            f"\n=================================================="
            f"\nTarget Level: {ctx.level.upper()}"
            f"\nTopic: {topic_info['topic']}"
            f"\n--------------------------------------------------"
            f"\n{explanation}"
            f"\n=================================================="
        )

    def _generate_exercises(
        self, ctx: ModuleContext, topic_info: dict, llm: BaseLLM, io: IOHandler
    ) -> list[dict]:
        out = self.skills["generate_exercises"].run(
            SkillInput(
                user_id=ctx.user_id,
                level=ctx.level,
                parameters={"topic": topic_info["topic"], "language": ctx.language},
            ),
            llm,
        )
        if out.success:
            return out.metadata["exercises"]
        log_skill_error(
            self.name, "generate_exercises", out.metadata.get("error", ""),
            {"level": ctx.level, "language": ctx.language, "topic": topic_info["topic"]},
        )
        io.output("\n[!] Exercise generation failed — ending session with no exercises.")
        return []

    def _display_exercises(self, exercises: list[dict], io: IOHandler) -> None:
        if not exercises:
            return
        lines = [f"{i + 1}. {ex['prompt']}" for i, ex in enumerate(exercises)]
        io.output("\n" + "\n".join(lines))

    def _handle_btw(
        self, ctx: ModuleContext, topic: str, question: str, llm: BaseLLM, io: IOHandler
    ) -> BtwEntry:
        io.output(f"[*] Asking tutor: '{question}'...")
        session_context = {
            "module": self.name,
            "topic": topic,
            "user_text_so_far": "",
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

    def _grade_and_score(
        self,
        ctx: ModuleContext,
        topic_info: dict,
        exercises: list[dict],
        answer_lines: list[str],
        llm: BaseLLM,
    ) -> tuple[list[dict], list[dict], float]:
        if not exercises:
            return [], [], 0.0

        # A blank answer is unambiguously wrong — no LLM judgment needed, and
        # sending it into the batch was actually causing bad model behaviour
        # (an empty answer occasionally judged "correct", or graded with no
        # feedback). Resolve these locally instead of relying on the model.
        NO_ANSWER_FEEDBACK = "No answer was provided."
        known_results: dict[int, dict] = {}
        grading_items: list[dict] = []

        for i, ex in enumerate(exercises):
            user_answer = answer_lines[i] if i < len(answer_lines) else ""

            if not user_answer.strip():
                known_results[i] = {"correct": False, "feedback": NO_ANSWER_FEEDBACK}
                continue

            if ex["grading"] == "exact":
                candidates = {_normalize(ex["correct_answer"])} | {
                    _normalize(a) for a in ex.get("accepted_answers", [])
                }
                if _normalize(user_answer) in candidates:
                    known_results[i] = {"correct": True, "feedback": ""}
                    continue

            grading_items.append({
                "index": i,
                "prompt": ex["prompt"],
                "correct_answer": ex["correct_answer"],
                "error_tag": ex["error_tag"],
                "topic": topic_info["topic"],
                "user_answer": user_answer,
                "already_known_wrong": ex["grading"] == "exact",
            })

        if grading_items:
            grade_out = self.skills["grade_exercises"].run(
                SkillInput(
                    user_id=ctx.user_id,
                    level=ctx.level,
                    parameters={"items": grading_items, "language": ctx.language},
                ),
                llm,
            )
            if not grade_out.success:
                log_skill_error(
                    self.name, "grade_exercises", grade_out.metadata.get("error", ""),
                    {"level": ctx.level, "language": ctx.language, "topic": topic_info["topic"]},
                )
            results_by_index = {r["index"]: r for r in grade_out.metadata.get("results", [])}
        else:
            results_by_index = {}

        items: list[dict] = []
        errors: list[dict] = []
        correct_count = 0
        for i, ex in enumerate(exercises):
            user_answer = answer_lines[i] if i < len(answer_lines) else ""
            if i in known_results:
                correct, feedback = known_results[i]["correct"], known_results[i]["feedback"]
            else:
                r = results_by_index.get(i, {"correct": False, "feedback": ""})
                correct, feedback = r["correct"], r["feedback"]

            if correct:
                correct_count += 1
            else:
                errors.append({
                    "error_tag": ex["error_tag"],
                    "fragment": ex["prompt"],
                    "explanation": feedback,
                })

            items.append({
                "prompt": ex["prompt"],
                "exercise_type": ex["exercise_type"],
                "grading": ex["grading"],
                "user_answer": user_answer,
                "correct_answer": ex["correct_answer"],
                "correct": correct,
                "feedback": feedback,
                "error_tag": ex["error_tag"],
            })

        score = correct_count / len(exercises)
        return items, errors, score

    def _display_results(self, items: list[dict], score: float, io: IOHandler) -> None:
        io.output(
            f"\n=================================================="
            f"\n                 RESULTS"
            f"\n=================================================="
        )
        for i, item in enumerate(items):
            status = "correct" if item["correct"] else "incorrect"
            io.output(f"{i + 1}. [{status}] {item['prompt']}")
            io.output(f"   Your answer: {item['user_answer']}")
            if not item["correct"]:
                io.output(f"   Correct answer: {item['correct_answer']}")
                io.output(f"   Feedback: {item['feedback']}")
        correct_count = sum(1 for item in items if item["correct"])
        io.output(f"\nScore: {score:.0%} ({correct_count}/{len(items)})")
        io.output("==================================================\n")
