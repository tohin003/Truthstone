"""Codex accounts (golden amendment G5): two ChatGPT logins, each a CODEX_HOME's ``auth.json``.

``main`` is the user's own login (``~/.codex``), which the user and the ChatGPT desktop app need
every day; ``p`` (``~/.codex-personal``) is dedicated to the benchmark. A cell's throwaway
CODEX_HOME gets the chosen account's ``auth.json`` as a **symlink**: the harness never opens,
reads, prints or copies either file (as ``homes.link_auth`` documents).

Pre-registered rules. They act on usage readings only, never on outcomes:

* prefer ``p``; use ``main`` only when ``p`` cannot take the whole pair;
* never start a ``main`` cell when main's weekly window is at 50% or more, or its 5-hour
  window at 80% or more;
* ``p`` stops at 80% of its weekly window; no cell starts at 98% or more of either account's
  5-hour window;
* a pair's two cells run on one account, admitted only if the second cell will still be
  allowed after the first's expected spend (the pilot's measured 0.55% of a 5-hour window and
  0.1% of a week per cell);
* both accounts' windows are read with no model call (``account/rateLimits/read`` on
  ``codex app-server``) before the study and every refresh interval, and each cell's own
  pre-cell reading (taken in its home, on its account) updates its account between reads.
"""

from __future__ import annotations

import math
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from truthstone.bench.codex import appserver, homes

ACCOUNTS: dict[str, Path] = {
    "main": Path.home() / ".codex",
    "p": Path.home() / ".codex-personal",
}
PREFERENCE = ("p", "main")


def auth_source(account: str | None) -> Path:
    """The login a cell on ``account`` links to (None: the default login, as before G5)."""
    if account is None:
        return homes.DEFAULT_AUTH_SOURCE
    if account not in ACCOUNTS:
        raise ValueError(f"unknown Codex account {account!r}; known: {sorted(ACCOUNTS)}")
    return ACCOUNTS[account] / "auth.json"


@dataclass(frozen=True, slots=True)
class CodexAccountPolicy:
    """The G5 rules, pinned in a multi-account Codex plan's ``budget``."""

    start_max_primary: float = 98.0  # no cell starts at >= 98% of a 5-hour window
    week_stop: dict[str, float] = field(default_factory=lambda: {"p": 80.0, "main": 50.0})
    primary_cap: dict[str, float] = field(default_factory=lambda: {"main": 80.0})
    preference: tuple[str, ...] = PREFERENCE
    per_cell_primary: float = 0.55  # measured on the dev pilot (5-hour percent per cell)
    per_cell_week: float = 0.1  # measured on the dev pilot (weekly percent per cell)
    usage_refresh_s: int = 1800
    max_wait_s: int = 6 * 3600
    reset_slack_s: int = 90

    def caps(self, name: str) -> tuple[float, float]:
        primary = min(self.primary_cap.get(name, self.start_max_primary), self.start_max_primary)
        return primary, self.week_stop.get(name, 80.0)


@dataclass(frozen=True, slots=True)
class Choice:
    account: str | None
    reason: str
    wait_s: int = 0


def windows(reading: dict | None) -> tuple[float, float] | None:
    """(5-hour used %, weekly used %) from an app-server reading, if both are known."""
    if not reading:
        return None
    primary = (reading.get("primary") or {}).get("used_percent")
    weekly = (reading.get("secondary") or {}).get("used_percent")
    if not isinstance(primary, (int, float)) or not isinstance(weekly, (int, float)):
        return None
    return float(primary), float(weekly)


