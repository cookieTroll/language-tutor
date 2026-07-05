import json
import re

from llm.base import BaseLLM, LLMMessage
from skills.protocols import (
    SkillInput,
    SkillOutput,
    call_with_self_correction,
    SelfCorrectionError,
)
from skills.summarize_writing_history.prompts import SUMMARIZE_WRITING_HISTORY_PROMPT


class SummarizeWritingHistorySkill:
    """Utility skill behind the on-demand `/history` command (Layer 2b).

    Takes pre-aggregated topics/recurring-mistake-counts/level-trend (built in Python
    from filtered SessionLogs by the orchestrator, not raw session objects — same
    shape as SummarizeProgressSkill taking a pre-built SessionAggregate) and returns
    one readable report. No storage calls, no persistence of the result.
    """

    name = "summarize_writing_history"
    description = (
        "Utility: turns pre-aggregated writing-history stats (topics, recurring "
        "mistake tags, level trend) into a short readable progress report."
    )
    skill_type = "utility"

    def run(self, input: SkillInput, llm: BaseLLM) -> SkillOutput:
        language: str = input.parameters.get("language", "").capitalize()
        report_language: str = (input.parameters.get("report_language") or "english").capitalize()
        scope_label: str = input.parameters.get("scope_label", "your recent sessions")
        topics: list[str] = input.parameters.get("topics", [])
        recurring_mistakes: list[dict] = input.parameters.get("recurring_mistakes", [])
        level_trend: list[dict] = input.parameters.get("level_trend", [])

        topics_str = ", ".join(topics) if topics else "(none)"
        mistakes_str = (
            "\n".join(f"  {m['error_tag']}: {m['count']}" for m in recurring_mistakes)
            if recurring_mistakes else "  (none)"
        )
        trend_str = (
            "\n".join(f"  {t['date']}: {t['level'].upper()}" for t in level_trend)
            if level_trend else "  (not enough data)"
        )

        prompt = SUMMARIZE_WRITING_HISTORY_PROMPT.format(
            language=language,
            report_language=report_language,
            level=input.level,
            scope_label=scope_label,
            topics=topics_str,
            recurring_mistakes=mistakes_str,
            level_trend=trend_str,
        )
        messages = [
            LLMMessage(
                role="system",
                content=f"You are an encouraging {language} language tutor, writing in {report_language}.",
            ),
            LLMMessage(role="user", content=prompt),
        ]

        def parse(text: str) -> dict:
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\n", "", text)
                text = re.sub(r"\n```$", "", text)
                text = text.strip()
            data = json.loads(text)
            if not isinstance(data.get("history_summary"), str) or not data["history_summary"].strip():
                raise ValueError("'history_summary' must be a non-empty string")
            return {"history_summary": data["history_summary"]}

        try:
            result = call_with_self_correction(llm, messages, parse, temperature=0.3)
            return SkillOutput(skill_name=self.name, success=True, metadata=result)
        except SelfCorrectionError as e:
            return SkillOutput(
                skill_name=self.name,
                success=False,
                metadata={"history_summary": "", "error": str(e)},
            )
