"""Read-only MCP server over the language-tutor memory layer.

Exposes progress stats, session history, vocab flags, and writing-session
export as MCP tools — no LLM calls, no writes. Run with:

    python ui/mcp_server.py

or point an MCP client (Claude Desktop, Claude Code) at this file via stdio.
Config resolution matches ui/app.py: set LTUT_CONFIG to override config.yaml.
"""
import os
import sys
from datetime import datetime, timedelta

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import yaml
from mcp.server.fastmcp import FastMCP

from config import load_config
from memory.factory import build_storage
from memory.protocols import StorageProtocol
from lang.loader import get_taxonomy, get_grammar_topics

config_path = os.environ.get("LTUT_CONFIG", os.path.join(project_root, "config.yaml"))
_config = load_config(config_path)
_store: StorageProtocol = build_storage(_config)

mcp = FastMCP("language-tutor")


def _resolve_language(user_id: str, language: str | None) -> str:
    if language:
        return language.lower()
    active = _store.get_active_language(user_id)
    if not active:
        known = _store.get_user_languages(user_id)
        raise ValueError(
            f"No active language for user '{user_id}'. Pass `language` explicitly. "
            f"Known languages for this user: {known or 'none'}."
        )
    return active


def _read_session_file(file_path: str) -> dict:
    """Read a session YAML file, refusing any path that escapes data_root."""
    data_root_abs = os.path.abspath(_config.data_root)
    abs_path = os.path.abspath(os.path.join(_config.data_root, file_path))
    if not abs_path.startswith(data_root_abs + os.sep):
        raise ValueError("Refusing to read a path outside data_root.")
    if not os.path.isfile(abs_path):
        raise ValueError(f"Session file not found: {file_path}")
    with open(abs_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


@mcp.tool()
def list_users() -> list[str]:
    """List all known user IDs that have at least one language profile."""
    return _store.list_users()


@mcp.tool()
def list_languages(user_id: str) -> list[str]:
    """List languages the given user has a profile for."""
    return _store.get_user_languages(user_id)


@mcp.tool()
def get_progress(user_id: str, language: str | None = None) -> dict:
    """Progress snapshot for a user: sessions per module, days since last session
    per module, total time per module, recurring error tags, recent writing
    topics, vocab flag count, and current CEFR level. `language` defaults to the
    user's active language."""
    lang = _resolve_language(user_id, language)
    agg = _store.get_session_aggregate(user_id, lang)
    profile = _store.get_user_profile(user_id, lang)
    return {
        "user_id": user_id,
        "language": lang,
        "level": profile.level if profile else _store.get_current_level(user_id),
        "level_source": profile.level_source if profile else None,
        **agg.model_dump(),
    }


@mcp.tool()
def list_sessions(
    user_id: str,
    language: str | None = None,
    module: str | None = None,
    n: int = 10,
) -> list[dict]:
    """List recent sessions for a user, most recent first. Filter by module
    (e.g. 'writing', 'grammar') or cap the count with `n`."""
    lang = _resolve_language(user_id, language)
    sessions = (
        _store.get_sessions_by_module(user_id, lang, module)
        if module
        else _store.get_recent_sessions(user_id, lang, n=n)
    )
    if module:
        sessions = sessions[:n]
    return [
        {
            "session_id": s.session_id,
            "date": s.date.isoformat(),
            "module": s.module,
            "task_label": s.task_label,
            "level": s.level,
            "status": s.status,
            "duration_minutes": s.duration_minutes,
            "text_level_estimate": s.text_level_estimate,
        }
        for s in sessions
    ]


@mcp.tool()
def get_session(user_id: str, session_id: str) -> dict:
    """Full content of one session file — mistakes, corrected text, score, tips,
    exercises, etc. depending on module."""
    log = _store.get_session_by_id(session_id)
    if not log or log.user_id != user_id:
        raise ValueError(f"No session '{session_id}' found for user '{user_id}'.")
    return _read_session_file(log.file_path)


@mcp.tool()
def get_recurring_errors(
    user_id: str, language: str | None = None, module: str | None = None
) -> dict[str, int]:
    """Error tag -> occurrence count across a user's sessions. Pair with
    get_error_taxonomy to turn tags into human-readable descriptions."""
    lang = _resolve_language(user_id, language)
    return _store.get_error_frequency(user_id, lang, module)


@mcp.tool()
def get_vocab_flags(user_id: str, language: str | None = None) -> list[dict]:
    """Words flagged during sessions (via /btw, the evaluator, or manual add),
    with translation and how often each has recurred."""
    lang = _resolve_language(user_id, language)
    flags = _store.get_vocab_flags(user_id, lang)
    return [
        {
            "word": f.word,
            "translation": f.translation,
            "source": f.source,
            "occurrence_count": f.occurrence_count,
            "first_seen": f.first_seen.isoformat(),
            "last_seen": f.last_seen.isoformat(),
        }
        for f in flags
    ]


@mcp.tool()
def export_writing_history(
    user_id: str,
    language: str | None = None,
    n: int | None = None,
    days: int | None = None,
) -> str:
    """Compile completed writing sessions (topic, date, your text, corrected
    text, tips) into one text blob, most recent first. Filter by session count
    (`n`) or a day window (`days`); with neither, returns all completed writing
    sessions. Returns the text directly — save it yourself if you want a file."""
    lang = _resolve_language(user_id, language)
    logs = [l for l in _store.get_sessions_by_module(user_id, lang, "writing") if l.status == "completed"]

    if days is not None:
        cutoff = datetime.now() - timedelta(days=days)
        logs = [l for l in logs if l.date >= cutoff]
    if n is not None:
        logs = logs[:n]

    if not logs:
        return "No completed writing sessions found."

    blocks = []
    for log in logs:
        content = _read_session_file(log.file_path)
        tips = content.get("tips") or []
        blocks.append(
            f"=== {content.get('date', log.date.isoformat())} — {content.get('topic', log.task_label)} "
            f"({(content.get('level') or log.level).upper()}) ===\n\n"
            f"Your text:\n{content.get('user_text', '')}\n\n"
            f"Corrected:\n{content.get('corrected_text', '')}\n\n"
            f"Tips: {'; '.join(tips)}"
        )
    return "\n\n".join(blocks)


@mcp.tool()
def get_error_taxonomy(language: str) -> dict[str, str]:
    """Error tag -> human-readable description for this language, for
    interpreting the tags returned by get_recurring_errors."""
    taxonomy = get_taxonomy(language)
    return taxonomy.tags if taxonomy else {}


@mcp.tool()
def get_grammar_topic_list(language: str) -> list[dict]:
    """Curated grammar topics for this language: topic name, CEFR difficulty,
    and which error tags each topic addresses. Cross-reference against
    get_recurring_errors to suggest what to practise next."""
    topics_map = get_grammar_topics(language)
    if not topics_map:
        return []
    return [
        {
            "topic": t.topic,
            "difficulty": t.difficulty,
            "related_error_tags": t.related_error_tags,
        }
        for t in topics_map.topics
    ]


if __name__ == "__main__":
    mcp.run()
