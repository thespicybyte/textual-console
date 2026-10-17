from __future__ import annotations

import pytest
from textual import events
from textual.app import App, ComposeResult
from textual.geometry import Offset
from textual.selection import Selection
from textual.suggester import SuggestFromList, SuggestionReady
from textual.widgets import Button

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

    def on_console_input_submitted(self, message: ConsoleInput.Submitted) -> None:
        self.submitted.append(message.value)


class CssInputApp(InputApp):
    CSS = "ConsoleInput { max-height: 5; }"


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
        assert prompt.command_history.entries == ["ls"]
        assert prompt.value == ""


async def test_submit_keeps_value_without_clear_on_submit() -> None:
    app = InputApp(clear_on_submit=False)
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        await pilot.press("l", "s", "enter")
        assert app.submitted == ["ls"]
        assert prompt.value == "ls"
        assert prompt.command_history.entries == ["ls"]


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


async def test_middle_click_pastes_all_lines() -> None:
    app = InputApp()
    async with app.run_test() as pilot:
        output = app.query_one(ConsoleOutput)
        prompt = app.query_one(ConsoleInput)
        output.write("first line")
        output.write("second line")
        await pilot.pause()
        output.screen.selections = {output: Selection(Offset(6, 0), Offset(6, 1))}
        await pilot.click(ConsoleInput, button=2)
        assert prompt.value == "line\nsecond"
        assert app.submitted == []


async def test_ctrl_v_with_multi_line_clipboard() -> None:
    # Input.action_paste put the raw newline in a one-line widget, and the
    # raw line feed drew stacked boxes in the terminal.
    app = InputApp()
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        app.copy_to_clipboard("line 194\nline 195")
        await pilot.press("ctrl+v")
        assert prompt.value == "line 194\nline 195"
        assert prompt.outer_size.height == 4
        for y in range(prompt.outer_size.height):
            assert "\n" not in prompt.render_line(y).text
        assert app.submitted == []


async def test_paste_inserts_all_lines() -> None:
    app = InputApp()
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        await pilot.press("a")
        app.post_message(events.Paste("b\r\nc\rd\n"))
        await pilot.pause()
        assert prompt.value == "ab\nc\nd"
        assert app.submitted == []


async def test_paste_removes_only_one_trailing_newline() -> None:
    app = InputApp()
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        app.post_message(events.Paste("one\n\n"))
        await pilot.pause()
        assert prompt.value == "one\n"


async def test_grows_up_to_max_height_then_scrolls() -> None:
    app = InputApp(max_height=4)
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        assert prompt.outer_size.height == 3
        for count in (2, 3, 4):
            prompt.value = "\n".join(str(n) for n in range(count))
            await pilot.pause()
            assert prompt.outer_size.height == count + 2
        prompt.value = "\n".join(str(n) for n in range(12))
        await pilot.pause()
        assert prompt.outer_size.height == 6
        assert prompt.max_scroll_y > 0
        assert prompt.cursor_location == (11, 2)
        assert prompt.region.contains_point(prompt.cursor_screen_offset)


async def test_max_height_none_follows_css() -> None:
    app = CssInputApp(max_height=None)
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.value = "\n".join(str(n) for n in range(12))
        await pilot.pause()
        assert prompt.outer_size.height == 5


async def test_default_max_height_is_ten_rows() -> None:
    app = InputApp()
    async with app.run_test(size=(80, 40)) as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.value = "\n".join(str(n) for n in range(30))
        await pilot.pause()
        assert prompt.outer_size.height == 12


async def test_shrinks_after_submit_and_clear() -> None:
    app = InputApp()
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        prompt.value = "a\nb\nc"
        await pilot.pause()
        assert prompt.outer_size.height == 5
        await pilot.press("enter")
        await pilot.pause()
        assert prompt.outer_size.height == 3
        prompt.value = "a\nb"
        await pilot.pause()
        prompt.value = ""
        await pilot.pause()
        assert prompt.outer_size.height == 3


