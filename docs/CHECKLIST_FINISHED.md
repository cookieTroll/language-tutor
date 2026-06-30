# GermanTutor — Finished Work

Items with at least two sign-offs (Validated + optionally Finished). Pulled from CHECKLIST.md as sections complete.

`[Impl]` (Implemented) | `[Val]` (Validated — user sign-off) | `[Fin]` (Finished — second sign-off at stage end)

---

## PoC

### Repo & Config
- [x] [x] [ ] Create repo, add `DESIGN.md`, `TODO.md`, `CHECKLIST.md`, `.gitignore` (`data/`, `.env`, `__pycache__`)
- [x] [x] [ ] `requirements.txt` — `google-generativeai`, `pyyaml`, `pytest`, minimum deps only for now
- [x] [x] [ ] `config.yaml` — `data_root`, `default_level`, `cold_start_threshold`, `interruption_timeout_minutes`, `storage_backend` (`sqlite` | `json`)
- [x] [x] [ ] Config loader with basic validation (required fields present, storage_backend is valid value)

### Contracts / Protocols
- [x] [x] [ ] `memory/protocols.py` — `SessionLog`, `SessionFileContent` (abstract base + `to_dict()`), `WritingSessionContent`, `StorageProtocol`
- [x] [x] [ ] `skills/protocols.py` — `ContextRequest`, `SkillContext`, `SkillResult`, `SkillProtocol`
- [x] [x] [ ] `orchestrator/protocols.py` — `ProgressSummary`, `ExerciseRecommendation`, `OrchestratorProtocol`
- [x] [x] [ ] Verify all dataclasses have type annotations; no untyped fields

### Memory — Storage Layer
- [x] [x] [ ] `memory/schema.sql` — `sessions` table (including `status`, `started_at`), `errors` table, `user_levels` table
- [x] [x] [ ] `memory/sqlite_store.py` — implement `StorageProtocol`:
  - [x] [x] [ ] `write_session()` — insert or update sessions row
  - [x] [x] [ ] `write_file()` — serialize `SessionFileContent.to_dict()` to YAML, write to temp path, atomic rename, return relative path
  - [x] [x] [ ] `update_session_status()` — update status field, validate against allowed values
  - [x] [x] [ ] `get_recent_sessions()`
  - [x] [x] [ ] `get_interrupted_sessions()` — query `in_progress` older than timeout
- [x] [x] [ ] `memory/json_store.py` — same interface, JSON file backend for dev/test
- [x] [x] [ ] `data/sessions/`, `data/summaries/`, `data/checkpoints/` directories created by store on first run

### Storage Unit Tests
- [x] [x] [ ] `tests/test_storage.py`:
  - [x] [x] [ ] Write session → read back → assert all fields equal (SQLite and JSON store)
  - [x] [x] [ ] `get_error_frequency()` aggregates correctly across multiple sessions
  - [x] [x] [ ] `update_session_status()` transitions correctly; rejects invalid status
  - [x] [x] [ ] `get_interrupted_sessions()` returns only `in_progress` records older than timeout
  - [x] [x] [ ] `get_recent_topics()` returns correct n most recent, filtered by skill
  - [x] [x] [ ] Atomic write: no `.tmp` file exists after successful write
  - [x] [x] [ ] Relative file path resolves correctly against `data_root`
  - [x] [x] [ ] `get_current_level()` returns most recent row when multiple exist

### Skill Registry
- [x] [x] [ ] `skills/registry.py` — `MODULE_REGISTRY` dict, `get_registry_description()`
- [x] [x] [ ] `modules/writing/__init__.py`, `modules/writing/agent.py` — `WritingModule` implementing `ModuleProtocol`
- [x] [x] [ ] `tests/test_registry.py`:
  - [x] [x] [ ] All registered skills implement `SkillProtocol` (check for required attributes and methods)
  - [x] [x] [ ] `get_registry_description()` includes all registry keys

