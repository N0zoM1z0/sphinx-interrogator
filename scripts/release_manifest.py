#!/usr/bin/env python3
"""Create a reproducible release manifest from public generated artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jsonschema

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_ARTIFACTS = (
    "runs/standard-benchmark-v2/standard-benchmark-report.json",
    "runs/tutorial-demo-v3/report.json",
    "runs/state-learning-m8/state-learning-report.json",
    "runs/reduced-witnesses-m9/reduced-witnesses-report.json",
    "runs/release-m9/evaluation-artifacts/evaluation-artifacts-manifest.json",
)

EXPECTED_ROOT_GATES = (
    "just fmt",
    "just lint",
    "just test",
    "just schema-check",
    "just docs-check",
    "just verify-formal",
    "just demo-tutorial",
    "just boundary-audit",
    "just benchmark-standard",
    "just evaluate-state-learning",
    "just reduce-witnesses",
    "just export-evaluation-artifacts",
)

CHECK_STATUS_PASS = "pass"
CHECK_STATUS_FAIL = "fail"
CHECK_STATUS_MISSING_EVIDENCE = "missing_evidence"


def parse_args() -> argparse.Namespace:
    """Parse manifest options."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "runs/release-m9/release-manifest.json",
        help="manifest JSON output path",
    )
    parser.add_argument(
        "--require-artifacts",
        action="store_true",
        help="exit nonzero when an expected public artifact is missing",
    )
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help="exit nonzero unless all release artifact, semantic, and gate checks pass",
    )
    parser.add_argument(
        "--validation-evidence",
        type=Path,
        help=(
            "JSON evidence for root validation commands; accepts either a list of "
            "command objects or an object with validation_commands/commands"
        ),
    )
    parser.add_argument(
        "--artifact",
        action="append",
        default=[],
        help="additional artifact path relative to the repository root",
    )
    return parser.parse_args()


def main() -> int:
    """Write the release manifest and return a process status."""
    started = time.time()
    args = parse_args()
    artifacts = tuple(dict.fromkeys((*DEFAULT_ARTIFACTS, *args.artifact)))
    artifact_data = [_artifact_entry(Path(path)) for path in artifacts]
    missing = [str(item["path"]) for item in artifact_data if item["status"] == "missing"]
    release_checks = [
        *_repository_release_checks(),
        *_artifact_release_checks(artifact_data),
    ]
    validation_commands = _validation_commands(args.validation_evidence)
    semantic_checks_pass = all(item["status"] == CHECK_STATUS_PASS for item in release_checks)
    validation_gates_pass = all(item["status"] == CHECK_STATUS_PASS for item in validation_commands)
    complete = not missing and semantic_checks_pass and validation_gates_pass
    status = "complete" if complete else "blocked"
    ended = time.time()
    manifest: dict[str, object] = {
        "manifest_version": "2.0",
        "kind": "sphinx-interrogator-release",
        "schema": "release-manifest/v2",
        "status": status,
        "started_at": _iso_time(started),
        "ended_at": _iso_time(ended),
        "duration_ms": int((ended - started) * 1000),
        "repository": _git_state(),
        "versions": _versions(),
        "command": {
            "argv": sys.argv,
            "cwd": str(ROOT),
            "environment": {
                "CARGO_HOME": os.environ.get("CARGO_HOME"),
                "CARGO_TARGET_DIR": os.environ.get("CARGO_TARGET_DIR"),
                "CARGO_BUILD_JOBS": os.environ.get("CARGO_BUILD_JOBS"),
                "SPHINX_VM_BINARY": os.environ.get("SPHINX_VM_BINARY"),
            },
        },
        "validation_commands": validation_commands,
        "release_checks": release_checks,
        "artifacts": artifact_data,
        "hashes": {
            str(item["path"]): item["sha256"]
            for item in artifact_data
            if item["status"] == "present"
        },
        "summary": {
            "artifact_count": len(artifact_data),
            "present_count": sum(item["status"] == "present" for item in artifact_data),
            "missing_count": len(missing),
            "missing": missing,
            "all_present": not missing,
            "semantic_checks_pass": semantic_checks_pass,
            "validation_gates_pass": validation_gates_pass,
            "complete": complete,
        },
    }
    manifest["manifest_sha256"] = _digest_json(manifest)
    schema = json.loads((ROOT / "spec/release-manifest.schema.json").read_text("utf-8"))
    jsonschema.Draft202012Validator(schema).validate(manifest)
    output_path = args.output if args.output.is_absolute() else ROOT / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    _write_markdown(output_path.with_suffix(".md"), manifest)
    print(_display_path(output_path))
    if args.require_artifacts and missing:
        return 1
    if args.require_complete and not complete:
        return 1
    return 0


