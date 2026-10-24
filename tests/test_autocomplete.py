from __future__ import annotations

import inspect
import logging
import shlex
from collections.abc import Callable, Iterator, Sequence

import pytest
from textual.app import App, ComposeResult
from textual.pilot import Pilot
from textual.widgets import Button
from textual_autocomplete import AutoComplete, DropdownItem

from textual_console import (
    CandidateSource,
    CommandAutoComplete,
    CommandHistory,
    CommandItem,
    CompletionHint,
    ConsoleInput,
)

SnapCompare = Callable[..., bool]
FILES = ["readme.md", "notes.txt", "my file.txt"]
COMMANDS = ["hello", "help", "exit"]


class CompleteApp(App[None]):
    def __init__(
        self,
        candidates: Sequence[str | DropdownItem],
        history: list[str] | None = None,
        tab_moves_focus: bool = False,
        read_only: bool = False,
    ) -> None:
        super().__init__()
        self.candidates = candidates
        self.read_only = read_only
        self.tab_moves_focus = tab_moves_focus
        self.entries = history or []
        self.lines: list[str] = []

    def compose(self) -> ComposeResult:
        yield ConsoleInput(
            id="prompt",
            history=CommandHistory(self.entries),
            tab_moves_focus=self.tab_moves_focus,
            read_only=self.read_only,
        )
        if self.tab_moves_focus:
            yield Button("other")
        yield CommandAutoComplete("#prompt", lambda line: self.candidates)

    def on_console_input_submitted(self, message: ConsoleInput.Submitted) -> None:
        self.lines.append(message.value)


def option_texts(app: App[None]) -> list[str]:
    options = app.query_one(AutoComplete).option_list.options
    return [o.prompt.plain for o in options]  # type: ignore[union-attr]


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


@pytest.mark.parametrize(
    "candidates",
    [["pwd", "pwdx", "ps", "cd"], ["pwd", "pwait-dump", "ps"]],
)
async def test_enter_submits_when_word_equals_highlighted_option(
    candidates: list[str],
) -> None:
    app = CompleteApp(candidates)
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        await pilot.press("p", "w", "d")
        await pilot.pause()
        assert dropdown_open(app)
        assert app.query_one(AutoComplete).option_list.highlighted == 0
        await pilot.press("enter")
        assert app.lines == ["pwd"]
        assert prompt.value == ""
        assert not dropdown_open(app)


async def test_enter_accepts_other_highlighted_option() -> None:
    app = CompleteApp(["pwd", "pwdx"])
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        await pilot.press("p", "w", "d", "down", "enter")
        assert prompt.value == "pwdx "
        assert app.lines == []


async def test_enter_submits_after_moving_back_to_the_exact_option() -> None:
    app = CompleteApp(["pwd", "pwdx"])
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        await pilot.press("p", "w", "d", "down", "up", "enter")
        assert app.lines == ["pwd"]


async def test_tab_still_accepts_exact_match() -> None:
    app = CompleteApp(["pwd", "pwdx"])
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        await pilot.press("p", "w", "d", "tab")
        assert prompt.value == "pwd "
        assert app.lines == []


async def test_enter_accepts_when_only_the_case_differs() -> None:
    app = CompleteApp(["PWD", "pwd2"])
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        await pilot.press("p", "w", "d", "enter")
        assert prompt.value == "PWD "
        assert app.lines == []


async def test_enter_submits_exact_match_in_dropdown_opened_with_tab() -> None:
    app = CompleteApp(["pwd", "pwdx"])
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        await pilot.press("p", "w", "d", "escape")
        assert not dropdown_open(app)
        await pilot.press("tab")
        assert dropdown_open(app)
        await pilot.press("enter")
        assert app.lines == ["pwd"]


