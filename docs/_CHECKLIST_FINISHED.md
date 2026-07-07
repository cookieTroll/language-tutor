# Wharf the Language Tutor — Finished Work

Items with at least two sign-offs (Validated + optionally Finished). Pulled from `_CHECKLIST.md` as sections complete.

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
- [x] [x] [ ] Checkpoint file written incrementally during `skill.run()` — each turn appended to `data/checkpoints/{user_id}/{session_id}.json`. **Correction, found 2026-07-05:** this was checked off prematurely — the file is created empty and neither `WritingModule` nor `GrammarModule` ever appends to it. The "Log it" summary path this feeds still works, just always off an empty transcript. Tracked as a post-submission fix in `docs/CHECKLIST.md`, not re-opened here since sign-off already happened and the historical record should show that, not erase it.
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

### Design Research — Error Taxonomy & Feedback Rubrics
- [x] [x] [ ] Evaluate whether taxonomy tags surface to the user directly or are mapped to learner-friendly labels in the UI layer — resolved: raw `error_tag` values (`verb_conjugation`, etc.) now go through `shared/humanize.py::humanize_tag()` (underscore→space, title case) at every render/display site (`TerminalIOHandler`/`WebIOHandler` in `shared/io.py`, plus a `humanize_tag` Jinja filter used in `session.html`/`sessions.html`) rather than being stored or re-derived per site. `weak_tags`/`strong_tags` needed no change — `orchestrator/mastery.py` already resolves those to full taxonomy descriptions or grammar topic names, not raw tag keys

### Steps 2, 3, 4, 5, 6 — Detect, Verify, Classify, Explain, Correct
- [x] [x] [ ] `skills/detect_mistakes/skill.py` — Step 2: Raw Mistake Detector
  - [x] [x] [ ] Prompt in `skills/detect_mistakes/prompts.py`; CEFR context injected via `lang.loader.get_cefr_context(language, level)`
  - [x] [x] [ ] Returns `list[dict]` with `fragment` and `error_type_hint` fields
  - [x] [x] [ ] Handles empty mistake list and malformed LLM JSON gracefully
- [x] [x] [ ] `skills/verify_mistakes/skill.py` — Step 3: Mistake Verifier (added after the original 1a build; see judge-test note below)
  - [x] [x] [ ] Prompt in `skills/verify_mistakes/prompts.py`; re-checks each raw fragment from Step 2 against its original sentence context and drops false positives (Step 2 judges the whole text in one pass and can misjudge a fragment — e.g. correct verb-second inversion — in isolation)
  - [x] [x] [ ] Registered in `modules/writing/skills.py`; wired into `WritingPipeline` (`modules/writing/pipeline.py`) between `detect_mistakes` and `classify_mistakes`
  - [x] [x] [ ] Unit test coverage in `tests/unit/writing/test_writing_pipeline.py`
- [x] [x] [ ] `skills/classify_mistakes/skill.py` — Step 4: Mistake Classifier
  - [x] [x] [ ] Classifies each mistake with `error_tag` via `lang.loader.get_taxonomy()`; uses `taxonomy.format_for_prompt()` and `taxonomy.validate_tag()` with `TaxonomyError` → `"other"` fallback
  - [x] [x] [ ] Adds `correction` field to each mistake
- [x] [x] [ ] `skills/explain_mistakes/skill.py` — Step 5: Explanation Generator
  - [x] [x] [ ] Adds `explanation` field pitched to user's level; short-circuits gracefully if mistake list is empty
- [x] [x] [ ] `skills/write_correction/skill.py` — Step 6: Correction Writer
  - [x] [x] [ ] Returns `corrected_text`, `recommendations[]`, `comment`; correction derived from structured mistakes, not regenerated freeform
- [x] [x] [ ] `WritingModule._run_pipeline()` wires Steps 2–6; `_build_results()` assembles full `WritingSessionContent`
- [x] [x] [ ] **Writing fixture set** — minimum 3 verified input/output pairs (`tests/fixtures/writing_pairs.json`)
- [x] [x] [ ] `tests/unit/writing/test_writing_pipeline.py` — unit tests for Steps 3, 4, 5, 6 (mocked LLM, offline)
- [x] [x] [ ] `tests/unit/writing/test_writing.py` — unit tests for `WritingModule` helper methods

### Steps 1, 7 — Text-Level Estimation & Session Summary
- [x] [x] [ ] `skills/estimate_text_level/skill.py` — Step 1: Text CEFR Estimator
  - [x] [x] [ ] Input: raw user text + writing prompt + user's stated level
  - [x] [x] [ ] Output: `text_level_estimate: str` (CEFR band) or `None` if text is too short
  - [x] [x] [ ] Prompt grounds estimation in CEFR descriptors from `lang/maps/cefr_descriptors/`
- [x] [x] [ ] `skills/summarise_session/writing/skill.py` — Step 7: Session Summariser
  - [x] [x] [ ] Input: user level, text level estimate, explained mistakes (with `error_tag`, `occurrence_count` per tag), writing prompt
  - [x] [x] [ ] Output: `session_summary: str`, `mistakes: list[dict]` enriched with `severity` (`critical` / `expected` / `minor`), `tips: list[str]`, `comparison_note: None`
