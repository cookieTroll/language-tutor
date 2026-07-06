# LanguageTutor — Orchestrator

Top-level agent. The only component that touches storage. Routes between modules, manages session lifecycle, persists all results.

The effective session key is `(user_id, language)`. All progress aggregation, cold start tracking, error frequency, and vocab flags are scoped to this pair — a user's Spanish progress is fully independent from their German progress.

See `docs/_contracts.md` for `OrchestratorProtocol`, `ProgressSummary`, `ExerciseRecommendation`.

---

## Files

- `orchestrator/orchestrator.py` — `OrchestratorProtocol` implementation
- `orchestrator/protocols.py` — `OrchestratorProtocol`, `ProgressSummary`, `ExerciseRecommendation`
- `orchestrator/session_manager.py` — `SessionManager`: checkpoints, context fulfillment, finalization, writing↔grammar next-action signal computation
- `orchestrator/mastery.py` — `get_module_mastery()` / `get_level_trend()` — mastery & progress logic
- `orchestrator/prompts.py` — prompt templates (Layer 1b+)

---

## Module Registry

```python
# modules/registry.py
MODULE_REGISTRY: dict[str, ModuleProtocol] = {
    "writing": WritingModule(),
    "grammar": GrammarModule(),     # Layer 2a
    # "vocab": VocabModule(),       # Layer 3a — not yet registered, module doesn't exist yet
}

def get_registry_description() -> str:
    return "\n".join(
        f"- {name}: {module.description}"
        for name, module in MODULE_REGISTRY.items()
    )
```

To add a module: implement `ModuleProtocol`, add to registry. Nothing else changes.

---

## Session Flow (`run_session(user_id, language)`)

```
0.  get_interrupted_sessions(user_id) → resume / log / discard
      Not language-scoped — surface all interrupted sessions regardless of language
      Resume:   module.restore_checkpoint() if supported, else unavailable
      Log it:   load transcript → LLM summarize → write interrupted file → clear checkpoint
      Discard:  delete checkpoint, mark abandoned

1.  get_user_profile(user_id, language)
      If no profile exists → prompt user for level → write_user_profile()

2.  summarize_progress(user_id, language) → ProgressSummary | None
      All queries scoped to (user_id, language)

3.  recommend_exercise(summary) → ExerciseRecommendation
      None → DEFAULT_RECOMMENDATION (cold start, per language)

4.  Display recommendation + reason to user
    User confirms or overrides module choice + optional parameters

5.  write_session(SessionLog(language=language, status='in_progress', started_at=now()))

6.  Fulfill module.context_request() from storage — all scoped to (user_id, language):
      get_recent_sessions(user_id, language)
      get_error_frequency(user_id, language)
      get_recent_topics(user_id, language, module)
      get_vocab_flags(user_id, language)
    → build ModuleContext(user_id=user_id, language=language, level=profile.level, ...)

7.  module.run(ctx, llm) → (ModuleResult, SessionFileContent)
      (clock runs inside module; checkpoint transcript written per turn)

8.  write_file(content) → temp path → atomic rename → final path

9.  update_session_status(session_id, 'completed')

10. write_session(full result: errors, comment, completed_at, duration_minutes, file_path)

11. write_btw(entry) for each entry in result.metadata['btw_entries']

12. write_vocab_flag(flag) for each signal in result.metadata['vocab_signals']

13. Delete checkpoint file
```

---

## Language Selection (PoC)

On startup, before the session flow:

```
1. get_active_language(user_id)
   - If found → confirm or switch:
       "Currently studying German. Continue or switch language? [enter / language name]"
   - If not found → prompt:
       "Which language would you like to study? "

2. If switching or new:
   - get_user_profile(user_id, new_language)
     - If profile exists → load level, set active=True
     - If not → prompt for level → write_user_profile()

3. run_session(user_id, active_language)
```

Language names are normalised to lowercase on input (`"German"` → `"german"`). Stored consistently in DB. Asset discovery uses the normalised form.

---

## Cold Start

Cold start is **per (user_id, language)**. A user with 10 German sessions is still cold-start for Spanish.

Below `cold_start_threshold` (default: 3, from `config.yaml`), `summarize_progress()` returns `None`.

`recommend_exercise()` detects `None` and returns:

```python
DEFAULT_RECOMMENDATION = ExerciseRecommendation(
    module="writing",
    reason="Not enough session history yet — starting with writing.",
    suggested_focus=None,
)
```

Explicit branch in code, not a degraded LLM call. Testable as a unit test.

---

## Progress Summary (Layer 1b)

### Aggregation

Orchestrator reads recent sessions for `(user_id, language)` and computes:

```python
{
  "language": "german",
  "sessions_by_module": {"writing": 5, "grammar": 1},
  "days_since_module": {"writing": 0, "grammar": 8},
  "total_time_by_module": {"writing": 120, "grammar": 20},  # minutes
  "recurring_errors": ["dative_case", "word_order"],        # appeared 2+ sessions
  "vocab_flag_count": 14,
  "recent_topics": ["daily routine", "weekend plans", "food"]
}
```

### Progress Summary Prompt

