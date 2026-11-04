"""SPEC §7, §8 — latency budgets.

    "Deterministic check: < 100 ms target"
    "The user should not feel that AgentGuard is slowing down the coding agent."

These assertions run on every commit from here on. As real checks land in Phases 1-4, the
budget is the thing that stops them from quietly getting expensive.

Two numbers are measured, and they answer different questions:

* **in-process** — what the Guard itself costs. This is the number the engines must keep
  down as they grow.
* **end-to-end over HTTP** — what Claude Code actually experiences, including the socket
  round trip. This is the number the developer feels.

A timing is only worth its assertion if the timed call did the work (IMPROVEMENTS.md M8:
an "Edit" that extracts no claims took 0.26 ms and proved nothing). The M8 tests below
first prove the work happens on every timed call: claims extracted, a change found by the
sweep, the completion gate evaluated.
"""

from __future__ import annotations

import json
import os
import random
import shutil
import subprocess
import time
from pathlib import Path

import httpx
import pytest

from agentguard.adapters.claude_code import translate as claude
from agentguard.core.config import Settings
from agentguard.core.engine import Guard
from agentguard.core.metrics import percentile
from agentguard.evidence import extractors
from agentguard.repo.index import RepoIndex
from tests.conftest import pre_tool_use, user_prompt_submit

pytestmark = [pytest.mark.spec, pytest.mark.latency]

ITERATIONS = 200
WARMUP = 20

# SPEC §8
DETERMINISTIC_BUDGET_MS = 100.0
REPOSITORY_BUDGET_MS = 500.0

# M8(b): a whole-tree sweep of a ~2,000-file repository. Not a SPEC target but a tripwire
# for superlinear regressions, with room for slow CI runners.
#
# Set at 2,000 ms when a sweep took ~0.32-0.37 s p95. With R5's linear test map and
# one-lstat scanner, re-measured on an M2 (8 cores, 2,032 indexed files, 10 sweeps per run),
# p95 per path across runs:
#   idle (5 runs)                            41-68 ms     (p50 40-49 ms)
#   one full test suite alongside (4 runs)   50-69 ms
#   all 8 cores busy (3 runs)                75-164 ms    (worst: post-Bash)
#   16 busy loops on 8 cores (3 runs)        145-243 ms   (worst: Stop)
# Budget: about 3x the idle p95 (~70 ms -> ~210 ms), floored at 300 ms so a loaded runner
# does not flake (1.8x the 8-core-busy worst). A return to the pre-R5 cost (0.34-0.48 s)
# fails it.
LARGE_REPO_FILES = 2_000
SWEEP_P95_MEASURED_MS = 70.0
SWEEP_BUDGET_FLOOR_MS = 300.0
SWEEP_BUDGET_MS = max(3 * SWEEP_P95_MEASURED_MS, SWEEP_BUDGET_FLOOR_MS)
SWEEP_ITERATIONS = 10


def measure(fn, iterations: int = ITERATIONS, warmup: int = WARMUP) -> dict[str, float]:
    for _ in range(warmup):
        fn()
    samples = []
    for _ in range(iterations):
        start = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - start) * 1000.0)
    return {
        "p50": percentile(samples, 50),
        "p95": percentile(samples, 95),
        "p99": percentile(samples, 99),
        "max": max(samples),
        "mean": sum(samples) / len(samples),
    }


def report(label: str, stats: dict[str, float]) -> None:
    print(
        f"\n  {label:<34} p50={stats['p50']:6.2f}ms  p95={stats['p95']:6.2f}ms  "
        f"p99={stats['p99']:6.2f}ms  max={stats['max']:6.2f}ms"
    )