async def test_enter_submits_exact_match_after_an_earlier_word() -> None:
    app = CompleteApp(["pwd", "pwdx"])
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        await pilot.press(*"sudo pwd")
        await pilot.pause()
        assert dropdown_open(app)
        await pilot.press("enter")
        assert app.lines == ["sudo pwd"]


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
        prompt.cursor_position = 2  # inside the word "open"
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
    for name in (
        "target",
        "_listen_to_messages",
        "_complete",
        "_get_target_state",
        "_align_to_target",
        "_rebuild_options",
        "_handle_target_update",
    ):
        base = inspect.getattr_static(AutoComplete, name)
        ours = inspect.getattr_static(CommandAutoComplete, name)
        if isinstance(base, property):
            assert isinstance(ours, property), name
            base, ours = base.fget, ours.fget
        assert callable(base) and callable(ours), name
        base_params = list(inspect.signature(base).parameters)
        assert base_params == list(inspect.signature(ours).parameters), name
    assert list(inspect.signature(AutoComplete._handle_target_update).parameters) == [
        "self"
    ]
    assert list(inspect.signature(AutoComplete._rebuild_options).parameters) == [
        "self",
        "target_state",
        "search_string",
    ]
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


async def test_down_leaves_a_line_whose_end_has_candidates() -> None:
    app = CompleteApp(["return", "relative"])
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        prompt.value = "re\nlonger"
        await pilot.press("up")
        assert prompt.cursor_location == (0, 2)
        await pilot.pause()
        assert app.query_one(AutoComplete).option_list.option_count
        await pilot.press("down")
        assert prompt.cursor_location == (1, 2)
        assert not app.query_one(AutoComplete).display


async def test_escape_then_down_walks_history_without_dropdown() -> None:
    app = CompleteApp(COMMANDS, history=["old"])
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        await pilot.press("h", "e")
        await pilot.pause()
        assert dropdown_open(app)
        await pilot.press("escape", "down")
        await pilot.pause()
        assert prompt.value == "he"
        assert not app.query_one(AutoComplete).display


async def test_tab_after_space_opens_dropdown() -> None:
    app = CompleteApp(["read", "write"])
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        prompt.value = "open --mode "
        await pilot.pause()
        assert not dropdown_open(app)
        await pilot.press("tab")
        assert dropdown_open(app)
        assert option_texts(app) == ["read", "write"]
        assert prompt.value == "open --mode "
        await pilot.press("down", "tab")
        assert prompt.value == "open --mode write "
        assert app.focused is prompt


async def test_tab_on_a_word_opens_dropdown_after_escape() -> None:
    app = CompleteApp(COMMANDS)
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        await pilot.press("h", "e", "escape")
        assert not dropdown_open(app)
        await pilot.press("tab")
        assert dropdown_open(app)
        assert option_texts(app) == ["hello", "help"]


async def test_tab_with_one_candidate_applies_it() -> None:
    app = CompleteApp(["only"])
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        prompt.value = "go "
        await pilot.pause()
        await pilot.press("tab")
        assert prompt.value == "go only "
        assert not dropdown_open(app)
        assert app.focused is prompt


async def test_tab_ignores_read_only_input() -> None:
    app = CompleteApp(["only"], read_only=True)
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        prompt.load_text("go ")
        await pilot.press("tab")
        assert prompt.value == "go "
        assert not dropdown_open(app)


async def test_tab_with_no_candidates_falls_through() -> None:
    app = CompleteApp([])
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        prompt.value = "go "
        await pilot.pause()
        await pilot.press("tab")
        assert not dropdown_open(app)
        assert app.focused is prompt
    app = CompleteApp([], tab_moves_focus=True)
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        await pilot.press("tab")
        assert app.focused is not prompt


async def test_tab_with_candidates_keeps_focus_when_tab_moves_focus() -> None:
    app = CompleteApp(["a", "b"], tab_moves_focus=True)
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        await pilot.press("tab")
        assert dropdown_open(app)
        assert app.focused is prompt


@pytest.mark.parametrize("cursor", [1, 3])
async def test_tab_inside_a_word_does_not_open(cursor: int) -> None:
    app = CompleteApp(["a", "b"])
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        prompt.value = "go x"
        prompt.cursor_position = cursor
        await pilot.pause()
        await pilot.press("tab")
        assert not dropdown_open(app)
        assert prompt.value == "go x"


