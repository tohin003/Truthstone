"""Where a shell command actually runs a test suite (G3a).

The question the Completion Gate asks of every shell command is narrow: *did this run
the project's tests, and is the command's exit status the test runner's?* A substring
answer got both halves wrong. ``grep -n pytest pyproject.toml``, ``pip install pytest``
and ``git commit -m "…pytest…"`` were counted as test runs — each one silencing the
"no tests were run" block — while ``node --test``, ``make test`` and ``./gradlew test``
were not recognised at all (docs/IMPROVEMENTS.md G3a, probe D).

So a runner counts only in **command position**: the first word of a simple command,
after the shell's own plumbing is peeled away —

* environment assignments, ``env``, ``time``, ``nice``, ``timeout N``, ``sudo``,
  ``nohup`` and friends (``cd`` is a command of its own and simply is not a runner);
* launchers that run their argument as a program: ``uv run``, ``poetry run``,
  ``pdm run``, ``hatch run``, ``npx``, ``bunx``, ``pnpm exec``, ``bundle exec``,
  ``coverage run``;
* interpreter flags, as in ``python -I -B -X dev -m pytest``;
* ``bash -c "<script>"``, whose script is read the same way.

Quoted text, heredoc bodies and comments are never commands. A run that runs nothing
(``--collect-only``, ``--version``, ``--help``, ``--list…``) or never finishes on its own
(``--watch``) is not a test run.

The splitter records the operator after every part, because that decides whether the
command's exit status belongs to the runner: ``pytest -q | tail`` exits with ``tail``'s
status, ``pytest; true`` with ``true``'s, and ``pytest && echo ok`` with pytest's
whenever pytest fails (G1).

Deterministic and dependency-free: nothing is ever executed. The scan is linear and
capped, so a pathological command line costs microseconds, not the daemon.
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass
from pathlib import PurePosixPath

__all__ = [
    "Part",
    "TestInvocation",
    "is_test_command",
    "split",
    "test_invocation",
    "test_invocations",
    "typecheck_invocation",
]

# Operators between simple commands. `|&` (bash: pipe stdout and stderr) is a pipe.
PIPE, AND, OR, SEQ, BACKGROUND, NEWLINE = "|", "&&", "||", ";", "&", "\n"

# Never scan more than this. A runner worth recognising is never 64 KB into a command;
# the cap keeps a pathological command line (a 900 KB heredoc was seen) cheap.
MAX_COMMAND = 64_000
_MAX_NESTING = 3  # `bash -c "sh -c '…'"` and no deeper


@dataclass(frozen=True, slots=True)
class Part:
    """One simple command: its words (quotes removed, redirections dropped) and the
    operator that follows it (``""`` for the last part)."""

    words: tuple[str, ...]
    sep: str = ""


# -- splitting ------------------------------------------------------------------------


def split(command: str) -> list[Part]:
    """Quote-aware split into simple commands. Never raises.

    Understands single, double and ``$'…'`` quotes, backslash escapes and line
    continuations, ``$(…)``, ``${…}`` and backtick substitutions (kept whole, inside
    their word), comments, redirections (``2>&1``, ``> out``, ``&> log``) and heredocs,
    whose bodies are skipped. Grouping parentheses are word boundaries:
    ``(cd x && pytest) | tail`` is the parts ``cd x`` (&&) ``pytest`` (|) ``tail``, which
    is exactly what decides whose exit status the command returns.
    """
    return _Splitter(command[:MAX_COMMAND] if isinstance(command, str) else "").run()


class _Splitter:
    def __init__(self, text: str) -> None:
        self.text = text
        self.i = 0
        self.parts: list[Part] = []
        self.words: list[str] = []
        self.word: list[str] = []
        self.in_word = False
        self.redirect_target = False  # the next word is a redirection target, not an arg
        self.heredocs: list[tuple[str, bool]] = []  # (delimiter, strip leading tabs)

    # -- word and part boundaries --

    def end_word(self) -> None:
        if not self.in_word:
            return
        value = "".join(self.word)
        self.word.clear()
        self.in_word = False
        if self.redirect_target:
            self.redirect_target = False
        else:
            self.words.append(value)

    def end_part(self, sep: str) -> None:
        self.end_word()
        self.redirect_target = False
        if self.words:
            self.parts.append(Part(tuple(self.words), sep))
            self.words = []
        # An empty part (a newline after `|`, `;;`, a leading operator) adds nothing: the
        # previous part keeps the operator it already has.

    # -- scanning --

    def run(self) -> list[Part]:
        text, n = self.text, len(self.text)
        while self.i < n:
            ch = text[self.i]
            if ch == "\\":
                if text[self.i + 1 : self.i + 2] == "\n":  # line continuation
                    self.i += 2
                    continue
                self.in_word = True
                self.word.append(text[self.i + 1 : self.i + 2])
                self.i += 2
            elif ch == "'":
                end = text.find("'", self.i + 1)
                end = n if end < 0 else end
                self.in_word = True
                self.word.append(text[self.i + 1 : end])
                self.i = end + 1
            elif ch == '"':
                self.in_word = True
                self.i = self.double_quoted(self.i + 1)
            elif ch == "$" and text[self.i + 1 : self.i + 2] == "'":
                self.in_word = True
                self.i = self.ansi_quoted(self.i + 2)
            elif ch == "$" and text[self.i + 1 : self.i + 2] in ("(", "{"):
                self.in_word = True
                end = self.balanced(self.i + 1)
                self.word.append(text[self.i : end])
                self.i = end
            elif ch == "`":
                self.in_word = True
                end = text.find("`", self.i + 1)
                end = n if end < 0 else end + 1
                self.word.append(text[self.i : end])
                self.i = end
            elif ch == "#" and not self.in_word:
                end = text.find("\n", self.i)
                self.i = n if end < 0 else end
            elif ch == "\n":
                self.end_part(NEWLINE)
                self.i += 1
                self.skip_heredocs()
            elif ch in " \t\r()":
                self.end_word()
                self.i += 1
            elif ch == ";":
                self.end_part(SEQ)
                self.i += 2 if text[self.i + 1 : self.i + 2] in (";", "&") else 1
            elif ch == "|":
                nxt = text[self.i + 1 : self.i + 2]
                self.end_part(OR if nxt == "|" else PIPE)
                self.i += 2 if nxt in ("|", "&") else 1
            elif ch == "&":
                nxt = text[self.i + 1 : self.i + 2]
                if nxt == "&":
                    self.end_part(AND)
                    self.i += 2
                elif nxt == ">":  # `&>` / `&>>`: redirect stdout and stderr
                    self.end_word()
                    self.i += 3 if text[self.i + 2 : self.i + 3] == ">" else 2
                    self.redirect_target = True
                else:
                    self.end_part(BACKGROUND)
                    self.i += 1
            elif ch in "<>":
                self.redirection()
            else:
                self.in_word = True
                self.word.append(ch)
                self.i += 1
        self.end_part("")
        return self.parts

    def double_quoted(self, i: int) -> int:
        text, n = self.text, len(self.text)
        while i < n:
            ch = text[i]
            if ch == '"':
                return i + 1
            if ch == "\\" and text[i + 1 : i + 2] in ('"', "\\", "$", "`", "\n"):
                if text[i + 1] != "\n":
                    self.word.append(text[i + 1])
                i += 2
                continue
            if ch == "$" and text[i + 1 : i + 2] in ("(", "{"):
                end = self.balanced(i + 1)
                self.word.append(text[i:end])
                i = end
                continue
            self.word.append(ch)
            i += 1
        return n

    def ansi_quoted(self, i: int) -> int:
        text, n = self.text, len(self.text)
        while i < n:
            ch = text[i]
            if ch == "'":
                return i + 1
            if ch == "\\" and i + 1 < n:
                self.word.append(text[i + 1])
                i += 2
                continue
            self.word.append(ch)
            i += 1
        return n

    def balanced(self, i: int) -> int:
        """End (exclusive) of the bracketed construct that opens at ``text[i]``."""
        text, n = self.text, len(self.text)
        opener = text[i]
        closer = ")" if opener == "(" else "}"
        depth = 0
        while i < n:
            ch = text[i]
            if ch == "\\":
                i += 2
                continue
            if ch == "'":
                end = text.find("'", i + 1)
                i = n if end < 0 else end + 1
                continue
            if ch == '"':
                j = i + 1
                while j < n and text[j] != '"':
                    j += 2 if text[j] == "\\" else 1
                i = j + 1
                continue
            if ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    return i + 1
            i += 1
        return n

    def redirection(self) -> None:
        text, n = self.text, len(self.text)
        # A word made only of digits right before the operator is a file descriptor.
        if self.in_word and "".join(self.word).isdigit():
            self.word.clear()
            self.in_word = False
        else:
            self.end_word()
        ch, nxt = text[self.i], text[self.i + 1 : self.i + 2]
        if nxt == "(":  # process substitution: an opaque argument, like `$(…)`
            end = self.balanced(self.i + 1)
            self.in_word = True
            self.word.append(text[self.i : end])
            self.i = end
            return
        if text.startswith("<<<", self.i):  # here-string: the next word is input
            self.i += 3
            self.redirect_target = True
            return
        if ch == "<" and nxt == "<":  # heredoc: its body follows the current line
            self.i += 2
            strip_tabs = text.startswith("-", self.i)
            self.i += 1 if strip_tabs else 0
            while self.i < n and text[self.i] in " \t":
                self.i += 1
            self.heredocs.append((self.heredoc_word(), strip_tabs))
            return
        self.i += 1
        if (ch, nxt) in ((">", ">"), (">", "|"), ("<", ">")):
            self.i += 1
        elif nxt == "&":
            self.i += 1
            start = self.i  # `2>&1`, `>&-`: the target is a descriptor, not a word
            while self.i < n and (text[self.i].isdigit() or text[self.i] == "-"):
                self.i += 1
            if self.i > start:
                return
        self.redirect_target = True

    def heredoc_word(self) -> str:
        """The delimiter after ``<<``, without its quotes."""
        text, n = self.text, len(self.text)
        out: list[str] = []
        while self.i < n and text[self.i] not in " \t\n;&|<>()":
            ch = text[self.i]
            if ch in ("'", '"'):
                end = text.find(ch, self.i + 1)
                end = n if end < 0 else end
                out.append(text[self.i + 1 : end])
                self.i = end + 1
                continue
            if ch != "\\":
                out.append(ch)
            self.i += 1
        return "".join(out)

    def skip_heredocs(self) -> None:
        """At the start of the line after a heredoc operator: skip each body."""
        text, n = self.text, len(self.text)
        while self.heredocs:
            delimiter, strip_tabs = self.heredocs.pop(0)
            while self.i < n:
                end = text.find("\n", self.i)
                line = text[self.i : n if end < 0 else end]
                self.i = n if end < 0 else end + 1
                if (line.lstrip("\t") if strip_tabs else line) == delimiter:
                    break


# -- what a part runs -----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TestInvocation:
    """A test run found in command position, and what can be known about it statically."""

    runner: str  # whose output and exit codes are read: pytest, jest, go, make, …
    family: str  # the suite it verifies, for the timeline: python, js, go, rust, jvm, …
    argv: tuple[str, ...]  # the runner's own words, prefixes and launchers removed
    selectors: tuple[str, ...]  # what narrows the run; empty means the whole suite
    exit_reliable: bool  # the command's exit status is this runner's
    background: bool = False  # launched with a trailing `&`: there is no result yet

    @property
    def key(self) -> str:
        """The normalised command: what makes two runs "the same run"."""
        return " ".join(self.argv)[:200]


def test_invocations(command: str, _depth: int = 0) -> list[TestInvocation]:
    """Every test run in command position, in order."""
    parts = split(command)
    found: list[TestInvocation] = []
    pipefail = False
    for index, part in enumerate(parts):
        if _sets_pipefail(part.words):
            pipefail = True
        stripped, negated = _strip_prefixes(list(part.words))
        reliable = not negated and _exit_is_this_parts(parts, index, pipefail)
        background = part.sep == BACKGROUND
        script = _shell_script(stripped)
        if script is not None:
            if _depth < _MAX_NESTING:
                for inner in test_invocations(script, _depth + 1):
                    found.append(
                        dataclasses.replace(
                            inner,
                            exit_reliable=inner.exit_reliable and reliable,
                            background=inner.background or background,
                        )
                    )
            continue
        run = _runner_of(stripped)
        if run is not None:
            runner, family, argv, selectors = run
            found.append(TestInvocation(runner, family, argv, selectors, reliable, background))
    return found


def test_invocation(command: str) -> TestInvocation | None:
    """The test run whose result the command reports: its last one, or None."""
    found = test_invocations(command)
    return found[-1] if found else None


def is_test_command(command: str) -> bool:
    return bool(test_invocations(command))


def typecheck_invocation(command: str) -> tuple[str, ...] | None:
    """A typecheck run in command position (G7: still running at Stop), or None."""
    for part in split(command):
        words = _strip_launchers(_strip_prefixes(list(part.words))[0])
        if not words:
            continue
        name, args = _program(words[0]), words[1:]
        if _has_flag(args, _WATCH | _NOT_A_RUN) or "-w" in args:
            continue
        if name in ("tsc", "vue-tsc", "mypy", "dmypy", "pyright", "basedpyright"):
            return tuple(words)
        if name == "cargo" and args[:1] in (["check"], ["clippy"]):
            return tuple(words)
        if name == "go" and args[:1] == ["vet"]:
            return tuple(words)
        if name in ("npm", "pnpm", "yarn", "bun"):
            script = _script_name(name, args)
            if script and _TYPECHECK_SCRIPT.match(script):
                return tuple(words)
    return None


# -- exit status ownership --------------------------------------------------------------

# Stages that pass a pipeline's text through and do not fail on their own. Under
# `set -o pipefail` a runner's status survives a pipe into these. `grep` is not one:
# it fails whenever nothing matches.
_TRANSPARENT = frozenset(
    {"tail", "head", "tee", "cat", "sed", "awk", "cut", "sort", "uniq", "nl", "column", "ts", "less", "more"}
)


def _exit_is_this_parts(parts: list[Part], index: int, pipefail: bool) -> bool:
    """The command's exit status is part ``index``'s: only ``&&`` may follow it (G1)."""
    if parts[index].sep == BACKGROUND:
        return False
    for position in range(index, len(parts) - 1):
        sep = parts[position].sep
        if sep == AND:
            continue
        if sep == PIPE and pipefail:
            following = parts[position + 1].words
            if following and _program(following[0]) in _TRANSPARENT:
                continue
        return False
    return True


def _sets_pipefail(words: tuple[str, ...]) -> bool:
    if not words or words[0] != "set":
        return False
    args = words[1:]
    return any(
        re.fullmatch(r"-[a-zA-Z]*o", arg) is not None and args[i + 1 : i + 2] == ("pipefail",)
        for i, arg in enumerate(args)
    )


# -- peeling away the shell's own plumbing ------------------------------------------------

_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\+?=")
_RESERVED = frozenset({"if", "then", "else", "elif", "do", "while", "until", "{"})
_NO_COMMAND = frozenset({"fi", "done", "esac", "}"})
_SHELLS = frozenset({"sh", "bash", "zsh", "dash", "ksh", "mksh", "ash"})
_SHELL_SCRIPT_FLAG = re.compile(r"-[a-zA-Z]*c[a-zA-Z]*")

# Prefix commands, and their options that take a value. Anything else starting with "-"
# is a flag; the first other word starts the real command.
_PREFIXES: dict[str, frozenset[str]] = {
    "env": frozenset({"-u", "--unset", "-C", "--chdir"}),
    "time": frozenset({"-o", "-f", "--output", "--format"}),
    "nice": frozenset({"-n", "--adjustment"}),
    "timeout": frozenset({"-s", "--signal", "-k", "--kill-after"}),
    "gtimeout": frozenset({"-s", "--signal", "-k", "--kill-after"}),
    "sudo": frozenset({"-u", "-g", "-C", "-D", "-h", "-p", "-r", "-t", "-U", "-T", "--user", "--group"}),
    "doas": frozenset({"-u", "-C"}),
    "nohup": frozenset(),
    "stdbuf": frozenset({"-i", "-o", "-e", "--input", "--output", "--error"}),
    "command": frozenset(),
    "exec": frozenset({"-a"}),
    "builtin": frozenset(),
    "xvfb-run": frozenset({"-s", "-n", "-e", "-f", "-p", "-w", "--server-args", "--server-num"}),
    "caffeinate": frozenset({"-t", "-w"}),
}


def _program(word: str) -> str:
    """``./node_modules/.bin/jest`` -> ``jest``; ``.\\gradlew.bat`` -> ``gradlew``."""
    name = PurePosixPath(word.replace("\\", "/")).name.lower()
    for suffix in (".exe", ".cmd", ".bat", ".ps1"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def _strip_prefixes(words: list[str]) -> tuple[list[str], bool]:
    """Drop assignments, reserved words and prefix commands. Returns (words, negated)."""
    negated = False
    for _ in range(16):
        if not words:
            break
        head = words[0]
        if head == "!":
            negated = not negated
            words = words[1:]
        elif head in _RESERVED or _ASSIGNMENT.match(head):
            words = words[1:]
        else:
            name = _program(head)
            if name not in _PREFIXES:
                break
            if name == "command" and words[1:2] in (["-v"], ["-V"]):
                return [], negated  # `command -v pytest` looks a program up
            words = _skip_options(words[1:], _PREFIXES[name])
            if name == "env":
                while words and _ASSIGNMENT.match(words[0]):
                    words = words[1:]
            elif name in ("timeout", "gtimeout") and words:
                words = words[1:]  # the duration
            elif name == "nice":
                while words and re.fullmatch(r"-\d+", words[0]):
                    words = words[1:]
    return words, negated


def _skip_options(words: list[str], valued: frozenset[str]) -> list[str]:
    """Skip leading options (and the values of those in ``valued``)."""
    i = 0
    while i < len(words):
        word = words[i]
        if word == "--":
            return words[i + 1 :]
        if not word.startswith("-") or word == "-":
            break
        i += 2 if word in valued else 1
    return words[i:]


def _shell_script(words: list[str]) -> str | None:
    """The script of ``bash -c '<script>'`` (also ``-lc``, ``-ec``), else None."""
    if len(words) < 3 or _program(words[0]) not in _SHELLS:
        return None
    for i, word in enumerate(words[1:-1], start=1):
        if _SHELL_SCRIPT_FLAG.fullmatch(word):
            return words[i + 1]
        if not word.startswith("-"):
            return None
    return None


# -- launchers ------------------------------------------------------------------------------

_UV_RUN_VALUED = frozenset(
    {
        "--with", "--with-editable", "--with-requirements", "-p", "--python", "--package",
        "--extra", "--group", "--only-group", "--no-group", "--env-file", "--directory",
        "--project", "--index", "--index-url", "--extra-index-url", "--find-links", "-f",
        "--exclude-newer", "--resolution", "--prerelease", "--config-file", "--cache-dir",
        "--color", "--refresh-package", "--reinstall-package", "--upgrade-package", "-P",
        "--keyring-provider", "--link-mode", "--python-preference", "--from",
    }
)
_UV_GLOBAL_VALUED = frozenset(
    {"--directory", "--project", "--config-file", "--cache-dir", "--color", "--python-preference"}
)
_NPX_VALUED = frozenset({"-p", "--package", "--node-options"})
_POETRY_VALUED = frozenset({"-C", "--directory", "-P", "--project"})
_PDM_VALUED = frozenset({"-p", "--project", "--venv"})
_COVERAGE_VALUED = frozenset(
    {"--source", "--rcfile", "--omit", "--include", "--context", "--concurrency", "--data-file"}
)


def _strip_launchers(words: list[str]) -> list[str]:
    """``uv run --frozen pytest -q`` -> ``pytest -q``, repeated for nested launchers.

    A launcher that runs one of the project's *scripts* (``pdm run test``,
    ``hatch run test:cov``) is left in place: the script is the run.
    """
    for _ in range(4):
        if not words:
            return words
        name, rest = _program(words[0]), words[1:]
        if name == "uv":
            rest = _skip_options(rest, _UV_GLOBAL_VALUED)
            if rest[:2] == ["tool", "run"]:
                rest = rest[1:]
            if rest[:1] != ["run"]:
                return words
            words = _uv_run(rest[1:])
        elif name == "uvx":
            words = _uv_run(rest)
        elif name in ("poetry", "pipenv", "rye", "pixi"):
            rest = _skip_options(rest, _POETRY_VALUED)
            if rest[:1] != ["run"]:
                return words
            words = _skip_options(rest[1:], frozenset())
        elif name == "pdm":
            rest = _skip_options(rest, _PDM_VALUED)
            if rest[:1] != ["run"]:
                return words
            target = _skip_options(rest[1:], _PDM_VALUED)
            if target and _TEST_SCRIPT.match(target[0]):
                return words
            words = target
        elif name == "hatch":
            rest = _skip_options(rest, frozenset({"-e", "--env"}))
            if rest[:1] != ["run"]:
                return words
            target = [arg for arg in rest[1:] if not re.match(r"^[+-]\w[\w-]*=", arg)]
            if not target:
                return []
            script = target[0].split(":", 1)[-1]
            if _TEST_SCRIPT.match(script):
                return words
            words = [script, *target[1:]]
        elif name in ("npx", "bunx"):
            if "-c" in rest or "--call" in rest:
                return []  # a shell string, not a program
            words = _skip_options(rest, _NPX_VALUED)
        elif name in ("pnpm", "yarn") and rest[:1] in (["exec"], ["dlx"]):
            words = _skip_options(rest[1:], frozenset({"-C", "--dir"}))
        elif name == "npm" and rest[:1] in (["exec"], ["x"]):
            if "-c" in rest or "--call" in rest:
                return []
            words = _skip_options(rest[1:], _NPX_VALUED)
        elif name == "bun" and rest[:1] == ["x"]:
            words = _skip_options(rest[1:], frozenset())
        elif name == "bundle" and rest[:1] == ["exec"]:
            words = rest[1:]
        elif name == "coverage" and rest[:1] == ["run"]:
            words = ["python", *_until_module(rest[1:], _COVERAGE_VALUED)]
        else:
            return words
    return words


def _uv_run(rest: list[str]) -> list[str]:
    i = 0
    while i < len(rest):
        word = rest[i]
        if word == "--":
            return rest[i + 1 :]
        if word in ("-m", "--module"):
            return ["python", "-m", *rest[i + 1 :]]
        if not word.startswith("-"):
            break
        i += 2 if word in _UV_RUN_VALUED else 1
    return rest[i:]


def _until_module(words: list[str], valued: frozenset[str]) -> list[str]:
    """Skip options up to ``-m module`` or the script (``coverage run [opts] -m pytest``)."""
    i = 0
    while i < len(words):
        word = words[i]
        if word == "-m" or not word.startswith("-"):
            break
        i += 2 if word in valued else 1
    return words[i:]


# -- runners ---------------------------------------------------------------------------------

# Never a test run, whatever the runner: they describe, list, or never finish.
_NOT_A_RUN = frozenset({"--version", "--help", "-h", "--collect-only", "--co", "--dry-run"})
_WATCH = frozenset({"--watch", "--watchAll", "--watch-all", "--ui"})
_RUNNER_NOT_A_RUN: dict[str, frozenset[str]] = {
    "pytest": frozenset({"-V", "--fixtures", "--fixtures-per-test", "--markers", "--setup-plan"}),
    "go": frozenset({"-list"}),
    "cargo": frozenset({"--no-run"}),
    "deno": frozenset({"--no-run"}),
    "mocha": frozenset({"-w"}),
    "dotnet": frozenset({"-t"}),
    "tox": frozenset({"-l", "-a", "--showconfig"}),
    "nox": frozenset({"-l"}),
    "gradle": frozenset({"-m"}),
    "jest": frozenset({"--showConfig", "--clearCache", "--init"}),
}

_TEST_SCRIPT = re.compile(r"^(?:test|tests|t|tst|spec|specs|unit|unittest)(?:$|[:_-](?!.*watch))", re.I)
_TYPECHECK_SCRIPT = re.compile(
    r"^(?:typecheck|type-check|types|check-types|check:types|tsc)(?:$|:\w+$)", re.I
)
_MAKE_TARGET = re.compile(r"^(?:tests?(?:[-_:.]\S*)?|check|unittests?|unit-tests?|integration-tests?)$", re.I)
_TEST_FILE = re.compile(r"(?:^|/)(?:test_[^/]+|[^/]+_tests?|tests?)\.(?:py|rb)$")
_PYTHON = re.compile(r"^(?:python(?:\d+(?:\.\d+)?)?|pypy\d*(?:\.\d+)?|py)$")
_CARGO_GLOBAL_VALUED = frozenset({"-Z", "--color", "--config", "-C"})

# Options whose next word is a value rather than a selector, per runner.
_VALUED: dict[str, frozenset[str]] = {
    "pytest": frozenset(
        {
            "-p", "-o", "-c", "-W", "-r", "-n", "--tb", "--maxfail", "--rootdir", "--basetemp",
            "--durations", "--durations-min", "--import-mode", "--capture", "--log-level",
            "--log-cli-level", "--log-file", "--log-format", "--junitxml", "--junit-prefix",
            "--confcutdir", "--cov", "--cov-report", "--cov-config", "--cov-fail-under",
            "--timeout", "--color", "--override-ini", "--dist", "--maxprocesses", "--reruns",
            "--reruns-delay", "--random-order-seed", "--html", "--alluredir", "--count",
            "--tx", "--rsyncdir", "--asyncio-mode", "--hypothesis-seed", "--benchmark-json",
        }
    ),
    "unittest": frozenset({"-s", "--start-directory", "-t", "--top-level-directory"}),
    "jest": frozenset(
        {
            "-c", "--config", "--maxWorkers", "-w", "--reporters", "--coverageReporters",
            "--rootDir", "--roots", "--testTimeout", "--shard", "--seed", "--outputFile",
            "--coverageDirectory", "--collectCoverageFrom", "--env", "--testEnvironment",
            "--globalSetup", "--globalTeardown", "--setupFiles",
        }
    ),
    "vitest": frozenset(
        {
            "-c", "--config", "-r", "--root", "--dir", "--reporter", "--outputFile", "--pool",
            "--environment", "--maxWorkers", "--minWorkers", "--shard", "--mode",
            "--testTimeout", "--coverage.provider", "--coverage.reporter", "--workspace",
        }
    ),
    "mocha": frozenset({"-r", "--require", "-R", "--reporter", "-t", "--timeout", "--config", "--ui", "-u"}),
    "node": frozenset(
        {
            "--test-reporter", "--test-reporter-destination", "--test-concurrency", "--test-timeout",
            "--import", "--require", "-r", "--loader", "--experimental-loader", "--env-file",
        }
    ),
    "go": frozenset(
        {
            "-p", "-count", "-timeout", "-cpu", "-parallel", "-coverprofile", "-covermode",
            "-coverpkg", "-o", "-tags", "-exec", "-benchtime", "-bench", "-cpuprofile",
            "-memprofile", "-blockprofile", "-mutexprofile", "-outputdir", "-trace", "-shuffle",
            "-fuzztime", "-gcflags", "-ldflags", "-mod", "-modfile", "-C", "-vet",
        }
    ),
    "cargo": frozenset(
        {
            "--features", "-F", "--target", "--target-dir", "-j", "--jobs", "--manifest-path",
            "--profile", "--message-format", "--color", "-Z", "--config", "--test-threads",
        }
    ),
    "nextest": frozenset(
        {
            "--features", "-F", "--target", "--target-dir", "-j", "--jobs", "--manifest-path",
            "--profile", "-P", "--cargo-profile", "--test-threads", "--retries", "--color",
            "--partition", "--message-format", "--config",
        }
    ),
    "gradle": frozenset({"-p", "--project-dir", "-D", "-P", "-I", "--init-script", "-c", "--settings-file"}),
    "maven": frozenset({"-f", "--file", "-s", "--settings", "-T", "--threads", "-P", "--activate-profiles"}),
    "dotnet": frozenset(
        {
            "-c", "--configuration", "-f", "--framework", "-r", "--runtime", "-v", "--verbosity",
            "-l", "--logger", "-s", "--settings", "-a", "--test-adapter-path", "-o", "--output",
            "--results-directory", "-d", "--diag", "--blame-hang-timeout",
        }
    ),
    "rspec": frozenset({"-r", "--require", "-f", "--format", "-o", "--out", "--seed", "-I"}),
    "phpunit": frozenset(
        {"-c", "--configuration", "--bootstrap", "--log-junit", "--testdox-html", "--cache-directory"}
    ),
    "tox": frozenset({"-c", "--conf", "--workdir", "--root", "-x", "--override", "-p", "--parallel"}),
    "nox": frozenset({"-f", "--noxfile", "--envdir", "--python", "-p", "--force-python", "-db"}),
    "deno": frozenset(
        {"--config", "-c", "--import-map", "--location", "--seed", "--reporter", "--junit-path"}
    ),
    "bun": frozenset(
        {"--timeout", "--preload", "--rerun-each", "--coverage-reporter", "--coverage-dir", "--reporter"}
    ),
    "playwright": frozenset(
        {
            "-c", "--config", "--project", "--reporter", "-j", "--workers", "--retries", "--timeout",
            "--output", "--shard", "--repeat-each", "--max-failures",
        }
    ),
    "swift": frozenset(
        {"--configuration", "-c", "--package-path", "--scratch-path", "-j", "--jobs", "--num-workers"}
    ),
    "mix": frozenset({"--seed", "--max-failures", "--slowest", "--timeout", "--formatter"}),
    "make": frozenset(
        {"-C", "--directory", "-f", "--file", "--makefile", "-j", "--jobs", "-l", "-I", "-o", "-W"}
    ),
    "just": frozenset({"-f", "--justfile", "-d", "--working-directory", "--set", "--dotenv-path"}),
}

# Options whose value narrows the run: the pair becomes a selector.
_FILTERS: dict[str, frozenset[str]] = {
    "pytest": frozenset({"-k", "-m", "--deselect", "--ignore", "--ignore-glob"}),
    "unittest": frozenset({"-k"}),
    "jest": frozenset(
        {
            "-t", "--testNamePattern", "--testPathPattern", "--testPathPatterns", "--findRelatedTests",
            "--changedSince", "--selectProjects", "--testPathIgnorePatterns",
        }
    ),
    "vitest": frozenset({"-t", "--testNamePattern", "--project", "--changed", "--exclude"}),
    "mocha": frozenset({"-g", "--grep", "-f", "--fgrep", "--spec"}),
    "node": frozenset({"--test-name-pattern", "--test-skip-pattern", "--test-shard"}),
    "go": frozenset({"-run", "-skip"}),
    "cargo": frozenset({"-p", "--package", "--test", "--bin", "--example", "--bench", "--exclude"}),
    "nextest": frozenset(
        {"-p", "--package", "-E", "--filter-expr", "--filterset", "--test", "--bin", "--exclude"}
    ),
    "gradle": frozenset({"--tests"}),
    "maven": frozenset({"-pl", "--projects"}),
    "dotnet": frozenset({"--filter"}),
    "rspec": frozenset({"-e", "--example", "-t", "--tag"}),
    "phpunit": frozenset({"--filter", "--group", "--testsuite", "--exclude-group"}),
    "tox": frozenset({"-e", "--env", "-m", "--labels", "-f", "--factors"}),
    "nox": frozenset({"-s", "--session", "--sessions", "-k", "--keywords", "-t", "--tags"}),
    "deno": frozenset({"--filter"}),
    "bun": frozenset({"-t", "--test-name-pattern"}),
    "playwright": frozenset({"-g", "--grep", "--grep-invert"}),
    "swift": frozenset({"--filter", "--skip"}),
    "mix": frozenset({"--only", "--exclude", "--include"}),
    "rails": frozenset({"-n", "--name", "-e"}),
    "minitest": frozenset({"-n", "--name", "-e", "--exclude"}),
    "django": frozenset({"-k", "--tag", "--exclude-tag", "-p", "--pattern"}),
    "npm": frozenset(
        {"-w", "--workspace", "--filter", "-F", "--filter-prod", "--prefix", "-C", "--dir", "--cwd"}
    ),
}

# Flags that narrow the run on their own.
_NARROWING: dict[str, frozenset[str]] = {
    "pytest": frozenset({"--lf", "--last-failed", "--sw", "--stepwise", "--sw-skip", "--stepwise-skip"}),
    "jest": frozenset({"-o", "--onlyChanged", "--onlyFailures", "-f", "--lastCommit"}),
    "vitest": frozenset({"--related"}),
    "node": frozenset({"--test-only"}),
    "cargo": frozenset({"--lib", "--bins", "--examples", "--tests", "--benches", "--doc", "--exact"}),
    "nextest": frozenset({"--lib", "--bins", "--tests", "--run-ignored"}),
    "mix": frozenset({"--failed", "--stale"}),
    "playwright": frozenset({"--last-failed", "--only-changed"}),
    "rspec": frozenset({"--only-failures", "--next-failure", "-n"}),
}

# A package script (`npm test -- …`) passes what follows `--` to a JavaScript runner this module
# cannot see, so any of their name or path filters, and any flag of theirs that narrows a run on its
# own, narrows it (day 3: `npm test -- --test-name-pattern=x` was read as the whole suite). Their
# long valued options keep their values off the selectors; a short one is ambiguous between
# runners (`-t` is mocha's timeout and jest's name filter), so its value stays a selector: a run
# read as narrower than it was asks for one more run, never fewer.
_SCRIPT_RUNNERS = ("jest", "vitest", "mocha", "node", "bun", "playwright")
_SCRIPT_FILTERS = frozenset().union(*(_FILTERS[runner] for runner in _SCRIPT_RUNNERS))
_SCRIPT_NARROWING = frozenset().union(*(_NARROWING.get(runner, frozenset()) for runner in _SCRIPT_RUNNERS))
_SCRIPT_VALUED = frozenset(
    option
    for runner in _SCRIPT_RUNNERS
    for option in _VALUED.get(runner, frozenset())
    if option.startswith("--") and option not in _SCRIPT_FILTERS
)

# Single-component folders that stand for the whole suite, as `pytest tests/` does in
# nearly every project (Pebble's rule: a bare runner or its test folder runs the suite).
# A deeper folder (`tests/unit`) narrows the run.
_WHOLE_SUITE = frozenset({".", "tests", "test", "spec", "specs", "__tests__", "t", "...", "./..."})


def _runner_of(words: list[str]) -> tuple[str, str, tuple[str, ...], tuple[str, ...]] | None:
    """(runner, family, argv, selectors) when this part runs tests."""
    if not words or words[0] in _NO_COMMAND:
        return None
    argv = _strip_launchers(words)
    if not argv:
        return None
    found = _identify(argv)
    if found is None:
        return None
    runner, family, args = found
    excluded = _NOT_A_RUN | _WATCH | _RUNNER_NOT_A_RUN.get(runner, frozenset())
    if _has_flag(args, excluded) or any(arg.lower().startswith("--list") for arg in args):
        return None
    if runner == "maven" and any(_skips_maven_tests(arg) for arg in args):
        return None
    return runner, family, tuple(argv), _selectors(runner, args)


def _has_flag(args: list[str], flags: frozenset[str]) -> bool:
    return any(arg in flags or arg.split("=", 1)[0] in flags for arg in args)


def _skips_maven_tests(arg: str) -> bool:
    lowered = arg.lower()
    return lowered.startswith(("-dskiptests", "-dmaven.test.skip")) and not lowered.endswith("=false")


def _identify(argv: list[str]) -> tuple[str, str, list[str]] | None:
    """(runner, family, the runner's arguments) for a part that runs tests, else None."""
    name, args = _program(argv[0]), argv[1:]

    if name in ("pytest", "py.test"):
        return "pytest", "python", args
    if _PYTHON.match(name):
        return _python(args)
    if name in ("jest", "mocha", "_mocha"):
        return ("mocha" if name == "_mocha" else name), "js", args
    if name == "vitest":
        if args[:1] and args[0] in ("watch", "dev", "list", "bench", "init", "typecheck"):
            return None
        if args[:1] == ["run"]:
            args = args[1:]
        elif args[:1] == ["related"]:
            args = ["--related", *args[1:]]
        return "vitest", "js", args
    if name == "playwright":
        return ("playwright", "playwright", args[1:]) if args[:1] == ["test"] else None
    if name == "node":
        if "--test" in args:
            return "node", "js", [arg for arg in args if arg != "--test"]
        if "--run" in args:
            at = args.index("--run")
            script = args[at + 1] if at + 1 < len(args) else ""
            if _TEST_SCRIPT.match(script):
                return "npm", "js", args[at + 2 :]
        return None
    if name in ("npm", "pnpm", "yarn", "bun"):
        return _package_manager(name, args)
    if name in ("turbo", "nx"):
        # Monorepo task runners: `turbo run test`, `nx run-many -t test`, `nx test api`.
        tasks = [arg.split(":")[-1] for arg in args if not arg.startswith("-")]
        tasks += [arg.split("=", 1)[1] for arg in args if arg.startswith(("--target=", "--targets="))]
        tasks += [args[i + 1] for i, arg in enumerate(args[:-1]) if arg in ("-t", "--target", "--targets")]
        if any(_TEST_SCRIPT.match(task) for task in tasks) and "watch" not in " ".join(args):
            return "npm", "js", [arg for arg in args if arg.startswith("--filter")]
        return None
    if name == "deno":
        return ("deno", "js", args[1:]) if args[:1] == ["test"] else None
    if name == "go":
        return ("go", "go", args[1:]) if args[:1] == ["test"] else None
    if name == "cargo":
        rest = _skip_options([arg for arg in args if not arg.startswith("+")], _CARGO_GLOBAL_VALUED)
        if rest[:1] in (["test"], ["t"]):
            return "cargo", "rust", rest[1:]
        if rest[:1] == ["nextest"] and rest[1:2] in (["run"], ["r"]):
            return "nextest", "rust", rest[2:]
        return None
    if name in ("make", "gmake", "just"):
        runner = "just" if name == "just" else "make"
        rest = _skip_options(args, _VALUED[runner])
        targets = [arg for arg in rest if not arg.startswith("-") and not _ASSIGNMENT.match(arg)]
        return (runner, runner, rest) if any(_MAKE_TARGET.match(t) for t in targets) else None
    if name in ("tox", "nox"):
        return _tox_nox(name, args)
    if name == "hatch":
        if args[:1] == ["test"]:
            return "hatch", "python", args[1:]
        if args[:1] == ["run"]:  # left in place by `_strip_launchers`: a test script
            return "script", "python", args[1:]
        return None
    if name == "pdm":
        rest = _skip_options(args, _PDM_VALUED)
        return ("script", "python", rest[1:]) if rest[:1] == ["run"] else None
    if name in ("gradle", "gradlew"):
        tasks = [arg for arg in args if not arg.startswith("-")]
        if any(re.search(r"(?:^|:)(?:test\w*|check)$", task) for task in tasks):
            return "gradle", "jvm", args
        return None
    if name in ("mvn", "mvnw"):
        phases = [arg for arg in args if not arg.startswith("-")]
        if any(p in ("test", "verify", "integration-test") or p.endswith(":test") for p in phases):
            return "maven", "jvm", args
        return None
    if name == "rspec":
        return "rspec", "ruby", args
    if name in ("rails", "rake"):
        if args[:1] and re.fullmatch(r"(?:test|spec)(?::[\w:]+)?", args[0]):
            return "rails", "ruby", args[1:]
        return None
    if name == "ruby":
        return _ruby(args)
    if name in ("phpunit", "pest", "paratest"):
        return "phpunit", "php", args
    if name == "php":
        if args[:2] == ["artisan", "test"]:
            return "phpunit", "php", args[2:]
        if args and _program(args[0]) in ("phpunit", "pest", "paratest"):
            return "phpunit", "php", args[1:]
        return None
    if name == "dotnet":
        return ("dotnet", "dotnet", args[1:]) if args[:1] == ["test"] else None
    if name == "swift":
        if args[:1] == ["test"] and args[1:2] != ["list"]:
            return "swift", "swift", args[1:]
        return None
    if name == "mix":
        return ("mix", "elixir", args[1:]) if args[:1] == ["test"] else None
    if name == "django-admin":
        return ("django", "python", args[1:]) if args[:1] == ["test"] else None
    return None


def _python(args: list[str]) -> tuple[str, str, list[str]] | None:
    """``python [interpreter flags] (-m module | script) …``."""
    i = 0
    while i < len(args):
        arg = args[i]
        if arg in ("-c", "--version", "-V", "--help", "-h"):
            return None
        if arg == "-m" or re.fullmatch(r"-[bBdEiIOPqRsSuvx]+m", arg):
            if i + 1 >= len(args):
                return None
            return _python_module(args[i + 1], args[i + 2 :])
        if arg in ("-X", "-W"):
            i += 2
            continue
        if arg.startswith("-"):
            i += 1  # -I -B -u, -Xdev, `py -3.12`
            continue
        script, rest = arg.replace("\\", "/"), args[i + 1 :]
        if PurePosixPath(script).name == "manage.py":
            return ("django", "python", rest[1:]) if rest[:1] == ["test"] else None
        if script.endswith(".py") and _TEST_FILE.search(script):
            return "unittest", "python", [script, *rest]
        return None
    return None


def _python_module(module: str, rest: list[str]) -> tuple[str, str, list[str]] | None:
    if module in ("pytest", "py.test"):
        return "pytest", "python", rest
    if module == "unittest":
        return "unittest", "python", rest
    if module in ("tox", "nox"):
        return _tox_nox(module, rest)
    if module == "coverage" and rest[:1] == ["run"]:
        return _python(_until_module(rest[1:], _COVERAGE_VALUED))
    if module == "django" and rest[:1] == ["test"]:
        return "django", "python", rest[1:]
    return None


def _ruby(args: list[str]) -> tuple[str, str, list[str]] | None:
    """``ruby -Itest test/models/user_test.rb``: minitest's autorun."""
    i = 0
    while i < len(args):
        arg = args[i]
        if arg in ("-e", "--version", "-v", "--help", "-h"):
            return None
        if arg in ("-I", "-r", "-C"):
            i += 2
            continue
        if arg.startswith("-"):
            i += 1
            continue
        if arg.endswith(".rb") and _TEST_FILE.search(arg.replace("\\", "/")):
            return "minitest", "ruby", [arg, *args[i + 1 :]]
        return None
    return None


_PM_VALUED = frozenset(
    {"-w", "--workspace", "--prefix", "-C", "--dir", "--filter", "-F", "--cwd", "--filter-prod", "--loglevel"}
)
_PM_SCOPE = _FILTERS["npm"]
_PM_SUBCOMMANDS = frozenset(
    {
        "add", "install", "i", "ci", "remove", "rm", "uninstall", "update", "up", "upgrade",
        "link", "publish", "pack", "init", "create", "audit", "outdated", "why", "list", "ls",
        "info", "view", "config", "set", "cache", "store", "import", "dedupe", "patch", "env",
        "setup", "build", "start", "dev", "lint", "format", "version", "login", "logout",
        "whoami", "workspace", "workspaces", "dlx", "exec", "x",
    }
)


def _package_manager(name: str, args: list[str]) -> tuple[str, str, list[str]] | None:
    """``npm test``, ``pnpm --filter api test``, ``yarn workspace api test``, ``bun test``."""
    if name == "bun" and args[:1] == ["test"]:
        return "bun", "js", args[1:]
    scope: list[str] = []
    rest = list(args)
    while rest and rest[0].startswith("-"):  # options before the subcommand
        option, equals, value = rest[0].partition("=")
        takes_value = option in _PM_VALUED and not equals
        if option in _PM_SCOPE:
            scope.append(f"{option}={value if equals else (rest[1] if len(rest) > 1 else '')}")
        rest = rest[2:] if takes_value else rest[1:]
    if name == "yarn" and rest[:1] == ["workspace"] and len(rest) >= 3:
        scope.append(f"workspace={rest[1]}")
        rest = rest[2:]
    elif name == "yarn" and rest[:1] == ["workspaces"]:
        if "run" not in rest:
            return None
        rest = rest[rest.index("run") :]
    script = _script_name(name, rest)
    if script is not None:
        if not _TEST_SCRIPT.match(script) or "watch" in script.lower():
            return None
        return "npm", "js", [*scope, *_script_args(rest[rest.index(script) + 1 :])]
    # `pnpm vitest`, `yarn jest`: a package manager also runs a dependency's binary.
    if name in ("pnpm", "yarn") and rest and rest[0] not in _PM_SUBCOMMANDS:
        found = _identify(rest)
        if found is not None:
            runner, family, inner = found
            return runner, family, [*scope, *inner]
    return None


def _script_name(name: str, rest: list[str]) -> str | None:
    """The package script a package-manager command runs, if any."""
    if not rest:
        return None
    head = rest[0]
    if head in ("test", "t", "tst") and name != "bun":
        return head
    if head in ("run", "run-script", "rum", "urn"):
        return next((arg for arg in rest[1:] if not arg.startswith("-")), None)
    if name in ("yarn", "pnpm") and head not in _PM_SUBCOMMANDS and (
        _TEST_SCRIPT.match(head) or _TYPECHECK_SCRIPT.match(head)
    ):
        return head
    return None


def _script_args(args: list[str]) -> list[str]:
    """What a package script receives that can narrow it."""
    if "--" in args:
        return args[args.index("--") + 1 :]
    return [arg for arg in args if not arg.startswith("-")]


_TEST_ENV = re.compile(r"^(?:py\S*|pypy\S*|tests?\S*|unit\S*|integration\S*|cov\S*|ALL|all)$")


def _tox_nox(name: str, args: list[str]) -> tuple[str, str, list[str]] | None:
    rest = list(args)
    if name == "tox" and rest[:1] and not rest[0].startswith("-"):
        if rest[0] not in ("run", "r", "run-parallel", "p"):
            return None  # list, config, devenv, exec, depends, quickstart, legacy
        rest = rest[1:]
    flags = ("-e", "--env") if name == "tox" else ("-s", "--session", "--sessions")
    selected: list[str] = []
    for i, arg in enumerate(rest):
        option, equals, value = arg.partition("=")
        if option in flags:
            value = value if equals else (rest[i + 1] if i + 1 < len(rest) else "")
            selected.extend(v for v in re.split(r"[,\s]+", value) if v)
    if selected and not any(_TEST_ENV.match(env) for env in selected):
        return None  # `tox -e lint`, `nox -s docs`: not the test suite
    return name, "python", rest


# -- selectors --------------------------------------------------------------------------------


def _selectors(runner: str, args: list[str]) -> tuple[str, ...]:
    """What narrows this run; empty means the whole suite.

    Positional paths and node ids, filter options with their values (``-k expr``,
    ``--testNamePattern x``, ``-run X``) and options that narrow on their own (``--lf``).
    Folders that stand for the whole suite (``tests/``, ``.``, ``./...``) are dropped.
    """
    valued = _VALUED.get(runner, frozenset())
    filters = _FILTERS.get(runner, frozenset())
    narrowing = _NARROWING.get(runner, frozenset())
    if runner == "npm":  # a package script: its arguments go to an unseen JavaScript runner
        valued, filters, narrowing = _SCRIPT_VALUED, filters | _SCRIPT_FILTERS, _SCRIPT_NARROWING
    out: list[str] = []
    i = 0
    if runner == "unittest" and args[:1] == ["discover"]:
        args = args[1:]
    while i < len(args):
        arg = args[i]
        if arg == "--":
            i += 1
            continue
        option, equals, value = arg.partition("=")
        if arg.startswith("-") and len(arg) > 1:
            if option in filters:
                if not equals:
                    value = args[i + 1] if i + 1 < len(args) else ""
                    i += 1
                out.append(f"{option}={value}")
            elif runner == "pytest" and re.fullmatch(r"-[km]\S+", arg):
                out.append(f"{arg[:2]}={arg[2:]}")
            elif runner == "unittest" and option in ("-p", "--pattern"):
                if not equals:
                    value = args[i + 1] if i + 1 < len(args) else ""
                    i += 1
                if not any(c in value for c in "*?["):
                    out.append(f"{option}={value}")  # one file's pattern narrows the run
            elif option in narrowing:
                out.append(option)
            elif runner == "maven" and option.lower().startswith(("-dtest", "-dit.test")):
                out.append(arg)
            elif option in valued and not equals:
                i += 1
            i += 1
            continue
        word = _normalise_path(arg)
        if runner in ("make", "just", "gradle", "maven", "tox", "nox", "script"):
            # Targets, tasks, phases and envs name *what* runs; the plain one is the suite.
            if not _plain_target(runner, word) and not _ASSIGNMENT.match(word):
                out.append(word)
        elif word and word not in _WHOLE_SUITE:
            out.append(word)
        i += 1
    whole_tree = any(_normalise_path(arg) in ("...", "./...") for arg in args)
    if runner == "go" and not whole_tree and all(s.startswith("-") for s in out):
        out.append(".")  # `go test` alone tests only the package in the current folder
    return tuple(sorted(dict.fromkeys(out)))


def _plain_target(runner: str, word: str) -> bool:
    if runner in ("make", "just"):
        return word.lower() in ("test", "tests", "check")
    if runner == "gradle":
        return word in ("clean", "test", "check", "build")
    if runner == "maven":
        return word in ("clean", "test", "verify", "integration-test", "install", "package")
    if runner == "tox":
        return word in ("run", "r", "p", "run-parallel")
    if runner == "script":
        return bool(_TEST_SCRIPT.match(word.split(":", 1)[-1]))
    return False


def _normalise_path(word: str) -> str:
    out = word.replace("\\", "/")
    while out.startswith("./") and len(out) > 2 and out != "./...":
        out = out[2:]
    return out.rstrip("/") if len(out) > 1 else out
