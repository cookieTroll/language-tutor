import pytest
from unittest.mock import patch, MagicMock
from modules.writing.agent import WritingModule
from modules.protocols import ModuleContext
from llm.base import BaseLLM, LLMResponse, LLMMessage
from memory.protocols import BtwEntry
from skills.btw_handler.skill import BtwHandlerSkill
from skills.protocols import SkillInput

@patch("modules.writing.agent.input")
def test_writing_module_run(mock_input):
    # Simulate user interaction inside the module's input loop:
    # 1. Write first sentence
    # 2. Ask a vocabulary question mid-session via /btw (matches regex extraction)
    # 3. Write second sentence
    # 4. Press Enter (empty line) to submit and finish
    mock_input.side_effect = [
        "Ich aufstehen um 7 Uhr.",
        "/btw what does aufstehen mean?",
        "Ich esse Fruhstuck.",
        ""
    ]

    llm = MagicMock(spec=BaseLLM)
    
    # Mock LLM completions:
    # 1. BTW Answer ("It means to get up.") - Regex extracts "aufstehen", so no extraction LLM call is made.
    # 2. Detect Mistakes JSON output
    resp_btw_ans = LLMResponse(text="It means to get up.", model="test-model")
    resp_detect = LLMResponse(
        text='{"mistakes": [{"fragment": "Ich aufstehen", "error_type_hint": "separable verb position"}]}',
        model="test-model"
    )
    llm.complete.side_effect = [resp_btw_ans, resp_detect]

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
    result, session_content = module.run(ctx, llm)

    # Asserts
    assert result.module == "writing"
    assert result.task_label == "writing_free"
    assert len(result.errors) == 1
    assert result.errors[0]["fragment"] == "Ich aufstehen"
    
    assert len(result.metadata["btw_entries"]) == 1
    assert isinstance(result.metadata["btw_entries"][0], BtwEntry)
    assert result.metadata["btw_entries"][0].question == "what does aufstehen mean?"
    assert result.metadata["btw_entries"][0].answer == "It means to get up."
    assert result.metadata["btw_entries"][0].flagged_word == "aufstehen"

    # Verify session text and log aggregation
    assert session_content.user_text == "Ich aufstehen um 7 Uhr.\nIch esse Fruhstuck."
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
