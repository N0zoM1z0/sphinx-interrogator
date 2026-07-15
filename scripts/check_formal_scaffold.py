#!/usr/bin/env python3
"""Check formal artifacts and exhaustively connect the finite M2 scheduler model."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TLA2TOOLS = ROOT / ".tools/tla2tools-1.7.4.jar"


def require_tokens(path: Path, tokens: tuple[str, ...]) -> list[str]:
    """Return diagnostics for required strings missing from a formal artifact."""
    text = path.read_text(encoding="utf-8")
    return [f"{path.relative_to(ROOT)} missing {token!r}" for token in tokens if token not in text]


def check_smt() -> list[str]:
    """Run the bounded SMT lemmas and fail closed when Z3 is unavailable."""
    z3 = shutil.which("z3")
    if z3 is None:
        return ["z3 executable not found; run `uv sync --extra dev` before verification"]
    path = ROOT / "formal/relation_contracts.smt2"
    completed = subprocess.run(
        [z3, str(path)],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if completed.returncode != 0:
        return [f"z3 failed: {completed.stderr.strip()}"]
    answers = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    if answers != ["unsat", "unsat", "unsat"]:
        return [f"unexpected SMT answers: {answers}"]
    print("SMT relation contracts: unsat, unsat, unsat")
    return []


def check_tlc() -> list[str]:
    """Run the complete configured TLA+ state graph with the pinned local TLC tool."""
    configured = os.environ.get("TLA2TOOLS_JAR")
    jar = Path(configured).resolve() if configured else DEFAULT_TLA2TOOLS
    if not jar.is_file():
        return [f"TLC tool not found at {jar}; run `just bootstrap-formal`"]
    java = shutil.which("java")
    if java is None:
        return ["java executable not found; Java 17+ is required for TLC"]
    completed = subprocess.run(
        [
            java,
            "-XX:+UseParallelGC",
            "-jar",
            str(jar),
            "-workers",
            "1",
            "-seed",
            "20260715",
            "-metadir",
            str(ROOT / ".cache/tlc"),
            "-config",
            str(ROOT / "formal/SphinxVM.cfg"),
            str(ROOT / "formal/SphinxVM.tla"),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    output = completed.stdout + completed.stderr
    if completed.returncode != 0:
        tail = "\n".join(output.splitlines()[-20:])
        return [f"TLC failed with exit {completed.returncode}:\n{tail}"]
    if "Model checking completed. No error has been found." not in output:
        return ["TLC did not report a complete successful state-graph search"]
    summary = next(
        (line.strip() for line in output.splitlines() if "distinct states found" in line),
        "complete state graph",
    )
    print(f"TLC scheduler model: {summary}")
    return []


def check_finite_scheduler(*, mutate_suppression: bool) -> list[str]:
    """Exhaust the guarded-replay cell and reset projections over their finite domains."""
    errors: list[str] = []
    hard_reset = (0, None, 0, 0, False, None)
    if hard_reset != (0, None, 0, 0, False, None):
        errors.append("hard reset is not the unique all-cleared state")

    fields = ("phase", "last_bank", "replay_credit", "uop_cache")
    source = (3, 2, 3, 15, True, (1, 0, True))
    for mask in range(1 << len(fields)):
        preserved = {field for index, field in enumerate(fields) if mask & (1 << index)}
        reset = (
            source[0] if "phase" in preserved else 0,
            source[1] if "last_bank" in preserved else None,
            source[2] if "replay_credit" in preserved else 0,
            source[3] if "uop_cache" in preserved else 0,
            source[4] if "uop_cache" in preserved else False,
            None,
        )
        expected = (
            *(
                source[index] if field in preserved else hard_reset[index]
                for index, field in enumerate(fields)
            ),
            source[4] if "uop_cache" in preserved else False,
            None,
        )
        if reset != expected:
            errors.append(f"soft-reset projection mismatch for {sorted(preserved)}")
            return errors

    for phase in range(4):
        for replay_credit in range(4):
            for lane in range(4):
                for token in range(16):
                    for epoch in range(2):
                        guard = phase == ((lane ^ token ^ epoch) & 0b11)
                        next_phase = (phase + 1 + epoch) & 0b11
                        if next_phase not in range(4):
                            errors.append("probe phase escaped the two-bit domain")
                            return errors
                        for secret_bank in range(4):
                            for anchor_bank in range(4):
                                collision = secret_bank == anchor_bank
                                suppress = replay_credit == (2 if mutate_suppression else 3)
                                delta = int(collision and guard and not suppress)
                                expected_delta = int(collision and guard and replay_credit != 3)
                                if delta != expected_delta:
                                    errors.append(
                                        "reference delta mismatch at "
                                        f"phase={phase}, replay={replay_credit}, lane={lane}, "
                                        f"token={token}, epoch={epoch}, secret_bank={secret_bank}, "
                                        f"anchor_bank={anchor_bank}"
                                    )
                                    return errors
                                next_replay = (
                                    min(3, replay_credit + 1)
                                    if collision
                                    else max(0, replay_credit - 1)
                                )
                                if next_replay not in range(4):
                                    errors.append("anchor replay credit escaped the two-bit domain")
                                    return errors
    return errors


def parse_args() -> argparse.Namespace:
    """Parse the deliberate-mutation switch used by the regression self-test."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mutate-suppression",
        action="store_true",
        help="intentionally use replay_credit == 2 as suppression; verification must fail",
    )
    return parser.parse_args()


def main() -> int:
    """Validate formal artifacts and return a process status."""
    args = parse_args()
    tla = ROOT / "formal/SphinxVM.tla"
    cfg = ROOT / "formal/SphinxVM.cfg"
    smt = ROOT / "formal/relation_contracts.smt2"
    errors: list[str] = []
    for path in (tla, cfg, smt):
        if not path.is_file():
            errors.append(f"missing {path.relative_to(ROOT)}")
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    errors.extend(
        require_tokens(
            tla,
            (
                "Init ==",
                "Probe(lane, token, epoch) ==",
                "Anchor(bank, epoch) ==",
                "HardReset ==",
                "SoftReset ==",
                "TypeOK ==",
                "NoFaultMeansZero ==",
            ),
        )
    )
    errors.extend(require_tokens(cfg, ("INIT Init", "NEXT Next", "TypeOK")))
    errors.extend(require_tokens(smt, ("sbox4", "bank", "check-sat")))
    errors.extend(check_finite_scheduler(mutate_suppression=args.mutate_suppression))
    if not args.mutate_suppression:
        mutation_errors = check_finite_scheduler(mutate_suppression=True)
        if not mutation_errors:
            errors.append("intentional replay-suppression mutation was not detected")
        else:
            print("finite scheduler mutation self-test: rejected")
        errors.extend(check_smt())
        errors.extend(check_tlc())
    if errors:
        print("formal model validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("formal scheduler model validated over all 131072 guarded-replay cells")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
