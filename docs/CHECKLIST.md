# GermanTutor — Development Checklist

Each item has three progress tracking checkboxes:
`[Impl]` (Implemented - code made) | `[Val]` (Validated - user sign-off) | `[Fin]` (Finished - second sign-off at stage end)
Example: `- [x] [ ] [ ] Item description` (means code is implemented, but not yet validated or finished)

Ordered by layer. Each item is a concrete implementation step. Check off as you go.
Cross-reference `DESIGN.md` for contracts and `TODO.md` for deferred decisions.
Finished items live in `CHECKLIST_FINISHED.md`.

---

## PoC

### Memory — Storage Layer (remaining)
- [x] [x] [ ] `memory/sqlite_store.py` — remaining methods:
  - [x] [ ] [ ] `get_sessions_by_skill()`
  - [x] [ ] [ ] `get_error_frequency()`
  - [x] [ ] [ ] `get_recent_topics()`
  - [x] [ ] [ ] `get_current_level()` — most recent row from `user_levels`
  - [x] [ ] [ ] `write_level()`

---

## Layer 1a — Full Evaluator Pipeline

### Steps 1–4 — Judges
- [x] [ ] [ ] `tests/judge/judge_detect_mistakes.py` — judge for Step 1 (fragment detection only)
- [x] [ ] [ ] `tests/judge/judge_classify_mistakes.py` — judge for Step 2 (error_tag accuracy)
- [x] [ ] [ ] `tests/judge/judge_explain_mistakes.py` — judge for Step 3 (explanation quality, semantic)
- [x] [ ] [ ] `tests/judge/judge_write_correction.py` — judge for Step 4 (corrected_text vs expected)
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

### Steps 5–6 — Judges
- [ ] [ ] [ ] `tests/judge/judge_summary.py` — judge for Step 6 output (severity accuracy, tip relevance)

### Fluency & Idiomatics (deferred — depends on Layer 1a rubric decisions)
- [ ] [ ] [ ] Define scope: what counts as an idiomatic issue vs a grammar error; which CEFR levels activate this check (suggest B1+)
- [ ] [ ] [ ] `skills/fluency_checker/skill.py` — runs after Step 4 (write_correction); flags unnatural phrasing with natural alternatives; output is a list of `{fragment, suggestion, note}` distinct from `mistakes[]`
- [ ] [ ] [ ] Wire into pipeline between Steps 4 and 6; pass fluency observations to summariser for holistic tip generation
- [ ] [ ] [ ] UI: render fluency observations separately from grammar mistakes (different label, no "correction" implied)
- [ ] [ ] [ ] `tests/judge/judge_fluency_checker.py` — judge for fluency output quality

---

## Layer 1b — User Personalization + Topic Picker

### User Level Review
- [x] [x] [ ] On startup (or via `/level` CLI command), display current CEFR level from `user_levels` table
- [x] [x] [ ] Prompt user to confirm or override — write override to `user_levels` with `source='stated'`
- [x] [x] [ ] `config.yaml` default level used only if no row exists in `user_levels`
- [x] [x] [ ] Unit test: stated level overrides config default; most recent row returned by `get_current_level()`

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

## Orchestrator Refactor (post-1b)

- [ ] [ ] [ ] Extract `SessionManager(store, config)` — absorbs `_init_write_ahead_log`, `_build_module_context`, `_finalize_session`; `Orchestrator.run_session` delegates to it

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
1. ~~Steps 5–6~~ — done
2. User Level Review (Layer 1b) — makes startup flow coherent on video
3. README — write alongside development, not at the end

**Cut rule:** if Steps 5–6 are not stable by Wednesday July 2, drop them from demo scope — a clean 4-step evaluator session is a better submission than a shaky 6-step one.

**Sunday tip:** draft the writeup structure and architecture section during development (30 min while code is fresh saves 90 min on Sunday).
