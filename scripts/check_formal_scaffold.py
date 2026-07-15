#!/usr/bin/env python3
"""Check formal artifacts structurally and run the SMT contract when Z3 is available."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require_tokens(path: Path, tokens: tuple[str, ...]) -> list[str]:
    """Return diagnostics for required strings missing from a formal artifact."""
    text = path.read_text(encoding="utf-8")
    return [f"{path.relative_to(ROOT)} missing {token!r}" for token in tokens if token not in text]


def check_smt() -> list[str]:
    """Run the bounded SMT lemmas when a Z3 executable is on PATH."""
    z3 = shutil.which("z3")
    if z3 is None:
        print("z3 executable not found; SMT execution skipped after structural check")
        return []
    path = ROOT / "formal/relation_contracts.smt2"
    completed = subprocess.run(
        [z3, str(path)],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return [f"z3 failed: {completed.stderr.strip()}"]
    answers = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    if answers != ["unsat", "unsat", "unsat"]:
        return [f"unexpected SMT answers: {answers}"]
    print("SMT relation contracts: unsat, unsat, unsat")
    return []


def main() -> int:
    """Validate the formal scaffold and return a process status."""
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
    errors.extend(require_tokens(tla, ("Init ==", "Next ==", "TypeOK ==", "NoFaultMeansZero")))
    errors.extend(require_tokens(cfg, ("INIT Init", "NEXT Next", "TypeOK")))
    errors.extend(require_tokens(smt, ("sbox4", "bank", "check-sat")))
    errors.extend(check_smt())
    if errors:
        print("formal scaffold validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("formal scaffold structure validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
