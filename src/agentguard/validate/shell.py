"""Shell command lines, split before they are judged (IMPROVEMENTS.md A2, A5, R13).

Every Bash check used to be a regular expression over the raw line, so text that merely
*mentions* a command was judged as one: a heredoc writing docs about `rm -rf /`, a commit
message saying "never git push --force", a grep for "DROP TABLE". This module splits a
line into its simple commands first — the pieces joined by `;`, `&&`, `||`, `|`, `&` and
newlines — with quotes, comments and here-document bodies respected.

Each piece is then read into a `Part`: its argv with redirections, leading assignments and
wrappers (`env`, `nohup`, `time`, `timeout N`, `nice`, `xargs`, ...) removed, so checks see
the command that actually runs.

Provenance: the scanner (`_end_word`, `_bodies`, `split`) and the part reader (`_part`)
are ported from Pebble, `backend/pebble/shell_policy.py` (`_end_word`, `_bodies`,
`_scan`, `_part`; same owner, Apache-2.0), whose tests include a zsh-oracle fuzz test.
Changes from Pebble:

* each piece keeps its offsets in the line and the separators on either side, so a
  rewrite can be applied in place (A5) and an `a || b` list is never mistaken for `a; b`;
* reasons a piece cannot be fully read (command substitution, a subshell, ...) are kept
  per piece rather than for the whole line, so one `$(...)` does not blind every check;
* it never raises, and it reads at most `MAX_SCAN` characters (R13). Pebble refuses
  anything over 8,000 characters; a guard that refused would fail open silently.

Everything here is linear in the length of the line.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from pathlib import PurePosixPath

# R13: a 900 KB command line once cost 203 s in backtracking regexes, wedging the daemon.
# Nothing past this many characters is scanned; `Split.truncated` says so.
MAX_SCAN = 64 * 1024

_END_WORD_STOP = frozenset(" \t\n;&|<>()")

# Commands that run the command after their own options (Pebble's WRAPPERS, plus
# `timeout N` and `xargs`, handled in `_part`).
WRAPPERS = frozenset({"env", "nohup", "time", "nice", "command", "exec", "caffeinate", "stdbuf"})
# A word in command position that makes the piece control flow, not a simple command.
OPAQUE_KEYWORDS = frozenset(
    {
        "if", "then", "else", "elif", "fi", "for", "while", "until", "do", "done", "case",
        "esac", "function", "select", "[[", "{", "}", "eval", "source", ".", "coproc", "trap",
    }
)
_OPERATOR = frozenset("<>&|")
_ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=.*", re.S)
# xargs options that take a value (GNU and BSD).
_XARGS_VALUED = frozenset({"-n", "-I", "-J", "-L", "-P", "-R", "-S", "-s", "-E", "-d", "-a"})
_ENV_VALUED = frozenset({"-u", "--unset", "-C", "--chdir"})
_PRIVILEGE = frozenset({"sudo", "doas"})
_SUDO_VALUED = frozenset({"-u", "-g", "-C", "-D", "-h", "-p", "-r", "-t", "-U", "-T"})


@dataclass(frozen=True, slots=True)
class Piece:
    """One simple command, as written.

    `text` excludes a trailing comment and any here-document body (which follow the
    command line, never inside it); `line[start:end] == text`.
    """

    text: str
    start: int
    end: int
    before: str  # the separator before it: "", ";", "&&", "||", "|", "&" or "\n"
    after: str  # the separator after it, same alphabet
    opaque: tuple[str, ...] = ()  # why it cannot be fully read; empty when it can

    @property
    def piped(self) -> bool:
        """Its output goes into the next piece."""
        return self.after == "|"

    @property
    def piped_in(self) -> bool:
        """It reads the previous piece's output."""
        return self.before == "|"


@dataclass(frozen=True, slots=True)
class Heredoc:
    """One here-document: its end word, whether that word was quoted (the body is then
    literal), the body, and the index of the piece that holds its `<<`."""

    word: str
    quoted: bool
    body: str
    piece: int


