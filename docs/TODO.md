# GermanTutor — TODO

Items that arose during design discussion but are deferred decisions, known risks, or future work. Not implementation steps (see CHECKLIST.md for those).

---

## Refactoring Backlog

- [ ] **Skill LLM call abstraction** — significant boilerplate repeated across all skills: `LLMMessage` list construction, `call_with_self_correction` try/except, `show_incomplete_responses` config check. Extract as a protected `_call(llm, system, user, parse_fn, temperature)` helper on `SkillProtocol` returning `(success, result, error_msg)`. Each skill reduces to: build prompts → call `self._call()` → package `SkillOutput`. Do after CR round is complete and all skills are committed; test coverage is the gate.

---

## Known Risks & Hard Points

- [ ] **Evaluator prompt complexity** — getting consistent, accurate German grammar feedback in a single (or chained) LLM call is the highest-risk part of the project. Budget significant time for prompt iteration. The 4-step decomposition mitigates this but each step still needs tuning.
- [ ] **Evaluator ground truth** — need 3–5 manually verified writing input/output pairs per evaluator step for judge testing. Ground truth must be within B1 scope (verifiable by author). Generate a few more examples if needed, but keep scope honest — do not use unverified B1+ examples as ground truth.
- [ ] **Judge prompt variance** — before trusting any LLM-as-judge prompt, run it 5 times on the same input and verify score consistency. Document acceptable variance per step. A flaky judge is worse than no judge.
- [ ] **Cold start edge cases** — below threshold (default: 3 sessions), orchestrator defaults to writing. Verify this branch handles zero sessions, one session, and exactly-threshold sessions correctly.
- [ ] **Orchestrator hallucination guard** — LLM may return a `skill` value not in the registry. Validation is in the design; make sure the fallback path is tested explicitly.

---

## Deferred Design Decisions

- [x] **`/btw` word extraction heuristic** — resolved: regex for quoted words + LLM fallback. `BtwHandler` implemented in `skills/btw_handler/skill.py`. Remaining risk: extraction quality on ambiguous questions; monitor via judge tests.
- [ ] **Vocab flag deduplication** — when the evaluator flags a `vocabulary` error, the word needs to be normalized (lowercase, strip punctuation) before writing to `vocab_flags` to avoid duplicate entries for the same word in different forms. Define normalization strategy.
- [ ] **Interrupted session summary quality** — the "Log it" path generates an LLM summary from a partial transcript. Quality will vary depending on how far into the session the interruption occurred. Define minimum transcript length before summary is attempted; below that, offer only Discard. When implementing: define checkpoint granularity per skill (exercise generated / user text received / evaluation complete), decide whether to offer resumption or just detection for mid-evaluator interruptions.
- [x] **Cross-session writing comparison (Layer 2b)** — resolved, and reshaped: not a per-session `summarise_session` field, not automatic. An on-demand `/history` command (topics covered, recurring mistakes, level trend) built entirely from the existing `get_sessions_by_module()` + one new `SessionLog.text_level_estimate` field — no `get_writing_sessions()`/file-path-based lookup needed. See `docs/writing.md` and `docs/CHECKLIST.md` Layer 2b.
- [ ] **CEFR estimator (Layer 2c)** — reads session logs and estimates user level, writes to `user_levels` table with `source='estimated'`. Should consume `text_level_estimate` field (produced by Step 5 each session) as a primary signal rather than re-estimating from text. Define minimum session count threshold and how to weight text-level trend vs error frequency vs exercise scores.
- [ ] **Level as canonical source of truth** — currently level comes from `config.yaml` (stated) or `user_levels` table (estimated). Decide what happens when CEFR estimator disagrees with stated level — does it override, suggest, or just log? Flag this before implementing Layer 2c.
- [ ] **Summary files format** — defined as markdown in design but content structure not fully specified. When implementing Layer 1b, define the exact sections (skill frequency, error patterns, suggested focus, writing comparison placeholder).
- [ ] **Progress summary storage** — currently generated on demand. If generation becomes slow (large log), consider caching the most recent summary as a file and invalidating on new session write. Defer until performance is a real problem.
- [ ] **Anki export format** — basic format agreed (`word\ttranslation\texample`). Decide whether to export per-session or accumulated across sessions. AnkiConnect integration (Layer 3c) requires user to have Anki + AnkiConnect plugin running — document this dependency clearly.
- [ ] **Per-tag CEFR mastery levels** — Step 6 (Session Summariser) assigns severity (`critical`/`expected`/`minor`) based on the gap between the user's level and the level at which each error tag is expected to be mastered. This mapping needs to be defined as part of Design Research (Layer 1a prerequisite). Options: (a) encode in taxonomy YAML as a `mastery_level` field per tag, (b) define in a separate rubric file, (c) derive from CEFR descriptors in the prompt. Decision feeds directly into the Step 6 prompt design.

