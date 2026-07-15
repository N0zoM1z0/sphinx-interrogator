# Repository guide

## 1. Planned tree

```text
sphinx-interrogator/
├── AGENTS.md
├── README.md
├── agent/
│   ├── CODEX_MASTER_PROMPT.md
│   ├── CODEX_TASK_SPEC.md
│   ├── IMPLEMENTATION_RUNBOOK.md
│   ├── PLANS.md
│   ├── REVIEW_CHECKLIST.md
│   ├── STATUS.md
│   └── plans/0001-full-system.md
├── benchmarks/
│   └── profiles/*.toml
├── crates/
│   └── sphinx-vm/
├── docs/
├── examples/
├── formal/
├── python/
│   └── sphinx_interrogator/
├── scripts/
├── spec/
└── tests/
```

## 2. Ownership by layer

### `spec/`

Normative public contracts. Changes require synchronized Rust/Python tests and a schema-version decision.

### `crates/sphinx-vm/`

System A only. It owns private challenge loading and concrete execution. No Python package code should be generated from or import private modules.

### `python/sphinx_interrogator/`

System B only. It owns public parsing, relation logic, knowledge base, SMT, synthesis, learning, statistics, and campaign reporting.

### `formal/`

Small auditable models and proof examples. Formal files do not replace executable differential tests.

### `agent/`

Implementation contract and agent workflow. `CODEX_TASK_SPEC.md` is normative; the active ExecPlan is living and records how the requirements are being achieved.

## 3. Toolchain

Recommended:

- Rust 1.82 or later compatible with the checked toolchain;
- Python 3.12;
- `uv` for Python environments/locking;
- `just` as the command front-end;
- Z3 Python bindings;
- AALpy;
- TLC/TLA+ tools for formal checks;
- GitHub Actions.

Dependencies should be pinned in a generated lockfile once implementation begins. Do not manually edit generated locks.

## 4. Command contract

The final repository must implement these stable commands:

```bash
just bootstrap
just fmt
just fmt-fix
just lint
just unit
just test
just schema-check
just verify-formal
just demo-tutorial
just benchmark-standard
```

Additional useful commands:

```bash
just vm-serve PROFILE=benchmarks/profiles/tutorial.toml
just campaign PROFILE=... SEED=...
just replay RUN=...
just report RUN=...
just boundary-audit
```

The root commands are the verification surface used by coding agents and CI.

## 5. Public CLI sketch

### Target

```text
sphinx-vm serve --profile <public.toml> --private-challenge-fd <n>
sphinx-vm challenge create --profile <name> --seed <n> --out <dir>
sphinx-vm judge --private <dir> --guess <hex>
```

Challenge creation/judging are development/evaluation tools. The normal Interrogator process should be launched with only the `serve` endpoint.

### Interrogator

```text
sphinx-interrogate doctor
sphinx-interrogate recover --endpoint stdio --profile <file> --run-dir <dir>
sphinx-interrogate replay --run-dir <dir>
sphinx-interrogate inspect --run-dir <dir>
sphinx-interrogate reduce --witness <id>
sphinx-interrogate benchmark --matrix <file>
```

## 6. Coding conventions

### Rust

- pure transition functions where practical;
- newtypes for secret cells, lanes, banks, cycles, buckets, request IDs;
- checked arithmetic for counters;
- typed errors with stable protocol codes;
- no `unsafe`;
- no `unwrap`/`expect` in non-test code;
- deterministic serialization and seeded RNG.

### Python

- Python 3.12 type syntax and strict mypy;
- frozen dataclasses or Pydantic models at boundaries;
- `Protocol` interfaces for solvers/learners/samplers;
- dependency injection instead of hidden singletons;
- explicit solver timeout/result enums;
- pure AST/canonicalization functions;
- structured logging/events, not ad hoc prints.

## 7. Test layout

- Rust unit tests beside modules.
- Python unit/property tests under `tests/python/`.
- Cross-language tests launch the target process; they never import it.
- Golden protocol fixtures under `tests/fixtures/`.
- Reduced exhaustive models under `tests/exhaustive/`.
- Statistical tests use deterministic fake distributions and seeded integration cases.
- Slow benchmarks are marked and excluded from ordinary unit CI.

## 8. Documentation discipline

- Public protocol or DSL changes require updates to `spec/` and docs.
- Semantic changes require a version bump and migration/compatibility note.
- Benchmark claims must link to generated run artifacts.
- Architecture decision records may be added under `docs/adr/`.
- `agent/STATUS.md` is an implementation log, not a replacement for user-facing documentation.
