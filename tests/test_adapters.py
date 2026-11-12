"""The way in for tools that are not promptfoo."""

import json

import pytest

from evalstat.adapters import load_table
from evalstat.compare import compare
from evalstat.parse import EvalFormatError, list_arms, pair_within

CSV = """case,variant,value
q1,baseline,pass
q1,candidate,pass
q2,baseline,fail
q2,candidate,pass
q3,baseline,pass
q3,candidate,fail
"""


def _write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_csv_becomes_the_same_shape_a_promptfoo_file_has(tmp_path):
    doc = load_table(_write(tmp_path, "runs.csv", CSV))
    assert [arm[1] for arm in list_arms(doc)] == ["baseline", "candidate"]
    sample = pair_within(doc)
    assert sample.n == 3
    assert sample.a == [1.0, 0.0, 1.0]
    assert sample.b == [1.0, 1.0, 0.0]
    assert sample.binary


def test_pairing_follows_the_case_column_not_the_row_order(tmp_path):
    shuffled = "case,variant,value\nq2,candidate,1\nq1,baseline,1\nq2,baseline,0\nq1,candidate,0\n"
    doc = load_table(_write(tmp_path, "shuffled.csv", shuffled))

    # The baseline is whichever variant the file mentions first, which here is
    # candidate, so the columns come out the other way round.
    sample = pair_within(doc)
    assert (sample.label_a, sample.label_b) == ("candidate", "baseline")
    pairs = dict(zip(sample.keys, zip(sample.a, sample.b)))
    assert pairs[next(k for k in sample.keys if "q1" in k)] == (0.0, 1.0)

    # Naming the sides removes the dependence on row order entirely.
    pinned = pair_within(doc, a="baseline", b="candidate")
    pinned_pairs = dict(zip(pinned.keys, zip(pinned.a, pinned.b)))
    assert pinned_pairs[next(k for k in pinned.keys if "q1" in k)] == (1.0, 0.0)
    assert pinned_pairs[next(k for k in pinned.keys if "q2" in k)] == (0.0, 1.0)


def test_json_lines(tmp_path):
    lines = "\n".join(
        json.dumps(entry)
        for entry in [
            {"case": "a", "variant": "old", "value": 0.2},
            {"case": "a", "variant": "new", "value": 0.9},
            {"case": "b", "variant": "old", "value": 0.4},
            {"case": "b", "variant": "new", "value": 0.8},
        ]
    )
    sample = pair_within(load_table(_write(tmp_path, "runs.jsonl", lines)), metric="score")
    assert sample.a == pytest.approx([0.2, 0.4])
    assert sample.b == pytest.approx([0.9, 0.8])
    assert not sample.binary


def test_numbers_and_words_both_work_in_the_value_column(tmp_path):
    mixed = "case,variant,value\nq1,a,TRUE\nq1,b,0.75\nq2,a,no\nq2,b,1\n"
    doc = load_table(_write(tmp_path, "mixed.csv", mixed))
    scores = [row["score"] for row in doc["results"]["results"]]
    assert scores == pytest.approx([1.0, 0.75, 0.0, 1.0])


def test_column_names_can_be_overridden(tmp_path):
    custom = "prompt_id,model,accuracy\nq1,gpt,1\nq1,claude,0\n"
    doc = load_table(
        _write(tmp_path, "custom.csv", custom),
        case="prompt_id",
        variant="model",
        value="accuracy",
    )
    assert [arm[1] for arm in list_arms(doc)] == ["gpt", "claude"]


def test_a_table_can_be_compared_end_to_end(tmp_path):
    rows = ["case,variant,value"]
    for i in range(60):
        rows.append("q%d,baseline,%d" % (i, 1 if i < 30 else 0))
        rows.append("q%d,candidate,%d" % (i, 1 if i < 52 else 0))
    doc = load_table(_write(tmp_path, "big.csv", "\n".join(rows)))
    verdict = compare(pair_within(doc), reps=400)
    assert verdict.n == 60
    assert verdict.decision == "better"


def test_tables_that_cannot_be_used(tmp_path):
    with pytest.raises(EvalFormatError):
        load_table(_write(tmp_path, "empty.csv", "case,variant,value\n"))
    with pytest.raises(EvalFormatError):
        load_table(_write(tmp_path, "wrong.csv", "a,b,c\n1,2,3\n"))
    with pytest.raises(EvalFormatError):
        load_table(_write(tmp_path, "junk.csv", "case,variant,value\nq1,a,maybe\n"))
    with pytest.raises(EvalFormatError):
        load_table(_write(tmp_path, "bad.jsonl", "{not json\n"))


def test_blank_lines_in_json_lines_are_skipped(tmp_path):
    lines = '{"case":"a","variant":"x","value":1}\n\n{"case":"a","variant":"y","value":0}\n'
    doc = load_table(_write(tmp_path, "gaps.jsonl", lines))
    assert len(doc["results"]["results"]) == 2
