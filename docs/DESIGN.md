# LanguageTutor Agent — Design Document

## Overview

LanguageTutor is an AI-powered language tutoring agent focused on **output and writing**. It personalizes practice by tracking session history, identifying weak areas, and routing users to the most relevant exercise.

The primary pitch: **personalized feedback loop**. Most language tools are rigid. This agent learns which skills you've neglected, what errors recur, and adapts accordingly.

Detailed specs for each component live in `docs/`. This document is the human-facing overview.

---

## Goals & Non-Goals

### Goals
- Adaptive module routing based on session history
- Writing-focused feedback with error annotation
- Grammar instruction and practice
- Lightweight vocabulary drilling
- True multi-language support — independent progress profiles per user per language
- Persistent memory across sessions (log + files), scoped to (user_id, language)
- Testable, modular architecture with explicit contracts
- Swappable LLM backend (Gemini, OpenAI-compatible APIs, LM Studio (local))
- `/btw` inline question command available during any active session
- Session clock with visible timer (CLI and UI)
- Negative vocab list — per-user per-language, populated from `/btw` flags and evaluator signals
- Explicit session history aggregation and personalization
- Simple CLI for PoC; local browser frontend as a later layer

### Non-Goals (explicitly out of scope)
- Speaking / pronunciation
- Listening (copyright and complexity)
- Full spaced repetition system (Anki handles this; export in Layer 3)
- Real-time audio/video

---

## Delivery Layers

| Layer | Scope |
|-------|-------|
| **PoC** | Contracts + storage abstraction + orchestrator skeleton (cold start) + writing module: hardcoded topic + raw mistake detector + session file write + CLI + `lang/` content maps (CEFR hints, error taxonomy) |
| **1a** | Full evaluator pipeline: detect → classify → explain → correct (Steps 1–4); design research (feedback rubrics, severity); text-level estimation + session summary (Steps 5–6) |
| **1b** | User level review + session history aggregation + topic picker + orchestrator LLM routing |
| **1c** | `IOHandler` protocol + light local frontend (chat window + session file browser) |
| **2a** | Grammar module |
| **2b** | On-demand writing history summary (`/history` command — topics, recurring mistakes, level trend; not a per-session field) |
| **2c** | CEFR estimator — aggregates per-session text-level estimates (Step 5) into a user-level estimate |
| **3a** | Vocab module |
| **3b** | Level progression tracking |
| **3c** | Anki export |
| **3d** | MCP Server |

Frontend (1c) may be moved earlier without architectural impact.

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
    ┌────────┬──────────┬──────────┬─────────┬──────────┬────────────┐
    ▼        ▼          ▼          ▼         ▼          ▼
[detect_  [classify_ [explain_  [write_   [estimate_ [summarise_
mistakes] mistakes]  mistakes]  correction] text_level] session]
  Step 1    Step 2     Step 3     Step 4     Step 5      Step 6
