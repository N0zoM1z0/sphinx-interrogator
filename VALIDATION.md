# Verification record

Last updated: **2026-07-16 16:37Z**

This is a living implementation record. The immutable generated-package baseline is
commit `ab30e28`; its original checksum manifest and archive remain in the local
`preparation/` directory. This record distinguishes completed checks from later
milestone requirements and never treats a scaffold check as full-system evidence.

## 2026-07-16 acceptance re-audit

The latest task-spec audit supersedes any later section that describes M8, M9, or the
release as complete. No tracked implementation source was changed by this audit; the
status/checklist/ExecPlan were corrected to match current evidence.

Commands rerun:

```text
just fmt                 pass
just lint                pass
just test                pass (46 Rust tests; 169 Python tests)
just schema-check        pass
just docs-check          pass
just verify-formal       pass (Z3 unsat x3; TLC 70,557/2,276 states;
                               131,072 guarded-replay cells)
just boundary-audit      pass (recursive validation; distinct UID/FD broker;
                               binary c094fff9561f0997dd8c307940dba991b80c920792c07095113f979d430da6cd)
just demo-tutorial       pass (unique_exact; judge accepted; 16 logical families)
just evaluate-state-learning
                         pass as a command (0.246/1.0/1.0 measured accuracy)
just reduce-witnesses    pass as a command (10 families reported minimized)
```

The passing commands do not close the following acceptance gaps:

- `runs/standard-benchmark-v2/standard-benchmark-report.json` now contains the full
  100-seed / 700-campaign current-code standard benchmark with paired bootstrap
  confidence intervals and a complete B0-B7 surface. It records
  `full_published_matrix=true`, `targets_met=true`, full/reference 100/100 exact,
  B0 random-final-guess 0/100 exact, and fault-off 0 false exact declarations.
- The M8/M9 semantic artifact gaps identified by the audit have now been repaired:
  M8 emits a non-trivial learned-state effective-nibble constraint, and M9 emits
  continuous reducer parent paths with reset-policy-aware measured replay.
- `scripts/release_manifest.py` has been repaired after this audit to fail closed:
  current `runs/release-m9/release-manifest.json` reports `status=blocked`,
  `semantic_checks_pass=false`, and `validation_gates_pass=true`. It no longer
  crashes for absolute `--output` paths. Remaining release blockers are dirty-tree
  plus the broader proof/formal/reproducibility obligations tracked in
  `agent/STATUS.md`.
- The TLA+/SMT suite omits several task-required reset, architectural-confinement,
  gas/progress, normalized-cost, exact-cycle, and extractor-differential obligations.
- Integrated campaign modes, CLI documentation, release versions, and expanded
  release-smoke CI coverage remain below the normative task specification. Tutorial
  and standard benchmark campaign manifests now use v1.2 runtime reproducibility
  metadata and normative campaign statuses. Release-bound public CSV/plot artifacts
  are now generated and hashed by the release manifest.

The repaired challenge boundary is a confirmed positive result: private roots are
unpredictable, public labels do not derive secrets, IDs are generic, System B receives
only public paths/socket access, and adversarial recursive-field and distinct-UID
tests pass. A full current benchmark has now been performed, remote `main` exists, and
GitHub Actions CI has passed on the pushed repair series.

## 2026-07-16 task-spec gap audit and lifecycle documentation repair

The task-spec gap audit reconfirmed that the current P0 benchmark/security repairs and
M8/M9 semantic artifact repairs are supported by local evidence, but release
completion is still blocked by incomplete formal/differential obligations,
non-normative statuses in some public result schemas, incomplete mutation-ladder
separation, broader release-smoke CI coverage, release-tag evidence, and final
documentation/version alignment.

README, `docs/PROTOCOL.md`, and `docs/REPOSITORY_GUIDE.md` now document the repaired
split challenge lifecycle: `challenge private-root`, split public/private challenge
outputs, private-root files, private directory FD brokerage, and public VM/judge
sockets. The old `challenge create --seed --output` and `serve --challenge` examples
were removed from current lifecycle docs. An older release-manifest hash in this file
was relabeled as historical and paired with the current manifest hash.

```text
git diff --check         pass
PATH=/tmp/sphinx-just/bin:$PATH just docs-check
                         pass
PATH=/tmp/sphinx-just/bin:$PATH just schema-check
                         pass
```

## 2026-07-16 normative public result status repair

Tutorial, standard, and B0 random-final-guess recovery reports now emit the
task-spec result status vocabulary. Legacy report statuses are accepted only for
resume/migration and are normalized as follows: `unique_exact_unjudged` to
`unique_exact`, `inconclusive` to `candidate_set`, `inconsistent` to
`model_inconsistent`, and `judge_rejected` to `target_error`. Internal
relation/statistical decisions still use `inconclusive` where appropriate; that is no
longer a public campaign result status.

The full standard benchmark was rerun in resume/upgrade mode. The regenerated
aggregate contains 500 `unique_exact` rows and 200 `candidate_set` rows; all 700
per-run reports and all 700 campaign manifests use the same normative status set, and
no per-run recovery report retains a legacy status string.

```text
uv run --frozen ruff format --check python/sphinx_interrogator/persistence.py python/sphinx_interrogator/tutorial.py python/sphinx_interrogator/standard.py python/sphinx_interrogator/cli.py scripts/benchmark_standard.py scripts/tutorial_matrix.py tests/python/test_protocol_process.py tests/python/test_standard_benchmark.py
                         pass
uv run --frozen ruff check python/sphinx_interrogator/persistence.py python/sphinx_interrogator/tutorial.py python/sphinx_interrogator/standard.py python/sphinx_interrogator/cli.py scripts/benchmark_standard.py scripts/tutorial_matrix.py tests/python/test_protocol_process.py tests/python/test_standard_benchmark.py
                         pass
uv run --frozen python -m py_compile python/sphinx_interrogator/persistence.py python/sphinx_interrogator/tutorial.py python/sphinx_interrogator/standard.py python/sphinx_interrogator/cli.py scripts/benchmark_standard.py scripts/tutorial_matrix.py
                         pass
uv run --frozen pytest tests/python/test_standard_benchmark.py tests/python/test_persistence.py
                         pass (10 tests)
SPHINX_VM_BINARY="${CARGO_TARGET_DIR:-target}/debug/sphinx-vm" uv run --frozen pytest tests/python/test_protocol_process.py -k 'tutorial_campaign_recovers or standard_campaign_recovers or fault_free_tutorial_control or fault_free_standard_control'
                         pass (4 selected integration tests)
PATH=/tmp/sphinx-just/bin:$PATH just schema-check
                         pass
PATH=/tmp/sphinx-just/bin:$PATH just benchmark-standard
                         pass; 700/700 result rows use normative statuses
PATH=/tmp/sphinx-just/bin:$PATH just release-manifest
                         expected fail; validation_gates_pass true, only repository.clean fails
```

