# Package validation record

Validation date: **2026-07-15**

This record describes checks run against the design package itself. It does not claim that the full research system or its benchmark acceptance targets are implemented.

## Passed checks

```text
PYTHONPATH=python python3 -m compileall -q python scripts tests/python
```

All Python source, scripts, and tests compiled to bytecode.

```text
.venv/bin/ruff format --check python tests/python scripts
.venv/bin/ruff check python tests/python scripts
PYTHONPATH=python .venv/bin/mypy python
```

Result: formatting clean, lint clean, and strict mypy reported no issues in the Python package.

```text
PYTHONPATH=python .venv/bin/pytest -q tests/python
```

Result: **14 passed**, including an end-to-end deterministic tutorial loop against a black-box-compatible fake target.

```text
python3 scripts/validate_schemas.py
python3 scripts/check_markdown_links.py
ruby -e 'require "yaml"; YAML.load_file(ARGV[0])' <each .github YAML file>
```

Result: JSON Schemas parsed, protocol/relation fixtures validated, public TOML profiles passed structural checks, all repository-relative Markdown links resolved, and all checked-in GitHub YAML files parsed successfully.

```text
PATH="$PWD/.venv/bin:$PATH" python3 scripts/check_formal_scaffold.py
```

Result: formal structure passed and Z3 returned `unsat` for all three bounded relation-contract checks.

A Tree-sitter Rust parser was also run over every checked-in `.rs` file. All files produced syntax trees without error or missing nodes.

The Python CLI was smoke-tested through `--help`, `render-cell`, and `render-anchor-switch`; it produced canonical DSL programs and a deterministic relation-certificate digest.

## Environment limitations

The execution environment did not contain `cargo`, `rustc`, `rustfmt`, `clippy`, `just`, or the TLA+ TLC tools. Direct installation of Rust was unavailable because the runtime could not resolve the Rust distribution host. Consequently:

- Rust syntax was parsed, but the crate was **not compiled or linked** here;
- `cargo fmt`, `cargo clippy`, and Rust unit tests were **not executed**;
- the TLA+ model received structural review, but TLC state exploration was **not executed**.

GitHub Actions is configured to run the Rust formatting, Clippy, and test surface on a normal hosted runner. Milestone M0 explicitly requires resolving any resulting compiler or lint findings before implementation proceeds.

## Deliberately incomplete surfaces

The package contains an executable reference scaffold, schemas, tests, and formal seeds. It deliberately leaves the following to the Codex implementation task:

- complete ISA, challenge generation, private judge, and hardened process server;
- production Z3/MaxSMT encoding and exact uniqueness proof artifacts;
- all relation families and bounded certificates;
- CEGIS campaign integration, model counting, and state-conditioned query selection;
- AALpy learning loop and conformance testing;
- stochastic profile calibration, witness reduction, benchmark reports, and release evidence.

The authoritative completion contract is `agent/CODEX_TASK_SPEC.md`.
