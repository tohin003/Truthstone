"""Normalized, agent-agnostic event model (SPEC §23).

    "The core does not care which agent generated the event."

Adapters (Claude Code, Cursor, Codex, ...) translate their host's native payloads into
`AgentEvent`, and translate a `Decision` back into whatever their host understands.
Nothing below this line may branch on `event.agent`.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from truthstone.core.enums import EventType

# Tools that cannot change anything. Used to short-circuit the validation pipeline at
# Level 0 so ordinary exploration costs essentially nothing (SPEC §7, §8).
READ_ONLY_TOOLS: frozenset[str] = frozenset(
    {"Read", "Glob", "Grep", "WebFetch", "WebSearch", "NotebookRead", "TodoWrite", "ListMcpResources"}
)

# Tools that write to the workspace. These get the full pipeline.
MUTATING_TOOLS: frozenset[str] = frozenset({"Edit", "Write", "MultiEdit", "NotebookEdit"})

# A file removal (`arguments["file_path"]`). Not one of Claude Code's tools — Claude
# deletes through Bash — but the core's vocabulary for one: the Codex adapter maps a
# patch's `*** Delete File` to it, and a move to a Write of the destination plus a
# Delete of the source. A deletion is a change: it is validated, and the Completion Gate
# still asks for the tests that covered the deleted file (G5).
DELETE_TOOLS: frozenset[str] = frozenset({"Delete"})

# Tools that run a shell command (`arguments["command"]`): where test runs come from.
# PowerShell is Claude Code's primary shell on Windows, and its failing runs reach the
# core through the same PostToolUseFailure contract as Bash's.
SHELL_TOOLS: frozenset[str] = frozenset({"Bash", "PowerShell"})


class AgentEvent(BaseModel):
    """One thing an agent did or is about to do."""

    model_config = ConfigDict(extra="allow")

    event: EventType
    agent: str = "unknown"
    workspace: str = "."
    session_id: str = ""
    task_id: str | None = None

    # Tool events
    tool: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    tool_use_id: str | None = None
    result: Any = None

    # Prompt / message events
    prompt_text: str | None = None
    last_assistant_message: str | None = None

    # Stop: work the host is still running in the background, one dict per task with
    # `id`, `type` ("shell", ...), `status` ("running", ...) and `command`. A test run
    # still in flight is not a verified finish (G7). Adapters fill it where the host
    # reports it (Claude Code: Stop's `background_tasks`).
    pending_tasks: list[dict[str, Any]] = Field(default_factory=list)

    # What the host knows that a payload does not say (H5). Recognised keys:
    #   read_only: bool    — this tool cannot change the workspace (an embedding host's own
    #                        searches, git reads, snapshot test runs); it skips validation
    #                        and touches nothing. Only True adds read-only-ness.
    #   tests_waived: bool — on a prompt: the host's own answer to "were tests waived?",
    #                        which overrides the prompt lexicon either way.
    # Upstreamed from Pebble's vendored seams (`raw["host_read_only"]`, `tests_waiver`).
    host_hints: dict[str, Any] = Field(default_factory=dict)

    # Host-specific extras kept verbatim so adapters can round-trip without loss.
    raw: dict[str, Any] = Field(default_factory=dict)

    event_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    ts: float = Field(default_factory=time.time)

    # Internal routing state.  A rejected explicit task id is intentionally cleared
    # before persistence, but must not become indistinguishable from an event that never
    # carried a task id: the latter may resolve to the session's current task.
    _task_id_rejected: bool = PrivateAttr(default=False)
    # The edited file as it was when the action was proposed, for checks that run after the
    # action did (WP9): `evidence.extractors.resolve_edit` prefers it to the disk.
    _before: str | None = PrivateAttr(default=None)
    # Judged and recorded by the workspace's worker, not where it was answered (WP9).
    _decided_later: bool = PrivateAttr(default=False)

    @property
    def is_read_only(self) -> bool:
        return self.tool in READ_ONLY_TOOLS or self.host_hints.get("read_only") is True

    @property
    def is_mutating(self) -> bool:
        if self.host_hints.get("read_only") is True:
            return False
        return self.tool in MUTATING_TOOLS or self.tool in DELETE_TOOLS

    @property
    def is_delete(self) -> bool:
        return self.tool in DELETE_TOOLS

    def arg(self, name: str, default: Any = None) -> Any:
        return self.arguments.get(name, default)
