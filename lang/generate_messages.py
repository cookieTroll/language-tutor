"""Generates a target language's message catalog (backend UI text: menus, prompts,
confirmations) via LLM translation of lang/messages/default.yaml, validated through
the same MessageCatalog contract lang/loader.py already applies to English.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from lang.models import MessageCatalog
from llm.base import BaseLLM, LLMMessage
from skills.protocols import call_with_self_correction

_LANG_DIR = Path(__file__).parent
_MESSAGES_DIR = _LANG_DIR / "messages"
_DEFAULT_CATALOG_PATH = _MESSAGES_DIR / "default.yaml"

_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")

MESSAGE_CATALOG_PROMPT = """You are translating a language-learning app's backend UI \
text (menus, prompts, confirmations shown to the learner) into {language}.

Below is the English source catalog as id: template pairs. Translate every template's \
text into {language}, naturally and concisely, matching the tone of the English original.

CRITICAL: every "{{placeholder}}" token (curly braces and the name inside, exactly as \
written) MUST appear in your translation, verbatim, unchanged and untranslated — these \
are filled in by code afterward. Do not translate, rename, drop, or add any placeholder. \
Do not add new ids and do not omit any id below.

English source (YAML id: template pairs):
{source_yaml}

Output ONLY raw YAML (no markdown fences, no commentary) in exactly this shape — a \
"messages" map with the SAME ids as above, values translated into {language}:

messages:
  some_id: "translated template with {{placeholder}} preserved exactly"
  another_id: "..."
"""


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:yaml|yml)?\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return text.strip()


def _placeholders(template: str) -> frozenset[str]:
    return frozenset(_PLACEHOLDER_RE.findall(template))


def _load_default_messages(messages_dir: Path | None = None) -> dict[str, str]:
    path = (messages_dir or _MESSAGES_DIR) / "default.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data["messages"]


def generate_message_catalog(
    llm: BaseLLM, language: str, messages_dir: Path | None = None,
) -> MessageCatalog:
    """Generates a MessageCatalog for `language` by translating every template in
    lang/messages/default.yaml. Id completeness is checked by MessageCatalog's own
    validator; placeholder preservation is checked here — a dropped or mistranslated
    {placeholder} would KeyError at runtime, not at generation time, without it."""
    default_messages = _load_default_messages(messages_dir)
    source_yaml = yaml.safe_dump({"messages": default_messages}, sort_keys=False, allow_unicode=True)

    def parse(text: str) -> MessageCatalog:
        data = yaml.safe_load(_strip_fences(text))
        catalog = MessageCatalog.model_validate({"language": language, **(data or {})})
        for msg_id, template in catalog.messages.items():
            expected = _placeholders(default_messages.get(msg_id, ""))
            actual = _placeholders(template)
            if actual != expected:
                raise ValueError(
                    f"Message '{msg_id}' placeholder mismatch: expected {sorted(expected)}, "
                    f"got {sorted(actual)}"
                )
        return catalog

    prompt = MESSAGE_CATALOG_PROMPT.format(language=language, source_yaml=source_yaml)
    messages = [LLMMessage(role="user", content=prompt)]
    return call_with_self_correction(llm, messages, parse, temperature=0.3)


def write_message_catalog(
    language: str, catalog: MessageCatalog, messages_dir: Path | None = None,
) -> Path:
    """Writes lang/messages/{language}.yaml and re-validates by re-parsing the
    written file through MessageCatalog — no cross-file references to check here
    (unlike lang/generate.py's write_language_assets), so a reparse is sufficient."""
    messages_dir = messages_dir or _MESSAGES_DIR
    messages_dir.mkdir(parents=True, exist_ok=True)
    path = messages_dir / f"{language.lower()}.yaml"

    path.write_text(
        yaml.safe_dump(catalog.model_dump(), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    MessageCatalog.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))

    return path
