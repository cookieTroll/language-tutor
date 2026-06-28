import os
import yaml
from dataclasses import dataclass

@dataclass
class LLMConfig:
    provider: str
    base_url: str | None
    api_key: str | None
    model: str
    max_tokens: int = 1000
    show_incomplete_responses: bool = False
    show_cut_by_limit_tag: bool = True
    max_retries: int = 3
    initial_retry_delay: float = 1.0
    max_skill_retries: int = 3

@dataclass
class AppConfig:
    data_root: str
    default_level: str
    cold_start_threshold: int
    interruption_timeout_minutes: int
    storage_backend: str
    llm: LLMConfig

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
