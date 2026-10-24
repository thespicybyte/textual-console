import pytest

from textual_console._tokens import last_token_span, token_span_at


def _last(text: str) -> str:
    return text[slice(*last_token_span(text))]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("open", "open"),
        ("open readme", "readme"),
        ("  open   readme", "readme"),
        ('open "my file.txt" re', "re"),
        ('open "my file.txt"', '"my file.txt"'),
        ('open "my fi', None),
        ("open 'single arg'", "'single arg'"),
        (r"open my\ file", r"my\ file"),
        (r"open my\ file re", "re"),
        ('echo "a \\" b"', '"a \\" b"'),
        ("echo pre'fix x'", "pre'fix x'"),
        ("echo 'a\\' b", "b"),
    ],
)
def test_last_token(text: str, expected: str | None) -> None:
    if expected is None:
        with pytest.raises(ValueError):
            last_token_span(text)
    else:
        assert _last(text) == expected


@pytest.mark.parametrize("text", ["", "ls ", "ls   ", "\t"])
def test_empty_span_at_end(text: str) -> None:
    assert last_token_span(text) == (len(text), len(text))


def test_prefix_is_untouched() -> None:
    text = 'open "my file.txt" re'
    start, _ = last_token_span(text)
    assert text[:start] == 'open "my file.txt" '


def test_unterminated_quote() -> None:
    with pytest.raises(ValueError):
        last_token_span("echo 'abc")


@pytest.mark.parametrize(
    ("text", "cursor", "expected"),
    [
        ("upload --pa foobar", 11, "--pa"),
        ("upload --pa foobar", 18, "foobar"),
        ("upload  foobar", 7, ""),
        ("upload --pa foobar", 9, None),
        ("upload --pa foobar", 7, None),
        ('open "my file" x', 14, '"my file"'),
        ('open "my fi le"', 11, None),
        (r"cp my\ file", 5, None),
        ('go ab "unclosed', 5, "ab"),
    ],
)
def test_token_span_at(text: str, cursor: int, expected: str | None) -> None:
    if expected is None:
        with pytest.raises(ValueError):
            token_span_at(text, cursor)
    else:
        start, end = token_span_at(text, cursor)
        assert end == cursor
        assert text[start:end] == expected


@pytest.mark.parametrize(
    "text",
    ["open", "open readme", 'open "my file.txt" re', "ls ", "", r"open my\ file"],
)
def test_token_span_at_end_matches_last_token_span(text: str) -> None:
    assert token_span_at(text, len(text)) == last_token_span(text)
