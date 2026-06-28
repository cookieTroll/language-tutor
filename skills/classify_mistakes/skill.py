import json
import re

from llm.base import BaseLLM, LLMMessage
from lang.loader import get_taxonomy
from lang.models import TaxonomyError
from skills.classify_mistakes.prompts import CLASSIFY_MISTAKES_PROMPT
from skills.protocols import SkillProtocol, SkillInput, SkillOutput, call_with_self_correction, SelfCorrectionError


class ClassifyMistakesSkill(SkillProtocol):
    name = "classify_mistakes"
    description = (
        "Step 2: Classifies each raw mistake with a validated error tag from the "
        "language's taxonomy and generates a minimal correction snippet."
    )
    skill_type = "session"

    def run(self, input: SkillInput, llm: BaseLLM) -> SkillOutput:
        raw_mistakes = input.parameters.get("raw_mistakes", [])
        language = input.parameters.get("language", "German").capitalize()

        if not raw_mistakes:
            return SkillOutput(
                skill_name=self.name,
                success=True,
                metadata={"classified_mistakes": []}
            )

        taxonomy = get_taxonomy(language)
        if taxonomy is None:
            return SkillOutput(
                skill_name=self.name,
                success=False,
                metadata={
                    "classified_mistakes": [],
                    "error": f"No taxonomy found for language '{language}'.",
                }
            )

        prompt = CLASSIFY_MISTAKES_PROMPT.format(
            level=input.level,
            language=language,
            taxonomy=taxonomy.format_for_prompt(),
            raw_mistakes=json.dumps(raw_mistakes, ensure_ascii=False, indent=2),
        )

        messages = [
            LLMMessage(
                role="system",
                content=(
                    f"You are a strict, precise {language} language teacher. "
                    "You classify grammar mistakes and suggest minimal corrections."
                ),
            ),
            LLMMessage(role="user", content=prompt),
        ]

        def parse_classified(text: str) -> list[dict]:
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\n", "", text)
                text = re.sub(r"\n```$", "", text)
                text = text.strip()

            data = json.loads(text)
            classified = data.get("classified", [])

            validated = []
            for item in classified:
                if not isinstance(item, dict):
                    continue
                if "fragment" not in item or "error_tag" not in item:
                    continue
                try:
                    tag = taxonomy.validate_tag(item["error_tag"])
                except TaxonomyError:
                    tag = "other"
                validated.append({
                    "fragment": str(item["fragment"]),
                    "error_tag": tag,
                    "correction": str(item.get("correction", "")),
                })
            return validated

        try:
            classified = call_with_self_correction(llm, messages, parse_classified, temperature=0.1)
            return SkillOutput(
                skill_name=self.name,
                success=True,
                metadata={"classified_mistakes": classified}
            )
        except SelfCorrectionError as e:
            metadata: dict = {"classified_mistakes": [], "error": str(e)}
            show_inc = getattr(llm.config, "show_incomplete_responses", False)
            if not isinstance(show_inc, bool):
                show_inc = False
            if e.raw_response and show_inc:
                metadata["raw_response"] = e.raw_response
            return SkillOutput(
                skill_name=self.name,
                success=False,
                metadata=metadata
            )
