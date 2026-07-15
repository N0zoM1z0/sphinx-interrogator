set shell := ["bash", "-cu"]

bootstrap:
    @command -v cargo >/dev/null
    @command -v python3 >/dev/null
    @echo "Install Python dependencies with: uv sync --extra dev"

fmt:
    cargo fmt --all -- --check
    python3 -m ruff format --check python tests/python scripts

fmt-fix:
    cargo fmt --all
    python3 -m ruff format python tests/python scripts

lint:
    cargo clippy --workspace --all-targets --all-features -- -D warnings
    python3 -m ruff check python tests/python scripts
    python3 -m mypy python

unit:
    cargo test --workspace --lib
    python3 -m pytest tests/python -m "not integration"

test:
    cargo test --workspace --all-targets
    python3 -m pytest tests/python

schema-check:
    python3 scripts/validate_schemas.py

docs-check:
    python3 scripts/check_markdown_links.py

verify-formal:
    python3 scripts/check_formal_scaffold.py
    @echo "When TLC is installed: java -jar tla2tools.jar -config formal/SphinxVM.cfg formal/SphinxVM.tla"

demo-tutorial:
    @echo "TODO(M6): start SphinxVM and run a deterministic tutorial campaign"
    @exit 1

benchmark-standard:
    @echo "TODO(M10): execute reproducible standard-profile benchmark matrix"
    @exit 1
