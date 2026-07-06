from skills.protocols import SkillProtocol, SkillInput, SkillOutput, call_with_self_correction, SelfCorrectionError
from llm.base import BaseLLM, LLMMessage
from skills.write_correction.prompts import WRITE_CORRECTION_PROMPT
import json
import re


class WriteCorrectionSkill(SkillProtocol):
    name = "write_correction"
    description = (
        "Step 4: Produces corrected_text, recommendations[], and a session comment "
        "derived strictly from the classified mistake list — not a freeform LLM rewrite."
    )
    skill_type = "session"

    def run(self, input: SkillInput, llm: BaseLLM) -> SkillOutput:
        user_text = input.parameters.get("user_text", "")
        explained_mistakes = input.parameters.get("explained_mistakes", [])
        language = input.parameters.get("language", "German").capitalize()
        explanation_language = (input.parameters.get("explanation_language") or "english").capitalize()

        # Short-circuit: no mistakes means the original text is the corrected text
        if not explained_mistakes:
            return SkillOutput(
                skill_name=self.name,
                success=True,
                metadata={
                    "corrected_text": user_text,
                    "recommendations": [],
                    "comment": "Excellent work — no mistakes were found!",
                }
            )

        prompt = WRITE_CORRECTION_PROMPT.format(
            level=input.level,
            language=language,
            explanation_language=explanation_language,
            user_text=user_text,
            explained_mistakes=json.dumps(explained_mistakes, ensure_ascii=False, indent=2),
        )

        messages = [
            LLMMessage(
                role="system",
                content=(
                    f"You are a precise {language} language teacher. "
                    "You apply corrections exactly as instructed and do not improvise. "
                    f"You write recommendations and comments in {explanation_language}."
                ),
            ),
            LLMMessage(role="user", content=prompt),
        ]

        def parse_correction(text: str) -> dict:
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\n", "", text)
                text = re.sub(r"\n```$", "", text)
                text = text.strip()

            data = json.loads(text)

            corrected = data.get("corrected_text", "")
            recs = data.get("recommendations", [])
            comment = data.get("comment", "")

            if not isinstance(corrected, str) or not corrected.strip():
                raise ValueError("corrected_text is missing or empty")
            if not isinstance(recs, list):
                raise ValueError("recommendations must be a list")
            if not isinstance(comment, str):
                raise ValueError("comment must be a string")

            return {
                "corrected_text": corrected.strip(),
                "recommendations": [str(r) for r in recs if str(r).strip()],
                "comment": comment.strip(),
            }

        try:
            result = call_with_self_correction(llm, messages, parse_correction, temperature=0.2)
            return SkillOutput(
                skill_name=self.name,
                success=True,
                metadata=result,
            )
        except SelfCorrectionError as e:
            metadata: dict = {
                "corrected_text": user_text,
                "recommendations": [],
                "comment": "",
                "error": str(e),
            }
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
