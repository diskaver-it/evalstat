import pytest

from conftest import make_doc
from evalstat.compare import BETTER, UNDECIDED, WORSE, compare
from evalstat.parse import pair_within


def _sample(a, b, **kwargs):
    return pair_within(make_doc([("baseline", a), ("candidate", b)], **kwargs))


def test_a_clear_improvement_is_called_better():
    a = [False] * 40 + [True] * 60
    b = [True] * 95 + [False] * 5
    verdict = compare(_sample(a, b), reps=400)
    assert verdict.decision == BETTER
    assert verdict.diff > 0
    assert verdict.test.startswith("mcnemar")
    assert verdict.gained + verdict.lost + verdict.tied == verdict.n


def test_a_clear_regression_is_called_worse():
    a = [True] * 90 + [False] * 10
    b = [False] * 50 + [True] * 50
    verdict = compare(_sample(a, b), reps=400)
    assert verdict.decision == WORSE
    assert verdict.diff < 0


def test_a_small_difference_on_a_small_set_is_undecided():
    # 31/50 against 34/50 is the shape of result people ship on.
    a = [True] * 31 + [False] * 19
    b = [True] * 29 + [False] * 2 + [True] * 5 + [False] * 14
    verdict = compare(_sample(a, b), reps=400)
    assert verdict.decision == UNDECIDED
    assert verdict.p >= verdict.alpha
    assert any("not the same as equal" in note for note in verdict.notes)
    assert verdict.resolution > 0


def test_identical_runs_are_undecided_with_no_discordant_pairs():
    values = [True, False, True, True, False]
    verdict = compare(_sample(values, values), reps=200)
    assert verdict.decision == UNDECIDED
    assert (verdict.gained, verdict.lost) == (0, 0)
    assert verdict.p == 1.0
    assert verdict.ci == (0.0, 0.0)


def test_continuous_scores_use_the_permutation_test():
    a = [0.1, 0.2, 0.3, 0.25, 0.15] * 8
    b = [0.5, 0.6, 0.7, 0.65, 0.55] * 8
    verdict = compare(pair_within(make_doc([("a", a), ("b", b)]), metric="score"), reps=800)
    assert verdict.test == "paired-permutation"
    assert verdict.decision == BETTER
    assert verdict.gained is None


def test_averaged_repeats_stop_being_treated_as_pass_fail():
    a = [[True, False, False]] * 20
    b = [[True, True, False]] * 20
    verdict = compare(_sample(a, b), reps=400)
    assert verdict.test == "paired-permutation"
    assert any("repeats were averaged" in note for note in verdict.notes)


def test_notes_warn_about_positional_matching():
    verdict = compare(_sample([True] * 10, [False] * 10, with_vars=False), reps=200)
    assert any("matched by position" in note for note in verdict.notes)


def test_notes_count_the_pairs_that_carry_no_information():
    a = [True] * 48 + [False, False]
    b = [True] * 48 + [True, False]
    verdict = compare(_sample(a, b), reps=200)
    assert any("carry no information" in note for note in verdict.notes)


def test_tighter_alpha_makes_the_interval_wider():
    a = [False] * 30 + [True] * 70
    b = [True] * 85 + [False] * 15
    loose = compare(_sample(a, b), alpha=0.05, reps=600)
    tight = compare(_sample(a, b), alpha=0.01, reps=600)
    assert tight.resolution > loose.resolution


def test_nothing_in_common_is_an_error():
    doc_a = make_doc([("a", [True, True])])
    doc_b = make_doc([("b", [True, True])])
    doc_b["results"]["results"] = [
        dict(row, vars={"question": "other%d" % i})
        for i, row in enumerate(doc_b["results"]["results"])
    ]
    from evalstat.parse import pair_across

    with pytest.raises(ValueError):
        compare(pair_across(doc_a, doc_b))
