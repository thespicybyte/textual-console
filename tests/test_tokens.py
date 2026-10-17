import pytest

from textual_console._tokens import last_token_span


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
