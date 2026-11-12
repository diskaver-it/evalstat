"""Calibrating the grader, and the shrinkage it imposes on everything else."""

import json
import random

import pytest

from conftest import make_doc
from evalstat import stats
from evalstat.judge import calibrate, load_truth
from evalstat.parse import EvalFormatError, vars_key


def test_kappa_matches_a_hand_computed_table():
    # 20 both pass, 5 judge only, 10 human only, 15 both fail.
    judged = [1.0] * 20 + [1.0] * 5 + [0.0] * 10 + [0.0] * 15
    human = [1.0] * 20 + [0.0] * 5 + [1.0] * 10 + [0.0] * 15
    # observed 0.70, chance 0.50, so kappa is 0.40.
    assert stats.cohen_kappa(judged, human) == pytest.approx(0.40)


def test_kappa_punishes_a_rater_that_always_says_pass():
    human = [1.0] * 45 + [0.0] * 5
    lazy = [1.0] * 50
    assert sum(1 for a, b in zip(lazy, human) if a == b) / 50 == pytest.approx(0.90)
    assert stats.cohen_kappa(lazy, human) == pytest.approx(0.0, abs=1e-12)


def test_kappa_edges():
    assert stats.cohen_kappa([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert stats.cohen_kappa([1.0, 1.0], [1.0, 1.0]) == pytest.approx(1.0)
    with pytest.raises(ValueError):
        stats.cohen_kappa([1.0], [1.0, 0.0])


def test_the_shrinkage_factor_is_the_one_that_actually_happens():
    # Build a true difference, then view it through a judge with known error and
    # check the difference comes out shrunk by sensitivity + specificity - 1.
    rng = random.Random(13)
    sensitivity, specificity = 0.90, 0.80
    attenuation = sensitivity + specificity - 1
    true_a, true_b, n = 0.40, 0.60, 40000

    def seen(rate):
        passed = 0
        for _ in range(n):
            truth = rng.random() < rate
            if truth:
                passed += rng.random() < sensitivity
            else:
                passed += rng.random() > specificity
        return passed / n

    observed = seen(true_b) - seen(true_a)
    assert observed == pytest.approx(attenuation * (true_b - true_a), abs=0.01)


def _labelled(n_agree=34, judge_only=3, human_only=5, both_fail=8):
    """A run plus human labels, laid out so the 2x2 table is known."""
    kinds = (
        [("pass", "pass")] * n_agree
        + [("pass", "fail")] * judge_only
        + [("fail", "pass")] * human_only
        + [("fail", "fail")] * both_fail
    )
    doc = make_doc([("graded", [k[0] == "pass" for k in kinds])])
    truth = {}
    for index, kind in enumerate(kinds):
        truth[vars_key({"question": "q%d" % index})] = kind[1] == "pass"
    return doc, truth


def test_calibrate_reports_the_table_and_the_factor():
    doc, truth = _labelled()
    result = calibrate(doc, truth, reps=300)
    assert result.n == 50
    assert result.agreement == pytest.approx(42 / 50)
    assert result.sensitivity == pytest.approx(34 / 39)
    assert result.specificity == pytest.approx(8 / 11)
    assert result.attenuation == pytest.approx(result.sensitivity + result.specificity - 1)
    assert result.kappa_ci[0] < result.kappa < result.kappa_ci[1]


def test_implied_effect_undoes_the_shrinkage():
    doc, truth = _labelled()
    result = calibrate(doc, truth, reps=200)
    assert result.implied(0.05) > 0.05
    assert result.implied(0.05) == pytest.approx(0.05 / result.attenuation)


def test_a_useless_judge_is_called_useless():
    # Judge agrees with the humans exactly as often as a coin: se + sp = 1.
    doc, truth = _labelled(n_agree=10, judge_only=10, human_only=10, both_fail=10)
    result = calibrate(doc, truth, reps=200)
    assert result.attenuation == pytest.approx(0.0, abs=1e-9)
    assert any("no usable signal" in note for note in result.notes)
    assert result.implied(0.05) != result.implied(0.05)  # nan


def test_weak_agreement_is_called_out():
    doc, truth = _labelled(n_agree=20, judge_only=10, human_only=10, both_fail=10)
    result = calibrate(doc, truth, reps=200)
    assert any("Fixing the rubric" in note for note in result.notes)


def test_labels_for_cases_not_in_the_run_are_counted():
    doc, truth = _labelled()
    truth[vars_key({"question": "q999"})] = True
    result = calibrate(doc, truth, reps=200)
    assert result.unmatched_truth == 1
    assert any("do not appear in this run" in note for note in result.notes)


def test_one_sided_labels_leave_the_factor_undefined():
    doc, truth = _labelled(n_agree=30, judge_only=0, human_only=20, both_fail=0)
    result = calibrate(doc, truth, reps=200)
    assert result.attenuation != result.attenuation
    assert any("all one class" in note for note in result.notes)


def test_truth_as_json_list_of_vars(tmp_path):
    path = tmp_path / "labels.json"
    path.write_text(
        json.dumps([{"vars": {"question": "q0"}, "pass": True},
                    {"vars": {"question": "q1"}, "pass": "no"}]),
        encoding="utf-8",
    )
    labels = load_truth(str(path))
    assert labels[vars_key({"question": "q0"})] is True
    assert labels[vars_key({"question": "q1"})] is False


def test_truth_as_csv(tmp_path):
    path = tmp_path / "labels.csv"
    path.write_text("question,pass\nq0,yes\nq1,0\n", encoding="utf-8")
    labels = load_truth(str(path))
    assert labels[vars_key({"question": "q0"})] is True
    assert labels[vars_key({"question": "q1"})] is False


def test_truth_files_that_cannot_be_used(tmp_path):
    broken = tmp_path / "broken.json"
    broken.write_text("{", encoding="utf-8")
    with pytest.raises(EvalFormatError):
        load_truth(str(broken))

    no_label = tmp_path / "nolabel.json"
    no_label.write_text(json.dumps([{"vars": {"question": "q0"}}]), encoding="utf-8")
    with pytest.raises(EvalFormatError):
        load_truth(str(no_label))

    no_column = tmp_path / "nocol.csv"
    no_column.write_text("question,verdict\nq0,yes\n", encoding="utf-8")
    with pytest.raises(EvalFormatError):
        load_truth(str(no_column))


def test_calibrate_needs_overlap():
    doc, _ = _labelled()
    with pytest.raises(ValueError):
        calibrate(doc, {vars_key({"question": "elsewhere"}): True}, reps=50)
    with pytest.raises(ValueError):
        calibrate(doc, {}, reps=50)


def test_calibrate_rejects_an_unknown_variant():
    doc, truth = _labelled()
    with pytest.raises(EvalFormatError):
        calibrate(doc, truth, variant="ghost", reps=50)
