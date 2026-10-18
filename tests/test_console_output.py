from __future__ import annotations

import pytest
from rich.color import Color
from rich.table import Table
from rich.text import Text
from textual import events
from textual.app import App, ComposeResult
from textual.geometry import Offset
from textual.pilot import Pilot
from textual.selection import Selection
from textual.widgets import Input

from textual_console import ConsoleOutput


class OutputApp(App[None]):
    def __init__(self, **output_kwargs: object) -> None:
        super().__init__()
        self.output_kwargs = output_kwargs
        self.copied: list[str] = []

    def compose(self) -> ComposeResult:
        yield ConsoleOutput(**self.output_kwargs)  # type: ignore[arg-type]
        yield Input()

    def on_console_output_selection_copied(
        self, message: ConsoleOutput.SelectionCopied
    ) -> None:
        self.copied.append(message.text)


def lines_text(output: ConsoleOutput) -> list[str]:
    return [strip.text.rstrip() for strip in output.lines]


async def test_write_lines() -> None:
    app = OutputApp()
    async with app.run_test() as pilot:
        output = app.query_one(ConsoleOutput)
        output.write("plain")
        output.write(Text("styled", style="bold red"))
        table = Table("a", "b")
        table.add_row("1", "2")
        output.write(table)
        output.write_ansi("\x1b[31mred\x1b[0m done")
        output.write("")
        output.write("\n")
        await pilot.pause()
        texts = lines_text(output)
        assert texts[0] == "plain"
        assert texts[1] == "styled"
        assert any("┃ a" in line for line in texts)
        assert "red done" in texts
        red = next(s for s in output.lines if s.text.startswith("red done"))
        assert red._segments[0].style is not None
        assert red._segments[0].style.color is not None
        assert "\x1b" not in "".join(texts)
        assert output.write("x") is output


async def test_double_click_selects_word_and_focus_stays() -> None:
    app = OutputApp()
    async with app.run_test() as pilot:
        output = app.query_one(ConsoleOutput)
        app.query_one(Input).focus()
        output.write("hello brave world")
        await pilot.pause()
        await pilot.click(ConsoleOutput, offset=(7, 0), times=2)
        await pilot.pause()
        assert output.selected_text == "brave"
        assert app.focused is app.query_one(Input)


async def test_double_click_on_whitespace_selects_nothing() -> None:
    app = OutputApp()
    async with app.run_test() as pilot:
        output = app.query_one(ConsoleOutput)
        output.write("a b")
        await pilot.pause()
        await pilot.click(ConsoleOutput, offset=(1, 0), times=2)
        await pilot.pause()
        assert output.selected_text is None


async def test_triple_click_selects_line_without_padding() -> None:
    app = OutputApp()
    async with app.run_test() as pilot:
        output = app.query_one(ConsoleOutput)
        output.write("hello brave world")
        output.write("second")
        await pilot.pause()
        await pilot.click(ConsoleOutput, offset=(3, 0), times=3)
        await pilot.pause()
        assert output.selected_text == "hello brave world"
        await pilot.click(ConsoleOutput, offset=(3, 0), times=4)
        await pilot.pause()
        assert output.selected_text == "hello brave world"


async def test_drag_selects_across_lines() -> None:
    app = OutputApp()
    async with app.run_test() as pilot:
        output = app.query_one(ConsoleOutput)
        output.write("hello brave world")
        output.write("second line")
        await pilot.pause()
        await pilot.mouse_down(ConsoleOutput, offset=(6, 0))
        await pilot.hover(ConsoleOutput, offset=(4, 1))
        await pilot.mouse_up(ConsoleOutput, offset=(4, 1))
        await pilot.pause()
        assert output.selected_text == "brave world\nsecon"


async def test_drag_past_bottom_edge_auto_scrolls() -> None:
    app = OutputApp()
    async with app.run_test(size=(40, 10)) as pilot:
        output = app.query_one(ConsoleOutput)
        for i in range(60):
            output.write(f"line {i}")
        await pilot.pause()
        output.scroll_to(y=0, animate=False)
        await pilot.pause()
        await pilot.mouse_down(ConsoleOutput, offset=(0, 0))
        bottom = output.region.y + output.size.height - 1
        # Pilot moves have no vertical delta, and the engine only auto-scrolls
        # on a vertical move, so send the move with a delta.
        app.screen._forward_event(
            events.MouseMove(
                output,
                3,
                bottom,
                0,
                5,
                1,
                False,
                False,
                False,
                screen_x=3,
                screen_y=bottom,
            )
        )
        await pilot.pause(0.6)
        assert output.scroll_offset.y > 0
        await pilot.mouse_up(ConsoleOutput, offset=(3, output.size.height - 1))
        await pilot.pause()
        text = output.selected_text
        assert text is not None
        assert text.startswith("line 0\nline 1")
        assert len(text.splitlines()) > output.size.height - 1


