"""What a parsed command does, judged on its argv (IMPROVEMENTS.md A3).

The regex rules saw `rm -rf /` and missed `rm -r -f /`, `rm --recursive --force ~`,
`rm -rf -- /`, `git reset HEAD~3 --hard`, `git -C ../o reset --hard`, `git clean -d -f`,
`git push origin +main` and `git push -fu origin main`; they flagged the dry run
`git clean -nfd`; and they could not see what a command does to the files it names. The
lead asked on 3 of 18 destructive commands, D2 missed 22 of 26 (IMPROVEMENTS.md A3).

Here each simple command (`shell.Part`) is classified by what it does:

* **Spellings of today's families stay asks, at today's severities:** recursive deletes of
  `/`, a top-level system directory or the home folder (however spelled: `~`, `~/`,
  `$HOME`, `/Users/me`, `/*`, `../..` when that is home); an unvalidated variable delete;
  force pushes (`--force`, `-f` in a cluster, `+ref`; critical to main/master); hard
  resets in any order; `git clean` with force and no dry run; download-and-execute in
  every form (`curl | sh`, `| python3`, `sh -c "$(curl ...)"`, `bash <(curl ...)`,
  download to a file then run it); recursive world-writable chmod; `mkfs.*`, `dd of=/dev/`.
* **New families are recorded only** (INFO, DESTRUCTIVE_ACTION): `git checkout -- paths`,
  `git restore`, `git stash drop|clear`, `git branch -D`, remote branch deletes;
  `find -delete|-exec rm`, `xargs rm`; terraform/kubectl/helm/aws s3/gsutil deletes;
  `dropdb`, `prisma migrate reset`, SQL DELETE/UPDATE without WHERE run by a database
  client, `FLUSHALL`, `docker system prune --volumes`; package publishes. They stay
  observe-only until the census measures their precision.
* **Writes outside the workspace:** to the developer's own configuration (`~/.ssh`,
  `~/.aws`, `~/.gnupg`, `~/.config`, `~/.gitconfig`, shell startup files) they are asks;
  anywhere else (`/tmp`, a sibling project) they are recorded. Relative deletes inside the
  repository stay quiet.

Provenance: the git option handling follows Pebble `git_commands.py:416-1038` (global
options before the subcommand, flags inside short clusters, `+ref` and `:ref` refspecs);
the filesystem targets follow `shell_policy.py:625-724` (`targets`, `_find_roots`). Same
owner, Apache-2.0. Nothing here touches the filesystem: paths are judged lexically.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from agentguard.core.enums import FailureMode, Severity
from agentguard.validate import shell

# The descriptions of today's families: the risk rules (checks._RULES) and MODIFY share them.
ROOT_DELETE = "recursive delete of a root or home path"
VARIABLE_DELETE = "recursive delete of an unvalidated variable path — expands to `/` if it is unset"
FORCE_PUSH = "force push"
FORCE_PUSH_MAIN = "force push to main"
HARD_RESET = "hard reset discards uncommitted work"
GIT_CLEAN = "git clean removes untracked files"
DOWNLOAD_EXEC = "piping a download straight into a shell"
WORLD_WRITABLE = "world-writable permissions applied recursively"
BLOCK_DEVICE = "writing directly to a block device"
DOTFILE_WRITE = "writes the developer's own configuration outside the workspace"
HOME_FOLDER_DELETE = "recursive delete of a top-level folder of the home directory"

# The developer's own configuration: SSH keys and config, cloud credentials, GPG, XDG
# config, git identity, shell startup files.
DOTFILES = (
    ".ssh", ".aws", ".gnupg", ".config", ".gitconfig", ".bashrc", ".zshrc", ".profile",
    ".bash_profile", ".zprofile",
)
_SINKS = re.compile(r"/dev/(?:null|stdout|stderr|tty|zero|random|urandom|fd/\d{1,3})")
_DELETERS = frozenset({"rm", "rmdir", "unlink", "srm", "trash", "shred"})
_COPIERS = frozenset({"cp", "ln", "install", "rsync", "ditto", "gcp"})
_IN_PLACE_EDITORS = frozenset({"sed", "gsed", "perl"})
_DOWNLOADERS = frozenset({"curl", "wget"})
_GIT_GLOBAL_VALUED = frozenset(
    {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--config-env", "--super-prefix"}
)
_DEFAULT_BRANCHES = frozenset({"main", "master"})
_NAME_REF = re.compile(r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))")
_LEADING_VAR = re.compile(r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))(?=/|$)")
_HOME_VAR = re.compile(r"\$(?:\{HOME\}|HOME(?![A-Za-z0-9_]))")
_RUNS_DOWNLOAD = re.compile(r"(?:\$\(|`|<\()\s*+(?:\S*/)?(?:curl|wget)\b")
_SQL_STATEMENT = re.compile(r"[^;]++")
_DELETE_ALL = re.compile(r"\A\s*+DELETE\s++FROM\s++\S++(?:\s++(?!WHERE\b)\S++)*+\s*+\Z", re.IGNORECASE)
_UPDATE_ALL = re.compile(r"\A\s*+UPDATE\s++\S++\s++SET\b(?:(?!\bWHERE\b).)*+\Z", re.IGNORECASE | re.DOTALL)

SCRATCH = object()  # `$(mktemp ...)`: a fresh temporary path
UNKNOWN = object()  # an assignment whose value cannot be known


@dataclass(frozen=True, slots=True)
class Effect:
    family: str  # one finding per family: the most severe effect
    description: str
    severity: Severity
    raised: bool  # True: the developer is asked; False: recorded only
    subject: str
    failure_mode: FailureMode = FailureMode.DESTRUCTIVE_ACTION


@dataclass
class Context:
    """What is known about the shell a part runs in."""

    workspace: str
    home: str
    cwd: str | None  # None once a `cd` went somewhere unknowable
    values: dict[str, object] = field(default_factory=dict)  # literal / SCRATCH / UNKNOWN
    guarded: set[str] = field(default_factory=set)  # tested non-empty, or a mktemp path
    downloads: set[str] = field(default_factory=set)  # files a download wrote
    # successors[at]: the index of the next part in the same shell, or -1 (`successors`).
    successors: list[int] = field(default_factory=list)


def successors(parsed: shell.Parsed) -> list[int]:
    """For each part, the index of the next part of the same shell (scope), or -1. One
    pass, so following a pipe is constant time however long the line."""
    after = [-1] * len(parsed.parts)
    last: dict[int, int] = {}
    for at in range(len(parsed.parts) - 1, -1, -1):
        scope = parsed.parts[at].scope
        after[at] = last.get(scope, -1)
        last[scope] = at
    return after


def raised(family: str, description: str, severity: Severity, subject: str, **kw) -> Effect:
    return Effect(family, description, severity, True, subject[:80], **kw)


def recorded(family: str, description: str, subject: str) -> Effect:
    # New families: observe-only until the census measures their precision (A3).
    return Effect(family, description, Severity.INFO, False, subject[:80])


# -- paths ----------------------------------------------------------------------------


def place(path: str, ctx: Context) -> str:
    """Where an absolute, normalised path is: "root", "home", "workspace", "inside",
    "sink", "device", "dotfile" or "outside"."""
    if path == "/":
        return "root"
    if path == ctx.home:
        return "home"
    workspace = ctx.workspace
    if path == workspace:
        return "workspace"
    if path.startswith(workspace.rstrip("/") + "/"):
        return "inside"
    if path.count("/") == 1 and path != "/tmp":
        return "root"  # a top-level directory: /usr, /etc, /Users, /var ...
    if path.startswith("/dev/"):
        return "sink" if _SINKS.fullmatch(path) else "device"
    if path.startswith(ctx.home + "/"):
        rest = path[len(ctx.home) + 1 :]
        first = rest.split("/", 1)[0]
        if first in DOTFILES:
            return "dotfile"
        if "/" not in rest and not first.startswith("."):
            return "home-folder"  # ~/Documents, ~/projects: a top-level folder of home
    return "outside"


def resolve(word: shell.Token, ctx: Context) -> tuple[str, str]:
    """(kind, value) for one path word: ("path", absolute) | ("children", absolute) — a
    trailing `/*` — | ("variable", name) | ("guarded", name) | ("unknown", "")."""
    value = word.value
    if word.expands:
        value = _NAME_REF.sub(lambda m: _literal(m, ctx), value)
        home = _HOME_VAR.match(value)
        if home:
            value = ctx.home + value[home.end() :]
        leading = _LEADING_VAR.match(value)
        if leading:
            name = leading.group(1) or leading.group(2)
            return ("guarded", name) if name in ctx.guarded else ("variable", name)
        if "$" in value or "`" in value:
            return "unknown", ""
    if value == "~" or value.startswith("~/"):
        value = ctx.home + value[1:]
    elif value.startswith("~"):
        return "unknown", ""  # another user's home
    children = False
    for suffix in ("/*", "/.*"):
        if value.endswith(suffix) and len(value) > len(suffix) - 1:
            value, children = value[: -len(suffix)] or "/", True
            break
    if value == "*":
        value, children = ".", True
    if not os.path.isabs(value):
        if ctx.cwd is None:
            return "unknown", ""
        value = os.path.join(ctx.cwd, value)
    normal = os.path.normpath(value)
    if normal.startswith("//"):
        normal = "/" + normal.lstrip("/")
    return ("children" if children else "path"), normal


def _literal(match: re.Match[str], ctx: Context) -> str:
    known = ctx.values.get(match.group(1) or match.group(2))
    return known if isinstance(known, str) else match.group(0)


def written_paths(part: shell.Part) -> list[shell.Token | str]:
    """The paths a simple command visibly writes, moves or deletes (Pebble `targets`):
    output redirections, tee, sed/perl -i, rm/rmdir/unlink/mv/truncate operands,
    cp/ln/install/rsync destinations, dd of=. Tokens where the argv has them."""
    paths: list[shell.Token | str] = [
        target for op, target in part.redirects if ">" in op and target and not target.startswith("&")
    ]
    name = part.name
    words = list(part.words[1:])
    operands = [w for w in words if not w.value.startswith("-") or w.value == "-"]
    if name == "tee" or name in _DELETERS or name in ("mv", "truncate"):
        paths += operands
    elif name in _COPIERS and len(operands) > 1:
        paths.append(operands[-1])
    elif name in _IN_PLACE_EDITORS and any(
        w.value.startswith("--in-place") or re.fullmatch(r"-[A-Za-z]{0,3}i\S*", w.value) for w in words
    ):
        has_script_option = any(w.value in ("-e", "--expression", "-f") for w in words)
        paths += operands if has_script_option else operands[1:]
    elif name == "dd":
        paths += [w.value[3:] for w in words if w.value.startswith("of=")]
    return paths[:64]


def _as_token(item: shell.Token | str) -> shell.Token:
    if isinstance(item, shell.Token):
        return item
    expands = "$" in item or "`" in item
    return shell.Token(item, item, 0, len(item), expands=expands)


# -- classifiers -------------------------------------------------------------------------


def classify(parsed: shell.Parsed, at: int, ctx: Context) -> list[Effect]:
    """The effects of one readable part (`parsed.parts[at]`)."""
    part = parsed.parts[at]
    name = part.name
    if not name:
        return []
    found: list[Effect] = []
    if name in _DELETERS:
        found += _rm(part, ctx)
    elif name == "git":
        found += _git(part.argv)
    elif name == "find":
        found += _find(part, ctx)
    elif name == "chmod":
        found += _chmod(part)
    elif _formats_a_device(part):
        found.append(raised("device", BLOCK_DEVICE, Severity.CRITICAL, " ".join(part.argv)))
    found += _download_exec(parsed, at, ctx)
    found += _recorded_families(parsed, at, ctx)
    found += _writes(part, ctx)
    if "xargs" in part.wrappers and name in _DELETERS:
        found.append(recorded("pipe-delete", "deletes whatever is piped in (xargs rm)", part.text))
    return found


def _formats_a_device(part: shell.Part) -> bool:
    """`mkfs.ext4 /dev/sdb1`, `newfs_apfs`, `wipefs`, `diskutil eraseDisk ...`."""
    name = part.name
    if name.startswith(("mkfs", "newfs")) or name in ("mke2fs", "mkswap", "wipefs"):
        return True
    verbs = ("erase", "zero", "partition")
    return name == "diskutil" and any(arg.lower().startswith(verbs) for arg in part.argv[1:])


def _rm(part: shell.Part, ctx: Context) -> list[Effect]:
    words = list(part.words[1:])
    options: list[str] = []
    targets: list[shell.Token] = []
    ended = False
    for word in words:
        if not ended and word.value == "--":
            ended = True
        elif not ended and word.value.startswith("-") and len(word.value) > 1:
            options.append(word.value)
        else:
            targets.append(word)
    recursive = any(
        option == "--recursive" or (not option.startswith("--") and ("r" in option or "R" in option))
        for option in options
    )
    found: list[Effect] = []
    flags = " ".join(options)
    for word in targets:
        kind, value = resolve(word, ctx)
        subject = f"rm {flags} {word.raw}".replace("  ", " ")
        if kind == "variable" and recursive and part.name == "rm":
            found.append(raised("delete", VARIABLE_DELETE, Severity.HIGH, subject))
        elif kind in ("path", "children"):
            where = place(value, ctx)
            if where in ("root", "home") and recursive:
                found.append(raised("delete", ROOT_DELETE, Severity.CRITICAL, subject))
            elif where == "home-folder" and recursive:
                # Not today's root-or-home family, but it was asked before (as a "variable
                # delete" of `$HOME/x`), and a top-level folder of home is not scratch.
                found.append(raised("delete", HOME_FOLDER_DELETE, Severity.HIGH, subject))
            elif where == "dotfile":
                found.append(raised("dotfile", DOTFILE_WRITE, Severity.HIGH, subject))
            elif where == "workspace" and recursive:
                found.append(recorded("workspace-delete", "deletes the whole workspace", subject))
            elif where == "outside":
                found.append(recorded("outside-write", "deletes outside the workspace", subject))
    return found


def git_subcommand(argv: tuple[str, ...]) -> tuple[str, tuple[str, ...]]:
    """(subcommand, its arguments), global options (`-C dir`, `-c k=v`, `--no-pager`)
    stepped over, as Pebble `git_commands.typed` does."""
    rest = list(argv[1:])
    while rest and rest[0].startswith("-"):
        option = rest[0]
        rest = rest[2:] if option in _GIT_GLOBAL_VALUED and "=" not in option else rest[1:]
    return (rest[0], tuple(rest[1:])) if rest else ("", ())


def _letters(args: tuple[str, ...]) -> set[str]:
    """The letters of every short-option cluster (`-fdx` -> f, d, x)."""
    return {ch for arg in args if arg.startswith("-") and not arg.startswith("--") for ch in arg[1:]}


def _git(argv: tuple[str, ...]) -> list[Effect]:
    sub, args = git_subcommand(argv)
    text = "git " + " ".join((sub, *args))
    letters = _letters(args)
    if sub == "push":
        return _push(args, text)
    if sub == "reset":
        return [raised("reset", HARD_RESET, Severity.HIGH, text)] if "--hard" in args else []
    if sub == "clean":
        force = "f" in letters or "--force" in args
        dry = "n" in letters or "--dry-run" in args or "i" in letters or "--interactive" in args
        return [raised("clean", GIT_CLEAN, Severity.HIGH, text)] if force and not dry else []
    if sub == "checkout":
        paths_follow = "--" in args and args.index("--") < len(args) - 1
        if paths_follow or "." in args:
            return [recorded("git-discard", "discards uncommitted changes (git checkout -- paths)", text)]
        return []
    if sub == "restore":
        staged_only = ("--staged" in args or "S" in letters) and not ("--worktree" in args or "W" in letters)
        paths = [a for a in args if not a.startswith("-")]
        if paths and not staged_only:
            return [recorded("git-discard", "discards uncommitted changes (git restore)", text)]
        return []
    if sub == "stash" and args[:1] in (("drop",), ("clear",)):
        return [recorded("git-discard", f"deletes stashed work (git stash {args[0]})", text)]
    if sub == "branch":
        force_delete = "-D" in args or (
            ("-d" in args or "--delete" in args) and ("-f" in args or "--force" in args)
        )
        if force_delete:
            return [recorded("branch-delete", "force-deletes a branch (git branch -D)", text)]
    return []


def _push(args: tuple[str, ...], text: str) -> list[Effect]:
    force = deletes = dry = False
    positional: list[str] = []
    skip = False
    for at, arg in enumerate(args):
        if skip:
            skip = False
            continue
        if arg == "--":
            positional += list(args[at + 1 :])
            break
        if arg.startswith("--"):
            option = arg.split("=", 1)[0]
            force = force or option in ("--force", "--mirror")
            deletes = deletes or option == "--delete"
            dry = dry or option == "--dry-run"
            skip = option in ("--repo", "--receive-pack", "--exec", "--push-option") and "=" not in arg
        elif arg.startswith("-") and len(arg) > 1:
            force = force or "f" in arg[1:]
            deletes = deletes or "d" in arg[1:]
            dry = dry or "n" in arg[1:]
            skip = arg.endswith("o")  # -o <push option>
        else:
            positional.append(arg)
    if dry:
        return []
    refspecs = positional[1:]
    plus = any(spec.startswith("+") for spec in refspecs)
    found: list[Effect] = []
    if force or plus:
        targets = {spec.lstrip("+").rsplit(":", 1)[-1].removeprefix("refs/heads/") for spec in refspecs}
        if targets & _DEFAULT_BRANCHES:
            found.append(raised("push", FORCE_PUSH_MAIN, Severity.CRITICAL, text))
        else:
            found.append(raised("push", FORCE_PUSH, Severity.HIGH, text))
    if deletes or any(spec.startswith(":") for spec in refspecs):
        found.append(recorded("remote-delete", "deletes a remote branch", text))
    return found


def _find_roots(argv: tuple[str, ...]) -> list[str]:
    """The path operands of a `find` (Pebble `_find_roots`)."""
    words = list(argv[1:])
    while words and re.fullmatch(r"-[HLPEXdsx]+", words[0]):
        words = words[1:]
    roots = []
    for word in words:
        if word.startswith(("-", "(", "!", ")")):
            break
        roots.append(word)
    return roots or ["."]


def _find(part: shell.Part, ctx: Context) -> list[Effect]:
    args = part.argv[1:]
    runs_rm = any(
        arg in ("-exec", "-execdir", "-ok", "-okdir")
        and at + 1 < len(args)
        and shell.basename(args[at + 1]) in _DELETERS
        for at, arg in enumerate(args)
    )
    if "-delete" not in args and not runs_rm:
        return []
    text = " ".join(part.argv)
    unfiltered = ("-delete", "-depth", "-xdev", "-mount", "-print")
    tests = [a for a in args if a.startswith("-") and a not in unfiltered]
    for root in _find_roots(part.argv):
        kind, value = resolve(_as_token(root), ctx)
        if kind == "path" and place(value, ctx) in ("root", "home") and not tests:
            return [raised("delete", ROOT_DELETE, Severity.CRITICAL, text)]
    return [recorded("find-delete", "deletes everything find matches", text)]


def _world_writable(mode: str) -> bool:
    if re.fullmatch(r"[0-7]{3,4}", mode):
        return int(mode[-1]) & 2 == 2
    for clause in mode.split(","):
        match = re.fullmatch(r"([ugoa]*)([+=])([rwxXst]*)", clause)
        if match and "w" in match.group(3) and (not match.group(1) or set(match.group(1)) & {"o", "a"}):
            return True
    return False


def _chmod(part: shell.Part) -> list[Effect]:
    args = part.argv[1:]
    recursive = "--recursive" in args or "R" in _letters(args)
    operands = [a for a in args if not a.startswith("-")]
    if recursive and operands and _world_writable(operands[0]):
        return [raised("chmod", WORLD_WRITABLE, Severity.HIGH, " ".join(part.argv))]
    return []


def _download_exec(parsed: shell.Parsed, at: int, ctx: Context) -> list[Effect]:
    """A download handed straight to something that runs it, in every form."""
    part = parsed.parts[at]
    name = part.name
    text = part.text
    hit = ""
    if name in _DOWNLOADERS:
        runner = _next_in_pipe(parsed, at, ctx)
        if runner is not None and _runs_stdin(runner):
            hit = f"{name} … | {runner.name}"
        out = _download_target(part)
        if out:
            ctx.downloads.add(out)
    elif name in shell.SHELLS | {"eval", "source", "."} | shell.INTERPRETERS:
        # `sh -c "$(curl ...)"`, `eval "$(curl ...)"`, `bash <(curl ...)`, `. <(wget -O- ...)`
        if any(_RUNS_DOWNLOAD.search(word.value) for word in part.words[1:]):
            hit = text
        else:
            script = next((w.value for w in part.words[1:] if not w.value.startswith("-")), "")
            if script and (script in ctx.downloads or script.lstrip("./") in ctx.downloads):
                hit = text  # downloaded to a file, then run
    elif part.argv and part.argv[0].lstrip("./") in ctx.downloads:
        hit = text
    return [raised("download", DOWNLOAD_EXEC, Severity.HIGH, hit)] if hit else []


def _download_target(part: shell.Part) -> str:
    """The file a curl or wget writes: `-o F`, `-fsSLo F`, `--output F`, wget `-O F`, or
    the URL's own name for curl `-O`."""
    args = part.argv[1:]
    cluster = re.compile(r"-[A-Za-z]*o") if part.name == "curl" else re.compile(r"-[A-Za-z]*O")
    for at, arg in enumerate(args[:-1]):
        if arg in ("--output", "--output-document") or cluster.fullmatch(arg):
            target = args[at + 1]
            return "" if target == "-" else target.lstrip("./")
    if part.name == "curl" and any(a in ("-O", "--remote-name") for a in args):
        url = next((a for a in args if "://" in a), "")
        return url.rstrip("/").rsplit("/", 1)[-1].split("?", 1)[0]
    return ""


