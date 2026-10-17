"""Demo app. Run it with ``python -m textual_console``."""

import argparse
from collections.abc import Sequence
from pathlib import Path

from rich import box
from rich.table import Table
from rich.text import Text
from textual import on
from textual.app import App, ComposeResult
from textual.widgets import Footer, Static

from textual_console import (
    CommandAutoComplete,
    ConsoleInput,
    ConsoleLog,
    ConsoleOutput,
)

COMMANDS = ("help", "colors", "table", "ansi", "flood", "clear", "echo", "quit")
"""The commands of the demo. They are also the autocomplete candidates."""

HINTS = """\
[b]Manual checks[/b]
1. Drag, double-click, triple-click in the output. ctrl+c copies (a notification shows).
2. Select text in the output, then middle-click the prompt: the selection is pasted.
3. With no selection, middle-click the prompt: the last app copy is pasted.
4. Copy text in ANOTHER app, then middle-click the prompt: does the app get
   the click, or does the terminal paste?
5. Copy text in ANOTHER app, then shift+middle-click the prompt: the terminal
   pastes by itself.
6. Paste multi-line text with cmd+v / ctrl+shift+v: only the first line is kept.
Commands: {commands}. Use "flood 500" with --max-lines to check the cap."""
"""The hints that are shown under the output."""


class ConsoleDemo(App[None]):
    """A small REPL that shows all widgets of the package."""

    CSS = """
    ConsoleOutput {
        border: round $primary;
        height: 1fr;
    }
    #hints {
        height: auto;
        padding: 0 1;
        color: $text-muted;
    }
    """

    def __init__(
        self, log_path: Path | None = None, max_lines: int | None = None
    ) -> None:
        """Create the demo.

        Args:
            log_path: A file that receives a plain-text transcript, or ``None``.
            max_lines: The scrollback limit of the output, or ``None``.
        """
        super().__init__()
        self.log_path = log_path
        self.max_lines = max_lines
        self._transcript = ConsoleLog(log_path) if log_path is not None else None

    def compose(self) -> ComposeResult:
        """Create the output, the hints, the prompt and the footer."""
        yield ConsoleOutput(
            id="output",
            max_lines=self.max_lines,
            log=self._transcript,
            markup=False,
        )
        yield Static(HINTS.format(commands=", ".join(COMMANDS)), id="hints")
        yield ConsoleInput(placeholder="type a command, then press enter", id="prompt")
        yield CommandAutoComplete("#prompt", lambda _line: COMMANDS)
        yield Footer()

    def on_mount(self) -> None:
        """Write the welcome text and focus the prompt."""
        output = self.query_one(ConsoleOutput)
        output.write(Text("textual-console demo", style="bold magenta"))
        output.write("Type 'help' to see the commands.")
        if self.log_path is not None:
            output.write(f"Transcript: {self.log_path}")
        if self.max_lines is not None:
            output.write(f"Scrollback is limited to {self.max_lines} lines.")
        self.query_one(ConsoleInput).focus()

    def on_unmount(self) -> None:
        """Close the transcript."""
        if self._transcript is not None:
            self._transcript.close()

    def copy_to_clipboard(self, text: str) -> None:
        """Copy the text, and show a notification.

        ``ctrl+c`` copies through the screen, which does not post
        ``SelectionCopied``, so the notification is made here.

        Args:
            text: The text to copy.
        """
        super().copy_to_clipboard(text)
        self.notify(f"Copied {len(text)} characters")

    @on(ConsoleOutput.LogFailed)
    def _notify_log_failure(self, event: ConsoleOutput.LogFailed) -> None:
        self.notify(f"Transcript failed: {event.error}", severity="error")

    @on(ConsoleInput.Submitted)
    def _run_command(self, event: ConsoleInput.Submitted) -> None:
        output = self.query_one(ConsoleOutput)
        line = event.value
        # The command is echoed into the output, so it also reaches the transcript.
        output.write(Text(f"> {line}", style="bold green"))
        name, _, rest = line.strip().partition(" ")
        if name == "help":
            output.write(f"Commands: {', '.join(COMMANDS)}")
        elif name == "colors":
            for colour in ("red", "green", "yellow", "blue", "magenta", "cyan"):
                output.write(Text(f"{colour} text", style=colour))
        elif name == "table":
            output.write(self._table())
        elif name == "ansi":
            output.write_ansi(
                "\x1b[1;31mbold red\x1b[0m \x1b[4;32munderlined green\x1b[0m"
            )
        elif name == "flood":
            count = int(rest) if rest.isdigit() else 200
            for number in range(1, count + 1):
                output.write(f"line {number}")
        elif name == "clear":
            output.clear()
        elif name == "echo":
            output.write(rest)
        elif name == "quit":
            self.exit()
        elif name:
            output.write(Text(f"Unknown command: {name}", style="red"))

    @staticmethod
    def _table() -> Table:
        table = Table(title="Example", box=box.SIMPLE_HEAVY)
        table.add_column("Name", style="cyan")
        table.add_column("Value", justify="right", style="yellow")
        for name, value in (("alpha", 1), ("beta", 22), ("gamma", 333)):
            table.add_row(name, str(value))
        return table


def main(argv: Sequence[str] | None = None) -> None:
    """Run the demo.

    Args:
        argv: The command-line arguments. The default is ``sys.argv[1:]``.
    """
    parser = argparse.ArgumentParser(
        prog="python -m textual_console", description="Demo of textual-console."
    )
    parser.add_argument(
        "--log", type=Path, metavar="PATH", help="write a plain-text transcript"
    )
    parser.add_argument(
        "--max-lines",
        type=int,
        metavar="N",
        help="limit the scrollback of the output to N lines",
    )
    args = parser.parse_args(argv)
    if args.max_lines is not None and args.max_lines < 1:
        parser.error("--max-lines must be at least 1")
    ConsoleDemo(log_path=args.log, max_lines=args.max_lines).run()


if __name__ == "__main__":
    main()
