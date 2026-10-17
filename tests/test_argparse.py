import argparse
import logging

import pytest
from textual_autocomplete import DropdownItem

from textual_console import (
    ArgparseCompleter,
    CommandItem,
    CompletionHint,
    set_completer,
)


def values(items: list[DropdownItem]) -> list[str]:
    return [item.value for item in items if not isinstance(item, CompletionHint)]


def hints(items: list[DropdownItem]) -> list[str]:
    return [item.value for item in items if isinstance(item, CompletionHint)]


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="open", description="Open a file.\nMore.")
    parser.add_argument("path", help="the file to open")
    parser.add_argument("--mode", "-m", choices=["r", "w", "a"], help="How to open")
    parser.add_argument("-v", "--verbose", action="count", help="More output")
    parser.add_argument("--tag", action="append", help="A tag")
    parser.add_argument("--hidden", help=argparse.SUPPRESS)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--fast", action="store_true", help="Go fast")
    group.add_argument("--slow", action="store_true", help="Go slow")
    return parser


@pytest.fixture
def complete() -> ArgparseCompleter:
    return ArgparseCompleter({"open": make_parser()})


def test_command_names_with_help(complete: ArgparseCompleter) -> None:
    items = complete("")
    assert values(items) == ["open"]
    assert isinstance(items[0], CommandItem)
    assert items[0].help == "Open a file."


def test_unknown_command(complete: ArgparseCompleter) -> None:
    assert complete("nope --") == []


def test_unused_options_with_help(complete: ArgparseCompleter) -> None:
    items = complete("open --")
    assert values(items) == [
        "--mode",
        "-m",
        "-v",
        "--verbose",
        "--tag",
        "--fast",
        "--slow",
    ]
    assert {i.value: i.help for i in items if isinstance(i, CommandItem)}[
        "--mode"
    ] == "How to open"
    assert "--hidden" not in values(items)
    assert "--help" not in values(items)
    assert hints(items) == []


def test_used_options_disappear(complete: ArgparseCompleter) -> None:
    items = values(complete("open --mode r -"))
    assert "--mode" not in items
    assert "-m" not in items


def test_append_and_count_repeat(complete: ArgparseCompleter) -> None:
    items = values(complete("open -v --tag x --tag y -"))
    assert "--verbose" in items
    assert "--tag" in items


def test_mutually_exclusive(complete: ArgparseCompleter) -> None:
    items = values(complete("open --fast -"))
    assert "--slow" not in items
    assert "--fast" not in items


def test_help_option() -> None:
    parser = make_parser()
    assert "--help" not in values(ArgparseCompleter({"open": parser})("open -"))
    shown = values(ArgparseCompleter({"open": parser}, show_help_option=True)("open -"))
    assert {"-h", "--help"} <= set(shown)


def test_option_choices_and_hint(complete: ArgparseCompleter) -> None:
    items = complete("open --mode ")
    assert values(items) == ["r", "w", "a"]
    assert hints(items) == ["MODE: How to open"]
    assert values(complete("open -m ")) == ["r", "w", "a"]


def test_option_equals_prefix(complete: ArgparseCompleter) -> None:
    assert values(complete("open --mode=")) == ["--mode=r", "--mode=w", "--mode=a"]
    assert values(complete("open --mode=w")) == ["--mode=r", "--mode=w", "--mode=a"]


def test_value_consumed_then_positional(complete: ArgparseCompleter) -> None:
    items = complete("open --mode r ")
    assert values(items) == []
    assert hints(items) == ["path: the file to open"]


def test_positional_after_taken_is_exhausted(complete: ArgparseCompleter) -> None:
    assert complete("open file.txt ") == []


def test_no_hints() -> None:
    complete = ArgparseCompleter({"open": make_parser()}, hints=False)
    assert hints(complete("open --mode ")) == []
    assert hints(complete("open ")) == []


def positional_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="p")
    parser.add_argument("pair", nargs=2, choices=["a", "b"])
    parser.add_argument("maybe", nargs="?", choices=["x"])
    parser.add_argument("rest", nargs="*", choices=["y", "z"])
    return parser


