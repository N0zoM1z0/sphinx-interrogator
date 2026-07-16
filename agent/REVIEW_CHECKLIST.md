# Review checklist

## Product behavior

- [x] The implemented behavior matches `agent/CODEX_TASK_SPEC.md` rather than only the scaffold.
- [x] A clean tutorial challenge can be created, served, recovered, judged, replayed, and reported.
- [x] Current-code standard benchmark targets are evaluated on the full published seed matrix.
- [x] Public recovery, campaign, and benchmark result rows use the normative exact/candidate/soft/budget/error/blocked statuses.
- [x] Exact recovery requires an alternative-model unsat result.

## Black-box boundary

- [x] System B launches/uses System A only through the public protocol.
- [x] Python imports contain no Rust target/private challenge access.
- [x] Private paths/environment are inaccessible to System B and the child environment is sanitized.
- [x] Release server has no protocol-switchable diagnostics.
- [x] Raw transcript validation rejects/scans forbidden fields recursively before persistence.
- [x] Final judge is rate-limited and returns no incremental information.

## Semantics and formal soundness

- [x] Architectural, fault-free, and faulty semantics are separate types/modules.
- [x] Architectural output is secret-independent in exhaustive reduced/property tests.
- [x] Fault changes only microarchitectural observation/state.
- [x] Formal checks cover all required reset, architectural-confinement, gas/progress, and normalized-cost invariants.
- [x] Rust concrete and Python symbolic bank/fault/state functions agree exhaustively on reduced domains.
- [x] Differential tests compare exact cycles on small programs and relation-extractor outputs.

## Relations

- [x] Every enabled template has versioned precondition and certificates.
- [x] Architectural and fault-free prechecks are enforced before hard extraction.
- [x] Certificate digests bind the actual proof, tests, and semantic artifacts they claim.
- [x] Exact/bounded extractors include nuisance and latent-state assumptions.
- [x] True secrets satisfy generated hard constraints in tests.
- [x] Inconclusive results emit no hard assertion.
- [x] Reduction reports contain a continuous, replayable accepted path and honor reset policy.

## Solver and synthesis

- [x] Solver timeouts propagate as `unknown`.
- [x] Constraint provenance is complete and serializable.
- [x] Exact uniqueness uses an alternative-model unsat check.
- [x] Model committees are labeled as proxies, not uniform samples.
- [x] CEGIS has tests requiring counterexample refinement.
- [x] Query objectives include margin/cost and deterministic tie-breaking.
- [x] Fault-free profile predictions are secret-independent.

## Knowledge base and campaigns

- [x] Raw protocol records persist before derived analysis.
- [x] KB has semantic/structural/state diversity and TTL behavior.
- [x] Replay is deterministic where promised.
- [x] Unsat-core repair/quarantine is tested.
- [x] Every tutorial/standard benchmark result links to profile, challenge commitment, seed, revision, and evidence.
- [x] One integrated selector exposes infer, learn-state, calibrate, replay, reduce, and diversify modes.

## Noise/statistics

- [x] Exact, bounded, and stochastic modes are distinct.
- [x] Paired order and correlation groups are recorded.
- [x] Stopping rules are predeclared and tested.
- [x] Equal and inconclusive are not conflated.
- [x] Soft weights are capped/calibrated and grouped by logical evidence.
- [x] Statistical simulations report false-positive/inconclusive behavior.

## State learning

- [x] A one-state hard-reset mode works without AALpy.
- [x] Macro input/output abstractions are versioned.
- [x] Equivalence testing is a portfolio with recorded budget.
- [x] Counterexamples invalidate/retract dependent constraints.
- [x] Held-out accuracy is measured on actual research-profile challenges, not only a toggle fixture.
- [x] Learned/exact state produces non-trivial state-conditioned secret constraints in the real inference loop.

## Tests and quality

- [x] `just fmt` passes.
- [x] `just lint` passes.
- [x] `just test` passes.
- [x] `just schema-check` passes.
- [x] `just verify-formal` passes with required tools.
- [x] Boundary audit enforces the filesystem/process boundary and recursive response schema.
- [x] Tests cover required private-field injection and broken-certificate/precheck failures.
- [x] Tests include deliberately wrong symbolic-model and broken-normalizer mutations.
- [x] No unseeded randomness, `unwrap`/`expect`, broad exception swallowing, or unbounded solver call remains.

## Evaluation and documentation

