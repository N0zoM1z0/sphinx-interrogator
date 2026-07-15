# Verification record

Last updated: **2026-07-15 16:58Z**

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
