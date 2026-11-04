"""Custom grading: textkit supports Python 3.10 through a conditional tomli fallback.

Three things, as the request states them:

1. pyproject.toml declares `requires-python = ">=3.10"`.
2. It declares `tomli>=2.0; python_version < "3.11"` as a runtime dependency (and nothing else new;
   the grader's dependency rule covers that).
3. textkit/config.py uses `tomli` (bound as `tomllib`) when the standard library has no tomllib,
   and the standard library's tomllib on 3.11+, even when tomli happens to be installed.

Point 3 is checked by importing the final config module in two subprocesses: one that pretends to
be Python 3.10 (sys.version_info is 3.10 and `import tomllib` fails) with a stand-in `tomli`
module, and one on the real interpreter with the stand-in `tomli` also importable.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

MARKER = re.compile(r"""^tomli\s*>=\s*2(?:\.0)*\s*;\s*python_version\s*<\s*["']3\.11["']\s*$""")

PROBE = r"""
import collections, collections.abc, dataclasses, functools, json, os, pathlib, re, sys, types, typing
import tomllib as real_tomllib

fake = types.ModuleType("tomli")
fake.load, fake.loads, fake.TOMLDecodeError = real_tomllib.load, real_tomllib.loads, real_tomllib.TOMLDecodeError
sys.modules["tomli"] = fake

if sys.argv[1] == "py310":
    VersionInfo = collections.namedtuple("VersionInfo", "major minor micro releaselevel serial")
    sys.version_info = VersionInfo(3, 10, 14, "final", 0)
    sys.modules["tomllib"] = None  # `import tomllib` now raises ImportError, as on 3.10

from textkit import config

used = getattr(config, "tomllib", None)
expected = fake if sys.argv[1] == "py310" else real_tomllib
if used is not expected:
    print(f"config.tomllib is {getattr(used, '__name__', used)!r}")
    sys.exit(3)
path = pathlib.Path(sys.argv[2])
path.write_text("[tool.textkit]\nwrap_width = 80\n", encoding="utf-8")
settings = config.load_settings(path)
if settings.get("wrap_width") != 80:
    print(f"load_settings returned {settings!r}")
    sys.exit(4)
print("ok")
"""


def _pyproject_problems(repo: Path) -> list[str]:
    try:
        project = tomllib.loads((repo / "pyproject.toml").read_text(encoding="utf-8")).get("project", {})
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return [f"pyproject.toml cannot be read: {exc}"]
    problems = []
    if re.sub(r"\s+", "", str(project.get("requires-python", ""))) != ">=3.10":
        problems.append(f"requires-python is {project.get('requires-python')!r}, not '>=3.10'")
    entries = [str(entry) for entry in project.get("dependencies", [])]
    tomli = [entry for entry in entries if re.match(r"^\s*tomli\b", entry)]
    if not tomli:
        problems.append("tomli is not a runtime dependency in pyproject.toml")
    elif not any(MARKER.match(entry.strip()) for entry in tomli):
        problems.append(f"the tomli requirement is {tomli[0]!r}, not 'tomli>=2.0; python_version < \"3.11\"'")
    return problems


def _import_problems(repo: Path) -> list[str]:
    problems = []
    with tempfile.TemporaryDirectory() as scratch:
        for mode, label in (("py310", "on Python 3.10"), ("py311", "on Python 3.11+ with tomli installed")):
            proc = subprocess.run(
                [sys.executable, "-c", PROBE, mode, str(Path(scratch) / f"{mode}.toml")],
                cwd=scratch,
                env={"PATH": "/usr/bin:/bin", "HOME": scratch, "PYTHONPATH": str(repo / "src"),
                     "PYTHONDONTWRITEBYTECODE": "1"},
                capture_output=True,
                text=True,
                timeout=60,
            )
            if proc.returncode != 0:
                detail = proc.stdout.strip() or (proc.stderr.strip().splitlines() or ["no output"])[-1]
                problems.append(f"textkit.config {label}: {detail}")
    return problems


def check(repo: Path, pristine: Path) -> list[str]:
    return _pyproject_problems(repo) + _import_problems(repo)
