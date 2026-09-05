#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Sequence

import validation_lanes


REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "docs" / "validation" / "validation_evidence_graph.json"
SDK_ROOT_ENV = "AOA_SESSION_MEMORY_AOA_SDK_ROOT"
SDK_PIN = "b73c8aca9ef5275df0ec9e3e55d446db08823fb2"
SDK_RUNNER_RELATIVE_PATH = Path(
    "mechanics/release-support/parts/validation-evidence-graph/scripts/validation_graph.py"
)
SERIAL_SOURCE_COMMAND = (
    "{python}",
    "-m",
    "pytest",
    "-q",
    "-p",
    "no:cacheprovider",
    "tests/test_session_memory.py",
    "tests/test_session_memory_outbox_core.py",
    "tests/test_public_tree_audit.py",
    "tests/test_git_history_audit.py",
)
GRAPH_SOURCE_COMMAND = SERIAL_SOURCE_COMMAND


class AdapterError(ValueError):
    pass


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def require_pinned_sdk_runner(sdk_root: Path) -> Path:
    sdk_root = sdk_root.resolve()
    top_level = _git(sdk_root, "rev-parse", "--show-toplevel")
    if top_level.returncode != 0 or not top_level.stdout.strip():
        raise AdapterError(f"SDK runner root is not a Git checkout: {sdk_root}")
    actual_root = Path(top_level.stdout.strip()).resolve()
    if actual_root != sdk_root:
        raise AdapterError(
            "SDK runner root must equal its Git top-level: "
            f"requested={sdk_root} actual={actual_root}"
        )
    head = _git(sdk_root, "rev-parse", "HEAD")
    actual_pin = head.stdout.strip() if head.returncode == 0 else ""
    if actual_pin != SDK_PIN:
        raise AdapterError(
            f"SDK runner pin mismatch: expected={SDK_PIN} actual={actual_pin or 'unavailable'}"
        )
    status = _git(sdk_root, "status", "--porcelain=v1", "--untracked-files=all")
    if status.returncode != 0:
        raise AdapterError("SDK runner worktree status is unavailable")
    if status.stdout:
        raise AdapterError("SDK runner worktree must be clean at the pinned commit")
    runner = sdk_root / SDK_RUNNER_RELATIVE_PATH
    tracked = _git(
        sdk_root,
        "ls-files",
        "--error-unmatch",
        SDK_RUNNER_RELATIVE_PATH.as_posix(),
    )
    if tracked.returncode != 0 or not runner.is_file():
        raise AdapterError(f"pinned SDK runner is missing: {runner}")
    return runner


def _normalized(command: Sequence[str]) -> tuple[str, ...]:
    return tuple("{python}" if token == sys.executable else token for token in command)


def serial_oracle_commands() -> list[tuple[str, ...]]:
    return [
        _normalized(step.command)
        for step in validation_lanes.command_sequence("standalone_full")
    ]


def graph_obligation_commands(
    manifest_path: Path = MANIFEST_PATH,
) -> list[tuple[str, ...]]:
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        nodes = payload["nodes"]
    except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise AdapterError(f"cannot load validation graph command inventory: {exc}") from exc
    commands: list[tuple[str, ...]] = []
    try:
        for node in nodes:
            commands.extend(
                tuple(step["argv"])
                for step in node["steps"]
                if step["id"]
                != "validate-owner-graph-runner-pin-and-serial-inventory"
            )
    except (KeyError, TypeError) as exc:
        raise AdapterError(f"invalid validation graph command inventory: {exc}") from exc
    return commands


def require_schedule_equivalent_serial_inventory(
    manifest_path: Path = MANIFEST_PATH,
) -> None:
    expected = Counter(serial_oracle_commands())
    actual = Counter(graph_obligation_commands(manifest_path))
    serial_source_count = expected.pop(SERIAL_SOURCE_COMMAND, 0)
    graph_source_count = actual.pop(GRAPH_SOURCE_COMMAND, 0)
    if serial_source_count == graph_source_count == 1 and actual == expected:
        return
    missing = [list(command) for command in sorted((expected - actual).elements())]
    extra = [list(command) for command in sorted((actual - expected).elements())]
    raise AdapterError(
        "validation graph diverges from the schedule-equivalent serial leaf scope: "
        + json.dumps(
            {
                "serial_source_count": serial_source_count,
                "graph_source_count": graph_source_count,
                "missing": missing,
                "extra": extra,
            },
            sort_keys=True,
        )
    )


def runner_environment(sdk_root: Path) -> dict[str, str]:
    return {**os.environ, SDK_ROOT_ENV: str(sdk_root.resolve())}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run aoa-session-memory validation through the pinned aoa-sdk graph ABI."
    )
    parser.add_argument(
        "--sdk-root",
        type=Path,
        default=Path(os.environ.get(SDK_ROOT_ENV, REPO_ROOT / ".deps" / "aoa-sdk")),
    )
    parser.add_argument("--profile", default="full")
    parser.add_argument("--changed-path", action="append", default=[])
    parser.add_argument("--shadow-route", action="store_true")
    parser.add_argument("--max-workers", type=int)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        require_schedule_equivalent_serial_inventory()
        runner = require_pinned_sdk_runner(args.sdk_root)
    except (AdapterError, validation_lanes.ManifestError) as exc:
        payload = {"ok": False, "error": str(exc)}
        print(
            json.dumps(payload, sort_keys=True)
            if args.json
            else f"validation graph adapter: {exc}",
            file=sys.stderr,
        )
        return 2

    command = [
        sys.executable,
        str(runner),
        "--repo-root",
        str(REPO_ROOT),
        "--manifest",
        str(MANIFEST_PATH),
    ]
    if args.validate_only:
        command.append("--validate-only")
    elif args.shadow_route:
        command.append("--shadow-route")
        for path in args.changed_path:
            command.extend(("--changed-path", path))
    else:
        command.extend(("--profile", args.profile))
    if args.max_workers is not None:
        command.extend(("--max-workers", str(args.max_workers)))
    if args.receipt is not None:
        command.extend(("--receipt", str(args.receipt)))
    if args.json:
        command.append("--json")
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        env=runner_environment(args.sdk_root),
        check=False,
    )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
