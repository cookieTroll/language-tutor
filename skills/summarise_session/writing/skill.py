import json
from collections import Counter

from llm.base import LLMMessage
from lang.loader import get_cefr_descriptors
from skills.protocols import SkillInput
from skills.summarise_session.base import BaseSummariseSkill
from skills.summarise_session.writing.prompts import SUMMARISE_WRITING_SESSION_PROMPT, LOW_WORD_COUNT_WARNING

_VALID_SEVERITIES = frozenset({"critical", "expected", "minor"})
_REQUIRED_MISTAKE_KEYS = {"fragment", "error_tag", "correction", "explanation"}


class SummariseWritingSessionSkill(BaseSummariseSkill):
    name = "summarise_writing_session"
    description = "Step 6: Enriches mistakes with severity, generates session summary and tips."

    def _build_messages(self, input: SkillInput, language: str) -> list[LLMMessage]:
        explained_mistakes = input.parameters.get("explained_mistakes", [])
        text_level_estimate = input.parameters.get("text_level_estimate")
        writing_prompt = input.parameters.get("writing_prompt", "")
        user_text = input.parameters.get("user_text", "")
        min_words = input.parameters.get("min_words", 0)
        word_count = len(user_text.split()) if user_text else 0
        low_word_count = min_words > 0 and word_count < min_words
        low_word_count_warning = (
            LOW_WORD_COUNT_WARNING.format(word_count=word_count, min_words=min_words)
            if low_word_count else ""
        )

        tag_counts = Counter(m.get("error_tag", "") for m in explained_mistakes)
        mistakes_with_counts = [
            {**m, "occurrence_count": tag_counts[m.get("error_tag", "")]}
            for m in explained_mistakes
        ]

        prompt = SUMMARISE_WRITING_SESSION_PROMPT.format(
            level=input.level,
            language=language,
            cefr_descriptors=get_cefr_descriptors(language),
            text_level_estimate=text_level_estimate or "not available",
            writing_prompt=writing_prompt,
            user_text=user_text,
            word_count=word_count,
            low_word_count_warning=low_word_count_warning,
            explained_mistakes=json.dumps(mistakes_with_counts, ensure_ascii=False, indent=2),
        )
        return [
            LLMMessage(role="system", content=f"You are an expert {language} language teacher and assessor."),
            LLMMessage(role="user", content=prompt),
        ]

    def _validate(self, data: dict, input: SkillInput) -> dict:
        explained_mistakes = input.parameters.get("explained_mistakes", [])
        mistakes = data.get("mistakes", [])
        if len(mistakes) != len(explained_mistakes):
            raise ValueError(
                f"'mistakes' count mismatch: expected {len(explained_mistakes)}, got {len(mistakes)}"
            )
        for m in mistakes:
            missing = _REQUIRED_MISTAKE_KEYS - m.keys()
            if missing:
                raise ValueError(f"Mistake missing required keys: {sorted(missing)}")
            sev = m.get("severity", "")
            if sev not in _VALID_SEVERITIES:
                raise ValueError(
                    f"Invalid severity {sev!r}. Must be one of {sorted(_VALID_SEVERITIES)}"
                )

        user_text = input.parameters.get("user_text", "")
        min_words = input.parameters.get("min_words", 0)
        word_count = len(user_text.split()) if user_text else 0
        if min_words > 0 and word_count < min_words:
            data.setdefault("tips", []).append(
                f"Work on writing stamina — your response was {word_count} "
                f"{'word' if word_count == 1 else 'words'}, well below the {min_words} requested. "
                "Try to address every part of the prompt and build up to the full length."
            )

        return data

    def _extra_defaults(self, input: SkillInput) -> dict:
        return {"mistakes": input.parameters.get("explained_mistakes", [])}
