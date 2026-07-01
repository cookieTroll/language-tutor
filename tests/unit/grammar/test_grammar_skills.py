"""
Unit tests for Layer 2a grammar skills. All LLM calls are mocked — no live network access.
"""
import json
from unittest.mock import MagicMock

from llm.base import BaseLLM, LLMResponse
from skills.protocols import SkillInput


def make_llm(responses: list[str]) -> MagicMock:
    """Create a mock BaseLLM whose .complete() returns each response in order."""
    llm = MagicMock(spec=BaseLLM)
    llm.config = MagicMock()
    llm.config.max_skill_retries = 3
    llm.config.show_incomplete_responses = False
    llm.config.show_cut_by_limit_tag = True
    llm.complete.side_effect = [LLMResponse(text=t, model="test-model") for t in responses]
    return llm


def make_input(level: str = "b1", **params) -> SkillInput:
    return SkillInput(user_id="user1", level=level, parameters=params)


# ---------------------------------------------------------------------------
# SelectGrammarSkill
# ---------------------------------------------------------------------------

class TestSelectGrammarSkill:

    def test_selects_major_topic(self):
        from skills.select_grammar.skill import SelectGrammarSkill
        payload = json.dumps({
            "topic": "Dative case — prepositions",
            "difficulty": "b1",
            "scope": "major",
            "reason": "noun_declension error appeared 4 times",
        })
        llm = make_llm([payload])

        skill = SelectGrammarSkill()
        out = skill.run(
            make_input(
                language="german",
                error_frequency={"noun_declension": 4},
                recent_topics=["Present tense — regular verbs"],
            ),
            llm,
        )

        assert out.success is True
        assert out.metadata["topic"] == "Dative case — prepositions"
        assert out.metadata["difficulty"] == "b1"
        assert out.metadata["scope"] == "major"
        assert out.metadata["reason"]

        # Curated topics for German must have reached the prompt.
        prompt_text = llm.complete.call_args_list[0].args[0][0].content
        assert "Present tense — regular verbs" in prompt_text
        assert "verb_conjugation" in prompt_text

    def test_selects_minor_topic_when_no_major_fits(self):
        from skills.select_grammar.skill import SelectGrammarSkill
        payload = json.dumps({
            "topic": "sondern vs. aber",
            "difficulty": "b1",
            "scope": "minor",
            "reason": "connector confusion is idiomatic, not covered by a major topic",
        })
        llm = make_llm([payload])

        skill = SelectGrammarSkill()
        out = skill.run(
            make_input(language="german", error_frequency={"other": 3}, recent_topics=[]),
            llm,
        )

        assert out.success is True
        assert out.metadata["scope"] == "minor"

    def test_unknown_language_falls_back_gracefully(self):
        """No grammar_topics map for the language must not crash — LLM still consulted."""
        from skills.select_grammar.skill import SelectGrammarSkill
        payload = json.dumps({
            "topic": "Basic word order",
            "difficulty": "a1",
            "scope": "minor",
            "reason": "no curated topics available",
        })
        llm = make_llm([payload])

        skill = SelectGrammarSkill()
        out = skill.run(
            make_input(language="klingon", error_frequency={}, recent_topics=[]),
            llm,
        )

        assert out.success is True
        prompt_text = llm.complete.call_args_list[0].args[0][0].content
        assert "(none available)" in prompt_text

    def test_rejects_invalid_difficulty_triggers_retry(self):
        from skills.select_grammar.skill import SelectGrammarSkill
        bad = json.dumps({
            "topic": "Dative case", "difficulty": "intermediate", "scope": "major", "reason": "x",
        })
        good = json.dumps({
            "topic": "Dative case", "difficulty": "b1", "scope": "major", "reason": "x",
        })
        llm = make_llm([bad, good])

        skill = SelectGrammarSkill()
        out = skill.run(make_input(language="german", error_frequency={}, recent_topics=[]), llm)

        assert out.success is True
        assert out.metadata["difficulty"] == "b1"
        assert llm.complete.call_count == 2

    def test_rejects_invalid_scope_triggers_retry(self):
        from skills.select_grammar.skill import SelectGrammarSkill
        bad = json.dumps({
            "topic": "Dative case", "difficulty": "b1", "scope": "syllabus", "reason": "x",
        })
        good = json.dumps({
            "topic": "Dative case", "difficulty": "b1", "scope": "major", "reason": "x",
        })
        llm = make_llm([bad, good])

        skill = SelectGrammarSkill()
        out = skill.run(make_input(language="german", error_frequency={}, recent_topics=[]), llm)

        assert out.success is True
        assert out.metadata["scope"] == "major"
        assert llm.complete.call_count == 2

    def test_missing_key_fails_after_retries_exhausted(self):
        from skills.select_grammar.skill import SelectGrammarSkill
        bad = json.dumps({"topic": "Dative case", "difficulty": "b1"})  # missing scope/reason
        llm = make_llm([bad, bad, bad])

        skill = SelectGrammarSkill()
        out = skill.run(make_input(language="german", error_frequency={}, recent_topics=[]), llm)

        assert out.success is False
        assert "error" in out.metadata


