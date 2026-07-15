# Roadmap

## Phase 0 — Repository bootstrap

Outcome: reproducible Rust/Python workspace, schemas, CI, task runner, and boundary skeleton.

Exit evidence:

- `just fmt`, `just lint`, `just test`, and `just schema-check` pass;
- target/client exchange `hello` and structured error messages;
- no private data appears in protocol fixtures.

## Phase 1 — Architectural semantics and DSL

Outcome: typed probe DSL, assembler/parser, validator, architectural interpreter, static-cost analysis.

Exit evidence:

- parser/formatter round trips;
- gas/termination tests;
- secret-independence property tests;
- cross-language schema compatibility.

## Phase 2 — Microcode and fault-free timing

Outcome: micro-op expansion, vault scheduler, fixed envelope, reset semantics, exact public static metrics.

Exit evidence:

- differential tests between architectural and concrete final state;
- fault-free normalized secret independence on exhaustive reduced domain;
- TLA+ reset/session invariants.

## Phase 3 — Injected fault and profiles

Outcome: reference guarded-replay fault, mutation ladder, quantization/noise profiles, private challenge mechanism.

Exit evidence:

- architectural equivalence across fault variants;
- deterministic replay tests;
- transcript secret-leak scan;
- one-shot and learnability calibration tools.

## Phase 4 — Relation engine

Outcome: core relation templates, certificates, normalizers, exact/bounded extractors.

Exit evidence:

- exhaustive reduced-domain relation soundness;
- true secret satisfies all generated hard constraints;
- invalid/inconclusive handling tests.

## Phase 5 — Harness and knowledge base

Outcome: process client, schedules, append-only events, SQLite view, diversity/TTL frontier.

Exit evidence:

- crash/restart/timeout tests;
- deterministic campaign replay;
- provenance from every constraint to raw observations.

## Phase 6 — Tutorial recovery

Outcome: exact SMT model and hand/heuristic query policy recover all tutorial challenges.

Exit evidence:

- 100/100 unique recoveries under target budget;
- alternative-model unsat proof per result;
- fault-free control does not recover.

## Phase 7 — CEGIS query synthesis

Outcome: grammar, symbolic signatures, diverse model committees, pair/committee refinement, cost objectives.

Exit evidence:

- tiny-domain known-optimum tests;
- at least one test requiring a counterexample refinement;
- synthesized policy beats random selection on tutorial/standard calibration.

## Phase 8 — Noise and robust inference

Outcome: bounded interval extraction, randomized paired sampling, sequential/robust stochastic mode, MaxSMT quarantine.

Exit evidence:

- calibrated false-hard-constraint rate of zero in bounded mode tests;
- stochastic simulation metrics;
- standard recovery target met.

## Phase 9 — Stateful research mode

Outcome: soft-reset state, exact history model, AALpy wrapper, conformance portfolio, state-conditioned query composition.

Exit evidence:

- learned model predicts held-out sequences at target accuracy;
- counterexample invalidation retracts dependent constraints;
- full system outperforms no-learner baseline on selected metrics.

## Phase 10 — Reducer, evaluation, and release

Outcome: relational witness reducer, full baselines/ablations, report generator, reproducible artifact bundle.

Exit evidence:

- reduced witnesses for core relations;
- acceptance criteria in `docs/EVALUATION.md` evaluated;
- boundary and ethics review;
- versioned release notes and archived benchmark manifest.

## Stretch directions

- joint synthesis of fault-model holes and secret recovery;
- probabilistic/stochastic automata learning;
- SyGuS benchmark export and external solver comparison;
- decision-tree decoder synthesis;
- approximate model-counting backend;
- proof-assistant formalization of relation soundness;
- multi-secret challenge family and transfer learning of query policies.