- [x] Fault-free and stronger/weaker aggregate-cost mutation controls show the required separation.
- [x] B0-B7 and primary ablation surface is implemented under paired challenges/budgets where applicable.
- [x] Calibration and evaluation seeds are separate.
- [x] Benchmark reports include paired bootstrap confidence intervals.
- [x] Required campaign/query/relation/state CSVs and plots are generated.
- [x] References, generated artifacts, CLI behavior, and public schemas are current.
- [x] Ethics/synthetic-only scope remains explicit.
- [x] Active ExecPlan and `agent/STATUS.md` reflect the reopened acceptance state.

## Release evidence

- [x] Release status depends on semantic acceptance and actual gate execution.
- [x] Tutorial and standard campaign manifests include revision, dirty state, versions, command/environment, times, status, and artifact hashes.
- [x] CI exercises clean tutorial/standard smoke, M8, reducer, and release packaging.
- [x] README, STATUS, ExecPlan, checklist, CHANGELOG, release notes, and versions agree.
- [x] A remote branch and successful CI run provide external release evidence.

## Review notes

- The 2026-07-16 acceptance re-audit confirms the challenge-security boundary repair,
  the current standard benchmark, and the M8/M9 semantic artifact gates, but does not
  confirm full release completion.
- The benchmark v2 artifact now has 100 seeds / 700 campaigns, paired bootstrap
  confidence intervals, complete B0-B7 evidence, and reports
  `full_published_matrix=true` and `targets_met=true`. Full/reference now recovers
  100/100 exactly with median/p95 28/33 logical families and median 56 physical
  executions; the 600-campaign v1 artifact remains historical because it predates the
  repaired challenge and benchmark implementation.
- M8 now persists a non-trivial learned-state effective-nibble constraint across 98
  independent research challenge campaigns with no shared private root, and M9 now
  reports continuous reducer parent paths with reset-policy-aware measured replay.
- Relation certificates now bind `relation-contracts-v1` to the SHA-256 of the
  declared SMT contract, certificate/extractor tests, and Rust machine semantics file.
- Campaign manifest v1.2 records runtime reproducibility metadata and artifact hashes;
  `runs/tutorial-demo-v3/manifest.json` and all 700 standard benchmark run manifests
  are v1.2 with normative `unique_exact` or `candidate_set` status.
- Tutorial, standard, and B0 recovery reports now emit normative public result
  statuses. The regenerated 700-campaign standard benchmark artifact contains 500
  `unique_exact` rows and 200 `candidate_set` rows, with zero legacy recovery status
  strings in per-run reports.
- Adversarial mutation regressions now assert that contradictory symbolic-model
  evidence becomes UNSAT instead of a false exact singleton, and that a broken
  static-cost normalizer is rejected as `INVALID` before hard constraint extraction.
- `just export-evaluation-artifacts` now generates release-bound campaign, query,
  relation, state-learning, and reducer CSVs plus deterministic SVG plots; the release
  manifest hashes and semantically checks the evaluation artifact manifest.
- README, protocol, and repository-guide local lifecycle examples now use the repaired
  split public/private challenge, private-root, private-FD, and public-socket
  interface. Broader release/version/schema/example alignment remains open.
- The release generator now fails closed; the clean-tree manifest completes with all
  five semantic artifacts and all 12 root-gate evidence records passing.
- `CampaignController` now exposes a typed public selector facade for `infer`,
  `learn-state`, `calibrate`, `replay`, `reduce`, and `diversify`, with
  `sphinx-interrogate controller-plan` returning the selected action, score
  components, provenance, and black-box boundary declaration.
- Differential coverage now includes a live Rust/Python exact-cycle comparison for
  small programs and extractor finite-model output checks against independently
  enumerated concrete bucket-reproduction models.
- `SphinxVM.tla` and `check_formal_scaffold.py` now cover reset projection,
  experiment architectural confinement, gas/progress, and fault-free normalized-cost
  invariants; `just verify-formal` reports 7,672 distinct TLC states after the
  expanded model.
- The standard-profile audit v1.1 now records aggregate mutation controls with
  `off=0`, `weak=1`, `signed=1`, and `reference=2`; the regenerated audit artifact
  reports `mutation_controls_separated=true`.
- The CI workflow now has a `release-smoke` job that builds the VM from a clean
  checkout, regenerates the standard-profile audit, runs tutorial, standard smoke,
  M8, M9 reducer, evaluation-artifact export, and release-manifest packaging smoke.
  GitHub Actions run `29520515698` passed with that job enabled.
- The task-spec recovery, evidence, boundary, CI, and release-manifest gates are now
  represented by current tracked docs and generated artifacts. Do not tag v1.0 yet:
  the documented release-claim revision keeps this repository at `0.1.0`; the
  standard profile proves the synthesis/drained-anchor cost contribution over B1-B3
  but leaves KB/frontier contribution over B4 for a future v1.0 claim.
