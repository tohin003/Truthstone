"""Exact paired statistics, standard library only.

* exact McNemar: a two-sided binomial test on the discordant pairs (b vs c, p = 1/2);
* Clopper-Pearson intervals for rates and for the discordant proportion;
* a cluster bootstrap over **tasks** for the paired difference, because the phrasings
  and replicates of one task are correlated (the reason Pebble's pair-level p-values
  overstated significance);
* Holm's step-down adjustment for the secondary family;
* an exact sign test over per-task differences, as a robustness check.
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence


def _log_pmf(k: int, n: int, p: float) -> float:
    if p <= 0.0:
        return 0.0 if k == 0 else float("-inf")
    if p >= 1.0:
        return 0.0 if k == n else float("-inf")
    return (
        math.lgamma(n + 1)
        - math.lgamma(k + 1)
        - math.lgamma(n - k + 1)
        + k * math.log(p)
        + (n - k) * math.log1p(-p)
    )


def binom_cdf(k: int, n: int, p: float) -> float:
    """P(X <= k) for X ~ Bin(n, p)."""
    if k < 0:
        return 0.0
    if k >= n:
        return 1.0
    return min(1.0, sum(math.exp(_log_pmf(i, n, p)) for i in range(0, k + 1)))


def binom_sf(k: int, n: int, p: float) -> float:
    """P(X >= k)."""
    if k <= 0:
        return 1.0
    if k > n:
        return 0.0
    return min(1.0, sum(math.exp(_log_pmf(i, n, p)) for i in range(k, n + 1)))


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value. ``b`` and ``c`` are the discordant counts."""
    n = b + c
    if n == 0:
        return 1.0
    return min(1.0, 2.0 * binom_cdf(min(b, c), n, 0.5))


def clopper_pearson(k: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    """Exact (conservative) interval for a binomial proportion."""
    if n == 0:
        return (0.0, 1.0)

    def solve(f, target: float) -> float:
        lo, hi = 0.0, 1.0
        for _ in range(80):
            mid = (lo + hi) / 2
            if f(mid) < target:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2

    lower = 0.0 if k == 0 else solve(lambda p: binom_sf(k, n, p), alpha / 2)
    upper = 1.0 if k == n else 1.0 - solve(lambda q: binom_sf(n - k, n, q), alpha / 2)
    return (lower, upper)


def holm(pvalues: dict[str, float]) -> dict[str, float]:
    """Holm-adjusted p-values (monotone, capped at 1)."""
    ordered = sorted(pvalues.items(), key=lambda kv: kv[1])
    m = len(ordered)
    adjusted: dict[str, float] = {}
    running = 0.0
    for i, (name, p) in enumerate(ordered):
        running = max(running, min(1.0, (m - i) * p))
        adjusted[name] = running
    return adjusted


def paired_counts(pairs: Sequence[tuple[bool, bool]]) -> dict[str, int]:
    """Counts for (treatment, control) indicator pairs.

    ``b`` = control had it, treatment did not; ``c`` = treatment had it, control did not.
    """
    a = sum(1 for t, c in pairs if t and c)
    b = sum(1 for t, c in pairs if c and not t)
    c = sum(1 for t, c_ in pairs if t and not c_)
    d = sum(1 for t, c_ in pairs if not t and not c_)
    return {"both": a, "b": b, "c": c, "neither": d, "n": len(pairs)}


def cluster_bootstrap_diff(
    clusters: dict[str, list[tuple[bool, bool]]],
    resamples: int = 10_000,
    seed: int = 20261104,
    alpha: float = 0.05,
) -> tuple[float, float, float]:
    """(estimate, lower, upper) for rate(control) - rate(treatment), resampling clusters.

    A positive difference means the treatment arm had *fewer* of the counted events.
    """
    names = sorted(clusters)
    if not names:
        return (0.0, 0.0, 0.0)
    sums = {k: (sum(c for _, c in v) - sum(t for t, _ in v), len(v)) for k, v in clusters.items()}
    total_diff = sum(d for d, _ in sums.values())
    total_n = sum(n for _, n in sums.values())
    estimate = total_diff / total_n if total_n else 0.0
    rng = random.Random(seed)
    stats: list[float] = []
    for _ in range(resamples):
        diff = n = 0
        for _ in names:
            d_k, n_k = sums[names[rng.randrange(len(names))]]
            diff += d_k
            n += n_k
        stats.append(diff / n if n else 0.0)
    stats.sort()
    lo = stats[math.floor((alpha / 2) * (resamples - 1))]
    hi = stats[math.ceil((1 - alpha / 2) * (resamples - 1))]
    return (estimate, lo, hi)


def sign_test(clusters: dict[str, list[tuple[bool, bool]]]) -> dict[str, float | int]:
    """Exact sign test on per-cluster differences (control minus treatment)."""
    positive = negative = 0
    for values in clusters.values():
        diff = sum(c for _, c in values) - sum(t for t, _ in values)
        if diff > 0:
            positive += 1
        elif diff < 0:
            negative += 1
    return {"positive": positive, "negative": negative, "p": mcnemar_exact(positive, negative)}


def median(values: Sequence[float]) -> float | None:
    data = sorted(values)
    if not data:
        return None
    mid = len(data) // 2
    return data[mid] if len(data) % 2 else (data[mid - 1] + data[mid]) / 2


def bootstrap_median_diff(
    clusters: dict[str, list[tuple[float, float]]],
    resamples: int = 5_000,
    seed: int = 20261104,
    alpha: float = 0.05,
) -> tuple[float | None, float | None, float | None]:
    """Median of paired differences (treatment - control), clusters resampled."""
    names = sorted(clusters)
    diffs = {k: [t - c for t, c in v] for k, v in clusters.items()}
    everything = [d for v in diffs.values() for d in v]
    if not everything:
        return (None, None, None)
    rng = random.Random(seed)
    stats = []
    for _ in range(resamples):
        sample: list[float] = []
        for _ in names:
            sample.extend(diffs[names[rng.randrange(len(names))]])
        stats.append(median(sample) or 0.0)
    stats.sort()
    lo = stats[math.floor((alpha / 2) * (resamples - 1))]
    hi = stats[math.ceil((1 - alpha / 2) * (resamples - 1))]
    return (median(everything), lo, hi)


def power_mcnemar(
    pairs: int,
    p_control: float,
    p_treatment: float,
    rho: float = 0.0,
    alpha: float = 0.05,
    simulations: int = 4000,
    seed: int = 7,
) -> float:
    """Simulated power of the exact McNemar test for correlated binary pairs.

    ``rho`` is a crude within-pair dependence: with probability rho the treatment arm
    copies the control arm's outcome *when the control did not fail* (failures the guard
    is meant to catch are drawn independently). Used only to size the study.
    """
    rng = random.Random(seed)
    hits = 0
    for _ in range(simulations):
        b = c = 0
        for _ in range(pairs):
            control = rng.random() < p_control
            treatment = control if (not control and rng.random() < rho) else rng.random() < p_treatment
            if control and not treatment:
                b += 1
            elif treatment and not control:
                c += 1
        if mcnemar_exact(b, c) < alpha and b > c:
            hits += 1
    return hits / simulations