async def test_ctrl_c_copies_with_empty_input_focused() -> None:
    app = OutputApp()
    async with app.run_test() as pilot:
        output = app.query_one(ConsoleOutput)
        app.query_one(Input).focus()
        output.write("hello brave world")
        await pilot.pause()
        await pilot.click(ConsoleOutput, offset=(7, 0), times=2)
        await pilot.press("ctrl+c")
        await pilot.pause()
        assert app.clipboard == "brave"


async def test_ctrl_c_prefers_input_selection() -> None:
    app = OutputApp()
    async with app.run_test() as pilot:
        output = app.query_one(ConsoleOutput)
        field = app.query_one(Input)
        output.write("hello brave world")
        await pilot.pause()
        await pilot.click(ConsoleOutput, offset=(7, 0), times=2)
        field.focus()
        field.value = "typed text"
        field.select_all()
        await pilot.press("ctrl+c")
        await pilot.pause()
        assert app.clipboard == "typed text"


async def test_single_click_and_escape_clear_selection() -> None:
    app = OutputApp()
    async with app.run_test() as pilot:
        output = app.query_one(ConsoleOutput)
        output.write("hello brave world")
        await pilot.pause()
        await pilot.click(ConsoleOutput, offset=(7, 0), times=2)
        assert output.selected_text == "brave"
        await pilot.click(ConsoleOutput, offset=(1, 0))
        await pilot.pause()
        assert output.text_selection is None
        await pilot.click(ConsoleOutput, offset=(7, 0), times=2)
        assert output.selected_text == "brave"
        await pilot.press("escape")
        await pilot.pause()
        assert output.text_selection is None


async def test_scrolled_view_x_and_y() -> None:
    app = OutputApp()
    async with app.run_test(size=(40, 10)) as pilot:
        output = app.query_one(ConsoleOutput)
        for i in range(30):
            output.write(f"row{i:02d} " + "x" * 60 + " tail-word")
        await pilot.pause()
        output.scroll_to(x=30, y=12, animate=False)
        await pilot.pause()
        # Row 0 of the view is line 12, and the view starts at cell 30.
        assert output.render_line(0).text.startswith("x" * 10)
        await pilot.click(ConsoleOutput, offset=(1, 0), times=3)
        await pilot.pause()
        assert (output.selected_text or "").startswith("row12 ")
        await pilot.click(ConsoleOutput, offset=(1, 1), times=2)
        await pilot.pause()
        assert output.selected_text == "x" * 60
        # Selected cells are at the scrolled position: 6..66 in the line,
        # so 0..36 are visible at scroll x 30.
        selected = [
            (s.text, s.style.bgcolor)
            for s in output.render_line(1)
            if s.style is not None
        ]
        assert selected[0][1] != output.rich_style.bgcolor
        output.scroll_to(x=50, y=12, animate=False)
        await pilot.pause()
        row = output.render_line(1)
        highlighted = "".join(
            s.text
            for s in row
            if s.style is not None and s.style.bgcolor != output.rich_style.bgcolor
        )
        # The run ends at cell 66 (the scroll is clamped to the line width).
        assert output.scroll_offset.x > 30
        assert highlighted == "x" * (66 - output.scroll_offset.x)
        output.select_word_at(Offset(70, 14))
        assert output.selected_text == "tail-word"


async def test_max_lines_prune_shifts_selection() -> None:
    app = OutputApp(max_lines=5)
    async with app.run_test() as pilot:
        output = app.query_one(ConsoleOutput)
        for i in range(5):
            output.write(f"line {i}")
        await pilot.pause()
        output.select_line(3)
        assert output.selected_text == "line 3"
        output.write("line 5")
        assert output.selected_text == "line 3"
        assert output.text_selection == Selection(Offset(0, 2), Offset(6, 2))
        output.write("line 6")
        output.write("line 7")
        assert output.selected_text == "line 3"
        assert output.text_selection == Selection(Offset(0, 0), Offset(6, 0))
        output.write("line 8")
        assert output.text_selection is None
        assert lines_text(output) == [f"line {i}" for i in range(4, 9)]


