---
name: evidence-before-done
description: Use before telling the user that a coding task is done, fixed, passing or ready to merge, and when a hook, CI job or reviewer reports that verification is missing. Builds a requirement ledger from the user's own words, ties each requirement to evidence gathered after the last edit (test output, command output, file:line), and reports every item as verified, failed or not verified instead of claiming success.
license: Apache-2.0
---

# Evidence before done

"Done" is a claim, so it needs evidence like any other claim. This protocol replaces "Done, all tests pass" with a short report the user can check.

Skip it for replies that changed nothing. For a one-line change, the whole protocol fits in three lines.

## 1. Build the requirement ledger

Reread the request, and any earlier messages in this conversation that still apply. Write down every sentence the user could check, quoting their words:

- **Deliverables**: what to add, fix, change or remove.
- **Constraints**, for example "the whole suite must pass", "the output must stay identical to `expected.txt`" or "keep the public API".
- **Prohibitions**, for example "don't edit the tests", "leave `config.toml` alone", "don't change anything else" or "don't push".

Count prohibitions as requirements. They are the easiest to break without noticing. Only checkable sentences belong in the ledger. Record a vague wish such as "make it cleaner" as a judgement call, not as something you verified.

## 2. Gather evidence for each requirement

Pick the evidence that would convince a skeptical reviewer.

| Change | Evidence |
|---|---|
| Bug fix | A regression test that fails without the fix and passes with it |
| New behavior | Tests for the behavior, including edge cases |
| Refactor | The existing tests, unchanged, still passing |
| Rename or removal | The full suite, plus a repository-wide search showing no remaining references |
| Performance | A measurement before and after, not just passing tests |
| Migration | Evidence that old and new behavior are equivalent |
| API, database, UI, model or infrastructure change | Contract tests, migration and integrity checks, component or end-to-end tests, evaluation metrics, or configuration and deployment validation |
| Prohibition | `git status` or `git diff --stat` showing the protected paths untouched |

Rules for evidence:

- **Run the tests that cover what you changed.** That means the tests for each changed file and for the code that imports it. Use the project's own command from its configuration, scripts or Makefile.
- **Gather evidence after your last edit.** If you edited after a run, run again.
- **Check that every changed source file still parses or compiles.** It is the cheapest check there is.
- **Treat incomplete output as proof of nothing.** That covers a run that timed out, was cut off or was interrupted, and output you did not read.
- **Reread any file you cite if it could have changed since you read it.**
- **Skip tests that add nothing.** Changes only to documentation or comments, projects without a test runner, and requests that waive tests ("no need to run the tests") don't need a run. Say which case applies.
- **Report untested code.** If you changed code that no test covers, in a project that otherwise tests its code, and you added no test, say so.

## 3. Classify each requirement, then the task

Each ledger item is exactly one of:

- **Verified.** Quote the evidence: the command and its result line, or `path:line`.
- **Failed.** The evidence shows the requirement is not met. Fix it or report it, and don't call the task done.
- **Not verified.** No evidence could be gathered, because no runner exists, commands cannot run here, or the output was unreadable. Say what blocked the check and give the exact command the user can run. "Could not tell" is never reported as a pass, and never as a failure.

Then give the task as a whole one of these statuses:

- **Done**: only when every item is verified or explicitly waived.
- **Incomplete**: work or verification remains.
- **Verification failed**: the evidence shows something is broken.
- **Needs your decision**: the remaining call belongs to the user.

## 4. Check your own summary for open doubts

Before sending, read your draft. Part of the request is still open if the draft says any of these:

- you "couldn't confirm" something
- you are "not sure"
- a decision goes back to the user ("if you know it's generated, it's safe to delete")

Settle the doubt with the project's evidence: read the file, script or build step that decides it, and act within what the request asks. If it stays open, report that item as open and don't describe the task as done.

## 5. Report

Lead with the status, then list the ledger. For example:

    Status: done. 3 of 3 requirements verified.
    R1 "fix the pagination off-by-one": verified. tests/test_pager.py::test_last_page fails before the fix and passes after it.
    R2 "keep the public API": verified. The signature of paginate() at src/pager.py:12 is unchanged; only its body changed.
    R3 "the whole suite must pass": verified. `pytest -q` after the last edit printed "214 passed".

Say exactly what ran. "Ran tests/test_pager.py: 12 passed. The full suite was not run" is a report. "All tests pass" is not a report unless you ran all of them. If you believe a failure predates your change, show it, for example the same test failing on the base commit. Don't just assert it.

## Never

- Never delete, skip, loosen or rewrite a test to make it pass unless the user asked for that. Report the failure instead.
- Never present "not verified" as "done".

The user's explicit instructions, repository instructions such as AGENTS.md, and the platform's safety rules take priority over this skill. When one of them conflicts with a step, follow it and say which step you skipped.