async def test_enter_submits_all_lines_as_one_command() -> None:
    app = InputApp()
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        prompt.value = "one\ntwo\nthree"
        await pilot.press("enter")
        await pilot.pause()
        assert app.submitted == ["one\ntwo\nthree"]
        assert prompt.command_history.entries == ["one\ntwo\nthree"]
        assert prompt.value == ""


@pytest.mark.parametrize("key", ["shift+enter", "alt+enter", "ctrl+j"])
async def test_newline_keys_insert_a_newline(key: str) -> None:
    app = InputApp()
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        await pilot.press("a", key, "b")
        assert prompt.value == "a\nb"
        assert app.submitted == []


async def test_enter_never_inserts_a_newline() -> None:
    app = InputApp(clear_on_submit=False)
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        await pilot.press("a", "enter")
        assert prompt.value == "a"


async def test_up_down_move_between_rows_before_history() -> None:
    app = InputApp(history=CommandHistory(["old"]))
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        prompt.value = "aa\nbb\ncc"
        await pilot.press("up")
        assert prompt.cursor_location == (1, 2)
        assert prompt.value == "aa\nbb\ncc"
        await pilot.press("up")
        assert prompt.cursor_location == (0, 2)
        await pilot.press("up")
        assert prompt.value == "old"
        assert prompt.recalled_value == "old"
        await pilot.press("down")
        assert prompt.value == "aa\nbb\ncc"
        assert prompt.cursor_location == (2, 2)


async def test_down_moves_between_rows_before_history() -> None:
    app = InputApp(history=CommandHistory(["x", "y"]))
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        await pilot.press("up", "up")
        assert prompt.value == "x"
        prompt.value = "aa\nbb"
        prompt.move_cursor((0, 0))
        await pilot.press("down")
        assert prompt.cursor_location == (1, 0)
        assert prompt.value == "aa\nbb"


async def test_wrapped_line_counts_as_several_rows() -> None:
    app = InputApp(history=CommandHistory(["old"]))
    async with app.run_test(size=(20, 24)) as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        prompt.value = "word " * 12
        await pilot.pause()
        assert prompt.wrapped_document.height > 2
        await pilot.press("up")
        assert prompt.value == "word " * 12
        assert prompt.cursor_location[0] == 0
        assert prompt.cursor_location[1] < len(prompt.value)


async def test_recall_multi_line_cursor_at_end_then_up_moves_inside() -> None:
    app = InputApp(history=CommandHistory(["first", "a\nb\nc"]))
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        await pilot.press("up")
        assert prompt.value == "a\nb\nc"
        assert prompt.cursor_location == (2, 1)
        await pilot.press("up")
        assert prompt.value == "a\nb\nc"
        assert prompt.cursor_location == (1, 1)
        await pilot.press("up", "up")
        assert prompt.value == "first"


async def test_cursor_position_and_value_setter() -> None:
    app = InputApp()
    async with app.run_test():
        prompt = app.query_one(ConsoleInput)
        prompt.value = "ab\ncd"
        assert prompt.cursor_position == 5
        prompt.cursor_position = 1
        assert prompt.cursor_location == (0, 1)
        prompt.cursor_position = 4
        assert prompt.cursor_location == (1, 1)


def test_input_only_arguments_are_rejected() -> None:
    with pytest.raises(TypeError):
        ConsoleInput(password=True)  # pyright: ignore[reportCallIssue]


@pytest.mark.parametrize("value", [0, -1])
def test_max_height_below_one_is_rejected(value: int) -> None:
    with pytest.raises(ValueError, match="max_height must be at least 1"):
        ConsoleInput(max_height=value)


class PromptApp(App[None]):
    def __init__(self, **kwargs: object) -> None:
        super().__init__()
        self.kwargs = kwargs

    def compose(self) -> ComposeResult:
        yield ConsoleInput(**self.kwargs)  # type: ignore[arg-type]


def _row(prompt: ConsoleInput, y: int) -> str:
    return prompt.render_line(y).text


