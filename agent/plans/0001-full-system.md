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
The M1 implementation replaces the partial language/interpreter with complete Rust and
independent Python models plus cross-language golden evidence.
The M2 checkpoint now supplies the production challenge/judge, explicit microcode,
fault-free and faulty timing composition, typed hidden state/reset semantics, seeded
noise, independent Python target-family model, concrete differential vectors, and
executable TLC/SMT/exhaustive checks. The verified M3 checkpoint adds all nine stateless
hard-reset templates, artifact-bound certificates, conservative interval decisions,
latent-fault finite extractors, and the typed serializable constraint expression IR.
The verified M4 checkpoint adds raw-wire write-ahead, hash-chained events, rebuildable
SQLite views, deterministic scheduling/frontier logic, and exact Z3 hypothesis
management with durable provenance. The verified M5 checkpoint adds deterministic
public-only tutorial recovery, exact secret-projection uniqueness, one-shot judging,
accepted-report resume, and a blind fault-free negative control. The verified M6
checkpoint adds typed bounded relation skeletons, Z3 finite-hole
filling, diverse exact/proxy committees, pair-separating CEGIS, conservative margin and
resource objectives, cache identity, and durable frontier score logs. The verified M7
checkpoint adds calibrated sequential soft evidence, capped grouped MaxSMT weights,
soft-group replay/quarantine/repair, bounded standard-profile recovery, public
leakage/learnability audit, and the full published standard benchmark. The verified
M8 checkpoint adds one-state, exact-history, and AALpy-backed learned-state Mealy
models; membership caching; conformance/counterexample evidence; state-model
constraint retraction; and `soft-history-contrast/v1`. The verified M9 checkpoint
adds relation-aware best-first witness reduction, finite public-model preservation
predicates, minimized witnesses for every enabled relation family, CLI
doctor/reduce/benchmark coverage, reducer report schema coverage, release notes, a
completed review checklist, and an ignored release manifest with artifact hashes.

A comprehensive audit on 2026-07-16 reopened M8 and M9 acceptance. The repair pass
following that audit rebuilt challenge security, recursive protocol validation,
certificate/extractor enforcement, standard benchmark v2 semantics, real research
state learning, measured replay witness reduction, clean formal bootstrapping, and
release manifest v2. The negative audit reproductions below are retained as history;
the later superseding observations and evidence list record the current behavior.

## Progress

- [x] (2026-07-15 00:00Z) Create project brief, formal model, architecture, research basis, evaluation design, safety policy, task specification, and initial ExecPlan.
- [x] (2026-07-15 16:10Z) Verify and import the 106-file research handoff as commit `ab30e28`; inspect the full tree and record the real scaffold baseline.
- [x] (2026-07-15 16:17Z) Complete M0 locks, fail-closed checks, bounded/correlated JSONL protocol, live process/schema tests, and initial boundary audit; evidence is recorded in `VALIDATION.md`.
- [x] (2026-07-16 02:34Z) Close M1 after its complete DSL/architecture evidence and the real downstream tutorial gate both pass.
- [x] (2026-07-16 02:34Z) Close M2 after its semantic/challenge/formal evidence and the real downstream tutorial gate both pass.
- [x] (2026-07-16 02:34Z) Close M3 after all certified relation/extractor evidence and the real downstream tutorial gate both pass.
- [x] (2026-07-16 02:34Z) Close M4 after durable campaign/exact-solver evidence, database migration 2, and the real downstream tutorial gate all pass.
- [x] (2026-07-16 02:34Z) Complete M5 deterministic tutorial recovery and blind fault-free negative control: 100/100 exact accepted reference seeds and 100/100 `candidate_set` off-fault results at 16 logical families each.
- [x] (2026-07-16 03:00Z) Complete M6 grammar-guided CEGIS: typed anchor/repeat skeletons, bounded enumeration, Z3 hole filling, diverse hypothesis-store committees, real counterexample refinement, interval/resource objectives, deterministic cache/ties, frontier integration, live Rust execution, and 20-seed random-hole calibration.
- [x] (2026-07-16 04:52Z) Complete M7 bounded/stochastic noise, robust sampling, MaxSMT repair, and standard acceptance: 600-campaign standard matrix passed with 100/100 full-reference exact, p95 48 logical families, and 100/100 off-control `candidate_set` results.
- [x] (2026-07-16 05:08Z) Historical M8 closure, superseded by the acceptance
  re-audit below: deterministic fixture evaluation reported no-learner 0.133,
  exact-history 1.0, and learned-state 1.0.
- [x] (2026-07-16 06:24Z) Historical M9 closure, superseded by the acceptance
  re-audit below: the original scripts reported 10/10 minimized families and passing
  release gates.
- [x] (2026-07-16 08:00Z) Reopen M8 acceptance: replace the deterministic
  `ping/toggle` fixture-only report with held-out measurements from actual
  research-profile SphinxVM challenges and integrate state-conditioned inference.
- [x] (2026-07-16 08:00Z) Reopen M9 acceptance: repair boundary isolation, relation
  certificate enforcement, baseline semantics, run manifests/artifact validation,
  clean CI formal bootstrap, result/CLI contracts, and release documentation.
- [x] (2026-07-16 10:30Z) Complete P0 challenge-security repair: private 256-bit root
  generation is separate from public campaign scheduling, public IDs are generic,
  VM launch uses only a public directory plus private FD brokerage, and boundary tests
  cover distinct UID/FD and recursive private-field injection.
