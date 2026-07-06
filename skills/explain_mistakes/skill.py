from skills.protocols import SkillProtocol, SkillInput, SkillOutput, call_with_self_correction, SelfCorrectionError
from llm.base import BaseLLM, LLMMessage
from skills.explain_mistakes.prompts import EXPLAIN_MISTAKES_PROMPT
import json
import re


class ExplainMistakesSkill(SkillProtocol):
    name = "explain_mistakes"
    description = (
        "Step 3: Adds a pedagogical explanation to each classified mistake, "
        "pitched to the learner's CEFR level. Short-circuits gracefully on empty input."
    )
    skill_type = "session"

    def run(self, input: SkillInput, llm: BaseLLM) -> SkillOutput:
        classified_mistakes = input.parameters.get("classified_mistakes", [])
        language = input.parameters.get("language", "German").capitalize()
        explanation_language = (input.parameters.get("explanation_language") or "english").capitalize()

        # Short-circuit: nothing to explain
        if not classified_mistakes:
            return SkillOutput(
                skill_name=self.name,
                success=True,
                metadata={"explained_mistakes": []}
            )

        prompt = EXPLAIN_MISTAKES_PROMPT.format(
            level=input.level,
            language=language,
            explanation_language=explanation_language,
            classified_mistakes=json.dumps(classified_mistakes, ensure_ascii=False, indent=2),
        )

        messages = [
            LLMMessage(
                role="system",
                content=(
                    f"You are a supportive {language} language teacher writing explanations "
                    f"for a {input.level} learner, in {explanation_language}."
                ),
            ),
            LLMMessage(role="user", content=prompt),
        ]

        def parse_explained(text: str) -> list[dict]:
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\n", "", text)
                text = re.sub(r"\n```$", "", text)
                text = text.strip()

            data = json.loads(text)
            explained = data.get("explained", [])

            validated = []
            for item in explained:
                if not isinstance(item, dict):
                    continue
                required = {"fragment", "error_tag", "correction", "explanation"}
                if not required.issubset(item.keys()):
                    continue
                if not item["explanation"].strip():
                    continue
                validated.append({
                    "fragment": str(item["fragment"]),
                    "error_tag": str(item["error_tag"]),
                    "correction": str(item["correction"]),
                    "explanation": str(item["explanation"]).strip(),
                })
            return validated

        try:
            explained = call_with_self_correction(llm, messages, parse_explained, temperature=0.2)
            return SkillOutput(
                skill_name=self.name,
                success=True,
                metadata={"explained_mistakes": explained}
            )
        except SelfCorrectionError as e:
            metadata: dict = {"explained_mistakes": [], "error": str(e)}
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
