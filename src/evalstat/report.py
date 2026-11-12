"""Renders a verdict for a terminal, a pull request, or another program."""

from __future__ import annotations

import json
from dataclasses import asdict

from .compare import BETTER, UNDECIDED, WORSE, Verdict

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


def render(verdict: Verdict, fmt: str = "text") -> str:
    if fmt == "text":
        return as_text(verdict)
    if fmt == "markdown":
        return as_markdown(verdict)
    if fmt == "json":
        return as_json(verdict)
    raise ValueError("unknown format %r" % fmt)
