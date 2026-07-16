#!/usr/bin/env python3
"""Run the published tutorial seed matrix through the real black-box process."""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

from sphinx_interrogator.tutorial import recover_tutorial

ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    """Parse explicit matrix inputs."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--seeds",
        type=Path,
        default=ROOT / "benchmarks/seeds/tutorial-evaluation.txt",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fault", choices=("reference", "off"), default="reference")
    parser.add_argument("--limit", type=int)
    return parser.parse_args()


def main() -> int:
    """Execute all selected seeds and write one aggregate public summary."""
    args = parse_args()
    configured = os.environ.get("SPHINX_VM_BINARY")
    if configured is None:
        print("SPHINX_VM_BINARY is required", file=sys.stderr)
        return 2
    binary = Path(configured).resolve()
    seeds = _load_seeds(args.seeds)
    if args.limit is not None:
        if args.limit < 1:
            raise ValueError("--limit must be positive")
        seeds = seeds[: args.limit]
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, object]] = []
    for index, seed in enumerate(seeds, start=1):
        challenge_id = f"tutorial-eval-{args.fault}-{seed:03d}"
        with tempfile.TemporaryDirectory(prefix="sphinx-tutorial-matrix-") as temporary:
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
                    challenge_id,
                    "--seed",
                    str(seed),
                    "--fault",
                    args.fault,
                ],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=10,
            )
            if created.returncode != 0:
                raise RuntimeError(f"challenge seed {seed} failed: {created.stderr.strip()}")
            run = output / f"seed-{seed:03d}"
            recovered = recover_tutorial(
                vm_binary=binary,
                challenge=challenge,
                run_directory=run,
                campaign_seed=10_000 + seed,
                submit_judge=args.fault == "reference",
            )
        cost = recovered.report.get("cost")
        if not isinstance(cost, dict):
            raise RuntimeError("tutorial report lacks a cost object")
        result = {
            "seed": seed,
            "status": recovered.status,
            "logical_relation_families": cost["logical_relation_families"],
            "physical_executions": cost["physical_executions"],
            "run": str(run.relative_to(output)),
        }
        results.append(result)
        print(
            f"[{index:03d}/{len(seeds):03d}] seed={seed} status={recovered.status}",
            flush=True,
        )

    logical = [int(result["logical_relation_families"]) for result in results]
    expected = "unique_exact" if args.fault == "reference" else "inconclusive"
    successes = sum(result["status"] == expected for result in results)
    summary = {
        "matrix_version": "1.0",
        "profile_name": "tutorial",
        "fault_assignment": args.fault,
        "seed_file": _portable_path(args.seeds.resolve()),
        "campaigns": len(results),
        "expected_status": expected,
        "matching_statuses": successes,
        "success_rate": successes / len(results),
        "median_logical_relation_families": statistics.median(logical),
        "maximum_logical_relation_families": max(logical),
        "results": results,
    }
    _write_json(output / "summary.json", summary)
    print(json.dumps({key: value for key, value in summary.items() if key != "results"}, indent=2))
    return int(successes != len(results))


def _load_seeds(path: Path) -> list[int]:
    values = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            value = int(stripped)
            if value < 0:
                raise ValueError("tutorial seeds must be nonnegative")
            values.append(value)
    if not values or len(set(values)) != len(values):
        raise ValueError("tutorial seed file must be nonempty and unique")
    return values


def _portable_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _write_json(path: Path, data: object) -> None:
    temporary = path.with_suffix(f".tmp-{os.getpid()}")
    temporary.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


if __name__ == "__main__":
    raise SystemExit(main())
