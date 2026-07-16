# Changelog

All notable changes should be recorded here after implementation begins.

## Unreleased

- Initial design package, executable scaffold, formal specifications, and Codex implementation plan.
- Complete M0 reproducible bootstrap with Rust/Python lockfiles and fail-closed checks.
- Harden the JSONL transport with bounded lines, identifier/session/reset/query budgets,
  explicit capabilities and semantic versions, correlated client responses, and timeouts.
- Add live cross-language schema tests and an initial black-box boundary audit.
- Repair challenge security, recursive protocol validation, artifact-bound certificate
  enforcement, benchmark v2 ablations, real research-profile state learning,
  measured-replay witness reduction, formal bootstrap, and release manifest v2.
- Make release manifest v2 fail closed on semantic artifact checks, root-gate
  evidence, dirty tracked state, and incomplete M8/M9/release acceptance; absolute
  `--output` paths now write and print correctly, and root-gate evidence is recorded
  through `record-validation-gate`.
- Add standard benchmark report v1.1 with paired seed-level bootstrap intervals and a
  machine-readable B0-B7 surface, including a real no-query random-final-guess
  baseline and development-only upper-bound artifact linkage.
- Regenerate the current-code standard benchmark v2 full matrix: 100 seeds / 700
  campaigns, `targets_met=true`, complete B0-B7 evidence, and zero fault-off false
  exact declarations.
- Add the certified `drained-anchor-switch/v1` relation and connect it to standard
  CEGIS selection. The refreshed full benchmark now recovers 100/100 reference
  challenges with median/p95 28/33 logical families and shows paired cost
  improvements over B1-B3 while remaining tied with B4 synthesis-without-KB.
- Regenerate M8/M9 artifacts with non-trivial learned-state effective-nibble
  constraints, 98 independent M8 research challenge campaigns without a shared
  private root, 11 minimized reducer families, continuous reducer parent paths, and
  reset-policy-aware measured replay.
- Add a public `CampaignController` facade and `sphinx-interrogate controller-plan`
  CLI for the integrated infer, learn-state, calibrate, replay, reduce, and diversify
  selector modes.
- Add live Rust/Python exact-cycle differential coverage, relation extractor
  finite-model differential checks, and expanded formal reset, architectural
  confinement, gas/progress, and normalized-cost invariants.
- Extend the standard-profile audit to report mutation aggregate controls
  `off=0`, `weak=1`, `signed=1`, and `reference=2`, while preserving the documented
  drained-repeat active-variant equivalence.
- Add a clean GitHub Actions `release-smoke` job covering tutorial recovery,
  standard benchmark smoke, M8 state learning, M9 reducer smoke, evaluation artifact
  export, and release-manifest packaging; standard and reducer smoke commands now
  support short `--socket-root` runtime directories for long CI checkout paths.
