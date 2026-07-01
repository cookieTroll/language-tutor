import json
import re

import yaml
from pydantic import ValidationError

from llm.base import BaseLLM, LLMMessage
from lang.loader import get_grammar_topics
from lang.models import GrammarTopic
from skills.protocols import SkillProtocol, SkillInput, SkillOutput, call_with_self_correction, SelfCorrectionError
from skills.select_grammar.prompts import SELECT_GRAMMAR_PROMPT


class SelectGrammarSkill(SkillProtocol):
    name = "select_grammar"
    description = (
        "Selects a grammar topic for the session — a curated major topic linked to "
        "a recurring error, or an LLM-proposed minor topic when none fit."
    )
    skill_type = "session"

    def run(self, input: SkillInput, llm: BaseLLM) -> SkillOutput:
        language = input.parameters.get("language", "German").capitalize()
        error_frequency: dict[str, int] = input.parameters.get("error_frequency", {})
        recent_topics: list[str] = input.parameters.get("recent_topics", [])

        topics_map = get_grammar_topics(language)
        if topics_map is None or not topics_map.topics:
            grammar_topics_yaml = "(none available)"
        else:
            grammar_topics_yaml = yaml.safe_dump(
                [t.model_dump() for t in topics_map.topics],
                allow_unicode=True,
                sort_keys=False,
            )

        prompt = SELECT_GRAMMAR_PROMPT.format(
            language=language,
            level=input.level.upper(),
            grammar_topics_yaml=grammar_topics_yaml,
            error_frequency_json=json.dumps(error_frequency, ensure_ascii=False),
            recent_topics=", ".join(recent_topics) or "(none)",
        )

        messages = [LLMMessage(role="user", content=prompt)]

        def parse(text: str) -> dict:
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\n?", "", text)
                text = re.sub(r"\n?```$", "", text)
                text = text.strip()
            data = json.loads(text)
            for key in ("topic", "difficulty", "scope", "reason"):
                if key not in data:
                    raise ValueError(f"Missing key '{key}' in select_grammar response")

            topic = str(data["topic"]).strip()
            if not topic:
                raise ValueError("Empty topic in select_grammar response")

            # GrammarTopic is the single contract for valid difficulty (CEFR a1-c2)
            # and scope (major|minor) — reuse its validation rather than duplicating
            # the allowed sets here. related_error_tags isn't part of this skill's
            # output, so it's passed empty just to satisfy the model.
            try:
                validated = GrammarTopic(
                    topic=topic,
                    difficulty=data["difficulty"],
                    scope=str(data["scope"]).lower(),
                    related_error_tags=[],
                )
            except ValidationError as e:
                raise ValueError(f"Invalid difficulty/scope in select_grammar response: {e}") from e

            return {
                "topic": validated.topic,
                "difficulty": validated.difficulty,
                "scope": validated.scope,
                "reason": str(data["reason"]),
            }

        try:
            result = call_with_self_correction(llm, messages, parse, temperature=0.3)
            return SkillOutput(skill_name=self.name, success=True, metadata=result)
        except SelfCorrectionError as exc:
            return SkillOutput(
                skill_name=self.name,
                success=False,
                metadata={"error": str(exc)},
            )


def resolve_manual_topic(topic: str, level: str, language: str) -> dict:
    """Resolves a user-typed free-text topic without calling the LLM.

    Mirrors WritingModule._pick_topic's manual-override shape (modules/writing/agent.py):
    the module offers "enter your own topic, or press Enter for a suggestion" before
    invoking select_grammar. If the user's text matches a curated major topic (by
    exact, case-insensitive topic string), reuse its difficulty — otherwise treat it
    as an ad hoc minor topic at the user's stated level. Returns the same
    {topic, difficulty, scope, reason} shape as SelectGrammarSkill's output, so the
    module can use either path interchangeably.
    """
    topics_map = get_grammar_topics(language.capitalize())
    if topics_map is not None:
        for entry in topics_map.topics:
            if entry.topic.strip().casefold() == topic.strip().casefold():
                return {
                    "topic": entry.topic,
                    "difficulty": entry.difficulty,
                    "scope": "major",
                    "reason": "Matched user-provided topic to a curated syllabus entry.",
                }

    return {
        "topic": topic.strip(),
        "difficulty": level.lower(),
        "scope": "minor",
        "reason": "User-provided topic not found in the curated list; treated as ad hoc.",
    }
