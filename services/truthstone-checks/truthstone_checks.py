"""Truthstone checks: a stateless, read-only MCP server over Truthstone's own rules.

Three tools, each a thin wrapper over a rule the Truthstone runtime (``truthstone`` 0.2.0)
already applies in its hooks, run here on text the model passes in:

* ``check_shell_command``: ``validate.checks.risky_command`` (and ``validate.modify.safer_form``);
* ``check_test_edit``: ``validate.weakened_tests.weakenings``;
* ``check_test_runs``: ``verify.runners.outcome_from_result`` and ``assess_timeline``, with
  ``verify.claims.classify`` for an optional final message.

Nothing is stored, nothing is fetched, nothing is run, and no request body or tool argument is
logged: the privacy policy (docs/legal/PRIVACY.md) says so, and this module must keep it true.

Run: ``uvicorn truthstone_checks:app`` (MCP endpoint ``/mcp``).
"""

from __future__ import annotations

import logging
import os
from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from pydantic import BaseModel, Field, model_validator
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response

from truthstone.core.enums import EventType, Verdict
from truthstone.core.events import AgentEvent
from truthstone.repo import scanner
from truthstone.validate import checks, modify, weakened_tests
from truthstone.verify import claims, runners

VERSION = "1.0.0"
MAX_TEXT = 200_000  # characters per text field, and in total per call
MAX_STEPS = 200
CHALLENGE_ENV = "OPENAI_APPS_CHALLENGE"

# The SDK logs a rejected call's error message, which can quote an argument, at INFO: WARNING
# keeps it out. (Uvicorn's access log holds the method, path, status and client address only.)
logging.getLogger("mcp").setLevel(logging.WARNING)

INSTRUCTIONS = (
    "Deterministic second opinions from Truthstone's rules; they only read the text you pass and "
    "never run anything. Before running a shell command that could delete, overwrite, force-push or "
    "reset, call check_shell_command. When an edit changes an existing test file, call "
    "check_test_edit with the file before and after. Before saying a code change is done or tested, "
    "call check_test_runs with the commands run since the change and their results."
)

READ_ONLY = dict(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)

mcp = MCPServer("truthstone-checks", version=VERSION, instructions=INSTRUCTIONS)


def _result(text: str, data: BaseModel) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=text)], structured_content=data.model_dump(mode="json")
    )


def _cap(*texts: str) -> None:
    size = sum(len(text) for text in texts)
    if size > MAX_TEXT:
        raise ToolError(f"Input too large: {size:,} characters; the limit is {MAX_TEXT:,} per call.")


# -- check_shell_command ------------------------------------------------------------------------


class CommandFinding(BaseModel):
    severity: Literal["low", "medium", "high", "critical"]
    rule: str = Field(description="The rule that matched, e.g. 'force push to main'.")
    matched: str = Field(description="The part of the command the rule matched.")


class CommandCheck(BaseModel):
    verdict: Literal["review", "clean"] = Field(
        description="'review': the command has an irreversible or destructive effect a person should confirm."
    )
    findings: list[CommandFinding]
    safer_command: str | None = Field(
        description="A guarded form of the command, when the rule has a sound one; otherwise null."
    )


@mcp.tool(
    title="Check a shell command",
    description=(
        "Use this before running, or suggesting, a shell command that may delete files, rewrite git "
        "history, force-push, reset or clean a working tree, pipe a download into a shell, drop "
        "database tables, or write to a device. It reads the command text with Truthstone's rules and "
        "returns 'review' with the matched rules, or 'clean'. It never runs the command. Text inside "
        "quotes, commit messages, echo and grep is treated as text, not as a command. 'clean' means no "
        "rule matched, not that the command is safe."
    ),
    annotations=ToolAnnotations(title="Check a shell command", **READ_ONLY),
)
def check_shell_command(
    command: Annotated[
        str, Field(description="The full command line, exactly as it would run.", max_length=MAX_TEXT)
    ],
) -> Annotated[CallToolResult, CommandCheck]:
    _cap(command)
    # A fixed workspace path so the verdict does not depend on the host the server runs on.
    event = AgentEvent(
        event=EventType.PRE_TOOL_USE, tool="Bash", arguments={"command": command}, workspace="/workspace"
    )
    raised = [f for f in checks.risky_command(event) if f.verdict is Verdict.REQUIRES_HUMAN]
    found = [
        CommandFinding(
            severity=f.severity.value,
            rule=f.summary.removeprefix("Irreversible command: "),
            matched=f.subject,
        )
        for f in raised
    ]
    safer = modify.safer_form(event, raised) if raised else None
    data = CommandCheck(verdict="review" if found else "clean", findings=found, safer_command=safer)
    if not found:
        return _result(
            "clean: no destructive or irreversible effect matched. This is not a safety guarantee.", data
        )
    lines = [f"review: {len(found)} rule(s) matched; confirm with the user before running it."]
    lines += [f"- {f.severity}: {f.rule} (`{f.matched}`)" for f in found]
    if safer:
        lines.append(f"Safer form: `{safer}`")
    return _result("\n".join(lines), data)


