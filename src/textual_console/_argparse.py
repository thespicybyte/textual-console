"""Completion of command lines from ``argparse`` parsers."""

import argparse
import logging
import re
import shlex
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from textual_autocomplete import DropdownItem

from textual_console._autocomplete import CommandItem, CompletionHint
from textual_console._tokens import last_token_span

ArgCompleter = Callable[[str], Iterable[str | DropdownItem]]
"""A function that gets the current word and returns the possible values."""

_log = logging.getLogger(__name__)
_NEGATIVE_NUMBER = re.compile(r"^-\d+$|^-\d*\.\d+$")
_INFINITE = 1 << 30


# --- The only code that reads the private parts of ``argparse``. ---------------


def _actions(parser: argparse.ArgumentParser) -> list[argparse.Action]:
    return list(parser._actions)  # noqa: SLF001


def _option_map(parser: argparse.ArgumentParser) -> dict[str, argparse.Action]:
    return parser._option_string_actions  # noqa: SLF001


def _exclusive_groups(parser: argparse.ArgumentParser) -> list[list[argparse.Action]]:
    return [
        list(group._group_actions)  # noqa: SLF001
        for group in parser._mutually_exclusive_groups  # noqa: SLF001
    ]


def _is_subparsers(action: argparse.Action) -> bool:
    return isinstance(action, argparse._SubParsersAction)  # noqa: SLF001


def _is_help(action: argparse.Action) -> bool:
    return isinstance(action, argparse._HelpAction)  # noqa: SLF001


def _is_repeatable(action: argparse.Action) -> bool:
    return isinstance(
        action,
        (
            argparse._AppendAction,  # noqa: SLF001
            argparse._AppendConstAction,  # noqa: SLF001
            argparse._CountAction,  # noqa: SLF001
            argparse._ExtendAction,  # noqa: SLF001
        ),
    )


def _subcommand_help(action: argparse.Action) -> dict[str, str]:
    """Map every subcommand name, aliases included, to its help text."""
    choices: Mapping[str, argparse.ArgumentParser] = action.choices or {}  # type: ignore[assignment]
    pseudo: list[argparse.Action] = getattr(action, "_choices_actions", [])
    by_parser = {id(choices[p.dest]): p.help for p in pseudo if p.dest in choices}
    return {
        name: _first_line(by_parser.get(id(parser)) or parser.description)
        for name, parser in choices.items()
    }


# --------------------------------------------------------------------------------


def set_completer(action: argparse.Action, completer: ArgCompleter) -> argparse.Action:
    """Attach a completer to an argparse action.

    The completer is stored in the ``completer`` attribute of the action, the
    name that ``argcomplete`` uses, so existing setups keep working. It gets
    the word being typed and returns strings or dropdown items.

    Args:
        action: The action that ``add_argument`` returned.
        completer: A function that gets the current word and returns the
            possible values. If it raises an exception, there are no
            candidates and the error is logged.

    Returns:
        The same action, so the call can be chained.

    Example:
        >>> parser = argparse.ArgumentParser()
        >>> action = parser.add_argument("--mode")
        >>> _ = set_completer(action, lambda word: ["read", "write"])
        >>> action.completer("")  # type: ignore[attr-defined]
        ['read', 'write']
    """
    action.completer = completer  # type: ignore[attr-defined]
    return action


def _first_line(text: str | None) -> str:
    lines = (text or "").strip().splitlines()
    return lines[0].strip() if lines and text != argparse.SUPPRESS else ""


def _help(action: argparse.Action) -> str:
    """The first line of the help of an action, with ``%(name)s`` expanded."""
    text = action.help
    if not text or text == argparse.SUPPRESS:
        return ""
    try:
        text = text % {**vars(action), "prog": ""}
    except (KeyError, ValueError, TypeError):
        pass
    return _first_line(text)


def _takes_values(action: argparse.Action) -> bool:
    return action.nargs != 0


def _arity(action: argparse.Action) -> tuple[int, int]:
    """The least and most values an action takes."""
    nargs = action.nargs
    if nargs is None:
        return 1, 1
    if isinstance(nargs, int):
        return nargs, nargs
    return {
        argparse.OPTIONAL: (0, 1),
        argparse.ZERO_OR_MORE: (0, _INFINITE),
        argparse.ONE_OR_MORE: (1, _INFINITE),
        argparse.REMAINDER: (0, _INFINITE),
        argparse.PARSER: (1, _INFINITE),
    }.get(nargs, (1, 1))


def _metavar(action: argparse.Action) -> str:
    metavar = action.metavar
    if isinstance(metavar, tuple):
        return metavar[0] if metavar else ""
    if metavar:
        return metavar
    if _is_subparsers(action):
        return "COMMAND" if action.dest == argparse.SUPPRESS else action.dest.upper()
    return action.dest.upper() if action.option_strings else action.dest


