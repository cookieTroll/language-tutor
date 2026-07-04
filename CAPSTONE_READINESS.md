# LanguageTutor — Submission Readiness Review

Kaggle capstone readiness audit, a value ranking of what's actually built, and a shape
for the 2,500-word writeup and 5-minute video. Assessed against
`docs/capstone_assignment.md`, `docs/CHECKLIST.md`, `docs/CHECKLIST_FINISHED.md`,
`docs/DESIGN.md`, `docs/LAYERS.md`, `docs/TODO.md`, `README.md`, `PROVIDERS.md`,
`docs/llm_backends.md`, `docs/testing.md`, `docs/memory.md`, `docs/grammar.md`.

Timezone: GMT+2. Written Thu Jul 2, 2026, evening.

---

## Timeline

| Day | Focus |
|---|---|
| Fri Jul 3 | Dev + polish |
| Sat Jul 4 | Dev + polish |
| Sun Jul 5 | Documentation + video |
| Mon Jul 6 | Documentation + video |
| Tue Jul 7 | Extra buffer |

Hard deadline: Jul 7, 11:59pm PT = Wed Jul 8, 08:59am GMT+2.

---

## 1. Reality check

Everything through Layer 2a (grammar module, writing↔grammar bridge, both directions)
is fully checked off in `CHECKLIST_FINISHED.md` — Impl, Val, and Fin. Layer 2b
(`/history`) is implemented but not yet validated. Nothing beyond that is required for
submission.

| Layer | What it is | Status |
|---|---|---|
| PoC → 1a → 1b → 1c | Evaluator pipeline, routing, progress summary, web UI | done |
| 2a (i–viii) | Grammar module + bidirectional writing↔grammar bridge | done |
| 2b | `/history` on-demand summary | implemented, not validated |
| 2c / 3a / 3b / 3c / 3d | CEFR estimator, vocab module, level tracking, Anki export, MCP server | not started — correctly cut |

2c–3d were always later layers; the checklist's own "cut rule" already says a clean,
stable core beats a shaky feature-complete one. The one loose end worth closing is
**validating 2b** — it's already built and mid-flight.

---

## 2. Rubric gap: README

**Documentation is worth 20 of 100 points.** The rubric asks explicitly for "a
README.md file explaining the problem, solution, architecture, instructions for
setup, and relevant diagrams." The current `README.md` is 18 lines — a title, one
paragraph, and a table of links into `docs/`. A judge who doesn't click through five
internal docs scores this section on what's actually in the file.

This is writing, not code — pull the problem statement, the three-grain architecture
diagram (already in `DESIGN.md`), and the `PROVIDERS.md` setup steps into the README
itself. Twenty minutes of editing recovers points a week of extra features wouldn't.

---

## 3. Component value ranking

Ranked by judging leverage — pitch-criteria fit (30 pts), technical-implementation
weight (50 pts), and demo-ability in 5 minutes — not by engineering effort spent.

1. **Cross-session memory → adaptive routing (the writing↔grammar bridge).** This
   *is* the pitch. "Most language tools are rigid; this one learns what you neglect
   and routes you there" only becomes real because `error_frequency` feeds
   `next_actions` feeds a live "start grammar practice on dative case now?" prompt.
   Fully built — spend zero new dev time, spend all your video time here.
2. **Configurable LLM backend** (Ollama / Gemini / Vertex / OpenAI-compat, one env
   var). Not a generic "we support multiple providers" flex — it's the actual
   mechanism behind the paywall-democratization thesis. Without it, "runs free on
   your own hardware" is a claim; with it, it's a `$env:LTUT_CONFIG` switch you can
   show live. Maps to the Deployability concept.
3. **README + writeup as a deliverable.** Best return on remaining dev time — see
   §2. 20 rubric points sitting on a file you already have all the source material
   for.
4. **Typed contracts + three-grain architecture** (skills → modules → orchestrator,
   Pydantic-validated LLM output). Real weight in Technical Implementation (50 pts)
   — most capstone submissions won't have a hard memory boundary or self-correcting
   validation on every LLM call. Low demo visibility: needs one clean architecture
   slide, not live interaction.
5. **LLM-as-judge test suite** (two-LLM design, fixtures, judge verdicts). Answers
   the question serious reviewers ask about LLM apps — "how do you know the prompts
   work?" — but invisible unless said out loud. One sentence in the video, one
   paragraph in the writeup.
6. **Grammar module on its own** (theory → exercises → grading). Necessary — the
   bridge in #1 can't exist without it — but as a standalone feature it's "another
   exercise generator." Its value is almost entirely in being the second half of the
   loop.
