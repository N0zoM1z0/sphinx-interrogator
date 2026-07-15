# Changelog

All notable changes should be recorded here after implementation begins.

## Unreleased

- Initial design package, executable scaffold, formal specifications, and Codex implementation plan.
- Complete M0 reproducible bootstrap with Rust/Python lockfiles and fail-closed checks.
- Harden the JSONL transport with bounded lines, identifier/session/reset/query budgets,
  explicit capabilities and semantic versions, correlated client responses, and timeouts.
- Add live cross-language schema tests and an initial black-box boundary audit.
