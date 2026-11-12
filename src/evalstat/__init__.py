from .compare import BETTER, UNDECIDED, WORSE, Verdict, compare
from .parse import EvalFormatError, PairedSample, list_arms, load, pair_across, pair_within
from .plan import Plan, plan
from .report import render, render_plan

__version__ = "0.1.0"
__all__ = [
    "BETTER",
    "UNDECIDED",
    "WORSE",
    "Verdict",
    "compare",
    "EvalFormatError",
    "PairedSample",
    "list_arms",
    "load",
    "pair_across",
    "pair_within",
    "Plan",
    "plan",
    "render",
    "render_plan",
]
