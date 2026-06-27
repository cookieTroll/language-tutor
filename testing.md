# GermanTutor — Testing Architecture

Three tiers, each with a distinct purpose. Tier 1 runs in CI. Tiers 2 and 3 run manually or on a schedule — they cost API calls and should not block commits.

---

## Tier 1 — Unit Tests (deterministic)

`pytest` assertions, no LLM calls, no network. Fast. Run on every commit.

All orchestrator and module tests use a **mock LLM** returning fixed strings — no API keys needed in CI.

### Coverage

**Storage (`tests/test_storage.py`)**
- Write session → read back → assert all fields equal (SQLite and JSON store)
- Error frequency aggregation across multiple sessions
- `update_session_status()` transitions correctly; rejects invalid values
- `get_interrupted_sessions()` returns only `in_progress` records older than timeout
- `get_recent_topics()` returns correct n, filtered by module
- `get_vocab_flags()` returns correct user-scoped results
- `write_vocab_flag()` increments `occurrence_count` on duplicate, does not insert new row
- Atomic write: no `.tmp` file exists after successful write; `.tmp` cleaned on failure
- Relative file path resolves correctly against `data_root`
- `get_current_level()` returns most recent row when multiple exist

**Registry (`tests/test_registry.py`)**
- All registered modules implement `ModuleProtocol`
- All registered skills implement `SkillProtocol`
- `get_registry_description()` includes all registry keys
- Skills declare valid `skill_type` (`session` or `utility`)

**Taxonomy (`tests/test_taxonomy.py`)**
- `validate_error_tag()` accepts all defined tags
- `validate_error_tag()` rejects unknown tag with `TaxonomyError` + informative message

**Orchestrator (`tests/test_orchestrator.py`)**
- Cold start returns `DEFAULT_RECOMMENDATION` when sessions = 0
- Cold start returns `DEFAULT_RECOMMENDATION` when sessions < threshold
- Cold start does NOT trigger when sessions >= threshold
- `weakest_module` validation: invalid LLM output falls back to default
- Interrupted session detection surfaces correct records on startup
- All three interruption paths produce correct DB state (resume/log/discard)
- Post-session: btw entries written, vocab signals written, checkpoint deleted

**LLM (`tests/test_llm.py`)**
- `build_llm()` returns correct implementation for each backend value
- `build_llm()` raises informative error on unknown backend value
- Mock LLM returns fixed strings; can be configured per test

**Storage (`tests/test_storage.py`) — interruption**
- `update_session_status()` transitions correctly; rejects invalid status values
- Atomic write leaves no `.tmp` on success; `.tmp` cleaned up on failure

---

## Tier 2 — LLM-as-Judge (skill output quality)

Offline evaluation against manually verified fixtures. Ground truth kept within B1 scope (verifiable by author). Fixtures in `tests/fixtures/`.

**Scope:** A1–A2 content for PoC and Layer 1a fixtures. B1 content added as confidence grows. Do not use unverified content as ground truth.

**When to run:** Before merging prompt changes. After tuning a step, run its judge to verify improvement.

---

### Writing Evaluator Judges

One judge per pipeline step — targeted criteria, not a single catch-all.

#### Step 1 — Detector (`tests/judge/judge_detector.py`)

```
You are evaluating a German mistake detector's output.

Student level: {level}
Writing prompt: {writing_prompt}
Student text: {user_text}
Detector output: {raw_mistakes_json}

Score each criterion 0–2:
1. Accuracy — are flagged fragments actually errors in German?
2. Completeness — are significant errors missed?
3. False positives — are correct German phrases flagged as errors?

Return JSON: { "scores": {"accuracy": N, "completeness": N, "false_positives": N}, "total": N, "notes": "..." }
```

#### Step 2 — Processor (`tests/judge/judge_evaluator.py`)

