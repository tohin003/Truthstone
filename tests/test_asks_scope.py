"""A4: scope never denies a test run; proportionality is recorded only (IMPROVEMENTS.md A4).

`scope_creep` ran on every non-read-only PreToolUse, Bash included, so once a task had
drifted the deny landed on whatever came next — usually the agent's own `pytest` (probe
S1, D2 S1, D4a, D1). Docs and manifests counted as drift, so a docs typo sweep and a
monorepo dependency bump were denied at file 9. And the DIRECT-band proportionality
challenge would have fired on 20 of 69 real turns that edited 8 or more files.

Now: a Bash command that only reads or runs tests is allowed after the risk checks;
scope is judged only on edits that write a file, counting only source files; and
proportionality is recorded for the census, never said to the agent.
"""

from __future__ import annotations

import pytest

from tests.test_asks_support import Session, make_guard, make_repo, permission
from truthstone.core.enums import DecisionAction, FailureMode, Severity
from truthstone.core.enums import EventType as ET
from truthstone.core.events import AgentEvent
from truthstone.validate import checks


@pytest.fixture
def session(tmp_path):
    repo = make_repo(tmp_path)
    guard = make_guard(repo)
    yield Session(guard, repo)
    guard.close()


def drift(session: Session, paths: list[str]) -> None:
    """The agent edits these files (PostToolUse is what records a touched file)."""
    for path in paths:
        session.post("Edit", file_path=path, old_string="a", new_string="b")


UNRELATED = [f"src/shop/unrelated_{i}.py" for i in range(17)]


class TestScopeIsJudgedOnWritesOnly:
    @pytest.mark.parametrize(
        "command",
        [
            "pytest -q",
            "python -m pytest tests/test_pagination.py -x",
            "cd . && pytest -q 2>&1 | tail -20",
            "npm test",
            "git status && git diff --stat",
            "TRUTHSTONE_X=1 timeout 60 pytest -q",
        ],
    )
    def test_scope_challenge_never_lands_on_a_test_run(self, session, command):
        session.prompt("Fix the get_user validation bug.")
        drift(session, UNRELATED)

        decision = session.pre("Bash", command=command)
        assert decision.action is DecisionAction.ALLOW, decision.reason
        assert session.claude("Bash", command=command) == {}
        assert session.codex_bash(command) == {}

        # Writes still are: the next unrelated edit hears about the drift.
        edit = session.pre("Edit", file_path="src/shop/models.py", old_string="x", new_string="y")
        assert edit.action is DecisionAction.CHALLENGE
        assert any(f.failure_mode is FailureMode.UNRELATED_FILES_MODIFIED for f in edit.findings)

    def test_a_mutating_bash_command_is_not_scope_challenged_either(self, session):
        """Scope is about the files a task writes; the edits are where it is judged."""
        session.prompt("Fix the get_user validation bug.")
        drift(session, UNRELATED)
        decision = session.pre("Bash", command="mkdir -p build && touch build/marker")
        assert not any(f.category.value == "scope" for f in decision.findings)
        assert decision.action is DecisionAction.ALLOW


