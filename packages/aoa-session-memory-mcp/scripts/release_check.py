#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def run(argv: list[str]) -> None:
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    subprocess.run(argv, cwd=PACKAGE_ROOT, env=env, check=True)


def main() -> None:
    run([sys.executable, "scripts/validate_package_projection.py"])
    run([sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "tests", "-q"])
    if os.environ.get("AOA_SESSION_MEMORY_ROOT") or os.environ.get("AOA_WORKSPACE_ROOT"):
        run([sys.executable, "scripts/validate_session_memory_mcp.py"])


if __name__ == "__main__":
    main()