async def test_prompt_on_first_row_only() -> None:
    app = PromptApp(prompt="py> ", value="one\ntwo")
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        await pilot.pause()
        assert prompt.gutter_width == 4
        assert _row(prompt, 0).startswith("py> one")
        assert _row(prompt, 1).startswith("    two")
        assert prompt.value == "one\ntwo"


async def test_prompt_pads_wrapped_rows() -> None:
    app = PromptApp(prompt="> ", value="x" * 60)
    async with app.run_test(size=(20, 10)) as pilot:
        prompt = app.query_one(ConsoleInput)
        await pilot.pause()
        assert _row(prompt, 0).startswith("> xxx")
        assert _row(prompt, 1).startswith("  xxx")
        assert len(_row(prompt, 0)) == len(_row(prompt, 1))


async def test_prompt_with_placeholder() -> None:
    app = PromptApp(prompt="> ", placeholder="command")
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        await pilot.pause()
        assert _row(prompt, 0).startswith("> command")
        assert prompt.value == ""


async def test_prompt_change_at_runtime() -> None:
    app = PromptApp(prompt="> ", value="y" * 30)
    async with app.run_test(size=(20, 10)) as pilot:
        prompt = app.query_one(ConsoleInput)
        await pilot.pause()
        rows = prompt.wrapped_document.height
        prompt.prompt = ">>>>>>>> "
        await pilot.pause()
        assert prompt.gutter_width == 9
        assert _row(prompt, 0).startswith(">>>>>>>> yyy")
        assert prompt.wrapped_document.height > rows
        prompt.prompt = ""
        await pilot.pause()
        assert _row(prompt, 0).startswith("yyy")


async def test_prompt_cursor_and_click_positions() -> None:
    app = PromptApp(prompt="py> ", value="hello")
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        await pilot.pause()
        assert prompt.cursor_screen_offset.x == prompt.content_region.x + 4 + 5
        await pilot.click(ConsoleInput, offset=(2 + 4 + 2, 1))
        assert prompt.cursor_location == (0, 2)
        await pilot.click(ConsoleInput, offset=(2 + 1, 1))
        assert prompt.cursor_location == (0, 0)


async def test_prompt_click_on_wrapped_row() -> None:
    app = PromptApp(prompt="> ", value="abcdefghijklmnopqrstuvwxyz")
    async with app.run_test(size=(14, 10)) as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        await pilot.pause()
        assert prompt.wrapped_document.height > 1
        await pilot.click(ConsoleInput, offset=(2 + 2 + 1, 2))
        row_start = prompt.wrapped_document.get_offsets(0)[0]
        assert prompt.cursor_location == (0, row_start + 1)


async def test_wide_character_prompt() -> None:
    app = PromptApp(prompt="漢> ", value="ab\ncd")
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        await pilot.pause()
        assert prompt.gutter_width == 4
        assert _row(prompt, 0).startswith("漢> ab")
        assert _row(prompt, 1).startswith("    cd")
        await pilot.click(ConsoleInput, offset=(2 + 4 + 1, 2))
        assert prompt.cursor_location == (1, 1)


class SuggestApp(App[None]):
    def compose(self) -> ComposeResult:
        yield ConsoleInput(
            suggester=SuggestFromList(["hello", "help me"], case_sensitive=True)
        )


async def test_suggester_shows_ghost_text_and_right_accepts() -> None:
    app = SuggestApp()
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        await pilot.press("h", "e", "l", "l")
        await pilot.pause()
        assert prompt.suggestion == "o"
        assert prompt.value == "hell"
        await pilot.press("right")
        assert prompt.value == "hello"
        assert prompt.suggestion == ""


async def test_suggester_clears_on_multiple_lines_and_mismatch() -> None:
    app = SuggestApp()
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        await pilot.press("h", "e")
        await pilot.pause()
        assert prompt.suggestion
        await pilot.press("ctrl+j")
        await pilot.pause()
        assert prompt.suggestion == ""
        await pilot.press("x")
        await pilot.pause()
        assert prompt.suggestion == ""


