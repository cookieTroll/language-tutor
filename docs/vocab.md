# LanguageTutor — Vocab Module & Skills

> **Status: not implemented.** Layer 3a was cut — `modules/vocab/` and `skills/drill_vocab/`
> do not exist in the codebase. This document is a design spec for future work, not a
> record of shipped behavior. See `docs/_design.md`'s Delivery Layers table and
> `docs/_CHECKLIST.md` for current scope.

Layer 3a. Lightweight drilling from static word lists, seeded by the negative vocab list.

See `docs/_contracts.md` for `ModuleProtocol`, `SkillProtocol`, `SessionFileContent`.

---

## Vocab Module (`modules/vocab/`)

**Goal:** Drill vocabulary from static word lists, prioritising words on the negative vocab list (unknown/misused words flagged in previous sessions).

**Layer:** 3a

**Non-goal:** Spaced repetition. That belongs to Anki. This module provides in-session drilling; Anki export (Layer 3c) handles long-term retention.

### `module.md` spec

```
name: vocab
description: Drills German vocabulary using gap-fill and translation exercises.
             Prioritises words flagged as unknown or misused in past sessions.
             Lightweight — no spaced repetition logic.
skill_type: session
```

### Context request (`modules/vocab/agent.py`)

```python
def context_request(self) -> ContextRequest:
    return ContextRequest(
        recent_sessions_n=3,
        module_filter="vocab",
        include_error_frequency=False,
        include_recent_topics=False,
        include_vocab_flags=True,     # primary signal for word selection
    )
```

### Skills injected (`modules/vocab/skills.py`)

| Layer | Skill | Role |
|-------|-------|------|
| 3a | `drill_vocab` | exercise generation + validation |
| PoC | `btw_handler` | utility — inline /btw questions |

### Session flow (`modules/vocab/agent.py`)

```
1. Load word pool:
   a. Words from vocab_flags (high occurrence_count first)
   b. Top up from static word lists if pool < target count
2. drill_vocab(word_pool, level) → exercises[]
3. For each exercise:
   a. Display prompt
   b. Accept answer
      └─ /btw handled inline at any point
   c. Validate → correct | incorrect
   d. If incorrect: increment word's occurrence_count signal
      add to session vocab_signals
4. Compute score
5. Return (ModuleResult, VocabSessionContent)
```

### `ModuleResult.metadata` keys

```python
{
  "btw_entries": [BtwEntry, ...],
  "vocab_signals": ["word1", ...],   # words answered incorrectly → vocab_flags
  "score": float,
}
```

---

## Skills

### `skills/drill_vocab/` — Vocab Drill

**Layer:** 3a
**Type:** session

Generates gap-fill and translation exercises from a provided word pool.

**Input:**
```python
word_pool: list[dict]    # [{word, translation, example}]
level: str
exercise_count: int = 10
```

**Output:**
```python
exercises: list[dict]
# [{
#   type: "gap_fill" | "translation",
#   prompt: str,
#   correct_answer: str,
#   word: str,            # which word this tests
# }]
```

**Exercise types:**

`gap_fill` — fill in the missing word:
```
"Ich ___ jeden Morgen um sieben Uhr auf." (aufstehen)
Answer: stehe ... auf
```

`translation` — translate the German word:
```
"What does 'aufstehen' mean?"
Answer: to get up / to stand up
```

**Prompt template:**
```
Generate {exercise_count} German vocabulary exercises for a {level} learner.

Word pool:
{word_pool_json}

Mix gap-fill and translation exercises. Use the provided example sentences
as a basis for gap-fill prompts where possible.

Return JSON only:
{
  "exercises": [
    {
      "type": "gap_fill",
      "prompt": "Ich ___ jeden Morgen um sieben Uhr auf.",
      "correct_answer": "stehe ... auf",
      "word": "aufstehen"
    },
    {
      "type": "translation",
      "prompt": "What does 'der Bahnhof' mean?",
      "correct_answer": "train station",
      "word": "Bahnhof"
    }
  ]
}
```

**Answer validation:** Done inside module loop. Normalised comparison (lowercase, stripped, accept reasonable synonyms for translations). If incorrect, word added to `vocab_signals` for orchestrator to write to `vocab_flags`.

---

## Word Lists

Static YAML files. Each entry: word, translation, example sentence, difficulty.

### `skills/drill_vocab/word_lists/greetings.yaml`

```yaml
- word: "Guten Morgen"
  translation: "Good morning"
  example: "Guten Morgen! Wie geht es Ihnen?"
  difficulty: A1

- word: "Auf Wiedersehen"
  translation: "Goodbye (formal)"
  example: "Auf Wiedersehen, bis morgen!"
  difficulty: A1

- word: "bitte"
  translation: "please / you're welcome"
  example: "Ein Kaffee, bitte."
  difficulty: A1
```

### `skills/drill_vocab/word_lists/daily_routine.yaml`

```yaml
- word: "aufstehen"
  translation: "to get up"
  example: "Ich stehe jeden Morgen um sieben Uhr auf."
  difficulty: A2

- word: "frühstücken"
  translation: "to have breakfast"
  example: "Wir frühstücken zusammen."
  difficulty: A2

- word: "einschlafen"
  translation: "to fall asleep"
  example: "Ich schlafe meistens um Mitternacht ein."
  difficulty: A2
```

### Adding word lists

Add a new YAML file to `skills/drill_vocab/word_lists/`. Module loads all files in the directory at startup. No code changes required.

Review all word lists for accuracy before Layer 3a implementation.

---

## Anki Export (Layer 3c)

The negative vocab list (`vocab_flags` table) is the primary source for Anki card creation.

Export format: `{word}\t{translation}\t{example}\n` — Anki basic import format.

Output path: `data/exports/{user_id}_anki_{date}.txt`

Export triggered via CLI option or UI button. User imports file into Anki manually (File → Import). Full AnkiConnect integration (REST API via local plugin) deferred to post-Layer 3c.

---

## `VocabSessionContent`

```python
@dataclass
class VocabSessionContent(SessionFileContent):
    words_drilled: list[str]
    exercise_results: list[dict]    # [{word, type, user_answer, correct}]
    score: float
    btw_log: list[dict]

    def to_dict(self) -> dict: ...
```