+ [btw_handler] — utility skill, invoked mid-session, no session file
+ [pick_topic] [summarize_progress] — Layer 1b
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
├── detect_mistakes/        # Step 1 — session skill (implemented)
│   └── prompts.py
├── classify_mistakes/      # Step 2 — session skill (implemented)
│   └── prompts.py
├── explain_mistakes/       # Step 3 — session skill (implemented)
│   └── prompts.py
├── write_correction/       # Step 4 — session skill (implemented)
│   └── prompts.py
├── estimate_text_level/    # Step 5 — session skill (Layer 1a, planned)
│   └── prompts.py
├── summarise_session/      # Step 6 — session skill (Layer 1a, planned)
│   └── prompts.py
├── btw_handler/            # utility skill — invoked mid-session, no session file (implemented)
│   └── prompts.py
├── pick_topic/             # session skill (Layer 1b, planned)
├── summarize_progress/     # session skill (Layer 1b, planned)
├── cefr_estimator/         # session skill (Layer 2c, planned)
├── select_grammar/         # session skill (Layer 2a, planned)
├── dump_grammar/           # session skill (Layer 2a, planned)
├── generate_exercises/     # session skill (Layer 2a, planned)
├── grade_exercises/        # session skill (Layer 2a, planned) — batched grading + feedback
└── drill_vocab/            # session skill (Layer 3a, planned)
```

### Grain 2 — Modules (agents, middle grain)

A module is an agent with a goal. It receives a set of skills (injected at startup via `skills.py`), and orchestrates them to complete a session. The module decides which skills to invoke, in what order, and how to handle branching (e.g. topic picker bypassed if user provides own topic).

Each module lives in its own folder under `modules/`:
```
modules/
├── writing/
│   ├── module.md           # goal, skills used, context request, session file schema
│   ├── agent.py            # ModuleProtocol implementation
│   └── skills.py           # skill instantiation and injection
├── grammar/                # Layer 2a
│   ├── module.md
│   ├── agent.py
│   └── skills.py
└── vocab/                  # Layer 3a
    ├── module.md
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
- `llm/openai_compat.py` — `OpenAICompatibleLLM` (OpenAI API + LM Studio local)
- `llm/factory.py` — `build_llm(config)` factory

LLM instance injected at startup into orchestrator and modules. Unit tests use a mock.

See `docs/llm_backends.md` for full detail.

---

## Repository Structure