- [x] (2026-07-16 14:40Z) Finish P0 benchmark v2: challenge/noise pairing,
  randomized execution, false-exact accounting, CLI status reading, and real selector
  branches are implemented; paired bootstrap confidence intervals are reported in
  v1.1; the B0-B7 surface is machine-readable and complete; `just
  benchmark-standard` completed the full 100-seed / 700-campaign matrix with
  `full_published_matrix=true`, `targets_met=true`, full/reference 100/100 exact,
  and fault-off 0 false exact.
- [x] (2026-07-16 13:20Z) Add paired seed-level bootstrap confidence intervals to
  the standard benchmark report, schema, fixture, tests, and current selected
  benchmark artifact.
- [x] (2026-07-16 13:45Z) Add B0-B7 benchmark surface evidence: B0 is a real
  no-query deterministic final-guess judge baseline, B1-B4 bind to measured selector
  branches, B5/B6 are marked not applicable to the standard profile, and B7 binds to
  the development-only standard-profile upper-bound artifact.
- [x] (2026-07-16 14:53Z) Finish P1 real M8 semantic artifact evidence: real research
  SphinxVM measurements compare no learner, exact history, and learned state; M8 now
  records independent campaign private roots and one non-trivial learned-state
  effective-nibble constraint with state-model provenance and retraction metadata.
- [x] (2026-07-16 14:53Z) Finish P1 real M9 semantic artifact evidence: reducer
  results now reconstruct the accepted parent chain to the final witness, and measured
  replay records and honors each relation's reset policy.
- [x] (2026-07-16 15:04Z) Bind relation certificates to real proof/test/semantic
  artifact contents: `relation-contracts-v1` records SHA-256 digests for the SMT
  contract, certificate/extractor tests, and Rust machine semantics file; stale
  supporting hashes now fail closed in certificate loading.
- [x] (2026-07-16 16:08Z) Add adversarial mutation regressions: a contradictory
  symbolic-model constraint is UNSAT rather than false-exact, and a broken static-cost
  normalizer is rejected as `INVALID` before hard extraction.
- [x] (2026-07-16 13:05Z) Repair release-manifest fail-closed behavior: status now
  depends on semantic artifact checks and explicit root-gate evidence, absolute
  `--output` paths no longer crash after writing, and `just release-manifest` fails
  while current release evidence is blocked.
- [x] (2026-07-16 15:10Z) Add machine-readable validation-gate evidence recording:
  `scripts/record_validation_gate.py` runs a root command, captures exit status,
  timestamps, stdout/stderr log hashes, and merges the entry into
  `runs/release-m9/validation-evidence.json`; `just release-manifest` now reads this
  file by default.
- [x] (2026-07-16 15:37Z) Add campaign manifest v1.2 reproducibility metadata:
  finalized tutorial and standard campaign manifests record revision, dirty state,
  versions, command/cwd, timing, normative campaign status, and artifact hashes; all
  700 standard benchmark run directories now have v1.2 manifests with
  `unique_exact` or `candidate_set` status.
- [x] (2026-07-16 15:47Z) Re-audit the task-spec gap list and repair stale public
  lifecycle documentation: README, protocol, and repository-guide examples now use
  split public/private challenge creation, private-root files, private directory FD
  brokerage, and public sockets. `git diff --check`, `just docs-check`, and
  `just schema-check` passed after the documentation repair.
- [x] (2026-07-16 15:56Z) Normalize public recovery and benchmark result statuses:
  tutorial, standard, and B0 reports now emit task-spec statuses (`unique_exact`,
  `candidate_set`, `model_inconsistent`, `target_error`) instead of legacy
  `inconclusive`, `unique_exact_unjudged`, `inconsistent`, or `judge_rejected`;
  existing standard run reports are upgraded on resume, and the 700-campaign
  standard benchmark artifact now contains only `unique_exact`/`candidate_set`
  result rows.
- [x] (2026-07-16 16:24Z) Generate release-bound evaluation CSV/plot artifacts:
  `just export-evaluation-artifacts` writes campaign, query, relation, state-learning,
  and reducer CSVs plus deterministic SVG plots; release manifest v2 now hashes and
  semantically checks the evaluation artifact manifest.
- [ ] (2026-07-16 13:30Z) Finish P2 release evidence: manifest v2 records useful
  metadata, five aggregate hashes, semantic release checks, and gate-evidence slots,
  and the clean-tree manifest now completes. Current evidence is still short of a
  release tag because broader CI smoke, release proof, and documentation/version
  alignment remain incomplete.
- [x] (2026-07-16 12:08Z) Re-audit every task-spec acceptance area and rerun local
  quality, schema, formal, boundary, tutorial, M8, and M9 checks. Record the remaining
  P0/P1/P2 blockers in `agent/STATUS.md`, `agent/REVIEW_CHECKLIST.md`, this ExecPlan,
  and `VALIDATION.md`.

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

- Observation: A target response and its derived oracle event are two distinct crash-consistency boundaries.
  Evidence: the injected recorder crash occurs after exact public response bytes are atomically written but before protocol decode; resume commits one execution from those bytes while the replacement fake endpoint records zero calls.