- [ ] **Base vs Target language communication** — Define a base language (defaults to English) and a target language (configurable per user/session, e.g. German). Allow the user to select whether tutoring explanations, error hints, and the entire conversation are conducted in the base language or the target language (typically preferred for higher CEFR levels). For now, the base language is fixed as English and the target language is configurable.

---

## Testing Backlog

- [ ] **LLM-as-judge setup for BTW Questions** — Set up an LLM-as-judge evaluation pipeline to run automated regression checks on mid-session side-questions (`/btw`). Introduce tests that assert both explanation language (English by default) and translation accuracy (no hallucinations).
  * **Test case backlog**:
    - **Query**: "How is wake up in German?"
    - **Expected correct behavior**: Suggests "aufwachen" or "aufstehen" and explains the difference in English.
    - **Hallucination regression pattern**: Must not output "Die Wachstunde" or equate it to a greeting like "Good morning".
- [x] **Create writing fixture set** — done: `tests/fixtures/writing_pairs.json`. Covers verb conjugation, mixed errors, no-error case. Expand with dative case and word order fixtures as new evaluator stages are added.
- [ ] **Create orchestrator fixture set** — 3–5 session history scenarios with expected recommendations. Cover: cold start, single skill overuse, recurring error pattern, balanced history.
- [ ] **Validate judge prompts** — run each judge 5x on same fixture, record variance, tighten if needed.
- [ ] **Regression fixture process** — establish convention during development: when a prompt produces a notably good output on a real input, save to `tests/fixtures/regression/` with a descriptive filename and note what was good about it.
- [ ] **CI setup** — low priority for solo project; unit tests run manually during development. If added: Tier 1 (unit, mocked) on push; Tier 2 (judge, LLM calls) and Tier 3 (regression) manually or scheduled.

---

## Quality & Polish (post-PoC)

- [ ] **Error taxonomy review** — German taxonomy v1 (`lang/maps/taxonomy/german_taxonomy_v1.yaml`) has 8 tags: `noun_declension`, `adjective_declension`, `article`, `verb_conjugation`, `verb_tense`, `vocabulary`, `spelling`, `other`. Review against real session output; add new versions as a new YAML file (e.g. `german_taxonomy_v2.yaml`) rather than modifying in place — old sessions reference the version they were tagged with.
- [ ] **German topic list for grammar** — curate A1–B2 grammar topics from a standard syllabus (e.g. Goethe Institut curriculum). Store in `lang/maps/grammar_topics/german_a1_b2.yaml` (versioned-map pattern, same as `taxonomy`/`cefr_hints`). Review for completeness before Layer 2a.
- [ ] **Vocab word lists** — compile 2–3 thematic units (greetings, daily routine, food) in `skills/vocab/word_lists/`. Include: word, translation, example sentence, difficulty tag. Review for accuracy.
- [ ] **Frontend file browser** — Layer 1c session file browser should render YAML files in a readable format, not raw YAML. Decide rendering approach (parse and template, or simple markdown-style display).
- [ ] **Config schema validation** — `config.yaml` is loaded at startup but not validated in design. Add schema validation (e.g. with `pydantic`) to catch misconfiguration early.

---

## Capstone-Specific

- [ ] **Kaggle writeup** — document architecture decisions, not just setup. Reference `DESIGN.md`. Explain the skill registry pattern, storage abstraction, evaluator decomposition, and testing approach. Frame the PoC scope honestly.
- [ ] **Demo video** — walk through one complete session end-to-end: startup → orchestrator default recommendation → writing session → feedback → session file written → DB entry visible. Keep under 5 minutes.
- [ ] **Submission checklist** — writeup, video, rationale, code link. Deadline: July 7, 11:59 PM PT.
