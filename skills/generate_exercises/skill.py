import json
import re

from llm.base import BaseLLM, LLMMessage
from lang.loader import get_taxonomy, get_exercise_types, get_grammar_topics
from lang.models import TaxonomyError
from skills.protocols import SkillProtocol, SkillInput, SkillOutput, call_with_self_correction, SelfCorrectionError
from skills.generate_exercises.prompts import GENERATE_EXERCISES_PROMPT, GENERIC_SCOPE_FALLBACK

MAX_TOPUP_ROUNDS = 3  # top up the shortfall this many times before giving up


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

        def parse_batch(text: str) -> list[dict]:
            """Validates each item, silently dropping ones that don't match the
            requested type or taxonomy — the caller tops up the shortfall with a
            fresh, cheaper request instead of the whole batch being discarded and
            regenerated from scratch over a single bad item."""
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
                # Structural problems (not an object, missing a required key) mean the
                # model botched the JSON itself — raise so call_with_self_correction
                # retries with corrective feedback, same as before.
                if not isinstance(item, dict):
                    raise ValueError(f"Exercise item is not an object: {item!r}")
                for key in ("prompt", "type", "correct_answer", "error_tag"):
                    if key not in item:
                        raise ValueError(f"Missing key '{key}' in exercise: {item!r}")

                # Semantic mismatches (wrong type, invalid/null tag) mean this specific
                # exercise doesn't fit the ask — drop it and let the caller top up the
                # shortfall with a fresh request, rather than failing the whole batch.
                item_type = str(item["type"]).strip()
                if item_type != exercise_type:
                    continue
                grading = exercise_types_map.grading_for(item_type)

                if item["error_tag"] is None:
                    continue
                try:
                    error_tag = taxonomy.validate_tag(str(item["error_tag"]))
                except TaxonomyError:
                    continue

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
            return parsed

        accumulated: list[dict] = []
        try:
            for _ in range(MAX_TOPUP_ROUNDS):
                remaining = exercise_count - len(accumulated)
                if remaining <= 0:
                    break

                avoid_block = ""
                if accumulated:
                    already = "\n".join(f"- {ex['prompt']}" for ex in accumulated)
                    avoid_block = (
                        "\nAlready written earlier in this batch — write DIFFERENT new "
                        f"exercises, do not repeat or rephrase any of these:\n{already}"
                    )
                prompt = GENERATE_EXERCISES_PROMPT.format(
                    language=language,
                    exercise_count=remaining,
                    topic=topic,
                    level=input.level.upper(),
                    exercise_type=exercise_type,
                    exercise_type_line=exercise_type_line,
                    taxonomy=taxonomy.format_for_prompt(),
                    scope_block=scope_block,
                    avoid_block=avoid_block,
                )
                messages = [LLMMessage(role="user", content=prompt)]
                batch = call_with_self_correction(llm, messages, parse_batch, temperature=0.6)

                # Dedup against what's already accumulated — the "avoid_block" prompt
                # instruction is a soft ask, not a guarantee the model won't repeat itself.
                existing_prompts = {ex["prompt"] for ex in accumulated}
                for ex in batch:
                    if len(accumulated) >= exercise_count:
                        break
                    if ex["prompt"] in existing_prompts:
                        continue
                    accumulated.append(ex)
                    existing_prompts.add(ex["prompt"])
        except SelfCorrectionError as exc:
            return SkillOutput(
                skill_name=self.name,
                success=False,
                metadata={"exercises": [], "error": str(exc)},
            )

        if len(accumulated) < exercise_count:
            return SkillOutput(
                skill_name=self.name,
                success=False,
                metadata={
                    "exercises": [],
                    "error": (
                        f"Only produced {len(accumulated)}/{exercise_count} valid "
                        f"'{exercise_type}' exercises after {MAX_TOPUP_ROUNDS} rounds."
                    ),
                },
            )

        return SkillOutput(skill_name=self.name, success=True, metadata={"exercises": accumulated})
