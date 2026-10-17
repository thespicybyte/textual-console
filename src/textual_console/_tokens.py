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