def _artifact_entry(path: Path) -> dict[str, object]:
    absolute = ROOT / path
    base: dict[str, object] = {
        "path": str(path),
        "kind": _artifact_kind(path),
    }
    if not absolute.exists():
        return {
            **base,
            "status": "missing",
            "sha256": None,
            "size_bytes": None,
            "modified_at": None,
            "json": None,
        }
    raw = absolute.read_bytes()
    json_summary = _json_summary(raw)
    return {
        **base,
        "status": "present",
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
        "modified_at": _iso_time(absolute.stat().st_mtime),
        "json": json_summary,
    }


def _json_summary(raw: bytes) -> dict[str, object] | None:
    try:
        decoded: object = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(decoded, dict):
        return None
    summary: dict[str, object] = {"top_level_keys": sorted(decoded)}
    for key in (
        "report_version",
        "status",
        "targets_met",
        "acceptance",
        "summary",
        "artifact_sha256",
    ):
        if key in decoded:
            summary[key] = decoded[key]
    return summary


def _repository_release_checks() -> list[dict[str, object]]:
    state = _git_state()
    return [
        _release_check(
            "repository.clean",
            not bool(state["dirty"]),
            "working tree is clean" if not state["dirty"] else "working tree has tracked changes",
            {
                "revision": state["revision"],
                "status_short": state["status_short"],
            },
        )
    ]


def _artifact_release_checks(artifact_data: list[dict[str, object]]) -> list[dict[str, object]]:
    checks: list[dict[str, object]] = []
    for artifact in artifact_data:
        path = Path(_string(artifact, "path"))
        kind = _string(artifact, "kind")
        present = artifact["status"] == "present"
        checks.append(
            _release_check(
                f"artifact.{kind}.present",
                present,
                "artifact is present" if present else "artifact is missing",
                {"path": str(path)},
            )
        )
        if not present:
            continue
        decoded = _load_artifact_json(path)
        if decoded is None:
            checks.append(
                _release_check(
                    f"artifact.{kind}.json",
                    False,
                    "artifact is not a JSON object",
                    {"path": str(path)},
                )
            )
            continue
        checks.extend(_semantic_artifact_checks(kind, path, decoded))
    return checks


def _semantic_artifact_checks(
    kind: str,
    path: Path,
    decoded: dict[str, object],
) -> list[dict[str, object]]:
    if kind == "standard-benchmark-report":
        return _standard_benchmark_checks(path, decoded)
    if kind == "tutorial-demo-report":
        return _tutorial_demo_checks(path, decoded)
    if kind == "state-learning-report":
        return _state_learning_checks(path, decoded)
    if kind == "reduced-witnesses-report":
        return _reducer_checks(path, decoded)
    if kind == "evaluation-artifacts-manifest":
        return _evaluation_artifacts_checks(path, decoded)
    return [
        _release_check(
            f"artifact.{kind}.semantic",
            False,
            "no semantic release check is registered for this artifact kind",
            {"path": str(path)},
        )
    ]


