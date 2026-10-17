"""A small REPL: ConsoleOutput, ConsoleInput, argparse completion and ConsoleLog."""

import argparse
import contextlib
import io
import shlex
from pathlib import Path

from rich.text import Text
from textual import on
from textual.app import App, ComposeResult

from textual_console import (
    ArgparseCompleter,
    CommandAutoComplete,
    ConsoleInput,
    ConsoleLog,
    ConsoleOutput,
)

PARSERS = {
    "help": argparse.ArgumentParser(prog="help", description="Show the commands"),
    "echo": argparse.ArgumentParser(prog="echo", description="Write the text"),
    "quit": argparse.ArgumentParser(prog="quit", description="Leave the app"),
}
PARSERS["echo"].add_argument("text", nargs="*", metavar="TEXT", help="the words")


class ReplApp(App[None]):
    """Echo commands into the output, so they also reach the transcript."""

    def __init__(self, log_path: Path | None = None) -> None:
        """Create the app.

        Args:
            log_path: A file for the plain-text transcript, or ``None``.
        """
        super().__init__()
        self._transcript = ConsoleLog(log_path) if log_path is not None else None

    def compose(self) -> ComposeResult:
        """Create the output, the prompt and the autocomplete."""
        yield ConsoleOutput(id="output", max_lines=5000, log=self._transcript)
        yield ConsoleInput(prompt="> ", placeholder="command", id="prompt")
        yield CommandAutoComplete("#prompt", ArgparseCompleter(PARSERS))

    @on(ConsoleInput.Submitted)
    def _run(self, event: ConsoleInput.Submitted) -> None:
        # One submit can hold several lines. Run each non-blank line as a command.
        for line in event.value.splitlines():
            if line.strip():
                self._run_line(line)

    def _run_line(self, line: str) -> None:
        output = self.query_one(ConsoleOutput)
        output.write(Text(f"> {line}", style="bold green"))
        try:
            name, *args = shlex.split(line)
        except ValueError as error:
            output.write(f"Error: {error}")
            return
        parser = PARSERS.get(name)
        if parser is None:
            output.write(f"Unknown command: {name}")
            return
        # parse_args prints for -h and errors, and then raises SystemExit.
        buffer = io.StringIO()
        try:
            with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
                namespace = parser.parse_args(args)
        except SystemExit:
            output.write(buffer.getvalue().rstrip())
            return
        if name == "help":
            output.write("Commands: " + ", ".join(PARSERS))
        elif name == "echo":
            output.write(" ".join(namespace.text))
        elif name == "quit":
            self.exit()

    def on_unmount(self) -> None:
        """Close the transcript."""
        if self._transcript is not None:
            self._transcript.close()


if __name__ == "__main__":
    ReplApp(Path("repl.log")).run()
