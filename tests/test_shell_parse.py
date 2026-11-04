"""A2: tokenise before judging (IMPROVEMENTS.md A2).

Every Bash check was a regex over the raw line, so text that only *mentions* a command was
judged as one. Of Truthstone's 221 risky-command hits in 42,426 real commands, 128 were
text inside heredocs or quoted arguments and 93 deleted a variable assigned in the same
command (D2); `git commit -m "...pip install requests..."` and `grep -rn "npm install
lodash"` were denied as new dependencies (probes Q1/Q2).

`validate/shell.py` is ported from Pebble's `shell_policy.py`, and the first half of this
file ports the key cases of Pebble's `test_heredoc_1929.py` and `test_shell_policy_40.py`,
including the zsh-oracle fuzz: whatever zsh actually runs, the parser must see as a
command — a body read as "data" is never executed.
"""

from __future__ import annotations

import os
import random
import shutil
import statistics
import subprocess
import time
from pathlib import Path

import pytest

from tests.test_asks_support import Session, make_guard, make_repo, permission
from truthstone.core.enums import DecisionAction, EventType
from truthstone.core.events import AgentEvent
from truthstone.evidence import extractors
from truthstone.validate import checks, shell

ZSH = Path("/bin/zsh")

# A heredoc script of the Pebble d-cd-01 kind: words that are commands appear only as
# Python text.
SCRIPT = (
    "cd ~/Desktop && python3 - <<'EOF'\n"
    "import os\n"
    "# sort the receipts at the end, then log in the summary\n"
    "for name in sorted(os.listdir('.')):\n"
    "    if name.startswith('receipt'):\n"
    "        print('security deposit', name)  # at login: nothing\n"
    "EOF"
)


def argvs(line: str) -> list[tuple[str, ...]]:
    return [part.argv for part in shell.parse(line).parts]


# -- the parser (Pebble's cases) --------------------------------------------------------


