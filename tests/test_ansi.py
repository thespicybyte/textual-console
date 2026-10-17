import pytest

from textual_console import strip_ansi


@pytest.mark.parametrize(
    ("raw", "plain"),
    [
        ("plain", "plain"),
        ("\x1b[31mred\x1b[0m", "red"),
        ("\x1b[1;4;32mbold\x1b[m", "bold"),
        ("\x1b[38;5;208morange\x1b[0m", "orange"),
        ("\x1b[38;2;10;20;30mtrue\x1b[0m", "true"),
        ("\x1b]8;;http://x.io\x07link\x1b]8;;\x07", "link"),
        ("\x1b]8;;http://x.io\x1b\\link\x1b]8;;\x1b\\", "link"),
        ("\x1b]0;title\x07text", "text"),
        ("a\x1b[2Ab\x1b[10;5Hc\x1b[2Kd", "abcd"),
        ("progress 50%\rprogress 100%", "progress 50%progress 100%"),
        ("a\tb", "a\tb"),
        ("a\x00b\x07c\x08d\x7fe", "abcde"),
        ("a\x1b=b\x1bMc", "abc"),
        ("日本\x1b[1m語", "日本語"),
        ("text\x1b]0;unterminated", "text"),
        ("", ""),
    ],
)
def test_strip_ansi(raw: str, plain: str) -> None:
    assert strip_ansi(raw) == plain
