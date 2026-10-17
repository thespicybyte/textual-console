"""Write text and a table to a ConsoleOutput. Select with the mouse and copy."""

from rich.table import Table
from rich.text import Text
from textual.app import App, ComposeResult

from textual_console import ConsoleOutput


class BasicApp(App[None]):
    """Show colored text and a table. Select with the mouse, then press ctrl+c."""

    def compose(self) -> ComposeResult:
        """Create the output."""
        yield ConsoleOutput(id="output")

    def on_mount(self) -> None:
        """Write the content."""
        output = self.query_one(ConsoleOutput)
        output.write(Text("Hello, brave new world", style="bold cyan"))
        table = Table("Name", "Value")
        table.add_row("alpha", "1")
        table.add_row("beta", "2")
        output.write(table)
        output.write("Drag, double-click or triple-click. Press ctrl+c to copy.")


if __name__ == "__main__":
    BasicApp().run()
