"""Remove terminal escape sequences from text."""

import re

_ESCAPES = re.compile(
    r"""
    \x1b\[[0-?]*[ -/]*[@-~]                  # CSI: colors, cursor moves
    | \x1b\].*?(?:\x07|\x1b\\|\Z)            # OSC: hyperlinks, titles (BEL or ST)
    | \x1b[ -/]*[0-~]                        # other ESC sequences
    | [\x00-\x08\x0a-\x1f\x7f]               # C0 controls and DEL, except tab
    """,
    re.VERBOSE | re.DOTALL,
)


def strip_ansi(text: str) -> str:
    r"""Remove escape sequences and control characters from text.

    This removes CSI sequences (which include SGR color codes), OSC sequences
    ended by BEL or ``ESC \``, other ``ESC`` sequences, and the C0 control
    characters except tab. That includes ``\r`` and ``\n``, so pass one line
    at a time.

    Args:
        text: Text that may hold raw escape codes.

    Returns:
        The plain text.

    Example:
        >>> strip_ansi("\x1b[1;31merror\x1b[0m:\tfailed")
        'error:\tfailed'
        >>> strip_ansi("\x1b]8;;http://x.io\x07link\x1b]8;;\x07")
        'link'
    """
    return _ESCAPES.sub("", text)
