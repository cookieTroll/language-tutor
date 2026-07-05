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
- [x] [ ] [ ] Evaluate whether taxonomy tags surface to the user directly or are mapped to learner-friendly labels in the UI layer — resolved: raw `error_tag` values (`verb_conjugation`, etc.) now go through `shared/humanize.py::humanize_tag()` (underscore→space, title case) at every render/display site (`TerminalIOHandler`/`WebIOHandler` in `shared/io.py`, plus a `humanize_tag` Jinja filter used in `session.html`/`sessions.html`) rather than being stored or re-derived per site. `weak_tags`/`strong_tags` needed no change — `orchestrator/mastery.py` already resolves those to full taxonomy descriptions or grammar topic names, not raw tag keys

### Fluency & Idiomatics (deferred — depends on Layer 1a rubric decisions)
- [ ] [ ] [ ] Define scope: what counts as an idiomatic issue vs a grammar error; which CEFR levels activate this check (suggest B1+)
- [ ] [ ] [ ] `skills/fluency_checker/skill.py` — runs after Step 4 (write_correction); flags unnatural phrasing with natural alternatives; output is a list of `{fragment, suggestion, note}` distinct from `mistakes[]`
- [ ] [ ] [ ] Wire into pipeline between Steps 4 and 6; pass fluency observations to summariser for holistic tip generation
- [ ] [ ] [ ] UI: render fluency observations separately from grammar mistakes (different label, no "correction" implied)
- [ ] [ ] [ ] `tests/judge/judge_fluency_checker.py` — judge for fluency output quality

---

## Layer 1c — Local Frontend


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

## Layer 3b — merged into Layer 2c

> Level progression tracking turned out to be the same mastery/trend data as the CEFR estimator,
> just rendered differently. See "Layer 2c — Level & Progress" in `docs/CHECKLIST_FINISHED.md` —
> the progression bar and trend sparkline items there are what this layer used to describe separately.

---

## Layer 3c — Anki Export

- [ ] [ ] [ ] `storage.get_vocab_errors(user_id)` — aggregates `vocabulary`-tagged errors across sessions
- [ ] [ ] [ ] Export as `{word}\t{translation}\t{example}\n` to `data/exports/{user_id}_anki_{date}.txt`
- [ ] [ ] [ ] Surface export option in CLI and frontend
- [ ] [ ] [ ] Document Anki import steps in README

---

## LLM Throughput Optimization

- [ ] [ ] [ ] Identify and evaluate the LLM inference optimization package (cache efficiency + low-level throughput improvements); assess fit with `llm/` abstraction layer and document findings in `docs/llm_backends.md`
- [ ] [ ] [ ] Investigate `/btw` response latency — measure time from question submission to answer; evaluate whether prompt size, token budget, or the Gemini API cold path is the dominant factor

---

## Language Generation & Configurability

> The `lang/` package (`lang/loader.py`, `lang/models.py`, `lang/maps/*`, `lang/languages/*.yaml`)
> is already architected to be language-agnostic — a new target language is just new content
> files in the same shape, no loader/model changes needed. Today that content is hand-authored
> (German is the only populated language). This section starts closing that gap.

### Generation Utility (in progress — `feature/generate-language-assets`)
- [ ] [ ] [ ] `lang/generate.py` — `generate_taxonomy` / `generate_cefr_hints` / `generate_grammar_topics`, each validated via the existing Pydantic models (`TaxonomyMap` / `CEFRMap` / `GrammarTopicsMap`) through `skills.protocols.call_with_self_correction`; `write_language_assets()` writes all four files and re-validates end-to-end via a fresh `lang.loader._Registry` pointed at the real `lang/maps`/`lang/languages` directories — reuses the exact cross-reference validation `lang/loader.py` already runs at import time instead of duplicating it
- [ ] [ ] [ ] `lang/generate_prompts.py` — prompt templates for the three generators (compact inlined example, not the full German file, to keep token cost sane)
- [ ] [ ] [ ] `scripts/generate_language.py` — CLI entry (`python -m scripts.generate_language <language>`), wires config/LLM the same way `ui/cli.py::main` does; refuses to overwrite an existing `lang/languages/{name}.yaml` without `--force`
- [ ] [ ] [ ] `lang/loader.py::is_configured()` + `orchestrator._check_language_config` + `ui/cli.py::_language_config_warning` — when a user picks a language with no config file at all, tell them it needs generating (and how) instead of silently falling back to generic defaults
- [ ] [ ] [ ] `tests/unit/lang/test_generate.py` — mocked-LLM coverage: happy-path parse/validate per generator, self-correction retry when a generated grammar topic references an unknown taxonomy tag, round-trip through a fresh `_Registry` at `tmp_path`
- [ ] [ ] [ ] Manual smoke test: generate a real second language against a live LLM, inspect the output, run one grammar session end-to-end in that language

### Backlog — Message Catalog (i18n for non-LLM backend text)
> Not started. `orchestrator.py` has ~14 `io.output`/`io.prompt` call sites (menus, confirmations,
> status lines) hardcoded in English, independent of `profile.explanation_language` — a user with
> `explanation_language: spanish` still gets English menus and confirmations. This is distinct from
> LLM-generated content (feedback, explanations, exercises), which is already parametrized via
> `{language}`/`{explanation_language}` in nearly every `skills/*/prompts.py` template — only
> `skills/write_correction/prompts.py` still has real hardcoded German prose to generalize.
- [ ] [ ] [ ] Design a `lang/messages/{language}.yaml` catalog (id-keyed strings), loaded the same way `lang/maps/*` is (per-concept default + language override)
- [ ] [ ] [ ] Extract `orchestrator.py`'s hardcoded `io.output`/`io.prompt` strings into catalog lookups
- [ ] [ ] [ ] Extend the generation utility (above) to also generate a language's message catalog, not just the LLM-facing maps

### Backlog — Fully Configurable Origin / Target / Communication Languages
> End goal: a catalog of supported languages (backed by `lang/languages/*.yaml` plus the message
> catalog above) that the user picks from along three independent axes — origin/native language,
> target/study language, and communication (explanation) language — with an unsupported pick
> pointed at the generation utility rather than silently degrading to generic defaults.
- [ ] [ ] [ ] Model "origin language" explicitly — today `UserProfile` only has `language` (target) and `explanation_language`; no distinct native-language concept exists
- [ ] [ ] [ ] Expose the available-languages catalog to the selection flow (CLI + web) — `lang.loader` already holds the registry internally; needs a public "list configured languages" accessor
- [ ] [ ] [ ] Validate user selection against the catalog for all three axes; surface "needs generation" consistently across CLI and web, not just the CLI warning path added above

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

### Judge Verdict Reliability
- [ ] [ ] [ ] Variance script: run each judge file n=5 on a fixed commit, diff per-case verdicts (`tests/judge/results/*.json`, already written per run) to measure gemma2:9b's verdict agreement rate — currently unmeasured, only manually spot-checked. Separately, a regression-diff tool comparing a fresh run against a committed baseline would catch prompt/behavior drift over time (`judge_detector_20260629_084234.json` is the one existing results file, but it's stale against current code — not usable as a baseline as-is). Not a pre-submission code task — write-up material only, see `CAPSTONE_READINESS.md` §11: name the unmeasured variance as an honest testing-tier limitation rather than let a judge infer it.

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
