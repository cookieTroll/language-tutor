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
| 2a | `generate_exercises` | exercise generation + validation |
| 2a | `explain_grammar` | utility — inline "why is this wrong?" |
| PoC | `btw_handler` | utility — inline /btw questions |

### Session flow (`modules/grammar/agent.py`)

```
1. select_grammar(error_frequency, recent_topics, level) → topic
2. dump_grammar(topic, level) → explanation
3. Display explanation to user
4. generate_exercises(topic, level) → exercises[]
5. For each exercise:
   a. Display prompt to user
   b. Accept answer
      └─ /btw handled inline at any point
   c. Validate answer → correct | incorrect + correction
   d. If incorrect: explain_grammar(fragment, error_tag) → inline note
   e. Log error to session errors list
6. Compute score = correct / total
7. Return (ModuleResult, GrammarSessionContent)
```

### `ModuleResult.metadata` keys

```python
{
  "btw_entries": [BtwEntry, ...],
  "score": float,
  "topic": str,
}
```

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
topic: str        # e.g. "Dative case — prepositions"
difficulty: str   # A1 | A2 | B1 | B2
```

**Topic list:** `skills/select_grammar/topics/a1_b2_topics.yaml`

Curated YAML list sourced from standard German syllabi (A1–B2). Each entry:
```yaml
- topic: "Dative case — prepositions"
  difficulty: B1
  related_error_tags: ["dative_case"]
  aliases: ["mit bei nach seit von zu", "dative prepositions"]
```

**Prompt template:**
```
You are selecting a German grammar topic for a {level} learner.

Available topics (YAML):
{topics_yaml}

Recurring errors (error_tag → count):
{error_frequency_json}

Recently covered topics (avoid):
{recent_topics}

Select the most relevant topic. Prioritise topics linked to recurring errors
that have not been covered recently.

Return JSON only:
{
  "topic": "Dative case — prepositions",
  "difficulty": "B1",
  "reason": "dative_case error appeared 4 times in recent writing sessions"
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
#   correct_answer: str,
#   error_tag: str,         # what error this exercise targets
#   distractor_hint: str,   # common wrong answer pattern
# }]
```

**Exercise types (vary by topic):**
- `fill_in_the_blank` — "Ich fahre ___ meinem Freund. (with)"
- `transformation` — "Rewrite using Perfekt: Ich esse einen Apfel."
- `error_correction` — "Find and fix the error: Ich habe gestern ins Kino gegangen."

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

**Answer validation:** Done inside module loop, not inside skill. Module compares user answer to `correct_answer` (normalised: lowercase, stripped). If incorrect, logs error with `error_tag` from exercise.

---

### `skills/explain_grammar/` — Grammar Explainer

**Layer:** 2a
**Type:** utility

Lightweight contextual explanation — "why is this wrong?" Used inline during exercise sessions when a user answers incorrectly. Shorter and crisper than `dump_grammar`. Not a standalone session.

**Input:**
```python
fragment: str         # user's wrong answer
correction: str       # correct form
error_tag: str        # from taxonomy
level: str
topic: str            # current session topic for context
```

**Output:**
```python
explanation: str      # 1-3 sentences, direct and specific
```

**Prompt template:**
```
A {level} German learner made this error during a {topic} exercise:

Wrong:   "{fragment}"
Correct: "{correction}"
Error type: {error_tag}

Explain briefly why this is wrong and what the rule is.
1-3 sentences. Be direct. No preamble.
```

**Also used by:** Writing module's `generate_feedback` skill — invoked when a grammar error needs a quick inline note rather than a full taxonomy explanation.

---

## Grammar Topics File

`skills/select_grammar/topics/a1_b2_topics.yaml`

Sample structure:

```yaml
- topic: "Present tense — regular verbs"
  difficulty: A1
  related_error_tags: ["verb_conjugation"]

- topic: "Articles — nominative case"
  difficulty: A1
  related_error_tags: ["article_gender"]

- topic: "Separable verbs — present tense"
  difficulty: A2
  related_error_tags: ["separable_verb", "verb_position"]

- topic: "Dative case — prepositions"
  difficulty: B1
  related_error_tags: ["dative_case"]

- topic: "Adjective endings — all cases"
  difficulty: B2
  related_error_tags: ["adjective_ending"]
```

Full list to be compiled from Goethe Institut A1–B2 curriculum before Layer 2a implementation. Review for accuracy before use.
