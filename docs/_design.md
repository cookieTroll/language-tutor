# LanguageTutor Agent — Design Document

## Overview

LanguageTutor is a single, unified environment for practicing a language — one login, one
shared memory of what you've practiced and where you're weak, across every module rather than
a separate app per skill. Its core is **output**: writing practice drives the loop, because
producing the language builds fluency faster than passive recognition does. Grammar directly
complements writing today — a recurring writing mistake can trigger a grammar session on that
exact point, and a mastered grammar topic can trigger a writing session that uses it. Reading
(with comprehension), listening, and speaking are planned as further modules under the same
environment; none of the three is scoped yet, and all are deferred to post-submission.

The primary pitch: **one environment, a personalized feedback loop that spans it**. Most
language tools are either rigid drill generators or single-skill apps that don't talk to each
other. This agent learns which skills you've neglected, what errors recur, and routes you
across modules accordingly — and it's built to keep growing into further modules rather than
stay a single-exercise tool.

Detailed specs for each component live in `docs/`. This document is the human-facing,
policy-level overview.

---

## Goals & Non-Goals

### Goals
- One unified environment across modules — writing and grammar today; vocab management,
  reading, listening, and speaking planned — sharing one login, one memory, one session model
- Output-first: writing is the core driver skill; grammar directly complements it via a
  bidirectional bridge (recurring writing mistake → grammar session; mastered grammar topic →
  writing session using it)
- Adaptive module routing based on session history
- Writing-focused feedback with error annotation
- Grammar instruction and practice
- Vocab **management**, not drilling — track a per-user, per-language negative vocab list and
  export it to Anki; spaced-repetition drilling itself is deliberately not rebuilt in-house
- AI-supported language-asset generation — `lang/generate.py` chains self-correcting LLM calls
  to produce a new target language's taxonomy/CEFR/grammar-topic content maps, validated
  through the same Pydantic contracts and registry cross-check every shipped language passes
- True multi-language support — independent progress profiles per user per language
- Persistent memory across sessions (log + files), scoped to (user_id, language)
- Testable, modular architecture with explicit contracts
- Swappable LLM backend (Gemini, Vertex AI, OpenAI-compatible APIs, Ollama/LM Studio local),
  with a supporting setup script (`scripts/check_ollama_model.py`) for the local cold-start case
- `/btw` inline question command, available during the writing session today — unifies the
  environment by surfacing translation/grammar help without leaving the current flow
- Session clock with a visible timer (CLI and web) — deliberately simulates timed test/exam
  conditions, not just a UX nicety
- Negative vocab list — per-user per-language, populated from `/btw` flags and evaluator signals
- Explicit session history aggregation and personalization
- Both a CLI and a browser frontend, available today, sharing the same orchestrator/module code
  through the `IOHandler` abstraction

### Non-Goals (for this submission)
- Building an in-house vocabulary drill/spaced-repetition engine — Anki already solves this
  well; LanguageTutor manages the vocab list and exports to it instead of reinventing that loop
- Real-time audio/video infrastructure

### Roadmap (planned, explicitly deferred post-submission — none of these are fully scoped yet)
1. **Vocab management** — the negative vocab list already exists; what's planned next is the
   management surface and Anki export, not a drill module
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

**Roadmap (post-submission, in priority order — none of these are fully scoped yet):**

1. **Vocab management** — negative vocab list + Anki export; no in-house drill engine
2. **Reading**, with comprehension checks
3. **Listening**
4. **Speaking / pronunciation**

`docs/_CHECKLIST.md` carries the tactical, line-item backlog for both sections above — this
table states what a layer *is*, the checklist tracks what's actually left to do.

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
             ┌──────────────┼──────────────┐
             ▼              ▼              ▼
       [Writing]       [Grammar]       [Vocab]
        Module          Module         Module
       (PoC+1a/b)      (Layer 2a)    (Layer 3a)
             │
             │ composes and invokes
    ┌───────────┬────────────┬────────────┬────────────┬────────────┬──────────────┬──────────────────┐
    ▼           ▼            ▼            ▼            ▼            ▼              ▼
[estimate_  [detect_    [verify_    [classify_  [explain_   [write_      [summarise_
text_level] mistakes]  mistakes]   mistakes]   mistakes]   correction]  writing_session]
  Step 1      Step 2      Step 3       Step 4      Step 5      Step 6        Step 7
