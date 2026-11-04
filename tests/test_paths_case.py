"""Case-variant paths on case-insensitive volumes (R18).

On APFS (macOS's default) `/x/REPO/src/a.py` *is* `/x/Repo/src/a.py`, but containment
compared spellings and called it outside: the edit went untracked, and the Completion
Gate allowed a Stop the control blocked. A path whose head names the workspace by
identity (`samefile`) is now inside and comes back in the tree's own spelling.
Confinement against symlink escapes and `..` is unchanged, which the second half of this
file pins down for the case-variant spelling specifically.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from agentguard.core.config import Settings
from agentguard.core.engine import Guard
from agentguard.core.enums import EventType
from agentguard.core.events import AgentEvent
from agentguard.repo import RepoIndex
from agentguard.repo.paths import relative_path


def _case_insensitive(directory: Path) -> bool:
    probe = directory / "CaseProbe"
    probe.mkdir()
    try:
        return (directory / "caseprobe").exists()
    finally:
        probe.rmdir()


@pytest.fixture
def lab(tmp_path: Path) -> Path:
    base = tmp_path.resolve()
    repo = base / "Repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "a.py").write_text("def f():\n    return 1\n")
    (base / "outside").mkdir()
    (base / "outside" / "secret.py").write_text("TOKEN = 'x'\n")
    try:
        (repo / "link_out").symlink_to(base / "outside", target_is_directory=True)
        (repo / "link_in.py").symlink_to(repo / "src" / "a.py")
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlinks unavailable: {exc}")
    return base


def _variant(repo: Path) -> str:
    return str(repo.parent / repo.name.upper())


requires_case_insensitive = pytest.mark.skipif(
    not _case_insensitive(Path(os.environ.get("TMPDIR", "/tmp")).resolve()),
    reason="the temporary directory is on a case-sensitive volume",
)
requires_case_sensitive = pytest.mark.skipif(
    _case_insensitive(Path(os.environ.get("TMPDIR", "/tmp")).resolve()),
    reason="the temporary directory is on a case-insensitive volume",
)


@requires_case_insensitive
def test_case_variant_path_is_inside(lab):
    repo = lab / "Repo"
    variant = _variant(repo)

    assert relative_path(repo, f"{variant}/src/a.py") == "src/a.py"
    # Respelled as the tree spells it, so it names the indexed file.
    assert relative_path(repo, f"{variant}/SRC/A.PY") == "src/a.py"
    # A file about to be created keeps the spelling it was given.
    assert relative_path(repo, f"{variant}/src/New.py") == "src/New.py"
    # An internal symlink keeps its own name, as the scanner keys it.
    assert relative_path(repo, f"{variant}/link_in.py") == "link_in.py"
    assert relative_path(repo, variant) is None  # the root is not a file path

    index = RepoIndex(repo).build()
    assert index.normalize(f"{variant}/src/a.py") == "src/a.py"
    assert index.file_exists(f"{variant}/src/a.py")
    (repo / "src" / "a.py").write_text("def f():\n    return 2\n\n\ndef g():\n    return 3\n")
    assert index.refresh_path(f"{variant}/src/a.py") is True
    assert index.has_symbol("g")
    assert set(index.files) == {"src/a.py", "link_in.py"}, "no case-duplicate record"


@requires_case_insensitive
def test_case_variant_edit_is_tracked_by_the_engine(lab):
    repo = lab / "Repo"
    guard = Guard(Settings())
    try:
        ws = guard.workspace(repo)
        ws.index.ready(timeout=30)
        guard.handle(
            AgentEvent(
                event=EventType.USER_PROMPT,
                agent="claude-code",
                workspace=str(repo),
                session_id="s-case",
                prompt_text="Change f to return 2",
            )
        )
        task_id = ws.resolve_task_id("s-case")
        assert task_id
        guard.handle(
            AgentEvent(
                event=EventType.POST_TOOL_USE,
                agent="claude-code",
                workspace=str(repo),
                session_id="s-case",
                tool="Edit",
                arguments={"file_path": f"{_variant(repo)}/src/a.py"},
            )
        )
        state = ws.task_state(task_id, "s-case")
        assert state is not None
        assert state.touched_files == {"src/a.py"}
    finally:
        guard.close()


@requires_case_insensitive
def test_case_variant_spelling_cannot_escape(lab):
    repo = lab / "Repo"
    variant = _variant(repo)

    assert relative_path(repo, f"{variant}/link_out/secret.py") is None  # symlink escape
    assert relative_path(repo, f"{variant}/../outside/secret.py") is None  # `..` escape
    assert relative_path(repo, f"{variant}/src/../../outside/secret.py") is None
    assert relative_path(repo, str(lab / "OUTSIDE" / "secret.py")) is None  # a sibling
    index = RepoIndex(repo).build()
    assert index.refresh_path(f"{variant}/link_out/secret.py") is False
    assert not any("secret" in path for path in index.files)


def test_a_variant_spelling_is_admitted_only_by_identity(lab, monkeypatch):
    """Folding the spelling only selects the candidate; `samefile` decides.

    With identity denied (as for a distinct `REPO` directory on a case-sensitive volume),
    the variant is outside on every platform, while the exact spelling is unaffected.
    """
    repo = lab / "Repo"
    monkeypatch.setattr(os.path, "samefile", lambda a, b: False)

    assert relative_path(repo, f"{_variant(repo)}/src/a.py") is None
    assert relative_path(repo, str(repo / "src" / "a.py")) == "src/a.py"
    assert relative_path(repo, "src/a.py") == "src/a.py"


@requires_case_sensitive
def test_differently_cased_sibling_is_outside_on_case_sensitive_volumes(lab):
    """Where case matters, `REPO` is another directory, and must stay outside."""
    repo = lab / "Repo"
    sibling = lab / "REPO"
    (sibling / "src").mkdir(parents=True)
    (sibling / "src" / "a.py").write_text("TOKEN = 'other'\n")

    assert relative_path(repo, str(sibling / "src" / "a.py")) is None
    assert relative_path(repo, str(sibling / "src" / "new.py")) is None
