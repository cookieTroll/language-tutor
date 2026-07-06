# Wharf the Language Tutor — Development Checklist

Each item has three progress tracking checkboxes:
`[Impl]` (Implemented - code made) | `[Val]` (Validated - user sign-off) | `[Fin]` (Finished - second sign-off at stage end)
Example: `- [x] [ ] [ ] Item description` (means code is implemented, but not yet validated or finished)

Split into two top-level sections: **Pre-Submission** (must happen before the July 7
deadline) and **Post-Submission** (everything else — real, tracked, but not gating
submission). Within each section, items are ordered by suggested priority, not by layer.
Cross-reference `_design.md` for contracts and `_TODO.md` for deferred decisions.
Finished items live in `_CHECKLIST_FINISHED.md`.

---

# Pre-Submission

Deadline: **July 7, 11:59 PM PT** = Tuesday July 8, 08:59 AM GMT+2. Target: submit Monday evening.

Suggested order and why:

1. **README** — setup instructions, architecture overview, layer status, known
   limitations. First because it's both a direct rubric line (Documentation, 20 pts)
   *and* the source material the writeup and video architecture slide should be drawn
   from — do this before drafting either.
   - [ ] [ ] [ ] README rewrite/expansion
2. **Market research & pricing** — before the writeup, not after, since the writeup's
   Deployability section depends on this number existing.
   - [ ] [ ] [ ] Re-verify `docs/competitive_landscape.md`'s claims before relying on them (the doc's own note: competitor products change, written 2026-07-05)
   - [ ] [ ] [ ] Confirm the "couple of cents per exercise" `gemini-2.5-flash` figure with an actual per-request token/cost estimate rather than a rounded gut number; decide where it lands (Deployability section, per `CAPSTONE_READINESS.md` §7's note)
3. **Kaggle writeup** — architecture decisions, design rationale, testing approach,
   honest PoC scope statement. Needs README + pricing settled first.
   - [ ] [ ] [ ] Draft against the `CAPSTONE_READINESS.md` §11 word budget
4. **Demo video** — one complete end-to-end session (≤5 min): startup → recommendation
   → writing → feedback → file written. Benefits from the writeup's framing being
   settled first (same "why agents"/architecture story), but can be shot in parallel.
   - [ ] [ ] [ ] Record per `CAPSTONE_READINESS.md` §10's beat list (bridge trigger is non-negotiable; correction step, close-of-loop, language-generation clip are cuttable in that order)
5. **Optional, only if 1-4 land with time to spare:** finish the language-generation
   utility's last open item — run one full grammar session end-to-end in the generated
   Czech content through the app (not just inspecting the generated files), which
   further de-risks using it as a video beat.
   - [x] [ ] [ ] Manual smoke test: generate a real second language against a live LLM, inspect the output, run one grammar session end-to-end in that language — partially done: Czech was generated live and spot-checked at a high level by a native speaker (the author); an actual end-to-end grammar session run in Czech through the app hasn't been confirmed yet
6. **Verify code link is accessible** — quick check, do right before submitting.
   - [ ] [ ] [ ] Verify code link is accessible
7. **Submit** before July 7, 11:59 PM PT (= Tuesday July 8, 08:59 AM GMT+2).
   - [ ] [ ] [ ] Submit

---

# Post-Submission

Nothing here gates the deadline. Rough priority if/when picked back up — cheapest,
already-diagnosed fixes first; then foundational hygiene; then larger feature work;
lowest-impact research/design items last.

### Cheap, already-diagnosed fixes (found stale during the docs pass, 2026-07-05)
- [ ] [ ] [ ] **Interrupted-Session Checkpoint Transcript** — the "Log it" path (`SessionManager.summarize_interrupted_transcript`) reads `{data_root}/checkpoints/{user_id}/{session_id}.json` and feeds it to `INTERRUPTION_SUMMARY_PROMPT` — but nothing ever appends a turn to that file after `init_write_ahead_log()` creates it empty (`json.dump([], f)`). Neither `WritingModule` nor `GrammarModule` implements `save_checkpoint()` (confirmed: zero matches for `save_checkpoint`/`restore_checkpoint`/`checkpoint` in either module's code). The summary is therefore always generated from an empty transcript, regardless of how much work was actually lost — not "quality varies with interruption point" as originally assumed, but "there's nothing to summarize yet." Fix: append a turn (user input + agent response) to the checkpoint file at 2-3 natural points in each module's loop — `checkpoint_path` is already threaded into `ctx.parameters` for both modules, so this is wiring, not a redesign. `docs/memory.md` and `docs/_CHECKLIST_FINISHED.md`'s PoC section both currently describe the incremental-append behavior as if it works; both corrected to note the gap rather than rewritten as if it were still true.
- [ ] [ ] [ ] **Evaluator-Sourced Vocab Flags** — `docs/memory.md`'s "Negative Vocab List" section claims two write sources — `/btw`-flagged words and evaluator `vocabulary`-tagged errors — but only the `/btw` path exists in code. `vocab_signals` (`ModuleResult.metadata`) is populated exclusively from `BtwEntry.flagged_word` (`modules/writing/agent.py:204`), and `SessionManager.finalize_session` hardcodes `source="btw"` on every `write_vocab_flag()` call (`session_manager.py:158-170`) — an evaluator-detected `vocabulary` error is never turned into a vocab flag today. Deduplication itself is *not* the gap: `write_vocab_flag()` already matches on `(user_id, language, word)` and increments `occurrence_count` on conflict in both backends, and the one real call site already normalizes (`word.lower().strip()`). Fix: when `classify_mistakes`/`explain_mistakes` tags a mistake `error_tag == "vocabulary"`, add its `fragment` to `vocab_signals` the same way `/btw` entries do, reusing the existing normalize-then-`write_vocab_flag(source="evaluator")` path — no new dedup logic needed, just the missing wiring. `docs/memory.md` corrected to describe this as designed-but-not-built rather than working.

### Engineering Tooling — foundational hygiene
- [ ] [ ] [ ] `.github/workflows/ci.yml` — install deps, run `pytest tests/unit/` on every push
- [ ] [ ] [ ] Document three test tiers in README: unit (CI, mocked), judge (manual, LLM calls), regression (manual, real fixtures)
- [ ] [ ] [ ] Add `mypy` to `requirements.txt`; run `mypy` in CI — enforce typed contracts that are currently declared but not checked (skill parameter dicts, Pydantic model shapes, Protocol implementations)
- [ ] [ ] [ ] Add `ruff` for linting + formatting; add `pyproject.toml` with config; run in CI pre-test step
- [ ] [ ] [ ] Replace `print()` debug/diagnostic output with a lightweight logger writing to `data/logs/`; keep user-facing `print()` calls in `ui/` only
- [ ] [ ] [ ] Log LLM call metadata per skill invocation: model, latency, token count (where available) — enables cost/latency tracking without changing skill interfaces
- [ ] [ ] [ ] Add a `PROMPT_VERSION` constant to each skill's `prompts.py`; write it into `SkillOutput.metadata` and session YAML
- [ ] [ ] [ ] Judge fixtures record the prompt version used — stale fixtures (version mismatch) are flagged at judge run time rather than silently producing wrong baselines
- [ ] [ ] [ ] Variance script: run each judge file n=5 on a fixed commit, diff per-case verdicts (`tests/judge/results/*.json`, already written per run) to measure gemma2:9b's verdict agreement rate — currently unmeasured, only manually spot-checked. Separately, a regression-diff tool comparing a fresh run against a committed baseline would catch prompt/behavior drift over time (`judge_detector_20260629_084234.json` is the one existing results file, but it's stale against current code — not usable as a baseline as-is)

### Cross-Module Recommendation Routing (generalize beyond 2 modules)
- [ ] [ ] [ ] `SessionManager._compute_next_actions()` (`orchestrator/session_manager.py`) currently dispatches next-action signals with a hardcoded `if module_key == "writing": ... elif module_key == "grammar": ...` — fine for 2 modules, but won't scale once Layer 3a (vocab) or a future reading module exist: writing plausibly wants to route to *both* grammar and vocab, grammar back to writing *or* vocab, vocab likely only to writing. Replace with an N-module routing table/registry *inside* `SessionManager` — keep cross-module knowledge centralized there rather than pushing a `compute_next_actions` hook onto `ModuleProtocol` itself (that would force e.g. `WritingModule` to import grammar's `get_grammar_topics`/tag shape directly, and every other module's shape too — N×M coupling across modules that otherwise don't know of each other, worse than today's `if/elif`). Trigger: do this when the third module (most likely vocab, Layer 3a) is actually implemented, not before

### Language Generation & Configurability — Backlog
> The `lang/` package (`lang/loader.py`, `lang/models.py`, `lang/maps/*`, `lang/languages/*.yaml`)
> is already architected to be language-agnostic — a new target language is just new content
> files in the same shape, no loader/model changes needed. The core generation utility is
> done (see `docs/_CHECKLIST_FINISHED.md`); these are the deferred extensions.

**Message Catalog (i18n for non-LLM backend text)** — implemented 2026-07-06 (reversing
the 2026-07-05 deferral decision): `lang/messages/{language}.yaml` (id-keyed strings,
`MessageCatalog` model in `lang/models.py`) loaded the same per-concept
default+override way `lang/maps/*` is, resolved by `profile.explanation_language`
(an orthogonal axis from `LanguageConfig`'s target-language maps). All ~24
`orchestrator.py` `io.output`/`io.prompt` call sites (menus, confirmations, status
lines) now resolve through it instead of hardcoded English; a language with no
generated catalog falls back to English and surfaces a warning
(`_check_message_catalog`, mirroring `_check_language_config`) via a new
`on_message_catalog_warning` hook through `ui/cli.py`/`ui/app.py`. See
`docs/lang.md` for the design and `docs/lang_generation.md` for the generator.
Auditing every `skills/*/prompts.py` for output-language handling (prompted by this
work, broader than the original "only write_correction" note below) found 5 prompts
producing learner-facing prose with no `{explanation_language}` directive at all —
fixed alongside the catalog. Pending: user validation on this branch
(`worktree-feature-message-catalog`) and merge to main.
- [x] [ ] [ ] Design a `lang/messages/{language}.yaml` catalog (id-keyed strings), loaded the same way `lang/maps/*` is (per-concept default + language override)
- [x] [ ] [ ] Extract `orchestrator.py`'s hardcoded `io.output`/`io.prompt` strings into catalog lookups
- [x] [ ] [ ] Extend the generation utility to also generate a language's message catalog, not just the LLM-facing maps — `scripts/generate_messages.py` + `lang/generate_messages.py`, same on-demand-generate-then-validate pattern as `lang/generate.py`, validated for required-id completeness and exact `{placeholder}` preservation
- [x] [ ] [ ] Audit every `skills/*/prompts.py` for an explicit output-language directive, not just `write_correction`'s hardcoded German prose — fixed `explain_mistakes`, `write_correction`, `btw_handler`, `grade_exercises`, `summarize_progress` (two hardcoded "in English", three with no language directive at all); threaded `explanation_language` through the same `ctx.parameters` path `dump_grammar` already used, and dropped `write_correction`'s German-specific word-order note from the shared (all-languages) prompt

**Fully Configurable Origin / Target / Communication Languages** — end goal: a catalog
of supported languages (backed by `lang/languages/*.yaml` plus the message catalog
above) that the user picks from along three independent axes — origin/native language,
target/study language, and communication (explanation) language — with an unsupported
pick pointed at the generation utility rather than silently degrading to generic
defaults. The message catalog dependency above is now satisfied; the items below are
still open.
- [ ] [ ] [ ] Model "origin language" explicitly — today `UserProfile` only has `language` (target) and `explanation_language`; no distinct native-language concept exists
- [ ] [ ] [ ] Expose the available-languages catalog to the selection flow (CLI + web) — `lang.loader` already holds the registry internally; needs a public "list configured languages" accessor
- [ ] [ ] [ ] Validate user selection against the catalog for all three axes; surface "needs generation" consistently across CLI and web, not just the CLI warning path added above

### Layer 3a — Vocab Skill (new module, larger scope)
- [ ] [ ] [ ] `/add_vocab <word>` CLI command — lets user manually flag a word mid-session; module appends it to `vocab_signals` in `ModuleResult.metadata` (same path as `/btw`-flagged words); `SessionManager.finalize_session` then calls `write_vocab_flag()` — module stays storage-free, memory boundary stays in orchestrator
- [ ] [ ] [ ] `modules/vocab/word_lists/greetings.yaml` — word, translation, example, difficulty
- [ ] [ ] [ ] `modules/vocab/word_lists/daily_routine.yaml`
- [ ] [ ] [ ] (Optional) `modules/vocab/word_lists/food.yaml`
- [ ] [ ] [ ] Review word lists for accuracy
- [ ] [ ] [ ] `VocabModule.run()` — gap-fill and translation drills from static lists
- [ ] [ ] [ ] `VocabSessionContent` dataclass
- [ ] [ ] [ ] Register in `MODULE_REGISTRY`

### Layer 3c — Anki Export (new module, larger scope)
- [ ] [ ] [ ] `storage.get_vocab_errors(user_id)` — aggregates `vocabulary`-tagged errors across sessions
- [ ] [ ] [ ] Export as `{word}\t{translation}\t{example}\n` to `data/exports/{user_id}_anki_{date}.txt`
- [ ] [ ] [ ] Surface export option in CLI and frontend
- [ ] [ ] [ ] Document Anki import steps in README

### Layer 1a — Design Research & Fluency (lowest impact — decided 2026-07-05, none of these have strong pitch/rubric impact)

**Error Taxonomy & Feedback Rubrics** — reordered so each item's prerequisite comes first:
> Outputs feed into `lang/maps/taxonomy/`, `lang/maps/cefr_descriptors/`, and evaluator prompts.
1. - [ ] [ ] [ ] Research alternative error taxonomies — compare Weir's framework and SLA classification against current German taxonomy; identify gaps or tags worth adding. First: everything below is easier to decide well once this survey exists, rather than redoing it after committing to a rubric shape.
2. - [ ] [ ] [ ] Define feedback rubrics: dimensions to comment on per session (accuracy, fluency, vocabulary range, task completion, coherence) and at which CEFR levels each becomes relevant
3. - [ ] [ ] [ ] Decide which rubric dimensions map to `tips[]` vs `session_summary` vs a future `rubric_scores` field — depends on #2 existing
4. - [ ] [ ] [ ] Define per-tag CEFR mastery level — the level at which each error type is expected to be mastered; drives Step 6 severity (`critical` / `expected` / `minor`). Options: (a) encode as a `mastery_level` field per tag in the taxonomy YAML, (b) a separate rubric file, (c) derive from CEFR descriptors in the prompt. None of these is actually implemented today — `skills/summarise_session/writing/prompts.py:27-28` has the LLM freely judge "how fundamental is this error type at this level" at inference time, with no per-tag ground truth backing it. Severity grading works in practice but has no documented, versioned answer to check it against
5. - [ ] [ ] [ ] Document decisions in `docs/writing.md`; propagate to taxonomy maps and evaluator prompts — wraps up 2-4
6. - [ ] [ ] [ ] Enrich CEFR descriptor maps — add `lang/maps/cefr_descriptors/german_v1.yaml` with German-specific level descriptions for more accurate text-level estimation (infrastructure in place, content missing). Independent content-authoring task, no hard dependency on 1-5
7. - [ ] [ ] [ ] Vary error taxonomy by progression level — different tag granularity per CEFR band: coarser at A1/A2 (e.g. `verb_conjugation`), finer at B2/C1 (e.g. `konjunktiv_ii`); implement as additional versioned taxonomy maps. Last: the most invasive change in this group — ripples into every taxonomy map, `classify_mistakes`, and every `related_error_tags` cross-reference in `lang/maps/grammar_topics/*.yaml`

**Fluency & Idiomatics** (deferred — depends on the Design Research decisions above; already in build order)
1. - [ ] [ ] [ ] Define scope: what counts as an idiomatic issue vs a grammar error; which CEFR levels activate this check (suggest B1+)
2. - [ ] [ ] [ ] `skills/fluency_checker/skill.py` — runs after Step 4 (write_correction); flags unnatural phrasing with natural alternatives; output is a list of `{fragment, suggestion, note}` distinct from `mistakes[]`
3. - [ ] [ ] [ ] Wire into pipeline between Steps 4 and 6; pass fluency observations to summariser for holistic tip generation
4. - [ ] [ ] [ ] UI: render fluency observations separately from grammar mistakes (different label, no "correction" implied)
5. - [ ] [ ] [ ] `tests/judge/judge_fluency_checker.py` — judge for fluency output quality

### LLM Throughput Optimization (exploratory, lowest priority)
- [ ] [ ] [ ] Identify and evaluate the LLM inference optimization package (cache efficiency + low-level throughput improvements); assess fit with `llm/` abstraction layer and document findings in `docs/llm_backends.md`
- [ ] [ ] [ ] Investigate `/btw` response latency — measure time from question submission to answer; evaluate whether prompt size, token budget, or the Gemini API cold path is the dominant factor

---

## History

Development (Sat June 28 – Fri July 4) is done — see `docs/_CHECKLIST_FINISHED.md`. The
original "development priority order" and cut rule that used to live in this file (Steps
5–6, Layer 1b, README) are archived there / in git history. See `CAPSTONE_READINESS.md`
§0 for the live pre-submission reprioritization narrative rather than duplicating it here.