### Language Maps (`lang/`)
> Versioned YAML content maps for CEFR hints and error taxonomy. Language configs reference maps by name; the registry cross-validates all references at startup. Default maps provide a language-agnostic fallback for unconfigured languages.
- [x] [x] [ ] `lang/models.py` — Pydantic models: `CEFRMap` (per-level hints + default fallback), `TaxonomyMap` (enforces `other` tag, `validate_tag()`, `format_for_prompt()`), `LanguageConfig`
- [x] [x] [ ] `lang/loader.py` — `_Registry`: loads all maps and language configs on startup, cross-validates references; exposes `get_cefr_context()`, `get_taxonomy()`, `using_defaults()`
- [x] [x] [ ] `lang/maps/cefr/cefr_map1.yaml` — German CEFR pedagogical hints (a1–c2 + default)
- [x] [x] [ ] `lang/maps/cefr/default.yaml` — language-agnostic CEFR fallback
- [x] [x] [ ] `lang/maps/taxonomy/german_taxonomy_v1.yaml` — 8 German error tags (`noun_declension`, `adjective_declension`, `article`, `verb_conjugation`, `verb_tense`, `vocabulary`, `spelling`, `other`)
- [x] [x] [ ] `lang/maps/taxonomy/default.yaml` — 4 language-agnostic tags (`grammar`, `vocabulary`, `spelling`, `other`)
- [x] [x] [ ] `lang/languages/german.yaml` — maps `german` → `cefr_map1` + `german_taxonomy_v1`
- [x] [x] [ ] `tests/lang/test_lang.py` — 34 tests across `TestCEFRMap`, `TestTaxonomyMap`, `TestLanguageConfig`, `TestRegistry` (tmp_path isolation), `TestIntegration` (real YAML files)

### Language Configuration (Session Startup)
> Startup surfaces both language and level configuration together — same moment, same prompt.
- [x] [x] [ ] On session start, call `using_defaults(language)` — if any map is a fallback, print warning, explain which map is missing, point to `lang/languages/` and `lang/maps/`; user can proceed or exit to configure; choice suppresses warning for remainder of session
- [x] [x] [ ] Unit test: `using_defaults()` returns correct flags for configured vs unconfigured language; warning not re-raised after user confirms (`test_lang.py` covers flags; suppression is structural — single call per language per orchestrator instance)

### Orchestrator Skeleton (PoC — cold start only)
- [x] [x] [ ] `orchestrator/orchestrator.py` — implement `OrchestratorProtocol`:
  - [x] [x] [ ] Startup: call `get_interrupted_sessions()`, surface to user if any found
  - [x] [x] [ ] `summarize_progress()` — return `None` if sessions < `cold_start_threshold`
  - [x] [x] [ ] `recommend_exercise()` — if summary is `None`, return `DEFAULT_RECOMMENDATION`
  - [x] [x] [ ] `run_session()` — full 9-step loop (see DESIGN.md):
    - [x] [x] [ ] Step 0: interrupted session check
    - [x] [x] [ ] Steps 1–3: summarize + recommend + user confirmation
    - [x] [x] [ ] Step 4: write-ahead `in_progress` record
    - [x] [x] [ ] Steps 5–6: fulfill `ContextRequest`, call `skill.run()`
    - [x] [x] [ ] Step 7: atomic file write
    - [x] [x] [ ] Step 8–9: update status to `completed`, update DB record
- [x] [x] [ ] `tests/test_orchestrator.py`:
  - [x] [x] [ ] Cold start returns `DEFAULT_RECOMMENDATION` when sessions = 0
  - [x] [x] [ ] Cold start returns `DEFAULT_RECOMMENDATION` when sessions < threshold
  - [x] [x] [ ] Cold start does NOT trigger when sessions >= threshold
  - [x] [x] [ ] Interrupted session detection surfaces correct records
  - [x] [x] [ ] Invalid skill name from LLM falls back to default (mock LLM response)

### `/btw` Command (PoC)
- [x] [x] [ ] `skills/btw_handler/skill.py` — `BtwHandler.answer(question, session_context)` → LLM call with context-aware prompt
- [x] [x] [ ] `skills/btw_handler/prompts.py` — prompt template that injects current skill, topic, and user text so far
- [x] [x] [ ] Word extraction from `/btw` question → `flagged_word` (regex + LLM fallback)
- [x] [x] [ ] Input loop in `WritingModule._collect_input()` detects `/btw` prefix, routes to handler, collects `BtwEntry`, continues session
- [x] [x] [ ] Orchestrator post-session: `storage.write_btw()` for each entry in `result.metadata['btw_entries']`
- [x] [x] [ ] `btw_log` written to session YAML file under `btw_log` key
- [x] [x] [ ] Unit test: `/btw` input detected correctly, session loop continues after answer