@dataclass
class _Context:
    """Where the parsing of the words before the cursor ended."""

    parser: argparse.ArgumentParser
    used: dict[argparse.Action, int] = field(default_factory=dict)
    pending: list[Any] | None = None  # [action, values taken]
    positional: int = 0
    taken: int = 0
    after_separator: bool = False
    valid: bool = True

    @property
    def positionals(self) -> list[argparse.Action]:
        return [a for a in _actions(self.parser) if not a.option_strings]

    def current_positional(self) -> argparse.Action | None:
        """Skip the positionals that took all their values, and return the next."""
        positionals = self.positionals
        while self.positional < len(positionals):
            if self.taken < _arity(positionals[self.positional])[1]:
                return positionals[self.positional]
            self.positional += 1
            self.taken = 0
        return None


def _is_option_like(parser: argparse.ArgumentParser, word: str) -> bool:
    return (
        len(word) > 1
        and word[0] in parser.prefix_chars
        and not _NEGATIVE_NUMBER.match(word)
    )


def _read_option(ctx: _Context, word: str) -> None:
    """Record an option word, with an attached ``=value`` or short cluster."""
    parser = ctx.parser
    options = _option_map(parser)
    ctx.pending = None
    action = options.get(word)
    if action is None and "=" in word:
        action = options.get(word.split("=", 1)[0])
        if action is not None:
            ctx.used[action] = ctx.used.get(action, 0) + 1
            return
    if action is not None:
        ctx.used[action] = ctx.used.get(action, 0) + 1
        if _takes_values(action):
            ctx.pending = [action, 0]
        return
    if word[1] in parser.prefix_chars:
        return
    flags = word[1:]
    for index, flag in enumerate(flags):
        action = options.get(word[0] + flag)
        if action is None:
            return
        ctx.used[action] = ctx.used.get(action, 0) + 1
        if _takes_values(action):
            if index == len(flags) - 1:
                ctx.pending = [action, 0]
            return


def _read_positional(ctx: _Context, word: str) -> _Context:
    action = ctx.current_positional()
    if action is None:
        return ctx
    if _is_subparsers(action):
        choices: Mapping[str, argparse.ArgumentParser] = action.choices or {}  # type: ignore[assignment]
        if word in choices:
            return _Context(choices[word])
        ctx.valid = False
        return ctx
    ctx.taken += 1
    return ctx


def _read_words(parser: argparse.ArgumentParser, words: list[str]) -> _Context:
    ctx = _Context(parser)
    for word in words:
        if not ctx.valid:
            break
        if ctx.after_separator:
            ctx = _read_positional(ctx, word)
        elif word == "--":
            ctx.after_separator = True
            ctx.pending = None
        elif _is_option_like(ctx.parser, word):
            _read_option(ctx, word)
        elif ctx.pending is not None:
            ctx.pending[1] += 1
            if ctx.pending[1] >= _arity(ctx.pending[0])[1]:
                ctx.pending = None
        else:
            ctx = _read_positional(ctx, word)
    return ctx


