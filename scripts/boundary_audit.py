#!/usr/bin/env python3
"""Audit the initial System A/System B process and response boundary."""

from __future__ import annotations

import ast
import hashlib
import os
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from sphinx_interrogator.protocol import ProtocolError, VmClient

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_IMPORT_ROOTS = {"ctypes", "sphinx_vm"}
FORBIDDEN_SOURCE_MARKERS = ("/proc/", "process_vm_readv", "ptrace(", "private/secret")
FORBIDDEN_RESPONSE_KEYS = {
    "secret",
    "bank",
    "phase",
    "replay_credit",
    "pending_probe",
    "fault_delta",
    "exact_cycles",
    "noise_sample",
}


def audit_python_sources() -> list[str]:
    """Reject imports and host-introspection markers that bypass the public protocol."""
    errors: list[str] = []
    for path in sorted((ROOT / "python/sphinx_interrogator").glob("*.py")):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                names = [node.module]
            for name in names:
                if name.split(".", maxsplit=1)[0] in FORBIDDEN_IMPORT_ROOTS:
                    errors.append(f"{path.relative_to(ROOT)} imports forbidden module {name}")
        lowered = source.lower()
        for marker in FORBIDDEN_SOURCE_MARKERS:
            if marker in lowered:
                errors.append(f"{path.relative_to(ROOT)} contains forbidden marker {marker!r}")
    return errors


def walk_keys(value: Any) -> set[str]:
    """Collect all serialized mapping keys from one public response model."""
    if isinstance(value, dict):
        return set(value).union(*(walk_keys(item) for item in value.values()))
    if isinstance(value, (list, tuple)):
        return set().union(*(walk_keys(item) for item in value))
    return set()


def audit_live_process(binary: Path) -> list[str]:
    """Exercise the target and reject internal fields in accepted public responses."""
    errors: list[str] = []
    profile = ROOT / "benchmarks/profiles/tutorial.toml"
    try:
        with VmClient.start(binary, profile=profile, timeout_seconds=2.0) as client:
            hello = client.hello()
            execution = client.execute(
                "PROBE 0, 0, 0\nANCHOR 0, 0\nHALT\n",
                session_id="boundary-audit",
                logical_batch_id="boundary-audit",
                reset="hard",
            )
    except (OSError, ProtocolError) as error:
        return [f"live boundary audit failed: {error}"]

    keys = walk_keys(asdict(hello)) | walk_keys(asdict(execution))
    leaked = sorted(keys.intersection(FORBIDDEN_RESPONSE_KEYS))
    if leaked:
        errors.append(f"public response contains forbidden internal fields: {leaked}")
    digest = hashlib.sha256(binary.read_bytes()).hexdigest()
    print(f"audited target binary sha256={digest}")
    return errors


def main() -> int:
    """Run static and live boundary checks with a meaningful exit status."""
    configured = os.environ.get("SPHINX_VM_BINARY")
    if configured is None:
        print("SPHINX_VM_BINARY is required", file=sys.stderr)
        return 2
    binary = Path(configured).resolve()
    errors = [*audit_python_sources()]
    if not binary.is_file():
        errors.append(f"target binary does not exist: {binary}")
    else:
        errors.extend(audit_live_process(binary))
    if errors:
        print("boundary audit failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("boundary audit passed: System B used only typed public process responses")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
