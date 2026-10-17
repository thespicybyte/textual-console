from __future__ import annotations

from collections.abc import Callable

from textual.app import App, ComposeResult
from textual.pilot import Pilot

from textual_console import ConsoleInput

SnapCompare = Callable[..., bool]


class PromptSnapshotApp(App[None]):
    def __init__(self, theme: str) -> None:
        super().__init__()
        self.theme = theme

    def compose(self) -> ComposeResult:
        yield ConsoleInput(prompt="py> ", value="first\nsecond line\nthird")


async def _focus(pilot: Pilot[None]) -> None:
    pilot.app.query_one(ConsoleInput).focus()
    await pilot.pause()


def test_prompt_dark(snap_compare: SnapCompare) -> None:
    assert snap_compare(
        PromptSnapshotApp("textual-dark"), run_before=_focus, terminal_size=(40, 8)
    )


def test_prompt_light(snap_compare: SnapCompare) -> None:
    assert snap_compare(
        PromptSnapshotApp("textual-light"), run_before=_focus, terminal_size=(40, 8)
    )
