"""Answers the question a verdict of undecided leaves behind: how many cases?

The useful part is that the assumption does not have to be invented. A run that
has already happened says how often the two variants actually disagree, and for
a paired test that rate is what drives power.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from . import stats
from .parse import PairedSample


@dataclass
class Plan:
    metric: str
    n: int
    binary: bool
    alpha: float
    power: float
    spread: float
    """Discordant rate for pass/fail, standard deviation of differences otherwise."""
    mde: float
    detect: Optional[float] = None
    needed: Optional[float] = None
    discordant: Optional[int] = None


def plan(
    sample: PairedSample,
    detect: Optional[float] = None,
    alpha: float = 0.05,
    power: float = 0.8,
) -> Plan:
    if sample.n == 0:
        raise ValueError("no test case appears in both variants, so nothing is paired")
    if not 0.0 < power < 1.0:
        raise ValueError("power must be between 0 and 1")

    if sample.binary:
        gained, lost = stats.discordant(sample.a, sample.b)
        disagreements = gained + lost
        if disagreements == 0:
            raise ValueError(
                "the two variants agreed on every case, so there is no basis for a plan"
            )
        spread = disagreements / sample.n
        mde = stats.mcnemar_mde(sample.n, spread, alpha, power)
        needed = (
            stats.mcnemar_sample_size(spread, detect, alpha, power)
            if detect is not None
            else None
        )
    else:
        disagreements = None
        spread = stats.stdev(sample.diffs)
        if spread == 0:
            raise ValueError("every pair differed by the same amount, so there is nothing to plan")
        mde = stats.paired_mde(sample.n, spread, alpha, power)
        needed = (
            stats.paired_sample_size(spread, detect, alpha, power)
            if detect is not None
            else None
        )

    return Plan(
        metric=sample.metric,
        n=sample.n,
        binary=sample.binary,
        alpha=alpha,
        power=power,
        spread=spread,
        mde=mde,
        detect=detect,
        needed=None if needed is None else math.ceil(needed),
        discordant=disagreements,
    )