async def _mid_line(
    pilot: Pilot[None], value: str, cursor: int, key: str | None = "tab"
) -> ConsoleInput:
    prompt = pilot.app.query_one(ConsoleInput)
    prompt.focus()
    prompt.value = value
    prompt.cursor_position = cursor
    await pilot.pause()
    if key == "tab" and dropdown_open(pilot.app):
        await pilot.press("escape")  # Tab then opens it, as the user asks
    if key:
        await pilot.press(key)
        await pilot.pause()
    return prompt


async def test_tab_mid_line_completes_word_and_keeps_rest() -> None:
    app = CompleteApp(["--path"])
    async with app.run_test() as pilot:
        prompt = await _mid_line(pilot, "upload --pa foobar", 11)
        assert prompt.value == "upload --path foobar"
        assert prompt.cursor_location == (0, 13)
        assert not dropdown_open(app)


async def test_tab_mid_line_with_several_candidates_opens_dropdown() -> None:
    app = CompleteApp(["--path", "--pattern"])
    async with app.run_test() as pilot:
        prompt = await _mid_line(pilot, "upload --pa foobar", 11)
        assert dropdown_open(app)
        assert len(option_texts(app)) == 2
        assert prompt.value == "upload --pa foobar"
        await pilot.press("down", "tab")
        assert prompt.value == "upload --pattern foobar"


async def test_tab_mid_line_with_no_candidates_falls_through() -> None:
    app = CompleteApp([], tab_moves_focus=True)
    async with app.run_test() as pilot:
        prompt = await _mid_line(pilot, "upload --pa foobar", 11)
        assert app.focused is not prompt
        assert prompt.value == "upload --pa foobar"


async def test_source_gets_the_line_up_to_the_cursor() -> None:
    seen: list[str] = []

    def source(line: str) -> list[str]:
        seen.append(line)
        return ["--path", "--pattern"]

    app = SourceApp(source)
    async with app.run_test() as pilot:
        await _mid_line(pilot, "upload --pa foobar", 11)
        assert seen[-1] == "upload --pa"


async def test_typing_mid_line_suggests_and_enter_accepts() -> None:
    app = CompleteApp(["--path", "--pattern"])
    async with app.run_test() as pilot:
        prompt = await _mid_line(pilot, "upload --p foobar", 10, key="a")
        assert dropdown_open(app)
        await pilot.press("enter")
        assert prompt.value == "upload --path foobar"
        assert app.lines == []


async def test_enter_submits_exact_match_mid_line() -> None:
    app = CompleteApp(["--path", "--pathx"])
    async with app.run_test() as pilot:
        await _mid_line(pilot, "upload --path foobar", 13)
        assert dropdown_open(app)
        await pilot.press("enter")
        assert app.lines == ["upload --path foobar"]


async def test_quoting_mid_line() -> None:
    app = CompleteApp(FILES)
    async with app.run_test() as pilot:
        prompt = await _mid_line(pilot, "open my x", 7)
        assert prompt.value == "open 'my file.txt' x"
    app = CompleteApp(FILES)
    async with app.run_test() as pilot:
        prompt = await _mid_line(pilot, 'open "my file.txt" re x', 21)
        assert prompt.value == 'open "my file.txt" readme.md x'


async def test_tab_on_empty_word_mid_line_lists_all_candidates() -> None:
    app = CompleteApp(["--path", "--port"])
    async with app.run_test() as pilot:
        prompt = await _mid_line(pilot, "upload  foobar", 7)
        assert dropdown_open(app)
        assert option_texts(app) == ["--path", "--port"]
        await pilot.press("tab")
        assert prompt.value == "upload --path foobar"


async def test_cursor_move_does_not_open_a_closed_dropdown() -> None:
    app = CompleteApp(["--path", "--pattern"])
    async with app.run_test() as pilot:
        prompt = await _mid_line(pilot, "upload --pa", 11)
        await pilot.press("escape")
        prompt.cursor_position = 4
        await pilot.pause()
        prompt.cursor_position = 11
        await pilot.pause()
        assert not dropdown_open(app)


async def test_guards_apply_before_the_cursor() -> None:
    app = CompleteApp(FILES, tab_moves_focus=True)
    async with app.run_test() as pilot:
        for value, cursor in [('open "x" y', 8), ("open  y", 5)]:
            await _mid_line(pilot, value, cursor, key=None)
            assert not dropdown_open(app), value
        prompt = await _mid_line(pilot, 'open "my fi" x', 11)
        assert not dropdown_open(app)
        assert app.focused is not prompt