# -- check_test_edit ----------------------------------------------------------------------------

# Module-level and import changes speak only with the task's failure history and the
# repository (weakened_tests._found / _concern); with two texts alone they are left out.
_KINDS = ("skipped", "hack", "deleted", "fewer-assertions", "expected-changed", "file-deleted")


class Weakening(BaseModel):
    test: str = Field(description="The test's name; empty for the whole file.")
    kind: Literal["skipped", "hack", "deleted", "fewer-assertions", "expected-changed", "file-deleted"]
    detail: str
    always: bool = Field(
        description="True for skips and run-around hacks, which are a problem whatever the request was."
    )


class TestEditCheck(BaseModel):
    verdict: Literal["weakened", "clean", "unsupported"] = Field(
        description="'unsupported': not a Python or JavaScript/TypeScript test file, or not parsable."
    )
    weakenings: list[Weakening]


@mcp.tool(
    title="Check a test file edit",
    description=(
        "Use this when a change edits or deletes an existing test file, to see whether it weakens "
        "the tests: a skip, xfail or .only added, a test deleted, fewer assertions, an expected value "
        "changed, or a hook that stops tests from running. Pass the whole file before and after the "
        "change (after = null if the file was deleted). Supports Python and JavaScript/TypeScript test "
        "files. Adding tests or assertions is never flagged. It does not see the repository, so it "
        "cannot tell whether the user asked for the tests to change."
    ),
    annotations=ToolAnnotations(title="Check a test file edit", **READ_ONLY),
)
def check_test_edit(
    path: Annotated[str, Field(description="The test file's path, e.g. tests/test_api.py.", max_length=1024)],
    before: Annotated[
        str, Field(description="The full file content before the change.", max_length=MAX_TEXT)
    ],
    after: Annotated[
        str | None,
        Field(
            description="The full file content after the change; null if it was deleted.", max_length=MAX_TEXT
        ),
    ] = None,
) -> Annotated[CallToolResult, TestEditCheck]:
    _cap(before, after or "")
    if not scanner.is_test_path(path):
        data = TestEditCheck(verdict="unsupported", weakenings=[])
        return _result(f"unsupported: {path} does not look like a test file.", data)
    found = weakened_tests.weakenings(path, before, after)
    if found is None:
        data = TestEditCheck(verdict="unsupported", weakenings=[])
        return _result("unsupported: the language is not supported or the file could not be parsed.", data)
    items = [
        Weakening(test=w.test, kind=w.kind, detail=w.detail, always=w.always)
        for w in found
        if w.kind in _KINDS
    ]
    data = TestEditCheck(verdict="weakened" if items else "clean", weakenings=items)
    if not items:
        return _result("clean: no existing test was skipped, deleted or weakened.", data)
    lines = [f"weakened: {len(items)} existing test(s) weakened."]
    lines += [f"- {w.test or path}: {w.detail or w.kind}" for w in items]
    lines.append(
        "Restore them unless the user asked for this change; if a test contradicts the request, say so."
    )
    return _result("\n".join(lines), data)


# -- check_test_runs ----------------------------------------------------------------------------


class Step(BaseModel):
    command: str | None = Field(None, description="A shell command that was run.", max_length=MAX_TEXT)
    exit_code: int | None = Field(None, description="Its exit status, if known.")
    output: str | None = Field(
        None,
        description="Its output, or at least the test runner's final summary line.",
        max_length=MAX_TEXT,
    )
    edited_file: str | None = Field(
        None,
        description="Instead of a command: the path of a code or test file changed at this point.",
        max_length=1024,
    )

    @model_validator(mode="after")
    def _one_kind(self) -> Step:
        if (self.command is None) == (self.edited_file is None):
            raise ValueError("each step needs exactly one of 'command' or 'edited_file'")
        return self


class RunsCheck(BaseModel):
    verdict: Literal["verified", "failing", "unverified"] = Field(
        description=(
            "'verified': a whole-suite run passed after the last edit. 'failing': the latest run of a "
            "suite failed. 'unverified': no readable passing whole-suite run covers the final code."
        )
    )
    reason: str
    test_runs: list[str] = Field(description="Each recognised test run: command, then passed/failed/unknown.")
    overclaim: bool | None = Field(
        description="True when final_message claims done or verified and the verdict is not 'verified'; "
        "null when no final_message was given."
    )


def _status(outcome: runners.TestOutcome) -> str:
    word = {True: "passed", False: "failed", None: "unknown"}[outcome.passed]
    return f"{outcome.command}: {word}" + (f" ({outcome.summary})" if outcome.summary else "")


