"""Run plans: everything pre-registered about a run, and the order cells run in.

A plan is a JSON file. Its digest covers every setting that could change a result:
model, effort, tasks, phrasings, replicates, seed, budget rule, trust method, sandbox,
the AgentGuard build ref, and the digest of the task suite itself. A run directory is
bound to one plan digest and refuses to start or resume under another.

Order: within each replicate block the pairs are shuffled with the plan's seed, and the
two cells of a pair run back to back, so both arms of a comparison see the same model
weather. Which arm goes first is balanced exactly within each block (half and half,
assigned at random), so a drift inside a pair cannot favour one arm.
"""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from agentguard.bench.codex.limits import BudgetPolicy

STAGES = ("pilot", "main", "smoke", "dry-run")
HOSTS = ("codex", "claude")
# Fields added after the first plans were registered: omitted from the digest at default.
_LATER_FIELDS: dict[str, Any] = {"host": "codex", "accounts": [], "permission_mode": "bypassPermissions"}


@dataclass(frozen=True, slots=True)
class Pair:
    task: str
    phrasing: str
    replicate: int

    @property
    def id(self) -> str:
        return f"{self.task}|{self.phrasing}|r{self.replicate}"


@dataclass(slots=True)
class Plan:
    name: str
    stage: str
    seed: int
    tasks: list[str]
    phrasings: list[str]
    replicates: list[int]
    arms: list[str] = field(default_factory=lambda: ["on", "observe"])
    model: str = "gpt-6-luna"
    effort: str = "medium"
    reasoning_summary: str = "none"
    service_tier: str = "default"
    sandbox: str = "workspace-write"
    network: bool = False
    cell_timeout_s: int = 1200
    max_attempts: int = 3
    trust: str = "app-server"
    recorder: bool = True
    agentguard_ref: str = "HEAD"
    codex_version: str = ""
    task_python: str = "3.12"
    pytest_version: str = "9.1.1"
    budget: dict[str, Any] = field(default_factory=lambda: asdict(BudgetPolicy()))
    suite_digest: str = ""
    notes: str = ""
    # Added with the Claude Code host. Left out of the digest while at their defaults, so
    # plans registered before they existed keep their digest.
    host: str = "codex"  # "codex" | "claude"
    accounts: list[str] = field(default_factory=list)  # Claude: config-dir accounts allowed
    permission_mode: str = "bypassPermissions"  # Claude

    def __post_init__(self) -> None:
        if self.stage not in STAGES:
            raise ValueError(f"stage must be one of {STAGES}")
        if sorted(self.arms) != ["observe", "on"]:
            raise ValueError("a plan compares exactly the 'on' and 'observe' arms")
        if self.host not in HOSTS:
            raise ValueError(f"host must be one of {HOSTS}")
        if self.host == "claude" and not self.accounts:
            raise ValueError("a Claude plan names the accounts it may use")

    def budget_policy(self) -> BudgetPolicy:
        if self.host != "codex":
            raise ValueError("a Claude plan's budget is an account policy: use account_policy()")
        return BudgetPolicy(**self.budget)

    def account_policy(self) -> Any:
        """Claude plans: the pre-registered account rules (98% rule, personal reserve)."""
        from agentguard.bench.codex.claude import AccountPolicy

        if self.host != "claude":
            raise ValueError("only a Claude plan has an account policy")
        return AccountPolicy(**self.budget)

    def pairs(self) -> list[Pair]:
        return [
            Pair(task, phrasing, replicate)
            for replicate in self.replicates
            for task in self.tasks
            for phrasing in self.phrasings
        ]

    def schedule(self) -> list[tuple[Pair, tuple[str, str]]]:
        rng = random.Random(self.seed)
        out: list[tuple[Pair, tuple[str, str]]] = []
        for replicate in self.replicates:
            block = [p for p in self.pairs() if p.replicate == replicate]
            rng.shuffle(block)
            orders = [("on", "observe") if i % 2 == 0 else ("observe", "on") for i in range(len(block))]
            rng.shuffle(orders)
            out.extend(zip(block, orders, strict=True))
        return out

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def digest(self) -> str:
        data = self.to_dict()
        for key, default in _LATER_FIELDS.items():
            if data.get(key) == default:
                data.pop(key)
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()

    def save(self, path: Path) -> None:
        payload = {"plan": self.to_dict(), "digest": self.digest()}
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> Plan:
        payload = json.loads(path.read_text(encoding="utf-8"))
        plan = cls(**payload["plan"])
        if payload.get("digest") and payload["digest"] != plan.digest():
            raise ValueError(f"{path}: the plan's recorded digest does not match its contents")
        return plan
