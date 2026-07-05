# GermanTutor — Writing Module & Skills

The writing module is the PoC showpiece. Composed of atomic skills, it handles topic selection, error detection, feedback generation, and correction writing.

See `docs/contracts.md` for `ModuleProtocol`, `SkillProtocol`, `WritingSessionContent`.

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

Execution order: **Step 5 → 1 → 1.5 → 2 → 3 → 4 → 6**. Step 5 (`estimate_text_level`) runs first because it only needs the raw user text; Step 1 (`detect_mistakes`) acts as a gate — if no mistakes are found, Step 1.5 and Steps 2–4 are skipped. Step 1.5 (`verify_mistakes`) re-checks each raw fragment against its original sentence context and drops false positives before classification — `detect_mistakes` judges the whole text in one pass and can misjudge an isolated fragment (e.g. correct verb-second word order after a fronted connector).

Returns `PipelineResult` dataclass carrying all per-step outputs.

### Skills injected

| Layer | Skill | Role |
|-------|-------|------|
| PoC | `btw_handler` | utility — inline /btw questions during writing |
| 1a | `detect_mistakes` | Step 1 — raw mistake detection (gate) |
| 1a | `verify_mistakes` | Step 1.5 — re-checks each candidate against context, drops false positives |
| 1a | `classify_mistakes` | Step 2 — taxonomy classification |
| 1a | `explain_mistakes` | Step 3 — explanations pitched to level |
| 1a | `write_correction` | Step 4 — corrected text + tips + session summary |
| 1a | `estimate_text_level` | Step 5 — CEFR band estimation (runs first, independent) |
| 1a | `summarise_session` | Step 6 — severity-grouped summary |
| 1b | `topic_picker` | topic generation |

### Session flow (`modules/writing/agent.py`)

```
PoC flow:
  1. Use hardcoded topic (PoC) or pick_topic skill (1b)
  2. Display topic + requirements to user
  3. Accept multi-line text input (blank line or /end to submit)
     └─ /btw [question] handled inline at any point during writing
  4. detect_mistakes(user_text, topic, level) → raw mistakes   [PoC]
     process_mistakes(raw_mistakes) → classified               [1a]
     generate_feedback(classified, level) → explained          [1a]
     write_correction(user_text, classified) → corrected       [1a]
  5. Display feedback to user (mistakes, explanations, corrected text)

  6. Review loop                                               [1a]
     User may ask follow-up questions about specific mistakes.
     Loop continues until user types /done or /end.

     For each follow-up:
       if grammar question → explain_grammar(mistake, correction, error_tag, level)
       if vocab/usage question → btw_handler(question, session_context)
       display answer, continue loop

     Context available in review loop:
       - full classified mistake list
       - user's original text
       - corrected text
       - current session topic + level

  7. Return (ModuleResult, WritingSessionContent)
```

**Phase distinction:**
- **Writing phase** (step 3): `/btw` for quick inline questions that don't break flow. User is mid-composition.
- **Review phase** (step 6): explicit Q&A after evaluation. User is reading feedback and asking "why?". Both `explain_grammar` and `btw_handler` available here, with richer context than during writing.

### `ModuleResult.metadata` keys

```python
{
  "btw_entries": [BtwEntry, ...],      # from both writing and review phases
  "vocab_signals": ["word1", ...],     # for orchestrator → vocab_flags
  "review_qa": [                       # post-evaluation Q&A log
      {"question": str, "answer": str, "skill": "explain_grammar|btw_handler"}
  ],
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
raw_mistakes: list[dict]   # verified_mistakes from verify_mistakes (Step 1.5), not detect_mistakes' raw output directly
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
```

**Output:**
```python
explained: list[dict]     # [{error_tag, fragment, correction, explanation}]
# explanation pitched to level
```

**Notes:**
- Short-circuits gracefully if `classified` is empty — returns empty list
- Explanation depth calibrated to level: A1 = very simple, B1 = rule + example, B2+ = nuance

---

### `skills/write_correction/` — Correction Writer

**Layer:** 1a
**Type:** session

**Input:**
```python
user_text: str
classified: list[dict]    # from process_mistakes (structured, not freeform)
level: str
```

**Output:**
```python
corrected_text: str
tips: list[str]            # actionable next-steps (formerly recommendations)
session_summary: str       # overall comment (formerly comment)
```

**Prompt template:**
```
Apply the following corrections to the student's text and produce a corrected version.
Do not change anything that is not in the corrections list.

Student text:
{user_text}

Corrections to apply:
{corrections_json}   # [{fragment, correction}] — derived from classified

Also provide:
- 2-3 actionable recommendations for what to focus on next
- A 1-2 sentence overall comment on the student's performance

Return JSON only:
{
  "corrected_text": "...",
  "recommendations": ["Review dative prepositions", "..."],
  "comment": "Good sentence variety. Main issue is dative case after prepositions."
}
```

**Key design point:** Correction derived from structured `classified` list, not regenerated freeform. More consistent, easier to verify against judge fixtures.

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
session_context: dict     # current module, topic, user_text_so_far, level
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

Answer concisely, explaining in English (use {language} only for translations, examples, and vocabulary words). Answer in context. If the question is about a specific word, define it clearly and note if it's relevant to what they're writing.
```

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

See `docs/contracts.md` for the current German taxonomy tags.

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
