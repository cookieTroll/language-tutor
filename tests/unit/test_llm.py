import sys
import pytest
from unittest.mock import patch, MagicMock
from config import LLMConfig
from llm.factory import build_llm
from llm.base import LLMMessage, LLMResponse, LLMError
from llm.openai_compat import OpenAICompatibleLLM

# The 'vertexai' SDK is an optional dependency not installed in this environment
# (not in requirements.txt). Stub it in sys.modules so `llm.vertex` can be imported
# and its provider branch exercised like the others.
try:
    import vertexai  # noqa: F401
except ImportError:
    _vertexai_stub = MagicMock()
    _generative_models_stub = MagicMock()
    _vertexai_stub.generative_models = _generative_models_stub
    sys.modules.setdefault("vertexai", _vertexai_stub)
    sys.modules.setdefault("vertexai.generative_models", _generative_models_stub)

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

@patch("llm.gemini.genai")
def test_factory_build_gemini(mock_genai):
    from llm.gemini import GeminiLLM
    config = LLMConfig(
        provider="gemini",
        base_url=None,
        api_key="test-key",
        model="gemini-2.0-flash"
    )
    llm = build_llm(config)
    assert isinstance(llm, GeminiLLM)
    mock_genai.configure.assert_called_once_with(api_key="test-key")

@patch("llm.vertex.vertexai")
def test_factory_build_vertex(mock_vertexai):
    from llm.vertex import VertexAILLM
    config = LLMConfig(
        provider="vertex",
        base_url="my-gcp-project",
        api_key=None,
        model="gemini-2.0-flash-001"
    )
    llm = build_llm(config)
    assert isinstance(llm, VertexAILLM)
    mock_vertexai.init.assert_called_once_with(project="my-gcp-project", location="europe-west1")

def test_factory_build_vertex_missing_project_id_raises():
    config = LLMConfig(
        provider="vertex",
        base_url=None,
        api_key=None,
        model="gemini-2.0-flash-001"
    )
    with pytest.raises(ValueError, match="requires 'base_url'"):
        build_llm(config)

@patch("llm.ollama_setup.ensure_ollama_ready")
def test_factory_build_ollama(mock_ensure_ready):
    config = LLMConfig(
        provider="ollama",
        base_url="http://localhost:11434/v1",
        api_key="ollama",
        model="gemma2:9b"
    )
    llm = build_llm(config)
    assert isinstance(llm, OpenAICompatibleLLM)
    mock_ensure_ready.assert_called_once_with(model="gemma2:9b", base_url="http://localhost:11434/v1")

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

@patch("llm.gemini.types")
@patch("llm.gemini.genai")
def test_gemini_completion(mock_genai, mock_types):
    from llm.gemini import GeminiLLM

    mock_model = MagicMock()
    mock_genai.GenerativeModel.return_value = mock_model

    mock_candidate = MagicMock()
    mock_candidate.finish_reason.name = "STOP"
    mock_response = MagicMock()
    mock_response.text = "Hallo Welt!"
    mock_response.candidates = [mock_candidate]
    mock_model.generate_content.return_value = mock_response

    config = LLMConfig(provider="gemini", base_url=None, api_key="key", model="gemini-2.0-flash")
    llm = GeminiLLM(config)
    response = llm.complete([LLMMessage(role="user", content="Hello")])

    assert response.text == "Hallo Welt!"
    assert response.model == "gemini-2.0-flash"
    assert response.truncated is False

@patch("llm.gemini.types")
@patch("llm.gemini.genai")
def test_gemini_truncation_detection(mock_genai, mock_types):
    from llm.gemini import GeminiLLM

    mock_model = MagicMock()
    mock_genai.GenerativeModel.return_value = mock_model

    mock_candidate = MagicMock()
    mock_candidate.finish_reason.name = "MAX_TOKENS"
    mock_response = MagicMock()
    mock_response.text = "Hallo..."
    mock_response.candidates = [mock_candidate]
    mock_model.generate_content.return_value = mock_response

    config = LLMConfig(provider="gemini", base_url=None, api_key="key", model="gemini-2.0-flash")
    llm = GeminiLLM(config)
    response = llm.complete([LLMMessage(role="user", content="Hello")])

    assert response.truncated is True

