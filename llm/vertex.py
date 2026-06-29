"""
Vertex AI LLM backend.

Authenticates via Application Default Credentials (ADC) — no API key needed.
Set up once with:
    gcloud auth application-default login

Config fields used:
  - model:    Vertex AI model name (e.g. 'gemini-2.0-flash-001')
  - base_url: GCP project ID  (required)
  - api_key:  GCP region      (optional; defaults to 'us-central1')
"""
import time
import vertexai
from vertexai.generative_models import GenerativeModel, GenerationConfig, Content, Part
from llm.base import BaseLLM, LLMMessage, LLMResponse, LLMError
from config import LLMConfig

_DEFAULT_REGION = "europe-west1"


class VertexAILLM(BaseLLM):
    def __init__(self, config: LLMConfig):
        super().__init__(config)
        project_id = config.base_url
        if not project_id:
            raise ValueError(
                "Vertex AI backend requires 'base_url' to be set to your GCP project ID "
                "in the config file (e.g. base_url: 'my-gcp-project')."
            )
        region = config.api_key or _DEFAULT_REGION
        vertexai.init(project=project_id, location=region)
        self._model_name = config.model

    def complete(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        system_parts = [m.content for m in messages if m.role == "system"]
        system_instruction = system_parts[0] if system_parts else None

        contents: list[Content] = []
        for m in messages:
            if m.role == "system":
                continue
            vertex_role = "model" if m.role == "assistant" else "user"
            contents.append(Content(role=vertex_role, parts=[Part.from_text(m.content)]))

        model = GenerativeModel(
            model_name=self._model_name,
            system_instruction=system_instruction,
        )

        tokens_limit = max_tokens if max_tokens is not None else self.config.max_tokens
        generation_config = GenerationConfig(
            temperature=temperature,
            max_output_tokens=tokens_limit,
        )

        max_attempts = self.config.max_retries + 1
        delay = self.config.initial_retry_delay

        for attempt in range(1, max_attempts + 1):
            try:
                response = model.generate_content(
                    contents=contents,
                    generation_config=generation_config,
                )
                text = response.text or ""
                finish_reason = (
                    response.candidates[0].finish_reason
                    if response.candidates
                    else None
                )
                truncated = finish_reason is not None and finish_reason.name == "MAX_TOKENS"
                return LLMResponse(text=text, model=self._model_name, truncated=truncated)
            except Exception as e:
                if attempt == max_attempts:
                    raise LLMError(
                        f"Vertex AI completion failed after {attempt} attempts: {e}"
                    ) from e
                time.sleep(delay)
                delay *= 2.0

    def check_health(self) -> bool:
        try:
            # Lightweight check: list available models in the project
            vertexai.init()  # already initialised, no-op
            return True
        except Exception:
            return False
