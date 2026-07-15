# Review checklist

## Product behavior

- [ ] The implemented behavior matches `agent/CODEX_TASK_SPEC.md` rather than only the scaffold.
- [ ] A clean tutorial challenge can be created, served, recovered, judged, replayed, and reported.
- [ ] Standard benchmark targets are evaluated on published seeds.
- [ ] Unresolved/soft results are not mislabeled as exact unique recovery.

## Black-box boundary

- [ ] System B launches/uses System A only through the public protocol.
- [ ] Python imports contain no Rust target/private challenge access.
- [ ] Private paths/environment are sanitized and permission-tested.
- [ ] Release server has no protocol-switchable diagnostics.
- [ ] Transcript scan finds no secret, bank, phase, replay, or exact-cycle internals.
- [ ] Final judge is rate-limited and returns no incremental information.

## Semantics and formal soundness

- [ ] Architectural, fault-free, and faulty semantics are separate types/modules.
- [ ] Architectural output is secret-independent in exhaustive reduced/property tests.
- [ ] Fault changes only microarchitectural observation/state.
- [ ] Reset and termination invariants are tested/formally checked.
- [ ] Rust concrete and Python symbolic bank/fault/state functions agree exhaustively on reduced domains.

## Relations

- [ ] Every enabled template has versioned precondition and certificates.
- [ ] Architectural and fault-free relations are independently checked.
- [ ] Exact/bounded extractors include nuisance and latent-state assumptions.
- [ ] True secrets satisfy generated hard constraints in tests.
- [ ] Inconclusive results emit no hard assertion.
- [ ] Composition and reduction preserve declared obligations.

## Solver and synthesis

- [ ] Solver timeouts propagate as `unknown`.
- [ ] Constraint provenance is complete and serializable.
- [ ] Exact uniqueness uses an alternative-model unsat check.
- [ ] Model committees are labeled as proxies, not uniform samples.
- [ ] CEGIS has tests requiring counterexample refinement.
- [ ] Query objectives include margin/cost and deterministic tie-breaking.
- [ ] Fault-free profile predictions are secret-independent.

## Knowledge base and campaigns

- [ ] Raw protocol records persist before derived analysis.
- [ ] KB has semantic/structural/state diversity and TTL behavior.
- [ ] Replay is deterministic where promised.
- [ ] Unsat-core repair/quarantine is tested.
- [ ] Every result links to profile, challenge commitment, seed, revision, and evidence.

## Noise/statistics

- [ ] Exact, bounded, and stochastic modes are distinct.
- [ ] Paired order and correlation groups are recorded.
- [ ] Stopping rules are predeclared and tested.
- [ ] Equal and inconclusive are not conflated.
- [ ] Soft weights are capped/calibrated and grouped by logical evidence.
- [ ] Statistical simulations report false-positive/inconclusive behavior.

## State learning

- [ ] A one-state hard-reset mode works without AALpy.
- [ ] Macro input/output abstractions are versioned.
- [ ] Equivalence testing is a portfolio with recorded budget.
- [ ] Counterexamples invalidate/retract dependent constraints.
- [ ] Held-out sequence accuracy is reported.

## Tests and quality

- [ ] `just fmt` passes.
- [ ] `just lint` passes.
- [ ] `just test` passes.
- [ ] `just schema-check` passes.
- [ ] `just verify-formal` passes with required tools.
- [ ] Boundary audit passes.
- [ ] Tests include failure paths and mutation controls.
- [ ] No unseeded randomness, `unwrap`/`expect`, broad exception swallowing, or unbounded solver call remains.

## Evaluation and documentation

- [ ] Fault-free and mutation controls are included.
- [ ] Baselines use identical challenge sets/budgets.
- [ ] Calibration and evaluation seeds are separate.
- [ ] Reports distinguish targets, measured results, approximations, and failures.
- [ ] References and public schemas are current.
- [ ] Ethics/synthetic-only scope remains explicit.
- [ ] Active ExecPlan and `agent/STATUS.md` reflect actual final evidence.
