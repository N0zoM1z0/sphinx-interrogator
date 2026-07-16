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
The M1 implementation now replaces the partial language/interpreter with complete
Rust and independent Python models plus cross-language golden evidence. Its functional
acceptance checks pass, but the mandatory semantic `demo-tutorial` gate remains the
real M5 flow and is not yet available, so M1 is not declared closed.
The M2 checkpoint now supplies the production challenge/judge, explicit microcode,
fault-free and faulty timing composition, typed hidden state/reset semantics, seeded
noise, independent Python target-family model, concrete differential vectors, and
executable TLC/SMT/exhaustive checks. The verified M3 checkpoint adds all nine stateless
hard-reset templates, artifact-bound certificates, conservative interval decisions,
latent-fault finite extractors, and the typed serializable constraint expression IR.
Persistence, Z3 translation/hypothesis management, and M4–M9 campaign layers remain
outstanding.

## Progress

- [x] (2026-07-15 00:00Z) Create project brief, formal model, architecture, research basis, evaluation design, safety policy, task specification, and initial ExecPlan.
- [x] (2026-07-15 16:10Z) Verify and import the 106-file research handoff as commit `ab30e28`; inspect the full tree and record the real scaffold baseline.
- [x] (2026-07-15 16:17Z) Complete M0 locks, fail-closed checks, bounded/correlated JSONL protocol, live process/schema tests, and initial boundary audit; evidence is recorded in `VALIDATION.md`.
- [ ] (2026-07-15 16:58Z) M1 implementation and milestone-specific acceptance pass: full DSL/AST/validator/interpreter, canonical text/JSON/hash fixtures, sparse memory, malformed-input checks, and generated noninterference tests. Closure is deferred only because the required real `just demo-tutorial` M5 gate still exits 1.
- [ ] (2026-07-15 17:29Z) M2 implementation and milestone-specific acceptance pass: microcode/state/fault/noise separation, strict public/private profiles, committed challenge packages, one-shot judge, live fault confinement/replay, exhaustive Rust/Python vectors, TLC, and mutation detection. Formal closure is deferred only because the required real `just demo-tutorial` M5 gate still exits 1.
- [ ] (2026-07-16 01:33Z) M3 implementation and milestone-specific acceptance pass: nine typed stateless templates, strict cached certificates, exact/bounded interval decisions, latent-fault extractors, recursive expression IR, schemas, and reduced/live soundness evidence. Closure is deferred only because the required real `just demo-tutorial` M5 gate still exits 1.
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

- Observation: Summing every encoded instruction once is neither a minimum nor a maximum dynamic gas path in the presence of branches and loops.
  Evidence: the interrupted M1 draft called that value `minimum_gas`; it is now named and documented as exact `encoded_gas`, while the executor enforces the profile gas limit on the retired path.

- Observation: The repository-wide semantic demo gate cannot pass during M1 without implementing the actual M5 challenge/recovery/judge flow.
  Evidence: `just demo-tutorial` on 2026-07-15 printed its explicit M5 TODO and exited 1. A weaker smoke recipe would not satisfy the task, so the M1 implementation is checkpointed without falsely closing the milestone.

- Observation: The initial M2 commitment covered the secret but not all runtime-private scheduler configuration.
  Evidence: review found that changing the private fault variant could still pass load-time commitment verification; the version-1 commitment now length-frames and binds the secret, permutation, salts, fault, logged generation root, noise key, and nonce, with a tamper regression test.

- Observation: Running TLC exposed two defects that structural token checks could not detect.
  Evidence: the abstract guard used addition instead of the concrete XOR rule, and `HardReset == Init'` was not executable TLA+. After correction, TLC 2.19 exhausts 2,276 distinct reachable states without an invariant violation.

- Observation: A formal check that only produces positive results can silently become vacuous.
  Evidence: the M2 checker now exhausts 131,072 guarded-replay combinations and self-tests an intentional `replay_credit == 2` suppression mutation; the direct mutated run exits 1 at `phase=0,replay=2,lane=0,token=0,epoch=0,secret_bank=0,anchor_bank=0`.

- Observation: Treating the documented fault family as public does not reveal which family member a generated challenge selected.
  Evidence: exact equal anchor observations under the `off` member are consistent with all 16 lane secrets; the M3 extractor keeps fault identity in every finite assignment, and its off-control test retains the true off model and all secret projections.

- Observation: Equal quantized buckets are compatible with negative, zero, and positive cycle deltas even under a small bounded-noise profile.
  Evidence: the width-four regression produces a normalized interval containing `{-1,0,1}`, returns `inconclusive`, and emits no hard constraint; repeat amplification with certified replay drain moves a signal wholly above zero and emits a sound bounded disjunction for all nine noise pairs.

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

- Decision: Represent M3 hard evidence as finite disjunctions over secret projections and the shared latent fault variant, while also defining a generic solver-independent typed expression IR for M4.
  Rationale: Finite enumeration makes reduced extractor soundness directly testable and handles quantization/noise without false elimination; the generic IR prevents Z3 objects from becoming the persistence contract.
  Alternatives considered: Assume the reference fault from profile names; store Z3 ASTs; convert bucket equality directly into cycle equality.
  Date/author: 2026-07-16, Codex implementation.
  Consequences: M4 can translate either finite evidence or composed expressions to Z3, and exact recovery must identify a secret despite fault-family ambiguity.

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