class ArgparseCompleter:
    """A candidate source for :class:`CommandAutoComplete` built from argparse parsers.

    Describe the commands with a mapping ``{command: parser}``, which is read
    on every call so commands can be added later, or with one root parser
    whose subparsers are the commands. For the word at the cursor, it offers:

    - the command names, with the first line of each description as help;
    - the ``choices`` or the completer of an option or positional that
      expects a value, also after ``--option=``;
    - the options that are not used yet, with their help. ``append`` and
      ``count`` options stay available, a used member of a mutually
      exclusive group hides the others, and ``-h`` and options with
      ``help=argparse.SUPPRESS`` are hidden;
    - the next positional, counted with ``nargs``, or the names of the
      subcommands. After a lone ``--`` only positionals are offered.

    It never calls ``parse_args``, so nothing is printed and nothing exits.
    The parsers are read through some private ``argparse`` attributes
    (``_actions``, ``_option_string_actions``, ``_SubParsersAction`` and
    others), which have not changed since Python 3.2.

    The candidates are not filtered by the typed word. The dropdown does that.

    Example:
        >>> import argparse
        >>> parser = argparse.ArgumentParser(prog="open", description="Open a file.")
        >>> _ = parser.add_argument("--mode", choices=["r", "w"], help="How to open")
        >>> complete = ArgparseCompleter({"open": parser}, hints=False)
        >>> [item.value for item in complete("")]
        ['open']
        >>> [item.value for item in complete("open --m")]
        ['--mode']
        >>> [item.value for item in complete("open --mode ")]
        ['r', 'w']
    """

    def __init__(
        self,
        parsers: Mapping[str, argparse.ArgumentParser] | argparse.ArgumentParser,
        *,
        hints: bool = True,
        show_help_option: bool = False,
    ) -> None:
        """Create the completer.

        Args:
            parsers: A mapping from command name to its parser, or a root
                parser with subparsers.
            hints: Whether to show a :class:`CompletionHint` with the name and
                help of the value the cursor expects.
            show_help_option: Whether to offer ``-h`` and ``--help``.
        """
        self._parsers = parsers
        self._hints = hints
        self._show_help_option = show_help_option

    def __call__(self, line: str) -> list[DropdownItem]:
        """Return the candidates for the last word of ``line``.

        Args:
            line: The command line up to the cursor.

        Returns:
            The items, hints first. An unclosed quote gives no candidates.
        """
        try:
            start, _ = last_token_span(line)
            words = shlex.split(line[:start])
            current = (shlex.split(line[start:]) or [""])[0]
        except ValueError:
            return []
        if isinstance(self._parsers, Mapping):
            return self._complete_mapping(self._parsers, words, current)
        return self._complete(self._parsers, words, current)

    def _complete_mapping(
        self,
        parsers: Mapping[str, argparse.ArgumentParser],
        words: list[str],
        current: str,
    ) -> list[DropdownItem]:
        if not words:
            items: list[DropdownItem] = [
                CommandItem(name, _first_line(parser.description))
                for name, parser in parsers.items()
            ]
            return items
        parser = parsers.get(words[0])
        return self._complete(parser, words[1:], current) if parser else []

    def _complete(
        self, parser: argparse.ArgumentParser, words: list[str], current: str
    ) -> list[DropdownItem]:
        ctx = _read_words(parser, words)
        if not ctx.valid:
            return []
        if ctx.after_separator:
            return self._positional_items(ctx, current)
        typing_option = current[:1] != "" and current[0] in ctx.parser.prefix_chars
        if ctx.pending is not None and not typing_option:
            return self._value_items(ctx.pending[0], current)
        if typing_option:
            name, equals, value = current.partition("=")
            action = _option_map(ctx.parser).get(name)
            if equals and action is not None and _takes_values(action):
                return self._value_items(action, value, prefix=f"{name}=")
            return self._option_items(ctx)
        return self._positional_items(ctx, current)

    def _option_items(self, ctx: _Context) -> list[DropdownItem]:
        hidden = {
            member
            for group in _exclusive_groups(ctx.parser)
            if any(ctx.used.get(action) for action in group)
            for member in group
        }
        items: list[DropdownItem] = []
        for action in _actions(ctx.parser):
            if not action.option_strings or action.help == argparse.SUPPRESS:
                continue
            if _is_help(action) and not self._show_help_option:
                continue
            if ctx.used.get(action) and not _is_repeatable(action):
                continue
            if action in hidden and not ctx.used.get(action):
                continue
            items.extend(CommandItem(s, _help(action)) for s in action.option_strings)
        return items

    def _positional_items(self, ctx: _Context, current: str) -> list[DropdownItem]:
        action = ctx.current_positional()
        if action is None:
            return []
        if not _is_subparsers(action):
            return self._value_items(action, current)
        helps = _subcommand_help(action)
        items: list[DropdownItem] = [CommandItem(n, h) for n, h in helps.items()]
        return self._with_hint(action, items)

    def _value_items(
        self, action: argparse.Action, current: str, *, prefix: str = ""
    ) -> list[DropdownItem]:
        items: list[DropdownItem] = []
        completer: ArgCompleter | None = getattr(action, "completer", None)
        if completer is not None:
            items = _run_completer(completer, current, prefix)
        elif action.choices is not None:
            items = [DropdownItem(prefix + str(choice)) for choice in action.choices]
        return self._with_hint(action, items)

    def _with_hint(
        self, action: argparse.Action, items: list[DropdownItem]
    ) -> list[DropdownItem]:
        if not self._hints or action.help == argparse.SUPPRESS:
            return items
        text = _metavar(action)
        if help_text := _help(action):
            text = f"{text}: {help_text}"
        return [CompletionHint(text), *items]


def _run_completer(
    completer: ArgCompleter, current: str, prefix: str
) -> list[DropdownItem]:
    """Call a completer. A failure is logged and gives no candidates."""
    try:
        results = list(completer(current))
    except Exception:
        _log.exception("The completer %r failed", completer)
        return []
    items: list[DropdownItem] = []
    for result in results:
        if isinstance(result, CompletionHint):
            items.append(result)
        elif isinstance(result, CommandItem):
            items.append(CommandItem(prefix + result.value, result.help, result.prefix))
        elif isinstance(result, DropdownItem):
            items.append(DropdownItem(prefix + result.value, result.prefix))
        else:
            items.append(DropdownItem(prefix + str(result)))
    return items
