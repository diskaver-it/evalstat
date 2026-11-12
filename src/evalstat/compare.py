"""Turns a paired sample into a verdict."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from . import stats
from .parse import PairedSample

BETTER = "better"
WORSE = "worse"
UNDECIDED = "undecided"


@dataclass
class Verdict:
    metric: str
    label_a: str
    label_b: str
    n: int
    mean_a: float
    mean_b: float
    diff: float
    ci: Tuple[float, float]
    p: float
    alpha: float
    test: str
    exact: bool
    decision: str
    gained: Optional[int] = None
    lost: Optional[int] = None
    tied: Optional[int] = None
    notes: List[str] = field(default_factory=list)

    @property
    def resolution(self) -> float:
        """Half-width of the interval: the smallest effect this run could see."""
        lo, hi = self.ci
        return (hi - lo) / 2.0


def compare(
    sample: PairedSample,
    alpha: float = 0.05,
    reps: int = 10000,
    seed: int = 0,
) -> Verdict:
    if sample.n == 0:
        raise ValueError("no test case appears in both variants, so nothing is paired")

    diffs = sample.diffs
    gained = lost = tied = None
    if sample.binary:
        gained, lost = stats.discordant(sample.a, sample.b)
        tied = sample.n - gained - lost
        _, p, exact = stats.mcnemar(gained, lost)
        test = "mcnemar-exact" if exact else "mcnemar-chi2"
    else:
        p = stats.sign_flip_p(diffs, reps=reps, seed=seed)
        test = "paired-permutation"
        exact = False

    ci = stats.bootstrap_mean_ci(diffs, alpha=alpha, reps=reps, seed=seed + 1)
    diff = stats.mean(diffs)

    if p < alpha:
        decision = BETTER if diff > 0 else WORSE
    else:
        decision = UNDECIDED

    verdict = Verdict(
        metric=sample.metric,
        label_a=sample.label_a,
        label_b=sample.label_b,
        n=sample.n,
        mean_a=stats.mean(sample.a),
        mean_b=stats.mean(sample.b),
        diff=diff,
        ci=ci,
        p=p,
        alpha=alpha,
        test=test,
        exact=exact,
        decision=decision,
        gained=gained,
        lost=lost,
        tied=tied,
    )
    verdict.notes = _notes(sample, verdict)
    return verdict


@dataclass
class Family:
    """Several metrics judged together, so the 5% belongs to the family."""

    alpha: float
    verdicts: List[Verdict]
    adjusted: List[float]
    decisions: List[str]
    notes: List[str] = field(default_factory=list)

    @property
    def survivors(self) -> List[str]:
        return [
            v.metric for v, d in zip(self.verdicts, self.decisions) if d != UNDECIDED
        ]


def compare_family(
    samples: List[PairedSample],
    alpha: float = 0.05,
    reps: int = 10000,
    seed: int = 0,
) -> Family:
    if not samples:
        raise ValueError("no metric to compare")
    verdicts = [compare(s, alpha=alpha, reps=reps, seed=seed) for s in samples]
    adjusted = stats.holm([v.p for v in verdicts])

    decisions = []
    for verdict, adjusted_p in zip(verdicts, adjusted):
        if adjusted_p < alpha:
            decisions.append(BETTER if verdict.diff > 0 else WORSE)
        else:
            decisions.append(UNDECIDED)

    notes = []
    lost = [
        verdict.metric
        for verdict, decision in zip(verdicts, decisions)
        if verdict.decision != UNDECIDED and decision == UNDECIDED
    ]
    if lost:
        notes.append(
            "Significant on its own but not across %d metrics: %s. Looking at several "
            "metrics gives several chances to be wrong, and the correction is what you "
            "pay for having looked." % (len(samples), ", ".join(lost))
        )
    if len(samples) > 1 and not any(d != UNDECIDED for d in decisions):
        notes.append("Nothing survives the correction, so nothing here is established.")
    return Family(
        alpha=alpha,
        verdicts=verdicts,
        adjusted=adjusted,
        decisions=decisions,
        notes=notes,
    )


def _notes(sample: PairedSample, verdict: Verdict) -> List[str]:
    notes = []
    if sample.positional_keys:
        notes.append(
            "Test cases were matched by position, because the rows carry no vars. "
            "That is safe inside one run and wrong across two runs if the eval set changed."
        )
    if sample.only_a or sample.only_b:
        notes.append(
            "Unmatched test cases were dropped: %d only in %s, %d only in %s."
            % (sample.only_a, sample.label_a, sample.only_b, sample.label_b)
        )
    if sample.repeats > 1:
        notes.append(
            "Each test case ran up to %d times; repeats were averaged into one "
            "observation per cell rather than counted as independent rows." % sample.repeats
        )
    if verdict.gained is not None and verdict.tied is not None:
        notes.append(
            "%d of %d pairs agreed in both variants and carry no information about "
            "the difference." % (verdict.tied, verdict.n)
        )
    lo, hi = verdict.ci
    if verdict.decision == UNDECIDED and lo <= 0 <= hi:
        notes.append(
            "Undecided is not the same as equal: an effect smaller than %.1f pp "
            "would not have been visible at this sample size." % (abs(verdict.resolution) * 100)
        )
    if verdict.p < verdict.alpha and lo <= 0 <= hi:
        notes.append(
            "The test and the interval disagree, which happens near the threshold "
            "because they are different procedures. Treat this as not established."
        )
    return notes
