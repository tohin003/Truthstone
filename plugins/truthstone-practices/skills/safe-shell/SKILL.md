---
name: safe-shell
description: Use before running a shell command that deletes or overwrites files, rewrites or force-updates git history, discards uncommitted work, changes permissions recursively, alters or drops database objects, publishes or deploys, or runs a script downloaded from the internet. Runs a short pre-flight covering the exact target, reversibility, a safer alternative and authorization, and asks the user before any irreversible step they did not explicitly request.
license: Apache-2.0
---

# Safe shell

Most commands need no ceremony. Building, testing, reading, and deleting a known build directory inside the project are ordinary work. This pre-flight is for the few commands whose effects cannot be undone.

## Commands that need the pre-flight

- **Recursive deletion** of a root path, the home directory, anything outside the project, or a path built from a variable. An empty or unset variable can turn the path into the filesystem root.
- **Rewriting shared history**: force-pushing, especially to a default or shared branch, or deleting remote branches or tags.
- **Discarding work**: a hard reset, a forced clean of untracked files, a checkout or restore that overwrites local edits, or dropping a stash.
- **Destroying data**: dropping or truncating tables, databases or schemas, or a delete or update without a narrowing condition.
- **Running code you haven't read**: piping a downloaded script straight into a shell or an interpreter.
- **Loosening permissions**: making files world-writable, or changing ownership or permissions recursively.
- **Writing to disks or devices**: formatting a disk, or writing directly to a block device.
- **Publishing or deploying**: releasing a package, deploying to production, or applying or destroying infrastructure.

## The pre-flight

Before running the command, answer these four questions in one to three lines.

If the Truthstone checks tools are available, first call `check_shell_command` with the exact command line, and use its matched rules and any safer form in your answers. It reads the text and runs nothing, and a "clean" result is not authorization. Without the tools, answer the questions yourself.

1. **Target.** What exactly will the command touch? Expand variables and globs first: print the resolved path, list the files, or use the tool's dry-run or preview mode. When a variable appears in a destructive path, write it as `${VAR:?}` so the shell stops if the variable is empty.
2. **Reversibility.** Can the effect be undone, and how?
3. **Safer path.** Is there a narrower or reversible way to get the same result? For example:
   - make a backup branch or stash before a reset
   - use a lease-protected force push instead of a plain one
   - wrap destructive SQL in a transaction, or take a backup first
   - download a script and read it before running it
   - grant specific permissions instead of world-writable ones
   - delete the named files instead of a whole directory
4. **Authorization.** Did the user ask for this specific effect on this specific target?
   - If yes, proceed, and report what changed.
   - If not, or if the request was general (for example "clean up the repo"), don't run the irreversible step. Show the pre-flight and ask. A general instruction does not authorize an irreversible step.

## Always

- **Respect the platform's safeguards.** Use its approval and sandbox prompts, and never look for ways around them. Don't disable hooks, skip verification flags or bypass confirmations unless the user explicitly asks you to.
- **Keep secrets out of the transcript.** Don't print environment variables, tokens, key files or credentials to inspect them. To check that a variable is set, test it without echoing its value.
- **Stay in the project.** Prefer commands that are scoped to the project directory.
- **Explain recovery.** After an irreversible command, say what changed and how to recover if recovery is possible, for example from the reflog, a backup or a snapshot.

The user's explicit instructions, repository instructions such as AGENTS.md, and the platform's safety rules take priority over this skill. When one of them conflicts with a step, follow it and say which step you skipped.
