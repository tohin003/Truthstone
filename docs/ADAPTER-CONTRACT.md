# The adapter contract

An adapter connects one host (Claude Code, Codex, …) to the AgentGuard core. It does two
things and makes no policy decision of its own:

1. **inbound:** translate the host's hook payload into the core's `AgentEvent`;
2. **outbound:** spell the core's `Decision`, as rendered by the core's ladder for this
   host's capabilities, in the host's hook JSON.

Invariants every adapter keeps, whatever the core decides:

- **Fail open.** Any error, timeout or unknown input means "no opinion" (`{}`; the daemon
  answers `200 {}`). A hook process never exits 2.
- **Never a grant.** Nothing renders `allow`/approve as a permission, and nothing renders
  `defer`. The ladder has no kind for either.
- **Never silently.** A session that is not being guarded is told so (see the daemon's
  `/health` `degraded` list), and a deny, ask or block always carries a reason.
- **No LLM.**

Sections: [(a) tool results](#a-the-tool-result-contract) ·
[(b) capabilities and the ladder](#b-host-capabilities-and-the-rendering-ladder) ·
[(c) canonical fields](#c-canonical-fields-the-core-reads-when-present) ·
[(d) the adapter protocol](#d-the-adapter-protocol-and-registry)

## (a) The tool-result contract

A post-tool event (`EventType.POST_TOOL_USE` or `POST_TOOL_FAILURE`) carries the tool's
result in `AgentEvent.result`. For a shell command, that result is:

```python
{"stdout": str, "exit_code": int | None, "interrupted": bool}
```

| Field | Meaning |
|---|---|
| `stdout` | The command's output (stdout and stderr as the host merged them). |
| `exit_code` | The exit status when the host reports it. `None` means **unknown, never "passed"**. |
| `interrupted` | The user or the host stopped the command before it finished. |

Where each host's exit code comes from:

- **Claude Code.** A non-zero shell exit never arrives as `PostToolUse`. It arrives as
  `PostToolUseFailure` with `error = "Exit code N\n<output>"` and no `tool_response`; the
  adapter lifts `N` into `exit_code` and the rest into `stdout`
  (`translate.failure_result`). Without an exit line (the shell could not start), the
  whole message is `stdout` and `exit_code` is `None`. A successful `PostToolUse` result
  has no exit-code field; Claude Code routes every non-zero exit of a test runner to the
  failure event, but its own interpreter treats exit 1 of `grep`, `rg`, `find`, `diff`,
  `test` and `[` as success.
- **Codex.** The Bash `PostToolUse` result is plain text with no exit code, and it fires
  for non-zero exits too, so `exit_code` is `None` and the core's text parsing carries
  the verdict. (`apply_patch` results start with `Exit code: N`; the adapter lifts that.)

A plain string is still accepted as a result (legacy adapters); the core treats it as
`stdout` with an unknown exit code.

### How the core interprets a test run

This is the core's side of the contract (implemented in the core, not in adapters):

1. **The exit code comes first, interpreted per runner.**
   - pytest: 1 = failed; 2, 3, 4 and 5 = no opinion (5 means no tests were collected);
   - cargo: 101 = failed;
   - any other runner: non-zero = failed;
   - for every runner, 124, 126, 127, 130, 137 and 143 (timeout, not executable, not
     found, interrupted, killed, terminated) = no opinion.
2. **The last-stage rule.** A non-zero exit counts only if the runner is the last part
   of the command, or is followed only by `&&`. A `;`, a `|` (unless `pipefail` is set)
   or a `||` after the runner masks its exit status: `pytest; echo done` and
   `pytest | tail` report the status of `echo` and `tail`. The output text still counts.
3. **Interrupted = no opinion.**
4. **The latest run per runner family decides.** A red run followed by a green run of the
   same family is green.
5. **Stale.** Source changed after the latest passing run means the pass no longer
   covers the code: unverified.

## (b) Host capabilities and the rendering ladder

`agentguard.core.hosts` holds one frozen `HostCapabilities` profile per host, verified
against that host, and one pure function, `render(decision, caps, phase) -> Rendering`,
which picks the strongest form of a decision that the host can actually carry in that
phase. Adapters spell the result; they never choose.

### Profile fields

| Field | Values | Meaning |
|---|---|---|
| `name` | str | the adapter name (`AgentEvent.agent`) |
| `can_block_pre` | bool | a pre-tool deny stops the call |
| `ask` | `native` · `fails_open` · `none` | "ask the developer" really asks; is ignored and the tool runs; does not exist |
| `rewrite` | `with_user_approval` · `with_auto_approve` · `none` | how rewritten tool input is applied |
| `allow_is_grant` | bool | an `allow` bypasses the host's own permission checks |
| `context_channels` | set of phases | phases in which extra context reaches the agent |
| `stop_continue` | `same_turn` · `new_prompt` · `none` | what a Stop block does |
| `system_message_visible` | bool | a developer-facing message reaches a person |
| `failure_event` | bool | a failed tool call arrives as its own event |
| `exit_code_in_result` | bool | a shell result carries its exit code |
| `host_continuation_cap` | int or None | the host's own limit on consecutive Stop continuations |

Phases are the core's `EventType` values: `session_start`, `user_prompt`,
`pre_tool_use`, `post_tool_use`, `post_tool_failure`, `stop`, `subagent_stop`,
`session_end`.

### The profiles

| Field | `CLAUDE_CODE` | `CODEX` | `CONSERVATIVE` (any unknown host) |
|---|---|---|---|
| `can_block_pre` | yes | yes | assumed yes: deny is what every hook-capable host implements |
| `ask` | `native` | `fails_open` ("unsupported permissionDecision:ask"; the tool runs) | `fails_open`: never relied upon |
| `rewrite` | `with_user_approval` (ask + `updatedInput` shows the modified input) | `with_auto_approve` (allow + `updatedInput`; approval policy and sandbox still apply) | `none` |
| `allow_is_grant` | yes | no | assumed yes |
| `context_channels` | session start, prompt, pre, post, post failure | session start, prompt, pre, post | none: an unknown field can invalidate a host's whole output |
| `stop_continue` | `same_turn` | `new_prompt` (the reason becomes a continuation prompt; no prompt hook fires for it) | `same_turn`: no claim about a later prompt |
| `system_message_visible` | yes | yes in the TUI and app; `codex exec` does not show it | no |
| `failure_event` | yes (`PostToolUseFailure`) | no | no |
| `exit_code_in_result` | yes (failures carry "Exit code N") | no | no |
| `host_continuation_cap` | 8 | none documented | unknown |

`hosts.capabilities_for(agent)` returns the profile for an `AgentEvent.agent` value and
`CONSERVATIVE` for anything it does not know. A new adapter registers its profile with
`hosts.register_profile(caps)`. `translate.CLAUDE` (the Claude adapter's rendering
profile) is a subclass of `HostCapabilities` built from `hosts.CLAUDE_CODE`; the Codex
adapter renders with `hosts.CODEX` (`render.CODEX_0_166` is the same object).

### The ladder

`render` returns a `Rendering`: `kind` (one of `silent`, `deny`, `ask`, `context`,
`block`, `rewrite_ask`), `reason`, `updated_arguments`, `context`, `system_message` and
`expects_continuation`. A `deny`, `ask`, `block` or `rewrite_ask` always has a non-empty
reason ("AgentGuard objected to this action." when the decision had none).

| Decision | Before a tool | After a tool | After a failed tool | Prompt | Session start | Stop, subagent stop | Session end |
|---|---|---|---|---|---|---|---|
| ALLOW (+ context) | context | context | context | context | context | context (+ the unverified-finish notice) | silent |
| CHALLENGE, BLOCK | **deny**; else context¹; else record-only | **block** (+ context) | context: reason, then context | BLOCK: **block**; CHALLENGE: context only | context only | **block**²; else a notice to the developer | silent |
| REQUEST_REVIEW, sign-off required | **ask** where native; else **deny**: "needs developer sign-off: ask the user to confirm, then re-run." + the reason, and a system message to the developer | context: reason | context: reason | context: reason | context only | context: reason | silent |
| REQUEST_REVIEW, advisory | **ask** where native; else context: reason | context: reason | context: reason | context: reason | context only | context: reason | silent |
| MODIFY | **rewrite_ask** where `rewrite = with_user_approval` and there are rewritten arguments; else **deny** showing the guarded form to re-issue | context only | context only | context only | context only | context only | silent |

Every "context" happens only if that phase is in the profile's `context_channels`;
otherwise the rendering is silent (the decision is still recorded). "Context only" means
the decision's `additional_context`; "context: reason" means the decision's reason.

1. A host that cannot block before a tool gets the objection as context; if only its
   post-tool phase has a channel, the adapter delivers it with the tool's result.
2. Where the profile's `stop_continue` is `new_prompt`, `expects_continuation` is set:
   the continuation arrives as a prompt that belongs to the current task. Where the host
   cannot continue at all, the developer is told the turn ended unverified.

The developer-facing `system_message` appears only where `system_message_visible`: on a
sign-off deny ("AgentGuard is holding this for your sign-off: …"), and at Stop for an
unverified finish ("AgentGuard: this turn ended unverified — …").

### How each adapter spells a rendering

| `kind` | Claude Code | Codex |
|---|---|---|
| `silent` | `{}` | `{}` (print nothing) |
| `deny` | `hookSpecificOutput: {hookEventName, permissionDecision: "deny", permissionDecisionReason}` | the same, reason stripped (Codex rejects an empty one) |
| `ask` | `hookSpecificOutput: {hookEventName, permissionDecision: "ask", permissionDecisionReason}` | not produced by `CODEX` |
| `rewrite_ask` | `hookSpecificOutput: {hookEventName, permissionDecision: "ask", permissionDecisionReason, updatedInput, additionalContext}` | not produced by `CODEX`; would be spelled as a deny |
| `block` | `{decision: "block", reason}`, plus `hookSpecificOutput.additionalContext` after a tool | the same; Stop never carries `hookSpecificOutput` |
| `context` | `hookSpecificOutput: {hookEventName, additionalContext}` | the same, text stripped |
| `system_message` | top-level `systemMessage` | top-level `systemMessage` |

Two adapter-level details sit outside the ladder:

- **Claude Code's Stop** is still rendered by `translate._stop_out` (the completion gate's
  own path, including the gate-gave-up notice). It will move onto the ladder with
  `Decision.unverified_finish`.
- **Codex's `ENABLE_REWRITES`** (off) restores MODIFY as `allow` + `updatedInput` for a
  Bash call. It is the only path that bypasses the ladder, and it is never a grant on
  Codex (`allow_is_grant` is false: approval policy and sandbox still apply).

## (c) Canonical fields the core reads when present

`AgentEvent` accepts extra fields (`extra="allow"`), so an adapter can set these before
the core declares them. The core reads each one only if it is present.

| Field | Shape | Source today | What the core does with it |
|---|---|---|---|
| `AgentEvent.pending_tasks` | list of the host's background tasks still running at Stop | Claude Code Stop `background_tasks` (`{id, type, status, description, command}`) | a test run still in flight is not a verdict; the gate does not call the turn verified or failed on it |
| `AgentEvent.host_hints` | `{"read_only": bool, "tests_waived": bool}` | adapters that know (a host's own read-only flag; an explicit waiver) | `read_only` skips the write-path checks; `tests_waived` stops the gate demanding a test run |
| Delete vocabulary | tool `"Delete"` with `file_path`; a move is a `Write` at the destination plus a `Delete` of the source | Codex `apply_patch` (`Delete File`, `Move to`) | a deletion is a change to the workspace, recorded as one |
| `Decision.unverified_finish` | `str` or `None` | the completion gate, when it stops holding a turn open with a problem unresolved | adapters show it to the developer: Claude Code via `systemMessage`, Codex via `systemMessage` where it is visible (the ladder renders it as `Rendering.system_message` at Stop) |

## (d) The adapter protocol and registry

An adapter is a module with:

- `to_event(payload) -> AgentEvent | None` — `None` for payloads the core should not see;
- `from_decision(event, decision, hook_name) -> dict` — the hook's stdout JSON; `{}` is
  "no opinion";
- optionally `handle_payload(guard, payload) -> dict` — for hosts whose one payload stands
  for several actions (a Codex patch editing several files): it calls `guard.handle` per
  action and combines the answers. When present, the daemon uses it instead of the
  three-step path.

The daemon serves each adapter at `POST /hook/<name>` (`claude-code`, `codex`) and lists
the names under `adapters` in `/health`.
