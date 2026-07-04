# GermanTutor — Layer Manifest

Machine-readable delivery plan. Read this first in any coding session to know what is in scope for the current layer. Each entry maps to a specific folder and file in the repo.

---

## PoC

**Goal:** End-to-end loop working. One writing session, stored correctly, retrievable. Architecture proven — not feature-complete.

### Infrastructure
- `llm/base.py` — `BaseLLM` abstract class
- `llm/gemini.py` — `GeminiLLM` (primary backend)
- `llm/factory.py` — `build_llm(config)`
- `shared/io.py` — `IOHandler` protocol + `TerminalIOHandler`; passed into module.run() and orchestrator to decouple I/O from logic
- `memory/protocols.py` — `StorageProtocol` (composed from `SessionStore`, `LevelStore`, `BtwLogStore`, `VocabStore`, `ProfileStore`), `SessionLog`, `SessionAggregate`, `SessionFileContent` (base + `WritingSessionContent`), `UserProfile`, `VocabFlag`, `BtwEntry`
- `memory/sqlite_store.py` — full `StorageProtocol` implementation including `user_profiles` table
- `memory/json_store.py` — dev/test backend
- `memory/schema.sql` — all tables (sessions, errors, btw_log, vocab_flags, user_profiles)
- `modules/protocols.py` — `ModuleProtocol`, `ModuleContext`, `ModuleResult`, `ContextRequest`
- `modules/registry.py` — `MODULE_REGISTRY`, `get_registry_description()`
- `skills/protocols.py` — `SkillProtocol`, `SkillInput`, `SkillOutput`

### Orchestrator
- `orchestrator/orchestrator.py` — cold start only (no LLM routing); language selection, interrupted session surface, progress summarise, recommend, confirm, run
- `orchestrator/session_manager.py` — `SessionManager`: owns WAL init + checkpoint creation, context fulfillment, finalization, interruption log/discard
- `orchestrator/prompts.py` — interruption summarisation prompt

### Writing Module
- `modules/writing/agent.py` — `WritingModule` (ModuleProtocol impl)
- `modules/writing/pipeline.py` — `WritingPipeline`: sequences Steps 5→1→2→3→4→6; `WritingModule` delegates to it

### Skills (PoC)
- `skills/btw_handler/` — utility skill, invoked inline during writing phase

### UI
- `ui/cli.py` — startup, orchestrator loop, writing session flow, elapsed timer display

### Tests
- `tests/test_storage.py` — all storage unit tests
- `tests/test_registry.py` — module registry compliance
- `tests/test_orchestrator.py` — cold start, interrupted session detection
- `tests/test_llm.py` — factory, mock, backend switching

---

## Layer 1a — Full Evaluator Pipeline ✓

### Skills
- `skills/detect_mistakes/` — Step 1: Raw Mistake Detector (gate — skips Steps 2–4 if no mistakes)
- `skills/classify_mistakes/` — Step 2: Taxonomy Classifier
- `skills/explain_mistakes/` — Step 3: Explanation Generator
- `skills/write_correction/` — Step 4: Correction Writer (produces `corrected_text`, `tips`, `session_summary`)
- `skills/estimate_text_level/` — Step 5: CEFR Band Estimator (runs before Step 1; independent)
- `skills/summarise_session/` — Step 6: Session Summariser (severity-grouped mistakes, `session_summary`, `tips`)

### Module
- `modules/writing/pipeline.py` — `WritingPipeline` sequences all six steps; `WritingModule` delegates to it
- `modules/writing/agent.py` — updated: delegates to pipeline, handles I/O via `IOHandler`

### Tests
- `tests/fixtures/writing_pairs.json` — verified input/output pairs
- `tests/unit/writing/test_writing_pipeline.py`
- `tests/unit/writing/test_writing.py`
- `tests/judge/` — per-step judges

---

## Layer 1b — Topic Picker + LLM Routing + Progress Summary ✓

### Skills
- `skills/topic_picker/` — Topic Picker skill
- `skills/summarize_progress/` — Progress Summary skill (LLM-driven aggregation; returns `weakest_module` + `recommendation_reason`)

