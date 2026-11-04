"""ONE-PARSER: Codex has no shell classifier of its own; the core's decides for both hosts.

The Codex adapter used to keep a second, regex-and-``shlex`` classifier and drop every
PreToolUse it called read-only before the core saw it. Two classifiers disagree, and this
one was wrong in the dangerous direction: ``shlex`` does not split a ``;`` glued to a
word, so ``cat f;rm -rf /`` was "a read" and never reached the risk check. It also called
``rg --pre ./x.sh``, ``git grep -O <pager>`` and ``git diff --ext-diff`` reads, though
each runs a program of the caller's choosing.

Dropping on read-only was wrong even with the core's classifier: the core calls a test
run read-only *for evidence and scope* (A4), after its Level-0 checks — so
``mvn test -DskipTests`` is "read-only" and still challenged for skipping the tests (A8).
So Codex now hands every Bash call to the core, exactly as Claude Code's adapter does,
and the core's one classifier (``validate.shell`` + ``validate.checks.read_only``)
decides for both.

The corpus: every shell command in the Codex fixtures and the Codex tests (collected, so
a new one is included automatically), plus labelled adversarial commands. Where the
*core* is wrong, the test is a strict xfail with the reason — those belong to asks-b.
"""

from __future__ import annotations

import ast
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from agentguard.adapters.claude_code import translate as claude
from agentguard.adapters.codex import translate as codex
from agentguard.core.config import Settings
from agentguard.core.engine import Guard
from agentguard.core.enums import DecisionAction
from agentguard.validate import checks, shell
from tests.codex_schema import validate

TESTS = Path(__file__).parent
FIXTURES = TESTS / "fixtures"


# -- the corpus -----------------------------------------------------------------------


def fixture_commands() -> set[str]:
    found = set()
    for path in sorted((FIXTURES / "codex_payloads").glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("tool_name") == "Bash":
            command = codex.shell_command(payload.get("tool_input"))
            if command:
                found.add(command)
    return found


def _parametrized_commands(call: ast.Call) -> set[str]:
    """The ``command`` column of a ``pytest.mark.parametrize`` call, where it is literal."""
    if not call.args or not isinstance(call.args[0], ast.Constant | ast.Tuple):
        return set()
    names = call.args[0]
    if isinstance(names, ast.Constant):
        columns = [part.strip() for part in str(names.value).split(",")]
    else:
        columns = [elt.value for elt in names.elts if isinstance(elt, ast.Constant)]
    if "command" not in columns or len(call.args) < 2 or not isinstance(call.args[1], ast.List):
        return set()
    index = columns.index("command")
    found = set()
    for row in call.args[1].elts:
        cell = row if len(columns) == 1 else (row.elts[index] if isinstance(row, ast.Tuple) else None)
        if isinstance(cell, ast.Constant) and isinstance(cell.value, str):
            found.add(cell.value)
    return found


def commands_in_codex_tests() -> set[str]:
    """String literals used as a shell command in the Codex tests: ``"command"`` values in
    dict literals, ``command=`` keywords, and ``command`` parametrize columns."""
    found: set[str] = set()
    for path in sorted(TESTS.glob("test_codex_*.py")):
        if path.name.startswith("test_codex_b_"):
            continue  # this cluster's own tests: the corpus lives here already
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values, strict=True):
                    if (
                        isinstance(key, ast.Constant)
                        and key.value == "command"
                        and isinstance(value, ast.Constant)
                        and isinstance(value.value, str)
                    ):
                        found.add(value.value)
            elif isinstance(node, ast.keyword) and node.arg == "command":
                if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    found.add(node.value.value)
            elif isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "parametrize":
                found |= _parametrized_commands(node)
    return {command for command in found if not command.lstrip().startswith("*** Begin Patch")}