class TestPebbleParsing:
    @pytest.mark.parametrize(
        ("line", "expected", "opaque"),
        [
            ("ls -la ~/Desktop | head -5", [("ls", "-la", "~/Desktop"), ("head", "-5")], False),
            (
                "make build && ./run || echo failed; date",
                [("make", "build"), ("./run",), ("echo", "failed"), ("date",)],
                False,
            ),
            ("echo hi>out.txt 2>&1", [("echo", "hi")], False),
            ("FOO=1 BAR=2 env -i PATH=/bin nohup time python3 x.py", [("python3", "x.py")], False),
            ("echo \"a | b; c\" 'd && e'", [("echo", "a | b; c", "d && e")], False),
            ('bash -lc "sudo whoami"', [("bash", "-lc", "sudo whoami"), ("whoami",)], False),
            ("cat <<EOF\nx\nEOF", [("cat",)], False),
            ("echo $(whoami)", None, True),
            ("diff <(ls a) <(ls b)", None, True),
            ("(cd x; ls)", None, True),
            ("for f in *; do echo $f; done", None, True),
            ('echo "unclosed', None, True),
        ],
    )
    def test_the_line_is_split_into_its_plain_parts_or_kept_opaque(self, line, expected, opaque):
        parsed = shell.parse(line)
        if expected is not None:
            assert [p.argv for p in parsed.parts] == expected
        assert parsed.opaque is opaque

    def test_redirection_targets_are_read_as_the_shell_reads_them(self):
        part = shell.parse("sort < in.txt > out.txt 2>> err.log").parts[0]
        assert [op for op, _ in part.redirects] == ["<", ">", ">>"]
        assert [target for _, target in part.redirects] == ["in.txt", "out.txt", "err.log"]

    def test_a_python_heredoc_script_is_one_command_reading_code(self):
        parsed = shell.parse(SCRIPT)
        assert [p.argv for p in parsed.parts] == [("cd", "~/Desktop"), ("python3", "-")]
        assert not parsed.opaque
        assert [(d.word, d.quoted, d.kind) for d in parsed.heredocs] == [("EOF", True, "code")]
        assert parsed.heredocs[0].body.startswith("import os\n")
        assert parsed.heredocs[0].body.endswith("nothing\n")

    @pytest.mark.parametrize(
        ("line", "expected", "kind"),
        [
            ("cat > notes.md <<'EOF'\nsudo at login security\nEOF", [("cat",)], "data"),
            ("cat <<EOF\nx\nEOF", [("cat",)], "data"),
            ("cat <<-EOF\n\tindented\n\tEOF", [("cat",)], "data"),
            ("cat <<\\EOF\n$(not run)\nEOF", [("cat",)], "data"),
            ('cat <<"E O"\nbody\nE O\necho after', [("cat",), ("echo", "after")], "data"),
            (
                "cat <<A <<B && echo x\na\nA\nb\nB\necho done",
                [("cat",), ("echo", "x"), ("echo", "done")],
                "data",
            ),
            ("tee out.txt <<'EOF' | wc -l\nline\nEOF", [("tee", "out.txt"), ("wc", "-l")], "data"),
            ("node <<'EOF'\nconsole.log('at')\nEOF", [("node",)], "code"),
            ("cat <<'EOF' | python3\nprint('login')\nEOF", [("cat",), ("python3",)], "code"),
        ],
    )
    def test_a_body_is_never_split_into_commands(self, line, expected, kind):
        parsed = shell.parse(line)
        assert [p.argv for p in parsed.parts] == expected
        assert not parsed.opaque
        assert {d.kind for d in parsed.heredocs} == {kind}

    def test_a_here_string_is_one_word_of_input(self):
        parsed = shell.parse('cat <<< "sudo id"')
        assert [p.argv for p in parsed.parts] == [("cat",)]
        assert not parsed.opaque and parsed.heredocs == ()

    @pytest.mark.parametrize(
        "line",
        [
            "bash <<'EOF'\nsudo id\nEOF",
            "sh -s <<EOF\nsudo id\nEOF",
            "zsh <<'EOF'\necho hi; sudo id\nEOF",
            "cat <<'EOF' | sh\nsudo id\nEOF",
            "env bash <<'EOF'\nsudo id\nEOF",
            "cat <<'EOF'\nfine\nEOF\nsudo id",  # a command after the body
            "cat <<EOF && sudo id\nbody\nEOF",  # a command on the heredoc's own line
            "cat <<EOF\n$(sudo id)\nEOF",  # an unquoted end word: the substitution runs
            "cat <<EOF\nsudo id",  # no end line: opaque, read whole
            "echo ${a//<<x/y}\nsudo id\nx/y}",  # not a heredoc to the shell
            "echo $[1<<2]\nsudo id\n2]",
            "bash <<'A'\nbash <<'B'\nsudo id\nB\nA",  # nested
            "xargs -I{} sh -c '{}' <<'EOF'\nsudo id\nEOF",  # read as input, not data
            "sh -c 'eval \"$(cat)\"' <<'EOF'\nsudo id\nEOF",
        ],
    )
    def test_a_body_a_shell_runs_is_still_a_command(self, line):
        """Pebble's `test_every_refusal_of_a_real_command_is_kept`, for Truthstone: the
        `sudo` the shell runs is visible as a command, or the part around it is opaque."""
        parsed = shell.parse(line)
        assert any(
            p.name == "sudo" or "sudo" in p.wrappers or (p.opaque and "sudo" in p.text)
            for p in parsed.parts
        ) or parsed.reasons, line

    @pytest.mark.parametrize(
        ("line", "kind"),
        [
            ("awk -f - <<'EOF'\n{ print }\nEOF", "unread"),
            ("sed -f - in.txt <<'EOF'\ns/a/b/\nEOF", "unread"),
            ("xargs echo <<'EOF'\na\nEOF", "unread"),
            ("patch -p1 <<'EOF'\n--- a\nEOF", "unread"),
            ("sqlite3 x.db <<'EOF'\nselect 1;\nEOF", "sql"),
            ("psql -d app <<'EOF'\nselect 1;\nEOF", "sql"),
            ("git commit -F - <<'EOF'\nmessage\nEOF", "data"),
        ],
    )
    def test_readers_not_known_to_take_data(self, line, kind):
        assert [d.kind for d in shell.parse(line).heredocs] == [kind]

    @pytest.mark.parametrize("line", ["", "   ", "x" * (shell.MAX_SCAN + 10), "ls\x00", None, 42])
    def test_odd_lines_never_raise(self, line):
        parsed = shell.parse(line) if isinstance(line, str) else shell.parse("")
        assert isinstance(parsed, shell.Parsed)

    def test_a_long_line_is_read_up_to_the_limit_and_says_so(self):
        parsed = shell.parse("echo " + "x" * (shell.MAX_SCAN + 10))
        assert parsed.truncated and "truncated" in parsed.reasons

    def test_wrappers_are_recorded(self):
        part = shell.parse("sudo -u deploy timeout -s KILL 30 nice -n 5 git status").parts[0]
        assert part.argv == ("git", "status")
        assert part.wrappers == ("sudo", "timeout", "nice")

    def test_xargs_replacement_string_is_its_own(self):
        part = shell.parse("find . -name '*.tmp' | xargs -I % mv % /tmp/").parts[1]
        assert part.argv == ("mv", "%", "/tmp/") and part.replace == "%"

    def test_quoting_is_kept_where_it_decides_expansion(self):
        words = shell.parse("rm -rf '$D' \"$E\" $F").parts[0].words
        assert [(w.value, w.expands) for w in words[2:]] == [("$D", False), ("$E", True), ("$F", True)]

    def test_a_commit_message_heredoc_is_data(self):
        line = 'git commit -m "$(cat <<\'EOF\'\nfix: x; rm -rf /\n\nCo-Authored-By: y\nEOF\n)"'
        parsed = shell.parse(line)
        assert [p.name for p in parsed.parts] == ["git"]
        assert not parsed.opaque
        assert [d.kind for d in parsed.heredocs] == ["data"]


