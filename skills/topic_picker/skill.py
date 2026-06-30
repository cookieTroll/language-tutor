import json
import re

from llm.base import BaseLLM, LLMMessage
from modules.protocols import WritingPrompt
from skills.protocols import SkillInput, SkillOutput, call_with_self_correction, SelfCorrectionError
from skills.topic_picker.prompts import TOPIC_PICKER_PROMPT


class TopicPickerSkill:
    name = "topic_picker"
    description = (
        "Utility: generates a writing topic, requirements, and task_label for a given "
        "learner level, avoiding recent topics and steering toward weak grammar areas."
    )
    skill_type = "utility"

    def run(self, input: SkillInput, llm: BaseLLM) -> SkillOutput:
        p = input.parameters
        language = p.get("language", "German").capitalize()
        recent_topics = ", ".join(p.get("recent_topics", [])) or "(none)"
        error_tags = ", ".join(p.get("error_tags", [])) or "(none)"
        suggested_focus = p.get("suggested_focus") or "(none)"
        min_words: int = p.get("min_words", 100)

        prompt = TOPIC_PICKER_PROMPT.format(
            level=input.level.upper(),
            language=language,
            recent_topics=recent_topics,
            error_tags=error_tags,
            suggested_focus=suggested_focus,
            min_words=min_words,
        )

        messages = [LLMMessage(role="user", content=prompt)]

        def parse(text: str) -> dict:
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\n?", "", text)
                text = re.sub(r"\n?```$", "", text)
                text = text.strip()
            data = json.loads(text)
            for key in ("topic", "requirements", "task_label"):
                if key not in data:
                    raise ValueError(f"Missing key '{key}' in topic picker response")
            return {
                "topic": str(data["topic"]),
                "requirements": str(data["requirements"]),
                "task_label": str(data["task_label"]),
            }

        try:
            result = call_with_self_correction(llm, messages, parse, temperature=0.8)
            wp = WritingPrompt(
                topic=result["topic"],
                requirements=result["requirements"],
                min_words=min_words,
                suggested_focus=p.get("suggested_focus"),
            )
            return SkillOutput(
                skill_name=self.name,
                success=True,
                metadata={
                    "topic": wp.topic,
                    "requirements": wp.requirements,
                    "task_label": result["task_label"],
                    "min_words": wp.min_words,
                    "suggested_focus": wp.suggested_focus,
                },
            )
        except SelfCorrectionError as exc:
            return SkillOutput(
                skill_name=self.name,
                success=False,
                metadata={"error": str(exc)},
            )
