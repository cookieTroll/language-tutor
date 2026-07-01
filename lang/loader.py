from __future__ import annotations

from pathlib import Path

import yaml

from lang.models import (
    CEFRDescriptorMap,
    CEFRMap,
    ExerciseTypesMap,
    GrammarTopicsMap,
    LanguageConfig,
    TaxonomyMap,
    WritingMinWordsMap,
)

_LANG_DIR = Path(__file__).parent
_MAPS_DIR = _LANG_DIR / "maps"
_LANGUAGES_DIR = _LANG_DIR / "languages"


class _Registry:
    """Loads and cross-validates all language configs and their referenced maps at startup."""

    def __init__(
        self,
        maps_dir: Path | None = None,
        languages_dir: Path | None = None,
    ) -> None:
        self._maps_dir = maps_dir or _MAPS_DIR
        self._languages_dir = languages_dir or _LANGUAGES_DIR
        self._cefr_maps: dict[str, CEFRMap] = {}
        self._taxonomy_maps: dict[str, TaxonomyMap] = {}
        self._cefr_descriptor_maps: dict[str, CEFRDescriptorMap] = {}
        self._writing_min_words_maps: dict[str, WritingMinWordsMap] = {}
        self._grammar_topics_maps: dict[str, GrammarTopicsMap] = {}
        self._exercise_types_maps: dict[str, ExerciseTypesMap] = {}
        self._languages: dict[str, LanguageConfig] = {}
        self._load()

    def _load(self) -> None:
        for path in (self._maps_dir / "cefr").glob("*.yaml"):
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            self._cefr_maps[path.stem] = CEFRMap.model_validate(data)

        for path in (self._maps_dir / "taxonomy").glob("*.yaml"):
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            self._taxonomy_maps[path.stem] = TaxonomyMap.model_validate(data)

        for path in (self._maps_dir / "cefr_descriptors").glob("*.yaml"):
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            self._cefr_descriptor_maps[path.stem] = CEFRDescriptorMap.model_validate(data)

        for path in (self._maps_dir / "writing_word_ranges").glob("*.yaml"):
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            self._writing_min_words_maps[path.stem] = WritingMinWordsMap.model_validate(data)

        grammar_topics_dir = self._maps_dir / "grammar_topics"
        if grammar_topics_dir.exists():
            for path in grammar_topics_dir.glob("*.yaml"):
                data = yaml.safe_load(path.read_text(encoding="utf-8"))
                self._grammar_topics_maps[path.stem] = GrammarTopicsMap(topics=data or [])

        for path in (self._maps_dir / "exercise_types").glob("*.yaml"):
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            self._exercise_types_maps[path.stem] = ExerciseTypesMap(types=data or [])

        for path in self._languages_dir.glob("*.yaml"):
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            config = LanguageConfig.model_validate(data)
            self._validate_references(config)
            self._languages[config.name.lower()] = config

    def _validate_references(self, config: LanguageConfig) -> None:
        if config.cefr_hints not in self._cefr_maps:
            raise ValueError(
                f"Language '{config.name}' references unknown cefr_hints map "
                f"'{config.cefr_hints}'. Available: {sorted(self._cefr_maps)}"
            )
        if config.taxonomy not in self._taxonomy_maps:
            raise ValueError(
                f"Language '{config.name}' references unknown taxonomy map "
                f"'{config.taxonomy}'. Available: {sorted(self._taxonomy_maps)}"
            )
        if config.cefr_descriptors not in self._cefr_descriptor_maps:
            raise ValueError(
                f"Language '{config.name}' references unknown cefr_descriptors map "
                f"'{config.cefr_descriptors}'. Available: {sorted(self._cefr_descriptor_maps)}"
            )
        if config.writing_word_ranges not in self._writing_min_words_maps:
            raise ValueError(
                f"Language '{config.name}' references unknown writing_word_ranges map "
                f"'{config.writing_word_ranges}'. Available: {sorted(self._writing_min_words_maps)}"
            )
        if config.exercise_types not in self._exercise_types_maps:
            raise ValueError(
                f"Language '{config.name}' references unknown exercise_types map "
                f"'{config.exercise_types}'. Available: {sorted(self._exercise_types_maps)}"
            )
        if config.grammar_topics is not None:
            grammar_topics_map = self._grammar_topics_maps.get(config.grammar_topics)
            if grammar_topics_map is None:
                raise ValueError(
                    f"Language '{config.name}' references unknown grammar_topics map "
                    f"'{config.grammar_topics}'. Available: {sorted(self._grammar_topics_maps)}"
                )
            taxonomy_map = self._taxonomy_maps.get(config.taxonomy)
            if taxonomy_map is not None:
                for topic in grammar_topics_map.topics:
                    for tag in topic.related_error_tags:
                        if tag not in taxonomy_map.tag_set:
                            raise ValueError(
                                f"Grammar topic '{topic.topic}' for language '{config.name}' "
                                f"references unknown error tag '{tag}'. "
                                f"Must be one of {sorted(taxonomy_map.tag_set)}"
                            )

    def is_default(self, language: str) -> dict[str, bool]:
        """Return which maps are falling back to defaults for the given language."""
        config = self._languages.get(language.lower())
        if config is None:
            return {"cefr_hints": True, "taxonomy": True}
        return {
            "cefr_hints": config.cefr_hints == "default",
            "taxonomy": config.taxonomy == "default",
        }

    def get_cefr_context(self, language: str, level: str) -> str:
        config = self._languages.get(language.lower())
        map_name = config.cefr_hints if config else "default"
        cefr_map = self._cefr_maps.get(map_name) or self._cefr_maps.get("default")
        if cefr_map is None:
            return f"Identify errors appropriate to a {level.upper()} learner."
        return cefr_map.get(level)

    def get_taxonomy(self, language: str) -> TaxonomyMap | None:
        config = self._languages.get(language.lower())
        map_name = config.taxonomy if config else "default"
        return self._taxonomy_maps.get(map_name) or self._taxonomy_maps.get("default")

    def get_writing_min_words(self, language: str, level: str) -> int:
        config = self._languages.get(language.lower())
        map_name = config.writing_word_ranges if config else "default"
        wmap = (
            self._writing_min_words_maps.get(map_name)
            or self._writing_min_words_maps.get("default")
        )
        if wmap is None:
            return 100
        return wmap.get(level)

    def get_grammar_topics(self, language: str) -> GrammarTopicsMap | None:
        config = self._languages.get(language.lower())
        if config is None or config.grammar_topics is None:
            return None
        return self._grammar_topics_maps.get(config.grammar_topics)

    def get_exercise_types(self, language: str) -> ExerciseTypesMap | None:
        config = self._languages.get(language.lower())
        map_name = config.exercise_types if config else "default"
        return self._exercise_types_maps.get(map_name) or self._exercise_types_maps.get("default")

    def get_cefr_descriptors(self, language: str) -> str:
        config = self._languages.get(language.lower())
        map_name = config.cefr_descriptors if config else "default"
        descriptor_map = (
            self._cefr_descriptor_maps.get(map_name)
            or self._cefr_descriptor_maps.get("default")
        )
        if descriptor_map is None:
            return ""
        return descriptor_map.format_for_prompt()