def test_positional_nargs() -> None:
    complete = ArgparseCompleter({"p": positional_parser()}, hints=False)
    assert values(complete("p ")) == ["a", "b"]
    assert values(complete("p a ")) == ["a", "b"]
    assert values(complete("p a b ")) == ["x"]
    assert values(complete("p a b x ")) == ["y", "z"]
    assert values(complete("p a b x y z ")) == ["y", "z"]


def test_plus_nargs_and_option_values() -> None:
    parser = argparse.ArgumentParser(prog="p")
    parser.add_argument("--files", nargs="+", choices=["f1", "f2"])
    parser.add_argument("--pair", nargs=2, choices=["1", "2"])
    parser.add_argument("last", choices=["end"])
    complete = ArgparseCompleter({"p": parser}, hints=False)
    assert values(complete("p --files f1 ")) == ["f1", "f2"]
    assert values(complete("p --files f1 --")) == ["--pair"]
    assert values(complete("p --pair 1 ")) == ["1", "2"]
    assert values(complete("p --pair 1 2 ")) == ["end"]


def test_double_dash_positionals_only() -> None:
    parser = argparse.ArgumentParser(prog="p")
    parser.add_argument("--opt")
    parser.add_argument("word", choices=["-x", "y"])
    complete = ArgparseCompleter({"p": parser}, hints=False)
    assert values(complete("p --")) == ["--opt"]
    assert values(complete("p -- ")) == ["-x", "y"]
    assert values(complete("p -- -")) == ["-x", "y"]


def make_root() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="git")
    root.add_argument("--debug", action="store_true", help="Debug")
    sub = root.add_subparsers(dest="command", metavar="COMMAND", help="the command")
    remote = sub.add_parser("remote", aliases=["rm"], help="Manage remotes")
    remote.add_argument("--verbose", action="store_true", help="Talk more")
    nested = remote.add_subparsers(dest="action")
    add = nested.add_parser("add", help="Add one")
    add.add_argument("name", help="remote name")
    nested.add_parser("show", help="Show one")
    sub.add_parser("status", help="Show status")
    return root


def test_root_parser_subcommands() -> None:
    complete = ArgparseCompleter(make_root())
    items = complete("")
    assert values(items) == ["remote", "rm", "status"]
    assert hints(items) == ["COMMAND: the command"]
    helps = {i.value: i.help for i in items if isinstance(i, CommandItem)}
    assert helps == {
        "remote": "Manage remotes",
        "rm": "Manage remotes",
        "status": "Show status",
    }
    assert values(complete("--")) == ["--debug"]


def test_subcommand_alias_and_nested() -> None:
    complete = ArgparseCompleter(make_root())
    assert values(complete("remote --")) == ["--verbose"]
    assert values(complete("rm --")) == ["--verbose"]
    assert values(complete("remote ")) == ["add", "show"]
    assert values(complete("rm --verbose add ")) == []
    assert hints(complete("rm add ")) == ["name: remote name"]
    assert values(complete("status --")) == []
    assert complete("bogus ") == []


def test_mapping_with_subparsers() -> None:
    complete = ArgparseCompleter({"git": make_root()})
    assert values(complete("git ")) == ["remote", "rm", "status"]


def test_live_mapping() -> None:
    parsers: dict[str, argparse.ArgumentParser] = {}
    complete = ArgparseCompleter(parsers)
    assert complete("") == []
    parsers["open"] = make_parser()
    assert values(complete("")) == ["open"]
    assert "--mode" in values(complete("open --m"))


def test_set_completer_and_plain_attribute() -> None:
    parser = argparse.ArgumentParser(prog="p")
    action = parser.add_argument("--name")
    assert set_completer(action, lambda word: ["ann", "bob"]) is action
    other = parser.add_argument("target")
    other.completer = lambda word: [CommandItem("srv", "a server"), "db"]  # type: ignore[attr-defined]
    complete = ArgparseCompleter({"p": parser})
    items = complete("p --name ")
    assert values(items) == ["ann", "bob"]
    assert hints(items) == ["NAME"]
    assert values(complete("p --name=a")) == ["--name=ann", "--name=bob"]
    items = complete("p ")
    assert values(items) == ["srv", "db"]
    assert isinstance(items[-2], CommandItem) and items[-2].help == "a server"


