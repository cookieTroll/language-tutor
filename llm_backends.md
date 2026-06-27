# LanguageTutor — LLM Backends

All LLM calls go through `BaseLLM`. No skill, module, or orchestrator imports a provider SDK directly. Swap backend by changing `llm.backend` in `config.yaml`.

See `docs/contracts.md` for `BaseLLM`, `LLMMessage`, `LLMResponse`.

---

## File Structure

```
llm/
├── base.py         # BaseLLM abstract class — the only thing other components import
├── factory.py      # build_llm(config) → BaseLLM instance
├── gemini.py       # GeminiLLM (production default)
└── openai_compat.py  # OpenAICompatibleLLM (OpenAI API + LM Studio local)
```

Ollama is not currently supported. Can be added later as another `BaseLLM` subclass without touching any other component.

---

## `llm/base.py`

```python
from dataclasses import dataclass
from abc import ABC, abstractmethod

@dataclass
class LLMMessage:
    role: str        # system | user | assistant
    content: str

@dataclass
class LLMResponse:
    text: str
    model: str       # actual model used — logged for observability

class LLMError(Exception):
    """Raised on provider errors, timeouts, or malformed responses."""
    pass

class BaseLLM(ABC):
    @abstractmethod
    def complete(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.2,
        max_tokens: int = 1000,
    ) -> LLMResponse:
        """
        Send messages, return response.
        Raises LLMError on failure — never returns None.
        Callers parse LLMResponse.text; they do not catch provider exceptions.
        """
        ...
```

---

## `llm/gemini.py` — GeminiLLM

Production default. Wraps `google-generativeai` SDK.

```python
import google.generativeai as genai
from llm.base import BaseLLM, LLMMessage, LLMResponse, LLMError

class GeminiLLM(BaseLLM):
    def __init__(self, model: str = "gemini-2.0-flash", api_key: str | None = None):
        genai.configure(api_key=api_key or os.environ["GEMINI_API_KEY"])
        self._model = genai.GenerativeModel(model)
        self._model_name = model

    def complete(self, messages, temperature=0.2, max_tokens=1000) -> LLMResponse:
        try:
            # Convert LLMMessage list to Gemini format
            # System message handled separately as system_instruction
            ...
            return LLMResponse(text=response.text, model=self._model_name)
        except Exception as e:
            raise LLMError(f"Gemini error: {e}") from e
```

**Notes:**
- API key from `GEMINI_API_KEY` env var (preferred) or config
- System message must be passed as `system_instruction` in Gemini API — handle in adapter
- Rate limits: implement basic exponential backoff for 429 errors

---

## `llm/openai_compat.py` — OpenAICompatibleLLM

Single implementation covering two use cases via `base_url`:

- **OpenAI API** (`base_url=None`) — cloud, paid, high quality
- **LM Studio** (`base_url="http://localhost:1234/v1"`) — local, free, development use

Both use the same OpenAI-compatible `/v1/chat/completions` endpoint and the `openai` Python SDK.

```python
from openai import OpenAI
from llm.base import BaseLLM, LLMMessage, LLMResponse, LLMError

class OpenAICompatibleLLM(BaseLLM):
    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        base_url: str | None = None,   # None = OpenAI; set to LM Studio URL for local
    ):
        self._client = OpenAI(
            api_key=api_key or os.environ.get("OPENAI_API_KEY", "lm-studio"),
            base_url=base_url,
        )
        self._model = model

    def complete(self, messages, temperature=0.2, max_tokens=1000) -> LLMResponse:
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": m.role, "content": m.content} for m in messages],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return LLMResponse(
                text=response.choices[0].message.content,
                model=response.model,
            )
        except Exception as e:
            raise LLMError(f"OpenAI-compatible API error: {e}") from e
```

**LM Studio notes:**
- Download from [lmstudio.ai](https://lmstudio.ai), load a model, start the local server
- Default endpoint: `http://localhost:1234/v1`
- API key is not checked by LM Studio — any non-empty string works (e.g. `"lm-studio"`)
- Model name must match exactly what LM Studio shows (e.g. `"mistral-7b-instruct-v0.3"`)
- Quality warning: local models are weaker than Gemini on nuanced grammar feedback. Use for development and cost-free iteration, not as primary production backend. Run judge fixtures against both to compare.

**Other compatible providers (via `base_url`):**
- Together AI: `base_url="https://api.together.xyz/v1"`
- Groq: `base_url="https://api.groq.com/openai/v1"`
- Mistral API: `base_url="https://api.mistral.ai/v1"`

---

## `llm/factory.py`

```python
from llm.base import BaseLLM
from llm.gemini import GeminiLLM
from llm.openai_compat import OpenAICompatibleLLM

def build_llm(config: dict) -> BaseLLM:
    """
    Read config['llm'] and return the correct BaseLLM implementation.
    Raises ValueError on unknown backend — fail fast at startup, not mid-session.
    """
    llm_cfg = config.get("llm", {})
    backend = llm_cfg.get("backend", "gemini")
    model = llm_cfg.get("model")

    if backend == "gemini":
        return GeminiLLM(model=model or "gemini-2.0-flash")

    elif backend == "lm_studio":
        return OpenAICompatibleLLM(
            model=model or "mistral-7b-instruct-v0.3",
            api_key="lm-studio",           # LM Studio ignores the key value
            base_url=llm_cfg.get("lm_studio_base_url", "http://localhost:1234/v1"),
        )

    elif backend == "openai":
        return OpenAICompatibleLLM(
            model=model or "gpt-4o-mini",
            base_url=llm_cfg.get("openai_base_url"),  # None = OpenAI default
        )

    else:
        raise ValueError(
            f"Unknown LLM backend: '{backend}'. "
            f"Valid options: gemini, lm_studio, openai"
        )
```

---

## Config (`config.yaml`)

```yaml
llm:
  backend: gemini              # gemini | lm_studio | openai
  model: gemini-2.0-flash      # overrides per-implementation default
  temperature: 0.2
  lm_studio_base_url: http://localhost:1234/v1   # only used if backend: lm_studio
  openai_base_url: null                          # only used if backend: openai
```

**Development workflow:** set `backend: lm_studio` to iterate locally at zero cost. Switch to `backend: gemini` for quality testing and final evaluation.

---

## Injection Pattern

LLM instance built once at startup, injected into orchestrator and modules. Never constructed inside a skill or module.

```python
# ui/cli.py or ui/app.py
config = load_config("config.yaml")
llm = build_llm(config)
storage = build_storage(config)
orchestrator = Orchestrator(storage=storage, llm=llm, registry=MODULE_REGISTRY)
```

---

## Mock LLM (Testing)

```python
# tests/conftest.py
class MockLLM(BaseLLM):
    def __init__(self, responses: list[str]):
        self._responses = iter(responses)

    def complete(self, messages, **kwargs) -> LLMResponse:
        return LLMResponse(
            text=next(self._responses),
            model="mock"
        )
```

All unit tests inject `MockLLM` — no network calls, no API keys in CI.

```python
mock_llm = MockLLM(responses=[
    '{"mistakes": []}',          # detector returns no errors
    '{"classified": [...]}',     # processor output
])
module = WritingModule(skills=writing_skills(llm=mock_llm))
```
