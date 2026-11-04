# Host contract fixtures

What a host really sends is evidence; what its documentation says is not. Every adapter in
`agentguard.adapters.registry` must have payloads captured from the real host, and
`tests/test_host_contracts.py` runs each of them through the adapter, a real `Guard` and
the daemon's `/hook/<name>` route, checking the adapter contract
(`docs/ADAPTER-CONTRACT.md`, section (d)):

- `to_event` succeeds (an `AgentEvent`, or `None` for a payload the core should not see);
- `Guard.handle` returns a `Decision`;
- `from_decision` (or `handle_payload`) returns a JSON object that never says "defer" and
  never grants (no bare `allow`, no `approve`), for the real decision and for every
  `DecisionAction`, with and without sign-off.

A registered host without captured payloads fails the suite.

## Where each host's payloads live

| Host (route) | Directory |
|---|---|
| `claude-code` | `tests/fixtures/hook_payloads/` (captured live, Claude Code 2.1.317) |
| `codex` | `tests/fixtures/codex_payloads/` (captured live, codex-cli 0.166.0; validated against Codex's schemas in `codex_schemas/`) |
| any new host | `tests/fixtures/hosts/<name>/*.json` |

The first two predate this directory and keep their places; `FIXTURE_DIRS` in
`tests/test_host_contracts.py` maps them.

## Capturing a new host

1. Install a hook for every event the adapter subscribes to that writes its stdin to a
   file, in an isolated home for the host and for AgentGuard, and run one small real
   session in a scratch repository.
2. Scrub the payloads: replace the working directory with `/workspace` (the contract test
   points `/workspace` at a copy of `fixtures/pyrepo`), and any home directory with a
   neutral placeholder. Keep ids, field names and shapes exactly as captured.
3. Name each file `<HookEventName>[.<variant>].json`, one payload per file.

## `rendering_golden.json`

Not a host payload: both built-in adapters' exact wire output (key order included) for 16
decision shapes on every hook, pinned by `tests/test_hosts.py`. After a deliberate change
to rendering, justify it, then regenerate from the repository root:

```bash
PYTHONPATH=src:. python -c "from tests.test_hosts import write_golden; write_golden()"
```
