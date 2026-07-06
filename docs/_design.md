# Wharf the Language Tutor — Design Document

## Overview

Wharf the Language Tutor is a single, unified tool for practicing a language — one login, one
shared memory of what you've practiced and where you're weak, across every language competency
rather than a separate app per skill. Its core is **output**: writing practice drives the loop,
because producing the language builds fluency faster than passive recognition does. Grammar
directly complements writing today — a recurring writing mistake can trigger a grammar session
on that exact point, and a mastered grammar topic can trigger a writing session that uses it.
Reading (with comprehension), listening, and speaking are planned as further competencies under
the same tool, deferred to post-submission (see Roadmap below).

The primary pitch: **one tool, a personalized feedback loop that spans every competency**.
Existing language tools tend toward one of two gaps (see `docs/competitive_landscape.md` for a
detailed comparison): rigid drill generators that don't focus on producing the language, or
tools with genuine output feedback sitting behind a subscription paywall. Here the only real
cost is running the LLM itself — free if run locally (Ollama), or a few cents a session on a
hosted model provider.

This doesn't replace supervised learning — a human teacher still catches things and builds
rapport a model can't. But it complements one in ways a teacher's own capacity structurally
can't: feedback is instant and practically impossible to saturate (a teacher's time and
attention are a shared, finite resource split across a whole class; this tool's isn't), and
practice is available whenever and wherever the learner is, not scheduled around a lesson slot.
Data is stored locally by default; the storage layer (`memory/`) is designed to generalize to a
hosted/cloud backend without touching any other part of the app, when that's ever needed.

This agent learns which competencies you've neglected, what errors recur, and routes you
accordingly — and it's built to keep growing into further competencies rather than stay a
single-exercise tool.

Detailed specs for each component live in `docs/`. This document is the human-facing,
policy-level overview.

---

## Goals & Non-Goals

### Goals
- One unified tool across language competencies — writing and grammar today; vocab management,
  reading, listening, and speaking planned — sharing one login, one memory, one session model
- Output-first: writing is the core driver skill; grammar directly complements it via a
  bidirectional bridge (recurring writing mistake → grammar session; mastered grammar topic →
  writing session using it)
- Route the learner to whichever competency needs attention next, based on their own session
  history — not a fixed curriculum everyone follows in the same order
- Writing-focused feedback with error annotation
- Grammar instruction and practice
- Catch the words a learner struggles with automatically during a session — from `/btw`
  questions and mistakes the evaluator flags — and feed them into a vocab-management engine, so
  nobody has to curate their own weak-word list by hand; drilling itself stays with Anki (see
  Non-Goals), not rebuilt here
- Every new target language needs its own language-specific content — error taxonomy, CEFR
  guidance, grammar topics, and more — and hand-authoring all of that per language doesn't
  scale, so the project includes a built-in tool to help generate it
- True multi-language support — independent progress profiles per user per language
- Personalization carries over automatically between sessions — what's been practiced, what
  keeps recurring — scoped independently per user and per language
- Explicit, testable contracts between every component, so behavior stays predictable as the
  tool grows into more competencies
- Run on whichever LLM backend fits the learner's situation — free and private on a local
  model, or a hosted provider for less setup — without changing any other code
- `/btw` inline question command, available during the writing session today — unifies the
  tool by surfacing translation/grammar help without leaving the current flow
- Session clock with a visible timer (CLI and web) — deliberately simulates timed test/exam
  conditions, not just a UX nicety
- Both a CLI and a browser frontend available today — same underlying logic either way, so
  nothing behaves differently depending on which one you use

### Non-Goals (for this submission)
- Building an in-house vocabulary drill/spaced-repetition engine — Anki already solves this
  well; Wharf manages the vocab list and exports to it instead of reinventing that loop
- Real-time audio/video infrastructure

### Roadmap (planned, explicitly deferred post-submission — none of these are fully scoped yet)
1. **Vocab management** — the negative vocab list already exists; what's planned next is the
   management surface and Anki export
2. **Reading**, with comprehension checks
3. **Listening**
4. **Speaking / pronunciation**

---

## Delivery Layers

**Shipped (pre-submission):**