def _standard_benchmark_checks(
    path: Path,
    decoded: dict[str, object],
) -> list[dict[str, object]]:
    acceptance = _maybe_mapping(decoded.get("acceptance"))
    full_matrix = bool(acceptance.get("full_published_matrix")) if acceptance else False
    targets_met = bool(acceptance.get("targets_met")) if acceptance else False
    off_false_exact = acceptance.get("off_false_exact_declarations") if acceptance else None
    has_bootstrap_ci = any(
        key in decoded
        for key in (
            "bootstrap_confidence_intervals",
            "paired_bootstrap_confidence_intervals",
            "bootstrap_ci",
        )
    )
    variants = decoded.get("variants")
    variant_count = len(variants) if isinstance(variants, list) else 0
    baseline_surface = _maybe_mapping(decoded.get("baseline_surface"))
    baseline_complete = bool(baseline_surface and baseline_surface.get("complete") is True)
    return [
        _release_check(
            "standard.full_published_matrix",
            full_matrix,
            "full published matrix completed"
            if full_matrix
            else "standard benchmark is not the full published matrix",
            {"path": str(path), "selected_seed_count": acceptance.get("selected_seed_count")}
            if acceptance
            else {"path": str(path)},
        ),
        _release_check(
            "standard.targets_met",
            targets_met,
            "standard benchmark meets release targets"
            if targets_met
            else "standard benchmark targets are not met",
            {"path": str(path), "acceptance": acceptance or {}},
        ),
        _release_check(
            "standard.off_control_false_exact",
            off_false_exact == 0,
            "off-control has no false exact declarations"
            if off_false_exact == 0
            else "off-control false exact declarations are nonzero or missing",
            {"path": str(path), "off_false_exact_declarations": off_false_exact},
        ),
        _release_check(
            "standard.paired_bootstrap_ci",
            has_bootstrap_ci,
            "paired bootstrap confidence intervals are recorded"
            if has_bootstrap_ci
            else "paired bootstrap confidence intervals are missing",
            {"path": str(path)},
        ),
        _release_check(
            "standard.required_ablation_surface",
            baseline_complete,
            "required ablation surface is recorded"
            if baseline_complete
            else "benchmark does not record complete B0-B7/primary ablation evidence",
            {
                "path": str(path),
                "variant_count": variant_count,
                "baseline_surface": baseline_surface or {},
            },
        ),
    ]


def _tutorial_demo_checks(path: Path, decoded: dict[str, object]) -> list[dict[str, object]]:
    judge = _maybe_mapping(decoded.get("judge"))
    uniqueness = _maybe_mapping(decoded.get("uniqueness"))
    return [
        _release_check(
            "tutorial.unique_exact",
            decoded.get("status") == "unique_exact",
            "tutorial recovered a unique exact secret"
            if decoded.get("status") == "unique_exact"
            else "tutorial did not finish with unique_exact",
            {"path": str(path), "status": decoded.get("status")},
        ),
        _release_check(
            "tutorial.judge_accepted",
            bool(judge and judge.get("accepted") is True),
            "judge accepted the final tutorial submission"
            if judge and judge.get("accepted") is True
            else "judge acceptance is missing or false",
            {"path": str(path)},
        ),
        _release_check(
            "tutorial.alternative_secret_unsat",
            bool(uniqueness and uniqueness.get("alternative_model_unsat") is True),
            "alternative-secret query is unsat"
            if uniqueness and uniqueness.get("alternative_model_unsat") is True
            else "alternative-secret unsat evidence is missing or false",
            {"path": str(path)},
        ),
    ]