async def test_max_lines_prune_clamps_partially_removed_selection() -> None:
    app = OutputApp(max_lines=5)
    async with app.run_test() as pilot:
        output = app.query_one(ConsoleOutput)
        for i in range(5):
            output.write(f"line {i}")
        await pilot.pause()
        output.screen.selections = {output: Selection(Offset(2, 0), Offset(4, 2))}
        output.write("line 5")
        output.write("line 6")
        assert output.text_selection == Selection(Offset(0, 0), Offset(4, 0))


async def test_copy_on_select_double_click() -> None:
    app = OutputApp(copy_on_select=True)
    async with app.run_test() as pilot:
        output = app.query_one(ConsoleOutput)
        output.write("hello brave world")
        await pilot.pause()
        await pilot.click(ConsoleOutput, offset=(7, 0), times=2)
        await pilot.pause()
        assert app.clipboard == "brave"
        assert app.copied == ["brave"]


async def test_copy_on_select_drag() -> None:
    app = OutputApp(copy_on_select=True)
    async with app.run_test() as pilot:
        output = app.query_one(ConsoleOutput)
        output.write("hello brave world")
        await pilot.pause()
        await pilot.mouse_down(ConsoleOutput, offset=(6, 0))
        await pilot.hover(ConsoleOutput, offset=(10, 0))
        await pilot.mouse_up(ConsoleOutput, offset=(10, 0))
        await pilot.pause()
        assert app.clipboard == "brave"
        assert app.copied == ["brave"]


async def test_no_copy_without_copy_on_select() -> None:
    app = OutputApp()
    async with app.run_test() as pilot:
        output = app.query_one(ConsoleOutput)
        output.write("hello brave world")
        await pilot.pause()
        await pilot.click(ConsoleOutput, offset=(7, 0), times=2)
        await pilot.pause()
        assert app.clipboard == ""
        assert app.copied == []
        assert output.copy_selection() == "brave"
        await pilot.pause()
        assert app.copied == ["brave"]


async def test_selection_api() -> None:
    app = OutputApp()
    async with app.run_test() as pilot:
        output = app.query_one(ConsoleOutput)
        output.write("alpha beta")
        output.write("gamma")
        await pilot.pause()
        output.select_all()
        assert output.selected_text == "alpha beta\ngamma"
        output.clear_selection()
        assert output.selected_text is None
        output.select_word_at(Offset(-3, 0))
        assert output.selected_text == "alpha"
        output.select_word_at(Offset(5, 0))
        assert output.selected_text is None
        output.select_line(1)
        assert output.selected_text == "gamma"
        assert output.copy_selection() == "gamma"
        output.clear_selection()
        assert output.copy_selection() is None


async def test_word_chars() -> None:
    app = OutputApp(word_chars="(")
    async with app.run_test() as pilot:
        output = app.query_one(ConsoleOutput)
        output.write("call f(x) now")
        await pilot.pause()
        output.select_word_at(Offset(5, 0))
        assert output.selected_text == "f(x"


async def test_mouse_up_arrives_before_click() -> None:
    """Risk 1: the engine clears on MouseUp, before the Click that selects."""
    app = OutputApp()
    order: list[str] = []
    async with app.run_test() as pilot:
        output = app.query_one(ConsoleOutput)
        output.write("hello brave world")
        await pilot.pause()
        screen = app.screen
        original = screen.clear_selection

        def spy() -> None:
            order.append("clear")
            original()

        screen.clear_selection = spy  # type: ignore[method-assign]
        original_click = output.select_word_at

        def spy_select(offset: Offset) -> None:
            order.append("select")
            original_click(offset)

        output.select_word_at = spy_select  # type: ignore[method-assign]
        await pilot.click(ConsoleOutput, offset=(7, 0), times=2)
        await pilot.pause()
        assert order[-2:] == ["clear", "select"]
        assert output.selected_text == "brave"


async def test_click_event_is_not_handled_by_base_widget() -> None:
    """Chain 2 must not select the whole widget."""
    app = OutputApp()
    async with app.run_test() as pilot:
        output = app.query_one(ConsoleOutput)
        output.write("one two")
        output.write("three")
        await pilot.pause()
        await pilot.click(ConsoleOutput, offset=(1, 0), times=2)
        await pilot.pause()
        assert output.selected_text == "one"


