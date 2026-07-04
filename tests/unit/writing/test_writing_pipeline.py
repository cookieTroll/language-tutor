"""
Unit tests for the Layer 1a evaluator pipeline skills.
All LLM calls are mocked — no live network access.
"""
import json
import pytest
from unittest.mock import MagicMock, patch

from llm.base import BaseLLM, LLMResponse
from modules.protocols import ModuleContext
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
# VerifyMistakesSkill (Step 1.5)
# ---------------------------------------------------------------------------

class TestVerifyMistakesSkill:

    def test_drops_false_positive_keeps_genuine(self):
        from skills.verify_mistakes.skill import VerifyMistakesSkill
        raw = [
            {"fragment": "ein wichtige Wissenschaftszentrum", "error_type_hint": "adjective ending"},
            {"fragment": "deshalb organisierte sie einen Ausflug", "error_type_hint": "word order"},
        ]
        payload = json.dumps({"verified": [
            {"fragment": "ein wichtige Wissenschaftszentrum", "keep": True},
            {"fragment": "deshalb organisierte sie einen Ausflug", "keep": False},
        ]})
        llm = make_llm([payload])

        skill = VerifyMistakesSkill()
        out = skill.run(
            make_input(
                raw_mistakes=raw, language="german",
                user_text="CERN ist ein wichtige Wissenschaftszentrum. Deshalb organisierte sie einen Ausflug.",
            ),
            llm,
        )

        assert out.success is True
        kept = out.metadata["verified_mistakes"]
        assert len(kept) == 1
        assert kept[0]["fragment"] == "ein wichtige Wissenschaftszentrum"

    def test_keeps_all_when_all_genuine(self):
        from skills.verify_mistakes.skill import VerifyMistakesSkill
        raw = [{"fragment": "habe gegangen", "error_type_hint": "wrong auxiliary"}]
        payload = json.dumps({"verified": [{"fragment": "habe gegangen", "keep": True}]})
        llm = make_llm([payload])

        skill = VerifyMistakesSkill()
        out = skill.run(
            make_input(raw_mistakes=raw, language="german", user_text="Ich habe ins Büro gegangen."), llm,
        )

        assert out.success is True
        assert out.metadata["verified_mistakes"] == raw

    def test_short_circuits_on_empty_input(self):
        """Empty raw_mistakes list must not call the LLM at all."""
        from skills.verify_mistakes.skill import VerifyMistakesSkill
        llm = make_llm([])

        skill = VerifyMistakesSkill()
        out = skill.run(make_input(raw_mistakes=[], language="german", user_text="Alles korrekt."), llm)

        assert out.success is True
        assert out.metadata["verified_mistakes"] == []
        llm.complete.assert_not_called()

    def test_missing_verdict_triggers_retry(self):
        """A verdict must cover every candidate — a fragment the model never
        addressed is a structural failure that retries, not a silent drop/keep."""
        from skills.verify_mistakes.skill import VerifyMistakesSkill
        raw = [
            {"fragment": "foo", "error_type_hint": "a"},
            {"fragment": "bar", "error_type_hint": "b"},
        ]
        incomplete = json.dumps({"verified": [{"fragment": "foo", "keep": True}]})
        complete = json.dumps({"verified": [
            {"fragment": "foo", "keep": True}, {"fragment": "bar", "keep": False},
        ]})
        llm = make_llm([incomplete, complete])

        skill = VerifyMistakesSkill()
        out = skill.run(make_input(raw_mistakes=raw, language="german", user_text="foo bar"), llm)

        assert out.success is True
        assert [m["fragment"] for m in out.metadata["verified_mistakes"]] == ["foo"]
        assert llm.complete.call_count == 2

    def test_failure_falls_back_to_original_raw_mistakes(self):
        """Fail open: if verification itself breaks after retries, don't silently
        wipe out every detect_mistakes candidate — trust the original list."""
        from skills.verify_mistakes.skill import VerifyMistakesSkill
        raw = [{"fragment": "foo", "error_type_hint": "a"}]
        llm = make_llm(["not json", "still not json", "nope"])

        skill = VerifyMistakesSkill()
        out = skill.run(make_input(raw_mistakes=raw, language="german", user_text="foo"), llm)

        assert out.success is False
        assert out.metadata["verified_mistakes"] == raw


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


# ---------------------------------------------------------------------------
# EstimateTextLevelSkill
# ---------------------------------------------------------------------------