| Layer | Scope |
|-------|-------|
| **PoC** | Contracts + storage abstraction + orchestrator skeleton (cold start) + writing module: hardcoded topic + raw mistake detector + session file write + CLI + `lang/` content maps |
| **1a** | Full writing evaluator pipeline — 7 steps: estimate level, detect/verify/classify mistakes, explain, correct, summarise |
| **1b** | Topic picker + session history aggregation + orchestrator LLM routing + progress summary |
| **1c** | `IOHandler` protocol + both frontends: CLI (`ui/cli.py`) and browser (`ui/app.py`, Flask) |
| **2a** | Grammar module — theory, exercises, grading — plus the bidirectional writing↔grammar bridge |
| **2b** | On-demand writing history summary (`/history` command) |
| **2c** | Level & Progress — per-module mastery ratio plus a text-level trend, surfaced together on demand (`/progress`) |
| **3d** | MCP Server — read-only tools over session/progress data |

See Goals & Non-Goals above for the post-submission roadmap (vocab management, reading,
listening, speaking, in priority order) — not repeated here to avoid drift between two copies.
`docs/_CHECKLIST.md` carries the tactical, line-item backlog for both shipped and roadmap work
— this table states what a layer *is*, the checklist tracks what's actually left to do.

---

## Three-Grain Architecture

The system is organised into three levels of granularity. Each grain has a clear responsibility and a clean boundary with the others.

```
┌──────────────────────────────────────────────────────────┐
│                       ORCHESTRATOR                        │
│  Single top-level agent                                   │
│  - Owns memory access (only component touching storage)   │
│  - Reads session logs, aggregates progress profile        │
│  - Routes to module (cold start or LLM recommendation)    │
│  - Fulfills module's ContextRequest from storage          │
│  - Persists all results post-session                      │
└───────────────────────────┬──────────────────────────────┘
                            │ dispatches to
              ┌─────────────┴─────────────┐
              ▼                           ▼
       [Writing Module]            [Grammar Module]
```

**Writing** composes the 7-step evaluator pipeline — `estimate_text_level` + `detect_mistakes`
in parallel → `verify_mistakes` → `classify_mistakes` → `explain_mistakes` → `write_correction`
+ `summarise_writing_session` in parallel — plus `topic_picker`/`summarize_progress` (Layer 1b)
and the `btw_handler` utility skill (writing only today, see Goals & Non-Goals).

**Grammar** composes `select_grammar` (or a manual topic entry that bypasses it) → `dump_grammar`
→ a repeatable round of `generate_exercises` → `grade_exercises`.

Planned modules — **vocab management**, **reading**, **listening**, **speaking** — aren't
built yet and compose no skills today; see Goals & Non-Goals and Delivery Layers above.

### Grain 1 — Skills (atomic, lowest grain)

A skill is a single, focused callable unit. It has:
- A fixed input/output contract
- A prompt template
- A `skill_type`: `session` (full lifecycle, run by module) or `utility` (invoked inline, no session file)
- A `skill.md` as its authoritative spec

Skills are pure — no storage access, no LLM provider knowledge. They receive input, call the LLM via `LLMProtocol`, return structured output. Nothing else.

Skills are also a **shared, project-wide asset pool**, not owned by any one module. They live
under a single top-level `skills/` directory rather than nested inside `modules/writing/` or
`modules/grammar/`; a module's own `skills.py` just injects whichever subset it needs. Nothing
in a skill's contract ties it to one module — `btw_handler` is a good example: today only
`modules/writing/skills.py` injects it (see Goals & Non-Goals), but that's a module-level
wiring choice, not a property of the skill itself.

Each skill lives in its own folder under `skills/`:
```
skills/
├── estimate_text_level/    # Step 1 — session skill (implemented) — runs in parallel with Step 2
│   └── prompts.py
├── detect_mistakes/        # Step 2 — session skill (implemented) — gate: pipeline short-circuits on failure
│   └── prompts.py
├── verify_mistakes/        # Step 3 — session skill (implemented) — re-checks raw fragments against
│   │                       # sentence context and drops false positives before classification
│   └── prompts.py
├── classify_mistakes/      # Step 4 — session skill (implemented)
│   └── prompts.py
├── explain_mistakes/       # Step 5 — session skill (implemented)
│   └── prompts.py
├── write_correction/       # Step 6 — session skill (implemented) — runs in parallel with Step 7
│   └── prompts.py
├── summarise_session/      # Step 7 — session skill (Layer 1a) — runs in parallel with Step 6;
│   └── writing/            # module-specific variant (SummariseWritingSessionSkill) lives under
│       └── prompts.py      # summarise_session/writing/, invoked as "summarise_writing_session"
├── btw_handler/            # utility skill — invoked mid-session, no session file (implemented)
│   └── prompts.py
├── topic_picker/           # session skill (Layer 1b)
├── summarize_progress/     # session skill (Layer 1b)
├── summarize_writing_history/ # session skill (Layer 2b) — powers the on-demand `/history` command
├── cefr_estimator/         # session skill (Layer 2c "Level & Progress")
├── select_grammar/         # session skill (Layer 2a)
├── dump_grammar/           # session skill (Layer 2a)
├── generate_exercises/     # session skill (Layer 2a)
└── grade_exercises/        # session skill (Layer 2a) — batched grading + feedback
```