class TestInProcess:
    def test_read_only_tool_is_effectively_free(self, workspace):
        """SPEC §7: read-only tools never leave Level 0."""
        guard = Guard(Settings())
        event = claude.to_event(pre_tool_use("Read", cwd=str(workspace), file_path="a.py"))
        try:
            stats = measure(lambda: guard.handle(event))
        finally:
            guard.close()
        report("L0 read-only (in-process)", stats)
        assert stats["p95"] < DETERMINISTIC_BUDGET_MS

    def test_mutating_tool_within_deterministic_budget(self, workspace):
        guard = Guard(Settings())
        event = claude.to_event(
            pre_tool_use("Edit", cwd=str(workspace), file_path="a.py", old_string="x", new_string="y")
        )
        try:
            stats = measure(lambda: guard.handle(event))
        finally:
            guard.close()
        report("L0 mutating (in-process)", stats)
        assert stats["p95"] < DETERMINISTIC_BUDGET_MS

    def test_prompt_handling_within_repository_budget(self, workspace):
        """UserPromptSubmit does the heaviest Level-1 work (intent + complexity)."""
        guard = Guard(Settings())
        event = claude.to_event(
            user_prompt_submit("Add pagination to the /users endpoint", cwd=str(workspace))
        )
        try:
            stats = measure(lambda: guard.handle(event), iterations=100)
        finally:
            guard.close()
        report("L1 user prompt (in-process)", stats)
        assert stats["p95"] < REPOSITORY_BUDGET_MS

    def test_prompt_handling_against_a_real_index(self, tmp_path):
        """The measurement that matters: intent + complexity + governor over a repository
        with real symbols, imports and a real dependency graph."""
        import shutil

        from agentguard.complexity import assess
        from agentguard.intent import extract
        from agentguard.planning import render
        from agentguard.repo import RepoIndex

        dest = tmp_path / "pyrepo"
        shutil.copytree(Path(__file__).parent.parent / "fixtures" / "pyrepo", dest)
        index = RepoIndex(dest).build()

        prompts = [
            "Add pagination to /users.",
            "Make authentication horizontally scalable across multiple services.",
            "Rename get_user to fetch_user.",
        ]

        def once() -> None:
            for prompt in prompts:
                spec = extract(prompt, index)
                spec.complexity = assess(spec, index)
                render(spec, index)

        stats = measure(once, iterations=60, warmup=10)
        report("L1 full prompt path (indexed)", stats)
        assert stats["p95"] < REPOSITORY_BUDGET_MS


    def test_evidence_check_on_the_hot_path(self, tmp_path):
        """PreToolUse now parses the post-edit file and resolves its claims. That is the
        most expensive thing on the per-tool-call path, so it is the one to watch."""
        import shutil

        from agentguard import evidence
        from agentguard.core.enums import EventType
        from agentguard.core.events import AgentEvent
        from agentguard.repo import RepoIndex

        dest = tmp_path / "pyrepo"
        shutil.copytree(Path(__file__).parent.parent / "fixtures" / "pyrepo", dest)
        index = RepoIndex(dest).build()

        target = "src/shop/api/users.py"
        content = (dest / target).read_text()
        event = AgentEvent(
            event=EventType.PRE_TOOL_USE,
            agent="claude-code",
            workspace=str(dest),
            session_id="s",
            tool="Edit",
            arguments={
                "file_path": target,
                "old_string": content[:120],
                "new_string": content[:120] + "\n# touched\n",
            },
        )

        stats = measure(lambda: evidence.check(event, index), iterations=100)
        report("evidence check (indexed)", stats)
        assert stats["p95"] < DETERMINISTIC_BUDGET_MS

    def test_a_write_that_makes_claims_within_the_deterministic_budget(self, tmp_path, monkeypatch):
        """M8(a). The mutating-tool test above extracts no claims, so it times a no-op.
        This Write imports and calls repository code: every timed call, through the whole
        Guard (validator, evidence engine, store), must extract and resolve its claims."""
        dest = tmp_path / "pyrepo"
        shutil.copytree(Path(__file__).parent.parent / "fixtures" / "pyrepo", dest)
        payload = {
            **pre_tool_use("Write", cwd=str(dest)),
            "tool_input": {"file_path": str(dest / "src/shop/api/reports.py"), "content": REPORTS_MODULE},
        }
        claims, _ = extractors.claims_for_event(claude.to_event(payload), dest)
        assert len(claims) >= 10, "the timed Write must give the evidence engine real work"

        extracted: list[int] = []
        real = extractors.claims_for_event

        def counting(event, root):
            found = real(event, root)
            extracted.append(len(found[0]))
            return found

        guard = Guard(Settings())
        try:
            assert guard.workspace(dest).index.ready(timeout=30), "with no index, nothing is checked"
            guard.handle(claude.to_event(user_prompt_submit("Add a users report endpoint", cwd=str(dest))))
            monkeypatch.setattr(extractors, "claims_for_event", counting)
            events = iter([claude.to_event(payload) for _ in range(WARMUP + ITERATIONS)])
            stats = measure(lambda: guard.handle(next(events)))
        finally:
            guard.close()
        report(f"PreToolUse Write, {len(claims)} claims", stats)
        assert extracted == [len(claims)] * (WARMUP + ITERATIONS), "every timed call extracted every claim"
        assert stats["p95"] < DETERMINISTIC_BUDGET_MS


