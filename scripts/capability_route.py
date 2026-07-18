#!/usr/bin/env python3
"""Run shared deep retrieval or task-local DAG planning for this capability home."""

from __future__ import annotations

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
    for root in candidate_roots():
        runtime = root / "scripts" / "capability_home.py"
        if not runtime.is_file():
            continue
        environment = os.environ.copy()
        scripts = str(root / "scripts")
        existing = environment.get("PYTHONPATH")
        environment["PYTHONPATH"] = scripts if not existing else f"{scripts}{os.pathsep}{existing}"
        return subprocess.run(
            [
                sys.executable,
                str(runtime),
                "--owner-root",
                str(REPO_ROOT),
                *sys.argv[1:],
            ],
            cwd=REPO_ROOT,
            env=environment,
            check=False,
        ).returncode
    checked = ", ".join(str(root) for root in candidate_roots())
    print(f"[error] aoa-skills capability runtime is unavailable; checked: {checked}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

