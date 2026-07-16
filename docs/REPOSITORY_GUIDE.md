# Repository guide

## 1. Repository tree

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

The implementation uses committed `Cargo.lock` and `uv.lock` files. Local and CI
verification must use Cargo `--locked` and uv `--frozen`. The checked
`.python-version` selects Python 3.12. Cargo work should use a repository-specific
target directory; on shared developer machines, keep `CARGO_BUILD_JOBS` low enough not
to disrupt unrelated builds.

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
just docs-check
just verify-formal
just demo-tutorial
just benchmark-standard
just boundary-audit
just evaluate-state-learning
just reduce-witnesses
just release-manifest
```

Additional useful commands:

```bash
SPHINX_VM_BINARY=target/debug/sphinx-vm uv run --frozen python scripts/demo_tutorial.py
uv run --frozen python scripts/evaluate_state_learning.py --output runs/state-learning-m8
uv run --frozen python scripts/reduce_witnesses.py --output runs/reduced-witnesses-m9
```

The root commands are the verification surface used by coding agents and CI.

## 5. Public CLI

### Target

```text
sphinx-vm challenge create --profile <public.toml> --output <new-dir> \
  [--challenge-id <id>] [--seed <n>] [--fault off|reference|weak|signed]
sphinx-vm serve --challenge <challenge-dir>
sphinx-vm judge --challenge <challenge-dir> --campaign-token <token> --guess <hex-cells>
```

Challenge creation/judging are development/evaluation tools. The normal Interrogator process should be launched with only the `serve` endpoint.

### Interrogator

```text
sphinx-interrogate doctor
sphinx-interrogate hello --vm <binary> --challenge <dir>
sphinx-interrogate render-cell --lane <n> --token <n> --epoch <n> --anchor <n>
sphinx-interrogate render-anchor-switch --lane <n> --token <n> --epoch <n> \
  --bank-a <n> --bank-b <n>
sphinx-interrogate recover --vm <binary> --challenge <dir> --run <dir> --seed <n>
sphinx-interrogate replay --run <dir>
sphinx-interrogate inspect --run <dir>
sphinx-interrogate reduce --family repeat-amplify/v1
sphinx-interrogate benchmark --report runs/standard-benchmark-v1/standard-benchmark-report.json
```

`benchmark` inspects an existing generated report. The published standard matrix is
still executed through `just benchmark-standard`, which builds and launches the VM
process through the same public JSONL boundary as campaigns.

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
