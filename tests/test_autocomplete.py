from __future__ import annotations

import inspect
from collections.abc import Callable, Sequence

from textual.app import App, ComposeResult
from textual.pilot import Pilot
from textual.widgets import Button
from textual_autocomplete import AutoComplete, DropdownItem

from textual_console import (
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
    ) -> None:
        super().__init__()
        self.candidates = candidates
        self.tab_moves_focus = tab_moves_focus
        self.entries = history or []
        self.lines: list[str] = []

    def compose(self) -> ComposeResult:
        yield ConsoleInput(
            id="prompt",
            history=CommandHistory(self.entries),
            tab_moves_focus=self.tab_moves_focus,
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
    for name in (
        "target",
        "_listen_to_messages",
        "_complete",
        "_get_target_state",
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


async def test_tab_mid_line_does_not_open() -> None:
    app = CompleteApp(["a", "b"])
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        prompt.value = "go x"
        prompt.cursor_position = 1
        await pilot.pause()
        await pilot.press("tab")
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
