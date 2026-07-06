# Wharf the Language Tutor — Testing Architecture

Three tiers, each with a distinct purpose. Tier 1 runs in CI. Tiers 2 and 3 run manually or on a schedule — they cost API calls and should not block commits.

---

## Tier 1 — Unit Tests (deterministic)

`pytest` assertions, no LLM calls, no network. Fast. Run on every commit.

All orchestrator and module tests use a **mock LLM** returning fixed strings — no API keys needed in CI.

### Coverage

All unit test files live under `tests/unit/` (e.g. `tests/unit/test_storage.py`, not
`tests/test_storage.py`) — organized flat plus a few subpackages (`tests/unit/writing/`,
`tests/unit/lang/`) for areas with several test files of their own.

**Storage (`tests/unit/test_storage.py`)**
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
- `get_session_by_id()`/`list_users()` on both backends (added for the MCP server, Layer 3d)

**Registry, taxonomy validation, and CEFR/lang coverage**
- Module/skill registry compliance and taxonomy-tag validation are covered inline within
  the relevant test files (`tests/unit/test_orchestrator.py`, `tests/unit/lang/`) rather
  than in dedicated `test_registry.py`/`test_taxonomy.py` files — those two files don't
  exist as such.

**Orchestrator (`tests/unit/test_orchestrator.py`)**
- Cold start returns `DEFAULT_RECOMMENDATION` when sessions = 0
- Cold start returns `DEFAULT_RECOMMENDATION` when sessions < threshold
- Cold start does NOT trigger when sessions >= threshold
- `weakest_module` validation: invalid LLM output falls back to default (hallucination guard)
- Interrupted session detection surfaces correct records on startup
- All three interruption paths produce correct DB state (resume/log/discard)
- Post-session: btw entries written, vocab signals written, checkpoint deleted
- Writing↔grammar bridge gates (Layer 2a-vii), `/history` scope parsing (Layer 2b)

**LLM (`tests/unit/test_llm.py`)**
- `build_llm()` returns correct implementation for each backend value (`ollama`,
  `openai_compat`, `gemini`, `vertex`)
- `build_llm()` raises informative error on unknown backend value
- Mock LLM returns fixed strings; can be configured per test

**Grammar module (`tests/unit/test_grammar.py`)** — Layer 2a
- `parse_answer_block()`: exact count passes through, short blocks padded, long blocks
  truncated, empty block handled
- `GrammarModule.run()` end-to-end with a mocked LLM

**Module mastery/progress (`tests/unit/test_mastery.py`)** — Layer 2c
- Grammar mastery scoped to the user's current level; best score kept across repeated
  attempts on the same topic; behaves when no topics map is configured
- Writing mastery word counts and mastery ratio, including the ratio capping at 1.0
- Weak-tag reporting requires recurrence and surfaces human-readable labels, not raw tags
- Level trend is chronological and skips sessions with no text-level estimate

**MCP server (`tests/unit/test_mcp_server.py`)** — Layer 3d
- Listing users/languages; progress defaults to the active language; raises when no
  active language is set
- Listing sessions and fetching a single session; raises for the wrong user
- Recurring errors and vocab flags; writing-history export (including the days filter and
  the no-sessions message); error taxonomy and grammar topic list lookups

**CEFR estimator (`tests/unit/test_cefr_estimator.py`)**
- Suggests a level-up once all topics at the current level are mastered; withholds the
  suggestion below the mastery threshold, when no topics are configured, or past C2

**Tag humanization (`tests/unit/test_humanize.py`)**
- `humanize_tag()` replaces underscores and title-cases; handles single-word tags and
  empty-string passthrough

**Error logging (`tests/unit/test_error_log.py`)**
- `log_skill_error()` writes one JSON line with the expected fields, appends across
  multiple calls, and works when called without additional context

**Config loading (`tests/unit/test_config.py`)**
- `load_config()` against the real committed config files (`config.yaml`,
  `config.test.yaml`, `config.gemini.yaml`, `config.vertex.yaml`) resolves the expected
  provider for each, guarding against config/dependency drift going unnoticed

---

## Tier 2 — LLM-as-Judge (skill output quality)

Offline evaluation against manually verified fixtures. Fixtures in `tests/fixtures/pipeline_cases.json`.

**Scope:** A1–A2 content for PoC and Layer 1a fixtures. B1 content added as confidence grows.

**When to run:** Before merging prompt changes. After tuning a step, run its judge to verify improvement.

---

### Two-LLM design

Each judge uses two LLM instances:

- **Executor** (`LTUT_CONFIG`) — runs the skill under test with real prompt inputs
- **Judge** (`LTUT_JUDGE_CONFIG`, defaults to `LTUT_CONFIG`) — evaluates executor output against fixture labels