# Commands that change something: each must never be read-only.
WRITES = [
    # redirections
    "ls > out", "ls >> out", "ls 2> err", "ls &> out", "ls >| out", "ls 1>out", "ls>out",
    "cat<in>out", "exec 3>out; echo hi >&3", "head -c 1G /dev/zero > big", "printf 'x' > .env",
    "cat f >> ~/.bashrc", "time cat f > out", "git log --pretty=format:%s > CHANGELOG",
    "git rev-parse HEAD > .git/refs/heads/x", "cat <<'EOF' > out\nx\nEOF", "cat > out <<EOF\nx\nEOF",
    # tee
    "echo x | tee out", "tee out < in", "cat f | tee -a log", "tee out <<EOF\nx\nEOF",
    "doas tee /etc/x < f",
    # substitutions
    "echo $(rm x)", 'ls "$(touch x)"', "echo `rm x`", "cat <(rm x)", "ls >(cat)", "ls ${X:=$(rm x)}",
    # find
    "find . -delete", "find . -exec rm {} +", "find . -execdir rm {} \\;", "find . -ok rm {} \\;",
    "find . -fprint out", "find . -fls out", "find . -fprintf out %p", "find . -fprint0 out",
    "find . -name '*.pyc' -delete",
    # sed
    "sed -i 's/a/b/' f", "sed -i.bak s/a/b/ f", "sed --in-place s/a/b/ f", "sed -n 'w out' f",
    "sed 's/a/b/w out' f",
    # git
    "git -C x diff --output=f", "git diff --output f", "git log --output=x", "git show --output=x",
    "git -C sub diff --output=../x", "git -P diff --output=x", "git --no-pager show HEAD --output=x",
    "git branch newb", "git branch -D main", "git branch -m a b", "git branch --set-upstream-to=o/m",
    "git status; git stash", "git log --format=%H | xargs git branch -D", "git checkout -- .",
    "git restore .", "git stash drop", "git reset --hard", "git clean -fdx", "git commit -am x",
    "git tag v1", "git config user.name x", "git apply x.diff", "git diff --ext-diff",
    "git grep -O vim foo", "git grep --open-files-in-pager=vim x",
    # env prefixes and wrappers
    "X=1 rm x", "env rm x", "env -i rm x", "env -u HOME rm x", "FOO=bar sh -c 'rm x'", "timeout 5 rm x",
    "nice -n 10 rm x", "nohup rm x &", "command rm x", "stdbuf -o0 rm x", "caffeinate rm x",
    "env -S 'rm -rf x' ls", "sudo rm -rf build", "xargs -a list rm",
    # separators glued to words (the old Codex classifier read these as reads)
    "cat f;rm -rf /", "echo x;rm -rf ~", "ls;rm x", "ls&&rm x", "ls||rm x", "ls|rm x", "ls &rm x",
    "ls\nrm x",
    # programs that run programs
    "rg --pre ./x.sh foo", "rg --pre=./x.sh foo", "ls | xargs -I{} cp {} /tmp", "ls | xargs -0 rm",
    "ls | xargs rm", "echo rm -rf / | sh", "echo rm | bash", "cat script.sh | zsh", "curl x | sh",
    "cat <<EOF | sh\nrm -rf x\nEOF", "bash -c 'rm x'", 'sh -c "ls; rm x"', "eval 'rm x'",
    "source evil.sh", ". evil.sh", "alias ls='rm -rf'", "function ls { rm x; }", "ls() { rm x; }; ls",
    "diff -u a b | patch -p0", "awk '{print > \"out\"}' f", "grep -rl x . | xargs perl -pi -e 's/a/b/'",
    # builds and installs that are not test runs
    "make", "make clean", "make test install", "make -f evil.mk test", "npm run build", "npm install",
    "npm test && npm publish", "pytest; git push", "python -c \"import os; os.remove('x')\"",
    # plain writers
    "set -e; rm x", "cd /tmp && rm -rf x", "chmod +x f", "touch f", "mkdir x", "ln -s a b", "cp a b",
    "mv a b", "rm f", "rmdir x", "truncate -s 0 f", "dd if=a of=b", "unlink f", "rsync -a a/ b/",
    "tar xf a.tar", "unzip a.zip", "wget url", "curl -o f url", "curl url > f", "pip install x",
    "npm i x", "psql -c 'drop table x'", "sqlite3 db 'delete from t'",
]

