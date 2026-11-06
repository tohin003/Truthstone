"""The checks behind SPEC §18's validation pipeline.

    Agent proposal -> Evidence -> Scope -> Architecture -> Risk -> Complexity -> Decision

Evidence is Phase 3's engine; this module supplies the rest. Each check is a small
function returning findings, tagged with the escalation level it costs to run so the
validator can short-circuit (SPEC §7).

Every check here is written to under-report. Scope creep needs a *pattern* before it is
worth mentioning, and a dangerous command has to be unambiguously dangerous. The cost of
a missed finding is one imperfect edit; the cost of a false one is the developer turning
the whole layer off.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from truthstone.core.config import truthstone_home
from truthstone.core.enums import (
    ChallengeCategory,
    EscalationLevel,
    FailureMode,
    PlanningDepth,
    Severity,
    Verdict,
)
from truthstone.core.events import SHELL_TOOLS, AgentEvent
from truthstone.core.models import EvidenceRef, Finding
from truthstone.core.taskstate import DEFAULT_UNRELATED_LIMIT, TaskState
from truthstone.repo import manifests, scanner
from truthstone.repo.index import RepoIndex
from truthstone.validate import effects, shell

log = logging.getLogger(__name__)

# A DIRECT-band task that has rewritten this much of the repository is not the task that
# was described, whatever the file paths say.
DIRECT_BAND_FILE_LIMIT = 8

# How much agreement it takes before a repository is deemed to *have* a convention.
# Below this, "the siblings do it differently" is a coincidence, not a pattern — and a
# census built on coincidences is worse than no census.
CONVENTION_MIN_SIBLINGS = 5

# Only source files count toward scope and proportionality (IMPROVEMENTS.md A4). A docs
# typo sweep and a monorepo dependency bump were each denied at file 9 because every
# README and manifest they touched was counted as drift.
_NOT_SOURCE = frozenset({"markdown", "yaml", "json", "toml", "unknown"})


def counts_toward_scope(path: str) -> bool:
    """Whether a changed file is evidence about the task's scope: source, not docs, data,
    configuration or a dependency manifest."""
    if manifests.is_manifest(path.rsplit("/", 1)[-1]):
        return False
    return scanner.detect_language(path) not in _NOT_SOURCE


# -- scope (SPEC §18) -------------------------------------------------------------


def scope_creep(state: TaskState, index: RepoIndex, path: str = "") -> list[Finding]:
    """SPEC §18's worked example.

        Task: Fix login validation.
        Agent attempts: Modify 17 unrelated files.
        Expected scope: authentication module -> SCOPE VIOLATION -> CHALLENGE

    Raised once per task. After the agent has heard it and chosen to continue, repeating
    it is nagging (SPEC §17).

    `path` is the file the proposed edit writes, when there is one. Only the validator's
    mutating file tools reach this: a scope challenge used to land on whatever came next,
    including the agent's own `pytest` (IMPROVEMENTS.md A4).
    """
    if state.scope_challenged:
        return []

    spec = state.spec
    findings: list[Finding] = []

    # Everything reachable from the expected scope counts as related: its importers, its
    # imports, and its tests. Only genuine outliers are worth raising.
    related: set[str] = set(spec.expected_scope)
    for scoped in spec.expected_scope:
        related |= index.blast_radius(scoped, depth=2)
        related |= index.tests_for(scoped)
        related |= {record.resolved for record in index.imports_of(scoped) if record.resolved}

    unrelated = {p for p in state.unrelated_files(related) if counts_toward_scope(p)}
    if len(unrelated) >= DEFAULT_UNRELATED_LIMIT:
        findings.append(
            Finding(
                category=ChallengeCategory.SCOPE,
                verdict=Verdict.INSUFFICIENT_EVIDENCE,
                failure_mode=FailureMode.UNRELATED_FILES_MODIFIED,  # SPEC §3
                severity=Severity.HIGH,
                subject="scope",
                summary=(
                    f"{len(unrelated)} file(s) changed that the task does not reach"
                ),
                detail=(
                    f"The request was: \"{spec.goal or spec.prompt[:120]}\". Its evidence points at "
                    f"{', '.join(sorted(spec.expected_scope)[:3])}"
                    f"{'…' if len(spec.expected_scope) > 3 else ''}. "
                    f"These changes are outside that and outside anything connected to it: "
                    f"{', '.join(sorted(unrelated)[:6])}"
                    f"{'…' if len(unrelated) > 6 else ''}."
                ),
                evidence=[EvidenceRef(source="filesystem", path=p) for p in sorted(unrelated)[:6]],
                suggestion=(
                    "Either explain what connects these to the task, or split them into a "
                    "separate change."
                ),
                level=EscalationLevel.REPOSITORY,
            )
        )
        return findings

    # A proportionality check that does not depend on scope resolving at all.
    source = {p for p in state.touched_files if counts_toward_scope(p)}
    if spec.complexity.depth is PlanningDepth.DIRECT and _crosses_direct_band(source, path):
        findings.append(
            Finding(
                category=ChallengeCategory.SCOPE,
                verdict=Verdict.OVERENGINEERED,
                # SPEC §3, "over-plan trivial tasks" — observed through what the agent
                # *did* rather than what it planned. A rename that rewrote nine files is
                # the visible end of over-planning, and it is the only end a
                # deterministic layer can see. §3's planning failure proper is measured
                # in Phase 9, against plan length and tool counts.
                failure_mode=FailureMode.OVERPLANNED_TRIVIAL,
                # Recorded, never raised (IMPROVEMENTS.md A4, approved by the lead). The
                # complexity band is read from the prompt alone, and it is wrong often
                # enough to make this a nag: of 69 real turns that edited 8 or more
                # files, 20 had been rated DIRECT (an upper bound), 14 of them on prompts
                # over 200 characters. The census can count it; the agent never hears it
                # until the census says it is precise.
                severity=Severity.INFO,
                subject="proportionality",
                summary=(
                    f"{len(source) + (1 if path else 0)} source files changed for a task "
                    f"assessed as direct implementation"
                ),
                detail=(
                    f"Complexity was {spec.complexity.score:.0f}/100. Either the task is larger "
                    "than it appeared — in which case say so — or this change has grown beyond it."
                ),
                evidence=[EvidenceRef(source="filesystem", path=p) for p in sorted(source)[:6]],
                level=EscalationLevel.DETERMINISTIC,
            )
        )

    return findings


def _crosses_direct_band(source: set[str], path: str) -> bool:
    """Whether the DIRECT-band limit is reached.

    With the edit's `path`, only the edit that *crosses* the limit — a new source file
    beyond it — is recorded, so the census counts a disproportionate task once rather than
    once per edit after the ninth. Without one, the task's state as a whole is judged.
    """
    if not path:
        return len(source) >= DIRECT_BAND_FILE_LIMIT
    return (
        counts_toward_scope(path)
        and path not in source
        and len(source) == DIRECT_BAND_FILE_LIMIT
    )


# -- read-only commands (IMPROVEMENTS.md A4) -----------------------------------------
#
# A Bash command that only reads, or only runs the tests, changes nothing that the scope
# and evidence checks are about. Pebble pins this (`guard.py:549-573`,
# `test_run_tests_is_never_scope_challenged_while_writes_still_are`). The allowlist is
# short on purpose: a command missing from it is simply checked, which costs a little
# latency and nothing else. Every part of the line must qualify, in command position after
# assignments and wrappers, and nothing may write a file through a redirection.

_READERS = frozenset(
    {"ls", "cat", "head", "tail", "wc", "rg", "grep", "egrep", "fgrep", "pwd", "which", "echo", "printf"}
)
_FIND_WRITES = frozenset(
    {"-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint", "-fprint0", "-fprintf", "-fls"}
)
_GIT_READS = frozenset({"status", "log", "diff", "show", "rev-parse"})
_GIT_BRANCH_LISTING = frozenset(
    {
        "-a", "-r", "-v", "-vv", "--all", "--remotes", "--verbose", "--list", "-l",
        "--show-current", "--color", "--no-color", "--column", "--no-column", "-i",
        "--ignore-case",
    }
)
_GIT_BRANCH_VALUED = frozenset(
    {"--contains", "--no-contains", "--merged", "--no-merged", "--points-at", "--sort", "--format"}
)
# Redirection targets that are not files.
_SINK = re.compile(r"/dev/(?:null|stdout|stderr|tty)|&?-|&?\d{1,2}")
_TEST_RUNNERS = frozenset(
    {"pytest", "py.test", "tox", "nox", "jest", "vitest", "mocha", "ava", "rspec", "phpunit"}
)
_PYTHON_TEST_MODULES = frozenset({"pytest", "unittest", "tox", "nox"})
# Commands whose test subcommand runs the suite: `go test`, `cargo test`, `npm test`.
_TEST_SUBCOMMANDS: dict[str, frozenset[str]] = {
    "go": frozenset({"test"}),
    "cargo": frozenset({"test", "nextest"}),
    "dotnet": frozenset({"test"}),
    "deno": frozenset({"test"}),
    "bun": frozenset({"test"}),
    "npm": frozenset({"test", "t"}),
    "pnpm": frozenset({"test", "t"}),
    "yarn": frozenset({"test"}),
}
# Build tools whose goals must *all* be test goals (`mvn deploy test` publishes).
_TEST_GOALS: dict[str, frozenset[str]] = {
    "mvn": frozenset({"test"}),
    "mvnw": frozenset({"test"}),
    "gradle": frozenset({"test", "check"}),
    "gradlew": frozenset({"test", "check"}),
    "make": frozenset({"test", "check"}),
}
# `npx vitest run`, `uv run pytest`: the command after the launcher is what runs.
_LAUNCHERS: dict[str, frozenset[str]] = {
    "npx": frozenset(),
    "pnpx": frozenset(),
    "bunx": frozenset(),
    "uv": frozenset({"run"}),
    "poetry": frozenset({"run"}),
    "pipenv": frozenset({"run"}),
    "pdm": frozenset({"run"}),
}
_PACKAGE_RUNNERS = frozenset({"npm", "pnpm", "yarn", "bun"})
_PACKAGE_VALUED = frozenset({"--filter", "-F", "--prefix", "-C", "--dir", "--workspace", "-w", "--cwd"})


def read_only_bash(event: AgentEvent) -> bool:
    """Whether a Bash action certainly changes nothing: every part reads or runs tests.

    Unsure means False, and False only means "checked as usual".
    """
    if event.tool != "Bash":
        return False
    command = event.arg("command")
    if not isinstance(command, str) or not command.strip():
        return False
    return read_only(shell.parse(command))


def read_only(parsed: shell.Parsed) -> bool:
    if parsed.truncated or parsed.reasons or not parsed.parts:
        return False
    return all(_reads_only(part) for part in parsed.parts)


def _reads_only(part: shell.Part) -> bool:
    if part.opaque or not part.argv:
        return False
    if any(wrapper in ("sudo", "doas") for wrapper in part.wrappers):
        return False
    for operator, target in part.redirects:
        if ">" in operator and not _SINK.fullmatch(target):
            return False  # writes a file
    name, args = part.name, part.argv[1:]
    if name in _READERS:
        # ripgrep's --pre runs a program on every file it searches.
        return not (name == "rg" and any(a == "--pre" or a.startswith("--pre=") for a in args))
    if name == "find":
        return not any(arg in _FIND_WRITES for arg in args)
    if name == "git":
        return _git_reads(args)
    if name in ("sed", "gsed"):
        return _sed_prints_only(args)
    if len(args) == 1 and args[0] in _ASKS_ITSELF:
        return True  # `node --version`, `python3 -V`, `tsc --help`: the program describes itself
    return _runs_tests(part.argv)


# A program asked only about itself (day 3: `node --version` in a read-only look around held a
# premise note's first edit, which it is not).
_ASKS_ITSELF = frozenset({"--version", "-V", "--help"})
# `sed -n '120,160p' file`: lines printed, nothing written. Only with -n (or --quiet/--silent),
# only -n/-E/-r/-s/-u/-z as options, and a script of addresses each followed by `p`, `l` or `=`:
# no `w` that writes, no `e` that runs, no in-place edit, no script file.
_SED_ADDRESS = r"(?:\d+(?:~\d+)?|\$|/(?:\\.|[^/\\\n])*/I?)"
_SED_PRINT_SCRIPT = re.compile(
    rf"(?:\s*{_SED_ADDRESS}(?:\s*,\s*(?:{_SED_ADDRESS}|\+\d+))?\s*!?\s*[pl=]\s*;?)+\s*"
)
_SED_OPTION = re.compile(r"-[nErsuz]+|--(?:quiet|silent|regexp-extended|separate|unbuffered|null-data)")


def _sed_prints_only(args: tuple[str, ...]) -> bool:
    options = [arg for arg in args if arg.startswith("-") and arg != "-"]
    operands = [arg for arg in args if not arg.startswith("-") or arg == "-"]
    if not operands or not all(_SED_OPTION.fullmatch(option) for option in options):
        return False
    if not any(
        option in ("--quiet", "--silent") or (option[1:2] != "-" and "n" in option) for option in options
    ):
        return False
    return _SED_PRINT_SCRIPT.fullmatch(operands[0]) is not None


# -- positive evidence of a write (day 3) -----------------------------------------------------
#
# The premise hold (``core/engine.py``) waits for the task's first *edit*. "Not provably
# read-only" was the old test, and it held reads: `sed -n`, `node --version`. This is the
# opposite question, answered only on evidence: the command visibly writes, moves or deletes a
# file (an output redirect to a file, `tee`, `sed -i`, `mv`, `cp`, `rm`, `touch`, `mkdir`, `dd
# of=`, a patch), checks out or rewrites the work tree through git, or runs inline interpreter
# code that writes one. Unsure is False.

_TREE_WRITERS = frozenset({"mkdir", "touch", "patch", "apply_patch", "applypatch"})
_GIT_TREE_WRITES = frozenset(
    {
        "apply", "am", "checkout", "restore", "switch", "reset", "stash", "merge", "rebase",
        "cherry-pick", "revert", "mv", "rm", "clean", "pull",
    }
)  # fmt: skip
_INLINE_WRITE = re.compile(
    r"\.(?:write_text|write_bytes)\s*\(|\bopen\s*\([^)]*['\"][rwab+]*[wax][rwab+]*['\"]"
    r"|\b(?:writeFileSync|appendFileSync|writeFile|appendFile|createWriteStream|rmSync|renameSync|"
    r"copyFileSync|unlinkSync)\s*\("
    r"|\bshutil\.(?:copy\w*|move|rmtree)\s*\(|\bos\.(?:remove|rename|replace|unlink|makedirs|mkdir)\s*\("
    r"|\b(?:Path|path)\([^)]*\)\.(?:unlink|rename|replace|mkdir|touch)\s*\("
)


def writes_files(event: AgentEvent) -> bool:
    """Whether a shell action visibly writes, moves or deletes a file (see above). Never raises."""
    if event.tool not in SHELL_TOOLS:
        return False
    command = event.arg("command")
    if not isinstance(command, str) or not command.strip():
        return False
    try:
        return writes(shell.parse(command))
    except Exception:  # a command the shell reader chokes on is no evidence
        log.debug("truthstone: could not read a command for writes", exc_info=True)
        return False


def writes_inside(event: AgentEvent, root: str | Path) -> bool:
    """``writes_files``, less a command whose every visible write lands outside ``root``
    (``pytest -q | tee /tmp/run.log``, ``> /tmp/out.txt``): it changes nothing of the repository
    (day 3). A tree writer, a git work-tree write or inline interpreter code still counts: their
    targets are not read here. Never raises."""
    if not writes_files(event):
        return False
    try:
        parsed = shell.parse(event.arg("command"))
        inline = any(part.name in shell.INTERPRETERS for part in parsed.parts)
        if inline and any(_INLINE_WRITE.search(doc.body) for doc in parsed.heredocs):
            return True
        base = Path(root).resolve()
        for part in parsed.parts:
            if part.name in _TREE_WRITERS or (
                part.name in shell.INTERPRETERS and _INLINE_WRITE.search(" ".join(part.argv[1:]))
            ):
                return True
            if part.name == "git" and effects.git_subcommand(part.argv)[0] in _GIT_TREE_WRITES:
                return True
            for target in effects.written_paths(part):
                value = str(getattr(target, "value", target))
                if _SINK.fullmatch(value):
                    continue
                path = Path(value).expanduser()
                if "$" in value or "`" in value or not path.is_absolute():
                    return True  # relative to the repository, or not known: inside
                if path.resolve(strict=False).is_relative_to(base):
                    return True
        return False
    except Exception:  # a command the shell reader chokes on: as writes_files said
        log.debug("truthstone: could not read a command's write targets", exc_info=True)
        return True


def writes(parsed: shell.Parsed) -> bool:
    inline = any(part.name in shell.INTERPRETERS for part in parsed.parts)
    for part in parsed.parts:
        if any(
            not _SINK.fullmatch(str(getattr(target, "value", target)))
            for target in effects.written_paths(part)
        ):
            return True
        if part.name in _TREE_WRITERS:
            return True
        if part.name == "git":
            sub, _ = effects.git_subcommand(part.argv)
            if sub in _GIT_TREE_WRITES:
                return True
        if part.name in shell.INTERPRETERS and _INLINE_WRITE.search(" ".join(part.argv[1:])):
            return True
    return inline and any(_INLINE_WRITE.search(doc.body) for doc in parsed.heredocs)


def _git_reads(args: tuple[str, ...]) -> bool:
    rest = list(args)
    while rest and rest[0].startswith("-"):
        if rest[0] == "-C" and len(rest) > 1:
            rest = rest[2:]
        elif rest[0] in ("--no-pager", "-P", "--no-optional-locks"):
            rest = rest[1:]
        else:
            return False  # -c, --git-dir, --exec-path ...: not worth trusting
    if not rest:
        return False
    sub, sub_args = rest[0], rest[1:]
    if any(arg.startswith("--output") or arg == "--ext-diff" for arg in sub_args):
        return False  # `git diff --output=FILE` writes
    if sub in _GIT_READS:
        return True
    return sub == "branch" and _lists_branches(sub_args)


def _lists_branches(args: list[str]) -> bool:
    """`git branch`, `-a`, `-vv`, `--list 'feat*'`; never a name that creates one, or -d/-m."""
    listing = False
    positional = False
    i = 0
    while i < len(args):
        arg = args[i]
        if arg in ("--list", "-l"):
            listing = True
        elif arg in _GIT_BRANCH_LISTING:
            pass
        elif arg.split("=", 1)[0] in _GIT_BRANCH_VALUED:
            if "=" not in arg and i + 1 < len(args) and not args[i + 1].startswith("-"):
                i += 1
        elif arg.startswith("-"):
            return False  # -d, -D, -m, -M, -c, -C, -f, -u, --set-upstream-to ...
        else:
            positional = True
        i += 1
    return listing or not positional


def _runs_tests(argv: tuple[str, ...], depth: int = 0) -> bool:
    """Whether argv runs a test suite, recognised by command position (not by mention)."""
    if not argv or depth > 2:
        return False
    name = shell.basename(argv[0])
    args = argv[1:]
    if name in _TEST_RUNNERS:
        return True
    if name.startswith("python") and len(args) >= 2 and args[0] == "-m":
        return args[1] in _PYTHON_TEST_MODULES
    if name == "node":
        return "--test" in args
    if name in _LAUNCHERS:
        rest = list(args)
        if _LAUNCHERS[name]:
            if not rest or rest[0] not in _LAUNCHERS[name]:
                return False
            rest = rest[1:]
        while rest and rest[0].startswith("-"):
            rest = rest[1:]
        if name in ("npx", "pnpx", "bunx") and rest[:2] == ["playwright", "test"]:
            return True
        return _runs_tests(tuple(rest), depth + 1)
    if name in _TEST_GOALS:
        goals = [arg for arg in args if not arg.startswith("-")]
        return bool(goals) and set(goals) <= _TEST_GOALS[name]
    if name in _TEST_SUBCOMMANDS:
        rest = list(args)
        while rest and rest[0].startswith("-"):
            valued = name in _PACKAGE_RUNNERS and rest[0] in _PACKAGE_VALUED
            rest = rest[2:] if valued else rest[1:]
        if not rest:
            return False
        if rest[0] in _TEST_SUBCOMMANDS[name]:
            return True
        # `npm run test`, `pnpm run test:unit`
        return (
            name in _PACKAGE_RUNNERS
            and rest[0] == "run"
            and len(rest) > 1
            and (rest[1] == "test" or rest[1].startswith("test:"))
        )
    return False


# -- risky commands (SPEC §18 risk check) -----------------------------------------

# Only patterns that are dangerous regardless of context. `rm -rf ./build` is ordinary
# work; `rm -rf /` and `rm -rf $UNSET_VAR` are not.
#
# Each rule belongs to a *family*; a command gets one finding per family, the most
# severe that matched. Every family is reported — not only the first — because MODIFY
# may only rewrite a command whose sole serious problem is the one the rewrite fixes
# (IMPROVEMENTS.md A5), and that cannot be judged from the first match alone.
VARIABLE_DELETE = effects.VARIABLE_DELETE  # shared with effects and MODIFY

_SEVERITY_RANK = {
    Severity.INFO: 0,
    Severity.LOW: 1,
    Severity.MEDIUM: 2,
    Severity.HIGH: 3,
    Severity.CRITICAL: 4,
}

# R13: every rule is linear in the length of the command. The old forms backtracked
# quadratically (`git push\b[^\n]*\s-f`, `(curl|wget)\b[^\n|]*\|`, `(mkfs|dd)\s+[^\n]*of=`)
# or cubically (`git push\b[^\n]*\bmain\b[^\n]*\s-f`): one 900 KB line cost 203 s and
# wedged the daemon. Now a rule is an anchor — where the command starts, with possessive
# quantifiers — plus followers searched once from the anchor's end, all within one simple
# command (`shell.split`), and nothing past `shell.MAX_SCAN` characters is read.


@dataclass(frozen=True, slots=True)
class _Rule:
    keywords: frozenset[str]  # the words that make the rule worth trying on a piece
    anchor: re.Pattern[str]
    description: str
    severity: str
    family: str
    then: tuple[re.Pattern[str], ...] = ()  # must each match after the anchor
    flags: str = ""  # letters (case-insensitive) the anchor's `flags` group must all contain
    unless: str = ""  # letters that, in the `flags` group, cancel the rule (a dry run)


_FORCE = re.compile(r"\s(?:--force|-f)\b(?![-\w])")
_RULES: tuple[_Rule, ...] = (
    _Rule(
        frozenset({"rm"}),
        re.compile(r"\brm\s++(?P<flags>-[a-zA-Z]++)\s++(?:/\*|/|~|\$HOME)(?=\s|$)"),
        "recursive delete of a root or home path",
        "critical",
        "delete",
        flags="rf",
    ),
    _Rule(
        frozenset({"rm"}),
        re.compile(r"\brm\s++(?P<flags>-[a-zA-Z]++)\s++\"?\$\{?(?P<var>\w++)\}?\"?(?=/|\s|$)"),
        VARIABLE_DELETE,
        "high",
        "delete",
        flags="r",
    ),
    _Rule(frozenset({"git"}), re.compile(r"\bgit\s++push\b"), "force push", "high", "push", (_FORCE,)),
    _Rule(
        frozenset({"git"}),
        re.compile(r"\bgit\s++push\b"),
        "force push to main",
        "critical",
        "push",
        (_FORCE, re.compile(r"\bmain\b")),
    ),
    _Rule(
        frozenset({"git"}),
        re.compile(r"\bgit\s++reset\s++--hard\b"),
        "hard reset discards uncommitted work",
        "high",
        "reset",
    ),
    _Rule(
        frozenset({"git"}),
        re.compile(r"\bgit\s++clean\s++(?P<flags>-[a-zA-Z]++)"),
        "git clean removes untracked files",
        "high",
        "clean",
        flags="f",
        unless="ni",  # `git clean -nfd` is a dry run, `-i` asks first (A3)
    ),
    _Rule(
        frozenset({"curl", "wget"}),
        re.compile(r"\b(?:eval|source|sh|bash|zsh|dash|python3?|node|ruby|perl)\b"),
        effects.DOWNLOAD_EXEC,
        "high",
        "download",
        (re.compile(r"(?:\$\(|`|<\()\s*+(?:\S*/)?(?:curl|wget)\b"),),
    ),
    _Rule(
        frozenset({"drop"}),
        re.compile(r"\bDROP\s++(?:TABLE|DATABASE|SCHEMA)\b", re.IGNORECASE),
        "destructive SQL",
        "critical",
        "sql",
    ),
    _Rule(
        frozenset({"truncate"}),
        re.compile(r"\bTRUNCATE\s++TABLE\b", re.IGNORECASE),
        "destructive SQL",
        "high",
        "sql",
    ),
    _Rule(
        frozenset({"chmod"}),
        re.compile(r"\bchmod\s++-R\s++777\b"),
        "world-writable permissions applied recursively",
        "high",
        "chmod",
    ),
    _Rule(
        frozenset({"mkfs", "dd"}),
        re.compile(r"\b(?:mkfs|dd)\s"),
        "writing directly to a block device",
        "critical",
        "device",
        (re.compile(r"of=/dev/"),),
    ),
)
_KEYWORD = re.compile(r"\b(?:rm|git|drop|truncate|curl|wget|chmod|mkfs|dd)\b", re.IGNORECASE)
_SQL_FAMILIES = frozenset({"sql"})
_DOWNLOAD_EXEC = "piping a download straight into a shell"
# `[ -n "$OUT" ]`, `[[ -z $OUT ]]`, `test -n "$OUT"`.
_GUARD = re.compile(r"(?:\[\[?|\btest)\s++-[nz]\s++\"?\$\{?(\w++)\}?\"?")
# A command longer than `shell.MAX_SCAN` is checked in its first MAX_SCAN characters and
# its last `_TAIL` — where a long heredoc's trailing `&& git push --force` would be.
_TAIL = 4096

# A2: arguments that are text, not commands. A commit message saying "never git push
# --force", a grep for "DROP TABLE", an echo of `rm -rf /`: of 221 risky-command hits in
# 42,426 real commands, 128 were text inside heredocs or quoted arguments (D2).
_DATA_COMMANDS = frozenset(
    {
        "grep", "egrep", "fgrep", "rg", "ag", "ack", "echo", "printf",
        "sed", "gsed", "awk", "gawk", "mawk", "nawk",
    }
)
# Options whose value is text: git commit/tag/notes/merge -m, git log --grep/-S/-G,
# gh pr/issue --body/--title.
_TEXT_OPTIONS: dict[str, frozenset[str]] = {
    "git": frozenset(
        {
            "-m", "--message", "--grep", "-S", "-G", "--author", "--committer", "--format",
            "--pretty", "--trailer",
        }
    ),
    "gh": frozenset({"--body", "-b", "--title", "-t", "--notes", "-n", "--message", "-m"}),
}
_DECLARERS = frozenset({"export", "local", "declare", "typeset", "readonly"})
_NAME_REF = re.compile(r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))")
_MKTEMP = re.compile(r"\$\(\s*mktemp\b[^()`]*\)|`\s*mktemp\b[^`]*`")
_UNKNOWN = effects.UNKNOWN  # an assignment whose value cannot be known (an expansion)
_SCRATCH = effects.SCRATCH  # `$(mktemp ...)`: a fresh temporary path


def is_variable_delete(finding: Finding) -> bool:
    """Whether a risk finding is the unvalidated-variable delete — the one MODIFY fixes."""
    return finding.category is ChallengeCategory.RISK and finding.summary.endswith(VARIABLE_DELETE)


def _guarded_names(text: str) -> set[str]:
    """Variables the command tests for emptiness: `[ -n "$OUT" ] && rm -rf "$OUT"`.

    That is the recommended form: it refuses to run rather than expanding to `/`.
    Flagging it would be a false positive on correct code, and would also stop MODIFY
    from ever being able to fix the unguarded version. Found in one pass, so judging many
    deletes costs no more than judging one.
    """
    return {match.group(1) for match in _GUARD.finditer(text)}


def _match(rule: _Rule, text: str, guarded: set[str]) -> str | None:
    """The text that triggered `rule` in one simple command, or None."""
    for match in rule.anchor.finditer(text):
        if rule.flags:
            flags = match.group("flags").lower()
            if not all(letter in flags for letter in rule.flags):
                continue
            if any(letter in flags for letter in rule.unless):
                continue
        if "var" in rule.anchor.groupindex and match.group("var") in guarded:
            continue  # this one is guarded; a later, unguarded one may not be
        if all(follower.search(text, match.end()) for follower in rule.then):
            return match.group(0)
        if rule.then:
            # The followers were searched to the end of the command from the first
            # anchor; a later anchor cannot find more. Stop: this keeps it linear.
            return None
    return None


def _assignment(raw: str) -> tuple[str, object] | None:
    """`NAME=value` as written -> (NAME, literal value | _SCRATCH | _UNKNOWN)."""
    name, sep, rest = raw.partition("=")
    if not sep or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        return None
    words = shell.tokens(rest) if rest else []
    if not words:
        return name, ""
    if len(words) != 1:
        return name, _UNKNOWN
    word = words[0]
    if not word.expands:
        return name, word.value
    return name, _SCRATCH if _MKTEMP.fullmatch(word.value) else _UNKNOWN


def _record_assignments(part: shell.Part, values: dict[str, object], scratch: set[str]) -> None:
    """Assignments that hold for the rest of this shell: `D=x;`, `export D=x &&`.

    Not a prefix (`D=x cmd` sets it for `cmd` only), not in a pipeline or after `||` or
    `&`, where it may not run in this shell or may not run at all.
    """
    if part.piece.before not in ("", ";", "&&", "\n") or part.piece.piped:
        return
    if part.argv and part.name not in _DECLARERS:
        return
    raws = list(part.assignments) + [w.raw for w in part.words[1:]] if part.argv else list(part.assignments)
    for raw in raws:
        parsed = _assignment(raw)
        if parsed is None:
            continue
        name, value = parsed
        values[name] = value
        if value is _SCRATCH:
            scratch.add(name)


def _render(word: shell.Token, values: dict[str, object]) -> str:
    """One word as the risk rules should read it.

    A literal value assigned earlier in the same command stands in for its variable, so
    `D=build; rm -rf $D` is judged as `rm -rf build` — and `D=/; rm -rf $D` as `rm -rf /`.
    A `$` the shell will not expand (`'$D'`) is kept from looking like a variable.
    """
    value = word.value
    if not word.expands:
        return f"'{value}'" if "$" in value else value

    def substitute(match: re.Match[str]) -> str:
        known = values.get(match.group(1) or match.group(2))
        return known if isinstance(known, str) else match.group(0)

    return _NAME_REF.sub(substitute, value) if values else value


def _judged(part: shell.Part, values: dict[str, object], piped_to_runner: bool) -> str:
    """The text of one simple command that the risk rules read: the command with its
    data arguments left out.

    An opaque part is read whole, as before, so recall never drops.
    """
    if part.opaque:
        return part.text
    if not part.argv:
        return ""
    name = part.name
    words = part.words
    if name in _DATA_COMMANDS and not piped_to_runner:
        return name  # its arguments are patterns, text or a script, not commands
    if name in shell.SHELLS and shell.shell_flag(part.argv) is not None:
        words = words[: shell.shell_flag(part.argv) + 1]  # the string is parsed as its own parts
    elif name == "eval":
        return name
    text_options = _TEXT_OPTIONS.get(name, frozenset())
    rendered: list[str] = []
    skip = False
    for word in words:
        if skip:
            skip = False
            continue
        value = word.value
        if value in text_options:
            rendered.append(value)
            skip = True  # its value is text
            continue
        if any(value.startswith(f"{option}=") for option in text_options if option.startswith("--")):
            rendered.append(value.split("=", 1)[0])
            continue
        if name == "git" and value.startswith("-m") and len(value) > 2:
            rendered.append("-m")  # a glued message: -m"text"
            continue
        rendered.append(_render(word, values))
    return " ".join(rendered)


def _feeds_a_runner(parts: tuple[shell.Part, ...], at: int, after: list[int]) -> shell.Part | None:
    """The part this one pipes into, when that part runs what it reads: a shell reading
    its standard input, or a database client. `after` is `effects.successors(parsed)`."""
    if not parts[at].piece.piped or after[at] < 0:
        return None
    later = parts[after[at]]
    reads = later.name in shell.STDIN_SHELLS and shell.shell_flag(later.argv) is None
    return later if reads or later.name in shell.DB_CLIENTS else None


def risky_command(event: AgentEvent) -> list[Finding]:
    """Commands worth a human's attention before they run.

    These produce REQUEST_REVIEW rather than a block. Truthstone is not the authority on
    whether a force push is appropriate — the developer is — so the right move is to
    surface it, not to overrule it.

    Judged per simple command, on what runs (A2): a here-document body is data unless a
    shell or a database client reads it; a commit message, a grep pattern or an echo is
    text; `sh -c`, `bash -c` and `eval` strings are read as commands of their own. A
    readable command is judged by what it does to what it names (`effects`, A3); one that
    cannot be read whole falls back to the linear rules over its text (R13), so recall
    never drops. Effects of new families come back recorded (INFO), not asked.
    """
    if event.tool != "Bash":
        return []
    command = event.arg("command")
    if not isinstance(command, str) or not command.strip():
        return []

    parsed = shell.parse(command)
    texts: list[tuple[str, frozenset[str] | None]] = []  # (text, only these families)
    guarded = _guarded_names(parsed.line)
    workspace = os.path.abspath(event.workspace or ".")
    home = os.path.normpath(str(Path.home()))
    contexts: dict[int, effects.Context] = {}
    found: list[effects.Effect] = []
    downloads: list[str] = []
    after = effects.successors(parsed)
    for at, part in enumerate(parsed.parts):
        ctx = contexts.get(part.scope)
        if ctx is None:
            ctx = effects.Context(workspace, home, workspace, guarded=guarded, successors=after)
            contexts[part.scope] = ctx
        runner = _feeds_a_runner(parsed.parts, at, after)
        if part.opaque:
            texts.append((part.text, None))
            if runner is not None and runner.name in shell.STDIN_SHELLS and _KEYWORD.search(part.text):
                downloads.append(f"{part.text[:40]} … | {runner.name}")
        else:
            # Text a data command pipes into a shell is commands after all
            # (`echo "rm -rf /" | sh`): every rule reads it, as A2 did.
            shell_reads = (
                runner is not None and runner.name in shell.STDIN_SHELLS and part.name in _DATA_COMMANDS
            )
            families = None if shell_reads else _SQL_FAMILIES
            texts.append((_judged(part, ctx.values, runner is not None), families))
            found += effects.classify(parsed, at, ctx)
            if part.name == "cd" and part.scope == 0:
                target = part.words[1] if len(part.words) > 1 else None
                kind, value = effects.resolve(target, ctx) if target is not None else ("path", home)
                ctx.cwd = value if kind == "path" else None
        _record_assignments(part, ctx.values, guarded)
    texts.extend((body, _SQL_FAMILIES) for body in parsed.sql)
    found += [effect for body in parsed.sql for effect in effects.sql_effects(body, body.strip()[:80])]
    if parsed.truncated:
        log.warning(
            "truthstone: a %d-character command was checked in its first %d and last %d characters",
            len(command),
            shell.MAX_SCAN,
            _TAIL,
        )
        tail = command[-_TAIL:]
        guarded |= _guarded_names(tail)
        texts.extend((piece.text, None) for piece in shell.split(tail).pieces)

    # One finding per family: the most severe. Rules are tried in order, so on a tie the
    # earlier (more specific) description wins.
    chosen: dict[str, effects.Effect] = {}

    def offer(effect: effects.Effect) -> None:
        held = chosen.get(effect.family)
        if held is None or _SEVERITY_RANK[effect.severity] > _SEVERITY_RANK[held.severity]:
            chosen[effect.family] = effect

    for effect in found:
        offer(effect)
    for text, families in texts:
        if not text:
            continue
        words = {word.lower() for word in _KEYWORD.findall(text)}
        if not words:
            continue
        for rule in _RULES:
            if not rule.keywords & words or (families is not None and rule.family not in families):
                continue
            grade = Severity(rule.severity)
            held = chosen.get(rule.family)
            if held is not None and _SEVERITY_RANK[held.severity] >= _SEVERITY_RANK[grade]:
                continue
            matched = _match(rule, text, guarded)
            if matched is not None:
                offer(effects.raised(rule.family, rule.description, grade, matched))
    if downloads:
        offer(effects.raised("download", _DOWNLOAD_EXEC, Severity.HIGH, downloads[0]))

    ordered = sorted(chosen.values(), key=lambda effect: -_SEVERITY_RANK[effect.severity])
    return [_effect_finding(effect, command) for effect in ordered]


def _effect_finding(effect: effects.Effect, command: str) -> Finding:
    shown = command.strip()[:200]
    if effect.raised:
        return Finding(
            category=ChallengeCategory.RISK,
            verdict=Verdict.REQUIRES_HUMAN,
            # A force push may be exactly right, and SPEC §3 has no bullet for it, so this
            # is counted in the census's separately-reported *extension*
            # (`EXTENDED_TAXONOMY`), whose `proves` text says exactly that: the command
            # needed a human's yes, not that it was wrong. Tagging it NOT_A_FAILURE made
            # the highest-harm behaviour uncountable (C1).
            failure_mode=effect.failure_mode,
            severity=effect.severity,
            subject=effect.subject,
            summary=f"Irreversible command: {effect.description}",
            detail=f"`{shown}`",
            evidence=[EvidenceRef(source="runtime", note=shown)],
            suggestion="Confirm this is intended, or narrow it to the specific target.",
            level=EscalationLevel.DETERMINISTIC,
        )
    return Finding(
        category=ChallengeCategory.RISK,
        verdict=Verdict.SUPPORTED_WITH_RISK,
        # Recorded, never raised: a new family stays observe-only until the census has
        # measured its precision (IMPROVEMENTS.md A3).
        failure_mode=effect.failure_mode,
        severity=Severity.INFO,
        subject=effect.subject,
        summary=f"Recorded: {effect.description}",
        detail=f"`{shown}`",
        evidence=[EvidenceRef(source="runtime", note=shown)],
        level=EscalationLevel.DETERMINISTIC,
    )


def _raw_target(event: AgentEvent) -> str:
    """The un-normalised target path of a file-writing or deleting action, or "".

    The validator's normalised path is empty for a target outside the workspace, which is
    exactly where A3 (outside writes) and A9 (self-protection) must look. One accessor, so
    the core names the host's path arguments once (canonical actions, H6, will remove it).
    """
    if not event.is_mutating:
        return ""
    raw = event.arg("file_path") or event.arg("notebook_path")
    return raw if isinstance(raw, str) else ""


def outside_write(event: AgentEvent, *, roots: ProtectedRoots | None = None) -> list[Finding]:
    """A file tool writing outside the workspace (A3): the developer's own configuration
    is an ask; anywhere else is recorded. Truthstone's own paths are A9's (`roots`: the
    validation's `ProtectedRoots`, when it has them)."""
    raw = _raw_target(event)
    if not raw or protected_path(raw, event.workspace, roots=roots):
        return []
    workspace = os.path.abspath(event.workspace or ".")
    ctx = effects.Context(workspace, os.path.normpath(str(Path.home())), workspace)
    found = effects.file_tool(event.tool, raw, ctx)
    return [_effect_finding(effect, f"{event.tool} {raw}") for effect in found]


# -- verification bypass (IMPROVEMENTS.md A8) -------------------------------------------
#
# A command that switches off the checks meant to verify the work: git hooks, or a
# build's test phase. Transcripts show five uses of `--no-verify`, none flagged. Pebble
# looks for the same flags (`conventions.py:285-297`). Raised once per concern per task
# (the ledger), at MEDIUM: skipping a hook may be right, so the agent is told, not stopped.

_GIT_GLOBAL_VALUED = frozenset({"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"})
_HOOKED = frozenset({"commit", "push", "merge", "rebase"})
# `git commit` short options that take a value: in `-nm msg` the n is a flag, in `-mn`
# the n is the message.
_COMMIT_VALUED = frozenset("mFCcSt")
_SKIP_TESTS_FLAGS = frozenset({"-DskipTests", "-DskipTests=true", "-Dmaven.test.skip=true", "--skip-tests"})
_HOOKS = "git hooks skipped"
_TESTS = "test phase skipped"
_BYPASS_TEXT = re.compile(r"--no-verify\b|-DskipTests\b|-Dmaven\.test\.skip=true|--skip-tests\b|\bHUSKY=0\b")


def _git_subcommand(argv: tuple[str, ...]) -> tuple[str, tuple[str, ...]]:
    """(subcommand, its arguments) of a git argv, global options stepped over."""
    rest = list(argv[1:])
    while rest and rest[0].startswith("-"):
        option = rest[0]
        rest = rest[2:] if option in _GIT_GLOBAL_VALUED and "=" not in option else rest[1:]
    return (rest[0], tuple(rest[1:])) if rest else ("", ())


def _commit_no_verify_short(args: tuple[str, ...]) -> bool:
    """`git commit -n`, also inside a cluster (`-anm msg`) — never in a value (`-mn`)."""
    skip = False
    for arg in args:
        if skip:
            skip = False
            continue
        if arg == "--":
            return False
        if not arg.startswith("-") or arg.startswith("--") or len(arg) < 2:
            continue
        for at, letter in enumerate(arg[1:], 1):
            if letter == "n":
                return True
            if letter in _COMMIT_VALUED:
                skip = at == len(arg) - 1  # the value is the next word unless glued
                break
    return False


def _assigned(part: shell.Part) -> dict[str, str]:
    """NAME -> value for the assignments that reach this part's command's environment:
    a prefix (`HUSKY=0 git commit`), `env NAME=value`, or `export NAME=value`."""
    raws = list(part.assignments)
    if part.name in ("export", "declare", "typeset"):
        raws += [w.raw for w in part.words[1:]]
    out: dict[str, str] = {}
    for raw in raws:
        name, sep, value = raw.partition("=")
        if sep:
            out[name] = value.strip("'\"")
    return out


def verification_bypass(event: AgentEvent) -> list[Finding]:
    """`--no-verify`, `git commit -n`, `HUSKY=0`, `SKIP=` before git, `-DskipTests`,
    `-Dmaven.test.skip=true`, `--skip-tests`, `SKIP_TESTS=1`. Never `git push -n`, which
    is a dry run."""
    if event.tool != "Bash":
        return []
    command = event.arg("command")
    if not isinstance(command, str) or not command.strip():
        return []

    found: dict[str, str] = {}  # concern -> the spelling that triggered it
    for part in shell.parse(command).parts:
        if part.opaque:
            match = _BYPASS_TEXT.search(part.text)
            if match:
                found.setdefault(_TESTS if "test" in match.group(0).lower() else _HOOKS, match.group(0))
            continue
        env = _assigned(part)
        if env.get("HUSKY") == "0":
            found.setdefault(_HOOKS, "HUSKY=0")
        if env.get("SKIP_TESTS", "").lower() in ("1", "true", "yes"):
            found.setdefault(_TESTS, "SKIP_TESTS=1")
        if part.name == "git":
            sub, args = _git_subcommand(part.argv)
            if sub in _HOOKED and "--no-verify" in args:
                found.setdefault(_HOOKS, f"git {sub} --no-verify")
            elif sub == "commit" and _commit_no_verify_short(args):
                found.setdefault(_HOOKS, "git commit -n")
            if sub in _HOOKED and "SKIP" in env:
                found.setdefault(_HOOKS, f"SKIP={env['SKIP']}")  # pre-commit's skip list
        elif part.name == "pre-commit" and "SKIP" in env:
            found.setdefault(_HOOKS, f"SKIP={env['SKIP']}")
        flag = next((arg for arg in part.argv[1:] if arg in _SKIP_TESTS_FLAGS), None)
        if flag:
            found.setdefault(_TESTS, flag)

    return [
        Finding(
            category=ChallengeCategory.TESTABILITY,
            verdict=Verdict.SUPPORTED_WITH_RISK,
            failure_mode=FailureMode.VERIFICATION_TAMPERING,
            severity=Severity.MEDIUM,
            subject=concern,
            summary=f"Verification skipped: `{spelling}` turns off the "
            + ("git hooks" if concern == _HOOKS else "build's tests"),
            detail=f"`{command.strip()[:200]}`",
            evidence=[EvidenceRef(source="runtime", note=command.strip()[:200])],
            suggestion=(
                "Run the hooks and fix what they report."
                if concern == _HOOKS
                else "Run the tests and fix what they report."
            ),
            level=EscalationLevel.DETERMINISTIC,
        )
        for concern, spelling in found.items()
    ]


# -- self-protection (IMPROVEMENTS.md A9) ---------------------------------------------
#
# A command or a write that would switch Truthstone off — its CLI's off switches, its own
# home (configuration, token, state), or the host settings its hooks live in — is the
# developer's decision, every time. Pebble asks the same way for its own data and the
# agents' settings (`shell_policy.py:47-83`, `policy.py:13-26`). Reading any of it is fine.

_SELF_OFF: tuple[tuple[str, ...], ...] = (("off",), ("uninstall",), ("observe", "on"), ("daemon", "stop"))
_CLI_MODULES = frozenset({"truthstone", "truthstone.cli", "truthstone.cli.main"})
_LAUNCH_VALUED = frozenset({"--from", "--with", "--python", "-p", "--spec", "--index-url"})
_SELF_TEXT = re.compile(r"\btruthstone\s++(?:off|uninstall|observe\s++on|daemon\s++stop|approve)\b")

# The developer's sign-off (A1b) is theirs alone, so every shell route to one that can be
# seen needs a sign-off of its own: `truthstone approve`, a command carrying a sign-off
# reply (a nested `codex exec resume … "approve K7M2QX"`, a hook payload sent with curl),
# and resuming an agent session from the shell, which sends a prompt into it.
#
# A sign-off code's shape: six letters and digits with at least one of each, so it never
# reads as a word or a number. `signoff.py` issues codes of exactly this shape.
SIGNOFF_CODE_SHAPE = r"(?=[0-9A-Za-z]{0,5}[0-9])(?=[0-9A-Za-z]{0,5}[A-Za-z])[0-9A-Za-z]{6}(?![0-9A-Za-z])"
_REPLY_TEXT = re.compile(rf"\bapproved?\b[^\w\n]{{1,4}}{SIGNOFF_CODE_SHAPE}", re.IGNORECASE)
_RESUMES: dict[str, frozenset[str]] = {
    "codex": frozenset({"resume"}),
    "claude": frozenset({"--resume", "-r", "--continue", "-c"}),
}
_SIGNOFF_ONLY = "Only the developer can give Truthstone's sign-off."
_PROTECTED_HINT = re.compile(
    r"\.truthstone|\.claude/settings[^/\s]*\.json|\.codex/(?:hooks\.json|config\.toml)"
)
_WRITE_HINT = re.compile(
    r">(?!&)|\btee\b|\b(?:sed|perl)\s++(?:-\w++\s++)*-\w*i|\b(?:rm|mv|cp|ln|truncate|dd)\b"
)
_MAX_PATHS = 64


def _truthstone_command(argv: tuple[str, ...], depth: int = 0) -> tuple[str, ...] | None:
    """The arguments given to the Truthstone CLI, however it is launched, or None."""
    if not argv or depth > 2:
        return None
    name = shell.basename(argv[0])
    args = list(argv[1:])
    if name == "truthstone":
        return tuple(args)
    if name.startswith("python") and len(args) >= 2 and args[0] == "-m" and args[1] in _CLI_MODULES:
        return tuple(args[2:])
    if (name == "uv" and args[:1] == ["run"]) or (name == "pipx" and args[:1] == ["run"]) or name == "uvx":
        rest = args[1:] if args[:1] == ["run"] else args
        while rest and rest[0].startswith("-"):
            rest = rest[2:] if rest[0] in _LAUNCH_VALUED else rest[1:]
        return _truthstone_command(tuple(rest), depth + 1)
    return None


def _switches_off(part: shell.Part) -> str:
    """The Truthstone off switch this part throws, or ""."""
    cli = _truthstone_command(part.argv)
    if cli is not None:
        words = tuple(arg for arg in cli if not arg.startswith("-"))
        for switch in _SELF_OFF:
            if words[: len(switch)] == switch:
                return "truthstone " + " ".join(switch)
    if part.name in ("pkill", "killall") and any("truthstone" in arg.lower() for arg in part.argv[1:]):
        return f"{part.name} truthstone"
    return ""


def _signs_off(part: shell.Part) -> str:
    """The developer-only sign-off route this part takes, or "" (A1b)."""
    cli = _truthstone_command(part.argv)
    if cli is not None and tuple(arg for arg in cli if not arg.startswith("-"))[:1] == ("approve",):
        return "truthstone approve"
    flags = _RESUMES.get(part.name)
    if flags and any(arg.split("=", 1)[0] in flags for arg in part.argv[1:]):
        return f"{part.name} resume"
    return ""


def _protected_roots(truthstone: str | None = None, home: str | None = None) -> tuple[str, ...]:
    """Truthstone's home, as configured and by default, lexically and resolved."""
    truthstone = str(truthstone_home()) if truthstone is None else truthstone
    home = str(Path.home()) if home is None else home
    return _spellings(truthstone, os.path.join(home, ".truthstone"))


def _codex_homes(home: str | None = None) -> tuple[str, ...]:
    home = str(Path.home()) if home is None else home
    return _spellings(os.environ.get("CODEX_HOME") or os.path.join(home, ".codex"))


@dataclass(frozen=True, slots=True)
class ProtectedRoots:
    """Where Truthstone's own switches live, worked out once per validation (A9-perf).

    `truthstone_home()` walks every ancestor of the home, resolving trusted symlinks with
    an `lstat` each. `protected_path` used to do that three times per write target: one
    900 KB command naming a dotfile 3,449 times made 10,347 home walks and 82,793
    `lstat`s, most of a one-second PreToolUse. A validation now computes these once, on
    first need, and hands them to every `protected_path` call.
    """

    home: str  # the user's home: what `$HOME` stands for
    truthstone: str  # Truthstone's home, configured and resolved: `$TRUTHSTONE_HOME`
    roots: tuple[str, ...]  # Truthstone's home, configured and default, every spelling
    codex: tuple[str, ...]  # Codex's home, every spelling

    @classmethod
    def now(cls) -> ProtectedRoots:
        home = str(Path.home())
        truthstone = str(truthstone_home())
        return cls(home, truthstone, _protected_roots(truthstone, home), _codex_homes(home))


@lru_cache(maxsize=16)
def _spellings(*paths: str) -> tuple[str, ...]:
    """Each path lexically normalised and resolved, case-folded (APFS ignores case)."""
    out: set[str] = set()
    for path in paths:
        expanded = os.path.expanduser(path)
        out.add(os.path.normpath(expanded).casefold())
        out.add(os.path.realpath(expanded).casefold())
    return tuple(sorted(out))


def protected_path(raw: str, cwd: str, *, roots: ProtectedRoots | None = None) -> str:
    """Why writing `raw` would touch Truthstone's own switches, or "".

    `raw` is the path as given (a tool's `file_path`, a shell word), so a path outside the
    workspace — which the index never sees — is judged as well. A caller judging many
    paths passes `roots` (`ProtectedRoots.now()`, once); without it they are worked out
    here.
    """
    if not isinstance(raw, str) or not raw or "\x00" in raw:
        return ""
    where = roots if roots is not None else ProtectedRoots.now()
    expanded = os.path.expanduser(raw)
    for variable, value in (
        ("$HOME", where.home),
        ("${HOME}", where.home),
        ("$TRUTHSTONE_HOME", where.truthstone),
        ("${TRUTHSTONE_HOME}", where.truthstone),
    ):
        if expanded.startswith(variable):
            expanded = value + expanded[len(variable) :]
            break
    if "$" in expanded:
        return ""  # an expansion that cannot be known here
    joined = expanded if os.path.isabs(expanded) else os.path.join(cwd or ".", expanded)
    candidates = {os.path.normpath(joined).casefold(), os.path.realpath(joined).casefold()}
    for candidate in candidates:
        if any(candidate == root or candidate.startswith(root + os.sep) for root in where.roots):
            return "Truthstone's own configuration and state"
        parent, name = os.path.split(candidate)
        if os.path.basename(parent) == ".claude" and name.startswith("settings") and name.endswith(".json"):
            return "Claude Code's settings, where Truthstone's hooks are installed"
        in_codex = os.path.basename(parent) == ".codex" or parent in where.codex
        if name in ("hooks.json", "config.toml") and in_codex:
            return "Codex's hook configuration"
    return ""


def _self_finding(
    subject: str,
    summary: str,
    detail: str,
    note: str,
    suggestion: str = "Only the developer can turn Truthstone off or change its hooks.",
) -> Finding:
    return Finding(
        category=ChallengeCategory.RISK,
        verdict=Verdict.REQUIRES_HUMAN,
        # Switching off the guard is the most complete way to bypass the checks that
        # verify the work. Asked every time (A1), never decided by Truthstone itself.
        failure_mode=FailureMode.VERIFICATION_TAMPERING,
        severity=Severity.HIGH,
        subject=subject[:80],
        summary=summary,
        detail=detail,
        evidence=[EvidenceRef(source="runtime", note=note[:200])],
        suggestion=suggestion,
        level=EscalationLevel.DETERMINISTIC,
    )


def self_protection(event: AgentEvent, *, roots: ProtectedRoots | None = None) -> list[Finding]:
    """Turning Truthstone off, writing its home or the host hook settings, or taking a
    route to the developer's own sign-off (A1b): each needs a sign-off.

    `roots` are the validation's `ProtectedRoots`; without them they are worked out at
    the first write target, once, and each distinct target is judged once (A9-perf).
    """
    raw = _raw_target(event)
    if raw:
        why = protected_path(raw, event.workspace, roots=roots)
        if not why:
            return []
        return [
            _self_finding(
                raw,
                f"Self-protection: this writes {why}",
                f"`{raw}`",
                f"{event.tool} {raw}",
            )
        ]
    if event.tool not in SHELL_TOOLS:  # PowerShell can switch Truthstone off too
        return []
    command = event.arg("command")
    if not isinstance(command, str) or not command.strip():
        return []

    cwd = event.workspace
    found: list[Finding] = []
    # (target, cwd) -> why: a target a command names many times is judged once (A9-perf).
    judged: dict[tuple[str, str], str] = {}
    # A sign-off reply anywhere in the command, quoted or not: the text is the route (A1b).
    reply = _REPLY_TEXT.search(command, 0, shell.MAX_SCAN)
    if reply:
        found.append(
            _self_finding(
                "a sign-off reply",
                "Self-protection: this command carries a sign-off reply "
                f"(`{reply.group(0)}`); only the developer can sign off",
                f"`{command.strip()[:200]}`",
                command.strip(),
                _SIGNOFF_ONLY,
            )
        )
    parsed = shell.parse(command)
    # What cannot be read is judged together, as Pebble reads an opaque line whole: a loop
    # names the file in one piece (`for f in .claude/settings*.json`) and edits it in the
    # next (`do sed -i ... $f`).
    unread = "\n".join(part.text for part in parsed.parts if part.opaque)
    writes_hooks = bool(_PROTECTED_HINT.search(unread) and _WRITE_HINT.search(unread))
    if unread and (_SELF_TEXT.search(unread) or writes_hooks):
        found.append(
            _self_finding(
                "an unreadable command",
                "Self-protection: this command may turn Truthstone off, change its hooks or "
                "give a sign-off",
                f"`{command.strip()[:200]}`",
                command.strip(),
            )
        )
    for part in parsed.parts:
        if part.opaque:
            continue
        if part.depth == 0 and part.name == "cd" and part.scope == 0:
            target = part.argv[1] if len(part.argv) > 1 else "~"
            cwd = os.path.normpath(os.path.join(cwd, os.path.expanduser(target))) if target != "-" else ""
            continue
        switch = _switches_off(part)
        if switch:
            found.append(
                _self_finding(
                    switch,
                    f"Self-protection: `{switch}` turns Truthstone off",
                    f"`{command.strip()[:200]}`",
                    command.strip(),
                )
            )
        route = _signs_off(part)
        if route:
            what = "gives the developer's sign-off" if route.startswith("truthstone") else (
                "sends a prompt into an agent session, where a sign-off is given"
            )
            found.append(
                _self_finding(
                    route,
                    f"Self-protection: `{route}` {what}",
                    f"`{command.strip()[:200]}`",
                    command.strip(),
                    _SIGNOFF_ONLY,
                )
            )
        if not cwd:
            continue
        for item in effects.written_paths(part):
            path = item.value if isinstance(item, shell.Token) else item
            key = (path, cwd)
            if key not in judged:
                roots = roots if roots is not None else ProtectedRoots.now()
                judged[key] = protected_path(path, cwd, roots=roots)
            why = judged[key]
            if why:
                found.append(
                    _self_finding(
                        path,
                        f"Self-protection: this command writes {why}",
                        f"`{path}` in `{command.strip()[:160]}`",
                        command.strip(),
                    )
                )
                break
    # One finding per subject is enough for the developer.
    return list({finding.subject: finding for finding in found}.values())[:3]


# -- repository consistency (SPEC §16 CONSISTENCY · SPEC §3 "ignore existing patterns") --
#
# Every finding below is INFO, which puts it under the challenge threshold: recorded in
# the decision log and counted by the census, never said to the agent. That is deliberate
# for Phase 7 and not merely caution. A convention detector that starts objecting during
# the census would change the behaviour the census exists to measure.
#
# The discipline that makes these worth counting at all: a convention has to be *proved*
# before it can be broken. Fewer than `CONVENTION_MIN_SIBLINGS` files agreeing is not a
# convention, and a file that carries no distinguishing marker cannot be said to violate
# one. Both rules cost recall and buy the only thing that matters here — a census nobody
# has to discount.


# Two questions about a filename, asked separately because a filename answers them
# separately. Lumping them into one four-way "snake / kebab / camel / pascal" verdict
# made `store.py` uncommitted — it is compatible with snake *and* kebab — and a directory
# of single-word lowercase modules is the commonest shape in Python. The detector was
# therefore silent on the clearest violation there is: `NewThing.py` among `store.py` and
# `engine.py`. Asked separately, every filename answers the casing question, and only
# multi-word ones need answer the separator question.


def _casing(stem: str) -> str:
    """`lower` or `mixed`. Every filename commits to this one."""
    return "lower" if stem == stem.lower() else "mixed"


def _separator(stem: str) -> str:
    """`_`, `-`, or "" when the name is a single word and so has no opinion.

    Dunder names are excluded by the caller: `__init__` is a language requirement, not a
    house style, and counting it as an underscore vote would invent a convention out of
    Python's own rules.
    """
    if "_" in stem:
        return "_"
    if "-" in stem:
        return "-"
    return ""


def _stem_and_suffix(path: str) -> tuple[str, str]:
    name = path.rsplit("/", 1)[-1]
    suffix = Path(name).suffix
    return name[: len(name) - len(suffix)] if suffix else name, suffix


def pattern_consistency(event: AgentEvent, index: RepoIndex, path: str) -> list[Finding]:
    """Does a new file follow the conventions its neighbours already keep?

    Runs on file *creation* only. That is where conventions get broken, it is rare enough
    to afford a scan of the file map, and it avoids re-judging files that already exist.
    """
    if event.tool != "Write" or index.file_exists(path):
        return []

    findings = _placement(index, path)
    findings.extend(_naming(index, path))
    return findings


def _placement(index: RepoIndex, path: str) -> list[Finding]:
    """A new file in a part of the tree its kind does not live in.

    Two cases, and only two, because both have unambiguous evidence: a test written
    outside wherever every other test lives, and a file created in a directory that does
    not exist yet.
    """
    directory = path.rsplit("/", 1)[0] if "/" in path else ""
    if not directory:
        return []

    if scanner.is_test_path(path):
        roots = {p.split("/")[0] for p, record in index.files.items() if record.is_test}
        count = sum(1 for record in index.files.values() if record.is_test)
        if count >= CONVENTION_MIN_SIBLINGS and len(roots) == 1:
            home = next(iter(roots))
            if path.split("/")[0] != home:
                return [
                    _consistency(
                        path,
                        f"new test outside `{home}/`, where all {count} existing tests live",
                        f"Every test file in this repository is under `{home}/`.",
                    )
                ]

    if not any(p.startswith(f"{directory}/") for p in index.files):
        return [
            _consistency(
                path,
                f"new file in a directory with no existing siblings: {directory}/",
                "",
            )
        ]
    return []


def _naming(index: RepoIndex, path: str) -> list[Finding]:
    """A new file named unlike every one of its same-extension siblings.

    Same extension only: `.tsx` components and `.css` files routinely follow different
    conventions in the same directory, and comparing across them invents violations.

    Unanimity is required, not a majority. One dissenting sibling means the repository
    tolerates both, and a house style that is merely popular is not one an agent can be
    said to have ignored.
    """
    stem, suffix = _stem_and_suffix(path)
    if not stem or not suffix:
        return []

    directory = path.rsplit("/", 1)[0] if "/" in path else ""
    prefix = f"{directory}/" if directory else ""

    casings: list[str] = []
    separators: list[str] = []
    for sibling in index.files:
        if sibling == path or not sibling.startswith(prefix):
            continue
        if "/" in sibling[len(prefix) :]:
            continue  # direct children only; a subtree is a different context
        sibling_stem, sibling_suffix = _stem_and_suffix(sibling)
        if sibling_suffix != suffix or not sibling_stem:
            continue
        casings.append(_casing(sibling_stem))
        if not sibling_stem.startswith("_"):
            separator = _separator(sibling_stem)
            if separator:
                separators.append(separator)

    verdict = _unanimous(casings, _casing(stem))
    if verdict:
        style = {"lower": "lowercase", "mixed": "mixed-case"}
        return [
            _consistency(
                path,
                f"`{stem}{suffix}` is {style[_casing(stem)]}; all {len(casings)} sibling "
                f"{suffix} files are {style[verdict]}",
                f"Existing convention in {prefix or './'}: {style[verdict]} filenames.",
            )
        ]

    separator = _separator(stem)
    verdict = _unanimous(separators, separator) if separator else ""
    if verdict:
        return [
            _consistency(
                path,
                f"`{stem}{suffix}` separates words with `{separator}`; all "
                f"{len(separators)} multi-word sibling {suffix} files use `{verdict}`",
                f"Existing convention in {prefix or './'}: `{verdict}` between words.",
            )
        ]
    return []


def _unanimous(votes: list[str], candidate: str) -> str:
    """The single value every sibling agreed on, when it differs from `candidate`.

    Empty when there are too few siblings, when they disagree, or when the new file
    already matches them — the three ways of having nothing to report.
    """
    if len(votes) < CONVENTION_MIN_SIBLINGS:
        return ""
    agreed = set(votes)
    if len(agreed) != 1:
        return ""
    only = agreed.pop()
    return "" if only == candidate else only


def _consistency(path: str, summary: str, detail: str) -> Finding:
    return Finding(
        category=ChallengeCategory.CONSISTENCY,
        verdict=Verdict.SUPPORTED_WITH_RISK,
        failure_mode=FailureMode.IGNORED_REPO_PATTERN,  # SPEC §3
        severity=Severity.INFO,
        subject=path,
        summary=summary,
        detail=detail,
        evidence=[EvidenceRef(source="filesystem", path=path)],
        level=EscalationLevel.DETERMINISTIC,
    )


# -- new dependencies (SPEC §16 DEPENDENCY · SPEC §3 "unnecessary dependencies") ---
#
# The Evidence Engine already catches `pip install X` (`evidence/resolvers._dependency`).
# It cannot see the other half of the same act: editing pyproject.toml or package.json,
# which is how a dependency actually becomes permanent. This closes that.
#
# Recorded, never raised, for a reason specific to this phase: the detector is new and
# unmeasured, and adding a fresh interruption during a census would contaminate the thing
# being counted. If the census says this fires often and accurately, Phase 8 can promote
# it.

# Packages that do the same job. Adding one when the repository already declares another
# is the strongest deterministic evidence available for the word "unnecessary" in SPEC
# §3 — everything else this detector sees is merely "new".
#
# A heuristic list, and short on purpose. Each row is a set of genuine substitutes, not
# merely a shared topic: `requests` and `httpx` really are alternatives, while `pydantic`
# and `sqlalchemy` both touch data and are not.
_INTERCHANGEABLE: tuple[frozenset[str], ...] = (
    frozenset({"requests", "httpx", "aiohttp", "urllib3", "treq", "niquests"}),
    frozenset({"orjson", "ujson", "simplejson", "python-rapidjson", "hyperjson"}),
    frozenset({"python-dateutil", "arrow", "pendulum", "delorean"}),
    frozenset({"python-dotenv", "environs", "dynaconf", "python-decouple"}),
    frozenset({"pydantic", "marshmallow", "cerberus", "voluptuous", "schematics"}),
    frozenset({"typer", "click", "fire", "docopt", "argh"}),
    frozenset({"pytest", "nose", "nose2", "unittest2"}),
    frozenset({"flask", "fastapi", "django", "bottle", "sanic", "starlette", "quart"}),
    frozenset({"sqlalchemy", "peewee", "tortoise-orm", "pony"}),
    frozenset({"loguru", "structlog", "logbook"}),
    frozenset({"axios", "node-fetch", "got", "superagent", "ky", "undici"}),
    frozenset({"jest", "vitest", "mocha", "jasmine", "ava", "tape"}),
    frozenset({"lodash", "underscore", "ramda"}),
    frozenset({"moment", "dayjs", "date-fns", "luxon"}),
    frozenset({"redux", "zustand", "jotai", "mobx", "recoil", "valtio"}),
    frozenset({"styled-components", "emotion", "@emotion/styled", "stitches"}),
)


def _substitute_for(package: str, declared: set[str]) -> str:
    """An already-declared package that does the same job, if there is one."""
    lowered = package.lower()
    for group in _INTERCHANGEABLE:
        if lowered not in group:
            continue
        for existing in sorted(declared):
            if existing.lower() != lowered and existing.lower() in group:
                return existing
    return ""


def dependency_added(event: AgentEvent, index: RepoIndex, path: str) -> list[Finding]:
    """Packages this edit would add to a manifest.

    Reads the manifest as it would be *after* the edit and diffs it against the current
    one, so what gets reported is the change rather than the file's whole contents.
    """
    if event.tool not in ("Write", "Edit", "MultiEdit"):
        return []
    filename = path.rsplit("/", 1)[-1]
    if not manifests.is_manifest(filename):
        return []

    from truthstone.evidence import extractors

    outcome = extractors.resolve_edit(event, index.root)
    if outcome is None or outcome.after is None:
        return []

    after = manifests.parse_text(filename, outcome.after)
    before = manifests.parse_text(filename, outcome.before or "")
    if after is None:
        return []  # the result does not parse as a manifest; say nothing about it
    if before is None and (outcome.before or "").strip():
        return []  # no clean baseline, so "added" cannot be distinguished from "existing"

    existing = set(before.all_names) if before else set()
    declared = existing | set(index.dependencies.all_names)
    added = sorted(set(after.all_names) - existing)
    if not added:
        return []

    findings: list[Finding] = []
    for package in added[:5]:
        substitute = _substitute_for(package, declared)
        findings.append(
            Finding(
                category=ChallengeCategory.DEPENDENCY,
                verdict=Verdict.INSUFFICIENT_EVIDENCE,
                failure_mode=FailureMode.UNNECESSARY_DEPENDENCY,  # SPEC §3
                # LOW when the repository already has something that does the job — that
                # is real evidence for "unnecessary". INFO otherwise, where all we can
                # honestly say is "new". Both are below the challenge threshold.
                severity=Severity.LOW if substitute else Severity.INFO,
                subject=package,
                summary=(
                    f"`{package}` added to {filename}, but `{substitute}` is already a "
                    f"dependency and does the same job"
                    if substitute
                    else f"`{package}` added to {filename} as a new dependency"
                ),
                detail=(
                    "New dependencies are permanent and are rarely removed. "
                    "If both are needed, the reason is worth stating."
                    if substitute
                    else "New dependencies are permanent; the reason should be explicit."
                ),
                evidence=[EvidenceRef(source="manifest", path=path, note=f"adds {package}")],
                level=EscalationLevel.DETERMINISTIC,
            )
        )
    return findings
