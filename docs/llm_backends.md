# LanguageTutor — LLM Backends

All LLM calls go through `BaseLLM`. No skill, module, or orchestrator imports a provider SDK directly. Swap provider by editing the `llm:` block in the active config file (see `PROVIDERS.md`).

---

## File Structure

```
llm/
├── base.py           # BaseLLM abstract class + LLMMessage, LLMResponse, LLMError
├── factory.py        # build_llm(LLMConfig) → BaseLLM
├── gemini.py         # GeminiLLM — Google Gemini via google-generativeai SDK
├── openai_compat.py  # OpenAICompatibleLLM — LM Studio, Ollama, or any OpenAI-compat endpoint
└── ollama_setup.py   # ensure_ollama_ready() — auto-starts Ollama, pulls model if missing
```

---

## `llm/base.py`

```python
@dataclass
class LLMMessage:
    role: str        # system | user | assistant
    content: str

@dataclass
class LLMResponse:
    text: str
    model: str       # actual model used — logged for observability
    truncated: bool = False

class BaseLLM(ABC):
    config: LLMConfig

    def __init__(self, config: LLMConfig): ...

    @abstractmethod
    def complete(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.2,
        max_tokens: int | None = None,   # None → uses config.max_tokens
    ) -> LLMResponse: ...

    def check_health(self) -> bool:
        """Returns True if the backend is reachable. Default: True."""
        ...
```

`LLMResponse.truncated` is `True` when the response was cut short by the token limit (`finish_reason == "length"` for OpenAI-compat, `MAX_TOKENS` for Gemini).

---

## Providers

### `llm/openai_compat.py` — OpenAICompatibleLLM

Handles both **LM Studio** and **Ollama** via their shared OpenAI-compatible endpoint.

```python
class OpenAICompatibleLLM(BaseLLM):
    def __init__(self, config: LLMConfig):
        # Default base_url: localhost:11434/v1 (Ollama) or localhost:1234/v1 (LM Studio)
        default_url = (
            "http://localhost:11434/v1" if config.provider == "ollama"
            else "http://localhost:1234/v1"
        )
        self._base_url = config.base_url or default_url
        self.client = OpenAI(api_key=config.api_key or "ollama", base_url=self._base_url)
```

Ollama-specific: `num_ctx` from config is passed via `extra_body={"num_ctx": N}` if set.

Retry: exponential backoff, `config.max_retries` attempts, starting at `config.initial_retry_delay` seconds.

`check_health()` hits `{base_url}/models` with a 1.5 s timeout.

### `llm/gemini.py` — GeminiLLM

```python
class GeminiLLM(BaseLLM):
    def __init__(self, config: LLMConfig):
        genai.configure(api_key=config.api_key)
        self._model_name = config.model
```

- System messages are extracted and passed as `system_instruction` to `GenerativeModel`.
- `assistant` role is mapped to `"model"` (Gemini's name for that role).
- `truncated` is set from `finish_reason.name == "MAX_TOKENS"`.
- `check_health()` calls `genai.list_models()`.
- Same retry/backoff pattern as `OpenAICompatibleLLM`.

---

## `llm/ollama_setup.py`

Called automatically by `factory.py` when `provider == "ollama"`. No manual invocation needed.

```python
def ensure_ollama_ready(model: str, base_url: str | None = None) -> None:
    # 1. Strips /v1 from base_url to get native Ollama API root
    # 2. If Ollama is not running, spawns 'ollama serve' and waits up to 15 s
    # 3. Checks local model list; runs 'ollama pull <model>' if absent
    # Raises RuntimeError if Ollama is not installed or startup times out
```

Model matching: treats `name` and `name:latest` as equivalent.

---

## `llm/factory.py`

```python
def build_llm(config: LLMConfig) -> BaseLLM:
    if config.provider == "ollama":
        ensure_ollama_ready(model=config.model, base_url=config.base_url)
        return OpenAICompatibleLLM(config)
    if config.provider == "openai_compat":
        return OpenAICompatibleLLM(config)
    elif config.provider == "gemini":
        return GeminiLLM(config)
    else:
        raise ValueError(f"Unknown LLM provider: '{config.provider}'")
```

Valid providers: `"ollama"`, `"openai_compat"`, `"gemini"`. Validated in `config.py` at load time.

---

## Config

`LLMConfig` fields (all sourced from the `llm:` block in the active config file):

| Field | Type | Default | Notes |
|---|---|---|---|
| `provider` | str | required | `ollama` \| `openai_compat` \| `gemini` |
| `model` | str | required | Exact model identifier |
| `base_url` | str \| None | None | Provider API URL; has per-provider defaults |
| `api_key` | str \| None | None | Supports `${VAR_NAME}` env var placeholder |
| `max_tokens` | int | 1000 | Max response tokens per call |
| `num_ctx` | int \| None | None | Ollama context window; omit for model default |
| `max_retries` | int | 3 | Retry attempts on transient failure |
| `initial_retry_delay` | float | 1.0 | First backoff delay in seconds (doubles each retry) |
| `max_skill_retries` | int | 3 | Max self-correction loops inside skills |
| `show_incomplete_responses` | bool | False | Print raw LLM text on JSON parse failure |
| `show_cut_by_limit_tag` | bool | True | Append `[TRUNCATED BY LIMIT]` on truncation |

`${VAR_NAME}` placeholders in `api_key` or `base_url` are resolved from environment variables at load time. Missing variable → `ValueError` at startup.

---

## Injection Pattern

`build_llm` is called once at startup; the instance is injected everywhere.

```python
# ui/cli.py
config = load_config(os.environ.get("LTUT_CONFIG", "config.yaml"))
llm = build_llm(config.llm)
orchestrator = Orchestrator(storage=build_storage(config), llm=llm, ...)
```

Skills and modules receive `llm` as a parameter. They never import a provider SDK or call `build_llm` themselves.

---

## Mock LLM (unit tests)

```python
class MockLLM(BaseLLM):
    def __init__(self, responses: list[str]):
        self._responses = iter(responses)

    def complete(self, messages, **kwargs) -> LLMResponse:
        return LLMResponse(text=next(self._responses), model="mock")
```

All unit tests use `MockLLM` — no network calls, no API keys required in CI.
