import pytest
from unittest.mock import patch, MagicMock
from config import LLMConfig
from llm.factory import build_llm
from llm.base import LLMMessage, LLMResponse, LLMError
from llm.openai_compat import OpenAICompatibleLLM

def test_factory_build_openai_compat():
    config = LLMConfig(
        provider="openai_compat",
        base_url="http://localhost:1234/v1",
        api_key="test-key",
        model="test-model"
    )
    llm = build_llm(config)
    assert isinstance(llm, OpenAICompatibleLLM)
    assert llm.model == "test-model"

def test_factory_invalid_provider():
    config = LLMConfig(
        provider="invalid_provider",
        base_url=None,
        api_key=None,
        model="test-model"
    )
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        build_llm(config)

@patch("llm.openai_compat.OpenAI")
def test_openai_compat_completion(mock_openai):
    # Setup mock OpenAI response
    mock_client = MagicMock()
    mock_openai.return_value = mock_client
    
    mock_chat = MagicMock()
    mock_client.chat = mock_chat
    
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Hallo Welt!"
    mock_chat.completions.create.return_value = mock_response

    config = LLMConfig(provider="openai_compat", base_url="url", api_key="key", model="model")
    llm = OpenAICompatibleLLM(config)
    messages = [LLMMessage(role="user", content="Hello world")]
    response = llm.complete(messages)

    assert response.text == "Hallo Welt!"
    assert response.model == "model"
    mock_chat.completions.create.assert_called_once_with(
        model="model",
        messages=[{"role": "user", "content": "Hello world"}],
        temperature=0.2,
        max_tokens=1000
    )

@patch("llm.openai_compat.OpenAI")
def test_openai_compat_completion_failure(mock_openai):
    mock_client = MagicMock()
    mock_openai.return_value = mock_client
    mock_client.chat.completions.create.side_effect = Exception("API Connection error")

    config = LLMConfig(provider="openai_compat", base_url="url", api_key="key", model="model")
    llm = OpenAICompatibleLLM(config)
    messages = [LLMMessage(role="user", content="Hello world")]
    
    with pytest.raises(LLMError, match="Local LLM completion failed"):
        llm.complete(messages)

@patch("llm.openai_compat.OpenAI")
def test_openai_compat_truncation_detection(mock_openai):
    mock_client = MagicMock()
    mock_openai.return_value = mock_client
    mock_chat = MagicMock()
    mock_client.chat = mock_chat
    
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Hallo..."
    mock_response.choices[0].finish_reason = "length"  # Truncated
    mock_chat.completions.create.return_value = mock_response

    config = LLMConfig(
        provider="openai_compat",
        base_url="url",
        api_key="key",
        model="model",
        max_tokens=50,
        show_incomplete_responses=True,
        show_cut_by_limit_tag=True
    )
    llm = OpenAICompatibleLLM(config)
    messages = [LLMMessage(role="user", content="Hello")]
    response = llm.complete(messages)

    assert response.text == "Hallo..."
    assert response.truncated is True
    mock_chat.completions.create.assert_called_once_with(
        model="model",
        messages=[{"role": "user", "content": "Hello"}],
        temperature=0.2,
        max_tokens=50
    )

@patch("llm.openai_compat.OpenAI")
def test_openai_compat_completion_retry(mock_openai):
    mock_client = MagicMock()
    mock_openai.return_value = mock_client
    mock_chat = MagicMock()
    mock_client.chat = mock_chat
    
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Hallo Welt!"
    mock_response.choices[0].finish_reason = "stop"
    
    # Fail first, succeed second
    mock_chat.completions.create.side_effect = [
        Exception("Transient API Error"),
        mock_response
    ]

    config = LLMConfig(
        provider="openai_compat",
        base_url="url",
        api_key="key",
        model="model",
        max_retries=2,
        initial_retry_delay=0.01  # Short delay for fast test
    )
    llm = OpenAICompatibleLLM(config)
    messages = [LLMMessage(role="user", content="Hello")]
    
    response = llm.complete(messages)
    
    assert response.text == "Hallo Welt!"
    assert mock_chat.completions.create.call_count == 2

@patch("urllib.request.urlopen")
def test_openai_compat_check_health_success(mock_urlopen):
    mock_response = MagicMock()
    mock_response.status = 200
    mock_urlopen.return_value.__enter__.return_value = mock_response

    config = LLMConfig(provider="openai_compat", base_url="http://localhost:1234/v1", api_key="key", model="model")
    llm = OpenAICompatibleLLM(config)
    assert llm.check_health() is True

@patch("urllib.request.urlopen")
def test_openai_compat_check_health_failure(mock_urlopen):
    mock_urlopen.side_effect = Exception("Connection refused")

    config = LLMConfig(provider="openai_compat", base_url="http://localhost:1234/v1", api_key="key", model="model")
    llm = OpenAICompatibleLLM(config)
    assert llm.check_health() is False