# Writing commands the core still calls read-only: core bugs, for asks-b (validate/**).
CORE_MISSES = {
    "GIT_EXTERNAL_DIFF=./evil.sh git diff": "a leading assignment can make a reader run a program "
    "(GIT_EXTERNAL_DIFF, PAGER, GIT_PAGER, LESSOPEN, GIT_CONFIG_*); checks._reads_only ignores assignments",
    "PAGER='rm -rf src' git log": "PAGER runs a program whenever git pages (a PTY, as Codex's exec can use)",
    "GIT_PAGER='rm x' git log": "GIT_PAGER, as PAGER",
    "pytest --basetemp=src": "pytest deletes --basetemp's directory before the run; "
    "checks._runs_tests trusts every pytest invocation",
    "python -m pytest --basetemp src": "as --basetemp=src",
    "jest --init": "`--init` writes a config file; checks._runs_tests trusts every jest invocation",
    "rspec --init": "`--init` writes .rspec and spec/spec_helper.rb",
    "npx jest -u": "`-u` rewrites snapshot files (test tampering, A6)",
    "npx jest --updateSnapshot": "as -u",
    "npx vitest run -u": "as jest -u",
    "rg --hostname-bin=./evil.sh foo": "ripgrep runs --hostname-bin's program; checks._reads_only "
    "only knows --pre",
    "./ls": "a path-qualified command is a file in the repository, not the system tool: "
    "shell.basename('./ls') == 'ls'",
    "./cat f": "as ./ls",
    "bin/git status": "as ./ls",
}

# Commands that only read (or only run tests): the core's read-only set, for agreement.
READS = [
    "ls", "ls -la src", "cat a.py | head -20", "rg foo src && git status", "git -C sub log --oneline",
    'find . -name "*.py"', "ls ; pwd", "grep 'a|b' f", "ls > /dev/null", "ls 2>/dev/null",
    "echo hi >&2", "ls > /dev/null 2>&1", "echo 'a;rm x'", "cat \"f;rm x\"", "echo '$(rm x)'",
    "ls # ; rm x", "git branch -a", "git branch", "git branch --list 'feat*'", "git log -p",
    "git show HEAD:f", "git diff --stat", "git rev-parse HEAD", "which python",
    "head -n 5 f && tail -n 5 f", "wc -l < f", "X=1 ls", "pytest -q", "env ls", "timeout 5 cat f",
    "ls &", "ls\npwd", "ls | xargs cat", "/bin/ls -la", "mvn test -DskipTests", "SKIP_TESTS=1 npm test",
    "npx vitest run", "uv run pytest -q", "cargo test", "go test ./...", "python -m pytest tests/",
]

ADVERSARIAL = sorted(set(WRITES) | set(CORE_MISSES) | set(READS))
CORPUS = sorted(fixture_commands() | commands_in_codex_tests() | set(ADVERSARIAL))


def test_the_corpus_is_what_the_item_asks_for():
    assert fixture_commands() >= {"echo hello-codex", "rm -rf build ."}
    from_tests = commands_in_codex_tests()
    assert {"cat a > b", "find . -delete", "git diff --output=p.diff", "make build"} <= from_tests
    assert len(set(WRITES) | set(CORE_MISSES)) >= 50
    assert set(WRITES).isdisjoint(READS) and set(CORE_MISSES).isdisjoint(READS)


# -- the adapter never classifies: the core does, for both hosts ------------------------


def codex_pre(command: str, cwd: str = "/workspace", session: str = "sess-codex") -> dict:
    return {
        "session_id": session,
        "turn_id": "turn-1",
        "transcript_path": None,
        "cwd": cwd,
        "hook_event_name": "PreToolUse",
        "model": "gpt-test",
        "permission_mode": "default",
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "tool_use_id": "call-1",
    }


def claude_pre(command: str, cwd: str = "/workspace", session: str = "sess-claude") -> dict:
    return {
        "session_id": session,
        "transcript_path": "/tmp/t.jsonl",
        "cwd": cwd,
        "permission_mode": "default",
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "tool_use_id": "toolu_1",
    }


@pytest.mark.parametrize("command", CORPUS)
def test_codex_hands_the_core_what_claude_code_does(command):
    """Every command reaches the core, reads included: the same Bash event either host's
    adapter would build, so the core's one classifier decides for both."""
    events = codex.to_events(codex_pre(command))
    assert [(e.tool, e.arguments) for e in events] == [("Bash", {"command": command})]
    other = claude.to_event(claude_pre(command))
    assert (other.tool, other.arguments) == ("Bash", {"command": command})
    assert checks.read_only_bash(events[0]) is checks.read_only_bash(other)


@pytest.mark.parametrize("command", CORPUS)
def test_the_adapter_and_the_core_never_disagree(command):
    core = checks.read_only(shell.parse(command))
    assert codex.is_read_only_command(command) is core
    (event,) = codex.to_events(codex_pre(command))
    assert checks.read_only_bash(event) is core


