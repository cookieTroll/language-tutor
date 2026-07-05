"""Generates a new target language's content maps (taxonomy, CEFR hints, grammar
topics) via LLM, validated through the same Pydantic contracts and cross-reference
checks lang/loader.py already applies to the hand-authored German maps.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from lang.generate_prompts import CEFR_HINTS_PROMPT, GRAMMAR_TOPICS_PROMPT, TAXONOMY_PROMPT
from lang.loader import _Registry
from lang.models import CEFRMap, GrammarTopicsMap, LanguageConfig, TaxonomyMap
from llm.base import BaseLLM, LLMMessage
from skills.protocols import call_with_self_correction

_LANG_DIR = Path(__file__).parent
_MAPS_DIR = _LANG_DIR / "maps"
_LANGUAGES_DIR = _LANG_DIR / "languages"

MIN_GRAMMAR_TOPICS = 8
CEFR_LEVELS = ("a1", "a2", "b1", "b2", "c1", "c2")


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:yaml|yml)?\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return text.strip()


def generate_taxonomy(llm: BaseLLM, language: str) -> TaxonomyMap:
    """Generates the error-classification taxonomy — validated by TaxonomyMap,
    which already enforces the 'other' catch-all tag."""

    def parse(text: str) -> TaxonomyMap:
        data = yaml.safe_load(_strip_fences(text))
        return TaxonomyMap.model_validate(data)

    prompt = TAXONOMY_PROMPT.format(language=language)
    messages = [LLMMessage(role="user", content=prompt)]
    return call_with_self_correction(llm, messages, parse, temperature=0.4)


def generate_cefr_hints(llm: BaseLLM, language: str, taxonomy: TaxonomyMap) -> CEFRMap:
    """Generates per-level pedagogical focus hints, grounded in the just-generated
    taxonomy's tag names so the hints reference tags that actually exist."""

    def parse(text: str) -> CEFRMap:
        data = yaml.safe_load(_strip_fences(text))
        cefr_map = CEFRMap.model_validate(data)
        missing = [lvl for lvl in CEFR_LEVELS if not getattr(cefr_map, lvl)]
        if missing:
            raise ValueError(f"Missing hints for CEFR level(s): {missing}")
        return cefr_map

    prompt = CEFR_HINTS_PROMPT.format(language=language, taxonomy_tags=taxonomy.format_for_prompt())
    messages = [LLMMessage(role="user", content=prompt)]
    return call_with_self_correction(llm, messages, parse, temperature=0.4)


def generate_grammar_topics(
    llm: BaseLLM,
    language: str,
    taxonomy: TaxonomyMap,
    level_range: tuple[str, str] = ("a1", "b2"),
    min_topics: int = MIN_GRAMMAR_TOPICS,
) -> GrammarTopicsMap:
    """Generates the curated grammar syllabus. related_error_tags are checked against
    the taxonomy's tag_set here — the same check lang/loader.py runs at load time —
    so a hallucinated tag triggers a self-correction retry instead of silently
    writing a syllabus that would fail validation later."""

    def parse(text: str) -> GrammarTopicsMap:
        data = yaml.safe_load(_strip_fences(text))
        topics_map = GrammarTopicsMap(topics=data or [])
        for topic in topics_map.topics:
            for tag in topic.related_error_tags:
                if tag not in taxonomy.tag_set:
                    raise ValueError(
                        f"Grammar topic '{topic.topic}' references unknown error tag "
                        f"'{tag}'. Must be one of {sorted(taxonomy.tag_set)}"
                    )
        if len(topics_map.topics) < min_topics:
            raise ValueError(
                f"Only {len(topics_map.topics)} topics returned, need at least {min_topics}"
            )
        return topics_map

    prompt = GRAMMAR_TOPICS_PROMPT.format(
        language=language,
        taxonomy_tags=taxonomy.format_for_prompt(),
        level_low=level_range[0],
        level_high=level_range[1],
        min_topics=min_topics,
    )
    messages = [LLMMessage(role="user", content=prompt)]
    return call_with_self_correction(llm, messages, parse, temperature=0.5)


def write_language_assets(
    name: str,
    taxonomy: TaxonomyMap,
    cefr_hints: CEFRMap,
    grammar_topics: GrammarTopicsMap,
    maps_dir: Path | None = None,
    languages_dir: Path | None = None,
) -> dict[str, Path]:
    """Writes the four generated files and re-validates everything end-to-end by
    constructing a fresh _Registry over the target directories — the same
    cross-reference checks lang/loader.py already runs at import time, reused as-is
    instead of duplicated here. Raises ValueError on any bad reference."""
    maps_dir = maps_dir or _MAPS_DIR
    languages_dir = languages_dir or _LANGUAGES_DIR
    name = name.lower()

    taxonomy_name = f"{name}_taxonomy_v1"
    cefr_name = f"{name}_map1"
    grammar_topics_name = f"{name}_a1_b2"

    taxonomy_path = maps_dir / "taxonomy" / f"{taxonomy_name}.yaml"
    cefr_path = maps_dir / "cefr" / f"{cefr_name}.yaml"
    grammar_topics_path = maps_dir / "grammar_topics" / f"{grammar_topics_name}.yaml"
    language_path = languages_dir / f"{name}.yaml"

    for path in (taxonomy_path, cefr_path, grammar_topics_path, language_path):
        path.parent.mkdir(parents=True, exist_ok=True)

    taxonomy_path.write_text(
        yaml.safe_dump(taxonomy.model_dump(), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    cefr_path.write_text(
        yaml.safe_dump(cefr_hints.model_dump(), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    grammar_topics_path.write_text(
        yaml.safe_dump(
            [t.model_dump() for t in grammar_topics.topics], sort_keys=False, allow_unicode=True
        ),
        encoding="utf-8",
    )

    language_config = LanguageConfig(
        name=name,
        cefr_hints=cefr_name,
        taxonomy=taxonomy_name,
        grammar_topics=grammar_topics_name,
    )
    language_path.write_text(
        yaml.safe_dump(language_config.model_dump(exclude_none=True), sort_keys=False),
        encoding="utf-8",
    )

    _Registry(maps_dir=maps_dir, languages_dir=languages_dir)

    return {
        "taxonomy": taxonomy_path,
        "cefr_hints": cefr_path,
        "grammar_topics": grammar_topics_path,
        "language_config": language_path,
    }


def generate_language(
    name: str,
    llm: BaseLLM,
    level_range: tuple[str, str] = ("a1", "b2"),
    maps_dir: Path | None = None,
    languages_dir: Path | None = None,
) -> dict[str, Path]:
    """End-to-end: generates taxonomy, CEFR hints, and grammar topics for `name` via
    `llm`, then writes and validates all four asset files. Returns the written paths."""
    taxonomy = generate_taxonomy(llm, name)
    cefr_hints = generate_cefr_hints(llm, name, taxonomy)
    grammar_topics = generate_grammar_topics(llm, name, taxonomy, level_range)
    return write_language_assets(name, taxonomy, cefr_hints, grammar_topics, maps_dir, languages_dir)
