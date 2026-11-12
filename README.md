# evalstat

[![CI](https://github.com/diskaver-it/evalstat/actions/workflows/ci.yml/badge.svg)](https://github.com/diskaver-it/evalstat/actions/workflows/ci.yml)

*[Русская версия](README.ru.md)*

**You changed a prompt and the score went up. evalstat tells you whether that
actually happened or whether you got lucky.**

No account, no API key, no network. It reads the file your eval tool already
writes.

```bash
pip install evalstat
evalstat compare results.json
```

```
success on 50 paired test cases

  baseline prompt  0.620
  new prompt       0.680
  difference       +6.0 pp   95% CI [-6.0 pp, +18.0 pp]
  test             McNemar, exact, p = 0.549   (7 gained, 4 lost, 39 tied)

  VERDICT: new prompt is not distinguishable from baseline prompt
```

62% became 68%. Six points, and most people ship that. But look at the last
number on the test line: the new prompt **fixed 7 cases and broke 4**. Thirty-nine
cases did not change at all. Eleven cases moved, seven of them your way — that is
the same evidence as tossing a coin eleven times and getting seven heads.

Try it yourself in thirty seconds, no setup:

```bash
git clone https://github.com/diskaver-it/evalstat && cd evalstat
pip install -e .
python examples/make_demo.py
evalstat compare examples/demo_run.json
```

## Where to look

| | |
| --- | --- |
| **I just want to use it** | you are in the right place, keep reading |
| **What do these words mean?** | [the output in plain words](#the-output-in-plain-words) |
| **Why these statistics and not others?** | [docs/method.md](docs/method.md) |
| **I do not use promptfoo** | [any tool, via a table](#any-tool-via-a-table) |
| **What it cannot do** | [limitations](#what-it-does-not-do-yet) |
| **In Russian** | [README.ru.md](README.ru.md), [docs/method.ru.md](docs/method.ru.md) |

## The three questions it answers

**1. Is this change real?**

```bash
evalstat compare results.json
```

**2. If it is undecided, how many test cases would I need?**

```bash
evalstat plan results.json --detect 0.03
```

```
  the variants disagreed on              11 of 50 pairs (22.0%)
  smallest effect these pairs can see    +18.1 pp
  to see +3.0 pp you need                1 917 paired test cases
```

Fifty cases cannot see a three-point change. They cannot see anything smaller
than eighteen points. That is worth knowing before you spend a week tuning.

**3. Can I trust the LLM that did the grading?**

```bash
evalstat judge results.json --truth labels.json
```

```
  agreement with the humans  0.900
  shrinkage factor           0.788
  - Differences measured through this judge are shrunk by about 0.79, so an
    observed gap of 5.0 pp corresponds to roughly 6.3 pp of real difference.
```

A grader that is wrong sometimes does not just add noise — it pulls every
difference towards zero. This gives you the factor.

## Use it as a gate

```bash
evalstat compare results.json --fail-on regression
```

Exit code 1 if the candidate is significantly worse, 0 otherwise, so a pull
request can block on it. Add `--anytime` if the metric is checked on every commit:
looking repeatedly is itself a way to be fooled, and that flag accounts for it.
Add `--format markdown` to paste the verdict into the pull request.

## The output in plain words

| what you see | what it means |
| --- | --- |
| **paired test cases** | the same questions were asked of both variants, so they can be compared one by one instead of as two averages |
| **pp** | percentage points. From 62% to 68% is +6 pp |
| **95% CI [−6, +18]** | the plausible range for the true difference. If it contains 0, the difference might be nothing |
| **p = 0.549** | how easily chance alone could produce a gap this big. Big number, easy for chance, no conclusion. Below 0.05 is the usual bar |
| **7 gained, 4 lost, 39 tied** | cases the change fixed, broke, and left alone. Only the first two carry information |
| **McNemar** | the test for pass/fail results on the same cases. There is a different one for scores, and evalstat picks it for you |
| **not distinguishable** | not the same as equal. It means this eval set was too small to tell |
| **anytime interval** | a wider range that stays honest when you check the metric again and again |
| **shrinkage factor** | how much an imperfect grader flattens real differences |
| **adjusted** | the p-value after accounting for how many metrics you checked at once |

## Any tool, via a table

Not using promptfoo? Export a three-column table — which case, which variant, what
it scored — as CSV or JSON lines:

```
case,variant,value
q1,baseline,pass
q1,candidate,pass
q2,baseline,fail
q2,candidate,pass
```

```bash
evalstat compare runs.csv
```

Values can be `pass`/`fail`, `1`/`0`, or any number. Column names are
`--case-column`, `--variant-column` and `--value-column` if yours differ. The
baseline is whichever variant appears first in the file, or name it with
`--a` and `--b`.

## Several metrics at once

```bash
evalstat compare results.json --metric all
```

```
  metric           difference         p   adjusted  verdict
  success            +14.0 pp     0.016      0.062  undecided
  helpfulness        +14.0 pp     0.016      0.062  undecided
  tone                +9.5 pp     0.077      0.077  undecided
```

Each metric on its own looks significant. Checking four of them gives four chances
to be wrong, and after the correction nothing survives.

## Why it exists

`promptfoo`, `deepeval` and `ragas` have about 63 000 GitHub stars between them and
not one occurrence of `mcnemar` or `paired bootstrap` in their source. They report
two column means and leave the comparison to the reader.

The information needed to do better is already in the output file. A promptfoo run
that compares two prompts stores every (test case, variant) cell keyed by `testIdx`
and `promptIdx` — a paired design, written to disk, then averaged away.

The reasoning behind each number is in [docs/method.md](docs/method.md).

## What it does not do yet

- **Only promptfoo's own format** is read natively; everything else goes through the
  table above.
- **The parser has not met a live run.** It is exercised against fixtures built to
  promptfoo's published `EvaluateResult` and `OutputFile` interfaces, not against a
  file written by an actual `promptfoo eval`.
- **No causal claim.** If you chose which cases to retry, no statistic here can fix
  that.

## Tested

140 tests, no network and no API key. Published chi-square and normal quantiles are
reproduced to nine decimals; the exact binomial is checked against hand-computed
tails and independently against 40 000 simulated coin flips; Holm's correction is
checked against R's `p.adjust`. The claims are measured rather than asserted — the
sample-size formula is verified by computing `n`, running the comparison that many
times and confirming the promised power, and the shrinkage factor is verified by
simulating a judge with known error and watching a known difference shrink by it.

```bash
pip install -e ".[dev]"
pytest
```

## License

MIT.
