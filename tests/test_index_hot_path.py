"""The index's hot path stays cheap and gives the same answers (R5).

`refresh_path()` runs after every changing Edit/Write and rebuilds the derived maps;
`scanner.scan()` runs on every post-Bash sweep and at Stop. Both used to cost
O(tests x files) and ~20 syscalls per file respectively: 126 ms per edit on a real
1,410-file repository and 2.6 s on a 42k-file monorepo, inside the event lock.

Each optimisation here is checked against a reference copy of the algorithm it
replaced, kept verbatim in this file, so "faster" can never quietly mean "different".
"""

from __future__ import annotations

import os
import subprocess
import time
from collections import Counter, defaultdict
from pathlib import Path

import pytest

from truthstone.core.config import IndexSettings
from truthstone.repo import RepoIndex, scanner
from truthstone.repo.index import ParsedFile
from truthstone.repo.models import FileRecord, ImportRecord
from truthstone.repo.paths import relative_path

# -- reference implementations of the replaced algorithms ---------------------------------


def _reference_test_map(index: RepoIndex) -> dict[str, set[str]]:
    """The pre-R5 test map, verbatim: every test file rescans every file."""
    out: dict[str, set[str]] = defaultdict(set)
    for path, record in index.files.items():
        if not record.is_test:
            continue
        for imported in index.parsed.get(path, ParsedFile()).imports:
            if imported.resolved and not index.files[imported.resolved].is_test:
                out[imported.resolved].add(path)
        name = path.rsplit("/", 1)[-1]
        stem = name
        for prefix in ("test_",):
            stem = stem.removeprefix(prefix)
        for suffix in ("_test.py", ".test.ts", ".test.tsx", ".test.js", ".spec.ts", ".spec.js", "_test.go"):
            if stem.endswith(suffix):
                stem = stem[: -len(suffix)]
                break
        else:
            stem = stem.rsplit(".", 1)[0]
        if not stem:
            continue
        for other, other_record in index.files.items():
            if not other_record.is_test and other.rsplit("/", 1)[-1].rsplit(".", 1)[0] == stem:
                out[other].add(path)
    return out


def _reference_scan(root: Path, settings: IndexSettings | None = None) -> dict[str, FileRecord]:
    """The pre-R5 scanner loop, verbatim: a full resolve, a stat and an isfile per file."""
    settings = settings or IndexSettings()
    root = root.resolve()
    paths = scanner._git_listed_files(root)
    from_git = paths is not None
    if paths is None:
        paths = scanner._walked_files(root, settings)
    excluded = set(settings.exclude_dirs)
    records: dict[str, FileRecord] = {}
    for rel in paths:
        rel = rel.replace(os.sep, "/")
        parts = rel.split("/")
        if from_git and any(part in excluded for part in parts[:-1]):
            continue
        if relative_path(root, rel) is None:
            continue
        full = root / rel
        try:
            st = full.stat()
        except OSError:
            continue
        try:
            if not full.resolve(strict=False).is_relative_to(root):
                continue
        except (OSError, RuntimeError):
            continue
        if not os.path.isfile(full):
            continue
        if st.st_size > settings.max_file_bytes:
            continue
        records[rel] = FileRecord(
            path=rel,
            size=st.st_size,
            mtime_ns=st.st_mtime_ns,
            lang=scanner.detect_language(rel),
            is_test=scanner.is_test_path(rel),
            is_config=scanner.is_config_path(rel),
        )
        if len(records) >= settings.max_files:
            break
    return records


# -- helpers --------------------------------------------------------------------------------

# Names chosen to exercise every branch of the naming convention: each suffix, the
# `test_` prefix, an empty stem, dotted stems, extensionless files, a test directory
# without a test_ prefix, and stems shared by several sources in different places.
_EDGE_FILES: tuple[str, ...] = (
    "src/user.py", "lib/user.ts", "tests/test_user.py",
    "src/api/users.ts", "src/api/users.test.ts", "src/api/users.test.tsx",
    "pkg/handler.go", "pkg/handler_test.go",
    "web/button.js", "web/button.spec.js", "web/button.spec.ts",
    "tests/test_.py", "tests/conftest.py", "tests/helpers.py", "src/helpers.py",
    "src/a.b.c.py", "tests/test_a.b.c.py", "Makefile", "tests/test_Makefile",
    "src/.hidden.py", "tests/test_.hidden.py", "src/widget.jsx", "src/widget.test.jsx",
    "e2e/flow.py", "src/flow.py", "src/flow.rs",
)


