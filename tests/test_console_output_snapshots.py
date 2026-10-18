from __future__ import annotations

from collections.abc import Callable

from rich.table import Table
from rich.text import Text
from textual.app import App, ComposeResult
from textual.geometry import Offset
from textual.pilot import Pilot
from textual.selection import Selection

from textual_console import ConsoleOutput

SnapCompare = Callable[..., bool]


class SnapshotApp(App[None]):
    def __init__(self, theme: str) -> None:
        super().__init__()
        self.theme = theme

    def compose(self) -> ComposeResult:
        yield ConsoleOutput()

    def on_mount(self) -> None:
        output = self.query_one(ConsoleOutput)
        output.write(Text("hello brave world", style="bold green"))
        table = Table("name", "value", style="cyan")
        table.add_row("alpha", "1")
        table.add_row("beta", "漢字 2")
        output.write(table)
        output.write_ansi("\x1b[31mred\x1b[0m and \x1b[44mblue\x1b[0m text")
        output.write("漢字漢字 wide and 😀 emoji")


async def _select(pilot: Pilot[None]) -> None:
    output = pilot.app.query_one(ConsoleOutput)
    await pilot.pause()
    output.screen.selections = {output: Selection(Offset(6, 0), Offset(4, 6))}
    await pilot.pause()


async def _select_wide(pilot: Pilot[None]) -> None:
    output = pilot.app.query_one(ConsoleOutput)
    await pilot.pause()
    last = len(output.lines) - 1
    output.select_word_at(Offset(1, last))
    await pilot.pause()


async def _select_extended(pilot: Pilot[None]) -> None:
    output = pilot.app.query_one(ConsoleOutput)
    for i in range(40):
        output.write(f"scrolled line {i}")
    await pilot.pause()
    output.scroll_to(y=0, animate=False)
    await pilot.pause()
    await pilot.mouse_down(ConsoleOutput, offset=(2, 1))
    await pilot.hover(ConsoleOutput, offset=(6, 2))
    await pilot.mouse_up(ConsoleOutput, offset=(6, 2))
    output.scroll_to(y=30, animate=False)
    await pilot.pause()
    await pilot.click(ConsoleOutput, offset=(5, 4), shift=True)
    await pilot.pause()


def test_highlight_dark(snap_compare: SnapCompare) -> None:
    assert snap_compare(
        SnapshotApp("textual-dark"), run_before=_select, terminal_size=(50, 14)
    )


def test_highlight_light(snap_compare: SnapCompare) -> None:
    assert snap_compare(
        SnapshotApp("textual-light"), run_before=_select, terminal_size=(50, 14)
    )


def test_highlight_wide_characters(snap_compare: SnapCompare) -> None:
    assert snap_compare(
        SnapshotApp("textual-dark"), run_before=_select_wide, terminal_size=(50, 14)
    )


def test_highlight_shift_extended(snap_compare: SnapCompare) -> None:
    assert snap_compare(
        SnapshotApp("textual-dark"), run_before=_select_extended, terminal_size=(50, 14)
    )
