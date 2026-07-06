import random
import uuid
from datetime import datetime

from modules.protocols import ModuleProtocol, ContextRequest, ModuleContext, ModuleResult
from memory.protocols import GrammarSessionContent
from llm.base import BaseLLM
from shared.io import IOHandler
from shared.error_log import log_skill_error
from shared.slugify import slugify_topic
from skills.protocols import SkillInput
from skills.select_grammar.skill import resolve_manual_topic
from modules.grammar.skills import get_grammar_skills
from lang.loader import get_exercise_types


def parse_answer_block(raw_block: str, exercise_count: int) -> list[str]:
    """Splits a submitted answer block into exactly exercise_count lines,
    padded/truncated as needed, preserving order so each line still lines up
    with its exercise index by position.
    """
    answer_lines = raw_block.split("\n")
    if len(answer_lines) < exercise_count:
        answer_lines = answer_lines + [""] * (exercise_count - len(answer_lines))
    else:
        answer_lines = answer_lines[:exercise_count]

    return answer_lines


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

        # Each round generates one batch of a single exercise type (see
        # generate_exercises' prompt); after grading, the user can ask for
        # another round on the same topic or end the session. All rounds'
        # items/errors are pooled into one session file/score.
        all_items: list[dict] = []
        all_errors: list[dict] = []

        while True:
            used_types = [item["exercise_type"] for item in all_items]
            exercises = self._generate_exercises(ctx, topic_info, llm, io, used_types)
            self._display_exercises(ctx, exercises, io)

            if exercises:
                raw_block = io.prompt_block(
                    "\nEnter your answers below, one per line, in the same order as the exercises."
                    "\nPress Enter on an empty line to submit."
                )
                answer_lines = parse_answer_block(raw_block, len(exercises))
            else:
                answer_lines = []

            items, errors, score = self._grade_and_score(ctx, topic_info, exercises, answer_lines, llm)
            self._display_results(items, score, io)
            all_items.extend(items)
            all_errors.extend(errors)

            if not exercises:
                break  # generation failed this round — nothing to repeat

            again = io.prompt(
                f"\nAnother exercise on '{topic_info['topic']}'? [Y/n]: "
            ).strip().lower()
            if again == "n":
                break

        completed_at = datetime.now()
        duration_minutes = (completed_at - started_at).total_seconds() / 60.0
        task_label = self._task_label(topic_info)
        overall_score = (
            sum(1 for item in all_items if item["correct"]) / len(all_items)
            if all_items else 0.0
        )

        result = ModuleResult(
            session_id=session_id,
            module=self.name,
            task_label=task_label,
            task_description=f"Topic: {topic_info['topic']}",
            errors=all_errors,
            comment=f"Grammar session on '{topic_info['topic']}' — score {overall_score:.0%}.",
            started_at=started_at,
            completed_at=completed_at,
            duration_minutes=duration_minutes,
            metadata={},
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
            items=all_items,
            score=overall_score,
            btw_log=[],
        )

        return result, session_content

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _task_label(self, topic_info: dict) -> str:
        return slugify_topic(topic_info["topic"])

    def _pick_topic(self, ctx: ModuleContext, llm: BaseLLM, io: IOHandler) -> dict:
        suggested_focus = ctx.parameters.get("suggested_focus")

        # A suggested_focus here means the user already confirmed this session
        # (either the initial recommendation screen or a chained next-action
        # prompt) with this focus attached — asking again for a topic would be
        # re-litigating a choice they already made. Skip straight to select_grammar,
        # which does the level-aware pick using suggested_focus as a hint.
        if suggested_focus is None:
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
                    "suggested_focus": suggested_focus,
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
                parameters={
                    "topic": topic_info["topic"],
                    "language": ctx.language,
                    "explanation_language": ctx.parameters.get("explanation_language"),
                },
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

    def _pick_exercise_type(self, ctx: ModuleContext, used_types: list[str]) -> str:
        """Chosen here, not left to the LLM — generate_exercises used to ask the
        model to pick one type and stick to it, but weaker local models would
        drift across types mid-batch, which was silently filtered out afterward
        and could shrink a requested batch of N down to just a few. The type
        vocabulary (lang/maps/exercise_types) is pedagogically generic rather than
        topic-specific, so a random pick avoiding the immediately previous round's
        type is just as good as asking the model, at zero extra LLM latency."""
        types_map = get_exercise_types(ctx.language)
        if not types_map or not types_map.type_names:
            return ""  # let generate_exercises' own missing-map check produce the error
        candidates = sorted(types_map.type_names)
        last_used = used_types[-1] if used_types else None
        pool = [t for t in candidates if t != last_used] or candidates
        return random.choice(pool)

    def _generate_exercises(
        self, ctx: ModuleContext, topic_info: dict, llm: BaseLLM, io: IOHandler, used_types: list[str]
    ) -> list[dict]:
        exercise_type = self._pick_exercise_type(ctx, used_types)
        parameters = {
            "topic": topic_info["topic"],
            "language": ctx.language,
            "exercise_type": exercise_type,
        }
        # Same override pattern as suggested_focus above — normally unset, letting
        # generate_exercises fall back to its own default batch size.
        if "exercise_count" in ctx.parameters:
            parameters["exercise_count"] = ctx.parameters["exercise_count"]
        out = self.skills["generate_exercises"].run(
            SkillInput(user_id=ctx.user_id, level=ctx.level, parameters=parameters),
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

    def _display_exercises(self, ctx: ModuleContext, exercises: list[dict], io: IOHandler) -> None:
        if not exercises:
            return
        types_map = get_exercise_types(ctx.language)

        # exercises is already clustered by type (generate_exercises regroups
        # defensively) — fold consecutive same-type runs into display batches,
        # each with one shared instruction instead of repeating it per line.
        groups: list[dict] = []
        for ex in exercises:
            etype = ex["exercise_type"]
            if not groups or groups[-1]["exercise_type"] != etype:
                groups.append({
                    "exercise_type": etype,
                    "instruction": types_map.instruction_for(etype) if types_map else None,
                    "exercises": [],
                })
            groups[-1]["exercises"].append({"prompt": ex["prompt"]})

        io.render_exercises({"groups": groups})

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
                    parameters={
                        "items": grading_items, "language": ctx.language,
                        "explanation_language": ctx.parameters.get("explanation_language"),
                    },
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
        io.render_results({"items": items, "score": score})
