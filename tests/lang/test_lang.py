"""
Tests for lang/ — Pydantic models, YAML loading, registry validation, and public accessors.
Registry tests use tmp_path to avoid coupling to real YAML files.
"""
import pytest
import yaml
from pathlib import Path
from pydantic import ValidationError

from lang.models import CEFRMap, CEFRDescriptorMap, TaxonomyMap, TaxonomyError, LanguageConfig
from lang.loader import _Registry, get_cefr_context, get_taxonomy, get_cefr_descriptors, using_defaults


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_yaml(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(data), encoding="utf-8")


def _minimal_registry(tmp_path: Path) -> _Registry:
    """Registry with one configured language plus the required default fallback maps."""
    _write_yaml(tmp_path / "maps/cefr/map1.yaml", {
        "a1": "A1 hint.", "default": "Default CEFR."
    })
    _write_yaml(tmp_path / "maps/cefr/default.yaml", {
        "a1": "Generic A1.", "default": "Generic default."
    })
    _write_yaml(tmp_path / "maps/taxonomy/tax1.yaml", {
        "tags": {"verb_conjugation": "Verb form error.", "other": "Catch-all."}
    })
    _write_yaml(tmp_path / "maps/taxonomy/default.yaml", {
        "tags": {"grammar": "General grammar error.", "other": "Catch-all."}
    })
    _write_yaml(tmp_path / "maps/cefr_descriptors/default.yaml", {
        "a1": "Very basic phrases.", "b1": "Connected text.", "default": "Assess writing."
    })
    _write_yaml(tmp_path / "languages/testlang.yaml", {
        "name": "testlang", "cefr_hints": "map1", "taxonomy": "tax1"
    })
    return _Registry(maps_dir=tmp_path / "maps", languages_dir=tmp_path / "languages")


# ---------------------------------------------------------------------------
# CEFRMap model
# ---------------------------------------------------------------------------

class TestCEFRMap:

    def test_get_known_level(self):
        m = CEFRMap(a1="Focus on basics.", b1="Focus on cases.")
        assert m.get("a1") == "Focus on basics."
        assert m.get("B1") == "Focus on cases."  # case-insensitive

    def test_get_unknown_level_returns_default(self):
        m = CEFRMap(default="Fallback hint.")
        assert m.get("x9") == "Fallback hint."

    def test_get_empty_field_falls_back_to_default(self):
        m = CEFRMap(default="Default hint.")
        assert m.get("a1") == "Default hint."

    def test_default_provided_in_data(self):
        m = CEFRMap.model_validate({"a1": "A1 hint.", "default": "Custom default."})
        assert m.get("c2") == "Custom default."

    def test_rejects_non_string_field(self):
        with pytest.raises(ValidationError):
            CEFRMap.model_validate({"a1": 42})


# ---------------------------------------------------------------------------
# CEFRDescriptorMap model
# ---------------------------------------------------------------------------

class TestCEFRDescriptorMap:

    def test_format_for_prompt_includes_all_levels(self):
        m = CEFRDescriptorMap(
            a1="Very basic.", a2="Simple.", b1="Connected.", b2="Clear.",
            c1="Fluent.", c2="Near-native."
        )
        result = m.format_for_prompt()
        for level in ("A1", "A2", "B1", "B2", "C1", "C2"):
            assert level in result

    def test_format_for_prompt_skips_empty_levels(self):
        m = CEFRDescriptorMap(b1="Connected text.", default="Assess writing.")
        result = m.format_for_prompt()
        assert "B1" in result
        assert "A1" not in result  # empty — skipped

    def test_loads_from_yaml_dict(self):
        m = CEFRDescriptorMap.model_validate({
            "a1": "Very basic.", "default": "Assess writing."
        })
        assert m.a1 == "Very basic."
        assert m.default == "Assess writing."


# ---------------------------------------------------------------------------
# TaxonomyMap model
# ---------------------------------------------------------------------------

