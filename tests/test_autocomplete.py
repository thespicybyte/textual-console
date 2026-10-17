from __future__ import annotations

import inspect
from collections.abc import Callable

from textual.app import App, ComposeResult
from textual.pilot import Pilot
from textual_autocomplete import AutoComplete

from textual_console import CommandAutoComplete, CommandHistory, ConsoleInput

SnapCompare = Callable[..., bool]
FILES = ["readme.md", "notes.txt", "my file.txt"]
COMMANDS = ["hello", "help", "exit"]


class CompleteApp(App[None]):
    def __init__(self, candidates: list[str], history: list[str] | None = None) -> None:
        super().__init__()
        self.candidates = candidates
        self.entries = history or []
        self.lines: list[str] = []

    def compose(self) -> ComposeResult:
        yield ConsoleInput(id="prompt", history=CommandHistory(self.entries))
        yield CommandAutoComplete("#prompt", lambda line: self.candidates)

    def on_console_input_submitted(self, message: ConsoleInput.Submitted) -> None:
        self.lines.append(message.value)


def dropdown_open(app: App[None]) -> bool:
    complete = app.query_one(AutoComplete)
    return bool(complete.display and complete.option_list.option_count)


async def test_dropdown_open_up_down_and_tab() -> None:
    app = CompleteApp(COMMANDS)
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        await pilot.press("h", "e")
        await pilot.pause()
        assert dropdown_open(app)
        option_list = app.query_one(AutoComplete).option_list
        assert option_list.highlighted == 0
        await pilot.press("down")
        assert option_list.highlighted == 1
        assert prompt.value == "he"
        await pilot.press("up")
        assert option_list.highlighted == 0
        await pilot.press("tab")
        assert prompt.value == "hello "
        assert app.focused is prompt


async def test_dropdown_open_enter_accepts_without_submit() -> None:
    app = CompleteApp(COMMANDS)
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        await pilot.press("e", "x", "enter")
        assert prompt.value == "exit "
        assert app.lines == []
        await pilot.press("enter")
        assert app.lines == ["exit "]
        assert prompt.command_history.entries == ["exit "]


async def test_dropdown_closed_up_down_walk_history() -> None:
    app = CompleteApp(COMMANDS, history=["echo x", "zzz"])
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        await pilot.press("up")
        await pilot.pause()
        assert prompt.value == "zzz"
        await pilot.press("up")
        await pilot.pause()
        assert prompt.value == "echo x"
        await pilot.press("down", "down")
        await pilot.pause()
        assert prompt.value == ""
        assert not dropdown_open(app)


async def test_no_suggestions_for_recalled_value() -> None:
    app = CompleteApp(COMMANDS, history=["he"])
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        await pilot.press("up")
        await pilot.pause()
        assert prompt.value == "he"
        assert not dropdown_open(app)
        await pilot.press("l")
        await pilot.pause()
        assert prompt.recalled_value is None
        assert dropdown_open(app)


async def test_completion_keeps_quoting() -> None:
    app = CompleteApp(FILES)
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        prompt.value = 'open "my file.txt" re'
        await pilot.pause()
        assert dropdown_open(app)
        await pilot.press("tab")
        assert prompt.value == 'open "my file.txt" readme.md '


async def test_completion_quotes_when_needed() -> None:
    app = CompleteApp(FILES)
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        prompt.value = "open my"
        await pilot.pause()
        await pilot.press("tab")
        assert prompt.value == "open 'my file.txt' "


async def test_no_suggestions_in_odd_states() -> None:
    app = CompleteApp(FILES)
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        for text in ["", "open ", 'open "re', 'open "x"', "open re\\"]:
            prompt.value = text
            await pilot.pause()
            assert not dropdown_open(app), text
        prompt.value = "open re"
        prompt.cursor_position = 2
        await pilot.pause()
        assert not dropdown_open(app)


async def test_completion_on_second_line_changes_only_that_line() -> None:
    seen: list[str] = []

    def candidates(line: str) -> list[str]:
        seen.append(line)
        return FILES

    app = CompleteApp(FILES)
    async with app.run_test() as pilot:
        app.query_one(CommandAutoComplete)._source = candidates
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        prompt.value = "a\nopen re"
        await pilot.pause()
        assert seen[-1] == "open re"
        assert dropdown_open(app)
        await pilot.press("tab")
        assert prompt.value == "a\nopen readme.md "
        assert prompt.cursor_location == (1, len("open readme.md "))


async def test_completion_on_first_line_keeps_later_lines() -> None:
    app = CompleteApp(FILES)
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        prompt.value = "open re\nlater"
        prompt.move_cursor((0, 7))
        await pilot.pause()
        assert dropdown_open(app)
        await pilot.press("enter")
        assert prompt.value == "open readme.md \nlater"
        assert app.lines == []


async def test_recalled_multi_line_value_stays_closed() -> None:
    app = CompleteApp(COMMANDS, history=["x\nhe"])
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        await pilot.press("up")
        await pilot.pause()
        assert prompt.value == "x\nhe"
        assert not dropdown_open(app)


def test_adapter_overrides_match_the_pinned_autocomplete() -> None:
    # CommandAutoComplete overrides private methods of textual-autocomplete,
    # which is pinned to <4.1. If an upgrade changes one, fail here.
    for name in ("target", "_listen_to_messages", "_complete", "_get_target_state"):
        base = inspect.getattr_static(AutoComplete, name)
        ours = inspect.getattr_static(CommandAutoComplete, name)
        if isinstance(base, property):
            assert isinstance(ours, property), name
            base, ours = base.fget, ours.fget
        assert callable(base) and callable(ours), name
        base_params = list(inspect.signature(base).parameters)
        assert base_params == list(inspect.signature(ours).parameters), name
    assert list(inspect.signature(AutoComplete._complete).parameters) == [
        "self",
        "option_index",
    ]
    assert list(inspect.signature(AutoComplete._listen_to_messages).parameters) == [
        "self",
        "event",
    ]


async def _open_dropdown(pilot: Pilot[None]) -> None:
    prompt = pilot.app.query_one(ConsoleInput)
    prompt.focus()
    await pilot.press("h", "e")
    await pilot.pause()


def test_dropdown_snapshot(snap_compare: SnapCompare) -> None:
    assert snap_compare(
        CompleteApp(COMMANDS), run_before=_open_dropdown, terminal_size=(40, 10)
    )
