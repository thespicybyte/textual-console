"""Shell-style token finder for command completion."""


def last_token_span(text: str) -> tuple[int, int]:
    r"""Find the raw span of the last shell-style token.

    Tokens are separated by unquoted, unescaped whitespace. Single quotes, double
    quotes and backslash escapes are understood, as in a POSIX shell. The span
    covers the token exactly as typed, quotes and escapes included, so the text
    before it is never changed.

    Args:
        text: The command line.

    Returns:
        The ``(start, end)`` character span of the last token. When ``text``
        is empty or ends in unquoted whitespace, the span is empty and sits
        at the end of the text.

    Raises:
        ValueError: If a quote is not closed.

    Example:
        >>> text = 'open "my file.txt" re'
        >>> start, end = last_token_span(text)
        >>> text[start:end]
        're'
        >>> text = r"cp my\ file dest"
        >>> text[slice(*last_token_span(text))]
        'dest'
        >>> last_token_span("ls ")
        (3, 3)
    """
    start = 0
    quote = ""
    in_token = False
    index = 0
    while index < len(text):
        char = text[index]
        if quote:
            if char == quote:
                quote = ""
            elif (
                char == "\\"
                and quote == '"'
                and text[index + 1 : index + 2] in {'"', "\\", "$", "`"}
            ):
                index += 1
        elif char == "\\":
            index += 1
            if not in_token:
                start, in_token = index - 1, True
        elif char in "'\"":
            if not in_token:
                start, in_token = index, True
            quote = char
        elif char.isspace():
            in_token = False
        elif not in_token:
            start, in_token = index, True
        index += 1
    if quote:
        raise ValueError("No closing quotation")
    if not in_token:
        return len(text), len(text)
    return start, len(text)


def token_span_at(text: str, cursor: int) -> tuple[int, int]:
    r"""Find the raw span of the shell-style token that ends at ``cursor``.

    The quoting rules are the same as for :func:`last_token_span`. The span
    always ends at ``cursor``: text after the cursor is never part of it. The
    cursor must be at a token boundary: at the end of the text, or before
    unquoted, unescaped whitespace.

    Args:
        text: The command line.
        cursor: The cursor position in ``text``.

    Returns:
        The ``(start, end)`` character span of the token. When ``text`` before
        the cursor is empty or ends in unquoted whitespace, the span is empty
        and sits at the cursor.

    Raises:
        ValueError: If a quote before the cursor is not closed, or the cursor
            is inside a token.

    Example:
        >>> text = "upload --pa foobar"
        >>> start, end = token_span_at(text, 11)
        >>> text[start:end]
        '--pa'
        >>> token_span_at("upload  foobar", 7)
        (7, 7)
        >>> token_span_at("upload --pa foobar", 9)
        Traceback (most recent call last):
            ...
        ValueError: The cursor is inside a token
    """
    span = last_token_span(text[:cursor])
    if cursor < len(text) and last_token_span(text[: cursor + 1]) != (
        cursor + 1,
        cursor + 1,
    ):
        raise ValueError("The cursor is inside a token")
    return span
