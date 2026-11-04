"""Tool arguments -> claims (SPEC §14, §18).

Two decisions shape this module.

**Claims come from the post-edit file, not from the edit fragment.** An `Edit` supplies a
`new_string` with no context; `repo.get_active_users()` in isolation says nothing about
what `repo` is. Applying the edit to the file on disk and analysing the result recovers
the imports, the class definitions and the local bindings that make the call meaningful.

**Only *newly introduced* claims are checked.** Claims present before the edit are
subtracted out, so Truthstone never challenges the agent for something that was already
in the file. Being blamed for pre-existing code is the fastest way to become noise.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from truthstone.core.enums import ClaimKind
from truthstone.core.events import AgentEvent
from truthstone.evidence import pyanalysis
from truthstone.evidence.models import Claim
from truthstone.repo.paths import relative_path

PYTHON_SUFFIXES = (".py", ".pyi")

# -- dependency installs (SPEC §16 DEPENDENCY) ----------------------------------------
#
# Read from the installer's own argv (IMPROVEMENTS.md A2), never from text: a regex over
# the line denied `git commit -m "...pip install requests..."` and
# `grep -rn "npm install lodash" docs/` as new dependencies (probes Q1/Q2).

# (command, subcommand words) -> whether the installer records the package in the
# project's manifest itself. `npm install <pkg>` saves by default; `pip install` never does.
_INSTALLERS: dict[tuple[str, ...], bool] = {
    ("pip", "install"): False,
    ("pip3", "install"): False,
    ("uv", "pip", "install"): False,
    ("uv", "add"): True,
    ("poetry", "add"): True,
    ("pipenv", "install"): True,
    ("npm", "install"): True,
    ("npm", "i"): True,
    ("npm", "add"): True,
    ("pnpm", "add"): True,
    ("yarn", "add"): True,
    ("bun", "add"): True,
    ("cargo", "add"): True,
    ("go", "get"): True,
}
# Options that take a value, which is never a package (a requirements file, an index URL,
# a workspace, a feature list ...).
_VALUED = frozenset(
    {
        "-r", "--requirement", "-c", "--constraint", "-e", "--editable", "-i", "--index-url",
        "--extra-index-url", "-f", "--find-links", "-t", "--target", "--prefix", "--root",
        "--python", "-p", "--group", "-G", "--optional", "--extra", "-E", "--extras",
        "--source", "--index", "--default-index", "--rev", "--tag", "--branch", "--package",
        "--registry", "-w", "--workspace", "--filter", "-F", "--dir", "-C", "--cwd",
        "--features", "--path", "--git", "--rename", "--manifest-path", "--omit", "--include",
        "--platform", "--python-version", "--implementation", "--abi", "--markers",
        "--config-settings", "--trusted-host", "--proxy", "--timeout", "--retries", "--cache-dir",
    }
)
# Flags after which nothing is saved to the manifest.
_AD_HOC = frozenset({"--no-save", "-g", "--global", "--no-sync"})
_PACKAGE = re.compile(r"[@A-Za-z0-9][\w.@/+-]*")


@dataclass(frozen=True, slots=True)
class Install:
    """One package an installer command adds."""

    name: str
    tool: str  # "pip install", "uv add", "npm install" ...
    writes_manifest: bool  # whether the tool records it in the project manifest itself


def installs(command: str) -> list[Install]:
    """Packages that installer commands in this line add, read from their argv.

    Options and their values are skipped, as are paths, URLs and anything holding an
    expansion (`pip install $PKG` names nothing knowable).
    """
    from truthstone.validate import shell  # the validator's parser; no import cycle at load

    found: list[Install] = []
    seen: set[str] = set()
    for part in shell.parse(command).parts:
        located = _installer(part.argv)
        if located is None:
            continue
        start, tool, writes = located
        args = part.argv[start:]
        words = part.words[start:]  # argv is these tokens' values, one for one
        if any(arg in _AD_HOC for arg in args):
            writes = False
        skip = False
        for position, arg in enumerate(args):
            if skip:
                skip = False
                continue
            if arg.startswith("-"):
                skip = arg in _VALUED
                continue
            if words and words[position].expands:
                continue
            name = _package_name(arg, tool)
            if name and name not in seen:
                seen.add(name)
                found.append(Install(name, tool, writes))
    return found


def _installer(argv: tuple[str, ...]) -> tuple[int, str, bool] | None:
    """(index of the first argument after the install verb, tool, writes manifest)."""
    if not argv:
        return None
    head = argv[0].rsplit("/", 1)[-1]
    rest = list(argv[1:])
    if head.startswith("python") and rest[:2] == ["-m", "pip"]:
        head, rest = "pip", rest[2:]
        offset = 3
    else:
        offset = 1
    # Global options before the verb: `npm --prefix web install x`, `uv --quiet add x`.
    while rest and rest[0].startswith("-"):
        step = 2 if rest[0] in _VALUED and len(rest) > 1 else 1
        rest = rest[step:]
        offset += step
    for verbs, writes in _INSTALLERS.items():
        if verbs[0] != head:
            continue
        tail = list(verbs[1:])
        if rest[: len(tail)] == tail:
            return offset + len(tail), " ".join(verbs), writes
    return None


def _package_name(arg: str, tool: str) -> str:
    """The package a spec names: `requests[socks]>=2` -> requests, `@types/node@18` ->
    @types/node, `github.com/x/y@v1` -> github.com/x/y. "" for paths and URLs."""
    if (
        arg in (".", "..")
        or arg.startswith(("./", "../", "/", "~", "git+", "http:", "https:", "file:"))
        or "://" in arg
        or arg.endswith((".whl", ".tar.gz", ".zip", ".tgz"))
    ):
        return ""
    if tool.startswith(("pip", "uv", "poetry", "pipenv")):
        name = re.split(r"[\[=<>!~;@ ]", arg, maxsplit=1)[0]
        if "/" in name:
            return ""  # a local path such as `src/pkg`
    elif tool.startswith(("npm", "pnpm", "yarn", "bun")):
        scoped = arg.startswith("@")
        body = arg[1:] if scoped else arg
        name = ("@" if scoped else "") + body.split("@", 1)[0]
    else:  # cargo add, go get
        name = arg.split("@", 1)[0]
    match = _PACKAGE.fullmatch(name)
    return match.group(0).rstrip(",") if match else ""


class EditOutcome:
    """The state of one file before and after a proposed edit."""

    __slots__ = ("after", "applied", "before", "path")

    def __init__(self, path: str, before: str | None, after: str | None, applied: bool) -> None:
        self.path = path
        self.before = before
        self.after = after
        self.applied = applied


def _edit_target(event: AgentEvent) -> str | None:
    """The path argument an editing action names, or None."""
    raw_path = event.arg("file_path") or event.arg("notebook_path")
    return raw_path if isinstance(raw_path, str) and raw_path else None


def read_before(event: AgentEvent, root: Path) -> tuple[str, str] | None:
    """``(path, text)``: the file an edit targets, as it is now (``""`` if it does not exist
    yet), or None when the action edits no file inside ``root``."""
    raw_path = _edit_target(event)
    if raw_path is None:
        return None
    path = relative_path(root, raw_path)
    if path is None:
        return None
    # Re-check the canonical target immediately before reading.  A symlink can be
    # swapped between the lexical containment check and ``read_text``; refusing links
    # here closes that small TOCTOU window for evidence extraction.
    full = root / path
    try:
        if not full.resolve(strict=False).is_relative_to(root.resolve(strict=False)):
            return None
    except (OSError, RuntimeError):
        return None
    try:
        return path, (full.read_text(encoding="utf-8", errors="replace") if full.is_file() else "")
    except OSError:
        return None


def resolve_edit(event: AgentEvent, root: Path) -> EditOutcome | None:
    """Compute the file content this action would produce.

    Returns None when the tool does not edit a file, or when the edit cannot be applied
    (a missing `old_string` means the tool call will fail on its own — not our problem).
    A snapshot taken when the action was proposed (``event._before``) is preferred to the
    disk: a check deferred past the action must see the file the action found (WP9).
    """
    tool = event.tool
    if event._before is not None:
        raw_path = _edit_target(event)
        path = relative_path(root, raw_path) if raw_path is not None else None
        if path is None:
            return None
        before = event._before
    else:
        found = read_before(event, root)
        if found is None:
            return None
        path, before = found

    if tool == "Write":
        content = event.arg("content")
        if not isinstance(content, str):
            return None
        return EditOutcome(path, before, content, True)

    if tool == "Edit":
        old = event.arg("old_string")
        new = event.arg("new_string")
        if not isinstance(old, str) or not isinstance(new, str):
            return None
        if old and old not in before:
            return None  # the tool call will fail; nothing to assess
        after = before.replace(old, new, -1 if event.arg("replace_all") else 1) if old else before + new
        return EditOutcome(path, before, after, True)

    if tool == "MultiEdit":
        edits = event.arg("edits")
        if not isinstance(edits, list):
            return None
        after = before
        for edit in edits:
            if not isinstance(edit, dict):
                return None
            old, new = edit.get("old_string"), edit.get("new_string")
            if not isinstance(old, str) or not isinstance(new, str):
                return None
            if old and old not in after:
                return None
            after = after.replace(old, new, -1 if edit.get("replace_all") else 1) if old else after + new
        return EditOutcome(path, before, after, True)

    if tool == "NotebookEdit":
        source = event.arg("new_source")
        if not isinstance(source, str):
            return None
        return EditOutcome(path, "", source, True)

    return None


def _relative(raw: str, root: Path) -> str:
    """Backward-compatible wrapper for callers/tests that used the old helper.

    Outside paths are represented by an empty string; ``resolve_edit`` uses
    :func:`relative_path` directly so it can distinguish and reject them before any
    filesystem access.  Keeping this wrapper avoids breaking private-but-useful imports.
    """
    return relative_path(root, raw) or ""


def claims_from_edit(outcome: EditOutcome) -> tuple[list[Claim], pyanalysis.SourceFacts | None]:
    """Newly introduced claims, plus the facts about the resulting file.

    An empty list is returned — deliberately — when the *previous* content could not be
    parsed. Without a clean baseline there is no way to tell a new claim from an old one,
    and guessing would mean blaming the agent for someone else's code.
    """
    if not outcome.path.endswith(PYTHON_SUFFIXES):
        return [], None
    if outcome.after is None:
        return [], None

    after_facts = pyanalysis.analyze(outcome.after, outcome.path)
    if not after_facts.parsed:
        # The edit produces unparsable Python. That is a problem, but it is a syntax
        # problem for the verification layer, not a hallucinated-symbol problem.
        return [], after_facts

    before_facts = pyanalysis.analyze(outcome.before or "", outcome.path)
    if (outcome.before or "").strip() and not before_facts.parsed:
        return [], after_facts

    seen = {claim.fingerprint() for claim in before_facts.claims}
    new_claims = [claim for claim in after_facts.claims if claim.fingerprint() not in seen]
    return new_claims, after_facts


def claims_from_bash(command: str) -> list[Claim]:
    """Dependency additions only, read from installer argv (`installs`).

    File paths in shell commands are far too noisy to treat as claims — most commands
    create the paths they mention. Dependency installs are unambiguous.
    """
    return [
        Claim(kind=ClaimKind.DEPENDENCY_DECLARED, subject=install.name, snippet=command.strip()[:160])
        for install in installs(command)
    ]


def claims_for_event(event: AgentEvent, root: Path) -> tuple[list[Claim], pyanalysis.SourceFacts | None]:
    if event.tool == "Bash":
        command = event.arg("command")
        return (claims_from_bash(command) if isinstance(command, str) else []), None

    outcome = resolve_edit(event, root)
    if outcome is None:
        return [], None
    return claims_from_edit(outcome)
