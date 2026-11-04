"""The ChatGPT plan's usage windows, the budget rule, and infrastructure failures.

The benchmark runs on a ChatGPT Plus subscription, not API billing. Plus has a 5-hour
window and a weekly window; the same usage counts against both (OpenAI help center,
"Paid weekly Work and Codex rate limit resets" and "How resets work in Codex").
OpenAI publishes per-model *estimates* of local messages per 5 hours and a credit rate
card, but no weekly figure, so the weekly allowance is measured, not assumed: the
runner reads both windows from ``codex app-server`` (``account/rateLimits/read``, no
model request) before every pair and applies an outcome-blind rule.

A cell that fails for usage, auth, capacity or transport reasons is **void**: it is never
scored as an agent outcome, and its pair is re-run after the window allows it.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass

# Credits per 1M tokens (input, cached input, output), Standard speed.
# Source: https://learn.chatgpt.com/docs/pricing (the redirect target of
# https://developers.openai.com/codex/pricing), read 2026-11-04.
CREDIT_RATES_SOURCE = "learn.chatgpt.com/docs/pricing, Standard speed, read 2026-11-04"
CREDIT_RATES: dict[str, tuple[float, float, float]] = {
    "gpt-6.1-sol": (50.0, 2.5, 250.0),
    "gpt-6.1-terra": (25.0, 1.25, 125.0),
    "gpt-6-sol": (50.0, 5.0, 250.0),
    "gpt-6-luna": (2.5, 0.25, 12.5),
    "gpt-6-astra": (250.0, 25.0, 1250.0),
    "gpt-5.6-sol": (100.0, 10.0, 500.0),
}

# Published Plus estimates of local messages per 5 hours (same source).
PLUS_MESSAGES_PER_5H: dict[str, tuple[int, int]] = {
    "gpt-6-astra": (5, 45),
    "gpt-6.1-sol": (15, 160),
    "gpt-6.1-terra": (35, 285),
    "gpt-6-sol": (15, 150),
    "gpt-6-luna": (350, 3000),
}


def estimate_credits(model: str, usage: dict[str, int]) -> float | None:
    """Credits a cell's tokens would cost at the published rate card.

    ``input_tokens`` includes cached reads (Codex's convention); output includes
    reasoning. An estimate of plan consumption, not a bill: Plus meters its included
    usage in percent of a window, which is what the budget rule acts on.
    """
    rates = CREDIT_RATES.get(model)
    if rates is None:
        return None
    total_in = usage.get("input_tokens", 0)
    cached = usage.get("cached_input_tokens", 0)
    written = usage.get("cache_write_input_tokens", 0)
    uncached = max(0, total_in - cached - written)
    out = usage.get("output_tokens", 0)
    r_in, r_cached, r_out = rates
    return (uncached * r_in + (cached + written) * r_cached + out * r_out) / 1_000_000


@dataclass(frozen=True, slots=True)
class BudgetPolicy:
    """Pre-registered. Acts only on usage readings, never on outcomes."""

    stop_weekly_at: float = 80.0  # percent of the weekly window: stop starting pairs
    pause_primary_at: float = 90.0  # percent of the 5-hour window: wait for its reset
    max_wait_s: int = 6 * 3600  # a longer wait ends the session; resume later
    reset_slack_s: int = 90
    # Expected weekly-window percent per cell, for refusing a study the allowance cannot
    # finish. Conservative until the pilot measures it (two smoke cells moved the weekly
    # reading by less than its 1% resolution; ~0.06-0.09 credits each).
    weekly_percent_per_cell: float | None = 0.1


@dataclass(frozen=True, slots=True)
class Feasibility:
    ok: bool
    projected_percent: float | None
    headroom_percent: float | None
    reason: str


def feasibility(reading: dict | None, remaining_cells: int, policy: BudgetPolicy) -> Feasibility:
    """Can the current weekly window finish the remaining cells before the stop line?

    Outcome-blind: usage readings and a pre-registered per-cell estimate only. The
    projection ignores a reset that may happen mid-run, so it errs toward refusing.
    """
    if not reading or not isinstance(reading.get("secondary"), dict):
        return Feasibility(False, None, None, "the plan's usage windows could not be read")
    if reading.get("limit_reached") or reading.get("ordinary_usage_allowed") is False:
        return Feasibility(False, None, 0.0, "a usage limit is in force right now")
    used = reading["secondary"].get("used_percent")
    if not isinstance(used, (int, float)):
        return Feasibility(False, None, None, "the weekly window reported no usage figure")
    headroom = policy.stop_weekly_at - float(used)
    per_cell = policy.weekly_percent_per_cell
    if per_cell is None:
        return Feasibility(headroom > 0, None, headroom, "no per-cell estimate; only the stop line applies")
    projected = remaining_cells * per_cell
    verdict = "fits" if projected <= headroom else "does NOT fit"
    return Feasibility(
        projected <= headroom,
        projected,
        headroom,
        f"{remaining_cells} cells x {per_cell:g}% = {projected:.1f}% of the week {verdict} in the "
        f"{headroom:.1f}% left before the {policy.stop_weekly_at:g}% stop line (weekly window at {used:g}%)",
    )


@dataclass(frozen=True, slots=True)
class BudgetDecision:
    action: str  # "go" | "wait" | "stop"
    seconds: int
    reason: str


def decide(reading: dict | None, policy: BudgetPolicy, now: float | None = None) -> BudgetDecision:
    """Whether the next pair may start. A missing reading is a stop, not a guess."""
    now = time.time() if now is None else now
    if not reading or not reading.get("primary"):
        return BudgetDecision("stop", 0, "usage windows unavailable")
    primary = reading["primary"]
    weekly = reading.get("secondary") or {}

    def wait_for(window: dict, why: str) -> BudgetDecision:
        resets = window.get("resets_at")
        if not isinstance(resets, (int, float)):
            return BudgetDecision("stop", 0, f"{why}; reset time unknown")
        wait = int(resets - now) + policy.reset_slack_s
        if wait > policy.max_wait_s:
            return BudgetDecision("stop", 0, f"{why}; reset in {wait}s exceeds the wait limit")
        return BudgetDecision("wait", max(wait, policy.reset_slack_s), why)

    if reading.get("limit_reached") or reading.get("ordinary_usage_allowed") is False:
        if (weekly.get("used_percent") or 0) >= 100:
            return wait_for(weekly, "weekly limit reached")
        return wait_for(primary, "usage limit reached")
    weekly_used = weekly.get("used_percent")
    if isinstance(weekly_used, (int, float)) and weekly_used >= policy.stop_weekly_at:
        return BudgetDecision(
            "stop", 0, f"weekly window at {weekly_used:g}% (stop at {policy.stop_weekly_at:g}%)"
        )
    primary_used = primary.get("used_percent")
    if isinstance(primary_used, (int, float)) and primary_used >= policy.pause_primary_at:
        return wait_for(primary, f"5-hour window at {primary_used:g}%")
    return BudgetDecision("go", 0, f"5-hour {primary_used}%, weekly {weekly_used}%")


# -- infrastructure failures ------------------------------------------------------

_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "usage_limit",
        re.compile(
            r"usage limit|rate limit|too many requests|\b429\b|quota|purchase more credits|try again at",
            re.IGNORECASE,
        ),
    ),
    (
        "auth",
        re.compile(
            r"\b401\b|unauthori[sz]ed|not logged in|log ?in again|refresh token|"
            r"\bauthentication (failed|error|required)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "capacity",
        re.compile(
            r"at capacity|high demand|overloaded|\b50[0234]\b|internal server error|service unavailable",
            re.IGNORECASE,
        ),
    ),
    (
        "transport",
        re.compile(
            r"stream (disconnected|error)|connection (reset|refused|closed|failed)|timed out|network",
            re.IGNORECASE,
        ),
    ),
)


def classify_infra(
    exit_code: int | None,
    timed_out: bool,
    turns_completed: int,
    final_message: str | None,
    errors: list[str],
    stderr_tail: str,
    usage_limit_hit: bool = False,
) -> str | None:
    """The reason a cell is void, or ``None`` if the agent genuinely ran to an end.

    A run is an agent outcome only if Codex completed the turn. Everything else is
    infrastructure: run 01 scored quota no-ops as clean successes, and that must not
    happen again.
    """
    if usage_limit_hit:
        return "usage_limit"
    text = "\n".join([*errors, stderr_tail or ""])
    if timed_out:
        return None  # a cell that ran past its limit is graded as it stands (pre-registered)
    completed = turns_completed > 0 and bool((final_message or "").strip())
    if completed and exit_code == 0:
        return None
    for name, pattern in _PATTERNS:
        if pattern.search(text):
            return name
    if exit_code not in (0, None):
        return f"exit_{exit_code}"
    return "no_completed_turn"