async def test_wide_characters_select_and_highlight() -> None:
    app = OutputApp()
    async with app.run_test() as pilot:
        output = app.query_one(ConsoleOutput)
        output.write("ab 漢字漢字 cd")
        await pilot.pause()
        # "漢字漢字" covers cells 3..10.
        await pilot.click(ConsoleOutput, offset=(5, 0), times=2)
        await pilot.pause()
        assert output.selected_text == "漢字漢字"
        strip = output.render_line(0)
        selected = "".join(
            s.text
            for s in strip
            if s.style is not None and s.style.bgcolor != output.rich_style.bgcolor
        )
        assert selected == "漢字漢字"
        await pilot.click(ConsoleOutput, offset=(12, 0), times=2)
        await pilot.pause()
        assert output.selected_text == "cd"


class StyledApp(OutputApp):
    CSS = "ConsoleOutput > .console-output--selection { background: #ff0000; }"


def selected_bg(output: ConsoleOutput) -> object:
    strip = output.render_line(0)
    return next(
        s.style.bgcolor
        for s in strip
        if s.style is not None and s.text.strip() == "hello"
    )


async def test_highlight_uses_component_style_when_set() -> None:
    app = StyledApp()
    async with app.run_test() as pilot:
        output = app.query_one(ConsoleOutput)
        output.write("hello world")
        await pilot.pause()
        output.select_word_at(Offset(1, 0))
        bg = selected_bg(output)
        assert bg is not None
        assert bg.triplet is not None and bg.triplet.hex == "#ff0000"  # type: ignore[attr-defined]


async def test_highlight_falls_back_to_screen_selection() -> None:
    class ScreenStyled(OutputApp):
        CSS = "Screen > .screen--selection { background: #00ff00; }"

    app = ScreenStyled()
    async with app.run_test() as pilot:
        output = app.query_one(ConsoleOutput)
        output.write("hello world")
        await pilot.pause()
        output.select_word_at(Offset(1, 0))
        bg = selected_bg(output)
        assert bg.triplet.hex == "#00ff00"  # type: ignore[attr-defined]


async def test_clear_drops_selection() -> None:
    app = OutputApp()
    async with app.run_test() as pilot:
        output = app.query_one(ConsoleOutput)
        output.write("hello world")
        await pilot.pause()
        output.select_line(0)
        assert output.clear() is output
        output.write("new text")
        await pilot.pause()
        assert output.text_selection is None
        assert output.selected_text is None


async def test_selection_shift_keeps_sibling_selections() -> None:
    from textual.widgets import Static

    class Sibling(OutputApp):
        def compose(self) -> ComposeResult:
            yield from super().compose()
            yield Static("sibling text")

    app = Sibling(max_lines=3)
    async with app.run_test() as pilot:
        output = app.query_one(ConsoleOutput)
        static = app.query_one(Static)
        for i in range(3):
            output.write(f"line {i}")
        await pilot.pause()
        output.screen.selections = {
            output: Selection(Offset(0, 2), Offset(4, 2)),
            static: Selection(None, None),
        }
        output.write("line 3")
        assert static in output.screen.selections
        assert output.text_selection == Selection(Offset(0, 1), Offset(4, 1))


async def test_copy_on_select_once_with_prune_and_scrollbar_mouse_up() -> None:
    app = OutputApp(copy_on_select=True, max_lines=20)
    async with app.run_test(size=(40, 10)) as pilot:
        output = app.query_one(ConsoleOutput)
        for i in range(20):
            output.write(f"line {i}")
        await pilot.pause()
        await pilot.mouse_down(ConsoleOutput, offset=(0, 5))
        await pilot.hover(ConsoleOutput, offset=(4, 5))
        await pilot.mouse_up(ConsoleOutput, offset=(4, 5))
        await pilot.pause()
        assert len(app.copied) == 1
        output.write("line 20")
        await pilot.pause()
        # A MouseUp that does not clear the selection (a scrollbar press).
        scrollbar_x = output.region.right - 1
        await pilot.mouse_down(ConsoleOutput, offset=(scrollbar_x, 2))
        await pilot.mouse_up(ConsoleOutput, offset=(scrollbar_x, 2))
        await pilot.pause()
        assert len(app.copied) == 1


def _luminance(color: Color) -> float:
    r, g, b = color.get_truecolor()
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


