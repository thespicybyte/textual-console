"""Autocomplete for the last word of a command line."""

import shlex
from collections.abc import Callable, Iterable
from operator import itemgetter
from typing import Any

from rich.cells import cell_len
from textual import events
from textual.content import Content
from textual.geometry import Offset
from textual.widgets import TextArea
from textual.widgets.option_list import Option
from textual_autocomplete import (
    AutoComplete,
    DropdownItem,
    DropdownItemHit,
    TargetState,
)

from textual_console._console_input import ConsoleInput
from textual_console._tokens import last_token_span

CandidateSource = Callable[[str], Iterable[str | DropdownItem]]
"""A function that gets the cursor's line and returns the possible completions."""


def _width(prefix: Content | None, main: Content) -> int:
    return cell_len(main.plain) + (cell_len(prefix.plain) if prefix else 0)


class CommandItem(DropdownItem):
    """A completion with a dim help text in a second column.

    Only ``value`` is applied when the item is chosen, and only ``value`` is
    matched against the typed word. ``help`` is just shown.

    Example:
        >>> item = CommandItem("open", "Open a file")
        >>> item.value, item.help
        ('open', 'Open a file')
    """

    def __init__(
        self,
        value: str | Content,
        help: str = "",  # noqa: A002
        prefix: str | Content | None = None,
        *,
        id: str | None = None,  # noqa: A002
        disabled: bool = False,
        column: int = 0,
    ) -> None:
        """Create the item.

        Args:
            value: The text that completes the word.
            help: A short description shown after the value, dimmed.
            prefix: Text shown before the value, such as an icon.
            id: The option ID.
            disabled: Whether the option cannot be chosen.
            column: The cell where the help starts. The dropdown sets it so the
                help of all rows lines up. The help always follows the value by
                at least two cells.
        """
        main = Content(value) if isinstance(value, str) else value
        left = Content(prefix) if isinstance(prefix, str) else prefix
        parts: list[Content | str | tuple[str, str]] = []
        if left:
            parts.append(left)
        parts.append(main)
        if help:
            gap = max(2, column - _width(left, main))
            parts.extend([" " * gap, (help, "dim")])
        Option.__init__(self, Content.assemble(*parts), id, disabled)
        self.main = main
        self.prefix = left
        self.help = help
        """The help text."""


class CompletionHint(DropdownItem):
    """A dim italic row that tells the user what to type.

    A hint is always shown first. It is never matched, filtered or applied,
    and Tab and Enter skip it. When the dropdown holds only hints, Enter
    submits as usual and Tab does nothing.

    Example:
        >>> CompletionHint("FILE: the file to open").value
        'FILE: the file to open'
    """

    def __init__(self, text: str | Content) -> None:
        """Create the hint.

        Args:
            text: The text to show.
        """
        content = Content(text) if isinstance(text, str) else text
        super().__init__(content.stylize("dim italic"), disabled=True)


