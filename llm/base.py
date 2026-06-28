from dataclasses import dataclass
from abc import ABC, abstractmethod
from config import LLMConfig

class LLMError(Exception):
    """Custom exception raised when an LLM completion fails."""
    pass

@dataclass
class LLMMessage:
    role: str        # system | user | assistant
    content: str

@dataclass
class LLMResponse:
    text: str
    model: str       # actual model used, logged for observability
    truncated: bool = False

class BaseLLM(ABC):
    config: LLMConfig = None  # type: ignore

    def __init__(self, config: LLMConfig):
        self.config = config

    @abstractmethod
    def complete(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Send messages, return response. Raises LLMError on failure."""
        ...

    def check_health(self) -> bool:
        """Returns True if the LLM backend is reachable, False otherwise."""
        return True
