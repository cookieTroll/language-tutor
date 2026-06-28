# GermanTutor — Development Checklist

Each item has three progress tracking checkboxes:
`[Impl]` (Implemented - code made) | `[Val]` (Validated - user sign-off) | `[Fin]` (Finished - second sign-off at stage end)
Example: `- [x] [ ] [ ] Item description` (means code is implemented, but not yet validated or finished)

Ordered by layer. Each item is a concrete implementation step. Check off as you go.
Cross-reference `DESIGN.md` for contracts and `TODO.md` for deferred decisions.

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
  - [x] [ ] [ ] `get_sessions_by_skill()`
  - [x] [ ] [ ] `get_error_frequency()`
  - [x] [ ] [ ] `get_recent_topics()`
  - [x] [x] [ ] `get_interrupted_sessions()` — query `in_progress` older than timeout
  - [x] [ ] [ ] `get_current_level()` — most recent row from `user_levels`
  - [x] [ ] [ ] `write_level()`
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
- [ ] [ ] [ ] UI timer widget (Layer 1c — deferred, depends on `IOHandler`)

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
- [ ] [ ] [ ] `tests/judge/judge_detector.py` — judge for Step 1 output quality
- [ ] [ ] [ ] `tests/judge/judge_evaluator.py` — judges for Steps 2, 3, 4 (separate criteria per step)
- [ ] [ ] [ ] Run each judge 5× on same fixture; verify variance is acceptable; document threshold

### Design Research — Error Taxonomy & Feedback Rubrics
> Outputs feed into `lang/maps/taxonomy/`, `lang/maps/cefr_descriptors/`, and evaluator prompts.
- [ ] [ ] [ ] Enrich CEFR descriptor maps — add `lang/maps/cefr_descriptors/german_v1.yaml` with German-specific level descriptions for more accurate text-level estimation (infrastructure in place, content missing)
- [ ] [ ] [ ] Vary error taxonomy by progression level — different tag granularity per CEFR band: coarser at A1/A2 (e.g. `verb_conjugation`), finer at B2/C1 (e.g. `konjunktiv_ii`); implement as additional versioned taxonomy maps
- [ ] [ ] [ ] Define feedback rubrics: dimensions to comment on per session (accuracy, fluency, vocabulary range, task completion, coherence) and at which CEFR levels each becomes relevant
- [ ] [ ] [ ] Decide which rubric dimensions map to `tips[]` vs `session_summary` vs a future `rubric_scores` field
- [ ] [ ] [ ] Document decisions in `docs/writing.md`; propagate to taxonomy maps and evaluator prompts
- [ ] [ ] [ ] Research alternative error taxonomies — compare Weir's framework and SLA classification against current German taxonomy; identify gaps or tags worth adding
- [ ] [ ] [ ] Define per-tag CEFR mastery level — the level at which each error type is expected to be mastered; drives Step 6 severity (`critical` / `expected` / `minor`)
- [ ] [ ] [ ] Evaluate whether taxonomy tags surface to the user directly or are mapped to learner-friendly labels in the UI layer

### Steps 5–6 — Text-Level Estimation & Session Summary
- [x] [x] [ ] `skills/estimate_text_level/skill.py` — Step 5: Text CEFR Estimator
  - [x] [x] [ ] Input: raw user text + writing prompt + user's stated level
  - [x] [x] [ ] Output: `text_level_estimate: str` (CEFR band) or `None` if text is too short
  - [x] [x] [ ] Prompt grounds estimation in CEFR descriptors from `lang/maps/cefr_descriptors/`
- [ ] [ ] [ ] `skills/summarise_session/skill.py` — Step 6: Session Summariser
  - [ ] [ ] [ ] Input: user level, text level estimate, explained mistakes (with `error_tag`), writing prompt
  - [ ] [ ] [ ] Output:
    - `session_summary: str` — holistic contextual comment ("Strong B1 text, approaching B2 range")
    - `mistakes: list[dict]` — explained mistakes enriched with `severity` (`critical` / `expected` / `minor`); severity from gap between user level and per-tag CEFR mastery level (defined in design research)
    - `tips: list[str]` — improvement suggestions sorted by distance from current level (near-level first, aspirational last); not corrections
    - `comparison_note: str | None` — `None` in Layer 1a; filled in by Layer 2b
