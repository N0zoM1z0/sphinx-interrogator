# Implementation status

This file is the concise project checkpoint. The active ExecPlan contains the detailed history.

## Overall state

- **Specification/design package:** complete.
- **Executable system:** substantial and locally testable, but not yet compliant with
  every acceptance criterion in `agent/CODEX_TASK_SPEC.md`.
- **Verified repair:** the challenge private-root split, generic public identifiers,
  public-directory/FD-broker launch, distinct-UID isolation, recursive response
  validation, alternative-model exactness guard, and relation proof-bundle content
  binding are implemented and tested.
- **Current active plan:** `agent/plans/0001-full-system.md`.
- **Last updated:** 2026-07-16 16:24Z after adding release-bound evaluation CSV/plot
  artifacts.

## Current milestone

The P0 benchmark gate and the M8/M9 release-manifest semantic artifact gates now pass.
Root-gate evidence is now recorded for all 12 expected commands, and the tutorial plus
all 700 standard benchmark campaign run directories have manifest v1.2 with runtime
metadata and artifact hashes. Tutorial, standard, and B0 reports now use normative
public result statuses; the regenerated standard benchmark has 500 `unique_exact`
rows and 200 `candidate_set` rows. Adversarial mutation regressions now cover a
contradictory symbolic model and a broken static-cost normalizer. Release-bound CSV
and SVG artifacts now cover campaign, query, relation, state-learning, and reducer
evidence. Release remains blocked by a dirty working tree and broader P1/P2 proof,
documentation, and CI obligations. No v1.0 or research-complete release should be
created from the current evidence.

## Verification dashboard

| Check | Last result | Evidence |
|---|---|---|
| `just fmt`, `just lint`, `just test` | pass | Recorded via `record-validation-gate`; Rust 46 tests and Python 179 tests pass |
| `just schema-check`, `just docs-check` | pass | Current fixtures, release-manifest schema, and links pass their implemented checks |
| `just verify-formal` | pass, scope incomplete | Z3 `unsat` x3; TLC 70,557 generated/2,276 distinct; 131,072 guarded-replay cells |
| `just boundary-audit` | pass | Recursive schema checks and separate-UID/FD-broker isolation; binary SHA-256 `c094fff9561f0997dd8c307940dba991b80c920792c07095113f979d430da6cd` |
| `just demo-tutorial` | pass | `unique_exact`, judge accepted, 16 logical families; `runs/tutorial-demo-v3` |
| standard benchmark v2 | pass | Report v1.1 covers 100 seeds / 700 campaigns with paired bootstrap CI, complete B0-B7 surface, `full_published_matrix=true`, `targets_met=true`, full/reference 100/100 exact, fault-off 0 false exact, and normative result statuses only |
| `just evaluate-state-learning` | pass | Real research VM comparison plus one non-trivial learned-state effective-nibble constraint; independent campaign private roots; retraction demo still passes |
| `just reduce-witnesses` | pass | Reports 10 minimized families with continuous accepted parent paths and reset-policy-aware measured replay |
| release manifest v2 | blocked as intended | `just release-manifest` exits 1 with `--require-complete`; current manifest reads `runs/release-m9/validation-evidence.json`, records all 12 validation gates as pass, and reports only `repository.clean` failed |
| GitHub CI | no evidence | Remote has no branch heads and `gh run list` returns no runs |

## Release blockers

### P0

- Keep the release manifest fail-closed through the final clean-tree release
  candidate. Root-gate evidence is now recorded through `record-validation-gate`, but
  the manifest must be regenerated after the working tree is committed or otherwise
  made clean.
- Keep the repaired full standard benchmark artifact as the current P0 benchmark
  evidence; the legacy 600-campaign v1 report cannot validate current code.

### P1

- Implement the missing architectural, reset, gas/progress, normalized-cost,
  exact-cycle, and extractor differential obligations. Relation certificate proof
  bundles now fail closed if claimed proof/test/semantic artifact contents change.
- Finish the remaining integrated campaign-controller mode surface. Campaign manifest
  v1.2 and tutorial/standard/B0 reports now record normative result statuses,
  revision, dirty state, versions, command, timing, and artifact hashes for tutorial
  and all 700 standard benchmark runs.

### P2

- Finish full documentation/version alignment. README, protocol, and repository-guide
  local CLI examples now match the repaired private-root and socket/FD interfaces,
  but release notes, changelog/versioning, generated result schemas, and examples still
  need a final release consistency pass.
- Add clean-CI smoke coverage for tutorial, standard, M8, reducer, and release
  packaging; current remote CI has never run.

## Current release artifacts

- `runs/standard-benchmark-v2/standard-benchmark-report.json`: full 100-seed,
  700-campaign v2 benchmark with paired bootstrap CI and complete B0-B7 surface;
  `full_published_matrix=true`, `targets_met=true`, SHA-256
  `55e571cdeaea5f904e1d9c6cd79071c53a2539507dd3c7b73d24eb02d8456480`.
- `runs/tutorial-demo-v3/report.json`: fresh tutorial demo, SHA-256
  `ad02a85d07f5de69547a7bb1870fe2caa04031e56b482e4fda726b520d63cf5b`; companion
  manifest v1.2 SHA-256
  `8a77bcbbd91764261c402976cf5c7924bfd0bd6f72de550d54f0e3664b7a4950`.
- `runs/state-learning-m8/state-learning-report.json`: real research state-learning
  measurements plus one learned-state-conditioned effective-nibble constraint;
  `state_conditioned_inference.status=complete`, `nontrivial_constraints=1`, SHA-256
  `ce5b2daecf11499e3d1465200ecf04abd77a906927f3bb337f855ebaa354eef1`.
- `runs/reduced-witnesses-m9/reduced-witnesses-report.json`: measured replay reducer
  report; `all_minimized=true`, `all_replay_paths_valid=true`, and
  `reset_policy_honored=true`, SHA-256
  `a924448f71b27708c35945b5a64bff33f5ffd1394ca84cd700f052c12d95aa56`.
- `runs/release-m9/evaluation-artifacts/evaluation-artifacts-manifest.json`: public
  CSV/SVG artifact manifest; row counts are 700 campaign rows, 52,928 query rows,
  26,464 relation rows, 13 state rows, and 10 reducer-family rows, SHA-256
  `c7ff125818abd7b8d0a895a897a994638b54cc5c5c32086fe73f0ca1cf8ba367`.
- `runs/release-m9/release-manifest.json`: generated manifest v2; current
  `status=blocked`, `semantic_checks_pass=false`, and
  `validation_gates_pass=true`. The standard benchmark, tutorial, M8, M9, evaluation
  artifacts, and all 12 validation gate checks now pass; the only failed release
  check is `repository.clean`. File SHA-256
  `056de5eb4a0ef4208ed0b6dd05d59bc8c1f855217acc7f5073520dd961314042`.

## Decision summary

- System B remains black-box: it consumes public schemas, public challenge metadata,
  public VM sockets, and public observations only.
- Trusted local orchestration lives outside the `sphinx_interrogator` package and is
  responsible for private-root creation and FD-brokered VM launch.
- Exact uniqueness still requires an explicit alternative-model unsat query; `unknown`
  never means unique.
- Script success, schema validity, and artifact presence are not substitutes for the
  task specification's semantic acceptance criteria.
- Legacy generated evidence may be retained for history, but it cannot close a
  milestone after security, schema, or methodology changes.
- Release manifests are generated ignored artifacts under `runs/`; tracked source
  contains the generator, schemas, fixtures, and status evidence.
