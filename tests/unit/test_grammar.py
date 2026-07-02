"""
Unit tests for the Layer 2a grammar module. All LLM calls are mocked — no live
network access.
"""
import json
from unittest.mock import MagicMock

from llm.base import BaseLLM, LLMResponse
from modules.protocols import ModuleContext
from memory.protocols import BtwEntry
from shared.io import IOHandler


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


def _make_llm(responses: list[str]) -> MagicMock:
    llm = MagicMock(spec=BaseLLM)
    llm.config = MagicMock()
    llm.config.max_skill_retries = 3
    llm.config.show_incomplete_responses = False
    llm.config.show_cut_by_limit_tag = True
    llm.complete.side_effect = [LLMResponse(text=t, model="test-model") for t in responses]
    return llm


# ---------------------------------------------------------------------------
# parse_answer_block — pure function, no LLM/IO
# ---------------------------------------------------------------------------

class TestParseAnswerBlock:

    def test_exact_count_passes_through_unchanged(self):
        from modules.grammar.agent import parse_answer_block
        answers, btw = parse_answer_block("mit\nbei\nauf", 3)
        assert answers == ["mit", "bei", "auf"]
        assert btw == []

    def test_pads_short_block_with_empty_strings(self):
        from modules.grammar.agent import parse_answer_block
        answers, btw = parse_answer_block("mit", 3)
        assert answers == ["mit", "", ""]
        assert btw == []

    def test_truncates_long_block(self):
        from modules.grammar.agent import parse_answer_block
        answers, btw = parse_answer_block("mit\nbei\nauf\nvon", 2)
        assert answers == ["mit", "bei"]
        assert btw == []

    def test_extracts_btw_lines_and_preserves_answer_order(self):
        from modules.grammar.agent import parse_answer_block
        raw = "mit\n/btw what does bei mean?\nauf"
        answers, btw = parse_answer_block(raw, 2)
        assert answers == ["mit", "auf"]
        assert btw == ["what does bei mean?"]

    def test_multiple_btw_lines(self):
        from modules.grammar.agent import parse_answer_block
        raw = "/btw first question\nmit\n/btw second question\nauf"
        answers, btw = parse_answer_block(raw, 2)
        assert answers == ["mit", "auf"]
        assert btw == ["first question", "second question"]

    def test_empty_block(self):
        from modules.grammar.agent import parse_answer_block
        answers, btw = parse_answer_block("", 2)
        assert answers == ["", ""]
        assert btw == []


# ---------------------------------------------------------------------------
# GrammarModule.run — full integration, mocked IO + LLM
# ---------------------------------------------------------------------------

