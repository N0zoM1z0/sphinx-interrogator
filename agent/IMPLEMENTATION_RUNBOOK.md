# Implementation runbook

## 1. Initial checkout

From the repository root:

    git status --short
    find . -maxdepth 3 -type f | sort
    just bootstrap
    cargo metadata --no-deps
    python3 -m compileall python scripts tests/python
    just schema-check

Record versions and failures in `agent/plans/0001-full-system.md`. Do not modify or discard unrelated user changes.

## 2. Python environment

Preferred workflow:

    uv sync --extra dev
    uv run python -m pytest tests/python

After dependencies settle, generate and commit `uv.lock`. Dependency changes require rationale in the ExecPlan and a successful clean install.

## 3. Rust workflow

    cargo fmt --all
    cargo clippy --workspace --all-targets --all-features -- -D warnings
    cargo test --workspace --all-targets

Keep semantic functions in the library crate so unit/property tests do not drive behavior through the CLI unnecessarily. Cross-language boundary tests must still launch the server process.

## 4. Vertical-slice discipline

Implement each milestone as a visible path:

1. define/adjust schema;
2. add target type/behavior;
3. add client type/behavior;
4. add unit tests on both sides;
5. add process integration test;
6. update docs and status;
7. run repository checks.

Do not build a large untested target or solver layer before a public round trip works.

## 5. Protocol development

- Every request has `protocol_version`, `request_id`, and `kind`.
- Every response echoes `request_id` and uses a tagged success/error body.
- Unknown fields follow the schema's compatibility policy.
- Reject oversized lines before deserializing unbounded data.
- Flush one JSON response per input line.
- Never log private target fields.

Create golden fixtures in `tests/fixtures/protocol/` and validate them from Rust and Python.

## 6. Semantic development

For each instruction:

- add parser/formatter support;
- add validator rules;
- implement architectural step;
- implement microcode expansion/static cost;
- add unit examples;
- add generated differential properties.

Implement `PROBE`/`ANCHOR` architectural silence before the fault. Prove/test that changing the secret does not change architectural results.

## 7. Symbolic-model development

Begin with a reduced pure-Python concrete reference function for bank mapping, guard, delta, and state update. Then implement Z3 expressions and compare all finite inputs. Only after exhaustive agreement should extractors rely on the symbolic model.

Use named constraints and explicit widths. Every solver call receives a timeout and returns a structured `sat/unsat/unknown` result.

## 8. Relation development

For each template:

1. implement typed constructor/precondition;
2. add architectural relation property test;
3. add fault-free normalized relation property test;
4. implement exact extractor;
5. exhaustively check true-secret satisfaction on a reduced domain;
6. implement bounded/noisy extractor if required;
7. add reducer rules;
8. version the certificate.

Do not enable a template in campaigns before this sequence passes.

## 9. Campaign development

Use deterministic fixtures first:

- fake endpoint with scripted responses;
- in-memory or temporary SQLite KB;
- tiny two-bit secret solver;
- deterministic selector.

Then launch the real target process. Persist raw responses before analysis so a crash cannot lose or reinterpret observations.

## 10. Synthesis development

Test in this order:

1. enumerate a small grammar and calculate exact partitions;
2. fill finite holes with Z3;
3. generate diverse secret models;
4. implement pair separation;
5. add committee partition score;
6. add counterexample refinement;
7. add cost/margin objectives;
8. integrate with KB/selector.

Keep a brute-force tiny-domain oracle to verify synthesis output and optimality claims.

## 11. Noise development

- bounded mode first; exhaustively enumerate nuisance values;
- stochastic sampler behind an interface;
- fake distributions for exact tests;
- paired schedules and correlation groups;
- robust/sequential decision with simulation calibration;
- soft constraints and replay/quarantine.

No stochastic test should depend on an unseeded host random generator.

## 12. Active-learning development

First create a one-state hard-reset learner and exact-history adapter. Add the AALpy backend only when macro alphabets and output discretization are stable. Keep membership-query cache and model versioning explicit.

Use a small known Mealy target in unit tests before SphinxVM.

## 13. Benchmark runs

Never tune on final evaluation seeds. Use:

    benchmarks/seeds/calibration.txt
    benchmarks/seeds/evaluation.txt

Create them before comparative evaluation. A run manifest must include revision, profile hash, variant, seed, command, tool versions, and completion status.

## 14. Debugging hierarchy

When recovery fails:

1. check protocol/raw transcript;
2. verify architectural relation;
3. compare concrete and symbolic fault predictions in a development fixture;
4. inspect interval/statistical decision;
5. check constraint provenance and true-secret satisfaction in white-box tests;
6. inspect candidate-set/model sampling;
7. inspect synthesis score;
8. inspect state-model assumptions;
9. only then adjust calibration/profile strength.

Do not “fix” recovery by exposing more target data or weakening uniqueness.

## 15. Completion routine

Before closing a milestone:

    just fmt
    just lint
    just test
    just schema-check

For semantic/relation milestones:

    just verify-formal
    just demo-tutorial

For release milestones, run the boundary audit and benchmark matrix. Update `agent/STATUS.md`, the active ExecPlan, and relevant docs with exact evidence paths.
