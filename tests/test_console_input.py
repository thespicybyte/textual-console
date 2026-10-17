from __future__ import annotations

import pytest
from textual import events
from textual.app import App, ComposeResult
from textual.geometry import Offset
from textual.selection import Selection
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
