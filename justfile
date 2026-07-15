set shell := ["bash", "-euo", "pipefail", "-c"]

export CARGO_BUILD_JOBS := env_var_or_default("CARGO_BUILD_JOBS", "2")
export CARGO_TARGET_DIR := env_var_or_default("CARGO_TARGET_DIR", "target")

bootstrap: bootstrap-formal
    @command -v cargo >/dev/null
    @command -v uv >/dev/null
    @rustc --version
    @cargo --version
    @uv --version
    uv sync --frozen --extra dev
    cargo fetch --locked

bootstrap-formal:
    @command -v curl >/dev/null
    @command -v java >/dev/null
    @mkdir -p .tools
    @if [[ ! -f .tools/tla2tools-1.7.4.jar ]]; then curl --fail --location --silent --show-error --output .tools/tla2tools-1.7.4.jar https://github.com/tlaplus/tlaplus/releases/download/v1.7.4/tla2tools.jar; fi
    @printf '%s  %s\n' '936a262061c914694dfd669a543be24573c45d5aa0ff20a8b96b23d01e050e88' '.tools/tla2tools-1.7.4.jar' | sha256sum --check --status
    @echo 'TLC tla2tools 1.7.4 ready'

fmt:
    cargo fmt --all -- --check
    uv run --frozen ruff format --check python tests/python scripts

fmt-fix:
    cargo fmt --all
    uv run --frozen ruff format python tests/python scripts

lint:
    cargo clippy --locked --workspace --all-targets --all-features -- -D warnings
    uv run --frozen ruff check python tests/python scripts
    uv run --frozen mypy python

unit:
    cargo test --locked --workspace --lib
    uv run --frozen pytest tests/python -m "not integration"

test:
    cargo test --locked --workspace --all-targets
    cargo build --locked --bin sphinx-vm
    SPHINX_VM_BINARY="$CARGO_TARGET_DIR/debug/sphinx-vm" uv run --frozen pytest tests/python

schema-check:
    uv run --frozen python scripts/validate_schemas.py

docs-check:
    uv run --frozen python scripts/check_markdown_links.py

verify-formal:
    uv run --frozen python scripts/check_formal_scaffold.py

boundary-audit:
    cargo build --locked --bin sphinx-vm
    SPHINX_VM_BINARY="$CARGO_TARGET_DIR/debug/sphinx-vm" uv run --frozen python scripts/boundary_audit.py

demo-tutorial:
    @echo "TODO(M5): generate, recover, judge, and report a tutorial challenge"
    @exit 1

benchmark-standard:
    @echo "TODO(M7/M9): execute and report the reproducible standard benchmark matrix"
    @exit 1
