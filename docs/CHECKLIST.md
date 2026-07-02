# GermanTutor — Development Checklist

Each item has three progress tracking checkboxes:
`[Impl]` (Implemented - code made) | `[Val]` (Validated - user sign-off) | `[Fin]` (Finished - second sign-off at stage end)
Example: `- [x] [ ] [ ] Item description` (means code is implemented, but not yet validated or finished)

Ordered by layer. Each item is a concrete implementation step. Check off as you go.
Cross-reference `DESIGN.md` for contracts and `TODO.md` for deferred decisions.
Finished items live in `CHECKLIST_FINISHED.md`.

---

## Layer 1a — Full Evaluator Pipeline

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

### Fluency & Idiomatics (deferred — depends on Layer 1a rubric decisions)
- [ ] [ ] [ ] Define scope: what counts as an idiomatic issue vs a grammar error; which CEFR levels activate this check (suggest B1+)
- [ ] [ ] [ ] `skills/fluency_checker/skill.py` — runs after Step 4 (write_correction); flags unnatural phrasing with natural alternatives; output is a list of `{fragment, suggestion, note}` distinct from `mistakes[]`
- [ ] [ ] [ ] Wire into pipeline between Steps 4 and 6; pass fluency observations to summariser for holistic tip generation
- [ ] [ ] [ ] UI: render fluency observations separately from grammar mistakes (different label, no "correction" implied)
- [ ] [ ] [ ] `tests/judge/judge_fluency_checker.py` — judge for fluency output quality

---

## Layer 1c — Local Frontend


---

## Layer 2a — Grammar Module

> See `docs/grammar.md` for full skill/module design. Split into sub-stages so each is independently reviewable; do 2a-i → 2a-vi before 2a-vii (cross-module bridge) and 2a-viii (UI).

### 2a-iii — Skills
- [x] [x] [ ] `skills/select_grammar/` — outline + `tests/fixtures/select_grammar_cases.json` + `tests/judge/judge_select_grammar.py`
- [x] [x] [ ] Manual topic override — mirrors `WritingModule._pick_topic`'s "Enter your own topic, or press Enter for a suggestion" pattern (`modules/writing/agent.py:102-107`). Module prompts for a free-text topic before calling `select_grammar`; if given, resolve it against `get_grammar_topics(language)` (match a `scope: major` entry for `difficulty`/`related_error_tags`, else treat as an ad hoc `scope: minor` topic at the user's stated level) and skip the `select_grammar` call entirely — same "skip the step when forced" shape as 2a-vii's `forced_recommendation`. No new `ModuleContext` field needed; carried the same way `suggested_focus` already is, via `ctx.parameters`. Implemented as `skills/select_grammar/skill.py::resolve_manual_topic` — pure lookup, no LLM call; the actual "prompt user, call this, skip select_grammar" wiring happens in `modules/grammar/agent.py` (2a-iv)
- [x] [x] [ ] `skills/dump_grammar/` — outline + fixtures + judge
- [x] [x] [ ] `skills/generate_exercises/` — outline (exercise types, `grading` field, `correct_answer`/`accepted_answers`); validate each generated `error_tag` against `TaxonomyMap.validate_tag()` with `call_with_self_correction` retry (same as `classify_mistakes` does for writing) — an unvalidated hallucinated tag would silently corrupt `error_frequency`/`select_grammar` downstream + fixtures + judge. Exercise type vocabulary (name/grading/description) lives in `lang/maps/exercise_types/default.yaml`, loaded via `lang.loader.get_exercise_types(language)` — not hardcoded in the skill
- [x] [x] [ ] `skills/grade_exercises/` — outline: batched call covers *all* wrong answers regardless of grading mode (LLM judgment for `grading: llm` items, feedback-only phrasing for already-known-wrong `grading: exact` items) — replaces the separate `explain_grammar` utility for this path entirely; + fixtures + judge
- [x] [x] [ ] ~~`skills/explain_grammar/`~~ — dropped from 2a scope; `grade_exercises` absorbs its only required use. Move to Backlog in `docs/grammar.md` as a possible future standalone utility. Fix stale claim in `docs/LAYERS.md:101` ("already built in Layer 1a" — it was never built; `explain_mistakes` is a different skill) — both already done: Backlog entry exists in `docs/grammar.md`, `docs/LAYERS.md:106` already states the corrected history

