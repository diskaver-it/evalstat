"""How much to trust the grader before trusting what it graded.

When an LLM decides whether an answer passed, its verdicts are a measurement, and
a measurement with error does not just add noise: it pulls the difference between
two variants towards zero. For a binary judge the shrinkage factor is
sensitivity + specificity - 1, which is why a judge that agrees with a human 85%
of the time can turn a real five point gain into three.

So the useful output is not a grade for the judge. It is the factor by which
everything else in this tool is understated when run on its verdicts.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from . import stats
from .parse import EvalFormatError, _arm_id, _rows, list_arms, vars_key

TRUTH_COLUMNS = ("pass", "passed", "label", "correct", "expected")


@dataclass
class Judge:
    variant: str
    n: int
    agreement: float
    kappa: float
    kappa_ci: Tuple[float, float]
    sensitivity: float
    specificity: float
    attenuation: float
    judged_pass_rate: float
    truth_pass_rate: float
    unmatched_truth: int
    unmatched_rows: int
    notes: List[str] = field(default_factory=list)

    def implied(self, observed_effect: float) -> float:
        """What an observed difference would have been with a perfect judge."""
        if self.attenuation <= 0:
            return float("nan")
        return observed_effect / self.attenuation


def _truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value >= 0.5
    return str(value).strip().lower() in ("1", "true", "yes", "y", "pass", "passed", "ok")


def load_truth(path: str) -> Dict[str, bool]:
    """Human labels, as JSON or CSV, keyed the same way eval rows are keyed."""
    if path.lower().endswith(".csv"):
        return _load_truth_csv(path)
    with open(path, encoding="utf-8") as fh:
        try:
            doc = json.load(fh)
        except json.JSONDecodeError as exc:
            raise EvalFormatError("%s is not JSON: %s" % (path, exc)) from exc

    labels: Dict[str, bool] = {}
    if isinstance(doc, dict):
        for key, value in doc.items():
            labels[key] = _truthy(value)
        return labels
    if isinstance(doc, list):
        for entry in doc:
            if not isinstance(entry, dict):
                continue
            variables = entry.get("vars")
            if not variables:
                raise EvalFormatError("every label needs a vars object to match on")
            label = next((entry[c] for c in TRUTH_COLUMNS if c in entry), None)
            if label is None:
                raise EvalFormatError(
                    "every label needs one of these fields: %s" % ", ".join(TRUTH_COLUMNS)
                )
            labels[vars_key(variables)] = _truthy(label)
        return labels
    raise EvalFormatError("labels must be a list of objects or a mapping")


def _load_truth_csv(path: str) -> Dict[str, bool]:
    labels: Dict[str, bool] = {}
    with open(path, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            raise EvalFormatError("%s has no header row" % path)
        column = next((c for c in reader.fieldnames if c.lower() in TRUTH_COLUMNS), None)
        if column is None:
            raise EvalFormatError(
                "no label column; expected one of %s" % ", ".join(TRUTH_COLUMNS)
            )
        var_columns = [c for c in reader.fieldnames if c != column]
        if not var_columns:
            raise EvalFormatError("the labels carry no columns to match test cases on")
        for row in reader:
            variables = {c: row[c] for c in var_columns}
            labels[vars_key(variables)] = _truthy(row[column])
    return labels


def calibrate(
    doc: dict,
    truth: Dict[str, bool],
    variant: Optional[str] = None,
    by: str = "prompt",
    alpha: float = 0.05,
    reps: int = 2000,
    seed: int = 0,
) -> Judge:
    if not truth:
        raise ValueError("no human labels to compare against")

    arms = list_arms(doc, by)
    if not arms:
        raise EvalFormatError("no variants found in this file")
    chosen = arms[0]
    if variant is not None:
        chosen = next((a for a in arms if variant in (a[0], a[1])), None)
        if chosen is None:
            raise EvalFormatError("no variant %r in this file" % variant)

    pairs = []
    seen = set()
    unmatched_rows = 0
    for row in _rows(doc):
        if _arm_id(row, by) != chosen[0]:
            continue
        variables = row.get("vars") or (row.get("testCase") or {}).get("vars")
        if not variables:
            unmatched_rows += 1
            continue
        key = vars_key(variables)
        if key not in truth:
            unmatched_rows += 1
            continue
        seen.add(key)
        pairs.append((1.0 if row.get("success") else 0.0, 1.0 if truth[key] else 0.0))

    if not pairs:
        raise ValueError("no test case in this file carries a human label")

    judged = [p[0] for p in pairs]
    human = [p[1] for p in pairs]
    n = len(pairs)

    positives = sum(human)
    negatives = n - positives
    sensitivity = (
        sum(1 for j, h in pairs if h == 1.0 and j == 1.0) / positives if positives else float("nan")
    )
    specificity = (
        sum(1 for j, h in pairs if h == 0.0 and j == 0.0) / negatives if negatives else float("nan")
    )

    notes = []
    if positives == 0 or negatives == 0:
        notes.append(
            "The labels are all one class, so sensitivity or specificity is undefined "
            "and the shrinkage factor cannot be estimated."
        )
        attenuation = float("nan")
    else:
        attenuation = sensitivity + specificity - 1

    kappa = stats.cohen_kappa(judged, human)
    kappa_ci = stats.bootstrap_statistic_ci(
        pairs,
        lambda sample: stats.cohen_kappa([s[0] for s in sample], [s[1] for s in sample]),
        alpha=alpha,
        reps=reps,
        seed=seed,
    )

    if attenuation == attenuation and attenuation > 0:
        notes.append(
            "Differences measured through this judge are shrunk by about %.2f, so an "
            "observed gap of 5.0 pp corresponds to roughly %.1f pp of real difference."
            % (attenuation, 5.0 / attenuation)
        )
    if attenuation == attenuation and attenuation <= 0:
        notes.append(
            "This judge carries no usable signal: it agrees with the humans no more "
            "often than a coin would. Nothing measured through it means anything."
        )
    if kappa < 0.6:
        notes.append(
            "Agreement beyond chance is weak (kappa %.2f). Fixing the rubric will buy "
            "more than enlarging the eval set." % kappa
        )
    missing = len(set(truth) - seen)
    if missing:
        notes.append("%d labelled cases do not appear in this run." % missing)

    return Judge(
        variant=chosen[1],
        n=n,
        agreement=sum(1 for j, h in pairs if j == h) / n,
        kappa=kappa,
        kappa_ci=kappa_ci,
        sensitivity=sensitivity,
        specificity=specificity,
        attenuation=attenuation,
        judged_pass_rate=sum(judged) / n,
        truth_pass_rate=positives / n,
        unmatched_truth=missing,
        unmatched_rows=unmatched_rows,
        notes=notes,
    )
