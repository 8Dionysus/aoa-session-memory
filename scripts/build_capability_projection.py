#!/usr/bin/env python3
"""Delegate deterministic capability projection to the aoa-skills owner builder."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]


def candidate_roots() -> tuple[Path, ...]:
    explicit = os.environ.get("AOA_SKILLS_ROOT")
    if explicit is not None:
        return (Path(explicit).expanduser(),)
    return (
        REPO_ROOT / ".deps" / "aoa-skills",
        REPO_ROOT.parent / "aoa-skills",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for root in candidate_roots():
        builder = root / "scripts" / "build_capability_home_projection.py"
        if not builder.is_file():
            continue
        command = [
            sys.executable,
            str(builder),
            "--owner-root",
            str(REPO_ROOT),
        ]
        if args.check:
            command.append("--check")
        environment = os.environ.copy()
        scripts = str(root / "scripts")
        existing = environment.get("PYTHONPATH")
        environment["PYTHONPATH"] = scripts if not existing else f"{scripts}{os.pathsep}{existing}"
        return subprocess.run(
            command,
            cwd=REPO_ROOT,
            env=environment,
            check=False,
        ).returncode
    checked = ", ".join(str(root) for root in candidate_roots())
    print(f"[error] aoa-skills capability builder is unavailable; checked: {checked}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

