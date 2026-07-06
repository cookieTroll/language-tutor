# Wharf the Language Tutor — Submission Readiness Review

Regenerated from scratch rather than patched — the previous version (written Jul 2,
updated Jul 5) had accumulated two rounds of "add an update section on top" and had
started contradicting itself (its own §1 reality-check table said Layers 2b/2c/3d were
"not started — correctly cut" while its own §0 update, appended above it, said the
opposite). This version is a single consistent pass against current code and docs —
no further update-sections; regenerate again if it goes stale.

Assessed against `docs/capstone_assignment.md`, `docs/_design.md`, `docs/_layers.md`,
`docs/_CHECKLIST.md`, `docs/_CHECKLIST_FINISHED.md`, `docs/_TODO.md`, `README.md`,
`PROVIDERS.md`, `docs/llm_backends.md`, `docs/testing.md`, `docs/memory.md`,
`docs/grammar.md`, `docs/competitive_landscape.md`, and the code itself.

Timezone: GMT+2. Written Mon Jul 6, 2026.

---

## 1. Timeline

| Day | Focus |
|---|---|
| Mon Jul 6 (today) | README overhaul, writeup draft, video recording |
| Tue Jul 7 | Buffer, final alignment check, submit |

Hard deadline: Jul 7, 11:59pm PT = Wed Jul 8, 08:59am GMT+2. Two days of runway left,
not five — most of the code-side work is already done (see §2); what's left is almost
entirely writing and recording, not building.

---

## 2. Reality check — layer status

Everything through Layer 2c is fully checked off in `docs/_CHECKLIST_FINISHED.md`
(Impl, Val, and Fin), and Layer 3d (MCP server) is done and merged. Nothing beyond that
is required for submission.