# -- fuzz -----------------------------------------------------------------------------

COMMAND_WORDS = ("sudo", "at", "login", "security", "launchctl", "killall")
SAFE_WORDS = ("cat", "echo", "printf", "true", "python3", "wc", "tee")
SHELL_WORDS = ("sh", "bash", "zsh")


def _stubs(folder: Path, log: Path) -> None:
    """A PATH where every command is a stub that logs its name and drains its input; the
    shells, xargs and env are the real ones (Pebble's harness)."""
    folder.mkdir()
    for name in COMMAND_WORDS + SAFE_WORDS:
        stub = folder / name
        stub.write_text(f'#!/bin/sh\necho {name} >> "{log}"\nexec /bin/cat > /dev/null\n')
        stub.chmod(0o755)
    for name in SHELL_WORDS:
        os.symlink(shutil.which(name, path="/bin") or f"/bin/{name}", folder / name)
    for name in ("xargs", "env"):
        os.symlink(f"/usr/bin/{name}", folder / name)


def _line(rng: random.Random, depth: int = 0) -> str:
    """A random command line from heredocs, expansions, pipes, lists and nested shells
    (Pebble's generator)."""

    def word() -> str:
        return rng.choice(COMMAND_WORDS + SAFE_WORDS)

    def command() -> str:
        roll = rng.random()
        if roll < 0.12 and depth < 2:
            return rng.choice(SHELL_WORDS) + " -c '" + word() + "'"
        if roll < 0.2:
            return "echo " + rng.choice(("${a//<<x/y}", "$[1<<2]", "$((1<<2))", '"<<EOF"', "'<<'"))
        return word() + rng.choice(("", " a", " -n", " > out.txt"))

    end = rng.choice(("EOF", "END", "x/y}", "2]"))
    if rng.random() < 0.15:
        fake = rng.choice(
            ("echo ${a:-<<" + end + " }", "echo $[1<<" + end + " ]", "echo ${a//<<" + end + "}")
        )
        return "\n".join([fake] + [command() for _ in range(rng.randint(1, 3))] + [end])
    op = rng.choice(("<<" + end, "<<'" + end + "'", "<<-" + end, "<<\\" + end, '<<"' + end + '"'))
    body = [
        rng.choice((word(), word() + " x", "# at login", "$(" + word() + ")", "`" + word() + "`",
                    "\t" + end, end + " ", 'print("sudo")'))
        for _ in range(rng.randint(0, 3))
    ]
    if rng.random() < 0.15 and depth < 2:
        body.append(_line(rng, depth + 1))
    reader = rng.choice(
        SAFE_WORDS
        + SHELL_WORDS
        + (
            rng.choice(SHELL_WORDS) + " -s",
            "xargs echo",
            "xargs -I{} sh -c '{}'",
            "env bash",
            "xargs -n1 sh -c",
        )
    )
    head = rng.choice(
        (reader + " " + op, command() + " | " + reader + " " + op, "cat " + op + " | " + reader)
    )
    closing = [] if rng.random() < 0.1 else [rng.choice((end, "\t" + end if "<<-" in op else end))]
    tail = [command() for _ in range(rng.randint(0, 2))]
    sep = rng.choice(("\n", " && ", "; ", " || "))
    if sep != "\n":
        first = head + ("\n" + "\n".join(body + closing) if body or closing else "")
        return sep.join([first, *tail])
    return "\n".join([head, *body, *closing, *tail])


def _seen(parsed: shell.Parsed, name: str) -> bool:
    """Whether the parser treats `name` as something that may run: a command, a wrapper,
    or a word of an opaque part (read whole, as before)."""
    return any(
        part.name == name or name in part.wrappers or (part.opaque and name in part.text)
        for part in parsed.parts
    ) or (bool(parsed.reasons) and name in parsed.line)


