"""Action Validator (SPEC §18).

    Agent proposal -> Evidence check -> Scope check -> Architecture check
                   -> Risk check -> Complexity check -> Decision

    ALLOW · BLOCK · CHALLENGE · MODIFY · REQUEST_REVIEW

The pipeline is ordered by cost, and it stops as soon as the answer is known. Read-only
tools never enter it at all; a mutating tool pays a Level-0 pass over its own arguments
before anything touches the index (SPEC §7, §8).

Which decision a finding produces is a judgement about *authority*, not severity:

* **CHALLENGE** — AgentGuard has evidence the agent appears not to have. Hand it back and
  let the host reason (SPEC §21). This is the common case.
* **REQUEST_REVIEW** — the action may be entirely correct, but it is irreversible and only
  the developer can say. Force-pushing is not AgentGuard's call to make.
* **BLOCK** — reserved. Nothing currently produces it: every case examined so far is
  better served by challenging the agent or asking the human.
"""

from __future__ import annotations

import logging

from agentguard import evidence
from agentguard.challenge import render as render_challenge
from agentguard.challenge.ledger import ChallengeLedger
from agentguard.core.enums import DecisionAction, EscalationLevel, Verdict
from agentguard.core.events import AgentEvent
from agentguard.core.models import Decision, Finding
from agentguard.core.taskstate import TaskState
from agentguard.repo.index import RepoIndex
from agentguard.validate import checks, modify

log = logging.getLogger(__name__)


def validate(
    event: AgentEvent,
    index: RepoIndex,
    state: TaskState | None,
    ledger: ChallengeLedger,
    task_id: str | None,
) -> Decision:
    """One proposed action in, one decision out. Never raises."""
    findings: list[Finding] = []
    level = EscalationLevel.DETERMINISTIC

    # -- Level 0: the action's own arguments, no repository access ----------------
    #
    # Rewriting comes first, deliberately. A safe narrowing *fixes* the problem, where an
    # objection only describes it — so when a dangerous command has a provably-narrower
    # form, taking it is better than interrupting anyone. `modify.propose` re-checks its
    # own output, so anything it cannot make safe falls straight through to the risk
    # checks below and is escalated instead.
    rewrite = modify.propose(event)
    if rewrite is not None:
        finding = modify.finding_for(rewrite, event)
        return Decision(
            action=DecisionAction.MODIFY,
            level=EscalationLevel.DETERMINISTIC,
            updated_arguments=rewrite.arguments,
            additional_context=f"{finding.summary}. {finding.detail}",
            reason=finding.summary,
            findings=[finding],
        )

    findings.extend(checks.risky_command(event))

    # A command needing human sign-off is decided here; nothing further is relevant.
    human = [f for f in findings if f.verdict is Verdict.REQUIRES_HUMAN]
    if human:
        return _review(findings, human)

    if not index.is_built:
        return Decision.allow()

    # -- Level 1: repository evidence ---------------------------------------------
    level = EscalationLevel.REPOSITORY
    findings.extend(evidence.check(event, index))

    path = _edited_path(event, index)
    if path:
        findings.extend(checks.pattern_consistency(event, index, path))
        findings.extend(checks.dependency_added(event, index, path))

    if state is not None:
        findings.extend(checks.scope_creep(state, index))

    if not findings:
        return Decision.allow(level)

    # -- Level 2: hand the problem to the host ------------------------------------
    verdict = ledger.admit(task_id, findings)
    if not verdict.should_challenge:
        # Recorded for the log; the agent is not interrupted. Either it has heard this
        # already, or the task's challenge budget is spent (SPEC §17, §39).
        return Decision(
            action=DecisionAction.ALLOW,
            level=level,
            findings=findings,
            reason=verdict.reason,
        )

    ledger.record(task_id, verdict.raise_now)
    if state is not None and any(f.category.value == "scope" for f in verdict.raise_now):
        state.scope_challenged = True

    return Decision(
        action=DecisionAction.CHALLENGE,
        level=EscalationLevel.HOST_CHALLENGE,
        reason=render_challenge(verdict.raise_now),
        findings=findings,
    )


def _review(findings: list[Finding], human: list[Finding]) -> Decision:
    """Ask the developer, every time (IMPROVEMENTS.md A1).

    A review request is not a challenge, and the ledger's rationing must never touch it.
    Rationing assumes the recipient can answer — "the agent has heard this and chosen to
    proceed" — but the recipient here is the developer, and AgentGuard cannot see whether
    they approved or refused. So:

    * no "once per concern": an identical retry is asked again (on a host without a
      native ask, a retry after a refused sign-off would otherwise simply run);
    * no task budget: an irreversible command after six challenges is still asked;
    * no "no task context" silence: a command before the first prompt is still asked.

    Pebble behaves the same way (`shell_policy.py`: deleting outside the workbench is "a
    gate no setting waives"). The ask is still recorded: the engine persists this decision
    and its findings, which is the log. It is never written to the challenge ledger, so it
    never spends the advisory budget the agent-facing challenges share.
    """
    return Decision(
        action=DecisionAction.REQUEST_REVIEW,
        level=EscalationLevel.DETERMINISTIC,
        reason=render_challenge(human),
        findings=findings,
        # Every REQUEST_REVIEW produced here is an irreversible command: the developer
        # must say yes, so a host whose `ask` fails open renders this as a deny rather
        # than letting it through (core/hosts.py, H1).
        signoff_required=True,
    )


def _edited_path(event: AgentEvent, index: RepoIndex) -> str:
    raw = event.arg("file_path") or event.arg("notebook_path")
    return index.normalize(raw) if isinstance(raw, str) and raw else ""
