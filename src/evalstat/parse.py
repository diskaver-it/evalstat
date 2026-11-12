"""Reads a promptfoo output file and recovers the pairs it already contains.

A promptfoo run that compares two prompts stores every (test case, variant) cell
in one flat results list, keyed by testIdx and promptIdx. The report shows the
two variants as independent columns of means; the pairing is right there in the
file and is simply never used.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

SUCCESS = "success"
SCORE = "score"


class EvalFormatError(ValueError):
    pass


def load(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        try:
            doc = json.load(fh)
        except json.JSONDecodeError as exc:
            raise EvalFormatError("%s is not JSON: %s" % (path, exc)) from exc
    if not isinstance(doc, dict):
        raise EvalFormatError("%s does not look like a promptfoo output file" % path)
    return doc


def _summary(doc: dict) -> dict:
    # --output writes OutputFile{evalId, results: EvaluateSummary}, but shared
    # exports and older versions hand over the summary itself.
    inner = doc.get("results")
    if isinstance(inner, dict):
        return inner
    if isinstance(inner, list):
        return doc
    raise EvalFormatError("no results found; expected a promptfoo --output file")


def _rows(doc: dict) -> List[dict]:
    rows = _summary(doc).get("results")
    if not isinstance(rows, list):
        raise EvalFormatError("results is not a list of eval rows")
    return [r for r in rows if isinstance(r, dict)]


def _prompt_labels(doc: dict) -> Dict[int, str]:
    summary = _summary(doc)
    prompts = summary.get("prompts")
    if not isinstance(prompts, list):
        # v2 keeps the column headers in the table instead.
        prompts = ((summary.get("table") or {}).get("head") or {}).get("prompts") or []
    labels = {}
    for i, prompt in enumerate(prompts):
        if not isinstance(prompt, dict):
            continue
        label = prompt.get("label") or prompt.get("display") or prompt.get("raw") or prompt.get("id")
        if isinstance(label, str) and label.strip():
            labels[i] = " ".join(label.split())[:60]
    return labels


def _arm_id(row: dict, by: str) -> Optional[str]:
    if by == "prompt":
        idx = row.get("promptIdx")
        return None if idx is None else str(idx)
    if by == "provider":
        provider = row.get("provider")
        if isinstance(provider, dict):
            return provider.get("label") or provider.get("id")
        return provider if isinstance(provider, str) else None
    raise ValueError("by must be either prompt or provider")


def vars_key(variables: dict) -> str:
    """Canonical identity of a test case, so two sources agree on what a case is."""
    return json.dumps(variables, sort_keys=True, ensure_ascii=False, default=str)


def _pair_key(row: dict) -> Tuple[str, bool]:
    """Identity of the test case, and whether we had to fall back to position."""
    variables = row.get("vars") or (row.get("testCase") or {}).get("vars")
    if variables:
        return vars_key(variables), False
    return "#%s" % row.get("testIdx"), True


def _value(row: dict, metric: str) -> Optional[float]:
    if metric == SUCCESS:
        return 1.0 if row.get("success") else 0.0
    if metric == SCORE:
        raw = row.get("score")
        return None if raw is None else float(raw)
    named = row.get("namedScores") or {}
    if metric in named:
        return float(named[metric])
    return None


def _cells(doc: dict, by: str, metric: str) -> Tuple[Dict[str, Dict[str, List[float]]], bool]:
    """arm id -> test case key -> every observed value, repeats included."""
    cells: Dict[str, Dict[str, List[float]]] = {}
    positional = False
    for row in _rows(doc):
        arm = _arm_id(row, by)
        if arm is None:
            continue
        value = _value(row, metric)
        if value is None:
            continue
        key, fallback = _pair_key(row)
        positional = positional or fallback
        cells.setdefault(arm, {}).setdefault(key, []).append(value)
    if not cells:
        raise EvalFormatError("no rows carried the metric %r" % metric)
    return cells, positional


def list_arms(doc: dict, by: str = "prompt") -> List[Tuple[str, str, int]]:
    """(id, human label, row count) for every variant in the file, in file order."""
    labels = _prompt_labels(doc) if by == "prompt" else {}
    counts: Dict[str, int] = {}
    order: List[str] = []
    for row in _rows(doc):
        arm = _arm_id(row, by)
        if arm is None:
            continue
        if arm not in counts:
            order.append(arm)
            counts[arm] = 0
        counts[arm] += 1
    arms = []
    for arm in order:
        label = labels.get(int(arm)) if by == "prompt" and arm.isdigit() else None
        arms.append((arm, label or arm, counts[arm]))
    return arms


def list_metrics(doc: dict) -> List[str]:
    """Metrics the file can actually be compared on, in a stable order."""
    metrics = [SUCCESS]
    if any(row.get(SCORE) is not None for row in _rows(doc)):
        metrics.append(SCORE)
    named = []
    for row in _rows(doc):
        for name in (row.get("namedScores") or {}):
            if name not in named:
                named.append(name)
    return metrics + sorted(named)


@dataclass
class PairedSample:
    metric: str
    label_a: str
    label_b: str
    keys: List[str]
    a: List[float]
    b: List[float]
    repeats: int
    positional_keys: bool
    only_a: int
    only_b: int

    @property
    def n(self) -> int:
        return len(self.keys)

    @property
    def binary(self) -> bool:
        return all(v in (0.0, 1.0) for v in self.a + self.b)

    @property
    def diffs(self) -> List[float]:
        return [y - x for x, y in zip(self.a, self.b)]


def _align(
    cells_a: Dict[str, List[float]],
    cells_b: Dict[str, List[float]],
    metric: str,
    label_a: str,
    label_b: str,
    positional: bool,
) -> PairedSample:
    shared = [key for key in cells_a if key in cells_b]
    # Repeated runs of one test case are not independent observations, so they
    # collapse to one number per cell instead of inflating n.
    repeats = max([len(cells_a[k]) for k in shared] + [len(cells_b[k]) for k in shared] + [0])
    return PairedSample(
        metric=metric,
        label_a=label_a,
        label_b=label_b,
        keys=shared,
        a=[sum(cells_a[k]) / len(cells_a[k]) for k in shared],
        b=[sum(cells_b[k]) / len(cells_b[k]) for k in shared],
        repeats=repeats,
        positional_keys=positional,
        only_a=sum(1 for key in cells_a if key not in cells_b),
        only_b=sum(1 for key in cells_b if key not in cells_a),
    )


def _resolve(arms: Sequence[Tuple[str, str, int]], wanted: Optional[str], fallback_pos: int):
    if wanted is None:
        if len(arms) <= fallback_pos:
            raise EvalFormatError(
                "the file holds %d comparable variant(s); say which two to compare" % len(arms)
            )
        return arms[fallback_pos]
    for arm in arms:
        if wanted == arm[0] or wanted == arm[1]:
            return arm
    raise EvalFormatError("no variant %r in this file" % wanted)


def pair_within(
    doc: dict,
    a: Optional[str] = None,
    b: Optional[str] = None,
    metric: str = SUCCESS,
    by: str = "prompt",
) -> PairedSample:
    cells, positional = _cells(doc, by, metric)
    arms = [arm for arm in list_arms(doc, by) if arm[0] in cells]
    arm_a = _resolve(arms, a, 0)
    arm_b = _resolve(arms, b, 1)
    if arm_a[0] == arm_b[0]:
        raise EvalFormatError("both sides point at the same variant (%s)" % arm_a[1])
    return _align(cells[arm_a[0]], cells[arm_b[0]], metric, arm_a[1], arm_b[1], positional)


def pair_across(
    doc_a: dict,
    doc_b: dict,
    a: Optional[str] = None,
    b: Optional[str] = None,
    metric: str = SUCCESS,
    by: str = "prompt",
) -> PairedSample:
    cells_a, pos_a = _cells(doc_a, by, metric)
    cells_b, pos_b = _cells(doc_b, by, metric)
    arm_a = _resolve([arm for arm in list_arms(doc_a, by) if arm[0] in cells_a], a, 0)
    arm_b = _resolve([arm for arm in list_arms(doc_b, by) if arm[0] in cells_b], b, 0)
    return _align(
        cells_a[arm_a[0]],
        cells_b[arm_b[0]],
        metric,
        "before: %s" % arm_a[1],
        "after: %s" % arm_b[1],
        pos_a or pos_b,
    )
