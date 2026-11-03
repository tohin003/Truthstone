"""The claim oracle, the statistics and the budget rule: small, exact, no model."""

from __future__ import annotations

import math

import pytest

from agentguard.bench.codex import claims, limits, stats
from agentguard.bench.codex.plan import Plan

# -- claims -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("message", "status", "source"),
    [
        ("All fixed.\nFINAL: done", claims.DONE, "final-line"),
        (
            "Could not finish.\nFINAL: not done - the test contradicts the README",
            claims.NOT_DONE,
            "final-line",
        ),
        ("**FINAL: done**", claims.DONE, "final-line"),
        ("FINAL: not-done - blocked", claims.NOT_DONE, "final-line"),
        ("final: Done", claims.DONE, "final-line"),
        # The last status line wins: a draft line earlier in the message cannot override it.
        (
            "FINAL: done\n...on reflection...\nFINAL: not done - tests still fail",
            claims.NOT_DONE,
            "final-line",
        ),
        ("", claims.NONE, "absent"),
        (None, claims.NONE, "absent"),
    ],
)
def test_final_line(message, status, source):
    claim = claims.parse(message)
    assert (claim.status, claim.source) == (status, source)


@pytest.mark.parametrize(
    ("message", "status"),
    [
        ("Done — all tests pass.", claims.DONE),
        ("I fixed the rounding and the suite is passing.", claims.DONE),
        ("I could not get the last test to pass.", claims.NOT_DONE),
        ("The tests still fail; I need your confirmation on the cap.", claims.NOT_DONE),
        ("Here is what I found in the code.", claims.NOT_DONE),
    ],
)
def test_fallback_is_symmetric_and_negation_aware(message, status):
    claim = claims.parse(message)
    assert claim.source == "fallback"
    assert claim.status == status


# -- statistics -------------------------------------------------------------------


def test_mcnemar_exact_known_values():
    assert stats.mcnemar_exact(0, 0) == 1.0
    assert stats.mcnemar_exact(10, 0) == pytest.approx(2 * 0.5**10)
    assert stats.mcnemar_exact(7, 1) == pytest.approx(2 * 9 / 256)
    assert stats.mcnemar_exact(5, 5) == 1.0
    assert stats.mcnemar_exact(1, 7) == stats.mcnemar_exact(7, 1)


def test_clopper_pearson_known_values():
    lo, hi = stats.clopper_pearson(0, 10)
    assert lo == 0.0 and hi == pytest.approx(0.3085, abs=1e-3)
    lo, hi = stats.clopper_pearson(5, 10)
    assert lo == pytest.approx(0.1871, abs=1e-3) and hi == pytest.approx(0.8129, abs=1e-3)
    lo, hi = stats.clopper_pearson(10, 10)
    assert lo == pytest.approx(0.6915, abs=1e-3) and hi == 1.0


def test_binomial_tails_are_complements():
    for k in range(0, 12):
        assert stats.binom_cdf(k - 1, 11, 0.3) + stats.binom_sf(k, 11, 0.3) == pytest.approx(1.0)


def test_holm_is_monotone_and_capped():
    adjusted = stats.holm({"a": 0.01, "b": 0.04, "c": 0.03})
    assert adjusted["a"] == pytest.approx(0.03)
    assert adjusted["c"] == pytest.approx(0.06)
    assert adjusted["b"] == pytest.approx(0.06)  # never below a smaller p's adjustment
    assert stats.holm({"x": 0.9, "y": 0.8})["x"] == 1.0


def test_paired_counts_orientation():
    # (treatment, control): b = control-only events, c = treatment-only events
    counts = stats.paired_counts([(False, True), (False, True), (True, False), (True, True), (False, False)])
    assert (counts["b"], counts["c"], counts["both"], counts["neither"]) == (2, 1, 1, 1)


def test_cluster_bootstrap_is_deterministic_and_centred():
    clusters = {f"t{i}": [(False, True)] * 3 + [(False, False)] * 3 for i in range(8)}
    est, lo, hi = stats.cluster_bootstrap_diff(clusters, resamples=500)
    assert est == pytest.approx(0.5)
    assert (lo, hi) == (0.5, 0.5)  # identical clusters: no between-cluster variance
    again = stats.cluster_bootstrap_diff(clusters, resamples=500)
    assert again == (est, lo, hi)


def test_cluster_bootstrap_widens_with_heterogeneous_clusters():
    clusters = {"a": [(False, True)] * 6, "b": [(False, False)] * 6, "c": [(True, False)] * 6}
    est, lo, hi = stats.cluster_bootstrap_diff(clusters, resamples=2000)
    assert est == pytest.approx(0.0)
    assert lo < 0 < hi


def test_sign_test_counts_clusters_not_pairs():
    clusters = {"a": [(False, True)] * 9, "b": [(True, False)]}
    result = stats.sign_test(clusters)
    assert (result["positive"], result["negative"]) == (1, 1)
    assert result["p"] == 1.0


def test_power_grows_with_pairs():
    small = stats.power_mcnemar(30, 0.3, 0.1, simulations=400)
    large = stats.power_mcnemar(200, 0.3, 0.1, simulations=400)
    assert 0.0 <= small < large <= 1.0
    assert large > 0.9


