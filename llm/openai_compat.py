import time
from openai import OpenAI
from llm.base import BaseLLM, LLMMessage, LLMResponse, LLMError
from config import LLMConfig

class OpenAICompatibleLLM(BaseLLM):
    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self.model = config.model
        default_url = (
            "http://localhost:11434/v1" if config.provider == "ollama"
            else "http://localhost:1234/v1"
        )
        self._base_url = config.base_url or default_url
        self.client = OpenAI(
            api_key=config.api_key or "ollama",
            base_url=self._base_url,
        )

    def complete(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """
        Send messages to the local LM Studio instance (or any OpenAI-compatible API).
        Raises LLMError on failure after retrying.
        """
        formatted_messages = [
            {"role": msg.role, "content": msg.content}
            for msg in messages
        ]
        tokens_limit = max_tokens if max_tokens is not None else self.config.max_tokens
        
        max_attempts = self.config.max_retries + 1
        delay = self.config.initial_retry_delay
        
        for attempt in range(1, max_attempts + 1):
            try:
                extra = {}
                if self.config.num_ctx is not None:
                    extra["extra_body"] = {"num_ctx": self.config.num_ctx}
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=formatted_messages,
                    temperature=temperature,
                    max_tokens=tokens_limit,
                    **extra,
                )
                choice = response.choices[0]
                text = choice.message.content or ""
                truncated = (choice.finish_reason == "length")
                return LLMResponse(text=text, model=self.model, truncated=truncated)
            except Exception as e:
                # If we've exhausted all attempts, raise LLMError
                if attempt == max_attempts:
                    raise LLMError(f"Local LLM completion failed after {attempt} attempts: {e}") from e
                
                # Otherwise, wait with exponential backoff and try again
                time.sleep(delay)
                delay *= 2.0

    def check_health(self) -> bool:
        import urllib.request
        try:
            url = f"{self._base_url}/models"
            with urllib.request.urlopen(url, timeout=1.5) as response:
                return response.status == 200
        except Exception:
            return False
