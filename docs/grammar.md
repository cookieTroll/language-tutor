# GermanTutor — Grammar Module & Skills

Layer 2a. Four atomic skills composing a grammar practice session.

See `docs/contracts.md` for `ModuleProtocol`, `SkillProtocol`, `GrammarSessionContent`.

---

## Grammar Module (`modules/grammar/`)

**Goal:** Conduct a grammar practice session — select a topic based on the user's weakness profile, explain the grammar point, generate targeted exercises, validate answers, and log errors.

**Layer:** 2a

### `module.md` spec

```
name: grammar
description: Conducts a German grammar session. Selects a topic based on
             recurring errors and recency, provides an explanation at the
             user's level, generates targeted exercises, validates answers,
             and logs error patterns for future routing.
skill_type: session
```

### Context request (`modules/grammar/agent.py`)

```python
def context_request(self) -> ContextRequest:
    return ContextRequest(
        recent_sessions_n=10,
        module_filter="grammar",
        include_error_frequency=True,
        include_recent_topics=True,
        include_vocab_flags=False,
    )
```

### Skills injected (`modules/grammar/skills.py`)

| Layer | Skill | Role |
|-------|-------|------|
| 2a | `select_grammar` | topic selection |
| 2a | `dump_grammar` | comprehensive explanation |
| 2a | `generate_exercises` | exercise generation |
| 2a | `grade_exercises` | one batched call: judges open-ended exercises + produces feedback for every wrong answer, exact-match included |
| PoC | `btw_handler` | utility — inline /btw questions |

`explain_grammar` (originally planned as a separate utility skill) was dropped — `grade_exercises` absorbs its only required use. See Backlog.

### Session flow (`modules/grammar/agent.py`)

Exercises are answered as a single block, not one at a time — this mirrors the
writing module's existing pattern (`#writing-pad` → one `prompt()`/`send_input()`
call → full evaluation), so `IOHandler` needs no new protocol: `prompt()` already
returns one opaque string and the web client can already post a multi-line
textarea value in one shot. The CLI (`TerminalIOHandler.prompt()`) is the one
adjustment needed — `input()` only reads one line, so it must read until a
blank line to collect the block.

```
1. select_grammar(error_frequency, recent_topics, level) → topic
2. dump_grammar(topic, level) → explanation
3. Display explanation to user
4. generate_exercises(topic, level) → exercises[] (each tagged exercise_type + grading mode)
5. Display all exercises as one numbered block
6. Accept answers as a single multi-line block — one line per exercise, in order
   └─ /btw handled inline at any point before submission
7. Split the block by newline (pad/truncate to exercise count) and check:
   a. Exact-match exercises (fill_in_the_blank, multiple_choice, true_false)
      → compared in Python, normalised (lowercase, stripped) — no LLM call,
      correctness already known
   b. Open-ended exercises (error_correction, transformation, word_order,
      sentence_completion, sentence_combining, translation)
      → correctness not knowable in Python; deferred to step 8
8. One batched grade_exercises call: judges every open-ended exercise for
   correctness, and produces feedback for every wrong answer overall —
   open-ended ones it judged itself, exact-match ones Python already flagged
   wrong in step 7a (those just need feedback phrasing, not a correctness
   judgment) — see `grade_exercises` below for the `already_known_wrong` split
9. Log errors to session errors list
10. Compute score = correct / total
11. Return (ModuleResult, GrammarSessionContent)
```

`GrammarSessionContent.items` holds every exercise from the set, correct and
incorrect alike, each explicitly carrying `correct: bool` (and `feedback`
only populated when `correct == False`) — not just the misses. Mirrors why
the writing session file keeps the full `corrected_text` rather than only a
list of edits: for later browsing, the whole worked exercise set is more
useful than an isolated mistake list.

### `ModuleResult.metadata` keys

```python
{
  "btw_entries": [BtwEntry, ...],
}
```

`score` and `topic` are not duplicated into `metadata` — they're already typed fields on `GrammarSessionContent`, and `metadata` is reserved for things the orchestrator must separately persist elsewhere (matches the documented convention: `btw_entries` → btw_log, `vocab_signals` → vocab_flags). Grammar sessions don't produce `vocab_signals` (`include_vocab_flags=False` in `context_request()`).