# ---------------------------------------------------------------------------
# resolve_manual_topic (manual override — no LLM call)
# ---------------------------------------------------------------------------

class TestResolveManualTopic:

    def test_exact_match_resolves_as_major(self):
        from skills.select_grammar.skill import resolve_manual_topic
        result = resolve_manual_topic(
            "Dative case — indirect objects and personal pronouns", level="a2", language="german",
        )
        assert result["scope"] == "major"
        assert result["difficulty"] == "a2"
        assert result["topic"] == "Dative case — indirect objects and personal pronouns"

    def test_case_insensitive_match_resolves_as_major(self):
        from skills.select_grammar.skill import resolve_manual_topic
        result = resolve_manual_topic(
            "  present tense — sein AND haben  ", level="a1", language="german",
        )
        assert result["scope"] == "major"
        assert result["topic"] == "Present tense — sein and haben"
        assert result["difficulty"] == "a1"

    def test_no_match_falls_back_to_minor_at_stated_level(self):
        from skills.select_grammar.skill import resolve_manual_topic
        result = resolve_manual_topic("Sondern vs aber", level="b1", language="german")
        assert result["scope"] == "minor"
        assert result["topic"] == "Sondern vs aber"
        assert result["difficulty"] == "b1"

    def test_unknown_language_falls_back_to_minor(self):
        from skills.select_grammar.skill import resolve_manual_topic
        result = resolve_manual_topic("Some topic", level="a1", language="klingon")
        assert result["scope"] == "minor"
        assert result["difficulty"] == "a1"


# ---------------------------------------------------------------------------
# DumpGrammarSkill
# ---------------------------------------------------------------------------

class TestDumpGrammarSkill:

    def test_produces_markdown_explanation(self):
        from skills.dump_grammar.skill import DumpGrammarSkill
        explanation = "# Dative case\n\n## Rule\n...\n\n| Case | Article |\n|---|---|"
        llm = make_llm([explanation])

        skill = DumpGrammarSkill()
        out = skill.run(
            make_input(level="b1", topic="Dative case — prepositions", language="german"), llm,
        )

        assert out.success is True
        assert out.metadata["explanation"] == explanation
        prompt_text = llm.complete.call_args_list[0].args[0][0].content
        assert "Dative case — prepositions" in prompt_text
        assert "B1" in prompt_text

    def test_empty_topic_short_circuits_without_llm_call(self):
        from skills.dump_grammar.skill import DumpGrammarSkill
        llm = make_llm([])

        skill = DumpGrammarSkill()
        out = skill.run(make_input(level="b1", topic="   ", language="german"), llm)

        assert out.success is False
        assert out.metadata["explanation"] == ""
        llm.complete.assert_not_called()

    def test_truncated_response_appends_tag(self):
        from skills.dump_grammar.skill import DumpGrammarSkill
        llm = MagicMock(spec=BaseLLM)
        llm.config = MagicMock()
        llm.config.show_cut_by_limit_tag = True
        llm.complete.return_value = LLMResponse(text="Partial explanation...", model="test-model", truncated=True)

        skill = DumpGrammarSkill()
        out = skill.run(make_input(level="b1", topic="Dative case", language="german"), llm)

        assert out.success is True
        assert out.metadata["explanation"].endswith("[TRUNCATED BY LIMIT]")

    def test_empty_response_fails(self):
        from skills.dump_grammar.skill import DumpGrammarSkill
        llm = make_llm(["   "])

        skill = DumpGrammarSkill()
        out = skill.run(make_input(level="b1", topic="Dative case", language="german"), llm)

        assert out.success is False
        assert "error" in out.metadata

    def test_llm_exception_fails_gracefully(self):
        from skills.dump_grammar.skill import DumpGrammarSkill
        llm = MagicMock(spec=BaseLLM)
        llm.config = MagicMock()
        llm.complete.side_effect = RuntimeError("connection refused")

        skill = DumpGrammarSkill()
        out = skill.run(make_input(level="b1", topic="Dative case", language="german"), llm)

        assert out.success is False
        assert "connection refused" in out.metadata["error"]
