# Release notes

## v1.0 blocked release candidate

This repository contains substantial executable SphinxVM/Interrogator functionality,
but the current evidence does not yet satisfy `agent/CODEX_TASK_SPEC.md` through M9.
Do not tag this state as research-complete.

Measured release evidence is generated, not hand-edited:

- tutorial recovery: `just demo-tutorial`;
- standard benchmark and baselines: `just benchmark-standard`;
- state-learning evaluation: `just evaluate-state-learning`;
- minimized relation witnesses: `just reduce-witnesses`;
- public evaluation CSVs and plots: `just export-evaluation-artifacts`;
- release artifact manifest: `just release-manifest`.

The M9 reducer report is written to
`runs/reduced-witnesses-m9/reduced-witnesses-report.json`. It contains one minimized
witness for each enabled core relation family. A candidate is accepted only when it
preserves the finite public-model predicate and measured public VM replay
decision/confidence/provenance. It does not use the hidden challenge secret.

The release manifest is written to `runs/release-m9/release-manifest.json` and records
manifest v2 status, artifact hashes, repository revision, dirty status, tool versions,
command line, start/end timestamps, semantic release checks, and validation-gate
evidence slots. The manifest is fail-closed: `just release-manifest` exits nonzero
until repository-cleanliness and semantic evidence pass. From clean
`main`, the manifest completes with all semantic checks and all 12 root-gate evidence
records passing.

Current benchmark evidence: `just benchmark-standard` has been rerun on the current
code and produced the full 100-seed / 700-campaign v2 standard report with
`targets_met=true`. Current M8/M9 semantic evidence has also been regenerated: M8
records a non-trivial learned-state effective-nibble constraint, and M9 records
continuous reducer parent paths with reset-policy-aware replay. Public CSV/plot
release artifacts are generated under `runs/release-m9/evaluation-artifacts/`.
The standard-profile audit now reports mutation aggregate controls with `off=0`,
`weak=1`, `signed=1`, and `reference=2`. The CI workflow now includes clean
release-smoke coverage for tutorial, standard smoke, M8, reducer, evaluation artifact
export, and release-manifest packaging. Current release blockers are final
documentation/version/changelog alignment and the absence of a release tag.