No `drill_vocab` skill is planned (see Goals & Non-Goals).

### Grain 2 — Modules (agents, middle grain)

A module is an agent with a goal. It receives a set of skills (injected at startup via `skills.py`), and orchestrates them to complete a session. The module decides which skills to invoke, in what order, and how to handle branching (e.g. topic picker bypassed if user provides own topic).

Each module lives in its own folder under `modules/`. There is no `module.md` spec file per module — `agent.py` and `skills.py` are the authoritative reference:
```
modules/
├── writing/
│   ├── agent.py            # ModuleProtocol implementation
│   ├── skills.py           # skill instantiation and injection
│   └── pipeline.py         # WritingPipeline — sequences the 7-skill evaluator pipeline
└── grammar/                # agent.py, skills.py — grammar module + writing↔grammar bridge
```

Planned, not built: vocab management, reading, listening, speaking — see Delivery Layers above.

Modules are pure — no storage access. They receive `ModuleContext` (fulfilled by orchestrator from storage), run their skills, return `ModuleResult` + `SessionFileContent`.

### Grain 3 — Orchestrator (top grain)

Single top-level agent. The only component that touches storage. Responsibilities:
- Load module registry at startup
- Check for interrupted sessions (resume/log/discard)
- Aggregate session history into progress profile
- Route to correct module (cold start default or LLM recommendation)
- Fulfill module's `ContextRequest` via storage
- Dispatch to module, receive result
- Persist result: write file (atomic), update DB, write btw log, write vocab flags
- Delete checkpoint on completion

See `docs/orchestrator.md` for full detail.

---

## Memory Boundary

**Only the orchestrator touches storage.** Modules and skills are pure — they receive context in, return results out. This is a hard boundary, not a convention. It makes modules and skills independently testable without a storage backend, and keeps all persistence logic in one place.

Storage is infrastructure shared across all grains. It lives in `memory/` alongside `llm/`, separate from the grain hierarchy.

---

## LLM Abstraction

All LLM calls go through `LLMProtocol`. No skill, module, or orchestrator calls a provider SDK directly.

- `llm/base.py` — abstract base class (`BaseLLM`) defining the interface
- `llm/gemini.py` — `GeminiLLM` (production default)
- `llm/vertex.py` — `VertexAILLM` (Vertex AI via ADC, no API key)
- `llm/openai_compat.py` — `OpenAICompatibleLLM` (OpenAI API + LM Studio local)
- `llm/ollama_setup.py` — `ensure_ollama_ready()`, auto-starts Ollama and pulls the model if missing
- `llm/factory.py` — `build_llm(config)` factory

LLM instance injected at startup into orchestrator and modules. Unit tests use a mock.

See `docs/llm_backends.md` for full detail.

---

## Repository Structure

