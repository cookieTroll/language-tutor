# Wharf the Language Tutor — Memory Architecture

Storage is infrastructure. Only the orchestrator calls `StorageProtocol` — this is a hard boundary. Modules and skills are pure.

The effective session key throughout is `(user_id, language)`. All queries are scoped to both — a user's German progress never pollutes their Spanish profile.

See `docs/_contracts.md` for `StorageProtocol`, `SessionLog`, `SessionFileContent`, `BtwEntry`, `VocabFlag` definitions.

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
| `explanation_language` | TEXT | default `'english'`; meta-commentary language (dump_grammar, `/history`) — distinct from `language`, the target study language |

**Primary key:** `(user_id, language)`

Level history is not stored here — `user_profiles` holds current state only. Layer 2c ("Level &
Progress") deliberately does not add a `level_history` table: the trend it needs is derived from
data already stored per session (`sessions.text_level_estimate`, `sessions.level`, `sessions.score`,
and the new `sessions.word_count`), queried chronologically. No new table, no dual-write risk.

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
| `text_level_estimate` | TEXT | writing sessions only; denormalized (Layer 2b) |
| `word_count` | INTEGER | writing sessions only; denormalized (Layer 2c) |
| `score` | REAL | grammar sessions only; denormalized (Layer 2c) |

**Index:** `(user_id, language)` — all session queries filter on both.

### `errors` table

Normalized error log. Separate table enables frequency queries across sessions without parsing files.

| Column | Type | Notes |
|--------|------|-------|
| `error_id` | TEXT PK | UUID |
| `session_id` | TEXT FK | → sessions |
| `language` | TEXT | denormalized from session for direct query |
| `module` | TEXT | registry key, denormalized from session for direct query |
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
    severity: expected   # critical | expected | minor — gap between user's level and this tag's mastery level
tips:
  - "Review dative case after prepositions (mit, bei, nach, seit, von, zu)"
corrected_text: |
  Ich bin heute Morgen um sieben Uhr aufgestanden...
session_summary: "Good use of separable verbs overall. Dative case needs attention."
btw_log:
  - question: "what does aufstehen mean?"
    answer: "aufstehen means 'to get up / to stand up'. It's a separable verb..."
    flagged_word: "aufstehen"
    timestamp: "2026-06-27T20:12:00"
vocab_updates:
  - word: "aufstehen"
    source: "btw"
    occurrence_count: 1
suggested_focus: null            # set when this session was a forced_recommendation follow-up
text_level_estimate: "B1"        # Step 5 estimate on the raw text; null if text too short
word_count: 187                  # computed at submission; progress-bar flavor stat
next_actions: []                 # populated when a recurring error triggers the writing→grammar bridge
```

`tips`/`session_summary` were formerly named `recommendations`/`comment` — renamed in
Layer 1a Steps 5–6. The now-removed `comparison_note` field (an earlier Layer 2b
placeholder) is gone entirely, not just emptied — see `docs/_design.md`'s schema-evolution
note and `docs/writing.md` for why (superseded by the on-demand `/history` command).

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

## Summary Files — superseded, no longer generated

The original PoC design (this section, prior to this edit) planned a persisted
`{data_root}/summaries/{user_id}/{language}/summary_{date}.md` file per progress
summary. That was never built — `storage`'s init still creates the `data/summaries/`
directory (alongside `data/sessions/` and `data/checkpoints/`), but nothing writes into
it. Progress and history are computed on demand instead and shown live, never persisted
as their own file: `Orchestrator.summarize_progress()` returns a `ProgressSummary` object
consumed immediately, and the `/history`/`/progress` commands (Layers 2b/2c) regenerate
their report fresh on every request from `get_sessions_by_module()`/`get_module_mastery()`
rather than reading back anything written earlier. The `data/summaries/` directory can be
treated as vestigial.

---

## Language Asset Discovery

Language-specific content (error taxonomy, CEFR hints, grammar topics, exercise types)
lives in the `lang/` package — versioned YAML maps under `lang/maps/{concept}/`, resolved
per-language via `lang/languages/{language}.yaml` and loaded through `lang/loader.py`'s
`_Registry`, which cross-validates every reference at startup. See `docs/lang.md` for the
full architecture and `docs/lang_generation.md` for how new languages' content gets
produced. Adding a language means adding YAML files, not changing code.

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

**Checkpoint transcript — designed, not implemented (found 2026-07-05):** The intent was for
each turn (user input + agent response) to be appended incrementally to
`{data_root}/checkpoints/{user_id}/{session_id}.json` during `module.run()`, so a crash at
any point preserves all turns up to that moment. `init_write_ahead_log()` creates this file
with an empty list, but no module ever appends to it afterward — neither `WritingModule` nor
`GrammarModule` implements the (optional) `save_checkpoint()` hook. The "Log it" path below
still works and doesn't crash, but its LLM summary is always generated from an empty
transcript, not partial progress. See `docs/_CHECKLIST.md`'s "Interrupted-Session Checkpoint
Transcript" item — tracked as a post-submission fix, not pre-submission.

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

**One write source today, a second designed but not built (found 2026-07-05):**
- `/btw` handler returns `flagged_word` in `BtwEntry` → `vocab_signals` → `write_vocab_flag(source='btw')`. This path is real: `modules/writing/agent.py:204` populates `vocab_signals` from flagged words, and `SessionManager.finalize_session` writes each one.
- Evaluator `vocabulary`-tagged errors → `write_vocab_flag(source='evaluator')` was the intent, but nothing wires it up — `vocab_signals` is never populated from `classify_mistakes`/`explain_mistakes` output, and `finalize_session` hardcodes `source="btw"` on every write regardless of origin. See `docs/_CHECKLIST.md`'s "Evaluator-Sourced Vocab Flags" item — tracked as a post-submission fix.

**Deduplication:** already solved, and not blocked on the above. Words normalized (lowercase, punctuation stripped) at the one real call site (`session_manager.py`) before write. Unique constraint on `(user_id, language, word)` — `write_vocab_flag()` increments `occurrence_count` and updates `last_seen` on conflict rather than inserting new row. This applies to any source, so the evaluator path will get deduplication for free once it's wired up.

**Consumers:** topic picker (avoid flagged words), vocab module drill list, Anki export — all scoped to active language.
