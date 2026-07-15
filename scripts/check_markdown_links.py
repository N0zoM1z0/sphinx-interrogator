#!/usr/bin/env python3
"""Check repository-relative Markdown links in project-authored documentation."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")


def main() -> int:
    """Report missing relative link targets."""
    errors: list[str] = []
    for path in sorted(ROOT.rglob("*.md")):
        if any(part.startswith(".") for part in path.relative_to(ROOT).parts):
            continue
        text = path.read_text(encoding="utf-8")
        for match in LINK.finditer(text):
            raw_target = match.group(1).strip().split()[0]
            if raw_target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            target_text = raw_target.split("#", maxsplit=1)[0]
            if not target_text:
                continue
            target = (path.parent / target_text).resolve()
            try:
                target.relative_to(ROOT.resolve())
            except ValueError:
                errors.append(f"{path.relative_to(ROOT)} escapes repository: {raw_target}")
                continue
            if not target.exists():
                errors.append(f"{path.relative_to(ROOT)} missing target: {raw_target}")
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("repository-relative Markdown links are valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
