from typing import Protocol
from queue import Queue, Empty


class IOHandler(Protocol):
    show_cli_hints: bool

    def output(self, text: str = "") -> None: ...
    def prompt(self, text: str = "") -> str: ...


class TerminalIOHandler:
    show_cli_hints = True

    def output(self, text: str = "") -> None:
        print(text)

    def prompt(self, text: str = "") -> str:
        return input(text)


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

    def data(self, payload: dict) -> None:
        self._out_q.put({"type": "data", "payload": payload})

    def end(self) -> None:
        self._out_q.put({"type": "done", "text": ""})

    def get_event(self, timeout: float = 30.0) -> dict:
        """Raises queue.Empty on timeout."""
        return self._out_q.get(timeout=timeout)