- Observation: Syntactically new candidates do not establish semantic novelty when an implication query times out.
  Evidence: the M4 frontier test returns `unknown`, appends no candidate event, and only accepts the same candidate after a `not_implied` result supplies a countermodel status.

- Observation: Exact tutorial recovery does not require identifying the latent fault-family member.
  Evidence: each reference campaign has three satisfying full models (reference, weak, and signed) with one shared secret projection; excluding that 16-bit projection is `unsat` for all 100 published seeds.

- Observation: A fixed complete tutorial design is both cheaper and easier to audit than adaptive early stopping at this milestone.
  Evidence: every reference and off-fault campaign uses exactly 16 logical relation families and 32 physical executions; the reference matrix is 100/100 exact and the off-fault matrix is 100/100 `candidate_set` public results.

- Observation: Committee scoring materially improves candidate balance even before a full standard campaign exists.
  Evidence: on 20 deterministic eight-model nibble subsets with no designated true secret, M6 achieved mean worst bucket 3.00 versus 7.15 for seeded uniform random holes and won strictly on 19/20 subsets.

- Observation: Quantization/noise margin changes the grammar optimum, not merely its numeric score.
  Evidence: the exact committee selects a cheap anchor switch, while independent `[-1,1]` nuisance intervals with required positive separation select an eight-fold certified drained repeat; symbolic and concrete signatures agree exhaustively for every nibble/fault member.

- Observation: The standard recovery loop must reuse bounded public sessions.
  Evidence: an early smoke run reached the server's `session_limit` after allocating one source/follow-up session per relation; reusing `standard-source` and `standard-follow_up` completed seed 50000 exactly with 34 logical families and 68 executions.

- Observation: The frozen standard profile is learnable by simple certified anchor schedules, not only by the full CEGIS selector.
  Evidence: `runs/standard-benchmark-v1/standard-benchmark-report.json` records 100/100 exact and accepted reference campaigns for `full`, `random`, `stateless`, `kb_no_synthesis`, and `synthesis_no_kb`; the full selector median is 40 logical families and p95 is 48.

- Observation: The drained hard-reset M7 grammar does not distinguish the active `reference`, `weak`, and `signed` variants.
  Evidence: `runs/standard-profile-audit-m7/standard-profile-audit.json` records repeat-amplify fault margins of 15 cycles for all three active variants and zero for `off`; a one-seed mutation ladder recovered reference/weak/signed exactly at the same cost shape.

- Observation: A learned quotient can be much smaller than exact bounded history on the deterministic soft-reset fixture.
  Evidence: `runs/state-learning-m8/state-learning-report.json` reports exact-history depth four with 31 states and 1.0 held-out accuracy, while AALpy L* learns a 2-state Mealy model with 1.0 held-out accuracy; the one-state no-learner baseline reaches 0.133.

- Observation: Relation reduction can be useful without violating the black-box boundary.
  Evidence: `runs/reduced-witnesses-m9/reduced-witnesses-report.json` minimizes all ten enabled relation families using only typed public relation programs and finite public-family model signatures; the preservation record declares `uses_true_secret=false`.

- Observation: The final release manifest is inherently a generated run artifact, not a tracked source file.
  Evidence: `runs/release-m9/release-manifest.json` records the current HEAD, dirty status, tool versions, and hashes of five generated public artifacts; committing the manifest itself would immediately stale its recorded revision/dirty state.

- Observation: The current process split does not enforce the claimed private-file
  boundary.
  Evidence: Python receives the challenge root and runs under the same UID that owns
  mode-0700/mode-0600 private files; an audit probe confirmed a private `secret.bin` is
  readable. `scripts/boundary_audit.py` checks only literal source markers and decoded
  dataclass keys.

- Observation: Protocol response validation is strict only at the top level.
  Evidence: adding `observation.secret` to a schema fixture was accepted by
  `decode_execute_response`; the schema declares nested `additionalProperties=false`,
  and raw write-ahead would persist the injected field before typed decoding.

- Observation: Relation proof strength is self-declared rather than verified at hard
  extraction time.
  Evidence: replacing a certified relation's source program produced
  `architectural_precheck=False` while retaining an `exhaustive-enumeration`
  certificate, yet `extract_finite_models` emitted a hard constraint. The fault-free
  precheck is the tautology `x - x == 0`.

- Observation: The M8 report is a learner unit fixture, not research-profile
  evaluation.
  Evidence: `scripts/evaluate_state_learning.py` uses only `ping`, `toggle`, and a
  local `_toggle_oracle`; it never starts SphinxVM or reads `research.toml`.

- Observation: The published standard ablations cannot establish KB or synthesis
  value.
  Evidence: `full` and `synthesis_no_kb` take the same CEGIS branch;
  `kb_no_synthesis` selects the canonical minimum without consulting the KB; the full
  frontier is recreated around one candidate and immediately selects that candidate.

- Observation: Generated campaign artifacts have drifted across schema versions.
  Evidence: an audit sweep found 825 manifests, of which 202 are legacy version 1.0
  and fail the current version-1.1 schema. Both 100-seed tutorial matrix commands
  resumed these legacy runs, while a fresh detached-checkout tutorial generated a
  valid 1.1 manifest.

- Observation: The clean-CI TLC bootstrap defect found by the first audit has been
  repaired.
  Evidence: `just verify-formal` depends on `bootstrap-formal`, and
  `.github/workflows/ci.yml` downloads and SHA-256 verifies the pinned TLC 1.7.4 jar
  before invoking the formal checker.

