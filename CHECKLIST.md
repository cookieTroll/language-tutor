# GermanTutor — Development Checklist

Ordered by layer. Each item is a concrete implementation step. Check off as you go.
Cross-reference `DESIGN.md` for contracts and `TODO.md` for deferred decisions.

---

## PoC

### Repo & Config
- [ ] Create repo, add `DESIGN.md`, `TODO.md`, `CHECKLIST.md`, `.gitignore` (`data/`, `.env`, `__pycache__`)
- [ ] `requirements.txt` — `google-generativeai`, `pyyaml`, `pytest`, minimum deps only for now
- [ ] `config.yaml` — `data_root`, `default_level`, `cold_start_threshold`, `interruption_timeout_minutes`, `storage_backend` (`sqlite` | `json`)
- [ ] Config loader with basic validation (required fields present, storage_backend is valid value)

### Contracts / Protocols
- [ ] `memory/protocols.py` — `SessionLog`, `SessionFileContent` (abstract base + `to_dict()`), `WritingSessionContent`, `StorageProtocol`
- [ ] `skills/protocols.py` — `ContextRequest`, `SkillContext`, `SkillResult`, `SkillProtocol`
- [ ] `orchestrator/protocols.py` — `ProgressSummary`, `ExerciseRecommendation`, `OrchestratorProtocol`
- [ ] Verify all dataclasses have type annotations; no untyped fields

### Memory — Storage Layer
- [ ] `memory/schema.sql` — `sessions` table (including `status`, `started_at`), `errors` table, `user_levels` table
- [ ] `memory/sqlite_store.py` — implement `StorageProtocol`:
  - [ ] `write_session()` — insert or update sessions row
  - [ ] `write_file()` — serialize `SessionFileContent.to_dict()` to YAML, write to temp path, atomic rename, return relative path
  - [ ] `update_session_status()` — update status field, validate against allowed values
  - [ ] `get_recent_sessions()`
  - [ ] `get_sessions_by_skill()`
  - [ ] `get_error_frequency()`
  - [ ] `get_recent_topics()`
  - [ ] `get_interrupted_sessions()` — query `in_progress` older than timeout
  - [ ] `get_current_level()` — most recent row from `user_levels`
  - [ ] `write_level()`
- [ ] `memory/json_store.py` — same interface, JSON file backend for dev/test
- [ ] `data/sessions/`, `data/summaries/`, `data/checkpoints/` directories created by store on first run

### Storage Unit Tests
- [ ] `tests/test_storage.py`:
  - [ ] Write session → read back → assert all fields equal (SQLite and JSON store)
  - [ ] `get_error_frequency()` aggregates correctly across multiple sessions
  - [ ] `update_session_status()` transitions correctly; rejects invalid status
  - [ ] `get_interrupted_sessions()` returns only `in_progress` records older than timeout
  - [ ] `get_recent_topics()` returns correct n most recent, filtered by skill
  - [ ] Atomic write: no `.tmp` file exists after successful write
  - [ ] Relative file path resolves correctly against `data_root`
  - [ ] `get_current_level()` returns most recent row when multiple exist

### Skill Registry
- [ ] `skills/registry.py` — `MODULE_REGISTRY` dict, `get_registry_description()`
- [ ] `modules/writing/__init__.py`, `modules/writing/skill.py` — stub `WritingModule` implementing `SkillProtocol` (returns hardcoded result for now)
- [ ] `tests/test_registry.py`:
  - [ ] All registered skills implement `SkillProtocol` (check for required attributes and methods)
  - [ ] `get_registry_description()` includes all registry keys

### Error Taxonomy
- [ ] `modules/writing/taxonomy.py` — `ERROR_TAXONOMY` set, `validate_error_tag(tag)` function
- [ ] `tests/test_taxonomy.py`:
  - [ ] Validator accepts all defined tags
  - [ ] Validator rejects unknown tag, raises with informative message