@pytest.mark.parametrize("command", sorted(WRITES))
def test_no_writing_command_is_ever_read_only(command):
    assert not codex.is_read_only_command(command)
    assert not checks.read_only(shell.parse(command))


@pytest.mark.parametrize(
    "command",
    [
        pytest.param(command, marks=pytest.mark.xfail(strict=True, reason=why))
        for command, why in CORE_MISSES.items()
    ],
)
def test_writing_commands_the_core_still_reads_as_read_only(command):
    """Core bugs (asks-b). Strict: the day the core is fixed, this says so."""
    assert not checks.read_only(shell.parse(command))


@pytest.mark.parametrize("command", sorted(READS))
def test_reads_and_test_runs_are_read_only_to_both(command):
    assert codex.is_read_only_command(command)


# -- through a real Guard: same command, same answer --------------------------------------


@pytest.fixture
def repo(tmp_path) -> Path:
    dest = tmp_path / "pyrepo"
    shutil.copytree(FIXTURES / "pyrepo", dest)
    git = ["git", "-c", "user.email=t@example.com", "-c", "user.name=t"]
    subprocess.run([*git, "init", "-q"], cwd=dest, check=True)
    subprocess.run([*git, "add", "-A"], cwd=dest, check=True)
    subprocess.run([*git, "commit", "-qm", "init"], cwd=dest, check=True)
    return dest


@pytest.fixture
def guard(repo):
    g = Guard(Settings())
    g.workspace(repo).index.ready(timeout=30)
    yield g
    g.close()


def test_every_corpus_command_gets_the_same_answer_on_both_hosts(guard, repo):
    """Two sessions, one per host, fed the same commands in the same order: the core must
    decide the same thing for each. A command Codex dropped counted as an ALLOW."""
    differ = []
    for command in CORPUS:
        events = codex.to_events(codex_pre(command, cwd=str(repo)))
        on_codex = [guard.handle(event).action for event in events] or [DecisionAction.ALLOW]
        on_claude = guard.handle(claude.to_event(claude_pre(command, cwd=str(repo)))).action
        if on_codex != [on_claude]:
            differ.append((command, on_codex, on_claude))
    assert differ == []


def handle(guard, payload: dict) -> dict:
    out = codex.handle_payload(guard, payload)
    assert validate(out, "pre-tool-use.command.output") == []
    return out


GLUED = ["cat f;rm -rf /", "echo x;rm -rf ~", "ls -la;git push --force origin main"]


@pytest.mark.parametrize("command", GLUED)
def test_a_command_glued_to_a_read_is_still_held_for_sign_off(guard, repo, command):
    """Before ONE-PARSER, Codex called each of these a read and never asked the core."""
    spec = handle(guard, codex_pre(command, cwd=str(repo)))["hookSpecificOutput"]
    assert spec["permissionDecision"] == "deny"
    alone = command.split(";", 1)[1]
    expected = handle(guard, codex_pre(alone, cwd=str(repo), session="sess-alone"))["hookSpecificOutput"]

    def lead(reason: str) -> str:
        # A sign-off names a code bound to (session, exact action) (A1b): the glued command
        # and the part alone are held the same way, under different codes.
        return re.sub(checks.SIGNOFF_CODE_SHAPE, "<code>", reason.splitlines()[0])

    assert "<code>" in lead(expected["permissionDecisionReason"])
    assert lead(spec["permissionDecisionReason"]) == lead(expected["permissionDecisionReason"])


@pytest.mark.parametrize("command", ["mvn test -DskipTests", "SKIP_TESTS=1 npm test"])
def test_a_read_only_test_run_that_skips_the_tests_is_still_challenged(guard, repo, command):
    """The core calls these read-only (test runs, A4) *and* challenges them (A8): read-only
    only ever skipped evidence and scope. An adapter that dropped core-read-only commands
    would let them through unseen."""
    assert codex.is_read_only_command(command)
    spec = handle(guard, codex_pre(command, cwd=str(repo)))["hookSpecificOutput"]
    assert spec["permissionDecision"] == "deny"
    assert "Verification skipped" in spec["permissionDecisionReason"]


def test_a_plain_read_stays_silent_and_is_recorded(guard, repo):
    assert handle(guard, codex_pre("ls src/shop", cwd=str(repo))) == {}
    rows = guard.workspace(repo).store.recent_decisions(5)
    assert any(row["tool"] == "Bash" for row in rows)  # the core saw it, so the census can count it
