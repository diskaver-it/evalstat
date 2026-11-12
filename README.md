# evalstat

[![CI](https://github.com/diskaver-it/evalstat/actions/workflows/ci.yml/badge.svg)](https://github.com/diskaver-it/evalstat/actions/workflows/ci.yml)

*[Русская версия](README.ru.md)*

Your eval dashboard says the new prompt scores 68% against the old prompt's 62%.
Six points. Ship it.

```
$ evalstat compare examples/demo_run.json

success on 50 paired test cases

  baseline prompt  0.620
  new prompt       0.680
  difference       +6.0 pp   95% CI [-8.0 pp, +18.0 pp]
  test             McNemar, exact, p = 0.549   (7 gained, 4 lost, 39 tied)

  VERDICT: new prompt is not distinguishable from baseline prompt

  - 39 of 50 pairs agreed in both variants and carry no information about the difference.
  - Undecided is not the same as equal: an effect smaller than 13.0 pp would not have been visible at this sample size.
```

The new prompt fixed seven cases and broke four. That is a coin flip, and no eval
set of fifty could have told you otherwise — the smallest difference this run was
able to see at all was thirteen points.

So how big would the eval set have to be?

```
$ evalstat plan examples/demo_run.json --detect 0.03

plan for success, from 50 paired test cases

  the variants disagreed on              11 of 50 pairs (22.0%)
  smallest effect these pairs can see    +18.1 pp
  to see +3.0 pp you need                1 917 paired test cases

  at 80% power, alpha 0.05
```

The assumption behind that number is not invented: the run you already have says
how often the two variants actually disagree, and for a paired test that rate is
what drives power.

Reproduce the block above, no API key and no network:

```bash
python examples/make_demo.py
evalstat compare examples/demo_run.json
```

## Why this exists

`promptfoo`, `deepeval` and `ragas` have about 63 000 GitHub stars between them and
not one occurrence of `mcnemar` or `paired bootstrap` in their source. They report
two column means and leave the comparison to the reader.

The information needed to do better is already in the output file. A promptfoo run
that compares two prompts stores every (test case, variant) cell keyed by `testIdx`
and `promptIdx` — a paired design, written to disk, then averaged away.

## Install and use

```bash
pip install evalstat
```

```bash
# two prompts or two providers inside one run
promptfoo eval --output results.json
evalstat compare results.json

# a before and after run
evalstat compare before.json after.json

# which variants does this file hold?
evalstat arms results.json

# gate a pull request: exit 1 on a significant regression
evalstat compare results.json --fail-on regression

# how many cases would it take to see a three-point change?
evalstat plan results.json --detect 0.03
```

Options worth knowing: `--metric success|score|<named score>`, `--by prompt|provider`,
`--a` / `--b` to pick variants by index or label, `--alpha`, `--format text|markdown|json`,
`--fail-on none|regression|any`. The `markdown` format is meant to be pasted into a
pull request; `json` is meant for whatever reads it next.

## The five decisions behind the numbers

**Pairing is the whole gain, not a refinement.** Two runs over the same eval set
differ partly because the prompts differ and partly because some test cases are
simply harder. Comparing column means leaves the second part sitting in the noise;
differencing within a test case removes it. This is also why the tied pairs get
reported: 39 of 50 cases behaved identically in both variants and say nothing at all
about which prompt is better, which is how a decent-looking eval set can still be
hopeless at resolving a six-point change.

**The test and the interval are different procedures on purpose.** A significance
test may assume the null hypothesis; a confidence interval may not, since the null
is the thing being measured. So the p-value comes from a null-based procedure —
exact McNemar on the discordant pairs, or a paired sign-flip permutation for
continuous scores — while the interval comes from bootstrapping the pairs as
observed. When the two disagree, which happens near the threshold, the report says
so instead of picking the flattering one.

**Repeats are not extra observations.** If `repeat` ran each test case three times,
the file holds three rows per cell. Treating them as independent inflates `n` and
shrinks the interval on nothing. They are averaged into one number per cell, which
also turns pass/fail into a proportion, which is why the test then switches from
McNemar to the permutation test.

**Test cases are matched by their `vars`, not by row order.** Position works inside a
single run and silently lies across two runs if the eval set changed in between.
When a file carries no `vars` to match on, the report says that it fell back to
position.

**Power comes from the pairs that disagree, not from the size of the eval set.**
Which is why `plan` asks your existing run how often the two variants disagreed
instead of asking you to guess. Two variants that agree on almost everything can
need thousands of cases to separate, and a set that looks generous at fifty turns
out to resolve nothing below eighteen points.

No dependencies — standard library only, including the chi-square tail, the exact
binomial and the inverse normal. An eval gate has to install and run inside someone's CI in seconds,
and a dependency tree is the usual reason a check like this never gets adopted.

## What it does not do yet

- **No correction for repeated looks.** Watching one metric across fifty commits is
  fifty looks at the same question, and the 5% is per look. Always-valid bounds are
  the planned fix.
- **No correction across metrics.** Checking eight named scores at once inflates the
  false-positive rate; for now, pick the metric before you run it.
- **No judge calibration.** If an LLM grades the outputs, its agreement with a human
  is its own measurement problem, and it is not addressed here.
- **Only promptfoo's output format** is read today.

## Tested

81 tests, no network and no API key: known chi-square quantiles and normal quantiles
reproduced to nine decimals, the exact binomial checked against hand-computed tails
and independently against 40 000 simulated coin flips, false-positive rates of both
tests measured by simulation under a true null, and bootstrap coverage measured over
200 synthetic experiments. The sample-size formula is not taken on trust either: a
test computes the required `n`, runs the comparison that many times, and checks that
the power it promised is the power it got.

Honest limit on that: the parser is exercised against fixtures built to promptfoo's
published `EvaluateResult` / `OutputFile` interfaces, not yet against a file written
by a live `promptfoo eval` run.

```bash
pip install -e ".[dev]"
pytest
```

## License

MIT.