```
language-tutor/
├── docs/
│   ├── DESIGN.md           # this file
│   ├── CHECKLIST.md        # implementation checklist with submission schedule
│   ├── TODO.md             # deferred decisions and known risks
│   ├── contracts.md        # all protocols and dataclasses
│   ├── memory.md           # storage, schema, session files, interruption
│   ├── orchestrator.md     # orchestrator logic, cold start, prompts, aggregation
│   ├── testing.md          # three-tier testing architecture
│   ├── llm_backends.md     # LLM abstraction, implementations, config
│   └── writing.md          # writing module + evaluator pipeline spec (planned)
│
├── lang/                   # versioned content maps — CEFR hints and error taxonomy
│   ├── models.py           # Pydantic models: CEFRMap, TaxonomyMap, LanguageConfig
│   ├── loader.py           # _Registry: loads + cross-validates maps at startup
│   ├── maps/
│   │   ├── cefr/           # {name}.yaml — versioned CEFR pedagogical hint maps
│   │   └── taxonomy/       # {name}.yaml — versioned error taxonomy maps
│   └── languages/          # {language}.yaml — maps language → cefr_hints + taxonomy
│
├── shared/
│   └── timer.py            # SessionTimer — background thread, updates terminal title
│
├── llm/
│   ├── base.py             # BaseLLM abstract class
│   ├── factory.py          # build_llm(config) → BaseLLM
│   ├── gemini.py           # GeminiLLM (production default)
│   └── openai_compat.py    # OpenAICompatibleLLM (OpenAI API + LM Studio local)
│
├── orchestrator/
│   ├── orchestrator.py     # OrchestratorProtocol implementation
│   └── prompts.py
│
├── modules/
│   ├── protocols.py        # ModuleProtocol, ModuleContext, ModuleResult
│   ├── registry.py         # MODULE_REGISTRY, get_registry_description()
│   ├── writing/
│   │   ├── agent.py        # WritingModule — orchestrates evaluator pipeline
│   │   └── skills.py       # skill instantiation and injection
│   ├── grammar/            # Layer 2a
│   └── vocab/              # Layer 3a
│
├── skills/
│   ├── protocols.py        # SkillProtocol, SkillInput, SkillOutput
│   ├── detect_mistakes/    # Step 1 (implemented)
│   ├── classify_mistakes/  # Step 2 (implemented)
│   ├── explain_mistakes/   # Step 3 (implemented)
│   ├── write_correction/   # Step 4 (implemented)
│   ├── estimate_text_level/ # Step 5 (planned, Layer 1a)
│   ├── summarise_session/  # Step 6 (planned, Layer 1a)
│   ├── btw_handler/        # utility skill (implemented)
│   ├── pick_topic/         # Layer 1b
│   ├── summarize_progress/ # Layer 1b
│   ├── cefr_estimator/     # Layer 2c
│   ├── select_grammar/     # Layer 2a
│   ├── dump_grammar/       # Layer 2a
│   ├── generate_exercises/ # Layer 2a
│   ├── grade_exercises/    # Layer 2a — batched grading + feedback
│   └── drill_vocab/        # Layer 3a
│
├── memory/
│   ├── protocols.py        # StorageProtocol, SessionLog, SessionFileContent + subclasses
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
│   ├── app.py              # Layer 1c frontend
│   └── mcp_server.py       # Layer 3d
│
├── tests/
│   ├── test_storage.py
│   ├── test_registry.py
│   ├── test_orchestrator.py
│   ├── test_llm.py
│   ├── writing/
│   │   ├── test_writing.py
│   │   └── test_writing_pipeline.py
│   ├── lang/
│   │   └── test_lang.py
│   ├── judge/              # planned
│   │   ├── judge_detector.py
│   │   ├── judge_evaluator.py
│   │   ├── judge_summary.py
│   │   └── judge_orchestrator.py
│   └── fixtures/
│       ├── writing_pairs.json
│       ├── orchestrator_cases.json
│       └── regression/
│
├── pyproject.toml
├── README.md
├── requirements.txt
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

**Utility vs session skill types.** Skills declare `skill_type: session | utility`. Session skills have a full lifecycle (run by module, result persisted). Utility skills are invoked inline mid-session (`btw_handler`, `explain_grammar`) — no session file, returned in module result metadata for orchestrator to persist.

**LLM abstraction — base class + per-provider files.** `llm/base.py` defines `BaseLLM`. Each provider is its own file (`gemini.py`, `openai_compat.py`). Factory reads config, returns correct instance. `OpenAICompatibleLLM` covers both OpenAI API and LM Studio local hosting via `base_url`. Nothing outside `llm/` imports a provider directly.

**Explicit cold start branch.** Below threshold, orchestrator returns hardcoded default — not a degraded LLM call. Visible in code, testable as unit test.

**Interrupted session — resume/log/discard.** Chat transcript saved incrementally to checkpoint. On startup, three-way prompt. Resume available only if module supports `restore_checkpoint()`. PoC modules degrade to log/discard.

**Storage abstraction.** `SQLiteSessionStore` for production, `JSONSessionStore` for dev/test. Swap via config. Unit tests run against JSON store — no DB setup.

**Three-tier testing.** Unit tests (deterministic), LLM-as-judge (semantic quality), regression fixtures (accumulated during development). Ground truth within B1 scope.

**`lang/` versioned content maps.** CEFR pedagogical hints and error taxonomy live as versioned YAML artifacts in `lang/maps/`. Language configs in `lang/languages/` reference maps by name. The registry cross-validates all references at startup. Default maps (`default.yaml`) provide a language-agnostic fallback for unconfigured languages. Adding a language = one YAML file; adding a new taxonomy variant = one YAML file, no code change.

**`WritingSessionContent` schema evolution.** Layer 1a Steps 1–4 populate `mistakes`, `recommendations`, `comment`, `corrected_text`. Steps 5–6 extend the schema: add `text_level_estimate`, enrich each mistake with `severity` (`critical`/`expected`/`minor`), replace `recommendations` with `tips` (sorted by distance from user level), replace `comment` with `session_summary`. Schema changes are additive; no breaking changes to storage. (An earlier draft also added a `comparison_note: str | None` stub as a Layer 2b placeholder; Layer 2b took a different shape — an on-demand `/history` command, not a per-session field — so that stub was removed rather than left permanently `None`. See `docs/writing.md`.)
