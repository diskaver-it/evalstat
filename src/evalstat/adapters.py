"""A way in for eval tools other than promptfoo.

Rather than guess at the output format of every framework, this reads a three
column table: which test case, which variant, what it scored. Any tool that can
export CSV or JSON lines can be compared, and the rest of evalstat does not need
to know where the numbers came from, because the table is turned into the same
internal shape a promptfoo file produces.
"""

from __future__ import annotations

import csv
import json
from typing import Dict, List

from .parse import EvalFormatError

TRUE_WORDS = ("1", "true", "yes", "y", "pass", "passed", "ok")
FALSE_WORDS = ("0", "false", "no", "n", "fail", "failed")


def _as_cell(raw) -> tuple:
    """(success, score) from whatever the table had in the value column."""
    if isinstance(raw, bool):
        return raw, 1.0 if raw else 0.0
    if isinstance(raw, (int, float)):
        return float(raw) >= 0.5, float(raw)
    text = str(raw).strip().lower()
    if text in TRUE_WORDS:
        return True, 1.0
    if text in FALSE_WORDS:
        return False, 0.0
    try:
        number = float(text)
    except ValueError:
        raise EvalFormatError(
            "value %r is neither a number nor a pass/fail word" % raw
        ) from None
    return number >= 0.5, number


def _read_rows(path: str) -> List[dict]:
    if path.lower().endswith(".csv"):
        with open(path, encoding="utf-8", newline="") as fh:
            return list(csv.DictReader(fh))
    rows = []
    with open(path, encoding="utf-8") as fh:
        for number, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as exc:
                raise EvalFormatError("line %d of %s is not JSON: %s" % (number, path, exc))
            if isinstance(entry, dict):
                rows.append(entry)
    return rows


def load_table(
    path: str,
    case: str = "case",
    variant: str = "variant",
    value: str = "value",
) -> dict:
    rows = _read_rows(path)
    if not rows:
        raise EvalFormatError("%s holds no rows" % path)
    for column in (case, variant, value):
        if column not in rows[0]:
            raise EvalFormatError(
                "column %r is missing; the file has %s"
                % (column, ", ".join(sorted(rows[0])))
            )

    variants: List[str] = []
    cases: List[str] = []
    case_index: Dict[str, int] = {}
    results = []
    for row in rows:
        variant_name = str(row[variant])
        case_name = str(row[case])
        if variant_name not in variants:
            variants.append(variant_name)
        if case_name not in case_index:
            case_index[case_name] = len(cases)
            cases.append(case_name)
        success, score = _as_cell(row[value])
        results.append(
            {
                "promptIdx": variants.index(variant_name),
                "testIdx": case_index[case_name],
                "vars": {case: case_name},
                "success": success,
                "score": score,
                "namedScores": {},
                "provider": {"id": variant_name, "label": variant_name},
                "prompt": {"raw": variant_name, "label": variant_name},
            }
        )

    return {
        "evalId": path,
        "results": {
            "version": 3,
            "timestamp": "",
            "results": results,
            "prompts": [{"label": name} for name in variants],
            "stats": {},
        },
        "config": {},
        "shareableUrl": None,
    }
