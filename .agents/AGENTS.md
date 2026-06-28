# Custom Workspace Rules for GermanTutor

These rules define workspace-specific guidelines for AI agents working on this project.

## Quality Assurance & Testing

- **Regression Testing**: Whenever a bug, crash, or translation hallucination is identified, discussed, and fixed, you must write a regression test (e.g., in `tests/test_orchestrator.py` or a dedicated test file) to verify the correct behavior and prevent the regression from recurring.