- [x] [x] [ ] `skills/summarise_session/base.py` — `BaseSummariseSkill`: abstract base for module-specific summarisers; handles LLM call, JSON parsing, common field validation, error fallback
- [x] [x] [ ] Update `WritingSessionContent`: add `severity` to each mistake dict, replace `recommendations: list[str]` with `tips: list[str]`, replace `comment: str` with `session_summary: str`, add `comparison_note: str | None = None`
- [x] [x] [ ] Update `_PipelineResult`; update `_print_evaluation()` to display severity-grouped mistakes and tips
- [x] [x] [ ] Wire Steps 1, 7 into `WritingModule._run_pipeline()`
- [x] [x] [ ] Unit tests for Steps 1 and 7 (mocked LLM)

### Steps 2, 3, 4, 5, 6 — Judges
- [x] [x] [ ] `tests/judge/judge_detect_mistakes.py` — judge for Step 2 (fragment detection only)
- [x] [x] [ ] `tests/judge/judge_verify_mistakes.py` — judge for Step 3 (false-positive filtering accuracy — added alongside the `verify_mistakes` skill itself)
- [x] [x] [ ] `tests/judge/judge_classify_mistakes.py` — judge for Step 4 (error_tag accuracy)
- [x] [x] [ ] `tests/judge/judge_explain_mistakes.py` — judge for Step 5 (explanation quality, semantic)
- [x] [x] [ ] `tests/judge/judge_write_correction.py` — judge for Step 6 (corrected_text vs expected)
- [x] [x] [ ] Run each judge 5× on same fixture; verify variance is acceptable; document threshold

### Steps 1, 7 — Judges
- [x] [x] [ ] `tests/judge/judge_summary.py` — judge for Step 7 output (severity accuracy, tip relevance)

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

## Orchestrator Refactor (post-1b)

- [x] [x] [ ] Move `WritingModule._print_evaluation()` to `IOHandler` layer — `TerminalIOHandler.render_evaluation(data)` handles terminal formatting; `WebIOHandler.render_evaluation(data)` emits SSE event; removes `hasattr(io, "data")` guard
- [x] [x] [ ] Move `SessionTimer` into `TerminalIOHandler.start_timer/stop_timer`; `WebIOHandler` stubs are no-ops (JS manages web timer)

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
- [x] [x] [ ] Manual test: complete full session via browser, verify session file renders correctly

---

## LLM Throughput Optimization

- [x] [x] [ ] Investigate writing evaluation latency — per-step profiling via `StepTiming` dataclass; latency log written to `data/logs/skill_latency.jsonl` per session
- [x] [x] [ ] Parallelise independent pipeline steps — steps 1+2 run concurrently, steps 5+6 run concurrently via `ThreadPoolExecutor`; `total_wall_s` recorded in latency log

---

## Layer 2a — Grammar Module

### 2a-i — Contracts & schema
- [x] [x] [ ] `GrammarSessionContent` — update in `memory/protocols.py` and `docs/contracts.md` (kept in sync): `topic`, `scope`, `explanation`, `items` (`prompt`, `exercise_type`, `grading`, `user_answer`, `correct_answer`, `correct`, `feedback`, `error_tag`), `score`, `btw_log`. `items` holds *every* exercise, correct and incorrect alike, each explicitly tagged via `correct: bool` — not just the misses (more useful for later session browsing, mirrors why the writing session file keeps full `corrected_text` rather than just a diff list)
- [x] [x] [ ] `errors.module` column — `memory/schema.sql`, populate in `write_session()`, simplify `get_error_frequency()`'s module-filter branch to a flat `WHERE` instead of the `sessions` JOIN
- [x] [x] [ ] `lang/maps/grammar_topics/` map type — `lang/models.py` (new `GrammarTopicsMap`), `lang/loader.py` (`get_grammar_topics()` + cross-validation, same pattern as `taxonomy`/`cefr_hints`), `lang/languages/german.yaml` gets `grammar_topics: german_a1_b2` key. Wired now against a small seed file (`lang/maps/grammar_topics/german_a1_b2.yaml`, 5 hand-picked topics) — 2a-ii replaces it with the full reviewed Goethe curriculum compilation
- [x] [x] [ ] `TerminalIOHandler` — multi-line `prompt()` variant (read until blank line) so the CLI can collect a block answer; `WebIOHandler` needs no change (already returns one opaque string per `send_input()`)

### 2a-ii — Grammar topics content
- [x] [x] [x] `lang/maps/grammar_topics/german_a1_b2.yaml` — curated major topics compiled from Goethe Institut A1–B2 curriculum, `scope: major`, `related_error_tags` cross-checked against `lang/maps/taxonomy/german_taxonomy_v1.yaml`; review for accuracy before use

