"""
Unit tests for the Layer 1a evaluator pipeline skills.
All LLM calls are mocked — no live network access.
"""
import json
import pytest
from unittest.mock import MagicMock, patch

from llm.base import BaseLLM, LLMResponse
from skills.protocols import SkillInput


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_llm(responses: list[str]) -> MagicMock:
    """Create a mock BaseLLM whose .complete() returns each response in order."""
    llm = MagicMock(spec=BaseLLM)
    llm.config = MagicMock()
    llm.config.max_skill_retries = 3
    llm.config.show_incomplete_responses = False
    llm.config.show_cut_by_limit_tag = True
    llm.complete.side_effect = [LLMResponse(text=t, model="test-model") for t in responses]
    return llm


def make_input(level: str = "a1", **params) -> SkillInput:
    return SkillInput(user_id="user1", level=level, parameters=params)


# ---------------------------------------------------------------------------
# ClassifyMistakesSkill
# ---------------------------------------------------------------------------

class TestClassifyMistakesSkill:
    from skills.classify_mistakes.skill import ClassifyMistakesSkill

    def test_classifies_valid_tags(self):
        from skills.classify_mistakes.skill import ClassifyMistakesSkill
        raw = [{"fragment": "Ich aufstehen", "error_type_hint": "wrong verb form"}]
        payload = json.dumps({"classified": [
            {"fragment": "Ich aufstehen", "error_tag": "verb_conjugation", "correction": "Ich stehe auf"}
        ]})
        llm = make_llm([payload])

        skill = ClassifyMistakesSkill()
        out = skill.run(make_input(raw_mistakes=raw, language="german"), llm)

        assert out.success is True
        classified = out.metadata["classified_mistakes"]
        assert len(classified) == 1
        assert classified[0]["error_tag"] == "verb_conjugation"
        assert classified[0]["correction"] == "Ich stehe auf"

    def test_rejects_unknown_tag(self):
        """Items with unknown error_tag must be mapped to 'other', not dropped."""
        from skills.classify_mistakes.skill import ClassifyMistakesSkill
        raw = [{"fragment": "foo", "error_type_hint": "something"}]
        payload = json.dumps({"classified": [
            {"fragment": "foo", "error_tag": "nonexistent_tag", "correction": "bar"}
        ]})
        llm = make_llm([payload])

        skill = ClassifyMistakesSkill()
        out = skill.run(make_input(raw_mistakes=raw, language="german"), llm)

        assert out.success is True
        classified = out.metadata["classified_mistakes"]
        assert len(classified) == 1
        assert classified[0]["error_tag"] == "other"
        assert classified[0]["fragment"] == "foo"

    def test_short_circuits_on_empty_input(self):
        """Empty raw_mistakes list must not call the LLM at all."""
        from skills.classify_mistakes.skill import ClassifyMistakesSkill
        llm = make_llm([])

        skill = ClassifyMistakesSkill()
        out = skill.run(make_input(raw_mistakes=[], language="german"), llm)

        assert out.success is True
        assert out.metadata["classified_mistakes"] == []
        llm.complete.assert_not_called()

    def test_self_correction_retry_on_bad_json(self):
        """On first bad JSON, the skill must retry and succeed on the second call."""
        from skills.classify_mistakes.skill import ClassifyMistakesSkill
        raw = [{"fragment": "Ich aufstehen", "error_type_hint": "verb"}]
        bad_json = "{broken json"
        good_json = json.dumps({"classified": [
            {"fragment": "Ich aufstehen", "error_tag": "verb_conjugation", "correction": "Ich stehe auf"}
        ]})
        llm = make_llm([bad_json, good_json])

        skill = ClassifyMistakesSkill()
        out = skill.run(make_input(raw_mistakes=raw, language="german"), llm)

        assert out.success is True
        assert len(out.metadata["classified_mistakes"]) == 1
        assert llm.complete.call_count == 2


# ---------------------------------------------------------------------------
# ExplainMistakesSkill
# ---------------------------------------------------------------------------

