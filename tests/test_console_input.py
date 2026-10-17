from __future__ import annotations

from textual.app import App, ComposeResult
from textual.geometry import Offset
from textual.selection import Selection
from textual.widgets import Button, Input

from textual_console import CommandHistory, ConsoleInput, ConsoleOutput


class InputApp(App[None]):
    def __init__(self, **input_kwargs: object) -> None:
        super().__init__()
        self.input_kwargs = input_kwargs
        self.submitted: list[str] = []

    def compose(self) -> ComposeResult:
        yield ConsoleOutput()
        yield ConsoleInput(id="prompt", **self.input_kwargs)  # type: ignore[arg-type]
        yield Button("other")

    def on_input_submitted(self, message: Input.Submitted) -> None:
        self.submitted.append(message.value)


async def test_up_down_walks_history() -> None:
    app = InputApp(history=CommandHistory(["one", "two"]))
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        await pilot.press("x")
        await pilot.press("up")
        assert prompt.value == "two"
        assert prompt.cursor_position == 3
        assert prompt.recalled_value == "two"
        await pilot.press("up")
        assert prompt.value == "one"
        await pilot.press("up")
        assert prompt.value == "one"
        await pilot.press("down")
        assert prompt.value == "two"
        await pilot.press("down")
        assert prompt.value == "x"


async def test_up_down_with_empty_history() -> None:
    app = InputApp()
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        await pilot.press("a", "up", "down")
        assert prompt.value == "a"
        assert prompt.recalled_value is None


async def test_submit_records_and_clears() -> None:
    app = InputApp()
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        await pilot.press("l", "s", "enter")
        assert app.submitted == ["ls"]
        assert prompt.history.entries == ["ls"]
        assert prompt.value == ""


async def test_submit_keeps_value_without_clear_on_submit() -> None:
    app = InputApp(clear_on_submit=False)
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        await pilot.press("l", "s", "enter")
        assert app.submitted == ["ls"]
        assert prompt.value == "ls"
        assert prompt.history.entries == ["ls"]


async def test_tab_keeps_focus() -> None:
    app = InputApp()
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        await pilot.press("tab")
        assert app.focused is prompt


async def test_tab_moves_focus_when_asked() -> None:
    app = InputApp(tab_moves_focus=True)
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        await pilot.press("tab")
        assert app.focused is app.query_one(Button)


async def test_middle_click_pastes_output_selection() -> None:
    app = InputApp()
    async with app.run_test() as pilot:
        output = app.query_one(ConsoleOutput)
        prompt = app.query_one(ConsoleInput)
        output.write("hello brave world")
        await pilot.pause()
        output.screen.selections = {output: Selection(Offset(6, 0), Offset(11, 0))}
        app.copy_to_clipboard("old")
        await pilot.click(ConsoleInput, button=2)
        assert prompt.value == "brave"


async def test_middle_click_pastes_app_clipboard() -> None:
    app = InputApp()
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        app.copy_to_clipboard("copied")
        await pilot.click(ConsoleInput, button=2)
        assert prompt.value == "copied"


async def test_middle_click_paste_can_be_disabled() -> None:
    app = InputApp(middle_click_paste=False)
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        app.copy_to_clipboard("copied")
        await pilot.click(ConsoleInput, button=2)
        assert prompt.value == ""


async def test_middle_click_pastes_only_first_line() -> None:
    app = InputApp()
    async with app.run_test() as pilot:
        output = app.query_one(ConsoleOutput)
        prompt = app.query_one(ConsoleInput)
        output.write("first line")
        output.write("second line")
        await pilot.pause()
        output.screen.selections = {output: Selection(Offset(6, 0), Offset(6, 1))}
        await pilot.click(ConsoleInput, button=2)
        assert prompt.value == "line"
