# Evaluation plan

## 1. Evaluation goals

The evaluation should answer four distinct questions.

1. **Correctness:** Are relation certificates, symbolic extractors, and recovery claims sound on generated challenges?
2. **Effectiveness:** Does the full system recover the target within defined budgets?
3. **Contribution:** Which components—knowledge base, synthesis, state learning, statistics—produce the improvement?
4. **Calibration:** Is the fault challenging enough that baselines struggle, but not so weak that the full method cannot progress?

All numerical thresholds below are design acceptance targets. They become empirical claims only after benchmark artifacts are generated.

## 2. Benchmark profiles

### 2.1 Tutorial

- 100 generated 16-bit secrets.
- Exact cycles, hard reset, no stochastic jitter.
- Identity lane map.
- Acceptance target: 100% exact unique recovery.
- Median logical query-pair target: at most 48.
- Maximum logical query-pair target: 80.
- No false hard constraints across exhaustive reduced-domain extractor tests.

M5 measured result (2026-07-16): the published 100-seed reference matrix achieved
100/100 exact unique, judge-accepted recoveries with median/max 16 logical families.
The paired 100-seed off-fault control produced 100/100 inconclusive results, no exact
declarations, and no judge submissions. See `docs/TUTORIAL_RECOVERY.md` and
`VALIDATION.md`; generated per-campaign artifacts remain under ignored `runs/` paths.

M6 selector calibration (2026-07-16): across 20 fixed PRNG seeds, each defining an
eight-model surviving nibble committee without a designated true secret, bounded CEGIS
selection achieved mean worst predicted bucket 3.00 versus 7.15 for one seeded uniform
random grammar assignment and was strictly better on 19/20 subsets. This unit-scale
committee result tests synthesis contribution only; it is not substituted for the
standard campaign targets below.

### 2.2 Standard

- At least 100 generated 32-bit secrets, with a fixed published seed list.
- Bucket width 4, bounded seeded jitter in `[-1,1]`.
- Hard reset available.
- Acceptance target: at least 95% exact unique recovery.
- Median logical query families: at most 180.
- 95th percentile logical query families: at most 300.
- Median physical executions: at most 3,000.
- Per-campaign wall-clock target on the reference machine: documented rather than hard-coded until implementation is profiled.

### 2.3 Research

- At least 30 generated challenges.
- 32-bit secret plus hidden lane permutation and persistent state.
- Bucket width 8, bounded/heavy-tail mixture noise.
- Hard-reset budget or penalty.
- Initial target: at least 80% exact recovery within 1,000 logical families and 20,000 physical executions.
- State-model target: held-out macro-sequence prediction accuracy at least 95% after discretization.

These research targets may need calibration; any change must be justified and versioned before final evaluation.

### 2.4 Fault-free control

- Same public interface and challenge distribution as standard.
- Fault disabled.
- Exact unique recovery rate should remain no better than the rate implied by accidental public information and final-guess policy.
- The solver should not eliminate the true secret.
- Certified relation false-positive rate must match the declared noise model.

## 3. Baselines

### B0: Random final guess

No queries. Establishes chance success.

### B1: Random valid probes

Generate well-typed probe pairs uniformly from a fixed grammar, use the same exact extractor and budget. This isolates adaptive selection.

### B2: Stateless metamorphic testing

Generate local follow-ups from fresh seeds; do not retain/query a knowledge base, do not synthesize against candidate models.

### B3: Knowledge base without synthesis

Use interrogation retention, diversity, and transformations, but choose holes randomly.

### B4: Synthesis without knowledge-base selection

Synthesize each next query from current solver models, but do not select/compose prior nodes or use TTL/diversity history.

### B5: Full system without active state learning

Hard reset whenever possible or carry only explicit bounded history. Measures the learner's value/cost in research mode.

### B6: Full system without robust sequential sampling

Use a fixed sample count and ordinary paired mean. Run only in stochastic profiles and report false constraints/inconclusive cost.

### B7: White-box greedy oracle

Development-only upper bound: use true secret/internal state to choose the best query from the same bounded grammar. It must never be part of black-box recovery. It estimates headroom between the heuristic and grammar optimum.

## 4. Ablations

Independently disable or replace:

- relation family (`anchor`, `token`, `phase`, `repeat`, `swap`, `context`);
- TTL and density penalties;
- semantic novelty implication checks;
- committee refresh;
- CEGIS counterexample refinement;
- noise-margin objective;
- MaxSMT quarantine/repair;
- witness replay;
- witness reduction;
- hidden-state learner;
- exact history constraints;
- lane-wise decomposition.

A factorial study is likely too expensive. Pre-register a primary set of one-component ablations and use exploratory combinations separately.

## 5. Metrics

### Recovery