@dataclass(frozen=True, slots=True)
class Split:
    line: str  # what was scanned: at most MAX_SCAN characters of the command
    pieces: tuple[Piece, ...]
    heredocs: tuple[Heredoc, ...] = ()
    reasons: tuple[str, ...] = ()  # reasons that concern the whole line
    truncated: bool = False


def _end_word(line: str, i: int) -> tuple[str, bool, int]:
    """The end word of a here-document whose operator ends just before `i`: (word without
    its quotes, whether any of it was quoted, the index after it). Ported from Pebble."""
    n = len(line)
    while i < n and line[i] in " \t":
        i += 1
    word: list[str] = []
    quoted = False
    quote: str | None = None
    while i < n:
        c = line[i]
        if quote:
            if c == quote:
                quote = None
            else:
                word.append(c)
        elif c in ('"', "'"):
            quote, quoted = c, True
        elif c == "\\" and i + 1 < n:
            word.append(line[i + 1])
            quoted = True
            i += 1
        elif c in _END_WORD_STOP:
            break
        else:
            word.append(c)
        i += 1
    return "".join(word), quoted, i


def _bodies(
    line: str,
    i: int,
    pending: list[tuple[str, bool, bool, int]],
    reasons: list[str],
    docs: list[Heredoc],
) -> int:
    """Read the bodies of the pending here-documents from `i` (the start of the line after
    their command line), in order; each ends at a line that is exactly its word (leading
    tabs stripped for `<<-`). Returns the index after the last end line. A body that never
    ends takes the rest of the line. Ported from Pebble."""
    n = len(line)
    for word, quoted, strip, piece in pending:
        lines: list[str] = []
        start = i
        while True:
            if i >= n:
                reasons.append("a heredoc without its end line")
                docs.append(Heredoc(word, quoted, line[start:], piece))
                return n
            end = line.find("\n", i)
            text = line[i:] if end < 0 else line[i:end]
            i = n if end < 0 else end + 1
            if (text.lstrip("\t") if strip else text) == word:
                break
            lines.append(text)
        body = "".join(text + "\n" for text in lines)
        docs.append(Heredoc(word, quoted, body, piece))
    return i