async def test_recalled_value_stays_closed_mid_line() -> None:
    app = CompleteApp(["hello"], history=["he x"])
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        await pilot.press("up")
        prompt.cursor_position = 2
        await pilot.pause()
        assert prompt.value == "he x"
        assert not dropdown_open(app)


async def test_typing_after_tab_open_uses_automatic_rules() -> None:
    app = CompleteApp(["read", "write"])
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        prompt.value = "go "
        await pilot.pause()
        await pilot.press("tab")
        assert dropdown_open(app)
        await pilot.press("space")
        await pilot.pause()
        assert not dropdown_open(app)


async def test_command_item_shows_help_and_applies_value_only() -> None:
    items = [CommandItem("hello", "Say hello"), CommandItem("help", "Show help")]
    app = CompleteApp(items)
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        assert items[0].value == "hello"
        await pilot.press("h", "e", "l", "l")
        await pilot.pause()
        assert option_texts(app) == ["hello  Say hello"]
        await pilot.press("tab")
        assert prompt.value == "hello "


async def test_command_item_help_survives_filtering_and_prefix() -> None:
    items = [CommandItem("hello", "Say hello", prefix=">"), CommandItem("exit", "Quit")]
    app = CompleteApp(items)
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        await pilot.press("e", "x")
        await pilot.pause()
        assert option_texts(app) == ["exit  Quit"]
    app = CompleteApp(items)
    async with app.run_test() as pilot:
        app.query_one(ConsoleInput).focus()
        await pilot.press("h", "e")
        await pilot.pause()
        assert option_texts(app) == [">hello  Say hello"]


async def test_hint_is_first_and_never_applied() -> None:
    hint = CompletionHint("MODE: open mode")
    assert hint.value == "MODE: open mode"
    app = CompleteApp([CommandItem("r"), hint, CommandItem("w")])
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        prompt.value = "open "
        await pilot.pause()
        await pilot.press("tab")
        option_list = app.query_one(AutoComplete).option_list
        assert option_texts(app) == ["MODE: open mode", "r", "w"]
        assert option_list.highlighted == 1
        await pilot.press("up")
        assert option_list.highlighted == 2
        await pilot.press("down")
        assert option_list.highlighted == 1
        await pilot.press("enter")
        assert prompt.value == "open r "
        assert app.lines == []


async def test_hint_is_not_filtered_by_the_search() -> None:
    app = CompleteApp([CompletionHint("NAME: a name"), "alpha", "beta"])
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        await pilot.press("a", "l")
        await pilot.pause()
        assert option_texts(app) == ["NAME: a name", "alpha"]
        assert app.query_one(AutoComplete).option_list.highlighted == 1


async def test_hint_only_dropdown_enter_submits_and_tab_does_nothing() -> None:
    app = CompleteApp([CompletionHint("FILE: the file")], tab_moves_focus=True)
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        prompt.value = "open "
        await pilot.pause()
        assert not dropdown_open(app)
        await pilot.press("tab")
        assert app.query_one(AutoComplete).display
        assert option_texts(app) == ["FILE: the file"]
        await pilot.press("tab")
        assert prompt.value == "open "
        assert app.focused is prompt
        assert app.query_one(AutoComplete).display
        await pilot.press("enter")
        assert app.lines == ["open "]
        assert not app.query_one(AutoComplete).display


async def test_hint_is_not_shown_while_typing_without_candidates() -> None:
    app = CompleteApp([CompletionHint("FILE: the file")])
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        await pilot.press("o", "p")
        await pilot.pause()
        assert not app.query_one(AutoComplete).display


async def _open_dropdown_with_help(pilot: Pilot[None]) -> None:
    prompt = pilot.app.query_one(ConsoleInput)
    prompt.focus()
    prompt.value = "open "
    await pilot.pause()
    await pilot.press("tab")
    await pilot.pause()


def _help_app() -> CompleteApp:
    return CompleteApp(
        [
            CompletionHint("MODE: how to open"),
            CommandItem("read", "Open read-only"),
            CommandItem("write", "Open for writing"),
        ]
    )