def _next_in_pipe(parsed: shell.Parsed, at: int, ctx: Context) -> shell.Part | None:
    if not parsed.parts[at].piece.piped:
        return None
    following = ctx.successors[at] if at < len(ctx.successors) else -1
    if following < 0 and not ctx.successors:  # a caller without the precomputed map
        following = successors(parsed)[at]
    return parsed.parts[following] if following >= 0 else None


def _runs_stdin(part: shell.Part) -> bool:
    """A shell or interpreter that runs what it reads on standard input."""
    if part.name in shell.STDIN_SHELLS:
        return shell.shell_flag(part.argv) is None
    if part.name in shell.INTERPRETERS:
        operands = [a for a in part.argv[1:] if not a.startswith("-") or a == "-"]
        return not operands or operands[0] == "-"
    return False


_RECORDED_COMMANDS: tuple[tuple[tuple[str, ...], str, str, tuple[str, ...]], ...] = (
    # (argv prefix, family, description, flags of which at least one is required)
    (("terraform", "destroy"), "infra", "destroys infrastructure (terraform destroy)", ()),
    (("terraform", "apply"), "infra", "destroys infrastructure (terraform apply -destroy)", ("-destroy",)),
    (("kubectl", "delete"), "infra", "deletes Kubernetes resources", ()),
    (("helm", "uninstall"), "infra", "uninstalls a Helm release", ()),
    (("helm", "delete"), "infra", "uninstalls a Helm release", ()),
    (("aws", "s3", "rm"), "infra", "deletes S3 objects recursively", ("--recursive",)),
    (("aws", "s3", "rb"), "infra", "deletes an S3 bucket", ("--force",)),
    (("gsutil", "rm"), "infra", "deletes Cloud Storage objects recursively", ("-r", "-R")),
    (("dropdb",), "database", "drops a database", ()),
    (("prisma", "migrate", "reset"), "database", "resets the database (prisma migrate reset)", ()),
    (("rails", "db:drop"), "database", "drops the database (rails db:drop)", ()),
    (("rake", "db:drop"), "database", "drops the database (rake db:drop)", ()),
    (("docker", "system", "prune"), "database", "removes Docker volumes", ("--volumes",)),
    (("npm", "publish"), "publish", "publishes a package", ()),
    (("pnpm", "publish"), "publish", "publishes a package", ()),
    (("yarn", "publish"), "publish", "publishes a package", ()),
    (("twine", "upload"), "publish", "publishes a package", ()),
    (("cargo", "publish"), "publish", "publishes a package", ()),
    (("poetry", "publish"), "publish", "publishes a package", ()),
    (("gem", "push"), "publish", "publishes a package", ()),
)
_LAUNCHERS = frozenset({"npx", "pnpx", "bunx", "dlx"})
_RECORDED_BY_NAME: dict[str, list[tuple[tuple[str, ...], str, str, tuple[str, ...]]]] = {}
for _entry in _RECORDED_COMMANDS:
    _RECORDED_BY_NAME.setdefault(_entry[0][0], []).append(_entry)
