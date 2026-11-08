"""Day 4, C2 v3c: the task-start documentation snapshot (``verify/spec_snapshot.py``).

The frozen prototype ``snapshot_proto_v3c.py`` is the specification (FIX-DESIGN v4, S0, C2, D-C2).
Pinned here:

* its rule-level self-test (``protoC/c2-selftest.txt``): the git lines that re-snapshot and those
  that never do; the deleted-doc skips (a removed directory, a move); the re-snapshot cost of a
  1,000-doc checkout; a re-snapshot that is a no-op until the snapshot is done;
* the caps, the deadline, the scanner's listing, the first write-capable event's wait (live), the
  thread that publishes in a ``finally``, one snapshot per session's current task, a synchronous
  snapshot in process;
* ``spec_integrity.eroded``'s new keywords against the prototype's ``eroded_v3``;
* the engine: the C2 scenarios of ``tests/day4_c2c3_sessions.py`` (the heldout3 (a) shape, git
  commands that bring in another ref and those that do not, deleted and moved docs, a removed
  package, history and test files, a formatter before an edit, many docs) give, at every Stop, the
  decisions the prototype gives (``tests/data/day4_c2c3/prototype-decisions.json``).
"""

from __future__ import annotations

import json
import time
import zlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests import day4_c2c3_sessions as kit
from truthstone.adapters.claude_code import translate as claude
from truthstone.core.config import Settings
from truthstone.core.engine import Guard
from truthstone.core.shellchanges import ShellChanges
from truthstone.core.taskstate import TaskState
from truthstone.intent.models import TaskSpec
from truthstone.validate import spec_integrity as si
from truthstone.verify import spec_snapshot as S

REF = json.loads((Path(__file__).parent / "data" / "day4_c2c3" / "prototype-decisions.json").read_text())

# -- the git lines (the prototype's self-test, protoC/c2-selftest.txt) ---------------------------------------

RE_SNAPSHOT = [
    "git merge origin/main",
    "git pull",
    "git pull --rebase origin main",
    "git rebase main",
    "git rebase --continue",
    "git cherry-pick abc123",
    "git checkout feature/x",
    "git checkout main -- docs/A.md",
    "git checkout -",
    "git switch feature/x",
    "git switch -c fix origin/main",
    "git reset --hard origin/main",
    "git reset --hard",
    "git restore --source=HEAD~1 docs/A.md",
    "git restore -s v1.2 docs/A.md",
    "git revert abc123",
    "gh pr checkout 42",
    "git -C . merge topic",
    "git merge topic && git pull",
    "GIT_EDITOR=true git rebase --continue",
]
NEVER = [
    "git stash",
    "git stash pop",
    "git stash apply stash@{0}",
    "git apply fix.patch",
    "git am < series.mbox",
    "patch -p1 < fix.patch",
    "git switch -c fix",
    "git checkout -b fix",
    "git checkout -- docs/A.md",
    "git checkout .",
    "git checkout docs/A.md",
    "git restore docs/A.md",
    "git merge --abort",
    "git fetch origin",
    "git fetch origin && git merge origin/main",
    "git switch -c fix && cat > docs/A.md <<'EOF'\nnew text\nEOF",
    "git merge topic | tail -5",
    "git stash && pytest -q; git stash pop",
    "git merge topic > merge.log",
    "git status",
    "gh pr view 42",
    "cd repo && git merge topic",
    "git merge $(git rev-parse HEAD~1)",
]


@pytest.fixture
def root_with_doc(tmp_path: Path) -> Path:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "A.md").write_text("A doc.\n")
    return tmp_path


@pytest.mark.parametrize("command", RE_SNAPSHOT)
def test_a_line_made_of_git_commands_bringing_in_a_ref_re_snapshots(root_with_doc, command):
    assert S.brings_in_ref(command, root_with_doc) is True


@pytest.mark.parametrize("command", NEVER)
def test_stash_apply_patch_and_mixed_lines_never_re_snapshot(root_with_doc, command):
    assert S.brings_in_ref(command, root_with_doc) is False


def test_brings_in_ref_never_raises():
    assert S.brings_in_ref("git merge 'unterminated", None) is False
    assert S.brings_in_ref("", None) is False


# -- deleted docs: a removed directory, a move (the prototype's self-test) -----------------------------------

RULE = "This layer is frozen: it must not gain new features.\n" * 3


