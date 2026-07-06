# Wharf the Language Tutor — Writing Module & Skills

The writing module is the PoC showpiece. Composed of atomic skills, it handles topic selection, error detection, feedback generation, and correction writing.

See `docs/_contracts.md` for `ModuleProtocol`, `SkillProtocol`, `WritingSessionContent`.

---

## Writing Module (`modules/writing/`)

**Goal:** Conduct a complete writing session — generate a prompt, accept user text, evaluate it, produce structured feedback and a corrected version.

**Layer:** PoC (partial), 1a (full evaluator), 1b (topic picker + full context)

### `module.md` spec

```
name: writing
description: Conducts a German writing session. Generates a prompt at the user's
             level, accepts their written response, identifies grammar and vocabulary
             errors, provides structured feedback with explanations, and produces a
             corrected version.
```

### Context request (`modules/writing/agent.py`)

```python
def context_request(self) -> ContextRequest:
    return ContextRequest(
        recent_sessions_n=5,
        module_filter="writing",
        include_error_frequency=True,
        include_recent_topics=True,
        include_vocab_flags=True,
    )
```

### Pipeline (`modules/writing/pipeline.py`)

`WritingPipeline` sequences all seven evaluator skills. `WritingModule.run()` delegates to it — the module handles I/O (prompts, display), the pipeline handles LLM calls.

Execution order is **1+2 in parallel → 3 → 4 → 5 → 6+7 in parallel**, run via
`concurrent.futures.ThreadPoolExecutor`:

- **Step 1** `estimate_text_level` and **Step 2** `detect_mistakes` run
  concurrently (two workers) — both only need the raw user text and are
  independent of each other. Step 2 also acts as a **gate**: if it fails
  (bad JSON / LLM error), the pipeline returns early with
  `detector_success=False` and no further LLM calls are made; Step 1's
  result is still carried through even in that case.
- **Step 3** `verify_mistakes` re-checks each raw fragment from Step 2
  against its original sentence context and drops false positives —
  `detect_mistakes` judges the whole text in one pass and can misjudge an
  isolated fragment (e.g. correct verb-second word order after a fronted
  connector) — before classification.
- **Step 4** `classify_mistakes` maps verified fragments to taxonomy
  `error_tag`s.
- **Step 5** `explain_mistakes` adds a learner-facing pedagogical
  explanation to each classified mistake.
- **Step 6** `write_correction` and **Step 7** `summarise_writing_session`
  run concurrently (two workers) — both only need Step 5's
  `explained_mistakes` and are independent of each other. Step 6 rewrites
  the full corrected text; Step 7 adds severity tags, `tips[]`, and
  `session_summary`.

Returns a `PipelineResult` dataclass carrying all per-step outputs, plus (when
timing is enabled) `step_timings: list[StepTiming]` and `total_wall_s`. Each
step's wall-clock duration is appended to `data/logs/skill_latency.jsonl`
after the pipeline finishes (`modules/writing/agent.py::_write_latency_log`)
— one JSON line per step per session, plus a final `"step": "total"` line
for the whole pipeline; skipped during pytest runs (`PYTEST_CURRENT_TEST`
set).

### Skills injected

| Layer | Skill | Role |
|-------|-------|------|
| PoC | `btw_handler` | utility — inline /btw questions during writing and follow-up |
| 1a | `estimate_text_level` | Step 1 — CEFR band estimation (parallel with Step 2) |
| 1a | `detect_mistakes` | Step 2 — raw mistake detection (gate, parallel with Step 1) |
| 1a | `verify_mistakes` | Step 3 — re-checks each candidate against context, drops false positives |
| 1a | `classify_mistakes` | Step 4 — taxonomy classification |
| 1a | `explain_mistakes` | Step 5 — explanations pitched to level |
| 1a | `write_correction` | Step 6 — corrected text (parallel with Step 7) |
| 1a | `summarise_writing_session` | Step 7 — severity-grouped summary, tips, session_summary (parallel with Step 6) |
| 1b | `topic_picker` | topic generation |

### Session flow (`modules/writing/agent.py`)