- Observation: The M8 fixture-only finding is superseded only for measurement, not for
  state-conditioned secret inference.
  Evidence: `runs/state-learning-m8/state-learning-report.json` measures 126 held-out
  words on real research SphinxVM campaigns and reaches 0.246/1.0/1.0 accuracy, while
  `scripts/evaluate_state_learning.py` persists the dependent constraint as Boolean
  literal `true`.

- Observation: Measured reducer evidence does not make the reported `steps` array a
  replayable reduction trace.
  Evidence: `python/sphinx_interrogator/reducer.py` appends every accepted search edge
  to one flat list without parent reconstruction. A fresh report had discontinuities
  in 9 of 10 families, including 350 breaks across 351 hard-replay steps; the replay
  script also hard-resets every candidate regardless of relation policy.

- Observation: M8 state-conditioned inference now emits a non-trivial public
  projection constraint instead of a tautology.
  Evidence: `PATH=/tmp/sphinx-just/bin:$PATH just evaluate-state-learning` regenerated
  `runs/state-learning-m8/state-learning-report.json` with
  `state_conditioned_inference.status=complete`, `nontrivial_constraints=1`,
  `shared_private_root=false`, and an exact candidate snapshot reducing
  `effective_nibble_lane_0` from 16 values to 4.

- Observation: M9 reducer reports now contain continuous replayable parent paths and
  reset-policy-aware replay evidence.
  Evidence: `PATH=/tmp/sphinx-just/bin:$PATH just reduce-witnesses` regenerated
  `runs/reduced-witnesses-m9/reduced-witnesses-report.json` with
  `all_minimized=true`, `all_replay_paths_valid=true`, and
  `reset_policy_honored=true`; the `soft-history-contrast/v1` measured replay uses
  resets `["hard", "soft"]`.

- Observation: Release manifest v2 schema validity does not imply release validity.
  Evidence: `scripts/release_manifest.py` derives `complete` only from missing artifact
  files and records every gate as `not_run_by_manifest`; the generated manifest still
  says `complete` while its embedded standard benchmark reports
  `full_published_matrix=false` and `targets_met=false`.

- Observation: Release-manifest completion is now fail-closed instead of
  presence-based.
  Evidence: `PATH=/tmp/sphinx-just/bin:$PATH just release-manifest` writes
  `runs/release-m9/release-manifest.json` and exits 1 because the manifest is
  `blocked`; after the full standard benchmark rerun the generated report lists failed
  semantic checks, a dirty repository check, and root validation commands with missing
  evidence. After the M8/M9 and evaluation-artifact repairs, only the dirty repository
  check remains failed among release checks.

- Observation: Standard benchmark report v1.1 now records paired bootstrap
  confidence intervals. A selected one-seed matrix remains only smoke evidence, while
  the later full matrix is the release benchmark evidence.
  Evidence: rerunning `scripts/benchmark_standard.py --output
  runs/standard-benchmark-v2 --limit 1` generated 18 group intervals and 12
  full-vs-baseline paired comparisons over the selected one-seed matrix; that smoke
  artifact reported `full_published_matrix=false` and `targets_met=false`.

- Observation: The selected standard benchmark now has a complete B0-B7 surface, but
  remains selected evidence only.
  Evidence: rerunning the same command after adding B0 generated seven campaigns:
  B0 `random_final_guess` ended `candidate_set` with zero logical/physical queries;
  B1-B4 are measured black-box selector branches; B5/B6 are explicitly
  not-applicable to standard; and B7 points to the development-only upper-bound
  artifact. The release manifest's failed checks dropped to six, with
  `standard.required_ablation_surface` now passing.

- Observation: The repaired current-code standard benchmark now satisfies the full
  published matrix gate.
  Evidence: `PATH=/tmp/sphinx-just/bin:$PATH just benchmark-standard` completed 700
  campaigns over 100 published seeds and exited 0. The report records
  `full_published_matrix=true`, `targets_met=true`, paired bootstrap intervals,
  complete B0-B7 evidence, full/reference 100/100 exact, B0 random-final-guess 0/100
  exact, and fault-off 0 false exact declarations.

- Observation: Passing `just verify-formal` does not cover the task's complete formal
  obligation set.
  Evidence: `formal/SphinxVM.tla` models scheduler variables but no architectural
  state, gas, or progress, and its configured invariants do not state soft/hard reset,
  architectural confinement, or fault-disabled normalized-cost independence.

- Observation: Relation certificates now bind actual supporting artifact contents.
  Evidence: `relation-contracts-v1` records SHA-256 digests for
  `formal/relation_contracts.smt2`, `tests/python/test_certified_relations.py`, and
  `crates/sphinx-vm/src/machine.rs`; `uv run --frozen pytest
  tests/python/test_certified_relations.py tests/python/test_relations.py` passed 30
  tests, including a stale-supporting-hash rejection.

- Observation: Root-gate evidence now has a machine-readable recorder and all expected
  root gates have been rerun through it.
  Evidence: `uv run --frozen pytest tests/python/test_validation_evidence.py
  tests/python/test_release_manifest.py` passed 4 tests; `just release-manifest`
  records the validation evidence path in its command argv, reports
  `validation_gates_pass=true`, and remains `blocked` only because
  `repository.clean` fails.