REPORTS_MODULE = '''"""Reports over users."""

from fastapi import APIRouter

from shop.models import MAX_PAGE_SIZE, User
from shop.repositories.user import UserRepository
from shop.utils.pagination import paginate

router = APIRouter()


def active_report(session, page: int = 1) -> dict:
    repo = UserRepository(session)
    users = repo.list_all(limit=MAX_PAGE_SIZE)
    names = [user.display_name() for user in users if user.is_active]
    return {"total": repo.count(), "page": paginate(names, page), "first": repo.get_by_id(1)}


def describe(user: User) -> str:
    return user.display_name()
'''


# -- M8(b): whole-tree sweeps on a ~2,000-file repository -----------------------------------


def generate_repository(dest: Path, modules: int = 1_500, tests: int = 300, other: int = 200) -> Path:
    """A synthetic Python monorepo: packages of 50 modules that import each other, tests
    that import them, docs. Committed to git when git is available, as real repositories are
    (the scanner lists a git repository through `git ls-files`)."""
    rng = random.Random(42)
    (dest / "src" / "pkg").mkdir(parents=True)
    (dest / "pyproject.toml").write_text('[project]\nname = "synth"\nversion = "0.1"\ndependencies = []\n')
    (dest / "src" / "pkg" / "__init__.py").write_text("")
    for i in range(modules):
        package = dest / "src" / "pkg" / f"g{i // 50}"
        package.mkdir(exist_ok=True)
        (package / "__init__.py").touch()
        imports = "\n".join(
            f"from pkg.g{j // 50}.m{j} import Model{j}" for j in rng.sample(range(modules), 2) if j != i
        )
        (package / f"m{i}.py").write_text(
            f'"""Module {i}."""\n{imports}\n\n\nclass Model{i}:\n    def __init__(self, v=0):\n'
            f"        self.v = v\n\n    def compute(self, x):\n        return self.v + x\n\n\n"
            f"def helper_{i}(a, b):\n    return a * b + {i}\n"
        )
    for t in range(tests):
        i = rng.randrange(modules)
        directory = dest / "tests" / f"g{t // 50}"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"test_m{t}.py").write_text(
            f"from pkg.g{i // 50}.m{i} import Model{i}\n\n\n"
            f"def test_{t}():\n    assert Model{i}(1).compute(1) == 2\n"
        )
    for k in range(other):
        directory = dest / "docs" / f"d{k // 100}"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"f{k}.md").write_text("# doc\n")
    if shutil.which("git"):
        env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
        for argv in (
            ["git", "init", "-q"],
            ["git", "add", "-A"],
            ["git", "-c", "user.name=m8", "-c", "user.email=m8@example.invalid", "commit", "-qm", "m8"],
        ):
            subprocess.run(argv, cwd=dest, env=env, check=True, capture_output=True, timeout=120)
    return dest


@pytest.fixture(scope="module")
def large_repo(tmp_path_factory) -> Path:
    return generate_repository(tmp_path_factory.mktemp("m8") / "large")


