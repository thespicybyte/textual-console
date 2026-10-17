"""Autocomplete for the last word of a command line."""

import shlex
from collections.abc import Callable, Iterable
from typing import Any

from textual.widgets import Input
from textual_autocomplete import AutoComplete, DropdownItem, TargetState

from textual_console._tokens import last_token_span

CandidateSource = Callable[[str], Iterable[str | DropdownItem]]
"""A function that gets the full line and returns the possible completions."""


class CommandAutoComplete(AutoComplete):
    """Completes the last word of the line in the target input.

    The search string is the last shell-style word. Choosing an option
    replaces only that word and adds a space. The text before it stays as typed,
    and a completion that needs quoting is quoted. No suggestions are made when
    the line is empty, ends in a space or a quote, has an unclosed quote, or the
    cursor is not at the end. Nothing is suggested while the target shows a
    value from its history (its ``recalled_value`` attribute).

    The candidates are read in the event loop, so a slow source should cache.

    Example:
        >>> complete = CommandAutoComplete("#prompt", lambda line: ["help", "exit"])
    """

    def __init__(
        self,
        target: Input | str,
        candidates: CandidateSource,
        **autocomplete_kwargs: Any,  # noqa: ANN401
    ) -> None:
        """Create the autocomplete.

        Args:
            target: The input to complete, or a selector for it.
            candidates: A function that gets the full line and returns the
                possible completions for the last word. They are filtered
                against that word.
            **autocomplete_kwargs: Other arguments for
                :class:`textual_autocomplete.AutoComplete`.
        """
        super().__init__(target, **autocomplete_kwargs)
        self._source = candidates

    def get_search_string(self, target_state: TargetState) -> str:
        """Return the last word of the line, or an empty string for no search."""
        text = target_state.text
        if (
            not text
            or target_state.cursor_position != len(text)
            or text[-1].isspace()
            or text[-1] in "'\""
        ):
            return ""
        try:
            start, end = last_token_span(text)
            words = shlex.split(text[start:end])
        except ValueError:
            return ""
        return words[0] if words else ""

    def get_candidates(self, target_state: TargetState) -> list[DropdownItem]:
        """Return the options for the current line."""
        recalled: str | None = getattr(self.target, "recalled_value", None)
        if recalled is not None:
            if target_state.text == recalled:
                return []
            self.target.recalled_value = None  # type: ignore[attr-defined]
        if not self.get_search_string(target_state):
            return []
        return [
            item if isinstance(item, DropdownItem) else DropdownItem(item)
            for item in self._source(target_state.text)
        ]

    def apply_completion(self, value: str, state: TargetState) -> None:
        """Replace the last word with the chosen value, and add a space."""
        try:
            start, _ = last_token_span(state.text)
        except ValueError:
            return
        result = f"{state.text[:start]}{shlex.quote(value)} "
        self.target.value = result
        self.target.cursor_position = len(result)
