#!/usr/bin/env python3
"""Generate minimized release witness artifacts for every core relation family."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from sphinx_interrogator.ast import Program
from sphinx_interrogator.reducer import (
    ReductionConfig,
    ReductionMode,
    RelationReducer,
    SignatureKind,
    default_model_committee,
    report_digest,
)
from sphinx_interrogator.relations import (
    AnchorSwitchTemplate,
    Cell,
    ContextLiftTemplate,
    EpochSwitchTemplate,
    HardReplayTemplate,
    IndependentSwapTemplate,
    PhaseShiftTemplate,
    RegisterRenameTemplate,
    RelationInstance,
    RepeatAmplifyTemplate,
    SoftHistoryContrastTemplate,
    TokenSwitchTemplate,
)

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True, slots=True)
class WitnessSeed:
    """One generated starting relation plus known primitive relations."""

    family: str
    relation: RelationInstance
    known_relations: dict[str, RelationInstance]


def parse_args() -> argparse.Namespace:
    """Parse noninteractive reducer options."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "runs/reduced-witnesses-m9",
        help="directory for JSON/Markdown witness artifacts",
    )
    parser.add_argument(
        "--require-all-minimized",
        action="store_true",
        help="exit nonzero unless every generated family has a smaller witness",
    )
    return parser.parse_args()


def main() -> int:
    """Generate release witness artifacts and return a process status."""
    args = parse_args()
    output: Path = args.output
    witnesses_dir = output / "witnesses"
    witnesses_dir.mkdir(parents=True, exist_ok=True)

    config = ReductionConfig(
        mode=ReductionMode.IMPLIES_CORE,
        signature_kind=SignatureKind.SIGN,
        max_predicate_evaluations=1_024,
        max_generated_candidates=4_096,
    )
    witness_reports: list[dict[str, object]] = []
    for seed in _witness_seeds():
        reducer = RelationReducer(
            models=default_model_committee(seed.relation.involved_lanes),
            known_relations=seed.known_relations,
            config=config,
        )
        result = reducer.reduce(seed.relation)
        data = result.to_data()
        data["family"] = seed.family
        data["artifact_sha256"] = report_digest(data)
        witness_path = witnesses_dir / f"{_slug(seed.family)}.json"
        _write_json(witness_path, data)
        data["path"] = str(witness_path.relative_to(output))
        witness_reports.append(data)

    report = {
        "report_version": "1.0",
        "kind": "reduced-witnesses",
        "schema_version": "1.0",
        "generated_by": "scripts/reduce_witnesses.py",
        "preservation": {
            "mode": config.mode.value,
            "signature_kind": config.signature_kind.value,
            "model_scope": "finite-public-family-committee",
            "uses_true_secret": False,
            "result_label": "bounded public-model implication, not a hidden-secret comparison",
        },
        "families": witness_reports,
        "summary": {
            "family_count": len(witness_reports),
            "minimized_count": sum(item["status"] == "minimized" for item in witness_reports),
            "unchanged_count": sum(item["status"] != "minimized" for item in witness_reports),
            "all_minimized": all(item["status"] == "minimized" for item in witness_reports),
        },
    }
    report["artifact_sha256"] = report_digest(report)
    _write_json(output / "reduced-witnesses-report.json", report)
    _write_markdown(output / "reduced-witnesses-report.md", report)

    all_minimized = bool(report["summary"]["all_minimized"])  # type: ignore[index]
    if args.require_all_minimized and not all_minimized:
        return 1
    return 0


