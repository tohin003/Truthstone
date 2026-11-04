"""Isolated homes and environments for benchmark cells.

Everything a cell touches lives under a run's *work root*, a neutrally named directory
outside ``/tmp`` (Codex's default sandbox lets the agent write ``/tmp``, so nothing the
harness depends on may live there) and outside any repository. The model sees its own
working directory, so no path it can see names the arm, the task or the product.

Credentials: each CODEX_HOME gets ``auth.json`` as a **symlink** to the user's
``~/.codex/auth.json``. The harness never opens, reads, prints or copies that file.
Codex writes token refreshes through the link (``login/src/auth/storage.rs`` opens the
path with truncate+write, no rename), so the user's own login stays current.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

DEFAULT_AUTH_SOURCE = Path.home() / ".codex" / "auth.json"
PLUGIN_SKIP_PARTS = {"__pycache__", ".venv", ".DS_Store"}
PLUGIN_SKIP_SUFFIXES = {".pyc", ".pyo"}


class IsolationError(RuntimeError):
    pass


def private_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, 0o700)
    return path


def neutral_name(*parts: object, length: int = 10) -> str:
    """A stable, meaningless directory name derived from ``parts``."""
    digest = hashlib.sha256("\0".join(str(p) for p in parts).encode()).hexdigest()
    return "k" + digest[: length - 1]


def default_work_root(run_name: str) -> Path:
    return Path.home() / ".cache" / "cw" / neutral_name("run", run_name)


def assert_outside_tmp(path: Path) -> None:
    resolved = path.resolve()
    for tmp in (
        Path("/tmp").resolve(),
        Path("/private/var/folders"),
        Path(os.environ.get("TMPDIR", "/tmp")).resolve(),
    ):
        if resolved == tmp or tmp in resolved.parents:
            raise IsolationError(f"{path} is under {tmp}, which the agent's sandbox can write")


# -- credentials ------------------------------------------------------------------


def link_auth(codex_home: Path, source: Path = DEFAULT_AUTH_SOURCE) -> None:
    """Point ``codex_home/auth.json`` at the user's login. Never opens the file."""
    if not os.path.lexists(source):
        raise IsolationError(f"no Codex login at {source}; run `codex login` first")
    target = codex_home / "auth.json"
    if os.path.lexists(target):
        os.unlink(target)
    os.symlink(source, target)


def auth_link_intact(codex_home: Path, source: Path = DEFAULT_AUTH_SOURCE) -> bool:
    target = codex_home / "auth.json"
    return os.path.islink(target) and os.readlink(target) == str(source)


def unlink_auth(codex_home: Path) -> None:
    """Remove the link (never the file it points to) before a home is archived or deleted."""
    target = codex_home / "auth.json"
    if os.path.islink(target):
        os.unlink(target)
    elif target.exists():
        # Codex replaced the link with a regular file: a credential copy now sits in the
        # bench tree. Remove it without reading it, and say so.
        os.unlink(target)
        raise IsolationError(f"{target} had become a regular file; it was deleted unread")


def clone_codex_home(template: Path, dest: Path, source: Path = DEFAULT_AUTH_SOURCE) -> Path:
    """A per-cell copy of an arm's prepared home, with a fresh credential link."""
    if dest.exists():
        raise IsolationError(f"refusing to clone over {dest}")
    shutil.copytree(
        template,
        dest,
        symlinks=True,
        ignore=shutil.ignore_patterns("auth.json", "sessions", "log", "logs_*.sqlite", "tmp"),
    )
    link_auth(dest, source)
    os.chmod(dest, 0o700)
    return dest


# -- plugin copies ----------------------------------------------------------------


def symlink_free_copy(src: Path, dst: Path) -> list[str]:
    """Copy a plugin or marketplace tree, refusing links and special files.

    Codex fingerprints every file under a plugin root on every hook run; a symlink or a
    special file makes that fail and the hooks are then skipped silently. Returns the
    copied relative paths.
    """
    copied: list[str] = []
    for dirpath, dirnames, filenames in os.walk(src, followlinks=False):
        base = Path(dirpath)
        for name in list(dirnames):
            if name in PLUGIN_SKIP_PARTS:
                dirnames.remove(name)
            elif (base / name).is_symlink():
                raise IsolationError(f"symlinked directory in plugin source: {base / name}")
        for name in filenames:
            path = base / name
            if name in PLUGIN_SKIP_PARTS or path.suffix in PLUGIN_SKIP_SUFFIXES:
                continue
            mode = os.lstat(path).st_mode
            if not stat.S_ISREG(mode):
                raise IsolationError(f"not a regular file in plugin source: {path}")
            rel = path.relative_to(src)
            target = dst / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target, follow_symlinks=False)
            copied.append(rel.as_posix())
    return sorted(copied)


