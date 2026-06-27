import json
import re
from skills.protocols import SkillProtocol, SkillInput, SkillOutput
from llm.base import BaseLLM, LLMMessage
from skills.detect_mistakes.prompts import DETECT_MISTAKES_PROMPT

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

        prompt = DETECT_MISTAKES_PROMPT.format(
            level=input.level,
            writing_prompt=writing_prompt,
            recurring_errors=str(recurring_errors),
            user_text=user_text
        )

        messages = [
            LLMMessage(role="system", content="You are a strict, helpful German language teacher."),
            LLMMessage(role="user", content=prompt)
        ]

        try:
            response = llm.complete(messages, temperature=0.1)
            text = response.text.strip()
            
            # Clean up potential markdown formatting block
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
            
            return SkillOutput(
                skill_name=self.name,
                success=True,
                metadata={"raw_mistakes": validated}
            )
        except Exception as e:
            return SkillOutput(
                skill_name=self.name,
                success=False,
                metadata={"raw_mistakes": [], "error": str(e)}
            )