def _witness_seeds() -> tuple[WitnessSeed, ...]:
    anchor = AnchorSwitchTemplate().instantiate(
        instance_id="m9-anchor",
        lane=0,
        token=0,
        epoch=0,
        bank_a=3,
        bank_b=2,
        pad=8,
        repeats=4,
    )
    token = TokenSwitchTemplate().instantiate(
        instance_id="m9-token",
        lane=0,
        token_a=0,
        token_b=1,
        epoch=0,
        anchor=2,
        pad=8,
    )
    epoch = EpochSwitchTemplate().instantiate(
        instance_id="m9-epoch",
        lane=0,
        token=0,
        epoch_a=0,
        epoch_b=1,
        anchor=2,
        pad_a=8,
        pad_b=9,
    )
    phase = PhaseShiftTemplate().instantiate(
        instance_id="m9-phase",
        lane=0,
        token=0,
        epoch=0,
        anchor=2,
        pad_a=8,
        pad_b=9,
    )
    repeat = RepeatAmplifyTemplate().instantiate(
        instance_id="m9-repeat",
        lane=0,
        token=0,
        epoch=0,
        anchor=2,
        pad=8,
        repeats=6,
    )
    swap = IndependentSwapTemplate().instantiate(
        instance_id="m9-swap",
        first=Cell(0, 0, 0, 2, 8),
        second=Cell(1, 1, 1, 3, 10),
    )
    context = ContextLiftTemplate().instantiate(
        instance_id="m9-context",
        base=anchor,
        prefix_pad=8,
        suffix_fence=True,
    )
    register = RegisterRenameTemplate().instantiate(
        instance_id="m9-register",
        source=Program.parse(
            "MOVI r0, 7\nMOV r1, r0\nADD r2, r0, r1\nMIXOUT r2\nHALT\n",
            lanes=2,
        ),
        permutation=(1, 2, 0, 3, 4, 5, 6, 7),
    )
    hard_replay = HardReplayTemplate().instantiate(
        instance_id="m9-hard-replay",
        program=anchor.source_program,
        repetitions=5,
        deterministic_observation=True,
    )
    measurement = AnchorSwitchTemplate().instantiate(
        instance_id="m9-soft-measurement",
        lane=0,
        token=0,
        epoch=0,
        bank_a=0,
        bank_b=2,
        pad=0,
    )
    soft_history = SoftHistoryContrastTemplate().instantiate(
        instance_id="m9-soft-history",
        history_a=Program.parse("PAD 4\nFENCE\nHALT\n", lanes=2),
        history_b=Program.parse("PAD 8\nFENCE\nHALT\n", lanes=2),
        measurement=measurement,
        state_model_id="m9-state-model",
        source_state="q0",
        follow_up_state="q1",
    )
    return (
        WitnessSeed("anchor-switch/v1", anchor, {}),
        WitnessSeed("token-switch/v1", token, {}),
        WitnessSeed("epoch-switch/v1", epoch, {}),
        WitnessSeed("phase-shift/v1", phase, {}),
        WitnessSeed("repeat-amplify/v1", repeat, {}),
        WitnessSeed("independent-swap/v1", swap, {}),
        WitnessSeed("context-lift/v1", context, {anchor.instance_hash: anchor}),
        WitnessSeed("register-rename/v1", register, {}),
        WitnessSeed("hard-replay/v1", hard_replay, {}),
        WitnessSeed(
            "soft-history-contrast/v1",
            soft_history,
            {measurement.instance_hash: measurement},
        ),
    )


def _write_json(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


def _write_markdown(path: Path, report: dict[str, object]) -> None:
    summary = report["summary"]
    if not isinstance(summary, dict):
        raise TypeError("report summary must be a dictionary")
    lines = [
        "# Reduced relation witnesses",
        "",
        f"- Families: {summary['family_count']}",
        f"- Minimized: {summary['minimized_count']}",
        f"- All minimized: {summary['all_minimized']}",
        f"- Predicate: {report['preservation']}",
        "",
        "| family | status | original static | reduced static | steps | artifact |",
        "| --- | --- | ---: | ---: | ---: | --- |",
    ]
    families = report["families"]
    if not isinstance(families, list):
        raise TypeError("report families must be a list")
    for item in families:
        if not isinstance(item, dict):
            raise TypeError("witness entry must be a dictionary")
        original = item["original"]
        reduced = item["reduced"]
        if not isinstance(original, dict) or not isinstance(reduced, dict):
            raise TypeError("witness costs must be dictionaries")
        original_cost = original["cost"]
        reduced_cost = reduced["cost"]
        if not isinstance(original_cost, dict) or not isinstance(reduced_cost, dict):
            raise TypeError("witness cost entries must be dictionaries")
        steps = item["steps"]
        if not isinstance(steps, list):
            raise TypeError("witness steps must be a list")
        row_template = (
            "| {family} | {status} | {original_static} | {reduced_static} | {steps} | `{digest}` |"
        )
        lines.append(
            row_template.format(
                family=item["family"],
                status=item["status"],
                original_static=original_cost["static_cycles"],
                reduced_static=reduced_cost["static_cycles"],
                steps=len(steps),
                digest=str(item["artifact_sha256"])[:16],
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _slug(value: str) -> str:
    return value.replace("/", "-").replace("_", "-")


if __name__ == "__main__":
    raise SystemExit(main())
