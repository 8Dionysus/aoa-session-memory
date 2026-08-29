"""Thin aoa-session-memory binding for the reviewed KAG budget procedure.

The common KAG procedure owns the D-0042/D-0043 semantic contract.  This
module only binds the session-memory owner routes and their native dependency
witnesses to that procedure.  It deliberately does not reimplement evidence,
receipt, fixed-point, or negative-case semantics.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import subprocess
import time
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping, Sequence


OWNER = "aoa-session-memory"
REVIEW_REF = (
    "aoa-kag:docs/decisions/"
    "AOA-KAG-D-0042-semantic-owner-evidence-for-budget-admission.md"
)
PROCEDURE_VERSION = "aoa-kag:budget-semantic-admission-v3"
REVIEWED_PROCEDURE_PATHS = (
    "scripts/repo_local/portable_family.py",
    "scripts/repo_local/tiered_family.py",
    "scripts/generate_repo_local_kag_index.py",
    "scripts/repo_local/history.py",
    "scripts/repo_local/identity.py",
    "scripts/repo_local/indexes.py",
    "scripts/repo_local/structure.py",
    "scripts/prepare_landing.py",
    "schemas/repo-local-kag-budget-evidence.schema.json",
    "schemas/repo-local-kag-budget-receipt.schema.json",
)
REVIEWED_PROCEDURE_ENTRY = Path(REVIEWED_PROCEDURE_PATHS[0])
REVIEWED_PROCEDURE_IDENTITY_DIGEST = (
    "18715e6dfb1a3c3234571daefa3ff09fac9b827d80cce23a41baa65c7781a7fe"
)
PUBLIC_PROCEDURE_API = (
    "build_budget_publication",
    "build_budget_receipt",
    "publish_budget_pair",
    "render_manifest",
    "validate_changed_generated_budget",
)
OWNER_BINDING_SCHEMA_VERSION = "aoa-session-memory-d0043-v2-owner-binding-v1"

NATIVE_SOURCE_ROUTES = (
    "docs/decisions/AOA-SM-D-0025-process-loaded-producer-generation-identity.md",
    "docs/decisions/AOA-SM-D-0030-projection-scoped-producer-generation-identity.md",
    "docs/decisions/AOA-SM-D-0056-merkle-semantic-component-receipts.md",
)
NATIVE_DEPENDENCY_ROUTES = (
    "scripts/aoa_session_memory.py",
    "kag/indexes/index_family.manifest.json",
    "kag/indexes/shards/source/0.jsonl",
)
NEGATIVE_CASES = (
    "stale_head",
    "producer_substitution",
    "dependency_substitution",
    "receipt_evidence_mismatch",
    "tampered_currentness",
)


class OwnerPairError(ValueError):
    """The owner binding is incomplete or cannot admit the common result."""


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def payload_digest(value: object) -> str:
    return sha256_bytes(_canonical_bytes(value))


def _safe_route(route: str | Path) -> Path:
    path = Path(route)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise OwnerPairError(f"owner route is unsafe: {route}")
    return path


def _resolve_route(
    root: Path,
    route: str | Path,
    *,
    role: str,
    require_file: bool,
) -> tuple[Path, Path]:
    relative = _safe_route(route)
    try:
        resolved_root = root.resolve(strict=True)
        resolved = (resolved_root / relative).resolve(strict=require_file)
    except OSError as exc:
        raise OwnerPairError(f"{role} cannot be resolved: {route}") from exc
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise OwnerPairError(f"{role} escapes its root: {route}")
    if require_file and not resolved.is_file():
        raise OwnerPairError(f"{role} is missing: {route}")
    return relative, resolved


def _route_witness(root: Path, routes: Sequence[str], role: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for route in routes:
        relative, path = _resolve_route(
            root,
            route,
            role=f"owner witness {role} route",
            require_file=True,
        )
        content = path.read_bytes()
        result.append(
            {
                "path": relative.as_posix(),
                "bytes": len(content),
                "sha256": sha256_bytes(content),
                "role": role,
            }
        )
    return result


def owner_witness(
    root: Path,
    *,
    source_routes: Sequence[str] = NATIVE_SOURCE_ROUTES,
    dependency_routes: Sequence[str] = NATIVE_DEPENDENCY_ROUTES,
) -> dict[str, Any]:
    """Digest real owner inputs without copying them into generic evidence."""

    source = _route_witness(root, source_routes, "native_owner_source")
    dependencies = _route_witness(
        root,
        dependency_routes,
        "native_owner_dependency",
    )
    witness_material = {
        "source_routes": source,
        "dependency_routes": dependencies,
    }
    return {
        "schema_version": "aoa-session-memory-owner-witness-v1",
        "owner": OWNER,
        "source_routes": source,
        "dependency_routes": dependencies,
        "source_digest": payload_digest(source),
        "dependency_digest": payload_digest(dependencies),
        "witness_digest": payload_digest(witness_material),
        "root_identity_digest": payload_digest(
            {"owner": OWNER, **witness_material}
        ),
        "authority": "owner-local-binding-only",
    }


def _reviewed_procedure_identity(procedure_file: Path) -> tuple[Path, dict[str, Any]]:
    try:
        resolved_file = procedure_file.resolve(strict=True)
        procedure_root = resolved_file.parents[2]
        if resolved_file.relative_to(procedure_root) != REVIEWED_PROCEDURE_ENTRY:
            raise OwnerPairError(
                "reviewed KAG procedure entry is not the D-0043 portable-family module"
            )
    except OwnerPairError:
        raise
    except (IndexError, OSError, ValueError) as exc:
        raise OwnerPairError(
            f"reviewed KAG procedure entry cannot be resolved: {procedure_file}"
        ) from exc

    files: list[dict[str, Any]] = []
    for route in REVIEWED_PROCEDURE_PATHS:
        relative, path = _resolve_route(
            procedure_root,
            route,
            role="reviewed KAG procedure",
            require_file=True,
        )
        content = path.read_bytes()
        files.append(
            {
                "path": relative.as_posix(),
                "state": "present",
                "digest": sha256_bytes(content),
                "bytes": len(content),
            }
        )
    digest = sha256_bytes(_canonical_bytes(files))
    if digest != REVIEWED_PROCEDURE_IDENTITY_DIGEST:
        raise OwnerPairError(
            "reviewed KAG procedure identity mismatch: "
            f"expected {REVIEWED_PROCEDURE_IDENTITY_DIGEST}, got {digest}"
        )
    return procedure_root, {
        "contract_version": PROCEDURE_VERSION,
        "owner": "aoa-kag",
        "base_ref": digest,
        "files": files,
        "digest": digest,
    }


def load_reviewed_procedure(procedure_file: Path) -> ModuleType:
    """Load the exact reviewed common procedure supplied by the owner route."""

    procedure_root, _ = _reviewed_procedure_identity(procedure_file)
    path = (procedure_root / REVIEWED_PROCEDURE_ENTRY).resolve(strict=True)
    spec = importlib.util.spec_from_file_location(
        "aoa_kag_reviewed_portable_family",
        path,
    )
    if spec is None or spec.loader is None:
        raise OwnerPairError(f"cannot load reviewed KAG procedure: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if getattr(module, "BUDGET_PROCEDURE_VERSION", None) != PROCEDURE_VERSION:
        raise OwnerPairError("reviewed KAG procedure version is not D-0043 v2")
    loaded_path = Path(getattr(module, "__file__", "")).resolve()
    if loaded_path != path:
        raise OwnerPairError("reviewed KAG procedure loaded from an unexpected path")
    missing = [
        name
        for name in PUBLIC_PROCEDURE_API
        if not callable(getattr(module, name, None))
    ]
    if missing:
        raise OwnerPairError(
            "public aoa-kag D-0043 API is missing: " + ", ".join(missing)
        )
    return module


def _git_head(root: Path) -> str:
    return subprocess.run(
        ("git", "rev-parse", "HEAD"),
        cwd=root.resolve(),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _git_changed_paths(root: Path, base_ref: str) -> set[Path]:
    resolved_root = root.resolve(strict=True)
    changed = subprocess.run(
        ("git", "diff", "--name-only", "-z", base_ref, "--"),
        cwd=resolved_root,
        check=True,
        capture_output=True,
    ).stdout
    untracked = subprocess.run(
        ("git", "ls-files", "--others", "--exclude-standard", "-z"),
        cwd=resolved_root,
        check=True,
        capture_output=True,
    ).stdout
    paths: set[Path] = set()
    for encoded in (*changed.split(b"\0"), *untracked.split(b"\0")):
        if not encoded:
            continue
        try:
            path = Path(encoded.decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise OwnerPairError("Git changed path is not valid UTF-8") from exc
        if path.is_absolute() or ".." in path.parts:
            raise OwnerPairError(f"Git changed path is unsafe: {path}")
        paths.add(path)
    return paths


def _require_supported_pair(
    module: ModuleType,
    evidence: Mapping[str, Any],
    receipt: Mapping[str, Any],
) -> None:
    if evidence.get("schema_version") != module.BUDGET_EVIDENCE_SCHEMA_VERSION:
        raise OwnerPairError("common procedure did not return evidence v2")
    if evidence.get("state") != "supported":
        raise OwnerPairError(
            f"owner pair remains {evidence.get('state')}; supported is required"
        )
    if receipt.get("schema_version") != module.BUDGET_RECEIPT_SCHEMA_VERSION:
        raise OwnerPairError("common procedure did not return receipt v2")
    if receipt.get("semantic_admission") != "supported":
        raise OwnerPairError("receipt is not semantically admitted")
    measurements = evidence.get("measurements")
    if not isinstance(measurements, Mapping):
        raise OwnerPairError("common evidence measurements are missing")
    dependency = measurements.get("source_dependency")
    if not isinstance(dependency, Mapping) or dependency.get("state") != "matched":
        raise OwnerPairError("owner source dependency witness is not matched")
    fixed_point = evidence.get("fixed_point")
    head_identity = evidence.get("head_identity")
    if fixed_point != {
        "state": "required_external_gate",
        "family_digest": head_identity.get("family_digest")
        if isinstance(head_identity, Mapping)
        else None,
    }:
        raise OwnerPairError("common fixed-point binding is incomplete")


def _owner_binding(
    *,
    procedure_identity: Mapping[str, Any],
    witness: Mapping[str, Any],
    evidence_path: Path,
    evidence: Mapping[str, Any],
    receipt_path: Path,
    receipt: Mapping[str, Any],
    procedure: ModuleType,
) -> dict[str, Any]:
    evidence_digest = sha256_bytes(procedure.render_manifest(evidence))
    receipt_digest = sha256_bytes(procedure.render_manifest(receipt))
    material = {
        "owner": OWNER,
        "procedure_identity": copy.deepcopy(dict(procedure_identity)),
        "native_witness": copy.deepcopy(dict(witness)),
        "common_pair": {
            "evidence_path": evidence_path.as_posix(),
            "evidence_sha256": evidence_digest,
            "receipt_path": receipt_path.as_posix(),
            "receipt_sha256": receipt_digest,
        },
    }
    binding = {
        "schema_version": OWNER_BINDING_SCHEMA_VERSION,
        **material,
    }
    binding["binding_digest"] = payload_digest(binding)
    return binding


def _assert_owner_binding(
    *,
    owner_binding: Mapping[str, Any],
    expected: Mapping[str, Any],
) -> None:
    if dict(owner_binding) != dict(expected):
        raise OwnerPairError(
            "owner witness binding does not match the common evidence/receipt"
        )
    material = {
        key: value
        for key, value in owner_binding.items()
        if key != "binding_digest"
    }
    if owner_binding.get("binding_digest") != payload_digest(material):
        raise OwnerPairError("owner witness binding digest is invalid")


def build_owner_pair(
    root: Path,
    *,
    base_ref: str,
    manifest: Mapping[str, Any],
    procedure_file: Path,
    owner_source_root: Path | None = None,
    changed_source_route: str = NATIVE_SOURCE_ROUTES[-1],
    reason: str = "Bind aoa-session-memory native producer witnesses to D-0043 v2.",
) -> dict[str, Any]:
    """Build, publish, and validate one owner-bound common-procedure pair."""

    started = time.perf_counter_ns()
    _, procedure_identity = _reviewed_procedure_identity(procedure_file)
    procedure = load_reviewed_procedure(procedure_file)
    source_root = (owner_source_root or root).resolve()
    witness = owner_witness(source_root)
    if _safe_route(changed_source_route) not in _git_changed_paths(root, base_ref):
        raise OwnerPairError(
            f"changed owner route is absent from measured source delta: {changed_source_route}"
        )

    evidence_path, evidence, receipt_path, receipt = procedure.build_budget_publication(
        root,
        base_ref=base_ref,
        manifest=manifest,
        reason=reason,
        cause_class="legitimate_bulk_authored_change",
        review_ref=REVIEW_REF,
    )
    _require_supported_pair(procedure, evidence, receipt)
    procedure.publish_budget_pair(
        root,
        evidence_path=evidence_path,
        evidence=evidence,
        receipt_path=receipt_path,
        receipt=receipt,
    )
    binding = _owner_binding(
        procedure_identity=procedure_identity,
        witness=witness,
        evidence_path=evidence_path,
        evidence=evidence,
        receipt_path=receipt_path,
        receipt=receipt,
        procedure=procedure,
    )
    validate_published_pair(
        root,
        base_ref=base_ref,
        manifest=manifest,
        procedure_file=procedure_file,
        evidence_path=evidence_path,
        receipt_path=receipt_path,
        owner_source_root=source_root,
        owner_binding=binding,
    )
    evidence_bytes = procedure.render_manifest(evidence)
    receipt_bytes = procedure.render_manifest(receipt)
    return {
        "schema_version": "aoa-session-memory-d0043-v2-owner-pair-v1",
        "owner": OWNER,
        "base_ref": base_ref,
        "head_ref": _git_head(root),
        "procedure_identity": procedure_identity,
        "procedure_version": procedure.BUDGET_PROCEDURE_VERSION,
        "review_ref": REVIEW_REF,
        "changed_source_route": _safe_route(changed_source_route).as_posix(),
        "owner_witness": witness,
        "owner_binding": binding,
        "evidence_path": evidence_path.as_posix(),
        "evidence_sha256": sha256_bytes(evidence_bytes),
        "receipt_path": receipt_path.as_posix(),
        "receipt_sha256": sha256_bytes(receipt_bytes),
        "family_digest": evidence["head_identity"]["family_digest"],
        "fixed_point": copy.deepcopy(evidence["fixed_point"]),
        "state": evidence["state"],
        "wall_ms": round((time.perf_counter_ns() - started) / 1_000_000, 3),
    }


def validate_published_pair(
    root: Path,
    *,
    base_ref: str,
    manifest: Mapping[str, Any],
    procedure_file: Path,
    evidence_path: Path,
    receipt_path: Path,
    owner_source_root: Path,
    owner_binding: Mapping[str, Any],
) -> None:
    """Re-run the common validator against the materialized pair."""

    _, procedure_identity = _reviewed_procedure_identity(procedure_file)
    procedure = load_reviewed_procedure(procedure_file)
    evidence_relative, evidence_target = _resolve_route(
        root,
        evidence_path,
        role="owner evidence",
        require_file=True,
    )
    receipt_relative, receipt_target = _resolve_route(
        root,
        receipt_path,
        role="owner receipt",
        require_file=True,
    )
    evidence = json.loads(evidence_target.read_text(encoding="utf-8"))
    receipt = json.loads(receipt_target.read_text(encoding="utf-8"))
    if not isinstance(evidence, dict) or not isinstance(receipt, dict):
        raise OwnerPairError("published owner pair members must be JSON objects")
    witness = owner_witness(owner_source_root)
    expected_binding = _owner_binding(
        procedure_identity=procedure_identity,
        witness=witness,
        evidence_path=evidence_relative,
        evidence=evidence,
        receipt_path=receipt_relative,
        receipt=receipt,
        procedure=procedure,
    )
    _assert_owner_binding(owner_binding=owner_binding, expected=expected_binding)
    if receipt.get("semantic_evidence_ref") != evidence_relative.as_posix():
        raise OwnerPairError("published receipt points at a different evidence path")
    if receipt.get("semantic_evidence_digest") != expected_binding["common_pair"][
        "evidence_sha256"
    ]:
        raise OwnerPairError("published receipt digest does not bind evidence")
    recomputed_receipt_path, recomputed_receipt = procedure.build_budget_receipt(
        root,
        base_ref=base_ref,
        manifest=manifest,
        reason=str(receipt["reason"]),
        semantic_evidence=evidence,
        approved_by=str(receipt["approved_by"]),
    )
    if recomputed_receipt_path != receipt_relative or recomputed_receipt != receipt:
        raise OwnerPairError("public aoa-kag receipt validation did not reproduce the pair")
    try:
        procedure.validate_changed_generated_budget(
            root,
            base_ref=base_ref,
            manifest=manifest,
        )
    except Exception as exc:
        raise OwnerPairError("public aoa-kag budget validation rejected the pair") from exc


def _negative_record(
    case: str,
    started: int,
    *,
    exception: BaseException | None = None,
    unexpected: str | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "case": case,
        "rejected": exception is not None,
        "wall_ms": round((time.perf_counter_ns() - started) / 1_000_000, 3),
    }
    if exception is not None:
        record.update(
            {
                "exception": type(exception).__name__,
                "message": str(exception),
            }
        )
    if unexpected is not None:
        record["unexpected"] = unexpected
    return record


def run_negative_cases(
    root: Path,
    *,
    base_ref: str,
    manifest: Mapping[str, Any],
    procedure_file: Path,
    evidence_path: Path,
    receipt_path: Path,
    evidence: Mapping[str, Any] | None = None,
    receipt: Mapping[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Exercise the five exact fail-closed mutations through common code."""

    procedure = load_reviewed_procedure(procedure_file)
    _, evidence_target = _resolve_route(
        root,
        evidence_path,
        role="negative-case evidence",
        require_file=True,
    )
    _, receipt_target = _resolve_route(
        root,
        receipt_path,
        role="negative-case receipt",
        require_file=True,
    )
    valid_evidence = (
        copy.deepcopy(dict(evidence))
        if evidence is not None
        else json.loads(evidence_target.read_text(encoding="utf-8"))
    )
    valid_receipt = (
        copy.deepcopy(dict(receipt))
        if receipt is not None
        else json.loads(receipt_target.read_text(encoding="utf-8"))
    )
    results: dict[str, dict[str, Any]] = {}

    def validate_candidate(candidate: Mapping[str, Any], *, candidate_base: str) -> None:
        procedure.build_budget_receipt(
            root,
            base_ref=candidate_base,
            manifest=manifest,
            reason=str(valid_receipt["reason"]),
            semantic_evidence=candidate,
            approved_by=str(valid_receipt["approved_by"]),
        )

    for case in NEGATIVE_CASES:
        started = time.perf_counter_ns()
        prepared = copy.deepcopy(valid_evidence)
        candidate_receipt = copy.deepcopy(valid_receipt)
        try:
            if case == "stale_head":
                bad_base = _git_head(root)
                validate_candidate(prepared, candidate_base=bad_base)
            elif case == "producer_substitution":
                prepared["procedure"] = copy.deepcopy(prepared["procedure"])
                prepared["procedure"]["files"][0]["digest"] = "0" * 64
                validate_candidate(prepared, candidate_base=base_ref)
            elif case == "dependency_substitution":
                dependency = prepared["measurements"]["source_dependency"]
                dependency["unrelated_generated_bytes"] = int(
                    dependency.get("unrelated_generated_bytes", 0)
                ) + 1
                validate_candidate(prepared, candidate_base=base_ref)
            elif case == "receipt_evidence_mismatch":
                candidate_receipt["semantic_evidence_digest"] = "0" * 64
                procedure.publish_budget_pair(
                    root,
                    evidence_path=evidence_path,
                    evidence=prepared,
                    receipt_path=receipt_path,
                    receipt=candidate_receipt,
                )
            elif case == "tampered_currentness":
                prepared["head_identity"] = copy.deepcopy(
                    prepared["head_identity"]
                )
                prepared["head_identity"]["family_digest"] = "0" * 64
                validate_candidate(prepared, candidate_base=base_ref)
            else:  # pragma: no cover - NEGATIVE_CASES is closed above
                raise OwnerPairError(f"unknown negative case: {case}")
        except Exception as exc:
            results[case] = _negative_record(case, started, exception=exc)
        else:
            results[case] = _negative_record(
                case,
                started,
                unexpected=f"{case} was accepted",
            )
    return results


__all__ = [
    "OWNER",
    "NATIVE_DEPENDENCY_ROUTES",
    "NATIVE_SOURCE_ROUTES",
    "NEGATIVE_CASES",
    "OWNER_BINDING_SCHEMA_VERSION",
    "PUBLIC_PROCEDURE_API",
    "REVIEWED_PROCEDURE_IDENTITY_DIGEST",
    "REVIEWED_PROCEDURE_PATHS",
    "OwnerPairError",
    "build_owner_pair",
    "load_reviewed_procedure",
    "owner_witness",
    "run_negative_cases",
    "sha256_bytes",
    "validate_published_pair",
]