def _state_learning_checks(path: Path, decoded: dict[str, object]) -> list[dict[str, object]]:
    targets = _maybe_mapping(decoded.get("targets_met"))
    target_values = list(targets.values()) if targets else []
    inference = _maybe_mapping(decoded.get("state_conditioned_inference"))
    nontrivial = inference.get("nontrivial_constraints") if inference else None
    cost = _maybe_mapping(decoded.get("cost"))
    challenge_campaigns = cost.get("challenge_campaigns") if cost else None
    independent_challenges = (
        decoded.get("shared_private_root") is False
        and isinstance(challenge_campaigns, int)
        and challenge_campaigns >= 30
    )
    return [
        _release_check(
            "m8.measurement_targets",
            bool(target_values) and all(value is True for value in target_values),
            "state-learning measurement targets are met"
            if target_values and all(value is True for value in target_values)
            else "state-learning measurement targets are missing or failed",
            {"path": str(path), "targets_met": targets or {}},
        ),
        _release_check(
            "m8.state_conditioned_secret_inference",
            bool(
                inference
                and inference.get("status") == "complete"
                and isinstance(nontrivial, int)
                and nontrivial > 0
            ),
            "state-conditioned secret inference emitted non-trivial constraints"
            if inference
            and inference.get("status") == "complete"
            and isinstance(nontrivial, int)
            and nontrivial > 0
            else "state-conditioned secret inference evidence is missing or trivial",
            {"path": str(path), "state_conditioned_inference": inference or {}},
        ),
        _release_check(
            "m8.independent_research_challenges",
            independent_challenges,
            "state-learning used at least 30 independent research challenge campaigns"
            if independent_challenges
            else "state-learning research campaign independence/count evidence is insufficient",
            {
                "path": str(path),
                "shared_private_root": decoded.get("shared_private_root"),
                "challenge_campaigns": challenge_campaigns,
            },
        ),
    ]


def _reducer_checks(path: Path, decoded: dict[str, object]) -> list[dict[str, object]]:
    summary = _maybe_mapping(decoded.get("summary"))
    all_minimized = bool(summary and summary.get("all_minimized") is True)
    replay_paths_valid = bool(summary and summary.get("all_replay_paths_valid") is True)
    reset_policy_honored = bool(summary and summary.get("reset_policy_honored") is True)
    return [
        _release_check(
            "m9.reducer_all_minimized",
            all_minimized,
            "all reducer families minimized"
            if all_minimized
            else "not all reducer families are minimized",
            {"path": str(path), "summary": summary or {}},
        ),
        _release_check(
            "m9.reducer_replay_paths_valid",
            replay_paths_valid,
            "all reducer reports contain continuous replayable parent paths"
            if replay_paths_valid
            else "continuous replayable parent path evidence is missing or false",
            {"path": str(path), "summary": summary or {}},
        ),
        _release_check(
            "m9.reducer_reset_policy_honored",
            reset_policy_honored,
            "reducer replay honored relation reset policies"
            if reset_policy_honored
            else "reset-policy replay evidence is missing or false",
            {"path": str(path), "summary": summary or {}},
        ),
    ]


def _evaluation_artifacts_checks(
    path: Path,
    decoded: dict[str, object],
) -> list[dict[str, object]]:
    summary = _maybe_mapping(decoded.get("summary"))
    row_counts = _maybe_mapping(decoded.get("row_counts"))
    files = decoded.get("files")
    file_entries = files if isinstance(files, list) else []
    required_rows = (
        "campaign_results",
        "query_events",
        "relation_decisions",
        "state_learning",
        "reducer_families",
    )
    required_counts_present = (
        all(
            isinstance(row_counts.get(name), int) and row_counts[name] > 0 for name in required_rows
        )
        if row_counts
        else False
    )
    csv_count = sum(
        1 for item in file_entries if isinstance(item, dict) and item.get("kind") == "csv"
    )
    plot_count = sum(
        1 for item in file_entries if isinstance(item, dict) and item.get("kind") == "plot"
    )
    all_files_hashed = bool(file_entries) and all(
        isinstance(item, dict)
        and item.get("status") == "present"
        and isinstance(item.get("sha256"), str)
        and len(str(item.get("sha256"))) == 64
        for item in file_entries
    )
    return [
        _release_check(
            "evaluation_artifacts.private_free",
            decoded.get("private_artifacts_included") is False,
            "evaluation artifact manifest is public-only"
            if decoded.get("private_artifacts_included") is False
            else "evaluation artifact manifest may include private artifacts",
            {"path": str(path)},
        ),
        _release_check(
            "evaluation_artifacts.required_files",
            bool(summary and summary.get("all_required_present") is True)
            and csv_count >= 5
            and plot_count >= 4
            and all_files_hashed,
            "required CSV and plot files are present and hashed"
            if summary
            and summary.get("all_required_present") is True
            and csv_count >= 5
            and plot_count >= 4
            and all_files_hashed
            else "required CSV/plot files are missing or unhashed",
            {
                "path": str(path),
                "summary": summary or {},
                "csv_count": csv_count,
                "plot_count": plot_count,
            },
        ),
        _release_check(
            "evaluation_artifacts.row_counts",
            required_counts_present,
            "campaign, query, relation, state, and reducer CSVs have rows"
            if required_counts_present
            else "one or more required CSV row counts are missing or empty",
            {"path": str(path), "row_counts": row_counts or {}},
        ),
    ]


