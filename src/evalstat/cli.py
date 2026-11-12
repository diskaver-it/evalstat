"""Command line entry point.

Exit codes: 0 nothing to flag, 1 the gate tripped, 2 the input could not be used.
"""

from __future__ import annotations

import argparse
import sys
from typing import List, Optional

from .adapters import load_table
from .compare import BETTER, UNDECIDED, WORSE, compare, compare_family
from .judge import calibrate, load_truth
from .parse import EvalFormatError, list_arms, list_metrics, load, pair_across, pair_within
from .plan import plan
from .report import (
    combined_as_json,
    render,
    render_anytime,
    render_family,
    render_judge,
    render_plan,
)
from .sequential import NOT_ESTABLISHED, anytime

OK = 0
GATE_TRIPPED = 1
BAD_INPUT = 2

TABLE_SUFFIXES = (".csv", ".jsonl", ".ndjson")


def _add_input_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("files", nargs="+", metavar="FILE", help="promptfoo output, or a table")
    parser.add_argument("--a", help="baseline variant: its index or label")
    parser.add_argument("--b", help="candidate variant: its index or label")
    parser.add_argument("--by", default="prompt", choices=["prompt", "provider"])
    parser.add_argument("--case-column", default="case", help="for CSV and JSON lines input")
    parser.add_argument("--variant-column", default="variant")
    parser.add_argument("--value-column", default="value")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="evalstat",
        description="Says whether a change in an LLM eval is real or noise, "
        "using the pairing the eval run already has.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    cmp_parser = sub.add_parser("compare", help="compare two variants")
    _add_input_args(cmp_parser)
    cmp_parser.add_argument(
        "--metric",
        default="success",
        help="success, score, a named score, several separated by commas, or all",
    )
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
    cmp_parser.add_argument(
        "--anytime",
        action="store_true",
        help="add an interval that stays valid when the metric is watched after "
        "every commit, and judge the gate by it",
    )

    plan_parser = sub.add_parser("plan", help="how many test cases would you need")
    _add_input_args(plan_parser)
    plan_parser.add_argument("--metric", default="success")
    plan_parser.add_argument(
        "--detect",
        type=float,
        help="effect you want to be able to see, e.g. 0.03 for three points",
    )
    plan_parser.add_argument("--power", type=float, default=0.8)
    plan_parser.add_argument("--alpha", type=float, default=0.05)
    plan_parser.add_argument("--format", default="text", choices=["text", "json"])

    judge_parser = sub.add_parser("judge", help="check the grader against human labels")
    judge_parser.add_argument("file", metavar="FILE")
    judge_parser.add_argument(
        "--truth", required=True, metavar="LABELS", help="human labels as JSON or CSV"
    )
    judge_parser.add_argument("--variant", help="which variant was labelled; the first by default")
    judge_parser.add_argument("--by", default="prompt", choices=["prompt", "provider"])
    judge_parser.add_argument("--alpha", type=float, default=0.05)
    judge_parser.add_argument("--reps", type=int, default=2000)
    judge_parser.add_argument("--seed", type=int, default=0)
    judge_parser.add_argument("--format", default="text", choices=["text", "json"])

    arms_parser = sub.add_parser("arms", help="list the variants and metrics a file holds")
    arms_parser.add_argument("file", metavar="FILE")
    arms_parser.add_argument("--by", default="prompt", choices=["prompt", "provider"])
    return parser


def _read(path: str, args=None) -> dict:
    if path.lower().endswith(TABLE_SUFFIXES):
        if args is None:
            return load_table(path)
        return load_table(
            path,
            case=args.case_column,
            variant=args.variant_column,
            value=args.value_column,
        )
    return load(path)


def _docs_from(args) -> List[dict]:
    if len(args.files) > 2:
        raise EvalFormatError("this command takes one or two files")
    return [_read(path, args) for path in args.files]


