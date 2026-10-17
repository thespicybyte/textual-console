"""A small REPL: ConsoleOutput, ConsoleInput, CommandAutoComplete and ConsoleLog."""

from pathlib import Path

from rich.text import Text
from textual import on
from textual.app import App, ComposeResult

from textual_console import (
    CommandAutoComplete,
    ConsoleInput,
    ConsoleLog,
    ConsoleOutput,
)

COMMANDS = ["help", "echo", "quit"]


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
        yield ConsoleInput(placeholder="command", id="prompt")
        yield CommandAutoComplete("#prompt", lambda _line: COMMANDS)

    @on(ConsoleInput.Submitted)
    def _run(self, event: ConsoleInput.Submitted) -> None:
        output = self.query_one(ConsoleOutput)
        output.write(Text(f"> {event.value}", style="bold green"))
        name, _, rest = event.value.strip().partition(" ")
        if name == "help":
            output.write("Commands: " + ", ".join(COMMANDS))
        elif name == "echo":
            output.write(rest)
        elif name == "quit":
            self.exit()
        elif name:
            output.write(f"Unknown command: {name}")

    def on_unmount(self) -> None:
        """Close the transcript."""
        if self._transcript is not None:
            self._transcript.close()


if __name__ == "__main__":
    ReplApp(Path("repl.log")).run()