@pytest.mark.skipif(not ZSH.is_file(), reason="zsh is the oracle")
def test_fuzz_whatever_zsh_runs_the_parser_sees_as_a_command(tmp_path):
    """Pebble's zsh-oracle fuzz, recast: a body or argument the parser calls data must
    never be something zsh executes."""
    rng = random.Random(1929)
    log, bin_dir = tmp_path / "ran.log", tmp_path / "bin"
    _stubs(bin_dir, log)
    work = tmp_path / "work"
    work.mkdir()
    checked = ran = 0
    for _ in range(200):
        line = _line(rng)
        parsed = shell.parse(line)
        log.write_text("")
        subprocess.run(
            [str(ZSH), "-f", "-c", line],
            cwd=work,
            env={"PATH": str(bin_dir), "HOME": str(work)},
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
        executed = set(log.read_text().split()) & set(COMMAND_WORDS)
        checked += 1
        ran += bool(executed)
        for name in executed:
            assert _seen(parsed, name), (line, name, [p.argv for p in parsed.parts])
    assert checked == 200 and ran > 25, (checked, ran)  # the grammar reaches commands often


def test_fuzz_parse_is_bounded_and_never_raises():
    rng = random.Random(46)
    alphabet = ["<<", "<<-", "<<<", "'", '"', "\\", "\n", "\t", " ", "EOF", "$(", "${", "$[", "}", "]",
                ")", "(", "`", "|", "&&", ";", "#", "cat", "sudo", "x", "rm -rf", "$(cat <<'EOF'\n"]
    worst = 0.0
    for _ in range(3000):
        line = "".join(rng.choice(alphabet) for _ in range(rng.randint(1, 120)))
        began = time.perf_counter()
        shell.parse(line)
        event = AgentEvent(event=EventType.PRE_TOOL_USE, tool="Bash", arguments={"command": line})
        checks.risky_command(event)
        worst = max(worst, time.perf_counter() - began)
    hostile = "<<EOF\n" * 1300 + "x"
    began = time.perf_counter()
    shell.parse(hostile)
    # Pebble's bound is 50 ms; this one leaves room for a loaded machine and still catches
    # anything superlinear on 120-character lines.
    assert worst < 0.25 and time.perf_counter() - began < 0.5, worst


def test_parse_latency_on_ordinary_commands():
    """A2's stated cost was 33-57 us per Bash call (Pebble). Recorded, with a loose bound."""
    commands = [
        "pytest -q tests/test_x.py -k 'not slow' 2>&1 | tail -20",
        "git status && git diff --stat",
        'git commit -m "$(cat <<\'EOF\'\nfix: the thing\n\nCo-Authored-By: x\nEOF\n)"',
        "cd web && pnpm --filter app test -- --run",
        "rm -rf build dist && npm run build",
        "grep -rn 'TODO' src/ | head -50",
        "D=$(mktemp -d) && cp -r src $D && ls $D",
    ]
    timings = []
    for _ in range(50):
        for command in commands:
            shell.parse.cache_clear()
            began = time.perf_counter()
            shell.parse(command)
            timings.append(time.perf_counter() - began)
    timings.sort()
    p95 = timings[int(len(timings) * 0.95)]
    assert statistics.median(timings) < 0.005 and p95 < 0.025, (statistics.median(timings), p95)


# -- through the real Guard -------------------------------------------------------------


@pytest.fixture
def session(tmp_path):
    repo = make_repo(tmp_path)
    guard = make_guard(repo)
    yield Session(guard, repo)
    guard.close()


QUIET = [
    "cat > notes.md <<'EOF'\nNever run rm -rf / or git push --force.\nEOF",
    'git commit -m "docs: explain why we never git push --force"',
    'git commit -m "$(cat <<\'EOF\'\nfix: stop the deploy script running git reset --hard\n\nEOF\n)"',
    'grep -rn "DROP TABLE" migrations/',
    'grep -rn "git reset --hard" scripts/',
    "echo done # git clean -fdx would be wrong here",
    'gh pr create --title "Safer deploys" --body "Removes rm -rf / from the docs"',
    "git log --grep='reset --hard' --oneline",
    "python3 - <<'EOF'\n# never: rm -rf /\nprint('ok')\nEOF",
    "sed -i 's/git push --force/git push/' docs/release.md",
]


@pytest.mark.parametrize("command", QUIET)
def test_quoted_text_comments_and_heredoc_data_are_not_commands(session, command):
    session.prompt("Update the release docs.")
    decision = session.pre("Bash", command=command)
    assert decision.action is DecisionAction.ALLOW, decision.reason
    assert not any(f.verdict.value == "requires_human" for f in decision.findings)
    assert permission(session.claude("Bash", command=command)) is None
    assert permission(session.codex_bash(command)) is None


SEEN = [
    "sudo rm -rf /",
    "env X=1 bash -c 'rm -rf ~'",
    "timeout 30 git push -f origin main",
    "nohup git push --force &",
    "xargs -I{} sh -c 'git reset --hard' < targets.txt",
    "eval 'git push --force'",
    "bash <<'EOF'\nrm -rf /\nEOF",
    "cat <<'EOF' | sh\ngit reset --hard origin/main\nEOF",
    'echo "rm -rf /" | sh',
    "psql app <<'EOF'\nDROP TABLE users;\nEOF",
    'echo "DROP TABLE users;" | psql app',
    "X=$(rm -rf /)",
    "sh -c 'sh -c \"git push --force\"'",
]


@pytest.mark.parametrize("command", SEEN)
def test_wrappers_and_nested_shells_are_still_seen(session, command):
    session.prompt("Tidy up.")
    decision = session.pre("Bash", command=command)
    assert decision.action is DecisionAction.REQUEST_REVIEW, command
    assert permission(session.claude("Bash", command=command)) == "ask"
    assert permission(session.codex_bash(command)) == "deny"


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ('git commit -m "docs: tell users to pip install requests first"', []),
        ('grep -rn "npm install lodash" docs/', []),
        ("pip3 install --user requests", ["requests"]),
        ("npm i -D vitest", ["vitest"]),
        ("python -m pip install -U 'requests[socks]>=2' -r requirements.txt", ["requests"]),
        ("uv pip install --index-url https://x/simple httpx==0.27", ["httpx"]),
        ("npm install --prefix web @types/node@18 lodash@4", ["@types/node", "lodash"]),
        ("pnpm add zod", ["zod"]),
        ("yarn add -D jest", ["jest"]),
        ("bun add hono", ["hono"]),
        ("cargo add serde --features derive", ["serde"]),
        ("go get github.com/x/y@v1.2.3", ["github.com/x/y"]),
        ("poetry add --group dev black", ["black"]),
        ("pipenv install flask", ["flask"]),
        ("pip install -e . ./local_pkg", []),
        ("pip install $PKG", []),
        ("npm install", []),
        ("echo 'pip install requests' >> README.md", []),
        ("bash -c 'pip install redis'", ["redis"]),
    ],
)
def test_dependency_claims_come_only_from_installer_argv(command, expected):
    assert [claim.subject for claim in extractors.claims_from_bash(command)] == expected


