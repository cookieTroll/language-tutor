import json
import re

from llm.base import BaseLLM, LLMMessage
from skills.protocols import SkillProtocol, SkillInput, SkillOutput, call_with_self_correction, SelfCorrectionError
from skills.grade_exercises.prompts import GRADE_EXERCISES_PROMPT


class GradeExercisesSkill(SkillProtocol):
    name = "grade_exercises"
    description = (
        "One batched call: judges correctness for llm-graded exercises and produces "
        "feedback for every wrong answer in the set, including already-known-wrong "
        "exact-match items."
    )
    skill_type = "session"

    def run(self, input: SkillInput, llm: BaseLLM) -> SkillOutput:
        items: list[dict] = input.parameters.get("items", [])
        language = input.parameters.get("language", "German").capitalize()
        explanation_language = (input.parameters.get("explanation_language") or "english").capitalize()

        if not items:
            return SkillOutput(skill_name=self.name, success=True, metadata={"results": []})

        # A single grade_exercises call covers one session's exercise set, so all
        # items share one topic — carried per-item for context/logging, but the
        # prompt header only needs it once.
        topic = items[0].get("topic", "")
        indices = {item["index"] for item in items}
        already_known_wrong = {item["index"]: bool(item.get("already_known_wrong", False)) for item in items}

        prompt = GRADE_EXERCISES_PROMPT.format(
            level=input.level.upper(),
            language=language,
            explanation_language=explanation_language,
            topic=topic,
            items_json=json.dumps(items, ensure_ascii=False, indent=2),
        )
        messages = [LLMMessage(role="user", content=prompt)]

        def parse(text: str) -> list[dict]:
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\n?", "", text)
                text = re.sub(r"\n?```$", "", text)
                text = text.strip()
            data = json.loads(text)
            raw_results = data.get("results", [])

            if len(raw_results) != len(items):
                raise ValueError(f"Expected {len(items)} results, got {len(raw_results)}")

            parsed = []
            seen_indices = set()
            for item in raw_results:
                if not isinstance(item, dict):
                    raise ValueError(f"Result item is not an object: {item!r}")
                for key in ("index", "correct"):
                    if key not in item:
                        raise ValueError(f"Missing key '{key}' in result: {item!r}")

                index = item["index"]
                if index not in indices:
                    raise ValueError(f"Unknown index {index} — must be one of {sorted(indices)}")
                if index in seen_indices:
                    raise ValueError(f"Duplicate index {index} in results")
                seen_indices.add(index)

                # already_known_wrong items were already scored deterministically by
                # the module's exact-match comparison — don't trust the model to
                # re-judge correctness, just carry the known verdict through.
                correct = False if already_known_wrong[index] else bool(item["correct"])

                feedback = str(item.get("feedback", "")).strip()
                if not correct and not feedback:
                    raise ValueError(f"Missing feedback for incorrect item at index {index}")
                # Feedback is kept even when correct=true — used for non-penalizing
                # notes like flagging a typo that didn't affect the grammar rule.

                parsed.append({"index": index, "correct": correct, "feedback": feedback})

            missing = indices - seen_indices
            if missing:
                raise ValueError(f"Missing results for index(es) {sorted(missing)}")

            return parsed

        try:
            results = call_with_self_correction(llm, messages, parse, temperature=0.2)
            return SkillOutput(skill_name=self.name, success=True, metadata={"results": results})
        except SelfCorrectionError as exc:
            return SkillOutput(
                skill_name=self.name,
                success=False,
                metadata={"results": [], "error": str(exc)},
            )
