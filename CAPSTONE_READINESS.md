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
is fully checked off in `CHECKLIST_FINISHED.md` — Impl, Val, and Fin. Nothing beyond
that is required for submission.

**Correction from the previous pass:** Layer 2b is *not* "implemented, not validated" —
it's not implemented at all. `docs/CHECKLIST.md` shows all four 2b items unchecked
(`[ ] [ ] [ ]`), and the code confirms it: `comparison_note` on `WritingSessionContent`
is a stub that the summarise-session prompt is explicitly told to `Set comparison_note
to null` (`skills/summarise_session/writing/prompts.py:44`, `skill.py:87`). There's no
`/history` command in `ui/cli.py` either — that was a mischaracterization in the prior
version of this doc.

| Layer | What it is | Status |
|---|---|---|
| PoC → 1a → 1b → 1c | Evaluator pipeline, routing, progress summary, web UI | done |
| 2a (i–viii) | Grammar module + bidirectional writing↔grammar bridge | done |
| 2b | Cross-session writing comparison (`comparison_note`) | not started |
| 2c / 3a / 3b / 3c / 3d | CEFR estimator, vocab module, level tracking, Anki export, MCP server | not started — correctly cut |

2b belongs in the same bucket as 2c–3d, not in a special "almost done" category — the
checklist's own "cut rule" says a clean, stable core beats a shaky feature-complete
one. Comparing today's writing to a past session is a nice-to-have on top of the
memory story you're already telling with `error_frequency` + `next_actions`; it isn't
load-bearing for the pitch. **Recommendation: leave 2b cut, same as 2c–3d.** Spend the
time on the items below instead.

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

**For the two dev/polish days (Fri–Sat):** close out README first (§2), then the four
small fixes in §5 below — all cheap, all map to explicit rubric lines. Then do a
single real end-to-end run of the writing→grammar bridge with the actual LLM backend
you'll demo with, not just the automated e2e test, since that's the one flow the whole
video hangs on. That likely fills Friday. Saturday is genuinely spare: stabilize
whatever felt shakiest, don't start a new layer (2b/2c/3a and beyond stay cut) —
except possibly MCP, see §8.

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

## 5. Small fixes that map to explicit rubric lines

A second pass over the code (not just the docs) turned up five items — four cheap
fixes plus one correction to a claim you were about to make. All tests still pass
(225 passed, `pytest tests/ -x -q --ignore=tests/judge --ignore=tests/e2e`) and no
API keys or secrets are committed anywhere in the tree — but each one lines up with
a specific, named rubric criterion, which makes them cheap points relative to new
features. #1 below is the one to fix first; it's a functional bug, not polish.

