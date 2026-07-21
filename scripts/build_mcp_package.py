#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Any


IGNORED_NAMES = {".pytest_cache", "__pycache__", "build", "dist"}
IGNORED_SUFFIXES = {".egg-info", ".pyc", ".pyo"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ignored(path: Path) -> bool:
    return any(part in IGNORED_NAMES or any(part.endswith(suffix) for suffix in IGNORED_SUFFIXES) for part in path.parts)


def source_snapshot(root: Path) -> dict[str, dict[str, Any]]:
    snapshot: dict[str, dict[str, Any]] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if ignored(relative) or not path.is_file():
            continue
        snapshot[relative.as_posix()] = {
            "mode": f"{path.stat().st_mode & 0o777:04o}",
            "sha256": sha256(path),
            "size": path.stat().st_size,
        }
    return snapshot


def require_external_empty_directory(path: Path, repo_root: Path, label: str) -> Path:
    resolved = path.expanduser().resolve()
    if resolved == Path("/") or resolved == repo_root or repo_root in resolved.parents:
        raise RuntimeError(f"{label} must be outside the repository: {resolved}")
    if resolved.exists() and (not resolved.is_dir() or any(resolved.iterdir())):
        raise RuntimeError(f"{label} must be absent or empty: {resolved}")
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def canonicalize_sdist(source: Path, epoch: int) -> None:
    target = source.with_name(f".{source.name}.canonical")
    with tarfile.open(source, "r:gz") as input_archive:
        with target.open("wb") as raw_output:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw_output, compresslevel=9, mtime=epoch) as compressed:
                with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as output_archive:
                    for member in sorted(input_archive.getmembers(), key=lambda item: item.name):
                        member_path = Path(member.name)
                        if member_path.is_absolute() or ".." in member_path.parts:
                            raise RuntimeError(f"unsafe sdist member: {member.name}")
                        member.mtime = epoch
                        member.uid = 0
                        member.gid = 0
                        member.uname = ""
                        member.gname = ""
                        member.pax_headers = {}
                        payload = input_archive.extractfile(member) if member.isfile() else None
                        output_archive.addfile(member, payload)
    target.replace(source)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build aoa-session-memory-mcp without writing build state into the checkout")
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--staging-root", type=Path)
    parser.add_argument("--source-date-epoch", type=int)
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    package_root = repo_root / "packages" / "aoa-session-memory-mcp"
    manifest_path = package_root / "package.manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    epoch = args.source_date_epoch or int(manifest["upstream"]["commit_epoch"])
    if epoch <= 0:
        raise RuntimeError("SOURCE_DATE_EPOCH must be a positive integer")

    outdir = require_external_empty_directory(args.outdir, repo_root, "outdir")
    staging_root = None
    if args.staging_root:
        staging_root = require_external_empty_directory(args.staging_root, repo_root, "staging root")

    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["SOURCE_DATE_EPOCH"] = str(epoch)
    subprocess.run(
        [sys.executable, "scripts/validate_package_projection.py"],
        cwd=package_root,
        env=env,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    before = source_snapshot(package_root)

    with tempfile.TemporaryDirectory(prefix="aoa-session-memory-mcp-build-", dir=staging_root) as temporary:
        stage = Path(temporary) / "package"
        shutil.copytree(package_root, stage, ignore=lambda directory, names: [name for name in names if ignored(Path(name))])
        subprocess.run(
            [sys.executable, "-m", "build", "--sdist", "--wheel", "--outdir", outdir.as_posix()],
            cwd=stage,
            env=env,
            check=True,
            stdout=sys.stderr,
        )
        source_archives = sorted(outdir.glob("*.tar.gz"))
        if len(source_archives) != 1:
            raise RuntimeError("build did not produce exactly one source archive")
        canonicalize_sdist(source_archives[0], epoch)

    after = source_snapshot(package_root)
    if before != after:
        raise RuntimeError("package source tree changed during external build")
    artifacts = [
        {"filename": path.name, "sha256": sha256(path), "size": path.stat().st_size}
        for path in sorted(outdir.iterdir())
        if path.is_file()
    ]
    if len(artifacts) != 2 or {Path(item["filename"]).suffix for item in artifacts} != {".whl", ".gz"}:
        raise RuntimeError("build did not produce exactly one wheel and one source archive")
    result = {
        "schema": "aoa_session_memory_mcp_external_build_v1",
        "ok": True,
        "package": manifest["package"],
        "source_date_epoch": epoch,
        "source_file_count": len(before),
        "source_unchanged": True,
        "sdist_metadata_canonicalized": True,
        "artifacts": artifacts,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
