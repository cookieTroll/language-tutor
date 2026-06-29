import time
import google.generativeai as genai
from google.generativeai import types
from llm.base import BaseLLM, LLMMessage, LLMResponse, LLMError
from config import LLMConfig


class GeminiLLM(BaseLLM):
    def __init__(self, config: LLMConfig):
        super().__init__(config)
        genai.configure(api_key=config.api_key)
        self._model_name = config.model

    def complete(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        system_parts = [m.content for m in messages if m.role == "system"]
        system_instruction = system_parts[0] if system_parts else None

        contents = []
        for m in messages:
            if m.role == "system":
                continue
            gemini_role = "model" if m.role == "assistant" else "user"
            contents.append({"role": gemini_role, "parts": [m.content]})

        model = genai.GenerativeModel(
            model_name=self._model_name,
            system_instruction=system_instruction,
        )

        tokens_limit = max_tokens if max_tokens is not None else self.config.max_tokens
        generation_config = types.GenerationConfig(
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
                    raise LLMError(f"Gemini completion failed after {attempt} attempts: {e}") from e
                time.sleep(delay)
                delay *= 2.0

    def check_health(self) -> bool:
        try:
            list(genai.list_models())
            return True
        except Exception:
            return False
