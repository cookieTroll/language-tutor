from typing import Literal

from pydantic import BaseModel, field_validator, model_validator


class CEFRMap(BaseModel):
    """Pedagogical focus hints per CEFR level.

    Loaded from lang/maps/cefr/*.yaml.
    Hint strings reference error tags defined in the language's TaxonomyMap.
    """

    a1: str = ""
    a2: str = ""
    b1: str = ""
    b2: str = ""
    c1: str = ""
    c2: str = ""
    default: str = "Identify all grammatical, lexical, and spelling errors."

    def get(self, level: str) -> str:
        val = getattr(self, level.lower(), None)
        return val if val else self.default


class TaxonomyError(ValueError):
    """Raised when an error tag is not present in the language's TaxonomyMap."""


class TaxonomyMap(BaseModel):
    """Error classification taxonomy — maps tag names to human-readable descriptions.

    Loaded from lang/maps/taxonomy/*.yaml.
    Descriptions are used verbatim in classifier prompts, so write them as
    concise English phrases a language model can act on.
    'other' must always be present as the catch-all tag.
    """

    tags: dict[str, str]  # tag_name → description

    @model_validator(mode="after")
    def other_must_be_present(self) -> "TaxonomyMap":
        if "other" not in self.tags:
            raise ValueError("TaxonomyMap must include 'other' as a catch-all tag.")
        return self

    def validate_tag(self, tag: str) -> str:
        if tag not in self.tags:
            raise TaxonomyError(
                f"Unknown error_tag: '{tag}'. Must be one of {sorted(self.tags)}"
            )
        return tag

    def format_for_prompt(self) -> str:
        """Format tags with descriptions for inclusion in classifier prompts."""
        return "\n".join(f"  - {tag}: {desc}" for tag, desc in self.tags.items())

    @property
    def tag_set(self) -> frozenset[str]:
        return frozenset(self.tags.keys())


class CEFRDescriptorMap(BaseModel):
    """CEFR level descriptions for text-level estimation.

    Loaded from lang/maps/cefr_descriptors/*.yaml.
    Descriptions characterise what writing at each level looks like — used by
    estimate_text_level to ground the LLM's assessment. The default map is
    language-agnostic (CEFR is an international standard); language-specific
    files can override for additional nuance.
    """

    a1: str = ""
    a2: str = ""
    b1: str = ""
    b2: str = ""
    c1: str = ""
    c2: str = ""
    default: str = "Assess overall text complexity, vocabulary range, grammatical accuracy, and coherence."

    def format_for_prompt(self) -> str:
        """Format all levels as a reference table for prompt injection."""
        lines = []
        for level in ("a1", "a2", "b1", "b2", "c1", "c2"):
            desc = getattr(self, level, "")
            if desc:
                lines.append(f"  {level.upper()}: {desc}")
        return "\n".join(lines)


class WritingMinWordsMap(BaseModel):
    """Minimum word count per CEFR level for writing sessions.

    Loaded from lang/maps/writing_word_ranges/*.yaml.
    Each field is the minimum word count expected at that level.
    """

    a1: int = 40
    a2: int = 60
    b1: int = 100
    b2: int = 150
    c1: int = 200
    c2: int = 250

    def get(self, level: str) -> int:
        return getattr(self, level.lower(), self.b1)


class GrammarTopic(BaseModel):
    """A single curated grammar topic entry.

    scope: 'major' — from the curated syllabus list.
           'minor' — reserved for topics select_grammar proposes on the fly;
           never appears in a loaded map, only in skill output.
    """

    topic: str
    difficulty: str
    scope: Literal["major", "minor"]
    related_error_tags: list[str]

    @field_validator("difficulty")
    @classmethod
    def validate_difficulty(cls, v: str) -> str:
        valid_levels = {"a1", "a2", "b1", "b2", "c1", "c2"}
        if v.lower() not in valid_levels:
            raise ValueError(f"Invalid CEFR difficulty: '{v}'. Allowed: {valid_levels}")
        return v.lower()


class GrammarTopicsMap(BaseModel):
    """Curated major grammar topics — the syllabus backbone for select_grammar.

    Loaded from lang/maps/grammar_topics/*.yaml (a flat YAML list at the file root).
    related_error_tags on each topic are cross-validated against the language's
    TaxonomyMap at load time — see lang/loader.py.
    """

    topics: list[GrammarTopic]


class ExerciseType(BaseModel):
    """A single exercise type vocabulary entry for generate_exercises.

    grading is fixed per type — never chosen by the LLM — so the skill derives
    each generated exercise's grading mode from this map instead of trusting
    a self-reported field.
    """

    type: str
    grading: Literal["exact", "llm"]
    description: str


class ExerciseTypesMap(BaseModel):
    """Exercise type vocabulary for generate_exercises.

    Loaded from lang/maps/exercise_types/*.yaml (a flat YAML list at the file root).
    Pedagogically universal (not tied to a specific target language), but kept in
    the same per-language-resolved map pattern as taxonomy/cefr_hints so a future
    language could override the mix without touching skill code.
    """

    types: list[ExerciseType]

    @property
    def type_names(self) -> frozenset[str]:
        return frozenset(t.type for t in self.types)

    def grading_for(self, exercise_type: str) -> str | None:
        for t in self.types:
            if t.type == exercise_type:
                return t.grading
        return None

    def format_for_prompt(self) -> str:
        """Format types with grading mode and description for the generator prompt."""
        return "\n".join(f"  - {t.type} ({t.grading}): {t.description.strip()}" for t in self.types)


class LanguageConfig(BaseModel):
    """Top-level language config — maps learning concepts to versioned content maps.

    Loaded from lang/languages/*.yaml.
    Each string field is a map name resolved against the corresponding maps/ subfolder.
    To upgrade content for a concept, change the map name here — no Python changes needed.
    """

    name: str
    cefr_hints: str              # → lang/maps/cefr/{cefr_hints}.yaml
    taxonomy: str                # → lang/maps/taxonomy/{taxonomy}.yaml
    cefr_descriptors: str = "default"  # → lang/maps/cefr_descriptors/{cefr_descriptors}.yaml
    writing_word_ranges: str = "default"  # → lang/maps/writing_word_ranges/{name}.yaml
    grammar_topics: str | None = None  # → lang/maps/grammar_topics/{grammar_topics}.yaml; no map yet if unset
    exercise_types: str = "default"  # → lang/maps/exercise_types/{exercise_types}.yaml
