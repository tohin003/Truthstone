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
from dataclasses import dataclass
from functools import lru_cache

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
# `$(cat <<'EOF'` ... a line `EOF` ... `)`: a commit message, a PR body.
_CAT_HEREDOC = re.compile(
    r"\$\(\s*+cat\s*+<<(?P<strip>-?)\s*+(?P<q>['\"]?)(?P<word>[A-Za-z_][A-Za-z0-9_]*+)(?P=q)[ \t]*+\n"
)
_CLOSE = re.compile(r"\s*+\)")
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
    literal), the body, the index of the piece that holds its `<<`, and what it is to the
    command that reads it (`parse` decides; see `_kind`)."""

    word: str
    quoted: bool
    body: str
    piece: int
    kind: str = ""


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

    data_substitutions = True  # cleared after one `$(cat <<WORD` without its end
    substitution = 0  # depth of unquoted `$(` ... `)` spans open

    def data_substitution(at: int) -> int:
        """The index after `$(cat <<'WORD' ... WORD)` at `at` — a here-document fed to
        `cat` inside a command substitution, which is pure data — or -1.

        This is how Claude Code writes every commit message and PR body
        (`git commit -m "$(cat <<'EOF' ... EOF)"`). Read as an opaque substitution, its text
        was judged as commands. An unquoted end word whose body holds `$(` or a backtick
        still runs them, so it is not data.
        """
        nonlocal data_substitutions
        header = _CAT_HEREDOC.match(line, at)
        if not header:
            return -1
        word, strip = header.group("word"), bool(header.group("strip"))
        i = header.end()
        while i < n:
            end = line.find("\n", i)
            text = line[i:] if end < 0 else line[i:end]
            if (text.lstrip("\t") if strip else text) == word:
                after = _CLOSE.match(line, i + len(text))
                if not after:
                    break
                body = line[header.end() : i]
                if not header.group("q") and ("$(" in body or "`" in body):
                    return -1
                docs.append(Heredoc(word, bool(header.group("q")), body, len(pieces), "data"))
                return after.end()
            if end < 0:
                break
            i = end + 1
        data_substitutions = False  # one failed search per line keeps this linear
        return -1

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
        if c == "$" and data_substitutions and line.startswith("$(", i):
            skipped = data_substitution(i)
            if skipped > 0:
                i = skipped
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
            if c == "$":
                substitution += 1  # its `;` and newlines are its own, not this line's
                i += 2
                continue
        elif line.startswith(("<(", ">("), i):
            piece_reasons.append("process substitution")
        elif c in "()" and not (c == "(" and i and line[i - 1] == "$"):
            piece_reasons.append("a subshell")
            if substitution:
                substitution += 1 if c == "(" else -1
        elif c == "#" and (i == 0 or line[i - 1] in " \t;&|\n"):
            comment_at = i
            continue
        if substitution:
            i += 1  # inside `$(...)`: nothing splits the piece
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


# -- tokens -----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Token:
    """One shell word of a simple command, or one redirection operator.

    `value` has quotes removed, as the command will receive it — except that expansions
    stay as written (`$OUT`, `$(date)`): nothing here evaluates anything. `expands` says
    whether the shell will expand something in it (a `$` or backtick outside single
    quotes), which is what tells `rm -rf "$D"` from `rm -rf '$D'`.
    """

    raw: str
    value: str
    start: int
    end: int
    operator: bool = False
    expands: bool = False


_OPERATORS = ("<<<", "<<-", "&>>", "<<", ">>", ">&", "<&", ">|", "<>", "&>", ">", "<")


def tokens(text: str) -> list[Token]:
    """Split one simple command into words and redirection operators. Never raises.

    Replaces `shlex` for two reasons: shlex drops the difference between `"$D"` and `'$D'`,
    which decides whether a delete names a variable; and it splits `$(echo a b)` into three
    words. A backslash-newline is a line continuation; an unclosed quote runs to the end.
    """
    out: list[Token] = []
    n = len(text)
    i = 0
    while i < n:
        c = text[i]
        if c in " \t\n":
            i += 1
            continue
        if c == "\\" and text.startswith("\\\n", i):
            i += 2
            continue
        # A redirection operator, with the file descriptor before it (`2>`, `2>&1`).
        j = i
        while j < n and text[j].isdigit():
            j += 1
        op = next((o for o in _OPERATORS if text.startswith(o, j)), None)
        # (`<(...)` and `>(...)` are process substitutions: words, not redirections.)
        if op is not None and not (op[0] in "<>" and text.startswith("(", j + len(op))):
            out.append(Token(text[i : j + len(op)], op, i, j + len(op), operator=True))
            i = j + len(op)
            continue
        start = i
        value: list[str] = []
        expands = False
        quote: str | None = None
        closers: list[str] = []
        while i < n:
            c = text[i]
            if quote == "'":
                if c == "'":
                    quote = None
                else:
                    value.append(c)
                i += 1
                continue
            if quote == '"' and not closers:
                if c == '"':
                    quote = None
                    i += 1
                    continue
                if c == "\\" and i + 1 < n and text[i + 1] in '$`"\\\n':
                    if text[i + 1] != "\n":
                        value.append(text[i + 1])
                    i += 2
                    continue
                if c == "$" and i + 1 < n and (text[i + 1].isalnum() or text[i + 1] in "_{(@*#?!$-"):
                    expands = True
                    if text[i + 1] in "({":
                        closers.append(")" if text[i + 1] == "(" else "}")
                        value.append(text[i : i + 2])
                        i += 2
                        continue
                if c == "`":
                    expands = True
                    closers.append("`")
                value.append(c)
                i += 1
                continue
            if closers:
                # Inside $(...), ${...} or `...`: kept verbatim; whitespace does not split.
                if c == "\\" and i + 1 < n:
                    value.append(text[i : i + 2])
                    i += 2
                    continue
                if text.startswith(("$(", "${"), i):
                    closers.append(")" if text[i + 1] == "(" else "}")
                    value.append(text[i : i + 2])
                    i += 2
                    continue
                if c == closers[-1]:
                    closers.pop()
                elif c == "(" and closers[-1] == ")":
                    closers.append(")")
                elif c == "`":
                    closers.append("`")
                value.append(c)
                i += 1
                continue
            if c in " \t\n":
                break
            if c == "\\" and i + 1 < n:
                if text[i + 1] == "\n":
                    break  # a continuation ends the word
                value.append(text[i + 1])
                i += 2
                continue
            if c in "<>" and not text.startswith("(", i + 1):
                break  # a redirection glued to the word: `echo hi>out.txt`
            if c == "&" and i + 1 < n and text[i + 1] == ">":
                break
            if c in ("'", '"'):
                quote = c
                i += 1
                continue
            if c == "$" and i + 1 < n and (text[i + 1].isalnum() or text[i + 1] in "_{(@*#?!$-"):
                expands = True
                if text[i + 1] in "({":
                    closers.append(")" if text[i + 1] == "(" else "}")
                    value.append(text[i : i + 2])
                    i += 2
                    continue
            if c == "`":
                expands = True
                closers.append("`")
            if c in "<>" and text.startswith("(", i + 1):
                closers.append(")")  # process substitution: one word
                value.append(text[i : i + 2])
                i += 2
                continue
            value.append(c)
            i += 1
        if i == start:
            i += 1  # never stall
            continue
        out.append(Token(text[start:i], "".join(value), start, i, expands=expands))
    return out


# -- parts ------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Part:
    """One simple command, read: what runs, with what, and where its output goes.

    `argv` is the command after removing redirections, leading `NAME=value` assignments
    and wrappers, with quotes removed (`grep -rn "a b" x` -> `("grep", "-rn", "a b", "x")`);
    `words` are the same words as tokens. An opaque part's argv is a best effort and must
    not be trusted on its own.
    """

    argv: tuple[str, ...]
    redirects: tuple[tuple[str, str], ...]  # (operator, target)
    assignments: tuple[str, ...]  # leading NAME=value words, as written
    piece: Piece
    wrappers: tuple[str, ...] = ()  # wrapper commands removed from the front, in order
    replace: str = ""  # the replacement string of an `xargs -I R` that runs argv
    opaque: tuple[str, ...] = ()
    words: tuple[Token, ...] = ()
    depth: int = 0  # 0 for the line itself; 1+ inside `sh -c`, `eval` or a shell's heredoc
    scope: int = 0  # parts that share a shell (assignments carry between them)
    reader: str = ""  # "" or the kind of the here-document whose body this part came from
    name: str = ""  # the command's basename (`/usr/bin/git` -> `git`), or ""

    @property
    def text(self) -> str:
        return self.piece.text


@dataclass(frozen=True, slots=True)
class Parsed:
    line: str
    parts: tuple[Part, ...]
    heredocs: tuple[Heredoc, ...] = ()
    reasons: tuple[str, ...] = ()  # reasons that concern the whole line
    truncated: bool = False
    sql: tuple[str, ...] = ()  # here-document bodies read by a database client

    @property
    def opaque(self) -> bool:
        """Whether anything in the line could not be fully read."""
        return bool(self.reasons) or any(part.opaque for part in self.parts)


# Shells that run what they read on their standard input (no -c string).
SHELLS = frozenset({"sh", "bash", "zsh", "dash", "ksh", "mksh", "ash"})
STDIN_SHELLS = SHELLS | {"fish", "tcsh", "csh"}
INTERPRETERS = frozenset(
    {
        "python", "python3", "node", "ruby", "perl", "php", "deno", "bun", "lua", "swift",
        "Rscript", "julia", "osascript",
    }
)
# Database clients: a body they read is SQL (or the client's own commands).
DB_CLIENTS = frozenset(
    {
        "psql", "mysql", "mariadb", "sqlite3", "sqlcmd", "mongo", "mongosh", "redis-cli",
        "cqlsh", "clickhouse-client", "duckdb", "cockroach",
    }
)
# Programs whose standard input is only ever data to them (sed and awk only without -f).
# Pebble's list (shell_policy.DATA_READERS).
DATA_READERS = frozenset(
    {
        "cat", "tee", "head", "tail", "wc", "sort", "uniq", "grep", "egrep", "fgrep", "rg",
        "sed", "awk", "tr", "cut", "paste", "column", "fmt", "fold", "nl", "rev", "tac", "jq",
        "base64", "xxd", "od", "hexdump", "diff", "cmp", "comm", "pbcopy", "iconv", "shasum",
        "md5", "echo", "printf", "true", "read",
    }
)
NEST_LIMIT = 3
_SHELL_FLAG = re.compile(r"-[a-zA-Z]*c[a-zA-Z]*")
# `git commit -F -`, `gh pr create --body-file -`: a message read from standard input.
_MESSAGE_FROM_STDIN = re.compile(r"(?:^|\s)(?:-F|--file|--body-file)(?:\s+|=)-(?:\s|$)")


def basename(word: str) -> str:
    """`/usr/bin/git` -> `git`, cheaply: this runs once per word in command position."""
    return word.rsplit("/", 1)[-1]


def shell_flag(argv: tuple[str, ...]) -> int | None:
    """The index of a shell's `-c` option (`bash -lc`), or None."""
    return next((i for i, arg in enumerate(argv[1:], 1) if _SHELL_FLAG.fullmatch(arg)), None)