async def test_stale_suggestion_is_ignored() -> None:
    app = SuggestApp()
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        await pilot.press("h", "e")
        await pilot.pause()
        prompt.post_message(SuggestionReady("h", "hello"))
        await pilot.pause()
        assert prompt.suggestion == ""


async def test_no_suggester_no_suggestion() -> None:
    app = PromptApp()
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        await pilot.press("h", "e")
        await pilot.pause()
        assert prompt.suggestion == ""


async def test_suggestion_cleared_when_cursor_moves_away() -> None:
    app = SuggestApp()
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        await pilot.press("h", "e", "l", "l")
        await pilot.pause()
        assert prompt.suggestion == "o"
        await pilot.press("left")
        assert prompt.suggestion == ""
        await pilot.press("right")
        assert prompt.value == "hell"
        assert prompt.cursor_location == (0, 4)


async def test_case_insensitive_suggester() -> None:
    app = PromptApp(suggester=SuggestFromList(["Portugal"], case_sensitive=False))
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        await pilot.press("p", "o")
        await pilot.pause()
        assert prompt.suggestion == "rtugal"
        await pilot.press("right")
        assert prompt.value == "portugal"


class EscapeApp(InputApp):
    """An app whose own ``escape`` binding counts the presses that reach it."""

    BINDINGS = [("escape", "probe", "probe")]

    def __init__(self, **input_kwargs: object) -> None:
        super().__init__(**input_kwargs)
        self.probed = 0
        self.changes = 0

    def action_probe(self) -> None:
        self.probed += 1

    def on_text_area_changed(self) -> None:
        self.changes += 1


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    fake = Clock()
    monkeypatch.setattr("textual_console._console_input._monotonic", fake)
    return fake


async def test_double_escape_clears(clock: Clock) -> None:
    app = EscapeApp()
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        await pilot.press("a", "b", "escape")
        assert prompt.value == "ab"
        assert app.probed == 1
        clock.now += 0.3
        await pilot.press("escape")
        assert prompt.value == ""
        assert app.probed == 1


async def test_first_escape_clears_output_selection(clock: Clock) -> None:
    app = EscapeApp()
    async with app.run_test() as pilot:
        output = app.query_one(ConsoleOutput)
        output.write("hello world")
        await pilot.pause()
        output.screen.selections = {output: Selection(Offset(6, 0), Offset(11, 0))}
        app.query_one(ConsoleInput).focus()
        await pilot.press("a", "escape")
        await pilot.pause()
        assert not output.screen.selections
        assert app.probed == 1


async def test_slow_second_escape_becomes_first(clock: Clock) -> None:
    app = EscapeApp()
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        await pilot.press("a", "escape")
        clock.now += 0.8
        await pilot.press("escape")
        assert prompt.value == "a"
        assert app.probed == 2
        clock.now += 0.2
        await pilot.press("escape")
        assert prompt.value == ""


async def test_other_key_resets_escape_count(clock: Clock) -> None:
    app = EscapeApp()
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        await pilot.press("a", "escape", "x", "escape")
        assert prompt.value == "ax"
        assert app.probed == 2


async def test_escape_on_empty_input_is_not_consumed(clock: Clock) -> None:
    app = EscapeApp()
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        await pilot.press("escape", "escape", "escape")
        assert app.probed == 3
        assert prompt.value == ""


async def _dropdown_app(candidates: list[object]) -> EscapeApp:
    from textual_console import CommandAutoComplete

    class DropdownEscapeApp(EscapeApp):
        def compose(self) -> ComposeResult:
            yield from super().compose()
            yield CommandAutoComplete("#prompt", lambda line: candidates)  # type: ignore[arg-type,return-value]

    return DropdownEscapeApp()