1. **The default setup path is broken for a cold clone.** `config.yaml` (used
   whenever `LTUT_CONFIG` isn't set — i.e. the "just clone and run" path) references
   a custom Ollama model name, `gemma2-9b-tutor`, built locally from the repo's own
   `Modelfile` (`FROM gemma2:9b`, custom `num_ctx`/stop tokens). `llm/ollama_setup.py`
   auto-`pull`s a missing model, but `ollama pull gemma2-9b-tutor` will fail —
   that name only exists after someone runs
   `ollama create gemma2-9b-tutor -f Modelfile` once, and **that step isn't
   documented anywhere** (`PROVIDERS.md`, `README.md`, `docs/llm_backends.md` — none
   of them mention it, or `ollama create`, or the `Modelfile` at all). Separately,
   **no doc anywhere tells a new user to `pip install -r requirements.txt`** first
   either — every run example in `PROVIDERS.md` jumps straight to setting env vars
   and running `python -m ui.cli`. A judge who clones the repo and follows
   `PROVIDERS.md`'s own "Ollama (default)" instructions verbatim hits a confusing
   failure before ever seeing the app run. This is the single highest-priority fix
   in this whole review — it directly undermines "Public Project Link" (repo +
   setup instructions is your stated path, §5 below) and the Documentation score.
   Fix: add a real quickstart to the README — clone → `pip install -r
   requirements.txt` → `ollama create gemma2-9b-tutor -f Modelfile` → run. Fifteen
   minutes, and it's the difference between the demo working or not for anyone who
   isn't you.
2. **`app.run(debug=True, threaded=True, port=5000)` in `ui/app.py:202`.** Flask's
   debug mode ships the Werkzeug interactive debugger — a known remote-code-execution
   vector if the process is ever reachable from outside localhost. It binds to
   Flask's default host today, so it isn't exposed yet, but it directly undercuts the
   "Security features" concept you're planning to claim (§6) if a judge opens
   `app.py` — which Category 2's code review explicitly invites. Gate it behind an
   env var (`debug=os.environ.get("LTUT_DEBUG") == "1"`) or just drop it before the
   video. One line.
3. **You already have a real security detail you haven't claimed.** `ui/app.py:188-193`
   (`session_view`) checks `abs_path.startswith(data_root_abs)` before serving a
   session file by path — a genuine path-traversal guard, not a generic gesture. Add
   it to the "Solid, claim these → Security features" bullets in §6.
4. **`docs/DESIGN.md`'s architecture tree and repo-structure listing are stale.**
   The grammar module and its skills (`select_grammar`, `dump_grammar`,
   `generate_exercises`, `grade_exercises`) are annotated `(planned)` / "Layer 2a" in
   the ASCII diagrams (lines ~77–123, ~230–249) even though Layer 2a is fully done.
   `ui/mcp_server.py` is listed in the repo tree (line 265) but the file doesn't
   exist. Harmless while `DESIGN.md` stays an internal doc, but §2 recommends pulling
   this diagram straight into the README — do that *after* fixing the annotations,
   or the README will tell judges a finished module is still planned.
5. **Rubric line, not house style: "Your code should contain comments pertinent to
   implementation, design and behaviors."** This project's own convention (comment
   only the non-obvious WHY) is good practice, but comment density in the core files
   is thin — `orchestrator.py`, `modules/grammar/agent.py`, `modules/writing/agent.py`
   each sit around 2–3% comment lines, mostly section headers. You don't need a
   rewrite; you need five or six targeted comments at the spots that are already the
   most non-obvious: the `error_frequency ≥ 2` recurrence threshold,
   `GRAMMAR_MASTERY_THRESHOLD = 0.8`, the memory-boundary enforcement in the
   orchestrator, the `call_with_self_correction` retry loop, and the path-traversal
   check above. That satisfies the letter of the rubric with the same comments you'd
   want for your own sake reading this back in six months.

Separately — the rubric's "Public Project Link" wants either a live, login-free demo
or a public GitHub repo with detailed setup instructions. Given the time left, treat
the GitHub repo + `PROVIDERS.md` as the deliverable, not a hosted deploy: standing up
a public instance this week adds real risk (the `debug=True` issue above becomes
much more serious the moment it's internet-facing, and there's no auth layer at all).
Say so explicitly in the writeup rather than leaving judges to guess which path you
took.

---

## 6. Course concepts — where you actually stand

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
  every LLM output before it touches storage, and a path-traversal guard on the
  session-file viewer route (`ui/app.py:188-193`, checks the resolved path stays
  under `data_root` before serving it). Fix the `debug=True` item in §5 first, then
  claim this with a straight face.
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

## 7. Pushback on the pitch framing

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

## 8. MCP, reconsidered — a data server, not a skill wrapper

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

## 9. Track

**Agents for Good fits the pitch better than Concierge Agents.** Concierge's "keeps
personal information safe" language fits the local-run privacy angle, but the
central thesis — access to correction/tutoring normally paywalled — is squarely
"advancing education" in Agents for Good's own description. Concierge reads more
like scheduling/logistics agents; this project is closer to a tutor than a personal
assistant. Lead with Agents for Good; mention privacy-by-local-execution as a
secondary point, not the frame.

---

## 10. Video — 5 minutes, timed

