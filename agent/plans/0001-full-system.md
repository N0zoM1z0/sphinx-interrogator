```md
# Implement SphinxVM and the relational Interrogator end to end

This ExecPlan is maintained under `agent/PLANS.md`. It is a living document. Keep `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` current while work proceeds.

## Purpose / Big Picture

After this plan is complete, a researcher can generate a synthetic hidden-secret challenge, launch a Rust microcoded VM as an isolated black-box process, and use a Python agent to recover the secret through certified relational experiments. The agent will not read the target's private state. It will compare architecturally equivalent programs, turn weak timing-relation outcomes into SMT constraints, synthesize the next high-information experiment, and produce an auditable report.

The shortest proof is `just demo-tutorial`: it must generate/serve a seeded 16-bit challenge, recover a unique secret, obtain one final judge acceptance, and write a replayable run directory. The larger proof is the standard benchmark and fault-free negative control specified in `docs/EVALUATION.md`.

The normative requirements are in `agent/CODEX_TASK_SPEC.md`. Read that file, `AGENTS.md`, `docs/FORMAL_MODEL.md`, and `docs/EVALUATION.md` before modifying this plan.

## Scope and Non-Goals

In scope:

- Rust architectural, fault-free, and faulty SphinxVM semantics;
- probe DSL, profiles, challenge isolation, JSONL server, and judge;
- Python protocol harness, relation templates/certificates, KB, constraints/solver, synthesis, statistics, state learning, reducer, campaign/reporting;
- TLA+/SMT/differential checks;
- tutorial/standard/research benchmarks, baselines, controls, and boundary audit;
- repository commands, CI, documentation, and release evidence.

Out of scope:

- real hardware, cryptographic victims, remote targets, performance counters, cache/speculation attack code, power/EM acquisition, or third-party systems;
- a graphical UI;
- distributed deployment;
- proving every ISA instruction in a proof assistant;
- hiding the public machine/fault family from the learner in version 1.

## Current Repository State

The verified research handoff was imported as root commit `ab30e28`. It contains the
design documents, normative task specification, initial Rust/Python scaffold, schemas,
formal seeds, profiles, and tests. The original ZIP and conversation remain locally in
the ignored `preparation/` directory.

Baseline inspection established that the Python scaffold passed 14 narrow unit tests
while the Rust scaffold initially failed formatting, dependency resolution, and
Clippy. Milestone M0 repaired those failures, committed Rust/Python locks, hardened the
bounded JSONL transport and budget accounting, added exact-version negotiation, and
introduced live cross-process/schema/boundary tests. The only recovery path remains a
hand-invoked exact tutorial campaign against a fixed scaffold secret. There is no
complete DSL/architecture, production challenge/judge, persistence, Z3 hypothesis
store, bounded-noise extractor, CEGIS loop, state learner, or release evidence yet.

## Progress

- [x] (2026-07-15 00:00Z) Create project brief, formal model, architecture, research basis, evaluation design, safety policy, task specification, and initial ExecPlan.
- [x] (2026-07-15 16:10Z) Verify and import the 106-file research handoff as commit `ab30e28`; inspect the full tree and record the real scaffold baseline.
- [x] (2026-07-15 16:17Z) Complete M0 locks, fail-closed checks, bounded/correlated JSONL protocol, live process/schema tests, and initial boundary audit; evidence is recorded in `VALIDATION.md`.
- [ ] (date) Complete M1 DSL, validator, architectural semantics, and secret-independence tests.
- [ ] (date) Complete M2 microarchitecture, reference fault, profiles, challenge isolation, and observation pipeline.
- [ ] (date) Complete M3 relation templates, certificates, normalizers, and sound exact/bounded extractors.
- [ ] (date) Complete M4 harness, append-only/SQLite knowledge base, constraint IR, and exact hypothesis store.
- [ ] (date) Complete M5 tutorial recovery and fault-free negative control.
- [ ] (date) Complete M6 grammar-guided CEGIS query synthesis and integrate it into selection.
- [ ] (date) Complete M7 bounded/stochastic noise, robust sampling, MaxSMT repair, and standard acceptance.
- [ ] (date) Complete M8 soft-reset state, exact-history mode, AALpy learner, and retraction semantics.
- [ ] (date) Complete M9 relational reducer, baselines/ablations, formal/boundary audit, and release evidence.

## Surprises & Discoveries

- Observation: No implementation experiments have been run at design-package creation time.
  Evidence: `agent/STATUS.md` marks all implementation checks pending.

- Observation: The unmodified Rust scaffold does not satisfy its declared verification surface.
  Evidence: `cargo fmt --all -- --check` reports formatting differences; Clippy rejects the equal-priority `all` lint group; without `Cargo.lock`, Rust 1.82 resolves `indexmap 2.14.0`, whose manifest requires the unstabilized edition-2024 Cargo feature.

- Observation: The exact tutorial algorithm is not sound for the other published profiles.
  Evidence: a direct process run recovered the fixed tutorial secret in 10 relations, but the same scaffold campaign returned false singleton `66666666` for the fault-free profile and raised `InconsistentModelError` on standard because it treated equal quantized buckets as exact equality.

- Observation: Other long-running Rust builds are active on this host.
  Evidence: process inspection showed an OpenVM Cargo test using a separate `/home/yann/yann/ZK/arguzz-workspace/.cache/openvm-target` target directory.

Add dated observations here. Include failed assumptions, benchmark results, solver behavior, tool limitations, and concise command/artifact evidence.

## Decision Log

- Decision: Use separate Rust and Python processes with JSON Lines as the only production boundary.
  Rationale: The research question depends on black-box inference; in-process reuse would permit accidental secret access and invalidate results.
  Alternatives considered: Python-only simulator; Rust extension module; HTTP service.
  Date/author: 2026-07-15, design package.
  Consequences: Shared behavior needs schemas/golden/differential tests; production campaigns must launch a process.

- Decision: Maintain three separate semantic layers: architectural, fault-free timing, and faulty concrete execution.
  Rationale: Relation soundness requires independent proof that public semantics and the intended leakage contract hold before a fault violation is interpreted.
  Alternatives considered: One evaluator controlled by mode flags.
  Date/author: 2026-07-15, design package.
  Consequences: Some duplicated plumbing is acceptable; type boundaries and tests must prevent semantic confusion.

- Decision: Use exact bit-vector constraints first, bounded interval constraints for standard mode, and soft evidence only for stochastic mode.
  Rationale: This preserves clear soundness levels and avoids treating noisy measurements as facts.
  Alternatives considered: Bayesian inference for every profile.
  Date/author: 2026-07-15, design package.
  Consequences: Statistics is not needed for tutorial mode; final result statuses must distinguish exact and soft.

- Decision: Start query synthesis with typed relation skeleton enumeration plus SMT-filled holes and CEGIS model counterexamples.
  Rationale: It is easier to verify and debug than synthesizing arbitrary instruction streams, while still exercising syntax-guided synthesis.
  Alternatives considered: pure brute force; direct SyGuS solver; learned policy.
  Date/author: 2026-07-15, design package.
  Consequences: The grammar and relation certificates are central APIs; optional SyGuS export can follow.

- Decision: Use AALpy behind a project-owned interface only after hard-reset and exact-history modes work.
  Rationale: State-learning abstractions should not obscure core inference correctness.
  Alternatives considered: custom L* implementation; always explicit history.
  Date/author: 2026-07-15, design package.
  Consequences: M8 depends on stable macro alphabets and output discretization.

Record every later material deviation here before or with implementation.

- Decision: Preserve the verified handoff as an immutable Git baseline and keep the original preparation artifacts outside version control.
  Rationale: Implementation commits can now be reviewed against the exact supplied scaffold without duplicating the ZIP/extracted source in history.
  Alternatives considered: commit `preparation/`; edit the extracted tree in place without a baseline.
  Date/author: 2026-07-15, Codex.
  Consequences: commit `ab30e28` is the audit point for every scaffold replacement.

- Decision: Keep Rust 1.82 as the declared MSRV and commit a compatible dependency lock, including `indexmap 2.12.1`.
  Rationale: The task package explicitly pins 1.82; silently upgrading the toolchain would hide an M0 reproducibility failure.
  Alternatives considered: switch the repository to the host's newer stable toolchain; leave dependency resolution unlocked.
  Date/author: 2026-07-15, Codex.
  Consequences: CI and local commands use `--locked`; dependency upgrades must demonstrate MSRV compatibility.

- Decision: Limit this repository to two Cargo build jobs and use only its own target directory.
  Rationale: A separate OpenVM build is active and must not be interrupted or contend through a shared target lock.
  Alternatives considered: stop the other build; use unrestricted host parallelism.
  Date/author: 2026-07-15, Codex.
  Consequences: checks may take longer but do not modify or lock another project's build artifacts.

## Milestones

### Milestone 0 — Establish a trustworthy public boundary

Outcome: a clean Rust/Python workspace with locked dependencies, complete protocol schemas, and a tested `hello`/`execute` round trip between a Python client and a separate Rust process.

Implementation:

1. Inspect top-level configuration and repair generated scaffold issues.
2. Create/complete `spec/protocol.schema.json` and related schemas, with golden fixtures.
3. Implement target protocol types, bounded JSONL loop, `hello`, a minimal valid `execute`, typed errors, and `close`.
4. Implement Python protocol models/client and fake endpoint.
5. Add process integration tests and secret/private-field scans.
6. Generate dependency lockfiles and stabilize root commands/CI.

Acceptance:

    just schema-check
    just fmt
    just lint
    just test

All pass. An integration test launches the release target, negotiates the protocol, executes a minimal `HALT`, receives only public fields, handles malformed input, and closes cleanly.

### Milestone 1 — Implement the typed language and architectural machine

Outcome: users can parse, format, validate, and execute bounded programs with deterministic secret-independent architectural behavior.

Implementation:

1. Complete the EBNF and canonical fixture corpus.
2. Implement Rust AST/parser/formatter/validator.
3. Implement Python frozen AST/parser/formatter with compatible canonical text/hash.
4. Implement architectural state and instruction semantics.
5. Implement gas/control-flow validation and public digest.
6. Add static architectural-effect and resource summaries.
7. Add cross-language golden and property tests.

Acceptance:

- all ISA operations have success/failure tests;
- arbitrary bounded malformed inputs do not panic;
- for generated valid programs and several secrets, architectural results are identical;
- Rust/Python canonical text/hash agrees for golden programs;
- repository checks pass.

### Milestone 2 — Add microcode, fault, profiles, and challenge isolation

Outcome: SphinxVM exposes a coarse timing channel produced only by the intended synthetic scheduler defect, with deterministic tutorial/standard and stateful research configurations.

Implementation:

1. Add explicit micro-op lowering and fault-free cycle semantics.
2. Add bank/S-box mapping and typed microstate.
3. Implement hard/soft reset and pure state transition.
4. Implement `off`, `reference`, weaker, and stronger/signed fault variants.
5. Implement quantization and seeded noise.
6. Complete public/private profile parsing and validation.
7. Implement challenge creation/commitment/private loading and non-oracular judge.
8. Ensure server responses expose no diagnostic state.
9. Add TLA+ abstract invariants and concrete differential/property tests.

Acceptance:

- architecture is identical across faults/secrets;
- fault-free normalized cost is secret-independent on exhaustive reduced domains;
- hard reset is unique and deterministic;
- soft reset preserves exactly configured state;
- private/transcript boundary tests pass;
- deliberate fault mutations change only observation behavior;
- formal scaffold checks run and fail under an intentional test mutation.

### Milestone 3 — Build certified relation oracles

Outcome: Interrogator can create core related program families, prove/check their architectural and fault-free relations, decide exact/bounded outcomes, and emit sound serialized constraints.

Implementation:

1. Define relation/template/instance/certificate APIs.
2. Implement `anchor-switch`, `token-switch`, `epoch-switch`, `phase-shift`, `repeat-amplify`, `independent-swap`, `context-lift`, `register-rename`, and `hard-replay` in a safe order.
3. Implement static/fault-free normalizers.
4. Build a serializable constraint IR and concrete symbolic bank/fault/state functions.
5. Implement exact tutorial and bounded standard extractors.
6. Generate/cache bounded certificates.
7. Exhaustively compare concrete and symbolic behavior on a reduced domain.

Acceptance:

- every enabled template has precondition positive/negative tests;
- exhaustive reduced tests prove architectural/fault-free relations;
- the true secret/state satisfies every emitted hard constraint for all generating bounded noise values;
- quantized equal buckets produce disjunction/intervals rather than false exact equality;
- invalid/inconclusive outcomes add no hard constraints.

### Milestone 4 — Persist interrogations and maintain hypotheses

Outcome: one logical interrogation can be scheduled, executed, persisted, analyzed, committed to an exact solver, and replayed with complete provenance.

Implementation:

1. Implement subprocess harness, randomized balanced schedules, and raw transcript write-ahead.
2. Implement append-only events and SQLite schema/migrations/materialized queries.
3. Implement query nodes/relation edges/decisions/constraints/candidate snapshots.
4. Implement TTL/frontier, structural/semantic/state/partition novelty, and implication checks.
5. Implement Z3 translation, hard constraints, named assumptions, unsat cores, enumeration, diverse models, and uniqueness.
6. Implement campaign manifests, resume, replay, and basic reports.

Acceptance:

- a crash after raw response but before analysis resumes without duplicate evidence;
- every solver constraint links to raw request/response and certificate;
- implication `unknown` is not treated as novelty proof;
- exact uniqueness is tested by excluding the candidate;
- unsat-core quarantine/rollback has tests;
- deterministic replay reproduces the same derived events.

### Milestone 5 — Recover tutorial secrets

Outcome: an end-to-end black-box campaign recovers every tutorial challenge exactly under target budgets.

Implementation:

1. Seed a small set of certified relation instances.
2. Implement a deterministic lane-wise heuristic selector as a correctness baseline.
3. Add campaign stopping/result/judge/report flow.
4. Add fault-free control behavior.
5. Generate tutorial calibration/evaluation seed lists and benchmark command.
6. Diagnose and tune only through versioned profile constants if needed.

Acceptance:

- `just demo-tutorial` succeeds from a clean environment;
- 100/100 evaluation secrets recover uniquely;
- median/max logical pairs meet targets;
- fault-free controls do not report exact recovery;
- no query reads private state and boundary audit passes.

### Milestone 6 — Synthesize high-information experiments with CEGIS

Outcome: the next query is synthesized from a typed grammar to separate surviving models, verified against a diverse committee, and refined by counterexample models.

Implementation:

1. Define grammar skeletons/holes and lexicographic resource objectives.
2. Implement diverse secret/state model generation.
3. Implement symbolic signatures and pair-separation constraints.
4. Add committee partition scoring and interval/noise margin.
5. Add CEGIS counterexample selection/refinement.
6. Cache by hypothesis/profile/state-model/grammar version.
7. Integrate synthesized candidates with KB selection and log score components.

Acceptance:

- tiny exact domains match brute-force known optima;
- one test provably requires counterexample refinement;
- no-discriminator and solver-unknown cases are honest;
- fault-free profile exposes no secret discriminator;
- synthesized selection materially beats random holes on calibration seeds without using true secrets.

### Milestone 7 — Handle noise and meet standard targets

Outcome: bounded quantization is exact, stochastic evidence is robust/soft, inconsistent evidence can be diagnosed, and standard campaigns meet acceptance targets.

Implementation:

1. Complete interval/nuisance extraction and paired schedule logic.
2. Prototype robust/sequential alternatives in simulation and record decision.
3. Implement chosen estimator/stopping rule, correlation groups, and `inconclusive` semantics.
4. Implement capped grouped soft weights and MaxSMT ranking.
5. Implement high-influence witness replay, unsat-core diagnosis, quarantine, and repair.
6. Implement one-shot leakage audit, white-box grammar upper bound, and fault mutation ladder.
7. Freeze/version standard constants on calibration seeds.
8. Run full standard baselines and acceptance suite.

Acceptance:

- bounded hard constraints never exclude true configurations in exhaustive/generated tests;
- stochastic simulations report calibrated behavior;
- standard full system meets recovery/query/execution targets or a human-approved evidence-based revision is recorded;
- fault-free negative controls have no false exact declaration;
- random/stateless/KB-only/synthesis-only baselines are reported fairly.

### Milestone 8 — Learn persistent hidden state

Outcome: research mode supports exact-history inference and an AALpy-backed Mealy abstraction with conformance counterexamples and safe constraint retraction.

Implementation:

1. Stabilize macro input and discretized output alphabets.
2. Implement one-state and exact-history adapters.
3. Implement AALpy membership queries/cache and model serialization.
4. Implement conformance portfolio, distinguishing/access sequences, and held-out tests.
5. Implement `soft-history-contrast` relation.
6. Group constraints by state-model version and retract/re-evaluate after counterexamples.
7. Compare learned-state, exact-history, and no-learner variants.

Acceptance:

- unit learning works on a known Mealy fixture;
- learned model meets held-out prediction target on research challenges;
- an injected counterexample splits/invalidates a state and retracts dependent constraints;
- research results are measured and labeled, even if stretch recovery targets are not release blockers.

### Milestone 9 — Reduce witnesses and prepare a reproducible release

Outcome: high-value relation violations can be minimized while preserving proof/consequence, and the repository provides full evaluation, formal, safety, and documentation evidence.

Implementation:

1. Implement relation-aware best-first/generation-integrated reducer and caches.
2. Add equivalence/implies-core/same-partition predicates.
3. Generate minimized witnesses for every core relation family.
4. Complete baselines/ablations/report scripts and artifact hashes.
5. Complete TLA+/SMT/differential/mutation jobs.
6. Complete boundary/ethics/security/review audit.
7. Update all docs from measured behavior and produce release notes.

Acceptance:

- `agent/REVIEW_CHECKLIST.md` is completed honestly;
- all root checks and demo/benchmark/boundary commands pass;
- reports separate exact/bounded/soft/heuristic facts;
- run artifacts replay from a clean checkout;
- version 1.0 definition of complete in `agent/CODEX_TASK_SPEC.md` is satisfied.

## Concrete Implementation Steps

Work from the repository root unless stated otherwise.

1. Establish baseline:

       git status --short
       find . -maxdepth 4 -type f | sort
       rustc --version
       cargo --version
       python3 --version
       just --version
       just bootstrap
       python3 -m compileall python scripts tests/python
       cargo check --workspace

   Record exact results here and in `agent/STATUS.md`.

2. Execute milestones in order. For each milestone:

   - revise its design details based on inspected code;
   - implement the smallest vertical slice;
   - run narrow tests continuously;
   - run `just fmt`, `just lint`, `just test`, and relevant formal/demo checks;
   - update progress, discoveries, decisions, and artifact paths;
   - commit or checkpoint logically if the environment permits.

3. Use `agent/IMPLEMENTATION_RUNBOOK.md` for debugging order and campaign discipline.

4. Before profile tuning, preserve failing runs and compare concrete/symbolic predictions; do not expose private target fields or weaken uniqueness.

5. Before release, execute the full review checklist and reconcile docs/spec/schema/CLI behavior.

## Validation and Acceptance

Repository-wide required checks:

    just fmt
    just lint
    just test
    just schema-check
    just verify-formal
    just boundary-audit
    just demo-tutorial
    just benchmark-standard

Expected final observations:

- formatting/lint/tests/formal/boundary commands exit zero;
- tutorial output declares `unique_exact`, judge accepted, and provides a run path;
- standard report records at least 95/100 exact unique recoveries and target budgets, unless an explicit approved revision is present;
- fault-free report has no false exact recovery;
- benchmark report includes baselines and uncertainty/failure counts;
- every exact result includes an alternative-model unsat artifact;
- no transcript contains private target state.

Record command excerpts and artifact hashes/paths in `Artifacts and Evidence` rather than pasting huge logs.

## Recovery and Idempotence

- Do not delete user work or reset the repository to recover from errors.
- Schema/database migrations must be versioned and tested from an empty and prior-version fixture.
- Campaign event logs are append-only. Materialized SQLite views can be rebuilt from them.
- Every campaign/resume operation uses stable logical IDs to avoid double-counting retries.
- Generated challenges/runs live outside tracked source directories by default.
- Interrupted benchmark matrices detect completed campaign manifests and resume remaining seeds.
- Solver/model caches are disposable and version-keyed; deleting them must not change correctness.
- If a learned model is invalidated, disable its named constraint group and replay/recompute rather than editing history.
- If profile calibration changes, create a new semantic/profile version and retain old run readability.

## Artifacts and Evidence

Populate during implementation:

- M0 baseline and validation record: `VALIDATION.md`, 2026-07-15; locked toolchains, quality checks, live protocol tests, and initial boundary audit pass.
- Tutorial acceptance report: pending.
- Standard full-system report: pending.
- Baseline/ablation report: pending.
- Fault-free control report: pending.
- One-shot leakage audit: pending.
- Mutation ladder: pending.
- Formal/TLA+/SMT report: pending.
- Boundary-audit report: initial M0 evidence in `VALIDATION.md`; challenge permission/judge coverage remains pending M2/M9.
- Minimized witness collection: pending.
- Release manifest/revision: pending.

Each entry should contain a repository-relative or run-directory path, hash where appropriate, date, and one-sentence conclusion.

## Interfaces and Dependencies

Stable public interfaces:

- schemas under `spec/` and semantic protocol version;
- probe DSL canonical text;
- `sphinx-vm` server/challenge/judge CLI;
- `sphinx-interrogate` doctor/recover/replay/inspect/reduce/benchmark CLI;
- root `just` commands;
- result/run manifest schemas.

Core dependencies:

- Rust serde/serde_json and CLI/error/randomness crates selected during M0;
- Python Pydantic/jsonschema, Z3, AALpy, SQLite standard library, pytest/Hypothesis, ruff/mypy;
- TLC/TLA+ tool for abstract checks.

Pin resolved dependencies. Record substitutions and compatibility decisions in the Decision Log. Do not let external libraries define project persistence formats without a project-owned versioned wrapper.

## Outcomes & Retrospective

At completion, summarize:

- implemented user-visible flows;
- exact benchmark outcomes and caveats;
- strongest evidence that relation extraction is sound;
- measured contribution of interrogation KB and CEGIS;
- state-learning findings;
- fault calibration lessons;
- remaining non-blocking research questions;
- any specification changes and why.

Current outcome: design and handoff package complete; implementation and empirical results pending.
```
