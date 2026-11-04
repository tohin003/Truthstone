# Security policy

## Scope

This plugin runs code on your machine. Its hooks run two shell scripts in `scripts/`, and
those hand each event to the Truthstone runtime: a Python package that is not part of the
plugin. Outside a git work tree both scripts exit at once and do nothing.

- `scripts/session-start.sh` is the only part that installs anything. On the first session
  in a git repository, and after each plugin update, it installs the runtime with `uv`
  into the plugin's own data directory, from the GitHub release tag that matches the
  plugin version (`git+https://github.com/tohin003/Truthstone@v<version>`), with its
  dependencies from the Python Package Index. With `TRUTHSTONE_NO_BOOTSTRAP=1` it installs
  nothing and uses a runtime you installed yourself. It then starts a local daemon bound to
  `127.0.0.1`, which authenticates every request with a bearer token stored owner-only
  under `~/.truthstone`.
- `scripts/hook.sh` hands every other event to that runtime's forwarder, which talks only
  to the daemon. It installs and downloads nothing.
- `scripts/command.sh` runs the `/truthstone:*` commands when you type them.

Nothing is sent off the machine, and the plugin has no MCP servers. `README.md` lists
everything the plugin runs, sends, fetches and stores.

Truthstone's safety contract, and so what counts as a vulnerability here:

- **It never grants permissions.** No hook output may approve a tool call on the user's
  behalf (`permissionDecision: "allow"`), or skip the user's own approval prompt.
- **It fails open.** If Truthstone is broken or missing, Claude Code works as if it were
  not installed. It never blocks the agent because of its own failure.
- **It never fails silently.** A session that is not guarded is told so.
- **It never runs code from the repository it guards.** Hooks run inside your project,
  and nothing there may be imported or executed by them.
- **The daemon stays local.** It must be reachable only from `127.0.0.1`, and only with
  the token.
- **It does nothing outside a git work tree**, and installs nothing when told not to.

A break in any of these is a security issue. So is a way to reach or impersonate the
daemon, to read the token, or to make the installer fetch something other than the
pinned Truthstone release.

## Reporting a vulnerability

Report vulnerabilities privately, not in a public issue:

- through GitHub's private vulnerability reporting for
  https://github.com/tohin003/Truthstone: open the **Security** tab and select **Report a
  vulnerability**; or
- by email to Tohin Majumder, tohin1400@gmail.com.

Other ways to reach the maintainer are listed at
https://github.com/tohin003/Truthstone/blob/master/docs/legal/SUPPORT.md.

## Supported versions

Only the latest release receives fixes. Update the plugin (`/plugin update`) before you
report a problem.