- Observation: Tutorial and standard campaign manifests now carry v1.2 runtime
  reproducibility metadata.
  Evidence: `uv run --frozen python` inspection found 700/700 manifests under
  `runs/standard-benchmark-v2/runs` with `manifest_version` `1.2`, statuses
  `candidate_set` or `unique_exact`, and artifact hashes; `runs/tutorial-demo-v3/manifest.json`
  is also v1.2 with `unique_exact` status.

- Observation: Public lifecycle documentation had drifted behind the repaired split
  challenge interface and has now been corrected.
  Evidence: README, `docs/PROTOCOL.md`, and `docs/REPOSITORY_GUIDE.md` now show
  `challenge private-root`, split `--public-output`/`--private-output`,
  `--private-root-file`, `--private-challenge-fd`, and public socket usage. After the
  repair, `git diff --check`, `PATH=/tmp/sphinx-just/bin:$PATH just docs-check`, and
  `PATH=/tmp/sphinx-just/bin:$PATH just schema-check` passed.

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

- Decision: Make raw public bytes and the hash-chained event log authoritative; treat SQLite and Z3 state as rebuildable materializations.
  Rationale: The target cannot replay an already consumed physical budget after an analysis crash, while database/solver caches can be reconstructed deterministically from immutable public evidence.
  Alternatives considered: Write SQLite first; store only typed responses; pickle live Z3 objects.
  Date/author: 2026-07-16, Codex implementation.
  Consequences: Stable execution/event IDs make retries idempotent, constraints require raw/certificate provenance, and replay digest mismatch is a hard error.

- Decision: Declare tutorial uniqueness over the secret projection and submit the judge only after alternative-secret exclusion is unsatisfiable.
  Rationale: Fault assignment is deliberately private and reference, weak, and signed can remain observationally equivalent in this bounded tutorial; requiring a unique full model would reject an otherwise exact secret recovery.
  Alternatives considered: assume the reference member; judge a candidate before uniqueness; require a unique `(secret, fault)` tuple.
  Date/author: 2026-07-16, Codex implementation.
  Consequences: reports preserve the three-model ambiguity, contain an explicit projection-level `unsat` artifact, and off-fault campaigns remain `candidate_set` results with no judge call.

- Decision: Start query synthesis with typed relation skeleton enumeration plus SMT-filled holes and CEGIS model counterexamples.
  Rationale: It is easier to verify and debug than synthesizing arbitrary instruction streams, while still exercising syntax-guided synthesis.
  Alternatives considered: pure brute force; direct SyGuS solver; learned policy.
  Date/author: 2026-07-15, design package.
  Consequences: The grammar and relation certificates are central APIs; optional SyGuS export can follow.

- Decision: Use complete finite partition entropy only for enumerated committees and label bounded diverse-model scores as committee proxies.
  Rationale: Z3's deterministic diverse models improve coverage but are not posterior samples or uniform model counts; using an exact-information label would overstate the evidence.
  Alternatives considered: call every committee score information gain; add an uncalibrated Bayesian prior; delay synthesis until exact model counting exists.
  Date/author: 2026-07-16, Codex implementation.
  Consequences: the same lexicographic worst-bucket/margin/resource objective operates in both modes, but every durable score records `exact-information` or `committee-proxy`, committee size, and cache inputs.

- Decision: Use AALpy behind a project-owned interface only after hard-reset and exact-history modes work.
  Rationale: State-learning abstractions should not obscure core inference correctness.
  Alternatives considered: custom L* implementation; always explicit history.
  Date/author: 2026-07-15, design package.
  Consequences: M8 depends on stable macro alphabets and output discretization.

- Decision: Treat standard benchmark smoke/limited runs separately from full published acceptance.
  Rationale: a one-seed smoke can verify report/resume mechanics but cannot prove the 100-seed target; the CLI now records both selected-threshold health and full-target completion, while `just benchmark-standard` requires the full target.
  Alternatives considered: make all limited runs fail; allow limited runs to set `targets_met`.
  Date/author: 2026-07-16, Codex implementation.
  Consequences: partial calibration commands can pass honestly, and release evidence still requires `full_published_matrix=true`.

- Decision: Keep the standard active fault variants latent-equivalent under the M7 drained hard-reset grammar.
  Rationale: the M7 acceptance target is exact secret recovery and off-control soundness; distinguishing active variants requires state/history experiments that belong to M8.
  Alternatives considered: change the published standard fault constants; add uncertified stateful probes to M7.
  Date/author: 2026-07-16, Codex implementation.
  Consequences: M7 reports `reference`, `weak`, and `signed` ambiguity honestly and does not claim active-variant identification.

- Decision: Use a project-owned serializable Mealy model instead of persisting AALpy objects.
  Rationale: model artifacts must be stable, digestible, and replayable without depending on third-party object internals.
  Alternatives considered: pickle AALpy hypotheses; store only screenshots/metrics.
  Date/author: 2026-07-16, Codex implementation.
  Consequences: every learned model records alphabet/discretizer versions, transitions, membership-cache digest, conformance metrics, counterexamples, and an artifact digest.

