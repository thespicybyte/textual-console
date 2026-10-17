# textual-console

Console widgets for [Textual](https://textual.textualize.io/): color output with
word and line mouse selection and OSC 52 copy, a command input with history and
autocomplete, and a plain-text transcript.

![The textual-console demo](https://raw.githubusercontent.com/thespicybyte/textual-console/main/docs/demo.svg)

- `ConsoleOutput`: read-only output for Rich renderables. Drag, double-click (word)
  and triple-click (line) select text. `ctrl+c` copies it.
- `ConsoleInput`: a command prompt with history, a quiet Tab and middle-click paste.
- `CommandAutoComplete`: completes the last word of the line.
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
        yield ConsoleInput(placeholder="command", id="prompt")
        yield CommandAutoComplete("#prompt", lambda line: ["help", "quit"])

    @on(ConsoleInput.Submitted)
    def run_command(self, event: ConsoleInput.Submitted) -> None:
        self.query_one(ConsoleOutput).write(Text(f"> {event.value}", style="green"))


Repl().run()
```

More programs are in [`examples/`](https://github.com/thespicybyte/textual-console/tree/main/examples): `basic.py` (text, tables, copy),
`repl.py` (all widgets and a transcript) and `ansi_stream.py` (ANSI output of a
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

An `Input` with command history.

```python
history = CommandHistory(["help", "quit"])
prompt = ConsoleInput(history=history)
```

- Up and down walk through the history. The first up saves the text you typed, and
  down past the newest entry restores it.
- Submit records the command, clears the input and bubbles `Input.Submitted` as usual.
- Tab does nothing, so the focus stays in the prompt. Use `tab_moves_focus=True` to
  move the focus.
- Save the history with `history.entries`.

### Middle-click paste

**Middle-click pastes text from inside the app.** It pastes the text selected in the
output. If nothing is selected, it pastes the last text that the app copied.
**To paste text from other apps, use the terminal paste** (`cmd+v` or `ctrl+shift+v`).
Only the first line of a multi-line paste is kept, because the input has one line.

Some terminals use the middle-click for their own paste and do not send it to the
app. Then you get the terminal paste. The demo shows which one your terminal does.

## CommandAutoComplete

```python
CommandAutoComplete("#prompt", lambda line: ["open", "close", "help"])
```

The function gets the full line and returns the options for the last word. The text
before the last word stays as typed. A completion that needs quotes is quoted.

- **Key order:** when the dropdown is open, up and down move in the dropdown, and Tab or
  Enter accept the option. When it is closed, up and down walk the history. No options
  are shown while you walk the history.
- **The candidate source is synchronous.** It runs on the event loop. If the source is
  slow (files, network), cache the result.

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

The paste columns are the manual checks of the demo (`python -m textual_console`):

1. **Select + MMB:** select text in the output, then middle-click the prompt.
2. **No selection + MMB:** middle-click the prompt with no selection.
3. **Outside + MMB:** middle-click with text copied in another app.
4. **Outside + shift+MMB:** shift+middle-click with text copied in another app.
5. **Terminal paste:** paste multi-line text with `cmd+v` or `ctrl+shift+v`.

Expected results: 1 pastes the selection, 2 pastes the last app copy, 3 shows if the
terminal sends the click to the app, 4 is the terminal paste, 5 keeps the first line.

| Terminal | OSC 52 copy | Select + MMB | No selection + MMB | Outside + MMB | Outside + shift+MMB | Terminal paste |
|---|---|---|---|---|---|---|
| iTerm2 | untested | untested | untested | untested | untested | untested |
| kitty | untested | untested | untested | untested | untested | untested |
| WezTerm | untested | untested | untested | untested | untested | untested |
| Ghostty | untested | untested | untested | untested | untested | untested |
| VS Code terminal | untested | untested | untested | untested | untested | untested |
| tmux | untested | untested | untested | untested | untested | untested |
| macOS Terminal.app | untested (expected to fail) | untested | untested | untested | untested | untested |

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
