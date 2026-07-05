import json
import re
from abc import ABC, abstractmethod

from llm.base import BaseLLM, LLMMessage
from skills.protocols import SkillInput, SkillOutput, call_with_self_correction, SelfCorrectionError


class BaseSummariseSkill(ABC):
    """Abstract base for module-specific session summarisers.

    Handles the common LLM call, JSON parsing, shared field validation,
    and error fallback. Subclasses supply the prompt and module-specific
    validation only.
    """

    skill_type = "session"

    _FALLBACK_SUMMARY = "(Session summary unavailable — an error occurred while generating it.)"

    @abstractmethod
    def _build_messages(self, input: SkillInput, language: str) -> list[LLMMessage]:
        """Build LLM messages for this module's summary prompt."""

    @abstractmethod
    def _validate(self, data: dict, input: SkillInput) -> dict:
        """Validate and enrich the parsed JSON. Raise ValueError to trigger retry."""

    def _extra_defaults(self, input: SkillInput) -> dict:
        """Module-specific fields to merge into the fallback metadata (e.g. a
        module's own mistakes/items list). Override if a subclass needs more
        than session_summary/tips on the failure path."""
        return {}

    def _defaults(self, input: SkillInput) -> dict:
        """Safe fallback metadata when all retries fail."""
        return {
            "session_summary": self._FALLBACK_SUMMARY,
            "tips": [],
            **self._extra_defaults(input),
        }

    def run(self, input: SkillInput, llm: BaseLLM) -> SkillOutput:
        language = input.parameters.get("language", "").capitalize()
        messages = self._build_messages(input, language)

        def parse(text: str) -> dict:
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\n", "", text)
                text = re.sub(r"\n```$", "", text)
                text = text.strip()
            data = json.loads(text)
            if not isinstance(data.get("session_summary"), str) or not data["session_summary"].strip():
                raise ValueError("'session_summary' must be a non-empty string")
            if not isinstance(data.get("tips"), list):
                raise ValueError("'tips' must be a list")
            data = self._validate(data, input)
            return data

        try:
            result = call_with_self_correction(llm, messages, parse, temperature=0.3)
            return SkillOutput(skill_name=self.name, success=True, metadata=result)
        except SelfCorrectionError as e:
            defaults = self._defaults(input)
            defaults["error"] = str(e)
            show_inc = getattr(llm.config, "show_incomplete_responses", False)
            if not isinstance(show_inc, bool):
                show_inc = False
            if e.raw_response and show_inc:
                defaults["raw_response"] = e.raw_response
            return SkillOutput(skill_name=self.name, success=False, metadata=defaults)
