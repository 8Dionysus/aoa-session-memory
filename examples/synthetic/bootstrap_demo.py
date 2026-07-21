#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any


SESSION_ID = "builder-week-synthetic-demo"
FIXTURE_NAME = "rollout-builder-week-demo.jsonl"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_json(
    label: str,
    argv: list[str],
    *,
    cwd: Path,
    accepted_returncodes: tuple[int, ...] = (0,),
) -> dict[str, Any]:
    result = subprocess.run(
        argv,
        cwd=cwd,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={"PATH": str(Path(sys.executable).parent) + ":/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"},
    )
    if result.returncode not in accepted_returncodes:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"{label} failed ({result.returncode}): {detail}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{label} did not return JSON: {result.stdout[:500]}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"{label} returned a non-object JSON payload")
    return payload


def ensure_safe_empty_destination(destination: Path, repo_root: Path) -> None:
    destination = destination.resolve()
    repo_root = repo_root.resolve()
    if destination == Path("/") or destination == repo_root or repo_root.is_relative_to(destination):
        raise RuntimeError(f"refusing unsafe demo destination: {destination}")
    if destination.exists() and any(destination.iterdir()):
        raise RuntimeError(f"demo destination must be absent or empty: {destination}")
    destination.mkdir(parents=True, exist_ok=True)


def freeze_sqlite_snapshots(archive_root: Path) -> list[str]:
    frozen: list[str] = []
    for db_path in sorted(archive_root.rglob("*.sqlite3")):
        with sqlite3.connect(db_path) as conn:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            mode = conn.execute("PRAGMA journal_mode=DELETE").fetchone()
        if not mode or str(mode[0]).casefold() != "delete":
            raise RuntimeError(f"could not freeze SQLite snapshot: {db_path}")
        frozen.append(db_path.relative_to(archive_root).as_posix())
    return frozen


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a public synthetic aoa-session-memory root")
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()

    source_dir = Path(__file__).resolve().parent
    repo_root = source_dir.parents[1]
    destination = args.destination.expanduser().resolve()
    ensure_safe_empty_destination(destination, repo_root)

    source_script = repo_root / "scripts" / "aoa_session_memory.py"
    fixture = source_dir / FIXTURE_NAME
    install = run_json(
        "portable install",
        [
            sys.executable,
            source_script.as_posix(),
            "install",
            "--workspace-root",
            destination.as_posix(),
            "--source-aoa-root",
            repo_root.as_posix(),
            "--no-tests",
        ],
        cwd=repo_root,
    )

    archive_root = destination / ".aoa"
    archive_script = archive_root / "scripts" / "aoa_session_memory.py"
    input_root = destination / "synthetic-input"
    input_root.mkdir(parents=True, exist_ok=True)
    transcript = input_root / FIXTURE_NAME
    shutil.copyfile(fixture, transcript)
    project_root = destination / "synthetic-project"
    project_root.mkdir(parents=True, exist_ok=True)
    (project_root / "AGENTS.md").write_text("# Synthetic demo workspace\n", encoding="utf-8")

    common = ["--workspace-root", destination.as_posix(), "--aoa-root", archive_root.as_posix()]
    sync = run_json(
        "session sync",
        [
            sys.executable,
            archive_script.as_posix(),
            "sync",
            "--transcript-path",
            transcript.as_posix(),
            "--session-id",
            SESSION_ID,
            "--cwd",
            project_root.as_posix(),
            *common,
        ],
        cwd=destination,
    )
    search = run_json(
        "search index",
        [sys.executable, archive_script.as_posix(), "search-index", "all", "--rebuild", *common],
        cwd=destination,
    )
    atlas = run_json(
        "atlas build",
        [sys.executable, archive_script.as_posix(), "atlas", "build", "all", *common],
        cwd=destination,
    )
    graph = run_json(
        "graph build",
        [sys.executable, archive_script.as_posix(), "graph-build", SESSION_ID, "--write", *common],
        cwd=destination,
    )
    registry = run_json(
        "entity registry",
        [
            sys.executable,
            archive_script.as_posix(),
            "entity-registry",
            "--write",
            "--no-runtime",
            "--observed-source",
            "auto",
            *common,
        ],
        cwd=destination,
    )
    readiness = run_json(
        "route readiness",
        [sys.executable, archive_script.as_posix(), "route-readiness", "all", "--sample-limit", "2", "--write-report", *common],
        cwd=destination,
        accepted_returncodes=(0, 1),
    )
    frozen_sqlite_snapshots = freeze_sqlite_snapshots(archive_root)

    manifest = {
        "schema": "aoa_session_memory_synthetic_demo_v1",
        "session_id": SESSION_ID,
        "fixture": FIXTURE_NAME,
        "fixture_sha256": sha256(fixture),
        "workspace_root": destination.as_posix(),
        "aoa_root": archive_root.as_posix(),
        "source_posture": "public synthetic data only",
        "frozen_sqlite_snapshots": frozen_sqlite_snapshots,
        "results": {
            "install_ok": bool(install.get("ok")),
            "sync_ok": bool(sync.get("ok")),
            "search_ok": bool(search.get("ok")),
            "atlas_ok": bool(atlas.get("ok")),
            "graph_ok": bool(graph.get("ok")),
            "entity_registry_ok": bool(registry.get("ok")),
            "route_readiness_generated": readiness.get("artifact_type") == "route_layer_readiness"
            and bool(readiness.get("report_json")),
        },
        "readiness": {
            "ok": bool(readiness.get("ok")),
            "covered_requirement_count": readiness.get("covered_requirement_count"),
            "required_requirement_count": readiness.get("required_requirement_count"),
            "posture": "one-session demo coverage, not production readiness",
        },
    }
    (destination / "synthetic-demo.manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if all(manifest["results"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
