---
name: diff-review
description: Use before finishing a coding task, before committing or opening a pull request, and when asked to review a change. Compares the complete diff with the user's request, checking that every requirement is addressed, nothing unrequested changed, no references went stale after a rename or removal, no tests were weakened or deleted, and every new dependency or file is explained.
license: Apache-2.0
---

# Review the diff against the task

Review what will ship, not what you remember writing.

## 1. Collect the whole change

Collect staged and unstaged changes and new untracked files: run `git status --porcelain` and `git diff HEAD`, then read each untracked file. Include changes made by code generators and formatters. Outside git, use the list of files you edited and reread each one.

## 2. Compare the change with the request

Work through this list and record `path:line` for every problem.

1. **Coverage.** Every requirement in the request maps to a change. A requirement with no matching change means the task is not finished.
2. **Nothing unrequested.**
   - The task explains every changed file.
   - There is no unrelated reformatting, debug print, commented-out code, stray TODO or temporary file.
3. **Stale references after a rename, move or removal.** Search the whole repository for the old name: code, tests, documentation, configuration and scripts. Include string forms such as dynamic imports, route names, serialized field names and CLI help text. Every remaining hit is a bug, unless you can state a reason for it to stay.
4. **Changed signatures and defaults.**
   - Every caller is updated.
   - Default values, error behavior and return shapes are unchanged unless the request asked for a change.
   - Public interfaces stay backward compatible unless the user agreed to break them.
5. **Weakened tests.** Treat any of these as a finding unless the request asked for it:
   - a deleted test
   - a new skip or expected-failure marker
   - a loosened assertion, such as exact to approximate, or equality to merely truthy
   - an expected value edited to match the new output without an explanation
   - a raised timeout
   - narrowed test inputs

   If the request said not to modify the tests, any change to them is a violation.

   If the Truthstone checks tools are available, call `check_test_edit` for each changed or deleted test file, with its full content before and after, and include what it reports. Without the tools, check the list above by reading the diff.
6. **Untested changes.** Mention changed code that no test covers, when the project otherwise tests its code and you added no test.
7. **Dependencies.**
   - Every package added to a manifest has a stated reason.
   - The lockfile is updated consistently.
   - No existing package already does the job.
8. **New files.**
   - They are placed and named like their siblings.
   - They contain no secrets, credentials, `.env` files, large binaries or build output.
9. **Error handling.** No exceptions are newly swallowed, no catch-all handler is broadened, and no validation is removed.

## 3. Report

List the findings by severity. For each finding, give:

- `path:line`
- what is wrong
- why it matters for this request
- whether you fixed it or recommend a fix

Fix whatever is clearly within the task, and ask about anything that is a judgement call.

If nothing turns up, say what you checked, for example "Checked 6 files: no stale references to fetchUser, no test changes, no new dependencies." "Looks good" on its own is not a review.

The user's explicit instructions, repository instructions such as AGENTS.md, and the platform's safety rules take priority over this skill. When one of them conflicts with a step, follow it and say which step you skipped.
