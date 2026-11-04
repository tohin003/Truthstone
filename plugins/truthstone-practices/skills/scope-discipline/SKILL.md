---
name: scope-discipline
description: Use at the start of a coding task to state what the change will touch, and again before editing a file the request does not clearly reach, creating files in a new location, or reformatting or refactoring code nobody asked about. Keeps the change inside the task, asks before out-of-scope edits, and follows the repository's existing conventions.
license: Apache-2.0
---

# Scope discipline

Every file a change touches should be explainable from the request.

## 1. State the scope before editing

Write two or three lines covering:

- **Goal**: the request in one sentence, in the user's own terms.
- **Expected scope**: the files or modules the request names or clearly implies, plus what is connected to them. That means their callers, the code they import, and their tests.
- **Constraints**: anything the user ruled out, for example "don't touch the tests", "keep the API stable" or "no new dependencies".

If the request can be read two ways and the readings lead to different changes, ask one precise question before editing. If the difference is minor, pick the reading that changes less and say which one you chose.

## 2. Check each edit outside the expected scope

Before editing a file outside the expected scope, ask whether the task needs that edit to work.

- **Required.** For example, a caller has to change because a signature changed. The edit is in scope; note why.
- **Not required.** For example, unrelated cleanup, a refactor, reformatting, renaming, or a fix you noticed along the way. Don't make the edit. Mention it as a suggestion, or ask first.

If the work keeps spreading into files the request did not point to, stop. Either the task is bigger than it looked, so say so and confirm with the user, or the change has drifted and should be split.

## 3. Follow the repository's existing conventions

- **Mirror an existing example.** Before adding an endpoint, command, model, test or config option, find the closest one already in the repository. Copy its structure, error handling, logging and naming.
- **Put new files where that kind of file already lives.** Tests go next to the other tests and modules next to their siblings. Creating a new top-level directory is a decision to mention to the user.
- **Name new files like their siblings.** Match casing and word separators when sibling files of the same type all agree. If they disagree, there is no convention to break.
- **Prefer what the project already has.** Use existing helpers, libraries and patterns before adding new ones. A new dependency needs a stated reason.
- **Don't add structure nobody asked for.** Leave out abstraction layers, plugin systems, caching and configuration options unless the task needs them.

## 4. Check the result against the scope

Before finishing, list the files you changed with `git status` or `git diff --stat`, and compare them with the scope from step 1. For each file outside it, either explain why the task required it or revert it.

## When the user asks for a broad change

A request such as "clean up this module" or "refactor as you see fit" makes the scope broad. Follow it, and still report what you changed.

The user's explicit instructions, repository instructions such as AGENTS.md, and the platform's safety rules take priority over this skill. When one of them conflicts with a step, follow it and say which step you skipped.
