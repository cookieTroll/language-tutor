import pytest
from unittest.mock import patch, MagicMock
from modules.writing.agent import WritingModule
from modules.writing.pipeline import PipelineResult
from modules.protocols import ModuleContext
from llm.base import BaseLLM, LLMResponse, LLMMessage
from memory.protocols import BtwEntry
from skills.btw_handler.skill import BtwHandlerSkill
from skills.protocols import SkillInput
from shared.io import IOHandler, TerminalIOHandler


def _make_btw_llm(answer_text: str = "Because the verb splits.") -> MagicMock:
    llm = MagicMock(spec=BaseLLM)
    llm.config = MagicMock()
    llm.config.max_skill_retries = 3
    llm.config.show_incomplete_responses = False
    llm.config.show_cut_by_limit_tag = True
    llm.complete.return_value = LLMResponse(text=answer_text, model="test-model")
    return llm


def _make_ctx() -> ModuleContext:
    return ModuleContext(
        user_id="u1", language="german", level="a1",
        recent_sessions=[], error_frequency={}, recent_topics=[],
        vocab_flags=[], parameters={},
    )

def test_writing_module_run():
    # Simulate user interaction inside the module's input loop:
    # 1. Write first sentence
    # 2. Ask a vocabulary question mid-session via /btw (regex extracts "aufstehen")
    # 3. Write second sentence
    # 4. Press Enter (empty line) to submit and finish
    from shared.io import IOHandler
    mock_io = MagicMock(spec=IOHandler)
    mock_io.show_cli_hints = True
    mock_io.prompt.side_effect = [
        "Mein Morgen",                        # user provides own topic → no LLM call for topic
        "Ich aufstehen um 7 Uhr.",
        "/btw what does aufstehen mean?",
        "Ich esse Fruhstuck.",
        "",                                   # submit writing
        "",                                   # end follow-up phase
    ]

    llm = MagicMock(spec=BaseLLM)
    llm.config = MagicMock()
    llm.config.max_skill_retries = 3
    llm.config.show_incomplete_responses = False
    llm.config.show_cut_by_limit_tag = True

    # Mock LLM completions in pipeline order:
    # 1. BTW answer (regex extracts "aufstehen" — no extra LLM call needed)
    resp_btw_ans = LLMResponse(text="It means to get up.", model="test-model")
    # 2. Step 1 — detect_mistakes
    resp_detect = LLMResponse(
        text='{"mistakes": [{"fragment": "Ich aufstehen", "error_type_hint": "separable verb position"}]}',
        model="test-model"
    )
    # 3. Step 2 — classify_mistakes
    resp_classify = LLMResponse(
        text='{"classified": [{"fragment": "Ich aufstehen", "error_tag": "verb_conjugation", "correction": "Ich stehe auf"}]}',
        model="test-model"
    )
    # 4. Step 3 — explain_mistakes
    resp_explain = LLMResponse(
        text='{"explained": [{"fragment": "Ich aufstehen", "error_tag": "verb_conjugation", "correction": "Ich stehe auf", "explanation": "Separable verbs split in main clauses; the prefix moves to the end."}]}',
        model="test-model"
    )
    # 5. Step 4 — write_correction
    resp_correct = LLMResponse(
        text='{"corrected_text": "Ich stehe um 7 Uhr auf. Ich esse Frühstück.", "recommendations": ["Practice separable verbs."], "comment": "Good attempt!"}',
        model="test-model"
    )
    # 6. Step 6 — summarise_writing_session
    import json
    resp_summarise = LLMResponse(
        text=json.dumps({
            "session_summary": "Good attempt with one separable verb error typical for A1.",
            "mistakes": [{"fragment": "Ich aufstehen", "error_tag": "verb_conjugation", "correction": "Ich stehe auf", "explanation": "Separable verbs split in main clauses; the prefix moves to the end.", "severity": "expected"}],
            "tips": ["Practice separable verbs daily.", "Build longer connected sentences."],
            "comparison_note": None,
        }),
        model="test-model"
    )
    llm.complete.side_effect = [resp_btw_ans, resp_detect, resp_classify, resp_explain, resp_correct, resp_summarise]

    ctx = ModuleContext(
        user_id="user1",
        language="german",
        level="a1",
        recent_sessions=[],
        error_frequency={},
        recent_topics=[],
        vocab_flags=[],
        parameters={}
    )

    module = WritingModule()
    result, session_content = module.run(ctx, llm, mock_io)

    # Core module result assertions
    assert result.module == "writing"
    assert result.task_label == "writing_free"
    assert len(result.errors) == 1
    assert result.errors[0]["error_tag"] == "verb_conjugation"   # taxonomy tag, not raw hint
    assert result.errors[0]["fragment"] == "Ich aufstehen"

    # BTW entry assertions
    assert len(result.metadata["btw_entries"]) == 1
    assert isinstance(result.metadata["btw_entries"][0], BtwEntry)
    assert result.metadata["btw_entries"][0].question == "what does aufstehen mean?"
    assert result.metadata["btw_entries"][0].answer == "It means to get up."
    assert result.metadata["btw_entries"][0].flagged_word == "aufstehen"

    # Session content — full pipeline fields (no stubs)
    assert session_content.user_text == "Ich aufstehen um 7 Uhr.\nIch esse Fruhstuck."
    assert len(session_content.mistakes) == 1
    assert session_content.mistakes[0]["error_tag"] == "verb_conjugation"
    assert session_content.mistakes[0]["correction"] == "Ich stehe auf"
    assert session_content.mistakes[0]["explanation"] != ""
    assert session_content.corrected_text == "Ich stehe um 7 Uhr auf. Ich esse Frühstück."
    assert session_content.tips[:2] == ["Practice separable verbs daily.", "Build longer connected sentences."]
    assert any("stamina" in t or "word" in t.lower() for t in session_content.tips[2:])
    assert session_content.session_summary == "Good attempt with one separable verb error typical for A1."
    assert session_content.mistakes[0].get("severity") == "expected"
    assert session_content.comparison_note is None

    # BTW log in session YAML
    assert len(session_content.btw_log) == 1
    assert session_content.btw_log[0]["question"] == "what does aufstehen mean?"



