"""G3a: a test run is recognised by command position, never by substring.

Two failures motivated this, in opposite directions (docs/IMPROVEMENTS.md G3a, probe D):

* commands that merely *mention* a runner were counted as runs — 12 of 15 in D2's
  sample (`cat pytest.ini`, `pip install pytest`, `grep -rn pytest …`), each one
  silencing the gate's "no tests were run";
* real runners were missed — `node --test` alone appears 128 times in the local
  transcripts, and `make test`, `tox`, `./gradlew test` were unknown.

The corpus below is the D2 matrix's command list plus the shell shapes that decide whose
exit status a command returns (G1).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from truthstone.core.config import Settings
from truthstone.core.engine import Guard
from truthstone.core.enums import DecisionAction, EventType
from truthstone.core.events import AgentEvent
from truthstone.verify import commands, runners

FIXTURES = Path(__file__).parent / "fixtures"


RUNS = [
    # (command, runner, family)
    ("pytest -q", "pytest", "python"),
    ("py.test tests/", "pytest", "python"),
    ("python -m pytest", "pytest", "python"),
    ("python3 -I -B -X dev -W error -m pytest -q", "pytest", "python"),
    ("py -3.12 -m pytest", "pytest", "python"),
    (".venv/bin/python -m pytest", "pytest", "python"),
    ("uv run pytest -q", "pytest", "python"),
    ("uv run --frozen --with pytest-xdist pytest -n auto", "pytest", "python"),
    ("uv run -m pytest", "pytest", "python"),
    ("poetry run pytest", "pytest", "python"),
    ("pdm run pytest", "pytest", "python"),
    ("hatch run pytest", "pytest", "python"),
    ("coverage run -m pytest", "pytest", "python"),
    ("python -m coverage run --source=src -m pytest", "pytest", "python"),
    ("python -m unittest", "unittest", "python"),
    ("python -m unittest discover -s tests", "unittest", "python"),
    ("python tests/test_app.py", "unittest", "python"),
    ("python manage.py test", "django", "python"),
    ("tox", "tox", "python"),
    ("tox -e py312", "tox", "python"),
    ("tox run -e py312,py313", "tox", "python"),
    ("nox -s tests", "nox", "python"),
    ("hatch test", "hatch", "python"),
    ("pdm run test", "script", "python"),
    ("npx jest", "jest", "js"),
    ("npx --yes jest --ci", "jest", "js"),
    ("./node_modules/.bin/jest", "jest", "js"),
    ("npx vitest run", "vitest", "js"),
    ("pnpm exec vitest run", "vitest", "js"),
    ("pnpm vitest", "vitest", "js"),
    ("yarn jest", "jest", "js"),
    ("bunx vitest", "vitest", "js"),
    ("npm exec -- jest", "jest", "js"),
    ("npx mocha", "mocha", "js"),
    ("node --test", "node", "js"),
    ("node --test test/", "node", "js"),
    ("npm test", "npm", "js"),
    ("npm t", "npm", "js"),
    ("npm run test", "npm", "js"),
    ("npm run test:unit", "npm", "js"),
    ("npm -w api test", "npm", "js"),
    ("npm --workspace=api test", "npm", "js"),
    ("pnpm test", "npm", "js"),
    ("pnpm --filter api test", "npm", "js"),
    ("pnpm -r test", "npm", "js"),
    ("yarn test", "npm", "js"),
    ("yarn run test", "npm", "js"),
    ("yarn workspace api test", "npm", "js"),
    ("bun run test", "npm", "js"),
    ("node --run test", "npm", "js"),
    ("npx turbo run test", "npm", "js"),
    ("nx run-many -t test", "npm", "js"),
    ("bun test", "bun", "js"),
    ("deno test", "deno", "js"),
    ("npx playwright test", "playwright", "playwright"),
    ("go test ./...", "go", "go"),
    ("go test -v -run TestAdd ./calc", "go", "go"),
    ("cargo test", "cargo", "rust"),
    ("cargo +nightly test --workspace", "cargo", "rust"),
    ("cargo nextest run", "nextest", "rust"),
    ("make test", "make", "make"),
    ("make -C api test", "make", "make"),
    ("make check", "make", "make"),
    ("make test-fail", "make", "make"),
    ("just test", "just", "just"),
    ("gradle test", "gradle", "jvm"),
    ("./gradlew test", "gradle", "jvm"),
    ("./gradlew :app:testDebugUnitTest", "gradle", "jvm"),
    ("mvn test", "maven", "jvm"),
    ("./mvnw -q verify", "maven", "jvm"),
    ("rspec", "rspec", "ruby"),
    ("bundle exec rspec spec/models", "rspec", "ruby"),
    ("bin/rails test", "rails", "ruby"),
    ("bundle exec rake test", "rails", "ruby"),
    ("ruby -Itest test/models/user_test.rb", "minitest", "ruby"),
    ("vendor/bin/phpunit", "phpunit", "php"),
    ("php artisan test", "phpunit", "php"),
    ("dotnet test", "dotnet", "dotnet"),
    ("swift test", "swift", "swift"),
    ("mix test", "mix", "elixir"),
    # shell plumbing in front of the runner
    ("cd backend && pytest -q", "pytest", "python"),
    ("FOO=1 BAR=2 pytest -x", "pytest", "python"),
    ("env -u CI DEBUG=1 pytest", "pytest", "python"),
    ("timeout 600 pytest -q", "pytest", "python"),
    ("timeout -s KILL 10m npm test", "npm", "js"),
    ("time pytest", "pytest", "python"),
    ("nice -n 10 go test ./...", "go", "go"),
    ("sudo -u ci pytest", "pytest", "python"),
    ("(cd sub && pytest)", "pytest", "python"),
    ("bash -lc 'cd api && pytest -q'", "pytest", "python"),
    ("if pytest; then echo ok; fi", "pytest", "python"),
    ("pytest -q 2>&1 | tail -20", "pytest", "python"),
]

NOT_RUNS = [
    # mentions of a runner (D2: 12 of 15 were counted)
    "grep -n pytest pyproject.toml",
    "grep -rn pytest .",
    "rg -n unittest src/",
    "cat pytest.ini",
    "ls tests",
    "vim tests/test_x.py",
    "pip install pytest",
    "uv add --dev pytest",
    "npm install --save-dev jest",
    'echo "run pytest"',
    "which pytest",
    "command -v pytest",
    'git commit -m "Fix flaky jest config"',
    "python -c 'import pytest'",
    "python manage.py runserver",
    "go vet ./...",
    "go build ./...",
    "cargo build",
    "npm run build",
    "npm run lint",
    "npx turbo run build",
    "make build",
    "tox -e lint",
    "nox -s docs",
    # runs that run nothing
    "pytest --collect-only",
    "pytest --co -q",
    "pytest --version",
    "pytest -h",
    "pytest --fixtures",
    "jest --listTests",
    "go test -list .",
    "cargo test --no-run",
    "cargo nextest list",
    "mvn test -DskipTests",
    "dotnet test --list-tests",
    "tox -l",
    # never finishes on its own
    "npx jest --watch",
    "npx jest --watchAll",
    "npx vitest watch",
    "npm run test:watch",
    "npm test -- --watch",
    "node --test --watch",
    "mocha -w",
    # quoted, substituted, heredoc or commented text is not a command
    "cat > run.sh <<'EOF'\npytest -q\nEOF\nchmod +x run.sh",
    "# pytest\nls",
    "echo $(pytest)",
    "x=$(pytest -q)",
]


class TestRecognition:
    @pytest.mark.parametrize(("command", "runner", "family"), RUNS)
    def test_runs_are_recognised(self, command, runner, family):
        invocation = commands.test_invocation(command)
        assert invocation is not None, command
        assert (invocation.runner, invocation.family) == (runner, family)
        assert runners.is_test_command(command)
        assert runners.runner_for_command(command) == runner

    @pytest.mark.parametrize("command", NOT_RUNS)
    def test_non_runs_are_not(self, command):
        assert commands.test_invocation(command) is None, command
        assert not runners.is_test_command(command)
        assert runners.runner_for_command(command) == "unknown"


class TestExitOwnership:
    """Whose exit status the command returns decides whether it can be trusted (G1)."""

    @pytest.mark.parametrize(
        ("command", "reliable"),
        [
            ("pytest -q", True),
            ("cd x && pytest -q", True),
            ("pytest -q && echo done", True),
            ("(cd x && pytest)", True),
            ("pytest -q | tail -5", False),
            ("pytest -q 2>&1 | tail -5", False),
            ("pytest -q; true", False),
            ("pytest -q || true", False),
            ("pytest -q || echo failed", False),
            ("(pytest) | tail", False),
            ("! pytest", False),
            ("set -o pipefail; pytest -q | tail -5", True),
            ("set -euo pipefail\npytest -q | tee log.txt", True),
            ("set -o pipefail; pytest -q | grep passed", False),
            ("bash -c 'pytest -q | tail'", False),
            ("bash -c 'pytest -q' | tail", False),
            ("pytest -q > out.txt 2>&1", True),
        ],
    )
    def test_exit_reliability(self, command, reliable):
        invocation = commands.test_invocation(command)
        assert invocation is not None
        assert invocation.exit_reliable is reliable

    @pytest.mark.parametrize("command", ["pytest &", "nohup pytest > log 2>&1 &", "pytest -q & sleep 1"])
    def test_a_background_launch_is_flagged(self, command):
        invocation = commands.test_invocations(command)[0]
        assert invocation.background
        assert not invocation.exit_reliable


class TestSelectors:
    @pytest.mark.parametrize(
        ("command", "selectors"),
        [
            ("pytest", ()),
            ("pytest -q tests/", ()),
            ("pytest -p no:cacheprovider -q", ()),
            ("pytest tests/test_x.py::test_y", ("tests/test_x.py::test_y",)),
            ("pytest --lf", ("--lf",)),
            ("pytest -k 'not slow' tests/unit", ("-k=not slow", "tests/unit")),
            ("python -m unittest discover -s tests -p 'test_*.py'", ()),
            ("python -m unittest tests.test_x", ("tests.test_x",)),
            ("go test ./...", ()),
            ("go test", (".",)),
            ("go test -run TestFoo ./pkg/x", ("-run=TestFoo", "pkg/x")),
            ("cargo test my_test -- --exact", ("--exact", "my_test")),
            ("npx jest src/a.test.ts", ("src/a.test.ts",)),
            ("npm test -- src/a.test.ts", ("src/a.test.ts",)),
            ("pnpm --filter api test", ("--filter=api",)),
            ("make test", ()),
            ("./gradlew test --tests '*Foo*'", ("--tests=*Foo*",)),
        ],
    )
    def test_what_narrows_a_run(self, command, selectors):
        assert commands.test_invocation(command).selectors == selectors


class TestSplitter:
    def test_quotes_and_operators(self):
        parts = commands.split("cd x && pytest -q 2>&1 | tail -20")
        assert [(p.words, p.sep) for p in parts] == [
            (("cd", "x"), "&&"),
            (("pytest", "-q"), "|"),
            (("tail", "-20"), ""),
        ]

    def test_quoted_operators_are_text(self):
        parts = commands.split("echo 'a && b' \"c | d\"; ls")
        assert [p.words for p in parts] == [("echo", "a && b", "c | d"), ("ls",)]

    def test_heredoc_bodies_and_comments_are_skipped(self):
        parts = commands.split("cat <<-EOF > f\n\tpytest -q\n\tEOF\nls # pytest\nwc -l f")
        assert [p.words[0] for p in parts] == ["cat", "ls", "wc"]

    def test_never_raises_on_garbage(self):
        for text in ("'unterminated", '"unterminated', "$(", "<<", "a |", "&& ||", "\\", "x" * 70_000):
            commands.split(text)
            commands.test_invocations(text)


class TestTypecheck:
    @pytest.mark.parametrize(
        ("command", "found"),
        [
            ("npx tsc --noEmit", True),
            ("mypy src", True),
            ("npm run typecheck", True),
            ("cargo check", True),
            ("tsc -w", False),
            ("tsc --watch", False),
            ("cat tsconfig.json", False),
        ],
    )
    def test_typecheck_runs(self, command, found):
        assert (commands.typecheck_invocation(command) is not None) is found


# -- through the real Guard ------------------------------------------------------------------


@pytest.fixture
def repo(tmp_path) -> Path:
    dest = tmp_path / "pyrepo"
    shutil.copytree(FIXTURES / "pyrepo", dest)
    return dest


def _event(repo: Path, kind: EventType, tool: str | None = None, **args) -> AgentEvent:
    return AgentEvent(
        event=kind, agent="claude-code", workspace=str(repo), session_id="s1", tool=tool, arguments=args
    )


def test_a_command_that_only_mentions_pytest_does_not_silence_the_gate(repo):
    """Probe D: an edit, then `grep -n pytest pyproject.toml`, then "Done." used to pass,
    because the grep was counted as an uninterpretable test run."""
    guard = Guard(Settings())
    try:
        guard.workspace(repo).index.ready(timeout=30)
        guard.handle(
            AgentEvent(
                event=EventType.USER_PROMPT,
                agent="claude-code",
                workspace=str(repo),
                session_id="s1",
                prompt_text="Fix the paginate helper.",
            )
        )
        guard.handle(_event(repo, EventType.POST_TOOL_USE, "Edit", file_path="src/shop/utils/pagination.py"))
        grep = _event(repo, EventType.POST_TOOL_USE, "Bash", command="grep -n pytest pyproject.toml")
        grep.result = {"stdout": '12:    "pytest>=8.3",', "stderr": "", "interrupted": False}
        guard.handle(grep)

        state = guard.workspace(repo).task_state(None, "s1")
        assert state.verification.commands_seen == []

        stop = _event(repo, EventType.STOP)
        stop.last_assistant_message = "Done."
        decision = guard.handle(stop)
    finally:
        guard.close()

    assert decision.action is DecisionAction.BLOCK
    assert "incomplete" in decision.reason
    assert "no tests were run" in decision.reason


def test_a_real_runner_that_was_unknown_now_counts(repo):
    """`make test` was not recognised, so the gate demanded tests the agent had run."""
    guard = Guard(Settings())
    try:
        guard.workspace(repo).index.ready(timeout=30)
        guard.handle(
            AgentEvent(
                event=EventType.USER_PROMPT,
                agent="claude-code",
                workspace=str(repo),
                session_id="s1",
                prompt_text="Fix the paginate helper.",
            )
        )
        guard.handle(_event(repo, EventType.POST_TOOL_USE, "Edit", file_path="src/shop/utils/pagination.py"))
        run = _event(repo, EventType.POST_TOOL_USE, "Bash", command="make test")
        run.result = {"stdout": "pytest -q tests/\n..\n2 passed in 0.02s\n", "stderr": ""}
        guard.handle(run)
        state = guard.workspace(repo).task_state(None, "s1")
        decision = guard.handle(_event(repo, EventType.STOP))
    finally:
        guard.close()

    assert state.verification.commands_seen == ["make test"]
    assert decision.action is DecisionAction.ALLOW
