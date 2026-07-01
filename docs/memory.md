# LanguageTutor — Memory Architecture

Storage is infrastructure. Only the orchestrator calls `StorageProtocol` — this is a hard boundary. Modules and skills are pure.

The effective session key throughout is `(user_id, language)`. All queries are scoped to both — a user's German progress never pollutes their Spanish profile.

See `docs/contracts.md` for `StorageProtocol`, `SessionLog`, `SessionFileContent`, `BtwEntry`, `VocabFlag` definitions.

---

## Database Schema (`memory/schema.sql`)

### `user_profiles` table

Per-user, per-language profile. Replaces the old `user_levels` table. One row per `(user_id, language)` combination — a user learning both German and Spanish has two rows.

| Column | Type | Notes |
|--------|------|-------|
| `user_id` | TEXT | |
| `language` | TEXT | e.g. `german`, `spanish`, `french` |
| `level` | TEXT | A1–C2 for this language |
| `level_source` | TEXT | `stated` / `estimated` / `cefr_module` |
| `active` | BOOLEAN | last language the user selected |
| `created_at` | DATETIME | |
| `updated_at` | DATETIME | updated when level changes |

**Primary key:** `(user_id, language)`

Level history is not stored here — `user_profiles` holds current state. If level history is needed later (Layer 3b), add a separate `level_history` table. Keeping it simple for now.

### `sessions` table

Queryable index of all sessions. One row per session.

| Column | Type | Notes |
|--------|------|-------|
| `session_id` | TEXT PK | UUID |
| `user_id` | TEXT | |
| `language` | TEXT | target language for this session |
| `module` | TEXT | registry key |
| `task_label` | TEXT | e.g. `writing_free` |
| `task_description` | TEXT | full task prompt |
| `comment` | TEXT | agent comment |
| `level` | TEXT | level at time of session |
| `date` | DATETIME | |
| `file_path` | TEXT | relative to `data_root` |
| `status` | TEXT | `in_progress` / `completed` / `abandoned` / `interrupted` |
| `started_at` | DATETIME | set on write-ahead |
| `completed_at` | DATETIME | set on completion |
| `duration_minutes` | REAL | stored for query convenience |

**Index:** `(user_id, language)` — all session queries filter on both.

### `errors` table

Normalized error log. Separate table enables frequency queries across sessions without parsing files.

| Column | Type | Notes |
|--------|------|-------|
| `error_id` | TEXT PK | UUID |
| `session_id` | TEXT FK | → sessions |
| `language` | TEXT | denormalized from session for direct query |
| `error_tag` | TEXT | from language-scoped taxonomy |
| `error_detail` | TEXT | human-readable description |
| `source_text` | TEXT | user's original fragment |

`language` is denormalized here to avoid a join on every error frequency query.

### `btw_log` table

Log of all `/btw` inline questions across all sessions.

| Column | Type | Notes |
|--------|------|-------|
| `btw_id` | TEXT PK | UUID |
| `session_id` | TEXT FK | → sessions |
| `user_id` | TEXT | |
| `language` | TEXT | denormalized from session |
| `question` | TEXT | user's raw question |
| `answer` | TEXT | agent's response |
| `flagged_word` | TEXT \| NULL | extracted word if vocabulary-related |
| `timestamp` | DATETIME | |

### `vocab_flags` table

Per-user, per-language negative vocabulary list. Represents current state per word — not an event log.

| Column | Type | Notes |
|--------|------|-------|
| `flag_id` | TEXT PK | UUID |
| `user_id` | TEXT | |
| `language` | TEXT | which language this word belongs to |
| `word` | TEXT | flagged word (normalized: lowercase, stripped) |
| `translation` | TEXT \| NULL | known translation if available |
| `source` | TEXT | `btw` / `evaluator` / `manual` |
| `first_seen` | DATETIME | |
| `last_seen` | DATETIME | updated on repeat occurrence |
| `occurrence_count` | INT | incremented on repeat, not new row |

**Unique constraint:** `(user_id, language, word)` — same word in different languages is a different row.

---

## Storage Implementations

### `memory/sqlite_store.py` — `SQLiteSessionStore`

Production backend. Implements full `StorageProtocol`. DB file path from `config.yaml:data_root`.

### `memory/json_store.py` — `JSONSessionStore`

Dev/test backend. Same interface, JSON files on disk. No DB setup needed. Used in all unit tests via dependency injection.

**Swap:** `storage_backend: sqlite | json` in `config.yaml`. `build_storage(config)` factory returns correct instance.

---

## Session Files

One YAML file per session. Path: `{data_root}/sessions/{user_id}/{language}/{session_id}.yaml`.

Language added to path to keep per-language session files browsable as separate directories.

- Path stored as **relative** to `data_root` in DB. Resolved at runtime.
- Written by storage layer only — modules never write files directly.
- Written to `{session_id}.yaml.tmp` first, then **atomically renamed** to final path on success.

### Common header (all modules)

```yaml
session_id: abc-123
user_id: user-456
language: german
module: writing
task_label: writing_free
date: 2026-06-27T20:00:00
level: B1
status: completed
suggested_focus: dative case prepositions
```