def test_dependency_claims_through_the_guard(session):
    session.prompt("Document the client.")
    commit = 'git commit -m "docs: tell users to pip install requests first"'
    assert session.pre("Bash", command=commit).is_silent
    assert session.pre("Bash", command='grep -rn "npm install lodash" docs/').is_silent
    install = session.pre("Bash", command="pip3 install --user requests-toolbelt")
    assert install.action is DecisionAction.CHALLENGE
    assert any(f.subject == "requests-toolbelt" for f in install.findings)


@pytest.mark.parametrize(
    "command",
    [
        "D=$(mktemp -d); cp -r src $D; rm -rf $D",
        'T="$(mktemp -d)" && cd "$T" && rm -rf "$T"',
        "export WORK=$(mktemp -d -t build) && rm -rf $WORK/*",
        "OUT=build; rm -rf $OUT",
        'DIRS="dist build"; rm -rf $DIRS',
    ],
)
def test_mktemp_guarded_delete_is_quiet(session, command):
    session.prompt("Clean up the scratch directory.")
    decision = session.pre("Bash", command=command)
    assert decision.action is DecisionAction.ALLOW, decision.reason
    assert permission(session.claude("Bash", command=command)) is None


@pytest.mark.parametrize("command", ["D=/; rm -rf $D", "D=; rm -rf $D/", "D=~; rm -rf $D"])
def test_a_literal_assignment_is_judged_as_its_value(session, command):
    """Counting an assignment as a guard must not hide what it assigns."""
    session.prompt("Clean up.")
    decision = session.pre("Bash", command=command)
    assert decision.action is DecisionAction.REQUEST_REVIEW
    assert decision.findings[0].severity.value == "critical"


def test_an_assignment_that_may_not_run_is_not_a_guard(session):
    session.prompt("Clean up.")
    for command in ["test -d x || D=build; rm -rf $D", "D=build rm -rf $D", "echo | D=x; rm -rf $D"]:
        assert session.pre("Bash", command=command).action is not DecisionAction.ALLOW, command
