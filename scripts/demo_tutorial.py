#!/usr/bin/env python3
"""Generate, recover, judge, persist, and print one deterministic tutorial run."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path

from sphinx_interrogator.tutorial import recover_tutorial
from sphinx_trusted_runtime import create_challenge, create_private_root, launch_endpoints

ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN_SEED = 17


def main() -> int:
    """Execute the real M5 acceptance flow against a temporary private challenge."""
    configured = os.environ.get("SPHINX_VM_BINARY")
    if configured is None:
        print("SPHINX_VM_BINARY is required", file=sys.stderr)
        return 2
    binary = Path(configured).resolve()
    if not binary.is_file():
        print(f"SphinxVM binary does not exist: {binary}", file=sys.stderr)
        return 2
    run_directory = ROOT / "runs/tutorial-demo-v3"
    private_root = ROOT / "runs/.private-roots/tutorial-demo-v3.root"
    if not private_root.exists():
        create_private_root(binary, private_root)
    with tempfile.TemporaryDirectory(prefix="sphinx-tutorial-demo-") as temporary:
        temporary_root = Path(temporary)
        bundle = create_challenge(
            binary,
            profile=ROOT / "benchmarks/profiles/tutorial.toml",
            root=temporary_root / "challenge",
            private_root_file=private_root,
            challenge_id="challenge-0001",
            campaign_label="campaign-0001",
            fault="reference",
        )
        with launch_endpoints(
            binary,
            bundle,
            socket_directory=temporary_root / "sockets",
            with_judge=True,
        ) as endpoints:
            result = recover_tutorial(
                public_challenge=endpoints.public_directory,
                vm_socket=endpoints.vm_socket,
                judge_socket=endpoints.judge_socket,
                run_directory=run_directory,
                campaign_seed=CAMPAIGN_SEED,
                submit_judge=True,
            )
    cost = _mapping(result.report, "cost")
    judge = _mapping(result.report, "judge")
    output = {
        "status": result.status,
        "run_directory": str(result.run_directory.relative_to(ROOT)),
        "unique_secret_hex": result.report["unique_secret_hex"],
        "logical_relation_families": cost["logical_relation_families"],
        "judge_accepted": judge["accepted"],
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return int(result.status != "unique_exact")


def _mapping(data: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise RuntimeError(f"tutorial report field {key} is not an object")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