- Decision: Make state-conditioned constraints retract by provenance marker.
  Rationale: a conformance counterexample invalidates all evidence that assumed a learned state label, but independent hard-reset evidence should remain active.
  Alternatives considered: rebuild all constraints after every learner update; delete invalid evidence.
  Date/author: 2026-07-16, Codex implementation.
  Consequences: groups with `state-model:<id>` provenance are disabled through append-only state-change events when that model is invalidated.

- Decision: Treat M9 witness reduction as a public-model consequence-preservation problem.
  Rationale: release witnesses must not inspect a true challenge secret, but they still need a concrete preservation predicate stronger than syntax-only shrinking.
  Alternatives considered: compare against hidden true configurations; accept any precheck-preserving cost decrease; require exact residual equality for every reduction.
  Date/author: 2026-07-16, Codex implementation.
  Consequences: the reducer accepts only typed/certified candidates with lower lexicographic cost and finite public-family equivalence, same-partition, or implies-core preservation; repeat shrink uses sign-level implies-core where exact residual magnitude intentionally changes.

- Decision: Keep the release manifest under ignored `runs/` and track the generator instead.
  Rationale: the manifest records the current revision, dirty status, tool versions, and generated artifact hashes; committing it would make the recorded state stale.
  Alternatives considered: commit one manifest snapshot; omit release artifact hashing; hand-write release notes only.
  Date/author: 2026-07-16, Codex implementation.
  Consequences: reviewers regenerate `just release-manifest` after checkout or after a release commit, while tracked docs/status record the evidence path and current pre-commit hash.

- Decision: Reopen M8/M9 and treat the 2026-07-16 comprehensive audit as the current
  release status.
  Rationale: Passing existing tests and aggregate thresholds is insufficient when
  required boundary, proof, baseline, research, artifact, and clean-CI properties have
  direct counterexamples.
  Alternatives considered: retain the completion claim and list the findings as
  non-blocking limitations.
  Date/author: 2026-07-16, Codex audit.
  Consequences: no v1.0/research-complete tag should be created until the blockers are
  fixed, covered by regressions, and all evidence is regenerated from empty artifacts.

- Decision: Distinguish command success from task-spec acceptance in all status and
  release records.
  Rationale: The M8, reducer, formal, and manifest commands can exit zero while their
  output lacks required semantics or evidence.
  Alternatives considered: treat remaining gaps as documentation-only caveats.
  Date/author: 2026-07-16, Codex acceptance re-audit.
  Consequences: scripts may remain green, but milestones stay open until their
  normative properties are directly tested and represented in artifacts.

- Decision: A release manifest is complete only when artifact presence, artifact
  semantic acceptance, repository cleanliness, and explicit root-gate evidence all
  pass.
  Rationale: Hashing files proves reproducibility of bytes, not acceptance of their
  contents or execution of the release checks.
  Alternatives considered: keep validation commands as informational
  `not_run_by_manifest` entries; infer gate success from recently run local commands.
  Date/author: 2026-07-16, Codex implementation.
  Consequences: `just release-manifest` is now expected to fail while benchmark,
  M8/M9, repository cleanliness, or gate evidence is incomplete; manual manifest
  generation without `--require-complete` still writes a blocked audit artifact.

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
    just docs-check
    just verify-formal
    just boundary-audit
    just demo-tutorial
    just benchmark-standard
    just evaluate-state-learning
    just reduce-witnesses
    just release-manifest

Expected final observations:

- formatting/lint/tests/formal/boundary commands exit zero;
- tutorial output declares `unique_exact`, judge accepted, and provides a run path;
- standard report records at least 95/100 exact unique recoveries and target budgets, unless an explicit approved revision is present;
- fault-free report has no false exact recovery;
- benchmark report includes baselines and uncertainty/failure counts;
- reduced-witness report includes a minimized witness for every enabled relation family;
- release manifest hashes current generated public artifacts;
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
- M1 language/architecture evidence: `VALIDATION.md`, `tests/fixtures/programs/`, and `docs/DSL_AND_ARCHITECTURE.md`, 2026-07-15; all milestone-specific tests pass, and M5 closes the previously deferred real tutorial gate.
- M2 target/challenge evidence: `VALIDATION.md`, `tests/fixtures/model/`, `tests/fixtures/challenge/`, and `docs/SYSTEM_A_SPHINX_VM.md`, 2026-07-15; 44 Rust and 68 Python tests cover the semantic split, live fault confinement, deterministic replay, permissions, and judge policy.
- M3 relation/extractor evidence: `VALIDATION.md`, `tests/python/test_certified_relations.py`, `tests/python/test_constraint_ir.py`, `tests/fixtures/relations/`, and `docs/RELATION_ORACLES.md`, 2026-07-16; 99 Python tests include every stateless relation, all bounded noise/fault generators, strict certificate/IR persistence, and live Rust relation arms.
- Certificate proof-bundle binding repair:
  `python/sphinx_interrogator/proof_artifacts/relation-contracts-v1.json`,
  `python/sphinx_interrogator/certificates.py`, and
  `tests/python/test_certified_relations.py`, 2026-07-16; proof artifact SHA-256
  `24e7b87fbf8d1a0122e701bcfc5ff813b4da860942f9a83505c37be93b80765b`; focused
  relation/certificate tests pass 30/30, reject stale supporting artifact hashes, and
  include wrong-symbolic-model plus broken-normalizer mutation regressions.