class TestSweepsOnALargeRepository:
    """Every timed sweep has a change to find, and each test checks it was found."""

    @staticmethod
    def change(repo: Path, n: int) -> str:
        """Edit one module so a sweep has exactly one file to re-parse; returns its new symbol."""
        target = repo / "src" / "pkg" / "g0" / "m0.py"
        base = target.read_text().split("\n\n\ndef marker_")[0]
        target.write_text(f"{base}\n\n\ndef marker_{n}():\n    return {n}\n")
        return f"marker_{n}"

    def timed(self, repo: Path, run, check) -> dict[str, float]:
        samples = []
        for n in range(SWEEP_ITERATIONS + 1):  # the first is warm-up
            symbol = self.change(repo, n)
            start = time.perf_counter()
            result = run()
            elapsed = (time.perf_counter() - start) * 1000.0
            check(symbol, result)
            if n:
                samples.append(elapsed)
        return {"p50": percentile(samples, 50), "p95": percentile(samples, 95),
                "p99": percentile(samples, 99), "max": max(samples)}

    def test_refresh_after_a_change(self, large_repo):
        index = RepoIndex(large_repo).build()
        assert len(index.files) >= LARGE_REPO_FILES

        def check(symbol, counts):
            assert counts == {"added": 0, "modified": 1, "removed": 0}
            assert index.has_symbol(symbol)

        stats = self.timed(large_repo, lambda: index.refresh(min_interval=0), check)
        report(f"refresh(min_interval=0), {len(index.files)} files", stats)
        assert stats["p95"] < SWEEP_BUDGET_MS

    @pytest.fixture
    def guarded(self, large_repo):
        """A Guard on the large repository, inside a task that has edited a module."""
        guard = Guard(Settings())
        ws = guard.workspace(large_repo)
        assert ws.index.ready(timeout=120) and len(ws.index.files) >= LARGE_REPO_FILES
        cwd = str(large_repo)
        guard.handle(claude.to_event(user_prompt_submit("Add a marker to pkg.g0.m0", cwd=cwd)))
        edited = str(large_repo / "src" / "pkg" / "g0" / "m0.py")
        edit = {
            **pre_tool_use("Edit", cwd=cwd, file_path=edited, old_string="x", new_string="y"),
            "hook_event_name": "PostToolUse",
            "tool_response": {"filePath": edited},
        }
        guard.handle(claude.to_event(edit))
        yield guard, ws
        guard.close()

    def test_the_post_bash_sweep(self, guarded, large_repo):
        guard, ws = guarded
        bash = {
            **pre_tool_use("Bash", cwd=str(large_repo), command="make build"),
            "hook_event_name": "PostToolUse",
            "tool_response": {"stdout": "ok", "stderr": "", "interrupted": False},
        }

        def run():
            ws.index.last_refresh = 0.0  # past the 2 s rate limit: the sweep must run
            return guard.handle(claude.to_event(bash))

        def check(symbol, decision):
            assert ws.index.has_symbol(symbol), "the sweep found the change"

        stats = self.timed(large_repo, run, check)
        report("post-Bash sweep (Guard.handle)", stats)
        assert stats["p95"] < SWEEP_BUDGET_MS

    def test_the_stop_path(self, guarded, large_repo):
        guard, ws = guarded
        stop = {
            "session_id": "sess-1",
            "cwd": str(large_repo),
            "hook_event_name": "Stop",
            "last_assistant_message": "Done.",
            "stop_hook_active": False,
        }

        def run():
            ws.index.last_refresh = 0.0  # past the 5 s rate limit: Stop sweeps, then judges
            return guard.handle(claude.to_event(stop))

        def check(symbol, decision):
            assert ws.index.has_symbol(symbol), "the Stop sweep found the change"
            assert decision.findings, "the completion gate evaluated the task"

        stats = self.timed(large_repo, run, check)
        report("Stop (sweep + completion gate)", stats)
        assert stats["p95"] < SWEEP_BUDGET_MS


class TestEndToEnd:
    def test_http_hook_round_trip_within_budget(self, daemon, workspace):
        """What Claude Code actually pays per tool call.

        The `http` hook type is what makes this affordable: there is no Python process
        spawn here, only a localhost round trip.
        """
        url = f"{daemon.url}/hook/claude-code"
        headers = {"Authorization": f"Bearer {daemon.token}", "Content-Type": "application/json"}
        payload = json.dumps(
            pre_tool_use("Edit", cwd=str(workspace), file_path="a.py", old_string="x", new_string="y")
        )

        with httpx.Client(timeout=5.0) as client:
            stats = measure(lambda: client.post(url, content=payload, headers=headers), iterations=100)

        report("end-to-end over HTTP", stats)
        assert stats["p95"] < DETERMINISTIC_BUDGET_MS, (
            f"hot path p95 {stats['p95']:.1f}ms exceeds the SPEC §8 budget of "
            f"{DETERMINISTIC_BUDGET_MS}ms"
        )

    @pytest.mark.slow
    def test_command_shim_cost_is_measured_and_understood(self, daemon, workspace):
        """The fallback transport, measured so the choice of `http` stays justified.

        This is expected to be *over* budget — it pays Python interpreter startup per
        call. That is precisely why it is the fallback and not the default. The test
        records the number rather than asserting a budget it cannot meet.
        """
        import os
        import subprocess
        import sys

        from tests.conftest import REPO_ROOT

        env = dict(os.environ, AGENTGUARD_HOME=str(daemon.home), PYTHONPATH=str(REPO_ROOT / "src"))
        payload = json.dumps(pre_tool_use("Edit", cwd=str(workspace))).encode()

        def run_once():
            subprocess.run(
                [sys.executable, "-m", "agentguard.adapters.claude_code.shim"],
                input=payload,
                capture_output=True,
                env=env,
                timeout=30,
            )

        stats = measure(run_once, iterations=15, warmup=3)
        report("command shim (fallback)", stats)
        # Only a sanity ceiling: if even the fallback took seconds, something is wrong.
        assert stats["p95"] < 2000.0