def test_dropdown_help_and_hint_dark(snap_compare: SnapCompare) -> None:
    app = _help_app()
    app.theme = "textual-dark"
    assert snap_compare(
        app, run_before=_open_dropdown_with_help, terminal_size=(40, 10)
    )


def test_dropdown_help_and_hint_light(snap_compare: SnapCompare) -> None:
    app = _help_app()
    app.theme = "textual-light"
    assert snap_compare(
        app, run_before=_open_dropdown_with_help, terminal_size=(40, 10)
    )


async def test_two_hints_first_highlight_is_a_candidate() -> None:
    app = CompleteApp(
        [CompletionHint("A: one"), CompletionHint("B: two"), "x", "y"],
    )
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        prompt.value = "go "
        await pilot.pause()
        await pilot.press("tab")
        option_list = app.query_one(AutoComplete).option_list
        assert option_list.highlighted == 2
        await pilot.press("up")
        assert option_list.highlighted == 3
        await pilot.press("down")
        assert option_list.highlighted == 2
        await pilot.press("enter")
        assert prompt.value == "go x "
        assert app.lines == []


async def test_disabled_candidate_is_not_selectable() -> None:
    app = CompleteApp([DropdownItem("off", disabled=True)])
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        prompt.value = "go "
        await pilot.pause()
        await pilot.press("tab")
        assert prompt.value == "go "
    app = CompleteApp([DropdownItem("off", disabled=True), "on", "one"])
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        prompt.value = "go "
        await pilot.pause()
        await pilot.press("tab")
        assert app.query_one(AutoComplete).option_list.highlighted == 1
        await pilot.press("enter")
        assert prompt.value == "go on "


async def test_help_starts_in_one_column() -> None:
    app = CompleteApp(
        [CommandItem("--mode", "Mode"), CommandItem("-v", "Verbose"), "plain"]
    )
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        prompt.value = "go "
        await pilot.pause()
        await pilot.press("tab")
        texts = option_texts(app)
        assert texts[0].index("Mode") == texts[1].index("Verbose") == len("--mode") + 2
        await pilot.press("down", "tab")
        assert prompt.value == "go -v "


async def test_escape_on_hint_only_dropdown_hides_it() -> None:
    app = CompleteApp([CompletionHint("FILE: the file")], tab_moves_focus=True)
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        prompt.value = "open "
        await pilot.pause()
        await pilot.press("tab")
        assert app.query_one(AutoComplete).display
        await pilot.press("escape")
        assert not app.query_one(AutoComplete).display
        assert prompt.value == "open "
        assert app.focused is prompt


async def test_tab_with_unclosed_quote_does_not_open() -> None:
    app = CompleteApp(["a", "b"], tab_moves_focus=True)
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        prompt.value = 'go "x'
        await pilot.pause()
        await pilot.press("tab")
        assert not dropdown_open(app)
        assert app.focused is not prompt


class SourceApp(App[None]):
    def __init__(self, source: CandidateSource) -> None:
        super().__init__()
        self.source = source

    def compose(self) -> ComposeResult:
        yield ConsoleInput(id="prompt", history=CommandHistory([]))
        yield CommandAutoComplete("#prompt", self.source)


def first_word_source(line: str) -> list[str]:
    return COMMANDS if shlex.split(line)[0] else []


async def test_tab_on_empty_line_lists_all_candidates() -> None:
    app = SourceApp(lambda line: COMMANDS)
    async with app.run_test() as pilot:
        app.query_one(ConsoleInput).focus()
        await pilot.press("tab")
        await pilot.pause()
        assert dropdown_open(app)
        assert option_texts(app) == COMMANDS


@pytest.mark.parametrize(
    ("keys", "error"),
    [
        ([], "IndexError"),
        (["space"], "IndexError"),
        (["l", "s", "space", "backslash"], "ValueError"),
    ],
    ids=["empty", "space", "trailing-backslash"],
)
async def test_failing_source_on_tab_does_not_crash(
    keys: list[str], error: str, caplog: pytest.LogCaptureFixture
) -> None:
    app = SourceApp(first_word_source)
    with caplog.at_level(logging.ERROR, logger="textual_console._autocomplete"):
        async with app.run_test() as pilot:
            prompt = app.query_one(ConsoleInput)
            prompt.focus()
            await pilot.press(*keys)
            before = prompt.value
            await pilot.press("tab")
            await pilot.pause()
            assert app.is_running
            assert not dropdown_open(app)
            assert prompt.value == before
    assert "candidate source" in caplog.text
    assert error in caplog.text


