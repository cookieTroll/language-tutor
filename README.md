# Wharf the Language Tutor

Wharf is a language learning tool built entirely around language output. It is a self-hosted, multi-agent AI language tutor that provides the deep, corrected-output feedback loop normally locked behind a subscription. It runs on your own API key or a fully local model, free or almost free either way: 60 sessions per month costs roughly €1, which is less than a single espresso.

**New here?** See [QUICK_START.md](QUICK_START.md) for the fastest path to a first session, in-session commands, and what to try.

## The Problem: A Personal Journey

This project was born out of a real-world struggle. After moving to Germany as a working professional with zero prior knowledge of German, I hit two massive roadblocks to achieving fluency:

1. **The Production Bottleneck:** Traditional language apps focus on passive recognition like flashcards or clicking pre-arranged words. But to learn fast, you need active production such as writing and speaking, paired with immediate, corrective feedback.
2. **The Flexibility and Cost Trap:** Private tutors are expensive, and group classes lock you into rigid schedules. Even in those settings, a teacher's bandwidth for grading essays and providing detailed, personalized feedback is limited.

Large Language Models (LLMs) are uniquely suited to language processing, offering a natural solution. However, getting feedback from raw LLM chats (like pasting sentences into ChatGPT or Claude) is cumbersome. It forces you to juggle several different environments (chat web apps for translation, separate note files for error tracking, and flashcard apps for vocabulary review) and lacks good persistence. With no historical memory of what you have practiced, no error tracking, and no adaptive routing, every session starts from scratch.

Wharf bridges this gap by providing a structured, multi-agent feedback loop that is persistent, adaptive, and runs on your own API key or a fully offline local model.

## Why Wharf? Key Differentiators

Unlike generic AI chats or commercial language apps, Wharf is built on four core pillars:

1. **Unified Competency Memory:** Instead of siloed exercises, progress is tracked globally. A mistake in writing automatically routes the student to a targeted grammar session on that topic.
2. **True Language Independence (Validation, Not Rewrite):** The architecture is entirely data-driven via YAML maps. Supporting a new target language or explanation language does not require code changes — only running the generator script and a native speaker spot-check (as validated with Czech).
3. **Structured Production Depth:** Moves past simple multiple-choice or sentence-reordering drills. Focuses on free-text writing evaluated by a 7-step pipeline (estimation, detection, verification, taxonomy classification, explanation, correction, summary).
4. **Extreme Cost Disruption:** Runs completely free and local on suitable hardware, or costs **roughly €1 per month** for a standard study load of 60 sessions (e.g., 2 sessions/day combining essay grading, grammar dumps, and drills) using hosted `gemini-2.5-flash` API keys. This eliminates standard monthly subscription paywalls (€10 to €30/month) for advanced tutoring features.

See [`docs/competitive_landscape.md`](docs/competitive_landscape.md) for a detailed comparison against named existing tools.

## What It Does

One tool, one login, one memory — writing and grammar share the same session history
and the same adaptive loop:

- **Writing practice** with a 7-step evaluator pipeline: detect, verify, classify,
  explain, correct, and summarise mistakes; each graded by severity against your
  CEFR level
- **Grammar sessions** routed to the exact error pattern recurring in your writing —
  not a fixed curriculum you follow in the same order as everyone else
- **Bidirectional bridge**: a recurring writing mistake triggers a grammar drill on
  that topic; mastering a grammar topic suggests a writing session that uses it
- **Progress tracking**: mastery ratio per module and a text-level trend over time,
  surfaced on demand via `/progress`
- **`/btw` inline questions**: ask about a word or phrase mid-session without leaving
  the writing flow; the answer is logged and flagged for vocab review