def _validation_commands(evidence_path: Path | None) -> list[dict[str, object]]:
    evidence = _load_validation_evidence(evidence_path)
    commands: list[dict[str, object]] = []
    for command in EXPECTED_ROOT_GATES:
        supplied = evidence.get(command)
        if supplied is None:
            commands.append(
                {
                    "command": command,
                    "status": CHECK_STATUS_MISSING_EVIDENCE,
                    "exit_code": None,
                    "started_at": None,
                    "ended_at": None,
                    "duration_ms": None,
                    "evidence": None,
                }
            )
            continue
        exit_code = supplied.get("exit_code")
        supplied_status = supplied.get("status")
        passed = exit_code == 0 and supplied_status in {CHECK_STATUS_PASS, "passed", "success"}
        commands.append(
            {
                "command": command,
                "status": CHECK_STATUS_PASS if passed else CHECK_STATUS_FAIL,
                "exit_code": exit_code if isinstance(exit_code, int) else None,
                "started_at": supplied.get("started_at")
                if isinstance(supplied.get("started_at"), str)
                else None,
                "ended_at": supplied.get("ended_at")
                if isinstance(supplied.get("ended_at"), str)
                else None,
                "duration_ms": supplied.get("duration_ms")
                if isinstance(supplied.get("duration_ms"), int)
                else None,
                "evidence": supplied,
            }
        )
    return commands


