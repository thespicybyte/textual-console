"""Command history with up/down recall."""

from collections.abc import Iterable


class CommandHistory:
    """Remembers submitted commands and walks back and forth through them.

    This class is plain Python and does not import Textual. Call :meth:`record`
    after each submit, :meth:`previous` for the up key and :meth:`next` for the
    down key.

    Example:
        >>> history = CommandHistory(["ls", "pwd"])
        >>> history.previous("par")
        'pwd'
        >>> history.previous("par")
        'ls'
        >>> history.previous("par") is None
        True
        >>> history.next()
        'pwd'
        >>> history.next()
        'par'
    """

    def __init__(
        self,
        entries: Iterable[str] = (),
        *,
        max_entries: int | None = None,
        skip_duplicates: bool = True,
        skip_blank: bool = True,
    ) -> None:
        """Create a history.

        Args:
            entries: Earlier commands, oldest first. They follow the same rules as
                :meth:`record`.
            max_entries: Keep at most this many entries, and drop the oldest
                first. ``None`` means no limit.
            skip_duplicates: Do not record a command that equals the newest entry.
            skip_blank: Do not record a command that is empty or only whitespace.

        Raises:
            ValueError: If ``max_entries`` is less than 1.
        """
        if max_entries is not None and max_entries < 1:
            raise ValueError("max_entries must be at least 1")
        self._max_entries = max_entries
        self._skip_duplicates = skip_duplicates
        self._skip_blank = skip_blank
        self._entries: list[str] = []
        self._index: int | None = None
        self._draft = ""
        for entry in entries:
            self.record(entry)

    @property
    def entries(self) -> list[str]:
        """A copy of the recorded commands, oldest first."""
        return list(self._entries)

    def record(self, command: str) -> None:
        """Record a submitted command and end the current walk through history.

        Args:
            command: The command text.
        """
        self.reset()
        if self._skip_blank and not command.strip():
            return
        if self._skip_duplicates and self._entries and self._entries[-1] == command:
            return
        self._entries.append(command)
        if self._max_entries is not None and len(self._entries) > self._max_entries:
            del self._entries[: len(self._entries) - self._max_entries]

    def previous(self, draft: str) -> str | None:
        """Move to the previous (older) entry, as for the up key.

        Args:
            draft: The text typed so far. It is saved on the first call of a
                walk and returned by :meth:`next` when the walk passes the
                newest entry.

        Returns:
            The entry to show, or ``None`` if there is nothing to change (the
            history is empty or the walk is at the oldest entry).
        """
        if not self._entries:
            return None
        if self._index is None:
            self._draft = draft
            self._index = len(self._entries) - 1
        elif self._index > 0:
            self._index -= 1
        else:
            return None
        return self._entries[self._index]

    def next(self) -> str | None:
        """Move to the next (newer) entry, as for the down key.

        Returns:
            The entry to show. Past the newest entry, it is the saved draft and
            the walk ends. It is ``None`` if no walk is in progress.
        """
        if self._index is None:
            return None
        if self._index + 1 < len(self._entries):
            self._index += 1
            return self._entries[self._index]
        self._index = None
        return self._draft

    def reset(self) -> None:
        """End the current walk through history and forget the saved draft."""
        self._index = None
        self._draft = ""
