# Release notes

## v1.0 research-complete candidate

This repository now implements the synthetic SphinxVM/Interrogator system described in
`agent/CODEX_TASK_SPEC.md` through M9.

Measured release evidence is generated, not hand-edited:

- tutorial recovery: `just demo-tutorial`;
- standard benchmark and baselines: `just benchmark-standard`;
- state-learning evaluation: `just evaluate-state-learning`;
- minimized relation witnesses: `just reduce-witnesses`;
- release artifact manifest: `just release-manifest`.

The M9 reducer report is written to
`runs/reduced-witnesses-m9/reduced-witnesses-report.json`. It contains one minimized
witness for each enabled core relation family and labels preservation as a bounded
public-model implication over a finite committee. It does not use the hidden challenge
secret.

The release manifest is written to `runs/release-m9/release-manifest.json` and records
artifact hashes, repository revision, dirty status, and tool/environment metadata.

Known caveat: the frozen standard profile is recoverable by all published selector
baselines. The report therefore demonstrates robust exact recovery and boundary safety,
but not a large selector-performance gap for that profile.