**Revised approach:** assembled from a few separately-recorded pieces, each focused
on one feature, not one continuous take. Say so up front ("I'll skip the typing/
thinking time and show the interesting parts") — an honest framing move, not a
cop-out, and it removes the single biggest production risk in the original plan
(a live LLM demo staying clean for a 2-minute unbroken take). The rubric's own demo
language ("can include images, an animation, or a video of the agent working")
doesn't require unbroken realtime, so nothing is lost against the criteria. It also
buys editing insurance: a clip that doesn't render well gets re-recorded on its
own, nothing else is affected.

Since it's pieces rather than one flow, pick which features earn a clip — in
priority order, matching the ranking in §3:

1. **The bridge trigger** (non-negotiable — this is the pitch): a recurring error
   surfaces "start grammar practice on X now?", accepted, theory + exercises appear.
2. **The correction step**: a short German paragraph in → severity-graded
   correction + tips out. Establishes what "writing module" means before the bridge
   clip needs it.
3. **The close of the loop** (cut if time is short): exercises graded → suggested
   next writing topic uses the grammar just learned. Nice-to-have; #1 alone still
   carries the pitch without it.

| Time | Beat | Show |
|---|---|---|
| 0:00–0:45 | Problem | The paywall problem in one breath — good correction/tutoring is locked behind subscriptions; this runs on your own machine or your own API key, free either way. |
| 0:45–1:30 | Why agents | One architecture slide: orchestrator routes to modules, modules compose skills, memory boundary is hard. Say it's hand-built multi-agent, not framework-borrowed — own it honestly. |
| 1:30–3:30 | Demo — feature clips | 2-3 separately-recorded clips per the priority list above, stitched with a one-line spoken bridge between each ("once it notices a pattern, it offers..."). Each clip only needs to look clean on its own — no dependency between takes. |
| 3:30–4:15 | The build | Typed contracts, Pydantic-validated LLM output, LLM-as-judge test tier, swappable local/hosted backend — fast, confident, no code scrolling. |
| 4:15–5:00 | Close | One line on scope honesty (PoC, A1–B2 German, one language pair) + what's next. End on the funny background if it's still on screen — memorable beats polished. |

**One thing to make sure actually happens on screen, not just in speech:** the
rubric's key-concept table assigns a specific "where to demonstrate" location per
concept — most are "Code," but **Deployability is scored specifically in the
Video**. Right now "swappable local/hosted backend" is a spoken line in "The build"
— stronger to actually show it: a two-second cut to a terminal with `$env:LTUT_CONFIG
= "config.gemini.yaml"` (or just a slide listing Ollama/Gemini/Vertex with a "same
code, one env var" caption) satisfies that cell literally instead of by inference.

---

## 11. Writeup — 2,500 words, budgeted

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

---

## 12. Submission logistics, not just content

Three small items that aren't code or writing, but are easy to forget until the
last hour:

- **Cover image.** Required to submit the Writeup, separate from the video. Use an
  actual screenshot of the running app rather than a generic graphic — the
  correction-highlight view (colored mistake spans + tips) or the grammar exercise
  view both show real product, and either one doubles as a Media Gallery image
  without extra work. The funny background can be in frame; it's a legitimate
  personality signal, not just decoration.
- **One real diagram image, not ASCII.** The video rubric explicitly wants "images
  and a description of the overall agent architecture," and the writeup wants
  "relevant diagrams or images." The three-grain box diagram in `DESIGN.md` (the one
  in §5 item 4, once its `(planned)` labels are fixed) is the right content — but as
  a monospace code block it reads fine in a GitHub README, less well as a video
  slide or an embedded writeup image. Redrawing it as three or four boxes with
  arrows (any slide tool, ten minutes) gets reused three times: video slide, writeup
  image, and — optionally — a cleaner replacement in the README itself.
- **Title and subtitle.** The rubric asks for both by name on the Writeup, and
  §11's word budget already reserves 150 words for "title + subtitle + problem
  statement" but the actual title hasn't been decided yet. Worth nailing down
  before drafting the rest, since the rest of the writeup should read like it's
  arguing for that title's claim, not the other way around.
