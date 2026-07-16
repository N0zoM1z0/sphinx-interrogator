#!/usr/bin/env python3
"""Audit public standard-profile leakage and grammar learnability bounds."""

from __future__ import annotations

import argparse
import json
import math
import os
from collections import Counter
from pathlib import Path

from sphinx_interrogator.relations import RepeatAmplifyTemplate
from sphinx_interrogator.target_model import FaultVariant, bank_of, execute_experiment_program

ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    """Parse the output location for the public audit artifact."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "runs/standard-profile-audit-v1")
    return parser.parse_args()


def main() -> int:
    """Write a deterministic audit report over the public standard grammar."""
    args = parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    one_shot = _one_shot_leakage()
    learnability = _learnability_bound()
    signal = _fault_signal_summary()
    report = {
        "report_version": "1.0",
        "profile_name": "standard",
        "semantic_version": "0.1.0",
        "analysis_scope": "public-symbolic-development-audit",
        "one_shot_leakage": one_shot,
        "learnability_bound": learnability,
        "fault_signal": signal,
        "targets_met": {
            "one_shot_max_bits_le_4": one_shot["maximum_partition_bits"] <= 4.0,
            "median_useful_bits_in_range": (
                0.25 <= one_shot["median_useful_partition_bits"] <= 1.5
            ),
            "blind_scan_worst_logical_le_64": (
                learnability["blind_scan_worst_logical_relations"] <= 64
            ),
            "oracle_collision_logical_eq_16": (
                learnability["oracle_collision_logical_relations"] == 16
            ),
        },
    }
    _write_json(output / "standard-profile-audit.json", report)
    _write_markdown(output / "standard-profile-audit.md", report)
    print(json.dumps(report["targets_met"], indent=2, sort_keys=True))
    return int(not all(report["targets_met"].values()))


def _one_shot_leakage() -> dict[str, object]:
    candidates: list[dict[str, object]] = []
    for epoch in range(2):
        for anchor in range(4):
            sizes = _partition_sizes(
                "collision" if bank_of(secret, 0, epoch) == anchor else "noncollision"
                for secret in range(16)
            )
            candidates.append(
                {
                    "kind": "repeat_amplify_16",
                    "epoch": epoch,
                    "anchor": anchor,
                    "partition_sizes": sizes,
                    "partition_bits": _entropy_bits(sizes),
                }
            )
    for epoch in range(2):
        for bank_a in range(4):
            for bank_b in range(4):
                if bank_a == bank_b:
                    continue
                sizes = _partition_sizes(
                    _anchor_switch_signature(bank_of(secret, 0, epoch), bank_a, bank_b)
                    for secret in range(16)
                )
                candidates.append(
                    {
                        "kind": "anchor_switch",
                        "epoch": epoch,
                        "bank_a": bank_a,
                        "bank_b": bank_b,
                        "partition_sizes": sizes,
                        "partition_bits": _entropy_bits(sizes),
                    }
                )
    useful = [
        float(candidate["partition_bits"])
        for candidate in candidates
        if candidate["partition_bits"]
    ]
    by_kind = {
        kind: {
            "count": sum(candidate["kind"] == kind for candidate in candidates),
            "maximum_partition_bits": max(
                float(candidate["partition_bits"])
                for candidate in candidates
                if candidate["kind"] == kind
            ),
            "example_partition_sizes": next(
                candidate["partition_sizes"]
                for candidate in candidates
                if candidate["kind"] == kind
            ),
        }
        for kind in sorted({str(candidate["kind"]) for candidate in candidates})
    }
    return {
        "candidate_count": len(candidates),
        "domain_secret_values": 16,
        "maximum_partition_bits": max(useful),
        "median_useful_partition_bits": _median(useful),
        "target_maximum_partition_bits": 4.0,
        "target_median_useful_range": [0.25, 1.5],
        "by_kind": by_kind,
    }


def _learnability_bound() -> dict[str, object]:
    per_cell_costs = []
    for secret in range(16):
        domain = set(range(16))
        queries = 0
        for epoch in range(2):
            true_bank = bank_of(secret, 0, epoch)
            for anchor in range(4):
                queries += 1
                if anchor == true_bank:
                    domain = {
                        candidate for candidate in domain if bank_of(candidate, 0, epoch) == anchor
                    }
                    break
        if domain != {secret}:
            raise AssertionError("public S-box epochs did not isolate the secret")
        per_cell_costs.append(queries)
    return {
        "oracle_collision_logical_relations": 8 * 2,
        "blind_scan_worst_logical_relations": 8 * max(per_cell_costs),
        "blind_scan_mean_logical_relations": 8 * _mean(per_cell_costs),
        "blind_scan_per_cell_costs": per_cell_costs,
        "method": "public-sbox-lane-local-anchor-scan",
    }


def _fault_signal_summary() -> dict[str, object]:
    relation = RepeatAmplifyTemplate().instantiate(
        instance_id="audit-repeat",
        lane=0,
        token=0,
        epoch=0,
        anchor=bank_of(0, 0, 0),
        pad=0,
        repeats=16,
    )
    signals = {}
    for variant in FaultVariant:
        source = execute_experiment_program(
            relation.source_program,
            {0: 0},
            variant=variant,
        )
        follow = execute_experiment_program(
            relation.follow_up_programs[0],
            {0: 0},
            variant=variant,
        )
        signals[variant.value] = {
            "source_fault_cycles": source.fault_cycles,
            "follow_up_fault_cycles": follow.fault_cycles,
            "repeat_margin_cycles": follow.fault_cycles - source.fault_cycles,
        }
    return {
        "certified_repeat_amplify_16": signals,
        "interpretation": (
            "off disables the signal; reference, weak, and signed are intentionally "
            "latent-equivalent under the drained hard-reset M7 repeat grammar"
        ),
    }


def _anchor_switch_signature(secret_bank: int, bank_a: int, bank_b: int) -> str:
    if secret_bank == bank_a:
        return "source_collision"
    if secret_bank == bank_b:
        return "follow_up_collision"
    return "neither_collision"


def _partition_sizes(signatures: object) -> list[int]:
    counts = Counter(signatures)
    return sorted(counts.values(), reverse=True)


def _entropy_bits(sizes: list[int]) -> float:
    total = sum(sizes)
    return -sum((size / total) * math.log2(size / total) for size in sizes)


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / 2.0


def _mean(values: list[int]) -> float:
    return sum(values) / len(values)


def _write_json(path: Path, data: object) -> None:
    temporary = path.with_suffix(f".tmp-{os.getpid()}")
    temporary.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _write_markdown(path: Path, report: dict[str, object]) -> None:
    one_shot = report["one_shot_leakage"]
    learnability = report["learnability_bound"]
    if not isinstance(one_shot, dict) or not isinstance(learnability, dict):
        raise TypeError("audit sections must be objects")
    lines = [
        "# Standard Profile Audit",
        "",
        f"- Maximum one-shot partition bits: `{one_shot['maximum_partition_bits']:.3f}`",
        f"- Median useful partition bits: `{one_shot['median_useful_partition_bits']:.3f}`",
        f"- Oracle collision logical relations: "
        f"`{learnability['oracle_collision_logical_relations']}`",
        f"- Blind scan worst logical relations: "
        f"`{learnability['blind_scan_worst_logical_relations']}`",
        "",
    ]
    temporary = path.with_suffix(f".tmp-{os.getpid()}")
    temporary.write_text("\n".join(lines), encoding="utf-8")
    os.replace(temporary, path)


if __name__ == "__main__":
    raise SystemExit(main())
