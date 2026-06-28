# Custom Workspace Rules for GermanTutor

These rules define workspace-specific guidelines for AI agents working on this project.

## Quality Assurance & Testing

- **Regression Testing**: Whenever a bug, crash, or translation hallucination is identified, discussed, and fixed, you must write a regression test (e.g., in `tests/test_orchestrator.py` or a dedicated test file) to verify the correct behavior and prevent the regression from recurring.
- **No Live API Calls**: Unit tests (Tier 1) must never make live network calls to LLM backends or external servers. Mock responses must always be used, and HTTP client methods should be patched using standard pytest fixtures to keep test execution fast and offline-capable.

## Design & Implementation

- **Hardcoding Guard**: Prompts, system roles, and logs must never hardcode target languages (e.g., German) or CEFR levels. They must always use template tokens (like `{language}` and `{level}`) and dynamically format them from `ModuleContext`.
- **Mandatory Self-Correction**: Any skill that generates structured outputs (like JSON or YAML) must delegate its completion call to the universal `call_with_self_correction` helper in `skills/protocols.py` to ensure consistent retry-backoff configurations and prevent code duplication.
- **Safe Database Schema Updates**: Any changes to the SQLite database schema in `memory/sqlite_store.py` must handle schema upgrades gracefully (e.g., using `CREATE TABLE IF NOT EXISTS` or catching exceptions when adding columns) to prevent destroying or corrupting existing students' databases when they update to a new version of the package.
- **Git Commit Structure**: All commits must follow the Conventional Commits specification (e.g., `feat(ui):`, `fix(orchestrator):`, `test(cli):`).
