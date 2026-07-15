#!/usr/bin/env python3
"""Audit the initial System A/System B process and response boundary."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import tomllib
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
FORBIDDEN_PUBLIC_KEYS = {
    "secret",
    "permutation",
    "salts",
    "fault_variant",
    "generation_root_seed",
    "generation_root_seed_hex",
    "noise_key",
    "noise_key_hex",
    "commitment_nonce",
    "commitment_nonce_hex",
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
        with tempfile.TemporaryDirectory(prefix="sphinx-boundary-") as temporary:
            challenge = Path(temporary) / "challenge"
            generated = subprocess.run(
                [
                    str(binary),
                    "challenge",
                    "create",
                    "--profile",
                    str(profile),
                    "--output",
                    str(challenge),
                    "--challenge-id",
                    "boundary-audit",
                    "--seed",
                    "7001",
                    "--fault",
                    "reference",
                ],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=5,
            )
            if generated.returncode != 0:
                return [f"challenge generation failed: {generated.stderr.strip()}"]
            public_metadata = json_load(challenge / "public/challenge.json")
            with (challenge / "public/profile.toml").open("rb") as handle:
                public_profile = tomllib.load(handle)
            leaked_public = sorted(
                (walk_keys(public_metadata) | walk_keys(public_profile)).intersection(
                    FORBIDDEN_PUBLIC_KEYS
                )
            )
            if leaked_public:
                errors.append(f"public challenge artifacts contain private fields: {leaked_public}")
            if os.name == "posix":
                expected_modes = {
                    challenge / "private": 0o700,
                    challenge / "private/judge-used": 0o700,
                    challenge / "private/secret.bin": 0o600,
                    challenge / "private/config.toml": 0o600,
                    challenge / "public": 0o755,
                    challenge / "public/profile.toml": 0o644,
                    challenge / "public/challenge.json": 0o644,
                }
                for path, expected in expected_modes.items():
                    actual = path.stat().st_mode & 0o777
                    if actual != expected:
                        errors.append(
                            f"challenge path {path.relative_to(challenge)} has mode "
                            f"{actual:o}, expected {expected:o}"
                        )
            with VmClient.start(binary, challenge=challenge, timeout_seconds=2.0) as client:
                hello = client.hello()
                execution = client.execute(
                    "PROBE 0, 0, 0\nANCHOR 0, 0\nHALT\n",
                    session_id="boundary-audit",
                    logical_batch_id="boundary-audit",
                    reset="hard",
                )
    except (OSError, ProtocolError, subprocess.TimeoutExpired) as error:
        return [f"live boundary audit failed: {error}"]

    keys = walk_keys(asdict(hello)) | walk_keys(asdict(execution))
    leaked = sorted(keys.intersection(FORBIDDEN_RESPONSE_KEYS))
    if leaked:
        errors.append(f"public response contains forbidden internal fields: {leaked}")
    digest = hashlib.sha256(binary.read_bytes()).hexdigest()
    print(f"audited target binary sha256={digest}")
    return errors


def json_load(path: Path) -> Any:
    """Load one public JSON document for the external boundary audit."""
    return json.loads(path.read_text(encoding="utf-8"))


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
