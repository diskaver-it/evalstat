"""Several metrics at once, where the 5% belongs to the family."""

import random

import pytest

from conftest import make_doc
from evalstat import stats
from evalstat.compare import UNDECIDED, WORSE, compare_family
from evalstat.parse import list_metrics, pair_within


def test_holm_matches_r_p_adjust():
    # R: p.adjust(c(0.01, 0.02, 0.03, 0.04, 0.05), "holm")
    assert stats.holm([0.01, 0.02, 0.03, 0.04, 0.05]) == pytest.approx(
        [0.05, 0.08, 0.09, 0.09, 0.09]
    )
    # R: p.adjust(c(0.003, 0.03, 0.3), "holm")
    assert stats.holm([0.003, 0.03, 0.3]) == pytest.approx([0.009, 0.06, 0.3])


def test_holm_keeps_the_input_order_and_never_exceeds_one():
    adjusted = stats.holm([0.3, 0.003, 0.03])
    assert adjusted == pytest.approx([0.3, 0.009, 0.06])
    assert stats.holm([0.9, 0.95]) == pytest.approx([1.0, 1.0])
    assert stats.holm([]) == []
    assert stats.holm([0.02]) == pytest.approx([0.02])


def test_holm_is_monotone_in_the_sorted_order():
    rng = random.Random(3)
    raw = [rng.random() for _ in range(12)]
    adjusted = stats.holm(raw)
    pairs = sorted(zip(raw, adjusted))
    assert all(pairs[i][1] <= pairs[i + 1][1] + 1e-12 for i in range(len(pairs) - 1))


def test_holm_holds_the_family_wide_error_where_no_correction_fails():
    # Under a global null every p-value is uniform, so five metrics give five
    # chances to be wrong. Count how often each rule flags anything at all.
    rng = random.Random(5)
    alpha, trials, metrics = 0.05, 2000, 5
    naive = corrected = 0
    for _ in range(trials):
        ps = [rng.random() for _ in range(metrics)]
        if any(p < alpha for p in ps):
            naive += 1
        if any(p < alpha for p in stats.holm(ps)):
            corrected += 1
    assert naive / trials > 0.18, "five unadjusted looks should be well above 5%"
    assert corrected / trials <= alpha + 0.015


def _three_metric_doc():
    passes = [True] * 30 + [False] * 20
    gains = [True] * 36 + [False] * 14
    doc = make_doc([("baseline", passes), ("candidate", gains)], named_metric="helpfulness")
    rng = random.Random(11)
    for row in doc["results"]["results"]:
        # A second named score with no real difference between the variants.
        row["namedScores"]["tone"] = rng.random()
    return doc


def test_metrics_are_discovered_from_the_file():
    assert list_metrics(_three_metric_doc()) == ["success", "score", "helpfulness", "tone"]


def test_family_reports_raw_and_adjusted_side_by_side():
    doc = _three_metric_doc()
    samples = [pair_within(doc, metric=m) for m in ("success", "helpfulness", "tone")]
    family = compare_family(samples, reps=400)
    assert len(family.verdicts) == 3
    assert all(adj >= verdict.p for verdict, adj in zip(family.verdicts, family.adjusted))
    assert family.decisions[2] == UNDECIDED, "a metric with no signal must not survive"


def test_a_metric_can_lose_its_significance_to_the_family():
    # Built so that the single-metric verdict and the family verdict disagree.
    a = [True] * 24 + [False] * 26
    b = [True] * 34 + [False] * 16
    doc = make_doc([("baseline", a), ("candidate", b)], named_metric="x")
    sample = pair_within(doc, metric="success")
    alone = compare_family([sample], reps=400)
    assert alone.decisions[0] != UNDECIDED

    padded = compare_family([sample] * 8, reps=400)
    assert padded.adjusted[0] > alone.adjusted[0]
    if padded.decisions[0] == UNDECIDED:
        assert any("not across" in note for note in padded.notes)


def test_family_of_one_is_just_the_verdict():
    doc = _three_metric_doc()
    family = compare_family([pair_within(doc, metric="success")], reps=400)
    assert family.adjusted[0] == pytest.approx(family.verdicts[0].p)
    assert family.notes == [] or "not across" not in family.notes[0]


def test_family_needs_at_least_one_metric():
    with pytest.raises(ValueError):
        compare_family([])


def test_regression_in_the_family_is_reported_as_worse():
    a = [True] * 45 + [False] * 5
    b = [False] * 30 + [True] * 20
    doc = make_doc([("baseline", a), ("candidate", b)])
    family = compare_family([pair_within(doc, metric="success")], reps=400)
    assert family.decisions == [WORSE]
    assert family.survivors == ["success"]
