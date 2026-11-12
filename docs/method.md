# Method

*[Русская версия](method.ru.md) · [back to the README](../README.md)*

Why these statistics and not others. Every number below comes from a test in the
suite, not from a textbook quotation.

## 1. Pairing is the whole gain, not a refinement

Two runs over the same eval set differ for two reasons: the prompts differ, and
some test cases are simply harder. Comparing the two column means leaves the
second reason sitting in the noise. Differencing within a test case removes it.

This is why the report prints the tied pairs. Thirty-nine of fifty cases behaved
identically in both variants and say nothing at all about which prompt is better,
which is how a decent-looking eval set can still be hopeless at resolving a
six-point change.

The pairing does not have to be reconstructed: a promptfoo run that compares two
prompts stores every (test case, variant) cell in one flat list keyed by `testIdx`
and `promptIdx`. It is a paired design, written to disk and then averaged away.

## 2. The test and the interval are different procedures on purpose

A significance test may assume the null hypothesis. A confidence interval may not,
because the null is the thing it is measuring. So:

- the p-value comes from a null-based procedure — exact McNemar on the discordant
  pairs for pass/fail, a paired sign-flip permutation test for continuous scores;
- the interval comes from bootstrapping the pairs as they were observed.

When the two disagree, which happens near the threshold, the report says so rather
than picking the flattering one.

McNemar is exact for small discordant counts and switches to the
continuity-corrected chi-square above 25, because a discrete count read off a
continuous curve without the correction gives an anti-conservative test.

## 3. Repeats are not extra observations

If `repeat` ran each test case three times, the file holds three rows per cell.
Treating them as independent inflates `n` and shrinks the interval on nothing. They
are averaged into one number per cell, which turns pass/fail into a proportion,
which is why the test then switches from McNemar to the permutation test.

## 4. Test cases are matched by their `vars`, not by row order

Position works inside a single run and silently lies across two runs if the eval
set changed in between. When a file carries no `vars` to match on, the report says
it fell back to position.

## 5. Power comes from the pairs that disagree, not from the size of the eval set

Which is why `plan` asks your existing run how often the two variants disagreed
instead of asking you to guess. Two variants that agree on almost everything can
need thousands of cases to separate.

On the demo run, fifty cases with a 22% disagreement rate resolve nothing below
18.1 pp, and seeing a 3 pp change would take 1 917 cases.

The formula is the usual normal approximation for the paired case, and it is not
taken on trust: a test computes the required `n`, runs the comparison that many
times and confirms that the promised 80% power is the power achieved.

## 6. Wired into CI, the 5% is not 5%

A gate does not look at the metric once. It looks after every commit, and the error
rate is per look. Measured on a true null with twelve looks:

| | flags a difference that is not there |
| --- | --- |
| fixed interval, read once at the end | 6.0% |
| fixed interval, read at all twelve looks | **26.5%** |
| anytime interval, read at all twelve looks | 1.0% |

`--anytime` replaces the fixed interval with a confidence sequence, which holds at
every sample size simultaneously. There is no number of looks to declare in advance
and no alpha to spend across them, which matters because nobody knows how many
commits a branch will take. On the demo it costs a factor of 2.4 in width.

The method is predictable plug-in empirical Bernstein. The betting weight at each
step is computed from the earlier observations only, and that restriction is the
whole reason the guarantee survives: a variance estimate that peeked at the value
it is about to weigh would void it. It is the same discipline as point-in-time
correctness in a backtest, where a feature may not use a figure published after
the forecast date.

A normal mixture was tried first. For differences of two values in [0, 1] the
Hoeffding bound gives a sub-Gaussian parameter of 1, which is rigorous and, on
paired differences that are mostly zero, useless: it returned plus or minus 46
points. Correct and unusable is not a trade worth shipping.

## 7. Several metrics are one family

Checking eight named scores at once gives eight chances to be wrong, so the 5%
belongs to the family, not to each metric. The report prints the raw and the
adjusted p-value side by side and names the metrics that were significant alone and
did not survive.

Holm rather than Bonferroni, because it is uniformly more powerful and costs
nothing extra. Holm rather than Benjamini-Hochberg, because a release gate wants no
false alarms at all, not a controlled share of them. The implementation is checked
against R's `p.adjust(method = "holm")`, and the family-wide error rate is measured
by simulation: five metrics under a global null trip an uncorrected rule about 23%
of the time and the corrected one about 5%.

## 8. A grader with error does not add noise, it shrinks the effect

For a binary judge, an observed difference is the true difference multiplied by
`sensitivity + specificity - 1`. A judge that agrees with a human 90% of the time
can carry a factor of 0.79, which turns a real 6.3 pp gain into an observed 5 pp.

So `judge` does not grade the grader. It reports the factor by which every other
number in this tool is understated when run on that grader's verdicts, along with
Cohen's kappa — raw agreement flatters a rater on a lopsided set, since a rater
that passes everything agrees 90% of the time on a set that is 90% passes and knows
nothing.

The factor is verified by simulation: build a judge with known sensitivity and
specificity, push a known difference through it, and check the difference comes out
shrunk by exactly that factor.

## 9. No dependencies

Standard library only, including the chi-square tail through `erfc`, the exact
binomial through `math.comb` and the inverse normal through Acklam's approximation
with one Halley step. An eval gate has to install and run inside someone else's CI
in seconds, and a dependency tree is the usual reason a check like this never gets
adopted.

## What is deliberately absent

- **No Bayesian output.** A gate needs a decision rule with a stated error rate.
- **No effect-size-free verdicts.** Every verdict carries an interval, because
  "significant" without a magnitude is not actionable.
- **No causal claim.** If the test cases were chosen or retried in a way that
  depends on the outcome, nothing here repairs that, and the report says so.