def split(command: str) -> Split:
    """Split a command line at its top-level `;` `&&` `||` `|` `&` and newlines.

    Respects quotes and escapes; drops comments; reads each here-document's body up to its
    end line without splitting it. Never raises.
    """
    if not isinstance(command, str):
        return Split("", ())
    truncated = len(command) > MAX_SCAN
    line = command[:MAX_SCAN] if truncated else command

    pieces: list[Piece] = []
    docs: list[Heredoc] = []
    line_reasons: list[str] = []
    piece_reasons: list[str] = []
    # (word, quoted, strip tabs, piece index) for here-documents whose bodies start after
    # the current command line.
    pending: list[tuple[str, bool, bool, int]] = []
    nested: list[str] = []  # closing characters of the ${...} and $[...] expansions open
    i, n = 0, len(line)
    quote: str | None = None
    piece_start = 0
    comment_at = -1  # where a comment cut the current piece short
    before = ""

    def close(at: int, separator: str) -> None:
        nonlocal piece_start, comment_at, before, piece_reasons
        stop = comment_at if comment_at >= 0 else at
        raw = line[piece_start:stop]
        text = raw.strip()
        if text:
            start = piece_start + (len(raw) - len(raw.lstrip()))
            pieces.append(
                Piece(
                    text=text,
                    start=start,
                    end=start + len(text),
                    before=before,
                    after=separator,
                    opaque=tuple(dict.fromkeys(piece_reasons)),
                )
            )
            before = separator
        elif separator and pieces:
            # An empty piece between two separators (`a ;; b`, a blank line): the later
            # separator is the one that binds the next piece.
            before = separator
        piece_reasons = []
        comment_at = -1

    while i < n:
        c = line[i]
        if comment_at >= 0:
            # Inside a comment: only its newline matters.
            j = line.find("\n", i)
            i = n if j < 0 else j
            if i >= n:
                break
            c = line[i]
        if quote == "'":
            if c == "'":
                quote = None
            i += 1
            continue
        if c == "\\" and i + 1 < n:
            i += 2
            continue
        if quote == '"':
            if c == '"':
                quote = None
            elif c == "`" or line.startswith("$(", i):
                piece_reasons.append("command substitution")
            i += 1
            continue
        if c in ('"', "'"):
            quote = c
            i += 1
            continue
        if line.startswith(("${", "$["), i):
            nested.append("]" if line[i + 1] == "[" else "}")
            i += 2
            continue
        if nested and c == nested[-1]:
            nested.pop()
        if line.startswith("<<<", i):
            i += 3  # a here-string: one word of input
            continue
        if line.startswith("<<", i) and (nested or piece_reasons):
            # Not a here-document to the shell (`${a//<<x}`, `$[1<<2]`), or one inside a
            # piece that is opaque already: its lines stay commands, as Pebble 1.9.28 read
            # every body.
            piece_reasons.append("a heredoc")
            i += 2
            continue
        if line.startswith("<<", i):
            strip = line.startswith("<<-", i)
            word, quoted, end = _end_word(line, i + (3 if strip else 2))
            if word:
                pending.append((word, quoted, strip, len(pieces)))
            else:
                piece_reasons.append("a heredoc without an end word")
            i = end
            continue
        if c == "\n" and pending:
            close(i, "\n")
            first_doc = len(docs)
            i = _bodies(line, i + 1, pending, line_reasons, docs)
            for doc in docs[first_doc:]:
                if not doc.quoted and ("`" in doc.body or "$(" in doc.body):
                    # An unquoted end word: the shell expands the body, substitutions run.
                    owner = doc.piece
                    if 0 <= owner < len(pieces):
                        held = pieces[owner]
                        pieces[owner] = Piece(
                            held.text,
                            held.start,
                            held.end,
                            held.before,
                            held.after,
                            tuple(dict.fromkeys((*held.opaque, "command substitution"))),
                        )
            pending = []
            piece_start = i
            continue
        if c == "`" or line.startswith("$(", i):
            piece_reasons.append("command substitution")
        elif line.startswith(("<(", ">("), i):
            piece_reasons.append("process substitution")
        elif c in "()" and not (c == "(" and i and line[i - 1] == "$"):
            piece_reasons.append("a subshell")
        elif c == "#" and (i == 0 or line[i - 1] in " \t;&|\n"):
            comment_at = i
            continue
        if c in ";\n" or (
            c == "&" and not line.startswith("&>", i) and (i == 0 or line[i - 1] not in "<>")
        ):
            if line.startswith("&&", i):
                close(i, "&&")
                i += 2
            else:
                close(i, c)
                i += 1
            piece_start = i
            continue
        if c == "|":
            if line.startswith("||", i):
                close(i, "||")
                i += 2
            else:
                close(i, "|")
                i += 2 if line.startswith("|&", i) else 1  # `|&` pipes stderr too
            piece_start = i
            continue
        i += 1

    if quote:
        piece_reasons.append("an unclosed quote")
        line_reasons.append("an unclosed quote")
    if pending:
        # The line ends on its command line: no body at all.
        line_reasons.append("a heredoc without its end line")
    if truncated:
        piece_reasons.append("truncated")
        line_reasons.append("truncated")
    close(n, "")
    return Split(
        line=line,
        pieces=tuple(pieces),
        heredocs=tuple(docs),
        reasons=tuple(dict.fromkeys(line_reasons)),
        truncated=truncated,
    )


# -- words --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Word:
    """One word of a simple command, as written (quotes kept), with its offsets in the
    piece's text."""

    raw: str
    start: int
    end: int


