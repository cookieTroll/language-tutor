# LanguageTutor AI Agent

LanguageTutor is an AI-powered language tutoring agent focused on personalized **output and writing** practice. It tracks session history, identifies recurring grammatical and vocabulary errors, and routes users to adaptive exercises.

## Quickstart

```bash
git clone <repo-url> && cd language-tutor
pip install -e .
python -m scripts.check_ollama_model   # first run only: pulls/creates the local Ollama model
python -m ui.cli                       # or: python -m ui.app  (web UI, http://localhost:5000)
```

The default config (`config.yaml`) uses a local Ollama model — see
[PROVIDERS.md](PROVIDERS.md) to switch to Gemini or Vertex AI instead.

## Repository Structure

* [docs/_design.md](docs/_design.md) — Human-facing architectural overview.
* [docs/_layers.md](docs/_layers.md) — Deliverable manifest per release layer.
* [docs/_CHECKLIST.md](docs/_CHECKLIST.md) — Implementation task list.
* [docs/_TODO.md](docs/_TODO.md) — Known risks, backlog, and deferred design items.
* [docs/_contracts.md](docs/_contracts.md) — Original interface and protocol specifications.
* [docs/lang.md](docs/lang.md) — Language architecture: versioned content maps, registry, cross-validation.
* [docs/ui.md](docs/ui.md) — UI layer: Flask routes, the `IOHandler` CLI/web split, static JS.
* [PROVIDERS.md](PROVIDERS.md) — LLM provider setup, API key management, config selection.

### Source Code

* [llm/base.py](llm/base.py) — LLM client wrapper protocol.
* [skills/protocols.py](skills/protocols.py) — Atomic skill contracts.
* [modules/protocols.py](modules/protocols.py) — Middle-grain agent/module contracts.
* [memory/protocols.py](memory/protocols.py) — Data models and storage contracts.
* [ui/mcp_server.py](ui/mcp_server.py) — Read-only MCP server over session/progress data.

## MCP Server

`ui/mcp_server.py` exposes the `memory/` storage layer (plus static `lang/maps/`
reference data) as MCP tools for progress stats, session history, vocab flags,
and writing-session export. It's read-only — no LLM calls, no writes.

**Tools:** `list_users`, `list_languages`, `get_progress`, `list_sessions`,
`get_session`, `get_recurring_errors`, `get_vocab_flags`,
`export_writing_history`, `get_error_taxonomy`, `get_grammar_topic_list`.

### Run it

```bash
pip install -e .   # installs the `mcp` package and everything else the app needs
python ui/mcp_server.py
```

The server speaks MCP over stdio and expects to be launched as a subprocess
by an MCP client (Claude Desktop, Claude Code, etc.), not run standalone in a
terminal. It reads `config.yaml` from the repo root by default; set
`LTUT_CONFIG=/path/to/config.yaml` to point at a different config (e.g.
`config.test.yaml` for the isolated test data root).

To add it to Claude Desktop, add an entry to its MCP server config:

```json
{
  "mcpServers": {
    "language-tutor": {
      "command": "python",
      "args": ["/absolute/path/to/language-tutor/ui/mcp_server.py"]
    }
  }
}
```

### Test it

```bash
pytest tests/unit/test_mcp_server.py -v
```

Tests seed an isolated SQLite store (via a temp `data_root`) and call the
tool functions directly — no client/transport involved.
