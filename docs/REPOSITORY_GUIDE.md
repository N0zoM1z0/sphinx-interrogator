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
SPHINX_VM_BINARY=target/debug/sphinx-vm uv run --frozen python scripts/evaluate_state_learning.py --output runs/state-learning-m8
SPHINX_VM_BINARY=target/debug/sphinx-vm uv run --frozen python scripts/reduce_witnesses.py --output runs/reduced-witnesses-m9
SPHINX_VM_BINARY=target/debug/sphinx-vm uv run --frozen python scripts/benchmark_standard.py --output runs/standard-benchmark-v2 --socket-root /tmp/sphinx-standard-sockets --smoke
```

The root commands are the verification surface used by coding agents and CI. The
`--socket-root` option is for transient VM Unix sockets on long checkout paths; it
does not move challenge or report artifacts.

## 5. Public CLI

### Target

```text
sphinx-vm challenge private-root --output <private-root-file>
sphinx-vm challenge create --profile <public.toml> \
  --public-output <public-dir> --private-output <private-dir> \
  --private-root-file <private-root-file> \
  [--challenge-id <opaque-public-id>] --campaign-label <private-label> \
  [--fault off|reference|weak|signed]
sphinx-vm serve --public-challenge <public-dir> \
  --private-challenge-fd <trusted-private-dir-fd> --socket <vm.sock>
sphinx-vm judge-serve --public-challenge <public-dir> \
  --private-challenge-fd <trusted-private-dir-fd> --socket <judge.sock>
```

Challenge creation and private FD brokerage are trusted development/evaluation
orchestration. The normal Interrogator process is launched with only a public
challenge directory plus VM/judge socket paths.

### Interrogator

```text
sphinx-interrogate doctor
sphinx-interrogate controller-plan --secret-cells <n>
sphinx-interrogate hello --vm-socket <vm.sock>
sphinx-interrogate render-cell --lane <n> --token <n> --epoch <n> --anchor <n>
sphinx-interrogate render-anchor-switch --lane <n> --token <n> --epoch <n> \
  --bank-a <n> --bank-b <n>
sphinx-interrogate recover --public-challenge <public-dir> --vm-socket <vm.sock> \
  --judge-socket <judge.sock> --run <dir> --seed <n>
sphinx-interrogate replay --run <dir>
sphinx-interrogate inspect --run <dir>
sphinx-interrogate reduce --family repeat-amplify/v1
sphinx-interrogate benchmark --report runs/standard-benchmark-v2/standard-benchmark-report.json
```

`controller-plan` prints the integrated public selector plan for the current context.
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