- [ ] [ ] [ ] Update `WritingSessionContent`: ~~add `text_level_estimate: str | None`~~ (done in Step 5), add `severity` to each mistake dict, replace `recommendations: list[str]` with `tips: list[str]`, replace `comment: str` with `session_summary: str`, add `comparison_note: str | None = None`
- [ ] [ ] [ ] Update `_PipelineResult` to carry Step 5–6 outputs; update `_print_evaluation()` to display text level, severity-grouped mistakes, and tips
- [ ] [ ] [ ] Wire Steps 5–6 into `WritingModule._run_pipeline()`
- [ ] [ ] [ ] Unit tests for Steps 5 and 6 (mocked LLM)
- [ ] [ ] [ ] `tests/judge/judge_summary.py` — judge for Step 6 output (severity accuracy, tip relevance)

---

## Layer 1b — User Personalization + Topic Picker

### User Level Review
- [ ] [ ] [ ] On startup (or via `/level` CLI command), display current CEFR level from `user_levels` table
- [ ] [ ] [ ] Prompt user to confirm or override — write override to `user_levels` with `source='stated'`
- [ ] [ ] [ ] `config.yaml` default level used only if no row exists in `user_levels`
- [ ] [ ] [ ] Unit test: stated level overrides config default; most recent row returned by `get_current_level()`

### Session History Aggregation
- [ ] [ ] [ ] `storage.get_session_aggregate()` — structured profile: sessions by skill, recency, recurring errors, recent topics, vocab flag count
- [ ] [ ] [ ] Convert progress summary logic into `skills/summarize_progress/` (LLM-driven aggregation & analysis)
- [ ] [ ] [ ] Orchestrator uses `summarize_progress` skill to build progress summary
- [ ] [ ] [ ] `WritingModule.context_request()` — return full `ContextRequest` (recent 5 writing sessions, error frequency, recent topics, vocab flags)
- [ ] [ ] [ ] Topic picker receives and uses all three (avoid recent topics, steer toward weak grammar, avoid flagged vocab)
- [ ] [ ] [ ] Evaluator Step 1 prompt primed with recurring errors from context
- [ ] [ ] [ ] `suggested_focus` recorded in session file for traceability
- [ ] [ ] [ ] Unit test: aggregate computed correctly from mixed session history

### Topic Picker + Orchestrator LLM Routing
- [ ] [ ] [ ] `modules/writing/topic_picker.py` — takes level, `suggested_focus`, `recent_topics`; returns `WritingPrompt` dataclass; user can bypass with own topic
- [ ] [ ] [ ] `orchestrator/prompts.py` — progress summary prompt + recommendation prompt
- [ ] [ ] [ ] `Orchestrator.summarize_progress()` — LLM call when sessions >= threshold; validate `weakest_skill` against `MODULE_REGISTRY.keys()`
- [ ] [ ] [ ] `Orchestrator.recommend_exercise()` — LLM call over progress summary; validate `skill` field against registry
- [ ] [ ] [ ] `tests/fixtures/orchestrator_cases.json` — 3–5 session history scenarios with expected recommendations
- [ ] [ ] [ ] `tests/judge/judge_orchestrator.py` — judge for orchestrator recommendation quality
- [ ] [ ] [ ] Update CLI to display recommendation reason and suggested focus

---

## Layer 1c — Local Frontend

- [ ] [ ] [ ] Choose framework — Flask or FastAPI + minimal HTML/JS (single file preferred)
- [ ] [ ] [ ] `IOHandler` protocol — `prompt()`, `output()`, `confirm()` — decouples module I/O from terminal/web
  - [ ] [ ] [ ] `TerminalIOHandler` — wraps `input()` / `print()`
  - [ ] [ ] [ ] `WritingModule.run()` accepts `IOHandler`; all `input()` / `print()` calls replaced
