import pytest

from textual_console import CommandHistory


def test_record_and_entries() -> None:
    history = CommandHistory()
    history.record("a")
    history.record("b")
    assert history.entries == ["a", "b"]


def test_entries_is_a_copy() -> None:
    history = CommandHistory(["a"])
    history.entries.append("x")
    assert history.entries == ["a"]


def test_entries_round_trip() -> None:
    assert CommandHistory(CommandHistory(["a", "b", "a"]).entries).entries == [
        "a",
        "b",
        "a",
    ]


def test_skip_duplicate_only_when_adjacent() -> None:
    history = CommandHistory()
    for command in ["a", "a", "b", "a"]:
        history.record(command)
    assert history.entries == ["a", "b", "a"]


def test_keep_duplicates() -> None:
    history = CommandHistory(["a", "a"], skip_duplicates=False)
    assert history.entries == ["a", "a"]


def test_skip_blank() -> None:
    history = CommandHistory(["", "  ", "a"])
    assert history.entries == ["a"]
    assert CommandHistory(["", " "], skip_blank=False).entries == ["", " "]


def test_max_entries_drops_oldest() -> None:
    history = CommandHistory(["a", "b", "c"], max_entries=2)
    assert history.entries == ["b", "c"]
    history.record("d")
    assert history.entries == ["c", "d"]


def test_max_entries_invalid() -> None:
    with pytest.raises(ValueError):
        CommandHistory(max_entries=0)


def test_empty_history() -> None:
    history = CommandHistory()
    assert history.previous("x") is None
    assert history.next() is None


def test_up_stops_at_oldest() -> None:
    history = CommandHistory(["a", "b"])
    assert history.previous("") == "b"
    assert history.previous("") == "a"
    assert history.previous("") is None
    assert history.previous("") is None


def test_down_past_newest_restores_draft() -> None:
    history = CommandHistory(["a", "b"])
    history.previous("draft")
    history.previous("ignored")
    assert history.next() == "b"
    assert history.next() == "draft"
    assert history.next() is None


def test_down_without_walk_does_nothing() -> None:
    assert CommandHistory(["a"]).next() is None


def test_record_ends_walk() -> None:
    history = CommandHistory(["a", "b"])
    history.previous("")
    history.record("c")
    assert history.next() is None
    assert history.previous("") == "c"


def test_blank_record_ends_walk() -> None:
    history = CommandHistory(["a"])
    history.previous("")
    history.record("")
    assert history.next() is None


def test_reset_ends_walk() -> None:
    history = CommandHistory(["a"])
    history.previous("d")
    history.reset()
    assert history.next() is None
    assert history.previous("new") == "a"
    assert history.next() == "new"
