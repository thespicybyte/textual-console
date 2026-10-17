import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

from textual_console import ConsoleInput, ConsoleOutput
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