- [ ] [ ] [ ] Move evaluation rendering out of `WritingModule._print_evaluation()` into `TerminalIOHandler` — module returns structured data only (blocked on `IOHandler` above)
- [ ] [ ] [ ] Move `SessionTimer` display into `TerminalIOHandler`; add timer widget in web UI
- [ ] [ ] [ ] `ui/app.py`:
  - [ ] [ ] [ ] `/` — chat window: recommendation → confirm → exercise → feedback
  - [ ] [ ] [ ] `/sessions` — session file browser: lists past sessions by date/skill, renders YAML as readable HTML (not raw YAML)
  - [ ] [ ] [ ] `/session/{session_id}` — individual session view
  - [ ] [ ] [ ] Thin JS for multi-line text input and streaming display if possible
- [ ] [ ] [ ] Verify runs locally on `localhost` with no external dependencies
- [ ] [ ] [ ] Manual test: complete full session via browser, verify session file renders correctly

---

## Layer 2a — Grammar Module

- [ ] [ ] [ ] `modules/grammar/topics/a1_b2_topics.yaml` — curated grammar topic list, reviewed for accuracy
- [ ] [ ] [ ] `GrammarSessionContent` dataclass (subclass of `SessionFileContent`)
- [ ] [ ] [ ] `modules/grammar/selector.py` — picks topic given progress summary + error frequency
- [ ] [ ] [ ] `modules/grammar/dump.py` — comprehensive grammar explanation prompt
- [ ] [ ] [ ] `modules/grammar/explainer.py` — lightweight contextual explainer (utility, not standalone session)
- [ ] [ ] [ ] `modules/grammar/exercises.py` — fill-in, transformation, error correction; validates answers; logs errors with `error_tag`
- [ ] [ ] [ ] `GrammarModule.run()` — selector → dump or exercises → `GrammarSessionContent`
- [ ] [ ] [ ] Register `GrammarModule` in `MODULE_REGISTRY`
- [ ] [ ] [ ] Update orchestrator routing to include grammar
- [ ] [ ] [ ] Wire grammar explainer into writing evaluator Step 3 (inline "why is this wrong?" note)

---

## Layer 2b — Cross-Session Writing Comparison

> Fills in `comparison_note: str | None` introduced as `None` in Layer 1a Step 6.
- [ ] [ ] [ ] `StorageProtocol.get_writing_sessions()` — returns session logs with file paths for writing sessions
- [ ] [ ] [ ] Post-pipeline step: load previous writing session file, generate comparison note
- [ ] [ ] [ ] Populate `WritingSessionContent.comparison_note` (stub introduced in Layer 1a Step 6)
- [ ] [ ] [ ] Update session file viewer to render comparison section when present

---

## Layer 2c — CEFR Estimator

> Complements Step 5 (per-session text-level estimate on raw text). This layer estimates the *user's* accumulated level from session history.
- [ ] [ ] [ ] Define minimum session count before estimation is meaningful (suggest: 5 writing sessions)
- [ ] [ ] [ ] `skills/cefr_estimator/skill.py` — reads session logs (including `text_level_estimate` from Step 5 session files), estimates user level from error frequency + exercise scores + writing complexity trend
- [ ] [ ] [ ] Writes to `user_levels` table with `source='estimated'`
- [ ] [ ] [ ] Expose as on-demand skill (user asks "what level am I?") or post-session trigger
- [ ] [ ] [ ] Decide and document: estimated level vs stated level — suggest only, do not override without user confirmation

---

## Layer 3a — Vocab Skill