def words(text: str) -> list[Word]:
    """Split one simple command into its words at unquoted whitespace.

    Quotes are kept, so callers can tell `"$X"` from `$X` from `'$X'`. A `$(...)`, `${...}`
    or backtick span is one word however much whitespace it holds. A backslash-newline is
    a line continuation. Never raises; an unclosed quote runs to the end.
    """
    out: list[Word] = []
    i, n = 0, len(text)
    start = -1
    quote: str | None = None
    closers: list[str] = []  # the closing characters of open $(...) ${...} `...` spans

    def flush(at: int) -> None:
        nonlocal start
        if start >= 0:
            out.append(Word(text[start:at], start, at))
            start = -1

    while i < n:
        c = text[i]
        if quote == "'":
            if c == "'":
                quote = None
            i += 1
            continue
        if c == "\\" and i + 1 < n:
            if text[i + 1] == "\n" and quote is None and not closers:
                flush(i)  # a line continuation separates words like whitespace
                i += 2
                continue
            if start < 0:
                start = i
            i += 2
            continue
        if quote is None and not closers and c in " \t\n":
            flush(i)
            i += 1
            continue
        if start < 0:
            start = i
        if quote == '"':
            if c == '"' and not closers:
                quote = None
            elif text.startswith("$(", i):
                closers.append(")")
                i += 2
                continue
            elif closers and c == closers[-1]:
                closers.pop()
            i += 1
            continue
        if c in ('"', "'") and not closers:
            quote = c
            i += 1
            continue
        if text.startswith("$(", i) or text.startswith("${", i):
            closers.append(")" if text[i + 1] == "(" else "}")
            i += 2
            continue
        if c == "`":
            if closers and closers[-1] == "`":
                closers.pop()
            else:
                closers.append("`")
            i += 1
            continue
        if closers:
            if c == "(" and closers[-1] == ")":
                closers.append(")")
            elif c == closers[-1]:
                closers.pop()
        i += 1
    flush(n)
    return out


# -- parts ------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Part:
    """One simple command, read: what runs, with what, and where its output goes.

    `argv` is the command after removing redirections, leading `NAME=value` assignments
    and wrappers, with quotes removed (`grep -rn "a b" x` -> `("grep", "-rn", "a b", "x")`).
    An opaque part's argv is a best effort and must not be trusted on its own.
    """

    argv: tuple[str, ...]
    redirects: tuple[tuple[str, str], ...]  # (operator, target)
    assignments: tuple[str, ...]  # leading NAME=value words, as written
    piece: Piece
    wrappers: tuple[str, ...] = ()  # wrapper commands removed from the front, in order
    replace: str = ""  # the replacement string of an `xargs -I R` that runs argv
    opaque: tuple[str, ...] = ()

    @property
    def text(self) -> str:
        return self.piece.text

    @property
    def name(self) -> str:
        """The command's basename (`/usr/bin/git` -> `git`), or "" when there is none."""
        return PurePosixPath(self.argv[0]).name if self.argv else ""


@dataclass(frozen=True, slots=True)
class Parsed:
    line: str
    parts: tuple[Part, ...]
    heredocs: tuple[Heredoc, ...] = ()
    reasons: tuple[str, ...] = ()  # reasons that concern the whole line
    truncated: bool = False

    @property
    def opaque(self) -> bool:
        """Whether anything in the line could not be fully read."""
        return bool(self.reasons) or any(part.opaque for part in self.parts)


def parse(command: str) -> Parsed:
    """The line's parts. Never raises; bounded by `MAX_SCAN`."""
    split_line = split(command)
    parts = tuple(_part(piece) for piece in split_line.pieces)
    return Parsed(
        line=split_line.line,
        parts=parts,
        heredocs=split_line.heredocs,
        reasons=split_line.reasons,
        truncated=split_line.truncated,
    )


def _lex(text: str) -> list[str] | None:
    try:
        lexer = shlex.shlex(text, posix=True, punctuation_chars="<>&|")
        lexer.whitespace_split = True
        lexer.commenters = ""
        return list(lexer)
    except ValueError:
        return None


