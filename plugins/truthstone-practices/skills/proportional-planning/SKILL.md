---
name: proportional-planning
description: Use when starting a coding task to decide how much planning it deserves. Keeps small mechanical changes direct, and plans deeply when the work crosses service boundaries, touches security, data or a public interface, has an open-ended goal, or is hard to reverse. Produces a plan sized to the task, with the evidence that justifies its size.
license: Apache-2.0
---

# Proportional planning

Aim for the least complex solution that is correct enough for the requirements, the architecture, the risk and the evidence. That is not always the smallest plan, and not always the most detailed one.

## 1. Size the task

Weigh these eight signals. For each one that matters, cite what you saw.

- **Scope**: how many files and directories are involved.
- **Dependencies**: new or changed packages or services.
- **Architectural impact**: new components or changed boundaries.
- **Data risk**: whether stored data could be lost or corrupted.
- **Security risk**: authentication, permissions, secrets, untrusted input.
- **Uncertainty**: how clearly the request says what it wants.
- **Blast radius**: how much depends on the code that changes.
- **Reversibility**: whether the change can be undone cleanly.

Then pick a depth:

| Depth | When | Plan |
|---|---|---|
| Direct | Small, clear and low risk | One line stating the approach |
| Light | A few files and a clear goal | Three to five steps |
| Structured | Several components, or real risk | Steps, risks and how you will verify |
| Deep | Architectural, cross-service, high-risk or open-ended | Investigate first, then plan, then confirm the scope |

## 2. Apply the override rules

The signals don't simply add up. These rules take precedence:

- **Mechanical work stays direct.** Renaming, moving or deleting a small, identified target is direct even when it has many call sites. Many call sites make a change tedious, not complex. The exception is when the change crosses service boundaries or touches data or security.
- **Reuse what already exists.** If the repository already implements the capability, the task is to use it, and light planning is enough.
- **Work that is hard to undo needs structure.** Data migrations, deletions, removing a public API and published releases need at least a structured plan, however small the change.
- **Crossing service boundaries with security, data or architectural risk makes a task deep.**
- **An open-ended quality bar makes a task deep.** For "make it production-ready" or "make it scale" with no specific target, the first task is deciding what the task is. Establish the scope and confirm it before writing code.
- **An unspecified change to a public interface makes a task deep.** If the request changes an API, schema or protocol without saying what change, find out what is wanted first.

## 3. Write a plan of that size

**Direct or light**: four lines at most, with the steps chained on the first line. For example:

    Approach: find all references → rename → run the affected tests
    Already here: src/utils/pagination.py:10 (paginate), so reuse it
    Not needed here: new abstraction or service layer, new dependency, caching layer, restructuring unrelated code
    Verify with: the existing test suite, to prove no reference was missed

Use the approach that fits the request:

- **Fix**: reproduce → locate the cause → fix → test.
- **Add**: find the existing pattern → implement → test.
- **Remove**: find all references → remove → test.

**Structured or deep.** Say plainly that the depth is justified, and give the top reasons. Then list what to investigate before implementing. Always include:

- failure modes and degradation
- observability: what you will be able to see when it misbehaves
- deployment and rollback
- testing proportional to the risk

Add the questions specific to the domain:

- **Distributed systems**: state ownership and consistency, cache invalidation, concurrency and partial failure.
- **Authentication**: token lifetime, refresh and revocation; what a compromise of each component exposes; and migration for credentials already issued.
- **Databases**: the migration and its reverse, integrity constraints, and query plans at production volume.
- **APIs**: the contract and backward compatibility, input validation and error responses, and the latency budget.
- **ML and LLM systems**: versioning and reproducibility, evaluation cases (including known failures), drift and cost.
- **Frontend**: state ownership, accessibility, and loading, empty and error states.
- **Infrastructure**: change review, cost, rollout and health checks, and how secrets are handled.

## 4. Keep the size honest

- **Allow complexity when the evidence supports it.** If a heavier design is needed, cite why, for example "three existing consumers with independent business rules". Don't strip out design the task needs.
- **Resize the plan when the evidence changes.** If a direct task starts touching many files, stop and reassess with the user.
- **Match approval to the plan's depth.** Don't ask for approval of a direct plan. For deep or open-ended work, confirm the scope before implementing.

The user's explicit instructions, repository instructions such as AGENTS.md, and the platform's safety rules take priority over this skill. When one of them conflicts with a step, follow it and say which step you skipped.