- exact recovery rate;
- exact uniqueness rate;
- top-ranked candidate accuracy for soft-only outcomes;
- remaining candidate count/cardinality bounds;
- per-cell accuracy;
- false-secret declaration count.

### Cost

- logical relation families;
- physical VM executions;
- hard and soft resets;
- total VM gas/cycles;
- wall time;
- solver time and calls;
- state-learning membership/conformance queries;
- storage size.

### Information/search

- estimated candidate reduction per logical query;
- worst predicted versus realized partition;
- committee disagreement;
- query novelty and relation coverage;
- number of CEGIS refinements;
- duplicate query rate;
- frontier size and TTL expirations.

### Correctness/reliability

- true-secret satisfaction of every hard constraint;
- extractor differential mismatches;
- relation certificate failures;
- solver `unknown` and timeout rate;
- unsat-core repairs;
- quarantined/retracted evidence;
- replay disagreement;
- statistical false-positive and inconclusive rates.

### State learning

- learned states/transitions;
- counterexamples/equivalence rounds;
- held-out prediction accuracy;
- homing/access sequence cost;
- state-dependent constraints later retracted.

### Reduction

- original/reduced AST size, gas, history, samples;
- reduction time and predicate evaluations;
- constraint equivalence/implication result;
- reproduction rate.

## 6. Calibration experiments

### 6.1 One-shot leakage audit

Enumerate or synthesize all grammar candidates up to a small bound in tutorial/reduced standard domains. Estimate how many secret candidates each single query outcome can eliminate. Reject a profile where one cheap query nearly determines the secret.

Suggested target for standard mode: no single bounded logical relation should carry more than 4 bits of exact partition information over a uniform reduced-domain audit, and the median useful query should contribute roughly 0.25–1.5 bits. These are tuning ranges, not security guarantees.

### 6.2 Learnability audit

Use the white-box greedy upper bound to ensure the grammar contains a recovery path. If it cannot recover reliably, increasing search sophistication will not fix the benchmark.

### 6.3 Mutation ladder

Create versions with fault amplitude/guard frequency scaled from zero to strong. Plot recovery cost and baseline gap. Choose a standard profile in the region where:

- full system succeeds reliably;
- random/stateless baselines are materially worse;
- one-shot audit rejects trivial leakage;
- physical-execution cost remains practical.

## 7. Correctness validation

### 7.1 Exhaustive reduced machine

For two lanes, two-bit cells, small programs, and all microstates:

- exhaustively compare Rust concrete and Python symbolic semantics;
- verify every accepted relation certificate;
- assert the true secret satisfies every extracted hard formula;
- check fault-free secret independence.

### 7.2 Property-based testing

Generate valid programs, secrets, profiles, noise choices, and relations. Important properties:

- architectural output independent of secret;
- parser/serializer round trip;
- hard reset determinism;
- normalizer agreement;
- symbolic/concrete bank and state transition equality;
- extractor soundness;
- reducer predicate preservation.

### 7.3 Differential profile tests

Run the same challenge with fault `off`, `reference`, and mutations. Architectural outputs must be identical; only observation distributions/state effects may differ.

## 8. Experimental protocol

- Publish fixed benchmark seed lists before comparing variants.
- Use the same challenge instances and budgets for paired baseline comparisons.
- Randomize variant execution order to reduce host drift.
- Record hardware/software environment and repository revision.
- Separate calibration seeds from evaluation seeds.
- Report failures and timeouts, not only successful campaigns.
- Use bootstrap confidence intervals over challenge-level metrics where appropriate.
- Correct for multiple comparisons in confirmatory ablations or label them exploratory.

## 9. Success criteria for version 1.0

Version 1.0 should not be tagged until:

1. tutorial and standard acceptance targets are met on the published reference suite;
2. fault-free negative controls do not produce false exact recovery;
3. exhaustive reduced-domain soundness checks pass;
4. System B black-box boundary audit passes;
5. full-system improvement over B1–B4 is demonstrated on at least query or execution cost with uncertainty reporting;
6. every reported campaign can be replayed from artifacts;
7. documentation distinguishes measured results from design targets;
8. at least one minimized relational witness is produced for every core relation family.

Research-profile success may remain an experimental result rather than a release blocker if clearly labeled.

## 10. Reporting layout

Generate:

- `summary.md`: claims, caveats, environment, aggregate tables;
- `campaigns.csv`: one row per challenge/variant;
- `queries.csv`: logical-query metrics;
- `relations.csv`: oracle and constraint outcomes;
- `state_models.csv`: learner metrics;
- `witnesses/`: minimized examples and certificates;
- machine-readable JSON with schema version;
- plots produced by a checked-in script from raw CSV/JSON.

Never hand-edit derived benchmark tables without regenerating them.
