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


def stdev(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    centre = mean(values)
    return math.sqrt(sum((v - centre) ** 2 for v in values) / (len(values) - 1))


# Acklam rational approximation, then one Halley step against erfc. Without it
# every sample size calculation would need scipy for one number.
_A = (-3.969683028665376e01, 2.209460984245205e02, -2.759285104469687e02,
      1.383577518672690e02, -3.066479806614716e01, 2.506628277459239e00)
_B = (-5.447609879822406e01, 1.615858368580409e02, -1.556989798598866e02,
      6.680131188771972e01, -1.328068155288572e01)
_C = (-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e00,
      -2.549732539343734e00, 4.374664141464968e00, 2.938163982698783e00)
_D = (7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00, 3.754408661907416e00)


def norm_ppf(p: float) -> float:
    """Inverse standard normal cdf."""
    if not 0.0 < p < 1.0:
        raise ValueError("p must be strictly between 0 and 1")
    if p < 0.02425:
        q = math.sqrt(-2 * math.log(p))
        x = (((((_C[0] * q + _C[1]) * q + _C[2]) * q + _C[3]) * q + _C[4]) * q + _C[5]) / (
            (((_D[0] * q + _D[1]) * q + _D[2]) * q + _D[3]) * q + 1
        )
    elif p > 1 - 0.02425:
        q = math.sqrt(-2 * math.log(1 - p))
        x = -(((((_C[0] * q + _C[1]) * q + _C[2]) * q + _C[3]) * q + _C[4]) * q + _C[5]) / (
            (((_D[0] * q + _D[1]) * q + _D[2]) * q + _D[3]) * q + 1
        )
    else:
        q = p - 0.5
        r = q * q
        x = (((((_A[0] * r + _A[1]) * r + _A[2]) * r + _A[3]) * r + _A[4]) * r + _A[5]) * q / (
            ((((_B[0] * r + _B[1]) * r + _B[2]) * r + _B[3]) * r + _B[4]) * r + 1
        )
    error = 0.5 * math.erfc(-x / math.sqrt(2)) - p
    step = error * math.sqrt(2 * math.pi) * math.exp(x * x / 2)
    return x - step / (1 + x * step / 2)


def mcnemar_sample_size(
    discordant_rate: float, effect: float, alpha: float = 0.05, power: float = 0.8
) -> float:
    """Paired test cases needed to detect `effect`, given how often the two disagree.

    Power here is not driven by the eval set size but by the discordant pairs
    inside it: two variants that agree on almost everything need an enormous set
    to separate, however large the set already is.
    """
    if not 0.0 < discordant_rate <= 1.0:
        raise ValueError("the discordant rate must be in (0, 1]")
    effect = abs(effect)
    if effect <= 0:
        raise ValueError("the effect to detect must be positive")
    if effect > discordant_rate:
        raise ValueError("the effect cannot exceed the discordant rate")
    z_alpha = norm_ppf(1 - alpha / 2)
    z_beta = norm_ppf(power)
    numerator = z_alpha * math.sqrt(discordant_rate) + z_beta * math.sqrt(
        discordant_rate - effect ** 2
    )
    return numerator ** 2 / effect ** 2


def mcnemar_mde(
    n: int, discordant_rate: float, alpha: float = 0.05, power: float = 0.8
) -> float:
    """Smallest effect n paired cases could detect, inverted by bisection."""
    if n < 1:
        raise ValueError("n must be at least 1")
    low, high = 1e-9, discordant_rate
    if mcnemar_sample_size(discordant_rate, high, alpha, power) > n:
        return float("nan")  # even a total reversal would not be detectable
    for _ in range(200):
        mid = (low + high) / 2
        if mcnemar_sample_size(discordant_rate, mid, alpha, power) > n:
            low = mid
        else:
            high = mid
    return high


def paired_sample_size(
    sd_of_differences: float, effect: float, alpha: float = 0.05, power: float = 0.8
) -> float:
    """Paired test cases needed for a continuous metric."""
    effect = abs(effect)
    if effect <= 0:
        raise ValueError("the effect to detect must be positive")
    if sd_of_differences <= 0:
        return 0.0
    z = norm_ppf(1 - alpha / 2) + norm_ppf(power)
    return (z * sd_of_differences / effect) ** 2


def paired_mde(
    n: int, sd_of_differences: float, alpha: float = 0.05, power: float = 0.8
) -> float:
    if n < 1:
        raise ValueError("n must be at least 1")
    z = norm_ppf(1 - alpha / 2) + norm_ppf(power)
    return z * sd_of_differences / math.sqrt(n)
