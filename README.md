# LanguageTutor AI Agent

LanguageTutor is an AI-powered language tutoring agent focused on personalized **output and writing** practice. It tracks session history, identifies recurring grammatical and vocabulary errors, and routes users to adaptive exercises.

## Repository Structure

* [docs/DESIGN.md](file:///C:/Users/jankr/google_agents/language-tutor/docs/DESIGN.md) — Human-facing architectural overview.
* [docs/LAYERS.md](file:///C:/Users/jankr/google_agents/language-tutor/docs/LAYERS.md) — Deliverable manifest per release layer.
* [docs/CHECKLIST.md](file:///C:/Users/jankr/google_agents/language-tutor/docs/CHECKLIST.md) — Implementation task list.
* [docs/TODO.md](file:///C:/Users/jankr/google_agents/language-tutor/docs/TODO.md) — Known risks, backlog, and deferred design items.
* [docs/contracts.md](file:///C:/Users/jankr/google_agents/language-tutor/docs/contracts.md) — Original interface and protocol specifications.

### Source Code

* [llm/base.py](file:///C:/Users/jankr/google_agents/language-tutor/llm/base.py) — LLM client wrapper protocol.
* [skills/protocols.py](file:///C:/Users/jankr/google_agents/language-tutor/skills/protocols.py) — Atomic skill contracts.
* [modules/protocols.py](file:///C:/Users/jankr/google_agents/language-tutor/modules/protocols.py) — Middle-grain agent/module contracts.
* [memory/protocols.py](file:///C:/Users/jankr/google_agents/language-tutor/memory/protocols.py) — Data models and storage contracts.
