from typing import Protocol
from queue import Queue, Empty
from shared.timer import SessionTimer


class IOHandler(Protocol):
    show_cli_hints: bool

    def output(self, text: str = "") -> None: ...
    def prompt(self, text: str = "") -> str: ...
    def prompt_block(self, text: str = "") -> str:
        """Collect a multi-line answer as one opaque string (e.g. a block of grammar exercise answers)."""
        ...
    def render_evaluation(self, data: dict) -> None: ...
    def render_exercises(self, data: dict) -> None:
        """Render a generated exercise list, batched by type.
        data: {"groups": [{"exercise_type", "instruction", "exercises": [{"prompt"}, ...]}, ...]}.
        """
        ...
    def render_results(self, data: dict) -> None:
        """Render graded exercise results. data: {"items": [...], "score": float}."""
        ...
    def render_progress(self, data: dict) -> None:
        """Render mastery/level-progress data (Layer 2c /progress command).
        data: {"current_level": str, "modules": [asdict(ModuleMastery), ...], "trend": [{"date", "level"}, ...]}.
        """
        ...
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

    def prompt_block(self, text: str = "") -> str:
        """Read lines until a blank line, joined with '\\n'. terminal only — WebIOHandler
        already gets a full multi-line textarea value in one send_input() call."""
        if text:
            print(text)
        lines: list[str] = []
        while True:
            line = input()
            if line == "":
                break
            lines.append(line)
        return "\n".join(lines)

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

    def render_exercises(self, data: dict) -> None:
        groups = data.get("groups", [])
        if not groups:
            return
        lines = []
        counter = 0
        for group in groups:
            if group.get("instruction"):
                lines.append(f"-- {group['instruction']} --")
            for ex in group["exercises"]:
                counter += 1
                lines.append(f"{counter}. {ex['prompt']}")
        self.output("\n" + "\n".join(lines))

    def render_results(self, data: dict) -> None:
        items = data.get("items", [])
        score = data.get("score", 0.0)
        self.output(
            f"\n=================================================="
            f"\n                 RESULTS"
            f"\n=================================================="
        )
        for i, item in enumerate(items):
            status = "correct" if item["correct"] else "incorrect"
            self.output(f"{i + 1}. [{status}] {item['prompt']}")
            self.output(f"   Your answer: {item['user_answer']}")
            if not item["correct"]:
                self.output(f"   Correct answer: {item['correct_answer']}")
                self.output(f"   Feedback: {item['feedback']}")
        correct_count = sum(1 for item in items if item["correct"])
        self.output(f"\nScore: {score:.0%} ({correct_count}/{len(items)})")
        self.output("==================================================\n")

    def _render_bar(self, ratio: float, width: int = 20) -> str:
        filled = round(max(0.0, min(ratio, 1.0)) * width)
        return "[" + "█" * filled + "░" * (width - filled) + "]"

    def render_progress(self, data: dict) -> None:
        level = (data.get("current_level") or "").upper()
        self.output(
            "\n=================================================="
            f"\n          LEVEL & PROGRESS ({level})"
            "\n=================================================="
        )
        for m in data.get("modules", []):
            ratio = m.get("mastery_ratio", 0.0)
            bar = self._render_bar(ratio)
            self.output(f"\n{m['module'].capitalize()}: {bar} {ratio:.0%}")
            if m["module"] == "grammar":
                self.output(f"  Topics mastered: {m.get('topics_mastered', 0)}/{m.get('topics_total', 0)}")
            if m["module"] == "writing":
                self.output(
                    f"  Texts written: {m.get('texts_written', 0)}  "
                    f"Words written: {m.get('total_words', 0)} total, "
                    f"{m.get('words_at_current_level', 0)} at current level"
                )
            if m.get("strong_tags"):
                self.output(f"  Strong: {', '.join(m['strong_tags'])}")
            if m.get("weak_tags"):
                self.output(f"  Weak: {', '.join(m['weak_tags'])}")

        trend = data.get("trend", [])
        if trend:
            sparkline = " -> ".join(t["level"].upper() for t in trend[-5:])
            self.output(f"\nRecent text-level trend: {sparkline}")

        self.output("\n==================================================")


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

    def prompt_block(self, text: str = "") -> str:
        """Web client already posts a full multi-line textarea value in one send_input() call."""
        return self.prompt(text)

    def send_input(self, text: str) -> None:
        self._in_q.put(text)

    def render_evaluation(self, data: dict) -> None:
        self._out_q.put({"type": "data", "payload": {"event": "evaluation_complete", **data}})

    def render_exercises(self, data: dict) -> None:
        self._out_q.put({"type": "data", "payload": {"event": "exercises_ready", **data}})

    def render_results(self, data: dict) -> None:
        self._out_q.put({"type": "data", "payload": {"event": "grammar_results_complete", **data}})

    def render_progress(self, data: dict) -> None:
        self._out_q.put({"type": "data", "payload": {"event": "progress_ready", **data}})

    def start_timer(self, label: str = "Writing") -> None:
        pass  # web UI manages its own timer in JS

    def stop_timer(self) -> None:
        pass

    def end(self) -> None:
        self._out_q.put({"type": "done", "text": ""})

    def get_event(self, timeout: float = 30.0) -> dict:
        """Raises queue.Empty on timeout."""
        return self._out_q.get(timeout=timeout)