7. **`lang/` external content maps** (CEFR, taxonomy, exercise types as versioned
   YAML). Genuinely good engineering — "add a language without touching code" — but
   judges can't see it and it doesn't demo. One line in the writeup; skip in video.
8. **`/btw` inline question + cosmetic UI** (the funny background). Real UX charm,
   near-zero rubric weight. Worth 10 seconds in the video for watchability and
   personality.

**For the two dev/polish days (Fri–Sat):** close out README and finish validating
2b first — cheap, closes an open loop. Then do a single real end-to-end run of the
writing→grammar bridge with the actual LLM backend you'll demo with, not just the
automated e2e test, since that's the one flow the whole video hangs on. That likely
fills Friday. Saturday is genuinely spare: stabilize whatever felt shakiest, don't
start a new layer (2c/3a and beyond stay cut) — except possibly MCP, see below.

---

## 4. Points you omitted — worth adding

Beyond what you listed, four things in the code are worth a specific mention rather
than folding into generic "typed contracts" or "memory" framing:

1. **Interrupted-session handling (resume / log / discard, WAL-based checkpointing).**
   If the app dies or is closed mid-session, restart offers to resume, generate an
   LLM summary of the partial transcript and discard, or discard outright. Shows the
   system treats real-world interruption as first-class, not an afterthought — and
   it's demoable: kill the process mid-write, restart, show the prompt. Good video
   beat, cheap to show.
2. **Self-correction on LLM output, not just validation.** When a skill's structured
   output fails a Pydantic/taxonomy check, `call_with_self_correction` feeds the
   validation error back to the LLM and retries — an actual small agentic loop, not
   "validate and reject." More concrete than "typed contracts" and shows the
   contracts are load-bearing, not decorative.
3. **Severity-graded, level-aware feedback.** Each mistake is graded
   `critical`/`expected`/`minor` based on the gap between the user's CEFR level and
   the level that error tag is normally mastered at; `tips[]` are sorted by distance
   from the user's level. A pedagogy point, not an engineering one — it's part of the
   answer to "why not just paste this into ChatGPT": a flat correction list doesn't
   grade by what you're actually ready to hear.
4. **Zero-cost, zero-key local dev/test loop.** The full unit test suite runs against
   `MockLLM` and the JSON storage backend — no API key, no network, no Ollama install
   required to clone the repo and run tests. A cheap, concrete answer if a judge
   wants to try it without setting up billing first.

Best odds of making the final cut given the budgets in §9/§10: **#1** is a strong,
cheap video beat (worth a slot around 3:30–4:15 alongside "the build"); **#3** is a
strong, cheap writeup sentence in the "why agents" section. #2 and #4 are fine as
one-liners if there's room left over — don't let them crowd out the writing↔grammar
bridge demo, which stays the centerpiece.

---

## 5. Course concepts — where you actually stand

The rubric wants at least three of: Agent/Multi-agent system (ADK), MCP Server,
Antigravity, Security features, Deployability, Agent skills. A repo grep for `ADK`,
`MCP`, and `Antigravity` turns up nothing but the rubric text itself — be deliberate
about which ones you claim.

**Solid, claim these:**

- **Multi-agent system** — orchestrator + module agents + composable skills is a
  real three-grain agent architecture, just hand-built rather than on Google ADK.
  Say so plainly rather than staying silent on ADK.
- **Security features** — no keys in code, `${VAR}` resolution at load time, `.env`
  gitignored, Vertex AI path uses ADC (no static key at all), Pydantic validation on
  every LLM output before it touches storage.
- **Deployability** — one config swap between local (Ollama, private, free) and
  hosted (Gemini/Vertex/OpenAI-compat) API. Same evidence as ranking #2 above.
- **Agent skills** — the project's own atomic grain is literally named "skills,"
  each with its own contract, prompt, and `skill_type`.

**Real gaps — don't claim:**

- **MCP Server** — scoped as Layer 3d, not started. Better direction than the
  original spec: a **read-only data server over `StorageProtocol`** (error
  frequency, recent sessions, vocab flags, current level) rather than wrapping a
  skill. No LLM in the loop, so genuinely a few hours — see §6.
- **Antigravity** — no trace in the repo or docs. Not worth chasing this late; four
  concepts are already covered without it.

---

## 6. Pushback on the pitch framing

**Holds up as stated:** "one interface for all" (writing + grammar share the same
orchestrator/module/skill shape and the same UI), the memory/personalization loop,
the writing→grammar→writing chaining, `/btw` as a logged inline help command,
configurable local-or-API backend, and the funny background as a real, verifiable
UI detail (confirmed in `ui/static/decor.js`).

