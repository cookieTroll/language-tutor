import pytest
from unittest.mock import MagicMock

from llm.base import BaseLLM, LLMResponse
from lang.models import CEFRMap, GrammarTopicsMap, TaxonomyMap
from lang.generate import (
    generate_taxonomy,
    generate_cefr_hints,
    generate_grammar_topics,
    write_language_assets,
)


def make_llm(responses: list[str]) -> MagicMock:
    llm = MagicMock(spec=BaseLLM)
    llm.config = MagicMock()
    llm.config.max_skill_retries = 3
    llm.complete.side_effect = [LLMResponse(text=t, model="test-model") for t in responses]
    return llm


TAXONOMY_YAML = """
tags:
  verb_conjugation: "Verb conjugation error"
  gender_agreement: "Noun/adjective gender agreement error"
  article: "Article error"
  word_order: "Word order error"
  spelling: "Spelling error"
  vocabulary: "Wrong word choice"
  other: "Error does not clearly fit any category above"
"""

TAXONOMY_MISSING_OTHER_YAML = """
tags:
  verb_conjugation: "Verb conjugation error"
"""

CEFR_HINTS_YAML = """
a1: "Focus on verb_conjugation, article, and spelling."
a2: "Focus on verb_conjugation, gender_agreement, and spelling."
b1: "Focus on gender_agreement, word_order, and verb_conjugation."
b2: "Focus on word_order, vocabulary, and gender_agreement."
c1: "Focus on vocabulary, register, and idiomatic usage."
c2: "Focus on register, stylistic nuance, and near-native correctness."
default: "Identify all grammatical, lexical, and spelling errors."
"""

CEFR_HINTS_MISSING_LEVEL_YAML = """
a1: "Focus on verb_conjugation."
a2: "Focus on gender_agreement."
b1: ""
b2: "Focus on word_order."
c1: "Focus on vocabulary."
c2: "Focus on register."
"""

GRAMMAR_TOPICS_BAD_TAG_YAML = """
- topic: "Present tense"
  difficulty: a1
  scope: major
  related_error_tags: ["verb_conjugation"]
- topic: "Made up topic"
  difficulty: a1
  scope: major
  related_error_tags: ["nonexistent_tag"]
"""

GRAMMAR_TOPICS_GOOD_YAML = """
- topic: "Present tense"
  difficulty: a1
  scope: major
  related_error_tags: ["verb_conjugation"]
  in_scope: ["regular verb endings"]
  out_of_scope: ["past tense"]
- topic: "Gender agreement"
  difficulty: a1
  scope: major
  related_error_tags: ["gender_agreement"]
"""


@pytest.fixture
def taxonomy() -> TaxonomyMap:
    return TaxonomyMap.model_validate({
        "tags": {
            "verb_conjugation": "Verb conjugation error",
            "gender_agreement": "Gender agreement error",
            "article": "Article error",
            "word_order": "Word order error",
            "spelling": "Spelling error",
            "vocabulary": "Wrong word choice",
            "other": "Catch-all",
        }
    })


@pytest.fixture
def lang_dirs(tmp_path):
    """Minimal on-disk skeleton write_language_assets' internal fresh _Registry
    needs to resolve a LanguageConfig's 'default' references for the three
    concepts write_language_assets doesn't generate itself."""
    maps_dir = tmp_path / "maps"
    languages_dir = tmp_path / "languages"
    for sub in ("cefr", "taxonomy", "cefr_descriptors", "writing_word_ranges", "grammar_topics", "exercise_types"):
        (maps_dir / sub).mkdir(parents=True)
    (maps_dir / "cefr_descriptors" / "default.yaml").write_text(
        'default: "Assess overall text complexity."\n', encoding="utf-8"
    )
    (maps_dir / "writing_word_ranges" / "default.yaml").write_text("b1: 100\n", encoding="utf-8")
    (maps_dir / "exercise_types" / "default.yaml").write_text("[]\n", encoding="utf-8")
    languages_dir.mkdir(parents=True)
    return maps_dir, languages_dir


class TestGenerateTaxonomy:
    def test_happy_path(self):
        llm = make_llm([TAXONOMY_YAML])
        result = generate_taxonomy(llm, "french")
        assert isinstance(result, TaxonomyMap)
        assert "other" in result.tags
        assert "verb_conjugation" in result.tags
        assert llm.complete.call_count == 1

    def test_retries_when_other_tag_missing(self):
        llm = make_llm([TAXONOMY_MISSING_OTHER_YAML, TAXONOMY_YAML])
        result = generate_taxonomy(llm, "french")
        assert "other" in result.tags
        assert llm.complete.call_count == 2