@mcp.tool(
    title="Check test runs against edits",
    description=(
        "Use this before saying a code change is done, fixed or tested. Pass, in order, the file edits "
        "and the shell commands that were run with their exit codes and output (at least the test "
        "runner's summary line). It reports whether a whole-suite test run passed after the last edit, "
        "whether the latest run failed, and whether a later green run was only narrower (one file, -k, "
        "a single test). Optionally pass the final message to see whether it claims more than the runs "
        "show. Exit code 0 alone, without the runner's summary, is not read as a pass."
    ),
    annotations=ToolAnnotations(title="Check test runs against edits", **READ_ONLY),
)
def check_test_runs(
    steps: Annotated[
        list[Step], Field(description="Edits and commands, oldest first.", min_length=1, max_length=MAX_STEPS)
    ],
    final_message: Annotated[
        str | None,
        Field(description="Optional: the message that reports the work as done.", max_length=MAX_TEXT),
    ] = None,
) -> Annotated[CallToolResult, RunsCheck]:
    _cap(*(s.command or "" for s in steps), *(s.output or "" for s in steps), final_message or "")
    verification = runners.VerificationState()
    last_change: dict[str, int] = {}
    for seq, step in enumerate(steps, 1):
        if step.edited_file is not None:
            last_change[step.edited_file] = seq
            continue
        verification.commands_seen.append(step.command)
        outcome = runners.outcome_from_result(
            step.command, {"stdout": step.output or "", "exit_code": step.exit_code}
        )
        if outcome is None:
            continue  # not a test run
        outcome.seq = seq
        (verification.outcomes if outcome.passed is not None else verification.inconclusive).append(outcome)
    seen = sorted([*verification.outcomes, *verification.inconclusive], key=lambda o: o.seq)
    # Without the repository nothing says which tests a narrowed run reached, so only a
    # whole-suite run verifies a change (the hooks' G2b, with an unknown test map).
    timeline = runners.assess_timeline(
        verification, last_change, set(last_change), reaches=lambda run, path: not run.scope
    )
    verdict, reason = _judge(timeline, bool(last_change), seen)
    overclaim = None
    if final_message is not None:
        said = claims.classify(final_message)
        overclaim = said.claims and verdict != "verified"
    data = RunsCheck(
        verdict=verdict, reason=reason, test_runs=[_status(o) for o in seen], overclaim=overclaim
    )
    text = f"{verdict}: {reason}"
    if overclaim:
        text += " The final message claims the work is done or tested; the runs above do not show that."
    return _result(text, data)


def _judge(timeline: runners.Timeline, edited: bool, seen: list) -> tuple[str, str]:
    if timeline.failing is not None:
        failure = timeline.failing
        reason = f"the latest run of `{failure.command}` failed" + (
            f": {failure.summary}" if failure.summary else ""
        )
        if timeline.changed_after_failure:
            reason += f"; {', '.join(timeline.changed_after_failure)} changed after it, so re-run it"
        return "failing", reason + "."
    if timeline.open_failure is not None:
        return "unverified", (
            f"`{timeline.open_failure.command}` failed and was not re-run; the later green run "
            f"`{timeline.narrower_pass.command}` was narrower, so it does not show the failure is fixed."
        )
    if timeline.stale:
        return "unverified", (
            f"{', '.join(timeline.stale)} changed after the last passing run "
            f"(`{timeline.stale_against.command}`); re-run it."
        )
    if timeline.unreached:
        return "unverified", (
            f"no whole-suite run passed after the last edit to {', '.join(timeline.unreached)}; "
            "only narrowed runs did, and they may not reach the changed code."
        )
    if timeline.latest_pass is not None:
        return "verified", f"`{timeline.latest_pass.command}` passed after the last edit."
    if seen:
        return "unverified", "no test run had a readable result; pass the runner's output or summary line."
    return "unverified", "no test run was found" + (" after the edits." if edited else ".")


# -- plain HTTP routes ----------------------------------------------------------------------------


@mcp.custom_route("/", methods=["GET"])
@mcp.custom_route("/healthz", methods=["GET"])
async def about(request: Request) -> Response:
    return PlainTextResponse(
        f"Truthstone checks {VERSION}: a read-only MCP server at /mcp. It checks shell commands, test "
        "edits and test runs against Truthstone's rules, and stores nothing.\n"
    )


@mcp.custom_route("/.well-known/openai-apps-challenge", methods=["GET"])
async def challenge(request: Request) -> Response:
    token = os.environ.get(CHALLENGE_ENV, "").strip()
    return PlainTextResponse(token) if token else PlainTextResponse("not found\n", status_code=404)


app = mcp.streamable_http_app(
    stateless_http=True,
    json_response=True,
    max_request_body_size=1024 * 1024,
    # A public, unauthenticated, read-only service: there is nothing for DNS rebinding to reach,
    # and the default (localhost-only Host headers) would refuse the public hostname.
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)