- **Language-asset generation**: adding a new target language is a single command —
  see [Language Generation](#language-generation)
- Both a **CLI** and a **browser UI** (Flask), same orchestrator logic underneath

## Architecture

Three grains with hard boundaries:

![Wharf — Three-Grain Architecture](docs/img/architecture.jpg)

**Skills (atomic grain):** A skill is a single, focused callable with a typed
input/output contract, a prompt template, and Pydantic-validated output. Skills are
pure — no storage access, no provider SDK knowledge. They receive input, call the LLM
via `BaseLLM`, and return structured output. All skills live under a shared top-level
`skills/` directory, not nested inside any one module.

**Modules (middle grain):** A module is an agent with a goal. It receives an injected
set of skills and a fulfilled `ModuleContext`, orchestrates them to complete a session,
and returns a `ModuleResult`. Modules are pure — no storage access.

**Orchestrator (top grain):** The only component that touches storage. Aggregates
session history, routes to the right module, fulfills the module's context request,
dispatches, and persists the result.

**Memory boundary is hard:** not a convention — enforced by design. All persistence
flows through one place. This makes modules and skills independently testable without
a storage backend.

**Self-correcting LLM output:** every skill that produces structured JSON delegates to
`call_with_self_correction` — failed Pydantic validation feeds the error back to the
LLM and retries, so contracts are load-bearing, not decorative.

See [`docs/_design.md`](docs/_design.md) for the full design rationale and
[`docs/_contracts.md`](docs/_contracts.md) for all protocol definitions.

## What's Built

| Layer | What it is | Status |
|---|---|---|
| PoC → 1a → 1b → 1c | Evaluator pipeline, routing, progress summary, CLI + web UI | ✅ done |
| 2a | Grammar module + bidirectional writing↔grammar bridge | ✅ done |
| 2b | On-demand writing history summary (`/history`) | ✅ done |
| 2c | Level & Progress — mastery view + text-level trend | ✅ done |
| 3d | MCP server — read-only tools over session/progress data | ✅ done |
| 3a / 3c | Vocab module, Anki export | cut — post-submission |

**Test suite:** 379 unit tests pass with no API key or network required —
`MockLLM` + isolated storage for the full run:

```bash
pytest tests/ -x -q --ignore=tests/judge --ignore=tests/e2e
```

A two-LLM judge tier (`tests/judge/`) evaluates semantic output quality per skill on
demand. The executor model was validated on this suite: `gemma2:9b` passed 12/12 on
`detect_mistakes`; `qwen2.5:7b` had 4 failures on the same suite — which is why the
local default is `gemma2:9b`, not a smaller model.

## Language Generation

Adding a new target language doesn't require hand-authoring content.
`scripts/generate_language.py` chains three self-correcting LLM calls — error
taxonomy → CEFR pedagogical hints → grammar topics — each validated through Pydantic
contracts and cross-checked against the registry. Czech
([`lang/languages/czech.yaml`](lang/languages/czech.yaml)) was generated this way and
spot-checked by a native speaker.

**Use a strong model for this.** Content-generation quality was noticeably better on
hosted `gemini-2.5-flash` than on the local `gemma2:9b` default — worth the hosted path
even if you otherwise run day-to-day study sessions locally. Both generation scripts
default to `config.yaml` (Gemini), so set `GEMINI_API_KEY` before running:

```bash
export GEMINI_API_KEY=your-key-here
python -m scripts.generate_language czech
```

See [`docs/lang_generation.md`](docs/lang_generation.md) for the generation pipeline
design.

## Quickstart

```bash
git clone https://github.com/cookieTroll/language-tutor && cd language-tutor
pip install -e .
export GEMINI_API_KEY=your-key-here    # get one free at ai.google.dev
python -m ui.app                       # web UI, http://localhost:5000 — or: python -m ui.cli
```

See [QUICK_START.md](QUICK_START.md) for in-session commands (`/progress`, `/history`,
`/btw`) and a suggested first walkthrough.

The default config (`config.yaml`) uses Gemini. Prefer to run fully free and local
instead? Check your hardware first — a dedicated GPU with **~6–8 GB VRAM** to run
`gemma2:9b` at usable speed; without it, generation will be painfully slow or hang the
machine. If you're set, run `python -m scripts.check_ollama_model` (one-time setup),
then set `LTUT_CONFIG=config.ollama.yaml` — see [PROVIDERS.md](PROVIDERS.md), which also
covers Vertex AI.

## Configuration & Providers

Switch provider with one env var — no code changes:

| Config file | Provider | Requires |
|---|---|---|
| `config.yaml` | Gemini (default) | `GEMINI_API_KEY` env var |
| `config.ollama.yaml` | Ollama (local, free, private) | Ollama + one-time model setup + **~6–8 GB VRAM GPU** |
| `config.vertex.yaml` | Vertex AI (ADC, no API key) | `GCP_PROJECT`, `gcloud auth application-default login` |

```bash
export LTUT_CONFIG=config.ollama.yaml   # switch to local Ollama
```

See [PROVIDERS.md](PROVIDERS.md) for full setup instructions per provider.

## Known Limitations

- **Validated scope:** A1–B2 German is the tested range. Czech has been generated and
  spot-checked but not yet fully exercised end-to-end through a live grammar session.
- **Cost (Gemini path):** A typical session (100-word essay evaluation or grammar topic dump + drill) costs a fraction of a cent on `gemini-2.5-flash`. A full study monthly load of 60 sessions (2 sessions/day) runs **roughly €1 per month**. The prompt context (system prompts and taxonomy details) represents the bulk of the cost, making pricing highly flat and predictable. Furthermore, as a local library of generated lessons and exercises is gradually compiled, subsequent study sessions on those cached topics bypass the LLM entirely, reducing upkeep costs even further.
- **Local path requirements:** Running locally requires suitable hardware (a dedicated GPU with ~6–8 GB VRAM to run models like `gemma2:9b` or `qwen2.5:7b` at acceptable speeds). Offline execution is completely free, but local models represent the lower end of grading and pedagogical accuracy compared to hosted commercial models.
- **Recurrence check is session-scoped:** the writing↔grammar bridge fires when an
  error tag recurs within a session's accumulated errors, not across an aggregate of all
  sessions. Cross-session aggregate memory is a planned improvement.
- **No auth layer:** storage is per `data_root` directory; multi-user is profile-keyed
  within that root. Suitable for local single-user or self-hosted use — not a
  public-facing deployment without an added auth layer.

## MCP Server

**Purpose:** let another agent or assistant tool pull your learning stats and history
straight out of Wharf's storage — "what's my mastery ratio in German grammar" or "export
my last 10 writing sessions" — without opening the app itself. `ui/mcp_server.py` exposes
the `memory/` storage layer (plus static `lang/maps/` reference data) as MCP tools for
progress stats, session history, vocab flags, and writing-session export. It's read-only
— no LLM calls, no writes, so none of the tutoring features themselves (grading,
grammar generation, `/btw`) are exposed this way, only the stats/history/taxonomy data
listed below.

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

Google's equivalent — [Gemini CLI](https://github.com/google-gemini/gemini-cli) — uses
the same `mcpServers` shape in `~/.gemini/settings.json` (or a project-local
`.gemini/settings.json`):

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

## Repository Structure

```
language-tutor/
├── docs/                   # design docs, per-module specs, testing/lang architecture
├── lang/                   # versioned content maps + language-asset generation
│   ├── models.py           # Pydantic models: CEFRMap, TaxonomyMap, LanguageConfig, MessageCatalog
│   ├── loader.py           # _Registry: loads + cross-validates maps at startup
│   ├── generate.py         # language-asset generation subsystem
│   ├── maps/               # {name}.yaml versioned content: cefr/, taxonomy/, grammar_topics/, ...
│   ├── languages/          # {language}.yaml — maps language → cefr_hints + taxonomy
│   └── messages/           # {language}.yaml — backend UI text, resolved by explanation_language
├── shared/                 # SessionTimer, IOHandler protocol, error_log, humanize, slugify
├── llm/                    # BaseLLM + one file per provider (gemini, vertex, openai_compat, ollama_setup)
├── orchestrator/           # OrchestratorProtocol, SessionManager, mastery — the only grain touching storage
├── modules/
│   ├── writing/            # WritingModule — 7-step evaluator pipeline
│   └── grammar/            # GrammarModule — theory, exercises, grading, writing↔grammar bridge
├── skills/                 # one folder per atomic skill (detect_mistakes, dump_grammar, ...)
├── memory/                 # StorageProtocol, SQLite/JSON store implementations, schema.sql
├── data/                   # gitignored — sessions/, summaries/, checkpoints/
├── ui/
│   ├── cli.py              # CLI frontend
│   ├── app.py              # Flask web frontend
│   └── mcp_server.py       # read-only MCP server over StorageProtocol
├── scripts/                # standalone admin CLIs: check_ollama_model, generate_language, generate_messages
├── tests/                  # unit/, e2e/, judge/ (LLM-as-judge), fixtures/
├── config.yaml, config.gemini.yaml, config.vertex.yaml, config.ollama.yaml, config.test.yaml
└── Modelfile               # custom Ollama model definition (FROM gemma2:9b)
```

See [`docs/_design.md`](docs/_design.md#repository-structure) for the fully annotated tree
(every file, per-line purpose).

* [`QUICK_START.md`](QUICK_START.md) — First-session walkthrough and CLI command reference.
* [`docs/_design.md`](docs/_design.md) — Architecture overview, three-grain design, key decisions.
* [`docs/_layers.md`](docs/_layers.md) — Deliverable manifest per release layer.
* [`docs/_contracts.md`](docs/_contracts.md) — All protocol and dataclass definitions.
* [`docs/lang.md`](docs/lang.md) — Language architecture: versioned content maps, registry, cross-validation.
* [`docs/lang_generation.md`](docs/lang_generation.md) — Language-asset generation pipeline.
* [`docs/testing.md`](docs/testing.md) — Three-tier test architecture (unit / LLM-judge / regression).
* [`docs/competitive_landscape.md`](docs/competitive_landscape.md) — Comparison against existing tools.
* [`PROVIDERS.md`](PROVIDERS.md) — LLM provider setup, API key management, config selection.

### Source Code

* [`llm/base.py`](llm/base.py) — `BaseLLM` abstract class + `LLMMessage`, `LLMResponse`.
* [`skills/protocols.py`](skills/protocols.py) — Atomic skill contracts.
* [`modules/protocols.py`](modules/protocols.py) — Module contracts (`ModuleProtocol`, `ModuleContext`, `ModuleResult`).
* [`memory/protocols.py`](memory/protocols.py) — Storage contracts and data models.
* [`orchestrator/orchestrator.py`](orchestrator/orchestrator.py) — Top-level agent.
* [`ui/mcp_server.py`](ui/mcp_server.py) — Read-only MCP server over session/progress data.
