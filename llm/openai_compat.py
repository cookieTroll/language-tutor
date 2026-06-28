from openai import OpenAI
from llm.base import BaseLLM, LLMMessage, LLMResponse, LLMError
from config import LLMConfig

class OpenAICompatibleLLM(BaseLLM):
    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self.model = config.model
        self.client = OpenAI(
            api_key=config.api_key or "lm-studio",
            base_url=config.base_url or "http://localhost:1234/v1"
        )

    def complete(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """
        Send messages to the local LM Studio instance (or any OpenAI-compatible API).
        Raises LLMError on failure.
        """
        formatted_messages = [
            {"role": msg.role, "content": msg.content}
            for msg in messages
        ]
        tokens_limit = max_tokens if max_tokens is not None else self.config.max_tokens
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=formatted_messages,
                temperature=temperature,
                max_tokens=tokens_limit,
            )
            choice = response.choices[0]
            text = choice.message.content or ""
            truncated = (choice.finish_reason == "length")
            return LLMResponse(text=text, model=self.model, truncated=truncated)
        except Exception as e:
            raise LLMError(f"Local LLM completion failed: {e}") from e
