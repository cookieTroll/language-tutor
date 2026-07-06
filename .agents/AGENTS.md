# Custom Workspace Rules for Wharf the Language Tutor

These rules define workspace-specific guidelines for AI agents working on this project.

## Quality Assurance & Testing

- **Tests before commit**: Always run `python -m pytest tests/ -x -q --ignore=tests/judge` and confirm all tests pass before creating any git commit.

- **Regression Testing**: Whenever a bug, crash, or translation hallucination is identified, discussed, and fixed, you must write a regression test (e.g., in `tests/test_orchestrator.py` or a dedicated test file) to verify the correct behavior and prevent the regression from recurring.
- **No Live API Calls**: Unit tests (Tier 1) must never make live network calls to LLM backends or external servers. Mock responses must always be used, and HTTP client methods should be patched using standard pytest fixtures to keep test execution fast and offline-capable.

## Design & Implementation

- **Hardcoding Guard**: Prompts, system roles, and logs must never hardcode target languages (e.g., German) or CEFR levels. They must always use template tokens (like `{language}` and `{level}`) and dynamically format them from `ModuleContext`.
- **Mandatory Self-Correction**: Any skill that generates structured outputs (like JSON or YAML) must delegate its completion call to the universal `call_with_self_correction` helper in `skills/protocols.py` to ensure consistent retry-backoff configurations and prevent code duplication.
- **Safe Database Schema Updates**: Any changes to the SQLite database schema in `memory/sqlite_store.py` must handle schema upgrades gracefully (e.g., using `CREATE TABLE IF NOT EXISTS` or catching exceptions when adding columns) to prevent destroying or corrupting existing students' databases when they update to a new version of the package.
- **Git Commit Structure**: All commits must follow the Conventional Commits specification (e.g., `feat(ui):`, `fix(orchestrator):`, `test(cli):`).

## Code Health

- **Bloat check**: When a commit substantially grows an existing file or function (e.g. a file crosses ~500 lines, or a function/file starts visibly mixing unrelated concerns), proactively flag it and propose a concrete split — don't wait to be asked. Suggest only; don't refactor without confirmation, per the project's "don't refactor beyond what's asked" norm.

## Documentation Sync

Each `docs/` file owns a specific concern (see below). After any commit that adds, renames, or removes a package, skill, or module — or changes a public interface, session file schema, storage method, or test structure — check every `docs/` file whose concern is touched and update it to reflect current reality.

| File | Owns |
|---|---|
| `_design.md` | Architecture overview, delivery layers, repo structure tree, skills listing, key design decisions |
| `_TODO.md` | Deferred decisions and known risks — mark items done when the referenced code is implemented; update stale file paths |
| `_CHECKLIST.md` | Implementation progress — mark `[Impl]` for newly implemented items; add new items for planned work |
| `_contracts.md` | All protocol and dataclass definitions (`ModuleProtocol`, `SkillProtocol`, `StorageProtocol`, etc.) |
| `memory.md` | Storage schema, session file format, interruption/checkpoint flow |
| `orchestrator.md` | Orchestrator logic, cold start, prompts, LLM routing |
| `testing.md` | Three-tier test architecture, judge setup, fixture conventions |
| `llm_backends.md` | LLM abstraction, provider implementations, config |
| `writing.md` | Writing module + evaluator pipeline (Steps 1–6), `WritingSessionContent` schema |
| `grammar.md` | Grammar module spec (Layer 2a) |
| `vocab.md` | Vocab module spec (Layer 3a) |
| `_layers.md` | Flat layer manifest — update when a layer's scope or status changes |

Routine commits (prompt tweaks, YAML content updates, bug fixes that don't change interfaces) do not require a doc pass.