def _kind(readers: list[Part]) -> str:
    """What one here-document is to the parts that read it: the part holding its `<<` and
    the parts it pipes into, so a pipe cannot hide the reader (`cat <<EOF | sh`).

    "commands" when a shell reads it; "sql" when a database client does; "unread" for a
    reader not known to take it as data (judged as Pebble 1.9.28 judged every body: as
    commands, opaque); "code" for an interpreter; else "data". Ported from Pebble `_kind`,
    with "sql" added.
    """
    kinds: set[str] = set()
    for part in readers:
        head = part.name
        if head in STDIN_SHELLS and shell_flag(part.argv) is None:
            kinds.add("commands")
        elif "xargs" in part.wrappers or head in STDIN_SHELLS:
            kinds.add("unread")  # xargs makes it arguments, which a shell given -c '{}' runs
        elif head in DB_CLIENTS:
            kinds.add("sql")
        elif head in INTERPRETERS:
            kinds.add("code")
        elif head in ("git", "gh") and _MESSAGE_FROM_STDIN.search(" ".join(part.argv)):
            kinds.add("data")  # a commit message or PR body
        elif head not in DATA_READERS or (head in ("sed", "awk") and "-f" in part.argv):
            kinds.add("unread")
    return next((kind for kind in ("commands", "sql", "unread", "code") if kind in kinds), "data")


