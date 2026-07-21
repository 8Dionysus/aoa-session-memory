#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from audit_public_tree import (
    ARCHIVE_SUFFIXES,
    BLOCKING_SUFFIXES,
    BUILD_PARTS,
    CACHE_PARTS,
    RUNTIME_PARTS,
    SEVERITY_RANK,
    content_rules,
    fingerprint,
)


MAX_SCANNED_OBJECT_BYTES = 50 * 1024 * 1024
LARGE_OBJECT_BYTES = 1024 * 1024
DECLARED_SYNTHETIC_SECRET_FINGERPRINTS = {
    "sha256:26f878cc7b363eb0",
    "sha256:a3792a533536b805",
}


def git(repo: Path, *args: str, input_text: str | None = None) -> str:
    result = subprocess.run(
        ["git", "-C", repo.as_posix(), *args],
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout


class FindingAccumulator:
    def __init__(self) -> None:
        self._items: dict[tuple[str, str, str], dict[str, Any]] = {}

    def add(
        self,
        class_name: str,
        severity: str,
        value: bytes,
        reason: str,
        *,
        object_id: str,
        path: str,
        historical_only: bool,
        line: int | None = None,
        size: int | None = None,
    ) -> None:
        safe_fingerprint = fingerprint(class_name, value)
        key = (class_name, severity, safe_fingerprint)
        item = self._items.get(key)
        sample = {"object": object_id, "path": path, "historical_only": historical_only}
        if line is not None:
            sample["line"] = line
        if size is not None:
            sample["size"] = size
        if item is None:
            item = {
                "class": class_name,
                "severity": severity,
                "fingerprint": safe_fingerprint,
                "reason": reason,
                "occurrence_count": 0,
                "samples": [],
            }
            self._items[key] = item
        item["occurrence_count"] += 1
        if len(item["samples"]) < 5 and sample not in item["samples"]:
            item["samples"].append(sample)

    def sorted_items(self) -> list[dict[str, Any]]:
        return sorted(
            self._items.values(),
            key=lambda item: (item["severity"] != "blocking", item["class"], item["fingerprint"]),
        )


def object_inventory(repo: Path) -> tuple[dict[str, set[str]], dict[str, tuple[str, int]]]:
    object_paths: dict[str, set[str]] = {}
    for line in git(repo, "rev-list", "--objects", "--all").splitlines():
        object_id, separator, path = line.partition(" ")
        object_paths.setdefault(object_id, set())
        if separator and path:
            object_paths[object_id].add(path)
    object_ids = sorted(object_paths)
    metadata: dict[str, tuple[str, int]] = {}
    output = git(
        repo,
        "cat-file",
        "--batch-check=%(objectname) %(objecttype) %(objectsize)",
        input_text="\n".join(object_ids) + "\n",
    )
    for line in output.splitlines():
        object_id, object_type, raw_size = line.split()
        metadata[object_id] = (object_type, int(raw_size))
    return object_paths, metadata


def head_blob_ids(repo: Path) -> set[str]:
    result: set[str] = set()
    for line in git(repo, "ls-tree", "-r", "--full-tree", "HEAD").splitlines():
        metadata, _separator, _path = line.partition("\t")
        parts = metadata.split()
        if len(parts) == 3 and parts[1] == "blob":
            result.add(parts[2])
    return result


def virtual_path_rules(path: str) -> list[tuple[str, str, str]]:
    relative = Path(path)
    parts = set(relative.parts)
    name = relative.name.casefold()
    results: list[tuple[str, str, str]] = []
    if parts & CACHE_PARTS:
        results.append(("historical_cache", "blocking", "runtime cache was committed"))
    if parts & BUILD_PARTS or any(part.endswith(".egg-info") for part in relative.parts):
        results.append(("historical_build_artifact", "blocking", "generated build state was committed"))
    if parts & RUNTIME_PARTS:
        results.append(("historical_runtime_evidence", "blocking", "runtime evidence path was committed"))
    if len(relative.parts) > 1 and relative.parts[:1] == ("sessions",) and relative != Path("sessions/AGENTS.md"):
        results.append(("historical_session_material", "blocking", "session material path was committed"))
    if name == ".env" or (name.startswith(".env.") and name not in {".env.example", ".env.sample"}):
        results.append(("historical_environment_file", "blocking", "environment file was committed"))
    if relative.suffix.casefold() in BLOCKING_SUFFIXES or name.endswith(ARCHIVE_SUFFIXES):
        results.append(("historical_runtime_or_release_artifact", "blocking", "database, log, or built artifact was committed"))
    return results


class GitObjectReader:
    def __init__(self, repo: Path) -> None:
        self.process = subprocess.Popen(
            ["git", "-C", repo.as_posix(), "cat-file", "--batch"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def read(self, object_id: str, expected_type: str, expected_size: int) -> bytes:
        assert self.process.stdin is not None and self.process.stdout is not None
        self.process.stdin.write(object_id.encode("ascii") + b"\n")
        self.process.stdin.flush()
        header = self.process.stdout.readline().decode("ascii").strip().split()
        if len(header) != 3:
            raise RuntimeError(f"cannot read Git object metadata: {object_id}")
        actual_id, actual_type, raw_size = header
        size = int(raw_size)
        if actual_id != object_id or actual_type != expected_type or size != expected_size:
            raise RuntimeError(f"Git object metadata changed during audit: {object_id}")
        data = self.process.stdout.read(size)
        if len(data) != size or self.process.stdout.read(1) != b"\n":
            raise RuntimeError(f"incomplete Git object read: {object_id}")
        return data

    def close(self) -> None:
        if self.process.stdin is not None:
            self.process.stdin.close()
        returncode = self.process.wait(timeout=30)
        if returncode != 0:
            assert self.process.stderr is not None
            detail = self.process.stderr.read().decode("utf-8", errors="replace").strip()
            raise RuntimeError(detail or "git cat-file --batch failed")


def audit(repo: Path) -> dict[str, Any]:
    repo = repo.expanduser().resolve()
    object_paths, metadata = object_inventory(repo)
    current_blobs = head_blob_ids(repo)
    findings = FindingAccumulator()
    scanned_bytes = 0
    scanned_object_count = 0
    historical_only_blob_count = 0
    blob_count = 0
    skipped_object_count = 0
    owner_url_pattern = re.compile(
        r"(?:git@github\.com:|https://github\.com/)8Dionysus/[A-Za-z0-9_.-]+(?:\.git)?"
    )
    commit_email_pattern = re.compile(r"(?m)^(?:author|committer) .+ <([^>]+)>")
    compiled_content_rules = content_rules()
    object_reader = GitObjectReader(repo)

    for object_id in sorted(metadata):
        object_type, size = metadata[object_id]
        paths = sorted(object_paths.get(object_id) or {f"@object/{object_type}/{object_id}"})
        historical_only = object_type == "blob" and object_id not in current_blobs
        if object_type == "blob":
            blob_count += 1
            historical_only_blob_count += int(historical_only)
            for path in paths:
                for class_name, severity, reason in virtual_path_rules(path):
                    findings.add(
                        class_name,
                        severity,
                        path.encode("utf-8"),
                        reason,
                        object_id=object_id,
                        path=path,
                        historical_only=historical_only,
                    )
        if size >= LARGE_OBJECT_BYTES:
            findings.add(
                "large_git_object",
                "review",
                paths[0].encode("utf-8"),
                "large reachable Git object requires explicit content and licensing review",
                object_id=object_id,
                path=paths[0],
                historical_only=historical_only,
                size=size,
            )
        if object_type not in {"blob", "commit", "tag"}:
            continue
        if size > MAX_SCANNED_OBJECT_BYTES:
            skipped_object_count += 1
            findings.add(
                "unscanned_large_git_object",
                "blocking",
                paths[0].encode("utf-8"),
                "object exceeds the complete content-scan bound",
                object_id=object_id,
                path=paths[0],
                historical_only=historical_only,
                size=size,
            )
            continue
        data = object_reader.read(object_id, object_type, size)
        scanned_bytes += len(data)
        scanned_object_count += 1
        text = data.decode("utf-8", errors="ignore")
        for class_name, severity, pattern, reason in compiled_content_rules:
            for match in pattern.finditer(text):
                matched_value = match.group(0).encode("utf-8")
                matched_fingerprint = fingerprint(class_name, matched_value)
                declared_synthetic = (
                    any(path.startswith("tests/") for path in paths)
                    and matched_fingerprint in DECLARED_SYNTHETIC_SECRET_FINGERPRINTS
                )
                findings.add(
                    class_name,
                    "review" if declared_synthetic else severity,
                    matched_value,
                    "declared synthetic redaction test fixture" if declared_synthetic else reason,
                    object_id=object_id,
                    path=paths[0],
                    historical_only=historical_only,
                    line=text.count("\n", 0, match.start()) + 1,
                )
        for owner_url in owner_url_pattern.finditer(text):
            findings.add(
                "owner_repository_url",
                "review",
                owner_url.group(0).encode("utf-8"),
                "owner-namespace repository URL requires visibility classification",
                object_id=object_id,
                path=paths[0],
                historical_only=historical_only,
                line=text.count("\n", 0, owner_url.start()) + 1,
            )
        if object_type == "commit":
            for email_match in commit_email_pattern.finditer(text):
                email = email_match.group(1)
                if email.casefold().endswith("@users.noreply.github.com"):
                    continue
                findings.add(
                    "commit_identity_email",
                    "review",
                    email.encode("utf-8"),
                    "commit identity is exposed when history becomes public",
                    object_id=object_id,
                    path=paths[0],
                    historical_only=False,
                    line=text.count("\n", 0, email_match.start()) + 1,
                )
    object_reader.close()
    finding_items = findings.sorted_items()
    counts = {
        severity: sum(1 for item in finding_items if item["severity"] == severity)
        for severity in ("blocking", "review")
    }
    refs = git(repo, "for-each-ref", "--format=%(refname)").splitlines()
    return {
        "schema": "aoa_session_memory_git_history_audit_v1",
        "ok": counts["blocking"] == 0 and skipped_object_count == 0,
        "coverage": {
            "ref_count": len(refs),
            "commit_count": int(git(repo, "rev-list", "--all", "--count").strip()),
            "reachable_object_count": len(metadata),
            "blob_count": blob_count,
            "historical_only_blob_count": historical_only_blob_count,
            "scanned_object_count": scanned_object_count,
            "scanned_bytes": scanned_bytes,
            "skipped_object_count": skipped_object_count,
        },
        "counts": counts,
        "findings": finding_items,
        "value_exposure": "class, object, path, line, reason, occurrence count, and safe fingerprint only",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan every object reachable from local Git refs without printing matched values")
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--fail-on", choices=("blocking", "review", "none"), default="blocking")
    args = parser.parse_args()
    result = audit(args.repo)
    print(json.dumps(result, indent=2, sort_keys=True))
    threshold = SEVERITY_RANK[args.fail_on]
    return 1 if any(SEVERITY_RANK[item["severity"]] >= threshold for item in result["findings"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