### Orchestrator Skeleton (PoC — cold start only)
- [ ] `orchestrator/orchestrator.py` — implement `OrchestratorProtocol`:
  - [ ] Startup: call `get_interrupted_sessions()`, surface to user if any found
  - [ ] `summarize_progress()` — return `None` if sessions < `cold_start_threshold`
  - [ ] `recommend_exercise()` — if summary is `None`, return `DEFAULT_RECOMMENDATION`
  - [ ] `run_session()` — full 9-step loop (see DESIGN.md):
    - [ ] Step 0: interrupted session check
    - [ ] Steps 1–3: summarize + recommend + user confirmation
    - [ ] Step 4: write-ahead `in_progress` record
    - [ ] Steps 5–6: fulfill `ContextRequest`, call `skill.run()`
    - [ ] Step 7: atomic file write
    - [ ] Step 8–9: update status to `completed`, update DB record
- [ ] `tests/test_orchestrator.py`:
  - [ ] Cold start returns `DEFAULT_RECOMMENDATION` when sessions = 0
  - [ ] Cold start returns `DEFAULT_RECOMMENDATION` when sessions < threshold
  - [ ] Cold start does NOT trigger when sessions >= threshold
  - [ ] Interrupted session detection surfaces correct records
  - [ ] Invalid skill name from LLM falls back to default (mock LLM response)

### `/btw` Command (PoC)
- [ ] `skills/btw/handler.py` — `BtwHandler.answer(question, session_context)` → LLM call with context-aware prompt
- [ ] `skills/btw/prompts.py` — prompt template that injects current skill, topic, and user text so far
- [ ] Word extraction from `/btw` question → `flagged_word` (regex + LLM fallback)
- [ ] Input loop in `skill.run()` detects `/btw` prefix, routes to handler, collects `BtwEntry`, continues session
- [ ] Orchestrator post-session: `storage.write_btw()` for each entry in `result.metadata['btw_entries']`
- [ ] `btw_log` written to session YAML file under `btw_log` key
- [ ] Unit test: `/btw` input detected correctly, session loop continues after answer

### Session Clock (PoC)
- [ ] `started_at` set in write-ahead record (already present)
- [ ] `completed_at` set by orchestrator immediately after `skill.run()` returns
- [ ] `duration_minutes` computed and stored in DB
- [ ] `SkillResult` carries `started_at`, `completed_at`, `duration_minutes`
- [ ] CLI: background thread displays `[MM:SS elapsed]` updating every second during session
- [ ] UI (Layer 1c): timer widget in session header

### Negative Vocab List (PoC)
- [ ] `vocab_flags` table in `schema.sql`
- [ ] `storage.write_vocab_flag()` — insert or increment `occurrence_count` + update `last_seen`
- [ ] `storage.get_vocab_flags()` implemented
- [ ] Orchestrator post-session: writes vocab flags from `/btw` entries and evaluator `vocabulary` errors
- [ ] `ContextRequest.include_vocab_flags` fulfilled by orchestrator, passed into `SkillContext`
- [ ] Unit test: `write_vocab_flag()` increments count on duplicate, does not insert new row

### Session History Aggregation (Layer 1b)
- [ ] `storage.get_session_aggregate()` or equivalent — returns structured profile (sessions by skill, recency, time, recurring errors, recent topics, vocab flag count)
- [ ] Orchestrator uses aggregate as input to progress summary LLM prompt
- [ ] Writing skill `ContextRequest` requests error_frequency, recent_topics, vocab_flags
- [ ] Topic picker receives and uses all three (avoid recent topics, steer toward weak grammar, avoid flagged vocab)
- [ ] Evaluator Step 1 prompt primed with recurring errors from context
- [ ] `suggested_focus` recorded in session file for traceability
- [ ] Unit test: aggregate computed correctly from mixed session history

### Interruption — Resume/Log/Discard (PoC)
- [ ] Checkpoint file written incrementally during `skill.run()` — each turn appended to `data/checkpoints/{user_id}/{session_id}.json`
- [ ] `status='interrupted'` added to valid status values; schema updated
- [ ] On startup: detect `in_progress` sessions, present resume/log/discard prompt
- [ ] "Log it" path: load transcript → LLM summarize → write partial session file with `status='interrupted'`
- [ ] "Discard" path: delete checkpoint, mark `status='abandoned'`
- [ ] "Resume" path: check `restore_checkpoint()` available on skill; if not, show unavailable message, fall back to log/discard
- [ ] Checkpoint deleted on successful completion, log, or discard
- [ ] Unit test: startup correctly identifies interrupted sessions; all three paths produce correct DB state
- [ ] `modules/writing/detector.py` — Step 1: Raw Mistake Detector
  - [ ] Prompt template in `modules/writing/prompts.py`
  - [ ] Calls Gemini, parses JSON response
  - [ ] Returns `list[dict]` with `fragment` and `error_type_hint` fields
  - [ ] Handles empty mistake list (no errors found)
  - [ ] Handles malformed LLM JSON response gracefully