```text
standard_benchmark_sha256: 55e571cdeaea5f904e1d9c6cd79071c53a2539507dd3c7b73d24eb02d8456480
validation_evidence_sha256: e6d6f4491e98685f6d1fd47128964da75142663cfceaa7a8da975d3cc32e7cb7
release_manifest_sha256:    056de5eb4a0ef4208ed0b6dd05d59bc8c1f855217acc7f5073520dd961314042
```

## 2026-07-16 release-manifest gate repair

The release manifest now fails closed instead of deriving completion from artifact
presence alone. It records semantic checks for benchmark, tutorial, M8, and M9
artifacts; a repository-cleanliness check; and explicit root-gate evidence slots.
The standard benchmark artifact was also upgraded to report v1.1 with paired
seed-level bootstrap confidence intervals and B0-B7 surface evidence, then regenerated
as the full published 100-seed benchmark.

Commands run:

```text
PATH=/tmp/sphinx-just/bin:$PATH just fmt
                         pass
PATH=/tmp/sphinx-just/bin:$PATH just lint
                         pass
PATH=/tmp/sphinx-just/bin:$PATH just test
                         pass (46 Rust tests; 175 Python tests)
PATH=/tmp/sphinx-just/bin:$PATH just schema-check
                         pass
PATH=/tmp/sphinx-just/bin:$PATH just docs-check
                         pass
uv run --frozen pytest tests/python/test_standard_benchmark.py tests/python/test_release_manifest.py
                         pass (6 tests)
uv run --frozen python scripts/release_manifest.py --output /tmp/sphinx-release-manifest.json
                         pass; absolute output path writes a blocked manifest
PATH=/tmp/sphinx-just/bin:$PATH just release-manifest
                         expected fail; writes blocked manifest and exits 1 with
                         --require-complete
PATH=/tmp/sphinx-just/bin:$PATH just benchmark-standard
                         pass; 100 seeds / 700 campaigns; targets_met true
git diff --check         pass
```

After the full benchmark, the root gates were rerun:

```text
PATH=/tmp/sphinx-just/bin:$PATH just fmt
                         pass
PATH=/tmp/sphinx-just/bin:$PATH just lint
                         pass
PATH=/tmp/sphinx-just/bin:$PATH just test
                         pass (46 Rust tests; 175 Python tests)
PATH=/tmp/sphinx-just/bin:$PATH just schema-check
                         pass
PATH=/tmp/sphinx-just/bin:$PATH just docs-check
                         pass
git diff --check         pass
```

Current `runs/release-m9/release-manifest.json`:

```text
status: blocked
semantic_checks_pass: false
validation_gates_pass: true
failed_release_checks: 1
standard_benchmark_sha256: 55e571cdeaea5f904e1d9c6cd79071c53a2539507dd3c7b73d24eb02d8456480
missing_or_failed_gates: 0
file_sha256: 056de5eb4a0ef4208ed0b6dd05d59bc8c1f855217acc7f5073520dd961314042
```

## 2026-07-16 M8/M9 semantic artifact repair

M8 and M9 were regenerated after the acceptance re-audit. M8 now uses independent
campaign private roots and records a learned-state-conditioned effective-nibble
projection constraint. The constraint is intentionally labeled as an effective
projection because research profiles hide lane permutation and salts; it reduces the
public macro's effective nibble from 16 values to 4 and is grouped by state-model
provenance for retraction.

M9 now reconstructs the accepted parent chain to each final reduced witness instead of
serializing the whole accepted search tree. Measured VM replay records the reset
sequence used for each relation; the soft-history witness uses `["hard", "soft"]`
rather than hard-resetting every arm.

```text
PATH=/tmp/sphinx-just/bin:$PATH just evaluate-state-learning
                         pass; state_conditioned_inference.status complete,
                         nontrivial_constraints 1
PATH=/tmp/sphinx-just/bin:$PATH just reduce-witnesses
                         pass; all_replay_paths_valid true,
                         reset_policy_honored true
uv run --frozen pytest tests/python/test_reducer.py tests/python/test_research_state.py tests/python/test_release_manifest.py
                         pass (14 tests)
PATH=/tmp/sphinx-just/bin:$PATH just schema-check
                         pass
PATH=/tmp/sphinx-just/bin:$PATH just fmt
                         pass
PATH=/tmp/sphinx-just/bin:$PATH just lint
                         pass
PATH=/tmp/sphinx-just/bin:$PATH just test
                         pass (46 Rust tests; 176 Python tests)
PATH=/tmp/sphinx-just/bin:$PATH just release-manifest
                         expected fail; only repository.clean fails among release checks,
                         validation gates are supplied by the recorder section below
git diff --check         pass
```

Current regenerated artifacts:

```text
state_learning_sha256: ce5b2daecf11499e3d1465200ecf04abd77a906927f3bb337f855ebaa354eef1
reduced_witnesses_sha256: a924448f71b27708c35945b5a64bff33f5ffd1394ca84cd700f052c12d95aa56
release_manifest_sha256: 056de5eb4a0ef4208ed0b6dd05d59bc8c1f855217acc7f5073520dd961314042
```

## 2026-07-16 certificate proof-bundle binding repair

Relation certificates now bind `relation-contracts-v1` to the actual contents of the
declared proof/test/semantic artifacts instead of only hashing a manifest that lists
their paths. The installed proof artifact records and verifies SHA-256 digests for
`formal/relation_contracts.smt2`, `tests/python/test_certified_relations.py`, and
`crates/sphinx-vm/src/machine.rs`; persisted certificates fail closed when any claimed
supporting digest is stale.

```text
uv run --frozen pytest tests/python/test_certified_relations.py tests/python/test_relations.py
                         pass (30 tests)
uv run --frozen pytest tests/python/test_solver.py::test_wrong_symbolic_model_evidence_is_unsat_not_false_exact tests/python/test_certified_relations.py::test_broken_normalizer_static_cost_mutation_is_invalid
                         pass (2 tests)
uv run --frozen ruff check python/sphinx_interrogator/certificates.py tests/python/test_certified_relations.py
                         pass
uv run --frozen python -m py_compile python/sphinx_interrogator/certificates.py
                         pass
PATH=/tmp/sphinx-just/bin:$PATH just schema-check
                         pass
PATH=/tmp/sphinx-just/bin:$PATH just release-manifest
                         expected fail; only repository.clean fails among release checks,
                         validation gates are supplied by the recorder section below
```

```text
proof_artifact_sha256: 24e7b87fbf8d1a0122e701bcfc5ff813b4da860942f9a83505c37be93b80765b
relation_contracts_smt2_sha256: 9b8f79992e49783a8775a2aa9ae79fe2581d7533cf0fe83388044fb85711220e
certified_relations_test_sha256: 14367234ffc81e86f3f2fba3606f88497aac29adbaeaae2aa32908695c024b90
solver_test_sha256: 39e48ec11ac1518ae04a70da97dace9c5333de7aed0fbf558e0c299d97398a97
rust_machine_semantics_sha256: 122b77f9c7d32e3021a7fa02bf78a92d7fc4732aa121b142bc97bedbc30b9714
```

