#!/usr/bin/env python3
"""Verify reproducible MCP artifacts and one clean installed stdio route."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Sequence

import validation_identity


REPO_ROOT = Path(__file__).resolve().parents[1]
TAIL_CHARACTERS = 2_000


class ArtifactValidationError(RuntimeError):
    pass


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _git(*args: str) -> bytes:
    completed = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
    )
    return completed.stdout if completed.returncode == 0 else b""


def repository_identity() -> dict[str, Any]:
    return validation_identity.repository_identity(REPO_ROOT)


def _run(step_id: str, argv: Sequence[str], *, cwd: Path = REPO_ROOT) -> dict[str, Any]:
    started = time.monotonic()
    completed = subprocess.run(
        list(argv),
        cwd=cwd,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        check=False,
        capture_output=True,
        text=True,
    )
    result = {
        "id": step_id,
        "argv": list(argv),
        "returncode": completed.returncode,
        "duration_seconds": round(time.monotonic() - started, 6),
        "stdout_sha256": _sha256(completed.stdout.encode()),
        "stderr_sha256": _sha256(completed.stderr.encode()),
        "stdout_tail": completed.stdout[-TAIL_CHARACTERS:],
        "stderr_tail": completed.stderr[-TAIL_CHARACTERS:],
        "_stdout": completed.stdout,
    }
    if completed.returncode != 0:
        raise ArtifactValidationError(
            f"{step_id} exited {completed.returncode}: "
            f"{completed.stderr[-TAIL_CHARACTERS:] or completed.stdout[-TAIL_CHARACTERS:]}"
        )
    return result


def _json_stdout(step: dict[str, Any]) -> dict[str, Any]:
    try:
        payload = json.loads(step["_stdout"])
    except (json.JSONDecodeError, TypeError) as exc:
        raise ArtifactValidationError(
            f"{step['id']} did not emit one bounded JSON object"
        ) from exc
    if not isinstance(payload, dict):
        raise ArtifactValidationError(f"{step['id']} JSON output must be an object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def validate_release_artifacts() -> dict[str, Any]:
    started_at = dt.datetime.now(dt.UTC)
    before = repository_identity()
    steps: list[dict[str, Any]] = []
    temporary_root = Path(tempfile.mkdtemp(prefix="aoa-session-memory-release-"))
    error: str | None = None
    build_a: dict[str, Any] | None = None
    build_b: dict[str, Any] | None = None
    bootstrap_payload: dict[str, Any] = {}
    protocol_payload: dict[str, Any] = {}
    try:
        for label in ("a", "b"):
            step = _run(
                f"build-{label}",
                [
                    sys.executable,
                    "scripts/build_mcp_package.py",
                    "--outdir",
                    str(temporary_root / f"build-{label}"),
                    "--staging-root",
                    str(temporary_root / f"stage-{label}"),
                ],
            )
            steps.append(step)
            if label == "a":
                build_a = _json_stdout(step)
            else:
                build_b = _json_stdout(step)

        if build_a is None or build_b is None:
            raise ArtifactValidationError("both package builds must emit receipts")
        if build_a.get("artifacts") != build_b.get("artifacts"):
            raise ArtifactValidationError("wheel or sdist is not byte-reproducible")
        if build_a.get("source_unchanged") is not True or build_b.get("source_unchanged") is not True:
            raise ArtifactValidationError("external package build changed owner source")

        venv_root = temporary_root / "artifact-venv"
        steps.append(_run("create-artifact-venv", [sys.executable, "-m", "venv", str(venv_root)]))
        wheels = sorted((temporary_root / "build-a").glob("*.whl"))
        if len(wheels) != 1:
            raise ArtifactValidationError(
                f"expected exactly one wheel from build-a, found {len(wheels)}"
            )
        venv_python = venv_root / "bin" / "python"
        venv_pip = venv_root / "bin" / "pip"
        steps.append(
            _run(
                "install-wheel",
                [str(venv_pip), "install", "--disable-pip-version-check", str(wheels[0])],
            )
        )
        demo_root = temporary_root / "synthetic-demo"
        bootstrap = _run(
            "synthetic-bootstrap",
            [
                str(venv_python),
                "examples/synthetic/bootstrap_demo.py",
                "--destination",
                str(demo_root),
            ],
        )
        steps.append(bootstrap)
        bootstrap_payload = _json_stdout(bootstrap)
        bootstrap_results = bootstrap_payload.get("results")
        if (
            bootstrap_payload.get("schema") != "aoa_session_memory_synthetic_demo_v1"
            or not isinstance(bootstrap_results, dict)
            or not bootstrap_results
            or not all(value is True for value in bootstrap_results.values())
        ):
            raise ArtifactValidationError("synthetic bootstrap receipt is not complete")
        protocol = _run(
            "installed-stdio-protocol",
            [
                str(venv_python),
                "examples/synthetic/mcp_protocol_smoke.py",
                "--workspace-root",
                str(demo_root),
                "--cwd",
                str(temporary_root),
            ],
        )
        steps.append(protocol)
        protocol_payload = _json_stdout(protocol)
        if protocol_payload.get("ok") is not True:
            raise ArtifactValidationError("installed stdio protocol receipt is not ok")
    except (ArtifactValidationError, OSError, subprocess.SubprocessError) as exc:
        error = str(exc)
    finally:
        shutil.rmtree(temporary_root, ignore_errors=True)

    after = repository_identity()
    stable = before == after
    ok = error is None and stable
    for step in steps:
        step.pop("_stdout", None)
    return {
        "schema_version": "aoa_session_memory_release_artifact_validation_v1",
        "owner_repo": "aoa-session-memory",
        "started_at": started_at.isoformat(),
        "completed_at": dt.datetime.now(dt.UTC).isoformat(),
        "ok": ok,
        "error": error,
        "repository_identity": {"before": before, "after": after, "stable": stable},
        "artifact_identity": {
            "build_a": build_a.get("artifacts") if build_a else None,
            "build_b": build_b.get("artifacts") if build_b else None,
            "reproducible": bool(
                build_a is not None
                and build_b is not None
                and build_a.get("artifacts") == build_b.get("artifacts")
            ),
        },
        "installed_protocol": {
            "bootstrap_ok": bool(
                isinstance(bootstrap_payload.get("results"), dict)
                and bootstrap_payload.get("results")
                and all(
                    value is True
                    for value in bootstrap_payload["results"].values()
                )
            ),
            "protocol_ok": protocol_payload.get("ok") is True,
        },
        "steps": steps,
        "authority_boundary": (
            "owner-local reproducibility and clean-install protocol evidence only; "
            "no registry admission, publication, deployment, or release authority"
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = validate_release_artifacts()
    if args.receipt is not None:
        _write_json(args.receipt, payload)
    print(json.dumps(payload, sort_keys=True, ensure_ascii=False))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
