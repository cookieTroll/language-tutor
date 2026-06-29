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


def write_results(records: list[dict], prefix: str) -> str:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(RESULTS_DIR, f"{prefix}_{timestamp}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    return path
