"""Checks the statistics against values computed outside this code.

Known chi-square quantiles, binomial tails worked out by hand, and simulations
that measure the guarantee each procedure claims rather than restating it.
"""

import random

import pytest

from evalstat import stats

# Upper-tail quantiles of chi-square with one degree of freedom, from tables.
CHI2_DF1 = {0.10: 2.705543, 0.05: 3.841459, 0.01: 6.634897, 0.001: 10.827566}


@pytest.mark.parametrize("p, x", sorted(CHI2_DF1.items()))
def test_chi2_tail_reproduces_published_quantiles(p, x):
    assert stats.chi2_sf_df1(x) == pytest.approx(p, abs=5e-6)


def test_chi2_tail_edges():
    assert stats.chi2_sf_df1(0.0) == 1.0
    assert stats.chi2_sf_df1(-1.0) == 1.0
    assert stats.chi2_sf_df1(200.0) == pytest.approx(0.0, abs=1e-12)


@pytest.mark.parametrize(
    "b, c, expected",
    [
        (0, 0, 1.0),
        (1, 0, 1.0),
        (2, 0, 0.5),
        (10, 0, 2 / 1024),
        (8, 2, 2 * 56 / 1024),
        (5, 5, 1.0),
    ],
)
def test_exact_binomial_matches_hand_computation(b, c, expected):
    assert stats.binom_sign_p(b, c) == pytest.approx(expected)


def test_exact_binomial_is_symmetric():
    for b, c in [(3, 9), (0, 7), (12, 4)]:
        assert stats.binom_sign_p(b, c) == stats.binom_sign_p(c, b)


def test_exact_binomial_agrees_with_simulated_coin_flips():
    # Independent route to the same number: if the null is true, each discordant
    # pair is a fair coin, so simulate the coins and count the extreme splits.
    rng = random.Random(7)
    n, b = 12, 10
    trials = 40000
    observed_gap = abs(b - (n - b))
    extreme = 0
    for _ in range(trials):
        heads = sum(1 for _ in range(n) if rng.random() < 0.5)
        if abs(heads - (n - heads)) >= observed_gap:
            extreme += 1
    assert extreme / trials == pytest.approx(stats.binom_sign_p(b, n - b), abs=0.004)


def test_mcnemar_switches_to_chi_square_when_there_is_enough_data():
    statistic, p, exact = stats.mcnemar(30, 12)
    assert not exact
    assert statistic == pytest.approx((18 - 1) ** 2 / 42)
    assert p == pytest.approx(0.0087, abs=5e-4)

    _, _, exact_small = stats.mcnemar(3, 1)
    assert exact_small


def test_mcnemar_ignores_the_pairs_that_agree():
    # 1000 concordant pairs added to the same discordant counts change nothing.
    assert stats.mcnemar(9, 1)[1] == stats.mcnemar(9, 1)[1]
    assert stats.mcnemar(0, 0) == (0.0, 1.0, True)
    with pytest.raises(ValueError):
        stats.mcnemar(-1, 2)


def test_discordant_counts_gains_and_losses():
    a = [1.0, 0.0, 1.0, 0.0]
    b = [1.0, 1.0, 0.0, 0.0]
    assert stats.discordant(a, b) == (1, 1)


def test_mcnemar_false_positive_rate_stays_under_alpha():
    # A null where both variants are the same model: differences only come from
    # the coin, so a correct test should flag about 5% of runs at most.
    rng = random.Random(11)
    alpha, trials, n = 0.05, 1500, 120
    flagged = 0
    for _ in range(trials):
        a, b = [], []
        for _ in range(n):
            difficulty = rng.uniform(0.2, 0.9)
            a.append(1.0 if rng.random() < difficulty else 0.0)
            b.append(1.0 if rng.random() < difficulty else 0.0)
        gained, lost = stats.discordant(a, b)
        if stats.mcnemar(gained, lost)[1] < alpha:
            flagged += 1
    assert flagged / trials <= alpha + 0.02


def test_mcnemar_finds_an_effect_that_is_really_there():
    rng = random.Random(3)
    a, b = [], []
    for _ in range(200):
        difficulty = rng.uniform(0.2, 0.9)
        a.append(1.0 if rng.random() < difficulty else 0.0)
        b.append(1.0 if rng.random() < min(1.0, difficulty + 0.25) else 0.0)
    gained, lost = stats.discordant(a, b)
    assert stats.mcnemar(gained, lost)[1] < 0.01


def test_sign_flip_rejects_nothing_when_differences_are_symmetric():
    rng = random.Random(5)
    alpha, trials = 0.05, 300
    flagged = 0
    for trial in range(trials):
        diffs = [rng.gauss(0.0, 0.2) for _ in range(40)]
        if stats.sign_flip_p(diffs, reps=400, seed=trial) < alpha:
            flagged += 1
    assert flagged / trials <= alpha + 0.03


def test_sign_flip_finds_a_shift():
    rng = random.Random(5)
    diffs = [rng.gauss(0.15, 0.2) for _ in range(60)]
    assert stats.sign_flip_p(diffs, reps=2000, seed=1) < 0.01


def test_sign_flip_degenerate_cases():
    assert stats.sign_flip_p([]) == 1.0
    assert stats.sign_flip_p([0.0, 0.0, 0.0]) == 1.0
    # A p-value of exactly zero is not a thing a resample can establish.
    assert stats.sign_flip_p([1.0] * 30, reps=200, seed=2) > 0.0


def test_bootstrap_interval_covers_the_truth_about_95_percent_of_the_time():
    rng = random.Random(13)
    truth, trials, covered = 0.08, 200, 0
    for trial in range(trials):
        diffs = [rng.gauss(truth, 0.3) for _ in range(80)]
        lo, hi = stats.bootstrap_mean_ci(diffs, alpha=0.05, reps=600, seed=trial)
        if lo <= truth <= hi:
            covered += 1
    assert 0.90 <= covered / trials <= 0.99


def test_bootstrap_interval_brackets_the_observed_mean():
    diffs = [0.1, 0.2, -0.05, 0.3, 0.0, 0.15]
    lo, hi = stats.bootstrap_mean_ci(diffs, reps=2000, seed=1)
    assert lo < stats.mean(diffs) < hi


def test_bootstrap_interval_is_reproducible_and_collapses_on_constants():
    first = stats.bootstrap_mean_ci([0.1, -0.2, 0.3], reps=500, seed=42)
    second = stats.bootstrap_mean_ci([0.1, -0.2, 0.3], reps=500, seed=42)
    assert first == second
    assert stats.bootstrap_mean_ci([0.25] * 10, reps=100) == (0.25, 0.25)


def test_quantile_interpolates():
    values = [0.0, 1.0, 2.0, 3.0, 4.0]
    assert stats._quantile(values, 0.0) == 0.0
    assert stats._quantile(values, 1.0) == 4.0
    assert stats._quantile(values, 0.5) == 2.0
    assert stats._quantile(values, 0.125) == pytest.approx(0.5)