- [ ] `WritingSessionContent` — PoC version: populate `user_text` and raw `mistakes` only; other fields stubbed
- [ ] `WritingModule.run()` — wire detector into skill, return `(SkillResult, WritingSessionContent)` with hardcoded topic

### CLI (PoC)
- [ ] `ui/cli.py`:
  - [ ] Startup: load config, initialise storage, check for interrupted sessions
  - [ ] Display orchestrator recommendation with reason
  - [ ] Accept user confirmation or override
  - [ ] Display hardcoded writing topic + requirements
  - [ ] Accept multi-line user text input (blank line or sentinel to submit)
  - [ ] Display raw mistake list from detector
  - [ ] Confirm session written (show file path)
- [ ] Manual end-to-end test: run one full session, verify DB row and YAML file written correctly

---

## Layer 1a — Full Evaluator Pipeline

- [ ] `modules/writing/processor.py` — Step 2: Mistake Processor
  - [ ] Takes raw mistakes from Step 1
  - [ ] Classifies each with `error_tag` from `ERROR_TAXONOMY`
  - [ ] Calls `validate_error_tag()` on each output tag; rejects/flags unknowns
  - [ ] Adds `correction` field to each mistake
- [ ] `modules/writing/feedback.py` — Step 3: Feedback Generator
  - [ ] Takes classified mistakes from Step 2
  - [ ] Adds `explanation` field pitched to user's level
  - [ ] Short-circuits gracefully if mistake list is empty
- [ ] `modules/writing/corrector.py` — Step 4: Correction Writer
  - [ ] Takes user text + classified mistakes from Step 2
  - [ ] Returns `corrected_text`, `recommendations[]`, `comment`
  - [ ] Correction derived from structured mistakes, not regenerated freeform
- [ ] Wire all four steps in `WritingModule.run()`, populate full `WritingSessionContent`
- [ ] Update CLI to display full structured feedback (mistakes with explanations, corrected text, recommendations)
- [ ] **Create writing fixture set** (see TODO.md) — minimum 3 verified pairs before judge testing
- [ ] `tests/judge/judge_detector.py` — judge for Step 1 output
- [ ] `tests/judge/judge_evaluator.py` — judges for Steps 2, 3, 4 (separate criteria per step)
- [ ] Run each judge 5x on same fixture; verify variance is acceptable; document threshold
- [ ] `tests/fixtures/writing_pairs.json` — at least 3 manually verified pairs

---

## Layer 1b — Topic Picker + Orchestrator LLM Routing

- [ ] `modules/writing/topic_picker.py`
  - [ ] Takes level, suggested_focus, recent_topics (from `ContextRequest`), optional user overrides
  - [ ] Returns `WritingPrompt` dataclass
  - [ ] User can bypass: provide own topic → topic picker skipped
  - [ ] Prompt in `modules/writing/prompts.py`
- [ ] `WritingModule.context_request()` — return full `ContextRequest` (recent 5 writing sessions, error frequency, recent topics)
- [ ] `orchestrator/prompts.py` — progress summary prompt + recommendation prompt
- [ ] `Orchestrator.summarize_progress()` — LLM call when sessions >= threshold
  - [ ] Parse JSON response
  - [ ] Validate `weakest_skill` against `MODULE_REGISTRY.keys()`; fall back to default if invalid
  - [ ] Return `ProgressSummary`
- [ ] `Orchestrator.recommend_exercise()` — LLM call over progress summary
  - [ ] Parse and validate response
  - [ ] Validate `skill` field against registry
- [ ] `tests/fixtures/orchestrator_cases.json` — 3–5 session history scenarios with expected recommendations
- [ ] `tests/judge/judge_orchestrator.py` — judge for orchestrator recommendation quality
- [ ] Update CLI to display recommendation reason and suggested focus

---

## Layer 1c — Local Frontend

