# LanguageTutor — Orchestrator

Top-level agent. The only component that touches storage. Routes between modules, manages session lifecycle, persists all results.

The effective session key is `(user_id, language)`. All progress aggregation, cold start tracking, error frequency, and vocab flags are scoped to this pair — a user's Spanish progress is fully independent from their German progress.

See `docs/contracts.md` for `OrchestratorProtocol`, `ProgressSummary`, `ExerciseRecommendation`.

---

## Files

- `orchestrator/orchestrator.py` — `OrchestratorProtocol` implementation
- `orchestrator/prompts.py` — prompt templates (Layer 1b+)

---

## Module Registry

```python
# modules/registry.py
MODULE_REGISTRY: dict[str, ModuleProtocol] = {
    "writing": WritingModule(),
    "grammar": GrammarModule(),     # Layer 2a
    "vocab": VocabModule(),         # Layer 3a
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

## Session Clock

- `started_at` — set in write-ahead record (step 5)
- `completed_at` — set by orchestrator immediately after `module.run()` returns
- `duration_minutes` — computed from the two, stored in DB for query convenience
- CLI: background thread displays `[MM:SS elapsed]` updating every second during module.run()
- UI (Layer 1c): timer widget in session header, updated via polling

Progress summary includes `total_time_by_module` for the last N sessions, scoped to active language.
