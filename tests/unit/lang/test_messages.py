"""
Tests for the message catalog — MessageCatalog model, registry loading, and
the get_messages/is_message_catalog_configured public accessors.
Registry tests use tmp_path to avoid coupling to the real lang/messages/ files.
"""
import pytest
import yaml
from pathlib import Path
from pydantic import ValidationError

from lang.models import MessageCatalog, REQUIRED_MESSAGE_IDS
from lang.loader import _Registry


def _write_yaml(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(data), encoding="utf-8")


def _all_ids_catalog(language: str = "default", **overrides) -> dict:
    """A minimal but complete messages dict — every required id present, filled
    with a placeholder value unless overridden."""
    messages = {msg_id: f"<{msg_id}>" for msg_id in REQUIRED_MESSAGE_IDS}
    messages.update(overrides)
    return {"language": language, "messages": messages}


def _minimal_registry(tmp_path: Path, extra_languages: dict[str, dict] | None = None) -> _Registry:
    """Registry with only the message-catalog side wired up — the six map types
    aren't needed for these tests, so their directories are left empty."""
    _write_yaml(tmp_path / "messages/default.yaml", _all_ids_catalog("default"))
    for language, overrides in (extra_languages or {}).items():
        _write_yaml(tmp_path / f"messages/{language}.yaml", _all_ids_catalog(language, **overrides))
    (tmp_path / "maps").mkdir(parents=True, exist_ok=True)
    (tmp_path / "languages").mkdir(parents=True, exist_ok=True)
    return _Registry(
        maps_dir=tmp_path / "maps", languages_dir=tmp_path / "languages", messages_dir=tmp_path / "messages",
    )


# ---------------------------------------------------------------------------
# MessageCatalog model
# ---------------------------------------------------------------------------

class TestMessageCatalog:

    def test_valid_catalog_with_all_ids(self):
        catalog = MessageCatalog.model_validate(_all_ids_catalog())
        assert catalog.language == "default"

    def test_missing_required_id_raises(self):
        data = _all_ids_catalog()
        del data["messages"][next(iter(REQUIRED_MESSAGE_IDS))]
        with pytest.raises(ValidationError, match="missing required message id"):
            MessageCatalog.model_validate(data)

    def test_get_formats_placeholder(self):
        catalog = MessageCatalog.model_validate(
            _all_ids_catalog(confirm_level_display="Level: {level}")
        )
        assert catalog.get("confirm_level_display", level="B1") == "Level: B1"

    def test_get_without_kwargs_returns_template_as_is(self):
        catalog = MessageCatalog.model_validate(
            _all_ids_catalog(interruption_choice_prompt="Choice [l/d]: ")
        )
        assert catalog.get("interruption_choice_prompt") == "Choice [l/d]: "

    def test_get_unknown_id_raises_key_error(self):
        catalog = MessageCatalog.model_validate(_all_ids_catalog())
        with pytest.raises(KeyError):
            catalog.get("not_a_real_message_id")

    def test_extra_ids_are_allowed(self):
        catalog = MessageCatalog.model_validate(
            _all_ids_catalog(some_future_id="future text")
        )
        assert catalog.get("some_future_id") == "future text"


# ---------------------------------------------------------------------------
# Registry — YAML loading and public accessors (tmp_path)
# ---------------------------------------------------------------------------

class TestRegistryMessages:

    def test_get_messages_falls_back_to_default_for_unconfigured_language(self, tmp_path):
        reg = _minimal_registry(tmp_path)
        catalog = reg.get_messages("spanish")
        assert catalog.language == "default"

    def test_get_messages_resolves_configured_language(self, tmp_path):
        reg = _minimal_registry(tmp_path, extra_languages={
            "spanish": {"confirm_level_display": "Nivel: {level}"}
        })
        catalog = reg.get_messages("spanish")
        assert catalog.language == "spanish"
        assert catalog.get("confirm_level_display", level="B1") == "Nivel: B1"

    def test_get_messages_is_case_insensitive(self, tmp_path):
        reg = _minimal_registry(tmp_path, extra_languages={"spanish": {}})
        assert reg.get_messages("SPANISH").language == "spanish"

    def test_is_message_catalog_configured_false_for_unconfigured(self, tmp_path):
        reg = _minimal_registry(tmp_path)
        assert reg.is_message_catalog_configured("spanish") is False

    def test_is_message_catalog_configured_false_for_default_itself(self, tmp_path):
        reg = _minimal_registry(tmp_path)
        assert reg.is_message_catalog_configured("default") is False

    def test_is_message_catalog_configured_true_once_generated(self, tmp_path):
        reg = _minimal_registry(tmp_path, extra_languages={"spanish": {}})
        assert reg.is_message_catalog_configured("spanish") is True

    def test_missing_required_id_raises_on_load(self, tmp_path):
        data = _all_ids_catalog("default")
        del data["messages"][next(iter(REQUIRED_MESSAGE_IDS))]
        _write_yaml(tmp_path / "messages/default.yaml", data)
        (tmp_path / "maps").mkdir(parents=True, exist_ok=True)
        (tmp_path / "languages").mkdir(parents=True, exist_ok=True)
        with pytest.raises(ValidationError, match="missing required message id"):
            _Registry(
                maps_dir=tmp_path / "maps", languages_dir=tmp_path / "languages",
                messages_dir=tmp_path / "messages",
            )


# ---------------------------------------------------------------------------
# Integration — real lang/messages/default.yaml
# ---------------------------------------------------------------------------

class TestIntegration:

    def test_default_catalog_loads_and_has_all_required_ids(self):
        from lang.loader import get_messages
        catalog = get_messages("english")
        assert catalog.language == "default"
        assert REQUIRED_MESSAGE_IDS <= catalog.messages.keys()

    def test_unconfigured_language_falls_back_to_default(self):
        from lang.loader import get_messages, is_message_catalog_configured
        assert is_message_catalog_configured("klingon") is False
        catalog = get_messages("klingon")
        assert catalog.language == "default"
