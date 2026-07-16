#!/usr/bin/env python3
"""Run the published tutorial seed matrix through the real black-box process."""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import tempfile
from pathlib import Path

from sphinx_interrogator.tutorial import recover_tutorial
from sphinx_trusted_runtime import create_challenge, create_private_root, launch_endpoints

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
        challenge_id = f"challenge-{index:04d}"
        private_root = ROOT / "runs/.private-roots/tutorial-matrix" / f"seed-{seed:04d}.root"
        if not private_root.exists():
            create_private_root(binary, private_root)
        with tempfile.TemporaryDirectory(prefix="sphinx-tutorial-matrix-") as temporary:
            temporary_root = Path(temporary)
            bundle = create_challenge(
                binary,
                profile=ROOT / "benchmarks/profiles/tutorial.toml",
                root=temporary_root / "challenge",
                private_root_file=private_root,
                challenge_id=challenge_id,
                campaign_label=f"campaign-{args.fault}-{index:04d}",
                fault=args.fault,
            )
            run = output / f"seed-{seed:03d}"
            with launch_endpoints(
                binary,
                bundle,
                socket_directory=temporary_root / "sockets",
                with_judge=args.fault == "reference",
            ) as endpoints:
                recovered = recover_tutorial(
                    public_challenge=endpoints.public_directory,
                    vm_socket=endpoints.vm_socket,
                    judge_socket=endpoints.judge_socket,
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
    expected = "unique_exact" if args.fault == "reference" else "candidate_set"
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
