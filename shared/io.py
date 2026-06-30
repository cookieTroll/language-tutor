from typing import Protocol
from queue import Queue, Empty
from shared.timer import SessionTimer


class IOHandler(Protocol):
    show_cli_hints: bool

    def output(self, text: str = "") -> None: ...
    def prompt(self, text: str = "") -> str: ...
    def render_evaluation(self, data: dict) -> None: ...
    def start_timer(self, label: str = "Writing") -> None: ...
    def stop_timer(self) -> None: ...


class TerminalIOHandler:
    show_cli_hints = True

    def __init__(self) -> None:
        self._timer: SessionTimer | None = None

    def output(self, text: str = "") -> None:
        print(text)

    def prompt(self, text: str = "") -> str:
        return input(text)

    def start_timer(self, label: str = "Writing") -> None:
        self._timer = SessionTimer(label=label)
        self._timer.start()

    def stop_timer(self) -> None:
        if self._timer:
            self._timer.stop()
            self._timer = None

    def render_evaluation(self, data: dict) -> None:
        self.output(
            "\n=================================================="
            "\n                 EVALUATION"
            "\n=================================================="
        )
        if not data.get("detector_success", True):
            self.output(
                f"[!] Mistake detection failed."
                f"\n    Error: {data.get('detector_error', '')}"
            )
        elif data.get("explained_mistakes"):
            mistakes = data["explained_mistakes"]
            self.output(f"Found {len(mistakes)} mistake(s):\n")
            groups: dict[str, list[dict]] = {"critical": [], "expected": [], "minor": [], "": []}
            for m in mistakes:
                groups.setdefault(m.get("severity", ""), []).append(m)
            labels = {
                "critical": "── Critical ──────────────────────────────────────",
                "expected": "── Expected at this level ────────────────────────",
                "minor":    "── Minor / stylistic ─────────────────────────────",
                "":         "── Mistakes ──────────────────────────────────────",
            }
            counter = 0
            for sev in ("critical", "expected", "minor", ""):
                if not groups.get(sev):
                    continue
                self.output(labels[sev])
                for m in groups[sev]:
                    counter += 1
                    self.output(
                        f"{counter}. [{m['error_tag']}] '{m['fragment']}'"
                        f"\n   Correction : {m['correction']}"
                        f"\n   Explanation: {m['explanation']}\n"
                    )
        else:
            self.output("Excellent! No mistakes were identified.")

        if data.get("corrected_text"):
            self.output(
                f"── Corrected text ────────────────────────────────"
                f"\n{data['corrected_text']}\n"
            )
        if data.get("session_summary"):
            self.output(
                f"── Session summary ───────────────────────────────"
                f"\n  {data['session_summary']}\n"
            )
        if data.get("tips"):
            tips_text = "\n".join(f"  • {tip}" for tip in data["tips"])
            self.output(f"── Tips ──────────────────────────────────────────\n{tips_text}\n")
        if data.get("text_level_estimate"):
            estimate = data["text_level_estimate"].upper()
            level_line = f"  Estimated: {estimate}"
            if data.get("stated_level"):
                level_line += f"  (your stated level: {data['stated_level'].upper()})"
            self.output(
                f"── Text level ────────────────────────────────────"
                f"\n{level_line}"
            )
        self.output("==================================================\n")


class WebIOHandler:
    """Bridges a blocking session thread to an HTTP/SSE client via two queues.

    The session thread calls output() / prompt() normally.
    The Flask layer reads events via get_event() and posts replies via send_input().
    """

    show_cli_hints = False

    def __init__(self) -> None:
        self._out_q: Queue[dict] = Queue()
        self._in_q: Queue[str] = Queue()

    def output(self, text: str = "") -> None:
        self._out_q.put({"type": "output", "text": text})

    def prompt(self, text: str = "") -> str:
        self._out_q.put({"type": "prompt", "text": text})
        return self._in_q.get()  # blocks until send_input() is called

    def send_input(self, text: str) -> None:
        self._in_q.put(text)

    def render_evaluation(self, data: dict) -> None:
        self._out_q.put({"type": "data", "payload": {"event": "evaluation_complete", **data}})

    def start_timer(self, label: str = "Writing") -> None:
        pass  # web UI manages its own timer in JS

    def stop_timer(self) -> None:
        pass

    def end(self) -> None:
        self._out_q.put({"type": "done", "text": ""})

    def get_event(self, timeout: float = 30.0) -> dict:
        """Raises queue.Empty on timeout."""
        return self._out_q.get(timeout=timeout)