def _load_validation_evidence(path: Path | None) -> dict[str, dict[str, object]]:
    if path is None:
        return {}
    absolute = path if path.is_absolute() else ROOT / path
    try:
        decoded: object = json.loads(absolute.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if isinstance(decoded, dict):
        candidate = decoded.get("validation_commands", decoded.get("commands", decoded))
    else:
        candidate = decoded
    if not isinstance(candidate, list):
        return {}
    evidence: dict[str, dict[str, object]] = {}
    for item in candidate:
        if not isinstance(item, dict):
            continue
        command = item.get("command")
        if isinstance(command, str):
            evidence[command] = dict(item)
    return evidence


def _load_artifact_json(path: Path) -> dict[str, object] | None:
    absolute = path if path.is_absolute() else ROOT / path
    try:
        decoded: object = json.loads(absolute.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    return decoded if isinstance(decoded, dict) else None


def _release_check(
    name: str,
    passed: bool,
    reason: str,
    details: dict[str, object],
) -> dict[str, object]:
    return {
        "name": name,
        "status": CHECK_STATUS_PASS if passed else CHECK_STATUS_FAIL,
        "reason": reason,
        "details": details,
    }


def _maybe_mapping(value: object) -> dict[str, object] | None:
    return value if isinstance(value, dict) else None


def _git_state() -> dict[str, object]:
    status = _run(("git", "status", "--short"), allow_empty=True)
    head = _run(("git", "rev-parse", "HEAD"))
    return {
        "revision": head,
        "head": head,
        "branch": _run(("git", "branch", "--show-current")),
        "dirty": bool(status),
        "status_short": status.splitlines(),
    }


def _versions() -> dict[str, object]:
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "uv": _run(("uv", "--version"), first_line=True),
        "rustc": _run(("rustc", "--version"), first_line=True),
        "cargo": _run(("cargo", "--version"), first_line=True),
        "just": _run(("just", "--version"), first_line=True),
        "java": _run(("java", "-version"), stderr=True, first_line=True),
    }


def _artifact_kind(path: Path) -> str:
    text = str(path)
    if "standard-benchmark" in text:
        return "standard-benchmark-report"
    if "state-learning" in text:
        return "state-learning-report"
    if "reduced-witnesses" in text:
        return "reduced-witnesses-report"
    if "evaluation-artifacts" in text:
        return "evaluation-artifacts-manifest"
    if "tutorial-demo" in text:
        return "tutorial-demo-report"
    return "public-artifact"


def _run(
    command: tuple[str, ...],
    *,
    stderr: bool = False,
    first_line: bool = False,
    allow_empty: bool = False,
) -> str:
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            check=False,
            text=True,
            capture_output=True,
        )
    except OSError as error:
        return f"unavailable: {error}"
    output = completed.stderr if stderr else completed.stdout
    if completed.returncode != 0 and not output:
        output = completed.stderr
    if not output:
        if allow_empty:
            return ""
        return "unavailable"
    stripped = output.strip()
    return stripped.splitlines()[0] if first_line else stripped


def _digest_json(data: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()


def _iso_time(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, UTC).isoformat().replace("+00:00", "Z")


def _write_markdown(path: Path, manifest: dict[str, object]) -> None:
    repository = _object(manifest["repository"])
    summary = _object(manifest["summary"])
    artifacts = _list(manifest["artifacts"])
    release_checks = _list(manifest["release_checks"])
    validation_commands = _list(manifest["validation_commands"])
    lines = [
        "# Sphinx Interrogator release manifest",
        "",
        f"- Version: `{manifest['manifest_version']}`",
        f"- Status: `{manifest['status']}`",
        f"- Revision: `{repository['revision']}`",
        f"- Dirty: `{repository['dirty']}`",
        f"- Missing artifacts: {summary['missing_count']}",
        f"- Semantic checks pass: `{summary['semantic_checks_pass']}`",
        f"- Validation gates pass: `{summary['validation_gates_pass']}`",
        f"- Manifest SHA-256: `{manifest['manifest_sha256']}`",
        "",
        "| artifact | status | size | sha256 |",
        "| --- | --- | ---: | --- |",
    ]
    for item in artifacts:
        artifact = _object(item)
        digest = artifact["sha256"]
        rendered_digest = "" if digest is None else f"`{str(digest)[:16]}`"
        lines.append(
            f"| {artifact['path']} | {artifact['status']} | "
            f"{artifact['size_bytes']} | {rendered_digest} |"
        )
    lines.extend(
        [
            "",
            "| release check | status | reason |",
            "| --- | --- | --- |",
        ]
    )
    for item in release_checks:
        check = _object(item)
        lines.append(f"| {check['name']} | {check['status']} | {check['reason']} |")
    lines.extend(
        [
            "",
            "| validation command | status | exit code |",
            "| --- | --- | ---: |",
        ]
    )
    for item in validation_commands:
        command = _object(item)
        lines.append(f"| {command['command']} | {command['status']} | {command['exit_code']} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _string(mapping: dict[str, object], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str):
        raise TypeError(f"{key} must be a string")
    return value


def _object(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError("manifest section must be an object")
    return value


def _list(value: object) -> list[object]:
    if not isinstance(value, list):
        raise TypeError("manifest section must be a list")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