This keeps evaluation independent from the system under test. Set `LTUT_JUDGE_CONFIG` to use a stronger model as judge while keeping a local model as executor.

**Local model choice:** tested `qwen2.5:7b` vs `gemma2:9b` as the local Ollama executor —
qwen 7b wasn't strong enough for reliable structured output on this skill set (more judge
failures / self-correction retries), so `gemma2:9b` is the current default for local runs.

---

### Running judges

```powershell
# Both executor and judge use the default config (Ollama)
pytest tests/judge/ -v -s

# Both use Gemini
$env:GEMINI_API_KEY = "your-key-here"
$env:LTUT_CONFIG = "config.gemini.yaml"
pytest tests/judge/ -v -s

# Executor: Ollama, judge: Gemini
$env:GEMINI_API_KEY = "your-key-here"
$env:LTUT_JUDGE_CONFIG = "config.gemini.yaml"
pytest tests/judge/ -v -s
```

Results are written to `tests/judge/results/judge_<skill>_<timestamp>.json`, including `judge_prompt` per case for full traceability.

---

### Implemented judges

#### Step 1 — Detector (`tests/judge/judge_detect_mistakes.py`)

Evaluates `DetectMistakesSkill` output. Scoped to what the skill actually produces: erroneous fragments + `error_type_hint`. Does NOT check corrections or taxonomy tags (those belong to later steps).

Judge criteria:
1. Fragment coverage — does a detected fragment cover each expected error location?
2. False positives — is any correct German flagged as an error?
3. `error_type_hint` plausibility — does it name a real grammatical problem that maps to the expected taxonomy bucket?

Verdict: `PASS` / `PARTIAL` / `FAIL`. Score 0.0–1.0.

The judge is given the full taxonomy (`lang/maps/taxonomy/german_taxonomy_v1.yaml`) so it can accept `error_type_hint` values that map to the correct bucket without requiring exact tag matches.

A session-scoped fixture validates all `error_tag` values in `pipeline_cases.json` against the taxonomy before any test runs — fails fast with a clear message if labels drift out of sync.

---

### Fixture spec (`tests/fixtures/pipeline_cases.json`)

Each case:

```json
{
  "id": "single_001",
  "description": "Separable verb not split in main clause",
  "user_text": "Ich aufstehe um 7 Uhr.",
  "level": "a1",
  "language": "german",
  "writing_prompt": "Describe your morning routine.",
  "expected_mistake_count": 1,
  "expected_mistakes": [
    {
      "fragment": "Ich aufstehe",
      "error_tag": "verb_conjugation",
      "correction": "Ich stehe auf"
    }
  ],
  "expected_corrected_text": "Ich stehe um 7 Uhr auf."
}
```

`error_tag` must be a tag from `lang/maps/taxonomy/german_taxonomy_v1.yaml`. The taxonomy label check enforces this at test collection time.

Current coverage: 6 single-error cases (A1/A2), 3 correct-text false-positive probes, 3 multi-error cases (A1–B1).

**Ground truth rules:**
- Verified personally within B1 scope, or against a trusted German grammar reference
- Cover: single error, no errors (false-positive probe), multiple errors, mixed error types

---

## Tier 3 — Regression Fixtures

Accumulated during prompt development. When a prompt produces a notably good output on real input, save it.

Convention:
```
tests/fixtures/regression/{step}_{YYYYMMDD}_{short_description}.json
```

Example: `tests/fixtures/regression/detector_20260628_dative_mixed_errors.json`

On prompt changes, re-run all regression fixtures through the relevant judge. A drop in score flags a regression.

---

## CI Strategy

| Tier | When | Command |
|------|------|---------|
| Tier 1 — unit tests | Every commit | `pytest tests/ -x -q --ignore=tests/judge --ignore=tests/e2e` |
| Tier 2 — LLM judge | Before merging prompt changes | `pytest tests/judge/ -v -s` |
| Tier 3 — regression | Before merging prompt changes | `pytest tests/judge/ -v -s` (same runner) |
| e2e smoke (manual) | Verifying a full flow against a real LLM before a demo | `pytest tests/e2e/ -v -s` |

Tier 1 requires no API keys — `--ignore=tests/e2e` matters here, not just `--ignore=tests/judge`:
`tests/e2e/` (`test_smoke.py`, `test_bridge_smoke.py`) drives the CLI against a real,
running LLM backend end-to-end (e.g. confirming the writing→grammar bridge actually
chains a new session), so it belongs with the manual/live tiers, not Tier 1. Tiers 2, 3,
and the e2e smoke tier all require a live LLM backend (Ollama local or `GEMINI_API_KEY`
for Gemini). See `PROVIDERS.md` for setup.