class TestEstimateTextLevelSkill:

    def test_returns_valid_cefr_band(self):
        from skills.estimate_text_level.skill import EstimateTextLevelSkill
        user_text = " ".join(["Ich"] * 25)  # 25 words — above threshold
        payload = json.dumps({"text_level_estimate": "B1"})
        llm = make_llm([payload])

        skill = EstimateTextLevelSkill()
        out = skill.run(make_input(level="a2", user_text=user_text, writing_prompt="Describe your day.", language="german"), llm)

        assert out.success is True
        assert out.metadata["text_level_estimate"] == "b1"  # lowercased

    def test_short_text_returns_none_without_llm_call(self):
        from skills.estimate_text_level.skill import EstimateTextLevelSkill
        llm = make_llm([])

        skill = EstimateTextLevelSkill()
        out = skill.run(make_input(level="a1", user_text="Ich bin müde.", writing_prompt="...", language="german"), llm)

        assert out.success is True
        assert out.metadata["text_level_estimate"] is None
        llm.complete.assert_not_called()

    def test_llm_returns_null_estimate(self):
        from skills.estimate_text_level.skill import EstimateTextLevelSkill
        user_text = " ".join(["word"] * 25)
        payload = json.dumps({"text_level_estimate": None})
        llm = make_llm([payload])

        skill = EstimateTextLevelSkill()
        out = skill.run(make_input(level="a1", user_text=user_text, writing_prompt="...", language="german"), llm)

        assert out.success is True
        assert out.metadata["text_level_estimate"] is None

    def test_rejects_invalid_band_triggers_retry(self):
        from skills.estimate_text_level.skill import EstimateTextLevelSkill
        user_text = " ".join(["Ich"] * 25)
        bad = json.dumps({"text_level_estimate": "intermediate"})
        good = json.dumps({"text_level_estimate": "b2"})
        llm = make_llm([bad, good])

        skill = EstimateTextLevelSkill()
        out = skill.run(make_input(level="b1", user_text=user_text, writing_prompt="...", language="german"), llm)

        assert out.success is True
        assert out.metadata["text_level_estimate"] == "b2"
        assert llm.complete.call_count == 2


# ---------------------------------------------------------------------------
# Full pipeline integration (all skills mocked)
# ---------------------------------------------------------------------------

