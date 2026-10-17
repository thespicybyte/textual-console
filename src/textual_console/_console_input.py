"""Command prompt widget with history."""

from dataclasses import dataclass
from typing import Any, cast

from rich.cells import cell_len
from rich.segment import Segment
from textual import events, on
from textual.actions import SkipAction
from textual.binding import Binding
from textual.message import Message
from textual.reactive import reactive
from textual.strip import Strip
from textual.suggester import Suggester, SuggestionReady
from textual.widgets import TextArea
from textual.widgets.text_area import Document, Selection

from textual_console._history import CommandHistory


class ConsoleInput(TextArea):
    """A command prompt that grows with its text, with history and a quiet Tab.

    The widget is one row high when it is empty and grows row by row, up to
    ``max_height`` rows, and then scrolls. Enter submits the whole text, newlines
    included, as one command: one :class:`Submitted` message and one history
    entry. An app that wants one command per line splits ``event.value`` itself.

    ``shift+enter``, ``alt+enter`` and ``ctrl+j`` insert a newline. Many terminals
    send ``shift+enter`` as a plain Enter, so the other two keys are there as a
    fallback. The up and down keys move the cursor between rows. On the first row
    up walks the command history, and on the last row down does. Tab does not
    move focus unless ``tab_moves_focus`` is set. A middle click pastes the text
    selected in the output, or else the app clipboard.

    ``prompt`` is drawn in the left gutter on the first row. Other rows get blank
    padding of the same width. It is not part of the text, and the
    ``console-input--prompt`` component class styles it. ``suggester`` shows
    ghost text after the cursor, and the right key accepts it.

    The text is the :attr:`value`. Changes are posted as
    :class:`textual.widgets.TextArea.Changed`.

    The widget does not import any autocomplete code. An autocomplete widget
    can read :attr:`recalled_value` to stay closed while the user walks through
    the history.

    Example:
        >>> prompt = ConsoleInput(placeholder="command")
        >>> prompt.command_history.entries
        []
    """

    DEFAULT_CSS = """
    ConsoleInput {
        height: auto;
        & .console-input--prompt {
            color: $accent;
            text-style: bold;
        }
    }
    """

    COMPONENT_CLASSES = {"console-input--prompt"}

    BINDINGS = [
        Binding("enter", "submit", show=False),
        Binding("shift+enter,alt+enter,ctrl+j", "newline", show=False),
        Binding("up", "cursor_up_or_history", show=False),
        Binding("down", "cursor_down_or_history", show=False),
        Binding("tab", "tab", show=False),
    ]

    prompt: reactive[str] = reactive("", init=False)
    """The text drawn in the gutter on the first row. It is not part of the value."""

    @dataclass
    class Submitted(Message):
        """Posted when the user presses Enter."""

        console_input: "ConsoleInput"
        """The widget that was submitted."""
        value: str
        """The whole text, newlines included."""

        @property
        def control(self) -> "ConsoleInput":
            """The widget that was submitted."""
            return self.console_input

    def __init__(
        self,
        value: str = "",
        placeholder: str = "",
        *,
        prompt: str = "",
        history: CommandHistory | None = None,
        clear_on_submit: bool = True,
        middle_click_paste: bool = True,
        tab_moves_focus: bool = False,
        max_height: int | None = 10,
        suggester: Suggester | None = None,
        **text_area_kwargs: Any,  # noqa: ANN401
    ) -> None:
        """Create a console input.

        Args:
            value: The starting text.
            placeholder: The text shown while the input is empty.
            prompt: The text drawn in the gutter on the first row, such as
                ``"> "``. It is available as :attr:`prompt` and can change at
                run time.
            history: The history to use. Pass your own to share it or to save
                it. A new empty history is made if this is ``None``. It is
                available as :attr:`command_history`.
            clear_on_submit: Clear the input after a submit.
            middle_click_paste: Paste on a middle click (mouse button 2).
            tab_moves_focus: Let Tab move the focus to the next widget. If
                ``False``, Tab does nothing in the input.
            max_height: The most rows of text to show before the text scrolls.
                ``None`` sets no limit, so a CSS ``max-height`` applies. This
                sets an inline style, which wins over CSS. The limit is
                applied when the widget is mounted: changing the attribute
                later does nothing.
            suggester: A Textual suggester. While the text is one line and the
                cursor is at its end, the suggestion is shown as ghost text
                after the cursor, and the right key accepts it.
            **text_area_kwargs: Other arguments for
                :class:`textual.widgets.TextArea`, such as ``id``, ``classes``
                or ``compact``. The arguments that make a ``TextArea`` an editor
                (``soft_wrap``, ``language``, ``tab_behavior``, line numbers)
                are fixed here.

        Raises:
            ValueError: If ``max_height`` is not ``None`` and is less than 1.
        """
        if max_height is not None and max_height < 1:
            raise ValueError(f"max_height must be at least 1, not {max_height}")
        super().__init__(
            value,
            soft_wrap=True,
            show_line_numbers=False,
            tab_behavior="focus",
            highlight_cursor_line=False,
            placeholder=placeholder,
            **text_area_kwargs,
        )
        self.set_reactive(ConsoleInput.prompt, prompt)
        self.suggester = suggester
        """The suggester, or ``None``."""
        self.selection = Selection.cursor(self.document.end)
        # TextArea keeps its own undo history in ``history``, so the command
        # history has another name.
        self.command_history = history if history is not None else CommandHistory()
        """The command history."""
        self.clear_on_submit = clear_on_submit
        """Whether a submit clears the input."""
        self.middle_click_paste = middle_click_paste
        """Whether a middle click pastes."""
        self.tab_moves_focus = tab_moves_focus
        """Whether Tab moves the focus."""
        self.max_height = max_height
        """The most rows of text shown before the text scrolls, or ``None``.

        It is applied when the widget is mounted. Changing it later does nothing.
        """
        self._paste_text = ""
        self.recalled_value: str | None = None
        """The text that came from the history, or ``None``.

        It is set by :meth:`recall`. It is not cleared by this widget when the
        user edits the text: compare it with :attr:`value`.
        """

    def _on_mount(self, event: events.Mount) -> None:
        # The cursor was moved to the end before the widget had a size.
        self._recompute_cursor_offset()
        if self.max_height is not None:
            self.styles.max_height = self.max_height + self.gutter.height

    @property
    def gutter_width(self) -> int:
        """The cell width of the prompt, which is the width of the gutter."""
        return cell_len(self.prompt)

    def _watch_prompt(self) -> None:
        self._rewrap_and_refresh_virtual_size()
        self.refresh()

    def render_line(self, y: int) -> Strip:
        """Render a row, with the prompt or blank padding in the gutter."""
        gutter_width = self.gutter_width
        strip = super().render_line(y)
        if not gutter_width:
            return strip
        base_style = self.rich_style
        if y + self.scroll_offset.y == 0:
            style = base_style + self.get_component_rich_style("console-input--prompt")
            gutter = Segment(self.prompt, style)
        else:
            gutter = Segment(" " * gutter_width, base_style)
        # The placeholder row is as wide as the content, so crop it to the text.
        text = strip.crop(0, self.scrollable_content_region.width - gutter_width)
        return Strip.join([Strip([gutter], gutter_width), text])

    def update_suggestion(self) -> None:
        """Ask the suggester for ghost text, while the text is one line."""
        value = self.value
        if (
            self.suggester is None
            or not self.is_attached
            or not value
            or self.document.line_count > 1
            or self.cursor_location != self.document.end
        ):
            self.suggestion = ""
            return
        self.run_worker(self.suggester._get_suggestion(self, value), exclusive=True)

    def _on_suggestion_ready(self, event: SuggestionReady) -> None:
        value = self.value
        if (
            event.value == value
            and self.document.line_count == 1
            and self.cursor_location == self.document.end
            and event.suggestion.startswith(value)
        ):
            self.suggestion = event.suggestion[len(value) :]
        else:
            self.suggestion = ""

    @property
    def value(self) -> str:
        """The text. Setting it replaces the text and puts the cursor at the end."""
        return self.text

    @value.setter
    def value(self, value: str) -> None:
        self.load_text(value)
        self.selection = Selection.cursor(self.document.end)

    @property
    def cursor_position(self) -> int:
        """The cursor as an index into :attr:`value`."""
        return cast(Document, self.document).get_index_from_location(
            self.cursor_location
        )

    @cursor_position.setter
    def cursor_position(self, position: int) -> None:
        self.move_cursor(
            cast(Document, self.document).get_location_from_index(position)
        )

    def recall(self, value: str) -> None:
        """Show a value from the history, with the cursor at the end.

        Args:
            value: The text to show. It is stored in :attr:`recalled_value`.
        """
        self.recalled_value = value
        self.value = value

    def _cursor_row(self) -> int:
        """Return the visual row of the cursor, counting wrapped rows."""
        return self.wrapped_document.location_to_offset(self.cursor_location).y

    def action_cursor_up_or_history(self) -> None:
        """Move up a row, or show the previous history entry from the first row."""
        if self._cursor_row() > 0:
            self.action_cursor_up()
            return
        entry = self.command_history.previous(self.value)
        if entry is not None:
            self.recall(entry)

    def action_cursor_down_or_history(self) -> None:
        """Move down a row, or show the next history entry from the last row."""
        if self._cursor_row() < self.wrapped_document.height - 1:
            self.action_cursor_down()
            return
        entry = self.command_history.next()
        if entry is not None:
            self.recall(entry)

    def action_tab(self) -> None:
        """Do nothing, or move the focus if ``tab_moves_focus`` is set."""
        if not self.tab_moves_focus:
            return
        raise SkipAction()

    def action_newline(self) -> None:
        """Insert a newline at the cursor, replacing the selection."""
        self._replace_via_keyboard("\n", *self.selection)

    def action_submit(self) -> None:
        """Post the text as one command, record it, and clear if asked to."""
        value = self.value
        self.post_message(self.Submitted(self, value))
        self.command_history.record(value)
        self.recalled_value = None
        if self.clear_on_submit:
            self.value = ""

    async def _on_key(self, event: events.Key) -> None:
        # TextArea._on_key inserts a newline for Enter, and Textual calls it
        # after this method. Preventing the default stops that, and leaving the
        # event unstopped lets it reach the ``enter`` binding. An open dropdown
        # stops the event first, so Enter completes instead of submitting.
        if event.key == "enter":
            event.prevent_default()

    def _paste(self, text: str) -> None:
        """Insert pasted text at the selection, without one trailing newline."""
        if self.read_only:
            return
        text = text.replace("\r\n", "\n").replace("\r", "\n").removesuffix("\n")
        if result := self._replace_via_keyboard(text, *self.selection):
            self.move_cursor(result.end_location)

    async def _on_paste(self, event: events.Paste) -> None:
        event.prevent_default()
        self._paste(event.text)
        self.focus()

    def action_paste(self) -> None:
        """Paste the app clipboard."""
        self._paste(self.app.clipboard)

    @on(events.MouseDown)
    def _take_paste_text(self, event: events.MouseDown) -> None:
        # The screen clears the selection on mouse up, before this widget gets
        # the event, so the text is read on mouse down.
        self._paste_text = ""
        if event.button == 2 and self.middle_click_paste:
            self._paste_text = self.screen.get_selected_text() or self.app.clipboard

    @on(events.MouseUp)
    def _paste_on_middle_click(self, event: events.MouseUp) -> None:
        if event.button != 2:
            return
        text, self._paste_text = self._paste_text, ""
        if text:
            self._paste(text)
