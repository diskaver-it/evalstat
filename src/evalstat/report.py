"""Renders a verdict for a terminal, a pull request, or another program."""

from __future__ import annotations

import json
from dataclasses import asdict

from .compare import BETTER, UNDECIDED, WORSE, Verdict
from .plan import Plan
from .sequential import Anytime

HEADLINE = {
    BETTER: "better than %s",
    WORSE: "worse than %s",
    UNDECIDED: "not distinguishable from noise",
}

_TEST_NAMES = {
    "mcnemar-exact": "McNemar, exact",
    "mcnemar-chi2": "McNemar, chi-square",
    "paired-permutation": "paired permutation",
}


def _on_unit_scale(verdict: Verdict) -> bool:
    return all(0.0 <= value <= 1.0 for value in (verdict.mean_a, verdict.mean_b))


def _delta(value: float, unit_scale: bool) -> str:
    return "%+.1f pp" % (value * 100) if unit_scale else "%+.3f" % value


def _level(value: float, unit_scale: bool) -> str:
    return "%.3f" % value if unit_scale else "%.3f" % value


def _p(value: float) -> str:
    return "p < 0.001" if value < 0.001 else "p = %.3f" % value


def headline(verdict: Verdict) -> str:
    if verdict.decision == UNDECIDED:
        return "%s is not distinguishable from %s" % (verdict.label_b, verdict.label_a)
    return "%s is %s %s" % (
        verdict.label_b,
        "better than" if verdict.decision == BETTER else "worse than",
        verdict.label_a,
    )


def as_text(verdict: Verdict) -> str:
    unit = _on_unit_scale(verdict)
    lo, hi = verdict.ci
    width = max(len(verdict.label_a), len(verdict.label_b), 10)
    lines = [
        "%s on %d paired test cases" % (verdict.metric, verdict.n),
        "",
        "  %-*s  %s" % (width, verdict.label_a, _level(verdict.mean_a, unit)),
        "  %-*s  %s" % (width, verdict.label_b, _level(verdict.mean_b, unit)),
        "  %-*s  %s   %d%% CI [%s, %s]"
        % (
            width,
            "difference",
            _delta(verdict.diff, unit),
            round((1 - verdict.alpha) * 100),
            _delta(lo, unit),
            _delta(hi, unit),
        ),
    ]

    test_line = "  %-*s  %s, %s" % (
        width,
        "test",
        _TEST_NAMES.get(verdict.test, verdict.test),
        _p(verdict.p),
    )
    if verdict.gained is not None:
        test_line += "   (%d gained, %d lost, %d tied)" % (
            verdict.gained,
            verdict.lost,
            verdict.tied,
        )
    lines += [test_line, "", "  VERDICT: %s" % headline(verdict)]
    if verdict.notes:
        lines.append("")
        lines += ["  - %s" % note for note in verdict.notes]
    return "\n".join(lines)


def as_markdown(verdict: Verdict) -> str:
    unit = _on_unit_scale(verdict)
    lo, hi = verdict.ci
    rows = [
        "**%s** &mdash; %s" % (headline(verdict), verdict.metric),
        "",
        "| | value |",
        "| --- | --- |",
        "| %s | %s |" % (verdict.label_a, _level(verdict.mean_a, unit)),
        "| %s | %s |" % (verdict.label_b, _level(verdict.mean_b, unit)),
        "| difference | %s, %d%% CI [%s, %s] |"
        % (
            _delta(verdict.diff, unit),
            round((1 - verdict.alpha) * 100),
            _delta(lo, unit),
            _delta(hi, unit),
        ),
        "| test | %s, %s |" % (_TEST_NAMES.get(verdict.test, verdict.test), _p(verdict.p)),
        "| paired test cases | %d |" % verdict.n,
    ]
    if verdict.notes:
        rows += [""] + ["- %s" % note for note in verdict.notes]
    return "\n".join(rows)