### 2a-iii — Skills
- [x] [x] [ ] `skills/select_grammar/` — outline + `tests/fixtures/select_grammar_cases.json` + `tests/judge/judge_select_grammar.py`
- [x] [x] [ ] Manual topic override — mirrors `WritingModule._pick_topic`'s "Enter your own topic, or press Enter for a suggestion" pattern (`modules/writing/agent.py:102-107`). Module prompts for a free-text topic before calling `select_grammar`; if given, resolve it against `get_grammar_topics(language)` (match a `scope: major` entry for `difficulty`/`related_error_tags`, else treat as an ad hoc `scope: minor` topic at the user's stated level) and skip the `select_grammar` call entirely — same "skip the step when forced" shape as 2a-vii's `forced_recommendation`. No new `ModuleContext` field needed; carried the same way `suggested_focus` already is, via `ctx.parameters`. Implemented as `skills/select_grammar/skill.py::resolve_manual_topic` — pure lookup, no LLM call; the actual "prompt user, call this, skip select_grammar" wiring happens in `modules/grammar/agent.py` (2a-iv)
- [x] [x] [ ] `skills/dump_grammar/` — outline + fixtures + judge
- [x] [x] [ ] `skills/generate_exercises/` — outline (exercise types, `grading` field, `correct_answer`/`accepted_answers`); validate each generated `error_tag` against `TaxonomyMap.validate_tag()` with `call_with_self_correction` retry (same as `classify_mistakes` does for writing) — an unvalidated hallucinated tag would silently corrupt `error_frequency`/`select_grammar` downstream + fixtures + judge. Exercise type vocabulary (name/grading/description) lives in `lang/maps/exercise_types/default.yaml`, loaded via `lang.loader.get_exercise_types(language)` — not hardcoded in the skill
- [x] [x] [ ] `skills/grade_exercises/` — outline: batched call covers *all* wrong answers regardless of grading mode (LLM judgment for `grading: llm` items, feedback-only phrasing for already-known-wrong `grading: exact` items) — replaces the separate `explain_grammar` utility for this path entirely; + fixtures + judge
- [x] [x] [ ] ~~`skills/explain_grammar/`~~ — dropped from 2a scope; `grade_exercises` absorbs its only required use. Move to Backlog in `docs/grammar.md` as a possible future standalone utility. Fix stale claim in `docs/LAYERS.md:101` ("already built in Layer 1a" — it was never built; `explain_mistakes` is a different skill) — both already done: Backlog entry exists in `docs/grammar.md`, `docs/LAYERS.md:106` already states the corrected history