@lru_cache(maxsize=32)
def parse(command: str) -> Parsed:
    """The line's parts. Never raises; bounded by `MAX_SCAN`, nesting by `NEST_LIMIT`.

    Nested `sh -c '...'` strings, `eval` arguments and here-document bodies a shell reads
    are parsed too, each adding its parts. Cached: the validator, the evidence engine and
    MODIFY all read the same command.
    """
    counter = [0]
    return _parse(command if isinstance(command, str) else "", 0, counter)


def _parse(command: str, depth: int, scopes: list[int], reader: str = "") -> Parsed:
    split_line = split(command)
    scope = scopes[0]
    scopes[0] += 1
    parts: list[Part] = []
    sql: list[str] = []
    reasons = list(split_line.reasons)
    top: list[int] = []  # indexes in `parts` of this line's own pieces, by piece index
    docs = list(split_line.heredocs)

    for piece in split_line.pieces:
        part = _part(piece, depth, scope, reader)
        top.append(len(parts))
        parts.append(part)
        nested = _nested_command(part)
        inners = [nested] if nested is not None else []
        if "command substitution" in piece.opaque:
            # `X=$(rm -rf /)`: what a substitution runs is read as commands of its own.
            # The part itself stays opaque, so it is still read whole as well.
            inners.extend(_substitutions(piece.text))
        if not inners:
            continue
        if depth >= NEST_LIMIT:
            parts[top[-1]] = _with_reason(part, "shells nested too deeply")
            continue
        for text in inners:
            inner = _parse(text, depth + 1, scopes, reader)
            parts.extend(inner.parts)
            sql.extend(inner.sql)
            docs.extend(inner.heredocs)

    # Each body's readers: the part holding its `<<`, and the parts it pipes into.
    for number, doc in enumerate(split_line.heredocs):
        if doc.kind:  # decided by the scanner (a `$(cat <<EOF ...)` message)
            continue
        readers: list[Part] = []
        if 0 <= doc.piece < len(top):
            at = doc.piece
            readers.append(parts[top[at]])
            while parts[top[at]].piece.piped and at + 1 < len(top):
                at += 1
                readers.append(parts[top[at]])
        kind = _kind(readers) if readers else "unread"
        docs[number] = Heredoc(doc.word, doc.quoted, doc.body, doc.piece, kind)
        if (
            kind not in ("commands", "unread")
            and not doc.quoted
            and ("$(" in doc.body or "`" in doc.body)
            and depth < NEST_LIMIT
        ):
            # An unquoted end word: the shell expands the body before any reader sees it,
            # so its substitutions run even when the body itself is data.
            for text in _substitutions(doc.body):
                inner = _parse(text, depth + 1, scopes, reader)
                parts.extend(inner.parts)
                sql.extend(inner.sql)
                docs.extend(inner.heredocs)
        if kind == "sql":
            sql.append(doc.body)
        elif kind == "unread" and doc.body.strip():
            # A reader that may turn any word into a command (`xargs -n1 sh -c`): the body
            # is judged whole, as one opaque text — even what looks like a comment, which
            # xargs hands on as words (found by the zsh-oracle fuzz).
            scopes[0] += 1
            body = Piece(doc.body, 0, len(doc.body), "", "", ("a heredoc read as input",))
            parts.append(
                Part((), (), (), body, opaque=body.opaque, depth=depth + 1, scope=scopes[0], reader=kind)
            )
        elif kind == "commands" and doc.body.strip():
            if depth >= NEST_LIMIT:
                reasons.append("shells nested too deeply")
                continue
            inner = _parse(doc.body, depth + 1, scopes, kind)
            parts.extend(inner.parts)
            sql.extend(inner.sql)
            docs.extend(inner.heredocs)

    return Parsed(
        line=split_line.line,
        parts=tuple(parts),
        heredocs=tuple(docs),
        reasons=tuple(dict.fromkeys(reasons)),
        truncated=split_line.truncated,
        sql=tuple(sql),
    )