@patch("llm.gemini.types")
@patch("llm.gemini.genai")
def test_gemini_completion_failure_after_retries(mock_genai, mock_types):
    from llm.gemini import GeminiLLM

    mock_model = MagicMock()
    mock_genai.GenerativeModel.return_value = mock_model
    mock_model.generate_content.side_effect = Exception("API error")

    config = LLMConfig(
        provider="gemini", base_url=None, api_key="key", model="gemini-2.0-flash",
        max_retries=1, initial_retry_delay=0.01
    )
    llm = GeminiLLM(config)

    with pytest.raises(LLMError, match="Gemini completion failed"):
        llm.complete([LLMMessage(role="user", content="Hello")])
    assert mock_model.generate_content.call_count == 2

@patch("llm.gemini.genai")
def test_gemini_check_health_success(mock_genai):
    from llm.gemini import GeminiLLM
    mock_genai.list_models.return_value = [MagicMock()]

    config = LLMConfig(provider="gemini", base_url=None, api_key="key", model="model")
    llm = GeminiLLM(config)
    assert llm.check_health() is True

@patch("llm.gemini.genai")
def test_gemini_check_health_failure(mock_genai):
    from llm.gemini import GeminiLLM
    mock_genai.list_models.side_effect = Exception("Connection refused")

    config = LLMConfig(provider="gemini", base_url=None, api_key="key", model="model")
    llm = GeminiLLM(config)
    assert llm.check_health() is False

@patch("llm.vertex.Part")
@patch("llm.vertex.Content")
@patch("llm.vertex.GenerationConfig")
@patch("llm.vertex.GenerativeModel")
@patch("llm.vertex.vertexai")
def test_vertex_completion(mock_vertexai, mock_generative_model_cls, mock_gen_config, mock_content, mock_part):
    from llm.vertex import VertexAILLM

    mock_model = MagicMock()
    mock_generative_model_cls.return_value = mock_model

    mock_candidate = MagicMock()
    mock_candidate.finish_reason.name = "STOP"
    mock_response = MagicMock()
    mock_response.text = "Hallo Welt!"
    mock_response.candidates = [mock_candidate]
    mock_model.generate_content.return_value = mock_response

    config = LLMConfig(provider="vertex", base_url="my-gcp-project", api_key=None, model="gemini-2.0-flash-001")
    llm = VertexAILLM(config)
    response = llm.complete([LLMMessage(role="user", content="Hello")])

    assert response.text == "Hallo Welt!"
    assert response.model == "gemini-2.0-flash-001"
    assert response.truncated is False

@patch("llm.vertex.Part")
@patch("llm.vertex.Content")
@patch("llm.vertex.GenerationConfig")
@patch("llm.vertex.GenerativeModel")
@patch("llm.vertex.vertexai")
def test_vertex_completion_failure_after_retries(mock_vertexai, mock_generative_model_cls, mock_gen_config, mock_content, mock_part):
    from llm.vertex import VertexAILLM

    mock_model = MagicMock()
    mock_generative_model_cls.return_value = mock_model
    mock_model.generate_content.side_effect = Exception("API error")

    config = LLMConfig(
        provider="vertex", base_url="my-gcp-project", api_key=None, model="gemini-2.0-flash-001",
        max_retries=1, initial_retry_delay=0.01
    )
    llm = VertexAILLM(config)

    with pytest.raises(LLMError, match="Vertex AI completion failed"):
        llm.complete([LLMMessage(role="user", content="Hello")])
    assert mock_model.generate_content.call_count == 2

@patch("llm.vertex.vertexai")
def test_vertex_check_health_success(mock_vertexai):
    from llm.vertex import VertexAILLM
    config = LLMConfig(provider="vertex", base_url="my-gcp-project", api_key=None, model="model")
    llm = VertexAILLM(config)
    assert llm.check_health() is True

@patch("llm.vertex.vertexai")
def test_vertex_check_health_failure(mock_vertexai):
    from llm.vertex import VertexAILLM
    config = LLMConfig(provider="vertex", base_url="my-gcp-project", api_key=None, model="model")
    llm = VertexAILLM(config)
    mock_vertexai.init.side_effect = Exception("not initialised")
    assert llm.check_health() is False
