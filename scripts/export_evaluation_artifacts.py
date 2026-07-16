#!/usr/bin/env python3
"""Export public evaluation CSVs and deterministic SVG plots from release reports."""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import math
import time
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_OUTPUT = ROOT / "runs/release-m9/evaluation-artifacts"
DEFAULT_STANDARD_REPORT = ROOT / "runs/standard-benchmark-v2/standard-benchmark-report.json"
DEFAULT_STATE_REPORT = ROOT / "runs/state-learning-m8/state-learning-report.json"
DEFAULT_REDUCER_REPORT = ROOT / "runs/reduced-witnesses-m9/reduced-witnesses-report.json"

CAMPAIGN_CSV = "csv/campaign-results.csv"
QUERY_CSV = "csv/query-events.csv"
RELATION_CSV = "csv/relation-decisions.csv"
STATE_CSV = "csv/state-learning.csv"
REDUCER_CSV = "csv/reducer-families.csv"
EXACT_RATE_PLOT = "plots/exact-rate-by-selector.svg"
LOGICAL_COST_PLOT = "plots/median-logical-cost-by-selector.svg"
STATE_ACCURACY_PLOT = "plots/state-learning-accuracy.svg"
REDUCER_STEPS_PLOT = "plots/reducer-steps-by-family.svg"

REQUIRED_CSVS = (CAMPAIGN_CSV, QUERY_CSV, RELATION_CSV, STATE_CSV, REDUCER_CSV)
REQUIRED_PLOTS = (
    EXACT_RATE_PLOT,
    LOGICAL_COST_PLOT,
    STATE_ACCURACY_PLOT,
    REDUCER_STEPS_PLOT,
)