The same repair set now includes two adversarial mutation regressions: a deliberately
contradictory symbolic-model constraint is reported as UNSAT rather than a false
singleton, and a mutated static-cost normalizer is rejected as `INVALID` before any
hard evidence is extracted.

## 2026-07-16 validation-gate evidence recorder

`scripts/record_validation_gate.py` now runs a gate command, captures exit status,
timestamps, stdout/stderr log hashes, and log paths, and merges the result into
`runs/release-m9/validation-evidence.json`. `just release-manifest` now reads that
default evidence file. All 11 expected root gates have been rerun through the
recorder and pass; the release manifest remains blocked by the dirty working tree.

```text
uv run --frozen pytest tests/python/test_validation_evidence.py tests/python/test_release_manifest.py
                         pass (4 tests)
uv run --frozen ruff check scripts/record_validation_gate.py tests/python/test_validation_evidence.py
                         pass
uv run --frozen python -m py_compile scripts/record_validation_gate.py
                         pass
PATH=/tmp/sphinx-just/bin:$PATH just --list
                         pass; includes record-validation-gate label +command
PATH=/tmp/sphinx-just/bin:$PATH just release-manifest
                         expected fail; reads validation-evidence path, only
                         repository.clean fails among release checks,
                         validation_gates_pass true
```

```text
validation_evidence_sha256: e6d6f4491e98685f6d1fd47128964da75142663cfceaa7a8da975d3cc32e7cb7
release_manifest_sha256: 056de5eb4a0ef4208ed0b6dd05d59bc8c1f855217acc7f5073520dd961314042
```

## 2026-07-16 campaign manifest v1.2 reproducibility repair

`CampaignManifest` now supports version 1.2 with repository revision/dirty state,
status-short details, tool versions, command argv/cwd, timing, normative campaign
status, and artifact hashes. `CampaignRepository.finalize_manifest()` writes the v1.2
manifest after reports are durable. Tutorial recovery, standard recovery, and the B0
random-final-guess benchmark baseline all finalize manifests; existing accepted
reports are upgraded on resume.

```text
uv run --frozen pytest tests/python/test_persistence.py tests/python/test_validation_evidence.py tests/python/test_release_manifest.py
                         pass (11 tests)
SPHINX_VM_BINARY="${CARGO_TARGET_DIR:-target}/debug/sphinx-vm" uv run --frozen pytest tests/python/test_protocol_process.py -k 'tutorial_campaign_recovers or standard_campaign_recovers or fault_free_tutorial_control or fault_free_standard_control'
                         pass (4 selected integration tests)
uv run --frozen pytest tests/python/test_standard_benchmark.py
                         pass (3 tests)
PATH=/tmp/sphinx-just/bin:$PATH just fmt
                         pass via record-validation-gate
PATH=/tmp/sphinx-just/bin:$PATH just lint
                         pass via record-validation-gate
PATH=/tmp/sphinx-just/bin:$PATH just test
                         pass via record-validation-gate; 46 Rust tests and 179 Python tests
PATH=/tmp/sphinx-just/bin:$PATH just benchmark-standard
                         pass via record-validation-gate; 700/700 standard campaign manifests are v1.2
PATH=/tmp/sphinx-just/bin:$PATH just release-manifest
                         expected fail; validation_gates_pass true, only repository.clean fails
```

```text
tutorial_manifest_sha256: 8a77bcbbd91764261c402976cf5c7924bfd0bd6f72de550d54f0e3664b7a4950
standard_campaign_manifests: 700
standard_campaign_manifest_versions: ["1.2"]
standard_campaign_manifest_statuses: ["candidate_set", "unique_exact"]
validation_evidence_sha256: e6d6f4491e98685f6d1fd47128964da75142663cfceaa7a8da975d3cc32e7cb7
release_manifest_sha256: 056de5eb4a0ef4208ed0b6dd05d59bc8c1f855217acc7f5073520dd961314042
```

## 2026-07-16 evaluation CSV/plot artifact export

`scripts/export_evaluation_artifacts.py` now derives public release CSVs and SVG
plots from the standard benchmark, M8 state-learning, and M9 reducer artifacts. The
exporter reads only public generated reports and event logs, writes a schema-versioned
manifest, and `scripts/release_manifest.py` treats that manifest as a fifth semantic
release artifact.

```text
uv run --frozen pytest tests/python/test_evaluation_artifacts.py tests/python/test_release_manifest.py
                         pass (4 tests)
uv run --frozen ruff check scripts/export_evaluation_artifacts.py scripts/release_manifest.py tests/python/test_evaluation_artifacts.py scripts/validate_schemas.py
                         pass
uv run --frozen ruff format --check scripts/export_evaluation_artifacts.py scripts/release_manifest.py tests/python/test_evaluation_artifacts.py scripts/validate_schemas.py
                         pass
PATH=/tmp/sphinx-just/bin:$PATH just export-evaluation-artifacts
                         pass; wrote campaign/query/relation/state/reducer CSVs and SVG plots
PATH=/tmp/sphinx-just/bin:$PATH just record-validation-gate 'just export-evaluation-artifacts' just export-evaluation-artifacts
                         pass
PATH=/tmp/sphinx-just/bin:$PATH just schema-check
                         pass
PATH=/tmp/sphinx-just/bin:$PATH just release-manifest
                         expected fail; evaluation artifact checks pass, validation_gates_pass true,
                         only repository.clean fails
```

```text
campaign_rows: 700
query_rows: 52928
relation_rows: 26464
state_rows: 13
reducer_family_rows: 10
evaluation_artifacts_manifest_sha256: c7ff125818abd7b8d0a895a897a994638b54cc5c5c32086fe73f0ca1cf8ba367
validation_evidence_sha256: e6d6f4491e98685f6d1fd47128964da75142663cfceaa7a8da975d3cc32e7cb7
release_manifest_sha256: 056de5eb4a0ef4208ed0b6dd05d59bc8c1f855217acc7f5073520dd961314042
```

## M0 environment

```text
rustc 1.82.0 (f6e511eec 2024-10-15)
cargo 1.82.0 (8f40fc59f 2024-08-21)
Python 3.12.13
uv 0.11.28
just 1.56.0
```

Cargo builds used a repository-specific target directory and
`CARGO_BUILD_JOBS=2`. A separate OpenVM build active on the host was not stopped,
inspected beyond process identification, or made to share this project's target.

## M0 commands and results

```text
just bootstrap
```

Passed with frozen `uv.lock` and `Cargo.lock`. Cargo 1.82 compatibility is preserved by
locking `indexmap` to 2.12.1; dependency commands use `--locked`/`--frozen`.

