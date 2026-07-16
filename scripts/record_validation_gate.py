#!/usr/bin/env python3
"""Run one validation gate and append machine-readable release evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVIDENCE = ROOT / "runs/release-m9/validation-evidence.json"


def parse_args() -> argparse.Namespace:
    """Parse the evidence output path, canonical gate label, and command argv."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--evidence",
        type=Path,
        default=DEFAULT_EVIDENCE,
        help="validation evidence JSON path",
    )
    parser.add_argument(
        "--label",
        help="canonical command label expected by release_manifest.py, e.g. 'just fmt'",
    )
    parser.add_argument("command", nargs=argparse.REMAINDER, help="command to run after --")
    return parser.parse_args()


def main() -> int:
    """Run the command, persist its evidence entry, and return its exit code."""
    args = parse_args()
    command = _command(args.command)
    label = args.label or " ".join(command)
    started = time.time()
    completed = subprocess.run(
        command,
        cwd=ROOT,
        check=False,
        text=True,
        capture_output=True,
    )
    ended = time.time()
    evidence_path = args.evidence if args.evidence.is_absolute() else ROOT / args.evidence
    log_paths = _write_logs(evidence_path, label, started, completed)
    entry = {
        "command": label,
        "status": "pass" if completed.returncode == 0 else "fail",
        "exit_code": completed.returncode,
        "started_at": _iso_time(started),
        "ended_at": _iso_time(ended),
        "duration_ms": int((ended - started) * 1000),
        "evidence": {
            "argv": command,
            "cwd": str(ROOT),
            "stdout_log": _display_path(log_paths["stdout"]),
            "stderr_log": _display_path(log_paths["stderr"]),
            "stdout_sha256": _sha256_text(completed.stdout),
            "stderr_sha256": _sha256_text(completed.stderr),
            "stdout_tail": _tail(completed.stdout),
            "stderr_tail": _tail(completed.stderr),
        },
    }
    _merge_entry(evidence_path, entry)
    print(f"{label}: {entry['status']} ({completed.returncode})")
    return completed.returncode


def _command(raw: list[str]) -> list[str]:
    command = raw[1:] if raw and raw[0] == "--" else raw
    if not command:
        raise SystemExit("record_validation_gate.py requires a command after --")
    return command


def _write_logs(
    evidence_path: Path,
    label: str,
    started: float,
    completed: subprocess.CompletedProcess[str],
) -> dict[str, Path]:
    log_dir = evidence_path.parent / "validation-logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"{datetime.fromtimestamp(started, UTC).strftime('%Y%m%dT%H%M%SZ')}-{_slug(label)}"
    stdout_path = log_dir / f"{prefix}.stdout.txt"
    stderr_path = log_dir / f"{prefix}.stderr.txt"
    stdout_path.write_text(completed.stdout, encoding="utf-8")
    stderr_path.write_text(completed.stderr, encoding="utf-8")
    return {"stdout": stdout_path, "stderr": stderr_path}


def _merge_entry(evidence_path: Path, entry: dict[str, Any]) -> None:
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    existing = _load_existing(evidence_path)
    entries = [
        item
        for item in existing
        if isinstance(item, dict) and item.get("command") != entry["command"]
    ]
    entries.append(entry)
    payload = {
        "schema": "sphinx-interrogator-validation-evidence/v1",
        "updated_at": entry["ended_at"],
        "validation_commands": entries,
    }
    evidence_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


def _load_existing(path: Path) -> list[dict[str, Any]]:
    try:
        decoded: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(decoded, dict):
        commands = decoded.get("validation_commands", decoded.get("commands", []))
    else:
        commands = decoded
    if not isinstance(commands, list):
        return []
    return [dict(item) for item in commands if isinstance(item, dict)]


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _tail(text: str, *, limit: int = 20) -> list[str]:
    return text.splitlines()[-limit:]


def _slug(label: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", label.strip()).strip("-")
    return slug[:80] or "command"


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _iso_time(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, UTC).isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    raise SystemExit(main())