async def test_failing_source_while_typing_does_not_crash(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def broken(line: str) -> list[str]:
        raise RuntimeError("boom")

    app = SourceApp(broken)
    with caplog.at_level(logging.ERROR, logger="textual_console._autocomplete"):
        async with app.run_test() as pilot:
            prompt = app.query_one(ConsoleInput)
            prompt.focus()
            await pilot.press("h", "e")
            await pilot.pause()
            assert app.is_running
            assert not dropdown_open(app)
            assert prompt.value == "he"
    assert "boom" in caplog.text


async def test_failing_generator_source_is_caught(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def broken(line: str) -> Iterator[str]:
        yield "hello"
        raise RuntimeError("boom")

    app = SourceApp(broken)
    with caplog.at_level(logging.ERROR, logger="textual_console._autocomplete"):
        async with app.run_test() as pilot:
            app.query_one(ConsoleInput).focus()
            await pilot.press("tab")
            await pilot.pause()
            assert app.is_running
            assert not dropdown_open(app)
    assert "boom" in caplog.text


async def test_source_recovers_after_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def source(line: str) -> list[str]:
        if not line:
            raise RuntimeError("boom")
        return COMMANDS

    app = SourceApp(source)
    with caplog.at_level(logging.ERROR, logger="textual_console._autocomplete"):
        async with app.run_test() as pilot:
            app.query_one(ConsoleInput).focus()
            await pilot.press("tab")
            await pilot.pause()
            assert not dropdown_open(app)
            await pilot.press("h")
            await pilot.pause()
            assert dropdown_open(app)
    assert "boom" in caplog.text


class PlaceApp(App[None]):
    """An input docked at the bottom, or at the top with a margin, to test placement."""

    def __init__(
        self, candidates: Sequence[str], css: str = "", margin_top: int | None = None
    ) -> None:
        super().__init__()
        self.candidates = candidates
        self.css = css
        self.margin_top = margin_top

    def compose(self) -> ComposeResult:
        yield ConsoleInput(id="prompt")
        yield CommandAutoComplete("#prompt", lambda line: self.candidates)

    def on_mount(self) -> None:
        dock = "bottom" if self.margin_top is None else "top"
        margin = self.margin_top or 0
        self.stylesheet.add_source(
            f"#prompt {{ dock: {dock}; margin-top: {margin}; }}" + self.css
        )
        self.stylesheet.reparse()
        self.stylesheet.update(self)


async def type_text(app: App[None], pilot: Pilot[None], text: str) -> None:
    app.query_one(ConsoleInput).focus()
    await pilot.press(*text)
    await pilot.pause()


async def test_option_text_starts_under_the_word() -> None:
    app = CompleteApp(COMMANDS)
    async with app.run_test() as pilot:
        await type_text(app, pilot, "he")
        prompt = app.query_one(ConsoleInput)
        content = app.query_one(AutoComplete).option_list.content_region
        assert content.x == prompt.cursor_screen_offset.x - len("he")
        # In the middle of a line.
        prompt.value = "echo he there"
        prompt.move_cursor((0, 7))
        await pilot.pause()
        content = app.query_one(AutoComplete).option_list.content_region
        assert content.x == prompt.cursor_screen_offset.x - len("he")


async def test_option_text_starts_at_the_cursor_after_a_space() -> None:
    app = CompleteApp(COMMANDS)
    async with app.run_test() as pilot:
        await type_text(app, pilot, "echo ")
        await pilot.press("tab")
        await pilot.pause()
        prompt = app.query_one(ConsoleInput)
        assert dropdown_open(app)
        content = app.query_one(AutoComplete).option_list.content_region
        assert content.x == prompt.cursor_screen_offset.x


async def test_dropdown_stays_above_a_wrapped_word() -> None:
    word = "a" * 24
    app = PlaceApp([word + "b"])
    async with app.run_test(size=(20, 12)) as pilot:
        await type_text(app, pilot, word)
        prompt = app.query_one(ConsoleInput)
        dropdown = app.query_one(CommandAutoComplete)
        assert dropdown_open(app)
        x, y = prompt.cursor_screen_offset
        wrapped = prompt.wrapped_document
        _, word_row = wrapped.location_to_offset((0, 0))
        _, cursor_row = wrapped.location_to_offset((0, len(word)))
        word_top = y - (cursor_row - word_row)
        assert cursor_row > word_row
        assert dropdown.region.bottom <= word_top


async def test_dropdown_keeps_a_word_in_mid_row_visible() -> None:
    text = "echo hello there aaaaaaa"
    app = PlaceApp([text.rsplit(" ", 1)[1] + "b"])
    async with app.run_test(size=(20, 12)) as pilot:
        await type_text(app, pilot, text)
        prompt = app.query_one(ConsoleInput)
        dropdown = app.query_one(CommandAutoComplete)
        assert dropdown_open(app)
        _, y = prompt.cursor_screen_offset
        wrapped = prompt.wrapped_document
        start = len("echo hello there ")
        _, start_row = wrapped.location_to_offset((0, start))
        _, cursor_row = wrapped.location_to_offset((0, len(text)))
        assert dropdown.region.bottom <= y - (cursor_row - start_row)
        cursor_x, _ = wrapped.location_to_offset((0, len(text)))
        start_x, _ = wrapped.location_to_offset((0, start))
        word_x = prompt.cursor_screen_offset.x - (cursor_x - start_x)
        assert dropdown.option_list.content_region.x == word_x


async def test_dropdown_does_not_leave_the_left_edge() -> None:
    app = PlaceApp(COMMANDS, css="#prompt { border: none; padding: 0; }")
    async with app.run_test(size=(40, 12)) as pilot:
        await type_text(app, pilot, "he")
        prompt = app.query_one(ConsoleInput)
        dropdown = app.query_one(CommandAutoComplete)
        assert dropdown.region.x >= 0
        assert dropdown.option_list.content_region.x >= prompt.content_region.x


async def test_dropdown_stays_on_a_narrow_screen() -> None:
    long = "x" + "b" * 41
    app = PlaceApp(["xa", long])
    async with app.run_test(size=(30, 12)) as pilot:
        await type_text(app, pilot, "x")
        dropdown = app.query_one(CommandAutoComplete)
        assert dropdown_open(app)
        assert dropdown.region.width <= 30
        assert dropdown.region.right <= 30
        await pilot.press("a")
        await pilot.pause()
        assert dropdown.region.right <= 30


async def test_dropdown_scrolls_when_it_fits_on_neither_side() -> None:
    candidates = [f"cmd{n:02d}" for n in range(12)]
    app = PlaceApp(candidates, margin_top=4)
    async with app.run_test(size=(40, 13)) as pilot:
        await type_text(app, pilot, "c")
        dropdown = app.query_one(CommandAutoComplete)
        prompt = app.query_one(ConsoleInput)
        _, y = prompt.cursor_screen_offset
        assert dropdown.region.y == y + 1
        assert dropdown.region.bottom <= 13
        option_list = dropdown.option_list
        for _ in range(11):
            await pilot.press("down")
        await pilot.pause()
        assert option_list.highlighted == 11
        assert dropdown.region.contains_region(option_list.content_region)


async def test_dropdown_has_a_round_border_that_css_can_remove() -> None:
    app = CompleteApp(COMMANDS)
    async with app.run_test() as pilot:
        await type_text(app, pilot, "he")
        assert app.query_one(AutoComplete).option_list.styles.border.top[0] == "round"

    class Plain(CompleteApp):
        CSS = "CommandAutoComplete AutoCompleteList { border: none; }"

    app = Plain(COMMANDS)
    async with app.run_test() as pilot:
        await type_text(app, pilot, "he")
        prompt = app.query_one(ConsoleInput)
        option_list = app.query_one(AutoComplete).option_list
        assert option_list.outer_size.height == option_list.option_count
        assert option_list.content_region.x == prompt.cursor_screen_offset.x - 2