### Session Clock (PoC)
- [x] [x] [ ] `started_at` set after topic is displayed (not before); `completed_at` set immediately after submission — measures pure writing time, excludes evaluation pipeline
- [x] [x] [ ] `completed_at` and `duration_minutes` propagated through `ModuleResult` to DB
- [x] [x] [ ] `shared/timer.py` — `SessionTimer`: background thread updates terminal title with `[MM:SS elapsed]`; wired into `WritingModule.run()` (starts after `_print_exercise_header`, stops at submission)

### Negative Vocab List (PoC)
- [x] [x] [x] `vocab_flags` table in `schema.sql`
- [x] [x] [x] `storage.write_vocab_flag()` — insert or increment `occurrence_count` + update `last_seen`
- [x] [x] [x] `storage.get_vocab_flags()` implemented
- [x] [x] [x] Orchestrator post-session: writes vocab flags from `/btw` entries and evaluator `vocabulary` errors
- [x] [x] [x] `ContextRequest.include_vocab_flags` fulfilled by orchestrator, passed into `SkillContext`
- [x] [x] [x] Unit test: `write_vocab_flag()` increments count on duplicate, does not insert new row

### Interruption — Resume / Log / Discard (PoC)
- [x] [x] [ ] Checkpoint file written incrementally during `skill.run()` — each turn appended to `data/checkpoints/{user_id}/{session_id}.json`
- [x] [x] [ ] `status='interrupted'` added to valid status values; schema updated
- [x] [x] [ ] On startup: detect `in_progress` sessions, present resume/log/discard prompt
- [x] [x] [ ] "Log it" path: load transcript → LLM summarize → write partial session file with `status='interrupted'`
- [x] [x] [ ] "Discard" path: delete checkpoint, mark `status='abandoned'`
- [x] [x] [ ] "Resume" path: check `restore_checkpoint()` available on skill; if not, show unavailable message, fall back to log/discard
- [x] [x] [ ] Checkpoint deleted on successful completion, log, or discard
- [x] [x] [ ] Unit test: startup correctly identifies interrupted sessions; all three paths produce correct DB state

### CLI (PoC)
- [x] [x] [ ] `ui/cli.py`:
  - [x] [x] [ ] Startup: load config, initialise storage, check for interrupted sessions
  - [x] [x] [ ] Display orchestrator recommendation with reason
  - [x] [x] [ ] Accept user confirmation or override
  - [x] [x] [ ] Display writing topic + requirements
  - [x] [x] [ ] Accept multi-line user text input (blank line or `/end` to submit)
  - [x] [x] [ ] Display evaluation output (mistakes with explanations, corrected text, recommendations)
  - [x] [x] [ ] Confirm session written (show file path)
- [x] [x] [ ] Manual end-to-end test: run one full session, verify DB row and YAML file written correctly

---

## Layer 1a — Full Evaluator Pipeline

### Steps 1–4 — Detect, Classify, Explain, Correct
- [x] [x] [ ] `skills/detect_mistakes/skill.py` — Step 1: Raw Mistake Detector
  - [x] [x] [ ] Prompt in `skills/detect_mistakes/prompts.py`; CEFR context injected via `lang.loader.get_cefr_context(language, level)`
  - [x] [x] [ ] Returns `list[dict]` with `fragment` and `error_type_hint` fields
  - [x] [x] [ ] Handles empty mistake list and malformed LLM JSON gracefully
- [x] [x] [ ] `skills/classify_mistakes/skill.py` — Step 2: Mistake Classifier
  - [x] [x] [ ] Classifies each mistake with `error_tag` via `lang.loader.get_taxonomy()`; uses `taxonomy.format_for_prompt()` and `taxonomy.validate_tag()` with `TaxonomyError` → `"other"` fallback
  - [x] [x] [ ] Adds `correction` field to each mistake
- [x] [x] [ ] `skills/explain_mistakes/skill.py` — Step 3: Explanation Generator
  - [x] [x] [ ] Adds `explanation` field pitched to user's level; short-circuits gracefully if mistake list is empty
