#!/usr/bin/env python3
"""Install the source-owned session-memory skill interface as a bounded overlay.

The normal session-memory installer owns the portable kernel and its runtime
stores.  This module owns a smaller, independently reversible component: the
capability home read models and selected skill packages.  It deliberately does
not call ``copy_portable_bundle``.  The component is admitted only when the
source is a clean Git checkout, the caller names the aoa-skills contract
checkout explicitly, and the target has a valid unchanged kernel install
profile.

The command line has three verbs:

``check``
    Perform the complete read-only preflight and print a JSON plan.
``install`` / ``execute``
    Apply the plan after ``--force`` has explicitly authorized replacing a
    selected component.
``rollback``
    Verify the current after-state and restore the selected paths and the
    previous component receipt from the durable backup.

The receipt and backup are runtime diagnostics.  They are not part of the
portable source and do not confer prompt selection, invocation, routing
quality, runtime health, or outcome evidence.
"""

from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable, Iterable, Mapping, Sequence
import uuid


# ``scripts`` is on sys.path when this file is run directly.  The fallback is
# useful for callers importing this module from an arbitrary working directory.
try:
    import aoa_session_memory as _session_memory
except ModuleNotFoundError:  # pragma: no cover - exercised by direct importers
    _SCRIPT_DIR = Path(__file__).resolve().parent
    if str(_SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(_SCRIPT_DIR))
    import aoa_session_memory as _session_memory


runtime_install_source_provenance = (
    _session_memory.runtime_install_source_provenance
)
runtime_install_profile_status = _session_memory.runtime_install_profile_status


SCHEMA_VERSION = "aoa_session_memory_skill_projection_v1"
RECEIPT_RELATIVE = Path("diagnostics/skill-projection-install.json")
ROLLBACK_OUTCOME_RELATIVE = Path("diagnostics/skill-projection-rollback.json")
BACKUP_PARENT_RELATIVE = Path("diagnostics/skill-projection-backups")
BACKUP_MANIFEST_NAME = "backup-manifest.json"
PREVIOUS_RECEIPT_NAME = "previous-receipt.bin"
PREVIOUS_RECEIPT_STATE_NAME = "previous-receipt.json"
STAGE_PREFIX = ".skill-projection-stage-"
SOURCE_SKIP_RELATIVE = Path("scripts/install_skill_interface.py")

# This is the fixed interface closure.  The two package names are also the
# only default prompt-visible routers; additional names must be graph-declared
# and are explicit ``--skill`` values.
FIXED_SOURCE_RELATIVE = (
    Path("capabilities/AGENTS.md"),
    Path("capabilities/port.manifest.json"),
    Path("capabilities/families/session-memory.yaml"),
    Path("generated/capability_graph.json"),
    Path("generated/capability_graph.md"),
    Path("skills/AGENTS.md"),
    Path("skills/port.manifest.json"),
)
DEFAULT_SKILLS = (
    "aoa-session-memory-global-route",
    "aoa-session-memory-evidence-route",
)
GLOBAL_ROUTER_RELATIVE = Path(
    "skills/aoa-session-memory-global-route/references/capability-router.md"
)
SKILL_NAME_RE = r"[A-Za-z0-9][A-Za-z0-9._-]*"

# ``copy_portable_bundle`` renders this example for the selected runtime and
# preserves these generated map artifacts.  They are runtime-owned overlays,
# so an old value does not constitute unselected source drift.
RUNTIME_GENERATED_RELATIVES = {
    Path("hooks/codex-hooks.user.example.json"),
    Path("maps/INDEX.md"),
    Path("maps/index.json"),
    Path("maps/index-state.json"),
    Path("maps/entity-registry.json"),
    Path("maps/entity-registry.md"),
}


class SkillProjectionError(ValueError):
    """Expected preflight, compare-and-swap, or rollback failure."""


class PreflightError(SkillProjectionError):
    def __init__(self, diagnostics: Sequence[str], payload: Mapping[str, Any] | None = None):
        self.diagnostics = list(dict.fromkeys(str(item) for item in diagnostics))
        self.payload = dict(payload or {})
        super().__init__("; ".join(self.diagnostics) or "skill projection preflight failed")


@dataclass(frozen=True)
class SourcePackage:
    name: str
    root: Path
    version: str
    fingerprint: str
    graph_node_id: str
    declared_files: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class Plan:
    source_root: Path
    skills_root: Path
    workspace_root: Path
    target_root: Path
    source_identity: dict[str, Any]
    owner_validation: dict[str, Any]
    base_profile: dict[str, Any]
    source_metadata: dict[str, Any]
    selected_skills: tuple[str, ...]
    selected_roots: tuple[Path, ...]
    source_roots: tuple[dict[str, Any], ...]
    target_roots: tuple[dict[str, Any], ...]
    source_files: dict[str, dict[str, Any]]
    target_files: dict[str, dict[str, Any]]
    unselected_token: str
    source_token: str
    target_cas_token: str
    previous_receipt: dict[str, Any]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256_json(value: Any) -> str:
    return _sha256_bytes(_canonical_json(value))


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def _mode_text(value: int | None) -> str | None:
    return None if value is None else format(int(value), "04o")


def _resolve(path: Path | str) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def _safe_relative(value: Path | str, *, label: str) -> Path:
    path = Path(value)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise SkillProjectionError(f"{label} must be a non-empty safe relative path: {value!r}")
    if any(part in {"", "."} for part in path.parts):
        raise SkillProjectionError(f"{label} contains an unsupported path component: {value!r}")
    return path


def _root_ready(path: Path, *, label: str) -> Path:
    lexical = Path(path).expanduser()
    if lexical.is_symlink():
        raise SkillProjectionError(f"{label} must not be a symlink: {lexical}")
    root = _resolve(lexical)
    if root.is_symlink():
        raise SkillProjectionError(f"{label} must not be a symlink: {root}")
    if not root.exists() or not root.is_dir():
        raise SkillProjectionError(f"{label} directory is missing: {root}")
    return root


def _path_inside(root: Path, relative: Path, *, label: str) -> Path:
    rel = _safe_relative(relative, label=label)
    candidate = root.joinpath(rel)
    current = root
    for part in rel.parts:
        current = current / part
        if current.is_symlink():
            raise SkillProjectionError(
                f"{label} path component must not be a symlink: {rel.as_posix()}"
            )
    return candidate


def _record(path: Path, *, state: str = "file") -> dict[str, Any]:
    if path.is_symlink():
        raise SkillProjectionError(f"path must be a regular non-symlink file: {path}")
    if not path.exists() or not path.is_file():
        raise SkillProjectionError(f"path is not a regular file: {path}")
    raw = path.read_bytes()
    mode = _mode(path)
    return {
        "state": state,
        "sha256": _sha256_bytes(raw),
        "bytes": len(raw),
        "mode": mode,
        "mode_text": _mode_text(mode),
        "executable": bool(mode & 0o111),
    }


def _absent_record() -> dict[str, Any]:
    return {
        "state": "absent",
        "sha256": None,
        "bytes": 0,
        "mode": None,
        "mode_text": None,
    }


def _snapshot_tree(path: Path, *, relative_root: Path) -> dict[str, Any]:
    """Snapshot a selected file or directory, retaining all pre-state files."""
    if path.is_symlink():
        raise SkillProjectionError(
            f"target/source selected path must not be a symlink: {relative_root.as_posix()}"
        )
    if not path.exists():
        return {
            "path": relative_root.as_posix(),
            "state": "absent",
            "mode": None,
            "mode_text": None,
            "files": [],
        }
    if path.is_file():
        item = _record(path)
        item["path"] = relative_root.as_posix()
        return {
            "path": relative_root.as_posix(),
            "state": "file",
            "mode": item["mode"],
            "mode_text": item["mode_text"],
            "files": [item],
        }
    if not path.is_dir():
        raise SkillProjectionError(
            f"selected path must be a regular file or directory: {relative_root.as_posix()}"
        )
    files: list[dict[str, Any]] = []
    for child in sorted(path.rglob("*"), key=lambda item: item.as_posix()):
        child_rel = child.relative_to(path)
        if child.is_symlink():
            raise SkillProjectionError(
                f"selected path contains a symlink: "
                f"{relative_root.joinpath(child_rel).as_posix()}"
            )
        if child.is_dir():
            continue
        if not child.is_file():
            raise SkillProjectionError(
                f"selected path contains a non-regular entry: "
                f"{relative_root.joinpath(child_rel).as_posix()}"
            )
        item = _record(child)
        item["path"] = relative_root.joinpath(child_rel).as_posix()
        files.append(item)
    root_mode = _mode(path)
    return {
        "path": relative_root.as_posix(),
        "state": "directory",
        "mode": root_mode,
        "mode_text": _mode_text(root_mode),
        "files": files,
    }