(Steps 1+2 run in parallel; Steps 6+7 run in parallel once Step 5 finishes)
+ [btw_handler] — utility skill, invoked mid-session, no session file
+ [topic_picker] [summarize_progress] — Layer 1b
```

### Grain 1 — Skills (atomic, lowest grain)

A skill is a single, focused callable unit. It has:
- A fixed input/output contract
- A prompt template
- A `skill_type`: `session` (full lifecycle, run by module) or `utility` (invoked inline, no session file)
- A `skill.md` as its authoritative spec

Skills are pure — no storage access, no LLM provider knowledge. They receive input, call the LLM via `LLMProtocol`, return structured output. Nothing else.

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
├── grade_exercises/        # session skill (Layer 2a) — batched grading + feedback
└── drill_vocab/            # session skill (Layer 3a, planned)
```

### Grain 2 — Modules (agents, middle grain)

A module is an agent with a goal. It receives a set of skills (injected at startup via `skills.py`), and orchestrates them to complete a session. The module decides which skills to invoke, in what order, and how to handle branching (e.g. topic picker bypassed if user provides own topic).

Each module lives in its own folder under `modules/`. There is no `module.md` spec file per module — `agent.py` and `skills.py` are the authoritative reference:
```
modules/
├── writing/
│   ├── agent.py            # ModuleProtocol implementation
│   ├── skills.py           # skill instantiation and injection
│   └── pipeline.py         # WritingPipeline — sequences the 7-skill evaluator pipeline
├── grammar/                # Layer 2a
│   ├── agent.py
│   └── skills.py
└── vocab/                  # Layer 3a
    ├── agent.py
    └── skills.py
```

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
│   └── writing.md          # writing module + evaluator pipeline spec
│
├── lang/                   # versioned content maps + language-asset generation (see docs/lang.md)
│   ├── models.py           # Pydantic models: CEFRMap, TaxonomyMap, LanguageConfig
│   ├── loader.py           # _Registry: loads + cross-validates maps at startup
│   ├── generate.py         # language-asset generation subsystem — see docs/lang.md
│   ├── generate_prompts.py # prompt templates for generate.py — see docs/lang.md
│   ├── maps/
│   │   ├── cefr/                   # {name}.yaml — versioned CEFR pedagogical hint maps
│   │   ├── taxonomy/               # {name}.yaml — versioned error taxonomy maps
│   │   ├── cefr_descriptors/       # {name}.yaml — versioned CEFR level-descriptor maps
│   │   ├── exercise_types/         # {name}.yaml — grammar exercise type vocabulary (Layer 2a)
│   │   ├── grammar_topics/         # {name}.yaml — versioned grammar topic maps (Layer 2a)
│   │   └── writing_word_ranges/    # {name}.yaml — per-level minimum word counts for writing
│   └── languages/          # {language}.yaml — maps language → cefr_hints + taxonomy
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
│   ├── grammar/            # Layer 2a — agent.py, skills.py
│   └── vocab/              # Layer 3a
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
│   ├── grade_exercises/    # Layer 2a — batched grading + feedback
│   └── drill_vocab/        # Layer 3a
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
│   │   │   └── test_generate.py
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
└── config.yaml
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

**Three-tier testing.** Unit tests (deterministic), LLM-as-judge (semantic quality), regression fixtures (accumulated during development). Ground truth within B1 scope.

**`lang/` versioned content maps.** CEFR pedagogical hints, error taxonomy, CEFR level descriptors, grammar exercise types, grammar topics, and per-level writing word ranges all live as versioned YAML artifacts under their own subdirectory in `lang/maps/`. Language configs in `lang/languages/` reference maps by name. The registry cross-validates all references at startup. Default maps (`default.yaml`) provide a language-agnostic fallback for unconfigured languages. Adding a language = one YAML file; adding a new taxonomy variant = one YAML file, no code change. `lang/generate.py`/`lang/generate_prompts.py` generate these map assets — see `docs/lang.md` for that subsystem.

**`WritingSessionContent` schema evolution.** Layer 1a Steps 1–4 populate `mistakes`, `recommendations`, `comment`, `corrected_text`. Steps 5–6 extend the schema: add `text_level_estimate`, enrich each mistake with `severity` (`critical`/`expected`/`minor`), replace `recommendations` with `tips` (sorted by distance from user level), replace `comment` with `session_summary`. Schema changes are additive; no breaking changes to storage. (An earlier draft also added a `comparison_note: str | None` stub as a Layer 2b placeholder; Layer 2b took a different shape — an on-demand `/history` command, not a per-session field — so that stub was removed rather than left permanently `None`. See `docs/writing.md`.)
