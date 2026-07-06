import yaml
import pytest
from unittest.mock import MagicMock

from llm.base import BaseLLM, LLMResponse
from lang.models import MessageCatalog, REQUIRED_MESSAGE_IDS
from lang.generate_messages import generate_message_catalog, write_message_catalog


def make_llm(responses: list[str]) -> MagicMock:
    llm = MagicMock(spec=BaseLLM)
    llm.config = MagicMock()
    llm.config.max_skill_retries = 3
    llm.complete.side_effect = [LLMResponse(text=t, model="test-model") for t in responses]
    return llm


# One id carries a placeholder so placeholder-preservation can be exercised;
# every other id is a plain string — REQUIRED_MESSAGE_IDS must all be present
# for MessageCatalog's own validator to accept either the source or a "translation".
DEFAULT_MESSAGES = {msg_id: f"<{msg_id}>" for msg_id in REQUIRED_MESSAGE_IDS}
DEFAULT_MESSAGES["confirm_level_display"] = "Your current CEFR level: {level}"


def _translated_yaml(**overrides) -> str:
    """A 'translation' response: every id present (prefixed 'ES:'), with any
    override applied on top — used to simulate a good or bad LLM response."""
    translated = {msg_id: f"ES: {text}" for msg_id, text in DEFAULT_MESSAGES.items()}
    translated.update(overrides)
    return yaml.safe_dump({"messages": translated}, sort_keys=False, allow_unicode=True)


@pytest.fixture
def messages_dir(tmp_path):
    d = tmp_path / "messages"
    d.mkdir()
    (d / "default.yaml").write_text(
        yaml.safe_dump({"language": "default", "messages": DEFAULT_MESSAGES}, sort_keys=False),
        encoding="utf-8",
    )
    return d


class TestGenerateMessageCatalog:
    def test_happy_path_preserves_placeholders(self, messages_dir):
        good = _translated_yaml(confirm_level_display="ES: Su nivel CEFR actual: {level}")
        llm = make_llm([good])
        result = generate_message_catalog(llm, "spanish", messages_dir=messages_dir)
        assert isinstance(result, MessageCatalog)
        assert result.get("confirm_level_display", level="B1") == "ES: Su nivel CEFR actual: B1"
        assert llm.complete.call_count == 1

    def test_retries_when_placeholder_dropped(self, messages_dir):
        bad = _translated_yaml(confirm_level_display="ES: Su nivel CEFR actual.")  # dropped {level}
        good = _translated_yaml(confirm_level_display="ES: Su nivel CEFR actual: {level}")
        llm = make_llm([bad, good])
        result = generate_message_catalog(llm, "spanish", messages_dir=messages_dir)
        assert "{level}" in result.messages["confirm_level_display"]
        assert llm.complete.call_count == 2

    def test_gives_up_after_max_retries_on_persistent_mismatch(self, messages_dir):
        bad = _translated_yaml(confirm_level_display="ES: Su nivel CEFR actual.")
        llm = make_llm([bad, bad, bad])
        with pytest.raises(Exception):
            generate_message_catalog(llm, "spanish", messages_dir=messages_dir)


class TestWriteMessageCatalog:
    def test_round_trips_through_reparse(self, messages_dir):
        messages = {msg_id: f"ES: {text}" for msg_id, text in DEFAULT_MESSAGES.items()}
        catalog = MessageCatalog.model_validate({"language": "spanish", "messages": messages})
        path = write_message_catalog("spanish", catalog, messages_dir=messages_dir)
        assert path.exists()
        reloaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert reloaded["language"] == "spanish"
        assert reloaded["messages"]["confirm_level_display"] == "ES: Your current CEFR level: {level}"
