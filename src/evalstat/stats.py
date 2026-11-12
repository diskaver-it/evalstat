"""The statistics, in the standard library only.

No numpy, no scipy: an eval gate has to install and run inside someone's CI in
seconds, and a dependency tree is the usual reason a check like this never gets
adopted. Everything here is exact arithmetic or a seeded resample.

Two ideas are worth naming, because they are what the eval tools get wrong.

The test and the interval are separate procedures on purpose. A significance
test is allowed to assume the null hypothesis; a confidence interval must not,
since the null is the thing it is measuring. So the p-value comes from a
procedure built on the null (exact binomial, or sign flips) while the interval
comes from resampling the pairs as observed.

Pairing is not a refinement, it is the whole gain. Two runs over the same eval
set differ partly because the prompts differ and partly because some test cases
are simply harder. Comparing the two column means leaves the second part in the
noise; differencing within a test case removes it.
"""

from __future__ import annotations

import math
import random
from typing import List, Sequence, Tuple


def chi2_sf_df1(x: float) -> float:
    """Upper tail of chi-square with one degree of freedom."""
    if x <= 0:
        return 1.0
    return math.erfc(math.sqrt(x / 2.0))


def binom_sign_p(b: int, c: int) -> float:
    """Exact two-sided p for b successes out of b + c at probability one half."""
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(min(b, c) + 1))
    return min(1.0, 2.0 * tail / (2.0 ** n))


def mcnemar(b: int, c: int, exact_below: int = 26) -> Tuple[float, float, bool]:
    """Paired test for binary outcomes: (statistic, p-value, whether exact).

    Only the discordant pairs carry information. Pairs that passed in both runs
    or failed in both say nothing about which variant is better, which is also
    why a large eval set can still leave a comparison underpowered.
    """
    if b < 0 or c < 0:
        raise ValueError("discordant counts cannot be negative")
    n = b + c
    if n == 0:
        return 0.0, 1.0, True
    if n < exact_below:
        return float(abs(b - c)), binom_sign_p(b, c), True
    # Continuity correction, because a discrete count is being read off a
    # continuous curve; without it the test is anti-conservative.
    statistic = (abs(b - c) - 1.0) ** 2 / n
    return statistic, chi2_sf_df1(statistic), False


def discordant(a: Sequence[float], b: Sequence[float]) -> Tuple[int, int]:
    """Counts of pairs that only b passed, and that only a passed."""
    gained = sum(1 for x, y in zip(a, b) if y > x)
    lost = sum(1 for x, y in zip(a, b) if y < x)
    return gained, lost


def sign_flip_p(diffs: Sequence[float], reps: int = 10000, seed: int = 0) -> float:
    """Paired permutation test: under the null, each difference could flip sign."""
    diffs = [d for d in diffs]
    if not diffs:
        return 1.0
    observed = abs(sum(diffs) / len(diffs))
    if observed == 0.0:
        return 1.0
    rng = random.Random(seed)
    extreme = 0
    for _ in range(reps):
        total = 0.0
        for d in diffs:
            total += d if rng.random() < 0.5 else -d
        if abs(total / len(diffs)) >= observed - 1e-12:
            extreme += 1
    # The +1 keeps the p-value away from an impossible exact zero.
    return (extreme + 1.0) / (reps + 1.0)


def _quantile(sorted_values: List[float], q: float) -> float:
    if not sorted_values:
        return float("nan")
    if len(sorted_values) == 1:
        return sorted_values[0]
    pos = q * (len(sorted_values) - 1)
    low = int(math.floor(pos))
    high = min(low + 1, len(sorted_values) - 1)
    weight = pos - low
    return sorted_values[low] * (1 - weight) + sorted_values[high] * weight


def bootstrap_mean_ci(
    diffs: Sequence[float], alpha: float = 0.05, reps: int = 10000, seed: int = 0
) -> Tuple[float, float]:
    """Percentile interval for the mean difference, resampling whole pairs."""
    n = len(diffs)
    if n == 0:
        return float("nan"), float("nan")
    if all(d == diffs[0] for d in diffs):
        return diffs[0], diffs[0]
    rng = random.Random(seed)
    means = []
    for _ in range(reps):
        total = 0.0
        for _ in range(n):
            total += diffs[rng.randrange(n)]
        means.append(total / n)
    means.sort()
    return _quantile(means, alpha / 2.0), _quantile(means, 1.0 - alpha / 2.0)


def mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else float("nan")