### 2a-iv — Module
- [x] [x] [ ] `modules/grammar/agent.py` — `context_request()`; `run()`: **pick topic (manual override or `select_grammar`)** → dump → generate → display block → collect block → partition exact/llm → validate (Python) + grade (one batched `grade_exercises` call) → log errors → score → `GrammarSessionContent`. Blank answers are resolved deterministically in Python (never sent to `grade_exercises` — a blank answer is unambiguously wrong, and the model was observed marking one "correct" when it was included in a batch). **Revised 2026-07-04**: `/btw` support was removed entirely (its answer had nowhere visible to render in the web UI — the tutor panel is hidden throughout grammar sessions — so it silently didn't work); `run()` now loops — each round generates one batch of a single exercise type (see `generate_exercises`, also revised the same day to constrain to one type per call instead of mixing 2-3), grades it, and asks the user whether to do another round on the same topic or end. All rounds' items/errors are pooled into one `GrammarSessionContent`. `ModuleResult.metadata` is now always `{}` (previously carried `{btw_entries}`). `generate_exercises`'s "one type per batch" is prompt-requested but not model-trusted — live testing against the local `gemma2-9b` model showed it ignoring the instruction (one exercise per type across several types in a single response), so the skill now defensively keeps only the exercises matching the first one's type and drops the rest, regardless of what the model returns
- [x] [x] [ ] `modules/grammar/skills.py` — skill injection
- [x] [x] [ ] ~~`modules/grammar/module.md`~~ — dropped: not parsed by any code (confirmed `writing` has no equivalent file either); pure duplication of the class body and `docs/grammar.md`'s own module spec section
- [x] [x] [ ] Answer-block parsing (split by newline, pad/truncate to exercise count) — own test item, this is the fragile part
- [x] [x] [ ] `tests/unit/test_grammar.py` — module loop logic (partitioning, string-normalize compare, block parsing), no LLM
- [x] [x] [ ] `tests/fixtures/grammar_cases.json` + `tests/judge/judge_grammar_module.py` (mirrors `judge_orchestrator.py`)
- [x] [x] [ ] `shared/error_log.py` — `log_skill_error()` for skill call failures (not originally scoped, added while debugging judge-test flakiness); wired into every `out.success is False` branch across both `modules/grammar/` and `modules/writing/` (agent + pipeline), so any future skill failure — real or test-flake — leaves a diagnosable record in `data/logs/skill_errors.jsonl` instead of being silently discarded

### 2a-v — Registry & orchestrator wiring
- [x] [x] [ ] Register `GrammarModule` in `MODULE_REGISTRY`
- [x] [x] [ ] Confirm `get_registry_description()` picks it up automatically (iterates the registry — confirmed free, no changes needed)
- [x] [x] [ ] Confirm orchestrator routing / `recommend_exercise` works generically via registry validation, or needs a prompt update — confirmed generic: `SUMMARIZE_PROGRESS_PROMPT` takes `{modules}` as a formatted list, `ExerciseRecommendation.module`/`ProgressSummary.weakest_module` are plain `str` (not `Literal["writing"]`), `write_file()` (`memory/protocols.py:230`) is fully generic via `content.to_dict()` — no prompt or code changes needed

### 2a-vi — Writing module fix (independent of grammar module — can happen anytime)
- [x] [x] [ ] Thread `pipeline.explained_mistakes` / `corrected_text` / `tips` / `session_summary` into `_handle_btw`'s `session_context` (`modules/writing/agent.py:90` → `_follow_up_phase` → `_handle_btw:222-228`) — currently only `user_text_so_far` is passed, so post-evaluation `/btw` answers about "why is this wrong" aren't grounded in the actual structured mistake data already shown to the user. `_handle_btw` takes a new `pipeline: PipelineResult | None = None` param (`None` for the pre-evaluation call site in `_collect_input`, the real pipeline for the post-evaluation call in `_follow_up_phase`); `skills/btw_handler/skill.py`'s new `_format_evaluation_context()` renders it into `BTW_PROMPT`'s new `{evaluation_context}` placeholder, and the prompt now explicitly says to ground "why is this wrong?" answers in it
- [x] [x] [ ] Test: extend `tests/unit/test_writing.py` (or wherever `_handle_btw` is covered) to assert `session_context` includes the evaluation fields once a pipeline result exists — regression guard against this silently reverting. Added in `tests/unit/writing/test_writing.py`: `test_handle_btw_includes_evaluation_context_after_pipeline`, `test_handle_btw_without_pipeline_omits_evaluation_context`, and `TestFormatEvaluationContext` for the formatting helper directly

### 2a-vii — Cross-module bridge: writing ↔ grammar (depends on 2a-i…v; needs a short design pass, not a drop-in item)
- [x] [x] [ ] `NextActionSignal(module, reason, suggested_focus)` — new model in `memory/protocols.py` (kept separate from `orchestrator.protocols.ExerciseRecommendation` to respect the memory→orchestrator dependency direction, despite the shape overlap)
- [x] [x] [ ] `SessionFileContent.next_actions: list[NextActionSignal] = []` — on the *base* class in `memory/protocols.py` + `docs/contracts.md`, so any module can populate it later, not just writing
- [x] [x] [ ] `SessionManager.finalize_session()` (`orchestrator/session_manager.py:105`) — add an `error_frequency: dict[str, int]` parameter (the same dict `build_module_context()` already fetched at session start via `ctx.error_frequency`, not re-queried) so the standing aggregate is available alongside `result`/`file_content`. Before the existing `write_file()` call at line 116: gate the suggestion on *both* signals — `result.errors` used only as a cheap existence check ("did any tag from this session map to a grammar topic at all?"), `error_frequency` used as the actual judgment ("is that tag already recurring, freq ≥ 2, per `SessionAggregate.recurring_errors`'s existing threshold — not a one-off?"). Only set `file_content.next_actions` when both hold. Keeps the raw per-mistake log (`result.errors`) and the recommendation judgment (`error_frequency`) as separate inputs — one triggers, the other decides — rather than deriving the suggestion straight from the raw log. Confirmed intentional: `ctx.error_frequency` for a writing session is fetched with `module_filter="writing"` (`WritingModule.context_request()`), so the recurrence gate is writing-scoped by design, not a cross-module aggregate — keep it that way, don't "fix" it to be cross-module later. Implemented as `SessionManager._compute_next_actions()`, using `lang.loader.get_grammar_topics()` to check whether *any* curated topic's `related_error_tags` contains the recurring tag — existence check only, does not resolve or promise a specific topic (see precision note below and `docs/grammar.md` Backlog: taxonomy fan-out means a tag like `verb_tense` matches 12 topics with no level-aware way to pick one; `suggested_focus` carries the raw tag, and `select_grammar` does the real topic pick when the module runs)
- [x] [x] [ ] Reverse direction, grammar → writing: `SessionManager._grammar_mastery_signal()` — after a grammar session scoring >= `GRAMMAR_MASTERY_THRESHOLD` (0.8, tunable), suggest a writing session with `suggested_focus` set to the actual topic *name* (not a tag — unlike the writing→grammar direction, `WritingModule._pick_topic` already consumes `ctx.parameters["suggested_focus"]` as a soft phrase ("try to practise: ...") in the topic-picker prompt, so naming the specific topic here carries no broken-promise risk the way naming a grammar topic would). `SessionManager._compute_next_actions()` is now the dispatcher: routes to `_writing_error_recurrence_signal()` for `module_key == "writing"`, `_grammar_mastery_signal()` for `module_key == "grammar"`, `[]` otherwise
- [x] [x] [ ] `run_session(forced_recommendation: ExerciseRecommendation | None = None)` — when set, skip steps 2–4 (summarize_progress → recommend_exercise → confirm) and go straight to write-ahead with the forced recommendation
- [x] [x] [ ] Orchestrator: after `finalize_session()` returns, if `file_content.next_actions` is non-empty, prompt via `IOHandler` ("Session complete. Start {module} practice on '{focus}' now? This will begin a new session. [Y/n]" — module-agnostic wording so it reads correctly for either direction)
- [x] [x] [ ] `NextActionSignal.accepted: bool | None = None` — records the user's Y/n answer. `finalize_session()` writes the session file *before* the prompt is shown (the prompt is interactive and lives in `orchestrator.py`, never in `SessionManager`, which only ever informs via `io.output`), so the answer can't be baked into that write. Added `SessionManager.record_next_action_decision(file_content, accepted)` — a small follow-up rewrite of the same file via the existing `store.write_file()`, called from `orchestrator.py` right after the prompt resolves, before deciding whether to return the forced recommendation
- [x] [x] [ ] Caller changes: `ui/cli.py`'s `while True` loop done — on accept, re-invokes `run_session()` with `forced_recommendation` set instead of showing the normal "start another session?" prompt. Web `/api/start` deliberately **not** wired: `app.js`'s `handlePrompt()` shows no input box for any prompt while `inWritingPhase` is true (it assumes it's always the bare `>` writing-line prompt), so this Y/n prompt would hang a live web session with no way to answer until 2a-viii adds dedicated UI for it — confirmed with user, deferred to 2a-viii
- [x] [x] [ ] Design only for one signal now; data model (`list[NextActionSignal]`) and control flow already support multiple — only the confirmation UI (pick one of N vs. yes/no) would need extending later, not the underlying shape. **Known limitation, flagged but not addressed**: `_compute_next_actions()`'s per-module dispatch (`if module_key == "writing": ... elif module_key == "grammar": ...`) is a hardcoded 1:1 pairing that won't scale once Layer 3a (vocab) or a future reading module exist — writing plausibly wants to route to *both* grammar and vocab, grammar back to writing *or* vocab, vocab likely only to writing. Revisit as an N-module routing table *inside* `SessionManager` once a third module lands (keeps cross-module knowledge centralized, same invariant `MODULE_REGISTRY`/`recommend_exercise` already rely on — every other module stays ignorant of its siblings). Deliberately **not** a per-module `compute_next_actions` hook on `ModuleProtocol`: that would require e.g. `WritingModule` to import grammar's `get_grammar_topics`/tag shape directly, and a vocab module's shape too once it exists — N×M coupling across modules that don't otherwise know of each other, worse than the current `if/elif`, not better. Not worth generalizing for two modules either way
- [x] [x] [ ] Test: `tests/unit/test_orchestrator.py` — unit-tests for both directions' gates in isolation (writing→grammar: tag present but not recurring → no signal; recurring but absent from session → no signal; both present → signal set. grammar→writing: score below/at `GRAMMAR_MASTERY_THRESHOLD`) plus a dispatcher test confirming `_compute_next_actions()` routes by `module_key` and returns `[]` for an unrecognized module
- [x] [x] [ ] Added beyond original scope, while manually verifying 2a-viii in a browser: `tests/e2e/seed_helpers.py` (`seed_recurring_error()` — writes an active profile + N completed sessions carrying a given error tag through the real `StorageProtocol`, defaulting to `config.test.yaml`'s isolated `data_root` so it never touches real dev data) and `tests/e2e/test_bridge_smoke.py` — a fully automated, real-LLM CLI smoke test that seeds a recurring `verb_conjugation` error, reproduces it in a live writing session, accepts the resulting chaining prompt, and asserts a grammar session actually starts within the same process. Manual-run tier only (`pytest tests/e2e/ -v -s`), same as `test_smoke.py` — not part of the CI/unit suite. Extended further: `seed_writing_session()`/`seed_sample_writing_history()` in the same file seed *realistic* completed writing sessions (real German text, varied topics) from `tests/longer texts/`, for exercising `topic_picker`'s recent-topic avoidance, `recommend_exercise`'s aggregate stats, and the session history view with real content instead of synthetic placeholders — CLI: `python tests/e2e/seed_helpers.py writing-history --user-id ...`

### 2a-viii — UI (after 2a-i…vii work end-to-end via CLI)
- [x] [x] [ ] `ui/static/app.js` + `ui/templates/index.html` — exercise display panel + block-answer textarea + results rendering. Answer collection stays a flat block-answer textarea (matches `GrammarModule`'s single `io.prompt_block()` call, including inline `/btw` lines parsed server-side before grading) rather than per-exercise input boxes — considered and deliberately deferred as UI polish, see `docs/grammar.md` Backlog. **Revised 2026-07-04**: `/btw` inline parsing removed entirely (see 2a-iv); added a "Preparing exercises…"/"Evaluating…" loading-indicator pattern reused from the writing eval-overlay, an intra-session "Another exercise on this topic?" continuation prompt (own custom widget, not the block-answer textarea), and a `phase='loading'` state distinct from `phase='writing'` so an early Submit click during exercise generation can't be read as a blank answer. Grammar-specific JS (`handleExercisesReady`, `handleGrammarResultsComplete`, `showGrammarAgainPrompt`, `resetGrammarForNextRound`) actually lives in its own `ui/static/grammar-ui.js`, loaded alongside `app.js` in `index.html` — not inline in `app.js` as originally written here
- [x] [x] [ ] `ui/templates/session.html` — render `GrammarSessionContent` (explanation, exercises, score). Separately, render `next_actions` **generically** for *any* session type when present — `next_actions` lives on the `SessionFileContent` base class (`memory/protocols.py`), not `GrammarSessionContent` specifically, so a writing session that triggered a writing→grammar signal must show it too, not just grammar sessions (session *history* view)
- [x] [x] [ ] Live "Start {module} practice on '{focus}' now?" prompt in the *active* session UI (`index.html`/`app.js`) — module-agnostic wording matching the now-bidirectional bridge (2a-vii): surfaced after *either* a writing or a grammar session ends when `next_actions` is non-empty, not just after writing. Distinct from the history-view rendering above, and what the 2a-vii "web `/api/start`" caller change assumes exists
- [x] [x] [ ] Test: `tests/unit/test_ui.py` — `TerminalIOHandler`/`WebIOHandler` tests for new `render_exercises`/`render_results` methods (terminal output byte-identical to prior `GrammarModule` behavior; web SSE payload shape for `exercises_ready`/`grammar_results_complete`); a `/api/start` route test (patched `Orchestrator`) confirming the `forced_recommendation` chaining loop calls `run_session` again instead of ending, mirroring `test_cli_chains_forced_recommendation_without_reprompting` from 2a-vii; a `session.html` render test for a grammar-shaped fixture including `next_actions`. `TestJSSyntax`'s existing `node --check` on `app.js` already covers new JS syntax automatically — no new test needed there

---

## Layer 2b — Writing History Summary

> Supersedes the original "cross-session comparison" framing: not a per-session diff against
> the immediately-previous session, and not automatically attached to every session file.
> Instead, an on-demand `/history` command (typed at the existing "Start this module? [Y/n]"
> prompt in `orchestrator.py::_get_confirmed_module`, same interaction shape as `/btw`) that
> reports on writing history at whatever depth the user asks for — topics covered, recurring
> mistakes, and a CEFR-level trend. Nothing is persisted to any session file; the report is
> regenerated each time it's requested. Drops the `WritingSessionContent.comparison_note`
> stub from Layer 1a Step 6 — nothing will ever populate it under this design, so the field
> and its forced-`None` guard in `skills/summarise_session/base.py` are removed rather than
> left dead.
- [x] [x] [ ] `SessionLog.text_level_estimate: str | None` — new field (`memory/protocols.py`), the one schema addition this layer needed; everything else (topics, recurring-mistake counts) is built in Python from `get_sessions_by_module()`'s existing return value — `get_session_aggregate()` wasn't reused here since it aggregates all-time with no count/day bound, and `/history` needs a bounded window. No new `StorageProtocol` surface. Populated in `SessionManager.finalize_session()` from `file_content.text_level_estimate` (`getattr` fallback — only `WritingSessionContent` carries it). Threaded through both backends: `json_store.py` (write + all three `SessionLog`-constructing reads) and `sqlite_store.py` (`schema.sql` column + idempotent `ALTER TABLE ... ADD COLUMN` guard in `_init_db()` for pre-existing local DBs, since `CREATE TABLE IF NOT EXISTS` alone won't add a column to an already-created table — verified against a simulated pre-migration DB)
- [x] [x] [ ] Remove `WritingSessionContent.comparison_note` and `PipelineResult.comparison_note` (`modules/writing/pipeline.py`, `modules/writing/agent.py`), the forced-`None` guard + `_defaults()` doc line in `skills/summarise_session/base.py`, and the corresponding prompt field/JSON-schema line in `skills/summarise_session/writing/prompts.py` + `skill.py`. Updated the now-affected tests in `tests/unit/writing/test_writing.py` and `test_writing_pipeline.py`, including deleting the now-meaningless `test_forces_comparison_note_to_none`
- [x] [x] [ ] `skills/summarize_writing_history/` — new skill (own `skill.py` + `prompts.py`, no shared base needed — only writing consumes it). Input: pre-aggregated topics list, recurring-mistake tag counts, and a chronological level-estimate trend (already computed in Python from filtered `SessionLog`s, not raw session objects — mirrors how `SummarizeProgressSkill` takes a pre-built `SessionAggregate.model_dump()` rather than raw rows) plus a scope label (e.g. "last 10 sessions" / "last 30 days"). Output: one readable `history_summary` string. + `tests/fixtures/summarize_writing_history_cases.json` + `tests/judge/judge_summarize_writing_history.py`
- [x] [x] [ ] `orchestrator.py::_get_confirmed_module()` — needs `user_id`/`language` threaded in (currently only takes `recommendation`); wraps its prompt in a loop that recognizes `/history`, `/history <n>` (session count), and `/history <n>d` (days) before falling through to the normal `[Y/n]` handling. History depth is a parameter, not a hardcoded literal buried inline: no argument falls back to a module-level `DEFAULT_HISTORY_SESSIONS = 10` constant in `orchestrator.py`, matching the existing `RECURRING_ERROR_THRESHOLD` / `GRAMMAR_MASTERY_THRESHOLD` pattern in `orchestrator/session_manager.py`. An explicit `<n>` or `<n>d` argument always overrides the default. Filters `store.get_sessions_by_module(user_id, language, "writing")` (status `"completed"` only) by count or by date cutoff, builds the three inputs above, calls the new skill, prints the result via `io.output()`, then re-prompts. `log_skill_error()` on the skill's `out.success is False` branch, matching every other skill call site. No output is written back to any session file. Empty-history case ("no writing sessions yet") and a malformed argument both short-circuit before the LLM call
- [x] [x] [ ] Test: `tests/unit/test_orchestrator.py` — `_parse_history_scope` (default/count/days/invalid), `_handle_history_command` (invalid arg, no-history case, aggregation correctness incl. the recurring-mistake threshold and chronological level trend, days-window filtering, skill-failure logging), and `_get_confirmed_module`'s loop (confirms `/history` re-prompts and the normal `[Y/n]` path is unaffected) — each its own control-flow branch, not a fixed-up existing test
- [x] [x] [ ] Updated `docs/contracts.md` (`SessionLog` + `WritingSessionContent` schema blocks), `docs/writing.md`, `docs/DESIGN.md`, `docs/LAYERS.md`, `docs/TODO.md` — all previously described the old per-session `comparison_note` design

---

## Layer 2c — Level & Progress

> Merges the original Layer 2c (CEFR Estimator) and Layer 3b (Level Progression Tracking) into
> one build: both turned out to be different renderings of the same underlying mastery data, not
> independent features — see `docs/_TODO.md` for how this was resolved. Complements Step 5
> (per-session `text_level_estimate` on raw text) by aggregating it, and other per-session
> signals, into a user-level view.
>
> Explicitly dropped: a fixed "N texts to reach the next level" or "N words to reach the next
> level" threshold sourced from external research. Checked both — exam boards (Goethe, telc)
> publish per-text word-count *targets* (e.g. telc B1 ≈ 100–120 words), and vocabulary-size
> research gives a lemma-count gap per level (~1,500 words known, Milton's CEFR vocabulary-breadth
> monograph), but no published source gives a cumulative writing-output volume or text count
> needed to progress a level — for either metric, this looks like a genuine gap in the literature,
> not a search miss. Word/text counts are shown as flavor stats on the progress bar, not used as
> the level-up gate.

- [x] [x] [ ] `word_count: int` field on `WritingSessionContent` / `SessionLog` (`memory/protocols.py`) — computed once at submission from `user_text` (same computation already used by the live `/word_count` command, `modules/writing/agent.py:203`). Threaded through both backends the same way `text_level_estimate` was in Layer 2b: `json_store.py` (write + all `SessionLog`-constructing reads) and `sqlite_store.py` (`schema.sql` column + idempotent `ALTER TABLE ... ADD COLUMN` guard in `_init_db()`)
- [x] [x] [ ] `get_module_mastery(user_id, language, module)` (`orchestrator/mastery.py`) — grammar: `topics_total`/`topics_mastered` scoped to the curated topics *for the user's current level* (score ≥ `GRAMMAR_MASTERY_THRESHOLD`), weak tags from `get_error_frequency(module="grammar")`; writing: `texts_written` (completed session count), same weak/strong tag lookup (grammar error tags surface during writing too — same tag space); both: `total_words`, `words_at_current_level` (sum of `word_count` filtered to `sessions.level == user_profiles.level`). Also added `SessionLog.score` (grammar sessions) and `shared/slugify.py::slugify_topic` (shared between `modules/grammar/agent.py`'s `task_label` and mastery's topic matching — task_label is a slug, curated topic names aren't, so both sides must slugify identically)
- [x] [x] [ ] Weak/strong tag → human label: reuse `get_taxonomy(language)` / `get_grammar_topics(language)` (`lang/loader.py`, the same functions the MCP server's `get_error_taxonomy`/`get_grammar_topic_list` wrap) — don't duplicate the lookup
- [x] [x] [ ] `get_level_trend(user_id, language, module="writing")` (`orchestrator/mastery.py`) — chronological `[(date, text_level_estimate)]` pulled directly from `sessions.text_level_estimate` (Layer 2b field); no new computation, no LLM call
- [x] [x] [ ] Define minimum session count before estimation is meaningful — `TEXTS_PER_LEVEL_FOR_MASTERY = 25` (`orchestrator/mastery.py`), caps writing's mastery_ratio at 1.0 once 25 completed sessions *at the user's current level* are reached
- [x] [x] [ ] `skills/cefr_estimator/skill.py` — the level-up decision is a threshold crossing on `get_module_mastery`'s mastery ratio (~`GRAMMAR_MASTERY_THRESHOLD`, i.e. structured coverage), not a separate blended heuristic over multiple fuzzy signals; `get_level_trend` is informational only, shown alongside rather than folded into the gate. Suggests only (`should_level_up`, `next_level` in metadata) — the caller (`Orchestrator._handle_progress_command`) confirms with the user before calling `store.write_level(..., source="estimated")` — no `user_levels` table exists or is needed (see `docs/memory.md`)
- [x] [x] [ ] Decide and document: estimated level vs stated level — suggest only, do not override `user_profiles.level` without user confirmation (see `Orchestrator._handle_progress_command`'s `[Y/n]` prompt before `write_level`)
- [x] [x] [ ] UI: progression bar per module — fill % = mastery ratio from `get_module_mastery`, weak/strong topic chips, word-count flavor stats (`total_words`, `words_at_current_level`); trend sparkline from `get_level_trend`. Rendering goes through `IOHandler.render_progress(data)` (`shared/io.py`) — same "orchestrator gathers data, IOHandler renders" split as `render_evaluation`/`render_exercises`/`render_results`, so CLI and web UI share one data shape: `TerminalIOHandler` draws ASCII bars, `WebIOHandler` forwards a `progress_ready` SSE event to `ui/static/progress-ui.js`, which renders a conic-gradient dial per module (`#cmd-sidebar`-adjacent `.dial`/`.dial-wrap` CSS in `ui/templates/index.html`) plus weak/strong tag chips and the trend sparkline
- [x] [x] [ ] Expose `cefr_estimator` as on-demand skill via `/progress` command — same interaction shape as the existing `/history` command (`Orchestrator._handle_progress_command`, wired in `_get_confirmed_module`'s prompt loop, and in `CMD_HINTS.setup` in `ui/static/app.js` for the web UI's command sidebar)

---

## Layer 3d — MCP Server

- [x] [x] [ ] `memory/protocols.py` — add `StorageProtocol.get_session_by_id(session_id)` (no existing way to look up a single session directly — only "recent N" or "by module") and `list_users()` (distinct user_ids); implemented in both `sqlite_store.py` and `json_store.py`
- [x] [x] [ ] `ui/mcp_server.py` — FastMCP server (`mcp` package, stdio transport), built on the same `build_storage(config)` the CLI/UI already use; `LTUT_CONFIG` env var override matches `ui/app.py`'s pattern
- [x] [x] [ ] Memory-backed tools: `list_users`, `list_languages`, `get_progress` (wraps `get_session_aggregate` + current level), `list_sessions`, `get_session` (single session detail, ownership-checked), `get_recurring_errors`, `get_vocab_flags`, `export_writing_history` (compiles completed writing sessions into one text blob — returns text directly rather than writing to `data/exports/`, to keep the server strictly read-only)
- [x] [x] [ ] `get_session`/`export_writing_history` reuse the path-traversal guard already used by `ui/app.py`'s `/sessions/<path:rel_path>` route when reading a session YAML file directly off disk
- [x] [x] [ ] Reference-data tools over `lang/loader.py` (no user data, no LLM calls): `get_error_taxonomy(language)` (tag → description, for interpreting `get_recurring_errors` output) and `get_grammar_topic_list(language)` (curated topics + difficulty + related error tags, for cross-referencing against recurring errors)
- [x] [x] [ ] `tests/unit/test_mcp_server.py` — seeded-storage fixture exercising every tool (progress defaults to active language, ownership check on `get_session`, days/count filtering on `export_writing_history`, taxonomy/topic lookups); `tests/unit/test_storage.py` — `get_session_by_id`/`list_users` on both backends
- [x] [x] [ ] Document running and testing the MCP server in README.md

---

## Language Generation & Configurability

### Generation Utility
> The `lang/` package was already architected to be language-agnostic — a new target
> language is just new content files in the same shape, no loader/model changes needed.
> This utility closes the gap between "architecturally possible" and "actually usable"
> by generating that content via LLM instead of requiring it to be hand-authored.
- [x] [x] [ ] `lang/generate.py` — `generate_taxonomy` / `generate_cefr_hints` / `generate_grammar_topics`, each validated via the existing Pydantic models (`TaxonomyMap` / `CEFRMap` / `GrammarTopicsMap`) through `skills.protocols.call_with_self_correction`; `write_language_assets()` writes all four files and re-validates end-to-end via a fresh `lang.loader._Registry` pointed at the real `lang/maps`/`lang/languages` directories — reuses the exact cross-reference validation `lang/loader.py` already runs at import time instead of duplicating it
- [x] [x] [ ] `lang/generate_prompts.py` — prompt templates for the three generators (compact inlined example, not the full German file, to keep token cost sane)
- [x] [x] [ ] `scripts/generate_language.py` — CLI entry (`python -m scripts.generate_language <language>`), wires config/LLM the same way `ui/cli.py::main` does; refuses to overwrite an existing `lang/languages/{name}.yaml` without `--force`
- [x] [x] [ ] `lang/loader.py::is_configured()` + `orchestrator._check_language_config` + `ui/cli.py::_language_config_warning` — when a user picks a language with no config file at all, tell them it needs generating (and how) instead of silently falling back to generic defaults
- [x] [x] [ ] `tests/unit/lang/test_generate.py` — mocked-LLM coverage: happy-path parse/validate per generator, self-correction retry when a generated grammar topic references an unknown taxonomy tag, round-trip through a fresh `_Registry` at `tmp_path`

Czech (`lang/languages/czech.yaml` + maps) was generated with this utility and
spot-checked at a high level by a native Czech speaker (the author). The remaining
manual-smoke-test item (an end-to-end grammar session run in the generated language)
was later validated by the author — see the Pre-Submission section below.

---

## Pre-Submission (Capstone)

Validated by the author 2026-07-07. Moved wholesale from `_CHECKLIST.md`'s
Pre-Submission section — see that file's history for the original suggested-order
rationale.

- [x] [x] [ ] README rewrite/expansion — setup instructions, architecture overview, layer status, known limitations
- [x] [x] [x] Fix `docs/img/content_pipeline.jpg` when image-gen quota resets (~4h): wire both Skills and Orchestrator arrows from `_Registry` (not from map tiles directly); remove Skills↔Orchestrator connection (runtime relationships live on architecture diagram)
- [x] [x] [ ] Re-verify `docs/competitive_landscape.md`'s claims before relying on them (the doc's own note: competitor products change, written 2026-07-05) — validated by author's word; no updated date stamp or diff found in the doc itself as of this tick
- [x] [x] [ ] Confirm the "couple of cents per exercise" `gemini-2.5-flash` figure with an actual per-request token/cost estimate rather than a rounded gut number — validated by author's word; no computed figure found in `docs/_KAGGLE_WRITEUP.md` or elsewhere as of this tick
- [x] [x] [ ] Kaggle writeup draft against the pre-submission word budget (`docs/_KAGGLE_WRITEUP.md`)
- [x] [x] [ ] Demo video recorded per the pre-submission beat list (`vids/intro.mp4`)
- [x] [x] [ ] Manual smoke test: generate a real second language against a live LLM, inspect the output, run one grammar session end-to-end in that language — Czech generated live and spot-checked by a native speaker; author confirms the end-to-end session step is now done, though no new session file was found in the repo as of this tick
- [x] [x] [ ] Verify code link is accessible
