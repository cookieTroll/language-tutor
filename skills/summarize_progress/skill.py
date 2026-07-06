import json
import re

from llm.base import BaseLLM, LLMMessage
from memory.protocols import SessionAggregate
from skills.protocols import (
    SkillProtocol,
    SkillInput,
    SkillOutput,
    call_with_self_correction,
    SelfCorrectionError,
)
from skills.summarize_progress.prompts import SUMMARIZE_PROGRESS_PROMPT


class SummarizeProgressSkill:
    name = "summarize_progress"
    description = (
        "Utility: reads a SessionAggregate and returns the recommended next module "
        "with a one-sentence reason. Orchestrator validates weakest_module against registry."
    )
    skill_type = "utility"

    def run(self, input: SkillInput, llm: BaseLLM) -> SkillOutput:
        agg_dict: dict = input.parameters.get("aggregate", {})
        available_modules: list[str] = input.parameters.get("modules", [])

        try:
            agg = SessionAggregate(**agg_dict)
        except Exception as exc:
            return SkillOutput(
                skill_name=self.name,
                success=False,
                metadata={"error": f"Invalid aggregate: {exc}"},
            )

        if not agg.sessions_by_module:
            return SkillOutput(
                skill_name=self.name,
                success=True,
                metadata={
                    "weakest_module": available_modules[0] if available_modules else "writing",
                    "recommendation_reason": "No session history yet — start with the default module.",
                },
            )

        session_lines = "\n".join(
            f"  {mod}: {count} session(s), "
            f"{agg.days_since_module.get(mod, '?'):.1f} days ago, "
            f"{agg.total_time_by_module.get(mod, 0):.0f} min total"
            for mod, count in sorted(agg.sessions_by_module.items())
        )
        error_lines = (
            "\n".join(f"  {tag}" for tag in agg.recurring_errors)
            if agg.recurring_errors
            else "  (none)"
        )
        recent_topics = ", ".join(agg.recent_topics) if agg.recent_topics else "(none)"
        modules_str = ", ".join(available_modules) if available_modules else "(any)"
        explanation_language = (input.parameters.get("explanation_language") or "english").capitalize()

        prompt = SUMMARIZE_PROGRESS_PROMPT.format(
            level=input.level,
            modules=modules_str,
            session_lines=session_lines,
            error_lines=error_lines,
            recent_topics=recent_topics,
            vocab_flag_count=agg.vocab_flag_count,
            explanation_language=explanation_language,
        )

        messages = [
            LLMMessage(role="system", content="You are a concise language tutor advisor."),
            LLMMessage(role="user", content=prompt),
        ]

        def parse(text: str) -> dict:
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\n", "", text)
                text = re.sub(r"\n```$", "", text)
                text = text.strip()
            data = json.loads(text)
            if "weakest_module" not in data or "recommendation_reason" not in data:
                raise ValueError("Missing required keys in response")
            return {"weakest_module": str(data["weakest_module"]),
                    "recommendation_reason": str(data["recommendation_reason"])}

        try:
            result = call_with_self_correction(llm, messages, parse, temperature=0.2)
            return SkillOutput(skill_name=self.name, success=True, metadata=result)
        except SelfCorrectionError as exc:
            return SkillOutput(
                skill_name=self.name,
                success=False,
                metadata={"error": str(exc)},
            )
