"""Shared helpers for pipeline judge tests."""
import datetime
import json
import os
import re
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FIXTURE_PATH = os.path.join(PROJECT_ROOT, "tests", "fixtures", "pipeline_cases.json")
RESULTS_DIR = os.path.join(PROJECT_ROOT, "tests", "judge", "results")
sys.path.insert(0, PROJECT_ROOT)


def load_cases() -> list[dict]:
    with open(FIXTURE_PATH, encoding="utf-8") as f:
        return json.load(f)


def make_llm(config_path: str):
    from config import load_config
    from llm.factory import build_llm as _build
    config = load_config(os.path.join(PROJECT_ROOT, config_path))
    return _build(config.llm)


def strip_markdown_json(text: str) -> str:
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return text.strip()


def run_metadata(include_judge_config: bool = True) -> dict:
    """Run-identifying metadata sourced from env vars set by scripts/run_judge_variance.py.

    Falls back to sensible defaults so a plain `pytest tests/judge/...` invocation
    (no runner involved) still produces a valid, if sparse, metadata block.
    """
    repeat_index = os.environ.get("LTUT_REPEAT_INDEX")
    executor_config = os.environ.get("LTUT_CONFIG", "config.test.yaml")
    metadata = {
        "batch_id": os.environ.get("LTUT_BATCH_ID"),
        "repeat_index": int(repeat_index) if repeat_index else None,
        "executor_config": executor_config,
    }
    if include_judge_config:
        metadata["judge_config"] = os.environ.get("LTUT_JUDGE_CONFIG", executor_config)
    return metadata


def write_results(records: list[dict], prefix: str, metadata: dict | None = None) -> str:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(RESULTS_DIR, f"{prefix}_{timestamp}.json")
    payload = {"metadata": metadata or {}, "records": records}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path