- [ ] Choose framework — Flask or FastAPI + minimal HTML/JS (single file preferred for simplicity)
- [ ] `ui/app.py`:
  - [ ] `/` — chat window: displays session flow (recommendation → confirm → exercise → feedback)
  - [ ] `/sessions` — session file browser: lists past sessions by date/skill, renders YAML as readable HTML (not raw YAML)
  - [ ] `/session/{session_id}` — individual session view
  - [ ] Thin JS for multi-line text input and streaming display if possible
- [ ] Verify runs locally on `localhost` with no external dependencies
- [ ] Manual test: complete full session via browser, verify session file renders correctly

---

## Layer 2a — Grammar Module

- [ ] `modules/grammar/topics/a1_b2_topics.yaml` — curated grammar topic list, reviewed for accuracy
- [ ] `GrammarSessionContent` dataclass (subclass of `SessionFileContent`)
- [ ] `modules/grammar/selector.py` — picks topic from list given progress summary + error frequency
- [ ] `modules/grammar/dump.py` — comprehensive grammar explanation prompt
- [ ] `modules/grammar/explainer.py` — lightweight contextual explainer (utility, not standalone session)
- [ ] `modules/grammar/exercises.py` — exercise generator (fill-in, transformation, error correction)
  - [ ] Validates user answers
  - [ ] Logs errors with `error_tag` from taxonomy
- [ ] `GrammarModule.run()` — selector → dump or exercises → `GrammarSessionContent`
- [ ] Register `GrammarModule` in `MODULE_REGISTRY`
- [ ] Update orchestrator routing to include grammar
- [ ] Wire grammar explainer into writing evaluator Step 3 (inline "why is this wrong?" note)

---

## Layer 2b — Cross-Session Writing Comparison

- [ ] `StorageProtocol.get_writing_sessions()` — returns session logs with file paths for writing sessions
- [ ] `WritingSessionContent` — add `comparison_to_previous` field (optional, `None` if no prior session)
- [ ] Update `Corrector` (Step 4) or add a Step 5: load previous writing session file, generate comparison note
- [ ] Update session file viewer to render comparison section when present

---

## Layer 2c — CEFR Estimator

- [ ] Define minimum session count before estimation is meaningful (suggest: 5 writing sessions)
- [ ] `skills/cefr/estimator.py` — reads session logs, estimates level from error frequency + exercise scores + writing complexity
- [ ] Writes to `user_levels` table with `source='estimated'`
- [ ] Expose as on-demand skill (user asks "what level am I?") or post-session trigger
- [ ] Decide and document: estimated level vs stated level — suggest only, do not override without user confirmation

---

## Layer 3a — Vocab Skill

- [ ] `modules/vocab/word_lists/greetings.yaml` — word, translation, example, difficulty
- [ ] `modules/vocab/word_lists/daily_routine.yaml`
- [ ] (Optional) `modules/vocab/word_lists/food.yaml`
- [ ] Review word lists for accuracy
- [ ] `VocabModule.run()` — gap-fill and translation drills from static lists
- [ ] `VocabSessionContent` dataclass
- [ ] Register in `MODULE_REGISTRY`

---

## Layer 3b — Level Progression Tracking

- [ ] Surface level history in frontend: timeline of `user_levels` rows (stated + estimated)
- [ ] Orchestrator progress summary includes current level + trend if multiple estimates exist

---

## Layer 3c — Anki Export

- [ ] Evaluator flags unknown/misused vocabulary words during feedback (add `vocabulary` tag to taxonomy — already present)
- [ ] `storage.get_vocab_errors(user_id)` — aggregates `vocabulary`-tagged errors across sessions
- [ ] Export as `{word}\t{translation}\t{example}\n` format to `data/exports/{user_id}_anki_{date}.txt`
- [ ] Surface export option in CLI and frontend
- [ ] Document Anki import steps in README

---

## Capstone Submission

- [ ] README — setup instructions, architecture overview, layer status, known limitations
- [ ] Kaggle writeup — architecture decisions, design rationale, testing approach, honest PoC scope statement
- [ ] Demo video — one complete end-to-end session (≤5 min): startup → recommendation → writing → feedback → file written
- [ ] Verify code link is accessible
- [ ] Submit before June 30, 11:59 PM PT