def parse_args() -> argparse.Namespace:
    """Parse command-line options."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--standard-report", type=Path, default=DEFAULT_STANDARD_REPORT)
    parser.add_argument("--state-report", type=Path, default=DEFAULT_STATE_REPORT)
    parser.add_argument("--reducer-report", type=Path, default=DEFAULT_REDUCER_REPORT)
    return parser.parse_args()


def main() -> int:
    """Export artifacts and print the manifest path."""
    args = parse_args()
    manifest = build_artifacts(
        output=args.output,
        standard_report=args.standard_report,
        state_report=args.state_report,
        reducer_report=args.reducer_report,
    )
    print(manifest["path"])
    return 0


def build_artifacts(
    *,
    output: Path,
    standard_report: Path,
    state_report: Path,
    reducer_report: Path,
) -> dict[str, object]:
    """Generate all public CSV, SVG, Markdown, and manifest artifacts."""
    output_path = output if output.is_absolute() else ROOT / output
    output_path.mkdir(parents=True, exist_ok=True)
    (output_path / "csv").mkdir(exist_ok=True)
    (output_path / "plots").mkdir(exist_ok=True)

    standard_data = _load_object(standard_report)
    state_data = _load_object(state_report)
    reducer_data = _load_object(reducer_report)

    campaign_rows = _campaign_rows(standard_data)
    query_rows, relation_rows = _event_rows(
        campaign_rows,
        run_base=_resolve_path(standard_report).parent,
    )
    state_rows = _state_rows(state_data)
    reducer_rows = _reducer_rows(reducer_data)

    row_counts = {
        "campaign_results": _write_csv(
            output_path / CAMPAIGN_CSV,
            campaign_rows,
            (
                "seed",
                "selector_mode",
                "fault_assignment",
                "status",
                "judge_accepted",
                "remaining_secret_candidates",
                "logical_relation_families",
                "physical_executions",
                "hard_resets",
                "challenge_id",
                "run",
            ),
        ),
        "query_events": _write_csv(
            output_path / QUERY_CSV,
            query_rows,
            (
                "run",
                "seed",
                "selector_mode",
                "fault_assignment",
                "campaign_id",
                "sequence",
                "query_id",
                "request_id",
                "execution_id",
                "batch_id",
                "position",
                "ok",
                "status",
                "cycle_bucket",
                "bucket_width",
                "static_cycles",
                "retired_instructions",
                "logical_queries_used",
                "physical_executions_used",
                "program_sha256",
            ),
        ),
        "relation_decisions": _write_csv(
            output_path / RELATION_CSV,
            relation_rows,
            (
                "run",
                "seed",
                "selector_mode",
                "fault_assignment",
                "campaign_id",
                "sequence",
                "relation_instance_id",
                "relation_id",
                "decision_kind",
                "reset_policy",
                "emits_secret_constraints",
                "certificate_id",
                "constraint_count",
                "constraint_approximations",
                "source_request_ids",
            ),
        ),
        "state_learning": _write_csv(
            output_path / STATE_CSV,
            state_rows,
            (
                "row_type",
                "mode",
                "model_id",
                "metric",
                "value",
                "challenge_campaigns",
                "logical_queries",
                "physical_executions",
                "state_label",
                "anchor_bank",
                "output",
                "effective_candidates_before",
                "effective_candidates_after",
                "request_id",
            ),
        ),
        "reducer_families": _write_csv(
            output_path / REDUCER_CSV,
            reducer_rows,
            (
                "family",
                "status",
                "steps",
                "measured_replay_count",
                "blocked_reasons",
                "reset_policy_honored",
                "original_static_cycles",
                "reduced_static_cycles",
                "static_cycle_delta",
                "artifact_sha256",
            ),
        ),
    }

    _write_bar_svg(
        output_path / EXACT_RATE_PLOT,
        "Exact Rate By Selector",
        _summary_plot_items(standard_data, "exact_rate"),
        value_unit="",
        maximum=1.0,
    )
    _write_bar_svg(
        output_path / LOGICAL_COST_PLOT,
        "Median Logical Families By Selector",
        _summary_plot_items(standard_data, "median_logical_relation_families"),
        value_unit=" families",
    )
    _write_bar_svg(
        output_path / STATE_ACCURACY_PLOT,
        "Held-Out State-Learning Accuracy",
        _variant_plot_items(state_data, "held_out_accuracy"),
        value_unit="",
        maximum=1.0,
    )
    _write_bar_svg(
        output_path / REDUCER_STEPS_PLOT,
        "Reducer Steps By Relation Family",
        [(str(row["family"]), _int(row["steps"])) for row in reducer_rows],
        value_unit=" steps",
    )

    manifest = _manifest(
        output_path=output_path,
        sources=(standard_report, state_report, reducer_report),
        row_counts=row_counts,
    )
    manifest_path = output_path / "evaluation-artifacts-manifest.json"
    manifest_for_digest = dict(manifest)
    manifest_for_digest.pop("manifest_sha256", None)
    manifest["manifest_sha256"] = _digest_json(manifest_for_digest)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    _write_markdown(output_path / "evaluation-artifacts-manifest.md", manifest)
    return {"path": _display_path(manifest_path), "manifest": manifest}


def _campaign_rows(standard_data: Mapping[str, object]) -> list[dict[str, object]]:
    results = standard_data.get("results")
    if not isinstance(results, list):
        raise ValueError("standard benchmark report lacks results")
    rows: list[dict[str, object]] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        cost = _mapping(item.get("cost"))
        rows.append(
            {
                "seed": item.get("seed"),
                "selector_mode": item.get("selector_mode"),
                "fault_assignment": item.get("fault_assignment"),
                "status": item.get("status"),
                "judge_accepted": item.get("judge_accepted"),
                "remaining_secret_candidates": item.get("remaining_secret_candidates"),
                "logical_relation_families": cost.get("logical_relation_families"),
                "physical_executions": cost.get("physical_executions"),
                "hard_resets": cost.get("hard_resets"),
                "challenge_id": item.get("challenge_id"),
                "run": item.get("run"),
            }
        )
    return sorted(
        rows,
        key=lambda row: (_int(row["seed"]), str(row["selector_mode"]), str(row["run"])),
    )


def _event_rows(
    campaign_rows: Sequence[Mapping[str, object]],
    *,
    run_base: Path,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    query_rows: list[dict[str, object]] = []
    relation_rows: list[dict[str, object]] = []
    for campaign in campaign_rows:
        run = str(campaign.get("run") or "")
        if not run:
            continue
        run_path = _resolve_run_path(Path(run), run_base)
        events_path = run_path / "events.jsonl"
        report = _load_optional_object(run_path / "report.json")
        campaign_id = str(report.get("campaign_id", "")) if report else ""
        if not events_path.exists():
            continue
        events = list(_iter_events(events_path))
        query_programs: dict[str, str] = {}
        relations: dict[str, dict[str, object]] = {}
        constraints: dict[str, list[dict[str, object]]] = {}
        for event in events:
            kind = event.get("kind")
            payload = _mapping(event.get("payload"))
            if kind == "query_created":
                query_id = str(payload.get("query_id", ""))
                query_programs[query_id] = str(payload.get("program_sha256", ""))
            elif kind == "relation_recorded":
                relation_id = str(payload.get("relation_instance_id", ""))
                relations[relation_id] = _mapping(payload.get("relation"))
            elif kind == "constraint_added":
                relation_id = str(payload.get("relation_instance_id", ""))
                constraints.setdefault(relation_id, []).append(payload)
        for event in events:
            kind = event.get("kind")
            payload = _mapping(event.get("payload"))
            if kind == "execution_recorded":
                query_rows.append(
                    _query_row(
                        campaign=campaign,
                        campaign_id=campaign_id,
                        event=event,
                        program_sha256=query_programs.get(str(payload.get("query_id", "")), ""),
                    )
                )
            elif kind == "decision_recorded":
                relation_instance_id = str(payload.get("relation_instance_id", ""))
                relation_rows.append(
                    _relation_row(
                        campaign=campaign,
                        campaign_id=campaign_id,
                        event=event,
                        relation=relations.get(relation_instance_id, {}),
                        constraints=constraints.get(relation_instance_id, []),
                    )
                )
                if relation_instance_id and relation_instance_id not in constraints:
                    constraints[relation_instance_id] = []
    query_rows.sort(
        key=lambda row: (str(row["run"]), _int(row["sequence"]), str(row["request_id"]))
    )
    relation_rows.sort(
        key=lambda row: (str(row["run"]), _int(row["sequence"]), str(row["relation_instance_id"]))
    )
    return query_rows, relation_rows


def _query_row(
    *,
    campaign: Mapping[str, object],
    campaign_id: str,
    event: Mapping[str, object],
    program_sha256: str,
) -> dict[str, object]:
    payload = _mapping(event.get("payload"))
    response = _mapping(payload.get("response"))
    observation = _mapping(response.get("observation"))
    metrics = _mapping(response.get("public_metrics"))
    budget = _mapping(response.get("budget"))
    return {
        "run": campaign.get("run"),
        "seed": campaign.get("seed"),
        "selector_mode": campaign.get("selector_mode"),
        "fault_assignment": campaign.get("fault_assignment"),
        "campaign_id": campaign_id,
        "sequence": event.get("sequence"),
        "query_id": payload.get("query_id"),
        "request_id": payload.get("request_id"),
        "execution_id": payload.get("execution_id"),
        "batch_id": payload.get("batch_id"),
        "position": payload.get("position"),
        "ok": response.get("ok"),
        "status": response.get("status"),
        "cycle_bucket": observation.get("cycle_bucket"),
        "bucket_width": observation.get("bucket_width"),
        "static_cycles": metrics.get("static_cycles"),
        "retired_instructions": metrics.get("retired_instructions"),
        "logical_queries_used": budget.get("logical_queries_used"),
        "physical_executions_used": budget.get("physical_executions_used"),
        "program_sha256": program_sha256,
    }


def _relation_row(
    *,
    campaign: Mapping[str, object],
    campaign_id: str,
    event: Mapping[str, object],
    relation: Mapping[str, object],
    constraints: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    payload = _mapping(event.get("payload"))
    decision = _mapping(payload.get("decision"))
    certificate = _mapping(relation.get("certificate"))
    return {
        "run": campaign.get("run"),
        "seed": campaign.get("seed"),
        "selector_mode": campaign.get("selector_mode"),
        "fault_assignment": campaign.get("fault_assignment"),
        "campaign_id": campaign_id,
        "sequence": event.get("sequence"),
        "relation_instance_id": payload.get("relation_instance_id"),
        "relation_id": relation.get("relation_id"),
        "decision_kind": payload.get("kind"),
        "reset_policy": relation.get("reset_policy"),
        "emits_secret_constraints": relation.get("emits_secret_constraints"),
        "certificate_id": relation.get("certificate_id") or certificate.get("certificate_id"),
        "constraint_count": len(constraints),
        "constraint_approximations": _json_list(
            sorted({str(item.get("approximation", "")) for item in constraints if item})
        ),
        "source_request_ids": _json_list(_sequence(decision.get("source_request_ids"))),
    }


def _state_rows(state_data: Mapping[str, object]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for variant in _sequence(state_data.get("variants")):
        if not isinstance(variant, dict):
            continue
        cost = _mapping(variant.get("training_cost"))
        for metric in ("held_out_accuracy", "exact_matches", "counterexamples", "states"):
            rows.append(
                {
                    "row_type": "variant",
                    "mode": variant.get("mode"),
                    "model_id": variant.get("model_id"),
                    "metric": metric,
                    "value": variant.get(metric),
                    "challenge_campaigns": cost.get("challenge_campaigns"),
                    "logical_queries": cost.get("logical_queries"),
                    "physical_executions": cost.get("physical_executions"),
                    "state_label": "",
                    "anchor_bank": "",
                    "output": "",
                    "effective_candidates_before": "",
                    "effective_candidates_after": "",
                    "request_id": "",
                }
            )
    inference = _mapping(state_data.get("state_conditioned_inference"))
    for group in _sequence(inference.get("constraint_groups")):
        if not isinstance(group, dict):
            continue
        rows.append(
            {
                "row_type": "constraint",
                "mode": "learned_state",
                "model_id": inference.get("model_id"),
                "metric": "effective_nibble_candidates_after",
                "value": group.get("effective_nibble_candidates_after"),
                "challenge_campaigns": "",
                "logical_queries": "",
                "physical_executions": "",
                "state_label": group.get("state_label"),
                "anchor_bank": group.get("anchor_bank"),
                "output": group.get("output"),
                "effective_candidates_before": group.get("effective_nibble_candidates_before"),
                "effective_candidates_after": group.get("effective_nibble_candidates_after"),
                "request_id": group.get("measurement_request_id"),
            }
        )
    return rows


def _reducer_rows(reducer_data: Mapping[str, object]) -> list[dict[str, object]]:
    summary = _mapping(reducer_data.get("summary"))
    rows: list[dict[str, object]] = []
    for family in _sequence(reducer_data.get("families")):
        if not isinstance(family, dict):
            continue
        original_cost = _mapping(_mapping(family.get("original")).get("cost"))
        reduced_cost = _mapping(_mapping(family.get("reduced")).get("cost"))
        original_static = original_cost.get("combined_static_cycles")
        reduced_static = reduced_cost.get("combined_static_cycles")
        rows.append(
            {
                "family": family.get("family"),
                "status": family.get("status"),
                "steps": len(_sequence(family.get("steps"))),
                "measured_replay_count": len(_sequence(family.get("measured_replay"))),
                "blocked_reasons": _json_list(_sequence(family.get("blocked_reasons"))),
                "reset_policy_honored": summary.get("reset_policy_honored"),
                "original_static_cycles": original_static,
                "reduced_static_cycles": reduced_static,
                "static_cycle_delta": _delta(original_static, reduced_static),
                "artifact_sha256": family.get("artifact_sha256"),
            }
        )
    return sorted(rows, key=lambda row: str(row["family"]))


def _summary_plot_items(data: Mapping[str, object], metric: str) -> list[tuple[str, float]]:
    items: list[tuple[str, float]] = []
    for summary in _sequence(data.get("summaries")):
        if not isinstance(summary, dict):
            continue
        label = f"{summary.get('selector_mode')}/{summary.get('fault_assignment')}"
        items.append((label, _float(summary.get(metric))))
    return sorted(items)


def _variant_plot_items(data: Mapping[str, object], metric: str) -> list[tuple[str, float]]:
    items: list[tuple[str, float]] = []
    for variant in _sequence(data.get("variants")):
        if isinstance(variant, dict):
            items.append((str(variant.get("mode")), _float(variant.get(metric))))
    return sorted(items)


def _write_csv(path: Path, rows: Sequence[Mapping[str, object]], fields: Sequence[str]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _csv_value(row.get(field)) for field in fields})
    return len(rows)


def _write_bar_svg(
    path: Path,
    title: str,
    items: Sequence[tuple[str, float]],
    *,
    value_unit: str,
    maximum: float | None = None,
) -> None:
    width = 920
    row_height = 32
    label_width = 320
    bar_width = 460
    height = 72 + row_height * max(1, len(items))
    max_value = maximum if maximum is not None else max((value for _, value in items), default=1.0)
    if max_value <= 0:
        max_value = 1.0
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" role="img">',
        f"<title>{html.escape(title)}</title>",
        '<rect width="100%" height="100%" fill="#fbf7ef"/>',
        f'<text x="24" y="34" font-family="Georgia, serif" font-size="22" '
        f'fill="#1f2a24">{html.escape(title)}</text>',
    ]
    for index, (label, value) in enumerate(items):
        y = 64 + index * row_height
        length = int(bar_width * min(max(value, 0.0), max_value) / max_value)
        lines.extend(
            [
                f'<text x="24" y="{y + 18}" font-family="IBM Plex Mono, monospace" '
                f'font-size="13" fill="#28352d">{html.escape(label)}</text>',
                f'<rect x="{label_width}" y="{y}" width="{bar_width}" height="18" fill="#e6dfd0"/>',
                f'<rect x="{label_width}" y="{y}" width="{length}" height="18" fill="#35654d"/>',
                f'<text x="{label_width + bar_width + 18}" y="{y + 14}" '
                'font-family="IBM Plex Mono, monospace" font-size="13" fill="#28352d">'
                f"{html.escape(_format_value(value))}{html.escape(value_unit)}</text>",
            ]
        )
    lines.append("</svg>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _manifest(
    *,
    output_path: Path,
    sources: Sequence[Path],
    row_counts: Mapping[str, int],
) -> dict[str, object]:
    files = [_file_entry(output_path / relative) for relative in (*REQUIRED_CSVS, *REQUIRED_PLOTS)]
    all_required_present = all(item["status"] == "present" for item in files)
    return {
        "report_version": "1.0",
        "kind": "evaluation-artifacts",
        "schema": "evaluation-artifacts/v1",
        "generated_at": _iso_time(time.time()),
        "private_artifacts_included": False,
        "sources": [_source_entry(path) for path in sources],
        "files": files,
        "row_counts": dict(row_counts),
        "summary": {
            "all_required_present": all_required_present,
            "csv_count": len(REQUIRED_CSVS),
            "plot_count": len(REQUIRED_PLOTS),
            "required_csvs": list(REQUIRED_CSVS),
            "required_plots": list(REQUIRED_PLOTS),
        },
        "manifest_sha256": "",
    }


def _write_markdown(path: Path, manifest: Mapping[str, object]) -> None:
    summary = _mapping(manifest.get("summary"))
    row_counts = _mapping(manifest.get("row_counts"))
    files = _sequence(manifest.get("files"))
    lines = [
        "# Evaluation artifacts",
        "",
        f"- Status: `{'complete' if summary.get('all_required_present') else 'blocked'}`",
        f"- Private artifacts included: `{manifest.get('private_artifacts_included')}`",
        f"- CSV files: {summary.get('csv_count')}",
        f"- Plot files: {summary.get('plot_count')}",
        f"- Manifest SHA-256: `{manifest.get('manifest_sha256')}`",
        "",
        "## Row counts",
        "",
    ]
    for key, value in sorted(row_counts.items()):
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Files", "", "| path | status | sha256 |", "| --- | --- | --- |"])
    for item in files:
        if not isinstance(item, dict):
            continue
        lines.append(f"| `{item.get('path')}` | `{item.get('status')}` | `{item.get('sha256')}` |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _file_entry(path: Path) -> dict[str, object]:
    if not path.exists():
        return {
            "path": _display_path(path),
            "kind": _file_kind(path),
            "status": "missing",
            "sha256": None,
            "size_bytes": None,
        }
    raw = path.read_bytes()
    return {
        "path": _display_path(path),
        "kind": _file_kind(path),
        "status": "present",
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
    }


def _source_entry(path: Path) -> dict[str, object]:
    absolute = _resolve_path(path)
    if not absolute.exists():
        raise FileNotFoundError(f"source artifact is missing: {path}")
    return {
        "path": _display_path(absolute),
        "sha256": hashlib.sha256(absolute.read_bytes()).hexdigest(),
    }


def _file_kind(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return "csv"
    if suffix == ".svg":
        return "plot"
    return "public-artifact"


def _iter_events(path: Path) -> Iterable[dict[str, object]]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            decoded = json.loads(line)
            if isinstance(decoded, dict):
                yield decoded


def _load_object(path: Path) -> dict[str, object]:
    absolute = _resolve_path(path)
    decoded = json.loads(absolute.read_text(encoding="utf-8"))
    if not isinstance(decoded, dict):
        raise ValueError(f"expected JSON object: {path}")
    return decoded


def _load_optional_object(path: Path) -> dict[str, object] | None:
    try:
        return _load_object(path)
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def _resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def _resolve_run_path(path: Path, run_base: Path) -> Path:
    if path.is_absolute():
        return path
    benchmark_relative = run_base / path
    if benchmark_relative.exists():
        return benchmark_relative
    return ROOT / path


def _mapping(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, Mapping) else {}


def _sequence(value: object) -> list[object]:
    return list(value) if isinstance(value, list | tuple) else []


def _csv_value(value: object) -> object:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return value


def _json_list(value: Sequence[object]) -> str:
    return json.dumps(list(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _delta(left: object, right: object) -> int | str:
    if isinstance(left, int | float) and isinstance(right, int | float):
        return int(left - right)
    return ""


def _int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return int(value)
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return 0


def _float(value: object) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, int | float) and math.isfinite(value):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return 0.0


def _format_value(value: float) -> str:
    if abs(value - round(value)) < 1e-9:
        return str(round(value))
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _digest_json(data: Mapping[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()


def _iso_time(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, UTC).isoformat().replace("+00:00", "Z")


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    raise SystemExit(main())
