"""Command prompt widget with history."""

from typing import Any

from textual import events, on
from textual.actions import SkipAction
from textual.binding import Binding
from textual.widgets import Input

from textual_console._history import CommandHistory


class ConsoleInput(Input):
    """A single-line command prompt with history, a quiet Tab and middle-click paste.

    The up and down keys walk through the command history. Tab does not move
    focus unless ``tab_moves_focus`` is set. When the user submits, the
    command is recorded in the history and the input is cleared. A middle
    click pastes the text selected in the output, or else the app clipboard.

    The widget does not import any autocomplete code. An autocomplete widget
    can read :attr:`recalled_value` to stay closed while the user walks through
    the history.

    Example:
        >>> prompt = ConsoleInput(placeholder="command")
        >>> prompt.history.entries
        []
    """

    BINDINGS = [
        Binding("up", "history_previous", show=False),
        Binding("down", "history_next", show=False),
        Binding("tab", "tab", show=False),
    ]

    def __init__(
        self,
        value: str | None = None,
        placeholder: str = "",
        *,
        history: CommandHistory | None = None,
        clear_on_submit: bool = True,
        middle_click_paste: bool = True,
        tab_moves_focus: bool = False,
        **input_kwargs: Any,  # noqa: ANN401
    ) -> None:
        """Create a console input.

        Args:
            value: The starting text.
            placeholder: The text shown while the input is empty.
            history: The history to use. Pass your own to share it or to save
                it. A new empty history is made if this is ``None``.
            clear_on_submit: Clear the input after a submit.
            middle_click_paste: Paste on a middle click (mouse button 2).
            tab_moves_focus: Let Tab move the focus to the next widget. If
                ``False``, Tab does nothing in the input.
            **input_kwargs: Other arguments for :class:`textual.widgets.Input`.
        """
        super().__init__(value, placeholder, **input_kwargs)
        self.history = history if history is not None else CommandHistory()
        """The command history."""
        self.clear_on_submit = clear_on_submit
        """Whether a submit clears the input."""
        self.middle_click_paste = middle_click_paste
        """Whether a middle click pastes."""
        self.tab_moves_focus = tab_moves_focus
        """Whether Tab moves the focus."""
        self._paste_text = ""
        self.recalled_value: str | None = None
        """The text that came from the history, or ``None``.

        It is set by :meth:`recall`. It is not cleared by this widget when the
        user edits the text: compare it with :attr:`value`.
        """

    def recall(self, value: str) -> None:
        """Show a value from the history, with the cursor at the end.

        Args:
            value: The text to show. It is stored in :attr:`recalled_value`.
        """
        self.recalled_value = value
        self.value = value
        self.cursor_position = len(value)

    def action_history_previous(self) -> None:
        """Show the previous (older) history entry."""
        entry = self.history.previous(self.value)
        if entry is not None:
            self.recall(entry)

    def action_history_next(self) -> None:
        """Show the next (newer) history entry, or the saved draft."""
        entry = self.history.next()
        if entry is not None:
            self.recall(entry)

    def action_tab(self) -> None:
        """Do nothing, or move the focus if ``tab_moves_focus`` is set."""
        if not self.tab_moves_focus:
            return
        raise SkipAction()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Record the submitted value, and clear the input if asked to."""
        if event.input is not self:
            return
        self.history.record(event.value)
        self.recalled_value = None
        if self.clear_on_submit:
            self.value = ""

    @on(events.MouseDown)
    def _take_paste_text(self, event: events.MouseDown) -> None:
        # The screen clears the selection on mouse up, before this widget gets
        # the event, so the text is read on mouse down.
        if event.button == 2 and self.middle_click_paste:
            self._paste_text = self.screen.get_selected_text() or self.app.clipboard

    @on(events.MouseUp)
    def _paste_on_middle_click(self, event: events.MouseUp) -> None:
        if event.button != 2:
            return
        text, self._paste_text = self._paste_text, ""
        if text:
            start, end = self.selection
            self.replace(text, start, end)