def as_json(verdict: Verdict) -> str:
    payload = asdict(verdict)
    payload["ci"] = list(verdict.ci)
    payload["headline"] = headline(verdict)
    return json.dumps(payload, indent=2, ensure_ascii=False)


def anytime_as_text(result: Anytime) -> str:
    unit = result.scale <= 1.0
    width = 20
    lines = [
        "watched continuously, alpha %.2f" % result.alpha,
        "",
        "  %-*s %s" % (width, "difference", _delta(result.diff, unit)),
        "  %-*s [%s, %s]"
        % (
            width,
            "anytime interval",
            _delta(result.interval[0], unit),
            _delta(result.interval[1], unit),
        ),
        "  %-*s [%s, %s]   %.1f times narrower"
        % (
            width,
            "fixed interval",
            _delta(result.fixed_interval[0], unit),
            _delta(result.fixed_interval[1], unit),
            result.width_ratio,
        ),
        "",
        "  VERDICT: %s under repeated looks" % result.decision,
    ]
    if result.notes:
        lines.append("")
        lines += ["  - %s" % note for note in result.notes]
    return "\n".join(lines)


def anytime_as_json(result: Anytime) -> str:
    return json.dumps(_anytime_payload(result), indent=2, ensure_ascii=False)


def _anytime_payload(result: Anytime) -> dict:
    payload = asdict(result)
    payload["interval"] = list(result.interval)
    payload["fixed_interval"] = list(result.fixed_interval)
    return payload


def render_anytime(result: Anytime, fmt: str = "text") -> str:
    if fmt == "json":
        return anytime_as_json(result)
    return anytime_as_text(result)


def combined_as_json(verdict: Verdict, result: Anytime) -> str:
    payload = asdict(verdict)
    payload["ci"] = list(verdict.ci)
    payload["headline"] = headline(verdict)
    payload["anytime"] = _anytime_payload(result)
    return json.dumps(payload, indent=2, ensure_ascii=False)


def plan_as_text(plan: Plan) -> str:
    width = 38
    lines = ["plan for %s, from %d paired test cases" % (plan.metric, plan.n), ""]
    if plan.binary:
        lines.append(
            "  %-*s %d of %d pairs (%.1f%%)"
            % (width, "the variants disagreed on", plan.discordant, plan.n, plan.spread * 100)
        )
        mde = "not reachable at any effect size" if plan.mde != plan.mde else "%+.1f pp" % (
            plan.mde * 100
        )
    else:
        lines.append(
            "  %-*s %.3f" % (width, "spread of the paired differences", plan.spread)
        )
        mde = "%+.3f" % plan.mde
    lines.append("  %-*s %s" % (width, "smallest effect these pairs can see", mde))
    if plan.detect is not None:
        target = "%+.1f pp" % (plan.detect * 100) if plan.binary else "%+.3f" % plan.detect
        lines.append(
            "  %-*s %s paired test cases" % (width, "to see %s you need" % target, "{:,}".format(plan.needed).replace(",", " "))
        )
    lines += [
        "",
        "  at %d%% power, alpha %.2f" % (round(plan.power * 100), plan.alpha),
    ]
    if plan.binary:
        lines.append(
            "  - Power comes from the pairs that disagree, not from the size of the eval "
            "set. Two variants that agree on almost everything need an enormous set."
        )
    return "\n".join(lines)


def plan_as_json(plan: Plan) -> str:
    return json.dumps(asdict(plan), indent=2, ensure_ascii=False)


def render_plan(plan: Plan, fmt: str = "text") -> str:
    if fmt == "json":
        return plan_as_json(plan)
    return plan_as_text(plan)


def render(verdict: Verdict, fmt: str = "text") -> str:
    if fmt == "text":
        return as_text(verdict)
    if fmt == "markdown":
        return as_markdown(verdict)
    if fmt == "json":
        return as_json(verdict)
    raise ValueError("unknown format %r" % fmt)
