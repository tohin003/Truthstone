#!/usr/bin/env python3
"""Rebuild the `claude-directory` branch: the companion plugin as Claude's plugin directory takes it.

Claude's directory reads `plugins/truthstone-practices` from the branch `claude-directory`, not from
`master`. From an organization that is not Verified its policy check accepts Markdown, text, JSON,
YAML and raster images only, and it refused the folder as it is on `master` (`docs/LISTING.md` §8.2).
The branch therefore holds the folder without what only Codex reads:

* `.codex-plugin/` (the Codex manifest),
* the SVG logos and icons (Claude's manifest names `assets/logo.png`),
* `skills/<name>/agents/openai.yaml`,

with the one README sentence that lists the folder's contents adjusted to match, and a short README
at the branch root. Nothing else differs from the source commit.

    python3 scripts/claude_directory_branch.py            # from HEAD
    python3 scripts/claude_directory_branch.py v0.2.0     # from another commit

It moves the local branch `claude-directory` (a new commit on top of the old one, or nothing when
the tree is unchanged) and prints what to push. It does not push.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile

PLUGIN = "plugins/truthstone-practices"
BRANCH = "claude-directory"
README_ON_MASTER = (
    "The plugin contains Markdown instructions with YAML display metadata, icons, manifests, "
    "its licence and security policy; nothing else."
)
README_ON_BRANCH = (
    "The plugin contains Markdown instructions, an icon, its manifest, its licence and security "
    "policy; nothing else."
)
ROOT_README = (
    "# Truthstone Practices: directory branch\n\n"
    "This branch holds one thing: the `truthstone-practices` plugin, at `plugins/truthstone-practices/`, "
    "as Claude's plugin directory takes it. It is the folder from `master` without the files that only "
    "Codex reads (the Codex manifest, the SVG logos and each skill's `openai.yaml`), built by "
    "`scripts/claude_directory_branch.py` on `master`.\n\n"
    "Everything else (the Truthstone runtime, the hook plugins, the benchmark and the documentation) "
    "is on [`master`](https://github.com/tohin003/Truthstone).\n"
)


def git(*args: str, env: dict[str, str] | None = None, stdin: bytes | None = None) -> str:
    done = subprocess.run(["git", *args], check=True, capture_output=True, env=env, input=stdin)
    return done.stdout.decode().strip()


def dropped(path: str) -> bool:
    """Whether Claude's directory must not see this file of the plugin folder."""
    inside = path[len(PLUGIN) + 1 :]
    return (
        inside.startswith(".codex-plugin/")
        or inside.endswith(".svg")
        or (inside.startswith("skills/") and inside.endswith("/agents/openai.yaml"))
    )


def main() -> int:
    source = git("rev-parse", "--verify", f"{sys.argv[1] if len(sys.argv) > 1 else 'HEAD'}^{{commit}}")
    with tempfile.TemporaryDirectory() as scratch:
        env = dict(os.environ, GIT_INDEX_FILE=os.path.join(scratch, "index"))
        git("read-tree", "--empty", env=env)
        git("read-tree", f"--prefix={PLUGIN}/", f"{source}:{PLUGIN}", env=env)
        for path in git("ls-files", env=env).splitlines():
            if dropped(path):
                git("update-index", "--force-remove", path, env=env)

        readme = git("show", f"{source}:{PLUGIN}/README.md") + "\n"
        if readme.count(README_ON_MASTER) != 1:
            sys.exit(f"{PLUGIN}/README.md no longer has the sentence this script rewrites")
        readme = readme.replace(README_ON_MASTER, README_ON_BRANCH)
        blob = git("hash-object", "-w", "--stdin", stdin=readme.encode())
        git("update-index", "--cacheinfo", f"100644,{blob},{PLUGIN}/README.md", env=env)
        blob = git("hash-object", "-w", "--stdin", stdin=ROOT_README.encode())
        git("update-index", "--add", "--cacheinfo", f"100644,{blob},README.md", env=env)
        tree = git("write-tree", env=env)

    parent = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{BRANCH}"], capture_output=True
    ).stdout.decode().strip()
    if parent and git("rev-parse", f"{parent}^{{tree}}") == tree:
        print(f"{BRANCH} is up to date with {source[:7]} ({parent[:7]})")
        return 0
    version = git("show", f"{source}:{PLUGIN}/.claude-plugin/plugin.json")
    version = version.split('"version": "')[1].split('"')[0]
    message = (
        f"Truthstone Practices {version}, as on master {source[:7]}\n\n"
        "The plugin folder as Claude's plugin directory takes it.\n"
    )
    commit = git("commit-tree", tree, *(["-p", parent] if parent else []), "-m", message)
    git("update-ref", f"refs/heads/{BRANCH}", commit)
    print(f"{BRANCH} -> {commit[:7]} (from {source[:7]}, version {version})")
    print(f"push with: git push <public remote> {BRANCH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
