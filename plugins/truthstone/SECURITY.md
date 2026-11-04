# Security policy

## Scope

This plugin runs code on your machine. Every hook runs `hooks/truthstone-hook.sh`, a POSIX script that
does nothing outside a git work tree. Otherwise it hands the event to the Truthstone runtime:
an installed `truthstone-codex-hook`, or a private copy that the session-start hook installs once with
`uv` into Codex's data folder for this plugin, from `git+https://github.com/tohin003/Truthstone@v0.1.0-dev.0`. With
`TRUTHSTONE_NO_BOOTSTRAP=1` nothing is installed. The runtime talks only to its own daemon
on `127.0.0.1`, which authenticates every request with a bearer token stored owner-only
under `~/.truthstone`. Nothing is sent off the machine, and the plugin has no MCP servers.
`README.md` lists everything the plugin runs, sends, fetches and stores.

Codex runs these hooks only after you review and trust them in `/hooks`, and asks again
after any change to the plugin's files.

Truthstone's safety contract, and so what counts as a vulnerability here:

- **It never grants permissions.** No hook output may approve a tool call on the user's
  behalf.
- **It fails open.** If Truthstone is broken or missing, Codex works as if it were not
  installed. It never blocks the agent because of its own failure, and the launcher never
  exits 2.
- **It never fails silently.** A session that is not guarded is told so.
- **It never runs code from the repository it guards.**
- **The daemon stays local.** It must be reachable only from `127.0.0.1`, and only with the
  token.
- **It does nothing outside a git work tree**, and installs nothing when told not to.

A break in any of these is a security issue. So is a way to reach or impersonate the daemon,
to read the token, or to make the launcher install something other than the pinned
Truthstone release.

## Reporting a vulnerability

Report vulnerabilities privately, not in a public issue:

- through GitHub's private vulnerability reporting for https://github.com/tohin003/Truthstone: open the **Security** tab and
  select **Report a vulnerability**; or
- by email to Tohin Majumder, tohin1400@gmail.com.

Other ways to reach the maintainer are listed at https://github.com/tohin003/Truthstone/blob/master/docs/legal/SUPPORT.md.

## Supported versions

Only the latest release receives fixes. Update the plugin before you report a problem.
