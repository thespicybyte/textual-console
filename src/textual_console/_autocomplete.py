"""Autocomplete for the last word of a command line."""

import shlex
from collections.abc import Callable, Iterable
from typing import Any

from textual import events
from textual.widgets import TextArea
from textual_autocomplete import AutoComplete, DropdownItem, TargetState

from textual_console._console_input import ConsoleInput
from textual_console._tokens import last_token_span

CandidateSource = Callable[[str], Iterable[str | DropdownItem]]
"""A function that gets the full line and returns the possible completions."""


class CommandAutoComplete(AutoComplete):
    """Completes the last word of the cursor's line in the target input.

    ``textual-autocomplete`` only supports ``Input`` targets, so this class
    overrides four of its private methods to work with a :class:`ConsoleInput`.
    The package is pinned to a version these overrides were written for.

    The search string is the last shell-style word. Choosing an option
    replaces only that word and adds a space. The text before it stays as typed,
    and a completion that needs quoting is quoted. Only the cursor's line is
    used: the candidate source gets that line, and a completion changes only
    that line. No suggestions are made when
    the line is empty, ends in a space or a quote, has an unclosed quote, or the
    cursor is not at the end. Nothing is suggested while the target shows a
    value from its history (its ``recalled_value`` attribute).

    The candidates are read in the event loop, so a slow source should cache.

    Example:
        >>> complete = CommandAutoComplete("#prompt", lambda line: ["help", "exit"])
    """

    def __init__(
        self,
        target: ConsoleInput | str,
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
        super().__init__(target, **autocomplete_kwargs)  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
        self._source = candidates

    @property
    def target(self) -> ConsoleInput:  # type: ignore[override]  # pyright: ignore[reportIncompatibleVariableOverride]
        """The resolved target widget."""
        if not isinstance(self._target, str):
            assert isinstance(self._target, ConsoleInput)
            return self._target
        target = self.screen.query_one(self._target)
        assert isinstance(target, ConsoleInput)
        return target

    def _listen_to_messages(self, event: events.Event) -> None:
        super()._listen_to_messages(event)
        if isinstance(event, TextArea.Changed):
            self._handle_target_update()

    def _complete(self, option_index: int) -> None:
        if not self.display or self.option_list.option_count == 0:
            return
        option = self.option_list.get_option_at_index(option_index)
        assert isinstance(option, DropdownItem)
        with self.prevent(TextArea.Changed):
            self.apply_completion(option.value, self._get_target_state())
        self.post_completion()

    def _get_target_state(self) -> TargetState:
        target = self.target
        row, column = target.cursor_location
        return TargetState(text=target.document.get_line(row), cursor_position=column)

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
        recalled = self.target.recalled_value
        if recalled is not None:
            if self.target.value == recalled:
                return []
            self.target.recalled_value = None
        if not self.get_search_string(target_state):
            return []
        return [
            item if isinstance(item, DropdownItem) else DropdownItem(item)
            for item in self._source(target_state.text)
        ]

    def apply_completion(self, value: str, state: TargetState) -> None:
        """Replace the last word of the cursor's line, and add a space."""
        try:
            start, end = last_token_span(state.text)
        except ValueError:
            return
        target = self.target
        row = target.cursor_location[0]
        new = f"{shlex.quote(value)} "
        target.replace(new, (row, start), (row, end))
        target.move_cursor((row, start + len(new)))
