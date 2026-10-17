"""Word and line span helpers for mouse selection.

All spans are ``(start, end)`` pairs of **character** offsets into a line of
plain text, with ``end`` exclusive. Textual's ``Selection`` counts characters,
while Rich's ``Strip`` counts terminal cells. Use :func:`char_to_cell` and
:func:`cell_to_char` to convert between them.
"""

from rich.cells import cell_len

SEPARATORS = frozenset("()[]{}<>'\"`,;|")
"""Punctuation that ends a word, in addition to whitespace."""


def word_span(text: str, x: int, word_chars: str = "") -> tuple[int, int] | None:
    """Find the word that contains a character.

    A word is a run of characters that are not whitespace and not in :data:`SEPARATORS`.
    Paths, URLs, IP addresses, UUIDs, ``user@host`` and ``--flags`` stay in one piece.

    Args:
        text: Plain text of one line.
        x: Character offset into ``text`` (not a cell offset).
        word_chars: Characters to remove from the separator set, so that
            they count as part of a word.

    Returns:
        The ``(start, end)`` character span of the word, or ``None`` if
        ``x`` is outside the text, on whitespace, or on a separator.

    Example:
        >>> word_span("cd /usr/local/bin now", 6)
        (3, 17)
        >>> word_span("run (a, b)", 4) is None
        True
        >>> word_span("f(x)", 0, word_chars="(")
        (0, 3)
    """
    if not 0 <= x < len(text):
        return None
    separators = SEPARATORS - set(word_chars)

    def in_word(char: str) -> bool:
        return not char.isspace() and char not in separators

    if not in_word(text[x]):
        return None
    start = x
    while start > 0 and in_word(text[start - 1]):
        start -= 1
    end = x + 1
    while end < len(text) and in_word(text[end]):
        end += 1
    return start, end


def line_span(text: str) -> tuple[int, int]:
    """Find the content of a line, without trailing whitespace.

    Args:
        text: Plain text of one line.

    Returns:
        The ``(start, end)`` character span of the line. It is ``(0, 0)`` for
        a blank line.

    Example:
        >>> line_span("hello world   ")
        (0, 11)
        >>> line_span("   ")
        (0, 0)
    """
    return 0, len(text.rstrip())


def char_to_cell(text: str, x: int) -> int:
    """Convert a character offset to a cell offset.

    Args:
        text: Plain text of one line.
        x: Character offset into ``text``.

    Returns:
        The number of terminal cells that the first ``x`` characters take.

    Example:
        >>> char_to_cell("ab漢字", 3)
        4
    """
    return cell_len(text[:x])


def cell_to_char(text: str, cell: int) -> int:
    """Convert a cell offset to a character offset.

    A cell in the middle of a wide character maps to that character.

    Args:
        text: Plain text of one line.
        cell: Cell offset from the start of the line.

    Returns:
        The offset of the character that covers ``cell``. It is ``len(text)``
        or more when ``cell`` is at or past the end of the text.

    Example:
        >>> cell_to_char("ab漢字", 3)
        2
        >>> cell_to_char("ab漢字", 4)
        3
        >>> cell_to_char("ab", 5)
        5
    """
    used = 0
    for index, char in enumerate(text):
        used += cell_len(char)
        if used > cell:
            return index
    return len(text) + (cell - used)
