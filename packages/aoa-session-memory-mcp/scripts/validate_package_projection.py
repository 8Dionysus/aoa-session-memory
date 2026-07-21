#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tomllib
from pathlib import Path
from typing import Any


MANIFEST_NAME = "package.manifest.json"
SCHEMA_NAME = "package.manifest.schema.json"
IGNORED_RUNTIME_PARTS = {".mypy_cache", ".pytest_cache", ".ruff_cache", "__pycache__", "build", "dist"}
IGNORED_RUNTIME_SUFFIXES = {".pyc", ".pyo"}
FORBIDDEN_MUTATION_TOKENS = (
    "_apply",
    "_distill",
    "_export",
    "_install",
    "_promote",
    "_reindex",
    "_relabel",
    "_repair",
    "_write",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _actual_files(root: Path) -> set[str]:
    return {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
        and path.name != MANIFEST_NAME
        and not IGNORED_RUNTIME_PARTS.intersection(path.relative_to(root).parts)
        and path.suffix not in IGNORED_RUNTIME_SUFFIXES
        and not any(part.endswith(".egg-info") for part in path.relative_to(root).parts)
    }


def validate(package_root: Path) -> list[str]:
    errors: list[str] = []
    package_root = package_root.expanduser().resolve()
    manifest_path = package_root / MANIFEST_NAME
    schema_path = package_root / SCHEMA_NAME
    try:
        manifest = _load_json(manifest_path)
        schema = _load_json(schema_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [str(exc)]

    try:
        from jsonschema import Draft202012Validator

        for error in sorted(Draft202012Validator(schema).iter_errors(manifest), key=lambda item: list(item.path)):
            location = "/".join(str(part) for part in error.path) or "<root>"
            errors.append(f"manifest schema {location}: {error.message}")
    except ImportError:
        errors.append("manifest schema validation requires jsonschema")

    declared = {str(item.get("path")): item for item in manifest.get("files", []) if isinstance(item, dict)}
    actual = _actual_files(package_root)
    if actual != set(declared):
        for path in sorted(set(declared) - actual):
            errors.append(f"manifest file missing: {path}")
        for path in sorted(actual - set(declared)):
            errors.append(f"manifest file unknown: {path}")
    for relative, item in sorted(declared.items()):
        path = package_root / relative
        if not path.is_file():
            continue
        digest = _sha256(path)
        if digest != item.get("sha256"):
            errors.append(f"manifest digest mismatch: {relative}")
        if path.stat().st_size != item.get("size"):
            errors.append(f"manifest size mismatch: {relative}")
        mode = "0755" if path.stat().st_mode & 0o111 else "0644"
        if mode != item.get("mode"):
            errors.append(f"manifest mode mismatch: {relative}")

    src_root = package_root / "src"
    sys.dont_write_bytecode = True
    sys.path.insert(0, src_root.as_posix())
    try:
        from aoa_session_memory_mcp.contract import export_contract

        current_contract = export_contract()
    except (ImportError, SystemExit) as exc:
        errors.append(f"cannot load projected MCP contract: {exc}")
        current_contract = {}
    finally:
        if sys.path and sys.path[0] == src_root.as_posix():
            sys.path.pop(0)

    for key in ("root_discovery", "authority_boundary", "mcp_surface"):
        if current_contract.get(key) != manifest.get(key):
            errors.append(f"projected MCP contract mismatch: {key}")

    tools = current_contract.get("mcp_surface", {}).get("tools", [])
    for tool in tools:
        name = str(tool.get("name", ""))
        annotations = tool.get("annotations") or {}
        expected = {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        }
        for key, value in expected.items():
            if annotations.get(key) is not value:
                errors.append(f"unsafe or missing annotation: {name}.{key}")
        if any(token in name.casefold() for token in FORBIDDEN_MUTATION_TOKENS):
            errors.append(f"forbidden mutation tool: {name}")

    try:
        with (package_root / "pyproject.toml").open("rb") as handle:
            project = tomllib.load(handle)["project"]
    except (OSError, KeyError, tomllib.TOMLDecodeError) as exc:
        errors.append(f"cannot read package metadata: {exc}")
        project = {}
    package = manifest.get("package", {})
    if project.get("name") != package.get("distribution"):
        errors.append("package distribution mismatch")
    if project.get("version") != package.get("version"):
        errors.append("package version mismatch")
    if project.get("requires-python") != manifest.get("compatibility", {}).get("python"):
        errors.append("Python compatibility mismatch")
    if project.get("scripts") != manifest.get("entrypoints"):
        errors.append("entrypoint mismatch")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the standalone aoa-session-memory MCP package projection")
    parser.add_argument("--package-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    errors = validate(args.package_root)
    if errors:
        print(json.dumps({"ok": False, "errors": errors}, indent=2))
        return 1
    print(json.dumps({"ok": True, "package_root": args.package_root.expanduser().resolve().as_posix()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
