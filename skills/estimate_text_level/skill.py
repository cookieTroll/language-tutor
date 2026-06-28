import json
import re

from llm.base import BaseLLM, LLMMessage
from lang.loader import get_cefr_descriptors
from skills.estimate_text_level.prompts import ESTIMATE_TEXT_LEVEL_PROMPT
from skills.protocols import SkillProtocol, SkillInput, SkillOutput, call_with_self_correction, SelfCorrectionError

_VALID_LEVELS = frozenset({"a1", "a2", "b1", "b2", "c1", "c2"})
_MIN_WORDS = 20


class EstimateTextLevelSkill(SkillProtocol):
    name = "estimate_text_level"
    description = "Step 5: Estimates the CEFR level demonstrated by the user's writing."
    skill_type = "session"

    def run(self, input: SkillInput, llm: BaseLLM) -> SkillOutput:
        user_text = input.parameters.get("user_text", "")
        writing_prompt = input.parameters.get("writing_prompt", "")
        language = input.parameters.get("language", "German").capitalize()

        if len(user_text.split()) < _MIN_WORDS:
            return SkillOutput(
                skill_name=self.name,
                success=True,
                metadata={"text_level_estimate": None},
            )

        prompt = ESTIMATE_TEXT_LEVEL_PROMPT.format(
            level=input.level,
            language=language,
            cefr_descriptors=get_cefr_descriptors(language),
            writing_prompt=writing_prompt,
            user_text=user_text,
        )

        messages = [
            LLMMessage(
                role="system",
                content=f"You are an expert {language} language assessor.",
            ),
            LLMMessage(role="user", content=prompt),
        ]

        def parse_estimate(text: str) -> str | None:
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\n", "", text)
                text = re.sub(r"\n```$", "", text)
                text = text.strip()
            data = json.loads(text)
            estimate = data.get("text_level_estimate")
            if estimate is None:
                return None
            estimate = str(estimate).lower().strip()
            if estimate not in _VALID_LEVELS:
                raise ValueError(f"Invalid CEFR band: {estimate!r}. Must be one of {sorted(_VALID_LEVELS)}")
            return estimate

        try:
            estimate = call_with_self_correction(llm, messages, parse_estimate, temperature=0.1)
            return SkillOutput(
                skill_name=self.name,
                success=True,
                metadata={"text_level_estimate": estimate},
            )
        except SelfCorrectionError as e:
            metadata: dict = {"text_level_estimate": None, "error": str(e)}
            show_inc = getattr(llm.config, "show_incomplete_responses", False)
            if not isinstance(show_inc, bool):
                show_inc = False
            if e.raw_response and show_inc:
                metadata["raw_response"] = e.raw_response
            return SkillOutput(
                skill_name=self.name,
                success=False,
                metadata=metadata,
            )
