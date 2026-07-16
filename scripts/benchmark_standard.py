#!/usr/bin/env python3
"""Run the reproducible standard-profile benchmark and baseline matrix."""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import subprocess
import sys
import time
import tomllib
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import jsonschema

from sphinx_interrogator.standard import StandardSelectorMode, recover_standard

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MATRIX = ROOT / "benchmarks/matrices/standard.toml"
REFERENCE_FAULTS = ("reference", "weak", "signed")
ALL_VARIANTS = tuple(mode.value for mode in StandardSelectorMode)


def parse_args() -> argparse.Namespace:
    """Parse benchmark selection and resume options."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--seeds", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "runs/standard-benchmark-v1")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--variants", nargs="+", choices=ALL_VARIANTS)
    parser.add_argument("--faults", nargs="+", choices=REFERENCE_FAULTS, default=("reference",))
    parser.add_argument(
        "--skip-off-control",
        action="store_true",
        help="omit the full-selector fault-free negative-control campaigns",
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="run an explicit one-seed full-selector smoke matrix",
    )
    parser.add_argument(
        "--require-full-targets",
        action="store_true",
        help="fail unless the selected run is the full published acceptance matrix",
    )
    return parser.parse_args()


def main() -> int:
    """Execute selected campaigns, write JSON/Markdown aggregate reports, and return status."""
    args = parse_args()
    configured = os.environ.get("SPHINX_VM_BINARY")
    if configured is None:
        print("SPHINX_VM_BINARY is required", file=sys.stderr)
        return 2
    binary = Path(configured).resolve()
    if not binary.is_file():
        print(f"SphinxVM binary does not exist: {binary}", file=sys.stderr)
        return 2
    matrix = _load_matrix(args.matrix)
    seed_file = args.seeds or _root_relative_path(_string(matrix, "seed_file"))
    published_seeds = _load_seeds(seed_file)
    seeds = published_seeds
    variants = list(args.variants or _string_list(matrix, "variants"))
    if args.smoke:
        seeds = seeds[:1]
        variants = [StandardSelectorMode.FULL.value]
    if args.limit is not None:
        if args.limit < 1:
            raise ValueError("--limit must be positive")
        seeds = seeds[: args.limit]
    if not variants:
        raise ValueError("at least one selector variant is required")

    output = args.output.resolve()
    (output / "challenges").mkdir(parents=True, exist_ok=True)
    (output / "runs").mkdir(parents=True, exist_ok=True)
    results: list[dict[str, object]] = []
    campaign_plan = _campaign_plan(
        variants,
        tuple(args.faults),
        seeds,
        include_off_control=not args.skip_off_control,
    )
    for index, (mode, fault, seed) in enumerate(campaign_plan, start=1):
        challenge_id = f"standard-{mode.value}-{fault}-{seed:05d}"
        challenge = output / "challenges" / f"{mode.value}-{fault}-seed-{seed:05d}"
        run = output / "runs" / f"{mode.value}-{fault}-seed-{seed:05d}"
        profile = (
            ROOT / "benchmarks/profiles/fault_free.toml"
            if fault == "off"
            else ROOT / "benchmarks/profiles/standard.toml"
        )
        _ensure_challenge(
            binary,
            profile=profile,
            output=challenge,
            challenge_id=challenge_id,
            seed=seed,
            fault=fault,
        )
        started = time.perf_counter()
        recovered = recover_standard(
            vm_binary=binary,
            challenge=challenge,
            run_directory=run,
            campaign_seed=_campaign_seed(mode, fault, seed),
            selector_mode=mode,
            submit_judge=fault != "off",
        )
        elapsed = time.perf_counter() - started
        report = recovered.report
        cost = _mapping(report, "cost")
        judge = report.get("judge")
        result = {
            "selector_mode": mode.value,
            "fault_assignment": fault,
            "seed": seed,
            "challenge_id": challenge_id,
            "status": recovered.status,
            "judge_accepted": None if judge is None else _boolean(judge, "accepted"),
            "remaining_secret_candidates": _integer(report, "remaining_secret_candidates"),
            "cost": {
                "logical_relation_families": _integer(cost, "logical_relation_families"),
                "physical_executions": _integer(cost, "physical_executions"),
                "hard_resets": _integer(cost, "hard_resets"),
                "last_public_physical_remaining": cost.get("last_public_physical_remaining"),
            },
            "run": _portable_path(run, output),
        }
        results.append(result)
        print(
            "["
            f"{index:04d}/{len(campaign_plan):04d}] "
            f"mode={mode.value} fault={fault} seed={seed} "
            f"status={recovered.status} elapsed={elapsed:.2f}s",
            flush=True,
        )

    summaries = _summaries(results)
    selected_ok = _selected_thresholds_met(summaries)
    full_matrix = _is_full_published_matrix(
        variants=variants,
        faults=tuple(args.faults),
        seed_count=len(seeds),
        published_seed_count=len(published_seeds),
        off_control=not args.skip_off_control,
    )
    report = {
        "report_version": "1.0",
        "matrix_name": _string(matrix, "name"),
        "profile_name": "standard",
        "seed_file": _portable_path(seed_file.resolve(), ROOT),
        "variants": variants,
        "reference_faults": list(args.faults),
        "off_control": not args.skip_off_control,
        "campaigns": len(results),
        "acceptance": _acceptance(
            summaries,
            selected_seed_count=len(seeds),
            published_seed_count=len(published_seeds),
            full_published_matrix=full_matrix,
            selected_thresholds_met=selected_ok,
        ),
        "summaries": summaries,
        "results": results,
        "artifacts": {
            "challenges": "challenges",
            "runs": "runs",
            "markdown_report": "standard-benchmark-report.md",
        },
    }
    schema = json.loads(
        (ROOT / "spec/standard-benchmark-report.schema.json").read_text(encoding="utf-8")
    )
    jsonschema.Draft202012Validator(schema).validate(report)
    _write_json(output / "standard-benchmark-report.json", report)
    _write_markdown(output / "standard-benchmark-report.md", report)
    print(json.dumps(report["acceptance"], indent=2, sort_keys=True))
    required_success = (
        report["acceptance"]["targets_met"] if args.require_full_targets else selected_ok
    )
    return 0 if required_success else 1


def _campaign_plan(
    variants: Iterable[str],
    faults: tuple[str, ...],
    seeds: Iterable[int],
    *,
    include_off_control: bool,
) -> list[tuple[StandardSelectorMode, str, int]]:
    plan: list[tuple[StandardSelectorMode, str, int]] = []
    for variant in variants:
        mode = StandardSelectorMode(variant)
        for fault in faults:
            for seed in seeds:
                plan.append((mode, fault, seed))
    if include_off_control and StandardSelectorMode.FULL.value in set(variants):
        for seed in seeds:
            plan.append((StandardSelectorMode.FULL, "off", seed))
    return plan


def _ensure_challenge(
    binary: Path,
    *,
    profile: Path,
    output: Path,
    challenge_id: str,
    seed: int,
    fault: str,
) -> None:
    if (output / "public/challenge.json").is_file():
        return
    if output.exists() and any(output.iterdir()):
        raise RuntimeError(f"challenge directory is partial or incompatible: {output}")
    if output.exists():
        output.rmdir()
    output.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [
            str(binary),
            "challenge",
            "create",
            "--profile",
            str(profile),
            "--output",
            str(output),
            "--challenge-id",
            challenge_id,
            "--seed",
            str(seed),
            "--fault",
            fault,
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"standard challenge creation failed for {challenge_id}: {completed.stderr.strip()}"
        )


def _summaries(results: list[dict[str, object]]) -> list[dict[str, object]]:
    summaries = []
    keys = sorted(
        {
            (_string(result, "selector_mode"), _string(result, "fault_assignment"))
            for result in results
        }
    )
    for mode, fault in keys:
        group = [
            result
            for result in results
            if result["selector_mode"] == mode and result["fault_assignment"] == fault
        ]
        logical = [
            _integer(_mapping(result, "cost"), "logical_relation_families") for result in group
        ]
        physical = [_integer(_mapping(result, "cost"), "physical_executions") for result in group]
        unique_exact = sum(result["status"] == "unique_exact" for result in group)
        judge_accepted = sum(result["judge_accepted"] is True for result in group)
        false_exact = sum(fault == "off" and result["status"] == "unique_exact" for result in group)
        summaries.append(
            {
                "selector_mode": mode,
                "fault_assignment": fault,
                "campaigns": len(group),
                "unique_exact": unique_exact,
                "judge_accepted": judge_accepted,
                "false_exact": false_exact,
                "exact_rate": unique_exact / len(group),
                "median_logical_relation_families": float(statistics.median(logical)),
                "p95_logical_relation_families": float(_percentile(logical, 0.95)),
                "max_logical_relation_families": max(logical),
                "median_physical_executions": float(statistics.median(physical)),
                "max_physical_executions": max(physical),
            }
        )
    return summaries


def _acceptance(
    summaries: list[dict[str, object]],
    *,
    selected_seed_count: int,
    published_seed_count: int,
    full_published_matrix: bool,
    selected_thresholds_met: bool,
) -> dict[str, object]:
    reference = _find_summary(summaries, StandardSelectorMode.FULL.value, "reference")
    off = _find_summary(summaries, StandardSelectorMode.FULL.value, "off")
    full_targets_met = selected_thresholds_met and full_published_matrix
    return {
        "selected_seed_count": selected_seed_count,
        "published_seed_count": published_seed_count,
        "full_published_matrix": full_published_matrix,
        "selected_thresholds_met": selected_thresholds_met,
        "full_reference_exact_rate": None if reference is None else reference["exact_rate"],
        "full_reference_median_logical": (
            None if reference is None else reference["median_logical_relation_families"]
        ),
        "full_reference_p95_logical": (
            None if reference is None else reference["p95_logical_relation_families"]
        ),
        "full_reference_median_physical": (
            None if reference is None else reference["median_physical_executions"]
        ),
        "off_false_exact_declarations": None if off is None else off["false_exact"],
        "targets_met": full_targets_met,
    }


def _selected_thresholds_met(summaries: list[dict[str, object]]) -> bool:
    reference = _find_summary(summaries, StandardSelectorMode.FULL.value, "reference")
    if reference is None:
        return False
    off = _find_summary(summaries, StandardSelectorMode.FULL.value, "off")
    off_false_exact = 0 if off is None else _integer(off, "false_exact")
    return (
        float(reference["exact_rate"]) >= 0.95
        and float(reference["median_logical_relation_families"]) <= 180.0
        and float(reference["p95_logical_relation_families"]) <= 300.0
        and float(reference["median_physical_executions"]) <= 3000.0
        and off_false_exact == 0
    )


def _is_full_published_matrix(
    *,
    variants: list[str],
    faults: tuple[str, ...],
    seed_count: int,
    published_seed_count: int,
    off_control: bool,
) -> bool:
    return (
        seed_count == published_seed_count
        and published_seed_count >= 100
        and set(variants) == set(ALL_VARIANTS)
        and tuple(faults) == ("reference",)
        and off_control
    )


def _find_summary(
    summaries: list[dict[str, object]],
    mode: str,
    fault: str,
) -> dict[str, object] | None:
    for summary in summaries:
        if summary["selector_mode"] == mode and summary["fault_assignment"] == fault:
            return summary
    return None


def _campaign_seed(mode: StandardSelectorMode, fault: str, seed: int) -> int:
    fault_index = ("reference", "weak", "signed", "off").index(fault)
    return 600_000 + seed + 1009 * list(StandardSelectorMode).index(mode) + 7919 * fault_index


def _percentile(values: list[int], fraction: float) -> int:
    if not values:
        raise ValueError("percentile requires at least one value")
    ordered = sorted(values)
    index = max(0, math.ceil(fraction * len(ordered)) - 1)
    return ordered[index]


def _load_matrix(path: Path) -> Mapping[str, object]:
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    if not isinstance(data, dict):
        raise ValueError("standard benchmark matrix is not a TOML table")
    return data


def _load_seeds(path: Path) -> list[int]:
    values = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            value = int(stripped)
            if value < 0:
                raise ValueError("standard seeds must be nonnegative")
            values.append(value)
    if not values or len(set(values)) != len(values):
        raise ValueError("standard seed file must be nonempty and unique")
    return values


def _write_json(path: Path, data: object) -> None:
    temporary = path.with_suffix(f".tmp-{os.getpid()}")
    temporary.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _write_markdown(path: Path, report: Mapping[str, object]) -> None:
    lines = [
        "# Standard Benchmark Report",
        "",
        f"- Matrix: `{report['matrix_name']}`",
        f"- Campaigns: `{report['campaigns']}`",
        f"- Targets met: `{_mapping(report, 'acceptance')['targets_met']}`",
        "",
        "| selector | fault | campaigns | exact rate | median logical | "
        "p95 logical | median physical | false exact |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    summaries = report.get("summaries")
    if not isinstance(summaries, list):
        raise TypeError("report summaries must be a list")
    for item in summaries:
        if not isinstance(item, dict):
            raise TypeError("summary item must be an object")
        lines.append(
            "| "
            f"{item['selector_mode']} | {item['fault_assignment']} | {item['campaigns']} | "
            f"{float(item['exact_rate']):.3f} | "
            f"{float(item['median_logical_relation_families']):.1f} | "
            f"{float(item['p95_logical_relation_families']):.1f} | "
            f"{float(item['median_physical_executions']):.1f} | "
            f"{item['false_exact']} |"
        )
    temporary = path.with_suffix(f".tmp-{os.getpid()}")
    temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _portable_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _root_relative_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _string(data: Mapping[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise TypeError(f"{key} must be a nonempty string")
    return value


def _string_list(data: Mapping[str, object], key: str) -> list[str]:
    value = data.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise TypeError(f"{key} must be a list of strings")
    return value


def _mapping(data: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise TypeError(f"{key} must be an object")
    return value


def _integer(data: Mapping[str, object], key: str) -> int:
    value = data.get(key)
    if not isinstance(value, int):
        raise TypeError(f"{key} must be an integer")
    return value


def _boolean(data: Any, key: str) -> bool:
    if not isinstance(data, dict):
        raise TypeError("expected object")
    value = data.get(key)
    if not isinstance(value, bool):
        raise TypeError(f"{key} must be a boolean")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
