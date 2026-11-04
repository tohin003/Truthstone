"""Shell command lines, split before they are judged (IMPROVEMENTS.md A2, A5, R13).

Every Bash check used to be a regular expression over the raw line, so text that merely
*mentions* a command was judged as one: a heredoc writing docs about `rm -rf /`, a commit
message saying "never git push --force", a grep for "DROP TABLE". This module splits a
line into its simple commands first — the pieces joined by `;`, `&&`, `||`, `|`, `&` and
newlines — with quotes, comments and here-document bodies respected.

Provenance: the scanner (`_end_word`, `_bodies`, `split`) is ported from Pebble,
`backend/pebble/shell_policy.py` (`_end_word`, `_bodies`, `_scan`; same owner,
Apache-2.0), whose tests include a zsh-oracle fuzz test. Changes from Pebble:

* each piece keeps its offsets in the line and the separators on either side, so a
  rewrite can be applied in place (A5) and an `a || b` list is never mistaken for `a; b`;
* reasons a piece cannot be fully read (command substitution, a subshell, ...) are kept
  per piece rather than for the whole line, so one `$(...)` does not blind every check;
* it never raises, and it reads at most `MAX_SCAN` characters (R13). Pebble refuses
  anything over 8,000 characters; a guard that refused would fail open silently.

Everything here is linear in the length of the line.
"""

from __future__ import annotations

from dataclasses import dataclass

# R13: a 900 KB command line once cost 203 s in backtracking regexes, wedging the daemon.
# Nothing past this many characters is scanned; `Split.truncated` says so.
MAX_SCAN = 64 * 1024

_END_WORD_STOP = frozenset(" \t\n;&|<>()")


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