async def test_selected_text_stays_readable_in_themes() -> None:
    for theme in ("textual-dark", "textual-light"):
        app = OutputApp()
        app.theme = theme
        async with app.run_test() as pilot:
            output = app.query_one(ConsoleOutput)
            output.write(Text("plain"))
            output.write(Text("colored", style="#ff8800"))
            await pilot.pause()
            for line, expected in ((0, None), (1, "#ff8800")):
                output.select_line(line)
                style = next(
                    s.style for s in output.render_line(line) if s.text.strip()
                )
                assert style is not None
                color, bgcolor = style.color, style.bgcolor
                assert color is not None and bgcolor is not None
                assert color != bgcolor
                gap = abs(_luminance(color) - _luminance(bgcolor))
                if expected is None:
                    assert gap > 60, (theme, line, style)
                else:
                    assert color.get_truecolor().hex == expected


@pytest.mark.parametrize("value", [0, -1])
def test_max_lines_below_one_raises(value: int) -> None:
    with pytest.raises(ValueError, match="max_lines"):
        ConsoleOutput(max_lines=value)


# Extend a selection with shift-click or ctrl-click

MODS = pytest.mark.parametrize("mod", ["shift", "ctrl"])


def _mods(mod: str) -> dict[str, bool]:
    return {"shift": mod == "shift", "control": mod == "ctrl"}


async def _long_output(app: OutputApp, pilot: Pilot[None]) -> ConsoleOutput:
    output = app.query_one(ConsoleOutput)
    for i in range(60):
        output.write(f"line {i}")
    await pilot.pause()
    output.scroll_to(y=0, animate=False)
    await pilot.pause()
    return output


async def _drag(
    pilot: Pilot[None], start: tuple[int, int], end: tuple[int, int]
) -> None:
    await pilot.mouse_down(ConsoleOutput, offset=start)
    await pilot.hover(ConsoleOutput, offset=end)
    await pilot.mouse_up(ConsoleOutput, offset=end)
    await pilot.pause()


async def _extend(
    pilot: Pilot[None], mod: str, output: ConsoleOutput, x: int, line: int
) -> None:
    """Scroll so that ``line`` is visible, then click it with the modifier."""
    top = output.scroll_offset.y
    if not top <= line < top + output.size.height:
        output.scroll_to(y=max(0, line - 3), animate=False)
        await pilot.pause()
    row = line - output.scroll_offset.y
    await pilot.click(ConsoleOutput, offset=(x, row), **_mods(mod))
    await pilot.pause()


@MODS
async def test_extend_past_scrolled_lines(mod: str) -> None:
    app = OutputApp()
    async with app.run_test(size=(40, 10)) as pilot:
        output = await _long_output(app, pilot)
        await _drag(pilot, (2, 1), (4, 2))
        assert output.selected_text == "ne 1\nline "
        await _extend(pilot, mod, output, 3, 33)
        assert output.scroll_offset.y > 0
        lines = "\n".join(f"line {i}" for i in range(2, 33))
        assert output.selected_text == f"ne 1\n{lines}\nline"


@MODS
async def test_extend_backwards(mod: str) -> None:
    app = OutputApp()
    async with app.run_test(size=(40, 10)) as pilot:
        output = await _long_output(app, pilot)
        output.scroll_to(y=38, animate=False)
        await pilot.pause()
        await _drag(pilot, (1, 2), (3, 2))  # line 40, columns 1..3
        assert output.selected_text == "ine"
        await _extend(pilot, mod, output, 2, 5)
        lines = "\n".join(f"line {i}" for i in range(6, 40))
        assert output.selected_text == f"ne 5\n{lines}\nli"


@MODS
async def test_second_extend_keeps_anchor(mod: str) -> None:
    app = OutputApp()
    async with app.run_test(size=(40, 10)) as pilot:
        output = await _long_output(app, pilot)
        await _drag(pilot, (0, 4), (2, 4))
        await _extend(pilot, mod, output, 1, 6)
        assert output.selected_text == "line 4\nline 5\nli"
        await _extend(pilot, mod, output, 1, 2)
        assert output.selected_text == "ine 2\nline 3\nl"
        await _extend(pilot, mod, output, 1, 5)
        assert output.selected_text == "line 4\nli"


@MODS
async def test_extend_after_upward_drag(mod: str) -> None:
    app = OutputApp()
    async with app.run_test(size=(40, 10)) as pilot:
        output = await _long_output(app, pilot)
        await _drag(pilot, (3, 6), (1, 4))  # anchor is line 6, column 3
        assert output.selected_text == "ine 4\nline 5\nline"
        await _extend(pilot, mod, output, 1, 8)
        assert output.selected_text == "e 6\nline 7\nli"


