#!/usr/bin/env python3
"""Validate repository JSON schemas, fixtures, and public profile TOML files."""

from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path
from typing import Any

import jsonschema

ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path) -> Any:
    """Load one UTF-8 JSON document."""
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def validate_schema_documents() -> list[str]:
    """Parse every schema and run the Draft 2020-12 schema self-check."""
    errors: list[str] = []
    for path in sorted((ROOT / "spec").glob("*.schema.json")):
        try:
            schema = load_json(path)
            jsonschema.Draft202012Validator.check_schema(schema)
        except Exception as error:
            errors.append(f"{path.relative_to(ROOT)}: {error}")
    return errors


def validate_fixtures() -> list[str]:
    """Validate checked-in fixture documents against their normative schemas."""
    assignments = {
        ROOT / "spec/protocol.schema.json": sorted(
            (ROOT / "tests/fixtures/protocol").glob("*.json")
        ),
        ROOT / "spec/relation.schema.json": sorted(
            (ROOT / "tests/fixtures/relations").glob("*.json")
        ),
    }
    errors: list[str] = []
    for schema_path, fixtures in assignments.items():
        schema = load_json(schema_path)
        validator = jsonschema.Draft202012Validator(schema)
        for fixture in fixtures:
            instance = load_json(fixture)
            instance_errors = sorted(
                validator.iter_errors(instance), key=lambda item: list(item.path)
            )
            for error in instance_errors:
                location = ".".join(str(piece) for piece in error.path) or "<root>"
                errors.append(f"{fixture.relative_to(ROOT)} at {location}: {error.message}")
    return errors


def validate_profiles() -> list[str]:
    """Check profile TOML documents for the shared public invariants."""
    errors: list[str] = []
    required = {
        "profile_version",
        "name",
        "semantic_version",
        "lanes",
        "secret_cells",
        "fault_mode",
        "bucket_width",
        "logical_query_budget",
        "physical_execution_budget",
        "max_program_instructions",
        "max_gas",
    }
    for path in sorted((ROOT / "benchmarks/profiles").glob("*.toml")):
        try:
            with path.open("rb") as handle:
                profile = tomllib.load(handle)
            missing = sorted(required.difference(profile))
            if missing:
                errors.append(f"{path.relative_to(ROOT)} missing keys {missing}")
            if profile.get("profile_version") != "1.0":
                errors.append(f"{path.relative_to(ROOT)} has unsupported profile_version")
            if not isinstance(profile.get("bucket_width"), int) or profile["bucket_width"] < 1:
                errors.append(f"{path.relative_to(ROOT)} has invalid bucket_width")
            if profile.get("server_diagnostics") is not False:
                errors.append(f"{path.relative_to(ROOT)} enables public diagnostics")
        except (OSError, tomllib.TOMLDecodeError) as error:
            errors.append(f"{path.relative_to(ROOT)}: {error}")
    return errors


def main() -> int:
    """Run all repository contract checks and return a process status."""
    errors = [
        *validate_schema_documents(),
        *validate_fixtures(),
        *validate_profiles(),
    ]
    if errors:
        print("schema/profile validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("validated schemas, protocol/relation fixtures, and public profiles")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
