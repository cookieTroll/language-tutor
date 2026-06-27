from openai import OpenAI
from llm.base import BaseLLM, LLMMessage, LLMResponse, LLMError

class OpenAICompatibleLLM(BaseLLM):
    def __init__(self, api_key: str | None, base_url: str | None, model: str):
        self.model = model
        self.client = OpenAI(
            api_key=api_key or "lm-studio",
            base_url=base_url or "http://localhost:1234/v1"
        )

    def complete(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.2,
        max_tokens: int = 1000,
    ) -> LLMResponse:
        """
        Send messages to the local LM Studio instance (or any OpenAI-compatible API).
        Raises LLMError on failure.
        """
        formatted_messages = [
            {"role": msg.role, "content": msg.content}
            for msg in messages
        ]
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=formatted_messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            text = response.choices[0].message.content or ""
            return LLMResponse(text=text, model=self.model)
        except Exception as e:
            raise LLMError(f"Local LLM completion failed: {e}") from e
