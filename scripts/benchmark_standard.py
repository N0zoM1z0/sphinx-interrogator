#!/usr/bin/env python3
"""Run the reproducible standard-profile benchmark and baseline matrix."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import statistics
import sys
import time
import tomllib
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import jsonschema

from sphinx_interrogator.certificates import ProofMethod
from sphinx_interrogator.persistence import (
    CampaignManifest,
    CampaignRepository,
    CampaignResultStatus,
    normalize_campaign_result_status,
)
from sphinx_interrogator.protocol import submit_judge as submit_judge_request
from sphinx_interrogator.standard import StandardSelectorMode, recover_standard
from sphinx_trusted_runtime import (
    ChallengeBundle,
    create_challenge,
    create_private_root,
    launch_endpoints,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MATRIX = ROOT / "benchmarks/matrices/standard.toml"
DEFAULT_UPPER_BOUND_ARTIFACT = ROOT / "runs/standard-profile-audit-m7/standard-profile-audit.json"
REFERENCE_FAULTS = ("reference", "weak", "signed")
RANDOM_FINAL_GUESS_VARIANT = "random_final_guess"
ALL_BLACK_BOX_VARIANTS = tuple(mode.value for mode in StandardSelectorMode)
ALL_VARIANTS = (RANDOM_FINAL_GUESS_VARIANT, *ALL_BLACK_BOX_VARIANTS)
BOOTSTRAP_METRICS = (
    "exact_rate",
    "logical_relation_families",
    "physical_executions",
)
PAIRED_DELTA_METRICS = (
    "exact_success_delta",
    "logical_relation_families_delta",
    "physical_executions_delta",
)
BASELINE_DEFINITIONS = (
    ("B0", "random-final-guess", RANDOM_FINAL_GUESS_VARIANT),
    ("B1", "random-valid-probes", StandardSelectorMode.RANDOM.value),
    ("B2", "stateless-metamorphic-testing", StandardSelectorMode.STATELESS.value),
    ("B3", "knowledge-base-without-synthesis", StandardSelectorMode.KB_NO_SYNTHESIS.value),
    ("B4", "synthesis-without-kb-selection", StandardSelectorMode.SYNTHESIS_NO_KB.value),
    ("B5", "without-active-state-learning", None),
    ("B6", "without-robust-sequential-sampling", None),
    ("B7", "whitebox-greedy-oracle-upper-bound", None),
)


def parse_args() -> argparse.Namespace:
    """Parse benchmark selection and resume options."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--seeds", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "runs/standard-benchmark-v2")
    parser.add_argument(
        "--socket-root",
        type=Path,
        help="short runtime directory for VM/judge Unix sockets",
    )
    parser.add_argument("--upper-bound-artifact", type=Path, default=DEFAULT_UPPER_BOUND_ARTIFACT)
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
    parser.add_argument(
        "--bootstrap-samples",
        type=int,
        default=2000,
        help="paired seed-level bootstrap resamples to record in the aggregate report",
    )
    parser.add_argument(
        "--bootstrap-seed",
        type=int,
        default=901_337,
        help="deterministic seed for paired bootstrap confidence intervals",
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
    if args.bootstrap_samples < 1:
        raise ValueError("--bootstrap-samples must be positive")

    output = args.output.resolve()
    campaign_namespace = hashlib.sha256(str(output).encode()).hexdigest()[:16]
    (output / "runs").mkdir(parents=True, exist_ok=True)
    trusted_root = ROOT / "runs/.trusted-standard-v2"
    trusted_root.mkdir(parents=True, exist_ok=True)
    socket_root = (args.socket_root if args.socket_root is not None else trusted_root).resolve()
    socket_root.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, object]] = []
    campaign_plan = _campaign_plan(
        variants,
        tuple(args.faults),
        seeds,
        include_off_control=not args.skip_off_control,
    )
    for index, (mode, fault, seed) in enumerate(campaign_plan, start=1):
        seed_ordinal = seeds.index(seed) + 1
        challenge_id = f"challenge-{seed_ordinal:04d}"
        private_root = trusted_root / f"root-{seed_ordinal:04d}.bin"
        if not private_root.exists():
            create_private_root(binary, private_root)
        opaque_campaign = _opaque_campaign_id(
            campaign_namespace,
            mode,
            fault,
            seed,
        )
        challenge = trusted_root / f"bundle-{opaque_campaign}"
        run = output / "runs" / f"{mode}-{fault}-seed-{seed:05d}"
        bundle = _ensure_challenge(
            binary,
            profile=ROOT / "benchmarks/profiles/standard.toml",
            output=challenge,
            private_root_file=private_root,
            challenge_id=challenge_id,
            campaign_label=f"campaign-{opaque_campaign}",
            fault=fault,
        )
        started = time.perf_counter()
        socket_directory = socket_root / f"sockets-{opaque_campaign}"
        with launch_endpoints(
            binary,
            bundle,
            socket_directory=socket_directory,
            with_judge=fault != "off",
        ) as endpoints:
            if mode == RANDOM_FINAL_GUESS_VARIANT:
                if endpoints.judge_socket is None:
                    raise RuntimeError("B0 random final guess requires a judge endpoint")
                recovered_status, report = _recover_random_final_guess(
                    public_challenge=endpoints.public_directory,
                    judge_socket=endpoints.judge_socket,
                    run_directory=run,
                    campaign_seed=_campaign_seed(seed),
                )
            else:
                recovered = recover_standard(
                    public_challenge=endpoints.public_directory,
                    vm_socket=endpoints.vm_socket,
                    judge_socket=endpoints.judge_socket,
                    run_directory=run,
                    campaign_seed=_campaign_seed(seed),
                    selector_mode=StandardSelectorMode(mode),
                    submit_judge=fault != "off",
                )
                recovered_status = recovered.status
                report = recovered.report
        elapsed = time.perf_counter() - started
        cost = _mapping(report, "cost")
        judge = report.get("judge")
        result = {
            "selector_mode": mode,
            "fault_assignment": fault,
            "seed": seed,
            "challenge_id": challenge_id,
            "status": recovered_status,
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
            f"mode={mode} fault={fault} seed={seed} "
            f"status={recovered_status} elapsed={elapsed:.2f}s",
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
        "report_version": "1.1",
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
        "paired_bootstrap_confidence_intervals": _paired_bootstrap_confidence_intervals(
            results,
            samples=args.bootstrap_samples,
            seed=args.bootstrap_seed,
            confidence_level=0.95,
        ),
        "baseline_surface": _baseline_surface(
            results,
            variants=variants,
            upper_bound_artifact=args.upper_bound_artifact,
        ),
        "summaries": summaries,
        "results": results,
        "artifacts": {
            "runs": "runs",
            "markdown_report": "standard-benchmark-report.md",
            "private_challenges_included": False,
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
) -> list[tuple[str, str, int]]:
    plan: list[tuple[str, str, int]] = []
    selected_modes = tuple(variants)
    for seed in seeds:
        for fault in faults:
            paired = [(mode, fault, seed) for mode in selected_modes]
            random.Random(_campaign_seed(seed)).shuffle(paired)
            plan.extend(paired)
        if include_off_control and StandardSelectorMode.FULL.value in selected_modes:
            plan.append((StandardSelectorMode.FULL.value, "off", seed))
    return plan


def _recover_random_final_guess(
    *,
    public_challenge: Path,
    judge_socket: Path,
    run_directory: Path,
    campaign_seed: int,
) -> tuple[str, Mapping[str, object]]:
    report_path = run_directory / "report.json"
    public = _load_json(public_challenge / "challenge.json")
    if report_path.is_file():
        existing = _load_json(report_path)
        existing_status = _string(existing, "status")
        normative_status = normalize_campaign_result_status(existing_status)
        if existing_status != normative_status.value:
            existing = dict(existing)
            existing["status"] = normative_status.value
            _write_json(report_path, existing)
        _ensure_random_final_guess_manifest(
            public_challenge=public_challenge,
            run_directory=run_directory,
            campaign_seed=campaign_seed,
            report=existing,
        )
        return normative_status.value, existing
    run_directory.mkdir(parents=True, exist_ok=True)
    profile = _load_matrix(public_challenge / "profile.toml")
    secret_cells = _integer(profile, "secret_cells")
    guess = _deterministic_guess(campaign_seed, secret_cells)
    judge = submit_judge_request(
        judge_socket,
        campaign_token=_string(public, "campaign_token"),
        guess=guess,
    )
    accepted = _boolean(judge, "accepted")
    status = (
        CampaignResultStatus.UNIQUE_EXACT.value
        if accepted
        else CampaignResultStatus.CANDIDATE_SET.value
    )
    report: dict[str, object] = {
        "report_version": "1.0",
        "campaign_seed": campaign_seed,
        "selector_mode": RANDOM_FINAL_GUESS_VARIANT,
        "status": status,
        "unique_secret_hex": guess if accepted else None,
        "remaining_secret_candidates": 1 if accepted else 16**secret_cells,
        "cost": {
            "logical_relation_families": 0,
            "physical_executions": 0,
            "hard_resets": 0,
            "last_public_physical_remaining": None,
        },
        "evidence": {
            "baseline_id": "B0",
            "method": "deterministic-public-seed-final-guess/v1",
            "black_box_queries": 0,
            "uses_private_state": False,
        },
        "judge": dict(judge),
    }
    _write_json(report_path, report)
    _ensure_random_final_guess_manifest(
        public_challenge=public_challenge,
        run_directory=run_directory,
        campaign_seed=campaign_seed,
        report=report,
    )
    return status, report


def _ensure_random_final_guess_manifest(
    *,
    public_challenge: Path,
    run_directory: Path,
    campaign_seed: int,
    report: Mapping[str, object],
) -> None:
    public = _load_json(public_challenge / "challenge.json")
    budgets = _mapping(public, "budgets")
    challenge_id = _string(public, "challenge_id")
    status = _string(report, "status")
    manifest = CampaignManifest(
        campaign_id=f"standard-{RANDOM_FINAL_GUESS_VARIANT}-{challenge_id}-{campaign_seed}",
        challenge_id=challenge_id,
        challenge_commitment=_string(public, "commitment"),
        profile_name="standard",
        semantic_version="0.1.0",
        public_profile_sha256=_file_sha256(public_challenge / "profile.toml"),
        seed=campaign_seed,
        minimum_certificate_strength=ProofMethod.EMPIRICAL_ONLY.value,
        logical_query_budget=_integer(budgets, "logical_queries"),
        physical_execution_budget=_integer(budgets, "physical_executions"),
        hard_reset_budget=_integer(budgets, "hard_resets"),
    )
    repository = CampaignRepository.create(run_directory, manifest)
    try:
        judge = _mapping(report, "judge")
        if repository.database.table_count("judge_submissions") == 0:
            repository.append_event(
                event_id="judge:random-final-guess",
                kind="judge_recorded",
                logical_time=0,
                payload={
                    "submission_id": "random-final-guess",
                    "challenge_id": challenge_id,
                    "submission_recorded": _boolean(judge, "submission_recorded"),
                    "accepted": _boolean(judge, "accepted"),
                    "response": dict(judge),
                },
            )
        if repository.manifest.to_data()["manifest_version"] != "1.2":
            repository.finalize_manifest(
                status=normalize_campaign_result_status(status),
                artifact_paths={
                    "report.json": run_directory / "report.json",
                    "events.jsonl": run_directory / "events.jsonl",
                    "campaign.sqlite3": run_directory / "campaign.sqlite3",
                },
            )
    finally:
        repository.close()


def _deterministic_guess(seed: int, cells: int) -> str:
    rng = random.Random(f"standard-b0:{seed}")
    return "".join(f"{rng.randrange(16):x}" for _ in range(cells))


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _ensure_challenge(
    binary: Path,
    *,
    profile: Path,
    output: Path,
    private_root_file: Path,
    challenge_id: str,
    campaign_label: str,
    fault: str,
) -> ChallengeBundle:
    if (output / "public/challenge.json").is_file():
        return ChallengeBundle(
            output / "public",
            output / "private",
            private_root_file,
        )
    if output.exists() and any(output.iterdir()):
        raise RuntimeError(f"challenge directory is partial or incompatible: {output}")
    if output.exists():
        output.rmdir()
    return create_challenge(
        binary,
        profile=profile,
        root=output,
        private_root_file=private_root_file,
        challenge_id=challenge_id,
        campaign_label=campaign_label,
        fault=fault,
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


def _paired_bootstrap_confidence_intervals(
    results: list[dict[str, object]],
    *,
    samples: int,
    seed: int,
    confidence_level: float,
) -> dict[str, object]:
    if samples < 1:
        raise ValueError("bootstrap samples must be positive")
    if not 0.0 < confidence_level < 1.0:
        raise ValueError("confidence level must be between 0 and 1")
    rng = random.Random(seed)
    metrics: list[dict[str, object]] = []
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
        for metric in BOOTSTRAP_METRICS:
            values = _metric_values(group, metric)
            interval = _bootstrap_interval(
                values,
                samples=samples,
                confidence_level=confidence_level,
                rng=rng,
                statistic=_mean if metric == "exact_rate" else _median,
            )
            metrics.append(
                {
                    "selector_mode": mode,
                    "fault_assignment": fault,
                    "metric": metric,
                    "estimate": interval["estimate"],
                    "ci_low": interval["ci_low"],
                    "ci_high": interval["ci_high"],
                    "unit_count": len(values),
                }
            )
    return {
        "method": "paired-seed-percentile/v1",
        "unit": "challenge_seed",
        "confidence_level": confidence_level,
        "bootstrap_samples": samples,
        "seed": seed,
        "metrics": metrics,
        "comparisons": _paired_bootstrap_comparisons(
            results,
            samples=samples,
            confidence_level=confidence_level,
            rng=rng,
        ),
    }


def _paired_bootstrap_comparisons(
    results: list[dict[str, object]],
    *,
    samples: int,
    confidence_level: float,
    rng: random.Random,
) -> list[dict[str, object]]:
    comparisons: list[dict[str, object]] = []
    by_key = {
        (
            _string(result, "selector_mode"),
            _string(result, "fault_assignment"),
            _integer(result, "seed"),
        ): result
        for result in results
    }
    pair_keys = sorted(
        {
            (_string(result, "selector_mode"), _string(result, "fault_assignment"))
            for result in results
            if _string(result, "selector_mode") != StandardSelectorMode.FULL.value
        }
    )
    for baseline, fault in pair_keys:
        common_seeds = sorted(
            seed
            for mode, candidate_fault, seed in by_key
            if mode == StandardSelectorMode.FULL.value
            and candidate_fault == fault
            and (baseline, fault, seed) in by_key
        )
        if not common_seeds:
            continue
        for metric in PAIRED_DELTA_METRICS:
            deltas = [
                _paired_metric_delta(
                    by_key[(StandardSelectorMode.FULL.value, fault, paired_seed)],
                    by_key[(baseline, fault, paired_seed)],
                    metric,
                )
                for paired_seed in common_seeds
            ]
            interval = _bootstrap_interval(
                deltas,
                samples=samples,
                confidence_level=confidence_level,
                rng=rng,
                statistic=_mean,
            )
            comparisons.append(
                {
                    "variant": StandardSelectorMode.FULL.value,
                    "baseline": baseline,
                    "fault_assignment": fault,
                    "metric": metric,
                    "estimate": interval["estimate"],
                    "ci_low": interval["ci_low"],
                    "ci_high": interval["ci_high"],
                    "paired_seed_count": len(common_seeds),
                }
            )
    return comparisons


def _baseline_surface(
    results: list[dict[str, object]],
    *,
    variants: list[str],
    upper_bound_artifact: Path,
) -> dict[str, object]:
    entries: list[dict[str, object]] = []
    for baseline_id, name, selector in BASELINE_DEFINITIONS:
        if baseline_id in {"B5", "B6"}:
            entries.append(
                {
                    "baseline_id": baseline_id,
                    "name": name,
                    "status": "not_applicable",
                    "selector_mode": None,
                    "profile_scope": "research" if baseline_id == "B5" else "stochastic",
                    "evidence": {
                        "reason": (
                            "active state learning is evaluated in research mode"
                            if baseline_id == "B5"
                            else "robust sequential sampling is evaluated in stochastic profiles"
                        )
                    },
                }
            )
            continue
        if baseline_id == "B7":
            entries.append(_whitebox_upper_bound_entry(upper_bound_artifact))
            continue
        if selector is None:
            raise RuntimeError(f"baseline {baseline_id} has no selector mapping")
        matching_results = [
            result
            for result in results
            if result["selector_mode"] == selector and result["fault_assignment"] != "off"
        ]
        entries.append(
            {
                "baseline_id": baseline_id,
                "name": name,
                "status": "measured" if matching_results else "missing",
                "selector_mode": selector,
                "profile_scope": "standard",
                "evidence": {
                    "campaigns": len(matching_results),
                    "selected": selector in variants,
                    "fault_assignments": sorted(
                        {_string(result, "fault_assignment") for result in matching_results}
                    ),
                },
            }
        )
    required_ids = {f"B{index}" for index in range(8)}
    present_ids = {_string(entry, "baseline_id") for entry in entries}
    b0_b4_b7 = {"B0", "B1", "B2", "B3", "B4", "B7"}
    complete = (
        present_ids == required_ids
        and all(
            _string(entry, "status") == "measured"
            for entry in entries
            if _string(entry, "baseline_id") in b0_b4_b7
        )
        and all(
            _string(entry, "status") in {"measured", "not_applicable"}
            for entry in entries
            if _string(entry, "baseline_id") in {"B5", "B6"}
        )
    )
    return {
        "surface_version": "B0-B7/v1",
        "complete": complete,
        "entries": entries,
    }


def _whitebox_upper_bound_entry(path: Path) -> dict[str, object]:
    absolute = path if path.is_absolute() else ROOT / path
    if not absolute.is_file():
        return {
            "baseline_id": "B7",
            "name": "whitebox-greedy-oracle-upper-bound",
            "status": "missing",
            "selector_mode": None,
            "profile_scope": "development",
            "evidence": {"artifact": _portable_path(absolute, ROOT), "reason": "artifact missing"},
        }
    decoded = _load_json(absolute)
    targets = decoded.get("targets_met")
    passed = isinstance(targets, dict) and all(value is True for value in targets.values())
    learnability = decoded.get("learnability_bound")
    return {
        "baseline_id": "B7",
        "name": "whitebox-greedy-oracle-upper-bound",
        "status": "measured" if passed else "missing",
        "selector_mode": None,
        "profile_scope": "development",
        "evidence": {
            "artifact": _portable_path(absolute, ROOT),
            "analysis_scope": decoded.get("analysis_scope"),
            "uses_black_box_recovery": False,
            "targets_met": targets if isinstance(targets, dict) else {},
            "oracle_collision_logical_relations": (
                learnability.get("oracle_collision_logical_relations")
                if isinstance(learnability, dict)
                else None
            ),
        },
    }


def _metric_values(group: list[dict[str, object]], metric: str) -> list[float]:
    if metric == "exact_rate":
        return [1.0 if result["status"] == "unique_exact" else 0.0 for result in group]
    if metric == "logical_relation_families":
        return [
            float(_integer(_mapping(result, "cost"), "logical_relation_families"))
            for result in group
        ]
    if metric == "physical_executions":
        return [
            float(_integer(_mapping(result, "cost"), "physical_executions")) for result in group
        ]
    raise ValueError(f"unsupported bootstrap metric: {metric}")


def _paired_metric_delta(
    variant: dict[str, object],
    baseline: dict[str, object],
    metric: str,
) -> float:
    if metric == "exact_success_delta":
        return float(variant["status"] == "unique_exact") - float(
            baseline["status"] == "unique_exact"
        )
    if metric == "logical_relation_families_delta":
        return float(
            _integer(_mapping(variant, "cost"), "logical_relation_families")
            - _integer(_mapping(baseline, "cost"), "logical_relation_families")
        )
    if metric == "physical_executions_delta":
        return float(
            _integer(_mapping(variant, "cost"), "physical_executions")
            - _integer(_mapping(baseline, "cost"), "physical_executions")
        )
    raise ValueError(f"unsupported paired delta metric: {metric}")


def _bootstrap_interval(
    values: list[float],
    *,
    samples: int,
    confidence_level: float,
    rng: random.Random,
    statistic: Any,
) -> dict[str, float]:
    if not values:
        raise ValueError("bootstrap interval requires at least one value")
    estimate = statistic(values)
    if len(values) == 1:
        return {"estimate": estimate, "ci_low": estimate, "ci_high": estimate}
    bootstrap_values = []
    for _ in range(samples):
        resampled = [values[rng.randrange(len(values))] for _ in values]
        bootstrap_values.append(statistic(resampled))
    bootstrap_values.sort()
    alpha = (1.0 - confidence_level) / 2.0
    low_index = min(len(bootstrap_values) - 1, max(0, math.floor(alpha * samples)))
    high_index = min(
        len(bootstrap_values) - 1,
        max(0, math.ceil((1.0 - alpha) * samples) - 1),
    )
    return {
        "estimate": estimate,
        "ci_low": bootstrap_values[low_index],
        "ci_high": bootstrap_values[high_index],
    }


def _mean(values: list[float]) -> float:
    return float(statistics.fmean(values))


def _median(values: list[float]) -> float:
    return float(statistics.median(values))


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


def _campaign_seed(seed: int) -> int:
    return 600_000 + seed


def _opaque_campaign_id(
    namespace: str,
    mode: str,
    fault: str,
    seed: int,
) -> str:
    material = f"standard-v2:{namespace}:{mode}:{fault}:{seed}".encode()
    return hashlib.sha256(material).hexdigest()[:20]


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


def _load_json(path: Path) -> dict[str, object]:
    decoded: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(decoded, dict):
        raise ValueError(f"{path} is not a JSON object")
    return decoded


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