- M4 persistence/solver evidence: `VALIDATION.md`, `docs/CAMPAIGN_PERSISTENCE.md`, `tests/python/test_persistence.py`, `test_harness.py`, `test_hypothesis_persistence.py`, `test_frontier.py`, `test_solver.py`, and `test_symbolic_solver_model.py`, 2026-07-16; 125 Python tests cover real/fake write-ahead, replay, provenance, Z3 exactness, rollback, and CLI inspection.
- M5 tutorial acceptance report: `runs/tutorial-evaluation-v2/summary.json`, `runs/tutorial-demo-v2-seed-7/report.json`, `docs/TUTORIAL_RECOVERY.md`, and `VALIDATION.md`, 2026-07-16; 100/100 reference seeds are exact and judge accepted at 16 logical families.
- M6 synthesis evidence: `python/sphinx_interrogator/synthesis.py`, `tests/python/test_synthesis.py`, `tests/python/test_protocol_process.py`, `docs/PROGRAM_SYNTHESIS.md`, and `VALIDATION.md`, 2026-07-16; known-optimum, refinement, no-discriminator, unknown, margin, cache/frontier, exhaustive differential, live-process, and 20-seed random-hole calibration all pass.
- M7 standard full-system report: `runs/standard-benchmark-v1/standard-benchmark-report.json`, 2026-07-16; 600 campaigns passed, full/reference exact rate 1.0, median 40 logical families, p95 48, median 80 physical executions, and targets_met true.
- Baseline/ablation report: `runs/standard-benchmark-v1/standard-benchmark-report.json`, 2026-07-16; all four reference baselines also reached 100/100 exact, so the frozen standard profile shows robustness but not a large selector gap.
- M5 fault-free control report: `runs/tutorial-fault-free-v2/summary.json`, 2026-07-16; 100/100 blind off-fault campaigns are `candidate_set` public results with zero judge submissions.
- One-shot leakage audit: `runs/standard-profile-audit-m7/standard-profile-audit.json`, 2026-07-16; max public one-shot partition is 1.5 bits, median useful partition is 1.5 bits, oracle collision bound is 16 logical relations, and blind scan worst-case is 64.
- Mutation ladder: M2 off/reference/weak/signed unit and live confinement evidence in `VALIDATION.md`; M7 one-seed campaign ladder in `runs/standard-mutation-ladder-smoke-m7/standard-benchmark-report.json` confirms active variants recover and `runs/standard-profile-audit-m7/standard-profile-audit.json` records the active-variant latent equivalence under drained repeats.
- M8 state-learning report: `runs/state-learning-m8/state-learning-report.json`,
  2026-07-16; real research SphinxVM evaluation over 126 held-out words reports
  no-learner 0.246, exact-history 1.0, and learned-state 1.0; the regenerated report
  records `state_conditioned_inference.status=complete`, one non-trivial
  effective-nibble constraint, and `shared_private_root=false`; file SHA-256
  `ce5b2daecf11499e3d1465200ecf04abd77a906927f3bb337f855ebaa354eef1`.
- Formal/TLA+/SMT report: `just verify-formal`, 2026-07-16; Z3 relation contracts returned `unsat` x3, TLC generated 70,557 states with 2,276 distinct states and no invariant violation, and the 131,072-cell guarded-replay mutation self-test was rejected.
- Boundary-audit report: `just boundary-audit`, 2026-07-16; recursive protocol
  validation and separate-UID/FD-broker isolation passed with binary SHA-256
  `c094fff9561f0997dd8c307940dba991b80c920792c07095113f979d430da6cd`.
- Minimized witness collection:
  `runs/reduced-witnesses-m9/reduced-witnesses-report.json`, 2026-07-16; measured
  candidates are present, all 10 families are minimized, accepted steps form
  continuous parent paths, and measured replay honors each relation reset policy; file
  SHA-256 `a924448f71b27708c35945b5a64bff33f5ffd1394ca84cd700f052c12d95aa56`.
- Standard benchmark v2 full matrix:
  `runs/standard-benchmark-v2/standard-benchmark-report.json`, 2026-07-16; report
  v1.1 contains paired seed-level bootstrap confidence intervals and complete B0-B7
  surface evidence for the full 100-seed / 700-campaign matrix; full/reference,
  random, stateless, KB-no-synthesis, and synthesis-no-KB each reached 100/100 exact;
  B0 random final guess remained 0/100 exact; fault-off produced 0 false exact
  declarations; `full_published_matrix=true`; `targets_met=true`; file SHA-256
  `55e571cdeaea5f904e1d9c6cd79071c53a2539507dd3c7b73d24eb02d8456480`.
- Tutorial demo v3: `runs/tutorial-demo-v3/report.json`, 2026-07-16; `unique_exact`, judge accepted, 16 logical relation families, file SHA-256 `ad02a85d07f5de69547a7bb1870fe2caa04031e56b482e4fda726b520d63cf5b`; manifest v1.2 SHA-256 `8a77bcbbd91764261c402976cf5c7924bfd0bd6f72de550d54f0e3664b7a4950`.
- Evaluation CSV/plot artifacts:
  `runs/release-m9/evaluation-artifacts/evaluation-artifacts-manifest.json`,
  2026-07-16; public CSV rows cover 700 campaigns, 52,928 query executions, 26,464
  relation decisions, 13 state-learning rows, and 10 reducer-family rows; deterministic
  SVG plots cover exact rates, median logical cost, state-learning accuracy, and
  reducer steps; file SHA-256
  `c7ff125818abd7b8d0a895a897a994638b54cc5c5c32086fe73f0ca1cf8ba367`.
