"""Read-only console output with colors and mouse selection."""

from __future__ import annotations

from typing import Any, Self

from rich.segment import Segment
from rich.style import Style as RichStyle
from rich.text import Text
from textual import events
from textual.geometry import Offset, Size
from textual.message import Message
from textual.selection import Selection
from textual.strip import Strip
from textual.style import Style as VisualStyle
from textual.widgets import RichLog

from textual_console._console_log import ConsoleLog
from textual_console._selection import cell_to_char, char_to_cell, line_span
from textual_console._selection import word_span as _word_span


class ConsoleOutput(RichLog, can_focus=False):
    """Console output that shows Rich renderables and supports mouse selection.

    ``ConsoleOutput`` is a :class:`~textual.widgets.RichLog`. It renders strings,
    ``Text``, tables and any other Rich renderable in color. It takes part in
    Textual's screen selection, so you can drag to select (the view scrolls at
    the edges), double-click to select a word, triple-click to select a line,
    and press ``ctrl+c`` to copy through ``App.copy_to_clipboard`` (OSC 52).
    Shift-click moves the end of the selection and the start point stays, so
    a selection can be longer than one screen. Ctrl-click does the same, for
    terminals that keep shift-click for themselves. Without a selection,
    both do nothing.

    The widget cannot take focus by default, so keyboard focus stays on the
    prompt of the app. To change the highlight color, style the
    ``console-output--selection`` component class. If the app does not style
    it, the highlight uses ``screen--selection`` (the theme colors).

    Copied text has one line for each rendered line, without trailing spaces.
    With ``wrap=True`` that means the visual lines.

    Example:
        >>> from textual.app import App, ComposeResult
        >>> class Demo(App[None]):
        ...     def compose(self) -> ComposeResult:
        ...         yield ConsoleOutput(max_lines=1000, copy_on_select=True)
    """

    ALLOW_SELECT = True

    COMPONENT_CLASSES = {"console-output--selection"}

    DEFAULT_CSS = """
    ConsoleOutput {
        background: $surface;
        color: $foreground;
        overflow-y: scroll;
    }
    """

    class SelectionCopied(Message):
        """Posted after the selected text was copied to the clipboard."""

        def __init__(self, console_output: ConsoleOutput, text: str) -> None:
            """Create the message.

            Args:
                console_output: The widget that copied the text.
                text: The text that was copied.
            """
            super().__init__()
            self.console_output = console_output
            """The widget that copied the text."""
            self.text = text
            """The text that was copied."""

        @property
        def control(self) -> ConsoleOutput:
            """The widget that copied the text."""
            return self.console_output

    class LogFailed(Message):
        """Posted once when the transcript fails. The log is then dropped."""

        def __init__(self, console_output: ConsoleOutput, error: Exception) -> None:
            """Create the message.

            Args:
                console_output: The widget whose log failed.
                error: The error from the log.
            """
            super().__init__()
            self.console_output = console_output
            """The widget whose log failed."""
            self.error = error
            """The error from the log."""

        @property
        def control(self) -> ConsoleOutput:
            """The widget whose log failed."""
            return self.console_output

    def __init__(
        self,
        *,
        max_lines: int | None = None,
        min_width: int = 78,
        wrap: bool = False,
        highlight: bool = False,
        markup: bool = False,
        auto_scroll: bool = True,
        copy_on_select: bool = False,
        word_chars: str = "",
        log: ConsoleLog | None = None,
        name: str | None = None,
        id: str | None = None,  # noqa: A002
        classes: str | None = None,
        disabled: bool = False,
    ) -> None:
        """Create a console output.

        Args:
            max_lines: Scrollback limit. The oldest lines are removed when the
                output is longer. ``None`` means no limit.
            min_width: Minimum width, in cells, of a written renderable.
            wrap: Wrap text to the width of the widget.
            highlight: Highlight numbers, strings and other values in written
                strings.
            markup: Apply Rich console markup to written strings.
            auto_scroll: Scroll to the end when a line is written.
            copy_on_select: Copy the selection to the clipboard when a mouse
                selection ends, and after a double-click or triple-click.
            word_chars: Characters that count as part of a word, even if they
                are separators (for example ``"("``).
            log: Transcript that receives each written line as plain text. If
                it fails, :class:`LogFailed` is posted once and the log is not
                used again. :meth:`clear` does not change the file.
            name: Name of the widget.
            id: ID of the widget in the DOM.
            classes: CSS classes of the widget.
            disabled: Whether the widget is disabled.

        Raises:
            ValueError: If ``max_lines`` is not ``None`` and is less than 1.
        """
        if max_lines is not None and max_lines < 1:
            msg = f"max_lines must be at least 1, not {max_lines}"
            raise ValueError(msg)
        super().__init__(
            max_lines=max_lines,
            min_width=min_width,
            wrap=wrap,
            highlight=highlight,
            markup=markup,
            auto_scroll=auto_scroll,
            name=name,
            id=id,
            classes=classes,
            disabled=disabled,
        )
        self.copy_on_select = copy_on_select
        """Copy the selection to the clipboard when a selection ends."""
        self.word_chars = word_chars
        """Characters that count as part of a word."""
        self._copied_selection: Selection | None = None
        self._anchor: Offset | None = None
        self._transcript = log

    def on_mount(self) -> None:
        """Watch the screen for the end of a mouse selection."""
        self.screen.message_signal.subscribe(self, self._on_screen_message)

    def write(
        self,
        content: object,
        width: int | None = None,
        expand: bool = False,
        shrink: bool = True,
        scroll_end: bool | None = None,
        animate: bool = False,
    ) -> Self:
        """Write a string or a Rich renderable to the bottom of the output.

        The output keeps a selection on the same text when ``max_lines``
        removes lines from the top. A selection that is fully removed is
        cleared. The rendering is deferred until the size of the widget is
        known, as in :meth:`textual.widgets.RichLog.write`.

        Args:
            content: A Rich renderable, or a string.
            width: Width to render, or ``None`` to use ``min_width``.
            expand: Expand the content to the width of the widget.
            shrink: Shrink the content to fit the width of the widget.
            scroll_end: Scroll to the end, or ``None`` to use ``auto_scroll``.
            animate: Animate the scroll.

        Returns:
            The widget, so calls can be chained.
        """
        start_before = self._start_line
        length_before = len(self.lines)
        cap = self.max_lines
        keep_all = self._transcript is not None and cap is not None
        if keep_all:
            # Let RichLog keep every new line, so that lines which one write
            # adds beyond the cap still reach the transcript. They are pruned
            # below.
            self.max_lines = None
        try:
            super().write(content, width, expand, shrink, scroll_end, animate)
        finally:
            if keep_all:
                self.max_lines = cap
        new_lines = self.lines[length_before:]
        if keep_all and cap is not None and len(self.lines) > cap:
            self._start_line += len(self.lines) - cap
            self.lines = self.lines[-cap:]
            self.virtual_size = Size(self.virtual_size.width, len(self.lines))
            self.refresh()
        pruned = self._start_line - start_before
        added = len(self.lines) - length_before + pruned
        if added or pruned:
            self._lines_changed(added, pruned)
        if self._transcript is not None and new_lines:
            self._write_transcript(new_lines)
        return self

    def _write_transcript(self, strips: list[Strip]) -> None:
        """Send new lines to the transcript, or drop it and post ``LogFailed``."""
        transcript = self._transcript
        if transcript is None:
            return
        try:
            transcript.write_lines([strip.text.rstrip() for strip in strips])
        except (OSError, ValueError) as error:
            self._transcript = None
            try:
                transcript.close()
            except OSError:
                pass
            self.post_message(self.LogFailed(self, error))

    def _lines_changed(self, added: int, pruned: int) -> None:
        """Handle lines that ``write`` added to the end and pruned from the top.

        Args:
            added: Number of new lines at the end (``0`` for a deferred write).
            pruned: Number of lines removed from the top.
        """
        if pruned:
            self._shift_selection(pruned)

    def write_ansi(self, text: str, **write_kwargs: Any) -> Self:  # noqa: ANN401
        """Write text that has ANSI escape codes.

        Args:
            text: Text with ANSI color and style codes.
            **write_kwargs: Keyword arguments for :meth:`write`.

        Returns:
            The widget, so calls can be chained.
        """
        return self.write(Text.from_ansi(text), **write_kwargs)

    # Selection

    @property
    def selected_text(self) -> str | None:
        """The text that is selected in this widget, or ``None``."""
        selection = self.text_selection
        if selection is None:
            return None
        result = self.get_selection(selection)
        if result is None:
            return None
        return result[0] or None

    def word_span(self, text: str, x: int) -> tuple[int, int] | None:
        """Find the word at a character of a line.

        Override this method to use other word rules.

        Args:
            text: Plain text of one line.
            x: Character offset into ``text``.

        Returns:
            The ``(start, end)`` character span of the word, or ``None``.
        """
        return _word_span(text, x, self.word_chars)

    def select_word_at(self, offset: Offset) -> None:
        """Select the word at a position of the output.

        Nothing is selected, and this widget's selection is cleared, if the
        position is on whitespace, on a separator or outside the lines.

        Args:
            offset: Position in content coordinates. ``x`` is a cell column
                and ``y`` is a line index.
        """
        if not 0 <= offset.y < len(self.lines):
            self.clear_selection()
            return
        text = self.lines[offset.y].text
        span = self.word_span(text, cell_to_char(text, max(0, offset.x)))
        if span is None:
            self.clear_selection()
            return
        self._anchor = Offset(span[0], offset.y)
        self._set_selection(
            Selection(Offset(span[0], offset.y), Offset(span[1], offset.y))
        )

    def select_line(self, line: int) -> None:
        """Select the content of one line, without trailing spaces.

        Args:
            line: Line index. This widget's selection is cleared if it is
                outside the lines or the line is blank.
        """
        if not 0 <= line < len(self.lines):
            self.clear_selection()
            return
        start, end = line_span(self.lines[line].text)
        if start == end:
            self.clear_selection()
            return
        self._anchor = Offset(start, line)
        self._set_selection(Selection(Offset(start, line), Offset(end, line)))

    def extend_selection_to(self, offset: Offset) -> None:
        """Move the end of the selection to a position of the output.

        The start point (the anchor) stays. Nothing happens if this widget has
        no selection.

        Args:
            offset: Position in content coordinates. ``x`` is a character
                offset and ``y`` is a line index.
        """
        selection = self.text_selection
        if selection is None or not self.lines:
            return
        anchor = self._current_anchor(selection)
        point = Offset(offset.x, min(max(offset.y, 0), len(self.lines) - 1))
        first, second = sorted((anchor, point), key=lambda o: (o.y, o.x))
        self._anchor = anchor
        self._set_selection(Selection(first, second + Offset(1, 0)))

    def _current_anchor(self, selection: Selection) -> Offset:
        """Get the start point of ``selection``.

        The recorded anchor is used only if it fits the selection. The screen
        sorts the two points of a drag and adds one to the later one.
        """
        start, end = selection
        anchor = self._anchor
        if anchor is not None and (
            start == anchor or (end is not None and end == anchor + Offset(1, 0))
        ):
            return anchor
        return Offset(0, 0) if start is None else start

    def select_all(self) -> None:
        """Select all lines of the output."""
        self.text_select_all()

    def clear_selection(self) -> None:
        """Clear the selection of this widget.

        The selections of other widgets are not changed.
        """
        selections = self.screen.selections
        if self in selections:
            self.screen.selections = {
                widget: selection
                for widget, selection in selections.items()
                if widget is not self
            }

    def copy_selection(self) -> str | None:
        """Copy the selected text to the clipboard (OSC 52).

        Posts :class:`SelectionCopied` after the copy.

        Returns:
            The text that was copied, or ``None`` if nothing is selected.
        """
        text = self.selected_text
        if text is None:
            return None
        self.app.copy_to_clipboard(text)
        self._copied_selection = self.text_selection
        self.post_message(self.SelectionCopied(self, text))
        return text

    def _set_selection(self, selection: Selection) -> None:
        """Make ``selection`` the only selection on the screen."""
        self.screen.selections = {self: selection}

    def _shift_selection(self, lines: int) -> None:
        """Move the selection up after ``lines`` lines were removed from the top."""
        selection = self.text_selection
        if selection is None or selection == (None, None):
            return
        start, end = selection
        if end is not None and end.y - lines < 0:
            self.clear_selection()
            self._copied_selection = None
            self._anchor = None
            return
        if self._anchor is not None:
            anchor = self._anchor
            self._anchor = (
                Offset(0, 0) if anchor.y - lines < 0 else anchor - Offset(0, lines)
            )
        if start is not None:
            start = Offset(0, 0) if start.y - lines < 0 else start - Offset(0, lines)
        if end is not None:
            end = end - Offset(0, lines)
        shifted = Selection(start, end)
        if self._copied_selection == selection:
            self._copied_selection = shifted
        self.screen.selections = {**self.screen.selections, self: shifted}

    def clear(self) -> Self:
        """Remove all lines and clear the selection of this widget.

        Returns:
            The widget, so calls can be chained.
        """
        self.clear_selection()
        self._anchor = None
        super().clear()
        return self

    def get_selection(self, selection: Selection) -> tuple[str, str] | None:
        """Get the text under a selection.

        Only the selected range of lines is read, so the cost does not grow
        with the length of the scrollback.

        Args:
            selection: The selection, in character offsets of the lines.

        Returns:
            The text and the line ending, or ``None`` if there are no lines.
        """
        count = len(self.lines)
        if not count:
            return None
        start, end = selection
        first = 0 if start is None else max(0, start.y)
        last = count - 1 if end is None else min(count - 1, end.y)
        if first > last:
            return None
        text = "\n".join(strip.text.rstrip() for strip in self.lines[first : last + 1])
        shifted = Selection(
            None if start is None else Offset(start.x, start.y - first),
            None if end is None else Offset(end.x, end.y - first),
        )
        return shifted.extract(text), "\n"

    def selection_updated(self, selection: Selection | None) -> None:
        """Refresh the highlight when the selection changes.

        Args:
            selection: The new selection, or ``None`` if it was cleared.
        """
        if self.text_selection is None:
            self._copied_selection = None
        self.refresh()

    # Rendering

    def render_line(self, y: int) -> Strip:
        """Render one visible line, with the selection highlight.

        The segments carry their character offsets, which the screen uses to
        map the mouse position to the text.

        Args:
            y: Row of the widget, from the top of the viewport.

        Returns:
            The strip for the row.
        """
        strip = super().render_line(y)
        scroll_x, scroll_y = self.scroll_offset
        line = scroll_y + y
        if line >= len(self.lines):
            return strip
        text = self.lines[line].text
        selection = self.text_selection
        if selection is not None:
            span = selection.get_span(line)
            if span is not None:
                strip = self._highlight(strip, text, span, scroll_x)
        return strip.apply_offsets(cell_to_char(text, scroll_x), line)

    def _highlight(
        self, strip: Strip, text: str, span: tuple[int, int], scroll_x: int
    ) -> Strip:
        """Apply the selection style to a span of a line.

        The selection style is blended over the style of each segment, so
        translucent theme colors keep the text color and tint the background.

        Args:
            strip: The visible part of the line.
            text: Plain text of the whole line.
            span: Selected ``(start, end)`` characters. ``end == -1`` means
                the end of the line.
            scroll_x: Horizontal scroll, in cells.

        Returns:
            The strip with the highlight.
        """
        start, end = span
        content_end = len(text.rstrip())
        end = content_end if end == -1 else min(end, content_end)
        width = strip.cell_length
        first = min(max(char_to_cell(text, start) - scroll_x, 0), width)
        last = min(max(char_to_cell(text, end) - scroll_x, 0), width)
        if last <= first:
            return strip
        before, middle, after = strip.divide([first, last, width])
        component = "console-output--selection"
        styles = self.get_component_styles(component)
        if not styles.has_any_rules("background", "color", "text_style"):
            styles = self.screen.get_component_styles("screen--selection")
        selection_style = VisualStyle.from_styles(styles)
        cache: dict[RichStyle | None, RichStyle] = {}

        def blend(style: RichStyle | None) -> RichStyle:
            # The theme colors can be translucent (the default foreground is
            # transparent). Flattening them first would paint the text in the
            # highlight color, so blend them over each segment style instead.
            blended = cache.get(style)
            if blended is None:
                base = VisualStyle.from_rich_style(style or RichStyle.null())
                blended = (style or RichStyle.null()) + (
                    base + selection_style
                ).rich_style
                cache[style] = blended
            return blended

        selected = Strip(
            [Segment(seg.text, blend(seg.style), seg.control) for seg in middle],
            middle.cell_length,
        )
        return Strip.join([before, selected, after])

    # Events

    def on_mouse_down(self, event: events.MouseDown) -> None:
        """Record the start of a selection, or extend it on shift or ctrl.

        Args:
            event: The mouse down event.
        """
        if event.button != 1 or not (
            self.allow_select and self.screen.allow_select and self.app.ALLOW_SELECT
        ):
            return
        extend = event.shift or event.ctrl
        if extend and self.text_selection is None:
            return
        offset = self._content_offset_at(event)
        if offset is None:
            return
        if not extend:
            self._anchor = offset
            return
        self._cancel_screen_click()
        self.extend_selection_to(offset)

    def _content_offset_at(self, event: events.MouseDown) -> Offset | None:
        """Map a mouse event to content coordinates, as the screen does.

        Returns:
            The offset, or ``None`` if the event is not over this widget. Below
            the last line it is the end of the last line.
        """
        widget, offset = self.screen.get_widget_and_offset_at(
            event.screen_x, event.screen_y
        )
        if widget is not self:
            return None
        if offset is None:
            if not self.lines:
                return None
            last = len(self.lines) - 1
            return Offset(len(self.lines[last].text), last)
        return offset

    def _cancel_screen_click(self) -> None:
        """Stop the screen from treating this mouse press as a click.

        This uses private Textual state (checked on Textual 8.2.8). Without it,
        the screen clears the selection on the mouse up of a click.
        """
        screen = self.screen
        screen._mouse_down_offset = None
        screen._select_state = None

    def on_click(self, event: events.Click) -> None:
        """Select a word on double-click and a line on triple-click.

        Args:
            event: The click event.
        """
        if event.chain < 2 or event.widget is not self:
            return
        if not (
            self.allow_select and self.screen.allow_select and self.app.ALLOW_SELECT
        ):
            return
        if event.shift or event.ctrl:
            # A fast second click would select a word, or everything, and
            # replace the extended selection.
            event.prevent_default()
            return
        scroll_x, scroll_y = self.scroll_offset
        gutter = self.gutter
        x = event.x + scroll_x - gutter.left
        y = event.y + scroll_y - gutter.top
        if event.chain == 2:
            self.select_word_at(Offset(x, y))
        else:
            self.select_line(y)
        event.prevent_default()
        if self.copy_on_select:
            self.copy_selection()

    def _on_screen_message(self, message: Message) -> None:
        """Copy the selection when a mouse selection ends."""
        if (
            self.copy_on_select
            and isinstance(message, events.TextSelected)
            and self.text_selection is not None
            and self.text_selection != self._copied_selection
        ):
            self.copy_selection()