class TestExplainMistakesSkill:

    def test_adds_explanation_to_each_mistake(self):
        from skills.explain_mistakes.skill import ExplainMistakesSkill
        classified = [
            {"fragment": "Ich aufstehen", "error_tag": "verb_conjugation", "correction": "Ich stehe auf"}
        ]
        payload = json.dumps({"explained": [
            {
                "fragment": "Ich aufstehen",
                "error_tag": "verb_conjugation",
                "correction": "Ich stehe auf",
                "explanation": "Separable verbs split in main clauses; the prefix goes to the end.",
            }
        ]})
        llm = make_llm([payload])

        from skills.explain_mistakes.skill import ExplainMistakesSkill
        skill = ExplainMistakesSkill()
        out = skill.run(make_input(classified_mistakes=classified, language="german"), llm)

        assert out.success is True
        explained = out.metadata["explained_mistakes"]
        assert len(explained) == 1
        assert explained[0]["explanation"] != ""
        assert "fragment" in explained[0]
        assert "error_tag" in explained[0]
        assert "correction" in explained[0]

    def test_short_circuits_on_empty_input(self):
        """Empty classified_mistakes must not call the LLM."""
        from skills.explain_mistakes.skill import ExplainMistakesSkill
        llm = make_llm([])

        skill = ExplainMistakesSkill()
        out = skill.run(make_input(classified_mistakes=[], language="german"), llm)

        assert out.success is True
        assert out.metadata["explained_mistakes"] == []
        llm.complete.assert_not_called()

    def test_drops_items_with_empty_explanation(self):
        """Items where explanation is empty/whitespace must be excluded."""
        from skills.explain_mistakes.skill import ExplainMistakesSkill
        classified = [{"fragment": "Ich aufstehen", "error_tag": "verb_conjugation", "correction": "Ich stehe auf"}]
        payload = json.dumps({"explained": [
            {
                "fragment": "Ich aufstehen",
                "error_tag": "verb_conjugation",
                "correction": "Ich stehe auf",
                "explanation": "   ",
            }
        ]})
        llm = make_llm([payload])

        skill = ExplainMistakesSkill()
        out = skill.run(make_input(classified_mistakes=classified, language="german"), llm)

        assert out.success is True
        assert out.metadata["explained_mistakes"] == []


# ---------------------------------------------------------------------------
# WriteCorrectionSkill
# ---------------------------------------------------------------------------

class TestWriteCorrectionSkill:

    def test_produces_corrected_text_and_recommendations(self):
        from skills.write_correction.skill import WriteCorrectionSkill
        explained = [
            {
                "fragment": "Ich aufstehen",
                "error_tag": "verb_conjugation",
                "correction": "Ich stehe auf",
                "explanation": "Separable verbs split in main clauses.",
            }
        ]
        payload = json.dumps({
            "corrected_text": "Ich stehe um 7 Uhr auf.",
            "recommendations": ["Practice separable verbs daily."],
            "comment": "Good effort, keep it up!",
        })
        llm = make_llm([payload])

        skill = WriteCorrectionSkill()
        out = skill.run(
            make_input(
                user_text="Ich aufstehen um 7 Uhr.",
                explained_mistakes=explained,
                language="german",
            ),
            llm,
        )

        assert out.success is True
        assert out.metadata["corrected_text"] == "Ich stehe um 7 Uhr auf."
        assert len(out.metadata["recommendations"]) == 1
        assert out.metadata["comment"] == "Good effort, keep it up!"

    def test_short_circuits_on_empty_mistakes(self):
        """No mistakes → corrected_text equals user_text, no LLM call."""
        from skills.write_correction.skill import WriteCorrectionSkill
        llm = make_llm([])
        original = "Alles ist richtig."

        skill = WriteCorrectionSkill()
        out = skill.run(
            make_input(user_text=original, explained_mistakes=[], language="german"),
            llm,
        )

        assert out.success is True
        assert out.metadata["corrected_text"] == original
        assert out.metadata["recommendations"] == []
        llm.complete.assert_not_called()

    def test_rejects_missing_corrected_text(self):
        """If LLM returns JSON missing corrected_text, skill must fail gracefully."""
        from skills.write_correction.skill import WriteCorrectionSkill
        explained = [{"fragment": "foo", "error_tag": "spelling", "correction": "bar", "explanation": "typo"}]
        # All 3 retries return invalid JSON (missing corrected_text)
        bad = json.dumps({"recommendations": [], "comment": "ok"})
        llm = make_llm([bad, bad, bad])

        skill = WriteCorrectionSkill()
        out = skill.run(
            make_input(user_text="foo", explained_mistakes=explained, language="german"),
            llm,
        )

        assert out.success is False
        assert "corrected_text" in out.metadata  # fallback to original text


