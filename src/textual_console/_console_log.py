"""Plain-text transcript of a console."""

from __future__ import annotations

import os
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import IO, Self

from textual_console._ansi import strip_ansi


class ConsoleLog:
    r"""A plain-text transcript file.

    The file opens on the first write, and parent directories are created.
    Every line goes through :func:`~textual_console.strip_ansi`, and each
    :meth:`write_lines` call flushes, so the file is current while the app
    runs and after a crash.

    Example:
        >>> import tempfile
        >>> with tempfile.TemporaryDirectory() as folder:
        ...     with ConsoleLog(Path(folder) / "sub" / "session.log") as log:
        ...         log.write_lines(["\x1b[31mred\x1b[0m", "plain"])
        ...     print((Path(folder) / "sub" / "session.log").read_text(), end="")
        red
        plain
    """

    def __init__(
        self,
        path: str | os.PathLike[str],
        *,
        truncate: bool = False,
        timestamps: bool = False,
        encoding: str = "utf-8",
    ) -> None:
        """Create a transcript. No file is touched until the first write.

        Args:
            path: Path of the file.
            truncate: Empty an existing file on the first write. By default
                lines are appended to it.
            timestamps: Start each line with an ISO-8601 local time.
            encoding: Encoding of the file. Characters that it cannot hold are
                replaced.
        """
        self._path = Path(path)
        self._truncate = truncate
        self._timestamps = timestamps
        self._encoding = encoding
        self._file: IO[str] | None = None
        self._closed = False

    @property
    def path(self) -> Path:
        """Path of the transcript file."""
        return self._path

    @property
    def closed(self) -> bool:
        """Whether :meth:`close` was called."""
        return self._closed

    def write_lines(self, lines: Iterable[str]) -> None:
        """Write lines to the file, and flush.

        Args:
            lines: Lines of text, without line endings.

        Raises:
            OSError: If the file cannot be opened or written.
            ValueError: If the log is closed.
        """
        if self._closed:
            msg = "write to a closed ConsoleLog"
            raise ValueError(msg)
        if self._file is None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._file = self._path.open(
                "w" if self._truncate else "a",
                encoding=self._encoding,
                errors="replace",
                newline="\n",
            )
        for line in lines:
            text = strip_ansi(line)
            if self._timestamps:
                stamp = datetime.now().astimezone().isoformat(timespec="seconds")
                text = f"{stamp} {text}"
            self._file.write(text + "\n")
        self._file.flush()

    def close(self) -> None:
        """Close the file. It is safe to call this more than once."""
        self._closed = True
        file, self._file = self._file, None
        if file is not None:
            file.close()

    def __enter__(self) -> Self:
        """Return the log."""
        return self

    def __exit__(self, *exc_info: object) -> None:
        """Close the log."""
        self.close()