```
You are a language tutor assistant. Analyze the session history below
and return a structured progress summary.

Target language: {language}
Session history (JSON): {session_aggregate_json}
Available modules: {registry_keys}

Return JSON only — no preamble:
{
  "language": "{language}",
  "sessions_by_module": {"writing": 5, "grammar": 1},
  "days_since_module": {"writing": 0, "grammar": 8},
  "total_time_by_module": {"writing": 120, "grammar": 20},
  "recurring_errors": ["dative_case", "word_order"],
  "vocab_flag_count": 14,
  "recent_topics": ["daily routine", "weekend plans", "food"],
  "weakest_module": "<must be one of available modules>",
  "recommendation_reason": "..."
}
```

`weakest_module` validated against `MODULE_REGISTRY.keys()` after parsing. If invalid → fall back to `DEFAULT_RECOMMENDATION`.

### Recommendation Prompt

```
Available modules:
{registry_description}

Progress summary:
{progress_summary_json}

Target language: {language}
User level: {level}

Recommend the next exercise. Return JSON only:
{
  "module": "<registry key>",
  "reason": "...",
  "suggested_focus": "..."
}
```

`module` field validated against registry before use.

---

## Session History — Personalization

All signals below are scoped to `(user_id, language)` — no cross-language bleed.

### Writing Module — Topic Picker
- `recent_topics` → avoids repeating recent writing subjects
- `recurring_errors` → steers requirements toward weak areas
- `vocab_flags` → avoids prompts relying on flagged unknown words

### Writing Module — Evaluator
- `recurring_errors` → primes the detector to be attentive to known weak spots
- `vocab_flags` → correct reuse of flagged word = positive signal; wrong reuse = new error

### Grammar Module — Selector (Layer 2a)
- `recurring_errors` + `sessions_by_module` → picks topics addressing errors not recently practiced
- `recent_topics` filtered by module → avoids grammar topics covered recently

### Orchestrator Recommendation
- Primary signal: `days_since_module` (recency)
- Secondary signal: `recurring_errors` linked to that module's domain
- Tertiary signal: `total_time_by_module` — very short sessions may indicate avoidance

### Traceability
`suggested_focus` from `ExerciseRecommendation` is passed through `ModuleContext` and recorded in every session file. Creates a traceable link: history aggregate → recommendation → what was practiced.

---

## Writing ↔ Grammar Bridge (Layer 2a-vii)

This is the personalization loop the whole pitch centers on: a recurring mistake in one
module surfaces a live offer to practice the other module next, and accepting chains
straight into a new session without returning to the main menu.

### How a signal gets raised (`orchestrator/session_manager.py::_compute_next_actions`)

Runs once, at the end of `finalize_session()`, dispatching by which module just ran —
each direction has a different signal shape, so this is two separate gates, not one
shared check:

**Writing → grammar** (`_writing_error_recurrence_signal`) fires only when *both* hold:
1. **Existence check** — at least one `error_tag` from *this* session's mistakes maps to
   a curated grammar topic at all (`tag in topic.related_error_tags` for some topic in
   `lang.loader.get_grammar_topics(language)`).
2. **Recurrence check** — that tag's count in `error_frequency` (the standing aggregate,
   not just this session) is `>= RECURRING_ERROR_THRESHOLD` (2).

`suggested_focus` carries the raw **tag**, not a resolved topic name — several curated
topics can share a tag (e.g. 12 topics all tag `verb_tense`), and this gate has no
level-aware way to pick the right one. Naming a specific topic here would risk promising
something `select_grammar` (which does the real pick when the grammar module actually
runs) doesn't deliver. An explicit `/btw` "help me practice" request during the
follow-up phase (`requested_topic`) bypasses the recurrence threshold entirely — the
user already asked — and can offer a second, alternative signal if the first is declined.

**Grammar → writing** (`_grammar_mastery_signal`) fires when a grammar session's score is
`>= GRAMMAR_MASTERY_THRESHOLD` (0.8). Here `suggested_focus` *is* the actual topic name,
not a tag — safe because `WritingModule._pick_topic` only ever uses it as a soft phrase
("try to practise: ...") in the topic-picker prompt, not a hard contract the way
`generate_exercises`' topic input is.