```
language-tutor/
├── docs/
│   ├── _design.md          # this file
│   ├── _layers.md          # flat layer manifest
│   ├── _CHECKLIST.md       # implementation checklist with submission schedule
│   ├── _TODO.md            # deferred decisions and known risks
│   ├── _contracts.md       # all protocols and dataclasses
│   ├── memory.md           # storage, schema, session files, interruption
│   ├── orchestrator.md     # orchestrator logic, cold start, prompts, aggregation
│   ├── testing.md          # three-tier testing architecture
│   ├── llm_backends.md     # LLM abstraction, implementations, config
│   ├── writing.md          # writing module + evaluator pipeline spec
│   ├── grammar.md          # grammar module + skills spec (Layer 2a)
│   ├── vocab.md            # vocab spec — not implemented, see Goals & Non-Goals/Roadmap
│   ├── ui.md               # UI layer: Flask routes, IOHandler CLI/web split, static JS
│   ├── lang.md             # lang/ architecture: versioned content maps, registry
│   ├── lang_generation.md  # lang/generate.py — language-asset generation subsystem
│   └── competitive_landscape.md # how the writing evaluator compares to existing tools
│
├── lang/                   # versioned content maps + language-asset generation (see docs/lang.md)
│   ├── models.py           # Pydantic models: CEFRMap, TaxonomyMap, LanguageConfig, MessageCatalog
│   ├── loader.py           # _Registry: loads + cross-validates maps at startup
│   ├── generate.py         # language-asset generation subsystem — see docs/lang.md
│   ├── generate_prompts.py # prompt templates for generate.py — see docs/lang.md
│   ├── generate_messages.py # message-catalog generation — see docs/lang_generation.md
│   ├── maps/
│   │   ├── cefr/                   # {name}.yaml — versioned CEFR pedagogical hint maps
│   │   ├── taxonomy/               # {name}.yaml — versioned error taxonomy maps
│   │   ├── cefr_descriptors/       # {name}.yaml — versioned CEFR level-descriptor maps
│   │   ├── exercise_types/         # {name}.yaml — grammar exercise type vocabulary (Layer 2a)
│   │   ├── grammar_topics/         # {name}.yaml — versioned grammar topic maps (Layer 2a)
│   │   └── writing_word_ranges/    # {name}.yaml — per-level minimum word counts for writing
│   ├── languages/          # {language}.yaml — maps language → cefr_hints + taxonomy
│   └── messages/           # {language}.yaml — id-keyed backend UI text, resolved by
│                           #   explanation_language (not the target language) — see docs/lang.md
│
├── shared/
│   ├── timer.py            # SessionTimer — background thread, updates terminal title
│   ├── io.py               # IOHandler protocol — decouples module/orchestrator I/O from CLI/web
│   ├── error_log.py        # log_skill_error() — structured skill-failure logging
│   ├── humanize.py         # humanizes error tags / internal identifiers for display
│   └── slugify.py          # slug generation for filenames/ids
│
├── llm/
│   ├── base.py             # BaseLLM abstract class
│   ├── factory.py          # build_llm(config) → BaseLLM
│   ├── gemini.py           # GeminiLLM (production default)
│   ├── vertex.py           # VertexAILLM (Vertex AI via ADC)
│   ├── openai_compat.py    # OpenAICompatibleLLM (OpenAI API + LM Studio local)
│   └── ollama_setup.py     # ensure_ollama_ready() — auto-start + auto-pull for Ollama
│
├── orchestrator/
│   ├── orchestrator.py     # OrchestratorProtocol implementation
│   ├── protocols.py        # OrchestratorProtocol, ProgressSummary, ExerciseRecommendation
│   ├── session_manager.py  # SessionManager — checkpoints, context fulfillment, finalization,
│   │                       # writing<->grammar next-action signal computation
│   ├── mastery.py          # get_module_mastery() / get_level_trend() — mastery & progress logic
│   └── prompts.py
│
├── modules/
│   ├── protocols.py        # ModuleProtocol, ModuleContext, ModuleResult
│   ├── registry.py         # MODULE_REGISTRY, get_registry_description()
│   ├── writing/
│   │   ├── agent.py        # WritingModule — orchestrates evaluator pipeline
│   │   ├── skills.py       # skill instantiation and injection
│   │   └── pipeline.py     # WritingPipeline — sequences the 7-skill evaluator pipeline
│   └── grammar/            # Layer 2a — agent.py, skills.py
│                           # (planned, not built: vocab management, reading, listening, speaking)
│
├── skills/
│   ├── protocols.py        # SkillProtocol, SkillInput, SkillOutput
│   ├── estimate_text_level/ # Step 1 (implemented) — runs in parallel with Step 2
│   ├── detect_mistakes/    # Step 2 (implemented) — gate: pipeline short-circuits on failure
│   ├── verify_mistakes/    # Step 3 (implemented) — re-checks raw fragments against context,
│   │                       # drops false positives before classification (has judge tests)
│   ├── classify_mistakes/  # Step 4 (implemented)
│   ├── explain_mistakes/   # Step 5 (implemented)
│   ├── write_correction/   # Step 6 (implemented) — runs in parallel with Step 7
│   ├── summarise_session/  # Step 7 (Layer 1a) — writing variant under summarise_session/writing/
│   ├── btw_handler/        # utility skill (implemented)
│   ├── topic_picker/       # Layer 1b
│   ├── summarize_progress/ # Layer 1b
│   ├── summarize_writing_history/ # Layer 2b — powers the on-demand /history command
│   ├── cefr_estimator/     # Layer 2c "Level & Progress"
│   ├── select_grammar/     # Layer 2a
│   ├── dump_grammar/       # Layer 2a
│   ├── generate_exercises/ # Layer 2a
│   └── grade_exercises/    # Layer 2a — batched grading + feedback
│                           # (no drill_vocab planned — see Goals & Non-Goals)
│
├── memory/
│   ├── protocols.py        # StorageProtocol, SessionLog, SessionFileContent + subclasses
│   ├── factory.py          # build_storage() — factory for SQLite/JSON store selection
│   ├── sqlite_store.py
│   ├── json_store.py       # dev/test backend
│   └── schema.sql
│
├── data/                   # gitignored
│   ├── sessions/
│   ├── summaries/
│   └── checkpoints/
│
├── ui/
│   ├── cli.py              # PoC CLI
│   ├── app.py              # Layer 1c frontend (Flask)
│   └── mcp_server.py       # Layer 3d — read-only MCP server over StorageProtocol
│                           #   (get_progress, list_sessions, get_recurring_errors,
│                           #    get_vocab_flags, export_writing_history, get_error_taxonomy,
│                           #    get_grammar_topic_list, etc.) — see README.md
│
├── scripts/                # standalone admin CLIs, not imported by the app itself
│   ├── check_ollama_model.py  # interactive cold-start helper: ensures the Ollama model in the
│   │                           # active config exists locally, offers to pull the base model and
│   │                           # run `ollama create` for the custom Modelfile-based model
│   ├── generate_language.py   # CLI entry point for lang/generate.py's language-asset chain
│   └── generate_messages.py   # CLI entry point for lang/generate_messages.py's catalog generator
│
├── tests/
│   ├── unit/
│   │   ├── test_storage.py
│   │   ├── test_orchestrator.py
│   │   ├── test_llm.py
│   │   ├── writing/
│   │   │   ├── test_writing.py
│   │   │   └── test_writing_pipeline.py
│   │   ├── grammar/
│   │   │   └── test_grammar_skills.py
│   │   ├── lang/
│   │   │   ├── test_lang.py
│   │   │   ├── test_generate.py
│   │   │   ├── test_messages.py
│   │   │   └── test_generate_messages.py
│   │   └── ...              # test_cli.py, test_ui.py, test_mastery.py, test_mcp_server.py, etc.
│   ├── e2e/                # test_smoke.py, test_bridge_smoke.py, conftest.py, seed_helpers.py
│   ├── judge/              # LLM-as-judge eval tests; one judge_*.py per skill/module,
│   │   │                   # plus judge_summary.py (aggregator) and utils.py (shared harness)
│   │   └── ...
│   └── fixtures/
│       ├── writing_pairs.json
│       ├── orchestrator_cases.json
│       └── regression/
│
├── pyproject.toml
├── README.md
├── config.py               # load_config() — parses the active YAML, resolves ${VAR} env refs
├── config.yaml             # default config (Ollama, local, cold-start path)
├── config.gemini.yaml      # Gemini backend
├── config.vertex.yaml      # Vertex AI backend
├── config.test.yaml        # isolated data_root for tests
└── Modelfile               # custom Ollama model definition (FROM gemma2:9b) — see PROVIDERS.md
```