def cell_allowed(
    name: str, reading: dict | None, policy: CodexAccountPolicy, cells: int = 1
) -> tuple[bool, str]:
    """May ``cells`` more cells start on this account? (``cells=2`` admits a pair.)"""
    found = windows(reading)
    if found is None:
        return False, f"{name}: no complete reading"
    if (reading or {}).get("limit_reached") or (reading or {}).get("ordinary_usage_allowed") is False:
        return False, f"{name}: the account's limit is reached"
    primary, week = found
    primary_cap, week_cap = policy.caps(name)
    ahead_primary = policy.per_cell_primary * (cells - 1)
    ahead_week = policy.per_cell_week * (cells - 1)
    if week + ahead_week >= week_cap:
        return False, f"{name}: week {week:g}% (+{ahead_week:g}) >= {week_cap:g}%"
    if primary + ahead_primary >= primary_cap:
        return False, f"{name}: 5-hour {primary:g}% (+{ahead_primary:g}) >= {primary_cap:g}%"
    return True, f"{name}: 5-hour {primary:g}% < {primary_cap:g}%, week {week:g}% < {week_cap:g}%"


def choose(
    readings: dict[str, dict | None],
    policy: CodexAccountPolicy,
    now: float | None = None,
    allowed: tuple[str, ...] | None = None,
) -> Choice:
    """The first account in the preferred order that can take a whole pair, or how long to
    wait for a 5-hour reset (never for a weekly one)."""
    now = time.time() if now is None else now
    notes, waits = [], []
    for name in policy.preference:
        if allowed is not None and name not in allowed:
            continue
        reading = readings.get(name)
        ok, why = cell_allowed(name, reading, policy, cells=2)
        notes.append(why)
        if ok:
            return Choice(
                name, f"{name} (preferred order {'>'.join(policy.preference)}); " + "; ".join(notes)
            )
        found = windows(reading)
        if found is None or found[1] + policy.per_cell_week >= policy.caps(name)[1]:
            continue  # the weekly window does not reset within any wait we allow
        resets = ((reading or {}).get("primary") or {}).get("resets_at")
        if isinstance(resets, (int, float)):
            waits.append(resets - now)
    if waits:
        wait = int(max(0.0, min(waits))) + policy.reset_slack_s
        if wait <= policy.max_wait_s:
            return Choice(None, "no eligible account until a 5-hour reset: " + "; ".join(notes), wait)
    return Choice(None, "no eligible account: " + "; ".join(notes))


def capacity(name: str, reading: dict | None, policy: CodexAccountPolicy) -> int:
    """Cells this account can still start before its weekly stop, at the measured spend."""
    found = windows(reading)
    if found is None or policy.per_cell_week <= 0:
        return 0
    return max(0, math.ceil((policy.caps(name)[1] - found[1]) / policy.per_cell_week))


# -- reading an account's windows, with no model call --------------------------------


def account_home(state: Path, account: str) -> Path:
    """A private CODEX_HOME holding only the account's login link (reused within a study)."""
    home = homes.private_dir(state / homes.neutral_name("account", account))
    if not homes.auth_link_intact(home, auth_source(account)):
        homes.link_auth(home, auth_source(account))
    return home


def read_windows(codex_bin: str, home: Path, attempts: int = 3) -> dict | None:
    """``account/rateLimits/read`` through ``home``: plan type and both windows, or None."""
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(home.parent),
        "CODEX_HOME": str(home),
        "USER": os.environ.get("USER", "dev"),
        "LANG": "en_US.UTF-8",
    }
    for attempt in range(attempts):
        try:
            with appserver.AppServer(codex_bin, env) as server:
                return appserver.plan_type_and_windows(server.rate_limits())
        except appserver.AppServerError:
            time.sleep(2 * (attempt + 1))
    return None


def describe(name: str, reading: dict | None, policy: CodexAccountPolicy) -> dict[str, Any]:
    ok, why = cell_allowed(name, reading, policy, cells=2)
    return {
        "account": name,
        "plan_type": (reading or {}).get("plan_type"),
        "windows": windows(reading),
        "eligible_for_a_pair": ok,
        "why": why,
        "cells_before_weekly_stop": capacity(name, reading, policy),
    }
