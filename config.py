import os
import yaml
from dataclasses import dataclass

@dataclass
class LLMConfig:
    provider: str                      # LLM provider ('openai_compat' | 'gemini')
    base_url: str | None               # Base URL for API calls
    api_key: str | None                # API key for the provider
    model: str                         # The exact model identifier to request
    max_tokens: int = 1000             # Maximum response tokens per call
    show_incomplete_responses: bool = False # If true, outputs incomplete LLM text when JSON parsing fails
    show_cut_by_limit_tag: bool = True # If true, appends '[TRUNCATED BY LIMIT]' to responses cut off by max_tokens
    max_retries: int = 3               # Connection and network retry attempts for LLM completion requests
    initial_retry_delay: float = 1.0   # Starting backoff delay (in seconds) for connection retries
    max_skill_retries: int = 3         # Max agentic self-correction iterations for skills when output validation fails

@dataclass
class AppConfig:
    data_root: str                     # Root directory for session files, databases, checkpoints, and logs
    default_level: str                 # Default CEFR level (a1-c2) assigned to new users
    cold_start_threshold: int          # Minimum completed sessions before progress summaries can be generated
    interruption_timeout_minutes: int  # Time window (in minutes) to check and resume interrupted sessions
    storage_backend: str               # Storage engine choice ('sqlite' | 'json')
    llm: LLMConfig                     # LLM backend configurations

def load_config(config_path: str = "config.yaml") -> AppConfig:
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found at {config_path}")
    
    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
        
    # Basic validation of outer fields
    required_fields = [
        "data_root",
        "default_level",
        "cold_start_threshold",
        "interruption_timeout_minutes",
        "storage_backend",
        "llm",
    ]
    for field in required_fields:
        if field not in data:
            raise ValueError(f"Missing required config field: '{field}'")
            
    storage = data["storage_backend"]
    if storage not in ("sqlite", "json"):
        raise ValueError(f"Invalid storage_backend: '{storage}'. Must be 'sqlite' or 'json'")
        
    llm_data = data["llm"]
    llm_required = ["provider", "model"]
    for field in llm_required:
        if field not in llm_data:
            raise ValueError(f"Missing required LLM config field: '{field}'")
            
    provider = llm_data["provider"]
    if provider not in ("openai_compat", "gemini"):
        raise ValueError(f"Invalid LLM provider: '{provider}'. Must be 'openai_compat' or 'gemini'")
        
    llm_config = LLMConfig(
        provider=provider,
        base_url=llm_data.get("base_url"),
        api_key=llm_data.get("api_key"),
        model=llm_data["model"],
        max_tokens=int(llm_data.get("max_tokens", 1000)),
        show_incomplete_responses=bool(llm_data.get("show_incomplete_responses", False)),
        show_cut_by_limit_tag=bool(llm_data.get("show_cut_by_limit_tag", True)),
        max_retries=int(llm_data.get("max_retries", 3)),
        initial_retry_delay=float(llm_data.get("initial_retry_delay", 1.0)),
        max_skill_retries=int(llm_data.get("max_skill_retries", 3)),
    )
    
    return AppConfig(
        data_root=data["data_root"],
        default_level=data["default_level"].lower(),
        cold_start_threshold=int(data["cold_start_threshold"]),
        interruption_timeout_minutes=int(data["interruption_timeout_minutes"]),
        storage_backend=storage,
        llm=llm_config,
    )
