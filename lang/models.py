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

    in_scope / out_of_scope: optional explicit boundary points for topics whose
    name alone is ambiguous (e.g. two Präteritum entries split by which verbs
    they cover). dump_grammar and generate_exercises are two independent LLM
    calls given only the topic string — without this, one could explain
    regular verbs while the other tests irregular ones. Empty by default;
    only populated where the topic name's qualifier clause needs reinforcing.
    """

    topic: str
    difficulty: str
    scope: Literal["major", "minor"]
    related_error_tags: list[str]
    in_scope: list[str] = []
    out_of_scope: list[str] = []

    @field_validator("difficulty")
    @classmethod
    def validate_difficulty(cls, v: str) -> str:
        valid_levels = {"a1", "a2", "b1", "b2", "c1", "c2"}
        if v.lower() not in valid_levels:
            raise ValueError(f"Invalid CEFR difficulty: '{v}'. Allowed: {valid_levels}")
        return v.lower()

    def format_scope_for_prompt(self) -> str:
        """Empty string if no explicit scope was authored — callers fall back to
        a generic instruction (see dump_grammar/generate_exercises prompts)."""
        if not self.in_scope and not self.out_of_scope:
            return ""
        lines = ["Scope constraint for this topic — stay within these boundaries:"]
        if self.in_scope:
            lines.append("In scope: " + "; ".join(self.in_scope))
        if self.out_of_scope:
            lines.append("Out of scope (do NOT cover or test this): " + "; ".join(self.out_of_scope))
        return "\n".join(lines)


class GrammarTopicsMap(BaseModel):
    """Curated major grammar topics — the syllabus backbone for select_grammar.

    Loaded from lang/maps/grammar_topics/*.yaml (a flat YAML list at the file root).
    related_error_tags on each topic are cross-validated against the language's
    TaxonomyMap at load time — see lang/loader.py.
    """

    topics: list[GrammarTopic]

    def scope_for(self, topic: str) -> GrammarTopic | None:
        """Exact, case-insensitive match — mirrors resolve_manual_topic's lookup
        in skills/select_grammar/skill.py. Returns None for ad hoc/minor topics
        not in the curated list, which simply have no scope constraint to enforce."""
        for t in self.topics:
            if t.topic.strip().casefold() == topic.strip().casefold():
                return t
        return None


class ExerciseType(BaseModel):
    """A single exercise type vocabulary entry for generate_exercises.

    grading is fixed per type — never chosen by the LLM — so the skill derives
    each generated exercise's grading mode from this map instead of trusting
    a self-reported field.
    """

    type: str
    grading: Literal["exact", "llm"]
    description: str
    student_instruction: str


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

    def instruction_for(self, exercise_type: str) -> str | None:
        for t in self.types:
            if t.type == exercise_type:
                return t.student_instruction
        return None

    def format_for_prompt(self) -> str:
        """Format types with grading mode and description for the generator prompt."""
        return "\n".join(f"  - {t.type} ({t.grading}): {t.description.strip()}" for t in self.types)

    def describe_one(self, exercise_type: str) -> str | None:
        """Same one-line format as format_for_prompt, for a single pre-chosen type —
        used when the caller (not the LLM) has already picked the exercise type."""
        for t in self.types:
            if t.type == exercise_type:
                return f"  - {t.type} ({t.grading}): {t.description.strip()}"
        return None


REQUIRED_MESSAGE_IDS = frozenset({
    "interruption_banner",
    "interruption_choice_prompt",
    "interruption_resume_unavailable",
    "interruption_invalid_choice",
    "session_interrupted_keyboard",
    "next_action_prompt_first",
    "next_action_prompt_other",
    "confirm_level_display",
    "confirm_level_prompt",
    "confirm_explanation_language_display",
    "confirm_explanation_language_prompt",
    "active_language_status",
    "active_language_switch_prompt",
    "ask_target_language",
    "ask_level",
    "ask_explanation_language_new",
    "recommendation_display",
    "history_hint_block",
    "module_choice_prompt",
    "invalid_module_fallback",
    "language_command_current",
    "language_command_no_profile",
    "language_command_updated",
    "history_invalid_arg",
    "history_no_sessions",
    "history_could_not_generate",
    "history_report_header",
    "level_up_prompt",
    "level_up_confirmed",
})


class MessageCatalog(BaseModel):
    """Backend UI strings (menus, prompts, confirmations) — id-keyed, resolved by
    the user's explanation_language, not the target study language.

    Loaded from lang/messages/*.yaml. Distinct from the six map types above: those
    are LLM-facing content resolved per target language via LanguageConfig; this is
    orchestrator-facing display text resolved directly by language name, with
    lang/messages/default.yaml as the universal English fallback.

    Each value is a str.format() template; placeholders are filled by the caller
    (orchestrator.py), never by the catalog itself.
    """

    language: str
    messages: dict[str, str]

    @model_validator(mode="after")
    def all_required_ids_present(self) -> "MessageCatalog":
        missing = REQUIRED_MESSAGE_IDS - self.messages.keys()
        if missing:
            raise ValueError(
                f"MessageCatalog for '{self.language}' is missing required message id(s): "
                f"{sorted(missing)}"
            )
        return self

    def get(self, msg_id: str, **kwargs) -> str:
        template = self.messages.get(msg_id)
        if template is None:
            raise KeyError(f"Unknown message id: '{msg_id}'")
        return template.format(**kwargs) if kwargs else template


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
