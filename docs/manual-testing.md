# Manual testing

Run these checks by hand in each terminal before a release. Some things cannot be
tested in code: what a terminal sends to the app, and whether OSC 52 copy works.

## Run the demo

```bash
python -m textual_console
python -m textual_console --max-lines 100 --log demo.log
```

`--max-lines N` limits the scrollback (use it with `flood 500 --style red`). `--log PATH`
writes a plain-text transcript.

## Checks

1. Drag, double-click, triple-click in the output. ctrl+c copies (a notification shows).
2. Select text in the output, then middle-click the prompt: the selection is pasted.
   Select several lines: ALL lines are pasted.
3. With no selection, middle-click the prompt: the last app copy is pasted.
4. Copy text in ANOTHER app, then middle-click the prompt: does the app get
   the click, or does the terminal paste?
5. Copy text in ANOTHER app, then shift+middle-click the prompt: the terminal
   pastes by itself.
6. Paste or ctrl+v several lines (try "colors" output): the prompt grows up to 10
   rows, then scrolls; up/down move between rows. Enter runs each line as a command.
7. shift+enter / alt+enter / ctrl+j insert a newline (shift+enter only in
   terminals that report it).
8. Tab after a command (for example "flood ") shows its options and a hint.
   Type until nothing matches: does an empty dropdown stay open?
9. Esc Esc (quickly) clears the prompt; ctrl+z brings it back.
10. Drag a short selection in the output, scroll with the wheel, then shift-click: all
    lines are selected, and ctrl+c copies all of them. Do the same in a multi-line
    prompt. With no selection, shift-click does nothing.
11. Repeat check 10 with ctrl+click. It is the fallback where the terminal takes
    shift+click for its own selection.

## Results

The columns of the results table:

1. **Select + MMB:** select text in the output, then middle-click the prompt.
2. **No selection + MMB:** middle-click the prompt with no selection.
3. **Outside + MMB:** middle-click with text copied in another app.
4. **Outside + shift+MMB:** shift+middle-click with text copied in another app.
5. **Terminal paste:** paste multi-line text with `cmd+v` or `ctrl+shift+v`.
6. **shift+enter / alt+enter reported?:** press each key in the prompt. Does it insert a
   newline (reported) or submit (shift+enter arrives as Enter)?
7. **shift+click reaches app?:** check 10. Does shift-click extend the selection (the app
   gets the click), or does the terminal select text by itself?
8. **ctrl+click reaches app?:** check 11. Does ctrl-click extend the selection? It is the
   fallback where 7 fails.

Expected results: 1 pastes the selection (all lines), 2 pastes the last app copy, 3 shows
if the terminal sends the click to the app, 4 is the terminal paste, 5 keeps all lines and
the prompt grows, 6 shows which newline keys your terminal can send, 7 and 8 show which click keys
extend a selection.

| Terminal | OSC 52 copy | Select + MMB | No selection + MMB | Outside + MMB | Outside + shift+MMB | Terminal paste | shift+enter / alt+enter reported? | shift+click reaches app? | ctrl+click reaches app? |
|---|---|---|---|---|---|---|---|---|---|
| iTerm2 | untested | untested | untested | untested | untested | untested | untested | untested | untested |
| kitty | untested | untested | untested | untested | untested | untested | untested | untested | untested |
| WezTerm | untested | untested | untested | untested | untested | untested | untested | untested | untested |
| Ghostty | untested | untested | untested | untested | untested | untested | untested | untested | untested |
| VS Code terminal | untested | untested | untested | untested | untested | untested | untested | untested | untested |
| tmux | untested | untested | untested | untested | untested | untested | untested | untested | untested |
| macOS Terminal.app | untested (expected to fail) | untested | untested | untested | untested | untested | untested | untested | untested |
| herdr (in Ghostty) | untested | untested | untested | untested | untested | untested | shift+enter = Enter (submits); alt+enter untested | no (Ghostty keeps it) | yes |
