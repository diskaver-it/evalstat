"""The guarantee is measured here, not asserted.

A confidence sequence claims to hold at every sample size at once. The way to
check that claim is to peek the way a CI pipeline peeks, and count how often each
procedure is wrong.
"""

import math
import random

import pytest

from conftest import make_doc
from evalstat import stats
from evalstat.parse import pair_within
from evalstat.sequential import ESTABLISHED, NOT_ESTABLISHED, anytime

LOOKS = [20, 40, 60, 80, 100, 130, 160, 190, 220, 250, 280, 300]


def _null_stream(rng, n, discordant_rate=0.22):
    """Paired differences under a true null: gains and losses equally likely."""
    half = discordant_rate / 2
    out = []
    for _ in range(n):
        roll = rng.random()
        out.append(1.0 if roll < half else (-1.0 if roll < discordant_rate else 0.0))
    return out


def _fixed_excludes_zero(diffs, alpha=0.05):
    n = len(diffs)
    if n < 2:
        return False
    spread = stats.stdev(diffs)
    if spread == 0:
        return False
    radius = stats.norm_ppf(1 - alpha / 2) * spread / math.sqrt(n)
    centre = stats.mean(diffs)
    return abs(centre) > radius


def test_peeking_breaks_the_fixed_interval_and_not_the_sequence():
    rng = random.Random(23)
    trials = 200
    fixed_wrong = sequence_wrong = 0
    for _ in range(trials):
        stream = _null_stream(rng, LOOKS[-1])
        if any(_fixed_excludes_zero(stream[:k]) for k in LOOKS):
            fixed_wrong += 1
        mapped = [(d + 1) / 2 for d in stream]
        flagged = False
        for k in LOOKS:
            lo, hi = stats.eb_confidence_sequence(mapped[:k])
            if lo > 0.5 or hi < 0.5:
                flagged = True
                break
        if flagged:
            sequence_wrong += 1

    fixed_rate = fixed_wrong / trials
    sequence_rate = sequence_wrong / trials
    assert fixed_rate > 0.10, "twelve looks should inflate 5%% well past it, got %.3f" % fixed_rate
    assert sequence_rate <= 0.05, "the sequence must hold at every look, got %.3f" % sequence_rate
    assert sequence_rate < fixed_rate


def test_sequence_covers_a_shifted_mean_at_every_look():
    rng = random.Random(29)
    truth, trials, missed = 0.62, 150, 0
    for _ in range(trials):
        values = [1.0 if rng.random() < truth else 0.0 for _ in range(LOOKS[-1])]
        for k in LOOKS:
            lo, hi = stats.eb_confidence_sequence(values[:k])
            if not lo <= truth <= hi:
                missed += 1
                break
    assert missed / trials <= 0.05


def test_sequence_narrows_as_evidence_arrives():
    rng = random.Random(31)
    values = [1.0 if rng.random() < 0.5 else 0.0 for _ in range(800)]
    widths = []
    for k in (50, 200, 800):
        lo, hi = stats.eb_confidence_sequence(values[:k])
        widths.append(hi - lo)
    assert widths[0] > widths[1] > widths[2]


def test_sequence_adapts_to_variance():
    # Same length, but one stream barely moves. The quiet one must come out tighter.
    quiet = [0.5] * 300
    noisy = [float(i % 2) for i in range(300)]
    quiet_lo, quiet_hi = stats.eb_confidence_sequence(quiet)
    noisy_lo, noisy_hi = stats.eb_confidence_sequence(noisy)
    assert (quiet_hi - quiet_lo) < (noisy_hi - noisy_lo)


def test_sequence_stays_inside_the_unit_interval_and_handles_edges():
    assert stats.eb_confidence_sequence([]) == (0.0, 1.0)
    lo, hi = stats.eb_confidence_sequence([1.0] * 5)
    assert 0.0 <= lo <= hi <= 1.0
    for bad_alpha in (0.0, 1.0, -1.0):
        with pytest.raises(ValueError):
            stats.eb_confidence_sequence([0.5], alpha=bad_alpha)
    with pytest.raises(ValueError):
        stats.eb_confidence_sequence([0.5], cap=1.5)


def test_any_fixed_order_is_valid_even_though_the_answer_moves():
    rng = random.Random(37)
    values = [1.0 if rng.random() < 0.7 else 0.0 for _ in range(200)]
    forward = stats.eb_confidence_sequence(values)
    backward = stats.eb_confidence_sequence(values[::-1])
    assert forward != backward, "a sequential procedure depends on order"
    for lo, hi in (forward, backward):
        assert lo <= 0.7 <= hi


def _sample(a, b, **kwargs):
    return pair_within(make_doc([("baseline", a), ("candidate", b)], **kwargs))


def test_anytime_is_wider_than_the_fixed_interval():
    a = [False] * 40 + [True] * 60
    b = [True] * 95 + [False] * 5
    result = anytime(_sample(a, b), reps=400)
    assert result.width_ratio > 1.0
    fixed_width = result.fixed_interval[1] - result.fixed_interval[0]
    assert (result.interval[1] - result.interval[0]) > fixed_width


def test_a_large_effect_is_established_even_under_peeking():
    a = [False] * 150 + [True] * 50
    b = [True] * 190 + [False] * 10
    result = anytime(_sample(a, b), reps=400)
    assert result.decision == ESTABLISHED
    assert result.interval[0] > 0
    assert any("however many times you looked" in note for note in result.notes)


def test_the_demo_difference_does_not_survive_continuous_watching():
    a = [True] * 27 + [True] * 4 + [False] * 7 + [False] * 12
    b = [True] * 27 + [False] * 4 + [True] * 7 + [False] * 12
    result = anytime(_sample(a, b), reps=400)
    assert result.decision == NOT_ESTABLISHED
    assert any("times narrower" in note for note in result.notes)


def test_an_unbounded_metric_is_scaled_and_flagged():
    doc = make_doc([("a", [1.0, 2.0, 3.0]), ("b", [4.0, 9.0, 2.0])], named_metric="judge")
    # Values outside [0, 1] arrive through a named score, so no range is declared.
    for row in doc["results"]["results"]:
        row["namedScores"]["judge"] = row["score"] * 7
    result = anytime(pair_within(doc, metric="judge"), reps=200)
    assert result.scale > 1.0
    assert any("declares no range" in note for note in result.notes)


def test_anytime_needs_pairs():
    doc_a = make_doc([("a", [True])])
    doc_b = make_doc([("b", [True])])
    doc_b["results"]["results"] = [
        dict(row, vars={"question": "elsewhere"}) for row in doc_b["results"]["results"]
    ]
    from evalstat.parse import pair_across

    with pytest.raises(ValueError):
        anytime(pair_across(doc_a, doc_b))
