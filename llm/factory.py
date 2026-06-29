from config import LLMConfig
from llm.base import BaseLLM
from llm.openai_compat import OpenAICompatibleLLM

def build_llm(config: LLMConfig) -> BaseLLM:
    """
    Builds and returns the configured LLM backend.
    Supports: 'openai_compat' (LM Studio), 'ollama' (local Ollama), 'gemini' (Google cloud).
    """
    if config.provider == "ollama":
        from llm.ollama_setup import ensure_ollama_ready
        ensure_ollama_ready(model=config.model, base_url=config.base_url)
        return OpenAICompatibleLLM(config)
    if config.provider == "openai_compat":
        return OpenAICompatibleLLM(config)
    elif config.provider == "gemini":
        from llm.gemini import GeminiLLM
        return GeminiLLM(config)
    else:
        raise ValueError(f"Unknown LLM provider: '{config.provider}'")