class TestGrammarModuleRun:

    def test_all_correct_via_select_grammar(self):
        """No manual topic (empty prompt) -> select_grammar path. One exact-match
        exercise (correct) and one llm-graded exercise (correct)."""
        from modules.grammar.agent import GrammarModule

        mock_io = MagicMock(spec=IOHandler)
        mock_io.show_cli_hints = True
        mock_io.prompt.side_effect = [""]  # Enter -> use select_grammar suggestion
        mock_io.prompt_block.return_value = "gehe\nIch bin gegangen."

        resp_select = LLMResponse(text=json.dumps({
            "topic": "Present tense — regular verbs",
            "difficulty": "a1",
            "scope": "major",
            "reason": "verb_conjugation error appeared recently",
        }), model="test-model")
        resp_dump = LLMResponse(text="# Present tense\nCore rule...", model="test-model")
        resp_generate = LLMResponse(text=json.dumps({"exercises": [
            {
                "prompt": "Ich ___ (gehen) jeden Tag zur Schule.",
                "type": "fill_in_the_blank",
                "correct_answer": "gehe",
                "accepted_answers": [],
                "error_tag": "verb_conjugation",
                "distractor_hint": "",
            },
            {
                "prompt": "Rewrite in Perfekt: Ich gehe zur Schule.",
                "type": "transformation",
                "correct_answer": "Ich bin gegangen.",
                "accepted_answers": [],
                "error_tag": "verb_tense",
                "distractor_hint": "",
            },
        ]}), model="test-model")
        resp_grade = LLMResponse(text=json.dumps({"results": [
            {"index": 1, "correct": True, "feedback": ""},
        ]}), model="test-model")

        llm = _make_llm([])
        llm.complete.side_effect = [resp_select, resp_dump, resp_generate, resp_grade]

        module = GrammarModule()
        ctx = _make_ctx()
        result, session_content = module.run(ctx, llm, mock_io)

        assert result.module == "grammar"
        assert session_content.topic == "Present tense — regular verbs"
        assert session_content.scope == "major"
        assert len(session_content.items) == 2
        assert all(item["correct"] for item in session_content.items)
        assert session_content.score == 1.0
        assert result.errors == []
        assert result.metadata["btw_entries"] == []

    def test_suggested_focus_from_orchestrator_reaches_select_grammar(self):
        """ctx.parameters['suggested_focus'] (set by the orchestrator's
        recommendation) must be threaded into select_grammar's prompt so the
        module actually honors what the confirm screen suggested."""
        from modules.grammar.agent import GrammarModule

        mock_io = MagicMock(spec=IOHandler)
        mock_io.show_cli_hints = True
        mock_io.prompt.side_effect = [""]
        mock_io.prompt_block.return_value = ""

        resp_select = LLMResponse(text=json.dumps({
            "topic": "Dative case — prepositions",
            "difficulty": "a1",
            "scope": "major",
            "reason": "matches suggested focus",
        }), model="test-model")
        resp_dump = LLMResponse(text="# Dative case\nCore rule...", model="test-model")
        resp_generate = LLMResponse(text=json.dumps({"exercises": []}), model="test-model")

        llm = _make_llm([])
        llm.complete.side_effect = [resp_select, resp_dump, resp_generate]

        module = GrammarModule()
        ctx = _make_ctx(parameters={"suggested_focus": "noun_declension"})
        module.run(ctx, llm, mock_io)

        select_grammar_prompt = llm.complete.call_args_list[0].args[0][0].content
        assert "noun_declension" in select_grammar_prompt

    def test_manual_topic_override_with_wrong_answer_and_btw(self):
        """User supplies their own topic (skips select_grammar entirely) and
        asks a /btw question mid-block; one exact-match exercise is wrong."""
        from modules.grammar.agent import GrammarModule

        mock_io = MagicMock(spec=IOHandler)
        mock_io.show_cli_hints = True
        mock_io.prompt.side_effect = ["Articles — nominative case"]  # exact curated match
        mock_io.prompt_block.return_value = "die\n/btw what is the nominative case?\nfalsch"

        resp_dump = LLMResponse(text="# Articles\nCore rule...", model="test-model")
        resp_generate = LLMResponse(text=json.dumps({"exercises": [
            {
                "prompt": "___ Mann ist groß. (der/die/das)",
                "type": "fill_in_the_blank",
                "correct_answer": "der",
                "accepted_answers": [],
                "error_tag": "article",
                "distractor_hint": "",
            },
            {
                "prompt": "True or false: nominative marks the subject.",
                "type": "true_false",
                "correct_answer": "falsch",
                "accepted_answers": [],
                "error_tag": "other",
                "distractor_hint": "",
            },
        ]}), model="test-model")
        resp_btw = LLMResponse(text="The nominative case marks the subject of the sentence.", model="test-model")
        resp_grade = LLMResponse(text=json.dumps({"results": [
            {"index": 0, "correct": False, "feedback": "'der' is the masculine nominative article, not 'die'."},
        ]}), model="test-model")

        llm = _make_llm([])
        llm.complete.side_effect = [resp_dump, resp_generate, resp_btw, resp_grade]

        module = GrammarModule()
        ctx = _make_ctx()
        result, session_content = module.run(ctx, llm, mock_io)

        # Manual topic matched a curated entry -> resolved as major, no select_grammar call
        assert session_content.topic == "Articles — nominative case"
        assert session_content.scope == "major"

        assert len(session_content.items) == 2
        assert session_content.items[0]["correct"] is False
        assert session_content.items[0]["feedback"]
        assert session_content.items[1]["correct"] is True

        assert session_content.score == 0.5
        assert len(result.errors) == 1
        assert result.errors[0]["error_tag"] == "article"

        assert len(result.metadata["btw_entries"]) == 1
        assert isinstance(result.metadata["btw_entries"][0], BtwEntry)
        assert result.metadata["btw_entries"][0].answer == "The nominative case marks the subject of the sentence."
        assert len(session_content.btw_log) == 1

    def test_no_exercises_produces_zero_score_without_prompting_for_answers(self):
        """generate_exercises failing must not crash and must not prompt for a block."""
        from modules.grammar.agent import GrammarModule

        mock_io = MagicMock(spec=IOHandler)
        mock_io.show_cli_hints = True
        mock_io.prompt.side_effect = ["My own topic"]

        resp_dump = LLMResponse(text="# Explanation", model="test-model")
        bad_generate = LLMResponse(text="not json", model="test-model")

        llm = _make_llm([])
        llm.complete.side_effect = [resp_dump, bad_generate, bad_generate, bad_generate]

        module = GrammarModule()
        ctx = _make_ctx()
        result, session_content = module.run(ctx, llm, mock_io)

        assert session_content.items == []
        assert session_content.score == 0.0
        assert result.errors == []
        mock_io.prompt_block.assert_not_called()

    def test_blank_answers_scored_without_calling_grade_exercises(self):
        """A blank answer is unambiguously wrong — must be resolved locally,
        never sent to grade_exercises (the model can't be trusted to correctly
        judge an empty answer — it has been observed marking it 'correct')."""
        from modules.grammar.agent import GrammarModule

        mock_io = MagicMock(spec=IOHandler)
        mock_io.show_cli_hints = True
        mock_io.prompt.side_effect = ["My own topic"]
        mock_io.prompt_block.return_value = ""  # submit nothing

        resp_dump = LLMResponse(text="# Explanation", model="test-model")
        resp_generate = LLMResponse(text=json.dumps({"exercises": [
            {
                "prompt": "___ Mann ist groß. (der/die/das)",
                "type": "fill_in_the_blank",
                "correct_answer": "der",
                "accepted_answers": [],
                "error_tag": "article",
                "distractor_hint": "",
            },
            {
                "prompt": "Rewrite in Perfekt: Ich gehe zur Schule.",
                "type": "transformation",
                "correct_answer": "Ich bin gegangen.",
                "accepted_answers": [],
                "error_tag": "verb_tense",
                "distractor_hint": "",
            },
        ]}), model="test-model")

        # Only dump_grammar and generate_exercises should be called — no
        # grade_exercises call for an all-blank submission.
        llm = _make_llm([])
        llm.complete.side_effect = [resp_dump, resp_generate]

        module = GrammarModule()
        ctx = _make_ctx()
        result, session_content = module.run(ctx, llm, mock_io)

        assert llm.complete.call_count == 2
        assert session_content.score == 0.0
        assert all(item["correct"] is False for item in session_content.items)
        assert all(item["feedback"] == "No answer was provided." for item in session_content.items)
        assert len(result.errors) == 2