def _with_reason(part: Part, reason: str) -> Part:
    return Part(
        part.argv,
        part.redirects,
        part.assignments,
        part.piece,
        part.wrappers,
        part.replace,
        tuple(dict.fromkeys((*part.opaque, reason))),
        part.words,
        part.depth,
        part.scope,
        part.reader,
        part.name,
    )


def _substitutions(text: str) -> list[str]:
    """The commands inside `$(...)` and backticks in one piece, outermost only (each is
    parsed in turn, so inner ones are found then). `$((...))` is arithmetic, not a
    command. Linear: every substitution is stepped over once."""
    found: list[str] = []
    i, n = 0, len(text)
    quote: str | None = None
    while i < n:
        c = text[i]
        if quote == "'":
            if c == "'":
                quote = None
            i += 1
            continue
        if c == "\\":
            i += 2
            continue
        if c == '"':
            quote = None if quote == '"' else '"'
            i += 1
            continue
        if c == "'" and quote is None:
            quote = "'"
            i += 1
            continue
        if text.startswith("$(", i) and not text.startswith("$((", i):
            end = _closing(text, i + 2)
            found.append(text[i + 2 : end])
            i = end + 1
            continue
        if c == "`":
            end = text.find("`", i + 1)
            end = n if end < 0 else end
            found.append(text[i + 1 : end])
            i = end + 1
            continue
        i += 1
    return [inner for inner in found if inner.strip()]