# What a plugin shows the model: skills (listed with their paths), slash commands, agents.
MODEL_VISIBLE_PARTS = ("skills", "commands", "agents")
# Manifest keys a hooks-only variant keeps: identity and the hooks, nothing descriptive.
HOOKS_ONLY_MANIFEST_KEYS = ("name", "version", "hooks", "requires_local_executor")


def hooks_only_copy(src: Path, dst: Path, manifest_relative: str) -> list[str]:
    """A copy of a plugin with nothing model-visible: the observe arm's variant.

    The hooks (and the scripts they run) are kept byte for byte, so the observe arm records
    exactly what the guarded arm acts on; skills, commands and agents are dropped, and the
    manifest keeps only its name, version and hooks (the name stays, so the install id,
    the runtime's data directory and hook trust work as for the full plugin).
    """
    copied = symlink_free_copy(src, dst)
    for part in MODEL_VISIBLE_PARTS:
        shutil.rmtree(dst / part, ignore_errors=True)
    manifest = dst / manifest_relative
    data = json.loads(manifest.read_text(encoding="utf-8"))
    kept = {key: data[key] for key in HOOKS_ONLY_MANIFEST_KEYS if key in data}
    manifest.write_text(json.dumps(kept, indent=2) + "\n", encoding="utf-8")
    return sorted(p for p in copied if p.split("/", 1)[0] not in MODEL_VISIBLE_PARTS)


def assert_symlink_free(root: Path) -> None:
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        for name in [*dirnames, *filenames]:
            path = Path(dirpath) / name
            mode = os.lstat(path).st_mode
            if stat.S_ISLNK(mode) or not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
                raise IsolationError(f"link or special file under a plugin root: {path}")


def tree_digest(root: Path) -> str:
    hasher = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        if any(part in PLUGIN_SKIP_PARTS for part in path.parts) or path.suffix in PLUGIN_SKIP_SUFFIXES:
            continue
        hasher.update(path.relative_to(root).as_posix().encode() + b"\0" + path.read_bytes() + b"\0")
    return hasher.hexdigest()


# -- the agent's shell ------------------------------------------------------------


def scratch_shell_home(path: Path, path_prefix: list[str]) -> Path:
    """A HOME whose login profile pins PATH after macOS ``path_helper``.

    Codex runs both the agent's commands and its hooks as ``$SHELL -lc``. A login zsh
    sources /etc/zprofile, whose ``path_helper`` moves system directories to the front;
    ``.zprofile`` runs after it, so the task interpreter and pytest win again. Using a
    scratch HOME also keeps the user's own dotfiles out of both arms.
    """
    private_dir(path)
    prefix = ":".join(path_prefix)
    line = f'export PATH="{prefix}:$PATH"\n'
    for name in (".zshenv", ".zprofile", ".bash_profile", ".profile"):
        (path / name).write_text(
            "# benchmark shell profile (identical in both arms)\n" + line, encoding="utf-8"
        )
    return path


# -- the task interpreter ---------------------------------------------------------


def make_task_env(dest: Path, uv: str, python_version: str, pytest_version: str) -> Path:
    """A venv with only pytest: the agent's python, pytest and pip. Reused when it matches."""
    marker = dest / ".bench-env"
    wanted = f"python={python_version} pytest={pytest_version}\n"
    python = dest / "bin" / "python"
    if marker.exists() and marker.read_text(encoding="utf-8") == wanted and python.exists():
        return python
    if dest.exists():
        shutil.rmtree(dest)
    subprocess.run([uv, "venv", "--quiet", "--python", python_version, str(dest)], check=True, timeout=300)
    subprocess.run(
        [uv, "pip", "install", "--quiet", "--python", str(python), f"pytest=={pytest_version}"],
        check=True,
        timeout=600,
    )
    marker.write_text(wanted, encoding="utf-8")
    return python