class TestGenerateCefrHints:
    def test_happy_path(self, taxonomy):
        llm = make_llm([CEFR_HINTS_YAML])
        result = generate_cefr_hints(llm, "french", taxonomy)
        assert isinstance(result, CEFRMap)
        assert result.a1 and result.b2 and result.c2

    def test_retries_when_level_missing(self, taxonomy):
        llm = make_llm([CEFR_HINTS_MISSING_LEVEL_YAML, CEFR_HINTS_YAML])
        result = generate_cefr_hints(llm, "french", taxonomy)
        assert result.b1
        assert llm.complete.call_count == 2


class TestGenerateGrammarTopics:
    def test_happy_path(self, taxonomy):
        llm = make_llm([GRAMMAR_TOPICS_GOOD_YAML])
        result = generate_grammar_topics(llm, "french", taxonomy, min_topics=2)
        assert isinstance(result, GrammarTopicsMap)
        assert len(result.topics) == 2

    def test_retries_on_unknown_error_tag(self, taxonomy):
        llm = make_llm([GRAMMAR_TOPICS_BAD_TAG_YAML, GRAMMAR_TOPICS_GOOD_YAML])
        result = generate_grammar_topics(llm, "french", taxonomy, min_topics=2)
        assert all(
            tag in taxonomy.tag_set
            for topic in result.topics
            for tag in topic.related_error_tags
        )
        assert llm.complete.call_count == 2

    def test_retries_when_below_min_topics(self, taxonomy):
        one_topic_yaml = """
- topic: "Present tense"
  difficulty: a1
  scope: major
  related_error_tags: ["verb_conjugation"]
"""
        llm = make_llm([one_topic_yaml, GRAMMAR_TOPICS_GOOD_YAML])
        result = generate_grammar_topics(llm, "french", taxonomy, min_topics=2)
        assert len(result.topics) == 2


class TestWriteLanguageAssets:
    def test_round_trips_through_fresh_registry(self, taxonomy, lang_dirs):
        maps_dir, languages_dir = lang_dirs
        cefr_hints = CEFRMap.model_validate(
            {
                "a1": "Focus on verb_conjugation.",
                "a2": "Focus on gender_agreement.",
                "b1": "Focus on word_order.",
                "b2": "Focus on vocabulary.",
                "c1": "Focus on register.",
                "c2": "Focus on nuance.",
                "default": "Identify all errors.",
            }
        )
        grammar_topics = GrammarTopicsMap(
            topics=[
                {
                    "topic": "Present tense",
                    "difficulty": "a1",
                    "scope": "major",
                    "related_error_tags": ["verb_conjugation"],
                },
                {
                    "topic": "Gender agreement",
                    "difficulty": "a1",
                    "scope": "major",
                    "related_error_tags": ["gender_agreement"],
                },
            ]
        )

        paths = write_language_assets(
            "french", taxonomy, cefr_hints, grammar_topics,
            maps_dir=maps_dir, languages_dir=languages_dir,
        )

        assert paths["taxonomy"].exists()
        assert paths["cefr_hints"].exists()
        assert paths["grammar_topics"].exists()
        assert paths["language_config"].exists()
        assert "french_taxonomy_v1" in paths["taxonomy"].name
        assert "french" == paths["language_config"].stem

    def test_raises_on_bad_cross_reference(self, lang_dirs):
        """A grammar topic tag not present in the written taxonomy must fail the
        end-to-end _Registry validation, same as it would for a hand-authored map."""
        maps_dir, languages_dir = lang_dirs
        bad_taxonomy = TaxonomyMap.model_validate({"tags": {"other": "Catch-all"}})
        cefr_hints = CEFRMap.model_validate({"default": "Identify all errors."})
        grammar_topics = GrammarTopicsMap(
            topics=[
                {
                    "topic": "Present tense",
                    "difficulty": "a1",
                    "scope": "major",
                    "related_error_tags": ["verb_conjugation"],  # not in bad_taxonomy
                }
            ]
        )

        with pytest.raises(ValueError):
            write_language_assets(
                "french", bad_taxonomy, cefr_hints, grammar_topics,
                maps_dir=maps_dir, languages_dir=languages_dir,
            )