- Decision: Retain CALL/RET with forward-only calls, make LOOP the only backward edge, and validate an exact bounded return-stack abstraction before execution.
  Rationale: This implements the complete requested ISA while making recursion, reachable return underflow, stack overflow, and unbounded arbitrary backedges invalid programs.
  Alternatives considered: omit CALL/RET; allow arbitrary backward branches and rely only on gas.
  Date/author: 2026-07-15, Codex.
  Consequences: LOOP counts backedges and runtime gas supplies a second termination bound; the exact behavior is documented in `docs/DSL_AND_ARCHITECTURE.md`.

- Decision: Make `(base + signed offset) mod 256` the total memory-address rule and normalize all resolved branch targets to `LNNN` labels.
  Rationale: Total addressing prevents execution traps, while index-derived labels make independent formatting stable across source label choices.
  Alternatives considered: trap on out-of-range addresses; preserve user labels in hashes.
  Date/author: 2026-07-15, Codex.
  Consequences: Rust and Python independently agree on canonical text, typed-AST JSON, and SHA-256 through the checked-in full-ISA fixture.

- Decision: Distinguish exact encoded cost from dynamic execution gas instead of using an inaccurately named static minimum.
  Rationale: Conditional paths can skip encoded instructions and LOOP can repeat them; a one-pass sum is exact only as an encoded resource measure.
  Alternatives considered: conservatively reject programs whose encoded sum exceeds runtime gas; call the sum a minimum.
  Date/author: 2026-07-15, Codex.
  Consequences: `encoded_gas` is reported honestly, and structured runtime gas exhaustion remains authoritative and secret-independent.

- Decision: Put fault selection and every seed-bearing value only in strict private challenge configuration, while keeping the standard and fault-free public profile files byte-identical.
  Rationale: Blind negative controls must not identify their assignment through profile names or fields, and a public deterministic generation seed would reveal the challenge secret.
  Alternatives considered: retain a public `fault_mode`; log the root seed in public metadata; use separate visibly named control profiles.
  Date/author: 2026-07-15, Codex.
  Consequences: challenge creation logs its generation root under mode `0600`; the public commitment is opaque without its private nonce/root; System B receives only public metadata and process observations.

- Decision: Share one explicit microcode lowering and one pure hidden-state transition across off/reference/weak/signed variants, then apply the selected fault as a separate timing delta.
  Rationale: Fault variants must not accidentally change architecture or take a different scheduler path.
  Alternatives considered: per-variant evaluators; embed fault selection inside the transition.
  Date/author: 2026-07-15, Codex.
  Consequences: Rust tests compare architecture across variants, and a live off/reference bank sweep observes deltas `[0,0,0,0]` versus a permutation of `[0,0,0,1]` with identical digests.

- Decision: Pin TLA+ tools 1.7.4 in the ignored local tool directory and make `just verify-formal` run TLC, Z3, exhaustive finite checks, and a mutation self-test.
  Rationale: Structural formal-file checks did not establish that the TLA+ specification parsed or that invariants held.
  Alternatives considered: leave TLC optional until M9; commit the binary JAR; rely only on Python enumeration.
  Date/author: 2026-07-15, Codex.
  Consequences: `just bootstrap-formal` verifies the downloaded JAR SHA-256, TLC state goes under ignored `.cache/`, and missing formal tooling fails closed.

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
- M1 language/architecture evidence: `VALIDATION.md`, `tests/fixtures/programs/`, and `docs/DSL_AND_ARCHITECTURE.md`, 2026-07-15; all milestone-specific tests and repository checks pass, while the required M5 tutorial gate remains explicitly pending.
- M2 target/challenge evidence: `VALIDATION.md`, `tests/fixtures/model/`, `tests/fixtures/challenge/`, and `docs/SYSTEM_A_SPHINX_VM.md`, 2026-07-15; 44 Rust and 68 Python tests cover the semantic split, live fault confinement, deterministic replay, permissions, and judge policy.
- M3 relation/extractor evidence: `VALIDATION.md`, `tests/python/test_certified_relations.py`, `tests/python/test_constraint_ir.py`, `tests/fixtures/relations/`, and `docs/RELATION_ORACLES.md`, 2026-07-16; 99 Python tests include every stateless relation, all bounded noise/fault generators, strict certificate/IR persistence, and live Rust relation arms.
- Tutorial acceptance report: pending.
- Standard full-system report: pending.
- Baseline/ablation report: pending.
- Fault-free control report: pending.
- One-shot leakage audit: pending.
- Mutation ladder: M2 off/reference/weak/signed unit and live confinement evidence in `VALIDATION.md`; statistical M7/M9 calibration remains pending.
- Formal/TLA+/SMT report: M2 scheduler and M3 reduced relation/expression differential evidence in `VALIDATION.md`; durable-session and final mutation obligations remain M4/M9.
- Boundary-audit report: M2 artifact permission/public-key/live-response evidence in `VALIDATION.md`; final release rerun remains pending M9.
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