_registry = _Registry()


def get_cefr_context(language: str, level: str) -> str:
    """Return a pedagogical focus hint for the given language and CEFR level."""
    return _registry.get_cefr_context(language, level)


def get_taxonomy(language: str) -> TaxonomyMap | None:
    """Return the TaxonomyMap for the given language, falling back to the default map."""
    return _registry.get_taxonomy(language)


def get_grammar_topics(language: str) -> GrammarTopicsMap | None:
    """Return the curated GrammarTopicsMap for the given language, or None if unconfigured."""
    return _registry.get_grammar_topics(language)


def get_exercise_types(language: str) -> ExerciseTypesMap | None:
    """Return the ExerciseTypesMap for the given language, falling back to the default map."""
    return _registry.get_exercise_types(language)


def get_cefr_descriptors(language: str) -> str:
    """Return formatted CEFR level descriptions for the given language, for prompt injection."""
    return _registry.get_cefr_descriptors(language)


def get_writing_min_words(language: str, level: str) -> int:
    """Return the minimum word count for a writing session at the given CEFR level."""
    return _registry.get_writing_min_words(language, level)


def using_defaults(language: str) -> dict[str, bool]:
    """Return which maps are falling back to defaults for the given language.

    Used at session start to prompt the user if language content is not configured.
    Example: {"cefr_hints": False, "taxonomy": True} means taxonomy is using the generic default.
    """
    return _registry.is_default(language)
