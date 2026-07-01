import json
import os
from datetime import datetime

_LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "logs")
_LOG_PATH = os.path.join(_LOG_DIR, "skill_errors.jsonl")


def log_skill_error(module: str, skill_name: str, error: str, context: dict | None = None) -> None:
    """Appends a structured record for a failed skill call (out.success is False).

    Unlike the latency log, this deliberately does NOT skip during pytest runs —
    judge tests call real LLMs and a failure there is exactly what this exists
    to capture. A `pytest_current_test` field is included instead, so log
    entries written during automated test runs can still be told apart from
    real sessions without suppressing them.
    """
    os.makedirs(_LOG_DIR, exist_ok=True)
    record = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "module": module,
        "skill": skill_name,
        "error": error,
        "pytest_current_test": os.environ.get("PYTEST_CURRENT_TEST"),
        **(context or {}),
    }
    with open(_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
