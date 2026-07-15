# Noise and statistical inference

## 1. Principle

The statistical layer separates three fundamentally different settings:

1. exact deterministic observations;
2. deterministic observations with declared bounded nuisance terms and quantization;
3. stochastic observations whose relation is inferred from repeated samples.

The system must not use a stochastic confidence threshold to manufacture an exact hard constraint unless a separate bounded model justifies it.

## 2. Observation equation

For physical execution `j` of logical query `q`:

\[
Y_j=Q_h(C_0(q)+\Delta(k,z,q)+\eta_j),
\]

where:

- \(C_0\) is public static/fault-free cost;
- \(\Delta\) is the secret/state-dependent fault term;
- \(\eta_j\) is noise;
- \(Q_h(x)=\lfloor x/h\rfloor\).

Normalization removes `C_0` where the returned metadata and relation certificate permit it. Quantization is not invertible, so normalized values are intervals, not exact numbers.

## 3. Deterministic bounded inference

If \(\eta\in[-n,n]\) and bucket `b` is observed:

\[
hb-n \le C_0+\Delta \le h(b+1)-1+n.
\]

For paired queries A/B, retain separate nuisance variables unless the public profile states a shared component. The solver can determine which secret values have at least one feasible nuisance assignment.

This mode is exact relative to the stated bound and can emit hard constraints.

## 4. Paired experimental design

Run related queries close together to reduce drift. Recommended schedules:

- `ABBA` for four repetitions;
- randomized balanced blocks for larger samples;
- periodic hard-reset calibration queries;
- record physical order, seed, start state preparation, and timestamps.

The analysis operates on paired or block differences, not two unrelated sample means. Randomization prevents a monotone drift from consistently favoring one side.

## 5. Robust effect estimation

### Median of means

Partition paired differences into `g` groups, average each group, then take the median group mean. This gives a robust estimator under heavier-tailed noise than an ordinary mean.

Configuration must declare:

- total sample cap;
- number/group sizing policy;
- minimum samples;
- outlier model or rationale;
- confidence-bound method.

For tiny sample counts, use exact interval/rank methods or report inconclusive rather than invoking asymptotics without support.

### Trimmed alternatives

A trimmed mean or median can be used in exploratory reports, but the inference path should have one primary, tested estimator per profile to avoid researcher degrees of freedom.

## 6. Sequential testing

For a simple binary decision between hypotheses \(H_0\) and \(H_1\), accumulate log-likelihood ratio

\[
L_n=\sum_{j=1}^{n}\log\frac{p(X_j\mid H_1)}{p(X_j\mid H_0)}.
\]

With type-I target \(\alpha\) and type-II target \(\beta\), classical SPRT boundaries are approximately

\[
A=\log\frac{1-\beta}{\alpha},\qquad
B=\log\frac{\beta}{1-\alpha}.
\]

Stop for \(H_1\) when \(L_n\ge A\), for \(H_0\) when \(L_n\le B\), or inconclusive at the sample cap.

The reference implementation may begin with a simpler confidence-sequence or bounded-sign test if the likelihood model is not trustworthy. It must still use a predeclared stopping rule and report its assumptions.

## 7. Multi-outcome relation decisions

`anchor-switch` can predict `less`, `equal`, or `greater`. Options:

- fit a calibrated discrete likelihood over paired bucket differences;
- run two one-sided sequential tests with family-wise control;
- retain a posterior/likelihood vector over all outcomes and emit a soft disjunction.

Avoid collapsing every non-significant result into `equal`. “No evidence of difference” is `inconclusive`, not equality.

## 8. Soft constraints

For stochastic evidence, let the oracle produce likelihood or confidence for predicates \(C_1,\ldots,C_m\). Encode them as weighted soft constraints or maintain an external log-likelihood score.

Weights should be:

- monotone in evidence;
- capped;
- calibrated on synthetic known-secret runs;
- grouped so many correlated repetitions of one logical experiment do not overwhelm independent evidence.

Z3's optimization support can maximize satisfied weighted assertions [R13]. Keep an exact hard domain and use the soft optimum only to rank candidates. A `unique` exact result still requires an alternative-model unsatisfiability check under hard constraints, or an explicitly different probabilistic status.

## 9. Correlation

Repeated samples may share:

- deterministic query-hash jitter;
- process warm-up;
- persistent microstate;
- shared challenge/session seeds;
- overlapping relation programs.

Treating correlated samples as independent inflates confidence. Store a `correlation_group` for every physical observation. Weight or bootstrap at the group/block level. Hard-reset repetitions can still share deterministic jitter if the profile specifies it.

## 10. Calibration

Before recovery, run public secret-independent controls:

- identical-query hard-reset replay;
- register-renaming relation;
- programs with no `PROBE`;
- deliberately inactive phase context;
- known static-cost changes.

Estimate:

- bucket stability;
- jitter support or tails;
- order drift;
- outlier rate;
- false relation-violation rate;
- sample count needed for injected effect sizes in white-box development.

Calibration may tune the number of repetitions, not relation thresholds after observing a secret-dependent result.

## 11. Reproducibility

Stochastic mode uses counter-based seed derivation:

```text
physical_seed = H(root_seed, campaign_id, logical_batch_id, arm, repetition)
```

The raw transcript records derived public seed identifiers without exposing private VM randomness if that would become a side channel. A replay command reproduces deterministic profiles exactly and stochastic schedules statistically with recorded seeds where allowed.

## 12. Constraint quarantine

Quarantine evidence when:

- a replay changes the relation decision beyond the declared model;
- an unsat core repeatedly contains the same stochastic batch;
- a learned-state counterexample invalidates start-state preparation;
- calibration detects drift;
- confidence computation encounters numerical or model failure.

Quarantined evidence remains in the transcript and report. It is disabled from the active solver with a named assumption.

## 13. Evaluation metrics

- false hard-constraint rate on known secrets;
- coverage of true secret by bounded intervals;
- relation-decision confusion matrix;
- average/quantile physical samples per decision;
- inconclusive rate;
- soft-constraint calibration and ranking quality;
- unsat-core and quarantine frequency;
- recovery rate versus jitter, quantization, and outlier level.

All metrics are aggregated over independent challenge seeds with uncertainty intervals.
