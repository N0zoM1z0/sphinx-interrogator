# Verification record

Last updated: **2026-07-16 01:33Z**

This is a living implementation record. The immutable generated-package baseline is
commit `ab30e28`; its original checksum manifest and archive remain in the local
`preparation/` directory. This record distinguishes completed checks from later
milestone requirements and never treats a scaffold check as full-system evidence.

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