def _record(path: str) -> FileRecord:
    return FileRecord(
        path=path,
        size=1,
        mtime_ns=1,
        lang=scanner.detect_language(path),
        is_test=scanner.is_test_path(path),
        is_config=scanner.is_config_path(path),
    )


def _synthetic_index(root: Path, n_files: int, n_tests: int) -> RepoIndex:
    """An in-memory index of `n_files` files, `n_tests` of them tests that import a module.

    Built without touching the disk so the test measures the algorithm, not the filesystem.
    """
    index = RepoIndex(root)
    files: dict[str, FileRecord] = {}
    parsed: dict[str, ParsedFile] = {}
    for path in _EDGE_FILES:
        files[path] = _record(path)
        parsed[path] = ParsedFile(parsed=True)
    n_modules = max(1, (n_files - len(files) - n_tests) // 2)
    for i in range(n_modules):
        path = f"src/pkg/g{i // 50}/m{i}.py"
        files[path] = _record(path)
        parsed[path] = ParsedFile(parsed=True)
    for i in range(n_files - len(files) - n_tests):
        path = f"assets/d{i // 500}/f{i}.svg"
        files[path] = _record(path)
    for t in range(n_tests):
        target = (t * 7) % n_modules
        # Half the tests are named after the module they import, so both mapping rules fire.
        path = f"tests/g{t // 50}/test_m{target if t % 2 else t}.py"
        files[path] = _record(path)
        parsed[path] = ParsedFile(
            imports=[ImportRecord(raw=f"pkg.g{target // 50}.m{target}", names=[f"Model{target}"])],
            parsed=True,
        )
    index.files = files
    index.parsed = parsed
    index._rebuild_derived()
    return index


def _best_ms(fn, repeats: int = 5) -> float:
    best = float("inf")
    for _ in range(repeats):
        start = time.perf_counter()
        fn()
        best = min(best, (time.perf_counter() - start) * 1000)
    return best


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "-c", "commit.gpgsign=false", *args],
        cwd=root,
        check=True,
        capture_output=True,
    )


def _symlink(link: Path, target: Path, *, directory: bool = False) -> None:
    try:
        link.symlink_to(target, target_is_directory=directory)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlinks unavailable: {exc}")


# -- the test map ---------------------------------------------------------------------------


def test_test_map_is_linear_and_equivalent(tmp_path):
    small = _synthetic_index(tmp_path, n_files=2_500, n_tests=38)
    large = _synthetic_index(tmp_path, n_files=20_000, n_tests=300)

    # Identical to the replaced algorithm, edge-case names included.
    for index in (small, large):
        expected = {k: v for k, v in _reference_test_map(index).items() if v}
        actual = {k: set(v) for k, v in index.tests_by_source.items() if v}
        assert actual == expected
    assert large.tests_for("src/user.py") == {"tests/test_user.py"}
    assert large.tests_for("lib/user.ts") == {"tests/test_user.py"}
    assert large.tests_for("src/api/users.ts") == {"src/api/users.test.ts", "src/api/users.test.tsx"}
    assert large.tests_for("pkg/handler.go") == {"pkg/handler_test.go"}
    assert large.tests_for("src/helpers.py") == {"tests/helpers.py"}
    assert large.tests_for("Makefile") == {"tests/test_Makefile"}
    assert large.tests_for("src/flow.rs") == {"e2e/flow.py"}

    # Linear, not O(tests x files): 8x the files and 8x the tests cost about 8x, where
    # the old algorithm cost 64x (and took seconds at the large size).
    small_ms = _best_ms(small._rebuild_derived)
    large_ms = _best_ms(large._rebuild_derived)
    print(f"\n  _rebuild_derived: 2.5k files {small_ms:.1f} ms, 20k files/300 tests {large_ms:.1f} ms")
    assert large_ms < 500.0, f"rebuild of 20k files took {large_ms:.0f} ms"
    assert large_ms / max(small_ms, 1.0) < 24.0, (small_ms, large_ms)


