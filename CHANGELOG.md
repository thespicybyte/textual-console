# Changelog

## Unreleased

- `CommandAutoComplete`: the dropdown has a round grey border and a `$panel`
  background, so it stands out from the input and output. To change them, style
  `CommandAutoComplete` and `CommandAutoComplete AutoCompleteList`. The dropdown shows
  10 options before it scrolls, not 12.
- `CommandAutoComplete`: the option text starts under the first character of the typed
  word. Before, it started one cell left of the cursor. The dropdown never covers the
  typed word, also when the word wraps. It is never wider than the screen (long rows end
  in `…`), and when it is taller than the room above and below the cursor, it scrolls.

## 0.3.0 (2026-10-23)

- `CommandAutoComplete`: completes the word that ends at the cursor, also in the middle
  of a line. Before, it only completed the last word with the cursor at the end of the
  line. The text after the cursor is kept, and a space is added only at the end of the
  line. There is no completion when the cursor is inside a word.
- `CandidateSource` gets the line up to the cursor. At the end of the line this is the
  whole line, as before.

## 0.2.0 (2026-10-18)

- `ConsoleOutput` and `ConsoleInput`: shift-click (or ctrl-click) moves the end of the
  selection, also past lines that scrolled out of view. The end point is the place
  where the mouse button is released, because some terminal setups (herdr in Ghostty)
  report a wrong position for the press.
- `CommandAutoComplete`: Enter submits the line when the typed word already equals the
  highlighted option. Before, Enter accepted the option and added a space, and a second
  Enter was needed. Tab still accepts the option.
- `CommandAutoComplete`: an exception from the candidate source no longer stops the
  app. It is logged, and there are no candidates. The README tells which lines the
  source can get (also an empty line on Tab).
- `CandidateSource` is now public, so hosts can type their candidate source.

## 0.1.0 (2026-10-17)

- `ConsoleOutput`: Rich output with drag, word and line selection, and OSC 52 copy.
- `ConsoleInput` and `CommandHistory`: a `TextArea` command prompt that grows up to
  `max_height` rows, with a `prompt` gutter, a `suggester`, history
  (`command_history`), newline keys (shift+enter, alt+enter, ctrl+j), a quiet Tab and
  middle-click paste of all selected lines.
- `ConsoleInput`: double Escape clears the input (`double_escape_clear`).
- `CommandAutoComplete`: completes the last word of the cursor's line and keeps quotes.
  Tab opens the dropdown.
- `CommandItem` and `CompletionHint`: dropdown rows with a help column, and a hint row.
- `ArgparseCompleter` and `set_completer`: completion from `argparse` parsers.
- `ConsoleLog` and `strip_ansi`: plain-text transcript of the output.
- Demo (`python -m textual_console`, with `--log PATH` and `--max-lines N`) and
  examples.
- Project skeleton and CI.