- [ ] [ ] [ ] `modules/vocab/word_lists/greetings.yaml` — word, translation, example, difficulty
- [ ] [ ] [ ] `modules/vocab/word_lists/daily_routine.yaml`
- [ ] [ ] [ ] (Optional) `modules/vocab/word_lists/food.yaml`
- [ ] [ ] [ ] Review word lists for accuracy
- [ ] [ ] [ ] `VocabModule.run()` — gap-fill and translation drills from static lists
- [ ] [ ] [ ] `VocabSessionContent` dataclass
- [ ] [ ] [ ] Register in `MODULE_REGISTRY`

---

## Layer 3b — Level Progression Tracking

- [ ] [ ] [ ] Surface level history in frontend: timeline of `user_levels` rows (stated + estimated)
- [ ] [ ] [ ] Orchestrator progress summary includes current level + trend if multiple estimates exist

---

## Layer 3c — Anki Export

- [ ] [ ] [ ] `storage.get_vocab_errors(user_id)` — aggregates `vocabulary`-tagged errors across sessions
- [ ] [ ] [ ] Export as `{word}\t{translation}\t{example}\n` to `data/exports/{user_id}_anki_{date}.txt`
- [ ] [ ] [ ] Surface export option in CLI and frontend
- [ ] [ ] [ ] Document Anki import steps in README

---

## Layer 3d — MCP Server

- [ ] [ ] [ ] Create `ui/mcp_server.py` using `mcp` / `FastMCP`
- [ ] [ ] [ ] Implement `explain_grammar` tool (instantiates and runs the grammar explainer skill)
- [ ] [ ] [ ] Implement `get_vocab_drill` tool (instantiates and runs the vocab drill skill)
- [ ] [ ] [ ] Document running and testing the MCP server in README.md

---

## LLM Throughput Optimization

- [ ] [ ] [ ] Identify and evaluate the LLM inference optimization package (cache efficiency + low-level throughput improvements); assess fit with `llm/` abstraction layer and document findings in `docs/llm_backends.md`
- [ ] [ ] [ ] Investigate `/btw` response latency — measure time from question submission to answer; evaluate whether prompt size, token budget, or the Gemini API cold path is the dominant factor

---

## Capstone Submission

- [ ] [ ] [ ] README — setup instructions, architecture overview, layer status, known limitations
- [ ] [ ] [ ] Kaggle writeup — architecture decisions, design rationale, testing approach, honest PoC scope statement
- [ ] [ ] [ ] Demo video — one complete end-to-end session (≤5 min): startup → recommendation → writing → feedback → file written
- [ ] [ ] [ ] Verify code link is accessible
- [ ] [ ] [ ] Submit before July 7, 11:59 PM PT (= Tuesday July 8, 08:59 AM GMT+2)

---

## CI (post-submission)

- [ ] [ ] [ ] `.github/workflows/ci.yml` — install deps, run `pytest tests/` on every push (unit tests only; exclude `tests/judge/`)
- [ ] [ ] [ ] Document three test tiers in README: unit (CI, mocked), judge (manual, LLM calls), regression (manual, real fixtures)

---

## Submission Schedule

Deadline: **July 7, 11:59 PM PT** = Tuesday July 8, 08:59 AM GMT+2. Target: submit Monday evening.

| Date | Focus |
|---|---|
| Sat June 28 – Fri July 4 | Development — see priority order below |
| Sat July 5 | Final testing; no new features |
| Sun July 6 | Writeup + demo video recording |
| Mon July 7 | Polish, verify submission, **submit** |
| Tue July 8 (morning) | Hard deadline — buffer only |

**Development priority order (7 days):**
1. Steps 5–6 — text-level estimator + session summariser (highest visible impact for demo)
2. User Level Review (Layer 1b) — makes startup flow coherent on video
3. Language Configuration startup check — ~30 min, one if-block
4. README — write alongside development, not at the end

**Cut rule:** if Steps 5–6 are not stable by Wednesday July 2, drop them from demo scope — a clean 4-step evaluator session is a better submission than a shaky 6-step one.

**Sunday tip:** draft the writeup structure and architecture section during development (30 min while code is fresh saves 90 min on Sunday).
