# GermanTutor — TODO

Items that arose during design discussion but are deferred decisions, known risks, or future work. Not implementation steps (see CHECKLIST.md for those).

---

## Known Risks & Hard Points

- [ ] **Evaluator prompt complexity** — getting consistent, accurate German grammar feedback in a single (or chained) LLM call is the highest-risk part of the project. Budget significant time for prompt iteration. The 4-step decomposition mitigates this but each step still needs tuning.
- [ ] **Evaluator ground truth** — need 3–5 manually verified writing input/output pairs per evaluator step for judge testing. Ground truth must be within B1 scope (verifiable by author). Generate a few more examples if needed, but keep scope honest — do not use unverified B1+ examples as ground truth.
- [ ] **Judge prompt variance** — before trusting any LLM-as-judge prompt, run it 5 times on the same input and verify score consistency. Document acceptable variance per step. A flaky judge is worse than no judge.
- [ ] **Cold start edge cases** — below threshold (default: 3 sessions), orchestrator defaults to writing. Verify this branch handles zero sessions, one session, and exactly-threshold sessions correctly.
- [ ] **Orchestrator hallucination guard** — LLM may return a `skill` value not in the registry. Validation is in the design; make sure the fallback path is tested explicitly.

---

## Deferred Design Decisions

- [ ] **`/btw` word extraction heuristic** — extracting `flagged_word` from a free-text question ("what does Hauptbahnhof mean?") requires a simple NLP heuristic or a small LLM call. Decide approach before implementing BtwHandler. A regex for quoted words + a fallback LLM extraction call is probably sufficient.
- [ ] **Vocab flag deduplication** — when the evaluator flags a `vocabulary` error, the word needs to be normalized (lowercase, strip punctuation) before writing to `vocab_flags` to avoid duplicate entries for the same word in different forms. Define normalization strategy.
- [ ] **Interrupted session summary quality** — the "Log it" path generates an LLM summary from a partial transcript. Quality will vary depending on how far into the session the interruption occurred. Define minimum transcript length before summary is attempted; below that, offer only Discard. When implementing: define checkpoint granularity per skill (exercise generated / user text received / evaluation complete), decide whether to offer resumption or just detection for mid-evaluator interruptions.
- [ ] **Cross-session writing comparison (Layer 2b)** — summarize skill needs to look up a previous writing file to generate comparison. Dependency: writing session files must be queryable by topic similarity or date. May need a `get_writing_sessions()` storage method that returns file paths for loading.
- [ ] **CEFR estimator (Layer 2c)** — reads session logs and estimates level, writes to `user_levels` table with `source='estimated'`. Needs a minimum session count before meaningful estimation. Define threshold and what signals to use (error frequency, exercise scores, writing complexity).
- [ ] **Level as canonical source of truth** — currently level comes from `config.yaml` (stated) or `user_levels` table (estimated). Decide what happens when CEFR estimator disagrees with stated level — does it override, suggest, or just log? Flag this before implementing Layer 2c.
- [ ] **Summary files format** — defined as markdown in design but content structure not fully specified. When implementing Layer 1b, define the exact sections (skill frequency, error patterns, suggested focus, writing comparison placeholder).
- [ ] **Progress summary storage** — currently generated on demand. If generation becomes slow (large log), consider caching the most recent summary as a file and invalidating on new session write. Defer until performance is a real problem.
- [ ] **Anki export format** — basic format agreed (`word\ttranslation\texample`). Decide whether to export per-session or accumulated across sessions. AnkiConnect integration (Layer 3c) requires user to have Anki + AnkiConnect plugin running — document this dependency clearly.
- [ ] **Base vs Target language communication** — Define a base language (defaults to English) and a target language (configurable per user/session, e.g. German). Allow the user to select whether tutoring explanations, error hints, and the entire conversation are conducted in the base language or the target language (typically preferred for higher CEFR levels). For now, the base language is fixed as English and the target language is configurable.

---

## Testing Backlog

- [ ] **LLM-as-judge setup for BTW Questions** — Set up an LLM-as-judge evaluation pipeline to run automated regression checks on mid-session side-questions (`/btw`). Introduce tests that assert both explanation language (English by default) and translation accuracy (no hallucinations).
  * **Test case backlog**:
    - **Query**: "How is wake up in German?"
    - **Expected correct behavior**: Suggests "aufwachen" or "aufstehen" and explains the difference in English.
    - **Hallucination regression pattern**: Must not output "Die Wachstunde" or equate it to a greeting like "Good morning".
- [ ] **Create writing fixture set** — 3–5 input/output pairs per evaluator step, manually verified. Cover: dative case errors, word order errors, verb conjugation errors, separable verbs, mixed error text. At least one fixture with no errors (to test false positive rate).
- [ ] **Create orchestrator fixture set** — 3–5 session history scenarios with expected recommendations. Cover: cold start, single skill overuse, recurring error pattern, balanced history.
- [ ] **Validate judge prompts** — run each judge 5x on same fixture, record variance, tighten if needed.
- [ ] **Regression fixture process** — establish convention during development: when a prompt produces a notably good output on a real input, save to `tests/fixtures/regression/` with a descriptive filename and note what was good about it.
- [ ] **CI setup** — unit tests (Tier 1) should run in CI on every push. LLM-as-judge (Tier 2) and regression (Tier 3) run manually or on a scheduled basis — they cost API calls and shouldn't block commits.

---

## Quality & Polish (post-PoC)

- [ ] **Error taxonomy review** — current taxonomy is a reasonable starting set but should be reviewed against real writing session output. Add tags as new error patterns emerge; do not add tags retroactively to old sessions.
- [ ] **German topic list for grammar** — curate A1–B2 grammar topics from a standard syllabus (e.g. Goethe Institut curriculum). Store in `skills/grammar/topics/a1_b2_topics.yaml`. Review for completeness before Layer 2a.
- [ ] **Vocab word lists** — compile 2–3 thematic units (greetings, daily routine, food) in `skills/vocab/word_lists/`. Include: word, translation, example sentence, difficulty tag. Review for accuracy.
- [ ] **Frontend file browser** — Layer 1c session file browser should render YAML files in a readable format, not raw YAML. Decide rendering approach (parse and template, or simple markdown-style display).
- [ ] **Config schema validation** — `config.yaml` is loaded at startup but not validated in design. Add schema validation (e.g. with `pydantic`) to catch misconfiguration early.

---

## Capstone-Specific

- [ ] **Kaggle writeup** — document architecture decisions, not just setup. Reference `DESIGN.md`. Explain the skill registry pattern, storage abstraction, evaluator decomposition, and testing approach. Frame the PoC scope honestly.
- [ ] **Demo video** — walk through one complete session end-to-end: startup → orchestrator default recommendation → writing session → feedback → session file written → DB entry visible. Keep under 5 minutes.
- [ ] **Submission checklist** — writeup, video, rationale, code link. Deadline: July 7, 11:59 PM PT.
