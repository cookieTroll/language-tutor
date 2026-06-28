import json
import re
from skills.protocols import SkillProtocol, SkillInput, SkillOutput
from llm.base import BaseLLM, LLMMessage
from skills.detect_mistakes.prompts import DETECT_MISTAKES_PROMPT
from lang.loader import get_cefr_context

class DetectMistakesSkill(SkillProtocol):
    name = "detect_mistakes"
    description = "Step 1: Identifies raw spelling, grammar, and vocabulary errors in user text."
    skill_type = "session"

    def run(self, input: SkillInput, llm: BaseLLM) -> SkillOutput:
        user_text = input.parameters.get("user_text", "")
        writing_prompt = input.parameters.get("writing_prompt", "")
        recurring_errors = input.parameters.get("recurring_errors", [])
        
        # If student's text is empty, short-circuit
        if not user_text.strip():
            return SkillOutput(
                skill_name=self.name,
                success=True,
                metadata={"raw_mistakes": []}
            )

        language = input.parameters.get("language", "German").capitalize()

        recurring_errors_text = (
            ", ".join(recurring_errors) if recurring_errors else "none identified yet"
        )
        prompt = DETECT_MISTAKES_PROMPT.format(
            level=input.level,
            language=language,
            cefr_context=get_cefr_context(language, input.level),
            writing_prompt=writing_prompt,
            recurring_errors=recurring_errors_text,
            user_text=user_text,
        )

        messages = [
            LLMMessage(role="system", content=f"You are a strict, helpful {language} language teacher."),
            LLMMessage(role="user", content=prompt)
        ]

        def parse_mistakes(text: str) -> list[dict]:
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\n", "", text)
                text = re.sub(r"\n```$", "", text)
                text = text.strip()
                
            data = json.loads(text)
            raw_mistakes = data.get("mistakes", [])
            
            validated = []
            for item in raw_mistakes:
                if isinstance(item, dict) and "fragment" in item:
                    validated.append({
                        "fragment": str(item["fragment"]),
                        "error_type_hint": str(item.get("error_type_hint") or "unspecified error")
                    })
            return validated

        try:
            from skills.protocols import call_with_self_correction, SelfCorrectionError
            validated = call_with_self_correction(llm, messages, parse_mistakes, temperature=0.1)
            return SkillOutput(
                skill_name=self.name,
                success=True,
                metadata={"raw_mistakes": validated}
            )
        except SelfCorrectionError as e:
            metadata = {"raw_mistakes": []}
            metadata["error"] = str(e)
            
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
