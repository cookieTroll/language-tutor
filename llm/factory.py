from config import LLMConfig
from llm.base import BaseLLM
from llm.openai_compat import OpenAICompatibleLLM

def build_llm(config: LLMConfig) -> BaseLLM:
    """
    Builds and returns the configured LLM backend.
    Supports: 'openai_compat' (local LM Studio/Ollama) and 'gemini' (cloud).
    """
    if config.provider == "openai_compat":
        return OpenAICompatibleLLM(config)
    elif config.provider == "gemini":
        try:
            from llm.gemini import GeminiLLM
            return GeminiLLM(api_key=config.api_key, model=config.model)
        except (ImportError, ModuleNotFoundError):
            raise NotImplementedError(
                "Gemini provider is selected but the backend is not yet implemented."
            )
    else:
        raise ValueError(f"Unknown LLM provider: '{config.provider}'")
