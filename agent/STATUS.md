# Implementation status

This file is the concise project checkpoint. The active ExecPlan contains the detailed history.

## Overall state

- **Specification/design package:** complete.
- **Executable system:** task-spec recovery, boundary, M8/M9, release-manifest, and
  CI evidence gates are implemented and locally testable. The repository remains
  versioned as `0.1.0`; v1.0/research-complete is intentionally not claimed.
- **Verified repair:** the challenge private-root split, generic public identifiers,
  public-directory/FD-broker launch, distinct-UID isolation, recursive response
  validation, alternative-model exactness guard, and relation proof-bundle content
  binding are implemented and tested.
- **Current active plan:** `agent/plans/0001-full-system.md`.
- **Last updated:** 2026-07-16 20:51Z after the M8 independent research-campaign
  gate repair and artifact regeneration.

## Current milestone

The P0 benchmark gate and the M8/M9 release-manifest semantic artifact gates now pass.
Root-gate evidence is now recorded for all 12 expected commands, and the tutorial plus
all 700 standard benchmark campaign run directories have manifest v1.2 with runtime
metadata and artifact hashes. Tutorial, standard, and B0 reports now use normative
public result statuses; the regenerated standard benchmark has 500 `unique_exact`
rows and 200 `candidate_set` rows. Adversarial mutation regressions now cover a
contradictory symbolic model and a broken static-cost normalizer. Release-bound CSV
and SVG artifacts now cover campaign, query, relation, state-learning, and reducer
evidence. The clean-tree release manifest now completes, and `main` has a successful
GitHub Actions CI run. The public `CampaignController` now exposes the required
`infer`, `learn-state`, `calibrate`, `replay`, `reduce`, and `diversify` modes.
Differential tests now compare live Rust exact cycles for small programs against the
independent Python model and compare extractor outputs against concrete bucket-model
enumeration. Formal checks now cover reset projection, architectural confinement,
gas/progress, and normalized-cost invariants. The standard-profile audit v1.1 now
records mutation aggregate controls with `off=0`, `weak=1`, `signed=1`, and
`reference=2` while preserving the documented drained-repeat active-variant
equivalence. The CI workflow now includes a clean `release-smoke` job covering
tutorial, standard smoke, M8, M9 reducer, evaluation artifact export, and
release-manifest packaging smoke; standard and reducer smoke commands use short
`/tmp` socket roots to avoid GitHub runner `SUN_LEN` failures without moving
challenge artifacts. The standard selector now includes the certified
`drained-anchor-switch/v1` synthesis skeleton: full/reference is 100/100 exact with
median/p95 28/33 logical families and zero fault-off false exact declarations. M8
state-learning now reports 98 independent research challenge campaigns, no shared
private root, and a non-trivial learned-state effective-nibble constraint. The
release-claim decision is explicit: keep this state at `0.1.0`, do not tag v1.0, and
treat the B4/KB-frontier contribution as a future v1.0 claim gate.

## Verification dashboard

| Check | Last result | Evidence |
|---|---|---|
| `just fmt`, `just lint`, `just test` | pass | 2026-07-16 M8 campaign-count pass: Rust 46 tests and Python 196 tests pass |
| `just schema-check`, `just docs-check` | pass | Current fixtures, release-manifest schema, and links pass their implemented checks |
| `just verify-formal` | pass | Z3 `unsat` x3; TLC 78,333 generated/7,672 distinct; finite checker covers reset, gas, confinement, normalized cost, and 131,072 guarded-replay cells |
| `just boundary-audit` | pass | Recursive schema checks and separate-UID/FD-broker isolation; binary SHA-256 `c094fff76ebf1102a093b6b607f31612bf55e3516393de8d42271f3e079c0d64` |
| `just demo-tutorial` | pass | `unique_exact`, judge accepted, 16 logical families; `runs/tutorial-demo-v3` |
| standard benchmark v2 | pass | Report v1.1 covers 100 seeds / 700 campaigns with paired bootstrap CI, complete B0-B7 surface, `full_published_matrix=true`, `targets_met=true`, full/reference 100/100 exact with median/p95 28/33 logical families, fault-off 0 false exact, and normative result statuses only |
| standard profile audit v1.1 | pass | `mutation_controls_separated=true`; aggregate controls are off 0, weak 1, signed 1, reference 2 |
| `just evaluate-state-learning` | pass | Real research VM comparison plus one non-trivial learned-state effective-nibble constraint; 98 independent research challenge campaigns; retraction demo still passes |
| `just reduce-witnesses` | pass | Reports 11 minimized families with continuous accepted parent paths and reset-policy-aware measured replay |
| release manifest v2 | pass on clean tree | Current ignored manifest records 5 artifacts, all semantic checks including `m8.independent_research_challenges`, and all 12 validation gates as pass |
| GitHub CI | pass | Remote `main` run `29533351713` passed Rust, Python, integration/boundary, and release-smoke jobs |
| release-smoke CI job | pass | GitHub run `29533351713` generated audit, tutorial, standard smoke, M8, M9, evaluation artifacts, and a smoke-blocked release manifest; local socket-root regressions for standard and reducer pass |