- [x] [x] [ ] `skills/write_correction/skill.py` — Step 4: Correction Writer
  - [x] [x] [ ] Returns `corrected_text`, `recommendations[]`, `comment`; correction derived from structured mistakes, not regenerated freeform
- [x] [x] [ ] `WritingModule._run_pipeline()` wires Steps 1–4; `_build_results()` assembles full `WritingSessionContent`
- [x] [x] [ ] **Writing fixture set** — minimum 3 verified input/output pairs (`tests/fixtures/writing_pairs.json`)
- [x] [x] [ ] `tests/writing/test_writing_pipeline.py` — unit tests for Steps 2, 3, 4 (mocked LLM, offline)
- [x] [x] [ ] `tests/writing/test_writing.py` — unit tests for `WritingModule` helper methods

### Steps 5–6 — Text-Level Estimation & Session Summary
- [x] [x] [ ] `skills/estimate_text_level/skill.py` — Step 5: Text CEFR Estimator
  - [x] [x] [ ] Input: raw user text + writing prompt + user's stated level
  - [x] [x] [ ] Output: `text_level_estimate: str` (CEFR band) or `None` if text is too short
  - [x] [x] [ ] Prompt grounds estimation in CEFR descriptors from `lang/maps/cefr_descriptors/`
- [x] [x] [ ] `skills/summarise_session/writing/skill.py` — Step 6: Session Summariser
  - [x] [x] [ ] Input: user level, text level estimate, explained mistakes (with `error_tag`, `occurrence_count` per tag), writing prompt
  - [x] [x] [ ] Output: `session_summary: str`, `mistakes: list[dict]` enriched with `severity` (`critical` / `expected` / `minor`), `tips: list[str]`, `comparison_note: None`
- [x] [x] [ ] `skills/summarise_session/base.py` — `BaseSummariseSkill`: abstract base for module-specific summarisers; handles LLM call, JSON parsing, common field validation, error fallback
- [x] [x] [ ] Update `WritingSessionContent`: add `severity` to each mistake dict, replace `recommendations: list[str]` with `tips: list[str]`, replace `comment: str` with `session_summary: str`, add `comparison_note: str | None = None`
- [x] [x] [ ] Update `_PipelineResult`; update `_print_evaluation()` to display severity-grouped mistakes and tips
- [x] [x] [ ] Wire Steps 5–6 into `WritingModule._run_pipeline()`
- [x] [x] [ ] Unit tests for Steps 5 and 6 (mocked LLM)

### Steps 1–4 — Judges
- [x] [x] [ ] `tests/judge/judge_detect_mistakes.py` — judge for Step 1 (fragment detection only)
- [x] [x] [ ] `tests/judge/judge_classify_mistakes.py` — judge for Step 2 (error_tag accuracy)
- [x] [x] [ ] `tests/judge/judge_explain_mistakes.py` — judge for Step 3 (explanation quality, semantic)
- [x] [x] [ ] `tests/judge/judge_write_correction.py` — judge for Step 4 (corrected_text vs expected)
- [x] [x] [ ] Run each judge 5× on same fixture; verify variance is acceptable; document threshold

### Steps 5–6 — Judges
- [x] [x] [ ] `tests/judge/judge_summary.py` — judge for Step 6 output (severity accuracy, tip relevance)

---

## PoC — Storage Layer (remaining)

### Memory — Storage Layer (remaining)
- [x] [x] [ ] `memory/sqlite_store.py` — remaining methods:
  - [x] [x] [ ] `get_sessions_by_skill()`
  - [x] [x] [ ] `get_error_frequency()`
  - [x] [x] [ ] `get_recent_topics()`
  - [x] [x] [ ] `get_current_level()` — most recent row from `user_levels`
  - [x] [x] [ ] `write_level()`

---

## Layer 1b — User Personalization + Topic Picker

### User Level Review
- [x] [x] [ ] On startup (or via `/level` CLI command), display current CEFR level from `user_levels` table
- [x] [x] [ ] Prompt user to confirm or override — write override to `user_levels` with `source='stated'`
- [x] [x] [ ] `config.yaml` default level used only if no row exists in `user_levels`
- [x] [x] [ ] Unit test: stated level overrides config default; most recent row returned by `get_current_level()`