Both thresholds are separately-defined module constants (`session_manager.py`'s
`RECURRING_ERROR_THRESHOLD` and `orchestrator.py`'s `RECURRING_MISTAKE_THRESHOLD`, both
`= 2`, matching `SessionAggregate.recurring_errors`' own threshold) — not imported from
one shared location. Keep this in mind if the recurrence threshold is ever tuned; it
needs changing in more than one place today.

### Presenting and chaining the offer (`orchestrator.py::run_session`)

After `finalize_session()` returns, `run_session` loops over `file_content.next_actions`:
prompts `"Session complete. Start {module} practice on '{focus}' now? [Y/n]"` (or, for a
second alternative signal, `"How about {module} practice{focus} instead?"`), records the
answer via `SessionManager.record_next_action_decision()` (a follow-up rewrite of the
just-written session file — the file was already persisted *before* this interactive
prompt, since `SessionManager` never prompts, only informs), and on accept returns an
`ExerciseRecommendation` built from the signal. The caller (`ui/cli.py`'s loop,
`ui/app.py`'s `/api/start`) re-invokes `run_session(forced_recommendation=...)`, which
skips straight past steps 2–4 (summarize/recommend/confirm) into the write-ahead log for
the new session — no return to the main menu in between.

---

## `/history` — Writing History Summary (Layer 2b)

On-demand report, typed at the `_get_confirmed_module` prompt exactly like `/btw`.
Nothing is written back to storage — regenerated fresh from `get_sessions_by_module()`
on every call, never read from anything previously saved. This superseded an earlier,
different Layer 2b design (a per-session `comparison_note` field diffing against the
immediately-previous session) — see `docs/writing.md` for why that shape was dropped.

**Syntax**, all recognized by `_parse_history_scope`/`_split_history_args`:
- `/history` — last `DEFAULT_HISTORY_SESSIONS` (10) completed writing sessions
- `/history <n>` — last `n` sessions
- `/history <n>d` — last `n` days
- `lang:<language>` token anywhere in the args (e.g. `/history 5 lang:german`) —
  overrides the report's own output language for this one call only, independent of the
  scope argument. Absent an override, the report is written in the user's
  `profile.explanation_language` (see `/language` below), not the target study language —
  the report is meta-commentary the learner reads, not target-language content.

`_handle_history_command` builds three inputs from the filtered session window — topics
covered (`task_label`, deduplicated), recurring mistakes (`error_tag` counts `>=
RECURRING_MISTAKE_THRESHOLD`, this session-window's own tally, not the standing
`error_frequency` aggregate the bridge gate uses), and a chronological level trend from
each session's `text_level_estimate` — then calls `SummarizeWritingHistorySkill` once and
prints `history_summary` via `io.output()`.

### `/language` — on-demand explanation-language change

Not its own layer, but lives right next to `/history` in the same command loop: `/language
<language>` updates `profile.explanation_language` immediately (persisted via
`write_user_profile`), so a user doesn't have to wait for the next session's start-of-session
prompt (`_confirm_or_update_explanation_language`) to change which language `/history`
and `dump_grammar` write their output in.

---

## `/progress` — Mastery & Level Progress (Layer 2c)

On-demand, same shape as `/history` — nothing persisted except an optional,
user-confirmed level-up at the end. Merges what were originally two separate planned
layers (a CEFR estimator and a level-progression tracker): both turned out to be
different renderings of the same mastery data, not independent features — see
`docs/memory.md` on why no `level_history` table exists.

`_handle_progress_command` gathers three things and hands them to `io.render_progress()`
— the same "orchestrator gathers data, `IOHandler` renders it" split as
`render_evaluation`/`render_exercises`/`render_results`, so `TerminalIOHandler` draws
ASCII bars while the web UI renders an actual dial (`ui/static/progress-ui.js`):

- **`get_module_mastery(store, user_id, language, module)`** (`orchestrator/mastery.py`)
  — for grammar: `topics_mastered / topics_total`, scoped to curated `scope: major`
  topics *at the user's current level* (best session score per topic `>=
  GRAMMAR_MASTERY_THRESHOLD`, matched by `shared/slugify.py::slugify_topic` against
  `task_label`); for writing: completed sessions *at the user's current level* against
  `TEXTS_PER_LEVEL_FOR_MASTERY` (25), capped at 1.0 — writing has no discrete topic unit
  to count instead, so it mirrors grammar's per-level scoping via session count instead
  (`texts_written` itself stays an all-time total — just a display stat, not the ratio).
  Both also carry
  `weak_tags`/`strong_tags` (from `get_error_frequency`, resolved to human-readable
  taxonomy descriptions or topic names — never raw tag keys) and word-count flavor stats.
- **`get_level_trend(store, user_id, language, module="writing")`** — chronological
  `text_level_estimate` pull, no new computation, same field `/history`'s trend uses.
- **`CefrEstimatorSkill`** — the actual level-up decision: a threshold crossing on
  grammar's mastery ratio, not a blended weighting of trend + error frequency + scores
  (deliberately avoids inventing a second fuzzy rule on top of a threshold that already
  exists). Suggests only — `_handle_progress_command` confirms with the user
  (`[Y/n]`) before `store.write_level(..., source="estimated")` ever overwrites
  `user_profiles.level`.

No fixed "N texts" or "N words to reach the next level" threshold exists, and
deliberately so — checked against published sources (Goethe/telc word-count targets,
Milton's CEFR vocabulary-breadth research) and none give a cumulative writing-volume
threshold for leveling up. Word/text counts are shown as flavor stats on the progress
bar, not used as a gate.

---

## Session Clock

- `started_at` — set in write-ahead record (step 5)
- `completed_at` — set by orchestrator immediately after `module.run()` returns
- `duration_minutes` — computed from the two, stored in DB for query convenience
- CLI: background thread displays `[MM:SS elapsed]` updating every second during module.run()
- UI (Layer 1c): timer widget in session header, updated via polling

Progress summary includes `total_time_by_module` for the last N sessions, scoped to active language.