```
You are evaluating a German mistake classifier's output.

Classified mistakes: {classified_json}
Valid error tags: {taxonomy_list}

Score each criterion 0–2:
1. Tag accuracy — is each error_tag the correct category?
2. Correction accuracy — is each correction grammatically correct German?
3. Tag validity — are all tags from the valid set?

Return JSON: { "scores": {...}, "total": N, "notes": "..." }
```

#### Step 3 — Feedback Generator (`tests/judge/judge_evaluator.py`)

```
You are evaluating a German tutor's feedback explanations.

Student level: {level}
Feedback: {feedback_json}

Score each criterion 0–2:
1. Explanation accuracy — is the grammatical explanation correct?
2. Level appropriateness — is the explanation pitched correctly for {level}?
3. Clarity — is the explanation clear and actionable?

Return JSON: { "scores": {...}, "total": N, "notes": "..." }
```

#### Step 4 — Correction Writer (`tests/judge/judge_evaluator.py`)

```
You are evaluating a German corrected text.

Original student text: {user_text}
Corrections applied: {corrections_json}
Corrected text produced: {corrected_text}

Score each criterion 0–2:
1. Correction accuracy — are all specified corrections applied correctly?
2. Grammatical correctness — is the corrected text valid German?
3. Minimal intervention — are only the specified errors changed, nothing else?

Return JSON: { "scores": {...}, "total": N, "notes": "..." }
```

---

### Orchestrator Judge (`tests/judge/judge_orchestrator.py`)

```
Given this session history:
{session_aggregate_json}

The orchestrator recommended:
{recommendation_json}

Score 0–2:
1. Module selection — appropriate given recency and error patterns?
2. Suggested focus — relevant to recurring errors?
3. Reason quality — clear and accurate?

Return JSON: { "scores": {...}, "total": N }
```

---

### Judge Validation

Before trusting any judge prompt, run it 5 times on the same fixture input. Record scores. If variance > 1 point on any criterion, tighten the judge prompt before use.

Document acceptable variance threshold per step in a comment at the top of each judge file.

---

### Fixture Spec (`tests/fixtures/writing_pairs.json`)

Minimum 3 fixtures per evaluator step before judge testing begins. Each fixture:

```json
{
  "id": "w001",
  "level": "A2",
  "writing_prompt": "Describe your morning routine in 80-100 words.",
  "user_text": "Ich habe heute Morgen um sieben Uhr aufgestanden...",
  "expected_mistakes": [
    {
      "fragment": "habe ... aufgestanden",
      "error_tag": "verb_conjugation",
      "correction": "bin ... aufgestanden",
      "explanation": "aufstehen is a motion verb, takes sein in Perfekt"
    }
  ],
  "verified_by": "author",
  "verified_date": "2026-06-28",
  "notes": "Common Perfekt auxiliary error at A2"
}
```

**Ground truth rules:**
- Verified personally within B1 scope, or verified against a trusted German grammar reference
- Mark unverified fixtures clearly — do not use as judge ground truth
- Cover: single error, multiple errors, no errors (false positive test), mixed error types

---

## Tier 3 — Regression Fixtures

Accumulated during prompt development. When a prompt produces a notably good output on real input, save it.

Convention:
```
tests/fixtures/regression/{step}_{YYYYMMDD}_{short_description}.json
```

Example: `tests/fixtures/regression/detector_20260628_dative_mixed_errors.json`

On prompt changes, re-run all regression fixtures through the relevant judge. A drop in score flags a regression. No minimum count required upfront — grows naturally.

---

## CI Strategy

| Tier | When | Command |
|------|------|---------|
| Tier 1 — unit tests | Every commit | `pytest tests/test_*.py` |
| Tier 2 — LLM judge | Before merging prompt changes | `python tests/judge/judge_*.py` |
| Tier 3 — regression | Before merging prompt changes | `python tests/judge/run_regression.py` |

Tier 1 requires no API keys. Tiers 2 and 3 require a valid `GEMINI_API_KEY` (or configured backend).