def _part(piece: Piece) -> Part:
    """Read one piece into argv, redirections and assignments, and strip its wrappers.

    Ported from Pebble `shell_policy._part`.
    """
    opaque = list(piece.opaque)
    # A backslash-newline is a line continuation, not a word.
    tokens = _lex(piece.text.replace("\\\n", " "))
    if tokens is None:
        opaque.append("quoting that cannot be read")
        return Part((), (), (), piece, opaque=tuple(dict.fromkeys(opaque)))

    argv: list[str] = []
    redirects: list[tuple[str, str]] = []
    assignments: list[str] = []
    i = 0
    while i < len(tokens):
        word = tokens[i]
        if word and set(word) <= _OPERATOR:
            redirects.append((word, tokens[i + 1] if i + 1 < len(tokens) else ""))
            i += 2
            continue
        if word.isdigit() and i + 1 < len(tokens) and tokens[i + 1] and set(tokens[i + 1]) <= _OPERATOR:
            i += 1  # a file descriptor before its redirection (2>&1)
            continue
        if not argv and _ASSIGNMENT.fullmatch(word):
            assignments.append(word)
        else:
            argv.append(word)
        i += 1

    # Wrappers run the command after their own options: env FOO=1 cmd, nohup cmd,
    # time cmd, timeout 30 cmd, xargs -n1 cmd.
    wrappers: list[str] = []
    replace = ""
    while argv:
        head = PurePosixPath(argv[0]).name
        if head in WRAPPERS:
            rest = argv[1:]
            while rest and (
                rest[0].startswith("-")
                or (head == "env" and "=" in rest[0])
                or (head == "nice" and rest[0].lstrip("-").isdigit())
            ):
                if len(rest) > 1 and (
                    (head == "nice" and rest[0] == "-n")
                    or (head == "env" and rest[0] in _ENV_VALUED)
                ):
                    rest = rest[1:]  # `nice -n 10 cmd`, `env -u NAME cmd`: the value too
                rest = rest[1:]
            wrappers.append(head)
            argv = rest
            continue
        if head in _PRIVILEGE:
            # Not a wrapper to Pebble, which refuses it outright. Here the command it runs
            # is what gets judged, and `wrappers` keeps the privilege visible.
            rest = argv[1:]
            while rest and rest[0].startswith("-") and rest[0] != "--":
                rest = rest[2:] if rest[0] in _SUDO_VALUED else rest[1:]
            if rest and rest[0] == "--":
                rest = rest[1:]
            wrappers.append(head)
            argv = rest
            continue
        if head == "timeout":
            rest = argv[1:]
            while rest and rest[0].startswith("-"):
                valued = rest[0] in ("-s", "-k", "--signal", "--kill-after")
                rest = rest[2:] if valued else rest[1:]
            wrappers.append(head)
            argv = rest[1:]  # the duration
            continue
        if head == "xargs":
            rest = argv[1:]
            while rest and rest[0].startswith("-"):
                # The replacement string is this xargs's own option, never a word of the
                # part's text (Pebble 1.9.28, sec-w7 1).
                flag = rest[0]
                if flag in ("-I", "-J") and len(rest) > 1:
                    replace = rest[1]
                elif re.fullmatch(r"-[IJ].+", flag):
                    replace = flag[2:]
                elif flag.startswith(("--replace=", "-i")) and flag != "--replace=":
                    replace = flag.split("=", 1)[1] if "=" in flag else flag[2:] or "{}"
                elif flag == "--replace":
                    replace = "{}"
                rest = rest[2:] if flag in _XARGS_VALUED else rest[1:]
            wrappers.append(head)
            argv = rest
            continue
        break

    if argv and (argv[0] in OPAQUE_KEYWORDS or argv[0].endswith("()")):
        opaque.append("control flow")
    return Part(
        argv=tuple(argv),
        redirects=tuple(redirects),
        assignments=tuple(assignments),
        piece=piece,
        wrappers=tuple(wrappers),
        replace=replace,
        opaque=tuple(dict.fromkeys(opaque)),
    )
