import json

from conftest import make_doc, write_doc
from evalstat.cli import BAD_INPUT, GATE_TRIPPED, OK, main


def _improved(tmp_path, name="results.json"):
    doc = make_doc(
        [("baseline", [False] * 40 + [True] * 60), ("candidate", [True] * 95 + [False] * 5)]
    )
    return write_doc(tmp_path, doc, name)


def _regressed(tmp_path):
    doc = make_doc(
        [("baseline", [True] * 90 + [False] * 10), ("candidate", [False] * 50 + [True] * 50)]
    )
    return write_doc(tmp_path, doc, "regressed.json")


def test_compare_prints_a_verdict(tmp_path, capsys):
    assert main(["compare", _improved(tmp_path), "--reps", "200"]) == OK
    out = capsys.readouterr().out
    assert "VERDICT" in out
    assert "paired test cases" in out
    assert "candidate" in out


def test_gate_stays_quiet_on_an_improvement(tmp_path):
    args = ["compare", _improved(tmp_path), "--reps", "200", "--fail-on", "regression"]
    assert main(args) == OK


def test_gate_trips_on_a_regression(tmp_path):
    args = ["compare", _regressed(tmp_path), "--reps", "200", "--fail-on", "regression"]
    assert main(args) == GATE_TRIPPED


def test_fail_on_any_trips_on_an_improvement_too(tmp_path):
    args = ["compare", _improved(tmp_path), "--reps", "200", "--fail-on", "any"]
    assert main(args) == GATE_TRIPPED


