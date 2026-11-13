"""`textkit slug`, run from the repository, takes its max_length from [tool.textkit.slug] in pyproject.toml (60)."""

import os
import subprocess
import sys
from pathlib import Path

from textkit.cli import main
from textkit.slug import slugify

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "src" / "textkit").is_dir())
LONG = "Configuring percentage rollouts and environment overrides for the storefront and the mobile apps"
SHORT = "Release notes"


def test_slug_command_from_the_repository_caps_anchors_at_60(capsys, monkeypatch):
    monkeypatch.chdir(ROOT)
    assert main(["slug", LONG, SHORT]) == 0
    first, second = capsys.readouterr().out.splitlines()
    assert first == slugify(LONG, max_length=60)
    assert len(first) <= 60
    assert second == "release-notes"


def test_slug_command_as_a_process_from_the_repository():
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    out = subprocess.run(
        [sys.executable, "-m", "textkit.cli", "slug", LONG],
        cwd=ROOT, env=env, capture_output=True, text=True, check=True,
    ).stdout
    assert out == slugify(LONG, max_length=60) + "\n"


def test_slugify_itself_is_unchanged():
    assert slugify(LONG) == slugify(LONG, max_length=None)
    assert len(slugify(LONG)) > 60
    assert slugify("Crème Brûlée") == "creme-brulee"