class TestTaxonomyMap:

    def _make(self, **extra_tags) -> TaxonomyMap:
        tags = {"other": "Catch-all.", **extra_tags}
        return TaxonomyMap(tags=tags)

    def test_validate_tag_known(self):
        t = self._make(verb_conjugation="Verb error.")
        assert t.validate_tag("verb_conjugation") == "verb_conjugation"

    def test_validate_tag_unknown_raises(self):
        t = self._make()
        with pytest.raises(TaxonomyError):
            t.validate_tag("nonexistent_tag")

    def test_other_always_valid(self):
        t = self._make()
        assert t.validate_tag("other") == "other"

    def test_missing_other_raises_on_construction(self):
        with pytest.raises(ValidationError, match="other"):
            TaxonomyMap(tags={"verb_conjugation": "Verb error."})

    def test_format_for_prompt_contains_all_tags(self):
        t = self._make(spelling="Spelling error.")
        prompt_text = t.format_for_prompt()
        assert "spelling" in prompt_text
        assert "Spelling error." in prompt_text
        assert "other" in prompt_text

    def test_tag_set_matches_tags_keys(self):
        t = self._make(article="Article error.")
        assert t.tag_set == {"other", "article"}

    def test_rejects_non_string_description(self):
        with pytest.raises(ValidationError):
            TaxonomyMap(tags={"other": 42})


# ---------------------------------------------------------------------------
# LanguageConfig model
# ---------------------------------------------------------------------------

class TestLanguageConfig:

    def test_valid_config(self):
        cfg = LanguageConfig.model_validate({
            "name": "german", "cefr_hints": "cefr_map1", "taxonomy": "german_taxonomy_v1"
        })
        assert cfg.name == "german"
        assert cfg.taxonomy == "german_taxonomy_v1"

    def test_missing_name_raises(self):
        with pytest.raises(ValidationError):
            LanguageConfig.model_validate({"cefr_hints": "map1", "taxonomy": "tax1"})

    def test_missing_cefr_hints_raises(self):
        with pytest.raises(ValidationError):
            LanguageConfig.model_validate({"name": "german", "taxonomy": "tax1"})

    def test_missing_taxonomy_raises(self):
        with pytest.raises(ValidationError):
            LanguageConfig.model_validate({"name": "german", "cefr_hints": "map1"})


# ---------------------------------------------------------------------------
# Registry — YAML loading and cross-validation (tmp_path)
# ---------------------------------------------------------------------------

class TestRegistry:

    def test_loads_cefr_and_resolves_context(self, tmp_path):
        reg = _minimal_registry(tmp_path)
        assert reg.get_cefr_context("testlang", "a1") == "A1 hint."

    def test_loads_taxonomy_and_returns_map(self, tmp_path):
        reg = _minimal_registry(tmp_path)
        tax = reg.get_taxonomy("testlang")
        assert tax is not None
        assert "verb_conjugation" in tax.tag_set
        assert "other" in tax.tag_set

    def test_unknown_language_cefr_falls_back_to_default_map(self, tmp_path):
        reg = _minimal_registry(tmp_path)
        result = reg.get_cefr_context("klingon", "a1")
        assert result == "Generic A1."

    def test_unknown_language_taxonomy_falls_back_to_default_map(self, tmp_path):
        reg = _minimal_registry(tmp_path)
        tax = reg.get_taxonomy("klingon")
        assert tax is not None
        assert "grammar" in tax.tag_set

    def test_is_default_returns_true_for_unknown_language(self, tmp_path):
        reg = _minimal_registry(tmp_path)
        flags = reg.is_default("klingon")
        assert flags["cefr_hints"] is True
        assert flags["taxonomy"] is True

    def test_is_default_returns_false_for_configured_language(self, tmp_path):
        reg = _minimal_registry(tmp_path)
        flags = reg.is_default("testlang")
        assert flags["cefr_hints"] is False
        assert flags["taxonomy"] is False

    def test_unknown_level_returns_map_default(self, tmp_path):
        reg = _minimal_registry(tmp_path)
        assert reg.get_cefr_context("testlang", "z9") == "Default CEFR."

    def test_bad_cefr_reference_raises_on_load(self, tmp_path):
        _write_yaml(tmp_path / "maps/cefr/map1.yaml", {"a1": "ok", "default": "ok"})
        _write_yaml(tmp_path / "maps/taxonomy/tax1.yaml", {
            "tags": {"other": "ok"}
        })
        _write_yaml(tmp_path / "languages/bad.yaml", {
            "name": "bad", "cefr_hints": "nonexistent", "taxonomy": "tax1"
        })
        with pytest.raises(ValueError, match="nonexistent"):
            _Registry(maps_dir=tmp_path / "maps", languages_dir=tmp_path / "languages")

    def test_bad_taxonomy_reference_raises_on_load(self, tmp_path):
        _write_yaml(tmp_path / "maps/cefr/map1.yaml", {"a1": "ok", "default": "ok"})
        _write_yaml(tmp_path / "maps/taxonomy", None)  # empty dir
        _write_yaml(tmp_path / "languages/bad.yaml", {
            "name": "bad", "cefr_hints": "map1", "taxonomy": "nonexistent"
        })
        with pytest.raises((ValueError, Exception)):
            _Registry(maps_dir=tmp_path / "maps", languages_dir=tmp_path / "languages")

    def test_invalid_cefr_yaml_raises_pydantic_error(self, tmp_path):
        _write_yaml(tmp_path / "maps/cefr/bad.yaml", {"a1": 999})  # int not allowed
        (tmp_path / "maps/taxonomy").mkdir(parents=True, exist_ok=True)
        (tmp_path / "languages").mkdir(parents=True, exist_ok=True)
        with pytest.raises(ValidationError):
            _Registry(maps_dir=tmp_path / "maps", languages_dir=tmp_path / "languages")

    def test_invalid_taxonomy_yaml_raises_pydantic_error(self, tmp_path):
        (tmp_path / "maps/cefr").mkdir(parents=True, exist_ok=True)
        _write_yaml(tmp_path / "maps/taxonomy/bad.yaml", {"tags": {"other": 999}})  # int not allowed
        (tmp_path / "languages").mkdir(parents=True, exist_ok=True)
        with pytest.raises(ValidationError):
            _Registry(maps_dir=tmp_path / "maps", languages_dir=tmp_path / "languages")

    def test_taxonomy_missing_other_raises(self, tmp_path):
        (tmp_path / "maps/cefr").mkdir(parents=True, exist_ok=True)
        _write_yaml(tmp_path / "maps/taxonomy/bad.yaml", {
            "tags": {"verb_conjugation": "Verb error."}  # no 'other'
        })
        (tmp_path / "languages").mkdir(parents=True, exist_ok=True)
        with pytest.raises(ValidationError, match="other"):
            _Registry(maps_dir=tmp_path / "maps", languages_dir=tmp_path / "languages")

    def test_invalid_language_yaml_raises_pydantic_error(self, tmp_path):
        _write_yaml(tmp_path / "maps/cefr/map1.yaml", {"a1": "ok", "default": "ok"})
        _write_yaml(tmp_path / "maps/taxonomy/tax1.yaml", {"tags": {"other": "ok"}})
        _write_yaml(tmp_path / "languages/bad.yaml", {"cefr_hints": "map1", "taxonomy": "tax1"})  # missing name
        with pytest.raises(ValidationError):
            _Registry(maps_dir=tmp_path / "maps", languages_dir=tmp_path / "languages")


