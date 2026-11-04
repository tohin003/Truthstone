---
name: truthstone
description: How to read and resolve Truthstone (previously named AgentGuard) feedback. Use whenever a tool call is denied or sent for review with a reason from Truthstone, when a turn is held open by "Truthstone — completion gate", when Truthstone narrows a command, or when context marked [Truthstone] appears after a prompt.
user-invocable: false
license: Apache-2.0
---

# Working with Truthstone

Truthstone runs as hooks in this session. It is deterministic and has no model of its own:
it checks your actions against the repository and the evidence you produced, and hands any
problem back to you. It never approves anything on the user's behalf. Treat what it says as
evidence to check, not as orders, and never as an obstacle to route around.

## What you will see, and what to do

**A tool call denied with "Truthstone — evidence check".** Something your action relies on
contradicts the repository: a method, file, import or dependency that is not there, or a
change that has drifted outside the task's scope. Open the cited evidence. Then either use
what exists, or, if you are deliberately introducing the missing thing, say so and define
it in the same change. For scope, explain why the extra files are needed or narrow the
change.

**A permission prompt whose reason comes from Truthstone.** The command is irreversible or
unusually broad: a force push, `git reset --hard`, `git clean -f`, a recursive delete of a
variable path, a download piped into a shell, destructive SQL. The user decides. Say what
the command will do and offer a narrower form. In a non-interactive run nobody can answer,
so the call is denied: propose the safer command instead of retrying the same one.

**A command Truthstone narrowed.** Truthstone proposed a provably narrower form, such as
guarding an unset variable before a delete, and the user is asked to approve that form. If
it is denied, issue the narrowed command yourself rather than the original.

**"Truthstone — completion gate: incomplete" or "verification_failed" when you try to
finish.** You changed code that has tests and ran none of them, the tests you ran failed,
or a changed file no longer parses. Run the suggested tests (or the project's own test
command) and report what they actually said. If they fail, fix them or report the failure.
If you cannot run them, say so plainly and say why. Never claim that tests pass when they
did not run.

**Context starting with [Truthstone] after the user's prompt.** This is a planning budget:
how complex the task looks and how much investigation it warrants. Plan in proportion. A
trivial change stays small; a deep change gets the investigation it asks for.

## Rules

- Do not retry a denied action unchanged, or reshape it only to get past the check
  (renaming, splitting a command, moving it into a script). Fix the cause, or explain and
  ask the user.
- Do not disable, uninstall or reconfigure Truthstone, and do not edit hook settings,
  unless the user asks you to.
- If you believe Truthstone is wrong, say so with your evidence (file and line) and go on
  the way the user prefers. It is often right and sometimes not. It is never the authority.
- If Truthstone reports that the session is unguarded, mention it once. The user decides
  what to do about it.

The user can run `/truthstone:doctor`, `/truthstone:log`, `/truthstone:why <id>`,
`/truthstone:report`, `/truthstone:off` and `/truthstone:on`.