---

## Key Design Decisions

**Three-grain architecture.** Skills (atomic), modules (agents composing skills), orchestrator (top-level agent). Clean boundaries: skills don't call modules, modules don't call storage, only the orchestrator touches memory.

**Skills are pure.** No storage access, no provider SDK calls. Receive input via typed dataclass, call LLM via `LLMProtocol`, return typed output. Independently testable.

**Modules are pure.** Receive `ModuleContext` (fulfilled by orchestrator), orchestrate their skills, return `ModuleResult` + `SessionFileContent`. No storage access.

**Memory boundary is hard.** Only the orchestrator calls `StorageProtocol`. Not a convention — enforced by design. All persistence flows through one place.

**`ContextRequest` pattern.** Modules declare what they need from memory. Orchestrator fulfills it. Module stays decoupled from storage.

**`SessionFileContent` typed subclasses.** Each module defines its own content dataclass inheriting from `SessionFileContent`. Storage serializes via `to_dict()` without knowing module-specific fields.

**Utility vs session skill types.** Skills declare `skill_type: session | utility`. Session skills have a full lifecycle (run by module, result persisted). Utility skills are invoked inline mid-session (`btw_handler`) — no session file, returned in module result metadata for orchestrator to persist.

**LLM abstraction — base class + per-provider files.** `llm/base.py` defines `BaseLLM`. Each provider is its own file (`gemini.py`, `vertex.py`, `openai_compat.py`). Factory reads config, returns correct instance. `OpenAICompatibleLLM` covers both OpenAI API and LM Studio local hosting via `base_url`; `VertexAILLM` authenticates via ADC instead of an API key. Nothing outside `llm/` imports a provider directly.

