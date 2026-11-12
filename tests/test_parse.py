import pytest

from conftest import make_doc
from evalstat.parse import EvalFormatError, list_arms, load, pair_across, pair_within


def test_pairs_come_from_one_file():
    doc = make_doc([("baseline", [True, False, True]), ("candidate", [True, True, True])])
    sample = pair_within(doc)
    assert sample.n == 3
    assert sample.a == [1.0, 0.0, 1.0]
    assert sample.b == [1.0, 1.0, 1.0]
    assert sample.binary
    assert sample.label_a == "baseline"
    assert sample.label_b == "candidate"


def test_pairing_follows_vars_not_row_order():
    doc = make_doc([("a", [True, False]), ("b", [False, True])])
    rows = doc["results"]["results"]
    # The same test case reached the second arm in the opposite order, which is
    # what happens whenever promptfoo interleaves providers or retries a row.
    second_arm = [r for r in rows if r["promptIdx"] == 1]
    doc["results"]["results"] = [r for r in rows if r["promptIdx"] == 0] + second_arm[::-1]

    sample = pair_within(doc)
    pairs = dict(zip(sample.keys, zip(sample.a, sample.b)))
    key_q0 = next(k for k in sample.keys if "q0" in k)
    assert pairs[key_q0] == (1.0, 0.0)
    assert not sample.positional_keys


def test_positional_fallback_is_flagged():
    doc = make_doc([("a", [True, False]), ("b", [True, True])], with_vars=False)
    sample = pair_within(doc)
    assert sample.n == 2
    assert sample.positional_keys


def test_repeats_collapse_instead_of_inflating_n():
    doc = make_doc(
        [("a", [[True, True, False], [False, False, False]]), ("b", [[True, True, True], [True, False, False]])]
    )
    sample = pair_within(doc)
    assert sample.n == 2, "three runs of one test case are not three observations"
    assert sample.repeats == 3
    assert sample.a == pytest.approx([2 / 3, 0.0])
    assert sample.b == pytest.approx([1.0, 1 / 3])
    assert not sample.binary, "averaged repeats are proportions, not pass/fail"


def test_unmatched_test_cases_are_dropped_and_counted():
    doc_a = make_doc([("a", [True, False, True])])
    doc_b = make_doc([("b", [True, True])])
    sample = pair_across(doc_a, doc_b)
    assert sample.n == 2
    assert sample.only_a == 1
    assert sample.only_b == 0


def test_metric_can_be_a_score_or_a_named_score():
    doc = make_doc([("a", [0.2, 0.4]), ("b", [0.6, 0.9])], named_metric="helpfulness")
    scores = pair_within(doc, metric="score")
    assert scores.a == pytest.approx([0.2, 0.4])
    assert not scores.binary

    named = pair_within(doc, metric="helpfulness")
    assert named.b == pytest.approx([0.6, 0.9])


def test_grouping_by_provider():
    doc = make_doc(
        [("a", [True, False]), ("b", [True, True])],
        providers=["openai:gpt-x", "anthropic:claude-y"],
    )
    arms = list_arms(doc, by="provider")
    assert [arm[0] for arm in arms] == ["openai:gpt-x", "anthropic:claude-y"]
    sample = pair_within(doc, by="provider")
    assert sample.label_b == "anthropic:claude-y"


def test_v2_layout_is_accepted():
    doc = make_doc([("a", [True]), ("b", [False])], version=2)
    summary = doc["results"]
    summary["table"] = {"head": {"prompts": [{"label": "a"}, {"label": "b"}]}, "body": []}
    del summary["prompts"]
    sample = pair_within(doc)
    assert sample.label_a == "a" and sample.label_b == "b"


def test_bare_summary_without_the_output_wrapper():
    doc = make_doc([("a", [True]), ("b", [True])])
    sample = pair_within(doc["results"])
    assert sample.n == 1


def test_arms_reports_labels_and_counts():
    doc = make_doc([("baseline", [True, False]), ("candidate", [True, True])])
    assert list_arms(doc) == [("0", "baseline", 2), ("1", "candidate", 2)]


def test_missing_metric_is_an_error():
    doc = make_doc([("a", [True]), ("b", [True])])
    with pytest.raises(EvalFormatError):
        pair_within(doc, metric="not_a_metric")


def test_one_variant_cannot_be_compared_with_itself():
    doc = make_doc([("only", [True, False])])
    with pytest.raises(EvalFormatError):
        pair_within(doc)
    with pytest.raises(EvalFormatError):
        pair_within(doc, a="only", b="only")


def test_unknown_variant_name():
    doc = make_doc([("a", [True]), ("b", [True])])
    with pytest.raises(EvalFormatError):
        pair_within(doc, a="a", b="nope")


def test_rejects_files_that_are_not_eval_output(tmp_path):
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    with pytest.raises(EvalFormatError):
        load(str(broken))

    empty = tmp_path / "empty.json"
    empty.write_text('{"hello": 1}', encoding="utf-8")
    with pytest.raises(EvalFormatError):
        pair_within(load(str(empty)))


def test_rows_missing_the_score_field_are_skipped():
    doc = make_doc([("a", [True, True]), ("b", [True, True])], drop_score=True)
    with pytest.raises(EvalFormatError):
        pair_within(doc, metric="score")
    assert pair_within(doc, metric="success").n == 2
