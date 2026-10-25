# textual-console

Console widgets for [Textual](https://textual.textualize.io/): color output with
word and line mouse selection and OSC 52 copy, a multi-line command input with
history and autocomplete (also from `argparse` parsers), and a plain-text transcript.

![The textual-console demo](https://raw.githubusercontent.com/thespicybyte/textual-console/main/docs/demo.svg)

- `ConsoleOutput`: read-only output for Rich renderables. Drag, double-click (word)
  and triple-click (line) select text. `ctrl+c` copies it.
- `ConsoleInput`: a command prompt (a `TextArea`) that grows with its text, with a prompt
  string, history, a quiet Tab and middle-click paste.
- `CommandAutoComplete`: completes the word at the cursor. Tab opens it.
- `ArgparseCompleter`: gives `CommandAutoComplete` its candidates from `argparse` parsers.
- `ConsoleLog`: a plain-text transcript file of the output.

Python 3.11 or later. Tested on Textual 8.x.

## Install

```bash
pip install textual-console
```

Try the demo:

```bash
python -m textual_console
python -m textual_console --log session.log --max-lines 200
```

## Quick start

```python
from rich.text import Text
from textual import on
from textual.app import App, ComposeResult

from textual_console import CommandAutoComplete, ConsoleInput, ConsoleOutput


class Repl(App[None]):
    def compose(self) -> ComposeResult:
        yield ConsoleOutput(id="output", max_lines=5000)
        yield ConsoleInput(prompt="> ", placeholder="command", id="prompt")
        yield CommandAutoComplete("#prompt", lambda line: ["help", "quit"])

    @on(ConsoleInput.Submitted)
    def run_command(self, event: ConsoleInput.Submitted) -> None:
        self.query_one(ConsoleOutput).write(Text(f"> {event.value}", style="green"))


Repl().run()
```

More programs are in [`examples/`](https://github.com/thespicybyte/textual-console/tree/main/examples): `basic.py` (text, tables, copy),
`repl.py` (all widgets, argparse completion and a transcript) and `ansi_stream.py` (ANSI output of a
subprocess).

## ConsoleOutput

A `RichLog` that takes part in the Textual screen selection.

```python
output = ConsoleOutput(max_lines=5000, copy_on_select=False)
output.write(Text("done", style="bold green"))
output.write_ansi("\x1b[31mred\x1b[0m")
```

- Drag to select. The view scrolls at the edges.
- Double-click selects a word. Triple-click selects a line.
- Shift-click moves the end of the selection. The start stays, so you can select more
  than one screen: start a selection, scroll, then shift-click. With no selection,
  nothing happens. Many terminals keep shift-click for their own selection and never
  send it to the app. Then use ctrl-click, which does the same.
- `ctrl+c` copies the selection with `App.copy_to_clipboard` (OSC 52). `Escape` or a
  single click clears the selection.
- `copy_on_select=True` copies when a selection ends and posts `ConsoleOutput.SelectionCopied`.
  `ctrl+c` does not post `SelectionCopied`: only `copy_on_select` and `copy_selection()` do.
  To react to every copy, override `App.copy_to_clipboard` (the demo does this to show a
  notification).
- The widget cannot take focus, so the focus stays on your prompt.
- Copied text has one line for each rendered line, without trailing spaces.
- **Set `max_lines` for long-running apps.** The default is no limit, so memory grows
  with the session.
- To change the highlight, style the `console-output--selection` component class.
  If you do not, the theme `screen--selection` colors are used.

## ConsoleInput

A `TextArea` that works as a command prompt. It is one row high when it is empty, grows
row by row up to `max_height` rows (the default is 10), and then scrolls.

```python
history = CommandHistory(["help", "quit"])
prompt = ConsoleInput(prompt="> ", history=history, max_height=10)
```

Shift-click moves the end of the selection and the start stays, also when the start is
scrolled out of view. Ctrl-click does the same, for terminals that keep shift-click for
themselves. With no selection, both do nothing.

| Key | Action |
|---|---|
| Enter | Submit the whole text as one command. |
| shift+enter, alt+enter, ctrl+j | Insert a newline. |
| Up, down | Move the cursor between rows. On the first row up walks the history, and on the last row down does. |
| Tab | Nothing, so the focus stays in the prompt. Use `tab_moves_focus=True` to move the focus. |
| Esc Esc | Clear the input if both presses come within `double_escape_clear` seconds (default 0.5). Undo with ctrl+z. An Escape that closes the dropdown does not count. |
| Right | Accept the ghost text of a `suggester`. |

- `prompt` is drawn in the left gutter of the first row. It is not part of the text. Other
  rows get blank padding of the same width. It can change at run time, and the
  `console-input--prompt` component class styles it.
- `suggester` is a Textual `Suggester`. While the text is one line and the cursor is at
  its end, the suggestion shows as ghost text.
- `max_height` is checked when the widget is created (a value below 1 raises `ValueError`)
  and applied when the widget is mounted. `max_height=None` sets no limit, so a CSS
  `max-height` applies.
- The text is `prompt.value`. The history is `prompt.command_history`, a `CommandHistory`.
  Save it with `prompt.command_history.entries`.
- The first up saves the text you typed, and down past the newest entry restores it. A
  recalled multi-line command is shown with all its rows.
- Submit records the command, clears the input (unless `clear_on_submit=False`) and posts
  `ConsoleInput.Submitted` with `value`, the whole text.
- A `read_only` input keeps its text: paste, history, submit, completion and Esc Esc do
  nothing.
- `ConsoleInput.Changed` is `TextArea.Changed`: use `textual.widgets.TextArea.Changed`.
- `ConsoleInput` is not an `Input` any more. The arguments that only `Input` has
  (`password`, `restrict`, `type`, `max_length`, `validators`, `validate_on`,
  `valid_empty`, `select_on_focus`) raise `TypeError`. The editor settings of `TextArea`
  (`soft_wrap`, line numbers, `tab_behavior`) are fixed.

### Multi-line text

**Enter submits the whole text, newlines included, as one command.** One submit gives one
`Submitted` message and one history entry. To run each line as its own command, split the
value in your handler. This is the choice of your app, not of the widget:

```python
@on(ConsoleInput.Submitted)
def run_commands(self, event: ConsoleInput.Submitted) -> None:
    for line in event.value.splitlines():
        if line.strip():
            self.run_command(line)
```

**Terminals and the newline keys.** Many terminals send `shift+enter` as a plain Enter,
so the app cannot see the difference. Only terminals with the kitty keyboard protocol (or
a similar extension) report it. `alt+enter` and `ctrl+j` work in more terminals. Use
them as the fallback. In herdr, `shift+enter` arrives as Enter and submits.

### Middle-click paste

**Middle-click pastes text from inside the app.** It pastes the text selected in the
output. If nothing is selected, it pastes the last text that the app copied.
**All lines of a multi-line selection are pasted.**
**To paste text from other apps, use the terminal paste** (`cmd+v` or `ctrl+shift+v`).
It keeps all lines too. `ctrl+v` is different: it pastes the last text that the app
copied (`app.clipboard`), with all lines, and not the system clipboard.

Some terminals use the middle-click for their own paste and do not send it to the
app. Then you get the terminal paste. Check 4 in
[docs/manual-testing.md](https://github.com/thespicybyte/textual-console/blob/main/docs/manual-testing.md)
shows which one your terminal does.

## CommandAutoComplete

```python
CommandAutoComplete("#prompt", lambda line: ["open", "close", "help"])
```

The function gets the line of the cursor, up to the cursor, and returns the options for
the word that ends at the cursor. The text before the word stays as typed, and the text
after the cursor is kept. A space is added only at the end of the line. A completion that
needs quotes is quoted. In a multi-line input only the cursor's line is used, and a
completion changes only that line. When the cursor is inside a word, there is no
completion and Tab does what the input does.

- **Automatic opening:** the dropdown opens while you type a word. It does not open after
  a space, in an empty line, or while you walk the history.
- **Tab opens the dropdown** when it is closed, also after a space. If there is one
  option, Tab applies it at once. If there are none, Tab does what the input does.
- **Key order:** when the dropdown is open, up and down move in the dropdown, and Tab or
  Enter accept the option. If the word already equals the highlighted option, Enter
  submits the line and only Tab accepts it. When it is closed, up and down move between
  rows or walk the history.
- **Items:** a function can return strings, `DropdownItem`s, `CommandItem(value, help)`
  (shows `help` in a dim second column, aligned) and `CompletionHint(text)` (a dim,
  disabled row that tells what to type. It is never applied).
- **Style and placement:** the dropdown has a round grey border and a `$panel`
  background. To change them, style `CommandAutoComplete` and
  `CommandAutoComplete AutoCompleteList`. The option text starts under the first
  character of the word. The dropdown is below the cursor, or above the word if it does
  not fit below. It never covers the word. It is never wider than the screen, and long
  rows end in `…`.
- **The candidate source is synchronous.** It runs on the event loop. If the source is
  slow (files, network), cache the result.
- **The candidate source gets any line.** On Tab it can be empty, only spaces, or end in
  a space, a closed quote or a backslash. It is never a line with an unclosed quote. Do
  not assume that there is a first word. If the source raises, there are no candidates
  and the error is logged to the `textual_console` logger. To see it, set up `logging`
  (for example to a file, or `textual.logging.TextualHandler` with `textual console`).
  To type your source, use `from textual_console import CandidateSource`.
- The package needs `textual-autocomplete` 4.0.x, because `CommandAutoComplete` overrides
  some of its private methods.

## Argparse completion

`ArgparseCompleter` reads `argparse` parsers and gives the candidates for the word at the
cursor. It never calls `parse_args`, so nothing prints and nothing exits.

```python
import argparse

from textual_console import ArgparseCompleter, CommandAutoComplete, set_completer

flood = argparse.ArgumentParser(prog="flood", description="Write many lines")
flood.add_argument("count", nargs="?", type=int, metavar="COUNT", help="how many lines")
flood.add_argument("--style", choices=["plain", "red", "green"], help="line style")
open_ = argparse.ArgumentParser(prog="open", description="Open a file")
set_completer(open_.add_argument("file", metavar="FILE", help="the file"), list_files)

parsers = {"flood": flood, "open": open_}
CommandAutoComplete("#prompt", ArgparseCompleter(parsers))
```

- Describe the commands with a mapping `{name: parser}` (read on every call, so you can
  add commands later) or with one root parser that has subparsers.
- It offers the command names, the options not used yet (with their help), the `choices`
  of an option or positional (also after `--option=`), and the next positional, counted
  with `nargs`. It descends into subparsers. After a lone `--` it offers only positionals.
- `set_completer(action, function)` attaches a function that gets the current word and
  returns strings or items. It is stored in `action.completer`, the name that
  `argcomplete` uses. If it raises, there are no candidates and the error is logged.
- `hints=True` (the default) adds a `CompletionHint` such as `FILE: the file` where the
  user must type a value. `show_help_option=True` offers `-h` and `--help`.
- It reads some private `argparse` attributes that have been stable since Python 3.2. If
  they change, completion is reduced and the error is logged.

**Run the command with the same parsers.** `parse_args` prints for `-h` and on errors, and
then raises `SystemExit`. Catch it and write the text to the output, so the app keeps
running:

```python
import contextlib
import io
import shlex

name, *args = shlex.split(line)
buffer = io.StringIO()
try:
    with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
        namespace = parsers[name].parse_args(args)
except SystemExit:
    output.write(buffer.getvalue())
```

The demo (`python -m textual_console`) does this, so `flood -h` shows the usage.

## ConsoleLog

A plain-text copy of the output, with ANSI codes removed.

```python
log = ConsoleLog("session.log")
yield ConsoleOutput(log=log)
```

`ConsoleInput` does not write to the log. **To put commands in the transcript, echo
them into the output.** Then each command is written once, in order with its result:

```python
@on(ConsoleInput.Submitted)
def run_command(self, event: ConsoleInput.Submitted) -> None:
    output = self.query_one(ConsoleOutput)
    output.write(f"> {event.value}")
    ...
```

`ConsoleOutput.clear()` does not change the file. If the file cannot be written,
`ConsoleOutput.LogFailed` is posted once and the app keeps running. `strip_ansi(text)`
is also public.

## Terminals and OSC 52

Copy uses OSC 52, which asks the terminal to set the clipboard. The app cannot detect
whether it worked. `ctrl+c` is the reliable key. `cmd+c` reaches the app only on
terminals with the kitty keyboard protocol. Native terminal selection (shift-drag or
option-drag) is not changed.

**Shift-click.** Many terminals (xterm, kitty, WezTerm, Ghostty, GNOME Terminal,
Alacritty) use shift-click for their own selection, so the app never sees it. Use
ctrl-click there, or change the terminal setting (for example Ghostty
`mouse-shift-capture = true`, kitty `terminal_select_modifiers`, WezTerm
`bypass_mouse_reporting_modifiers`).

Maintainers test these things by hand in each terminal. The steps and the results table
are in [docs/manual-testing.md](https://github.com/thespicybyte/textual-console/blob/main/docs/manual-testing.md).

**tmux:** add `set -g set-clipboard on` to `~/.tmux.conf`. Without it, OSC 52 copy does
not reach the outer terminal. Some terminals limit the size of the copied text or ask
for permission first.

## Development

```bash
uv sync --group test --group lint
uv run pytest
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pyright
```

Repository: <https://github.com/thespicybyte/textual-console>

For maintainers: see `RELEASING.md` for the release steps.

## License

MIT. See `LICENSE`.