### Writing session body (`WritingSessionContent`)

```yaml
topic: "Describe your morning routine"
requirements: "150-200 words, use Perfekt tense, include 3 separable verbs"
user_text: |
  Ich habe heute Morgen um sieben Uhr aufgestanden...
mistakes:
  - error_tag: dative_case
    fragment: "mit meinen Bruder"
    correction: "mit meinem Bruder"
    explanation: "After 'mit', German requires dative case..."
recommendations:
  - "Review dative case after prepositions (mit, bei, nach, seit, von, zu)"
corrected_text: |
  Ich bin heute Morgen um sieben Uhr aufgestanden...
comment: "Good use of separable verbs overall. Dative case needs attention."
btw_log:
  - question: "what does aufstehen mean?"
    answer: "aufstehen means 'to get up / to stand up'. It's a separable verb..."
    flagged_word: "aufstehen"
    timestamp: "2026-06-27T20:12:00"
vocab_updates:
  - word: "aufstehen"
    source: "btw"
    occurrence_count: 1
```

### Grammar session body (`GrammarSessionContent`) — Layer 2a

```yaml
topic: "Dative case — prepositions"
scope: major
explanation: "..."
items:
  - prompt: "Ich fahre ___ meinem Freund. (with)"
    exercise_type: fill_in_the_blank
    grading: exact
    user_answer: "mit meinen"
    correct_answer: "mit meinem"
    correct: false
    feedback: "'mit' takes the dative case — 'meinen' is accusative."
    error_tag: noun_declension
score: 0.6
btw_log: []
```

---

## Summary Files

Generated on demand ("how am I doing?") or post-session if enabled.

Path: `{data_root}/summaries/{user_id}/{language}/summary_{date}.md`

Language added to path — summaries are per-language, not cross-language.

---

## Language Asset Discovery

Language-specific assets (grammar topic lists, word lists, error taxonomies) follow a convention:

```
skills/{skill_name}/assets/{language}/
  e.g. skills/select_grammar/assets/german/topics.yaml
       skills/select_grammar/assets/spanish/topics.yaml
       skills/drill_vocab/assets/german/greetings.yaml
       skills/drill_vocab/assets/spanish/greetings.yaml
```

Skills discover assets by convention at runtime using the `language` value from `ModuleContext`. No hardcoded paths — adding a new language means adding asset files, not changing code.

Error taxonomies follow the same pattern:
```
skills/detect_mistakes/taxonomy/{language}.py
  e.g. taxonomy/german.py   → ERROR_TAXONOMY = {"dative_case", ...}
       taxonomy/spanish.py  → ERROR_TAXONOMY = {"subjunctive_mood", ...}
```

`validate_error_tag(tag, language)` loads the correct taxonomy for the session language.

---

## Session Interruption

### Severity table

| Point | Severity |
|-------|----------|
| Before module confirmed | None — nothing to save |
| Mid-exercise (user quits before submitting) | Medium |
| Post-submit, evaluation incomplete | High |
| Post-evaluation, write fails | High |

### PoC implementation

**Write-ahead:** Orchestrator writes minimal `SessionLog(status='in_progress')` before `module.run()`. Updates to `completed` on success.

**Checkpoint transcript:** During `module.run()`, each turn (user input + agent response) is appended to `{data_root}/checkpoints/{user_id}/{session_id}.json`. Incremental — crash at any point preserves all turns up to that moment.

**Atomic writes:** Session files written to `.tmp` path first, renamed on success.

### Startup — resume/log/discard

On startup, orchestrator calls `get_interrupted_sessions()`. If any found:

```
Your last session (writing / german, 2026-06-27 21:03) was interrupted.
What would you like to do?
  [r] Resume     — continue from where you left off
  [l] Log it     — summarize and save what was completed, start fresh
  [d] Discard    — delete and start fresh
```

- **Resume** — available only if module implements `restore_checkpoint()` and checkpoint file exists. PoC modules do not support this; option shown as unavailable.
- **Log it** — load checkpoint transcript → LLM summarize → write session file with `status='interrupted'` → clear checkpoint → proceed to new session.
- **Discard** — delete checkpoint, mark `status='abandoned'`.

Checkpoint file deleted on any terminal outcome (completed, interrupted, abandoned).

`interrupted` sessions included in progress summary, weighted lower than `completed`.

---

## Negative Vocab List

`vocab_flags` table is the per-user, per-language persistent record of unknown/misused words. A user's German vocab flags are entirely separate from their Spanish vocab flags.

**Two write sources (both via orchestrator post-session):**
- `/btw` handler returns `flagged_word` in `BtwEntry` → `write_vocab_flag(source='btw')`
- Evaluator `vocabulary` errors → `write_vocab_flag(source='evaluator')`

**Deduplication:** Words normalized (lowercase, punctuation stripped) before write. Unique constraint on `(user_id, language, word)` — `write_vocab_flag()` increments `occurrence_count` and updates `last_seen` on conflict rather than inserting new row.

**Consumers:** topic picker (avoid flagged words), vocab module drill list, Anki export — all scoped to active language.
