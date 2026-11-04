# Security policy

## Scope

This plugin runs code on your machine. Its hooks call `scripts/hook.sh` and a small
Python forwarder. On the first session the plugin installs the AgentGuard runtime with
`uv`, from the GitHub release that matches the plugin version, into the plugin's own data
directory. It then starts a local daemon bound to `127.0.0.1` that authenticates every
request with a bearer token stored owner-only under `~/.agentguard`. Nothing is sent off
the machine, and the plugin has no MCP servers.

AgentGuard's safety contract, and so what counts as a vulnerability here:

- **It never grants permissions.** No hook output may approve a tool call on the user's
  behalf (`permissionDecision: "allow"`), or skip the user's own approval prompt.
- **It fails open.** If AgentGuard is broken or missing, Claude Code works as if it were
  not installed. It never blocks the agent because of its own failure.
- **It never fails silently.** A session that is not guarded is told so.
- **It never runs code from the repository it guards.** Hooks run inside your project,
  and nothing there may be imported or executed by them.
- **The daemon stays local.** It must be reachable only from `127.0.0.1`, and only with
  the token.

A break in any of these is a security issue. So is a way to reach or impersonate the
daemon, to read the token, or to make the installer fetch something other than the
pinned AgentGuard release.

## Reporting a vulnerability

Report vulnerabilities privately, not in a public issue. Use GitHub's private
vulnerability reporting for https://github.com/tohin003/AgentGuard: open the **Security**
tab and select **Report a vulnerability**.

You can also contact the maintainers through the channels listed at
https://github.com/tohin003/AgentGuard/blob/master/docs/legal/SUPPORT.md.

## Supported versions

Only the latest release receives fixes. Update the plugin (`/plugin update`) before you
report a problem.