---

## Skills

### `skills/select_grammar/` — Grammar Selector

**Layer:** 2a
**Type:** session

**Input:**
```python
error_frequency: dict[str, int]   # error_tag → count across sessions
recent_topics: list[str]          # grammar topics covered recently
level: str
```

**Output:**
```python
topic: str                    # curated topic string, or an LLM-proposed one when scope is minor
difficulty: str                # A1 | A2 | B1 | B2
scope: Literal["major", "minor"]  # major = from the curated map; minor = proposed on the fly
reason: str                    # why this topic, for logging/debugging
```

**Topic list:** `lang/maps/grammar_topics/{name}.yaml`, loaded via `lang.loader.get_grammar_topics(language)` — see "Grammar Topics Map" below for the authoritative schema (`topic`, `difficulty`, `scope: major`, `related_error_tags`). Not duplicated here; this section only describes how `select_grammar` *uses* that map.

**Prompt template:**
```
You are selecting a German grammar topic for a {level} learner.

Curated major topics for this language/level (YAML — the syllabus backbone):
{grammar_topics_yaml}

Recurring errors (error_tag → count):
{error_frequency_json}

Recently covered topics (avoid):
{recent_topics}

Prioritise a major topic linked to a recurring error that hasn't been
covered recently. If none of the major topics fit the recurring errors well
(e.g. the error is a small/idiomatic point like connector word choice, not
covered by the syllabus backbone), propose your own topic instead and mark
it as minor — do not force a poor-fitting major topic just to stay on the list.

Return JSON only:
{
  "topic": "Dative case — prepositions",
  "difficulty": "B1",
  "scope": "major",
  "reason": "noun_declension error appeared 4 times in recent writing sessions"
}
```

---

### `skills/dump_grammar/` — Grammar Dump

**Layer:** 2a
**Type:** session

Comprehensive reference-style explanation of a grammar topic. Full rules, all cases, edge cases, tables, examples. Think textbook entry.

**Input:**
```python
topic: str
level: str
```

**Output:**
```python
explanation: str    # rich markdown — headers, tables, examples
```

**Prompt template:**
```
You are a German grammar teacher writing a comprehensive explanation of:
"{topic}"

Target level: {level}

Include:
- Core rule statement
- Full declension table or conjugation table if applicable
- Common cases and edge cases
- 4-6 example sentences with translations
- Common mistakes to avoid

Format as markdown. Be thorough — this is a reference explanation, not a quick note.
```

**Notes:**
- Output is markdown, rendered in UI (Layer 1c)
- Not validated by taxonomy — explanation text, not structured errors
- Generates `GrammarSessionContent` partial (topic + explanation, exercises added later)

---

### `skills/generate_exercises/` — Exercise Generator

**Layer:** 2a
**Type:** session

Generates targeted exercises for a grammar topic. Validates user answers. Logs errors.

**Input:**
```python
topic: str
level: str
exercise_count: int = 5
```

**Output:**
```python
exercises: list[dict]
# [{
#   prompt: str,
#   exercise_type: str,       # see table below
#   grading: "exact" | "llm", # determined by exercise_type
#   correct_answer: str,
#   accepted_answers: list[str],  # optional alternates, exact-match only
#   error_tag: str,            # what error this exercise targets
#   distractor_hint: str,      # common wrong answer pattern
# }]
```

**Exercise types (vary by topic):**

