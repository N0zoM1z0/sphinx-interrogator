#!/usr/bin/env python3
"""Generate, recover, judge, persist, and print one deterministic tutorial run."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path

from sphinx_interrogator.tutorial import recover_tutorial

ROOT = Path(__file__).resolve().parents[1]
SEED = 7
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
    run_directory = ROOT / "runs/tutorial-demo-v2-seed-7"
    with tempfile.TemporaryDirectory(prefix="sphinx-tutorial-demo-") as temporary:
        challenge = Path(temporary) / "challenge"
        created = subprocess.run(
            [
                str(binary),
                "challenge",
                "create",
                "--profile",
                str(ROOT / "benchmarks/profiles/tutorial.toml"),
                "--output",
                str(challenge),
                "--challenge-id",
                "tutorial-demo-seed-7",
                "--seed",
                str(SEED),
                "--fault",
                "reference",
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
        )
        if created.returncode != 0:
            print(created.stderr.strip(), file=sys.stderr)
            return 1
        result = recover_tutorial(
            vm_binary=binary,
            challenge=challenge,
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
