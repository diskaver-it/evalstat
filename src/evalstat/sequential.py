"""An interval you are allowed to read after every commit.

The fixed interval in `compare` is correct if you look once. A metric wired into
CI is not looked at once: it is looked at after every push, and the 5% is per
look. Ten looks at a true null flag something about one time in five.

The usual answer is to declare the number of looks in advance and spend the alpha
across them. That does not survive contact with a repository, where nobody knows
how many commits a branch will take. A confidence sequence holds simultaneously at
every sample size, so there is nothing to declare and nothing to spend.

The price is width, and it is reported rather than hidden.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

from . import stats
from .parse import SCORE, SUCCESS, PairedSample

ESTABLISHED = "established"
NOT_ESTABLISHED = "not established"


@dataclass
class Anytime:
    metric: str
    n: int
    diff: float
    interval: Tuple[float, float]
    fixed_interval: Tuple[float, float]
    scale: float
    alpha: float
    decision: str
    width_ratio: float
    notes: List[str] = field(default_factory=list)

    @property
    def radius(self) -> float:
        return (self.interval[1] - self.interval[0]) / 2.0


def _scale_for(sample: PairedSample) -> Tuple[float, bool]:
    """Half-range of the paired differences, and whether it had to be inferred.

    A difference of two values in [0, 1] lies in [-1, 1], so pass rates and 0-1
    scores need no assumption. An arbitrary named score declares no range, and a
    range taken from the data is an assumption about data not yet seen.
    """
    if sample.metric in (SUCCESS, SCORE) or all(
        0.0 <= value <= 1.0 for value in sample.a + sample.b
    ):
        return 1.0, False
    widest = max((abs(d) for d in sample.diffs), default=0.0)
    return (widest or 1.0), True


def anytime(
    sample: PairedSample,
    alpha: float = 0.05,
    reps: int = 10000,
    seed: int = 0,
) -> Anytime:
    if sample.n == 0:
        raise ValueError("no test case appears in both variants, so nothing is paired")

    diffs = sample.diffs
    diff = stats.mean(diffs)
    scale, inferred = _scale_for(sample)

    # The sequence is stated for values in [0, 1], so differences in [-scale, scale]
    # are mapped in and the interval is mapped back.
    mapped = [(d / scale + 1.0) / 2.0 for d in diffs]
    lo_unit, hi_unit = stats.eb_confidence_sequence(mapped, alpha=alpha)
    interval = ((2.0 * lo_unit - 1.0) * scale, (2.0 * hi_unit - 1.0) * scale)

    fixed = stats.bootstrap_mean_ci(diffs, alpha=alpha, reps=reps, seed=seed + 1)
    fixed_width = fixed[1] - fixed[0]
    radius = (interval[1] - interval[0]) / 2.0
    width_ratio = (2 * radius / fixed_width) if fixed_width > 0 else float("inf")
    decision = ESTABLISHED if interval[0] > 0 or interval[1] < 0 else NOT_ESTABLISHED

    notes = []
    if inferred:
        notes.append(
            "The metric declares no range, so the bound was scaled by the largest "
            "difference seen (%.3f). A later run that exceeds it weakens the guarantee."
            % scale
        )
    if decision == NOT_ESTABLISHED:
        notes.append(
            "Watched continuously, this difference is not established. The fixed "
            "interval is %.1f times narrower, and that width is what the right to "
            "peek costs." % width_ratio
        )
    else:
        notes.append(
            "This holds however many times you looked, so it needs no correction "
            "for the looks already taken."
        )
    return Anytime(
        metric=sample.metric,
        n=sample.n,
        diff=diff,
        interval=interval,
        fixed_interval=fixed,
        scale=scale,
        alpha=alpha,
        decision=decision,
        width_ratio=width_ratio,
        notes=notes,
    )