```
  1. pick_topic (`WritingModule._pick_topic`):
     prompt "Enter your own topic, or press Enter for a suggestion"
       → user types a topic: used directly, requirements defaulted
         (word count + suggested_focus if any) — topic_picker skill
         is not called
       → blank input: topic_picker(level, recent_topics, error_tags,
         suggested_focus, min_words) → topic + requirements
  2. Display topic + requirements to user
  3. Accept multi-line text input (blank line or /end to submit)
     └─ /btw [question] handled inline at any point during writing
       (routed to btw_handler; session_context has no pipeline results
       yet at this point)
     └─ /word_count shown on request
  4. Pipeline (`WritingPipeline.run`, see "Pipeline" above) — 7 steps,
     steps 1+2 and 6+7 run in parallel:
       estimate_text_level + detect_mistakes → verify_mistakes →
       classify_mistakes → explain_mistakes → write_correction +
       summarise_writing_session
  5. Display feedback to user (mistakes, explanations, corrected text,
     tips, session_summary)

  6. Follow-up phase (`WritingModule._follow_up_phase`)          [1a]
     "Unsure about a mistake? Ask me here — or press Enter to finish."
     Loop continues until the user submits a blank input line.

     For each non-blank line:
       if it matches "practi[cs]e|exercise|drill" (`_PRACTICE_REQUEST_RE`)
         → `_offer_practice_topic`: picks the most common error_tag across
           this session's explained_mistakes and records it (only the
           first match counts; later matches just get an
           "already noted" acknowledgement)
       otherwise → routed to btw_handler(question, session_context),
         session_context now includes the pipeline's explained_mistakes,
         corrected_text, tips, and session_summary — richer than during
         the writing phase (step 3)
       display answer, continue loop

  7. Return (ModuleResult, WritingSessionContent)
```

