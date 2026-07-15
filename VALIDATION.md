# Verification record

Last updated: **2026-07-15 16:17Z**

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

## Current limitations

M0 establishes a reproducible public process boundary, not the finished research
system. The following remain incomplete:

- full DSL, validator, architectural state, control flow, and cross-language parser;
- separate architectural, fault-free, and faulty semantic implementations;
- private challenge generation, commitments, judge, profile separation, and fault
  mutations;
- proof-producing relation certificates and exact/bounded extractors;
- append-only/SQLite knowledge base and serializable Z3/MaxSMT hypothesis store;
- accepted tutorial flow, CEGIS, standard/noise calibration, active learning, reducer,
  benchmarks, TLC evidence, and release audit.

The authoritative completion criteria remain `agent/CODEX_TASK_SPEC.md`.