**Worth softening:**

- **"Democratize the corrected output"** — true for the LLM cost, not fully true yet
  for compute: A1–B2 German only, and the local path needs a GPU that can hold a
  usable model (own config notes 6GB VRAM tuning for `gemma2:9b`). Frame it as
  "removes the subscription paywall," not "removes all barriers."
- **"After grading it offers to switch to grammar drill"** — accurate, but only
  fires when an error tag is *recurring* (frequency ≥ 2 in that session's scope),
  not on every session with a mistake. Say "when it notices a pattern," not "after
  grading."
- **"It remembers what you did and personalizes"** — true, but currently
  writing-session-scoped for the recurrence check (confirmed intentional, not a
  bug) — don't imply cross-module aggregate memory that doesn't exist yet.

---

## 7. MCP, reconsidered — a data server, not a skill wrapper

Better idea than the original Layer 3d spec: expose read-only tools over
`StorageProtocol` — `get_error_frequency`, `get_sessions_by_module`,
`get_vocab_flags`, `get_current_level` — rather than wrapping a skill (which would
put an LLM call in the loop). Reasons:

1. **Lower risk.** No LLM call, no prompt tuning, no new failure mode — pure reads
   through already-typed storage methods. Genuinely an afternoon.
2. **Narratively coherent, not bolted-on.** Reinforces component #1 (memory/
   personalization) instead of adding an unrelated capability just to check a
   rubric box — it's the same memory, exposed a second way.
3. **Demos cleanly.** Open any MCP client, ask "what German errors do I keep
   making?", get a real answer pulled from your own session history.

Keep it strictly **read-only** — no tool that writes vocab flags or sessions — and
cap it at **3–4 tools**, not a full mirror of the storage surface. Architecturally
it's a second, read-only entry point onto the same storage boundary `DESIGN.md`
already documents (today only the orchestrator touches storage) — worth one
sentence in the writeup, not a redesign. Scope for Saturday, after Friday's
README/2b/bridge work is done. Optional insurance for the "3 of 6 concepts" rubric
line, not a requirement — skip without guilt if Friday runs long.

---

## 8. Track

**Agents for Good fits the pitch better than Concierge Agents.** Concierge's "keeps
personal information safe" language fits the local-run privacy angle, but the
central thesis — access to correction/tutoring normally paywalled — is squarely
"advancing education" in Agents for Good's own description. Concierge reads more
like scheduling/logistics agents; this project is closer to a tutor than a personal
assistant. Lead with Agents for Good; mention privacy-by-local-execution as a
secondary point, not the frame.

---

## 9. Video — 5 minutes, timed

| Time | Beat | Show |
|---|---|---|
| 0:00–0:45 | Problem | The paywall problem in one breath — good correction/tutoring is locked behind subscriptions; this runs on your own machine or your own API key, free either way. |
| 0:45–1:30 | Why agents | One architecture slide: orchestrator routes to modules, modules compose skills, memory boundary is hard. Say it's hand-built multi-agent, not framework-borrowed — own it honestly. |
| 1:30–3:30 | Demo — the loop | Live: write a short German paragraph → correction + tips appear → a recurring error triggers "start grammar practice on X now?" → accept → theory + exercises appear → grade → suggested next writing topic uses the grammar just learned. One continuous take carries the whole pitch. |
| 3:30–4:15 | The build | Typed contracts, Pydantic-validated LLM output, LLM-as-judge test tier, swappable local/hosted backend — fast, confident, no code scrolling. |
| 4:15–5:00 | Close | One line on scope honesty (PoC, A1–B2 German, one language pair) + what's next. End on the funny background if it's still on screen — memorable beats polished. |

---

## 10. Writeup — 2,500 words, budgeted

| Section | Words |
|---|---|
| Title + subtitle + problem statement | 150 |
| Why agents (not a single LLM call) | 250 |
| Architecture — three-grain, contracts, memory boundary | 500 |
| The personalization loop (writing↔grammar bridge) — the centerpiece | 500 |
| Deployability — local vs API, security posture | 300 |
| Testing approach — unit / LLM-judge / regression tiers | 300 |
| Honest scope — what's PoC, what's cut, why | 250 |
| Journey / what you'd do with more time | 250 |
| **Total** | **2,500** |

Cut candidates if over budget: the `lang/` content-map detail (one sentence instead
of a subsection), and the grammar module's internal exercise-type taxonomy (judges
care that theory→exercises→grading works, not its full type system).