@pytest.fixture
def moved_tree(tmp_path: Path) -> tuple[Path, SimpleNamespace, SimpleNamespace, set[str]]:
    root = tmp_path / "repo"
    (root / "src/kit/v2").mkdir(parents=True)
    (root / "docs/archive").mkdir(parents=True)
    (root / "src/kit/v2/README.md").write_text("v2 notes\n")
    (root / "docs/FORMAT.md").write_text("The stock file format, version 2, written by the exporter.\n")
    (root / "docs/archive/notes.md").write_text(RULE + "One more line.\n")
    (root / "docs/other.md").write_text("Nothing alike at all, a different page about something else.\n")
    state = SimpleNamespace(
        changed_files={
            "src/kit/v1/README.md",
            "src/kit/v1/core.py",
            "old/FORMAT.md",
            "docs/FORMAT.md",
            "guide/rules.md",
            "docs/archive/notes.md",
            "docs/other.md",
            "x/gone.md",
        }
    )
    gone = {"src/kit/v1/README.md", "src/kit/v1/core.py", "old/FORMAT.md", "guide/rules.md", "x/gone.md"}
    return root, state, SimpleNamespace(root=root), gone


def test_a_doc_whose_whole_directory_went_is_not_compared(moved_tree):
    root, _state, _index, _gone = moved_tree
    assert S.dir_removed(root, "src/kit/v1/README.md") is True
    assert S.dir_removed(root, "README.md") is False  # the repository root never counts
    assert S.dir_removed(root, "docs/gone.md") is False  # docs/ still holds files


def test_a_moved_doc_is_not_compared(moved_tree):
    _root, state, index, gone = moved_tree
    assert S.moved_to("old/FORMAT.md", RULE, state, index, {}, gone) == "docs/FORMAT.md"  # the same base name
    assert (
        S.moved_to("guide/rules.md", RULE, state, index, {}, gone) == "docs/archive/notes.md"
    )  # >= 80% alike
    assert (
        S.moved_to("x/gone.md", "A rule that must never change, written once.\n", state, index, {}, gone)
        == ""
    )


def test_similarity_is_difflib_at_eighty_percent():
    assert S.similar("abcdefghij", "abcdefghiX") is True
    assert S.similar("abcdefghij", "abcdeXXXXX") is False
    assert S.similar("", "abc") is False


# -- the snapshot: taking it, its caps, its wait -------------------------------------------------------------


def _state(task_id: str = "t-1") -> TaskState:
    return TaskState(task_id=task_id, spec=TaskSpec(prompt=""))


def test_scope_is_docs_without_history_and_without_tests():
    assert (
        S.in_spec_scope("README.md")
        and S.in_spec_scope("docs/FORMAT.md")
        and S.in_spec_scope("tests/README.md")
    )
    assert not S.in_spec_scope("CHANGELOG.md") and not S.in_spec_scope("docs/HISTORY.md")
    assert not S.in_spec_scope("tests/test_export.py") and not S.in_spec_scope("src/a.py")