def test_test_map_follows_refresh_path(tmp_path):
    """The stem dictionary is rebuilt with the map, so a new source is matched at once."""
    root = tmp_path / "repo"
    (root / "tests").mkdir(parents=True)
    (root / "src").mkdir()
    (root / "tests" / "test_billing.py").write_text("def test_x():\n    pass\n")
    index = RepoIndex(root).build()
    assert index.tests_for("src/billing.py") == set()

    (root / "src" / "billing.py").write_text("def charge():\n    return 1\n")
    assert index.refresh_path("src/billing.py") is True
    assert index.tests_for("src/billing.py") == {"tests/test_billing.py"}

    (root / "src" / "billing.py").unlink()
    assert index.refresh_path("src/billing.py") is True
    assert index.tests_for("src/billing.py") == set()


# -- the scanner ----------------------------------------------------------------------------


@pytest.mark.parametrize("use_git", [False, True], ids=["walk", "git"])
def test_scan_stats_once_and_still_rejects_symlink_escape(tmp_path, monkeypatch, use_git):
    root = (tmp_path / "repo").resolve()
    (root / "src" / "pkg").mkdir(parents=True)
    plain = []
    for i in range(30):
        path = root / "src" / "pkg" / f"m{i}.py"
        path.write_text(f"X{i} = {i}\n")
        plain.append(path)
    (root / "swapped").mkdir()
    (root / "swapped" / "mod.py").write_text("SWAPPED = 1\n")
    (root / "kept").mkdir()
    (root / "kept" / "m0.py").write_text("X0 = 0\n")

    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.py").write_text("TOKEN = 'x'\n")
    (outside / "mod.py").write_text("TOKEN = 'y'\n")

    _symlink(root / "escape.py", outside / "secret.py")
    _symlink(root / "alias.py", root / "src" / "pkg" / "m0.py")
    _symlink(root / "outdir", outside, directory=True)
    if use_git:
        _git(root, "init", "-q")
        _git(root, "add", "-A")
        _git(root, "commit", "-qm", "init")
    # `git ls-files --cached` keeps listing swapped/mod.py and kept/m0.py after their
    # directories become symlinks: one now leads outside, one back inside.
    for name, target in (("swapped", outside), ("kept", root / "src" / "pkg")):
        for child in (root / name).iterdir():
            child.unlink()
        (root / name).rmdir()
        _symlink(root / name, target, directory=True)

    calls: Counter[str] = Counter()

    def counting(real):
        def wrapper(path, *args, **kwargs):
            if not isinstance(path, int):
                calls[os.fspath(path)] += 1
            return real(path, *args, **kwargs)

        return wrapper

    # A scoped patch: undoing the whole fixture would also drop the isolated TRUTHSTONE_HOME.
    with monkeypatch.context() as patch:
        patch.setattr(os, "lstat", counting(os.lstat))
        patch.setattr(os, "stat", counting(os.stat))
        records = scanner.scan(root)

    # One stat-family call per ordinary file, where there used to be ~20. (m0.py is the
    # target of two links, so resolving those links legitimately touches it again.)
    ordinary = plain[1:]
    assert all(calls[str(path)] == 1 for path in ordinary), {
        str(p.relative_to(root)): calls[str(p)] for p in ordinary if calls[str(p)] != 1
    }
    assert {f"src/pkg/m{i}.py" for i in range(30)} <= set(records)

    # Containment is not weakened: nothing outside the root, by any route.
    assert "escape.py" not in records
    assert not any(path.startswith("outdir") for path in records)
    assert not any(path.startswith("swapped") for path in records)
    # A link that stays inside keeps its own repository spelling.
    assert "alias.py" in records
    assert records["alias.py"].size == (root / "src" / "pkg" / "m0.py").stat().st_size
    # And the whole result is exactly what the replaced per-file resolve produced.
    assert records == _reference_scan(root)
    if use_git:
        assert "kept/m0.py" in records  # a stale listing through an inside link survives


def test_scan_rejects_unsafe_listings_lexically(tmp_path, monkeypatch):
    """`..`, absolute, empty-component and NUL paths never reach the filesystem."""
    root = (tmp_path / "repo").resolve()
    (root / "src").mkdir(parents=True)
    (root / "src" / "a.py").write_text("A = 1\n")
    (tmp_path / "secret.py").write_text("TOKEN = 1\n")
    hostile = [
        "src/a.py",
        "../secret.py",
        "src/../../secret.py",
        str(tmp_path / "secret.py"),
        "src//a.py",
        "./src/a.py",
        "src/a\0.py",
    ]
    monkeypatch.setattr(scanner, "_git_listed_files", lambda _root: list(hostile))

    assert set(scanner.scan(root)) == {"src/a.py"}