| `exercise_type` | Grading | Example |
|---|---|---|
| `fill_in_the_blank` | exact | "Ich fahre ___ meinem Freund. (with)" |
| `multiple_choice` | exact | Options rendered as text ("a) mit  b) bei  c) nach"); user types the letter or word |
| `true_false` | exact | Statement about a rule or sentence; user types richtig/falsch |
| `error_correction` | llm | "Find and fix the error: Ich habe gestern ins Kino gegangen." |
| `transformation` | llm | "Rewrite using Perfekt: Ich esse einen Apfel." |
| `word_order` | llm | Words given as `wort1 / wort2 / ... / wortN`; two modes: **reorder** (words already inflected, just scrambled — tests word order only) or **build** (words in base/dictionary form — tests word order + conjugation/case together) |
| `sentence_completion` | llm | "Finish: Obwohl es regnet, ___" |
| `sentence_combining` | llm | Two short sentences + a connector cue ("Combine using *sondern*") — natural home for small/idiomatic topics (e.g. `sondern` vs `aber`) that don't fit a curated major-topic list |
| `translation` | llm | English cue → German answer (or reverse) |

Split rationale: single-token/discrete-choice answers (`fill_in_the_blank`,
`multiple_choice`, `true_false`) have one unambiguous correct string, so exact
match (normalised) is reliable and free. Whole-sentence-construction answers
have multiple valid phrasings in German (word order flexibility, synonym
choice), so string equality would produce false negatives — those are graded
by the LLM instead.

**Prompt template:**
```
Generate {exercise_count} German grammar exercises on:
"{topic}"

Level: {level}
Exercise types to use: {exercise_types}

Return JSON only:
{
  "exercises": [
    {
      "type": "fill_in_the_blank",
      "prompt": "Ich fahre ___ meinem Freund. (with)",
      "correct_answer": "mit",
      "error_tag": "dative_case",
      "distractor_hint": "Students often confuse 'mit' + accusative"
    }
  ]
}
```

**`error_tag` validation:** each generated exercise's `error_tag` must be validated against the language's `TaxonomyMap.validate_tag()` — same as `classify_mistakes` does for writing — with `call_with_self_correction` retry on an invalid tag. An LLM-hallucinated tag would otherwise silently corrupt `error_frequency`/`select_grammar`'s downstream lookups.

**Answer validation:** Done inside the module (`modules/grammar/agent.py`), not inside `generate_exercises`.
- `grading: exact` exercises → plain Python loop, no LLM call: compare user answer to `correct_answer` or any of `accepted_answers` (normalised: lowercase, stripped).
- `grading: llm` exercises → correctness can't be determined in Python.
- Both wrong-exact-match and all llm-graded exercises are then sent together into one batched `grade_exercises` call (see below), which returns `feedback` for every wrong answer.

Either path: if incorrect, logs error with `error_tag` from exercise.

---

### `skills/grade_exercises/` — Exercise Grader & Feedback Generator

**Layer:** 2a
**Type:** session

One batched call, two jobs: judges correctness for exercises Python can't
resolve on its own (`grading: llm` — multiple valid phrasings, e.g.
`error_correction`, `transformation`, `word_order`, `sentence_completion`,
`sentence_combining`, `translation`), and produces feedback text for every
wrong answer in the set — including `grading: exact` exercises the module
already determined wrong via plain string comparison. Same list-in/list-out
shape as `classify_mistakes`; this replaces the standalone `explain_grammar`
utility originally planned for the exact-match half (see Backlog).

**Input:**
```python
items: list[dict]
# [{
#   index: int,
#   prompt: str,
#   correct_answer: str,      # reference exemplar, not a strict key
#   error_tag: str,
#   topic: str,
#   user_answer: str,
#   already_known_wrong: bool,  # True: exact-match item Python already scored
#                                # wrong — skip correctness judgment, just
#                                # produce feedback. False: llm-graded item —
#                                # judge correctness AND produce feedback if wrong.
# }]
level: str
```

Only exercises that need a call are included: `grading: exact` items that
came back *correct* never reach this skill (nothing to judge, no feedback
needed); every `grading: llm` item is included regardless of a Python-side
guess, since correctness can't be determined without the LLM.

**Output:**
```python
results: list[dict]
# [{
#   index: int,
#   correct: bool,   # for already_known_wrong items, always false — unchanged, just carried through
#   feedback: str,   # only populated when correct == False; 1-3 sentences, direct
# }]
```