def test_btw_handler_llm_fallback_extraction():
    # Test that btw_handler falls back to LLM extraction when regex fails to match a word
    llm = MagicMock(spec=BaseLLM)
    
    resp_ans = LLMResponse(text="Yes, 'aufstehen' is a separable verb.", model="test-model")
    resp_ext = LLMResponse(text="aufstehen", model="test-model")
    llm.complete.side_effect = [resp_ans, resp_ext]
    
    skill = BtwHandlerSkill()
    # Question is a grammar question that mentions a vocabulary word, doesn't match standard patterns
    inp = SkillInput(
        user_id="user1",
        level="a1",
        parameters={
            "question": "Is the verb aufstehen regular or irregular?",
            "session_context": {"module": "writing", "topic": "morning", "user_text_so_far": ""}
        }
    )
    
    output = skill.run(inp, llm)
    
    assert output.success is True
    assert output.metadata["answer"] == "Yes, 'aufstehen' is a separable verb."
    assert output.metadata["flagged_word"] == "aufstehen"
    assert llm.complete.call_count == 2

def test_detect_mistakes_self_correction_retry():
    from skills.detect_mistakes.skill import DetectMistakesSkill
    
    llm = MagicMock(spec=BaseLLM)
    llm.config = MagicMock()
    llm.config.show_incomplete_responses = True
    llm.config.show_cut_by_limit_tag = True
    llm.config.max_skill_retries = 2
    
    # 1st response: malformed JSON
    resp_bad = LLMResponse(text='{"mistakes": [{"fragment": "Ich aufstehen"', model="test-model")
    # 2nd response: correct JSON
    resp_good = LLMResponse(text='{"mistakes": [{"fragment": "Ich aufstehen", "error_type_hint": "verb"}]}', model="test-model")
    
    llm.complete.side_effect = [resp_bad, resp_good]
    
    skill = DetectMistakesSkill()
    inp = SkillInput(
        user_id="user1",
        level="a1",
        parameters={
            "user_text": "Ich aufstehen um 7 Uhr.",
            "writing_prompt": "Describe your morning",
            "recurring_errors": []
        }
    )
    
    output = skill.run(inp, llm)

    assert output.success is True
    assert len(output.metadata["raw_mistakes"]) == 1
    assert output.metadata["raw_mistakes"][0]["fragment"] == "Ich aufstehen"
    assert llm.complete.call_count == 2


