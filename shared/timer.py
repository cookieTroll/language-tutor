import sys
import time
import threading


class SessionTimer:
    """Background thread that displays elapsed session time in the terminal title."""

    def __init__(self, label: str = "LanguageTutor"):
        self._label = label
        self._running = False
        self._thread: threading.Thread | None = None
        self._start_time: float | None = None

    def start(self) -> None:
        self._running = True
        self._start_time = time.time()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
        sys.stdout.write(f"\x1b]2;{self._label}\x07")
        sys.stdout.flush()

    def _run(self) -> None:
        while self._running:
            elapsed = time.time() - self._start_time  # type: ignore[operator]
            minutes = int(elapsed // 60)
            seconds = int(elapsed % 60)
            sys.stdout.write(f"\x1b]2;{self._label} [{minutes:02d}:{seconds:02d}]\x07")
            sys.stdout.flush()
            time.sleep(1.0)
