"""Builds promptfoo output files in the shape the real tool writes them.

Everything here is synthetic on purpose: the test suite must not need network
access, an API key, or a copy of promptfoo installed.
"""

from __future__ import annotations

import json

import pytest

TIMESTAMP = "2026-11-12T00:00:00Z"


def _rows_for(value):
    return value if isinstance(value, list) else [value]


def _cell(value):
    if isinstance(value, bool):
        return value, 1.0 if value else 0.0
    return bool(value >= 0.5), float(value)


def make_doc(
    arms,
    with_vars=True,
    version=3,
    providers=None,
    named_metric=None,
    drop_score=False,
):
    """arms: [(label, [value per test case])], value is bool, float, or a list of repeats."""
    results = []
    prompts = []
    for prompt_idx, (label, values) in enumerate(arms):
        prompts.append({"label": label, "raw": "prompt body %d" % prompt_idx})
        for test_idx, value in enumerate(values):
            for repeat_idx, one in enumerate(_rows_for(value)):
                success, score = _cell(one)
                provider_id = providers[prompt_idx] if providers else "openai:gpt-test"
                row = {
                    "promptIdx": prompt_idx,
                    "testIdx": test_idx,
                    "promptId": "p%d" % prompt_idx,
                    "success": success,
                    "latencyMs": 100,
                    "namedScores": {named_metric: score} if named_metric else {},
                    "provider": {"id": provider_id, "label": provider_id},
                    "prompt": {"raw": "prompt body %d" % prompt_idx, "label": label},
                }
                if not drop_score:
                    row["score"] = score
                if with_vars:
                    row["vars"] = {"question": "q%d" % test_idx}
                if isinstance(value, list):
                    row["repeatIndex"] = repeat_idx
                    row["repeatGroupId"] = "g%d-%d" % (prompt_idx, test_idx)
                results.append(row)

    summary = {
        "version": version,
        "timestamp": TIMESTAMP,
        "results": results,
        "prompts": prompts,
        "stats": {"successes": 0, "failures": 0},
    }
    return {"evalId": "eval-test", "results": summary, "config": {}, "shareableUrl": None}


def write_doc(tmp_path, doc, name="results.json"):
    path = tmp_path / name
    path.write_text(json.dumps(doc), encoding="utf-8")
    return str(path)


@pytest.fixture
def doc_factory():
    return make_doc


@pytest.fixture
def writer(tmp_path):
    def _write(doc, name="results.json"):
        return write_doc(tmp_path, doc, name)

    return _write