class CommandAutoComplete(AutoComplete):
    """Completes the last word of the cursor's line in the target input.

    ``textual-autocomplete`` only supports ``Input`` targets, so this class
    overrides some of its private methods to work with a :class:`ConsoleInput`.
    The package is pinned to a version these overrides were written for.

    The search string is the last shell-style word. Choosing an option
    replaces only that word and adds a space. The text before it stays as typed,
    and a completion that needs quoting is quoted. Only the cursor's line is
    used: the candidate source gets that line, and a completion changes only
    that line. No suggestions are made when
    the line is empty, ends in a space or a quote, has an unclosed quote, or the
    cursor is not at the end. Nothing is suggested while the target shows a
    value from its history (its ``recalled_value`` attribute).

    Tab with the dropdown closed asks for the candidates of the current word,
    which can be empty, and opens the dropdown, also after a space. A single
    candidate is applied at once. With no candidates, Tab does what the
    input does. The candidate source can return :class:`CommandItem` rows,
    which show help text, and :class:`CompletionHint` rows, which show what to
    type.

    Enter accepts the highlighted option only when it changes the word. When
    the word already equals the option, Enter submits the line. Tab always
    accepts.

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
            candidates: A function that gets the cursor's line and returns the
                possible completions for the last word. They are filtered
                against that word.
            **autocomplete_kwargs: Other arguments for
                :class:`textual_autocomplete.AutoComplete`.
        """
        super().__init__(target, **autocomplete_kwargs)  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
        self._source = candidates
        self._explicit = False

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
        # Upstream opens a hidden dropdown on Down and stops the key. Here Down
        # must reach the input, to move between rows and walk the history.
        if isinstance(event, events.Key):
            if event.key == "down" and not self.display:
                return
            if event.key == "tab" and not self.display and self._open_with_tab(event):
                return
            if self.display and self._only_hints():
                self._keys_with_only_hints(event)
                return
            if event.key == "enter" and self.display and self._highlighted_is_typed():
                # Accepting would not change the word, so Enter submits.
                self.action_hide()
                return
        super()._listen_to_messages(event)
        if isinstance(event, TextArea.Changed):
            self._handle_target_update()
        elif isinstance(event, events.Key) and event.key in {"up", "down"}:
            self._skip_hint(1 if event.key == "down" else -1)

    @staticmethod
    def _is_selectable(option: Option) -> bool:
        return (
            isinstance(option, DropdownItem)
            and not isinstance(option, CompletionHint)
            and not option.disabled
        )

    def _selectable(self) -> list[DropdownItem]:
        return [
            option
            for option in self.option_list.options
            if isinstance(option, DropdownItem) and self._is_selectable(option)
        ]

    def _only_hints(self) -> bool:
        return self.option_list.option_count > 0 and not self._selectable()

    def _keys_with_only_hints(self, event: events.Key) -> None:
        if event.key == "escape":
            event.prevent_default()
            event.stop()
            self.action_hide()
        elif event.key == "tab":
            event.prevent_default()
            event.stop()
        elif event.key == "enter":
            self.action_hide()

    def _highlighted_is_typed(self) -> bool:
        option_list = self.option_list
        highlighted = option_list.highlighted
        if highlighted is None or not option_list.option_count:
            return False
        option = option_list.get_option_at_index(highlighted)
        return (
            isinstance(option, DropdownItem)
            and self._is_selectable(option)
            and option.value == self.get_search_string(self._get_target_state())
        )

    def _skip_hint(self, step: int) -> None:
        option_list = self.option_list
        highlighted = option_list.highlighted
        if highlighted is None or option_list.option_count < 2:
            return
        count = option_list.option_count
        for _ in range(count):
            if self._is_selectable(option_list.get_option_at_index(highlighted)):
                break
            highlighted = (highlighted + step) % count
        option_list.highlighted = highlighted

    def _open_with_tab(self, event: events.Key) -> bool:
        """Open the dropdown for the current word. Return whether Tab was used."""
        target = self.target
        if target.read_only:
            return False
        row, column = target.cursor_location
        line = target.document.get_line(row)
        if column != len(line):
            return False
        try:
            last_token_span(line)
        except ValueError:
            return False
        self._explicit = True
        try:
            self._handle_target_update()
        finally:
            self._explicit = False
        selectable = self._selectable()
        if not self.option_list.option_count:
            self.action_hide()
            return False
        event.prevent_default()
        event.stop()
        if len(selectable) == 1:
            with self.prevent(TextArea.Changed):
                self.apply_completion(selectable[0].value, self._get_target_state())
            self.post_completion()
        return True

    def _complete(self, option_index: int) -> None:
        if not self.display or self.option_list.option_count == 0:
            return
        option = self.option_list.get_option_at_index(option_index)
        assert isinstance(option, DropdownItem)
        if not self._is_selectable(option):
            return
        with self.prevent(TextArea.Changed):
            self.apply_completion(option.value, self._get_target_state())
        self.post_completion()

    def _align_to_target(self) -> None:
        # The base class only moves the dropdown sideways, so a prompt at the
        # bottom of the screen hides it. Put it above the cursor if it does
        # not fit below. The options are rebuilt after this call, so their
        # height is only known after the next refresh.
        super()._align_to_target()
        self._place_vertically()
        self.call_after_refresh(self._place_vertically)

    def _place_vertically(self) -> None:
        offset = self.absolute_offset
        if offset is None or not self.display:
            return
        _, y = self.target.cursor_screen_offset
        height = self.option_list.outer_size.height
        fits_below = y + 1 + height <= self.screen.size.height
        row = y - height if not fits_below and y - height >= 0 else y + 1
        self.absolute_offset = Offset(offset.x, row)

    def _get_target_state(self) -> TargetState:
        target = self.target
        row, column = target.cursor_location
        return TargetState(text=target.document.get_line(row), cursor_position=column)

    def get_search_string(self, target_state: TargetState) -> str:
        """Return the last word of the line, or an empty string for no search."""
        text = target_state.text
        if not text or target_state.cursor_position != len(text):
            return ""
        if text[-1].isspace() or (not self._explicit and text[-1] in "'\""):
            return ""
        try:
            start, end = last_token_span(text)
            words = shlex.split(text[start:end])
        except ValueError:
            return ""
        return words[0] if words else ""

    def get_candidates(self, target_state: TargetState) -> list[DropdownItem]:
        """Return the options for the current line."""
        if not self._explicit:
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
        if target.read_only:
            return
        row = target.cursor_location[0]
        new = f"{shlex.quote(value)} "
        target.replace(new, (row, start), (row, end))
        target.move_cursor((row, start + len(new)))

    def get_matches(
        self,
        target_state: TargetState,
        candidates: list[DropdownItem],
        search_string: str,
    ) -> list[DropdownItem]:
        """Filter the candidates, keep help texts, and put hints first."""
        hints = [item for item in candidates if isinstance(item, CompletionHint)]
        others = [item for item in candidates if not isinstance(item, CompletionHint)]
        if not search_string:
            return hints + self._align_help(others)
        scored: list[tuple[DropdownItem, float]] = []
        for item in others:
            score, offsets = self.match(search_string, item.value)
            if score <= 0:
                continue
            main = self.apply_highlights(item.main, offsets)
            if isinstance(item, CommandItem):
                hit: DropdownItem = CommandItem(
                    main, item.help, item.prefix, id=item.id, disabled=item.disabled
                )
            else:
                hit = DropdownItemHit(
                    main, item.prefix, id=item.id, disabled=item.disabled
                )
            scored.append((hit, score))
        scored.sort(key=itemgetter(1), reverse=True)
        return hints + self._align_help([item for item, _ in scored])

    @staticmethod
    def _align_help(items: list[DropdownItem]) -> list[DropdownItem]:
        """Start the help text of all command items in the same cell."""
        commands = [item for item in items if isinstance(item, CommandItem)]
        column = max((_width(c.prefix, c.main) + 2 for c in commands), default=0)
        return [
            CommandItem(
                item.main,
                item.help,
                item.prefix,
                id=item.id,
                disabled=item.disabled,
                column=column,
            )
            if isinstance(item, CommandItem)
            else item
            for item in items
        ]

    def should_show_dropdown(self, search_string: str) -> bool:
        """Decide whether to show the dropdown.

        Hints do not count as candidates. They are shown only with a candidate,
        or when the user pressed Tab.
        """
        if self._explicit:
            return self.option_list.option_count > 0
        selectable = self._selectable()
        if not search_string or not selectable:
            return False
        if len(selectable) == 1:
            return selectable[0].value != search_string
        return True

    def _rebuild_options(self, target_state: TargetState, search_string: str) -> None:
        super()._rebuild_options(target_state, search_string)
        self._skip_hint(1)
