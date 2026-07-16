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
- Regenerate M8/M9 artifacts with non-trivial learned-state effective-nibble
  constraints, independent M8 campaign private roots, continuous reducer parent paths,
  and reset-policy-aware measured replay.