# ---------------------------------------------------------------------------
# Full pipeline integration (all skills mocked)
# ---------------------------------------------------------------------------

class TestFullPipeline:

    @patch("modules.writing.agent.input")
    def test_full_pipeline_populates_session_content(self, mock_input):
        """
        Run WritingModule.run() with mocked input and mocked LLM responses for
        all 4 pipeline steps. Verify WritingSessionContent has no stub values.
        """
        from modules.writing.agent import WritingModule
        from modules.protocols import ModuleContext

        mock_input.side_effect = [
            "Ich aufstehen um 7 Uhr.",
            "",  # submit
        ]

        llm = MagicMock(spec=BaseLLM)
        llm.config = MagicMock()
        llm.config.max_skill_retries = 3
        llm.config.show_incomplete_responses = False
        llm.config.show_cut_by_limit_tag = True

        # Step 1: detect_mistakes
        resp_detect = LLMResponse(
            text='{"mistakes": [{"fragment": "Ich aufstehen", "error_type_hint": "separable verb"}]}',
            model="test-model",
        )
        # Step 2: classify_mistakes
        resp_classify = LLMResponse(
            text=json.dumps({"classified": [
                {"fragment": "Ich aufstehen", "error_tag": "verb_conjugation", "correction": "Ich stehe auf"}
            ]}),
            model="test-model",
        )
        # Step 3: explain_mistakes
        resp_explain = LLMResponse(
            text=json.dumps({"explained": [
                {
                    "fragment": "Ich aufstehen",
                    "error_tag": "verb_conjugation",
                    "correction": "Ich stehe auf",
                    "explanation": "Separable verbs must split in main clauses.",
                }
            ]}),
            model="test-model",
        )
        # Step 4: write_correction
        resp_correct = LLMResponse(
            text=json.dumps({
                "corrected_text": "Ich stehe um 7 Uhr auf.",
                "recommendations": ["Review separable verbs."],
                "comment": "Nice try!",
            }),
            model="test-model",
        )

        llm.complete.side_effect = [resp_detect, resp_classify, resp_explain, resp_correct]

        ctx = ModuleContext(
            user_id="user1",
            language="german",
            level="a1",
            recent_sessions=[],
            error_frequency={},
            recent_topics=[],
            vocab_flags=[],
            parameters={},
        )

        module = WritingModule()
        result, session_content = module.run(ctx, llm)

        # Verify mistakes are fully populated (not stubs)
        assert len(session_content.mistakes) == 1
        assert session_content.mistakes[0]["error_tag"] == "verb_conjugation"
        assert session_content.mistakes[0]["correction"] == "Ich stehe auf"
        assert session_content.mistakes[0]["explanation"] == "Separable verbs must split in main clauses."

        # Verify corrected text is real
        assert session_content.corrected_text == "Ich stehe um 7 Uhr auf."

        # Verify recommendations are real
        assert session_content.recommendations == ["Review separable verbs."]

        # Verify comment is real
        assert session_content.comment == "Nice try!"

        # Verify ModuleResult errors use taxonomy tags (not raw guesses)
        assert result.errors[0]["error_tag"] == "verb_conjugation"