def _flatten_roots(roots: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for root in roots:
        for item in root.get("files", []):
            if isinstance(item, Mapping) and isinstance(item.get("path"), str):
                result[str(item["path"])] = dict(item)
    return result


def _root_snapshots_equal(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    if left.get("path") != right.get("path") or left.get("state") != right.get("state"):
        return False
    if left.get("mode") != right.get("mode"):
        return False
    left_files = left.get("files") if isinstance(left.get("files"), list) else []
    right_files = right.get("files") if isinstance(right.get("files"), list) else []
    def normalized(items: list[Any]) -> list[dict[str, Any]]:
        return [
            {
                "path": str(item.get("path")),
                "state": str(item.get("state")),
                "sha256": item.get("sha256"),
                "bytes": int(item.get("bytes") or 0),
                "mode": item.get("mode"),
            }
            for item in items
            if isinstance(item, Mapping)
        ]
    return normalized(left_files) == normalized(right_files)


def _snapshot_roots(root: Path, relatives: Sequence[Path]) -> tuple[dict[str, Any], ...]:
    return tuple(
        _snapshot_tree(
            _path_inside(root, relative, label="selected target path"),
            relative_root=relative,
        )
        for relative in relatives
    )


def _remove_path(path: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if path.is_symlink() or path.is_file():
        path.unlink()
        return
    if path.is_dir():
        shutil.rmtree(path)
        return
    path.unlink()


def _fsync_file(path: Path) -> None:
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def _fsync_dir(path: Path) -> None:
    try:
        fd = os.open(str(path), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _atomic_write(path: Path, raw: bytes, *, prefix: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=prefix, suffix=".tmp", dir=str(path.parent))
    temp = Path(name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
        _fsync_dir(path.parent)
    finally:
        if temp.exists() or temp.is_symlink():
            temp.unlink()


def _load_json(path: Path, *, label: str) -> Any:
    if path.is_symlink() or not path.is_file():
        raise SkillProjectionError(f"{label} must be a regular file: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SkillProjectionError(f"{label} is unreadable or invalid JSON: {path}") from exc


def _graph_skill_file_records(
    source_root: Path,
    graph: Mapping[str, Any],
    *,
    projection_paths: set[str],
) -> tuple[dict[str, dict[str, Any]], dict[str, Path], list[str]]:
    """Read only the graph-declared skill package closure.

    The runtime kernel is intentionally outside this comparison.  The owner
    validator already checks the complete source graph; this function supplies
    the narrow source/target parity boundary for graph-declared skill packages
    that the overlay leaves untouched.
    """
    nodes = graph.get("nodes")
    if not isinstance(nodes, list):
        raise SkillProjectionError("capability graph nodes are missing")
    records: dict[str, dict[str, Any]] = {}
    package_roots: dict[str, Path] = {}
    diagnostics: list[str] = []
    for node in nodes:
        if not isinstance(node, Mapping) or node.get("kind") != "skill":
            continue
        node_id = str(node.get("id") or "")
        if not node_id.startswith("skill."):
            continue
        name = node_id.removeprefix("skill.")
        _safe_skill_name(name)
        binding = node.get("binding")
        package = node.get("package")
        if not isinstance(binding, Mapping) or not isinstance(package, Mapping):
            raise SkillProjectionError(f"graph skill package metadata is incomplete: {name}")
        binding_ref = _safe_relative(
            str(binding.get("ref") or ""),
            label="graph skill binding",
        )
        if binding_ref != Path("skills") / name / "SKILL.md":
            raise SkillProjectionError(f"graph skill binding escapes package: {name}")
        package_root = Path("skills") / name
        package_roots[name] = package_root
        declared = package.get("files")
        if not isinstance(declared, list) or not declared:
            raise SkillProjectionError(f"graph skill package files are missing: {name}")
        declared_paths: set[str] = set()
        for row in declared:
            if not isinstance(row, Mapping):
                raise SkillProjectionError(f"graph skill package row is invalid: {name}")
            relative = _safe_relative(str(row.get("path") or ""), label="graph package file")
            if not relative.as_posix().startswith(package_root.as_posix() + "/"):
                raise SkillProjectionError(f"graph package file escapes package: {relative.as_posix()}")
            relative_text = relative.as_posix()
            declared_paths.add(relative_text)
            path = _path_inside(source_root, relative, label="graph package source file")
            observed = _record(path)
            if any(
                row.get(key) != observed[key]
                for key in ("sha256", "bytes", "executable")
            ):
                raise SkillProjectionError(
                    f"graph package source metadata mismatch: {relative_text}"
                )
            if relative_text not in projection_paths:
                records[relative_text] = observed
        root_path = _path_inside(source_root, package_root, label="graph skill package root")
        if root_path.is_symlink() or not root_path.is_dir():
            raise SkillProjectionError(f"graph skill package root is missing or symlinked: {name}")
        actual_paths: set[str] = set()
        for child in sorted(root_path.rglob("*"), key=lambda value: value.as_posix()):
            relative_text = child.relative_to(source_root).as_posix()
            if child.is_symlink():
                raise SkillProjectionError(f"graph skill package contains symlink: {relative_text}")
            if child.is_dir():
                continue
            if not child.is_file():
                raise SkillProjectionError(f"graph skill package contains non-regular entry: {relative_text}")
            if relative_text not in projection_paths:
                actual_paths.add(relative_text)
        extra = sorted(actual_paths - declared_paths)
        missing = sorted(declared_paths - actual_paths - projection_paths)
        diagnostics.extend(f"graph_package_source_extra:{item}" for item in extra)
        diagnostics.extend(f"graph_package_source_missing:{item}" for item in missing)
    if diagnostics:
        raise SkillProjectionError("; ".join(diagnostics))
    return records, package_roots, []


def _target_record(root: Path, relative: Path) -> dict[str, Any]:
    path = _path_inside(root, relative, label="unselected target path")
    if path.is_symlink():
        return {"state": "symlink", "sha256": None, "bytes": 0, "mode": None}
    if not path.exists():
        return _absent_record()
    if not path.is_file():
        return {"state": "non-regular", "sha256": None, "bytes": 0, "mode": None}
    return _record(path)


def _unselected_parity(
    source_root: Path,
    target_root: Path,
    *,
    graph: Mapping[str, Any],
    projection_paths: set[str],
    selected_skills: set[str],
    selected_files: set[str],
) -> tuple[list[str], dict[str, dict[str, Any]], str]:
    all_source_records, package_roots, _ = _graph_skill_file_records(
        source_root,
        graph,
        projection_paths=projection_paths,
    )
    source_records = {
        relative: record
        for relative, record in all_source_records.items()
        if relative not in selected_files
        and not any(
            relative == root.as_posix() or relative.startswith(root.as_posix() + "/")
            for name, root in package_roots.items()
            if name in selected_skills
        )
    }
    diagnostics: list[str] = []
    target_records: dict[str, dict[str, Any]] = {}
    for relative_text, source_record in sorted(source_records.items()):
        relative = Path(relative_text)
        target_record = _target_record(target_root, relative)
        target_records[relative_text] = target_record
        if target_record.get("state") != "file":
            diagnostics.append(f"unselected_target_mismatch:{relative_text}")
            continue
        if any(
            target_record.get(key) != source_record.get(key)
            for key in ("sha256", "bytes", "mode")
        ):
            diagnostics.append(f"unselected_target_mismatch:{relative_text}")
    extras: list[str] = []
    for name, package_root in sorted(package_roots.items()):
        if name in selected_skills:
            continue
        target_package_root = _path_inside(
            target_root,
            package_root,
            label="unselected target skill package",
        )
        if target_package_root.is_symlink():
            extras.append(f"{package_root.as_posix()}:symlink")
            continue
        if not target_package_root.exists():
            continue
        if not target_package_root.is_dir():
            extras.append(f"{package_root.as_posix()}:non-directory")
            continue
        for child in sorted(target_package_root.rglob("*"), key=lambda value: value.as_posix()):
            relative = child.relative_to(target_root)
            relative_text = relative.as_posix()
            if child.is_symlink():
                if relative_text not in selected_files:
                    extras.append(f"{relative_text}:symlink")
                continue
            if child.is_dir():
                continue
            if not child.is_file():
                extras.append(f"{relative_text}:non-regular")
                continue
            if relative_text in selected_files:
                continue
            if relative_text not in all_source_records:
                extras.append(relative_text)
    diagnostics.extend(f"unselected_target_extra:{item}" for item in extras)
    token_rows = [
        {
            "path": relative,
            "source": dict(source_records[relative]),
            "target": dict(target_records.get(relative) or _absent_record()),
        }
        for relative in sorted(source_records)
    ]
    token_rows.extend({"path": item, "extra": True} for item in extras)
    return diagnostics, source_records, _sha256_json(token_rows)


def _safe_skill_name(name: str) -> str:
    import re

    if not re.fullmatch(SKILL_NAME_RE, name):
        raise SkillProjectionError(f"skill name is not a safe graph package name: {name!r}")
    return name


def _contract_file_rows(skills_root: Path, graph: Mapping[str, Any]) -> dict[str, Any]:
    source = graph.get("source") if isinstance(graph.get("source"), Mapping) else {}
    contract = source.get("contract") if isinstance(source.get("contract"), Mapping) else {}
    if not contract:
        raise SkillProjectionError("capability graph has no shared contract metadata")
    rows = contract.get("contract_files")
    if not isinstance(rows, list):
        raise SkillProjectionError("capability graph shared contract files are missing")
    owner_repo = str(contract.get("owner_repo") or "")
    schema_path = str(contract.get("schema_path") or "")
    schema_sha256 = str(contract.get("schema_sha256") or "")
    validator_path_text = str(
        contract.get("validator_path")
        or "scripts/validation/validate_capability_home_port.py"
    )
    validator_sha256 = str(contract.get("validator_sha256") or "")
    if not owner_repo or not schema_path or not schema_sha256 or not validator_sha256:
        raise SkillProjectionError("capability graph shared contract identity is incomplete")
    checked: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise SkillProjectionError("capability graph shared contract row is invalid")
        relative = _safe_relative(str(row.get("path") or ""), label="shared contract path")
        expected = str(row.get("sha256") or "")
        path = _path_inside(skills_root, relative, label="shared contract path")
        if path.is_symlink() or not path.is_file():
            raise SkillProjectionError(f"shared contract file is missing: {relative.as_posix()}")
        observed = _sha256_file(path)
        if expected and observed != expected:
            raise SkillProjectionError(
                f"shared contract digest mismatch: {relative.as_posix()}"
            )
        checked.append({"path": relative.as_posix(), "sha256": observed})
    # The graph records the implementation validator under ``scripts/validation``
    # as part of the shared contract.  The owner-facing entrypoint is the
    # repository wrapper, which supplies the package import path and is the
    # stable command used by callers.
    contract_validator_path = _safe_relative(
        validator_path_text,
        label="shared validator path",
    )
    contract_validator = _path_inside(
        skills_root,
        contract_validator_path,
        label="shared validator path",
    )
    validator_path = Path("scripts/validate_capability_home_port.py")
    validator = _path_inside(skills_root, validator_path, label="owner validator entrypoint")
    if contract_validator.is_symlink() or not contract_validator.is_file():
        raise SkillProjectionError(
            f"shared validator implementation is missing: {contract_validator_path.as_posix()}"
        )
    if validator.is_symlink() or not validator.is_file():
        raise SkillProjectionError(f"owner validator entrypoint is missing: {validator_path.as_posix()}")
    checked_by_path = {str(row["path"]): str(row["sha256"]) for row in checked}
    if checked_by_path.get(schema_path) != schema_sha256:
        raise SkillProjectionError("shared contract schema digest does not match its file")
    if checked_by_path.get(contract_validator_path.as_posix()) != validator_sha256:
        raise SkillProjectionError("shared contract validator digest does not match its file")
    return {
        "owner_repo": owner_repo,
        "schema_path": schema_path,
        "schema_sha256": schema_sha256,
        "validator_path": validator_path.as_posix(),
        "validator_sha256": _sha256_file(contract_validator),
        "validator_entrypoint_sha256": _sha256_file(validator),
        "contract_validator_path": contract_validator_path.as_posix(),
        "contract_files": checked,
        "digest": "sha256:" + _sha256_json(contract),
    }


def _run_owner_validation(skills_root: Path, source_root: Path) -> dict[str, Any]:
    """Run the explicitly selected aoa-skills owner validator."""
    graph_path = source_root / "generated/capability_graph.json"
    graph = _load_json(graph_path, label="source capability graph")
    shared_contract = _contract_file_rows(skills_root, graph)
    validator = skills_root / shared_contract["validator_path"]
    command = [
        sys.executable,
        str(validator),
        "--owner-root",
        str(source_root),
        "--check-generated",
    ]
    try:
        environment = os.environ.copy()
        scripts_path = str(skills_root / "scripts")
        existing_pythonpath = environment.get("PYTHONPATH")
        environment["PYTHONPATH"] = (
            scripts_path
            if not existing_pythonpath
            else f"{scripts_path}{os.pathsep}{existing_pythonpath}"
        )
        completed = subprocess.run(
            command,
            cwd=str(skills_root),
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        return {
            "ok": False,
            "status": "validator_unavailable",
            "command": command,
            "returncode": None,
            "stdout": "",
            "stderr": str(exc),
            "shared_contract": shared_contract,
        }
    return {
        "ok": completed.returncode == 0,
        "status": "validated" if completed.returncode == 0 else "validator_failed",
        "command": command,
        "returncode": completed.returncode,
        "stdout": (completed.stdout or "")[-4000:],
        "stderr": (completed.stderr or "")[-4000:],
        "shared_contract": shared_contract,
    }


def _load_source_metadata(
    source_root: Path,
    *,
    selected_skills: Sequence[str],
) -> tuple[dict[str, Any], tuple[SourcePackage, ...], tuple[Path, ...]]:
    capabilities_manifest_path = source_root / "capabilities/port.manifest.json"
    skills_manifest_path = source_root / "skills/port.manifest.json"
    graph_path = source_root / "generated/capability_graph.json"
    graph_markdown_path = source_root / "generated/capability_graph.md"
    capabilities_manifest = _load_json(
        capabilities_manifest_path,
        label="source capabilities manifest",
    )
    skills_manifest = _load_json(skills_manifest_path, label="source skills manifest")
    graph = _load_json(graph_path, label="source capability graph")
    if not isinstance(capabilities_manifest, Mapping):
        raise SkillProjectionError("source capabilities manifest is not an object")
    if not isinstance(skills_manifest, Mapping):
        raise SkillProjectionError("source skills manifest is not an object")
    if not isinstance(graph, Mapping):
        raise SkillProjectionError("source capability graph is not an object")
    graph_source = graph.get("source")
    if not isinstance(graph_source, Mapping) or not str(graph_source.get("content_hash") or ""):
        raise SkillProjectionError("source capability graph content hash is missing")
    projection = capabilities_manifest.get("projection")
    if not isinstance(projection, Mapping):
        raise SkillProjectionError("source capabilities manifest projection is missing")
    router_text = str(projection.get("router_markdown") or "")
    if router_text != GLOBAL_ROUTER_RELATIVE.as_posix():
        raise SkillProjectionError("source global router projection path is not canonical")
    graph_json_text = str(projection.get("graph_json") or "")
    graph_md_text = str(projection.get("graph_markdown") or "")
    if graph_json_text != "generated/capability_graph.json" or graph_md_text != "generated/capability_graph.md":
        raise SkillProjectionError("source capability projection paths are not canonical")

    bundles = skills_manifest.get("bundles")
    if not isinstance(bundles, list):
        raise SkillProjectionError("source skills manifest bundles are missing")
    bundle_by_name = {
        str(bundle.get("name")): bundle
        for bundle in bundles
        if isinstance(bundle, Mapping) and bundle.get("name")
    }
    nodes = graph.get("nodes")
    if not isinstance(nodes, list):
        raise SkillProjectionError("source capability graph nodes are missing")
    node_by_id = {
        str(node.get("id")): node
        for node in nodes
        if isinstance(node, Mapping) and node.get("id")
    }
    package_specs: list[SourcePackage] = []
    package_roots: list[Path] = []
    selected_files = {
        relative.as_posix() for relative in FIXED_SOURCE_RELATIVE
    }
    selected_root_paths: list[Path] = list(FIXED_SOURCE_RELATIVE)
    package_metadata: list[dict[str, Any]] = []
    projection_paths = {
        str(projection.get("router_markdown")),
        str(projection.get("graph_json")),
        str(projection.get("graph_markdown")),
    }
    for name in selected_skills:
        safe_name = _safe_skill_name(str(name))
        node_id = f"skill.{safe_name}"
        node = node_by_id.get(node_id)
        if not isinstance(node, Mapping) or node.get("kind") != "skill":
            raise SkillProjectionError(f"selected skill is not graph-declared: {safe_name}")
        lifecycle = node.get("lifecycle")
        package = node.get("package")
        binding = node.get("binding")
        if not isinstance(lifecycle, Mapping) or not isinstance(package, Mapping) or not isinstance(binding, Mapping):
            raise SkillProjectionError(f"selected graph package metadata is incomplete: {safe_name}")
        version = str(lifecycle.get("version") or package.get("version") or "")
        fingerprint = str(package.get("fingerprint") or "")
        binding_ref = str(binding.get("ref") or "")
        expected_root = Path(f"skills/{safe_name}")
        if binding_ref != expected_root.joinpath("SKILL.md").as_posix():
            raise SkillProjectionError(f"selected skill binding is outside its package: {safe_name}")
        source_package_root = _path_inside(source_root, expected_root, label="source skill package")
        if source_package_root.is_symlink() or not source_package_root.is_dir():
            raise SkillProjectionError(f"selected skill package is missing or symlinked: {safe_name}")
        declared_files = package.get("files")
        if not isinstance(declared_files, list) or not declared_files:
            raise SkillProjectionError(f"selected skill package files are missing: {safe_name}")
        actual_rows: list[dict[str, Any]] = []
        actual_all: list[dict[str, Any]] = []
        for child in sorted(source_package_root.rglob("*"), key=lambda value: value.as_posix()):
            child_rel = child.relative_to(source_root).as_posix()
            if child.is_symlink():
                raise SkillProjectionError(f"selected skill package contains symlink: {child_rel}")
            if child.is_dir():
                continue
            if not child.is_file():
                raise SkillProjectionError(f"selected skill package contains non-regular entry: {child_rel}")
            row = {
                "path": child_rel,
                "sha256": _sha256_file(child),
                "bytes": child.stat().st_size,
                "executable": bool(child.stat().st_mode & 0o111),
                "mode": _mode(child),
            }
            actual_all.append(row)
            if child_rel not in projection_paths:
                actual_rows.append(row)
        declared_normalized: list[dict[str, Any]] = []
        for row in declared_files:
            if not isinstance(row, Mapping):
                raise SkillProjectionError(f"selected package row is invalid: {safe_name}")
            row_path = _safe_relative(str(row.get("path") or ""), label="selected package file")
            if not row_path.as_posix().startswith(expected_root.as_posix() + "/"):
                raise SkillProjectionError(f"selected package file escapes package root: {row_path.as_posix()}")
            path = _path_inside(source_root, row_path, label="selected package file")
            if path.is_symlink() or not path.is_file():
                raise SkillProjectionError(f"selected package file is missing: {row_path.as_posix()}")
            observed = {
                "path": row_path.as_posix(),
                "sha256": _sha256_file(path),
                "bytes": path.stat().st_size,
                "executable": bool(path.stat().st_mode & 0o111),
                "mode": _mode(path),
            }
            for key in ("sha256", "bytes", "executable"):
                if row.get(key) != observed[key]:
                    raise SkillProjectionError(
                        f"selected package metadata mismatch: {safe_name}:{row_path.as_posix()}"
                    )
            declared_normalized.append(observed)
        actual_identity = [
            {
                "path": row["path"],
                "sha256": row["sha256"],
                "executable": row["executable"],
            }
            for row in actual_rows
        ]
        declared_identity = [
            {
                "path": row["path"],
                "sha256": row["sha256"],
                "executable": row["executable"],
            }
            for row in declared_normalized
        ]
        if sorted(actual_identity, key=lambda item: item["path"]) != sorted(
            declared_identity, key=lambda item: item["path"]
        ):
            raise SkillProjectionError(f"selected package closure differs from graph: {safe_name}")
        observed_fingerprint = _sha256_json(
            sorted(actual_identity, key=lambda item: item["path"])
        )
        if fingerprint != observed_fingerprint:
            raise SkillProjectionError(f"selected package fingerprint mismatch: {safe_name}")
        bundle = bundle_by_name.get(safe_name)
        if isinstance(bundle, Mapping):
            if str(bundle.get("path") or "") != expected_root.as_posix():
                raise SkillProjectionError(f"selected skill manifest path mismatch: {safe_name}")
            if str(bundle.get("version") or "") != version:
                raise SkillProjectionError(f"selected skill manifest version mismatch: {safe_name}")
        package_specs.append(
            SourcePackage(
                name=safe_name,
                root=expected_root,
                version=version,
                fingerprint=fingerprint,
                graph_node_id=node_id,
                declared_files=tuple(declared_normalized),
            )
        )
        package_roots.append(expected_root)
        selected_root_paths.append(expected_root)
        selected_files.update(row["path"] for row in actual_all)
        package_metadata.append(
            {
                "name": safe_name,
                "path": expected_root.as_posix(),
                "version": version,
                "fingerprint": fingerprint,
                "graph_node_id": node_id,
                "declared_files": declared_normalized,
            }
        )
    # The generated router card remains part of the fixed interface even when
    # a caller explicitly selects only the evidence route.
    if GLOBAL_ROUTER_RELATIVE.as_posix() not in selected_files:
        selected_files.add(GLOBAL_ROUTER_RELATIVE.as_posix())
        selected_root_paths.append(GLOBAL_ROUTER_RELATIVE)
    for relative in FIXED_SOURCE_RELATIVE:
        path = _path_inside(source_root, relative, label="fixed source closure")
        if path.is_symlink() or not path.is_file():
            raise SkillProjectionError(f"fixed source closure file is missing: {relative.as_posix()}")
    router_path = _path_inside(source_root, GLOBAL_ROUTER_RELATIVE, label="generated global router")
    if router_path.is_symlink() or not router_path.is_file():
        raise SkillProjectionError("generated global router card is missing")
    source_files: dict[str, dict[str, Any]] = {}
    for relative in sorted(selected_files):
        path = _path_inside(source_root, Path(relative), label="selected source file")
        source_files[relative] = _record(path)
    metadata = {
        "capabilities_manifest": capabilities_manifest,
        "skills_manifest": skills_manifest,
        "graph": graph,
        "graph_source_content_hash": str(graph_source.get("content_hash")),
        "graph_projection_paths": sorted(projection_paths),
        "graph_json_sha256": _sha256_file(graph_path),
        "graph_markdown_sha256": _sha256_file(graph_markdown_path),
        "router_sha256": _sha256_file(router_path),
        "packages": package_metadata,
        "selected_files": source_files,
        "selected_roots": [path.as_posix() for path in selected_root_paths],
        "shared_contract": None,
    }
    return metadata, tuple(package_specs), tuple(dict.fromkeys(selected_root_paths))


def _base_profile(target_root: Path, workspace_root: Path) -> dict[str, Any]:
    status = runtime_install_profile_status(
        root=target_root,
        workspace_root=workspace_root,
    )
    if not status.get("valid"):
        raise SkillProjectionError(
            "invalid runtime install profile: "
            + ", ".join(str(item) for item in status.get("diagnostics", []))
        )
    path = _path_inside(target_root, _session_memory.INSTALL_PROFILE_PATH, label="base install profile")
    raw = path.read_bytes()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SkillProjectionError("base runtime install profile JSON is invalid") from exc
    if not isinstance(payload, Mapping):
        raise SkillProjectionError("base runtime install profile is not an object")
    return {
        "path": _session_memory.INSTALL_PROFILE_PATH.as_posix(),
        "sha256": _sha256_bytes(raw),
        "bytes": len(raw),
        "install_id": payload.get("install_id"),
        "source_ref": payload.get("source_ref"),
        "source_root": payload.get("source_root"),
        "source_commit": payload.get("source_commit"),
        "source_tree": payload.get("source_tree"),
        "source_script": payload.get("source_script"),
        "source_script_sha256": payload.get("source_script_sha256"),
        "source_worktree_clean": payload.get("source_worktree_clean"),
        "include_tests": payload.get("include_tests"),
        "raw_b64": base64.b64encode(raw).decode("ascii"),
        "status": status,
    }


def _previous_receipt(target_root: Path) -> dict[str, Any]:
    path = _path_inside(target_root, RECEIPT_RELATIVE, label="component receipt")
    if path.is_symlink():
        raise SkillProjectionError("component receipt must be a regular non-symlink file")
    if not path.exists():
        return {
            "present": False,
            "sha256": None,
            "bytes": 0,
            "raw_b64": None,
        }
    if not path.is_file():
        raise SkillProjectionError("component receipt must be a regular file")
    raw = path.read_bytes()
    return {
        "present": True,
        "sha256": _sha256_bytes(raw),
        "bytes": len(raw),
        "raw_b64": base64.b64encode(raw).decode("ascii"),
    }


def _source_identity_token(source_identity: Mapping[str, Any], selected_files: Mapping[str, Any]) -> str:
    return _sha256_json(
        {
            "identity": {
                key: source_identity.get(key)
                for key in (
                    "source_commit",
                    "source_tree",
                    "source_script_sha256",
                    "source_worktree_clean",
                )
            },
            "selected_files": selected_files,
        }
    )


def _target_cas_token(
    plan: Plan,
    *,
    source_files: Mapping[str, Mapping[str, Any]] | None = None,
) -> str:
    target_roots = _snapshot_roots(plan.target_root, plan.selected_roots)
    current_profile_path = plan.target_root / _session_memory.INSTALL_PROFILE_PATH
    profile_raw = current_profile_path.read_bytes() if current_profile_path.is_file() else b""
    current_receipt = _previous_receipt(plan.target_root)
    _diagnostics, _records, unselected_token = _unselected_parity(
        plan.source_root,
        plan.target_root,
        graph=plan.source_metadata["graph"],
        projection_paths=set(plan.source_metadata.get("graph_projection_paths", [])),
        selected_skills=set(plan.selected_skills),
        selected_files=set((source_files or plan.source_metadata["selected_files"]).keys()),
    )
    return _sha256_json(
        {
            "roots": list(target_roots),
            "profile_sha256": _sha256_bytes(profile_raw),
            "receipt": current_receipt,
            "unselected_token": unselected_token,
        }
    )


def _preflight(
    *,
    source_aoa_root: Path | str,
    skills_root: Path | str,
    workspace_root: Path | str,
    aoa_root: Path | str,
    selected_skills: Sequence[str] | None,
) -> Plan:
    diagnostics: list[str] = []
    try:
        source_root = _root_ready(Path(source_aoa_root), label="source .aoa root")
        explicit_skills_root = _root_ready(Path(skills_root), label="aoa-skills contract root")
        workspace = _root_ready(Path(workspace_root), label="workspace root")
        target = _root_ready(Path(aoa_root), label="target .aoa root")
    except SkillProjectionError as exc:
        raise PreflightError([str(exc)]) from exc
    if source_root == target:
        diagnostics.append("source and target .aoa roots must differ")
    names = tuple(dict.fromkeys(str(item) for item in (selected_skills or DEFAULT_SKILLS)))
    if not names:
        diagnostics.append("at least one graph-declared skill must be selected")
    try:
        source_identity = runtime_install_source_provenance(source_root)
    except Exception as exc:  # source helper has a broad subprocess/filesystem surface
        source_identity = {
            "status": "unresolved",
            "identity_status": "unresolved",
            "diagnostics": [f"source provenance helper failed: {exc}"],
        }
    if source_identity.get("status") != "current":
        diagnostics.extend(
            str(item) for item in source_identity.get("diagnostics", [])
            if str(item) != "source_worktree_dirty"
        )
    if not bool(source_identity.get("source_worktree_clean")):
        diagnostics.append("source_worktree_dirty")
    try:
        metadata, _packages, selected_roots = _load_source_metadata(
            source_root,
            selected_skills=names,
        )
        selected_files = dict(metadata["selected_files"])
    except SkillProjectionError as exc:
        diagnostics.append(str(exc))
        metadata = {
            "selected_files": {},
            "selected_roots": [],
            "packages": [],
            "graph_source_content_hash": "",
        }
        selected_roots = tuple()
        selected_files = {}
    try:
        owner_validation = _run_owner_validation(explicit_skills_root, source_root)
        metadata["shared_contract"] = owner_validation.get("shared_contract")
        if not owner_validation.get("ok"):
            diagnostics.append("aoa-skills owner validation failed")
    except SkillProjectionError as exc:
        owner_validation = {
            "ok": False,
            "status": "validator_preflight_failed",
            "diagnostics": [str(exc)],
        }
        diagnostics.append(str(exc))
    try:
        base_profile = _base_profile(target, workspace)
    except SkillProjectionError as exc:
        diagnostics.append(str(exc))
        base_profile = {
            "include_tests": True,
            "sha256": None,
            "install_id": None,
            "status": {"valid": False},
        }
    if selected_roots:
        try:
            source_roots = _snapshot_roots(source_root, selected_roots)
            target_roots = _snapshot_roots(target, selected_roots)
        except SkillProjectionError as exc:
            diagnostics.append(str(exc))
            source_roots = tuple()
            target_roots = tuple()
    else:
        source_roots = tuple()
        target_roots = tuple()
    target_files = _flatten_roots(target_roots)
    if selected_roots and selected_files:
        try:
            parity_diagnostics, _all_source_records, unselected_token = _unselected_parity(
                source_root,
                target,
                graph=metadata["graph"],
                projection_paths=set(metadata.get("graph_projection_paths", [])),
                selected_skills=set(names),
                selected_files=set(selected_files),
            )
            diagnostics.extend(parity_diagnostics)
        except SkillProjectionError as exc:
            diagnostics.append(str(exc))
            unselected_token = ""
    else:
        unselected_token = ""
    try:
        previous_receipt = _previous_receipt(target)
    except SkillProjectionError as exc:
        diagnostics.append(str(exc))
        previous_receipt = {"present": False, "sha256": None, "bytes": 0, "raw_b64": None}
    source_token = _source_identity_token(source_identity, selected_files)
    target_cas_token = _sha256_json(
        {
            "roots": list(target_roots),
            "profile_sha256": base_profile.get("sha256"),
            "receipt": previous_receipt,
            "unselected_token": unselected_token,
        }
    )
    if diagnostics:
        payload = {
            "source_root": str(source_root),
            "skills_root": str(explicit_skills_root),
            "workspace_root": str(workspace),
            "target_root": str(target),
            "selected_skills": list(names),
            "source_identity": source_identity,
            "owner_validation": owner_validation,
            "base_profile": {
                key: value
                for key, value in base_profile.items()
                if key != "raw_b64"
            },
            "source_metadata": {
                key: value
                for key, value in metadata.items()
                if key not in {"graph", "capabilities_manifest", "skills_manifest"}
            },
            "diagnostics": diagnostics,
        }
        raise PreflightError(diagnostics, payload)
    return Plan(
        source_root=source_root,
        skills_root=explicit_skills_root,
        workspace_root=workspace,
        target_root=target,
        source_identity=source_identity,
        owner_validation=owner_validation,
        base_profile=base_profile,
        source_metadata=metadata,
        selected_skills=names,
        selected_roots=selected_roots,
        source_roots=source_roots,
        target_roots=target_roots,
        source_files=selected_files,
        target_files=target_files,
        unselected_token=unselected_token,
        source_token=source_token,
        target_cas_token=target_cas_token,
        previous_receipt=previous_receipt,
    )


def _plan_payload(plan: Plan) -> dict[str, Any]:
    return {
        "source_root": str(plan.source_root),
        "skills_root": str(plan.skills_root),
        "workspace_root": str(plan.workspace_root),
        "target_root": str(plan.target_root),
        "selected_skills": list(plan.selected_skills),
        "selected_roots": [root.as_posix() for root in plan.selected_roots],
        "selected_paths": sorted(plan.source_files),
        "source_identity": plan.source_identity,
        "owner_validation": plan.owner_validation,
        "base_profile": {
            key: value for key, value in plan.base_profile.items() if key != "raw_b64"
        },
        "source_metadata": {
            key: value
            for key, value in plan.source_metadata.items()
            if key not in {"graph", "capabilities_manifest", "skills_manifest"}
        },
        "previous_receipt": {
            key: value
            for key, value in plan.previous_receipt.items()
            if key != "raw_b64"
        },
        "claim_limit": (
            "provenance and selected-byte parity only; no prompt selection, "
            "invocation, routing quality, runtime health, or outcome claim"
        ),
    }


def _copy_entry(source: Path, target: Path) -> None:
    if source.is_symlink():
        raise SkillProjectionError(f"cannot copy symlinked source entry: {source}")
    if source.is_dir():
        shutil.copytree(source, target, copy_function=shutil.copy2)
    elif source.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    else:
        raise SkillProjectionError(f"cannot copy non-regular source entry: {source}")


def _prepare_backup(plan: Plan, backup_root: Path) -> dict[str, Any]:
    backup_root.mkdir(parents=True, exist_ok=False)
    paths_root = backup_root / "paths"
    paths_root.mkdir()
    rows: list[dict[str, Any]] = []
    for index, relative in enumerate(plan.selected_roots):
        source_path = plan.target_root / relative
        stored = paths_root / str(index)
        snapshot = next(
            item for item in plan.target_roots if item.get("path") == relative.as_posix()
        )
        if snapshot.get("state") == "absent":
            rows.append({
                "index": index,
                "path": relative.as_posix(),
                "state": "absent",
                "snapshot": snapshot,
            })
            continue
        _copy_entry(source_path, stored)
        rows.append({
            "index": index,
            "path": relative.as_posix(),
            "state": str(snapshot.get("state")),
            "snapshot": snapshot,
            "stored": stored.relative_to(backup_root).as_posix(),
        })
    previous = plan.previous_receipt
    previous_state = {
        "present": bool(previous.get("present")),
        "sha256": previous.get("sha256"),
        "bytes": previous.get("bytes"),
    }
    (backup_root / PREVIOUS_RECEIPT_STATE_NAME).write_text(
        json.dumps(previous_state, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    if previous.get("present"):
        (backup_root / PREVIOUS_RECEIPT_NAME).write_bytes(
            base64.b64decode(str(previous.get("raw_b64") or ""))
        )
    manifest = {
        "schema_version": "aoa_session_memory_skill_projection_backup_v1",
        "operation_id": backup_root.name,
        "created_at": _utc_now(),
        "selected_roots": [root.as_posix() for root in plan.selected_roots],
        "paths": rows,
        "previous_receipt": previous_state,
    }
    manifest_path = backup_root / BACKUP_MANIFEST_NAME
    _atomic_write(
        manifest_path,
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n",
        prefix=".backup-manifest-",
    )
    for path in sorted(backup_root.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_file():
            _fsync_file(path)
    _fsync_dir(paths_root)
    _fsync_dir(backup_root)
    return manifest


def _stage(plan: Plan, stage_root: Path) -> None:
    for relative in plan.selected_roots:
        source = plan.source_root / relative
        staged = stage_root / relative
        _copy_entry(source, staged)
    for path in sorted(stage_root.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_file():
            _fsync_file(path)
    _fsync_dir(stage_root)


def _replace_staged_root(stage_root: Path, target_root: Path, relative: Path) -> None:
    staged = stage_root / relative
    target = target_root / relative
    if target.is_symlink():
        raise SkillProjectionError(f"target selected path became a symlink: {relative.as_posix()}")
    target.parent.mkdir(parents=True, exist_ok=True)
    _remove_path(target)
    os.replace(staged, target)
    _fsync_dir(target.parent)


def _validate_backup_manifest(
    plan: Plan,
    backup_root: Path,
    manifest: Mapping[str, Any],
    *,
    expected_before: Sequence[Mapping[str, Any]],
    expected_previous_receipt: Mapping[str, Any],
) -> None:
    """Validate a durable backup completely before any restore mutation."""
    if manifest.get("schema_version") != "aoa_session_memory_skill_projection_backup_v1":
        raise SkillProjectionError("backup manifest schema is unsupported")
    if str(manifest.get("operation_id") or "") != backup_root.name:
        raise SkillProjectionError("backup manifest operation id does not match its path")
    expected_roots = [root.as_posix() for root in plan.selected_roots]
    if manifest.get("selected_roots") != expected_roots:
        raise SkillProjectionError("backup manifest selected roots differ from receipt")
    paths = manifest.get("paths")
    if not isinstance(paths, list) or len(paths) != len(expected_roots):
        raise SkillProjectionError("backup manifest selected path rows are incomplete")
    rows_by_index: dict[int, Mapping[str, Any]] = {}
    for item in paths:
        if not isinstance(item, Mapping):
            raise SkillProjectionError("backup manifest selected path row is invalid")
        try:
            index = int(item.get("index"))
        except (TypeError, ValueError) as exc:
            raise SkillProjectionError("backup manifest selected path index is invalid") from exc
        if index in rows_by_index or index < 0 or index >= len(expected_roots):
            raise SkillProjectionError("backup manifest selected path indexes are not exact")
        if str(item.get("path") or "") != expected_roots[index]:
            raise SkillProjectionError("backup manifest selected path order differs from receipt")
        rows_by_index[index] = item
    if set(rows_by_index) != set(range(len(expected_roots))):
        raise SkillProjectionError("backup manifest selected path indexes are incomplete")
    if len(expected_before) != len(expected_roots):
        raise SkillProjectionError("expected selected before-state is incomplete")
    for index, relative in enumerate(plan.selected_roots):
        row = rows_by_index[index]
        snapshot = row.get("snapshot")
        if not isinstance(snapshot, Mapping) or not _root_snapshots_equal(snapshot, expected_before[index]):
            raise SkillProjectionError(f"backup snapshot differs from receipt before-state: {relative.as_posix()}")
        state = str(row.get("state") or "")
        if state != str(snapshot.get("state") or ""):
            raise SkillProjectionError(f"backup row state differs from snapshot: {relative.as_posix()}")
        if state == "absent":
            if row.get("stored") is not None:
                raise SkillProjectionError(f"absent backup unexpectedly has stored path: {relative.as_posix()}")
            continue
        stored_text = str(row.get("stored") or "")
        stored = _path_inside(backup_root, Path(stored_text), label="backup stored path")
        if not stored.exists() or stored.is_symlink():
            raise SkillProjectionError(f"backup stored path is missing or symlinked: {relative.as_posix()}")
        stored_snapshot = _snapshot_tree(stored, relative_root=relative)
        if not _root_snapshots_equal(stored_snapshot, snapshot):
            raise SkillProjectionError(f"backup stored bytes or modes differ: {relative.as_posix()}")
    previous = manifest.get("previous_receipt")
    if not isinstance(previous, Mapping):
        raise SkillProjectionError("backup previous receipt state is missing")
    for key in ("present", "sha256", "bytes"):
        if previous.get(key) != expected_previous_receipt.get(key):
            raise SkillProjectionError("backup previous receipt state differs from receipt")
    if bool(previous.get("present")):
        previous_path = backup_root / PREVIOUS_RECEIPT_NAME
        if previous_path.is_symlink() or not previous_path.is_file():
            raise SkillProjectionError("backup previous component receipt is missing")
        raw = previous_path.read_bytes()
        if _sha256_bytes(raw) != previous.get("sha256") or len(raw) != previous.get("bytes"):
            raise SkillProjectionError("backup previous component receipt bytes differ")
    previous_state_path = backup_root / PREVIOUS_RECEIPT_STATE_NAME
    if previous_state_path.is_symlink() or not previous_state_path.is_file():
        raise SkillProjectionError("backup previous receipt state file is missing")
    stored_previous_state = _load_json(
        previous_state_path,
        label="backup previous receipt state",
    )
    if stored_previous_state != dict(previous):
        raise SkillProjectionError("backup previous receipt state file differs from manifest")


def _restore_backup(
    plan: Plan,
    backup_root: Path,
    manifest: Mapping[str, Any],
    *,
    only_roots: Sequence[Path] | None = None,
    restore_receipt: bool = True,
) -> None:
    paths = manifest.get("paths")
    if not isinstance(paths, list):
        raise SkillProjectionError("backup manifest selected paths are missing")
    allowed_roots = {
        relative.as_posix() for relative in only_roots
    } if only_roots is not None else None
    for row in sorted(
        (item for item in paths if isinstance(item, Mapping)),
        key=lambda item: int(item.get("index") or 0),
    ):
        relative = _safe_relative(str(row.get("path") or ""), label="backup selected path")
        if allowed_roots is not None and relative.as_posix() not in allowed_roots:
            continue
        state = str(row.get("state") or "")
        snapshot = row.get("snapshot")
        if isinstance(snapshot, Mapping) and state != str(snapshot.get("state") or ""):
            raise SkillProjectionError(f"backup row state differs from snapshot: {relative.as_posix()}")
        target = _path_inside(plan.target_root, relative, label="backup selected path")
        _remove_path(target)
        if state == "absent":
            continue
        stored_text = str(row.get("stored") or "")
        stored = _path_inside(backup_root, Path(stored_text), label="backup stored path")
        if not stored.exists() or stored.is_symlink():
            raise SkillProjectionError(f"backup stored path is missing or symlinked: {relative.as_posix()}")
        _copy_entry(stored, target)
    if not restore_receipt:
        return
    previous = manifest.get("previous_receipt")
    if not isinstance(previous, Mapping):
        raise SkillProjectionError("backup previous receipt state is missing")
    receipt = _path_inside(plan.target_root, RECEIPT_RELATIVE, label="component receipt")
    _remove_path(receipt)
    if bool(previous.get("present")):
        previous_path = backup_root / PREVIOUS_RECEIPT_NAME
        if previous_path.is_symlink() or not previous_path.is_file():
            raise SkillProjectionError("backup previous component receipt is missing")
        receipt.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(previous_path, receipt)
    _fsync_dir(plan.target_root / "diagnostics")


def _selected_post_records(plan: Plan) -> tuple[dict[str, Any], ...]:
    return _snapshot_roots(plan.target_root, plan.selected_roots)


def _receipt_payload(
    plan: Plan,
    *,
    operation_id: str,
    backup_root: Path,
    before_roots: Sequence[Mapping[str, Any]],
    after_roots: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    installed_at = _utc_now()
    basis = {
        "schema_version": SCHEMA_VERSION,
        "operation_id": operation_id,
        "source_commit": plan.source_identity.get("source_commit"),
        "source_tree": plan.source_identity.get("source_tree"),
        "source_script_sha256": plan.source_identity.get("source_script_sha256"),
        "base_profile_sha256": plan.base_profile.get("sha256"),
        "base_install_id": plan.base_profile.get("install_id"),
        "selected_paths": sorted(plan.source_files),
        "installed_at": installed_at,
    }
    component_install_id = "sha256:" + _sha256_json(basis)
    after_files = _flatten_roots(after_roots)
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "runtime_skill_projection_install",
        "component": "session-memory-skill-interface",
        "component_install_id": component_install_id,
        "operation_id": operation_id,
        "installed_at": installed_at,
        "workspace_root": str(plan.workspace_root),
        "aoa_root": str(plan.target_root),
        "source_root": str(plan.source_root),
        "skills_root": str(plan.skills_root),
        "source_worktree_clean": bool(plan.source_identity.get("source_worktree_clean")),
        "source_identity": {
            key: plan.source_identity.get(key)
            for key in (
                "source_ref",
                "source_root",
                "source_commit",
                "source_tree",
                "source_script",
                "source_script_sha256",
                "source_worktree_clean",
            )
        },
        "installer_script_sha256": "sha256:" + _sha256_file(Path(__file__).resolve()),
        "shared_contract": plan.owner_validation.get("shared_contract"),
        "owner_validation": {
            "status": plan.owner_validation.get("status"),
            "returncode": plan.owner_validation.get("returncode"),
        },
        "base_profile": {
            "path": plan.base_profile.get("path"),
            "sha256": plan.base_profile.get("sha256"),
            "bytes": plan.base_profile.get("bytes"),
            "install_id": plan.base_profile.get("install_id"),
            "source_ref": plan.base_profile.get("source_ref"),
            "source_commit": plan.base_profile.get("source_commit"),
            "source_tree": plan.base_profile.get("source_tree"),
            "source_script_sha256": plan.base_profile.get("source_script_sha256"),
        },
        "selected_skills": list(plan.selected_skills),
        "selected_roots": [root.as_posix() for root in plan.selected_roots],
        "selected_paths": sorted(plan.source_files),
        "selected_before": list(before_roots),
        "selected_after": list(after_roots),
        "selected_after_files": after_files,
        "packages": plan.source_metadata.get("packages", []),
        "graph": {
            "content_hash": plan.source_metadata.get("graph_source_content_hash"),
            "json_sha256": plan.source_metadata.get("graph_json_sha256"),
            "markdown_sha256": plan.source_metadata.get("graph_markdown_sha256"),
            "router_sha256": plan.source_metadata.get("router_sha256"),
        },
        "base_profile_sha256": plan.base_profile.get("sha256"),
        "base_install_id": plan.base_profile.get("install_id"),
        "previous_component_receipt_sha256": plan.previous_receipt.get("sha256"),
        "previous_component_receipt": {
            key: plan.previous_receipt.get(key)
            for key in ("present", "sha256", "bytes")
        },
        "backup_root": str(backup_root),
        "unselected_target_token": plan.unselected_token,
        "claim_limit": (
            "provenance and selected-byte parity only; no prompt selection, "
            "invocation, routing quality, runtime health, or outcome claim"
        ),
    }


def _receipt_bytes(receipt: Mapping[str, Any]) -> bytes:
    return json.dumps(
        receipt,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
    ).encode("utf-8") + b"\n"


def _restore_after_failure(
    plan: Plan,
    backup_root: Path,
    manifest: Mapping[str, Any],
    *,
    stage_root: Path | None,
    replaced_roots: Sequence[Path],
    restore_receipt: bool,
) -> tuple[bool, str | None]:
    try:
        _validate_backup_manifest(
            plan,
            backup_root,
            manifest,
            expected_before=plan.target_roots,
            expected_previous_receipt=plan.previous_receipt,
        )
        _restore_backup(
            plan,
            backup_root,
            manifest,
            only_roots=replaced_roots,
            restore_receipt=restore_receipt,
        )
        if stage_root is not None:
            _remove_path(stage_root)
        return True, None
    except Exception as exc:  # keep the durable backup when recovery itself fails
        return False, str(exc)


def inspect_skill_projection(
    *,
    source_aoa_root: Path | str,
    skills_root: Path | str,
    workspace_root: Path | str,
    aoa_root: Path | str,
    selected_skills: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Return a read-only preflight payload."""
    try:
        plan = _preflight(
            source_aoa_root=source_aoa_root,
            skills_root=skills_root,
            workspace_root=workspace_root,
            aoa_root=aoa_root,
            selected_skills=selected_skills,
        )
    except PreflightError as exc:
        payload = dict(exc.payload)
        payload.setdefault("schema_version", SCHEMA_VERSION)
        payload["ok"] = False
        payload["status"] = "preflight_failed"
        payload["diagnostics"] = list(exc.diagnostics)
        return payload
    payload = _plan_payload(plan)
    payload.update({"schema_version": SCHEMA_VERSION, "ok": True, "status": "ready"})
    return payload


def install_skill_projection(
    *,
    source_aoa_root: Path | str,
    skills_root: Path | str,
    workspace_root: Path | str,
    aoa_root: Path | str,
    selected_skills: Sequence[str] | None = None,
    force: bool = False,
    replace_hook: Callable[[str, int], None] | None = None,
    before_commit_hook: Callable[[Plan], None] | None = None,
) -> dict[str, Any]:
    """Apply one source-owned skill projection with exact rollback on error."""
    try:
        plan = _preflight(
            source_aoa_root=source_aoa_root,
            skills_root=skills_root,
            workspace_root=workspace_root,
            aoa_root=aoa_root,
            selected_skills=selected_skills,
        )
    except PreflightError as exc:
        payload = dict(exc.payload)
        payload.update({
            "schema_version": SCHEMA_VERSION,
            "ok": False,
            "status": "preflight_failed",
            "diagnostics": list(exc.diagnostics),
        })
        return payload
    changed = any(
        not _root_snapshots_equal(source, target)
        for source, target in zip(plan.source_roots, plan.target_roots)
    )
    receipt_missing = not bool(plan.previous_receipt.get("present"))
    receipt_currentness: list[str] = []
    if not receipt_missing:
        receipt_path = _path_inside(
            plan.target_root,
            RECEIPT_RELATIVE,
            label="component receipt",
        )
        try:
            existing_receipt = _load_json(receipt_path, label="component receipt")
            if not isinstance(existing_receipt, Mapping):
                receipt_currentness = ["component_receipt_not_object"]
            else:
                receipt_currentness = _receipt_currentness_diagnostics(
                    plan,
                    existing_receipt,
                )
        except SkillProjectionError as exc:
            receipt_currentness = [str(exc)]
    if changed and not force:
        payload = _plan_payload(plan)
        payload.update({
            "schema_version": SCHEMA_VERSION,
            "ok": False,
            "status": "force_required",
            "diagnostics": [
                "selected component differs from target; pass --force to authorize replacement"
            ],
        })
        return payload
    if not changed and not receipt_missing and receipt_currentness and not force:
        payload = _plan_payload(plan)
        payload.update({
            "schema_version": SCHEMA_VERSION,
            "ok": False,
            "status": "receipt_stale",
            "diagnostics": receipt_currentness,
        })
        return payload
    if not changed and not receipt_missing and not receipt_currentness:
        payload = _plan_payload(plan)
        payload.update({
            "schema_version": SCHEMA_VERSION,
            "ok": True,
            "status": "already_current",
            "diagnostics": [],
        })
        return payload

    operation_id = f"{int(time.time())}-{uuid.uuid4().hex}"
    backup_root = plan.target_root / BACKUP_PARENT_RELATIVE / operation_id
    stage_root: Path | None = None
    backup_manifest: dict[str, Any] | None = None
    mutation_started = False
    replaced_roots: list[Path] = []
    receipt_mutation_started = False
    try:
        backup_manifest = _prepare_backup(plan, backup_root)
        stage_root = Path(tempfile.mkdtemp(prefix=STAGE_PREFIX, dir=str(plan.target_root)))
        _stage(plan, stage_root)
        if before_commit_hook is not None:
            before_commit_hook(plan)
        # Source and target are both CAS participants.  A source edit after
        # validation is as unsafe as a target edit, even before any rename.
        current_source_identity = runtime_install_source_provenance(plan.source_root)
        current_source_files = {
            relative: _record(plan.source_root / relative)
            for relative in sorted(plan.source_files)
        }
        if _source_identity_token(current_source_identity, current_source_files) != plan.source_token:
            raise SkillProjectionError("compare_and_swap_conflict: source changed after preflight")
        if _target_cas_token(plan) != plan.target_cas_token:
            raise SkillProjectionError("compare_and_swap_conflict: target changed after preflight")
        for index, relative in enumerate(plan.selected_roots):
            if replace_hook is not None:
                replace_hook(relative.as_posix(), index)
            mutation_started = True
            # Mark the root before entering the remove/rename pair.  If the
            # second rename fails, the first one may already have removed the
            # old target and this root must still be restored.
            replaced_roots.append(relative)
            _replace_staged_root(stage_root, plan.target_root, relative)
        after_roots = _selected_post_records(plan)
        if any(
            not _root_snapshots_equal(source, after)
            for source, after in zip(plan.source_roots, after_roots)
        ):
            raise SkillProjectionError("post-apply selected bytes or modes differ from source")
        profile_path = plan.target_root / _session_memory.INSTALL_PROFILE_PATH
        if _sha256_file(profile_path) != plan.base_profile.get("sha256"):
            raise SkillProjectionError("base install profile changed during skill overlay")
        parity_diagnostics, _records, parity_token = _unselected_parity(
            plan.source_root,
            plan.target_root,
            graph=plan.source_metadata["graph"],
            projection_paths=set(plan.source_metadata.get("graph_projection_paths", [])),
            selected_skills=set(plan.selected_skills),
            selected_files=set(plan.source_files),
        )
        if parity_diagnostics or parity_token != plan.unselected_token:
            raise SkillProjectionError(
                "post-apply unselected source parity changed: "
                + ", ".join(parity_diagnostics[:8])
            )
        receipt = _receipt_payload(
            plan,
            operation_id=operation_id,
            backup_root=backup_root,
            before_roots=plan.target_roots,
            after_roots=after_roots,
        )
        receipt_mutation_started = True
        mutation_started = True
        _atomic_write(
            plan.target_root / RECEIPT_RELATIVE,
            _receipt_bytes(receipt),
            prefix=".skill-projection-receipt-",
        )
        if stage_root is not None:
            _remove_path(stage_root)
        return {
            "schema_version": SCHEMA_VERSION,
            "ok": True,
            "status": "installed",
            "receipt": receipt,
            "backup_root": str(backup_root),
            "plan": _plan_payload(plan),
        }
    except Exception as exc:
        if backup_manifest is not None and mutation_started:
            restored, restore_error = _restore_after_failure(
                plan,
                backup_root,
                backup_manifest,
                stage_root=stage_root,
                replaced_roots=replaced_roots,
                restore_receipt=receipt_mutation_started,
            )
            if restored:
                # A failed operation has no live component receipt; leave its
                # durable backup only when the caller needs post-mortem repair.
                _remove_path(backup_root)
                return {
                    "schema_version": SCHEMA_VERSION,
                    "ok": False,
                    "status": "install_failed_rolled_back",
                    "diagnostics": [str(exc)],
                }
            return {
                "schema_version": SCHEMA_VERSION,
                "ok": False,
                "status": "install_failed_rollback_incomplete",
                "diagnostics": [str(exc), f"rollback failed: {restore_error}"],
                "backup_root": str(backup_root),
            }
        # A CAS conflict is detected before the first selected-root rename.
        # Never restore the preflight snapshot over a concurrent edit.  Only
        # our temporary stage and durable backup are owned at this point.
        if stage_root is not None:
            _remove_path(stage_root)
        if backup_root.exists():
            _remove_path(backup_root)
        conflict_status = (
            "compare_and_swap_conflict"
            if "compare_and_swap_conflict" in str(exc)
            else "install_failed_before_mutation"
        )
        return {
            "schema_version": SCHEMA_VERSION,
            "ok": False,
            "status": conflict_status,
            "diagnostics": [str(exc)],
        }


def _load_receipt(target_root: Path) -> tuple[dict[str, Any], bytes]:
    path = _path_inside(target_root, RECEIPT_RELATIVE, label="component receipt")
    if path.is_symlink() or not path.is_file():
        raise SkillProjectionError("component receipt is absent or not a regular file")
    raw = path.read_bytes()
    payload = _load_json(path, label="component receipt")
    if not isinstance(payload, Mapping) or payload.get("schema_version") != SCHEMA_VERSION:
        raise SkillProjectionError("component receipt schema is unsupported")
    return dict(payload), raw


def _receipt_after_matches(plan: Plan, receipt: Mapping[str, Any]) -> bool:
    selected_roots = receipt.get("selected_roots")
    if selected_roots != [root.as_posix() for root in plan.selected_roots]:
        return False
    expected = receipt.get("selected_after")
    if not isinstance(expected, list):
        return False
    current = _selected_post_records(plan)
    if len(current) != len(expected):
        return False
    if any(not isinstance(expected_item, Mapping) for expected_item in expected):
        return False
    return all(
        _root_snapshots_equal(actual, expected_item)
        for actual, expected_item in zip(current, expected)
    )


def _receipt_currentness_diagnostics(
    plan: Plan,
    receipt: Mapping[str, Any],
) -> list[str]:
    """Return concrete reasons an existing receipt is not current for ``plan``.

    A matching selected tree is insufficient for ``already_current``.  The
    receipt is also a provenance anchor for the source, shared contract,
    installer implementation, graph/package identities, and the unchanged
    base runtime profile.  Keep this check read-only so a stale or tampered
    receipt can never be silently accepted.
    """
    diagnostics: list[str] = []
    if receipt.get("schema_version") != SCHEMA_VERSION:
        diagnostics.append("component_receipt_schema_mismatch")
    if receipt.get("artifact_type") != "runtime_skill_projection_install":
        diagnostics.append("component_receipt_artifact_type_mismatch")
    if receipt.get("component") != "session-memory-skill-interface":
        diagnostics.append("component_receipt_component_mismatch")
    if str(receipt.get("workspace_root") or "") != str(plan.workspace_root):
        diagnostics.append("component_receipt_workspace_root_mismatch")
    if str(receipt.get("aoa_root") or "") != str(plan.target_root):
        diagnostics.append("component_receipt_target_root_mismatch")
    if str(receipt.get("source_root") or "") != str(plan.source_root):
        diagnostics.append("component_receipt_source_root_mismatch")
    if str(receipt.get("skills_root") or "") != str(plan.skills_root):
        diagnostics.append("component_receipt_skills_root_mismatch")

    identity = receipt.get("source_identity")
    if not isinstance(identity, Mapping):
        diagnostics.append("component_receipt_source_identity_missing")
    else:
        for key in (
            "source_ref",
            "source_root",
            "source_commit",
            "source_tree",
            "source_script",
            "source_script_sha256",
            "source_worktree_clean",
        ):
            if identity.get(key) != plan.source_identity.get(key):
                diagnostics.append(f"component_receipt_source_{key}_mismatch")
    if receipt.get("source_worktree_clean") is not True:
        diagnostics.append("component_receipt_source_not_clean")

    expected_installer_digest = "sha256:" + _sha256_file(Path(__file__).resolve())
    if receipt.get("installer_script_sha256") != expected_installer_digest:
        diagnostics.append("component_receipt_installer_script_mismatch")

    base = receipt.get("base_profile")
    if not isinstance(base, Mapping):
        diagnostics.append("component_receipt_base_profile_missing")
    else:
        for key in (
            "path",
            "sha256",
            "bytes",
            "install_id",
            "source_ref",
            "source_commit",
            "source_tree",
            "source_script_sha256",
        ):
            if base.get(key) != plan.base_profile.get(key):
                diagnostics.append(f"component_receipt_base_profile_{key}_mismatch")
    if receipt.get("base_profile_sha256") != plan.base_profile.get("sha256"):
        diagnostics.append("component_receipt_base_profile_sha256_mismatch")
    if receipt.get("base_install_id") != plan.base_profile.get("install_id"):
        diagnostics.append("component_receipt_base_install_id_mismatch")

    previous_state = receipt.get("previous_component_receipt")
    if not isinstance(previous_state, Mapping):
        diagnostics.append("component_receipt_previous_state_missing")
    else:
        if receipt.get("previous_component_receipt_sha256") != previous_state.get("sha256"):
            diagnostics.append("component_receipt_previous_state_anchor_mismatch")
        if previous_state.get("present") not in {True, False}:
            diagnostics.append("component_receipt_previous_state_present_invalid")
        if not isinstance(previous_state.get("bytes"), int) or int(previous_state.get("bytes")) < 0:
            diagnostics.append("component_receipt_previous_state_bytes_invalid")

    if receipt.get("selected_skills") != list(plan.selected_skills):
        diagnostics.append("component_receipt_selected_skills_mismatch")
    if receipt.get("selected_roots") != [root.as_posix() for root in plan.selected_roots]:
        diagnostics.append("component_receipt_selected_roots_mismatch")
    if receipt.get("selected_paths") != sorted(plan.source_files):
        diagnostics.append("component_receipt_selected_paths_mismatch")
    if not _receipt_after_matches(plan, receipt):
        diagnostics.append("component_receipt_selected_after_mismatch")
    after_files = receipt.get("selected_after_files")
    if not isinstance(after_files, Mapping):
        diagnostics.append("component_receipt_selected_after_files_missing")
    elif dict(after_files) != _flatten_roots(_selected_post_records(plan)):
        diagnostics.append("component_receipt_selected_after_files_mismatch")

    packages = receipt.get("packages")
    expected_packages = plan.source_metadata.get("packages", [])
    if packages != expected_packages:
        diagnostics.append("component_receipt_package_identity_mismatch")
    graph = receipt.get("graph")
    expected_graph = {
        "content_hash": plan.source_metadata.get("graph_source_content_hash"),
        "json_sha256": plan.source_metadata.get("graph_json_sha256"),
        "markdown_sha256": plan.source_metadata.get("graph_markdown_sha256"),
        "router_sha256": plan.source_metadata.get("router_sha256"),
    }
    if graph != expected_graph:
        diagnostics.append("component_receipt_graph_identity_mismatch")
    if receipt.get("shared_contract") != plan.owner_validation.get("shared_contract"):
        diagnostics.append("component_receipt_shared_contract_mismatch")
    if receipt.get("unselected_target_token") != plan.unselected_token:
        diagnostics.append("component_receipt_unselected_target_mismatch")

    backup_text = str(receipt.get("backup_root") or "")
    if not backup_text:
        diagnostics.append("component_receipt_backup_root_missing")
    else:
        backup = _resolve(Path(backup_text))
        expected_parent = _resolve(plan.target_root / BACKUP_PARENT_RELATIVE)
        try:
            backup.relative_to(expected_parent)
        except ValueError:
            diagnostics.append("component_receipt_backup_root_escapes_target")
        else:
            if backup.is_symlink() or not backup.is_dir():
                diagnostics.append("component_receipt_backup_missing")
            elif not (backup / BACKUP_MANIFEST_NAME).is_file():
                diagnostics.append("component_receipt_backup_manifest_missing")
    return list(dict.fromkeys(diagnostics))


def _rollback_expected_roots(selected_skills: Sequence[str]) -> tuple[Path, ...]:
    """Derive the closed top-level root allowlist from a receipt.

    Rollback intentionally does not re-admit the source graph.  The receipt
    records the selected skill names, so the safe restore surface is the
    fixed interface closure plus ``skills/<safe-name>`` package directories.
    """
    names = tuple(str(item) for item in selected_skills)
    if not names or tuple(dict.fromkeys(names)) != names:
        raise SkillProjectionError("rollback receipt selected skills are not unique")
    roots: list[Path] = list(FIXED_SOURCE_RELATIVE)
    for name in names:
        roots.append(Path("skills") / _safe_skill_name(name))
    if "aoa-session-memory-global-route" not in names:
        roots.append(GLOBAL_ROUTER_RELATIVE)
    return tuple(dict.fromkeys(roots))


def _validate_receipt_snapshot_rows(
    snapshots: Sequence[Any],
    expected_roots: Sequence[Path],
    *,
    label: str,
) -> list[str]:
    """Validate receipt root/file shape and keep paths inside the allowlist."""
    diagnostics: list[str] = []
    if len(snapshots) != len(expected_roots):
        return [f"{label}_count_mismatch"]
    seen_paths: set[str] = set()
    for index, (item, root) in enumerate(zip(snapshots, expected_roots)):
        if not isinstance(item, Mapping):
            diagnostics.append(f"{label}_{index}_not_object")
            continue
        if item.get("path") != root.as_posix():
            diagnostics.append(f"{label}_{index}_path_mismatch")
        state = str(item.get("state") or "")
        if state not in {"file", "directory", "absent"}:
            diagnostics.append(f"{label}_{index}_state_invalid")
        files = item.get("files")
        if not isinstance(files, list):
            diagnostics.append(f"{label}_{index}_files_invalid")
            continue
        if state == "file" and len(files) != 1:
            diagnostics.append(f"{label}_{index}_file_row_count_invalid")
        if state == "absent" and files:
            diagnostics.append(f"{label}_{index}_absent_has_files")
        for row in files:
            if not isinstance(row, Mapping):
                diagnostics.append(f"{label}_{index}_file_row_invalid")
                continue
            path_text = str(row.get("path") or "")
            try:
                relative = _safe_relative(path_text, label=f"{label} file")
            except SkillProjectionError:
                diagnostics.append(f"{label}_{index}_file_path_invalid")
                continue
            relative_text = relative.as_posix()
            if relative_text in seen_paths:
                diagnostics.append(f"{label}_duplicate_file:{relative_text}")
            seen_paths.add(relative_text)
            if not (
                relative_text == root.as_posix()
                or relative_text.startswith(root.as_posix() + "/")
            ):
                diagnostics.append(f"{label}_{index}_file_escapes_root:{relative_text}")
            if row.get("state") != "file":
                diagnostics.append(f"{label}_{index}_file_state_invalid")
            digest = str(row.get("sha256") or "")
            if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest.lower()):
                diagnostics.append(f"{label}_{index}_file_digest_invalid")
            if not isinstance(row.get("bytes"), int) or int(row.get("bytes")) < 0:
                diagnostics.append(f"{label}_{index}_file_bytes_invalid")
            if not isinstance(row.get("mode"), int) or int(row.get("mode")) < 0:
                diagnostics.append(f"{label}_{index}_file_mode_invalid")
    return diagnostics


def _rollback_receipt_diagnostics(
    plan: Plan,
    receipt: Mapping[str, Any],
) -> list[str]:
    """Validate receipt self-containment without source or owner re-admission."""
    diagnostics: list[str] = []
    if receipt.get("schema_version") != SCHEMA_VERSION:
        diagnostics.append("component_receipt_schema_mismatch")
    if receipt.get("artifact_type") != "runtime_skill_projection_install":
        diagnostics.append("component_receipt_artifact_type_mismatch")
    if receipt.get("component") != "session-memory-skill-interface":
        diagnostics.append("component_receipt_component_mismatch")
    if receipt.get("workspace_root") != str(plan.workspace_root):
        diagnostics.append("component_receipt_workspace_root_mismatch")
    if receipt.get("aoa_root") != str(plan.target_root):
        diagnostics.append("component_receipt_target_root_mismatch")
    selected_skills = receipt.get("selected_skills")
    if (
        not isinstance(selected_skills, list)
        or not selected_skills
        or any(not isinstance(item, str) for item in selected_skills)
    ):
        diagnostics.append("component_receipt_selected_skills_missing")
        selected_skills = []
    try:
        expected_roots = _rollback_expected_roots(selected_skills)
    except SkillProjectionError as exc:
        diagnostics.append(str(exc))
        expected_roots = tuple()
    selected_roots = receipt.get("selected_roots")
    if not isinstance(selected_roots, list):
        diagnostics.append("component_receipt_selected_roots_missing")
    elif selected_roots != [root.as_posix() for root in expected_roots]:
        diagnostics.append("component_receipt_selected_roots_outside_closed_allowlist")
    before = receipt.get("selected_before")
    after = receipt.get("selected_after")
    if not isinstance(before, list) or not isinstance(after, list):
        diagnostics.append("component_receipt_selected_snapshots_missing")
        before = []
        after = []
    else:
        diagnostics.extend(
            _validate_receipt_snapshot_rows(
                before,
                expected_roots,
                label="component_receipt_before",
            )
        )
        diagnostics.extend(
            _validate_receipt_snapshot_rows(
                after,
                expected_roots,
                label="component_receipt_after",
            )
        )
    if expected_roots and not _receipt_after_matches(plan, receipt):
        diagnostics.append("component_receipt_selected_after_mismatch")
    after_files = receipt.get("selected_after_files")
    flattened_after = _flatten_roots(after)
    if not isinstance(after_files, Mapping):
        diagnostics.append("component_receipt_selected_after_files_missing")
    elif dict(after_files) != flattened_after:
        diagnostics.append("component_receipt_selected_after_files_mismatch")
    selected_paths = receipt.get("selected_paths")
    if not isinstance(selected_paths, list) or selected_paths != sorted(flattened_after):
        diagnostics.append("component_receipt_selected_paths_mismatch")
    previous_state = receipt.get("previous_component_receipt")
    if not isinstance(previous_state, Mapping):
        diagnostics.append("component_receipt_previous_state_missing")
    else:
        if receipt.get("previous_component_receipt_sha256") != previous_state.get("sha256"):
            diagnostics.append("component_receipt_previous_state_anchor_mismatch")
        if previous_state.get("present") not in {True, False}:
            diagnostics.append("component_receipt_previous_state_present_invalid")
        if type(previous_state.get("bytes")) is not int or int(previous_state.get("bytes")) < 0:
            diagnostics.append("component_receipt_previous_state_bytes_invalid")
    if not isinstance(receipt.get("unselected_target_token"), str) or not receipt.get(
        "unselected_target_token"
    ):
        diagnostics.append("component_receipt_unselected_target_anchor_missing")
    base_profile = receipt.get("base_profile")
    if not isinstance(base_profile, Mapping):
        diagnostics.append("component_receipt_base_profile_missing")
    else:
        if base_profile.get("path") != _session_memory.INSTALL_PROFILE_PATH.as_posix():
            diagnostics.append("component_receipt_base_profile_path_mismatch")
        if type(base_profile.get("bytes")) is not int or int(base_profile.get("bytes")) < 0:
            diagnostics.append("component_receipt_base_profile_bytes_invalid")
        if base_profile.get("sha256") != receipt.get("base_profile_sha256"):
            diagnostics.append("component_receipt_base_profile_hash_mismatch")
        if base_profile.get("install_id") != receipt.get("base_install_id"):
            diagnostics.append("component_receipt_base_profile_install_id_mismatch")
    return list(dict.fromkeys(diagnostics))


def rollback_skill_projection(
    *,
    workspace_root: Path | str,
    aoa_root: Path | str,
    source_aoa_root: Path | str | None = None,
    skills_root: Path | str | None = None,
) -> dict[str, Any]:
    """Restore the exact prior selected component from its closed receipt.

    Rollback is deliberately independent of the candidate source and the
    external owner checkout.  Those trees may be dirty, moved, or unavailable
    precisely when the last-good runtime overlay needs to be recovered.  If
    callers provide either root, it is treated as an optional identity check
    against the receipt; it is never revalidated or used as a copy source.
    """
    try:
        workspace = _root_ready(Path(workspace_root), label="workspace root")
        target = _root_ready(Path(aoa_root), label="target .aoa root")
        receipt, receipt_raw = _load_receipt(target)
        if str(receipt.get("workspace_root")) != str(workspace):
            raise SkillProjectionError("rollback workspace root does not match receipt")
        if str(receipt.get("aoa_root")) != str(target):
            raise SkillProjectionError("rollback target root does not match receipt")
        if source_aoa_root is not None:
            source = _root_ready(Path(source_aoa_root), label="source .aoa root")
            if str(receipt.get("source_root")) != str(source):
                raise SkillProjectionError("rollback source root does not match receipt")
        if skills_root is not None:
            skills = _root_ready(Path(skills_root), label="aoa-skills contract root")
            if str(receipt.get("skills_root")) != str(skills):
                raise SkillProjectionError("rollback skills root does not match receipt")

        selected_skills = receipt.get("selected_skills")
        if (
            not isinstance(selected_skills, list)
            or not selected_skills
            or any(not isinstance(item, str) for item in selected_skills)
        ):
            raise SkillProjectionError("rollback receipt selected skills are missing")

        selected_roots = _rollback_expected_roots(selected_skills)
        plan = Plan(
            source_root=target,
            skills_root=target,
            workspace_root=workspace,
            target_root=target,
            source_identity={},
            owner_validation={},
            base_profile={},
            source_metadata={"selected_files": {}},
            selected_skills=tuple(selected_skills),
            selected_roots=selected_roots,
            source_roots=tuple(),
            target_roots=tuple(),
            source_files={},
            target_files={},
            unselected_token=str(receipt.get("unselected_target_token") or ""),
            source_token="",
            target_cas_token="",
            previous_receipt={},
        )
        receipt_diagnostics = _rollback_receipt_diagnostics(plan, receipt)
        if receipt_diagnostics:
            raise SkillProjectionError(
                "rollback receipt is stale or tampered: "
                + ", ".join(receipt_diagnostics)
            )
        selected_roots_text = receipt.get("selected_roots")
        if not isinstance(selected_roots_text, list) or not selected_roots_text:
            raise SkillProjectionError("rollback receipt selected roots are missing")
        before_roots = receipt.get("selected_before")
        if not isinstance(before_roots, list) or len(before_roots) != len(plan.selected_roots):
            raise SkillProjectionError("rollback receipt selected before-state is incomplete")
        if any(not isinstance(item, Mapping) for item in before_roots):
            raise SkillProjectionError("rollback receipt selected before-state is invalid")
        previous_state = receipt.get("previous_component_receipt")
        if not isinstance(previous_state, Mapping):
            raise SkillProjectionError("rollback receipt previous component receipt state is missing")
        if receipt.get("previous_component_receipt_sha256") != previous_state.get("sha256"):
            raise SkillProjectionError("rollback receipt previous component receipt anchor mismatch")

        backup_text = str(receipt.get("backup_root") or "")
        backup = _resolve(Path(backup_text))
        backup_parent = _resolve(target / BACKUP_PARENT_RELATIVE)
        try:
            backup.relative_to(backup_parent)
        except ValueError as exc:
            raise SkillProjectionError("rollback backup root escapes diagnostics backup area") from exc
        if backup.is_symlink() or not backup.is_dir():
            raise SkillProjectionError("rollback durable backup is absent or symlinked")
        manifest_path = backup / BACKUP_MANIFEST_NAME
        manifest = _load_json(manifest_path, label="rollback backup manifest")
        if not isinstance(manifest, Mapping):
            raise SkillProjectionError("rollback backup manifest is not an object")
        # The profile is an independent kernel owner anchor.  Read it directly
        # so rollback remains available when the source/validator checkout has
        # disappeared, while still rejecting a target that changed underneath
        # the receipt.
        profile_path = _path_inside(
            target,
            _session_memory.INSTALL_PROFILE_PATH,
            label="rollback base install profile",
        )
        profile_raw = profile_path.read_bytes()
        try:
            profile_payload = json.loads(profile_raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SkillProjectionError("rollback base install profile is invalid") from exc
        if not isinstance(profile_payload, Mapping):
            raise SkillProjectionError("rollback base install profile is not an object")
        if profile_payload.get("workspace_root") != str(workspace):
            raise SkillProjectionError("rollback base install profile workspace anchor changed")
        if profile_payload.get("aoa_root") != str(target):
            raise SkillProjectionError("rollback base install profile target anchor changed")
        base_profile = receipt.get("base_profile")
        if not isinstance(base_profile, Mapping):
            raise SkillProjectionError("rollback receipt base profile anchor is missing")
        profile_hash = _sha256_bytes(profile_raw)
        if profile_hash != receipt.get("base_profile_sha256"):
            raise SkillProjectionError("rollback base install profile anchor changed")
        if profile_hash != base_profile.get("sha256"):
            raise SkillProjectionError("rollback receipt base profile hash is inconsistent")
        if len(profile_raw) != base_profile.get("bytes"):
            raise SkillProjectionError("rollback base install profile byte anchor is inconsistent")
        if profile_payload.get("install_id") != receipt.get("base_install_id"):
            raise SkillProjectionError("rollback base install id anchor changed")
        if profile_payload.get("install_id") != base_profile.get("install_id"):
            raise SkillProjectionError("rollback receipt base install id is inconsistent")
        if str(receipt.get("operation_id") or "") != backup.name:
            raise SkillProjectionError("rollback receipt operation id does not match backup")
        _validate_backup_manifest(
            plan,
            backup,
            manifest,
            expected_before=before_roots,
            expected_previous_receipt=previous_state,
        )
    except SkillProjectionError as exc:
        return {
            "schema_version": SCHEMA_VERSION,
            "ok": False,
            "status": "rollback_precondition_failed",
            "diagnostics": [str(exc)],
        }

    try:
        _restore_backup(plan, backup, manifest)
        restored_roots = _snapshot_roots(target, plan.selected_roots)
        if any(
            not _root_snapshots_equal(actual, expected)
            for actual, expected in zip(restored_roots, before_roots)
        ):
            raise SkillProjectionError("rollback restored selected state differs from receipt before-state")
        if _sha256_file(profile_path) != receipt.get("base_profile_sha256"):
            raise SkillProjectionError("rollback changed base install profile")
        restored_previous = _previous_receipt(target)
        for key in ("present", "sha256", "bytes"):
            if restored_previous.get(key) != previous_state.get(key):
                raise SkillProjectionError("rollback restored previous receipt differs from backup state")
        outcome = {
            "schema_version": "aoa_session_memory_skill_projection_rollback_v1",
            "artifact_type": "runtime_skill_projection_rollback",
            "status": "rolled_back",
            "ok": True,
            "rolled_back_at": _utc_now(),
            "workspace_root": str(workspace),
            "aoa_root": str(target),
            "component_receipt_sha256": _sha256_bytes(receipt_raw),
            "restored_previous_receipt_sha256": (
                previous_state.get("sha256")
            ),
            "backup_root": str(backup),
            "claim_limit": "selected component rollback outcome only",
        }
        _atomic_write(
            target / ROLLBACK_OUTCOME_RELATIVE,
            json.dumps(outcome, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n",
            prefix=".skill-projection-rollback-",
        )
        return outcome
    except Exception as exc:
        return {
            "schema_version": "aoa_session_memory_skill_projection_rollback_v1",
            "ok": False,
            "status": "rollback_failed_after_precondition",
            "diagnostics": [str(exc)],
            "backup_root": str(backup),
        }


def _add_common_roots(parser: argparse.ArgumentParser, *, require_source: bool) -> None:
    if require_source:
        parser.add_argument("--source-aoa-root", required=True)
        parser.add_argument("--skills-root", required=True)
    else:
        parser.add_argument("--source-aoa-root")
        parser.add_argument("--skills-root")
    parser.add_argument("--workspace-root", required=True)
    parser.add_argument("--aoa-root", required=True)
    parser.add_argument(
        "--skill",
        action="append",
        dest="skills",
        metavar="NAME",
        help=(
            "Graph-declared skill package to include; repeat for multiple "
            "packages. Defaults to the two advertised session-memory routers."
        ),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Install a bounded source-owned session-memory skill interface overlay."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="Run the read-only skills overlay preflight.")
    _add_common_roots(check, require_source=True)
    check.set_defaults(_handler="check")
    install = sub.add_parser(
        "install",
        aliases=["execute"],
        help="Apply the selected overlay after explicit --force authorization.",
    )
    _add_common_roots(install, require_source=True)
    install.add_argument(
        "--force",
        action="store_true",
        help="Authorize replacing selected component paths after preflight.",
    )
    install.set_defaults(_handler="install")
    rollback = sub.add_parser(
        "rollback",
        help="Restore the prior selected component from its durable backup.",
    )
    rollback.add_argument("--workspace-root", required=True)
    rollback.add_argument("--aoa-root", required=True)
    rollback.add_argument(
        "--source-aoa-root",
        help="Optional source root identity check; rollback does not read or revalidate it.",
    )
    rollback.add_argument(
        "--skills-root",
        help="Optional aoa-skills root identity check; rollback does not read or revalidate it.",
    )
    rollback.set_defaults(_handler="rollback")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args._handler == "check":
        payload = inspect_skill_projection(
            source_aoa_root=args.source_aoa_root,
            skills_root=args.skills_root,
            workspace_root=args.workspace_root,
            aoa_root=args.aoa_root,
            selected_skills=args.skills,
        )
    elif args._handler == "install":
        payload = install_skill_projection(
            source_aoa_root=args.source_aoa_root,
            skills_root=args.skills_root,
            workspace_root=args.workspace_root,
            aoa_root=args.aoa_root,
            selected_skills=args.skills,
            force=bool(args.force),
        )
    else:
        payload = rollback_skill_projection(
            workspace_root=args.workspace_root,
            aoa_root=args.aoa_root,
            source_aoa_root=args.source_aoa_root,
            skills_root=args.skills_root,
        )
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