## Release blockers

### P0

- Keep the release manifest fail-closed through any future release candidate. The
  current clean-tree manifest completes, but it is an ignored generated artifact and
  must be regenerated after any subsequent release commit or tag.
- Keep the repaired full standard benchmark artifact as the current P0 benchmark
  evidence; the legacy 600-campaign v1 report cannot validate current code.

### P1

- No open P1 blocker is currently tracked after the controller, differential, and
  expanded-formal repairs. Relation certificate proof bundles fail closed if claimed
  proof/test/semantic artifact contents change, and campaign manifest v1.2 records
  normative status plus reproducibility metadata for tutorial and all 700 standard
  benchmark runs.

### P2

- No open P2 blocker is tracked for the current `0.1.0` task-spec artifact. The final
  v1.0 release-claim decision is documented: do not tag v1.0/research-complete yet.
  The refreshed standard benchmark demonstrates synthesis/relation-family cost
  contribution over B1-B3, but not KB/frontier contribution over B4.
- Create an intentional v1.0 tag only after a future KB/frontier contribution claim is
  demonstrated or the release scope is revised again, followed by a fresh clean-tree
  release manifest regeneration.

## Current release artifacts

- `runs/standard-benchmark-v2/standard-benchmark-report.json`: full 100-seed,
  700-campaign v2 benchmark with paired bootstrap CI and complete B0-B7 surface;
  `full_published_matrix=true`, `targets_met=true`, full/reference median/p95
  28/33 logical families, and SHA-256
  `fc83eec0a6c3fbdb828556fcd003ab3192bdae4ec8f2d9e04f1d734a197db238`.
- `runs/standard-profile-audit-m7/standard-profile-audit.json`: report v1.1 with
  public one-shot, learnability, drained-repeat, and stateful aggregate mutation
  controls; `mutation_controls_separated=true`, aggregate controls are `off=0`,
  `weak=1`, `signed=1`, and `reference=2`, SHA-256
  `5a56977028f0342813a55fe3bae33b15cac9f598f46cafbc4aa813fbb95e48ce`.
- `runs/tutorial-demo-v3/report.json`: fresh tutorial demo, SHA-256
  `ad02a85d07f5de69547a7bb1870fe2caa04031e56b482e4fda726b520d63cf5b`; companion
  manifest v1.2 SHA-256
  `8a77bcbbd91764261c402976cf5c7924bfd0bd6f72de550d54f0e3664b7a4950`.
- `runs/state-learning-m8/state-learning-report.json`: real research state-learning
  measurements plus one learned-state-conditioned effective-nibble constraint;
  `state_conditioned_inference.status=complete`, `nontrivial_constraints=1`,
  `shared_private_root=false`, `cost.challenge_campaigns=98`, SHA-256
  `637c69744aee9710bf9df52271aaf6c175c5cd800724f5ef39566c32aa1a02af`.
- `runs/reduced-witnesses-m9/reduced-witnesses-report.json`: measured replay reducer
  report; `family_count=11`, `all_minimized=true`, `all_replay_paths_valid=true`,
  and `reset_policy_honored=true`, SHA-256
  `068f6d7a4b77da267504eae17a28b5a92ee7086ba3dbf2581dbfc6c9f738fe64`.
- `runs/release-m9/evaluation-artifacts/evaluation-artifacts-manifest.json`: public
  CSV/SVG artifact manifest; row counts are 700 campaign rows, 67,162 query rows,
  33,581 relation rows, 13 state rows, and 11 reducer-family rows, SHA-256
  `a6b701f8598ded2ec91625bab694ec8281b46606d4ace19935c88519100afce5`.
- `runs/release-m9/release-manifest.json`: generated manifest v2; current
  `status=complete`, `semantic_checks_pass=true`, and
  `validation_gates_pass=true` when regenerated from clean `main`. The standard
  benchmark, tutorial, M8, M9, evaluation artifacts, and all 12 validation gate checks
  pass. The manifest is intentionally ignored; regenerate it after future commits
  before using it as release evidence.

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