### Module
- `modules/writing/agent.py` — updated: `topic_picker` wired, context request expanded

### Orchestrator
- `orchestrator/orchestrator.py` — updated: `summarize_progress()` LLM call, `recommend_exercise()` derives from summary; both validated against `MODULE_REGISTRY`

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

See `docs/grammar.md` for full design and `docs/CHECKLIST.md`'s 2a-i…2a-viii for the staged build order.

- `lang/maps/grammar_topics/german_a1_b2.yaml` + `lang/models.py`/`lang/loader.py` support (same versioned-map pattern as `taxonomy`/`cefr_hints`)
- `lang/maps/exercise_types/default.yaml` — exercise type vocabulary (name/grading/description) for `generate_exercises`, same versioned-map pattern; language-agnostic pedagogy, not German-specific content
- `skills/select_grammar/`
- `skills/dump_grammar/`
- `skills/generate_exercises/`
- `skills/grade_exercises/` — batched grading + feedback for all wrong answers (exact-match and open-ended); replaces the previously planned `explain_grammar` utility, which was dropped (never actually built — `explain_mistakes`, a different Layer 1a skill, was)
- `modules/grammar/agent.py`
- `modules/grammar/skills.py`
- `modules/grammar/module.md`
- `memory/protocols.py` — updated: `GrammarSessionContent` added, `errors.module` column, `SessionFileContent.next_actions`
- `modules/registry.py` — updated: grammar module registered
- Writing ↔ grammar cross-module bridge, both directions (`NextActionSignal`, `run_session(forced_recommendation=...)`) — depends on the above; see 2a-vii

---

## Layer 2b — Cross-Session Writing Comparison

- `modules/writing/agent.py` — updated: comparison step added post-evaluation
- `memory/protocols.py` — updated: `StorageProtocol.get_writing_sessions()` added
- `WritingSessionContent` — updated: `comparison_to_previous` field added (optional)

---

## Layer 2c — Level & Progress

> Merges the original Layer 2c (CEFR Estimator) and Layer 3b (Level Progression Tracking) —
> both turned out to be different views over the same mastery data, not independent features.

- `memory/protocols.py` — `WritingSessionContent.word_count` / `SessionLog.word_count` added (same idempotent-migration pattern as `text_level_estimate` in Layer 2b)
- `get_module_mastery(user_id, language, module)` — topics mastered/attempted, weak/strong tags (reuses `get_error_taxonomy`/`get_grammar_topic_list` from Layer 3d), word-count flavor stats
- `get_level_trend(user_id, language, module="writing")` — chronological `text_level_estimate` pull, no new computation
- `skills/cefr_estimator/` — level-up is a threshold crossing on the mastery ratio (~`GRAMMAR_MASTERY_THRESHOLD`); `write_level()` with `source='estimated'` on `user_profiles` (no separate `user_levels`/`level_history` table — see `docs/memory.md`)
- UI: progression bar (mastery % + weak/strong chips + word counts) + text-level trend sparkline, in session browser and progress summary
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

## Layer 3b — merged into Layer 2c above (see "Level & Progress")

---

## Layer 3c — Anki Export

- `memory/protocols.py` — `get_vocab_flags()` used as export source
- Export function: `data/exports/{user_id}_anki_{date}.txt`
- CLI and UI export option surfaced

---

## Layer 3d — MCP Server

> Redesigned from the original plan: rather than wrapping session skills
> (`explain_grammar` was dropped in Layer 2a; a vocab drill skill doesn't
> exist yet — Layer 3a), this is a read-only server over the `memory/`
> storage layer plus `lang/maps/` reference data. No LLM calls, no writes.

- `ui/mcp_server.py` — FastMCP server (stdio transport), built on `build_storage()`
- Tools: `list_users`, `list_languages`, `get_progress`, `list_sessions`,
  `get_session`, `get_recurring_errors`, `get_vocab_flags`,
  `export_writing_history`, `get_error_taxonomy`, `get_grammar_topic_list`
- `memory/protocols.py` — added `StorageProtocol.list_users()` and
  `get_session_by_id()`, implemented in both `sqlite_store.py`/`json_store.py`
- Running/testing documented in README.md
