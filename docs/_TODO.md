# Wharf the Language Tutor — TODO

Items that arose during design discussion but are deferred decisions, known risks, or future work. Not implementation steps (see `_CHECKLIST.md` for those).

---

## Refactoring Backlog

- [ ] **Skill LLM call abstraction** — partially resolved, not done. `call_with_self_correction` (`skills/protocols.py`) does consolidate the retry-loop logic (correction-feedback message construction, `max_attempts` handling) — that part of the original complaint is gone. Still duplicated exactly as described, though: `LLMMessage` list construction (per skill), the `try`/`except SelfCorrectionError` wrapper + `SkillOutput` packaging (per skill), and — most concretely — the `show_incomplete_responses` check, copy-pasted verbatim (`getattr(llm.config, "show_incomplete_responses", False)` + `isinstance` guard) across 7 separate files: `btw_handler`, `classify_mistakes`, `detect_mistakes`, `estimate_text_level`, `explain_mistakes`, `summarise_session/base.py`, `write_correction`. A shared `_call()` helper (as originally proposed) would still collapse real duplication. Low priority — internal code quality, not a rubric-relevant gap; fine to leave post-submission alongside Engineering Tooling.

---

## Known Risks & Hard Points

- [ ] **Evaluator prompt complexity** — getting consistent, accurate German grammar feedback in a single (or chained) LLM call is the highest-risk part of the project. Budget significant time for prompt iteration. The 4-step decomposition mitigates this but each step still needs tuning.

---

## Deferred Design Decisions

- [ ] **Progress summary storage** — currently generated on demand. If generation becomes slow (large log), consider caching the most recent summary as a file and invalidating on new session write. Defer until performance is a real problem.

---

## Testing Backlog

- [ ] **LLM-as-judge setup for BTW Questions** — Set up an LLM-as-judge evaluation pipeline to run automated regression checks on mid-session side-questions (`/btw`). Introduce tests that assert both explanation language (English by default) and translation accuracy (no hallucinations).
  * **Test case backlog**:
    - **Query**: "How is wake up in German?"
    - **Expected correct behavior**: Suggests "aufwachen" or "aufstehen" and explains the difference in English.
    - **Hallucination regression pattern**: Must not output "Die Wachstunde" or equate it to a greeting like "Good morning".
- [ ] **Regression fixture process** — establish convention during development: when a prompt produces a notably good output on a real input, save to `tests/fixtures/regression/` with a descriptive filename and note what was good about it.

---

## Quality & Polish (post-PoC)

- [ ] **Error taxonomy review** — German taxonomy v1 (`lang/maps/taxonomy/german_taxonomy_v1.yaml`) has 8 tags: `noun_declension`, `adjective_declension`, `article`, `verb_conjugation`, `verb_tense`, `vocabulary`, `spelling`, `other`. Review against real session output; add new versions as a new YAML file (e.g. `german_taxonomy_v2.yaml`) rather than modifying in place — old sessions reference the version they were tagged with.
