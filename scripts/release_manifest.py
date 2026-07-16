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
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_ARTIFACTS = (
    "runs/standard-benchmark-v1/standard-benchmark-report.json",
    "runs/standard-profile-audit-m7/standard-profile-audit.json",
    "runs/state-learning-m8/state-learning-report.json",
    "runs/reduced-witnesses-m9/reduced-witnesses-report.json",
    "runs/tutorial-demo-v2-seed-7/report.json",
)


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
        "--artifact",
        action="append",
        default=[],
        help="additional artifact path relative to the repository root",
    )
    return parser.parse_args()


def main() -> int:
    """Write the release manifest and return a process status."""
    args = parse_args()
    artifacts = tuple(dict.fromkeys((*DEFAULT_ARTIFACTS, *args.artifact)))
    artifact_data = [_artifact_entry(Path(path)) for path in artifacts]
    missing = [item["path"] for item in artifact_data if not item["exists"]]
    manifest = {
        "manifest_version": "1.0",
        "kind": "sphinx-interrogator-release",
        "repository": _git_state(),
        "environment": _environment(),
        "command": {
            "argv": sys.argv,
            "cwd": str(ROOT),
            "repo_local_cache": {
                "CARGO_HOME": os.environ.get("CARGO_HOME"),
                "CARGO_TARGET_DIR": os.environ.get("CARGO_TARGET_DIR"),
                "CARGO_BUILD_JOBS": os.environ.get("CARGO_BUILD_JOBS"),
            },
        },
        "expected_root_gates": [
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
        ],
        "artifacts": artifact_data,
        "summary": {
            "artifact_count": len(artifact_data),
            "missing_count": len(missing),
            "missing": missing,
        },
    }
    manifest["manifest_sha256"] = _digest_json(manifest)
    output_path = args.output if args.output.is_absolute() else ROOT / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    markdown = output_path.with_suffix(".md")
    _write_markdown(markdown, manifest)
    print(output_path.relative_to(ROOT))
    if args.require_artifacts and missing:
        return 1
    return 0


def _artifact_entry(path: Path) -> dict[str, object]:
    absolute = ROOT / path
    if not absolute.exists():
        return {
            "path": str(path),
            "exists": False,
            "sha256": None,
            "size_bytes": None,
            "kind": _artifact_kind(path),
        }
    raw = absolute.read_bytes()
    entry: dict[str, object] = {
        "path": str(path),
        "exists": True,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
        "kind": _artifact_kind(path),
    }
    if absolute.suffix == ".json":
        try:
            decoded = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            decoded = None
        if isinstance(decoded, dict):
            entry["top_level_keys"] = sorted(decoded)
            for key in (
                "targets_met",
                "status",
                "result_status",
                "accepted",
                "artifact_sha256",
            ):
                if key in decoded:
                    entry[key] = decoded[key]
    return entry


def _git_state() -> dict[str, object]:
    status = _run(("git", "status", "--short"))
    return {
        "head": _run(("git", "rev-parse", "HEAD")),
        "branch": _run(("git", "branch", "--show-current")),
        "dirty": bool(status),
        "status_short": status.splitlines(),
    }


def _environment() -> dict[str, object]:
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "uv": _run(("uv", "--version")),
        "rustc": _run(("rustc", "--version")),
    }


def _artifact_kind(path: Path) -> str:
    text = str(path)
    if "standard-benchmark" in text:
        return "standard-benchmark-report"
    if "profile-audit" in text:
        return "profile-audit-report"
    if "state-learning" in text:
        return "state-learning-report"
    if "reduced-witnesses" in text:
        return "reduced-witnesses-report"
    if "tutorial-demo" in text:
        return "tutorial-demo-report"
    return "public-artifact"


def _run(command: tuple[str, ...]) -> str:
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
    if completed.returncode != 0:
        return f"unavailable: {completed.stderr.strip()}"
    return completed.stdout.strip()


def _digest_json(data: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()


def _write_markdown(path: Path, manifest: dict[str, object]) -> None:
    repository = manifest["repository"]
    summary = manifest["summary"]
    artifacts = manifest["artifacts"]
    if not isinstance(repository, dict) or not isinstance(summary, dict):
        raise TypeError("manifest sections must be dictionaries")
    if not isinstance(artifacts, list):
        raise TypeError("manifest artifacts must be a list")
    lines = [
        "# Sphinx Interrogator release manifest",
        "",
        f"- HEAD: `{repository['head']}`",
        f"- Dirty: `{repository['dirty']}`",
        f"- Missing artifacts: {summary['missing_count']}",
        f"- Manifest SHA-256: `{manifest['manifest_sha256']}`",
        "",
        "| artifact | exists | size | sha256 |",
        "| --- | --- | ---: | --- |",
    ]
    for item in artifacts:
        if not isinstance(item, dict):
            raise TypeError("artifact item must be a dictionary")
        digest = item["sha256"]
        rendered_digest = "" if digest is None else f"`{str(digest)[:16]}`"
        lines.append(
            f"| {item['path']} | {item['exists']} | {item['size_bytes']} | {rendered_digest} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