**Prompt template:**
```
Grade these {level} German grammar exercises on "{topic}". Some answers are
already known to be wrong (marked already_known_wrong) — for those, just
explain why, don't re-judge them. For the rest, answers may be phrased
differently from the reference and still be correct — judge on grammatical
correctness and whether the target rule was applied, not on exact wording.

{items_json}

Return JSON only:
{
  "results": [
    {"index": 0, "correct": false, "feedback": "..."},
    {"index": 1, "correct": true, "feedback": ""}
  ]
}
```

---

## Grammar Topics Map

Follows the same versioned-map pattern as `taxonomy` / `cefr_hints` /
`writing_word_ranges`: `lang/languages/german.yaml` gets a new
`grammar_topics: german_a1_b2` key resolved against
`lang/maps/grammar_topics/german_a1_b2.yaml`. Per-language, not hardcoded
under `skills/`, so a second language config doesn't have to reach into the
grammar skill's folder to supply its own list.

Each entry is a curated **major** topic — the syllabus backbone — tied to
`related_error_tags` from the language's taxonomy map. `select_grammar`
prioritises `scope: major` topics linked to recurring errors that haven't
been covered recently; small/idiomatic topics (connector words, fixed
expressions) are not enumerated here — the LLM proposes those on the fly
in `select_grammar` when no major topic fits, tagged `scope: minor` in its
output. `scope: major` on curated entries lets the selection prompt
distinguish "cover the syllabus" from "patch a one-off error."

Sample structure:

```yaml
- topic: "Present tense — regular verbs"
  difficulty: A1
  scope: major
  related_error_tags: ["verb_conjugation"]

- topic: "Articles — nominative case"
  difficulty: A1
  scope: major
  related_error_tags: ["article"]

- topic: "Separable verbs — present tense"
  difficulty: A2
  scope: major
  related_error_tags: ["verb_conjugation", "word_order"]

- topic: "Dative case — prepositions"
  difficulty: B1
  scope: major
  related_error_tags: ["noun_declension"]

- topic: "Adjective endings — all cases"
  difficulty: B2
  scope: major
  related_error_tags: ["adjective_declension"]
```

`related_error_tags` values must match `lang/maps/taxonomy/german_taxonomy_v1.yaml`
tags exactly (`noun_declension`, `adjective_declension`, `article`,
`verb_conjugation`, `verb_tense`, `word_order`, `vocabulary`, `spelling`,
`other`) — cross-validated at load time the same way `lang/loader.py`
validates `taxonomy`/`cefr_hints` references today.

Full list to be compiled from Goethe Institut A1–B2 curriculum before Layer 2a implementation. Review for accuracy before use.

---

## Backlog / Deferred

- **`skills/explain_grammar/`** — originally planned as a standalone utility
  ("why is this wrong?", singular fragment/correction/error_tag input,
  reused both by the grammar module and the writing module's follow-up
  phase). Dropped from Layer 2a: the grammar module's only need for it is
  covered by `grade_exercises`'s batched feedback, and the writing module's
  follow-up phase (`modules/writing/agent.py:250` `_follow_up_phase`)
  already routes "why is this wrong?" questions through `btw_handler`
  (see 2a-vi in `docs/CHECKLIST.md` — that path needs the evaluation
  results threaded into its `session_context`, not a new skill). Revisit
  only if a concrete future need for an ad hoc, system-triggered "explain
  this one thing" call emerges that batching can't cover.

Exercise types considered and deliberately deferred — not part of the Layer
2a `generate_exercises` type set:

- **Matching** (e.g. match German word to English meaning) — no reliable
  free-text answer format. Typed pairings like "1-c, 2-a" are fragile to
  parse/validate, and the current UI has no click-to-pair widget (only a
  single text input / textarea, see `ui/static/app.js`). Would need a new
  UI component to do properly.
- **Multi-blank cloze paragraphs** (several blanks in one passage) — breaks
  the one-exercise-one-`correct_answer` model; would need its own multi-answer
  parsing/validation path instead of the flat exact/llm split used everywhere
  else. Revisit once the block-answer UI (see Session flow) is proven out for
  single-answer exercises.
- **Audio/dictation** — no audio pipeline exists in the app (`llm/`, `ui/`
  are text-only end to end). Out of scope until TTS/ASR is added.
