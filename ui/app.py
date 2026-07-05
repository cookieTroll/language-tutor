import os
import sys
import json
import threading
import uuid
import yaml
from queue import Empty

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from flask import Flask, Response, request, jsonify, render_template, stream_with_context
from config import load_config
from memory.factory import build_storage
from llm.factory import build_llm
from orchestrator.orchestrator import Orchestrator
from shared.io import WebIOHandler, SessionAbortRequested
from shared.humanize import humanize_tag

app = Flask(__name__)
app.jinja_env.filters["humanize_tag"] = humanize_tag

# ── Bootstrap ──────────────────────────────────────────────────────────────────
config_path = os.environ.get("LTUT_CONFIG", os.path.join(project_root, "config.yaml"))
_config = load_config(config_path)
_store  = build_storage(_config)
_llm    = build_llm(_config.llm)

# ── Live session registry ──────────────────────────────────────────────────────
_sessions: dict[str, dict] = {}
_sessions_lock = threading.Lock()


def _make_orchestrator(io: WebIOHandler) -> Orchestrator:
    return Orchestrator(_store, _llm, _config, io=io)


def _lang_warning(io: WebIOHandler, language: str, missing: list, configured: bool = True) -> None:
    if not configured:
        io.output(
            f"\n[!] '{language.upper()}' is not yet supported — no language configuration exists for it."
            f"\n    Generate it with: python -m scripts.generate_language {language.lower()}"
        )
    else:
        io.output(
            f"\n[!] No language config for '{language.upper()}'."
            f"\n    Falling back to defaults for: {', '.join(missing)}."
        )
    io.prompt("Press Enter to continue: ")


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/start", methods=["POST"])
def api_start():
    data    = request.get_json() or {}
    user_id = (data.get("user_id") or "student").strip() or "student"
    sid     = str(uuid.uuid4())
    io      = WebIOHandler()

    def run():
        try:
            orch = _make_orchestrator(io)
            forced_recommendation = None
            while True:
                try:
                    forced_recommendation = orch.run_session(
                        user_id,
                        language=None,
                        on_language_warning=lambda lang, missing, configured=True: _lang_warning(io, lang, missing, configured),
                        forced_recommendation=forced_recommendation,
                    )
                except SessionAbortRequested as abort:
                    if abort.action == "end":
                        break
                    io.reset_for_new_activity()
                    forced_recommendation = None
                    continue
                if forced_recommendation is None:
                    # No chaining accepted (or nothing was offered) — stay logged in and
                    # go back to the module chooser instead of ending the whole session.
                    io.reset_for_new_activity()
                    continue
        except Exception as e:
            io.output(f"[!] Session error: {e}")
        finally:
            io.end()

    t = threading.Thread(target=run, daemon=True)
    with _sessions_lock:
        _sessions[sid] = {"io": io, "thread": t}
    t.start()
    return jsonify({"session_id": sid})


@app.route("/api/stream/<sid>")
def api_stream(sid: str):
    with _sessions_lock:
        sess = _sessions.get(sid)
    if not sess:
        return jsonify({"error": "not found"}), 404
    io: WebIOHandler = sess["io"]

    def generate():
        while True:
            try:
                event = io.get_event(timeout=30.0)
                yield f"data: {json.dumps(event)}\n\n"
                if event["type"] == "done":
                    with _sessions_lock:
                        _sessions.pop(sid, None)
                    break
            except Empty:
                yield 'data: {"type":"heartbeat"}\n\n'

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/api/users")
def api_users():
    return jsonify({"users": _store.list_users()})


@app.route("/api/input/<sid>", methods=["POST"])
def api_input(sid: str):
    with _sessions_lock:
        sess = _sessions.get(sid)
    if not sess:
        return jsonify({"error": "not found"}), 404
    data = request.get_json() or {}
    sess["io"].send_input(data.get("text", ""))
    return jsonify({"ok": True})


@app.route("/sessions")
def sessions_list():
    from datetime import datetime, timedelta
    sessions_root = os.path.join(_config.data_root, "sessions")
    filter_user   = request.args.get("user", "")
    filter_7d     = request.args.get("days7", "") == "1"
    cutoff        = (datetime.now() - timedelta(days=7)).isoformat()[:19] if filter_7d else ""

    all_items: list[dict] = []
    if os.path.isdir(sessions_root):
        for dirpath, _, filenames in os.walk(sessions_root):
            for fn in sorted(filenames):
                if not fn.endswith(".yaml") or fn.endswith(".tmp"):
                    continue
                abs_path = os.path.join(dirpath, fn)
                rel_path = os.path.relpath(abs_path, _config.data_root).replace("\\", "/")
                try:
                    with open(abs_path, encoding="utf-8") as f:
                        d = yaml.safe_load(f)
                    mistakes = d.get("mistakes", [])
                    all_items.append({
                        "rel_path":      rel_path,
                        "date":          d.get("date", ""),
                        "module":        d.get("module", ""),
                        "language":      (d.get("language") or "").upper(),
                        "level":         (d.get("level")    or "").upper(),
                        "topic":         d.get("topic") or d.get("task_label", ""),
                        "status":        d.get("status", ""),
                        "user_id":       d.get("user_id", ""),
                        "mistake_count": len(mistakes),
                        "mistakes":      mistakes,
                        "error_tags":    list(dict.fromkeys(
                            m.get("error_tag", "") for m in mistakes if m.get("error_tag")
                        )),
                    })
                except Exception:
                    pass

    all_users = sorted({s["user_id"] for s in all_items if s["user_id"]})
    items = [
        s for s in all_items
        if (not filter_user or s["user_id"] == filter_user)
        and (not cutoff or s["date"][:19] >= cutoff)
    ]
    items.sort(key=lambda x: x["date"], reverse=True)

    error_freq: dict[str, int] = {}
    for s in items:
        for m in s.get("mistakes", []):
            tag = m.get("error_tag", "")
            if tag:
                error_freq[tag] = error_freq.get(tag, 0) + 1

    # strip raw mistakes list before passing to template (error_tags already extracted)
    for s in items:
        s.pop("mistakes", None)

    top_errors = sorted(error_freq.items(), key=lambda x: x[1], reverse=True)[:8]
    max_freq   = top_errors[0][1] if top_errors else 1
    return render_template(
        "sessions.html",
        sessions=items, top_errors=top_errors, max_freq=max_freq,
        all_users=all_users, filter_user=filter_user, filter_7d=filter_7d,
    )


@app.route("/sessions/<path:rel_path>")
def session_view(rel_path: str):
    data_root_abs  = os.path.abspath(_config.data_root)
    abs_path       = os.path.abspath(os.path.join(_config.data_root, rel_path))
    # rel_path comes straight from the URL; resolve '..' segments and confirm the
    # result is still inside data_root before opening it, or a crafted path could
    # read arbitrary files on the host.
    if not abs_path.startswith(data_root_abs + os.sep):
        return "Forbidden", 403
    if not os.path.isfile(abs_path):
        return "Not found", 404
    with open(abs_path, encoding="utf-8") as f:
        session = yaml.safe_load(f)
    return render_template("session.html", session=session, rel_path=rel_path)


if __name__ == "__main__":
    # Werkzeug's interactive debugger executes arbitrary code on exception pages —
    # only enable it via an explicit opt-in, never by default.
    app.run(debug=os.environ.get("LTUT_DEBUG") == "1", threaded=True, port=5000)
