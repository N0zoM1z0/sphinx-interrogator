# Review checklist

## Product behavior

- [x] The implemented behavior matches `agent/CODEX_TASK_SPEC.md` rather than only the scaffold.
- [x] A clean tutorial challenge can be created, served, recovered, judged, replayed, and reported.
- [x] Standard benchmark targets are evaluated on published seeds.
- [x] Unresolved/soft results are not mislabeled as exact unique recovery.

## Black-box boundary

- [x] System B launches/uses System A only through the public protocol.
- [x] Python imports contain no Rust target/private challenge access.
- [x] Private paths/environment are sanitized and permission-tested.
- [x] Release server has no protocol-switchable diagnostics.
- [x] Transcript scan finds no secret, bank, phase, replay, or exact-cycle internals.
- [x] Final judge is rate-limited and returns no incremental information.

## Semantics and formal soundness

- [x] Architectural, fault-free, and faulty semantics are separate types/modules.
- [x] Architectural output is secret-independent in exhaustive reduced/property tests.
- [x] Fault changes only microarchitectural observation/state.
- [x] Reset and termination invariants are tested/formally checked.
- [x] Rust concrete and Python symbolic bank/fault/state functions agree exhaustively on reduced domains.

## Relations

- [x] Every enabled template has versioned precondition and certificates.
- [x] Architectural and fault-free relations are independently checked.
- [x] Exact/bounded extractors include nuisance and latent-state assumptions.
- [x] True secrets satisfy generated hard constraints in tests.
- [x] Inconclusive results emit no hard assertion.
- [x] Composition and reduction preserve declared obligations.

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
- [x] Every result links to profile, challenge commitment, seed, revision, and evidence.

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
- [x] Held-out sequence accuracy is reported.

## Tests and quality

- [x] `just fmt` passes.
- [x] `just lint` passes.
- [x] `just test` passes.
- [x] `just schema-check` passes.
- [x] `just verify-formal` passes with required tools.
- [x] Boundary audit passes.
- [x] Tests include failure paths and mutation controls.
- [x] No unseeded randomness, `unwrap`/`expect`, broad exception swallowing, or unbounded solver call remains.

## Evaluation and documentation

- [x] Fault-free and mutation controls are included.
- [x] Baselines use identical challenge sets/budgets.
- [x] Calibration and evaluation seeds are separate.
- [x] Reports distinguish targets, measured results, approximations, and failures.
- [x] References and public schemas are current.
- [x] Ethics/synthetic-only scope remains explicit.
- [x] Active ExecPlan and `agent/STATUS.md` reflect actual final evidence.

## Review notes

- Final release gates passed locally on 2026-07-16: `just fmt`, `just lint`,
  `just test`, `just schema-check`, `just docs-check`, `just verify-formal`,
  `just demo-tutorial`, `just boundary-audit`, `just benchmark-standard`,
  `just evaluate-state-learning`, `just reduce-witnesses`, and
  `just release-manifest`.
- The only broad `BaseException` matches are atomic write cleanup paths that re-raise;
  they do not swallow failures.
- The standard profile caveat remains explicit: all published reference selector
  baselines recover the frozen standard profile, so the release does not claim a large
  selector gap for that profile.
- `runs/release-m9/release-manifest.json` is generated and ignored by design. Rerun
  `just release-manifest` after the final commit to capture the committed HEAD.