def test_json_output_is_machine_readable(tmp_path, capsys):
    main(["compare", _improved(tmp_path), "--reps", "200", "--format", "json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["decision"] == "better"
    assert len(payload["ci"]) == 2
    assert payload["headline"]


def test_markdown_output_is_a_table(tmp_path, capsys):
    main(["compare", _improved(tmp_path), "--reps", "200", "--format", "markdown"])
    out = capsys.readouterr().out
    assert out.startswith("**")
    assert "| --- | --- |" in out


def test_two_files_are_compared_as_before_and_after(tmp_path, capsys):
    before = write_doc(tmp_path, make_doc([("v1", [True, False, True, False])]), "before.json")
    after = write_doc(tmp_path, make_doc([("v2", [True, True, True, True])]), "after.json")
    assert main(["compare", before, after, "--reps", "200"]) == OK
    out = capsys.readouterr().out
    assert "before: v1" in out and "after: v2" in out


def test_anytime_adds_a_second_block(tmp_path, capsys):
    assert main(["compare", _improved(tmp_path), "--reps", "200", "--anytime"]) == OK
    out = capsys.readouterr().out
    assert "watched continuously" in out
    assert "anytime interval" in out
    assert "times narrower" in out


def test_anytime_in_json_is_one_object(tmp_path, capsys):
    main(["compare", _improved(tmp_path), "--reps", "200", "--anytime", "--format", "json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["decision"] == "better"
    assert payload["anytime"]["decision"] in ("established", "not established")
    assert len(payload["anytime"]["interval"]) == 2


def test_the_gate_gets_stricter_under_anytime(tmp_path):
    # A regression the fixed test calls significant, on a set too small to
    # establish it when the metric is watched after every commit.
    doc = make_doc(
        [("baseline", [True] * 24 + [False] * 16), ("candidate", [True] * 15 + [False] * 25)]
    )
    path = write_doc(tmp_path, doc, "small_regression.json")
    assert main(["compare", path, "--reps", "200", "--fail-on", "regression"]) == GATE_TRIPPED
    args = ["compare", path, "--reps", "200", "--fail-on", "regression", "--anytime"]
    assert main(args) == OK


def test_anytime_still_trips_on_a_large_regression(tmp_path):
    doc = make_doc(
        [("baseline", [True] * 180 + [False] * 20), ("candidate", [False] * 150 + [True] * 50)]
    )
    path = write_doc(tmp_path, doc, "big_regression.json")
    args = ["compare", path, "--reps", "200", "--fail-on", "regression", "--anytime"]
    assert main(args) == GATE_TRIPPED


def test_plan_reports_what_the_set_can_see(tmp_path, capsys):
    assert main(["plan", _improved(tmp_path), "--detect", "0.03"]) == OK
    out = capsys.readouterr().out
    assert "the variants disagreed on" in out
    assert "to see +3.0 pp you need" in out


def test_plan_as_json(tmp_path, capsys):
    assert main(["plan", _improved(tmp_path), "--format", "json"]) == OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["needed"] is None
    assert payload["mde"] > 0


def test_plan_refuses_a_file_where_nothing_disagreed(tmp_path, capsys):
    doc = make_doc([("a", [True, False, True]), ("b", [True, False, True])])
    assert main(["plan", write_doc(tmp_path, doc, "same.json")]) == BAD_INPUT
    assert "agreed on every case" in capsys.readouterr().err


def test_arms_lists_the_variants_and_the_metrics(tmp_path, capsys):
    assert main(["arms", _improved(tmp_path)]) == OK
    out = capsys.readouterr().out
    assert "baseline" in out and "candidate" in out
    assert "2 variant(s)" in out
    assert "metrics: success, score" in out


def _multi_metric(tmp_path):
    doc = make_doc(
        [("baseline", [True] * 30 + [False] * 20), ("candidate", [True] * 37 + [False] * 13)],
        named_metric="helpfulness",
    )
    return write_doc(tmp_path, doc, "multi.json")


def test_several_metrics_are_judged_as_a_family(tmp_path, capsys):
    assert main(["compare", _multi_metric(tmp_path), "--metric", "all", "--reps", "200"]) == OK
    out = capsys.readouterr().out
    assert "metrics on 50 paired test cases" in out
    assert "adjusted" in out
    assert "helpfulness" in out


def test_a_comma_separated_list_picks_the_family(tmp_path, capsys):
    args = ["compare", _multi_metric(tmp_path), "--metric", "success,helpfulness", "--reps", "200"]
    assert main(args) == OK
    assert "2 metrics" in capsys.readouterr().out


def test_family_as_json_lists_every_metric(tmp_path, capsys):
    args = [
        "compare", _multi_metric(tmp_path), "--metric", "all", "--reps", "200", "--format", "json"
    ]
    main(args)
    payload = json.loads(capsys.readouterr().out)
    assert len(payload["metrics"]) == 3
    assert all("adjusted_p" in row for row in payload["metrics"])


def test_anytime_and_a_family_do_not_mix(tmp_path, capsys):
    args = ["compare", _multi_metric(tmp_path), "--metric", "all", "--anytime"]
    assert main(args) == BAD_INPUT
    assert "one metric at a time" in capsys.readouterr().err


def test_a_csv_table_can_be_compared(tmp_path, capsys):
    rows = ["case,variant,value"]
    for i in range(40):
        rows.append("q%d,old,%d" % (i, 1 if i < 20 else 0))
        rows.append("q%d,new,%d" % (i, 1 if i < 34 else 0))
    path = tmp_path / "runs.csv"
    path.write_text("\n".join(rows), encoding="utf-8")
    assert main(["compare", str(path), "--reps", "200"]) == OK
    out = capsys.readouterr().out
    assert "old" in out and "new" in out


def test_custom_columns_through_the_cli(tmp_path, capsys):
    path = tmp_path / "custom.csv"
    path.write_text("q,model,acc\nq1,gpt,1\nq1,claude,0\nq2,gpt,1\nq2,claude,1\n", encoding="utf-8")
    args = [
        "compare", str(path), "--reps", "100",
        "--case-column", "q", "--variant-column", "model", "--value-column", "acc",
    ]
    assert main(args) == OK
    assert "gpt" in capsys.readouterr().out


def test_judge_through_the_cli(tmp_path, capsys):
    from evalstat.parse import vars_key

    labels = [
        {"vars": {"question": "q%d" % i}, "pass": i < 28}
        for i in range(50)
    ]
    labels_path = tmp_path / "labels.json"
    labels_path.write_text(json.dumps(labels), encoding="utf-8")
    assert vars_key({"question": "q0"})

    args = ["judge", _multi_metric(tmp_path), "--truth", str(labels_path), "--reps", "200"]
    assert main(args) == OK
    out = capsys.readouterr().out
    assert "agreement with the humans" in out
    assert "shrinkage factor" in out


def test_judge_reports_a_missing_labels_file(tmp_path, capsys):
    args = ["judge", _multi_metric(tmp_path), "--truth", str(tmp_path / "nope.json")]
    assert main(args) == BAD_INPUT
    assert "evalstat:" in capsys.readouterr().err


def test_a_missing_file_is_reported_not_raised(tmp_path, capsys):
    assert main(["compare", str(tmp_path / "nope.json")]) == BAD_INPUT
    assert "evalstat:" in capsys.readouterr().err


def test_an_unknown_variant_is_reported(tmp_path, capsys):
    assert main(["compare", _improved(tmp_path), "--b", "ghost"]) == BAD_INPUT
    assert "no variant" in capsys.readouterr().err


def test_more_than_two_files_is_refused(tmp_path, capsys):
    path = _improved(tmp_path)
    assert main(["compare", path, path, path]) == BAD_INPUT
    assert "one or two files" in capsys.readouterr().err
