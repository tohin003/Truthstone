"""Credentials in newly written content (IMPROVEMENTS.md A11).

GitGuardian's 2026 report puts secrets in Claude Code-assisted commits at about 3.2%,
against a 1.5% baseline. A key written into a tracked file is one `git push` from public.

The rules, each chosen to keep this silent on ordinary work:

* **Only newly introduced lines.** A key that was already in the file before the edit is
  not this edit's doing, and blaming the agent for it is noise.
* **Only strict formats** — the ones with a fixed, vendor-assigned shape: AWS access key
  ids, PEM private-key headers, GitHub tokens, Slack tokens, Stripe live keys, Anthropic and
  OpenAI project keys, Google API keys. No entropy guessing.
* **Never in a gitignored file.** A key in an ignored `.env` is exactly where it belongs.
  `git check-ignore` runs only when something matched, with a short timeout; if git cannot
  answer, the check fails open (silent) and says so in the log.
* **Placeholders are not secrets:** `AKIAIOSFODNN7EXAMPLE` (AWS's documented example),
  `xxxx…`, `your_key_here`, runs of one character.
* **The secret is never repeated.** The message names the kind of credential and where it
  is, with the value masked; nothing that is stored (subject, summary, detail, evidence)
  holds it.

A finding is a CHALLENGE at HIGH (SECRET_EXPOSURE), raised once per credential per task.
"""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from agentguard.core.enums import ChallengeCategory, EscalationLevel, FailureMode, Severity, Verdict
from agentguard.core.events import MUTATING_TOOLS, AgentEvent
from agentguard.core.models import EvidenceRef, Finding
from agentguard.evidence import extractors

log = logging.getLogger(__name__)

TOOLS = MUTATING_TOOLS  # the core's file-writing vocabulary (deletes write nothing)
CHECK_IGNORE_TIMEOUT = 1.0

# (kind, pattern, how many leading characters are a public prefix that may be shown)
FORMATS: tuple[tuple[str, re.Pattern[str], int], ...] = (
    ("an AWS access key id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), 4),
    ("a private key", re.compile(r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----"), 0),
    ("a GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36}\b"), 4),
    ("a GitHub fine-grained token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{60,}"), 11),
    ("a Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9]+-[A-Za-z0-9-]{8,}"), 5),
    ("a Stripe live secret key", re.compile(r"\b[rs]k_live_[A-Za-z0-9]{20,}"), 8),
    ("an Anthropic API key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}"), 7),
    ("an OpenAI project key", re.compile(r"\bsk-proj-[A-Za-z0-9_-]{20,}"), 8),
    ("a Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"), 4),
)
_PREFIXES = re.compile(
    r"AKIA|ASIA|PRIVATE KEY-----|gh[pousr]_|github_pat_|xox[abprs]-|[rs]k_live_|sk-ant-|sk-proj-|AIza"
)
# Template values: AWS's documented AKIAIOSFODNN7EXAMPLE, `xxxx`, `your_key`, a run of one
# character. A real key, being random, has none of these.
_PLACEHOLDER = re.compile(
    r"example|xxxx|placeholder|dummy|fake|redacted|your[_-]|changeme|(.)\1{7}", re.IGNORECASE
)


@dataclass(frozen=True, slots=True)
class Hit:
    kind: str
    masked: str
    line: int  # 1-based, in the file after the edit


def scan(text: str) -> list[Hit]:
    """Strict-format credentials in `text` (one per kind), placeholders excluded."""
    if not _PREFIXES.search(text):
        return []  # one pass for the common case: nothing shaped like a key at all
    hits: list[Hit] = []
    for kind, pattern, shown in FORMATS:
        for match in pattern.finditer(text):
            value = match.group(0)
            if _PLACEHOLDER.search(value[shown:]):
                continue  # a documented example or a template value, not a credential
            hits.append(Hit(kind, mask(value, shown), text.count("\n", 0, match.start()) + 1))
            break
    return hits


def mask(value: str, shown: int) -> str:
    """The public prefix, then the length of what is hidden: never the secret itself."""
    if shown == 0:
        return value  # a PEM header names a key type, not a secret
    return f"{value[:shown]}…({len(value) - shown} characters hidden)"


def new_lines(before: str, after: str) -> tuple[str, dict[int, int]]:
    """The lines of `after` that `before` did not have, joined, and a map from each joined
    line number to its line number in `after`."""
    old = set(before.splitlines())
    kept: list[str] = []
    where: dict[int, int] = {}
    for number, line in enumerate(after.splitlines(), start=1):
        if line not in old:
            kept.append(line)
            where[len(kept)] = number
    return "\n".join(kept), where


def check(event: AgentEvent, root: Path) -> list[Finding]:
    """Credentials this edit would newly write into a file git does not ignore."""
    if event.tool not in TOOLS:
        return []
    outcome = extractors.resolve_edit(event, root)
    if outcome is None or outcome.after is None:
        return []
    added, where = new_lines(outcome.before or "", outcome.after)
    if not added:
        return []
    hits = scan(added)
    if not hits or _ignored(root, outcome.path):
        return []
    return [_finding(hit, outcome.path, where.get(hit.line, hit.line)) for hit in hits]


def _ignored(root: Path, path: str) -> bool:
    """Whether git ignores `path`. Asked only after a hit. Unsure means "yes": silent,
    which is the fail-open answer, and logged so it is never silent to the developer."""
    try:
        result = subprocess.run(
            ["git", "check-ignore", "-q", "--", path],
            cwd=root,
            capture_output=True,
            timeout=CHECK_IGNORE_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("agentguard: secret check could not ask git about %s (%s); not raised", path, exc)
        return True
    if result.returncode in (0, 1):
        return result.returncode == 0
    log.warning(
        "agentguard: secret check could not tell whether %s is ignored (git exit %s); not raised",
        path,
        result.returncode,
    )
    return True


def _finding(hit: Hit, path: str, line: int) -> Finding:
    return Finding(
        category=ChallengeCategory.RISK,
        verdict=Verdict.SUPPORTED_WITH_RISK,
        failure_mode=FailureMode.SECRET_EXPOSURE,
        severity=Severity.HIGH,
        subject=f"{hit.kind} in {path}",
        summary=f"This writes {hit.kind} into {path}, which git does not ignore",
        detail=f"Line {line}: `{hit.masked}`. Once committed and pushed, a credential stays in history.",
        evidence=[EvidenceRef(source="proposed-edit", path=path, line=line, note=hit.masked)],
        suggestion=(
            "Read it from the environment or a secrets manager instead, or keep it in a "
            "gitignored file such as `.env`."
        ),
        level=EscalationLevel.REPOSITORY,
    )