# ---------------------------------------------------------------------------
# Integration — real YAML files (german + cefr_map1 + german_taxonomy_v1)
# ---------------------------------------------------------------------------

class TestIntegration:

    def test_german_b1_returns_expected_hint(self):
        result = get_cefr_context("german", "b1")
        assert "noun_declension" in result
        assert "verb_tense" in result

    def test_german_unknown_level_returns_default(self):
        result = get_cefr_context("german", "z9")
        assert result

    def test_unknown_language_cefr_falls_back_to_default_map(self):
        result = get_cefr_context("french", "a1")
        assert result  # non-empty — served by default map

    def test_german_taxonomy_has_required_tags(self):
        tax = get_taxonomy("german")
        assert tax is not None
        for tag in ("noun_declension", "verb_conjugation", "verb_tense", "spelling", "other"):
            assert tag in tax.tag_set

    def test_german_taxonomy_format_for_prompt_includes_descriptions(self):
        tax = get_taxonomy("german")
        assert tax is not None
        prompt_text = tax.format_for_prompt()
        assert "noun_declension" in prompt_text
        assert "other" in prompt_text

    def test_unknown_language_taxonomy_falls_back_to_default_map(self):
        tax = get_taxonomy("french")
        assert tax is not None
        assert "grammar" in tax.tag_set  # default map tags

    def test_german_using_defaults_returns_all_false(self):
        flags = using_defaults("german")
        assert flags["cefr_hints"] is False
        assert flags["taxonomy"] is False

    def test_unknown_language_using_defaults_returns_all_true(self):
        flags = using_defaults("french")
        assert flags["cefr_hints"] is True
        assert flags["taxonomy"] is True

    def test_german_cefr_descriptors_format_includes_all_levels(self):
        result = get_cefr_descriptors("german")
        for level in ("A1", "A2", "B1", "B2", "C1", "C2"):
            assert level in result

    def test_unknown_language_cefr_descriptors_falls_back_to_default(self):
        result = get_cefr_descriptors("french")
        assert result  # non-empty — served by default map
