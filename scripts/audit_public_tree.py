#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Pattern


MAX_TEXT_BYTES = 10 * 1024 * 1024
CACHE_PARTS = {".mypy_cache", ".pytest_cache", ".ruff_cache", "__pycache__", ".venv", "venv"}
BUILD_PARTS = {"build", "dist"}
RUNTIME_PARTS = {"attachments", "diagnostics", "raw", "segments"}
BLOCKING_SUFFIXES = {".db", ".log", ".pyo", ".pyc", ".sqlite", ".sqlite3", ".whl"}
ARCHIVE_SUFFIXES = (".tar.gz", ".tgz")
SEVERITY_RANK = {"none": 99, "review": 1, "blocking": 2}


def fingerprint(class_name: str, value: bytes) -> str:
    digest = hashlib.sha256(class_name.encode("utf-8") + b"\0" + value).hexdigest()
    return f"sha256:{digest[:16]}"


def finding(
    class_name: str,
    severity: str,
    path: Path,
    value: bytes,
    reason: str,
    *,
    line: int | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "class": class_name,
        "severity": severity,
        "path": path.as_posix(),
        "fingerprint": fingerprint(class_name, value),
        "reason": reason,
    }
    if line is not None:
        result["line"] = line
    return result


def path_findings(relative: Path, absolute: Path) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    encoded = relative.as_posix().encode("utf-8")
    parts = set(relative.parts)
    name = relative.name
    if absolute.is_symlink():
        results.append(finding("symlink", "blocking", relative, encoded, "symlinks require explicit public review"))
    if parts & CACHE_PARTS:
        results.append(finding("cache", "blocking", relative, encoded, "runtime cache is not public source"))
    if parts & BUILD_PARTS or any(part.endswith(".egg-info") for part in relative.parts):
        results.append(finding("build_artifact", "blocking", relative, encoded, "generated package build state is not public source"))
    if parts & RUNTIME_PARTS:
        results.append(finding("runtime_evidence", "blocking", relative, encoded, "runtime evidence must not ship in the source tree"))
    if len(relative.parts) > 1 and relative.parts[:1] == ("sessions",) and relative != Path("sessions/AGENTS.md"):
        results.append(finding("session_material", "blocking", relative, encoded, "session material is private runtime evidence"))
    if name == ".env" or (name.startswith(".env.") and name not in {".env.example", ".env.sample"}):
        results.append(finding("environment_file", "blocking", relative, encoded, "environment files may contain credentials"))
    if absolute.suffix.casefold() in BLOCKING_SUFFIXES or name.casefold().endswith(ARCHIVE_SUFFIXES):
        results.append(finding("runtime_or_release_artifact", "blocking", relative, encoded, "database, log, or built release artifact is not source"))
    if absolute.is_file() and absolute.stat().st_size > MAX_TEXT_BYTES:
        results.append(finding("large_file", "review", relative, encoded, "large files require explicit history and licensing review"))
    return results


def content_rules() -> list[tuple[str, str, Pattern[str], str]]:
    private_key_marker = "-----BEGIN " + r"(?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"
    host_profile_marker = "/srv/" + "AbyssOS"
    return [
        ("private_key", "blocking", re.compile(private_key_marker), "private-key material"),
        ("openai_api_key", "blocking", re.compile(r"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{20,}\b"), "OpenAI-shaped API credential"),
        ("github_token", "blocking", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"), "GitHub-shaped credential"),
        ("aws_access_key", "blocking", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"), "AWS-shaped access key"),
        (
            "credential_assignment",
            "blocking",
            re.compile(r"(?i)\b(?:api[_-]?key|access[_-]?token|client[_-]?secret|password)\b\s*[:=]\s*['\"][^'\"\s]{12,}['\"]"),
            "credential-like assignment",
        ),
        (
            "bearer_credential",
            "blocking",
            re.compile(r"(?i)\b(?:authorization\s*:\s*bearer|bearer[_-]?token\s*[:=])\s*['\"]?[A-Za-z0-9._~+/-]{16,}"),
            "bearer credential material",
        ),
        (
            "personal_home_path",
            "blocking",
            re.compile(r"/(?:home|Users)/(?!example(?:/|\b)|test(?:/|\b)|user(?:/|\b)|runner(?:/|\b)|workspace(?:/|\b))[A-Za-z0-9._-]+"),
            "non-generic home path",
        ),
        (
            "host_profile_path",
            "review",
            re.compile(re.escape(host_profile_marker) + r"(?:/|\b)"),
            "OS-specific host profile reference",
        ),
        (
            "private_network_address",
            "review",
            re.compile(r"(?<![0-9])(?:10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})(?![0-9])"),
            "private network topology reference",
        ),
    ]


def content_findings(relative: Path, absolute: Path) -> list[dict[str, Any]]:
    if not absolute.is_file() or absolute.stat().st_size > MAX_TEXT_BYTES:
        return []
    data = absolute.read_bytes()
    if b"\0" in data[:8192]:
        return [finding("binary_file", "review", relative, data[:256], "binary content requires explicit licensing review")]
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return [finding("non_utf8_file", "review", relative, data[:256], "non-UTF-8 content requires explicit review")]
    results: list[dict[str, Any]] = []
    for class_name, severity, pattern, reason in content_rules():
        match = pattern.search(text)
        if match is None:
            continue
        line = text.count("\n", 0, match.start()) + 1
        results.append(finding(class_name, severity, relative, match.group(0).encode("utf-8"), reason, line=line))
    return results


def audit(root: Path) -> dict[str, Any]:
    root = root.expanduser().resolve()
    findings: list[dict[str, Any]] = []
    file_count = 0
    for directory, dirnames, filenames in os.walk(root, followlinks=False):
        current = Path(directory)
        dirnames[:] = sorted(name for name in dirnames if name != ".git")
        for name in list(dirnames):
            path = current / name
            relative = path.relative_to(root)
            directory_findings = path_findings(relative, path)
            findings.extend(directory_findings)
            if any(item["severity"] == "blocking" for item in directory_findings):
                dirnames.remove(name)
        for name in sorted(filenames):
            path = current / name
            relative = path.relative_to(root)
            file_count += 1
            findings.extend(path_findings(relative, path))
            if not path.is_symlink():
                findings.extend(content_findings(relative, path))
    findings.sort(key=lambda item: (item["severity"] != "blocking", item["class"], item["path"], item.get("line", 0)))
    counts = {
        severity: sum(1 for item in findings if item["severity"] == severity)
        for severity in ("blocking", "review")
    }
    return {
        "schema": "aoa_session_memory_public_tree_audit_v1",
        "ok": counts["blocking"] == 0,
        "root": root.as_posix(),
        "file_count": file_count,
        "counts": counts,
        "findings": findings,
        "value_exposure": "class, path, line, reason, and safe fingerprint only",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit the current repository tree without printing secret values")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--fail-on", choices=("blocking", "review", "none"), default="blocking")
    args = parser.parse_args()
    result = audit(args.root)
    print(json.dumps(result, indent=2, sort_keys=True))
    threshold = SEVERITY_RANK[args.fail_on]
    return 1 if any(SEVERITY_RANK[item["severity"]] >= threshold for item in result["findings"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
