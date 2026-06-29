# LanguageTutor AI Agent

LanguageTutor is an AI-powered language tutoring agent focused on personalized **output and writing** practice. It tracks session history, identifies recurring grammatical and vocabulary errors, and routes users to adaptive exercises.

## Repository Structure

* [docs/DESIGN.md](docs/DESIGN.md) — Human-facing architectural overview.
* [docs/LAYERS.md](docs/LAYERS.md) — Deliverable manifest per release layer.
* [docs/CHECKLIST.md](docs/CHECKLIST.md) — Implementation task list.
* [docs/TODO.md](docs/TODO.md) — Known risks, backlog, and deferred design items.
* [docs/contracts.md](docs/contracts.md) — Original interface and protocol specifications.
* [PROVIDERS.md](PROVIDERS.md) — LLM provider setup, API key management, config selection.

### Source Code

* [llm/base.py](llm/base.py) — LLM client wrapper protocol.
* [skills/protocols.py](skills/protocols.py) — Atomic skill contracts.
* [modules/protocols.py](modules/protocols.py) — Middle-grain agent/module contracts.
* [memory/protocols.py](memory/protocols.py) — Data models and storage contracts.
