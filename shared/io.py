from typing import Protocol


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