| Layer | What it is | Status |
|---|---|---|
| PoC → 1a → 1b → 1c | Evaluator pipeline, routing, progress summary, CLI + web UI | done |
| 2a | Grammar module + bidirectional writing↔grammar bridge | done |
| 2b | On-demand writing history summary (`/history`) | done |
| 2c | Level & Progress — mastery view + text-level trend | done |
| 3d | MCP server — read-only tools over session/progress data | done |
| 3a / 3c | Vocab module, Anki export | cut — post-submission (see `docs/_design.md`'s Roadmap) |

**Test suite:** 354 unit tests pass in 17.5s (`pytest tests/ -x -q --ignore=tests/judge
--ignore=tests/e2e`), no API key or network required — `MockLLM` + JSON storage backend
for the whole run.

Rubric concept coverage is **5 of 6**: Multi-agent, MCP Server, Security, Deployability,
Agent skills. Antigravity is the one being skipped entirely, deliberately — no trace of
it in the project and five concepts is already comfortably above the "at least three"
bar. See §3 for the concept-by-concept evidence.

---

## 3. Rubric alignment snapshot

Reading `docs/capstone_assignment.md`'s literal text against the current repo, concept
by concept:

| Key Concept | Where to demonstrate | Status | Evidence |
|---|---|---|---|
| Agent / Multi-agent system (ADK) | Code | **Claim, without ADK** | Hand-built three-grain architecture — orchestrator → writing/grammar modules → shared skills pool (`docs/_design.md`'s Three-Grain Architecture section). Not built on Google ADK; say so plainly rather than staying silent on it. |
| MCP Server | Code | **Solid** | `ui/mcp_server.py` — 10 read-only tools over `StorageProtocol` (`list_users`, `list_languages`, `get_progress`, `list_sessions`, `get_session`, `get_recurring_errors`, `get_vocab_flags`, `export_writing_history`, `get_error_taxonomy`, `get_grammar_topic_list`). No LLM in the loop. Documented in README. |
| Antigravity | Video | **Skip** | No trace in repo or docs; not worth chasing two days out. |
| Security features | Code or Video | **Solid** | No keys in code, `${VAR_NAME}` resolution at load time, Vertex AI path uses ADC (no static key at all), Pydantic validation on every LLM output before it touches storage, path-traversal guard on the session-file viewer (`ui/app.py:213-219`, checks the resolved path stays under `data_root`), and Flask's debug mode is now gated behind `LTUT_DEBUG` rather than always on. |
| Deployability | Video | **Solid** | One config swap (`LTUT_CONFIG`) between local (Ollama, private, free) and hosted (Gemini/Vertex/OpenAI-compat). Needs to actually appear on screen in the video, not just be spoken — see §7. |
| Agent skills | Code or Video | **Solid** | The project's own atomic grain is literally named "skills" — each with a typed contract, prompt template, and `skill_type`. |

**Category 1 (30 pts — Pitch):** Core Concept & Value, Video, Writeup are all writing/
recording tasks at this point, not code tasks — see §5 and §7/§8.

**Category 2 (70 pts — Implementation):**
- **Technical Implementation (50 pts).** Architecture and agent usage are strong (see
  §5). The rubric also asks explicitly for "comments pertinent to implementation,
  design and behaviors" — comment density in the core files (`orchestrator.py`,
  `modules/*/agent.py`) is still thin, mostly section headers. Not worth a rewrite, but
  five or six targeted comments at genuinely non-obvious spots (the `error_frequency
  >= 2` recurrence threshold, `GRAMMAR_MASTERY_THRESHOLD`, the memory-boundary
  enforcement, the `call_with_self_correction` retry loop, the path-traversal check)
  would satisfy this literally.
- **Documentation (20 pts).** This is the one criterion where the repo doesn't yet
  match its own rubric line. The assignment asks for a README explaining "the problem,
  solution, architecture, instructions for setup, and relevant diagrams or images."
  Current `README.md` (~80 lines) has a working quickstart and a full MCP section, but
  no problem statement beyond one sentence, no architecture diagram, no layer status,
  and no known-limitations section. This is the highest-leverage remaining item — see
  §6.

---

## 4. What to highlight — deliverables review

Ranked by judging leverage (pitch fit + Technical Implementation weight + demo-ability
in 5 minutes), not by engineering effort spent. Reviewed against the current code —
the ranking mostly holds, with one change: **language-asset generation moves up**, from
a one-line footnote to a top-tier demo beat. It's real, it's validated the same way as
everything else in the pipeline, and it's concrete evidence of an agentic *pipeline*
rather than a single LLM call — stronger than the architecture slide alone can show.

1. **Cross-session memory → adaptive routing (the writing↔grammar bridge).** This *is*
   the pitch: "one tool that learns what you neglect and routes you there." Fully
   built, zero new dev time needed — spend all remaining video time here.
2. **Language-asset generation is real and demoable, not hypothetical.**
   `lang/generate.py` + `scripts/generate_language.py` chain three self-correcting LLM
   calls (taxonomy → CEFR hints → grammar topics), each validated through the same
   Pydantic contracts and `lang.loader._Registry` cross-reference check German already
   passes, then round-trips through a fresh registry load as an end-to-end check.
   Czech (`lang/languages/czech.yaml`) has already been generated this way and
   spot-checked by a native speaker. This directly answers "why not just hardcode one
   language" and is a genuine second agentic pipeline distinct from the writing/grammar
   loop — worth its own video beat and writeup paragraph, not a footnote. One caveat:
   an actual end-to-end grammar session run *in* the generated Czech content hasn't
   been confirmed yet (`docs/_CHECKLIST.md`'s pre-submission item 5) — do that before
   leaning on it too hard as a live demo, or fall back to showing the generated file.
3. **Configurable LLM backend** (Ollama / Gemini / Vertex / OpenAI-compat, one env
   var). Not a generic "we support providers" flex — it's the actual mechanism behind
   the paywall-democratization thesis. Maps directly to the Deployability concept.
4. **Typed contracts + three-grain architecture** (skills → modules → orchestrator,
   Pydantic-validated LLM output, hard memory boundary). Real weight in Technical
   Implementation. Low demo visibility — needs one clean diagram, not live interaction.
5. **README + writeup as a deliverable.** Best return on remaining time — 20 rubric
   points sitting on a file that already has all its source material written elsewhere
   (`docs/_design.md`, `docs/competitive_landscape.md`). See §6.
6. **LLM-as-judge test suite** (two-LLM design, per-skill judges, fixtures). Answers
   "how do you know the prompts work?" — invisible unless said out loud. One sentence
   in the video, one paragraph in the writeup.
7. **Grammar module on its own** (theory → exercises → grading). Necessary — the
   bridge can't exist without it — but standalone it's "another exercise generator."
8. **`lang/` versioned content maps** (CEFR, taxonomy, exercise types as YAML).
   Genuinely good engineering, but now subsumed by #2 above — the generation pipeline
   is the more demoable half of this story, this is just its data shape.
9. **`/btw` inline question + cosmetic UI.** Real UX charm, near-zero rubric weight.
   Worth 10 seconds in the video for personality.

**Supporting evidence worth one sentence each, not their own beat:**
- **Self-correction on LLM output**, not just validation — `call_with_self_correction`
  feeds a failed Pydantic/taxonomy check back to the LLM and retries. Shows the
  contracts are load-bearing, not decorative.
- **Severity-graded, level-aware feedback** — mistakes graded `critical`/`expected`/
  `minor` by the gap between the user's CEFR level and where that error is normally
  mastered; `tips[]` sorted by distance from the user's level. Part of the answer to
  "why not just paste this into ChatGPT."
- **Zero-cost, zero-key dev/test loop** — the full 354-test suite runs against
  `MockLLM` + JSON storage, no API key, no network, no Ollama install.
- **`docs/competitive_landscape.md`** grounds the "why not existing tools" pitch line
  in actual named comparators (Cambridge Write & Improve, Duolingo Max, Busuu,
  Grammarly, academic CEFR-scoring prototypes) rather than an unverified assertion —
  worth citing that the comparison was actually done, not just claimed.

---

## 5. Weaknesses — small fixes against the rubric

A pass over the current code and docs (not the old, now-superseded list) — everything
previously flagged as broken (cold-start Ollama, `requirements.txt`/`pyproject.toml`
drift, PowerShell-only docs, `debug=True`, stale `DESIGN.md` annotations, stale
`llm_backends.md` SDK description, the untested `on_language_warning` contract, the
missing config-file smoke test) is now fixed — see `git log` around commit `c5faf4d`
and this session's doc-freshness pass. What's actually still open:

1. **README doesn't meet the Documentation rubric line yet.** Missing: a problem
   statement beyond one sentence, an architecture diagram/image, layer status, known
   limitations. All the source material already exists (`docs/_design.md`'s Overview
   and Three-Grain diagram, `docs/competitive_landscape.md`). Highest-value remaining
   item — twenty minutes of editing recovers a fifth of the Category 2 Documentation
   score.
2. **Language generation isn't mentioned in README at all.** Given §4's #2 ranking,
   this is a real gap — a judge skimming the README has no way to know this pipeline
   exists. One paragraph plus a link to `docs/lang.md`/`docs/lang_generation.md`
   closes it.
3. **The cold-start Ollama fix has never been exercised on a genuinely cold machine.**
   `scripts/check_ollama_model.py` exists and is documented (`README.md`,
   `PROVIDERS.md`), but it's only been run against a machine that already had
   `gemma2-9b-tutor` created — which short-circuits before the interesting branches
   (base-model pull prompt, `ollama create` prompt) execute. Before recording the demo
   or submitting: `ollama rm gemma2-9b-tutor` (optionally `ollama rm gemma2:9b` too) on
   a machine that still has Ollama installed, re-run the script, confirm both prompts
   appear and `ollama create` actually succeeds afterward.
4. **The "a few cents a session" cost claim isn't backed by an actual number yet.**
   `docs/_design.md` and this doc both state it, but `docs/_CHECKLIST.md`'s own
   pre-submission list (item 2) still has this as an open action: compute a real
   per-request token/cost estimate for `gemini-2.5-flash` instead of a rounded gut
   figure, before it goes in the writeup's Deployability section.
5. **Judge verdict variance is measurable now but not yet measured.**
   `scripts/run_judge_variance.py` + `scripts/judge_variance.yaml` exist (configured
   for 5 repeats × 13 judges) — a real improvement over having no tooling at all — but
   checking `tests/judge/results/`, only a single pass per judge has actually been run
   so far, not the full repeated sweep. So "judge verdict stability across repeated
   runs isn't yet quantified" is still the honest sentence for the writeup's Testing
   section — say it as "the tooling exists and is ready to run," not "hasn't been
   built," which is the more accurate and slightly stronger framing than before.
6. **Comment density in core files is still thin** relative to the rubric's explicit
   "comments pertinent to implementation, design and behaviors" line — see §3's
   Technical Implementation row for the five or six specific spots worth targeting.
7. **`docs/_CHECKLIST.md`'s own pre-submission list is the tactical source of truth**
   for what's left (README, pricing number, writeup draft, video recording, Czech
   end-to-end grammar session, verify code link, submit) — not duplicated here to
   avoid the same two-copies drift this section itself was rewritten to fix. Check
   that list directly rather than this one for line-item task tracking.

Separately — the rubric's "Public Project Link" wants either a live demo or a public
GitHub repo with detailed setup instructions. Given the time left, the GitHub repo +
`PROVIDERS.md` should be the deliverable, not a hosted deploy: standing up a public
instance adds real risk (no auth layer at all) for no rubric benefit. Say so explicitly
in the writeup rather than leaving judges to guess which path was taken.

---

## 6. Pushback on the pitch framing

**Holds up as stated:** "one tool across every competency" (writing + grammar share
the same orchestrator/module/skill shape and the same UI), the memory/personalization
loop, the writing→grammar→writing chaining, `/btw` as a logged inline help command,
configurable local-or-API backend, and the funny background as a real, verifiable UI
detail (`ui/static/decor.js`).

**Worth stating carefully, not overstating:**
- **"Democratizes corrected output"** — true for the LLM cost (see §5 item 4 on
  getting a real number), not fully true for compute: A1–B2 German only today, and the
  local path needs a GPU that can hold a usable model (6GB VRAM tuning for
  `gemma2:9b`, per `PROVIDERS.md`). Frame it as "removes the subscription paywall," not
  "removes all barriers."
- **"Offers to switch to grammar drill after grading"** — accurate, but only fires
  when an error tag is *recurring* (frequency ≥ 2 in that session's scope), not on
  every session with a mistake. Say "when it notices a pattern," not "after grading."
- **"Remembers what you did and personalizes"** — true, but the recurrence check is
  currently writing-session-scoped (confirmed intentional, not a bug) — don't imply a
  cross-module aggregate memory that doesn't exist yet.

---

## 7. Track

**Agents for Good** fits better than Concierge Agents. Concierge's "keeps personal
information safe" language fits the local-run privacy angle, but the central thesis —
access to correction/tutoring normally paywalled — is squarely "advancing education" in
Agents for Good's own description. Lead with Agents for Good; mention
privacy-by-local-execution as a secondary point, not the frame.

---

## 8. Video — 5 minutes, timed

Assembled from a few separately-recorded pieces, each focused on one feature, not one
continuous take. Say so up front ("I'll skip typing/thinking time and show the
interesting parts") — the rubric's own demo language ("can include images, an
animation, or a video of the agent working") doesn't require unbroken realtime, and it
buys editing insurance: a clip that doesn't render well gets re-recorded alone.

Priority order for which features earn a clip, matching §4's ranking:

1. **The bridge trigger** (non-negotiable): a recurring error surfaces "start grammar
   practice on X now?", accepted, theory + exercises appear.
2. **The correction step**: a short German paragraph in → severity-graded correction +
   tips out. Establishes what "writing module" means before the bridge clip needs it.
3. **Language-asset generation**: `python -m scripts.generate_language <language>`
   running (or sped up), landing on the already-generated, human-spot-checked Czech
   content as proof it produced something usable — one command, validated through the
   same contracts + registry check German uses, zero code changes. Promoted up from
   optional-cut to a core beat per §4.
4. **The close of the loop** (cut first if time is short): exercises graded →
   suggested next writing topic uses the grammar just learned.

| Time | Beat | Show |
|---|---|---|
| 0:00–0:45 | Problem | The paywall problem in one breath — good correction/tutoring is locked behind subscriptions; this runs on your own machine or your own API key, free either way. |
| 0:45–1:30 | Why agents | One architecture slide: orchestrator routes to modules, modules compose skills, memory boundary is hard. Hand-built multi-agent, not framework-borrowed — own it honestly. |
| 1:30–3:30 | Demo — feature clips | Clips 1–3 above (and #4 if time allows), stitched with a one-line spoken bridge between each. |
| 3:30–4:15 | The build | Typed contracts, Pydantic-validated LLM output, LLM-as-judge test tier, swappable local/hosted backend. Text overlay: "354 unit tests, 0 API calls" — a visual credibility beat, not narrated. |
| 4:15–5:00 | Close | One line on scope honesty (PoC, A1–B2 German, one language pair) + what's next. End on the funny background if it's still on screen. |

**One thing to make sure actually happens on screen, not just in speech:** Deployability
is scored specifically in the Video per the key-concept table. A two-second cut to a
terminal with `$env:LTUT_CONFIG = "config.gemini.yaml"` (or a slide listing
Ollama/Gemini/Vertex with a "same code, one env var" caption) satisfies that cell
literally instead of by inference.

---

## 9. Writeup — 2,500 words, budgeted

| Section | Words |
|---|---|
| Title + subtitle + problem statement | 150 |
| Why agents (not a single LLM call) | 250 |
| Architecture — three-grain, contracts, memory boundary | 450 |
| The personalization loop (writing↔grammar bridge) — the centerpiece | 450 |
| Language-asset generation — a second real agentic pipeline | 250 |
| Deployability — local vs API, security posture | 300 |
| Testing approach — unit / LLM-judge / regression tiers | 300 |
| Honest scope — what's PoC, what's cut, why | 250 |
| Journey / what you'd do with more time | 250 |
| **Total** | **2,650 (trim ~150 if over)** |

In "Testing approach," open with the one number worth stating: 354 unit tests, no API
key or network required, full suite in under 20 seconds — one sentence, then move to
the two-LLM judge design, which is the more interesting part. Don't add commit count,
lines of code, or similar project-scale metrics anywhere — they don't map to any rubric
criterion, and a leaner, well-architected agent should have *less* code than a
sprawling one.

Worth a line: the local executor model wasn't assumed, it was tested —
`qwen2.5:7b` vs `gemma2:9b` on the judge suite (e.g. 12/12 passed on `detect_mistakes`
for gemma2:9b vs 4 failures for qwen2.5:7b). qwen 7b wasn't strong enough for reliable
structured output on this skill set, so gemma2:9b became the default local executor.

One honest limitation worth a sentence: judge verdict stability across repeated runs
isn't yet quantified — the tooling to measure it exists (`scripts/run_judge_variance.py`)
but hasn't been run as a full sweep yet (see §5 item 5). Naming this candidly is
stronger than silence, and preempts the obvious follow-up question.

Cut candidates if over budget: the `lang/` content-map internals (fold into the
language-generation paragraph instead of a separate subsection), and the grammar
module's internal exercise-type taxonomy (judges care that theory→exercises→grading
works, not its full type system).

---

## 10. Submission logistics

- **Cover image.** Required to submit the Writeup. Use an actual screenshot of the
  running app — the correction-highlight view (colored mistake spans + tips) or the
  grammar exercise view both show real product and double as a Media Gallery image.
- **One real diagram image, not ASCII.** The three-grain box diagram in
  `docs/_design.md` is the right content, but as a monospace code block it reads fine
  in a GitHub README, less well as a video slide or embedded writeup image. Redrawing
  it as three or four boxes with arrows gets reused three times: video slide, writeup
  image, and README.
- **Title and subtitle.** Not yet decided. Worth nailing down before drafting the rest
  of the writeup, since the rest should read like it's arguing for that title's claim.

---

## 11. Remaining work — see `docs/_CHECKLIST.md`

The line-item pre-submission task list (README rewrite, pricing-number confirmation,
writeup draft, video recording, Czech end-to-end grammar session, verify code link,
submit) lives in `docs/_CHECKLIST.md`'s Pre-Submission section — that's the canonical
tracker, not this document. This file is the strategic assessment; that one is the
checklist to actually work off of.