def _sample(docs: List[dict], args, metric: str):
    if len(docs) == 2:
        return pair_across(docs[0], docs[1], a=args.a, b=args.b, metric=metric, by=args.by)
    return pair_within(docs[0], a=args.a, b=args.b, metric=metric, by=args.by)


def _metrics_requested(args, docs: List[dict]) -> List[str]:
    if args.metric == "all":
        return list_metrics(docs[0])
    return [name.strip() for name in args.metric.split(",") if name.strip()]


def _cmd_arms(args) -> int:
    doc = _read(args.file)
    arms = list_arms(doc, by=args.by)
    if not arms:
        print("no variants found", file=sys.stderr)
        return BAD_INPUT
    print("%d variant(s) by %s:" % (len(arms), args.by))
    for arm_id, label, count in arms:
        print("  %-4s %-60s %d rows" % (arm_id, label, count))
    print("metrics: %s" % ", ".join(list_metrics(doc)))
    return OK


def _cmd_plan(args) -> int:
    docs = _docs_from(args)
    result = plan(
        _sample(docs, args, args.metric),
        detect=args.detect,
        alpha=args.alpha,
        power=args.power,
    )
    print(render_plan(result, args.format))
    return OK


def _cmd_judge(args) -> int:
    result = calibrate(
        _read(args.file),
        load_truth(args.truth),
        variant=args.variant,
        by=args.by,
        alpha=args.alpha,
        reps=args.reps,
        seed=args.seed,
    )
    print(render_judge(result, args.format))
    return OK


def _gate(args, decision: str) -> int:
    if args.fail_on == "regression" and decision == WORSE:
        return GATE_TRIPPED
    if args.fail_on == "any" and decision != UNDECIDED:
        return GATE_TRIPPED
    return OK


def _cmd_compare_family(args, docs: List[dict], metrics: List[str]) -> int:
    if args.anytime:
        raise EvalFormatError(
            "--anytime judges one metric at a time; drop it or name a single metric"
        )
    samples = [_sample(docs, args, metric) for metric in metrics]
    family = compare_family(samples, alpha=args.alpha, reps=args.reps, seed=args.seed)
    print(render_family(family, args.format))

    if WORSE in family.decisions:
        return _gate(args, WORSE)
    if BETTER in family.decisions:
        return _gate(args, BETTER)
    return _gate(args, UNDECIDED)


def _cmd_compare(args) -> int:
    docs = _docs_from(args)
    metrics = _metrics_requested(args, docs)
    if not metrics:
        raise EvalFormatError("no metric named")
    if len(metrics) > 1:
        return _cmd_compare_family(args, docs, metrics)

    sample = _sample(docs, args, metrics[0])
    verdict = compare(sample, alpha=args.alpha, reps=args.reps, seed=args.seed)

    watched = None
    if args.anytime:
        watched = anytime(sample, alpha=args.alpha, reps=args.reps, seed=args.seed)

    if watched is not None and args.format == "json":
        print(combined_as_json(verdict, watched))
    else:
        print(render(verdict, args.format))
        if watched is not None:
            print()
            print(render_anytime(watched, args.format))

    decision = verdict.decision
    if watched is not None:
        # The gate answers the question the pipeline actually asks, which is asked
        # again on every commit.
        if watched.decision == NOT_ESTABLISHED:
            decision = UNDECIDED
        else:
            decision = WORSE if watched.diff < 0 else BETTER
    return _gate(args, decision)


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    commands = {"arms": _cmd_arms, "plan": _cmd_plan, "judge": _cmd_judge}
    try:
        return commands.get(args.command, _cmd_compare)(args)
    except (EvalFormatError, ValueError) as exc:
        print("evalstat: %s" % exc, file=sys.stderr)
        return BAD_INPUT
    except OSError as exc:
        print("evalstat: %s" % exc, file=sys.stderr)
        return BAD_INPUT


if __name__ == "__main__":
    sys.exit(main())
