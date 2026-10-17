from __future__ import annotations

import re
from pathlib import Path

from rich.table import Table
from textual.app import App, ComposeResult

from textual_console import ConsoleLog, ConsoleOutput


def test_append_keeps_existing_content(tmp_path: Path) -> None:
    path = tmp_path / "a.log"
    path.write_text("old\n")
    with ConsoleLog(path) as log:
        log.write_lines(["new"])
    assert path.read_text() == "old\nnew\n"


def test_truncate_empties_file(tmp_path: Path) -> None:
    path = tmp_path / "a.log"
    path.write_text("old\n")
    with ConsoleLog(path, truncate=True) as log:
        log.write_lines(["one"])
        log.write_lines(["two"])
    assert path.read_text() == "one\ntwo\n"


def test_nothing_is_created_before_first_write(tmp_path: Path) -> None:
    path = tmp_path / "a.log"
    log = ConsoleLog(path)
    assert not path.exists()
    log.close()
    assert not path.exists()


def test_parent_dirs_created(tmp_path: Path) -> None:
    path = tmp_path / "x" / "y" / "a.log"
    with ConsoleLog(path) as log:
        log.write_lines(["hi"])
    assert path.read_text() == "hi\n"


def test_timestamps(tmp_path: Path) -> None:
    path = tmp_path / "a.log"
    with ConsoleLog(path, timestamps=True) as log:
        log.write_lines(["hi"])
    assert re.fullmatch(
        r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d hi\n", path.read_text()
    )


def test_flush_after_each_write(tmp_path: Path) -> None:
    path = tmp_path / "a.log"
    log = ConsoleLog(path)
    log.write_lines(["one"])
    assert path.read_text() == "one\n"
    log.write_lines(["two"])
    assert path.read_text() == "one\ntwo\n"
    log.close()


def test_strips_ansi(tmp_path: Path) -> None:
    path = tmp_path / "a.log"
    with ConsoleLog(path) as log:
        log.write_lines(["\x1b[31mred\x1b[0m"])
    assert path.read_text() == "red\n"


def test_close_twice_and_closed(tmp_path: Path) -> None:
    log = ConsoleLog(tmp_path / "a.log")
    log.write_lines(["x"])
    assert not log.closed
    log.close()
    log.close()
    assert log.closed
    assert log.path == tmp_path / "a.log"


def test_context_manager_closes(tmp_path: Path) -> None:
    with ConsoleLog(tmp_path / "a.log") as log:
        pass
    assert log.closed


class LogApp(App[None]):
    def __init__(self, **kwargs: object) -> None:
        super().__init__()
        self.kwargs = kwargs
        self.failures: list[ConsoleOutput.LogFailed] = []

    def compose(self) -> ComposeResult:
        yield ConsoleOutput(**self.kwargs)  # type: ignore[arg-type]

    def on_console_output_log_failed(self, message: ConsoleOutput.LogFailed) -> None:
        self.failures.append(message)


async def test_each_line_once_in_order_with_deferred_writes(tmp_path: Path) -> None:
    path = tmp_path / "a.log"
    log = ConsoleLog(path)
    app = LogApp(log=log)
    async with app.run_test() as pilot:
        output = app.query_one(ConsoleOutput)
        output.write("before-size-1")
        output.write("before-size-2")
        await pilot.pause()
        output.write("after")
        await pilot.pause()
    log.close()
    assert path.read_text().splitlines() == ["before-size-1", "before-size-2", "after"]


async def test_cap_lines_reach_log_and_are_pruned(tmp_path: Path) -> None:
    path = tmp_path / "a.log"
    log = ConsoleLog(path)
    app = LogApp(log=log, max_lines=3)
    async with app.run_test() as pilot:
        output = app.query_one(ConsoleOutput)
        await pilot.pause()
        output.write("a")
        output.write("\n".join(f"b{i}" for i in range(10)))
        output.write("c")
        await pilot.pause()
        assert [s.text.rstrip() for s in output.lines] == ["b8", "b9", "c"]
    log.close()
    expected = ["a", *(f"b{i}" for i in range(10)), "c"]
    assert path.read_text().splitlines() == expected


async def test_table_and_raw_ansi(tmp_path: Path) -> None:
    path = tmp_path / "a.log"
    log = ConsoleLog(path)
    app = LogApp(log=log)
    async with app.run_test() as pilot:
        output = app.query_one(ConsoleOutput)
        await pilot.pause()
        table = Table("a", "b")
        table.add_row("1", "2")
        output.write(table)
        output.write("\x1b[31mraw\x1b[0m")
        await pilot.pause()
    log.close()
    text = path.read_text()
    assert "┃ a" in text
    assert "raw\n" in text
    assert "\x1b" not in text


async def test_clear_does_not_touch_file(tmp_path: Path) -> None:
    path = tmp_path / "a.log"
    log = ConsoleLog(path)
    app = LogApp(log=log)
    async with app.run_test() as pilot:
        output = app.query_one(ConsoleOutput)
        await pilot.pause()
        output.write("kept")
        output.clear()
        output.write("next")
        await pilot.pause()
    log.close()
    assert path.read_text().splitlines() == ["kept", "next"]


async def test_log_failure_posts_once_and_app_keeps_running(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("x")
    log = ConsoleLog(blocker / "sub" / "a.log")
    app = LogApp(log=log)
    async with app.run_test() as pilot:
        output = app.query_one(ConsoleOutput)
        await pilot.pause()
        output.write("one")
        output.write("two")
        await pilot.pause()
        assert len(app.failures) == 1
        assert isinstance(app.failures[0].error, OSError)
        assert app.failures[0].control is output
        assert [s.text.rstrip() for s in output.lines] == ["one", "two"]
