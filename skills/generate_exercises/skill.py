import json
import re

from llm.base import BaseLLM, LLMMessage
from lang.loader import get_taxonomy, get_exercise_types, get_grammar_topics
from lang.models import TaxonomyError
from skills.protocols import SkillProtocol, SkillInput, SkillOutput, call_with_self_correction, SelfCorrectionError
from skills.generate_exercises.prompts import GENERATE_EXERCISES_PROMPT, GENERIC_SCOPE_FALLBACK


class GenerateExercisesSkill(SkillProtocol):
    name = "generate_exercises"
    description = (
        "Generates targeted exercises for a grammar topic, all of a single "
        "exercise type chosen by the caller (not the LLM), each tagged with a "
        "taxonomy-validated error_tag."
    )
    skill_type = "session"

    def run(self, input: SkillInput, llm: BaseLLM) -> SkillOutput:
        topic = input.parameters.get("topic", "").strip()
        language = input.parameters.get("language", "German").capitalize()
        exercise_count = input.parameters.get("exercise_count", 10)
        exercise_type = input.parameters.get("exercise_type", "").strip()

        if not topic:
            return SkillOutput(
                skill_name=self.name,
                success=False,
                metadata={"exercises": [], "error": "No topic provided."},
            )

        taxonomy = get_taxonomy(language)
        if taxonomy is None:
            return SkillOutput(
                skill_name=self.name,
                success=False,
                metadata={"exercises": [], "error": f"No taxonomy found for language '{language}'."},
            )

        exercise_types_map = get_exercise_types(language)
        if exercise_types_map is None:
            return SkillOutput(
                skill_name=self.name,
                success=False,
                metadata={"exercises": [], "error": f"No exercise_types map found for language '{language}'."},
            )

        # The exercise type is picked by the caller (modules/grammar/agent.py), not
        # the LLM — the old "ask the model to choose one type" design let weaker
        # local models drift across types mid-batch, which was silently filtered
        # out afterward and could shrink a requested batch of N down to just a few.
        exercise_type_line = exercise_types_map.describe_one(exercise_type)
        if exercise_type_line is None:
            return SkillOutput(
                skill_name=self.name,
                success=False,
                metadata={
                    "exercises": [],
                    "error": f"Unknown exercise_type '{exercise_type}'. "
                             f"Allowed: {sorted(exercise_types_map.type_names)}",
                },
            )

        # Same scope-boundary lookup as dump_grammar — the two skills are
        # independent LLM calls given only the topic string, so without this
        # they can silently disagree on scope (see GrammarTopic.in_scope docstring).
        topics_map = get_grammar_topics(language)
        matched = topics_map.scope_for(topic) if topics_map else None
        scope_block = (matched.format_scope_for_prompt() if matched else "") or GENERIC_SCOPE_FALLBACK

        prompt = GENERATE_EXERCISES_PROMPT.format(
            language=language,
            exercise_count=exercise_count,
            topic=topic,
            level=input.level.upper(),
            exercise_type=exercise_type,
            exercise_type_line=exercise_type_line,
            taxonomy=taxonomy.format_for_prompt(),
            scope_block=scope_block,
        )
        messages = [LLMMessage(role="user", content=prompt)]

        def parse(text: str) -> list[dict]:
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\n?", "", text)
                text = re.sub(r"\n?```$", "", text)
                text = text.strip()
            data = json.loads(text)
            raw_exercises = data.get("exercises", [])
            if not raw_exercises:
                raise ValueError("No exercises returned")

            parsed = []
            for item in raw_exercises:
                if not isinstance(item, dict):
                    raise ValueError(f"Exercise item is not an object: {item!r}")
                for key in ("prompt", "type", "correct_answer", "error_tag"):
                    if key not in item:
                        raise ValueError(f"Missing key '{key}' in exercise: {item!r}")

                item_type = str(item["type"]).strip()
                # exercise_type is fixed by the caller, not chosen by the model — a
                # mismatch means the model drifted off the requested type. That used
                # to be silently filtered out after the fact; now it's a hard retry.
                if item_type != exercise_type:
                    raise ValueError(
                        f"Exercise type '{item_type}' does not match the requested "
                        f"type '{exercise_type}' for exercise {item.get('prompt')!r}"
                    )
                grading = exercise_types_map.grading_for(item_type)

                # Taxonomy is the single contract for valid error_tag values — an
                # unvalidated hallucinated tag here would silently corrupt
                # error_frequency / select_grammar's downstream lookups, so this
                # retries the whole batch rather than falling back to "other".
                if item["error_tag"] is None:
                    raise ValueError(
                        f"error_tag is null for exercise {item.get('prompt')!r} — "
                        f"must be one of {sorted(taxonomy.tag_set)}"
                    )
                try:
                    error_tag = taxonomy.validate_tag(str(item["error_tag"]))
                except TaxonomyError as e:
                    raise ValueError(str(e)) from e

                accepted_answers = item.get("accepted_answers") or []
                if not isinstance(accepted_answers, list):
                    accepted_answers = []

                parsed.append({
                    "prompt": str(item["prompt"]),
                    "exercise_type": item_type,
                    "grading": grading,
                    "correct_answer": str(item["correct_answer"]),
                    "accepted_answers": [str(a) for a in accepted_answers],
                    "error_tag": error_tag,
                    "distractor_hint": str(item.get("distractor_hint", "")),
                })

            if len(parsed) != exercise_count:
                raise ValueError(
                    f"Expected exactly {exercise_count} exercises of type "
                    f"'{exercise_type}', got {len(parsed)}"
                )

            return parsed

        try:
            exercises = call_with_self_correction(llm, messages, parse, temperature=0.6)
            return SkillOutput(skill_name=self.name, success=True, metadata={"exercises": exercises})
        except SelfCorrectionError as exc:
            return SkillOutput(
                skill_name=self.name,
                success=False,
                metadata={"exercises": [], "error": str(exc)},
            )