```text
just fmt
just lint
```

Passed. Rustfmt and Ruff formatting are clean. Clippy passed for all targets/features
with warnings denied; Ruff lint and strict mypy passed for the Python package.

```text
just test
```

Passed:

- 10 Rust tests, including bounded transport recovery, identifiers, and budgets;
- 18 Python tests;
- 2 of the Python tests launched the separately built Rust binary and validated live
  responses against the normative JSON Schema;
- malformed JSON and an oversized line produced typed errors, after which the same
  server accepted `hello` and `close`.

```text
just schema-check
just docs-check
```

Passed. Schema validation now fails closed if `jsonschema` is unavailable. Protocol and
relation fixtures and all public profiles validate; repository-relative documentation
links resolve.

```text
just verify-formal
```

The M0 formal scaffold passed and Z3 returned `unsat` for all three checked contracts.
This is not yet evidence for the complete M1/M2 machine or all relation templates. TLC
state exploration and concrete/symbolic differential checks remain required.

```text
just boundary-audit
```

The initial M0 boundary audit passed. It checked System B imports/host-introspection
markers, launched the Rust target as a separate process, exercised a probe through the
public protocol, rejected unexpected response fields, scanned typed response keys for
private microarchitectural fields, and recorded the target binary SHA-256. Private
challenge permission isolation and one-shot judge controls do not exist until M2 and
therefore are not claimed here.

## Limitations after M0

At the M0 checkpoint, the following were still incomplete:

- full DSL, validator, architectural state, control flow, and cross-language parser;
- separate architectural, fault-free, and faulty semantic implementations;
- private challenge generation, commitments, judge, profile separation, and fault
  mutations;
- proof-producing relation certificates and exact/bounded extractors;
- append-only/SQLite knowledge base and serializable Z3/MaxSMT hypothesis store;
- accepted tutorial flow, CEGIS, standard/noise calibration, active learning, reducer,
  benchmarks, TLC evidence, and release audit.

The authoritative completion criteria remain `agent/CODEX_TASK_SPEC.md`.

## M1 language and architecture checkpoint

M1 adds the full 23-opcode Rust ISA, a separate location-aware parser and semantic
validator, a pure architectural step machine, and an independent frozen Python AST,
parser, validator, formatter, effect summary, and resource summary. The normative
full-ISA fixture records source, canonical text, compact typed-AST JSON, and SHA-256 in
`tests/fixtures/programs/`. Both languages independently produce the same artifacts.

The architectural tests cover 16-bit arithmetic/flags, modulo-256 memory, branches,
bounded loops, calls/returns, digest output, experiment-instruction silence, structured
gas exhaustion, typed operand rejection, 512-byte randomized DSL inputs, 1024 bounded
random protocol lines, and generated programs across four secrets and all 16 tokens.
Protocol tests prove invalid programs do not mutate sessions/budgets and exercise
sparse public memory through both unit and live Python-to-Rust paths.

The final M1 command suite used a repository-specific Cargo home/target and two build
jobs. No other Cargo process was active:

```text
just fmt             pass
just lint            pass (Clippy -D warnings, Ruff, strict mypy)
just test            pass (24 Rust; 62 Python; 3 live process tests)
just schema-check    pass
just docs-check      pass
just verify-formal   scaffold pass (Z3 unsat x3)
just boundary-audit  pass; binary sha256=771124090adc74163fb06ba80d9d00bb3682f6e61e55e0ab8bae874120732216
```

`just demo-tutorial` was also run because M1 changes semantics. It printed the
checked-in `TODO(M5): generate, recover, judge, and report a tutorial challenge` and
exited 1. This is a real outstanding cross-milestone acceptance gate, not an M1 code
failure, and no weaker placeholder was substituted. Accordingly this is an M1 code
checkpoint rather than a claim that the milestone is formally closed.

## Remaining limitations after M1

- architectural, fault-free microarchitectural, and faulty scheduling types still need
  the full M2 separation, micro-op lowering, concrete/model checks, and fault mutations;
- public/private profile separation, challenge generation/commitment, permission
  isolation, seeded noise, and the one-shot non-oracular judge remain M2;
- relation certificates/extractors, persistence/hypothesis solver, tutorial recovery,
  CEGIS, standard/noise evaluation, active learning, reducer, TLC, and release evidence
  remain M3 through M9.

## M2 microarchitecture, challenges, and formal checkpoint

M2 replaces the combined scaffold machine/configuration with explicit `microcode`,
`microarchitecture`, `mapping`, `fault`, `noise`, and strict public `profile` modules.
Every retired instruction uses one microcode table for public static cost and the pure
hidden-state transition. Off/reference/weak/signed policies are applied separately as
timing deltas, so fault selection cannot alter architectural writes or transition shape.

Challenge creation now writes `public/profile.toml`, schema-valid public metadata, and
a mode-`0700` private tree containing the ordered secret, complete private mapping,
fault assignment, privately logged generation root, noise key, and commitment nonce.
The length-framed commitment binds all of that material. Loading rejects public hash,
budget, mapping, secret, key, or commitment mismatches. The one-shot judge atomically
consumes its public campaign token and returns only schema-valid public metadata and two
Booleans. The release server accepts only a complete challenge directory.

The independent Python target-family model and concrete Rust transition both execute
`tests/fixtures/model/micro-vectors.json`. Rust additionally exhausts the public S-box
mapping and all 2,048 reduced off-fault cells. Live process tests sweep all four anchors
against matching off/reference challenges: off produces `[0,0,0,0]`, reference produces
one `+1` and three zero deltas, and every public digest is equal. Another live test
restarts two standard-profile servers and obtains byte-equivalent seeded schedules.

Pinned formal tooling is TLA+ tools 1.7.4 / TLC 2.19 on OpenJDK 17.0.19. The final M2
command suite used repository-specific Cargo home/target paths and two build jobs. No
other Cargo process was active:

```text
just fmt             pass after formatting the two new Python model/test files
just lint            pass (Clippy -D warnings, Ruff, strict mypy)
just test            pass (42 Rust lib + 2 Rust binary; 68 Python; 6 live process tests)
just schema-check    pass (protocol, relation, challenge, judge, and public profiles)
just docs-check      pass
just verify-formal   pass (Z3 unsat x3; TLC 70,557 generated/2,276 distinct states;
                          131,072 guarded-replay combinations; mutation self-test rejected)
just boundary-audit  pass; binary sha256=628cf0df3268710b9109e328ea72c854c3a506f4c2159837638e9645d2f64e4b
```

The direct intentional mutation command was also run:

```text
uv run --frozen python scripts/check_formal_scaffold.py --mutate-suppression
exit 1 (expected): reference delta mismatch at phase=0, replay=2, lane=0,
token=0, epoch=0, secret_bank=0, anchor_bank=0
```