@MODS
async def test_extend_without_selection_does_nothing(mod: str) -> None:
    app = OutputApp()
    async with app.run_test(size=(40, 10)) as pilot:
        output = await _long_output(app, pilot)
        await _extend(pilot, mod, output, 3, 3)
        assert output.text_selection is None
        await pilot.click(ConsoleOutput, offset=(2, 1))  # leaves an anchor
        await _extend(pilot, mod, output, 3, 5)
        assert output.text_selection is None


@MODS
async def test_extend_then_copy(mod: str) -> None:
    app = OutputApp()
    async with app.run_test(size=(40, 10)) as pilot:
        output = await _long_output(app, pilot)
        await _drag(pilot, (0, 1), (2, 1))
        await _extend(pilot, mod, output, 3, 30)
        app.query_one(Input).focus()
        await pilot.press("ctrl+c")
        lines = "\n".join(f"line {i}" for i in range(1, 30))
        assert app.clipboard == f"{lines}\nline"


@MODS
async def test_extend_copies_on_select(mod: str) -> None:
    app = OutputApp(copy_on_select=True)
    async with app.run_test(size=(40, 10)) as pilot:
        output = await _long_output(app, pilot)
        await _drag(pilot, (0, 1), (2, 1))
        assert app.copied == ["lin"]
        await _extend(pilot, mod, output, 3, 12)
        lines = "\n".join(f"line {i}" for i in range(1, 12))
        assert app.copied == ["lin", f"{lines}\nline"]


@MODS
async def test_extend_from_word_and_select_all(mod: str) -> None:
    app = OutputApp()
    async with app.run_test(size=(40, 10)) as pilot:
        output = await _long_output(app, pilot)
        await pilot.click(ConsoleOutput, offset=(5, 2), times=2)
        await pilot.pause()
        assert output.selected_text == "2"
        output.write("two words here")
        await pilot.pause()
        output.scroll_to(y=0, animate=False)
        await pilot.pause()
        await _extend(pilot, mod, output, 2, 4)
        assert output.selected_text == "2\nline 3\nlin"
        output.select_all()
        await pilot.pause()
        await _extend(pilot, mod, output, 1, 1)
        assert output.selected_text == "line 0\nli"


@MODS
async def test_double_extend_click_does_not_select_word(mod: str) -> None:
    app = OutputApp()
    async with app.run_test(size=(40, 10)) as pilot:
        output = await _long_output(app, pilot)
        await _drag(pilot, (0, 1), (2, 1))
        await pilot.click(ConsoleOutput, offset=(3, 4), times=2, **_mods(mod))
        await pilot.pause()
        assert output.selected_text == "line 1\nline 2\nline 3\nline"


@MODS
async def test_extend_anchor_follows_pruned_lines(mod: str) -> None:
    app = OutputApp(max_lines=20)
    async with app.run_test(size=(40, 10)) as pilot:
        output = app.query_one(ConsoleOutput)
        for i in range(20):
            output.write(f"line {i}")
        await pilot.pause()
        output.scroll_to(y=0, animate=False)
        await pilot.pause()
        await _drag(pilot, (0, 6), (2, 6))
        for i in range(20, 24):
            output.write(f"line {i}")
        await pilot.pause()
        output.scroll_to(y=0, animate=False)
        await pilot.pause()
        await _extend(pilot, mod, output, 1, 5)
        # The drag started on line 6 and 4 lines were pruned, so the anchor is
        # now line 2. The click on line 5 is the text "line 9".
        assert output.selected_text == "line 6\nline 7\nline 8\nli"


async def test_extend_selection_to_api() -> None:
    app = OutputApp()
    async with app.run_test(size=(40, 10)) as pilot:
        output = await _long_output(app, pilot)
        output.extend_selection_to(Offset(2, 5))
        assert output.text_selection is None
        output.screen.selections = {output: Selection(Offset(1, 2), Offset(3, 2))}
        output.extend_selection_to(Offset(2, 4))
        assert output.selected_text == "ine 2\nline 3\nlin"
        output.extend_selection_to(Offset(0, 999))
        assert (output.selected_text or "").endswith("line 58\nl")


async def test_plain_click_after_extension_clears_it() -> None:
    app = OutputApp()
    async with app.run_test(size=(40, 10)) as pilot:
        output = await _long_output(app, pilot)
        await _drag(pilot, (0, 1), (2, 1))
        await _extend(pilot, "shift", output, 3, 4)
        assert output.selected_text is not None
        await pilot.click(ConsoleOutput, offset=(1, 1))
        await pilot.pause()
        assert output.text_selection is None
