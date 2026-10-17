"""Stream the ANSI output of a subprocess into a ConsoleOutput."""

import asyncio
import sys

from textual.app import App, ComposeResult

from textual_console import ConsoleOutput

DEFAULT_COMMAND = [
    sys.executable,
    "-c",
    "for i in range(5): print(f'\\x1b[3{i + 1}mline {i}\\x1b[0m', flush=True)",
]


class AnsiStreamApp(App[None]):
    """Run a command and write each output line with ``write_ansi``."""

    def __init__(self, command: list[str] | None = None) -> None:
        """Create the app.

        Args:
            command: The command to run. The default prints five colored lines.
        """
        super().__init__()
        self.command = command or DEFAULT_COMMAND

    def compose(self) -> ComposeResult:
        """Create the output."""
        yield ConsoleOutput(id="output", max_lines=10_000)

    async def on_mount(self) -> None:
        """Start the command and stream its output."""
        output = self.query_one(ConsoleOutput)
        process = await asyncio.create_subprocess_exec(
            *self.command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        assert process.stdout is not None
        async for raw in process.stdout:
            output.write_ansi(raw.decode(errors="replace").rstrip("\n"))
        await process.wait()
        output.write(f"[exit {process.returncode}]")


if __name__ == "__main__":
    AnsiStreamApp(sys.argv[1:] or None).run()
