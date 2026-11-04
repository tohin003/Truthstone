"""`RepoIndex.refresh_delta`: which paths a sweep saw change (G5 support).

Edit/Write tell Truthstone which file they touched. Bash does not: `sed -i`, a codemod,
`rm` or `git mv` change files that only a sweep of the tree can see. `refresh()` always
computed those path sets but returned only counts; `refresh_delta()` returns the sets so
the Completion Gate can count Bash-made changes, deletions included.
"""

from __future__ import annotations

import dataclasses
import subprocess
from pathlib import Path

import pytest

from truthstone.repo import IndexDelta, RepoIndex


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "src" / "shop").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "src" / "shop" / "__init__.py").write_text("")
    (root / "src" / "shop" / "orders.py").write_text("def list_orders():\n    return []\n")
    (root / "src" / "shop" / "billing.py").write_text("def charge(amount):\n    return amount\n")
    (root / "src" / "shop" / "legacy.py").write_text("def old_path():\n    return None\n")
    (root / "src" / "shop" / "names.py").write_text("def rename_me():\n    return 1\n")
    (root / "tests" / "test_billing.py").write_text(
        "from shop.billing import charge\n\n\ndef test_charge():\n    assert charge(1) == 1\n"
    )
    return root


def test_refresh_delta_reports_external_add_modify_remove(repo):
    index = RepoIndex(repo).build()

    # What a shell command might do behind the agent's tools: create, rewrite in place,
    # delete, and move.
    (repo / "src" / "shop" / "refunds.py").write_text("def refund(amount):\n    return -amount\n")
    billing = repo / "src" / "shop" / "billing.py"
    billing.write_text(billing.read_text().replace("return amount", "return amount * 100"))
    (repo / "src" / "shop" / "legacy.py").unlink()
    (repo / "src" / "shop" / "names.py").rename(repo / "src" / "shop" / "labels.py")

    delta = index.refresh_delta()

    assert delta.swept is True
    assert delta.added == {"src/shop/refunds.py", "src/shop/labels.py"}
    assert delta.modified == {"src/shop/billing.py"}
    assert delta.removed == {"src/shop/legacy.py", "src/shop/names.py"}
    assert delta.changed == delta.added | delta.modified | delta.removed
    assert delta.counts() == {"added": 2, "modified": 1, "removed": 2}
    # The sweep also brought the index up to date, as refresh() always did.
    assert index.has_symbol("refund")
    assert not index.has_symbol("old_path")
    assert index.find_symbol("rename_me")[0].path == "src/shop/labels.py"
    assert index.tests_for("src/shop/billing.py") == {"tests/test_billing.py"}

    # Nothing changed since: a sweep that ran and saw nothing.
    again = index.refresh_delta()
    assert again == IndexDelta(swept=True)


def test_refresh_delta_sees_a_bash_move_in_git(repo):
    for args in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "init"]):
        subprocess.run(
            ["git", "-c", "user.email=t@t", "-c", "user.name=t", "-c", "commit.gpgsign=false", *args],
            cwd=repo,
            check=True,
            capture_output=True,
        )
    index = RepoIndex(repo).build()
    subprocess.run(
        ["git", "mv", "src/shop/orders.py", "src/shop/purchases.py"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    delta = index.refresh_delta()

    assert delta.added == {"src/shop/purchases.py"}
    assert delta.removed == {"src/shop/orders.py"}
    assert delta.modified == frozenset()


def test_refresh_delta_is_unswept_when_skipped_or_unbuilt(repo):
    unbuilt = RepoIndex(repo)
    assert unbuilt.refresh_delta() == IndexDelta(swept=False)
    assert unbuilt.is_built is False, "refresh_delta must never build on the caller's path"

    index = RepoIndex(repo).build()
    (repo / "src" / "shop" / "late.py").write_text("LATE = 1\n")
    skipped = index.refresh_delta(min_interval=60.0)
    assert skipped.swept is False
    assert skipped.changed == frozenset()
    # A skipped sweep loses nothing: the next one that runs reports the change.
    assert index.refresh_delta().added == {"src/shop/late.py"}


def test_index_delta_is_immutable():
    delta = IndexDelta(added=frozenset({"a.py"}), swept=True)
    with pytest.raises(dataclasses.FrozenInstanceError):
        delta.swept = False  # type: ignore[misc]
    assert isinstance(delta.added, frozenset)
    assert isinstance(delta.removed, frozenset)


def test_refresh_keeps_its_signature_and_counts(repo):
    index = RepoIndex(repo).build()
    (repo / "src" / "shop" / "refunds.py").write_text("def refund(amount):\n    return -amount\n")
    assert index.refresh() == {"added": 1, "modified": 0, "removed": 0}
    assert index.refresh(min_interval=60.0) == {"added": 0, "modified": 0, "removed": 0}

    fresh = RepoIndex(repo)
    counts = fresh.refresh()  # an unbuilt index is still built by refresh()
    assert fresh.is_built
    assert counts == {"added": len(fresh.files), "modified": 0, "removed": 0}