def _closing(text: str, i: int) -> int:
    """The index of the `)` closing a `$(` whose body starts at `i`, or len(text)."""
    depth, n = 1, len(text)
    quote: str | None = None
    while i < n:
        c = text[i]
        if quote:
            if c == "\\" and quote == '"':
                i += 2
                continue
            if c == quote:
                quote = None
        elif c == "\\":
            i += 2
            continue
        elif c in ("'", '"'):
            quote = c
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return n


def _nested_command(part: Part) -> str | None:
    """The command string a part hands to another shell: `sh -c '...'`, `eval ...`."""
    if not part.argv:
        return None
    if part.name in SHELLS:
        flag = shell_flag(part.argv)
        if flag is not None and flag + 1 < len(part.argv):
            return part.argv[flag + 1]
        return None
    if part.name == "eval" and len(part.argv) > 1:
        return " ".join(part.argv[1:])
    return None


def _part(piece: Piece, depth: int = 0, scope: int = 0, reader: str = "") -> Part:
    """Read one piece into argv, redirections and assignments, and strip its wrappers.

    Ported from Pebble `shell_policy._part`.
    """
    opaque = list(piece.opaque)
    words: list[Token] = []
    redirects: list[tuple[str, str]] = []
    assignments: list[str] = []
    stream = tokens(piece.text)
    i = 0
    while i < len(stream):
        token = stream[i]
        if token.operator:
            target = stream[i + 1] if i + 1 < len(stream) and not stream[i + 1].operator else None
            redirects.append((token.value, target.value if target else ""))
            i += 2 if target else 1
            continue
        if not words and _ASSIGNMENT.fullmatch(token.raw) and not token.raw.startswith(("'", '"')):
            assignments.append(token.raw)
        else:
            words.append(token)
        i += 1

    # Wrappers run the command after their own options: env FOO=1 cmd, nohup cmd,
    # time cmd, timeout 30 cmd, xargs -n1 cmd.
    wrappers: list[str] = []
    replace = ""
    while words:
        argv = [w.value for w in words]
        head = basename(argv[0])
        if head in WRAPPERS:
            k = 1
            while k < len(argv) and (
                argv[k].startswith("-")
                or (head == "env" and "=" in argv[k])
                or (head == "nice" and argv[k].lstrip("-").isdigit())
            ):
                if k + 1 < len(argv) and (
                    (head == "nice" and argv[k] == "-n") or (head == "env" and argv[k] in _ENV_VALUED)
                ):
                    k += 1  # `nice -n 10 cmd`, `env -u NAME cmd`: the value too
                elif head == "env" and _ASSIGNMENT.fullmatch(argv[k]):
                    assignments.append(words[k].raw)  # `env HUSKY=0 git commit`: the same as a prefix
                k += 1
            wrappers.append(head)
            words = words[k:]
            continue
        if head in _PRIVILEGE:
            # Not a wrapper to Pebble, which refuses it outright. Here the command it runs
            # is what gets judged, and `wrappers` keeps the privilege visible.
            k = 1
            while k < len(argv) and argv[k].startswith("-") and argv[k] != "--":
                k += 2 if argv[k] in _SUDO_VALUED else 1
            if k < len(argv) and argv[k] == "--":
                k += 1
            wrappers.append(head)
            words = words[k:]
            continue
        if head == "timeout":
            k = 1
            while k < len(argv) and argv[k].startswith("-"):
                k += 2 if argv[k] in ("-s", "-k", "--signal", "--kill-after") else 1
            wrappers.append(head)
            words = words[k + 1 :]  # and the duration
            continue
        if head == "xargs":
            k = 1
            while k < len(argv) and argv[k].startswith("-"):
                # The replacement string is this xargs's own option, never a word of the
                # part's text (Pebble 1.9.28, sec-w7 1).
                flag = argv[k]
                if flag in ("-I", "-J") and k + 1 < len(argv):
                    replace = argv[k + 1]
                elif re.fullmatch(r"-[IJ].+", flag):
                    replace = flag[2:]
                elif flag.startswith(("--replace=", "-i")) and flag != "--replace=":
                    replace = flag.split("=", 1)[1] if "=" in flag else flag[2:] or "{}"
                elif flag == "--replace":
                    replace = "{}"
                k += 2 if flag in _XARGS_VALUED else 1
            wrappers.append(head)
            words = words[k:]
            continue
        break

    argv_out = tuple(w.value for w in words)
    # `eval` with literal arguments is read like `sh -c` (`_nested_command`); anything else
    # in OPAQUE_KEYWORDS is control flow.
    readable_eval = (
        bool(argv_out)
        and argv_out[0] == "eval"
        and len(argv_out) > 1
        and not any(w.expands for w in words[1:])
    )
    if argv_out and not readable_eval and (argv_out[0] in OPAQUE_KEYWORDS or argv_out[0].endswith("()")):
        opaque.append("control flow")
    return Part(
        argv=argv_out,
        redirects=tuple(redirects),
        assignments=tuple(assignments),
        piece=piece,
        wrappers=tuple(wrappers),
        replace=replace,
        opaque=tuple(dict.fromkeys(opaque)),
        words=tuple(words),
        depth=depth,
        scope=scope,
        reader=reader,
        name=basename(argv_out[0]) if argv_out else "",
    )
