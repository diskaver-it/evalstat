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


def test_arms_lists_the_variants(tmp_path, capsys):
    assert main(["arms", _improved(tmp_path)]) == OK
    out = capsys.readouterr().out
    assert "baseline" in out and "candidate" in out
    assert "2 variant(s)" in out


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