**Phase distinction:**
- **Writing phase** (step 3): `/btw` for quick inline questions that don't break flow. User is mid-composition; no evaluation results exist yet to pass as context.
- **Follow-up phase** (step 6): Q&A after evaluation. User is reading feedback and asking "why?". Every question here goes through `btw_handler`, now with the full evaluation (explained_mistakes, corrected_text, tips, session_summary) available as context — there is no separate `explain_grammar` skill routing; that skill was deliberately dropped (see `docs/grammar.md`'s Backlog section / `docs/_layers.md`). The real replacement for what `explain_grammar` routing would have offered is the practice-request feature below, not a second skill in this loop.

**Practice request:** During the follow-up phase, typing anything containing "practice"/"practise"/"exercise"/"drill" (case-insensitive, matched via `_PRACTICE_REQUEST_RE`) is treated as a request to practise the material just covered, instead of being sent to `btw_handler`. `_offer_practice_topic` (`modules/writing/agent.py`) takes the most frequent `error_tag` across this session's `explained_mistakes` (via `collections.Counter`), tells the user a grammar session on that tag will be suggested, and returns it as `practice_requested_topic`. If there were no classified mistakes to draw a tag from, it tells the user a general suggestion will be passed along instead and returns `None`. Only the first practice request in a session counts — repeats just get a "already noted" message. The actual "Start grammar practice now?" offer happens later, at the orchestrator's normal end-of-session chaining point (`session_manager._writing_error_recurrence_signal`), not inside this loop — this phase only records the intent and the tag to focus it on.

### `ModuleResult.metadata` keys

```python
{
  "btw_entries": [BtwEntry, ...],           # from both writing and follow-up phases
  "vocab_signals": ["word1", ...],          # for orchestrator → vocab_flags
  "practice_requested_topic": str | None,   # error_tag to focus a suggested grammar
                                             # session on, from the practice-request
                                             # feature above; None if never requested
                                             # or no mistakes to draw a tag from
}
```

---

## Skills

### `skills/detect_mistakes/` — Raw Mistake Detector

**Layer:** PoC
**Type:** session

**Input:**
```python
user_text: str
writing_prompt: str       # topic + requirements
level: str                # A1–C2
recurring_errors: list[str]   # from context, primes attention
```

**Output:**
```python
raw_mistakes: list[dict]  # [{fragment: str, error_type_hint: str}]
```

**Prompt template:**
```
You are a {language} language teacher evaluating a {level} learner's writing.

Task given to the student:
{writing_prompt}

Known recurring errors to watch for:
{recurring_errors}

Student's text:
{user_text}

Identify all grammatical, vocabulary, and spelling errors.
Return JSON only:
{
  "mistakes": [
    {"fragment": "mit meinen Bruder", "error_type_hint": "wrong case after mit"}
  ]
}
Return empty list if no errors found.
```

**Notes:**
- Returns raw hints, not classified tags — classification happens in Step 2
- `recurring_errors` injected as a soft prime, not exclusive
- Empty text or no errors both handled gracefully
- Judging the whole text in one pass can anchor on a couple of salient errors (e.g.
  two verb-conjugation mistakes) and miss a subtler one nearby (e.g. an adjective
  ending) — `verify_mistakes` (Step 1.5) is a second, narrower pass over each
  candidate, not a fix for this at the source

**Test criteria (judge):** Detection accuracy (real errors caught), false positive rate (non-errors flagged).

---

### `skills/verify_mistakes/` — Candidate Error Verifier

**Layer:** 1a
**Type:** session

**Input:**
```python
raw_mistakes: list[dict]  # from detect_mistakes: [{fragment, error_type_hint}]
user_text: str            # full text, so each fragment is judged in its real sentence context
level: str
```

**Output:**
```python
verified_mistakes: list[dict]  # same shape as raw_mistakes, filtered — false positives dropped
```

**Notes:**
- `detect_mistakes` judges the whole text in one pass; a fragment that looks wrong in
  isolation (e.g. inverted word order) can actually be a correct grammar rule (verb-second
  after a fronted adverb/connector) once checked against its real sentence — this step's
  only job is that second check, one candidate at a time
- Does not classify, correct, or add new candidates — purely a keep/reject filter
- Fails open: if the LLM call itself fails after retries (`SelfCorrectionError`), falls
  back to the original unfiltered `raw_mistakes` rather than silently dropping every
  candidate — a broken verification pass shouldn't cost real errors
- A verdict must cover every candidate fragment; a response that omits one is treated as
  a structural failure and retried, not silently resolved either way

**Test criteria (judge):** Deterministic — each fixture case has a known keep/reject split
(`tests/fixtures/verify_mistakes_cases.json`), checked directly against the executor's
output rather than through a second judge LLM call.

---

### `skills/classify_mistakes/` — Mistake Classifier

**Layer:** 1a
**Type:** session

**Input:**
```python
raw_mistakes: list[dict]   # verified_mistakes from verify_mistakes (Step 3), not detect_mistakes' raw output directly
user_text: str
```

**Output:**
```python
classified: list[dict]     # [{fragment, error_tag, correction}]
# error_tag validated via lang.loader taxonomy before return
```

**Post-processing:** `taxonomy.validate_tag()` called on every `error_tag`. Unknown tags fall back to `"other"`.

---

### `skills/explain_mistakes/` — Explanation Generator

**Layer:** 1a
**Type:** session

**Input:**
```python
classified: list[dict]    # from classify_mistakes
level: str
explanation_language: str # profile.explanation_language, defaults to English if unset
```

**Output:**
```python
explained: list[dict]     # [{error_tag, fragment, correction, explanation}]
# explanation pitched to level, written in explanation_language
```

**Notes:**
- Short-circuits gracefully if `classified` is empty — returns empty list
- Explanation depth calibrated to level: A1 = very simple, B1 = rule + example, B2+ = nuance
- `explanation` text is written in `explanation_language`, not necessarily the target
  study language — previously hardcoded to English regardless of the user's setting

---

### `skills/write_correction/` — Correction Writer

**Layer:** 1a — Step 6 (runs in parallel with Step 7, `summarise_writing_session`)
**Type:** session

**Input:**
```python
user_text: str
explained_mistakes: list[dict]    # from explain_mistakes (Step 5), structured, not freeform
level: str
explanation_language: str # profile.explanation_language, defaults to English if unset
```

**Output:**
```python
corrected_text: str
recommendations: list[str]   # short next-step suggestions, written in explanation_language
comment: str                 # one-sentence overall comment, written in explanation_language
```

**Note:** Only `corrected_text` is actually consumed downstream
(`WritingPipeline.run` reads `correction_output.metadata["corrected_text"]`
and nothing else from this skill). `recommendations` and `comment` are part
of this skill's return shape but are superseded by `tips`/`session_summary`
from the parallel Step 7 (`summarise_writing_session`) — see that skill
below, which is what actually reaches `PipelineResult.tips` /
`.session_summary`. Short-circuits without an LLM call if
`explained_mistakes` is empty, returning the original text unchanged and a
canned "no mistakes" comment.

**Prompt template:**
```
You are a {language} language teacher. A {level} learner has written the following text.
You have already identified and classified all mistakes. Your task now is to:

1. Produce a corrected version of the text by applying ONLY the listed corrections.
   Treat each correction as a literal substitution: find the exact fragment in the text and
   replace only those words — do not restructure any surrounding clause, and preserve
   {language}'s own word order conventions when the substitution is applied.
2. Write 2-4 short, actionable recommendations the student should focus on going forward,
   in {explanation_language}.
3. Write one encouraging sentence as an overall comment on the student's attempt,
   in {explanation_language}.

Original student text:
"""{user_text}"""

Mistakes with corrections (JSON):
{explained_mistakes}

Return JSON only. Format:
{
  "corrected_text": "<full corrected version of the text>",
  "recommendations": ["<recommendation 1>", "<recommendation 2>"],
  "comment": "<one encouraging sentence>"
}
```

**Key design point:** Correction derived from structured `explained_mistakes`, not regenerated freeform. More consistent, easier to verify against judge fixtures.

---

### `skills/summarise_session/writing/` — Session Summariser (`summarise_writing_session`)

**Layer:** 1a — Step 7 (runs in parallel with Step 6, `write_correction`)
**Type:** session

Module-specific variant of `summarise_session`, invoked as `SummariseWritingSessionSkill`.
Takes the same `explained_mistakes` as `write_correction` and produces the fields that
actually reach the session file and the user-facing report — `write_correction`'s own
`recommendations`/`comment` are superseded by this skill's output (see that skill above).

**Input:**
```python
user_text: str
explained_mistakes: list[dict]    # from explain_mistakes (Step 5)
level: str
```

**Output:**
```python
tips: list[str]                # short next-step suggestions, sorted by distance from user level
session_summary: str           # one-sentence overall comment
mistakes: list[dict]           # explained_mistakes enriched with severity
# severity: "critical" | "expected" | "minor", added per mistake
```

**Notes:**
- Short-circuits without an LLM call if `explained_mistakes` is empty, returning a canned
  "no mistakes" summary and no tips.
- `severity` grouping and `tips` ordering are what `PipelineResult.tips` /
  `.session_summary` actually carry downstream — not `write_correction`'s
  `recommendations`/`comment`.

**Test criteria (judge):** `tests/judge/judge_summary.py` — severity assignment and tip
quality (no separate per-skill judge file; this skill is covered by the aggregator, unlike
most other Step skills in this pipeline).

---

### `skills/topic_picker/` — Topic Picker

**Layer:** 1b
**Type:** session

**Input:**
```python
level: str
suggested_focus: str | None    # from orchestrator recommendation
recent_topics: list[str]       # avoid repetition
vocab_flags: list[dict]        # avoid relying on unknown words
user_override: str | None      # user's own topic — bypasses LLM call entirely
```

**Output:**
```python
@dataclass
class WritingPrompt:
    topic: str
    requirements: str       # word count, target tense, grammar focus
    suggested_focus: str    # grammar point to demonstrate
```

**Prompt template:**
```
Generate a German writing prompt for a {level} learner.

Focus grammar area: {suggested_focus}
Avoid these recent topics: {recent_topics}
Avoid vocabulary that requires these words: {flagged_vocab_sample}
Target word count: {word_count}

Return JSON only:
{
  "topic": "Describe your last holiday",
  "requirements": "150-200 words, use Perfekt tense, include at least 2 dative prepositions",
  "suggested_focus": "dative case prepositions"
}
```

**Bypass:** If `user_override` is provided, skip LLM call entirely. Wrap in `WritingPrompt` with requirements set to defaults. Log that user provided own topic.

---

### `skills/btw_handler/` — /btw Handler

**Layer:** PoC
**Type:** utility

A utility skill — not a standalone session. Invoked inline during any active module session when user types `/btw [question]`. No session file written. Returns `BtwEntry` for orchestrator to persist.

**Input:**
```python
question: str
session_context: dict     # current module, topic, user_text_so_far, level, explanation_language
```

**Output:**
```python
answer: str
flagged_word: str | None  # extracted if vocabulary question
```

**Prompt template:**
```
You are a {language} language tutor assistant. A student is mid-session and has a quick question.

Current session context:
- Module: {module}
- Topic: {topic}
- Student's text so far: {user_text_so_far}
- Student level: {level}

Student's question: {question}

Answer concisely, explaining in {explanation_language} (use {language} only for translations, examples, and vocabulary words). Answer in context. If the question is about a specific word, define it clearly and note if it's relevant to what they're writing.
```

`explanation_language` comes from `ctx.parameters` the same way every other module
gets it (`orchestrator/session_manager.py`'s `build_module_context`), defaulting to
English if unset — previously hardcoded to English regardless of the user's
`profile.explanation_language` setting; see `docs/_CHECKLIST.md`'s Message Catalog
entry for the broader audit this was found and fixed alongside.

**Word extraction:** After answering, attempt to extract a single target language word from the question if it's vocabulary-related (regex pattern: quoted word, or "what does X mean", "how do I say X"). Fall back to LLM extraction if regex fails.

**Inline loop integration:**
```python
# Inside module input loop:
if user_input.startswith("/btw "):
    question = user_input[5:].strip()
    output = btw_handler.run(BtwInput(question, session_context), llm)
    btw_entries.append(BtwEntry(...))
    display(output.answer)
    continue   # session loop continues, state unchanged
```

---

## Error Taxonomy

Loaded at runtime from `lang/maps/taxonomy/` YAML files via `lang.loader.get_taxonomy(language)`. Language configs point to the active taxonomy version; a default fallback covers unconfigured languages.

All `error_tag` values in `classify_mistakes` output are validated against the loaded taxonomy. Unknown tags fall back to `"other"` via `taxonomy.validate_tag()`. To add tags without breaking existing fixtures, create a new taxonomy version file and update the language config — do not edit an in-use version in place.

See `docs/_contracts.md` for the current German taxonomy tags.

---

## Writing History Summary (Layer 2b)

Not a per-session field and not automatic — earlier design drafts had a
`WritingSessionContent.comparison_note` stub (Layer 1a Step 6) meant to be filled in with a
diff against the immediately-previous session, right when a session ends. That stub is
removed; nothing populates it.

Instead, an on-demand `/history` command, typed at the existing "Start this module? [Y/n]"
prompt (`orchestrator.py::_get_confirmed_module`) — same interaction shape as `/btw`, works
identically in CLI and web since both go through the generic `IOHandler.prompt()`. Not tied
to whichever session (if any) just finished; available any time before starting a module.

- `/history` — last `DEFAULT_HISTORY_SESSIONS` (10) completed writing sessions
- `/history <n>` — last `n` sessions
- `/history <n>d` — last `n` days

Data sources — no new `StorageProtocol` methods beyond one field addition:
- `store.get_sessions_by_module(user_id, language, "writing")` (existing), filtered to
  `status == "completed"` and bounded by count or date cutoff in Python
- `SessionLog.text_level_estimate` (new field) across the filtered sessions, for a CEFR-level
  trend — the one schema addition this layer needs

From the filtered `SessionLog`s, Python builds: topics covered (`task_label`s), recurring
mistake tag counts (`errors[].error_tag`), and the chronological level-estimate list. These
pre-aggregated inputs — not raw session objects — go to `skills/summarize_writing_history/`,
which returns one readable `history_summary` string via `io.output()`. Nothing is written
back to any session file; the report is regenerated on every request.