@pytest.mark.parametrize("hint_only", [False, True])
async def test_escape_closing_dropdown_does_not_count(
    clock: Clock, hint_only: bool
) -> None:
    from textual_autocomplete import AutoComplete

    from textual_console import CompletionHint

    app = await _dropdown_app(
        [CompletionHint("NAME: a name")] if hint_only else ["hello"]
    )
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        if hint_only:
            prompt.value = "open "
            await pilot.pause()
            await pilot.press("tab")
        else:
            await pilot.press("h", "e")
        await pilot.pause()
        assert app.query_one(AutoComplete).display
        await pilot.press("escape")
        await pilot.pause()
        assert not app.query_one(AutoComplete).display
        assert app.probed == 0
        assert prompt.value != ""
        await pilot.press("escape")
        assert app.probed == 1
        assert prompt.value != ""
        await pilot.press("escape")
        assert prompt.value == ""


async def test_clear_is_undoable(clock: Clock) -> None:
    app = EscapeApp()
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        await pilot.press("a", "b", "shift+enter", "c", "d")
        text = prompt.value
        assert "\n" in text
        await pilot.press("escape", "escape")
        assert prompt.value == ""
        await pilot.press("ctrl+z")
        assert prompt.value == text


async def test_clear_ends_history_walk(clock: Clock) -> None:
    app = EscapeApp(history=CommandHistory(["one", "two"]))
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        await pilot.press("up", "up")
        assert prompt.value == "one"
        await pilot.press("escape", "escape")
        assert prompt.value == ""
        assert prompt.recalled_value is None
        await pilot.press("up")
        assert prompt.value == "two"
        await pilot.press("down")
        assert prompt.value == ""


async def test_clear_removes_ghost_text(clock: Clock) -> None:
    app = EscapeApp(suggester=SuggestFromList(["hello"]))
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        await pilot.press("h", "e")
        await pilot.pause()
        assert prompt.suggestion
        await pilot.press("escape", "escape")
        await pilot.pause()
        assert prompt.suggestion == ""


async def test_clear_posts_only_changed(clock: Clock) -> None:
    app = EscapeApp()
    seen: list[str] = []
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        await pilot.press("a")
        await pilot.pause()
        app.changes = 0
        original = prompt.post_message

        def spy(message: object) -> bool:
            seen.append(type(message).__name__)
            return original(message)  # type: ignore[arg-type]

        prompt.post_message = spy  # type: ignore[method-assign]
        await pilot.press("escape", "escape")
        await pilot.pause()
        assert app.changes == 1
        assert "Changed" in seen
        # Key and Callback are the key press itself and Textual's own plumbing.
        assert set(seen) <= {"Key", "Callback", "Changed", "SelectionChanged"}


async def test_double_escape_disabled(clock: Clock) -> None:
    app = EscapeApp(double_escape_clear=None)
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        await pilot.press("a", "escape", "escape", "escape")
        assert prompt.value == "a"
        assert app.probed == 3


def test_double_escape_validation() -> None:
    for bad in (0, -1, "0.5"):
        with pytest.raises(ValueError):
            ConsoleInput(double_escape_clear=bad)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        ConsoleInput(double_escape_clear=True)
    prompt = ConsoleInput()
    assert prompt.double_escape_clear == 0.5
    with pytest.raises(ValueError):
        prompt.double_escape_clear = 0
    with pytest.raises(TypeError):
        prompt.double_escape_clear = True
    prompt.double_escape_clear = None
    assert prompt.double_escape_clear is None


async def test_double_escape_custom_window(clock: Clock) -> None:
    app = EscapeApp(double_escape_clear=1.0)
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.focus()
        await pilot.press("a", "escape")
        clock.now += 0.9
        await pilot.press("escape")
        assert prompt.value == ""


async def test_double_escape_ignores_read_only_input(clock: Clock) -> None:
    app = EscapeApp(read_only=True)
    async with app.run_test() as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.load_text("keep")
        prompt.focus()
        await pilot.press("escape", "escape")
        assert prompt.value == "keep"
        assert app.probed == 2
