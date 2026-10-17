"""Demo app. Run it with ``python -m textual_console``."""

import argparse
import contextlib
import io
import shlex
from collections.abc import Sequence
from pathlib import Path

from rich import box
from rich.table import Table
from rich.text import Text
from textual import on
from textual.app import App, ComposeResult
from textual.widgets import Footer, Static

from textual_console import (
    ArgparseCompleter,
    CommandAutoComplete,
    ConsoleInput,
    ConsoleLog,
    ConsoleOutput,
)

COLORS = ("red", "green", "yellow", "blue", "magenta", "cyan")
"""The colors of the ``colors`` command."""


def _build_parsers() -> dict[str, argparse.ArgumentParser]:
    """Describe the commands of the demo with argparse parsers.

    The same parsers drive the completion and the parsing of a command line.
    """

    def parser(name: str, description: str) -> argparse.ArgumentParser:
        return argparse.ArgumentParser(prog=name, description=description)

    parsers = {
        "help": parser("help", "Show the commands"),
        "colors": parser("colors", "Write text in some colors"),
        "table": parser("table", "Write a Rich table"),
        "ansi": parser("ansi", "Write text with ANSI escape codes"),
        "flood": parser("flood", "Write many lines to check the scrollback"),
        "clear": parser("clear", "Clear the output"),
        "echo": parser("echo", "Write the text to the output"),
        "quit": parser("quit", "Leave the demo"),
    }
    parsers["colors"].add_argument(
        "--only", nargs="+", choices=COLORS, metavar="COLOR", help="show only these"
    )
    parsers["flood"].add_argument(
        "count",
        nargs="?",
        type=int,
        default=200,
        metavar="COUNT",
        help="how many lines",
    )
    parsers["flood"].add_argument(
        "--style",
        choices=("plain", "red", "green"),
        default="plain",
        help="the style of the lines",
    )
    parsers["echo"].add_argument("text", nargs="*", metavar="TEXT", help="the words")
    return parsers


PARSERS = _build_parsers()
"""The parsers of the commands of the demo, by command name."""

COMMANDS = tuple(PARSERS)
"""The commands of the demo."""

HINTS = """\
Try: drag / double / triple-click to select, ctrl+c copy, middle-click paste, Tab complete,
shift+enter newline, Esc Esc clear.
Commands: {commands}; add -h for help."""
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
        yield ConsoleInput(
            prompt="> ", placeholder="type a command, then press enter", id="prompt"
        )
        yield CommandAutoComplete("#prompt", ArgparseCompleter(PARSERS))
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
    def _run_submit(self, event: ConsoleInput.Submitted) -> None:
        # A submit can hold several lines. This app runs each non-blank line as a
        # command: that is the app's choice, ConsoleInput only gives the text.
        for line in event.value.splitlines():
            if line.strip():
                self._run_line(line)

    def _run_line(self, line: str) -> None:
        output = self.query_one(ConsoleOutput)
        # The command is echoed into the output, so it also reaches the transcript.
        output.write(Text(f"> {line}", style="bold green"))
        try:
            words = shlex.split(line)
        except ValueError as error:
            output.write(Text(f"Error: {error}", style="red"))
            return
        name, args = words[0], words[1:]
        parser = PARSERS.get(name)
        if parser is None:
            output.write(Text(f"Unknown command: {name}", style="red"))
            return
        # parse_args prints usage and calls sys.exit for -h and for errors. Catch
        # that, and show the text in the output.
        buffer = io.StringIO()
        try:
            with (
                contextlib.redirect_stdout(buffer),
                contextlib.redirect_stderr(buffer),
            ):
                namespace = parser.parse_args(args)
        except SystemExit as exit_:
            style = "red" if exit_.code else ""
            output.write(Text(buffer.getvalue().rstrip(), style=style))
            return
        self._execute(name, namespace)

    def _execute(self, name: str, args: argparse.Namespace) -> None:
        output = self.query_one(ConsoleOutput)
        if name == "help":
            output.write(f"Commands: {', '.join(COMMANDS)}")
        elif name == "colors":
            for colour in args.only or COLORS:
                output.write(Text(f"{colour} text", style=colour))
        elif name == "table":
            output.write(self._table())
        elif name == "ansi":
            output.write_ansi(
                "\x1b[1;31mbold red\x1b[0m \x1b[4;32munderlined green\x1b[0m"
            )
        elif name == "flood":
            style = "" if args.style == "plain" else args.style
            for number in range(1, args.count + 1):
                output.write(Text(f"line {number}", style=style))
        elif name == "clear":
            output.clear()
        elif name == "echo":
            output.write(" ".join(args.text))
        elif name == "quit":
            self.exit()

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