`just demo-tutorial` still exits 1 at its explicit M5 recovery/judge/report TODO. This
is recorded as an outstanding cross-milestone semantic gate, not replaced by the M2
challenge/server/judge smoke coverage.

## Remaining limitations after M2

- M3 must replace the early relation scaffold with all required typed templates,
  certificates, normalizers, and sound exact/bounded extractors.
- M4–M5 must add durable campaign evidence, exact Z3 uniqueness, and the real accepted
  tutorial recovery/fault-free-control flows before M1/M2 formal closure.
- CEGIS, stochastic calibration/MaxSMT, active learning/retraction, reduction,
  benchmark acceptance, and the final release audit remain M6–M9.

## M3 certified relation and extractor checkpoint

M3 replaces the tutorial-only anchor scaffold with immutable typed relation instances
for `anchor-switch`, `token-switch`, `epoch-switch`, `phase-shift`,
`repeat-amplify`, `independent-swap`, `context-lift`, `register-rename`, and
`hard-replay`. Every template has structured applicability rejection, canonical program
and instance hashes, architectural/fault-free claims, normalization/decision methods,
extractor policy, and reducer rules. Register renaming and hard replay are apparatus
controls and cannot emit hard secret constraints. Stateful `soft-history-contrast`
remains disabled until M8 can certify its history abstraction.

Certificate persistence is strict and artifact-bound: the digest covers semantic
version, profile scope, relation hash, proof method, both claims, preconditions, and
limitations. Load-time digest recomputation rejects altered semantics/claims and
unknown fields. The current secret-bearing template scope is identity lane mapping,
unique hard reset, and tutorial/standard bounded observation profiles.

Normalization converts public quantized buckets into closed pre-noise integer
intervals after subtracting each program's public static cost. A hard extractor is
eligible only when the complete difference interval has one order. It exhaustively
retains every `(secret projection, fault variant)` whose independently modeled source
and follow-up can reproduce both buckets for some declared bounded-noise values. Thus
the private `off/reference/weak/signed` choice remains latent and fault-free controls do
not produce false secret singletons.

The solver-independent constraint expression IR has explicit Boolean, integer, named
finite-domain, and fixed-width bit-vector sorts; typed Boolean/arithmetic/ITE/extract
and signed/unsigned comparison operations; named assumption provenance; strict
recursive decoding; canonical JSON; and a Draft 2020-12 recursive schema. Exhaustive
tests compare its S-box/bank expression over all 512 cell inputs and its fault/replay
expressions over their complete reduced domains.

The final M3 suite used the repository-local Cargo home/target, two build jobs, and no
concurrent Cargo/rustc process:

```text
just fmt             pass (35 Python/script files already formatted; Rustfmt clean)
just lint            pass (Clippy -D warnings, Ruff, strict mypy over 18 modules)
just test            pass (42 Rust lib + 2 Rust binary; 99 Python; 7 live process tests)
just schema-check    pass (including relation, finite-constraint, and expression-IR fixtures)
just docs-check      pass
just verify-formal   pass (Z3 unsat x3; TLC 70,557 generated/2,276 distinct;
                          131,072 guarded-replay cells; mutation rejected)
just boundary-audit  pass; binary sha256=628cf0df3268710b9109e328ea72c854c3a506f4c2159837638e9645d2f64e4b
```

Python M3 tests cover positive/negative preconditions for all nine templates, reduced
architectural and off-fault normalization, exact extractors for all seven
secret-bearing templates, every `[-1,1]` noise pair and all four fault variants,
quantized equal-bucket inconclusiveness, certificate policy/tamper rejection, schema
round trips, and a live authoritative Rust-process execution of all relation arms.

`just demo-tutorial` was run and still exits 1 at the checked-in M5
generate/recover/judge/report TODO. M3 is therefore a verified implementation
checkpoint, not a false claim that the cross-milestone semantic gate has closed.

## Remaining limitations after M3

- M4 must persist raw/derived evidence, materialize SQLite views, translate the IR to
  Z3, prove exact uniqueness by excluding alternatives, and implement resume/replay,
  implication, unsat-core quarantine, and provenance-rich snapshots.
- M5 must replace the tutorial TODO with generated challenge recovery, one-shot judge
  acceptance, and the fault-free negative control.
- CEGIS, stochastic/MaxSMT calibration, stateful learning/retraction, relation-aware
  reduction, benchmarks, and final release evidence remain M6–M9.

## M4 durable campaign and exact hypothesis checkpoint

M4 introduces a four-layer authority order: immutable public `manifest.json`, exact
content-hashed public wire exchanges under `raw/`, a stable-ID/hash-chained append-only
`events.jsonl`, and disposable `campaign.sqlite3` materialized views. The real JSONL
client invokes its recorder immediately after reading an execute response line and
before JSON decoding. A crash injected at that point leaves raw evidence but no derived
event; reopening decodes that raw line, commits one stable execution event, and never
calls the fake endpoint again. A live integration test exercises the identical path
against the authoritative Rust challenge server.

SQLite version 1 materializes query nodes, seeded balanced/correlated batches,
executions, certificates, relation edges, decisions, constraints, candidate snapshots,
state-model versions, witnesses, and TTL frontier candidates. Events are validated
against current foreign-key/provenance state before append, then written before the
SQLite transaction. Reopen catches an event committed just before a database crash;
full rebuild reproduces the same deterministic view digest. Constraints cannot
materialize unless all raw request IDs, their relation, and certificate exist.

The solver-independent IR now has a complete Z3 translator. Fixed-width operations,
signed/unsigned comparisons, named assumptions, and finite-domain encodings preserve
their project semantics. The hypothesis store returns only `sat|unsat|unknown`, tracks
provenance-rich unsat cores, blocks models for enumeration, selects diverse bounded
committees, labels exact versus sampled marginals, checks implication, and proves
uniqueness only by an explicit alternative-model exclusion that returns `unsat`.
Constraint groups can be quarantined/reactivated/retracted and replayed from JSON IR;
grouped soft evidence has a configured weight cap and MaxSMT ranking.

The active frontier records independent structural, relation, state, observation,
partition, and semantic keys. TTL is enforced at insertion/selection and ties use the
stable candidate ID. Solver implication `unknown` defers a candidate and appends no
event; it is never treated as semantic novelty proof.

The final M4 suite used the repository-local Cargo home/target, two build jobs, and no
concurrent Cargo/rustc process:

```text
just fmt             pass (46 Python/script files and Rustfmt clean)
just lint            pass (Clippy -D warnings, Ruff, strict mypy over 23 modules)
just test            pass (42 Rust lib + 2 Rust binary; 125 Python; 8 live process tests)
just schema-check    pass (including versioned public campaign manifest fixture)
just docs-check      pass
just verify-formal   pass (Z3 unsat x3; TLC 70,557 generated/2,276 distinct;
                          131,072 guarded-replay cells; mutation rejected)
just boundary-audit  pass; binary sha256=628cf0df3268710b9109e328ea72c854c3a506f4c2159837638e9645d2f64e4b
```