### Session History Aggregation
- [x] [x] [ ] `storage.get_session_aggregate()` — structured profile: sessions by skill, recency, recurring errors, recent topics, vocab flag count
- [x] [x] [ ] Convert progress summary logic into `skills/summarize_progress/` (LLM-driven aggregation & analysis)
- [x] [x] [ ] Orchestrator uses `summarize_progress` skill to build progress summary
- [x] [x] [ ] `WritingModule.context_request()` — return full `ContextRequest` (recent 5 writing sessions, error frequency, recent topics, vocab flags)
- [x] [x] [ ] Topic picker receives and uses all three (avoid recent topics, steer toward weak grammar, avoid flagged vocab)
- [x] [x] [ ] Evaluator Step 1 prompt primed with recurring errors from context
- [x] [x] [ ] `suggested_focus` recorded in session file for traceability
- [x] [x] [ ] Unit test: aggregate computed correctly from mixed session history

### Topic Picker + Orchestrator LLM Routing
- [x] [x] [ ] `skills/topic_picker/` — takes level, `suggested_focus`, `recent_topics`; returns `WritingPrompt` dataclass; user can bypass with own topic
- [x] [x] [ ] Progress summary + recommendation prompts live in skills/ (not orchestrator/prompts.py)
- [x] [x] [ ] `Orchestrator.summarize_progress()` — LLM call when sessions >= threshold; validates module against `MODULE_REGISTRY`
- [x] [x] [ ] `Orchestrator.recommend_exercise()` — derives module/reason/suggested_focus from ProgressSummary
- [x] [x] [ ] `tests/fixtures/orchestrator_cases.json` — 4 session history scenarios with expected module and focus
- [x] [x] [ ] `tests/judge/judge_orchestrator.py` — judge for orchestrator recommendation quality (4/4 PASS)
- [x] [x] [ ] Update CLI to display recommendation reason and suggested focus

---

## Orchestrator Refactor (post-1b)

- [x] [x] [ ] Extract `SessionManager(store, config)` — absorbs `_init_write_ahead_log`, `_build_module_context`, `_finalize_session`; `Orchestrator.run_session` delegates to it
- [x] [x] [ ] Break up `_handle_interruption` — currently mixes console I/O, LLM summarisation, checkpoint cleanup, and DB updates in one method; separate concerns into named steps
- [x] [x] [ ] Split `StorageProtocol` into domain-specific sub-protocols: `SessionStore`, `LevelStore`, `BtwLogStore`, `VocabStore`, `ProfileStore` — 23-method kitchen-sink interface cascades bloat to every implementation
- [x] [x] [ ] Add `_hydrate_session_log(row) -> SessionLog` helper to `SQLiteSessionStore` — `SessionLog` reconstruction is duplicated ~5 times across query methods
- [x] [x] [ ] Extract `WritingPipeline` class from `WritingModule._run_pipeline()` — 114-line method sequencing 6 skill calls with error routing and metadata threading; should be its own unit

---

## Layer 1c — Local Frontend

- [x] [x] [ ] Choose framework — Flask
- [x] [x] [ ] `IOHandler` protocol — `prompt()`, `output()` — decouples module I/O from terminal/web
  - [x] [x] [ ] `TerminalIOHandler` — wraps `input()` / `print()`
  - [x] [x] [ ] `WebIOHandler` — queue-based SSE bridge for Flask sessions (`shared/io.py`)
  - [x] [x] [ ] `WritingModule.run()` accepts `IOHandler`; all `input()` / `print()` calls replaced
- [x] [x] [ ] `ui/app.py`:
  - [x] [x] [ ] `/` — chat window: recommendation → confirm → exercise → feedback
  - [x] [x] [ ] `/sessions` — session file browser: lists past sessions by date/skill, renders YAML as readable HTML
  - [x] [x] [ ] `/session/{session_id}` — individual session view
  - [x] [x] [ ] Thin JS for multi-line text input and SSE streaming display
- [x] [x] [ ] Verify runs locally on `localhost` with no external dependencies

---

## LLM Throughput Optimization

- [x] [x] [ ] Investigate writing evaluation latency — per-step profiling via `StepTiming` dataclass; latency log written to `data/logs/skill_latency.jsonl` per session
- [x] [x] [ ] Parallelise independent pipeline steps — steps 1+2 run concurrently, steps 5+6 run concurrently via `ThreadPoolExecutor`; `total_wall_s` recorded in latency log