class TestFullPipeline:

    def test_full_pipeline_populates_session_content(self):
        """
        Run WritingModule.run() with mocked IOHandler and mocked LLM responses for
        all pipeline steps. Verify WritingSessionContent has no stub values.
        """
        from modules.writing.agent import WritingModule
        from modules.protocols import ModuleContext
        from shared.io import IOHandler

        mock_io = MagicMock(spec=IOHandler)
        mock_io.show_cli_hints = True
        mock_io.prompt.side_effect = [
            "Mein Morgen",              # user provides own topic → no LLM call for topic
            "Ich aufstehen um 7 Uhr.",
            "",                         # submit writing
            "",                         # end follow-up phase
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
        # Step 1.5: verify_mistakes
        resp_verify = LLMResponse(
            text=json.dumps({"verified": [{"fragment": "Ich aufstehen", "keep": True}]}),
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
        # Step 6: summarise_writing_session
        resp_summarise = LLMResponse(
            text=json.dumps({
                "session_summary": "Solid A1 attempt with one separable verb error.",
                "mistakes": [{"fragment": "Ich aufstehen", "error_tag": "verb_conjugation", "correction": "Ich stehe auf", "explanation": "Separable verbs must split in main clauses.", "severity": "expected"}],
                "tips": ["Practise separable verb patterns.", "Aim for two-clause sentences."],
            }),
            model="test-model",
        )

        llm.complete.side_effect = [resp_detect, resp_verify, resp_classify, resp_explain, resp_correct, resp_summarise]

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
        result, session_content = module.run(ctx, llm, mock_io)

        # Verify mistakes are fully populated (not stubs)
        assert len(session_content.mistakes) == 1
        assert session_content.mistakes[0]["error_tag"] == "verb_conjugation"
        assert session_content.mistakes[0]["correction"] == "Ich stehe auf"
        assert session_content.mistakes[0]["explanation"] == "Separable verbs must split in main clauses."

        # Verify corrected text is real
        assert session_content.corrected_text == "Ich stehe um 7 Uhr auf."

        # Verify Step 6 outputs
        assert session_content.tips[:2] == ["Practise separable verb patterns.", "Aim for two-clause sentences."]
        assert any("stamina" in t or "word" in t.lower() for t in session_content.tips[2:])
        assert session_content.session_summary == "Solid A1 attempt with one separable verb error."
        assert session_content.mistakes[0].get("severity") == "expected"


# ---------------------------------------------------------------------------
# SummariseWritingSessionSkill (Step 6)
# ---------------------------------------------------------------------------

_ONE_MISTAKE = [
    {"fragment": "Ich aufstehen", "error_tag": "verb_conjugation",
     "correction": "Ich stehe auf", "explanation": "Separable verbs split."}
]
_TWO_MISTAKES = [
    {"fragment": "Ich aufstehen", "error_tag": "verb_conjugation",
     "correction": "Ich stehe auf", "explanation": "Separable verbs split."},
    {"fragment": "ein Hund", "error_tag": "article",
     "correction": "einen Hund", "explanation": "Accusative masculine needs einen."},
]


def _make_skill_input(mistakes, level="b1", text_level_estimate=None):
    return SkillInput(
        user_id="u1",
        level=level,
        parameters={
            "explained_mistakes": mistakes,
            "text_level_estimate": text_level_estimate,
            "writing_prompt": "Describe your morning.",
            "language": "german",
        },
    )


def _summarise_llm(mistakes_out, summary="Good effort.", tips=None):
    """Build a mock LLM that returns a valid Step 6 payload."""
    llm = MagicMock(spec=BaseLLM)
    llm.config = MagicMock()
    llm.config.max_skill_retries = 3
    llm.config.show_incomplete_responses = False
    llm.config.show_cut_by_limit_tag = True
    payload = json.dumps({
        "session_summary": summary,
        "mistakes": mistakes_out,
        "tips": tips or ["Focus on verb placement."],
    })
    llm.complete.return_value = LLMResponse(text=payload, model="test-model")
    return llm


class TestSummariseWritingSessionSkill:

    def test_enriches_mistakes_with_severity(self):
        from skills.summarise_session.writing.skill import SummariseWritingSessionSkill
        out_mistakes = [{**_ONE_MISTAKE[0], "severity": "expected"}]
        llm = _summarise_llm(out_mistakes)
        out = SummariseWritingSessionSkill().run(_make_skill_input(_ONE_MISTAKE), llm)
        assert out.success is True
        assert out.metadata["mistakes"][0]["severity"] == "expected"
        assert out.metadata["mistakes"][0]["fragment"] == "Ich aufstehen"

    def test_valid_tips_and_summary(self):
        from skills.summarise_session.writing.skill import SummariseWritingSessionSkill
        out_mistakes = [{**_ONE_MISTAKE[0], "severity": "minor"}]
        llm = _summarise_llm(out_mistakes, summary="Solid B1 text.", tips=["Try C1 vocab.", "Use Konjunktiv II."])
        out = SummariseWritingSessionSkill().run(_make_skill_input(_ONE_MISTAKE), llm)
        assert out.metadata["session_summary"] == "Solid B1 text."
        assert out.metadata["tips"] == ["Try C1 vocab.", "Use Konjunktiv II."]

    def test_invalid_severity_triggers_retry(self):
        from skills.summarise_session.writing.skill import SummariseWritingSessionSkill
        bad = json.dumps({"session_summary": "ok", "mistakes": [{**_ONE_MISTAKE[0], "severity": "moderate"}], "tips": ["tip"]})
        good = json.dumps({"session_summary": "ok", "mistakes": [{**_ONE_MISTAKE[0], "severity": "expected"}], "tips": ["tip"]})
        llm = MagicMock(spec=BaseLLM)
        llm.config = MagicMock()
        llm.config.max_skill_retries = 3
        llm.config.show_incomplete_responses = False
        llm.config.show_cut_by_limit_tag = True
        llm.complete.side_effect = [
            LLMResponse(text=bad, model="test-model"),
            LLMResponse(text=good, model="test-model"),
        ]
        out = SummariseWritingSessionSkill().run(_make_skill_input(_ONE_MISTAKE), llm)
        assert llm.complete.call_count == 2
        assert out.success is True
        assert out.metadata["mistakes"][0]["severity"] == "expected"

    def test_count_mismatch_triggers_retry(self):
        from skills.summarise_session.writing.skill import SummariseWritingSessionSkill
        one_out = [{**_ONE_MISTAKE[0], "severity": "expected"}]
        two_out = [{**m, "severity": "expected"} for m in _TWO_MISTAKES]
        bad = json.dumps({"session_summary": "ok", "mistakes": one_out, "tips": ["t"]})
        good = json.dumps({"session_summary": "ok", "mistakes": two_out, "tips": ["t"]})
        llm = MagicMock(spec=BaseLLM)
        llm.config = MagicMock()
        llm.config.max_skill_retries = 3
        llm.config.show_incomplete_responses = False
        llm.config.show_cut_by_limit_tag = True
        llm.complete.side_effect = [
            LLMResponse(text=bad, model="test-model"),
            LLMResponse(text=good, model="test-model"),
        ]
        out = SummariseWritingSessionSkill().run(_make_skill_input(_TWO_MISTAKES), llm)
        assert llm.complete.call_count == 2
        assert out.success is True
        assert len(out.metadata["mistakes"]) == 2

    def test_failure_returns_safe_defaults(self):
        from skills.summarise_session.writing.skill import SummariseWritingSessionSkill
        llm = MagicMock(spec=BaseLLM)
        llm.config = MagicMock()
        llm.config.max_skill_retries = 3
        llm.config.show_incomplete_responses = False
        llm.config.show_cut_by_limit_tag = True
        llm.complete.return_value = LLMResponse(text="not json", model="test-model")
        out = SummariseWritingSessionSkill().run(_make_skill_input(_ONE_MISTAKE), llm)
        assert out.success is False
        assert out.metadata["mistakes"] == _ONE_MISTAKE  # original preserved, no data loss
        assert out.metadata["tips"] == []

    def test_empty_mistakes_still_calls_llm(self):
        from skills.summarise_session.writing.skill import SummariseWritingSessionSkill
        payload = json.dumps({"session_summary": "No errors — excellent work!", "mistakes": [], "tips": ["Keep it up."]})
        llm = MagicMock(spec=BaseLLM)
        llm.config = MagicMock()
        llm.config.max_skill_retries = 3
        llm.config.show_incomplete_responses = False
        llm.config.show_cut_by_limit_tag = True
        llm.complete.return_value = LLMResponse(text=payload, model="test-model")
        out = SummariseWritingSessionSkill().run(_make_skill_input([]), llm)
        assert llm.complete.call_count == 1
        assert out.metadata["mistakes"] == []
        assert out.metadata["session_summary"] == "No errors — excellent work!"


# ---------------------------------------------------------------------------
# WritingPipeline unit tests
# ---------------------------------------------------------------------------

def _make_ctx(**kwargs) -> ModuleContext:
    defaults = dict(
        user_id="u1",
        language="german",
        level="a1",
        recent_sessions=[],
        error_frequency={},
        recent_topics=[],
        vocab_flags=[],
        parameters={},
    )
    defaults.update(kwargs)
    return ModuleContext(**defaults)


def _make_pipeline_llm(responses: list[str]) -> MagicMock:
    llm = MagicMock(spec=BaseLLM)
    llm.config = MagicMock()
    llm.config.max_skill_retries = 3
    llm.config.show_incomplete_responses = False
    llm.config.show_cut_by_limit_tag = True
    llm.complete.side_effect = [LLMResponse(text=t, model="test-model") for t in responses]
    return llm


class TestWritingPipeline:

    def test_detector_failure_short_circuits(self):
        """If detect_mistakes fails, pipeline returns immediately with detector_success=False."""
        from modules.writing.pipeline import WritingPipeline
        from modules.writing.skills import get_writing_skills

        # Only the estimator (short text → no LLM call) and detector run;
        # detector returns bad JSON → fail after retries.
        bad = "not json at all"
        llm = _make_pipeline_llm([bad, bad, bad])

        pipeline = WritingPipeline(get_writing_skills())
        ctx = _make_ctx()
        result = pipeline.run(ctx, "Ich bin müde.", "Describe your morning.", min_words=50, llm=llm)

        assert result.detector_success is False
        assert result.explained_mistakes == []
        assert result.tips == []
        assert result.session_summary == ""

    def test_happy_path_returns_enriched_result(self):
        """Full pipeline run with all skills mocked returns correct PipelineResult."""
        from modules.writing.pipeline import WritingPipeline
        from modules.writing.skills import get_writing_skills

        user_text = " ".join(["Ich"] * 30)  # >25 words → estimator makes LLM call

        resp_estimate = json.dumps({"text_level_estimate": "a2"})
        resp_detect = json.dumps({"mistakes": [{"fragment": "foo", "error_type_hint": "bar"}]})
        resp_verify = json.dumps({"verified": [{"fragment": "foo", "keep": True}]})
        resp_classify = json.dumps({"classified": [{"fragment": "foo", "error_tag": "verb_conjugation", "correction": "baz"}]})
        resp_explain = json.dumps({"explained": [{"fragment": "foo", "error_tag": "verb_conjugation", "correction": "baz", "explanation": "reason"}]})
        resp_correct = json.dumps({"corrected_text": "Corrected.", "recommendations": [], "comment": ""})
        resp_summarise = json.dumps({
            "session_summary": "Good attempt.",
            "mistakes": [{"fragment": "foo", "error_tag": "verb_conjugation", "correction": "baz", "explanation": "reason", "severity": "expected"}],
            "tips": ["Keep going."],
        })

        llm = _make_pipeline_llm([resp_estimate, resp_detect, resp_verify, resp_classify, resp_explain, resp_correct, resp_summarise])
        pipeline = WritingPipeline(get_writing_skills())
        ctx = _make_ctx()
        result = pipeline.run(ctx, user_text, "Write something.", min_words=20, llm=llm)

        assert result.detector_success is True
        assert result.text_level_estimate == "a2"
        assert len(result.explained_mistakes) == 1
        assert result.explained_mistakes[0]["severity"] == "expected"
        assert result.corrected_text == "Corrected."
        assert result.session_summary == "Good attempt."
        assert result.tips == ["Keep going."]
