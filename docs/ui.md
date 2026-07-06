# Wharf the Language Tutor — UI Layer (Layer 1c)

The Flask web app, the CLI, and the `IOHandler` abstraction that lets the exact same
orchestrator/module code drive either one. See `docs/_contracts.md` for the `IOHandler`
protocol shape and `docs/orchestrator.md` for the session flow this layer is rendering.

---

## `IOHandler` — one contract, two renderers

Modules and the orchestrator never touch the terminal or HTTP directly — everything
user-facing goes through `shared/io.py`'s `IOHandler` protocol:

```python
class IOHandler(Protocol):
    show_cli_hints: bool
    def output(self, text: str = "") -> None: ...
    def prompt(self, text: str = "") -> str: ...
    def prompt_block(self, text: str = "") -> str: ...   # multi-line answer as one string
    def reset_for_new_activity(self) -> None: ...          # back to the module chooser
    def render_evaluation(self, data: dict) -> None: ...    # writing feedback
    def render_exercises(self, data: dict) -> None: ...     # generated grammar exercises
    def render_results(self, data: dict) -> None: ...       # graded grammar results
    def render_progress(self, data: dict) -> None: ...      # Layer 2c /progress
    def start_timer(self, label: str = "Writing") -> None: ...
    def stop_timer(self) -> None: ...
```

The `render_*` split is deliberate: the orchestrator/module only ever gathers and hands
over structured data, never formats it — `TerminalIOHandler` draws ASCII (bar charts,
`==` section rules), `WebIOHandler` forwards the same data as an SSE event for
JS to render as HTML/CSS. Neither implementation knows the other exists.

### `TerminalIOHandler` (CLI)

Thin wrapper over `print()`/`input()`. `prompt_block()` reads lines until a blank line —
the one place the CLI needs special handling, since the web client already posts a full
multi-line textarea value in a single `send_input()` call.

### `WebIOHandler` (Flask) — queue bridge

Each session runs its module/orchestrator code on a background thread, blocked on
ordinary-looking `input()`-shaped calls that are actually reading from a queue:

```
Session thread                     Flask request handlers
───────────────                    ──────────────────────
io.output(text)      ──put──▶  _out_q  ──get──▶  GET /api/stream/<sid>  (SSE)
io.prompt(text)       ──put──▶  _out_q  (type: "prompt")
                      ──get──◀  _in_q   ◀──put──  POST /api/input/<sid>
```

`output()`/`render_*()` push `{"type": "output"|"data", ...}` onto `_out_q`; `prompt()`
pushes a `{"type": "prompt"}` event, then blocks on `_in_q.get()` until
`POST /api/input/<sid>` calls `send_input()`. Two reserved sentinel strings
(`ABANDON_SESSION_SENTINEL`, `SWITCH_USER_SENTINEL`) let the browser's "Return to
Menu"/"Switch User" buttons interrupt whatever `prompt()`/`prompt_block()` call the
thread is currently blocked on — `WebIOHandler` raises `SessionAbortRequested(action=...)`
instead of returning a normal answer, which `ui/app.py`'s `run()` closure and
`orchestrator.run_session()` both know how to catch (see `docs/orchestrator.md`).

`render_evaluation()` humanizes a **display copy** of each mistake's `error_tag`
(`shared/humanize.py::humanize_tag`) before sending it to the browser — never mutates
the caller's dict, since the raw tag values are the actual `error_frequency` keys
elsewhere in the pipeline. `render_progress()` needs no such step: `weak_tags`/
`strong_tags` (`orchestrator/mastery.py`) are already human-readable text.

---

## Flask routes (`ui/app.py`)

| Route | Method | Purpose |
|---|---|---|
| `/` | GET | Serves `index.html` — the chat/session SPA shell |
| `/api/start` | POST | Spawns a background thread running `orchestrator.run_session()` in a loop (re-invoking with `forced_recommendation` on an accepted bridge chain, looping back to the chooser via `reset_for_new_activity()` when nothing was accepted); returns a `session_id` |
| `/api/stream/<sid>` | GET | SSE endpoint — streams `WebIOHandler`'s `_out_q` events to the browser as `text/event-stream`; sends a heartbeat every 30s while idle |
| `/api/input/<sid>` | POST | Delivers browser input to the session's `_in_q` via `send_input()` |
| `/api/users` | GET | `store.list_users()` — populates the login/switch-user picker |
| `/sessions` | GET | Session history browser — walks `data/{data_root}/sessions/`, parses each YAML file, supports `?user=` and `?days7=1` filtering, computes an error-tag frequency table for the page |
| `/sessions/<path:rel_path>` | GET | Single session view — parses one session YAML and renders it via `session.html`. Checks the resolved absolute path stays under `data_root` before serving (path-traversal guard) |

Session state (`_sessions: dict[str, {"io", "thread"}]`) lives in an in-process dict
guarded by `_sessions_lock` — there is no persistence or multi-worker story for
in-flight sessions; a restart drops any session mid-flight (the WAL/checkpoint
mechanism in `docs/memory.md` covers *data* durability, not this in-memory session map).

---

## Static JS (`ui/static/`)

Load order matters — several files depend on globals defined earlier ones set up.
Each file's own header comment states its dependencies; summarized here:

| File | Role |
|---|---|
| `app.js` | Core: SSE event dispatch, session lifecycle/phase state machine (`idle → setup → loading → writing → evaluating → follow-up → done`), generic helpers (`escapeHtml`, `appendTutor`, `sendInput`). Loads first — everything else depends on it |
| `writing-ui.js` | Writing-module handlers: submit, evaluation rendering, follow-up `/btw` phase |
| `grammar-ui.js` | Grammar-module handlers: exercise display, block-answer collection, results rendering, a small hand-rolled markdown renderer for `dump_grammar`'s explanation output (headings/bold/lists/tables only — matches exactly what that skill's prompt asks the model to produce, not general-purpose markdown) |
| `progress-ui.js` | Renders the Layer 2c `/progress` response (mastery bars, weak/strong tags, trend) into `#setup-output` — fires during the setup phase, like `/history`, not inside an active session panel |
| `diff.js` | Word-level LCS diff (`tokenise`/`lcs`) — shared utility grammar-ui.js uses to highlight corrections against a user's answer |
| `decor.js` | Purely cosmetic: background themes, confetti, font size, column resizer. No session-state coupling except reading `appendTutor` (from `app.js`) at parse time for a confetti hook — must load after `app.js` |

---

## Templates (`ui/templates/`)

- **`index.html`** — the single-page app shell: module chooser, writing pad, grammar
  exercise panel, tutor/`/btw` sidebar, session timer widget. All dynamic content is
  DOM manipulation driven by the JS above, not server-side templating per session turn.
- **`session.html`** — one session's detail view (`humanize_tag` Jinja filter applied to
  raw `error_tag` values here too, matching the terminal/web render paths). Renders
  `next_actions` generically for *any* session type that has them, not just grammar
  sessions, since the field lives on the `SessionFileContent` base class.
- **`sessions.html`** — the session list/browser view, with the user/date filters and
  error-frequency table `/sessions` computes server-side.

---

## Session Timer

`start_timer()`/`stop_timer()` are asymmetric between the two `IOHandler`s:
`TerminalIOHandler` owns a real background thread (`shared/timer.py::SessionTimer`)
updating the terminal title; `WebIOHandler`'s versions are no-ops — the browser runs its
own JS timer, tied to active typing time rather than the whole session (see `app.js`'s
phase machine — the clock stops the moment `submitWriting()` fires, not when evaluation
finishes).