def test_completer_gets_current_word() -> None:
    seen: list[str] = []

    def record(word: str) -> list[str]:
        seen.append(word)
        return []

    parser = argparse.ArgumentParser(prog="p")
    set_completer(parser.add_argument("--name"), record)
    ArgparseCompleter({"p": parser})("p --name=bo")
    ArgparseCompleter({"p": parser})("p --name bo")
    assert seen == ["bo", "bo"]


def test_failing_completer(caplog: pytest.LogCaptureFixture) -> None:
    parser = argparse.ArgumentParser(prog="p")

    def broken(word: str) -> list[str]:
        raise RuntimeError("boom")

    set_completer(parser.add_argument("--name"), broken)
    complete = ArgparseCompleter({"p": parser}, hints=False)
    with caplog.at_level(logging.ERROR):
        assert complete("p --name ") == []
    assert "boom" in caplog.text


def test_hint_for_free_form_value() -> None:
    parser = argparse.ArgumentParser(prog="p")
    parser.add_argument(
        "--file", metavar="FILE", help="the file (default: %(default)s)"
    )
    items = ArgparseCompleter({"p": parser})("p --file ")
    assert items and hints(items) == ["FILE: the file (default: None)"]
    assert values(items) == []


def test_unclosed_quote_gives_nothing(complete: ArgparseCompleter) -> None:
    assert complete('open "my fi') == []
    assert complete("open --mode 'r") == []
    assert complete("open \\") == []


def test_quoted_earlier_words() -> None:
    complete = ArgparseCompleter({"open": make_parser()}, hints=False)
    assert "--mode" in values(complete('open "my file" -'))
    assert values(complete('open "my file" ')) == []


def test_short_clusters_and_inline_values(complete: ArgparseCompleter) -> None:
    assert "-v" in values(complete("open -vv -"))
    assert "-m" not in values(complete("open -mr -"))
    assert "--mode" not in values(complete("open --mode=r -"))
    assert values(complete("open -vm ")) == ["r", "w", "a"]


def test_never_exits_or_prints(
    complete: ArgparseCompleter, capsys: pytest.CaptureFixture[str]
) -> None:
    for line in ["open --bogus ", "open --mode", "open -h ", "open --mode x y z ", "-"]:
        complete(line)
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""


def test_append_const_extend_and_hidden_store_actions() -> None:
    parser = argparse.ArgumentParser(prog="p")
    parser.add_argument("--add", action="append_const", const=1)
    parser.add_argument("--ext", action="extend", nargs="+")
    parser.add_argument("--flag", action="store_true")
    parser.add_argument("--const", action="store_const", const=1)
    complete = ArgparseCompleter({"p": parser}, hints=False)
    assert values(complete("p --")) == ["--add", "--ext", "--flag", "--const"]
    shown = values(complete("p --add --ext a b --flag --const --"))
    assert shown == ["--add", "--ext"]


def test_plus_positional() -> None:
    parser = argparse.ArgumentParser(prog="p")
    parser.add_argument("names", nargs="+", choices=["a", "b"])
    parser.add_argument("--opt")
    complete = ArgparseCompleter({"p": parser}, hints=False)
    assert values(complete("p ")) == ["a", "b"]
    assert values(complete("p a b ")) == ["a", "b"]
    assert values(complete("p a --opt x ")) == ["a", "b"]


def test_subcommand_help_falls_back_to_description() -> None:
    root = argparse.ArgumentParser(prog="r")
    sub = root.add_subparsers()
    sub.add_parser("one", description="Described one.\nMore.")
    sub.add_parser("two", help="Helped two", description="ignored")
    items = ArgparseCompleter(root, hints=False)("")
    helps = {i.value: i.help for i in items if isinstance(i, CommandItem)}
    assert helps == {"one": "Described one.", "two": "Helped two"}


def test_broken_internals_degrade(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def broken(parser: argparse.ArgumentParser) -> list[argparse.Action]:
        raise AttributeError("_actions")

    monkeypatch.setattr("textual_console._argparse._actions", broken)
    complete = ArgparseCompleter({"open": make_parser()})
    assert values(complete("")) == ["open"]
    with caplog.at_level(logging.ERROR):
        assert complete("open --") == []
    assert "internals" in caplog.text
    assert ArgparseCompleter(make_root())("") == []
