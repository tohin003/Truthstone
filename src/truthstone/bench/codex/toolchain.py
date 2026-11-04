"""The Node toolchain TypeScript tasks run with: found once, pinned by version, exposed alone.

TypeScript tasks need ``node`` (and, realistically, ``npm`` for ``npm test``) on the
agent's ``PATH``. The user's Node lives in a version manager's ``bin`` directory next to
unrelated global tools (Claude Code itself among them), so a cell never gets that
directory: it gets a private ``bin`` holding links to ``node``, ``npm`` and ``npx`` only.
The plan pins the Node version (``node_version``) and a run refuses any other.

No npm package is ever installed: the TypeScript bases have zero dependencies, run fully
offline, and Node 24 executes ``.ts`` files by stripping types.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

ENV_NODE = "CODEX_BENCH_NODE"  # the harness's own override, like CODEX_BENCH_PYTHON
TOOLS = ("node", "npm", "npx")


class ToolchainError(RuntimeError):
    pass


def default_node() -> str:
    """The Node binary: ``$CODEX_BENCH_NODE``, else ``node`` on PATH, else the newest nvm one."""
    explicit = os.environ.get(ENV_NODE)
    if explicit:
        return explicit
    found = shutil.which("node")
    if found:
        return found
    candidates = sorted(
        Path.home().glob(".nvm/versions/node/*/bin/node"), key=lambda p: _version_key(p.parent.parent.name)
    )
    if candidates:
        return str(candidates[-1])
    raise ToolchainError(f"no Node found: set {ENV_NODE} or put node on PATH")


def _version_key(text: str) -> tuple[int, ...]:
    return tuple(int(n) for n in re.findall(r"\d+", text)[:3])


def node_version(node: str) -> str:
    """``v24.14.1`` -> ``24.14.1``."""
    try:
        out = subprocess.run(
            [node, "--version"], capture_output=True, text=True, timeout=30, env={"PATH": "/usr/bin:/bin"}
        ).stdout
    except OSError as exc:
        raise ToolchainError(f"cannot run {node}: {exc}") from exc
    match = re.search(r"(\d+\.\d+\.\d+)", out)
    if not match:
        raise ToolchainError(f"{node} --version said {out!r}")
    return match.group(1)


def make_toolchain(dest: Path, node: str, pinned: str = "") -> Path:
    """A ``bin`` directory with ``node``, ``npm`` and ``npx`` and nothing else.

    Each entry is a link to the real file (npm and npx are scripts that find their own
    library through their real path). Returns the directory, ready for ``PATH``.
    """
    real_node = Path(node).resolve()
    version = node_version(str(real_node))
    if pinned and version != pinned:
        raise ToolchainError(f"Node {version} != pinned {pinned}")
    bin_dir = dest / "bin"
    if bin_dir.exists():
        shutil.rmtree(bin_dir)
    bin_dir.mkdir(parents=True)
    os.symlink(real_node, bin_dir / "node")
    for tool in TOOLS[1:]:
        sibling = Path(node).parent / tool
        if os.path.lexists(sibling):
            os.symlink(sibling.resolve(), bin_dir / tool)
    return bin_dir


def npm_env(tmpdir: Path) -> dict[str, str]:
    """npm's cache and logs inside the cell's own temp directory; no network chatter.

    Identical in both arms. Without it ``npm test`` writes ``~/.npm/_logs`` (outside every
    cell, and outside the sandboxes' writable roots) and asks the registry for updates.
    """
    return {
        "npm_config_cache": str(tmpdir / "npm-cache"),
        "npm_config_update_notifier": "false",
        "npm_config_fund": "false",
        "npm_config_audit": "false",
    }
