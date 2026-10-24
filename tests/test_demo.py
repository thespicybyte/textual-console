import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

from textual_console import CommandAutoComplete, ConsoleInput, ConsoleOutput
from textual_console.__main__ import ConsoleDemo, main

EXAMPLES = Path(__file__).parent.parent / "examples"


def load_example(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        f"example_{name}", EXAMPLES / f"{name}.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def output_text(output: ConsoleOutput) -> str:
    return "\n".join(strip.text.rstrip() for strip in output.lines)


async def test_demo_runs_commands(tmp_path: Path) -> None:
    log = tmp_path / "demo.log"
    app = ConsoleDemo(log_path=log, max_lines=50)
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.press(*"table", "enter")
        await pilot.press(*"ansi", "enter")
        await pilot.press(*"flood 100", "enter")
        await pilot.pause()
        output = app.query_one(ConsoleOutput)
        assert len(output.lines) == 50
        assert "line 100" in output_text(output)
        assert app.query_one(ConsoleInput).value == ""
    text = log.read_text()
    assert "> table" in text
    assert "alpha" in text
    assert "bold red" in text
    assert "line 1\n" in text


async def test_demo_copy_notifies() -> None:
    app = ConsoleDemo()
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.press(*"echo hello", "enter")
        await pilot.pause()
        await pilot.double_click(ConsoleOutput, offset=(3, 2))
        await pilot.press("ctrl+c")
        await pilot.pause()
        assert app.clipboard
        assert len(app._notifications) == 1


async def test_demo_help_option_does_not_exit() -> None:
    app = ConsoleDemo()
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.press(*"flood -h", "enter")
        await pilot.pause()
        assert app.is_running
        text = output_text(app.query_one(ConsoleOutput))
        assert "usage: flood" in text
        assert "--style" in text


async def test_demo_reports_parse_errors() -> None:
    app = ConsoleDemo()
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.press(*"flood --style purple", "enter")
        await pilot.press(*"nope", "enter")
        await pilot.pause()
        assert app.is_running
        text = output_text(app.query_one(ConsoleOutput))
        assert "invalid choice: 'purple'" in text
        assert "Unknown command: nope" in text


async def test_demo_new_commands() -> None:
    app = ConsoleDemo()
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.press(*"colors --only red blue", "enter")
        await pilot.press(*"flood 3 --style green", "enter")
        await pilot.press(*"echo a  b", "enter")
        await pilot.pause()
        text = output_text(app.query_one(ConsoleOutput))
        assert "red text" in text and "blue text" in text
        assert "green text" not in text
        assert "line 3" in text
        assert "\na b" in text


async def test_demo_splits_multi_line_submit() -> None:
    app = ConsoleDemo()
    async with app.run_test(size=(100, 40)) as pilot:
        prompt = app.query_one(ConsoleInput)
        prompt.insert("echo one\n\n  \necho two")
        await pilot.press("enter")
        await pilot.pause()
        lines = output_text(app.query_one(ConsoleOutput)).splitlines()
        assert lines[-4:] == ["> echo one", "one", "> echo two", "two"]
        assert prompt.value == ""


async def test_demo_prompt_and_tab_dropdown() -> None:
    app = ConsoleDemo()
    async with app.run_test(size=(100, 40)) as pilot:
        assert app.query_one(ConsoleInput).prompt == "> "
        await pilot.press(*"flood ", "tab")
        await pilot.pause()
        assert app.query_one(CommandAutoComplete).display


async def test_demo_dropdown_stays_on_screen() -> None:
    app = ConsoleDemo()
    async with app.run_test(size=(100, 34)) as pilot:
        await pilot.press("tab")
        await pilot.pause()
        dropdown = app.query_one(CommandAutoComplete)
        assert dropdown.display
        assert dropdown.region.bottom <= app.screen.size.height
        assert dropdown.region.y >= 0
        prompt = app.query_one(ConsoleInput)
        assert dropdown.region.bottom == prompt.cursor_screen_offset.y


async def test_dropdown_returns_below_when_options_shrink() -> None:
    app = ConsoleDemo()
    async with app.run_test(size=(100, 34)) as pilot:
        dropdown = app.query_one(CommandAutoComplete)
        prompt = app.query_one(ConsoleInput)
        # A one-row prompt at the bottom has no room below for a bordered
        # dropdown, so the prompt has a second row.
        prompt.text = "c\n"
        prompt.move_cursor((0, 1))
        await pilot.pause()
        assert dropdown.region.height == 5  # 3 options and the border
        assert dropdown.region.bottom == prompt.cursor_screen_offset.y
        # Change the options while the cursor stays on the same cell.
        prompt.text = "q\n"
        prompt.move_cursor((0, 1))
        await pilot.pause()
        assert dropdown.region.height == 3  # 1 option and the border
        assert dropdown.region.y == prompt.cursor_screen_offset.y + 1


async def test_dropdown_shows_an_option_on_a_tiny_screen() -> None:
    app = ConsoleDemo()
    async with app.run_test(size=(100, 5)) as pilot:
        await pilot.press(*"echo ", "tab")
        await pilot.pause()
        dropdown = app.query_one(CommandAutoComplete)
        assert dropdown.display
        # There is no room for a border, so only the option row is shown.
        assert dropdown.region.height >= 1
        assert dropdown.region.bottom <= app.screen.size.height
        assert dropdown.option_list.content_region.height >= 1


async def test_dropdown_follows_the_cursor_when_the_screen_shrinks() -> None:
    app = ConsoleDemo()
    async with app.run_test(size=(80, 20)) as pilot:
        await pilot.press(*"echo ", "tab")
        await pilot.pause()
        dropdown = app.query_one(CommandAutoComplete)
        prompt = app.query_one(ConsoleInput)
        await pilot.resize_terminal(80, 16)
        await pilot.pause()
        assert dropdown.region.bottom == prompt.cursor_screen_offset.y
        assert dropdown.region.bottom <= app.screen.size.height


async def test_dropdown_follows_the_cursor_when_the_screen_grows() -> None:
    app = ConsoleDemo()
    async with app.run_test(size=(80, 20)) as pilot:
        await pilot.press(*"echo ", "tab")
        await pilot.pause()
        dropdown = app.query_one(CommandAutoComplete)
        prompt = app.query_one(ConsoleInput)
        await pilot.resize_terminal(80, 30)
        await pilot.pause()
        assert dropdown.region.bottom == prompt.cursor_screen_offset.y


async def test_dropdown_stays_on_screen_when_the_screen_narrows() -> None:
    app = ConsoleDemo()
    async with app.run_test(size=(80, 20)) as pilot:
        await pilot.press(*"echo ", "tab")
        await pilot.pause()
        dropdown = app.query_one(CommandAutoComplete)
        await pilot.resize_terminal(20, 20)
        await pilot.pause()
        assert dropdown.region.right <= app.screen.size.width


def test_main_parses_arguments(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    seen: list[ConsoleDemo] = []
    monkeypatch.setattr(ConsoleDemo, "run", lambda self: seen.append(self))
    main(["--log", str(tmp_path / "x.log"), "--max-lines", "7"])
    assert seen[0].max_lines == 7
    assert seen[0].log_path == tmp_path / "x.log"


async def test_basic_example() -> None:
    app = load_example("basic").BasicApp()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        assert "Hello, brave new world" in output_text(app.query_one(ConsoleOutput))


async def test_repl_example(tmp_path: Path) -> None:
    log = tmp_path / "repl.log"
    app = load_example("repl").ReplApp(log)
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.press(*"echo hi", "enter")
        await pilot.pause()
        assert "> echo hi" in output_text(app.query_one(ConsoleOutput))
    assert log.read_text().splitlines()[-2:] == ["> echo hi", "hi"]


async def test_repl_example_splits_lines_and_shows_help(tmp_path: Path) -> None:
    app = load_example("repl").ReplApp(tmp_path / "repl.log")
    async with app.run_test(size=(80, 24)) as pilot:
        app.query_one(ConsoleInput).insert("echo a\necho -h")
        await pilot.press("enter")
        await pilot.pause()
        assert app.is_running
        text = output_text(app.query_one(ConsoleOutput))
        assert "> echo a" in text
        assert "usage: echo" in text


async def test_ansi_stream_example() -> None:
    app = load_example("ansi_stream").AnsiStreamApp()
    async with app.run_test(size=(80, 24)) as pilot:
        for _ in range(50):
            await pilot.pause()
            if "[exit 0]" in output_text(app.query_one(ConsoleOutput)):
                break
        text = output_text(app.query_one(ConsoleOutput))
        assert "line 4" in text
        assert "\x1b" not in text


@pytest.mark.parametrize("value", ["0", "-1"])
def test_main_rejects_max_lines_below_one(value: str) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--max-lines", value])
    assert exc.value.code == 2