### 2a-iv — Module
- [x] [x] [ ] `modules/grammar/agent.py` — `context_request()`; `run()`: **pick topic (manual override or `select_grammar`)** → dump → generate → display block → collect block → partition exact/llm → validate (Python) + grade (one batched `grade_exercises` call) → log errors → score → `GrammarSessionContent`. `ModuleResult.metadata` carries only `{btw_entries}` — `score`/`topic` are not duplicated there, they're already typed fields on `GrammarSessionContent` and grammar sessions produce no `vocab_signals`. Blank answers are resolved deterministically in Python (never sent to `grade_exercises` — a blank answer is unambiguously wrong, and the model was observed marking one "correct" when it was included in a batch)
- [x] [x] [ ] `modules/grammar/skills.py` — skill injection
- [x] [x] [ ] ~~`modules/grammar/module.md`~~ — dropped: not parsed by any code (confirmed `writing` has no equivalent file either); pure duplication of the class body and `docs/grammar.md`'s own module spec section
- [x] [x] [ ] Answer-block parsing (split by newline, pad/truncate to exercise count) — own test item, this is the fragile part
- [x] [x] [ ] `tests/unit/test_grammar.py` — module loop logic (partitioning, string-normalize compare, block parsing), no LLM
- [x] [x] [ ] `tests/fixtures/grammar_cases.json` + `tests/judge/judge_grammar_module.py` (mirrors `judge_orchestrator.py`)
- [x] [x] [ ] `shared/error_log.py` — `log_skill_error()` for skill call failures (not originally scoped, added while debugging judge-test flakiness); wired into every `out.success is False` branch across both `modules/grammar/` and `modules/writing/` (agent + pipeline), so any future skill failure — real or test-flake — leaves a diagnosable record in `data/logs/skill_errors.jsonl` instead of being silently discarded

> 2a-v and 2a-vi are complete — see `docs/CHECKLIST_FINISHED.md`.

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

### 2a-viii — UI (after 2a-i…vii work end-to-end via CLI)
- [ ] [ ] [ ] `ui/static/app.js` + `ui/templates/index.html` — exercise display panel + block-answer textarea + results rendering
- [ ] [ ] [ ] `ui/templates/session.html` — render `GrammarSessionContent` (explanation, exercises, score) + `next_actions` if present (session *history* view)
- [ ] [ ] [ ] Live "Start grammar practice now?" prompt in the *active* session UI (`index.html`/`app.js`) — the interactive accept/decline surfaced right after a writing session ends when `next_actions` is non-empty; distinct from the history-view rendering above, and what the 2a-vii "web `/api/start`" caller change assumes exists

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

- [ ] [ ] [ ] `/add_vocab <word>` CLI command — lets user manually flag a word mid-session; module appends it to `vocab_signals` in `ModuleResult.metadata` (same path as `/btw`-flagged words); `SessionManager.finalize_session` then calls `write_vocab_flag()` — module stays storage-free, memory boundary stays in orchestrator
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

## Engineering Tooling (post-submission)

### CI
- [ ] [ ] [ ] `.github/workflows/ci.yml` — install deps, run `pytest tests/unit/` on every push
- [ ] [ ] [ ] Document three test tiers in README: unit (CI, mocked), judge (manual, LLM calls), regression (manual, real fixtures)

### Static Analysis & Linting
- [ ] [ ] [ ] Add `mypy` to `requirements.txt`; run `mypy` in CI — enforce typed contracts that are currently declared but not checked (skill parameter dicts, Pydantic model shapes, Protocol implementations)
- [ ] [ ] [ ] Add `ruff` for linting + formatting; add `pyproject.toml` with config; run in CI pre-test step

### Structured Logging
- [ ] [ ] [ ] Replace `print()` debug/diagnostic output with a lightweight logger writing to `data/logs/`; keep user-facing `print()` calls in `ui/` only
- [ ] [ ] [ ] Log LLM call metadata per skill invocation: model, latency, token count (where available) — enables cost/latency tracking without changing skill interfaces

### Prompt Versioning
- [ ] [ ] [ ] Add a `PROMPT_VERSION` constant to each skill's `prompts.py`; write it into `SkillOutput.metadata` and session YAML
- [ ] [ ] [ ] Judge fixtures record the prompt version used — stale fixtures (version mismatch) are flagged at judge run time rather than silently producing wrong baselines

### Cross-Module Recommendation Routing (generalize beyond 2 modules)
- [ ] [ ] [ ] `SessionManager._compute_next_actions()` (`orchestrator/session_manager.py`) currently dispatches next-action signals with a hardcoded `if module_key == "writing": ... elif module_key == "grammar": ...` — fine for 2 modules, but won't scale once Layer 3a (vocab) or a future reading module exist: writing plausibly wants to route to *both* grammar and vocab, grammar back to writing *or* vocab, vocab likely only to writing. Replace with an N-module routing table/registry *inside* `SessionManager` — keep cross-module knowledge centralized there rather than pushing a `compute_next_actions` hook onto `ModuleProtocol` itself (that would force e.g. `WritingModule` to import grammar's `get_grammar_topics`/tag shape directly, and every other module's shape too — N×M coupling across modules that otherwise don't know of each other, worse than today's `if/elif`). Trigger: do this when the third module (most likely vocab, Layer 3a) is actually implemented, not before

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