Python adds focused evidence for raw-write crash resume, exact event replay, empty and
existing SQLite migrations/future-version rejection, full constraint provenance,
deterministic schedule balance, fake/live endpoints, implication unknown, TTL and
tie-breaking, finite secret/fault correlation, exact uniqueness, core rollback, soft
weight caps, CLI inspect/replay, and 512-cell plus complete reduced fault/replay/phase
concrete-versus-Z3 differential checks.

`just demo-tutorial` was run and still exits 1 at the checked-in M5 TODO. M4 is a
verified implementation checkpoint; the deferred cross-milestone gate is not claimed
until generated recovery, uniqueness, judge, persistence, and reporting are real.

## Remaining limitations after M4

- M5 must integrate relation execution/selection with this repository and hypothesis
  store, recover every tutorial seed uniquely, invoke the one-shot judge, and prove the
  fault-free negative control cannot declare exact recovery.
- CEGIS, stochastic calibration and full MaxSMT repair policy, stateful learning,
  relation-aware reduction, standard benchmarks, and release evidence remain M6–M9.

## M5 deterministic tutorial recovery checkpoint

M5 replaces the semantic demo TODO with a complete generated-challenge campaign that
uses only `challenge/public/challenge.json`, `challenge/public/profile.toml`, and typed
responses from the separately launched Rust process. For each of four lanes and two
epochs it compares two certified anchor pairs at the public token zero, producing 16
logical relation families and 32 physical executions. All relation instances,
certificates, balanced batches, executions, decisions, and finite constraints are
stored through the M4 event log and SQLite materialization.

The final exactness claim is deliberately about the 16-bit secret projection. Three
full satisfying assignments can remain because reference, weak, and signed fault
members produce the same tutorial evidence, but they all share one secret. The report
declares `unique_exact` only after the solver excludes every assignment with a
different secret and returns `unsat`. Only then is the Rust one-shot judge invoked.
The accepted report records the manifest, challenge commitment, materialized digest,
costs, uniqueness artifact, and sole public judge event. A second invocation verifies
and returns that report without launching a second submission.

Campaign manifest version 1.1 adds the public challenge commitment. SQLite migration
version 2 adds `judge_submissions`; the prior-version test constructs a version-1
database, reopens it, applies the migration, and proves deterministic rebuild. Recovery
report version 1.0 has a strict Draft 2020-12 schema and checked-in fixture.

The published deterministic matrices were run against the authoritative Rust binary:

```text
SPHINX_VM_BINARY="$PWD/.cache/sphinx-target/debug/sphinx-vm" \
  uv run --frozen python scripts/tutorial_matrix.py \
  --output runs/tutorial-evaluation-v2 --fault reference

100/100 unique_exact; 100/100 judge accepted
median logical relation families: 16; maximum: 16
artifact: runs/tutorial-evaluation-v2/summary.json

SPHINX_VM_BINARY="$PWD/.cache/sphinx-target/debug/sphinx-vm" \
  uv run --frozen python scripts/tutorial_matrix.py \
  --output runs/tutorial-fault-free-v2 --fault off

100/100 candidate_set; 0 exact declarations; 0 judge submissions
median logical relation families: 16; maximum: 16
artifact: runs/tutorial-fault-free-v2/summary.json
```

The final M5 suite used the repository-local Cargo home/target, two build jobs, and no
concurrent Cargo/rustc process:

```text
just fmt             pass (49 Python/script files and Rustfmt clean)
just lint            pass (Clippy -D warnings, Ruff, strict mypy over 24 modules)
just test            pass (42 Rust lib + 2 Rust binary; 128 Python; 10 live process tests)
just schema-check    pass (including manifest 1.1 and recovery report 1.0)
just docs-check      pass
just verify-formal   pass (Z3 unsat x3; TLC 70,557 generated/2,276 distinct;
                          131,072 guarded-replay cells; mutation rejected)
just boundary-audit  pass; binary sha256=628cf0df3268710b9109e328ea72c854c3a506f4c2159837638e9645d2f64e4b
just demo-tutorial   pass; unique_exact e905; judge accepted; 16 logical/32 physical
```

`just demo-tutorial` was also run a second consecutive time against
`runs/tutorial-demo-v2-seed-7`. It returned the verified accepted report with the same
result and exactly one materialized judge event. A live reference integration test
independently checked schema validation, alternative-model `unsat`, database rebuild,
and accepted-report resume; its otherwise-identical off-fault test retained all 65,536
secret projections, emitted no exact result, and never called the judge.

## Remaining limitations after M5

- M6 must replace fixed candidate choice with grammar-guided skeleton enumeration, SMT
  hole filling, pair separation, deterministic committee scoring, and CEGIS refinement.
- Stochastic calibration/MaxSMT repair, persistent-state learning/retraction,
  relation-aware reduction, standard benchmarks, and release evidence remain M7–M9.

## M6 grammar-guided CEGIS synthesis checkpoint

M6 replaces the earlier entropy-only finite selector with versioned typed relation
skeletons for `anchor-switch/v1` and drained `repeat-amplify/v1`. Named finite holes
cover lane, token, epoch, bank, phase padding, and repetition count. Every enumerated
assignment lowers through the existing certified constructors and is rejected before
scoring if its exact combined AST/static resources exceed the grammar bound. Z3 fills
the actual named holes from a finite public signature truth table, enforces all current
model-pair separation requirements, and lexicographically minimizes resources and the
canonical assignment key under a configured timeout.

The CEGIS verifier starts with a maximum-distance secret/fault/state pair from a
deterministic diverse committee. It scores every satisfying bounded assignment by
worst predicted bucket, conservative closed-interval margin, physical executions,
hard resets, combined static/AST cost, and canonical key. An oversized bucket supplies
a new maximum-distance unseparated pair; the regression requires multiple iterations
and records five genuine refinements before proving that its deliberately impossible
balance target cannot be met. A solver timeout remains `unknown`, while a complete
off-fault committee is `unsat`/no discriminator.

Committees can be generated directly from M4 `HypothesisStore.diverse_models` while
preserving the correlated latent fault member. Complete finite committees label their
entropy `exact-information`; bounded diverse subsets label it `committee-proxy` and
make no uniform/posterior claim. The cache key binds hypothesis and committee
fingerprints, profile/semantic/state-model/grammar versions, certificate policy,
resource bounds, and observation/margin/balance configuration. Successful results
adapt to the persistent M4 frontier with every score component, typed hole assignment,
certificate-bound relation, and CEGIS counterexample in its data.

Focused M6 evidence includes:

- a four-model domain whose SMT/CEGIS result exactly matches exhaustive lexicographic
  scoring and selects the known two-way signed-margin optimum;