**Explicit cold start branch.** Below threshold, orchestrator returns hardcoded default — not a degraded LLM call. Visible in code, testable as unit test.

**Interrupted session — resume/log/discard.** Chat transcript saved incrementally to checkpoint. On startup, three-way prompt. Resume available only if module supports `restore_checkpoint()`. PoC modules degrade to log/discard.

**Storage abstraction.** `SQLiteSessionStore` for production, `JSONSessionStore` for dev/test. Swap via config. Unit tests run against JSON store — no DB setup.

**Three-tier testing.** Unit tests (deterministic, run automatically — mocked LLM, no network). LLM-as-judge (semantic quality — a judge runner exists per skill/module, `tests/judge/`, fully built and ready to run on demand; not wired into the default suite since it makes real LLM calls). Regression fixtures (accumulated during development). Ground truth within B1 scope.

**`lang/` versioned content maps.** CEFR pedagogical hints, error taxonomy, CEFR level descriptors, grammar exercise types, grammar topics, and per-level writing word ranges all live as versioned YAML artifacts under their own subdirectory in `lang/maps/`. Language configs in `lang/languages/` reference maps by name. The registry cross-validates all references at startup. Default maps (`default.yaml`) provide a language-agnostic fallback for unconfigured languages. Adding a language = one YAML file; adding a new taxonomy variant = one YAML file, no code change. `lang/generate.py`/`lang/generate_prompts.py` generate these map assets — see `docs/lang.md` for that subsystem. A second, orthogonal catalog, `lang/messages/{language}.yaml`, holds id-keyed backend UI text (orchestrator menus, confirmations) resolved by `explanation_language` instead — see `docs/lang.md`'s "Message catalog" section.

**Config files, not hardcoded settings.** `config.py`'s `load_config()` parses whichever YAML file `LTUT_CONFIG` points at (`config.yaml` by default) into typed dataclasses, resolving any `${VAR_NAME}` value against the environment at load time — API keys and other secrets never sit in a committed file. Swapping the LLM backend (a stated Goal) means pointing `LTUT_CONFIG` at a different file, not editing code.

**Supporting scripts are separate from runtime.** `scripts/check_ollama_model.py`, `scripts/generate_language.py`, and `scripts/generate_messages.py` are one-off admin CLIs a user runs directly — none is imported by `ui/cli.py` or `ui/app.py`. The first handles the local-model cold start (pulling the base model, then running `ollama create` for the custom Modelfile-based model); the second drives `lang/generate.py`'s self-correcting LLM chain to flesh out a new target language's content maps; the third drives `lang/generate_messages.py` to translate the backend UI text catalog into a new `explanation_language`.

**`WritingSessionContent` schema evolution.** Layer 1a Steps 1–4 populate `mistakes`, `recommendations`, `comment`, `corrected_text`. Steps 5–6 extend the schema: add `text_level_estimate`, enrich each mistake with `severity` (`critical`/`expected`/`minor`), replace `recommendations` with `tips` (sorted by distance from user level), replace `comment` with `session_summary`. Schema changes are additive; no breaking changes to storage. (An earlier draft also added a `comparison_note: str | None` stub as a Layer 2b placeholder; Layer 2b took a different shape — an on-demand `/history` command, not a per-session field — so that stub was removed rather than left permanently `None`. See `docs/writing.md`.)