- Release manifest/revision: `runs/release-m9/release-manifest.json`, 2026-07-16;
  five aggregate files are hashed and release checks are fail-closed. Current
  `status=blocked`, `semantic_checks_pass=false`, `validation_gates_pass=true`,
  one release check fails (`repository.clean`), and all 12 root gates have passing
  evidence; file SHA-256
  `056de5eb4a0ef4208ed0b6dd05d59bc8c1f855217acc7f5073520dd961314042`.
- Campaign manifest v1.2 reproducibility repair, 2026-07-16:
  `python/sphinx_interrogator/persistence.py`, `tutorial.py`, `standard.py`,
  `scripts/benchmark_standard.py`, `spec/campaign-manifest.schema.json`, and focused
  tests. `just test` passed with 46 Rust tests and 179 Python tests; all 700 standard
  benchmark run manifests are v1.2 and include artifact hashes.
- Task-spec gap audit and public lifecycle documentation repair, 2026-07-16:
  README, `docs/PROTOCOL.md`, `docs/REPOSITORY_GUIDE.md`, `VALIDATION.md`,
  `agent/STATUS.md`, and this ExecPlan were updated after confirming remaining
  blockers. `git diff --check`, `PATH=/tmp/sphinx-just/bin:$PATH just docs-check`,
  and `PATH=/tmp/sphinx-just/bin:$PATH just schema-check` passed.
- Acceptance/release-gate repair validation, 2026-07-16: `just fmt`, `just lint`,
  `just test` (Rust 46 tests, Python 175 tests), `just schema-check`, `just
  docs-check`,
  `just verify-formal`, `just demo-tutorial`, `just boundary-audit`,
  `just evaluate-state-learning`, and `just reduce-witnesses` passed as commands.
  At that checkpoint the standard artifact was still a one-seed selected matrix; it
  has since been superseded by the full standard benchmark rerun below.
- Release-manifest/benchmark-CI repair tests, 2026-07-16: `uv run --frozen pytest
  tests/python/test_standard_benchmark.py tests/python/test_release_manifest.py`
  passed 6 tests; `git diff --check` passed;
  `PATH=/tmp/sphinx-just/bin:$PATH just release-manifest` failed closed with
  `status=blocked`, not from an output-path error.
- Full standard benchmark rerun, 2026-07-16:
  `PATH=/tmp/sphinx-just/bin:$PATH just benchmark-standard` passed with 100 seeds /
  700 campaigns, `full_published_matrix=true`, `targets_met=true`, and report SHA-256
  `55e571cdeaea5f904e1d9c6cd79071c53a2539507dd3c7b73d24eb02d8456480`.
- M8/M9 semantic artifact repair, 2026-07-16:
  `PATH=/tmp/sphinx-just/bin:$PATH just evaluate-state-learning` and
  `PATH=/tmp/sphinx-just/bin:$PATH just reduce-witnesses` passed. The release manifest
  now passes `m8.state_conditioned_secret_inference`,
  `m9.reducer_replay_paths_valid`, and `m9.reducer_reset_policy_honored`. Final
  root checks after this repair passed `just test` with 46 Rust tests and 176 Python
  tests, and `git diff --check` passed.
- Validation-gate evidence recorder, 2026-07-16:
  `scripts/record_validation_gate.py`, `justfile`, and
  `tests/python/test_validation_evidence.py`; focused release-manifest/recorder tests
  pass 4/4. `just release-manifest` now reads
  `runs/release-m9/validation-evidence.json`; all 12 root gates have now been rerun
  through the recorder and pass. The generated manifest completes from a clean tree.
- Post-full-benchmark root checks, 2026-07-16: `just fmt`, `just lint`, `just test`,
  `just schema-check`, `just docs-check`, and `git diff --check` passed; `just test`
  covered 46 Rust tests and 175 Python tests.
- Historical clean-checkout negative evidence, 2026-07-16: before the bootstrap
  repair, a detached HEAD with no `.tools/` failed formal verification. The current
  justfile and CI workflow fetch and verify the pinned TLC jar; remote `main` CI now
  passes after moving the pinned TLC bootstrap before Python formal tests.
- Historical acceptance negative reproductions, 2026-07-16: before the repairs above,
  release manifest reported complete over a failed/incomplete benchmark; absolute
  manifest output wrote then crashed; M8's state-dependent expression was literal
  `true`; and reducer step arrays failed sequential replay in 9 of 10 families.

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

Current outcome: the tutorial flow, fault-free controls, standard recovery,
persistence/replay, solver/synthesis components, learner components, and reducer are
substantial and testable. The repaired challenge boundary passes direct adversarial
isolation tests; the current standard matrix passes; and M8/M9 semantic artifact
checks now pass with non-trivial state-conditioned inference and replayable reducer
paths. Campaign manifests for tutorial and the full standard benchmark matrix now
record v1.2 runtime reproducibility metadata and artifact hashes. The repository is
nevertheless not release-complete: formal/differential obligations,
documentation/version, expanded clean-CI release smoke, and release-tag evidence remain
partial. The generated release manifest has passing root-gate evidence and completes
from a clean tree. Work resumes from the open P1/P2 items above.
```