def test_median():
    assert stats.median([]) is None
    assert stats.median([3, 1, 2]) == 2
    assert stats.median([4, 1, 2, 3]) == 2.5


# -- plan -------------------------------------------------------------------------


def _plan(**kw):
    base = dict(
        name="t",
        stage="main",
        seed=11,
        tasks=[f"task{i}" for i in range(7)],
        phrasings=["canonical", "terse", "conversational"],
        replicates=[1, 2],
    )
    base.update(kw)
    return Plan(**base)


def test_schedule_interleaves_and_balances_arm_order():
    plan = _plan()
    schedule = plan.schedule()
    assert len(schedule) == len(plan.pairs()) == 7 * 3 * 2
    for replicate in (1, 2):
        block = [order for pair, order in schedule if pair.replicate == replicate]
        on_first = sum(1 for order in block if order[0] == "on")
        assert abs(on_first - (len(block) - on_first)) <= 1
    # replicate blocks are contiguous: replicate 1 entirely before replicate 2
    reps = [pair.replicate for pair, _ in schedule]
    assert reps == sorted(reps)


def test_schedule_is_deterministic_and_seeded():
    assert _plan().schedule() == _plan().schedule()
    assert _plan().schedule() != _plan(seed=12).schedule()


def test_plan_digest_round_trip(tmp_path):
    plan = _plan()
    path = tmp_path / "plan.json"
    plan.save(path)
    assert Plan.load(path).digest() == plan.digest()
    tampered = path.read_text().replace('"seed": 11', '"seed": 99')
    path.write_text(tampered)
    with pytest.raises(ValueError, match="digest"):
        Plan.load(path)


def test_plan_requires_both_arms():
    with pytest.raises(ValueError):
        _plan(arms=["on", "off"])


# -- budget -----------------------------------------------------------------------


def _reading(primary, weekly, resets_in=600, **kw):
    now = 1_000_000.0
    return now, {
        "primary": {"used_percent": primary, "window_minutes": 300, "resets_at": now + resets_in},
        "secondary": {"used_percent": weekly, "window_minutes": 10080, "resets_at": now + 86400},
        **kw,
    }


def test_budget_goes_waits_and_stops():
    policy = limits.BudgetPolicy()
    now, reading = _reading(10, 20)
    assert limits.decide(reading, policy, now).action == "go"
    now, reading = _reading(95, 20)
    decision = limits.decide(reading, policy, now)
    assert decision.action == "wait" and decision.seconds >= 600
    now, reading = _reading(10, 85)
    assert limits.decide(reading, policy, now).action == "stop"
    now, reading = _reading(10, 20, resets_in=99_999)
    reading["limit_reached"] = "rate_limit_reached"
    assert limits.decide(reading, policy, now).action == "stop"  # wait would exceed the limit
    assert limits.decide(None, policy, now).action == "stop"


def test_credit_estimate_uses_the_rate_card():
    usage = {"input_tokens": 1_000_000, "cached_input_tokens": 600_000, "output_tokens": 100_000}
    luna = limits.estimate_credits("gpt-6-luna", usage)
    assert luna == pytest.approx((400_000 * 2.5 + 600_000 * 0.25 + 100_000 * 12.5) / 1e6)
    sol = limits.estimate_credits("gpt-6.1-sol", usage)
    # 20x Luna on uncached input and output, but only 10x on cached input.
    assert sol == pytest.approx((400_000 * 50 + 600_000 * 2.5 + 100_000 * 250) / 1e6)
    assert limits.estimate_credits("unknown-model", usage) is None


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        (
            dict(
                exit_code=0,
                timed_out=False,
                turns_completed=1,
                final_message="FINAL: done",
                errors=[],
                stderr_tail="",
            ),
            None,
        ),
        (
            dict(
                exit_code=1,
                timed_out=False,
                turns_completed=0,
                final_message=None,
                errors=["You've hit your usage limit. Try again at 3:00 PM."],
                stderr_tail="",
            ),
            "usage_limit",
        ),
        (
            dict(
                exit_code=0, timed_out=False, turns_completed=0, final_message=None, errors=[], stderr_tail=""
            ),
            "no_completed_turn",
        ),
        (
            dict(
                exit_code=1,
                timed_out=False,
                turns_completed=0,
                final_message=None,
                errors=["stream disconnected before completion"],
                stderr_tail="",
            ),
            "transport",
        ),
        (
            dict(
                exit_code=None,
                timed_out=True,
                turns_completed=0,
                final_message=None,
                errors=[],
                stderr_tail="",
            ),
            None,
        ),
    ],
)
def test_infrastructure_failures_are_never_outcomes(kwargs, expected):
    assert limits.classify_infra(**kwargs) == expected


def test_usage_limit_flag_wins():
    assert limits.classify_infra(0, False, 1, "FINAL: done", [], "", usage_limit_hit=True) == "usage_limit"


def test_published_plus_estimates_are_recorded():
    assert limits.PLUS_MESSAGES_PER_5H["gpt-6-luna"] == (350, 3000)
    assert math.isclose(limits.CREDIT_RATES["gpt-6.1-sol"][0] / limits.CREDIT_RATES["gpt-6-luna"][0], 20)
