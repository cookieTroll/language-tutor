# GermanTutor — Layer Manifest

Machine-readable delivery plan. Read this first in any coding session to know what is in scope for the current layer. Each entry maps to a specific folder and file in the repo.

---

## PoC

**Goal:** End-to-end loop working. One writing session, stored correctly, retrievable. Architecture proven — not feature-complete.

### Infrastructure
- `llm/base.py` — `BaseLLM` abstract class
- `llm/gemini.py` — `GeminiLLM` (primary backend)
- `llm/factory.py` — `build_llm(config)`
- `memory/protocols.py` — `StorageProtocol`, `SessionLog`, `SessionFileContent` (base + `WritingSessionContent`), `UserProfile`, `VocabFlag`, `BtwEntry`
- `memory/sqlite_store.py` — full `StorageProtocol` implementation including `user_profiles` table
- `memory/json_store.py` — dev/test backend
- `memory/schema.sql` — all tables (sessions, errors, btw_log, vocab_flags, user_levels, user_profiles)
- `modules/protocols.py` — `ModuleProtocol`, `ModuleContext` (with `language` field), `ModuleResult`, `ContextRequest`
- `modules/registry.py` — `MODULE_REGISTRY`, `get_registry_description()`
- `skills/protocols.py` — `SkillProtocol`, `SkillInput`, `SkillOutput`

### Orchestrator
- `orchestrator/orchestrator.py` — cold start only (no LLM routing)
  - Startup: language selection (get/set active language, prompt for level if new)
  - Startup: interrupted session check → resume/log/discard
  - `summarize_progress(user_id, language)` → returns `None` below threshold
  - `recommend_exercise()` → `DEFAULT_RECOMMENDATION` when summary is None (per language)
  - `run_session(user_id, language)` — full 13-step loop
- `orchestrator/prompts.py` — stub (no LLM prompts in PoC orchestrator)

### Writing Module
- `modules/writing/agent.py` — `WritingModule` (ModuleProtocol impl, PoC scope)
- `modules/writing/skills.py` — instantiate and inject `detect_mistakes` skill only
- `modules/writing/module.md` — spec

### Skills (PoC)
- `skills/detect_mistakes/` — Raw Mistake Detector (Step 1 only)
- `skills/btw_handler/` — utility skill, invoked inline during writing phase

### UI
- `ui/cli.py` — startup, orchestrator loop, writing session flow, elapsed timer display

### Tests
- `tests/test_storage.py` — all storage unit tests
- `tests/test_registry.py` — module registry compliance
- `tests/test_orchestrator.py` — cold start, interrupted session detection
- `tests/test_llm.py` — factory, mock, backend switching

---

## Layer 1a — Full Evaluator Pipeline

### Skills
- `skills/process_mistakes/` — Step 2: Mistake Processor
- `skills/generate_feedback/` — Step 3: Feedback Generator
- `skills/write_correction/` — Step 4: Correction Writer
- `skills/explain_grammar/` — utility skill (shared); writing module uses it in post-evaluation review loop; grammar module uses it in exercise feedback (Layer 2a)
- `skills/detect_mistakes/` — updated: taxonomy validation added

### Module
- `modules/writing/agent.py` — updated: all 4 evaluator steps wired + post-evaluation review loop; full `WritingSessionContent` populated
- `modules/writing/skills.py` — updated: inject all 4 evaluator skills + `explain_grammar`

### Tests
- `tests/test_taxonomy.py` — error taxonomy enforcement
- `tests/fixtures/writing_pairs.json` — 3–5 manually verified pairs
- `tests/judge/judge_detector.py`
- `tests/judge/judge_evaluator.py`

---

## Layer 1b — Topic Picker + LLM Routing + Progress Summary

### Skills
- `skills/pick_topic/` — Topic Picker skill
- `skills/summarize_progress/` — Progress Summary skill

### Module
- `modules/writing/agent.py` — updated: topic picker wired, context request expanded
- `modules/writing/skills.py` — updated: inject `pick_topic` skill

### Orchestrator
- `orchestrator/orchestrator.py` — updated: `summarize_progress()` LLM call, `recommend_exercise()` LLM call, validation against registry
- `orchestrator/prompts.py` — progress summary prompt, recommendation prompt

### Tests
- `tests/fixtures/orchestrator_cases.json`
- `tests/judge/judge_orchestrator.py`

---

## Layer 1c — Local Frontend

- `ui/app.py` — Flask/FastAPI local server
  - `/` — chat window (session flow)
  - `/sessions` — session file browser (YAML rendered as HTML)
  - `/session/{session_id}` — individual session view
  - Timer widget in session header

---

## Layer 2a — Grammar Module

- `skills/select_grammar/`
- `skills/dump_grammar/`
- `skills/explain_grammar/` — already built in Layer 1a; grammar module injects it for exercise feedback
- `skills/generate_exercises/`
- `modules/grammar/agent.py`
- `modules/grammar/skills.py`
- `modules/grammar/module.md`
- `memory/protocols.py` — updated: `GrammarSessionContent` added
- `modules/registry.py` — updated: grammar module registered

---

## Layer 2b — Cross-Session Writing Comparison

- `modules/writing/agent.py` — updated: comparison step added post-evaluation
- `memory/protocols.py` — updated: `StorageProtocol.get_writing_sessions()` added
- `WritingSessionContent` — updated: `comparison_to_previous` field added (optional)

---

## Layer 2c — CEFR Estimator

- `skills/estimate_cefr/` — reads session logs, estimates level
- `memory/protocols.py` — `write_level()` with `source='estimated'`
- Trigger: on-demand ("what level am I?") or post-session hook

---

## Layer 3a — Vocab Module

- `skills/drill_vocab/`
- `modules/vocab/agent.py`
- `modules/vocab/skills.py`
- `modules/vocab/module.md`
- Word lists: `skills/drill_vocab/word_lists/greetings.yaml`, `daily_routine.yaml`
- `modules/registry.py` — updated: vocab module registered

---

## Layer 3b — Level Progression Tracking

- `ui/app.py` — updated: level history timeline in session browser
- Orchestrator progress summary updated to include level trend

---

## Layer 3c — Anki Export

- `memory/protocols.py` — `get_vocab_flags()` used as export source
- Export function: `data/exports/{user_id}_anki_{date}.txt`
- CLI and UI export option surfaced

---

## Layer 3d — MCP Server

- `ui/mcp_server.py` — MCP server implementation (FastMCP)
- Exposes tools wrapping pure skills:
  - `explain_grammar(topic, level)` (wraps `explain_grammar` skill)
  - `get_vocab_drill(topic, level)` (wraps vocab generation skill)
- CLI/UI instructions for connecting to local MCP server
