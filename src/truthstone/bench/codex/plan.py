"""Run plans: everything pre-registered about a run, and the order cells run in.

A plan is a JSON file. Its digest covers every setting that could change a result:
model, effort, tasks, phrasings, replicates, seed, budget rule, trust method, sandbox,
the Truthstone build ref, and the digest of the task suite itself. A run directory is
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
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

from truthstone import names
from truthstone.bench.codex.limits import BudgetPolicy

STAGES = ("pilot", "main", "smoke", "dry-run")
# Stages an observe-only (screening) plan may have: never the confirmatory main study.
SCREENING_STAGES = ("pilot", "smoke", "dry-run")
HOSTS = ("codex", "claude")
# Fields added after the first plans were registered: omitted from the digest at default.
_LATER_FIELDS: dict[str, Any] = {
    "host": "codex",
    "accounts": [],
    "permission_mode": "bypassPermissions",
    "allowed_tools": [],
    "suite": "codex_bench",
    "node_version": "",
    "sandbox_profile": "",
    "observe_plugin": "",
    "pair_shard": [],
}
# The observe arm's plugin. "" (plans registered before amendment G1): the full plugin, whose
# skill listing names the guard to the model. "hooks-only": no skills, nothing model-visible.
OBSERVE_PLUGINS = ("", "full", "hooks-only")


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
    truthstone_ref: str = "HEAD"
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
    allowed_tools: list[str] = field(default_factory=list)  # Claude: --allowedTools
    # Added with the golden set. Same rule: at their defaults they are left out of the
    # digest, so every earlier plan keeps its digest.
    suite: str = "codex_bench"  # the named suite the tasks (and suite_digest) come from
    node_version: str = ""  # pinned Node for TypeScript tasks ("" = no Node on PATH)
    sandbox_profile: str = ""  # Claude: the versioned Bash-sandbox settings every cell runs under
    # Amendment G1: what the observe arm installs ("" = the full plugin, as before G1).
    observe_plugin: str = ""
    # Amendment G9: [k, n] runs only the k-th of n disjoint pair shards (parallel runners, one
    # per account); [] runs every pair. The shards of one design are analysed together.
    pair_shard: list[int] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.stage not in STAGES:
            raise ValueError(f"stage must be one of {STAGES}")
        if sorted(self.arms) not in (["observe", "on"], ["observe"], ["on"]):
            raise ValueError("a plan compares the 'on' and 'observe' arms, or runs one arm alone")
        if len(self.arms) == 1 and self.stage not in SCREENING_STAGES:
            raise ValueError(
                f"a one-arm plan (a screen, or a guarded dev round) is never the main study: "
                f"stage must be one of {SCREENING_STAGES}"
            )
        if self.pair_shard and not (
            len(self.pair_shard) == 2 and 0 <= self.pair_shard[0] < self.pair_shard[1]
        ):
            raise ValueError("pair_shard is [k, n] with 0 <= k < n")
        if self.host not in HOSTS:
            raise ValueError(f"host must be one of {HOSTS}")
        if self.host == "claude" and not self.accounts:
            raise ValueError("a Claude plan names the accounts it may use")
        if self.observe_plugin not in OBSERVE_PLUGINS:
            raise ValueError(f"observe_plugin must be one of {OBSERVE_PLUGINS}")
        if self.host == "codex" and self.accounts:
            from truthstone.bench.codex.accounts import ACCOUNTS

            unknown = sorted(set(self.accounts) - set(ACCOUNTS))
            if unknown:
                raise ValueError(f"unknown Codex account(s) {unknown}; known: {sorted(ACCOUNTS)}")

    @property
    def observe_variant(self) -> str:
        """The plugin variant the observe arm installs: "full" or "hooks-only"."""
        return self.observe_plugin or "full"

    @property
    def skill_free_observe(self) -> bool:
        """Amendment G1: an observe-arm cell that names the product to its model is void."""
        return self.observe_plugin == "hooks-only"

    @property
    def uses_accounts(self) -> bool:
        """Claude plans, and Codex plans that name accounts (amendment G5), schedule each pair
        on an account; a Codex plan without accounts runs on the default login, as before."""
        return self.host == "claude" or bool(self.accounts)

    def budget_policy(self) -> BudgetPolicy:
        if self.uses_accounts:
            raise ValueError("this plan's budget is an account policy: use account_policy()")
        return BudgetPolicy(**self.budget)

    def account_policy(self) -> Any:
        """The pre-registered account rules: Claude's (98% rule, personal reserve), or the
        Codex accounts' (G5: prefer the dedicated account, reserves on the user's own)."""
        if self.host == "claude":
            from truthstone.bench.codex.claude import AccountPolicy

            return AccountPolicy(**self.budget)
        if self.accounts:
            from truthstone.bench.codex.accounts import CodexAccountPolicy

            known = {f.name for f in fields(CodexAccountPolicy)}  # a plan made without one: defaults
            data = {k: v for k, v in self.budget.items() if k in known}
            if "preference" in data:
                data["preference"] = tuple(data["preference"])
            return CodexAccountPolicy(**data)
        raise ValueError("only a plan that names accounts has an account policy")

    def all_pairs(self) -> list[Pair]:
        """Every pair of the design, whatever shard this plan runs."""
        return [
            Pair(task, phrasing, replicate)
            for replicate in self.replicates
            for task in self.tasks
            for phrasing in self.phrasings
        ]

    def pairs(self) -> list[Pair]:
        """The pairs this plan runs: all of them, or its shard (every n-th, from the k-th)."""
        pairs = self.all_pairs()
        if not self.pair_shard:
            return pairs
        k, n = self.pair_shard
        return [p for i, p in enumerate(pairs) if i % n == k]

    @property
    def screening(self) -> bool:
        """An observe-only plan: base rates, cost and the instrument, never an arm comparison."""
        return self.arms == ["observe"]

    def schedule(self) -> list[tuple[Pair, tuple[str, ...]]]:
        """Pairs in order, each with its arms' order. The random draws are the same whatever
        the arms, so an observe-only plan visits its pairs in the paired plan's order."""
        rng = random.Random(self.seed)
        out: list[tuple[Pair, tuple[str, ...]]] = []
        for replicate in self.replicates:
            block = [p for p in self.pairs() if p.replicate == replicate]
            rng.shuffle(block)
            orders: list[tuple[str, ...]] = [
                ("on", "observe") if i % 2 == 0 else ("observe", "on") for i in range(len(block))
            ]
            rng.shuffle(orders)
            if len(self.arms) == 1:
                orders = [tuple(self.arms)] * len(block)
            out.extend(zip(block, orders, strict=True))
        return out

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def digest(self, spelling: int = 0) -> str:
        """SHA-256 of the canonical plan. ``spelling`` 0 spells product-named fields (the
        build ref) with the current product name; 1.. with each former name, which is how
        a plan registered before the rename was digested."""
        data = self.to_dict()
        for key, default in _LATER_FIELDS.items():
            if data.get(key) == default:
                data.pop(key)
        if spelling:
            data = {_spelled(key, spelling): value for key, value in data.items()}
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()

    def registered_digests(self) -> list[str]:
        """This plan's digest as written now and as written under each former name."""
        return [self.digest(i) for i in range(len(names.FORMER) + 1)]

    def save(self, path: Path) -> None:
        payload = {"plan": self.to_dict(), "digest": self.digest()}
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> Plan:
        payload = json.loads(path.read_text(encoding="utf-8"))
        known = {f.name for f in fields(cls)}
        data = {}
        for key, value in payload["plan"].items():
            current = next((f for f in known if key in names.variants(f)), key)
            data[current] = value
        plan = cls(**data)
        if payload.get("digest") and payload["digest"] not in plan.registered_digests():
            raise ValueError(f"{path}: the plan's recorded digest does not match its contents")
        return plan


def _spelled(key: str, spelling: int) -> str:
    """``key`` as the ``spelling``-th former product name wrote it (unchanged if unnamed)."""
    spelled = names.variants(key)
    return spelled[spelling] if spelling < len(spelled) else key