- a positive-noise-margin case that changes the selected grammar production from a
  cheap anchor switch to an eight-fold drained repeat;
- exhaustive symbolic-versus-concrete signature agreement for representative
  candidates, all 16 nibbles, all four public fault-family members, bounded noise, and
  quantization width two;
- a live Rust-process test that executes the synthesized typed pair, confirms both
  public architectural digests match, and obtains a valid exact relation decision;
- cache identity and durable frontier materialization with all score components; and
- explicit no-discriminator and injected-solver-unknown failure paths.

The deterministic contribution calibration used 20 PRNG seeds. Each seed selects an
eight-model surviving nibble committee; no model is designated or consulted as a true
target secret. Under the same bounded anchor grammar, CEGIS selection achieved mean
worst bucket 3.00 (sum 60) versus 7.15 (sum 143) for one seeded uniform random hole and
won strictly on 19/20 subsets. This establishes an M6 selector contribution on a tiny
domain; it does not claim the M7 standard recovery target.

The final M6 suite used the repository-local Cargo home/target, two build jobs, and no
concurrent Cargo/rustc process:

```text
just fmt             pass (49 Python/script files and Rustfmt clean)
just lint            pass (Clippy -D warnings, Ruff, strict mypy over 24 modules)
just test            pass (42 Rust lib + 2 Rust binary; 141 Python; 11 live process tests)
just schema-check    pass
just docs-check      pass
just verify-formal   pass (Z3 unsat x3; TLC 70,557 generated/2,276 distinct;
                          131,072 guarded-replay cells; mutation rejected)
just boundary-audit  pass; binary sha256=628cf0df3268710b9109e328ea72c854c3a506f4c2159837638e9645d2f64e4b
just demo-tutorial   pass; unique_exact e905; judge accepted; 16 logical/32 physical
```

## Remaining limitations after M6

- M7 must calibrate robust bounded/stochastic decisions, grouped soft weights,
  contradiction quarantine/repair, and execute the standard/reference/control matrix.
- Persistent-state learning/retraction, relation-aware reduction, baselines/ablations,
  and final release evidence remain M8–M9.

## M7 noise, repair, and standard benchmark checkpoint

M7 completes the bounded/statistical evidence layer and the published standard
benchmark flow. Sequential sign decisions now use fixed checkpoints, Bonferroni
family-wise alpha, a dead zone, minimum nonzero observations, and median-of-means
aggregation. They explicitly return positive, negative, or inconclusive probabilistic
soft evidence; nonsignificance never becomes hard equality. Soft evidence is capped,
grouped, and ranked through MaxSMT weights. High-influence soft groups can be replayed
from provenance, quarantined with a persistent reason, repaired, and reactivated.

Standard recovery uses the public `standard` profile only, reads no private challenge
state, and launches the Rust VM as a separate process. It lowers certified
`repeat-amplify/v1` relations through the M6 grammar, uses exact bounded nuisance
elimination over width-four buckets and `[-1,1]` seeded noise, persists raw wire bytes,
stores factorized finite lane domains, proves alternative-secret `unsat` before
submitting one judge guess, and resumes from a completed report without a second judge
submission. The VM session limit bug found during smoke testing was fixed by reusing
two stable public sessions, `standard-source` and `standard-follow_up`, while retaining
stable per-execution IDs for replay.

Focused M7 evidence includes:

- 1,000 deterministic null simulations with at most 5/1,000 directional sequential
  false positives, and 977/1,000 positive decisions under a size-two effect;
- grouped soft MaxSMT tests proving capped weights do not duplicate evidence;
- replay/quarantine/repair tests for high-influence soft groups;
- exhaustive standard repeat-schedule soundness over all nibbles, epochs, anchors,
  public fault-family members, and bounded noise pairs;
- live standard reference recovery with schema validation, alternative-secret `unsat`,
  accepted one-shot judge, database rebuild, and completed-report resume;
- live blind standard off-control recovery with 64 logical families, 128 executions,
  all `16**8` secrets retained, no constraints, and no judge call.

The public standard profile audit is generated at
`runs/standard-profile-audit-m7/standard-profile-audit.json`:

```text
maximum one-shot partition: 1.5 bits
median useful partition:    1.5 bits
repeat partition example:   [12, 4] = 0.811278 bits
anchor-switch example:      [8, 4, 4] = 1.5 bits
oracle collision bound:     16 logical relations
blind scan worst bound:     64 logical relations
```

The one-seed mutation ladder at
`runs/standard-mutation-ladder-smoke-m7/standard-benchmark-report.json` recovered
`reference`, `weak`, and `signed` exactly. The audit records that these three active
variants all have the same drained-repeat margin of 15 cycles, while `off` has margin
0. M7 therefore keeps the active variant latent and treats only `off` as the release
negative control; active-variant identification remains an M8 state/history problem.

The full published standard matrix was run with:

```text
CARGO_HOME="$PWD/.cache/cargo-home" \
CARGO_TARGET_DIR="$PWD/.cache/sphinx-target" \
CARGO_BUILD_JOBS=2 \
  .tools/bin/just benchmark-standard
```

Artifact: `runs/standard-benchmark-v1/standard-benchmark-report.json`.

Results:

```text
campaigns:                         600
full/reference exact rate:         100/100
full/reference median logical:     40
full/reference p95 logical:        48
full/reference median physical:    80
off-control false exact:           0/100
off-control status:                100/100 candidate_set
targets_met:                       true
```

All reference selector modes also recovered 100/100 exactly:

```text
full              median 40 logical, p95 48, max 51
random            median 40 logical, p95 48, max 52
stateless         median 40 logical, p95 47, max 51
kb_no_synthesis   median 40 logical, p95 46, max 50
synthesis_no_kb   median 40 logical, p95 48, max 51
```

This is reported as robustness rather than a large selector gap for the frozen
standard profile.

The final M7 suite used the repository-local Cargo home/target, two build jobs, and no
concurrent Cargo/rustc process:

```text
just fmt             pass (52 Python/script files and Rustfmt clean)
just lint            pass (Clippy -D warnings, Ruff, strict mypy over 25 modules)
just test            pass (42 Rust lib + 2 Rust binary; 149 Python)
just schema-check    pass (including standard recovery and benchmark report schemas)
just verify-formal   pass (Z3 unsat x3; TLC 70,557 generated/2,276 distinct;
                          131,072 guarded-replay cells; mutation rejected)
just boundary-audit  pass; binary sha256=628cf0df3268710b9109e328ea72c854c3a506f4c2159837638e9645d2f64e4b
just demo-tutorial   pass; unique_exact e905; judge accepted; 16 logical/32 physical
just benchmark-standard pass; targets_met true
```

## Remaining limitations after M7

- M8 must add exact-history and AALpy-backed soft-reset state learning, conformance
  counterexamples, and safe retraction/replay of state-dependent constraints.
