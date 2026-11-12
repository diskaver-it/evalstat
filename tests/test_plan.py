"""Sample size planning, checked against tables and against simulation."""

import random

import pytest

from conftest import make_doc
from evalstat import stats
from evalstat.parse import pair_within
from evalstat.plan import plan

# Standard normal quantiles, from tables.
Z = {0.975: 1.959963985, 0.8: 0.841621234, 0.95: 1.644853627, 0.5: 0.0, 0.001: -3.090232306}


@pytest.mark.parametrize("p, z", sorted(Z.items()))
def test_normal_quantile_matches_published_values(p, z):
    assert stats.norm_ppf(p) == pytest.approx(z, abs=1e-9)


def test_normal_quantile_is_symmetric_and_bounded():
    for p in (0.01, 0.2, 0.37, 0.64, 0.99):
        assert stats.norm_ppf(p) == pytest.approx(-stats.norm_ppf(1 - p), abs=1e-9)
    for bad in (0.0, 1.0, -0.1, 2.0):
        with pytest.raises(ValueError):
            stats.norm_ppf(bad)


def test_normal_quantile_inverts_the_tail_function():
    # chi2_sf_df1(z^2) is the two-sided normal tail, so the two must agree.
    for alpha in (0.1, 0.05, 0.01, 0.001):
        z = stats.norm_ppf(1 - alpha / 2)
        assert stats.chi2_sf_df1(z * z) == pytest.approx(alpha, abs=1e-9)


def test_sample_size_reaches_the_power_it_promises():
    # The claim is 80% power. Compute n from the formula, then run the test that
    # many times at that n and count how often it actually fires.
    rng = random.Random(17)
    p_gain, p_loss = 0.12, 0.04
    discordant_rate = p_gain + p_loss
    effect = p_gain - p_loss
    n = int(stats.mcnemar_sample_size(discordant_rate, effect, alpha=0.05, power=0.8))

    fired = 0
    trials = 600
    for _ in range(trials):
        gained = lost = 0
        for _ in range(n):
            roll = rng.random()
            if roll < p_gain:
                gained += 1
            elif roll < p_gain + p_loss:
                lost += 1
        if stats.mcnemar(gained, lost)[1] < 0.05:
            fired += 1
    assert 0.74 <= fired / trials <= 0.87, "achieved power %.3f at n=%d" % (fired / trials, n)


def test_sample_size_grows_as_the_effect_shrinks():
    sizes = [stats.mcnemar_sample_size(0.2, e) for e in (0.08, 0.04, 0.02)]
    assert sizes[0] < sizes[1] < sizes[2]
    # Halving the effect roughly quadruples the requirement.
    assert 3.5 < sizes[2] / sizes[1] < 4.5


def test_agreement_is_what_costs_you_cases():
    # Same effect, but variants that agree more often need far more test cases.
    chatty = stats.mcnemar_sample_size(0.40, 0.03)
    quiet = stats.mcnemar_sample_size(0.06, 0.03)
    assert quiet < chatty


def test_mde_and_sample_size_are_inverse():
    rate, n = 0.25, 500
    mde = stats.mcnemar_mde(n, rate, alpha=0.05, power=0.8)
    assert stats.mcnemar_sample_size(rate, mde, alpha=0.05, power=0.8) == pytest.approx(n, rel=0.02)


def test_mde_is_nan_when_nothing_is_reachable():
    assert stats.mcnemar_mde(3, 0.02) != stats.mcnemar_mde(3, 0.02)


def test_continuous_sample_size_and_mde_are_inverse():
    sd, n = 0.4, 120
    mde = stats.paired_mde(n, sd)
    assert stats.paired_sample_size(sd, mde) == pytest.approx(n, rel=1e-6)


def test_sample_size_rejects_impossible_requests():
    with pytest.raises(ValueError):
        stats.mcnemar_sample_size(0.1, 0.0)
    with pytest.raises(ValueError):
        stats.mcnemar_sample_size(0.1, 0.5)
    with pytest.raises(ValueError):
        stats.mcnemar_sample_size(0.0, 0.05)


def _demo_sample():
    a = [True] * 27 + [True] * 4 + [False] * 7 + [False] * 12
    b = [True] * 27 + [False] * 4 + [True] * 7 + [False] * 12
    return pair_within(make_doc([("baseline", a), ("candidate", b)]))


def test_plan_reads_the_disagreement_rate_from_the_run():
    result = plan(_demo_sample(), detect=0.03)
    assert result.n == 50
    assert result.discordant == 11
    assert result.spread == pytest.approx(11 / 50)
    assert result.needed > 50
    assert result.mde > 0.03, "fifty cases cannot see three points"


def test_plan_without_a_target_still_reports_the_resolution():
    result = plan(_demo_sample())
    assert result.needed is None
    assert 0 < result.mde < 1


def test_plan_on_continuous_scores_uses_the_spread_of_differences():
    a = [0.40, 0.42, 0.38, 0.45, 0.41] * 10
    b = [0.52, 0.47, 0.55, 0.49, 0.51] * 10
    sample = pair_within(make_doc([("a", a), ("b", b)]), metric="score")
    result = plan(sample, detect=0.02)
    assert not result.binary
    assert result.discordant is None
    assert result.spread == pytest.approx(stats.stdev(sample.diffs))
    assert result.needed > 0


def test_plan_refuses_when_the_variants_never_disagreed():
    values = [True, False, True, True]
    with pytest.raises(ValueError):
        plan(pair_within(make_doc([("a", values), ("b", values)])))


def test_plan_rejects_a_silly_power():
    with pytest.raises(ValueError):
        plan(_demo_sample(), power=1.0)


def test_stdev_matches_the_textbook_definition():
    assert stats.stdev([2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0]) == pytest.approx(2.13808993)
    assert stats.stdev([3.0]) == 0.0
