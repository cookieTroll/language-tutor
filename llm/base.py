from dataclasses import dataclass
from abc import ABC, abstractmethod

@dataclass
class LLMMessage:
    role: str        # system | user | assistant
    content: str

@dataclass
class LLMResponse:
    text: str
    model: str       # actual model used, logged for observability

class BaseLLM(ABC):
    @abstractmethod
    def complete(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.2,
        max_tokens: int = 1000,
    ) -> LLMResponse:
        """Send messages, return response. Raises LLMError on failure."""
        ...