- M9 must add relation-aware witness reduction, final release baselines/ablations,
  minimized artifacts, docs polish, and the release manifest/audit bundle.

## M8 active state-learning checkpoint

M8 implements the project-owned state-learning boundary in
`python/sphinx_interrogator/learner.py`. It includes versioned macro input/output
alphabets, stable membership-cache digests, a one-state hard-reset learner, a bounded
exact-history Mealy learner, an AALpy-backed deterministic L* Mealy learner, learned
model serialization with artifact digests, held-out conformance metrics,
counterexample records, access-sequence lookup, bounded distinguishing suffixes, and
transition coverage. AALpy objects are converted into this repository-owned format;
they are not persisted directly.

`soft-history-contrast/v1` is now enabled in `relations.py` for research-mode
soft-reset experiments. It composes two public architecture-silent history prefixes
with one certified measurement suffix, uses reset policy `soft`, records a named
state-model ID and source/follow-up state labels, and cannot emit a standalone hard
secret constraint. Any downstream state-conditioned group must include
`state-model:<id>` provenance.

`CampaignHypotheses.record_state_model` persists learned model artifacts through the
existing `state_model_recorded` event. `retract_state_model_constraints` retracts all
active groups with the invalidated `state-model:<id>` marker through append-only
constraint-state events, preserving independent hard-reset evidence.

Focused M8 tests cover:

- exact-history suffix tracking and hard-versus-soft reset behavior;
- one-state hard-reset model serialization and prediction;
- stable membership-cache deduplication/digesting;
- AALpy L* learning of a deterministic two-state Mealy fixture;
- exact-history prediction beating the no-learner baseline;
- state-model artifact persistence and counterexample-driven group retraction after
  replay/reopen;
- `soft-history-contrast/v1` preconditions, schema validation, soft reset policy, and
  no-standalone-hard-constraint behavior.

The state-learning comparison was run with:

```text
just evaluate-state-learning
```

Artifact: `runs/state-learning-m8/state-learning-report.json`.

Results:

```text
held-out macro sequences: 30
no_learner:       1 state,  accuracy 0.13333333333333333, counterexamples 26
exact_history:   31 states, accuracy 1.0,                 counterexamples 0
learned_state:   2 states,  accuracy 1.0,                 counterexamples 0
targets_met:     exact_history_accuracy_eq_1,
                 learned_state_accuracy_ge_0_95,
                 learned_state_beats_no_learner
```

The final M8 suite used the repository-local Cargo home/target, two build jobs, and no
concurrent Cargo/rustc process:

```text
just fmt                    pass (54 Python/script files and Rustfmt clean)
just lint                   pass (Clippy -D warnings, Ruff, strict mypy over 25 modules)
just test                   pass (42 Rust lib + 2 Rust binary; 156 Python)
just schema-check           pass (including state-conditioned relation schema)
just docs-check             pass
just verify-formal          pass (Z3 unsat x3; TLC 70,557 generated/2,276 distinct;
                                 131,072 guarded-replay cells; mutation rejected)
just boundary-audit         pass; binary sha256=628cf0df3268710b9109e328ea72c854c3a506f4c2159837638e9645d2f64e4b
just demo-tutorial          pass; unique_exact e905; judge accepted; 16 logical/32 physical
just evaluate-state-learning pass; learned-state and exact-history targets met
```

## Remaining limitations after M8

- M9 must implement relation-aware witness reduction, minimized witness artifacts,
  final release/report packaging, review checklist completion, and release audit
  evidence.

## M9 reducer and release checkpoint

M9 implements `python/sphinx_interrogator/reducer.py`, a relation-aware best-first
reducer over typed relation families. A candidate is accepted only when it remains a
valid certified relation instance, its architectural and fault-free prechecks pass, it
strictly lowers `(physical executions, static cycles, AST nodes, history length,
lexical form)`, and it preserves the configured finite public-model consequence
(`equivalent`, `implies-core`, or `same-partition`). The reducer never uses the hidden
challenge secret; release witnesses use bounded public-family model signatures.

Release additions:

- `sphinx-interrogate doctor`, `sphinx-interrogate reduce`, and
  `sphinx-interrogate benchmark` CLI coverage;
- `scripts/reduce_witnesses.py` and `just reduce-witnesses`;
- `spec/reduced-witnesses-report.schema.json` plus fixture validation;
- `scripts/release_manifest.py` and `just release-manifest`;
- `docs/RELEASE_NOTES.md`, reducer/evaluation docs, and completed
  `agent/REVIEW_CHECKLIST.md`.

Artifact: `runs/reduced-witnesses-m9/reduced-witnesses-report.json`.

Results:

```text
families:       10
minimized:      10
unchanged:      0
all_minimized:  true
artifact_sha256 3558973ce4005e6cf2e478ffa44c23b2531e395860bb08dd92e6ff395c418434
```

Release manifest: `runs/release-m9/release-manifest.json`.

```text
artifact_count: 5
missing_count:  0
status:         blocked
semantic_checks_pass: false
validation_gates_pass: true
historical_manifest_sha256: 07abd071c4717435587bb42b3b5d012dea26806459aabda20a6998c9340ed6b7
current_manifest_sha256:    056de5eb4a0ef4208ed0b6dd05d59bc8c1f855217acc7f5073520dd961314042
```

The final M9 suite used the repository-local Cargo home/target, two build jobs, and no
concurrent Cargo/rustc process:

```text
just fmt                    pass (58 Python/script files and Rustfmt clean)
just lint                   pass (Clippy -D warnings, Ruff, strict mypy over 26 modules)
just test                   pass (42 Rust lib + 2 Rust binary; 162 Python)
just schema-check           pass (including reduced-witness report schema)
just docs-check             pass
just verify-formal          pass (Z3 unsat x3; TLC 70,557 generated/2,276 distinct;
                                 131,072 guarded-replay cells; mutation rejected)
just demo-tutorial          pass; unique_exact e905; judge accepted; 16 logical/32 physical
just boundary-audit         pass; binary sha256=628cf0df3268710b9109e328ea72c854c3a506f4c2159837638e9645d2f64e4b
just benchmark-standard     pass; 600 campaigns, targets_met true, full/reference
                                 exact rate 1.0, p95 48 logical, off false exact 0
just evaluate-state-learning pass; learned-state and exact-history targets met
just reduce-witnesses       pass; 10/10 relation families minimized
just release-manifest       fails closed; four public artifacts hashed, semantic
                            release checks/gate evidence incomplete
```

## Remaining limitations after M9

- The standard profile remains intentionally synthetic and locally generated.
- All published reference selector baselines recover the frozen standard profile, so
  the release reports robustness and boundary safety rather than a large selector gap.
- `runs/release-m9/release-manifest.json` is ignored by design; rerun
  `just release-manifest` after a release commit to capture the committed HEAD.
