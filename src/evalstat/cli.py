"""Command line entry point.

Exit codes: 0 nothing to flag, 1 the gate tripped, 2 the input could not be used.
"""

from __future__ import annotations

import argparse
import sys
from typing import List, Optional

from .compare import UNDECIDED, WORSE, compare
from .parse import EvalFormatError, list_arms, load, pair_across, pair_within
from .plan import plan
from .report import render, render_plan

OK = 0
GATE_TRIPPED = 1
BAD_INPUT = 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="evalstat",
        description="Says whether a change in an LLM eval is real or noise, "
        "using the pairing the eval run already has.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    cmp_parser = sub.add_parser("compare", help="compare two variants")
    cmp_parser.add_argument("files", nargs="+", metavar="FILE", help="promptfoo --output file(s)")
    cmp_parser.add_argument("--a", help="baseline variant: its index or label")
    cmp_parser.add_argument("--b", help="candidate variant: its index or label")
    cmp_parser.add_argument(
        "--metric",
        default="success",
        help="success (default), score, or the name of a named score",
    )
    cmp_parser.add_argument("--by", default="prompt", choices=["prompt", "provider"])
    cmp_parser.add_argument("--alpha", type=float, default=0.05)
    cmp_parser.add_argument("--reps", type=int, default=10000, help="resamples for the interval")
    cmp_parser.add_argument("--seed", type=int, default=0)
    cmp_parser.add_argument("--format", default="text", choices=["text", "markdown", "json"])
    cmp_parser.add_argument(
        "--fail-on",
        default="none",
        choices=["none", "regression", "any"],
        help="exit 1 on a significant regression, or on any significant change",
    )

    plan_parser = sub.add_parser("plan", help="how many test cases would you need")
    plan_parser.add_argument("files", nargs="+", metavar="FILE")
    plan_parser.add_argument("--a")
    plan_parser.add_argument("--b")
    plan_parser.add_argument("--metric", default="success")
    plan_parser.add_argument("--by", default="prompt", choices=["prompt", "provider"])
    plan_parser.add_argument(
        "--detect",
        type=float,
        help="effect you want to be able to see, e.g. 0.03 for three points",
    )
    plan_parser.add_argument("--power", type=float, default=0.8)
    plan_parser.add_argument("--alpha", type=float, default=0.05)
    plan_parser.add_argument("--format", default="text", choices=["text", "json"])

    arms_parser = sub.add_parser("arms", help="list the variants a file holds")
    arms_parser.add_argument("file", metavar="FILE")
    arms_parser.add_argument("--by", default="prompt", choices=["prompt", "provider"])
    return parser


def _cmd_arms(args) -> int:
    doc = load(args.file)
    arms = list_arms(doc, by=args.by)
    if not arms:
        print("no variants found", file=sys.stderr)
        return BAD_INPUT
    print("%d variant(s) by %s:" % (len(arms), args.by))
    for arm_id, label, count in arms:
        print("  %-4s %-60s %d rows" % (arm_id, label, count))
    return OK


def _sample_from(args):
    if len(args.files) > 2:
        raise EvalFormatError("this command takes one or two files")
    if len(args.files) == 2:
        return pair_across(
            load(args.files[0]),
            load(args.files[1]),
            a=args.a,
            b=args.b,
            metric=args.metric,
            by=args.by,
        )
    return pair_within(load(args.files[0]), a=args.a, b=args.b, metric=args.metric, by=args.by)


def _cmd_plan(args) -> int:
    result = plan(
        _sample_from(args), detect=args.detect, alpha=args.alpha, power=args.power
    )
    print(render_plan(result, args.format))
    return OK


def _cmd_compare(args) -> int:
    sample = _sample_from(args)
    verdict = compare(sample, alpha=args.alpha, reps=args.reps, seed=args.seed)
    print(render(verdict, args.format))

    if args.fail_on == "regression" and verdict.decision == WORSE:
        return GATE_TRIPPED
    if args.fail_on == "any" and verdict.decision != UNDECIDED:
        return GATE_TRIPPED
    return OK


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "arms":
            return _cmd_arms(args)
        if args.command == "plan":
            return _cmd_plan(args)
        return _cmd_compare(args)
    except (EvalFormatError, ValueError) as exc:
        print("evalstat: %s" % exc, file=sys.stderr)
        return BAD_INPUT
    except OSError as exc:
        print("evalstat: %s" % exc, file=sys.stderr)
        return BAD_INPUT


if __name__ == "__main__":
    sys.exit(main())