# ---------------------------------------------------------------------------
# _handle_btw — evaluation context threading (Layer 2a-vi)
# ---------------------------------------------------------------------------

def test_handle_btw_includes_evaluation_context_after_pipeline():
    """Post-evaluation /btw questions must be grounded in the actual pipeline
    result already shown to the user, not just user_text_so_far."""
    module = WritingModule()
    ctx = _make_ctx()
    pipeline = PipelineResult(
        detector_success=True,
        detector_error="",
        explained_mistakes=[{
            "fragment": "Ich aufstehen", "error_tag": "verb_conjugation",
            "correction": "Ich stehe auf", "explanation": "Separable verbs split in main clauses.",
        }],
        corrected_text="Ich stehe auf.",
        tips=["Practice separable verbs daily."],
        session_summary="Solid A1 attempt with one separable verb error.",
    )
    llm = _make_btw_llm()
    mock_io = MagicMock(spec=IOHandler)

    module._handle_btw(
        ctx, "My morning", ["Ich aufstehen um 7 Uhr."], "why is this wrong?", llm, mock_io,
        pipeline=pipeline,
    )

    prompt_text = llm.complete.call_args_list[0].args[0][1].content
    assert "Ich stehe auf" in prompt_text
    assert "Separable verbs split in main clauses." in prompt_text
    assert "Practice separable verbs daily." in prompt_text
    assert "Solid A1 attempt with one separable verb error." in prompt_text


def test_handle_btw_without_pipeline_omits_evaluation_context():
    """Pre-evaluation /btw (asked mid-writing, before a pipeline result exists)
    must not reference mistake data that doesn't exist yet — regression guard
    against evaluation_context leaking in when pipeline=None (the default)."""
    module = WritingModule()
    ctx = _make_ctx()
    llm = _make_btw_llm()
    mock_io = MagicMock(spec=IOHandler)

    module._handle_btw(
        ctx, "My morning", ["Ich aufstehen um 7 Uhr."], "what does aufstehen mean?", llm, mock_io,
    )

    prompt_text = llm.complete.call_args_list[0].args[0][1].content
    assert "Mistakes found" not in prompt_text
    assert "Corrected text" not in prompt_text
    assert "Session summary" not in prompt_text


class TestFormatEvaluationContext:

    def test_empty_without_explained_mistakes(self):
        from skills.btw_handler.skill import _format_evaluation_context
        assert _format_evaluation_context({}) == ""
        assert _format_evaluation_context({"explained_mistakes": []}) == ""

    def test_includes_mistake_correction_and_explanation(self):
        from skills.btw_handler.skill import _format_evaluation_context
        text = _format_evaluation_context({
            "explained_mistakes": [{
                "fragment": "Ich aufstehen", "correction": "Ich stehe auf",
                "error_tag": "verb_conjugation", "explanation": "Separable verbs split.",
            }],
        })
        assert "Ich aufstehen" in text
        assert "Ich stehe auf" in text
        assert "verb_conjugation" in text
        assert "Separable verbs split." in text

    def test_includes_optional_fields_only_when_present(self):
        from skills.btw_handler.skill import _format_evaluation_context
        mistakes = [{"fragment": "x", "correction": "y", "error_tag": "z", "explanation": "w"}]
        text = _format_evaluation_context({
            "explained_mistakes": mistakes,
            "corrected_text": "Corrected version.",
            "session_summary": "Good effort.",
            "tips": ["Tip one.", "Tip two."],
        })
        assert "Corrected version." in text
        assert "Good effort." in text
        assert "Tip one." in text and "Tip two." in text

        text_no_extras = _format_evaluation_context({"explained_mistakes": mistakes})
        assert "Corrected text" not in text_no_extras
        assert "Session summary" not in text_no_extras
        assert "Tips given" not in text_no_extras
