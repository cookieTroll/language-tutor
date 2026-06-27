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
| **PoC** | Contracts + storage abstraction + orchestrator skeleton (cold start) + writing module: hardcoded topic + raw mistake detector + session file write + CLI |
| **1a** | Full evaluator pipeline (4-step decomposition) |
| **1b** | Topic picker + orchestrator LLM routing + progress summary |
| **1c** | Light local frontend (chat window + session file browser) |
| **2a** | Grammar module |
| **2b** | Cross-session writing comparison |
| **2c** | CEFR estimator |
| **3a** | Vocab module |
| **3b** | Level progression tracking |
| **3c** | Anki export |

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
    ┌────────┼─────────────────────────┐
    ▼        ▼        ▼        ▼       ▼
[detect] [process] [feedback] [correct] [pick_topic]
  Skill    Skill     Skill      Skill     Skill
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
├── detect_mistakes/        # session skill
│   ├── skill.md
│   └── prompts.py
├── process_mistakes/       # session skill
│   ├── skill.md
│   └── prompts.py
├── generate_feedback/      # session skill
│   ├── skill.md
│   └── prompts.py
├── write_correction/       # session skill
│   ├── skill.md
│   └── prompts.py
├── pick_topic/             # session skill
│   ├── skill.md
│   └── prompts.py
├── btw_handler/            # utility skill — invoked mid-session, no session file
│   ├── skill.md
│   └── prompts.py
├── select_grammar/         # session skill (Layer 2a)
│   └── ...
├── dump_grammar/           # session skill (Layer 2a)
│   └── ...
├── explain_grammar/        # utility skill (Layer 2a)
│   └── ...
├── generate_exercises/     # session skill (Layer 2a)
│   └── ...
└── drill_vocab/            # session skill (Layer 3a)
    └── ...
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
│   ├── LAYERS.md           # flat layer manifest — agent-facing
│   ├── contracts.md        # all protocols and dataclasses
│   ├── memory.md           # storage, schema, session files, interruption
│   ├── orchestrator.md     # orchestrator logic, cold start, prompts, aggregation
│   ├── testing.md          # three-tier testing architecture
│   ├── llm_backends.md     # LLM abstraction, implementations, config
│   └── skills/
│       ├── writing.md      # writing module + skills spec
│       ├── grammar.md      # grammar module + skills spec (Layer 2a)
│       └── vocab.md        # vocab module + skills spec (Layer 3a)
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
│   │   ├── module.md
│   │   ├── agent.py
│   │   └── skills.py
│   ├── grammar/            # Layer 2a
│   │   ├── module.md
│   │   ├── agent.py
│   │   └── skills.py
│   └── vocab/              # Layer 3a
│       ├── module.md
│       ├── agent.py
│       └── skills.py
│
├── skills/
│   ├── protocols.py        # SkillProtocol, SkillInput, SkillOutput
│   ├── detect_mistakes/
│   │   ├── skill.md
│   │   └── prompts.py
│   ├── process_mistakes/
│   │   ├── skill.md
│   │   └── prompts.py
│   ├── generate_feedback/
│   │   ├── skill.md
│   │   └── prompts.py
│   ├── write_correction/
│   │   ├── skill.md
│   │   └── prompts.py
│   ├── pick_topic/
│   │   ├── skill.md
│   │   └── prompts.py
│   ├── btw_handler/        # utility skill
│   │   ├── skill.md
│   │   └── prompts.py
│   ├── select_grammar/     # Layer 2a
│   ├── dump_grammar/       # Layer 2a
│   ├── explain_grammar/    # Layer 2a utility
│   ├── generate_exercises/ # Layer 2a
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
│   ├── cli.py              # PoC
│   └── app.py              # Layer 1c
│
├── tests/
│   ├── test_storage.py
│   ├── test_registry.py
│   ├── test_taxonomy.py
│   ├── test_orchestrator.py
│   ├── test_llm.py
│   ├── judge/
│   │   ├── judge_detector.py
│   │   ├── judge_evaluator.py
│   │   └── judge_orchestrator.py
│   └── fixtures/
│       ├── writing_pairs.json
│       ├── orchestrator_cases.json
│       └── regression/
│
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
