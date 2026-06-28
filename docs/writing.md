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
skill_type: session
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

### Skills injected (`modules/writing/skills.py`)

| Layer | Skill | Role |
|-------|-------|------|
| PoC | `detect_mistakes` | Step 1 — raw mistake detection |
| PoC | `btw_handler` | utility — inline /btw questions during writing |
| 1a | `process_mistakes` | Step 2 — classify + taxonomy |
| 1a | `generate_feedback` | Step 3 — explanations |
| 1a | `write_correction` | Step 4 — corrected text |
| 1a | `explain_grammar` | utility — post-evaluation grammar follow-up |
| 1b | `pick_topic` | topic generation |

`explain_grammar` is a shared utility skill (also used by grammar module). Injected here for the post-evaluation review loop.

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

**Test criteria (judge):** Detection accuracy (real errors caught), false positive rate (non-errors flagged).

---

### `skills/process_mistakes/` — Mistake Processor

**Layer:** 1a
**Type:** session

**Input:**
```python
raw_mistakes: list[dict]   # from detect_mistakes
user_text: str
```

**Output:**
```python
classified: list[dict]     # [{fragment, error_tag, correction}]
# error_tag validated against ERROR_TAXONOMY before return
```

**Prompt template:**
```
Classify each mistake and provide the correct German form.

User text:
{user_text}

Raw mistakes:
{raw_mistakes_json}

Valid error tags: {taxonomy_list}

Return JSON only:
{
  "classified": [
    {
      "fragment": "mit meinen Bruder",
      "error_tag": "dative_case",
      "correction": "mit meinem Bruder"
    }
  ]
}
```

**Post-processing:** `validate_error_tag()` called on every `error_tag` in output. Unknown tags raise `TaxonomyError` and must be retried or removed before proceeding to Step 3.

---

### `skills/generate_feedback/` — Feedback Generator

**Layer:** 1a
**Type:** session

**Input:**
```python
classified: list[dict]    # from process_mistakes
level: str
```

**Output:**
```python
feedback: list[dict]      # [{error_tag, fragment, correction, explanation}]
# explanation pitched to level
```

**Prompt template:**
```
You are a {language} language teacher explaining errors to a {level} learner.

For each mistake, write a clear, concise explanation appropriate for this level.
Do not over-explain. Be specific about the rule.

Mistakes:
{classified_json}

Return JSON only:
{
  "feedback": [
    {
      "error_tag": "dative_case",
      "fragment": "mit meinen Bruder",
      "correction": "mit meinem Bruder",
      "explanation": "After 'mit', German requires dative case. The masculine dative article is 'meinem', not 'meinen'."
    }
  ]
}
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
recommendations: list[str]
comment: str
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

### `skills/pick_topic/` — Topic Picker

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

Shared across all writing skills. Defined in `skills/detect_mistakes/taxonomy.py`.

```python
ERROR_TAXONOMY = {
    "dative_case", "accusative_case", "genitive_case",
    "word_order", "verb_position", "separable_verb",
    "article_gender", "adjective_ending",
    "verb_conjugation", "tense_usage",
    "vocabulary", "spelling",
}
```

All `error_tag` values in `process_mistakes` output must be from this set. Validated before proceeding to `generate_feedback`. Tags may be extended as new error patterns emerge — do not add retroactively to old sessions.

---

## Cross-Session Writing Comparison (Layer 2b)

After `write_correction`, if a previous writing session file exists:
- Load previous `WritingSessionContent` from storage
- LLM generates a brief comparison: what improved, what persisted
- Added to `WritingSessionContent.comparison_to_previous`
- Requires `StorageProtocol.get_writing_sessions()` method
