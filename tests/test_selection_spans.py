import pytest

from textual_console._selection import cell_to_char, char_to_cell, line_span, word_span


def _word(text: str, x: int, word_chars: str = "") -> str | None:
    span = word_span(text, x, word_chars)
    return None if span is None else text[slice(*span)]


@pytest.mark.parametrize(
    ("text", "x", "expected"),
    [
        ("cat /usr/local/bin/x now", 8, "/usr/local/bin/x"),
        ("see https://a.io/p?q=1&r=2 ok", 10, "https://a.io/p?q=1&r=2"),
        ("ping 10.0.0.1 -c 3", 7, "10.0.0.1"),
        (
            "id 123e4567-e89b-12d3-a456-426614174000.",
            5,
            "123e4567-e89b-12d3-a456-426614174000.",
        ),
        ("ssh user@host --flag=1", 6, "user@host"),
        ("ssh user@host --flag=1", 16, "--flag=1"),
        ("f(arg, other)", 3, "arg"),
        ('say "hi there"', 6, "hi"),
        ("日本語 テスト", 1, "日本語"),
        ("abc", 0, "abc"),
        ("abc", 2, "abc"),
    ],
)
def test_word_span(text: str, x: int, expected: str) -> None:
    assert _word(text, x) == expected


@pytest.mark.parametrize(
    ("text", "x"),
    [("a  b", 1), ("a (b)", 2), ("a,b", 1), ("abc", 3), ("abc", -1), ("", 0)],
)
def test_word_span_none(text: str, x: int) -> None:
    assert word_span(text, x) is None


def test_word_chars_removes_separators() -> None:
    assert _word("f(x)", 0) == "f"
    assert _word("f(x)", 0, word_chars="()") == "f(x)"


def test_line_span() -> None:
    assert line_span("hello   ") == (0, 5)
    assert line_span("  indented  ") == (0, 10)
    assert line_span("") == (0, 0)
    assert line_span("   ") == (0, 0)


def test_cell_conversion_wide_characters() -> None:
    text = "a漢b"
    assert [char_to_cell(text, x) for x in range(4)] == [0, 1, 3, 4]
    assert [cell_to_char(text, c) for c in range(5)] == [0, 1, 1, 2, 3]
    assert cell_to_char(text, 6) == 5