_SQL_READERS = frozenset({"echo", "printf"})


def _recorded_families(parsed: shell.Parsed, at: int, ctx: Context) -> list[Effect]:
    part = parsed.parts[at]
    name = part.name
    first = shell.basename(part.argv[1]) if name in _LAUNCHERS and len(part.argv) > 1 else name
    if (
        first not in _RECORDED_BY_NAME
        and name not in shell.DB_CLIENTS
        and name not in _SQL_READERS
    ):
        return []  # most commands: one dictionary lookup
    argv = list(part.argv)
    if argv and shell.basename(argv[0]) in _LAUNCHERS:
        argv = argv[1:]
    if argv[:2] == ["gsutil", "-m"]:
        argv = ["gsutil", *argv[2:]]
    words = [a for a in argv if not a.startswith("-")]
    flags = {a for a in argv if a.startswith("-")}
    text = " ".join(part.argv)
    found: list[Effect] = []
    for prefix, family, description, required in _RECORDED_BY_NAME.get(first, ()):
        if words[:1] != [prefix[0]] or (required and not flags & set(required)):
            continue
        # The verb may follow a global option's value: `kubectl -n prod delete ns x`.
        head = words[1:5]
        verb = list(prefix[1:])
        if any(head[at : at + len(verb)] == verb for at in range(len(head))):
            found.append(recorded(family, description, text))
            break
    if part.name == "redis-cli" and any(a.upper() in ("FLUSHALL", "FLUSHDB") for a in part.argv[1:]):
        found.append(recorded("database", "empties a Redis database (FLUSHALL)", text))
    if part.name in shell.DB_CLIENTS:
        # `psql -c "..."`, `sqlite3 app.db "..."`: each argument is a candidate statement.
        found += next((hit for arg in part.argv[1:] if (hit := sql_effects(arg, text))), [])
    elif part.name in ("echo", "printf"):
        runner = _next_in_pipe(parsed, at, ctx)
        if runner is not None and runner.name in shell.DB_CLIENTS:
            found += sql_effects(" ".join(part.argv[1:]), text)
    return found


