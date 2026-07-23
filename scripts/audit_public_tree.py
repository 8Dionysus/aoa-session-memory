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
EMPTY_SESSION_SKELETON_PATHS = frozenset(
    {
        Path("sessions/INDEX.md"),
        Path("sessions/index.json"),
    }
)
EMPTY_SESSION_READ_ORDER = [
    "AGENTS.md",
    "INDEX.md",
    "../SESSION_NAMES.md",
    "../session-registry.json",
    "<session>/AGENTS.md",
    "<session>/SESSION.md",
    "<session>/session.index.json",
    "<session>/session.manifest.json",
    "<session>/segments/*.index.json",
]


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


def empty_session_index_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Sessions Directory Index",
        "",
        "Generated table of contents for the session archive directory.",
        "",
        f"- generated_at: `{payload['generated_at']}`",
        "- session_count: `0`",
        "- named_session_count: `0`",
        "- machine index: `./index.json`",
        "- name map: `../SESSION_NAMES.md`",
        "",
        "## Read Order",
        "",
    ]
    lines.extend(
        f"{index}. `{item}`"
        for index, item in enumerate(EMPTY_SESSION_READ_ORDER, start=1)
    )
    lines.extend(
        [
            "",
            "## Naming Readiness",
            "",
            "- No readiness data generated.",
            "",
            "## Naming Work Queue",
            "",
            "- No naming work is currently queued.",
            "",
            "## Named Sessions",
            "",
            "- No semantic session names have been attached yet.",
            "",
            "## Largest Sessions",
            "",
            "",
            "## All Sessions By Date",
            "",
        ]
    )
    return "\n".join(lines)


def verified_empty_session_skeleton_paths(root: Path) -> frozenset[Path]:
    index_path = root / "sessions" / "index.json"
    markdown_path = root / "sessions" / "INDEX.md"
    if not index_path.is_file() or not markdown_path.is_file():
        return frozenset()
    try:
        payload = json.loads(index_path.read_text(encoding="utf-8"))
        markdown = markdown_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return frozenset()
    generated_at = payload.get("generated_at") if isinstance(payload, dict) else None
    if not isinstance(generated_at, str) or re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z",
        generated_at,
    ) is None:
        return frozenset()
    expected_payload = {
        "schema_version": 1,
        "artifact_type": "sessions_directory_index",
        "generated_at": generated_at,
        "session_count": 0,
        "named_session_count": 0,
        "naming_readiness_counts": {"by_status": {}, "by_route": {}},
        "naming_work_queue": [],
        "sessions_root": "sessions",
        "read_order": EMPTY_SESSION_READ_ORDER,
        "by_date": {},
        "largest_sessions": [],
        "named_sessions": [],
        "sessions": [],
    }
    if payload != expected_payload or markdown != empty_session_index_markdown(payload):
        return frozenset()
    return EMPTY_SESSION_SKELETON_PATHS


def path_findings(
    relative: Path,
    absolute: Path,
    *,
    allowed_session_paths: frozenset[Path] = frozenset(),
) -> list[dict[str, Any]]:
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
    if (
        len(relative.parts) > 1
        and relative.parts[:1] == ("sessions",)
        and relative != Path("sessions/AGENTS.md")
        and relative not in allowed_session_paths
    ):
        results.append(finding("session_material", "blocking", relative, encoded, "session material is private runtime evidence"))
    if name == ".env" or (name.startswith(".env.") and name not in {".env.example", ".env.sample"}):
        results.append(finding("environment_file", "blocking", relative, encoded, "environment files may contain credentials"))
    if absolute.suffix.casefold() in BLOCKING_SUFFIXES or name.casefold().endswith(ARCHIVE_SUFFIXES):
        results.append(finding("runtime_or_release_artifact", "blocking", relative, encoded, "database, log, or built release artifact is not source"))
    if absolute.is_file() and absolute.stat().st_size > MAX_TEXT_BYTES:
        results.append(finding("large_file", "review", relative, encoded, "large files require explicit history and licensing review"))
    return results


def content_rules() -> list[tuple[str, str, Pattern[str], str]]:
    pem_marker_pattern = "-----BEGIN " + r"(?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"
    host_profile_marker = "/srv/" + "AbyssOS"
    return [
        ("private_key", "blocking", re.compile(pem_marker_pattern), "private-key material"),
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
            re.compile(
                r"(?i)\b(?:author"
                r"ization\s*:\s*bearer|bearer[_-]?token\s*[:=])"
                r"\s*['\"]?[A-Za-z0-9._~+/-]{16,}"
            ),
            "credential material in an authorization header",
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
        for match in pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            results.append(finding(class_name, severity, relative, match.group(0).encode("utf-8"), reason, line=line))
    return results


def audit(root: Path) -> dict[str, Any]:
    root = root.expanduser().resolve()
    findings: list[dict[str, Any]] = []
    file_count = 0
    allowed_session_paths = verified_empty_session_skeleton_paths(root)
    for directory, dirnames, filenames in os.walk(root, followlinks=False):
        current = Path(directory)
        dirnames[:] = sorted(name for name in dirnames if name != ".git")
        for name in list(dirnames):
            path = current / name
            relative = path.relative_to(root)
            directory_findings = path_findings(
                relative,
                path,
                allowed_session_paths=allowed_session_paths,
            )
            findings.extend(directory_findings)
            if any(item["severity"] == "blocking" for item in directory_findings):
                dirnames.remove(name)
        for name in sorted(filenames):
            path = current / name
            relative = path.relative_to(root)
            file_count += 1
            findings.extend(
                path_findings(
                    relative,
                    path,
                    allowed_session_paths=allowed_session_paths,
                )
            )
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