class TestReadOnlyBash:
    def test_read_only_bash_skips_evidence(self, session):
        session.prompt("Document how the shop client is installed.")
        command = 'grep -rn "npm install lodash" docs/'
        decision = session.pre("Bash", command=command)
        assert decision.is_silent, decision.reason
        assert session.claude("Bash", command=command) == {}

        # A real install is still checked.
        install = session.pre("Bash", command="npm install lodash")
        assert install.action is DecisionAction.CHALLENGE
        assert any(f.subject == "lodash" for f in install.findings)

    @pytest.mark.parametrize(
        "command",
        [
            "ls -la src",
            "cat src/shop/models.py | head -20",
            'grep -rn "DROP TABLE" migrations/ 2>/dev/null',
            "rg -n get_user src/",
            "find . -name '*.py' -type f",
            "wc -l src/shop/*.py",
            "git log --oneline -5",
            "git -C src --no-pager diff HEAD~1",
            "git show HEAD:src/shop/models.py",
            "git rev-parse --abbrev-ref HEAD",
            "git branch",
            "git branch -a --list 'feat*'",
            "pwd",
            "which python3",
            'echo "done"',
            "printf '%s\\n' a b",
            "FOO=1 env BAR=2 nohup pytest -q",
            "timeout 30 cargo test",
            "uv run pytest -q",
            "npx vitest run",
            "pnpm --filter web test",
            "go test ./...",
            "make test",
            "node --test",
        ],
    )
    def test_read_only_commands(self, command):
        assert checks.read_only_bash(bash(command)), command

    @pytest.mark.parametrize(
        "command",
        [
            "echo hi > notes.txt",
            "cat a >> b",
            "ls | tee listing.txt",
            "find . -name '*.orig' -delete",
            "find . -exec rm {} +",
            "git branch new-feature",
            "git branch -D old",
            "git diff --output=patch.diff",
            "git -c core.pager=less log",
            "git push",
            "git commit -m 'x'",
            "rg --pre ./decode.sh secret",
            "sudo ls /root",
            "pytest -q; rm -rf build",
            "echo $(rm -rf build)",
            "mvn deploy test",
            "npm install lodash",
            "python script.py",
            "ls 'unclosed",
            "for f in *; do cat $f; done",
        ],
    )
    def test_anything_else_is_checked(self, command):
        assert not checks.read_only_bash(bash(command)), command


class TestProportionality:
    def test_proportionality_is_recorded_not_raised(self, session):
        session.prompt("Update the copyright year in the file headers to 2026.")
        assert session.workspace.task_state(None, session.session_id).spec.complexity.depth.value == "direct"
        files = [f"src/shop/header_{i}.py" for i in range(12)]
        drift(session, files[:8])

        crossing = session.pre("Edit", file_path=files[8], old_string="a", new_string="b")
        assert crossing.action is DecisionAction.ALLOW
        recorded = [f for f in crossing.findings if f.subject == "proportionality"]
        assert recorded and recorded[0].severity is Severity.INFO
        assert recorded[0].failure_mode is FailureMode.OVERPLANNED_TRIVIAL
        assert permission(session.claude("Edit", file_path=files[8], old_string="a", new_string="b")) is None

        # Recorded once: the edit that crosses the line, not every edit after it.
        drift(session, files[8:10])
        later = session.pre("Edit", file_path=files[10], old_string="a", new_string="b")
        assert not any(f.subject == "proportionality" for f in later.findings)


class TestOnlySourceCounts:
    def test_docs_and_manifests_do_not_count_toward_scope(self, session):
        session.prompt("Fix the get_user validation bug.")
        drift(
            session,
            [f"docs/guide_{i}.md" for i in range(10)]
            + ["package.json", "pyproject.toml", "requirements.txt", "config/app.yaml", "data.json"],
        )
        decision = session.pre("Edit", file_path="src/shop/api/users.py", old_string="a", new_string="b")
        assert not any(f.category.value == "scope" for f in decision.findings)

        # Source drift still counts.
        drift(session, UNRELATED[:5])
        decision = session.pre("Edit", file_path="src/shop/models.py", old_string="a", new_string="b")
        assert any(f.failure_mode is FailureMode.UNRELATED_FILES_MODIFIED for f in decision.findings)

    def test_docs_do_not_count_toward_proportionality(self, session):
        session.prompt("Update the copyright year in the file headers to 2026.")
        drift(session, [f"docs/page_{i}.md" for i in range(12)])
        decision = session.pre("Edit", file_path="docs/page_12.md", old_string="a", new_string="b")
        assert not any(f.subject == "proportionality" for f in decision.findings)

    @pytest.mark.parametrize(
        ("path", "counts"),
        [
            ("src/app.py", True),
            ("web/src/App.tsx", True),
            ("scripts/deploy.sh", True),
            ("README.md", False),
            ("docs/index.md", False),
            ("package.json", False),
            ("pyproject.toml", False),
            ("requirements-dev.txt", False),
            ("go.mod", False),
            ("Cargo.toml", False),
            (".github/workflows/ci.yml", False),
            ("uv.lock", False),
        ],
    )
    def test_what_counts_as_source(self, path, counts):
        assert checks.counts_toward_scope(path) is counts


def bash(command: str) -> AgentEvent:
    return AgentEvent(event=ET.PRE_TOOL_USE, tool="Bash", arguments={"command": command})