def sql_effects(sql: str, subject: str) -> list[Effect]:
    """DELETE or UPDATE without WHERE, in SQL a database client runs."""
    if "delete" not in sql.lower() and "update" not in sql.lower():
        return []
    for statement in _SQL_STATEMENT.findall(sql):
        if _DELETE_ALL.match(statement):
            return [recorded("database", "deletes every row of a table (DELETE without WHERE)", subject)]
        if _UPDATE_ALL.match(statement):
            return [recorded("database", "updates every row of a table (UPDATE without WHERE)", subject)]
    return []


def _writes(part: shell.Part, ctx: Context) -> list[Effect]:
    """Writes outside the workspace: the developer's own configuration is an ask, a
    block device is critical, anywhere else is recorded. rm is judged by `_rm`."""
    if part.name in _DELETERS:
        return []
    found: list[Effect] = []
    for item in written_paths(part):
        kind, value = resolve(_as_token(item), ctx)
        if kind not in ("path", "children"):
            continue
        where = place(value, ctx)
        if where == "dotfile":
            found.append(raised("dotfile", DOTFILE_WRITE, Severity.HIGH, f"{part.name} → {value}"))
        elif where == "device":
            found.append(raised("device", BLOCK_DEVICE, Severity.CRITICAL, f"{part.name} → {value}"))
        elif where in ("outside", "root", "home", "home-folder"):
            found.append(recorded("outside-write", "writes outside the workspace", f"{part.name} → {value}"))
    return found


def file_tool(tool: str, raw: str, ctx: Context) -> list[Effect]:
    """An Edit/Write/MultiEdit/NotebookEdit (or Delete) of a path outside the workspace —
    which the index never sees, so the raw path is judged."""
    kind, value = resolve(_as_token(raw), ctx)
    if kind != "path":
        return []
    where = place(value, ctx)
    if where == "dotfile":
        return [raised("dotfile", DOTFILE_WRITE, Severity.HIGH, f"{tool} {value}")]
    if where in ("outside", "root", "home", "home-folder", "device"):
        return [recorded("outside-write", "writes outside the workspace", f"{tool} {value}")]
    return []