def test_the_caps_skip_large_and_binary_docs(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/big.md").write_text("x" * (S.FILE_BYTES + 1))
    (tmp_path / "docs/logo.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00" + b"\x00" * 64)
    (tmp_path / "docs/ok.md").write_text("It must hold.\n")
    files, sizes, stats = S.build(tmp_path, ["docs/big.md", "docs/logo.png", "docs/ok.md", "src/a.py"])
    assert sorted(files) == ["docs/ok.md"] and sizes == {"docs/ok.md": 14}
    assert (stats["skipped_large"], stats["skipped_binary"], stats["in_scope"], stats["cut"]) == (1, 1, 3, "")
    assert zlib.decompress(files["docs/ok.md"]) == b"It must hold.\n"


def test_the_file_and_byte_caps_and_the_deadline_cut_the_rest(tmp_path, monkeypatch):
    (tmp_path / "docs").mkdir()
    paths = []
    for n in range(5):
        (tmp_path / f"docs/p{n}.md").write_text("abcdefghij")
        paths.append(f"docs/p{n}.md")
    monkeypatch.setattr(S, "FILES", 3)
    files, _sizes, stats = S.build(tmp_path, paths)
    assert sorted(files) == paths[:3] and stats["cut"] == "files"
    monkeypatch.setattr(S, "FILES", 2_000)
    monkeypatch.setattr(S, "RAW_BYTES", 25)
    files, _sizes, stats = S.build(tmp_path, paths)
    assert sorted(files) == paths[:2] and stats["cut"] == "bytes" and stats["raw_bytes"] == 20
    files, _sizes, stats = S.build(tmp_path, paths, deadline=time.monotonic() - 1)
    assert files == {} and stats["cut"] == "deadline"


def test_with_no_listing_the_snapshot_reads_gits(tmp_path):
    repo = kit.make_repo(tmp_path / "repo", {"README.md": "# r\n\nIt must hold.\n", "src/a.py": "x = 1\n"})
    state = _state()
    snap = S.start(state, repo, lambda: None, synchronous=True)
    assert state.spec_snapshot is snap and snap.done.is_set() and snap.complete
    assert sorted(snap.files) == ["README.md"] and snap.raw_bytes == len("# r\n\nIt must hold.\n")
    assert S.snapshot_text(state, "README.md") == "# r\n\nIt must hold.\n"


def test_the_thread_publishes_in_a_finally(tmp_path, monkeypatch):
    def broken(*_args, **_kwargs):
        raise RuntimeError("no")

    monkeypatch.setattr(S, "build", broken)
    state = _state()
    snap = S.start(state, tmp_path, lambda: ["README.md"], synchronous=False)
    assert snap.done.wait(5)
    assert snap.complete is False
    t0 = time.monotonic()
    S.wait(state)
    assert time.monotonic() - t0 < 0.5  # no stall for the first write
    assert S.snapshot_docs(state) == {} and S.snapshot_text(state, "README.md") is None  # no snapshot


def test_the_live_snapshot_waits_once_for_the_first_write(tmp_path, monkeypatch):
    """Live (the daemon), the snapshot is taken on its own thread; only the task's first write-capable
    pre-tool event waits for it, a Read never does, and a later write does not wait again."""
    repo = kit.make_repo(
        tmp_path / "repo", {"README.md": "# r\n\nIt must hold.\n", "src/a.py": "x = 1\n"}
    ).resolve()
    real = S.build

    def slow(*args, **kwargs):
        time.sleep(0.4)
        return real(*args, **kwargs)

    monkeypatch.setattr(S, "build", slow)
    guard = Guard(Settings(profile="minimal"), defer_bookkeeping=True)
    try:
        guard.workspace(repo).index.ready(timeout=30)

        def send(payload: dict) -> None:
            guard.handle(claude.to_event({"session_id": "sess-live", "cwd": str(repo), **payload}))

        send({"hook_event_name": "UserPromptSubmit", "prompt": "Rename x in src/a.py."})
        state = guard.workspace(repo).task_state(None, "sess-live")
        snap = state.spec_snapshot
        assert snap is not None and snap.synchronous is False
        read = {"file_path": str(repo / "src/a.py")}
        send({"hook_event_name": "PreToolUse", "tool_name": "Read", "tool_input": read})
        assert snap.waited is False
        write = {"file_path": str(repo / "src/a.py"), "content": "y = 1\n"}
        send({"hook_event_name": "PreToolUse", "tool_name": "Write", "tool_input": write})
        assert snap.waited is True  # it waited (until done, or at most until the deadline)
        assert snap.done.wait(10) and snap.complete
        assert sorted(snap.files) == ["README.md"]
        assert S.wait(state) == 0.0  # a later write does not wait again
    finally:
        guard.close()


def test_in_process_the_snapshot_is_synchronous_and_one_per_sessions_current_task(tmp_path):
    files = {"README.md": "# r\n\nIt must hold.\n", "src/a.py": "x = 1\n"}
    repo = kit.make_repo(tmp_path / "repo", files).resolve()
    guard = Guard(Settings(profile="minimal"))
    try:
        guard.workspace(repo).index.ready(timeout=30)
        ws = guard.workspace(repo)

        def prompt(text: str) -> TaskState:
            guard.handle(
                claude.to_event(
                    {
                        "session_id": "sess-1",
                        "cwd": str(repo),
                        "hook_event_name": "UserPromptSubmit",
                        "prompt": text,
                    }
                )
            )
            return ws.task_state(None, "sess-1")

        first = prompt("Rename x in src/a.py.")
        snap = first.spec_snapshot
        assert (
            snap is not None
            and snap.synchronous
            and snap.done.is_set()
            and sorted(snap.files) == ["README.md"]
        )
        second = prompt("Now rename it back.")
        assert second.task_id != first.task_id and second.spec_snapshot is not None
        assert first.spec_snapshot is None  # freed: one snapshot per session's current task
    finally:
        guard.close()


# -- re-snapshot: queued under the lock, read off it (the prototype's self-test) -----------------------------


def _taken(state: TaskState, root: Path, paths: list[str]) -> S.SpecSnapshot:
    files, sizes, _stats = S.build(root, paths)
    snap = S.SpecSnapshot(True)
    snap.files, snap.raw, snap.raw_bytes = files, sizes, sum(sizes.values())
    snap.complete = True  # as ``start`` publishes it
    snap.done.set()
    state.spec_snapshot = snap
    return snap


def test_a_1000_doc_checkout_is_re_snapshotted_off_the_lock_within_a_bound(tmp_path):
    (tmp_path / "docs").mkdir()
    paths = []
    for n in range(1000):
        rel = f"docs/page{n:04d}.md"
        (tmp_path / rel).write_text(f"# Page {n}\n\n" + "Every rule here must hold. " * 60 + "\n")
        paths.append(rel)
    state = _state()
    snap = _taken(state, tmp_path, paths)
    for rel in paths:
        (tmp_path / rel).write_text("# Page (merged)\n\n" + "Every rule here must hold. " * 61 + "\n")
    t0 = time.perf_counter()
    for rel in paths:
        S.queue_resnapshot(state, tmp_path, rel)
    queued = time.perf_counter() - t0
    assert snap.files is state.spec_snapshot.files  # queueing reads nothing
    t0 = time.perf_counter()
    assert S.drain(synchronous=True) == 1000
    drained = time.perf_counter() - t0
    assert queued < 1.0 and drained < 10.0  # measured on the prototype: 4 ms and 177 ms
    files = state.spec_snapshot.files
    assert sum(zlib.decompress(files[rel]).startswith(b"# Page (merged)") for rel in paths) == 1000
    assert state.spec_snapshot.raw_bytes == sum(state.spec_snapshot.raw.values())


def test_a_re_snapshot_is_a_no_op_until_the_snapshot_is_done(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/a.md").write_text("It must hold.\n")
    state = _state()
    snap = S.SpecSnapshot(True)
    state.spec_snapshot = snap
    S.queue_resnapshot(state, tmp_path, "docs/a.md")
    S.drain(synchronous=True)
    assert "docs/a.md" not in snap.files


def test_only_in_scope_paths_of_a_task_with_a_snapshot_are_queued(tmp_path):
    state = _state()
    S.queue_resnapshot(state, tmp_path, "docs/a.md")  # no snapshot: nothing queued
    _taken(state, tmp_path, [])
    S.queue_resnapshot(state, tmp_path, "src/a.py")  # not a doc
    S.queue_resnapshot(state, tmp_path, "CHANGELOG.md")  # history
    assert S.drain() == 0


def test_a_reservation_carries_the_git_flag():
    state = _state()
    changes = ShellChanges()
    assert changes.reserve(state, "call-1").rewrites_tree is False
    assert changes.reserve(state, "call-2", rewrites_tree=True).rewrites_tree is True


# -- erosion with the snapshot's keywords: the prototype's eroded_v3 -----------------------------------------


@pytest.mark.parametrize("case", sorted(REF["rules"]["eroded"]["cases"]))
def test_eroded_keywords_are_the_prototypes(case):
    before, after, kw = REF["rules"]["eroded"]["cases"][case]
    found = si.eroded(
        before,
        after,
        set(),
        marker_only=kw.get("marker_only", ()),
        deleted=kw.get("deleted", ()),
        extra_pool=kw.get("extra_pool"),
    )
    assert [[e.path, e.sentence.text, e.kind, e.counterpart] for e in found] == REF["rules"]["eroded"][
        "results"
    ][case]


def test_eroded_without_keywords_is_unchanged():
    """A deleted file is not a rule edit, and a reworded prose sentence is, as before."""
    doc = "# Format\n\nEach export is one CSV file.\n\nArchived items must never be exported.\n"
    assert si.eroded({"docs/F.md": doc}, {"docs/F.md": None}) == []
    reworded = doc.replace("Each export is one CSV file.", "An export is a single CSV file.")
    assert [e.kind for e in si.eroded({"docs/F.md": doc}, {"docs/F.md": reworded})] == ["rewritten"]


# -- the engine: every Stop decision is the prototype's ------------------------------------------------------

C2_SCENARIOS = [
    "heredoc-rule-removed",
    "heredoc-paraphrase",
    "heredoc-exception",
    "no-pressure-sed",
    "git-merge",
    "git-pull",
    "git-revert",
    "stash-after-heredoc",
    "git-apply",
    "apply-after-heredoc",
    "git-mv",
    "plain-mv",
    "rm-and-v2",
    "rm-and-v2-requested",
    "package-removed",
    "changelog-and-test-by-shell",
    "formatter-then-edit",
    "many-docs-and-docstring",
]


@pytest.mark.parametrize("name", C2_SCENARIOS)
def test_the_engine_decides_the_c2_scenarios_as_the_prototype(tmp_path, name):
    assert kit.run_scenario(tmp_path / "repo", name) == REF["scenarios"][name]


def _stop(got: dict) -> dict:
    (stop,) = got["stops"]
    return stop


def test_the_heldout3_a_shape_is_found_through_the_snapshot(tmp_path):
    stop = _stop(kit.run_scenario(tmp_path / "repo", "heredoc-rule-removed"))
    assert stop["action"] == "block" and "spec_erosion" in stop["kinds"]
    assert '  - docs/FORMAT.md:7: "Archived items must never be exported."' in stop["reason"]
    assert "`tests/test_archived.py` failed before your first edit and passes now." in stop["reason"]


@pytest.mark.parametrize(
    "name, speaks",
    [
        ("heredoc-paraphrase", False),  # marker sentences only
        ("heredoc-exception", True),  # an exception beside a kept rule
        ("no-pressure-sed", False),  # no request pressure, no pressing test: recorded only
        ("git-merge", False),  # brings in another ref: re-snapshotted
        ("git-pull", False),
        ("git-revert", False),
        ("stash-after-heredoc", True),  # stash carries the agent's own content
        ("git-apply", True),
        ("apply-after-heredoc", True),  # apply carries the agent's own content
        ("git-mv", False),  # moved: the same base name
        ("plain-mv", False),
        ("rm-and-v2", True),  # the rules left with the file
        ("rm-and-v2-requested", False),  # a requested doc change records only
        ("package-removed", False),  # the whole directory went
        ("changelog-and-test-by-shell", False),  # history and tests are out of scope
        ("formatter-then-edit", True),  # changed_before: compared against the snapshot
        ("many-docs-and-docstring", True),  # the edit-baselined docstring rule, past 450 shell-changed docs
    ],
)
def test_what_each_c2_scenario_says(tmp_path, name, speaks):
    stop = _stop(kit.run_scenario(tmp_path / "repo", name))
    assert (stop["action"] == "block") is speaks
    assert ("spec_erosion" in stop["kinds"]) is speaks


def test_a_1000_doc_git_checkout_re_snapshots_every_doc(tmp_path):
    files = {f"docs/page{n:04d}.md": f"# Page {n}\n\nEvery rule here must hold.\n" for n in range(1000)}
    files["src/a.py"] = "x = 1\n"

    def setup(repo: Path) -> None:
        kit.git(repo, "checkout", "-q", "-b", "topic")
        for n in range(1000):
            (repo / f"docs/page{n:04d}.md").write_text(f"# Page {n} (topic)\n\nEvery rule here must hold.\n")
        kit.git(repo, "commit", "-qam", "topic")
        kit.git(repo, "checkout", "-q", "main")

    def body(s: kit.Session) -> None:
        s.prompt("Bring in the topic branch.")
        t0 = time.perf_counter()
        s.shell("git checkout topic", effect=lambda: kit.git(s.repo, "checkout", "-q", "topic"))
        elapsed = time.perf_counter() - t0
        state = s.guard.workspace(s.repo).task_state(None, kit.SESSION_ID)
        snap = state.spec_snapshot
        texts = [zlib.decompress(snap.files[f"docs/page{n:04d}.md"]) for n in range(1000)]
        assert sum(b"(topic)" in t for t in texts) == 1000
        assert snap.raw_bytes == sum(snap.raw.values())
        assert elapsed < 60.0
        s.stop()

    got = kit.run_session(tmp_path / "repo", files, body, setup=setup)
    assert [s["action"] for s in got["stops"]] == ["allow"]


@pytest.mark.parametrize(
    "name, re_snapshotted",
    [
        ("git-merge", True),
        ("git-pull", True),
        ("git-revert", True),
        ("git-apply", False),
        ("stash-after-heredoc", False),
    ],
)
def test_only_a_line_bringing_in_a_ref_re_snapshots_the_doc_it_changed(
    tmp_path, monkeypatch, name, re_snapshotted
):
    """The doc is credited to the command either way; only a ref-bringing line gives the snapshot its new
    text."""
    seen: dict[str, object] = {}
    real_stop = kit.Session.stop

    def stop(self: kit.Session, *args: object, **kwargs: object) -> dict:
        state = self.guard.workspace(self.repo).task_state(None, kit.SESSION_ID)
        seen["changed"] = "docs/FORMAT.md" in state.changed_files
        seen["text"] = zlib.decompress(state.spec_snapshot.files["docs/FORMAT.md"]).decode()
        return real_stop(self, *args, **kwargs)

    monkeypatch.setattr(kit.Session, "stop", stop)
    kit.run_scenario(tmp_path / "repo", name)
    assert seen["changed"] is True
    assert (seen["text"] == kit.FORMAT_NO_ARCHIVED) is re_snapshotted
    assert (seen["text"] == kit.FORMAT_MD) is not re_snapshotted
