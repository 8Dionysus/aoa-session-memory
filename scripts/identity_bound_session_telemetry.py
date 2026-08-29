#!/usr/bin/env python3
"""Typed, public-safe identity binding for session validation evidence.

This module is deliberately an adapter and admission surface, not a validation
owner.  It accepts only structured owner receipts, joins them to an exact
session/projection context, and preserves missing or unobservable fields
instead of inferring them from command text or session prose.
"""

from __future__ import annotations

import copy
import hmac
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import threading
import unicodedata
from collections.abc import Mapping, Sequence
from typing import Any


SCHEMA_VERSION = "identity_bound_session_telemetry_v1"
EPISODE_PACKET_SCHEMA_VERSION = "identity_bound_episode_session_telemetry_v1"
OWNER_RECEIPT_SCHEMA_VERSION = "validation_owner_telemetry_receipt_v1"
OWNER_RECEIPT_ARTIFACT = "validation_owner_telemetry_receipt"
PACKET_ARTIFACT = "identity_bound_session_telemetry"
EPISODE_PACKET_ARTIFACT = "identity_bound_episode_session_telemetry"
PACKET_ROUTE_SCHEMA_VERSION = "identity_bound_packet_route_admission_v1"
RECEIPT_PROVENANCE_SCHEMA_VERSION = "owner_receipt_provenance_chain_v1"
EPISODE_WITNESS_SCHEMA_VERSION = "identity_bound_episode_admission_witness_v1"
OWNER_SOURCE_EVIDENCE_SCHEMA_VERSION = "owner_source_evidence_v1"
OWNER_ROOT_IDENTITY_SCHEMA_VERSION = "owner_root_identity_v1"
OWNER_MEMBERSHIP_WITNESS_SCHEMA_VERSION = "owner_membership_witness_v1"
OWNER_ALIAS_SOURCE_SCHEMA_VERSION = "owner_session_alias_source_v2"
OWNER_ALIAS_ADMISSION_EPOCH_SCHEMA_VERSION = "owner_session_alias_epoch_v1"
OWNER_ALIAS_SOURCE_CONTRACT_RELATIVE_PATH = ".owner/session-alias-source.json"
OWNER_ALIAS_SOURCE_KEY_RELATIVE_PATH = ".owner/session-alias.key"

# These are the projection-clock fields excluded by the owner writer when it
# computes an episode semantic source digest.  Keeping the same bounded
# normalization here makes the digest independently recomputable from the
# persisted, already-redacted component payload.
EPISODE_SOURCE_SEMANTIC_VOLATILE_KEYS = frozenset(
    {
        "anchored_at",
        "captured_at",
        "copied_at",
        "generated_at",
        "indexed_at",
        "last_checked",
        "refreshed_at",
        "reindexed_at",
        "route_refreshed_at",
        "source_latest_mtime",
        "updated_at",
        "artifact_receipts",
    }
)

FIELD_STATES = (
    "known",
    "unknown",
    "missing",
    "null",
    "unobservable",
    "excluded",
)
REVIEW_STATES = ("provisional", "reviewed", "excluded", "unknown")
ELIGIBILITY_STATES = (
    "eligible_identity_packet",
    "missing",
    "unknown",
    "unobservable",
    "excluded",
)
EPISODE_BINDING_STATES = (
    "exact_episode_range",
    "missing",
    "unknown",
    "unresolved",
    "foreign",
)

OWNER_VALIDATION_PROFILE = "identity_bound_episode_owner_validator_v1"
OWNER_VALIDATION_REF = "scripts.identity_bound_session_telemetry.validate_episode_binding"
COMPARISON_CONTRACT_SCHEMA_VERSION = "identity_bound_cohort_comparison_v1"
COMPARISON_SCOPE_FIELDS = (
    "session_id",
    "session_ref",
    "source",
    "projection",
    "episode_binding",
)
COMPARISON_DESIGNS = {
    "paired": ("left", "right"),
    "before_after": ("before", "after"),
    "treatment_control": ("control", "treatment"),
}
COMPARISON_ROLE_BINDING_FIELDS = ("route_or_treatment_identity",)
COMPARISON_EQUALITY_ANCHOR_IDENTITY_FIELDS = frozenset(
    {
        "workload_id",
        "candidate_or_source_identity",
        "source_ref_or_digest",
        "environment_id",
        "evidence_class",
        "acceptance_target",
    }
)

IDENTITY_FIELDS = (
    "workload_id",
    "candidate_or_source_identity",
    "source_ref_or_digest",
    "environment_id",
    "route_or_treatment_identity",
    "evidence_class",
    "acceptance_target",
    "cache_posture",
    "resource_posture",
)
STEP_NAMES = ("first_failure", "repair", "validation", "rerun")
TIMING_FIELDS = (
    "first_failure_latency_seconds",
    "repair_latency_seconds",
    "validation_latency_seconds",
    "rerun_latency_seconds",
)
RESOURCE_FIELDS = ("cpu_ms", "peak_rss_bytes", "io_read_bytes", "io_write_bytes")
SOURCE_FIELDS = ("raw_sha256", "raw_bytes", "raw_line_count")

MAX_STRING_LENGTH = 512
MAX_REASON_LENGTH = 240
MAX_EVIDENCE_REFS = 32

SAFE_REF_RE = re.compile(r"^[A-Za-z0-9_.:/#@%\-]{1,512}$")
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
HEX_RE = re.compile(r"^[0-9a-f]{64}$")
PUBLIC_REF_COMPONENT_SAFE = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.-@"
)

_PRIVATE_KEYS = {
    "argv",
    "body",
    "command",
    "content",
    "prompt",
    "raw",
    "raw_body",
    "response",
    "secret",
    "stderr",
    "stdout",
    "text",
    "token",
}


class TelemetryError(ValueError):
    """Raised when a telemetry packet cannot be admitted safely."""


class TelemetryAdmissionError(TelemetryError):
    """Raised when a typed receipt is valid JSON but does not bind to context."""


_EPISODE_COMPONENT_ADMISSION_TOKEN = object()
_CARRYING_EVENT_WITNESS_TOKEN = object()
_RECEIPT_PROVENANCE_WITNESS_TOKEN = object()
_OWNER_SOURCE_EVIDENCE_TOKEN = object()
_OWNER_ROOT_WITNESS_TOKEN = object()
_OWNER_MEMBERSHIP_WITNESS_TOKEN = object()
_OWNER_ALIAS_SOURCE_TOKEN = object()
_OWNER_ALIAS_TRUST_ANCHOR_PROVISION_TOKEN = object()
_OWNER_ALIAS_ISSUANCE_REGISTRY_TOKEN = object()


class _OwnerAliasTrustAnchor:
    """Externally provisioned verifier; no signer or secret is owned here."""

    __slots__ = ("_anchor_ref", "_verify")

    def __init__(self, *, anchor_ref: str, verify: Any, token: object) -> None:
        if token is not _OWNER_ALIAS_TRUST_ANCHOR_PROVISION_TOKEN:
            raise TypeError("owner_alias_trust_anchor_is_owner_provisioned")
        if not callable(verify):
            raise TypeError("owner_alias_trust_anchor_verifier_required")
        self._anchor_ref = anchor_ref
        self._verify = verify

    def verify(self, message_digest: str, signature: str) -> bool:
        try:
            return bool(self._verify(message_digest, signature))
        except Exception:
            return False


class _OwnerAliasIssuance:
    """Opaque registry ticket for one authenticated root/epoch admission."""

    __slots__ = (
        "_root_path",
        "_root_sha256",
        "_epoch_sha256",
        "_source_ref",
        "_trust_anchor_ref",
        "_contract_path",
        "_key_path",
        "_expected_contract",
        "_contract_identity",
        "_key_identity",
        "_key_sha256",
        "_trust_anchor",
    )

    def __init__(
        self,
        *,
        root_path: Path,
        root_sha256: str,
        epoch_sha256: str,
        source_ref: str,
        trust_anchor_ref: str,
        contract_path: Path,
        key_path: Path,
        expected_contract: Mapping[str, Any],
        contract_identity: Mapping[str, Any],
        key_identity: Mapping[str, Any],
        key_sha256: str,
        trust_anchor: _OwnerAliasTrustAnchor,
        token: object,
    ) -> None:
        if token is not _OWNER_ALIAS_ISSUANCE_REGISTRY_TOKEN:
            raise TypeError("owner_alias_issuance_is_owner_issued")
        self._root_path = _absolute_path(root_path)
        self._root_sha256 = root_sha256
        self._epoch_sha256 = epoch_sha256
        self._source_ref = source_ref
        self._trust_anchor_ref = trust_anchor_ref
        self._contract_path = _absolute_path(contract_path)
        self._key_path = _absolute_path(key_path)
        self._expected_contract = copy.deepcopy(dict(expected_contract))
        self._contract_identity = copy.deepcopy(dict(contract_identity))
        self._key_identity = copy.deepcopy(dict(key_identity))
        self._key_sha256 = key_sha256
        self._trust_anchor = trust_anchor

    def __copy__(self) -> Any:
        raise TypeError("owner_alias_issuance_is_not_copyable")

    def __deepcopy__(self, memo: dict[int, Any]) -> Any:
        raise TypeError("owner_alias_issuance_is_not_copyable")


class _OwnerAliasIssuanceRegistry:
    """Process-local storage used only after an external admission succeeds."""

    __slots__ = ("_entries", "_lock")

    def __init__(self) -> None:
        self._entries: dict[int, _OwnerAliasIssuance] = {}
        self._lock = threading.RLock()

    def issue(self, **kwargs: Any) -> _OwnerAliasIssuance:
        issuance = _OwnerAliasIssuance(
            **kwargs,
            token=_OWNER_ALIAS_ISSUANCE_REGISTRY_TOKEN,
        )
        with self._lock:
            self._entries[id(issuance)] = issuance
        return issuance

    def _entry(self, issuance: _OwnerAliasIssuance) -> _OwnerAliasIssuance | None:
        with self._lock:
            entry = self._entries.get(id(issuance))
        return entry if entry is issuance else None

    def verify_current(
        self,
        issuance: _OwnerAliasIssuance,
        *,
        root_path: Path,
        root_identity: Mapping[str, Any],
        root_sha256: str,
        epoch_sha256: str,
    ) -> bool:
        entry = self._entry(issuance)
        if entry is None:
            return False
        if (
            _absolute_path(root_path) != entry._root_path
            or root_sha256 != entry._root_sha256
            or epoch_sha256 != entry._epoch_sha256
        ):
            return False
        try:
            contract_bytes, _contract_identity = _read_regular_file(
                entry._contract_path,
                expected_identity=entry._contract_identity,
                error_prefix="session_alias_owner_contract",
            )
            contract = json.loads(contract_bytes.decode("utf-8"))
            if not isinstance(contract, Mapping) or dict(contract) != entry._expected_contract:
                return False
            if not _owner_alias_admission_is_valid(
                contract,
                root_identity=root_identity,
                root_sha256=root_sha256,
                trust_anchor=entry._trust_anchor,
            ):
                return False
            key_bytes, _key_identity = _read_regular_file(
                entry._key_path,
                expected_identity=entry._key_identity,
                error_prefix="session_alias_owner_key",
            )
        except (OSError, TelemetryError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
            return False
        return hashlib.sha256(key_bytes).hexdigest() == entry._key_sha256

    def digest(
        self,
        issuance: _OwnerAliasIssuance,
        message: bytes,
        *,
        root_path: Path,
        root_identity: Mapping[str, Any],
        root_sha256: str,
        epoch_sha256: str,
    ) -> str:
        entry = self._entry(issuance)
        if entry is None or not isinstance(message, bytes):
            raise TelemetryAdmissionError("session_alias_owner_issuance_invalid")
        if not self.verify_current(
            issuance,
            root_path=root_path,
            root_identity=root_identity,
            root_sha256=root_sha256,
            epoch_sha256=epoch_sha256,
        ):
            raise TelemetryAdmissionError("session_alias_owner_source_not_current")
        key_bytes, _key_identity = _read_regular_file(
            entry._key_path,
            expected_identity=entry._key_identity,
            error_prefix="session_alias_owner_key",
        )
        return hmac.new(key_bytes, message, hashlib.sha256).hexdigest()


_OWNER_ALIAS_TRUST_ANCHORS: dict[str, _OwnerAliasTrustAnchor] = {}
_OWNER_ALIAS_ISSUANCE_REGISTRY = _OwnerAliasIssuanceRegistry()


class OwnerRootCurrentnessReceipt:
    """Immutable root snapshot reused within one admission transaction."""

    __slots__ = ("_owner_root_witness", "_root_identity", "_root_sha256", "_epoch_sha256")

    def __init__(
        self,
        *,
        owner_root_witness: "OwnerRootWitness",
        root_identity: Mapping[str, Any],
    ) -> None:
        self._owner_root_witness = owner_root_witness
        self._root_identity = copy.deepcopy(dict(root_identity))
        self._root_sha256 = owner_root_witness._root_sha256
        self._epoch_sha256 = owner_root_witness._epoch_sha256

    def __copy__(self) -> Any:
        raise TypeError("owner_root_currentness_is_not_copyable")

    def __deepcopy__(self, memo: dict[int, Any]) -> Any:
        raise TypeError("owner_root_currentness_is_not_copyable")

    def matches(self, owner_root_witness: "OwnerRootWitness") -> bool:
        return (
            self._owner_root_witness is owner_root_witness
            and self._root_sha256 == owner_root_witness._root_sha256
            and self._epoch_sha256 == owner_root_witness._epoch_sha256
            and self._root_identity == owner_root_witness._root_identity
        )

    def public_metadata(self) -> dict[str, str]:
        return {
            "owner_root_sha256": self._root_sha256,
            "owner_epoch_sha256": self._epoch_sha256,
        }


class OwnerAliasSource:
    """Authenticated owner alias source backed by an opaque issuance ticket."""

    __slots__ = ("_issuance",)

    def __init__(self, *, issuance: _OwnerAliasIssuance, token: object) -> None:
        if token is not _OWNER_ALIAS_SOURCE_TOKEN or not isinstance(issuance, _OwnerAliasIssuance):
            raise TypeError("owner_alias_source_is_owner_issued")
        self._issuance = issuance

    def __copy__(self) -> Any:
        raise TypeError("owner_alias_source_is_not_copyable")

    def __deepcopy__(self, memo: dict[int, Any]) -> Any:
        raise TypeError("owner_alias_source_is_not_copyable")

    def public_contract(self) -> dict[str, str]:
        issuance = self._issuance
        return {
            "schema_version": OWNER_ALIAS_SOURCE_SCHEMA_VERSION,
            "issuer": "aoa-session-memory",
            "source_ref": issuance._source_ref,
            "trust_anchor_ref": issuance._trust_anchor_ref,
            "root_sha256": issuance._root_sha256,
            "epoch_sha256": issuance._epoch_sha256,
            "contract_sha256": str(issuance._expected_contract["contract_sha256"]),
        }

    def _matches_root(self, root_path: Path, root_sha256: str, epoch_sha256: str) -> bool:
        issuance = self._issuance
        return (
            _absolute_path(root_path) == issuance._root_path
            and root_sha256 == issuance._root_sha256
            and epoch_sha256 == issuance._epoch_sha256
        )

    def _verify_current(
        self,
        *,
        root_path: Path,
        root_identity: Mapping[str, Any],
        root_sha256: str,
        epoch_sha256: str,
    ) -> bool:
        return _OWNER_ALIAS_ISSUANCE_REGISTRY.verify_current(
            self._issuance,
            root_path=root_path,
            root_identity=root_identity,
            root_sha256=root_sha256,
            epoch_sha256=epoch_sha256,
        )

    def _digest(
        self,
        message: bytes,
        *,
        root_path: Path,
        root_identity: Mapping[str, Any],
        root_sha256: str,
        epoch_sha256: str,
    ) -> str:
        return _OWNER_ALIAS_ISSUANCE_REGISTRY.digest(
            self._issuance,
            message,
            root_path=root_path,
            root_identity=root_identity,
            root_sha256=root_sha256,
            epoch_sha256=epoch_sha256,
        )


class OwnerRootWitness:
    """Non-copyable owner binding for one authenticated root and epoch."""

    __slots__ = (
        "_root_path",
        "_root_identity",
        "_root_sha256",
        "_epoch_sha256",
        "_alias_source",
    )

    def __init__(
        self,
        *,
        root_path: Path,
        root_identity: Mapping[str, Any],
        epoch_sha256: str,
        alias_source: OwnerAliasSource | None,
        token: object,
    ) -> None:
        if token is not _OWNER_ROOT_WITNESS_TOKEN:
            raise TypeError("owner_root_witness_is_owner_issued")
        self._root_path = _absolute_path(root_path)
        self._root_identity = copy.deepcopy(dict(root_identity))
        self._root_sha256 = canonical_sha256(
            {
                "schema_version": OWNER_ROOT_IDENTITY_SCHEMA_VERSION,
                "identity": self._root_identity,
            }
        )
        self._epoch_sha256 = epoch_sha256
        self._alias_source = alias_source

    def __copy__(self) -> Any:
        raise TypeError("owner_root_witness_is_not_copyable")

    def __deepcopy__(self, memo: dict[int, Any]) -> Any:
        raise TypeError("owner_root_witness_is_not_copyable")

    def public_identity(self) -> dict[str, str]:
        return {
            "schema_version": OWNER_ROOT_IDENTITY_SCHEMA_VERSION,
            "issuer": "aoa-session-memory",
            "root_sha256": self._root_sha256,
            "epoch_sha256": self._epoch_sha256,
        }

    def public_alias_contract(self) -> dict[str, str] | None:
        return self._alias_source.public_contract() if self._alias_source is not None else None

    def _capture_currentness(self, *, require_alias_source: bool = True) -> OwnerRootCurrentnessReceipt:
        try:
            current = _owner_directory_identity_snapshot(self._root_path)
        except (OSError, TelemetryError, TypeError, ValueError) as exc:
            raise TelemetryAdmissionError("owner_root_witness_not_current") from exc
        if current != self._root_identity:
            raise TelemetryAdmissionError("owner_root_witness_not_current")
        if require_alias_source and (
            self._alias_source is None
            or not self._alias_source._verify_current(
                root_path=self._root_path,
                root_identity=current,
                root_sha256=self._root_sha256,
                epoch_sha256=self._epoch_sha256,
            )
        ):
            raise TelemetryAdmissionError("session_alias_owner_source_not_current")
        return OwnerRootCurrentnessReceipt(
            owner_root_witness=self,
            root_identity=current,
        )

    def currentness_receipt(self) -> OwnerRootCurrentnessReceipt:
        return self._capture_currentness(require_alias_source=True)

    def verify_current(self, *, require_alias_source: bool = True) -> bool:
        try:
            self._capture_currentness(require_alias_source=require_alias_source)
        except (OSError, TelemetryError, TypeError, ValueError):
            return False
        return True

    def _alias_digest(self, message: bytes) -> str:
        receipt = self._capture_currentness(require_alias_source=True)
        if not isinstance(self._alias_source, OwnerAliasSource):
            raise TelemetryAdmissionError("session_alias_owner_witness_not_current")
        return self._alias_source._digest(
            message,
            root_path=self._root_path,
            root_identity=receipt._root_identity,
            root_sha256=self._root_sha256,
            epoch_sha256=self._epoch_sha256,
        )

    def assert_session_dir(
        self,
        session_dir: Path,
        *,
        currentness: OwnerRootCurrentnessReceipt | None = None,
    ) -> None:
        if currentness is None:
            currentness = self.currentness_receipt()
        elif not currentness.matches(self):
            raise TelemetryAdmissionError("owner_root_witness_not_current")
        candidate = _absolute_path(session_dir)
        if candidate.parent != self._root_path / "sessions":
            raise TelemetryAdmissionError("owner_session_root_identity_mismatch")


class _OwnerAdmissionTransaction:
    """One admission transaction with cached reads and a final TOCTOU check."""

    __slots__ = ("owner_root_witness", "root_currentness", "_reads", "_closed")

    def __init__(self, owner_root_witness: OwnerRootWitness) -> None:
        if not isinstance(owner_root_witness, OwnerRootWitness):
            raise TypeError("owner_root_witness_required")
        self.owner_root_witness = owner_root_witness
        self.root_currentness: OwnerRootCurrentnessReceipt | None = None
        self._reads: dict[str, tuple[Path, Mapping[str, Any] | None, bytes, dict[str, Any], str]] = {}
        self._closed = False

    def start(self) -> OwnerRootCurrentnessReceipt:
        if self._closed:
            raise TelemetryAdmissionError("owner_admission_transaction_closed")
        if self.root_currentness is None:
            self.root_currentness = self.owner_root_witness.currentness_receipt()
        return self.root_currentness

    def read(
        self,
        path: Path,
        *,
        expected_identity: Mapping[str, Any] | None,
        error_prefix: str,
    ) -> tuple[bytes, dict[str, Any]]:
        self.start()
        absolute = _absolute_path(path)
        key = str(absolute)
        cached = self._reads.get(key)
        if cached is not None:
            _cached_path, cached_expected, data, identity, _prefix = cached
            if expected_identity is not None and not _same_path_identity(
                expected_identity,
                identity,
            ):
                raise TelemetryAdmissionError(f"{error_prefix}_identity_changed")
            if cached_expected is not None and expected_identity is not None and not _same_path_identity(
                cached_expected,
                expected_identity,
            ):
                raise TelemetryAdmissionError(f"{error_prefix}_identity_changed")
            return data, identity
        data, identity = _read_regular_file(
            absolute,
            expected_identity=expected_identity,
            error_prefix=error_prefix,
        )
        self._reads[key] = (absolute, expected_identity, data, identity, error_prefix)
        return data, identity

    def finalize(self) -> bool:
        if self._closed:
            return True
        if self.root_currentness is None:
            raise TelemetryAdmissionError("owner_admission_transaction_not_started")
        for path, _expected, original_data, identity, error_prefix in self._reads.values():
            current_data, _current_identity = _read_regular_file(
                path,
                expected_identity=identity,
                error_prefix=error_prefix,
            )
            if current_data != original_data:
                raise TelemetryAdmissionError(f"{error_prefix}_changed_during_admission")
        self.owner_root_witness.currentness_receipt()
        self._closed = True
        return True


class OwnerMembershipWitness:
    """Non-serialisable witness for one current membership under one root."""

    __slots__ = ("_record", "_owner_root_witness", "_witness_sha256")

    def __init__(
        self,
        record: Mapping[str, Any],
        *,
        owner_root_witness: OwnerRootWitness,
        token: object,
    ) -> None:
        if token is not _OWNER_MEMBERSHIP_WITNESS_TOKEN:
            raise TypeError("owner_membership_witness_is_owner_issued")
        if not isinstance(owner_root_witness, OwnerRootWitness):
            raise TypeError("owner_root_witness_required")
        self._record = copy.deepcopy(dict(record))
        self._owner_root_witness = owner_root_witness
        self._witness_sha256 = canonical_sha256(
            {
                "schema_version": OWNER_MEMBERSHIP_WITNESS_SCHEMA_VERSION,
                "owner_root_sha256": owner_root_witness._root_sha256,
                "owner_epoch_sha256": owner_root_witness._epoch_sha256,
                "record": self._record,
            }
        )

    def __copy__(self) -> Any:
        raise TypeError("owner_membership_witness_is_not_copyable")

    def __deepcopy__(self, memo: dict[int, Any]) -> Any:
        raise TypeError("owner_membership_witness_is_not_copyable")

    @property
    def kind(self) -> str:
        return str(self._record.get("kind") or "")

    def public_metadata(self) -> dict[str, str]:
        return {
            "owner_root_sha256": self._owner_root_witness._root_sha256,
            "owner_epoch_sha256": self._owner_root_witness._epoch_sha256,
            "membership_witness_sha256": self._witness_sha256,
        }

    def verify_current(self) -> bool:
        transaction = _OwnerAdmissionTransaction(self._owner_root_witness)
        try:
            currentness = transaction.start()
            _verify_owner_membership_record_current(
                self._record,
                owner_root_witness=self._owner_root_witness,
                currentness=currentness,
                transaction=transaction,
                finalize=False,
            )
            transaction.finalize()
        except (OSError, TelemetryError, TypeError, ValueError):
            return False
        return True


class OwnerSourceEvidence:
    """Owner evidence retained outside a portable digest chain.

    The public record contains only safe refs and digests.  When an owner
    loader supplies source paths, ``verify_current`` re-reads those artifacts
    before admission.  A process-local record is intentionally weaker and is
    never sufficient to restore authority after JSON serialization.
    """

    __slots__ = ("_record", "_paths", "_path_identities", "_membership")

    def __init__(
        self,
        record: Mapping[str, Any],
        *,
        paths: Mapping[str, Path] | None = None,
        membership: OwnerMembershipWitness | None = None,
        token: object,
    ) -> None:
        if token is not _OWNER_SOURCE_EVIDENCE_TOKEN:
            raise TypeError("owner_source_evidence_is_owner_issued")
        if membership is not None and not isinstance(membership, OwnerMembershipWitness):
            raise TypeError("owner_membership_witness_required")
        self._record = copy.deepcopy(dict(record))
        self._paths = {
            str(key): _absolute_path(Path(path))
            for key, path in (paths or {}).items()
        }
        self._path_identities = {
            key: _path_identity_snapshot(path)
            for key, path in self._paths.items()
        }
        self._membership = membership

    def __copy__(self) -> Any:
        raise TypeError("owner_source_evidence_is_not_copyable")

    def __deepcopy__(self, memo: dict[int, Any]) -> Any:
        raise TypeError("owner_source_evidence_is_not_copyable")

    def public_record(self) -> dict[str, Any]:
        return copy.deepcopy(self._record)

    def is_persistent(self) -> bool:
        return (
            self._record.get("status") == "persistent_artifact"
            and bool(self._paths)
            and isinstance(self._membership, OwnerMembershipWitness)
            and self._record.get("owner_root_sha256")
            == self._membership.public_metadata()["owner_root_sha256"]
            and self._record.get("owner_epoch_sha256")
            == self._membership.public_metadata()["owner_epoch_sha256"]
            and self._record.get("membership_witness_sha256")
            == self._membership.public_metadata()["membership_witness_sha256"]
            and self._record.get("record_sha256") == _owner_record_digest(self._record)
        )

    def verify_current(self) -> bool:
        if self._record.get("record_sha256") != _owner_record_digest(self._record):
            return False
        if not self._paths:
            return self._record.get("status") == "process_local"
        if self._record.get("status") != "persistent_artifact":
            return False
        if not self._paths or set(self._paths) != set(self._path_identities):
            return False
        if not isinstance(self._membership, OwnerMembershipWitness):
            return False
        transaction = _OwnerAdmissionTransaction(self._membership._owner_root_witness)
        for record_key in self._paths:
            try:
                data = self._read_current(record_key, transaction=transaction)
            except (OSError, TelemetryError):
                return False
            actual = f"sha256:{hashlib.sha256(data).hexdigest()}"
            if actual != self._record.get(record_key):
                return False
        try:
            currentness = transaction.start()
            _verify_owner_membership_record_current(
                self._membership._record,
                owner_root_witness=self._membership._owner_root_witness,
                currentness=currentness,
                transaction=transaction,
                finalize=False,
            )
            return transaction.finalize()
        except (OSError, TelemetryError, TypeError, ValueError):
            return False

    def _read_current(
        self,
        record_key: str,
        *,
        transaction: _OwnerAdmissionTransaction | None = None,
    ) -> bytes:
        path = self._paths.get(record_key)
        if path is None:
            raise TelemetryAdmissionError("owner_source_path_missing")
        if transaction is None:
            data, _identity = _read_regular_file(
                path,
                expected_identity=self._path_identities.get(record_key),
                error_prefix="owner_source_path",
            )
        else:
            data, _identity = transaction.read(
                path,
                expected_identity=self._path_identities.get(record_key),
                error_prefix="owner_source_path",
            )
        expected_digest = self._record.get(record_key)
        if isinstance(expected_digest, str):
            actual_digest = f"sha256:{hashlib.sha256(data).hexdigest()}"
            if actual_digest != expected_digest:
                raise TelemetryAdmissionError("owner_source_digest_mismatch")
        return data

    def _path_for(self, record_key: str) -> Path:
        path = self._paths.get(record_key)
        if path is None:
            raise TelemetryAdmissionError("owner_source_path_missing")
        return path

    def verify_event(self, event: Mapping[str, Any]) -> bool:
        if not self.is_persistent() or not self.verify_current():
            return False
        if canonical_sha256(event) != self._record.get("event_sha256"):
            return False
        facet_digest = self._record.get("facet_sha256")
        if facet_digest is not None:
            facets = event.get("facets") if isinstance(event.get("facets"), Mapping) else {}
            candidate = facets.get("identity_bound_telemetry_receipt")
            if canonical_sha256(candidate) != facet_digest:
                return False
        return self.verify_event_source()

    def verify_event_source(self) -> bool:
        """Re-read the recorded event/facet from the current owner artifact."""

        if not self.is_persistent() or not self.verify_current():
            return False
        try:
            artifact_bytes = self._read_current("artifact_sha256")
        except (OSError, TelemetryError):
            return False
        facet_sha256 = self._record.get("facet_sha256")
        return _source_artifact_contains_event(
            artifact_bytes,
            event_sha256=str(self._record.get("event_sha256") or ""),
            facet_sha256=str(facet_sha256) if facet_sha256 is not None else None,
        )


class OwnerCapturedEvent(dict[str, Any]):
    """A generated event carrying its source-artifact evidence in memory."""

    __slots__ = ("_owner_source_evidence",)

    def __init__(self, value: Mapping[str, Any], *, owner_source_evidence: OwnerSourceEvidence) -> None:
        super().__init__(copy.deepcopy(dict(value)))
        self._owner_source_evidence = owner_source_evidence


class EpisodeComponentAdmission:
    """Immutable in-process witness issued after manifest/component verification."""

    __slots__ = ("_binding", "_owner_source_evidence", "_validation_context")

    def __init__(
        self,
        binding: Mapping[str, Any],
        *,
        owner_source_evidence: OwnerSourceEvidence,
        validation_context: Mapping[str, Any] | None = None,
        token: object,
    ) -> None:
        if token is not _EPISODE_COMPONENT_ADMISSION_TOKEN:
            raise TypeError("episode_component_admission_is_owner_issued")
        self._binding = copy.deepcopy(dict(binding))
        self._owner_source_evidence = owner_source_evidence
        self._validation_context = copy.deepcopy(dict(validation_context or {}))

    def __copy__(self) -> Any:
        raise TypeError("episode_component_admission_is_not_copyable")

    def __deepcopy__(self, memo: dict[int, Any]) -> Any:
        raise TypeError("episode_component_admission_is_not_copyable")

    def public_binding(self) -> dict[str, Any]:
        return copy.deepcopy(self._binding)

    def public_owner_record(self) -> dict[str, Any]:
        return self._owner_source_evidence.public_record()

    def verify_current(self) -> bool:
        if not self._owner_source_evidence.verify_current():
            return False
        if not self._validation_context:
            return True
        context = self._validation_context
        context_material = {
            key: copy.deepcopy(context[key])
            for key in (
                "session_id",
                "session_ref",
                "episode_id",
                "component_ref",
                "source",
                "component_identity",
                "expected_projection",
                "expected_task_episode_generation",
                "expected_generation_context",
            )
            if key in context
        }
        if self._owner_source_evidence.public_record().get("owner_context_sha256") != canonical_sha256(
            context_material
        ):
            return False
        try:
            _validate_episode_component_artifacts(
                session_id=str(context["session_id"]),
                manifest_path=self._owner_source_evidence._path_for("manifest_sha256"),
                component_path=self._owner_source_evidence._path_for("component_artifact_sha256"),
                session_manifest_path=self._owner_source_evidence._path_for("session_manifest_sha256"),
                episode_id=str(context["episode_id"]),
                component_ref=str(context["component_ref"]),
                manifest_sha256=str(context["manifest_sha256"]),
                artifact_sha256=str(context["artifact_sha256"]),
                payload_sha256=str(context["payload_sha256"]),
                source=context["source"],
                component_identity=context["component_identity"],
                expected_projection=context["expected_projection"],
                expected_task_episode_generation=str(context["expected_task_episode_generation"]),
                expected_generation_context=context.get("expected_generation_context"),
                source_evidence=self._owner_source_evidence,
            )
        except (KeyError, OSError, TelemetryError):
            return False
        return self._owner_source_evidence.verify_current()


class CarryingEventWitness:
    """Immutable capture-produced join witness for one receipt facet event."""

    __slots__ = ("_value", "_owner_source_evidence")

    def __init__(
        self,
        value: Mapping[str, Any],
        *,
        owner_source_evidence: OwnerSourceEvidence,
        token: object,
    ) -> None:
        if token is not _CARRYING_EVENT_WITNESS_TOKEN:
            raise TypeError("carrying_event_witness_is_capture_issued")
        if not isinstance(owner_source_evidence, OwnerSourceEvidence):
            raise TypeError("carrying_event_owner_source_evidence_required")
        self._value = copy.deepcopy(dict(value))
        self._owner_source_evidence = owner_source_evidence

    def __copy__(self) -> Any:
        raise TypeError("carrying_event_witness_is_not_copyable")

    def __deepcopy__(self, memo: dict[int, Any]) -> Any:
        raise TypeError("carrying_event_witness_is_not_copyable")

    def public_event(self) -> dict[str, Any]:
        return copy.deepcopy(self._value["event"])

    def public_context(self) -> dict[str, Any]:
        return copy.deepcopy(
            {
                key: self._value[key]
                for key in ("session_id", "session_ref", "source", "projection")
            }
        )

    def public_owner_record(self) -> dict[str, Any]:
        return copy.deepcopy(self._value["owner_record"])

    def verify_source_current(self) -> bool:
        return self._owner_source_evidence.verify_event_source()


class ReceiptProvenanceWitness:
    """Owner-issued receipt/facet chain retained alongside a packet."""

    __slots__ = ("_chain",)

    def __init__(self, chain: Mapping[str, Any], *, token: object) -> None:
        if token is not _RECEIPT_PROVENANCE_WITNESS_TOKEN:
            raise TypeError("receipt_provenance_witness_is_owner_issued")
        self._chain = copy.deepcopy(dict(chain))

    def __copy__(self) -> Any:
        raise TypeError("receipt_provenance_witness_is_not_copyable")

    def __deepcopy__(self, memo: dict[int, Any]) -> Any:
        raise TypeError("receipt_provenance_witness_is_not_copyable")

    def public_chain(self) -> dict[str, Any]:
        return copy.deepcopy(self._chain)


class IdentityBoundPacket(dict[str, Any]):
    """JSON-compatible packet retaining non-serialised owner witnesses in memory."""

    __slots__ = (
        "_component_admission",
        "_carrying_event_witness",
        "_receipt_provenance_witness",
    )

    def __init__(
        self,
        value: Mapping[str, Any],
        *,
        component_admission: EpisodeComponentAdmission | None = None,
        carrying_event_witness: CarryingEventWitness | None = None,
        receipt_provenance_witness: ReceiptProvenanceWitness | None = None,
    ) -> None:
        super().__init__(copy.deepcopy(dict(value)))
        self._component_admission = component_admission
        self._carrying_event_witness = carrying_event_witness
        self._receipt_provenance_witness = receipt_provenance_witness

    def __copy__(self) -> "IdentityBoundPacket":
        return type(self)(dict(self))

    def __deepcopy__(self, memo: dict[int, Any]) -> "IdentityBoundPacket":
        return type(self)(
            copy.deepcopy(dict(self), memo),
            component_admission=self._component_admission,
            carrying_event_witness=self._carrying_event_witness,
            receipt_provenance_witness=self._receipt_provenance_witness,
        )


def _semantic_source_value(value: Any) -> Any:
    """Normalize one persisted public projection value for source hashing."""

    if isinstance(value, Mapping):
        return {
            str(key): _semantic_source_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if str(key) not in EPISODE_SOURCE_SEMANTIC_VOLATILE_KEYS
        }
    if isinstance(value, list):
        return [_semantic_source_value(item) for item in value]
    return value


def canonical_episode_source_sha256(value: Any) -> str:
    """Return the owner-recomputable semantic digest of a public component."""

    encoded = json.dumps(
        _semantic_source_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _canonical_component_payload_sha256(value: Any) -> str:
    """Match the owner shard payload digest without admitting caller data."""

    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _absolute_path(path: Path) -> Path:
    """Pin a path lexically without resolving symlinks."""

    return Path(os.path.abspath(os.fspath(path)))


def _stat_signature(value: os.stat_result) -> tuple[int, int, int, int]:
    return (
        int(value.st_dev),
        int(value.st_ino),
        int(stat.S_IFMT(value.st_mode)),
        int(value.st_nlink),
    )


def _directory_signature(value: os.stat_result) -> tuple[int, int, int]:
    """Identify a parent directory without treating child-count as identity."""

    return (
        int(value.st_dev),
        int(value.st_ino),
        int(stat.S_IFMT(value.st_mode)),
    )


def _path_identity_snapshot(path: Path) -> dict[str, Any]:
    """Capture a regular-file identity and a symlink-safe parent chain.

    File bytes alone are insufficient for owner admission: a same-byte link or
    atomic replacement must not be able to inherit a previously issued
    witness.  Parent identities also keep a path from silently moving through
    a replaced or symlinked directory.
    """

    absolute = _absolute_path(path)
    parts = absolute.parts
    if not absolute.is_absolute() or len(parts) < 2:
        raise TelemetryAdmissionError("owner_source_path_invalid")
    try:
        parent_identities: list[dict[str, Any]] = []
        root = Path(absolute.anchor)
        root_stat = os.lstat(root)
        if not stat.S_ISDIR(root_stat.st_mode):
            raise TelemetryAdmissionError("owner_source_parent_not_directory")
        parent_identities.append({"path": str(root), "stat": _directory_signature(root_stat)})
        current = root
        for component in parts[1:-1]:
            current = current / component
            parent_stat = os.lstat(current)
            if stat.S_ISLNK(parent_stat.st_mode) or not stat.S_ISDIR(parent_stat.st_mode):
                raise TelemetryAdmissionError("owner_source_parent_not_safe")
            parent_identities.append(
                {"path": str(current), "stat": _directory_signature(parent_stat)}
            )
        final_stat = os.lstat(absolute)
    except OSError as exc:
        raise TelemetryAdmissionError("owner_source_path_unreadable") from exc
    if stat.S_ISLNK(final_stat.st_mode) or not stat.S_ISREG(final_stat.st_mode):
        raise TelemetryAdmissionError("owner_source_path_not_regular")
    if final_stat.st_nlink != 1:
        raise TelemetryAdmissionError("owner_source_path_hardlink_rejected")
    return {
        "path": str(absolute),
        "file": _stat_signature(final_stat),
        "parents": parent_identities,
    }


def _same_path_identity(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return (
        left.get("path") == right.get("path")
        and left.get("file") == right.get("file")
        and left.get("parents") == right.get("parents")
    )


def _read_regular_file(
    path: Path,
    *,
    expected_identity: Mapping[str, Any] | None = None,
    error_prefix: str,
) -> tuple[bytes, dict[str, Any]]:
    """Read one regular file through no-follow directory traversal.

    The lexical path is checked before opening, the opened descriptors are
    checked before and after the read, and the path/parent chain is checked
    again after closing.  This is intentionally a bounded local witness, not
    an external signature or registry claim.
    """

    absolute = _absolute_path(path)
    before = _path_identity_snapshot(absolute)
    if expected_identity is not None and not _same_path_identity(expected_identity, before):
        raise TelemetryAdmissionError(f"{error_prefix}_identity_changed")

    nofollow = getattr(os, "O_NOFOLLOW", 0)
    cloexec = getattr(os, "O_CLOEXEC", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    root_fd: int | None = None
    current_fd: int | None = None
    final_fd: int | None = None
    try:
        root_fd = os.open(absolute.anchor, os.O_RDONLY | directory | cloexec | nofollow)
        current_fd = root_fd
        parent_records = before.get("parents")
        parent_index = 0
        if not isinstance(parent_records, list):
            raise TelemetryAdmissionError(f"{error_prefix}_parent_identity_missing")
        if parent_records[0].get("stat") != _directory_signature(os.fstat(current_fd)):
            raise TelemetryAdmissionError(f"{error_prefix}_parent_identity_changed")
        for component in absolute.parts[1:-1]:
            next_fd = os.open(
                component,
                os.O_RDONLY | directory | cloexec | nofollow,
                dir_fd=current_fd,
            )
            if current_fd != root_fd:
                os.close(current_fd)
            current_fd = next_fd
            parent_index += 1
            current_stat = os.fstat(current_fd)
            if not stat.S_ISDIR(current_stat.st_mode):
                raise TelemetryAdmissionError(f"{error_prefix}_parent_not_directory")
            if parent_index >= len(parent_records) or parent_records[parent_index].get("stat") != _directory_signature(current_stat):
                raise TelemetryAdmissionError(f"{error_prefix}_parent_identity_changed")

        final_fd = os.open(
            absolute.parts[-1],
            os.O_RDONLY | cloexec | nofollow,
            dir_fd=current_fd,
        )
        opened_stat = os.fstat(final_fd)
        opened_identity = _stat_signature(opened_stat)
        if not stat.S_ISREG(opened_stat.st_mode) or opened_stat.st_nlink != 1:
            raise TelemetryAdmissionError(f"{error_prefix}_not_regular")
        if opened_identity != before.get("file"):
            raise TelemetryAdmissionError(f"{error_prefix}_identity_changed")
        if expected_identity is not None and opened_identity != expected_identity.get("file"):
            raise TelemetryAdmissionError(f"{error_prefix}_identity_changed")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(final_fd, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after_open_stat = os.fstat(final_fd)
        if _stat_signature(after_open_stat) != opened_identity:
            raise TelemetryAdmissionError(f"{error_prefix}_replaced_during_read")
        data = b"".join(chunks)
    except TelemetryAdmissionError:
        raise
    except OSError as exc:
        raise TelemetryAdmissionError(f"{error_prefix}_unreadable") from exc
    finally:
        if final_fd is not None:
            try:
                os.close(final_fd)
            except OSError:
                pass
        if current_fd is not None and current_fd != final_fd:
            try:
                os.close(current_fd)
            except OSError:
                pass
        if root_fd is not None and root_fd != current_fd and root_fd != final_fd:
            try:
                os.close(root_fd)
            except OSError:
                pass

    after = _path_identity_snapshot(absolute)
    if not _same_path_identity(before, after):
        raise TelemetryAdmissionError(f"{error_prefix}_replaced_after_read")
    if expected_identity is not None and not _same_path_identity(expected_identity, after):
        raise TelemetryAdmissionError(f"{error_prefix}_identity_changed")
    return data, after


def _owner_directory_identity_snapshot(path: Path) -> dict[str, Any]:
    """Capture one canonical directory and its symlink-safe parent chain."""

    absolute = _absolute_path(path)
    if not absolute.is_absolute() or len(absolute.parts) < 2:
        raise TelemetryAdmissionError("owner_root_path_invalid")
    try:
        parent_records: list[dict[str, Any]] = []
        current = Path(absolute.anchor)
        anchor_stat = os.lstat(current)
        if stat.S_ISLNK(anchor_stat.st_mode) or not stat.S_ISDIR(anchor_stat.st_mode):
            raise TelemetryAdmissionError("owner_root_parent_not_safe")
        parent_records.append({"path": str(current), "stat": _directory_signature(anchor_stat)})
        for component in absolute.parts[1:]:
            current = current / component
            current_stat = os.lstat(current)
            if stat.S_ISLNK(current_stat.st_mode) or not stat.S_ISDIR(current_stat.st_mode):
                raise TelemetryAdmissionError("owner_root_not_directory")
            parent_records.append({"path": str(current), "stat": _directory_signature(current_stat)})
    except OSError as exc:
        raise TelemetryAdmissionError("owner_root_unreadable") from exc
    return {
        "path": str(absolute),
        "directory": parent_records[-1]["stat"],
        "parents": parent_records,
    }


def _owner_alias_contract_digest(value: Mapping[str, Any]) -> str:
    return canonical_sha256(
        {key: item for key, item in value.items() if key != "contract_sha256"}
    )


def _owner_root_identity_digest(root_identity: Mapping[str, Any]) -> str:
    return canonical_sha256(
        {
            "schema_version": OWNER_ROOT_IDENTITY_SCHEMA_VERSION,
            "identity": dict(root_identity),
        }
    )


def _owner_alias_epoch_digest(
    *,
    root_sha256: str,
    source_ref: str,
    trust_anchor_ref: str,
    key_sha256: str,
) -> str:
    return canonical_sha256(
        {
            "schema_version": OWNER_ALIAS_ADMISSION_EPOCH_SCHEMA_VERSION,
            "root_sha256": root_sha256,
            "source_ref": source_ref,
            "trust_anchor_ref": trust_anchor_ref,
            "key_sha256": key_sha256,
        }
    )


def _owner_alias_admission_payload(contract: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: copy.deepcopy(value)
        for key, value in contract.items()
        if key not in {"admission_signature", "contract_sha256"}
    }


def _owner_alias_admission_message(contract: Mapping[str, Any]) -> str:
    return canonical_sha256(_owner_alias_admission_payload(contract))


def _owner_alias_admission_is_valid(
    contract: Mapping[str, Any],
    *,
    root_identity: Mapping[str, Any],
    root_sha256: str,
    trust_anchor: _OwnerAliasTrustAnchor,
) -> bool:
    if not isinstance(contract, Mapping) or not isinstance(trust_anchor, _OwnerAliasTrustAnchor):
        return False
    if contract.get("root_sha256") != root_sha256:
        return False
    if contract.get("key_path") != OWNER_ALIAS_SOURCE_KEY_RELATIVE_PATH:
        return False
    source_ref = contract.get("source_ref")
    trust_anchor_ref = contract.get("trust_anchor_ref")
    key_sha256 = contract.get("key_sha256")
    epoch_sha256 = contract.get("epoch_sha256")
    signature = contract.get("admission_signature")
    if (
        not isinstance(source_ref, str)
        or not isinstance(trust_anchor_ref, str)
        or not isinstance(key_sha256, str)
        or not HEX_RE.fullmatch(key_sha256)
        or not isinstance(epoch_sha256, str)
        or not SHA256_RE.fullmatch(epoch_sha256)
        or not isinstance(signature, str)
        or not SHA256_RE.fullmatch(signature)
        or trust_anchor._anchor_ref != trust_anchor_ref
    ):
        return False
    try:
        _safe_ref(source_ref, "session_alias_owner_source_ref")
        _safe_ref(trust_anchor_ref, "session_alias_owner_trust_anchor_ref")
    except TelemetryError:
        return False
    expected_epoch = _owner_alias_epoch_digest(
        root_sha256=root_sha256,
        source_ref=source_ref,
        trust_anchor_ref=trust_anchor_ref,
        key_sha256=key_sha256,
    )
    if epoch_sha256 != expected_epoch:
        return False
    if contract.get("contract_sha256") != _owner_alias_contract_digest(contract):
        return False
    return trust_anchor.verify(_owner_alias_admission_message(contract), signature)


def _provision_owner_alias_trust_anchor(
    anchor_ref: str,
    verifier: Any,
    *,
    token: object,
) -> None:
    """Install an owner-supplied verifier; production provisioning is external."""

    if token is not _OWNER_ALIAS_TRUST_ANCHOR_PROVISION_TOKEN:
        raise TypeError("owner_alias_trust_anchor_provisioning_is_owner_controlled")
    anchor = _OwnerAliasTrustAnchor(
        anchor_ref=anchor_ref,
        verify=verifier,
        token=_OWNER_ALIAS_TRUST_ANCHOR_PROVISION_TOKEN,
    )
    _OWNER_ALIAS_TRUST_ANCHORS[anchor_ref] = anchor


def _owner_alias_source_from_contract(
    owner_root: Path,
    *,
    root_identity: Mapping[str, Any] | None = None,
) -> OwnerAliasSource:
    """Load a signed owner admission and retain only an opaque issuance ticket."""

    owner_root = _absolute_path(owner_root)
    root_identity = (
        copy.deepcopy(dict(root_identity))
        if root_identity is not None
        else _owner_directory_identity_snapshot(owner_root)
    )
    root_sha256 = _owner_root_identity_digest(root_identity)
    contract_path = owner_root / OWNER_ALIAS_SOURCE_CONTRACT_RELATIVE_PATH
    key_path = owner_root / OWNER_ALIAS_SOURCE_KEY_RELATIVE_PATH
    try:
        contract_bytes, contract_identity = _read_regular_file(
            contract_path,
            error_prefix="session_alias_owner_contract",
        )
    except (OSError, TelemetryError) as exc:
        raise TelemetryAdmissionError("session_alias_owner_contract_unreadable") from exc
    try:
        contract = json.loads(contract_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TelemetryAdmissionError("session_alias_owner_contract_invalid") from exc
    if not isinstance(contract, Mapping):
        raise TelemetryAdmissionError("session_alias_owner_contract_invalid")
    required = {
        "schema_version",
        "issuer",
        "source_ref",
        "trust_anchor_ref",
        "key_path",
        "key_sha256",
        "root_sha256",
        "epoch_sha256",
        "admission_signature",
        "contract_sha256",
    }
    if set(contract) != required:
        raise TelemetryAdmissionError("session_alias_owner_contract_shape_invalid")
    if contract.get("schema_version") != OWNER_ALIAS_SOURCE_SCHEMA_VERSION:
        raise TelemetryAdmissionError("session_alias_owner_contract_schema_unsupported")
    if contract.get("issuer") != "aoa-session-memory":
        raise TelemetryAdmissionError("session_alias_owner_contract_issuer_invalid")
    source_ref = _safe_ref(contract.get("source_ref"), "session_alias_owner_source_ref")
    trust_anchor_ref = _safe_ref(
        contract.get("trust_anchor_ref"),
        "session_alias_owner_trust_anchor_ref",
    )
    if contract.get("key_path") != OWNER_ALIAS_SOURCE_KEY_RELATIVE_PATH:
        raise TelemetryAdmissionError("session_alias_owner_key_path_invalid")
    key_sha256 = contract.get("key_sha256")
    contract_sha256 = contract.get("contract_sha256")
    if (
        not isinstance(key_sha256, str)
        or not HEX_RE.fullmatch(key_sha256)
        or not isinstance(contract_sha256, str)
        or not SHA256_RE.fullmatch(contract_sha256)
    ):
        raise TelemetryAdmissionError("session_alias_owner_contract_digest_invalid")
    trust_anchor = _OWNER_ALIAS_TRUST_ANCHORS.get(trust_anchor_ref)
    if not isinstance(trust_anchor, _OwnerAliasTrustAnchor):
        raise TelemetryAdmissionError("session_alias_owner_trust_anchor_unavailable")
    if not _owner_alias_admission_is_valid(
        contract,
        root_identity=root_identity,
        root_sha256=root_sha256,
        trust_anchor=trust_anchor,
    ):
        raise TelemetryAdmissionError("session_alias_owner_admission_invalid")
    epoch_sha256 = str(contract["epoch_sha256"])
    try:
        key_bytes, key_identity = _read_regular_file(
            key_path,
            error_prefix="session_alias_owner_key",
        )
    except (OSError, TelemetryError) as exc:
        raise TelemetryAdmissionError("session_alias_owner_key_unreadable") from exc
    if hashlib.sha256(key_bytes).hexdigest() != key_sha256:
        raise TelemetryAdmissionError("session_alias_owner_key_digest_mismatch")
    issuance = _OWNER_ALIAS_ISSUANCE_REGISTRY.issue(
        root_path=owner_root,
        root_sha256=root_sha256,
        epoch_sha256=epoch_sha256,
        source_ref=source_ref,
        trust_anchor_ref=trust_anchor_ref,
        contract_path=contract_path,
        key_path=key_path,
        expected_contract=contract,
        contract_identity=contract_identity,
        key_identity=key_identity,
        key_sha256=key_sha256,
        trust_anchor=trust_anchor,
    )
    return OwnerAliasSource(
        issuance=issuance,
        token=_OWNER_ALIAS_SOURCE_TOKEN,
    )


def _issue_owner_root_witness(
    owner_root: Path,
    *,
    alias_source: OwnerAliasSource | None = None,
    root_identity: Mapping[str, Any] | None = None,
) -> OwnerRootWitness:
    if not isinstance(alias_source, OwnerAliasSource):
        raise TelemetryAdmissionError("owner_root_alias_source_required")
    owner_root = _absolute_path(owner_root)
    root_identity = (
        copy.deepcopy(dict(root_identity))
        if root_identity is not None
        else _owner_directory_identity_snapshot(owner_root)
    )
    root_sha256 = _owner_root_identity_digest(root_identity)
    epoch_sha256 = alias_source._issuance._epoch_sha256
    if not alias_source._matches_root(owner_root, root_sha256, epoch_sha256):
        raise TelemetryAdmissionError("owner_root_alias_source_root_mismatch")
    if not alias_source._verify_current(
        root_path=owner_root,
        root_identity=root_identity,
        root_sha256=root_sha256,
        epoch_sha256=epoch_sha256,
    ):
        raise TelemetryAdmissionError("owner_root_alias_source_not_current")
    return OwnerRootWitness(
        root_path=owner_root,
        root_identity=root_identity,
        epoch_sha256=epoch_sha256,
        alias_source=alias_source,
        token=_OWNER_ROOT_WITNESS_TOKEN,
    )


def _owner_root_witness_for_root(owner_root: Path) -> OwnerRootWitness:
    owner_root = _absolute_path(owner_root)
    root_identity = _owner_directory_identity_snapshot(owner_root)
    return _issue_owner_root_witness(
        owner_root,
        alias_source=_owner_alias_source_from_contract(
            owner_root,
            root_identity=root_identity,
        ),
        root_identity=root_identity,
    )


def _source_artifact_event_candidates(source: Path | bytes | bytearray) -> list[Mapping[str, Any]]:
    """Read only structured event candidates from one owner artifact."""

    try:
        if isinstance(source, (bytes, bytearray)):
            value = json.loads(bytes(source).decode("utf-8"))
        else:
            value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return []
    candidates: list[Mapping[str, Any]] = []
    if isinstance(value, list):
        candidates.extend(item for item in value if isinstance(item, Mapping))
    elif isinstance(value, Mapping):
        events = value.get("events")
        if isinstance(events, list):
            candidates.extend(item for item in events if isinstance(item, Mapping))
        for key in ("event", "record"):
            item = value.get(key)
            if isinstance(item, Mapping):
                candidates.append(item)
        if "line" in value and "event_id" in value:
            candidates.append(value)
    return candidates


def _source_artifact_contains_event(
    source: Path | bytes | bytearray,
    *,
    event_sha256: str,
    facet_sha256: str | None,
) -> bool:
    for candidate in _source_artifact_event_candidates(source):
        if canonical_sha256(candidate) != event_sha256:
            continue
        if facet_sha256 is None:
            return True
        facets = candidate.get("facets") if isinstance(candidate.get("facets"), Mapping) else {}
        if canonical_sha256(facets.get("identity_bound_telemetry_receipt")) == facet_sha256:
            return True
    return False


OWNER_MEMBERSHIP_SCHEMA_VERSION = "owner_admission_membership_v1"


def _owner_registry_path_for_session(session_dir: Path) -> Path:
    session_dir = _absolute_path(session_dir)
    if session_dir.parent.name != "sessions":
        raise TelemetryAdmissionError("owner_session_registry_root_invalid")
    return session_dir.parent.parent / "session-registry.json"


def _owner_membership_child_path(
    session_dir: Path,
    declared: Any,
    *,
    relative_parent: str,
    error: str,
) -> Path:
    if not isinstance(declared, str) or not declared:
        raise TelemetryAdmissionError(error)
    raw = Path(declared)
    candidate = _absolute_path(raw if raw.is_absolute() else session_dir / raw)
    expected_parent = _absolute_path(session_dir / relative_parent)
    if candidate.parent != expected_parent or candidate.name != raw.name:
        raise TelemetryAdmissionError(error)
    return candidate


def _owner_membership_file_spec(
    path: Path,
    *,
    error_prefix: str,
    transaction: _OwnerAdmissionTransaction | None = None,
) -> dict[str, Any]:
    if transaction is None:
        data, identity = _read_regular_file(path, error_prefix=error_prefix)
    else:
        data, identity = transaction.read(
            path,
            expected_identity=None,
            error_prefix=error_prefix,
        )
    return {
        "path": str(_absolute_path(path)),
        "sha256": f"sha256:{hashlib.sha256(data).hexdigest()}",
        "identity": identity,
    }


def _verify_owner_membership_artifact_current(
    membership: Mapping[str, Any],
    *,
    transaction: _OwnerAdmissionTransaction | None = None,
) -> None:
    files = membership.get("files")
    artifact = files.get("artifact") if isinstance(files, Mapping) else None
    if not isinstance(artifact, Mapping):
        raise TelemetryAdmissionError("owner_membership_artifact_missing")
    path = Path(str(artifact.get("path") or ""))
    expected_identity = (
        artifact.get("identity") if isinstance(artifact.get("identity"), Mapping) else None
    )
    if transaction is None:
        data, _identity = _read_regular_file(
            path,
            expected_identity=expected_identity,
            error_prefix="owner_artifact",
        )
    else:
        data, _identity = transaction.read(
            path,
            expected_identity=expected_identity,
            error_prefix="owner_artifact",
        )
    actual = f"sha256:{hashlib.sha256(data).hexdigest()}"
    if actual != artifact.get("sha256") or actual != membership.get("artifact_sha256"):
        raise TelemetryAdmissionError("owner_artifact_digest_mismatch")


def _owner_membership_json(
    membership: Mapping[str, Any],
    key: str,
    *,
    error_prefix: str,
    transaction: _OwnerAdmissionTransaction | None = None,
) -> tuple[bytes, dict[str, Any]]:
    if not isinstance(membership, Mapping):
        raise TelemetryAdmissionError(f"{error_prefix}_membership_invalid")
    files = membership.get("files")
    spec = files.get(key) if isinstance(files, Mapping) else None
    if not isinstance(spec, Mapping):
        raise TelemetryAdmissionError(f"{error_prefix}_file_missing")
    path = Path(str(spec.get("path") or ""))
    identity = spec.get("identity")
    expected_identity = identity if isinstance(identity, Mapping) else None
    if transaction is None:
        data, _current_identity = _read_regular_file(
            path,
            expected_identity=expected_identity,
            error_prefix=error_prefix,
        )
    else:
        data, _current_identity = transaction.read(
            path,
            expected_identity=expected_identity,
            error_prefix=error_prefix,
        )
    actual = f"sha256:{hashlib.sha256(data).hexdigest()}"
    if actual != spec.get("sha256"):
        raise TelemetryAdmissionError(f"{error_prefix}_digest_mismatch")
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TelemetryAdmissionError(f"{error_prefix}_json_invalid") from exc
    if not isinstance(value, dict):
        raise TelemetryAdmissionError(f"{error_prefix}_object_required")
    return data, value


def _owner_membership_registry_record(
    registry: Mapping[str, Any],
    *,
    session_manifest: Mapping[str, Any],
    session_dir: Path,
    session_id: str,
) -> dict[str, Any]:
    sessions = registry.get("sessions") if isinstance(registry.get("sessions"), list) else []
    matches = [
        item
        for item in sessions
        if isinstance(item, Mapping) and str(item.get("session_id") or "") == session_id
    ]
    if len(matches) != 1:
        raise TelemetryAdmissionError("owner_session_registry_membership_invalid")
    record = dict(matches[0])
    if _absolute_path(Path(str(record.get("path") or ""))) != _absolute_path(session_dir):
        raise TelemetryAdmissionError("owner_session_registry_path_mismatch")
    display = session_manifest.get("display") if isinstance(session_manifest.get("display"), Mapping) else {}
    session_label = str(
        session_manifest.get("session_label")
        or display.get("label")
        or ""
    )
    if not session_label or session_label != session_dir.name:
        raise TelemetryAdmissionError("owner_session_manifest_label_mismatch")
    if record.get("session_label") not in (None, "", session_label):
        raise TelemetryAdmissionError("owner_session_registry_label_mismatch")
    manifest_status = str(session_manifest.get("archive_status") or "")
    if record.get("archive_status") not in (None, "", manifest_status):
        raise TelemetryAdmissionError("owner_session_registry_status_mismatch")
    segments = session_manifest.get("segments") if isinstance(session_manifest.get("segments"), list) else []
    if record.get("segment_count") is not None:
        try:
            segment_count = int(record.get("segment_count"))
        except (TypeError, ValueError):
            raise TelemetryAdmissionError("owner_session_registry_segment_count_invalid") from None
        if segment_count != len(segments):
            raise TelemetryAdmissionError("owner_session_registry_segment_count_mismatch")
    return record


def _owner_segment_manifest_entry(
    session_manifest: Mapping[str, Any],
    *,
    session_dir: Path,
    artifact_path: Path,
    segment_id: str | None = None,
) -> dict[str, Any]:
    segments = session_manifest.get("segments") if isinstance(session_manifest.get("segments"), list) else []
    matches: list[dict[str, Any]] = []
    for item in segments:
        if not isinstance(item, Mapping):
            continue
        declared_path = _owner_membership_child_path(
            session_dir,
            item.get("index"),
            relative_parent="segments",
            error="owner_segment_manifest_path_invalid",
        )
        if declared_path != _absolute_path(artifact_path):
            continue
        if segment_id and str(item.get("segment_id") or "") != segment_id:
            continue
        matches.append(dict(item))
    if len(matches) != 1:
        raise TelemetryAdmissionError("owner_segment_manifest_membership_missing")
    entry = matches[0]
    receipts = entry.get("artifact_receipts") if isinstance(entry.get("artifact_receipts"), Mapping) else {}
    index_receipt = receipts.get("index") if isinstance(receipts.get("index"), Mapping) else {}
    expected_sha = str(index_receipt.get("sha256") or "")
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha):
        raise TelemetryAdmissionError("owner_segment_manifest_artifact_receipt_missing")
    return entry


def _owner_component_manifest_entry(
    component_manifest: Mapping[str, Any],
    *,
    component_ref: str,
    component_path: Path,
    session_dir: Path,
) -> dict[str, Any]:
    expected_path = _owner_membership_child_path(
        session_dir,
        component_ref,
        relative_parent="session-index-shards/task-episodes",
        error="owner_component_path_invalid",
    )
    if expected_path != _absolute_path(component_path):
        raise TelemetryAdmissionError("owner_component_path_membership_mismatch")
    components = (
        component_manifest.get("components")
        if isinstance(component_manifest.get("components"), Mapping)
        else {}
    )
    refs = components.get("task_episodes") if isinstance(components.get("task_episodes"), list) else []
    matches = [
        dict(item)
        for item in refs
        if isinstance(item, Mapping) and str(item.get("ref") or "") == component_ref
    ]
    if len(matches) != 1:
        raise TelemetryAdmissionError("owner_component_manifest_membership_missing")
    return matches[0]


def _verify_owner_membership_record_current(
    membership: Mapping[str, Any],
    *,
    owner_root_witness: OwnerRootWitness,
    currentness: OwnerRootCurrentnessReceipt | None = None,
    transaction: _OwnerAdmissionTransaction | None = None,
    finalize: bool = True,
) -> bool:
    if not isinstance(membership, Mapping):
        raise TelemetryAdmissionError("owner_membership_invalid")
    if not isinstance(owner_root_witness, OwnerRootWitness):
        raise TelemetryAdmissionError("owner_root_witness_required")
    if membership.get("schema_version") != OWNER_MEMBERSHIP_SCHEMA_VERSION:
        raise TelemetryAdmissionError("owner_membership_schema_unsupported")
    kind = str(membership.get("kind") or "")
    if kind not in {"segment_index", "episode_component"}:
        raise TelemetryAdmissionError("owner_membership_kind_invalid")
    session_dir = _absolute_path(Path(str(membership.get("session_dir") or "")))
    session_id = str(membership.get("session_id") or "")
    if not session_id:
        raise TelemetryAdmissionError("owner_membership_session_id_missing")
    if membership.get("owner_root_sha256") != owner_root_witness._root_sha256:
        raise TelemetryAdmissionError("owner_membership_owner_root_mismatch")
    if membership.get("owner_epoch_sha256") != owner_root_witness._epoch_sha256:
        raise TelemetryAdmissionError("owner_membership_owner_epoch_mismatch")
    if transaction is None:
        transaction = _OwnerAdmissionTransaction(owner_root_witness)
    if currentness is None:
        currentness = transaction.start()
    owner_root_witness.assert_session_dir(session_dir, currentness=currentness)
    _verify_owner_membership_artifact_current(membership, transaction=transaction)
    _registry_bytes, registry = _owner_membership_json(
        membership,
        "registry",
        error_prefix="owner_registry",
        transaction=transaction,
    )
    _session_bytes, session_manifest = _owner_membership_json(
        membership,
        "session_manifest",
        error_prefix="owner_session_manifest",
        transaction=transaction,
    )
    _owner_membership_registry_record(
        registry,
        session_manifest=session_manifest,
        session_dir=session_dir,
        session_id=session_id,
    )
    if str(session_manifest.get("session_id") or "") != session_id:
        raise TelemetryAdmissionError("owner_session_manifest_session_id_mismatch")

    if kind == "segment_index":
        _owner_bytes, segment_manifest = _owner_membership_json(
            membership,
            "owner_manifest",
            error_prefix="owner_segment_manifest",
            transaction=transaction,
        )
        if segment_manifest != session_manifest:
            raise TelemetryAdmissionError("owner_segment_manifest_not_session_manifest")
        files = membership.get("files")
        artifact_spec = files.get("artifact") if isinstance(files, Mapping) else None
        artifact_path = _absolute_path(Path(str(artifact_spec.get("path") or ""))) if isinstance(artifact_spec, Mapping) else Path()
        entry = _owner_segment_manifest_entry(
            session_manifest,
            session_dir=session_dir,
            artifact_path=artifact_path,
            segment_id=str(membership.get("segment_id") or "") or None,
        )
        receipt = entry.get("artifact_receipts") if isinstance(entry.get("artifact_receipts"), Mapping) else {}
        index_receipt = receipt.get("index") if isinstance(receipt.get("index"), Mapping) else {}
        expected_sha = f"sha256:{index_receipt.get('sha256')}"
        if expected_sha != str(membership.get("artifact_sha256") or ""):
            raise TelemetryAdmissionError("owner_segment_manifest_artifact_digest_mismatch")
        _verify_owner_membership_artifact_current(membership, transaction=transaction)
        if finalize:
            transaction.finalize()
        return True

    _component_manifest_bytes, component_manifest = _owner_membership_json(
        membership,
        "owner_manifest",
        error_prefix="owner_component_manifest",
        transaction=transaction,
    )
    component_ref = str(membership.get("component_ref") or "")
    files = membership.get("files")
    artifact_spec = files.get("artifact") if isinstance(files, Mapping) else None
    component_path = _absolute_path(Path(str(artifact_spec.get("path") or ""))) if isinstance(artifact_spec, Mapping) else Path()
    entry = _owner_component_manifest_entry(
        component_manifest,
        component_ref=component_ref,
        component_path=component_path,
        session_dir=session_dir,
    )
    expected_sha = f"sha256:{entry.get('artifact_sha256')}"
    if expected_sha != str(membership.get("artifact_sha256") or ""):
        raise TelemetryAdmissionError("owner_component_manifest_artifact_digest_mismatch")
    _verify_owner_membership_artifact_current(membership, transaction=transaction)
    if finalize:
        transaction.finalize()
    return True


def _verify_owner_membership_current(membership: OwnerMembershipWitness) -> bool:
    if not isinstance(membership, OwnerMembershipWitness):
        raise TelemetryAdmissionError("owner_membership_witness_required")
    return membership.verify_current()


def _owner_membership_snapshot(
    *,
    kind: str,
    session_dir: Path,
    artifact_path: Path,
    component_ref: str | None = None,
    segment_id: str | None = None,
    owner_root_witness: OwnerRootWitness,
) -> OwnerMembershipWitness:
    if not isinstance(owner_root_witness, OwnerRootWitness):
        raise TelemetryAdmissionError("owner_root_witness_required")
    session_dir = _absolute_path(session_dir)
    artifact_path = _absolute_path(artifact_path)
    transaction = _OwnerAdmissionTransaction(owner_root_witness)
    currentness = transaction.start()
    owner_root_witness.assert_session_dir(session_dir, currentness=currentness)
    registry_path = _owner_registry_path_for_session(session_dir)
    session_manifest_path = session_dir / "session.manifest.json"
    owner_manifest_path = (
        session_manifest_path
        if kind == "segment_index"
        else session_dir / "session-index-shards" / "manifest.json"
    )
    files = {
        "registry": _owner_membership_file_spec(
            registry_path,
            error_prefix="owner_registry",
            transaction=transaction,
        ),
        "session_manifest": _owner_membership_file_spec(
            session_manifest_path,
            error_prefix="owner_session_manifest",
            transaction=transaction,
        ),
        "owner_manifest": _owner_membership_file_spec(
            owner_manifest_path,
            error_prefix="owner_owner_manifest",
            transaction=transaction,
        ),
        "artifact": _owner_membership_file_spec(
            artifact_path,
            error_prefix="owner_artifact",
            transaction=transaction,
        ),
    }
    _registry_bytes, registry = _owner_membership_json(
        {"files": files},
        "registry",
        error_prefix="owner_registry",
        transaction=transaction,
    )
    _session_bytes, session_manifest = _owner_membership_json(
        {"files": files},
        "session_manifest",
        error_prefix="owner_session_manifest",
        transaction=transaction,
    )
    session_id = str(session_manifest.get("session_id") or "")
    if not session_id:
        raise TelemetryAdmissionError("owner_session_manifest_session_id_missing")
    _owner_membership_registry_record(
        registry,
        session_manifest=session_manifest,
        session_dir=session_dir,
        session_id=session_id,
    )
    membership: dict[str, Any] = {
        "schema_version": OWNER_MEMBERSHIP_SCHEMA_VERSION,
        "kind": kind,
        "session_dir": str(session_dir),
        "session_id": session_id,
        "owner_root_sha256": owner_root_witness._root_sha256,
        "owner_epoch_sha256": owner_root_witness._epoch_sha256,
        "owner_manifest_sha256": files["owner_manifest"]["sha256"],
        "session_manifest_sha256": files["session_manifest"]["sha256"],
        "artifact_sha256": files["artifact"]["sha256"],
        "files": files,
    }
    if kind == "segment_index":
        _owner_bytes, owner_manifest = _owner_membership_json(
            {"files": files},
            "owner_manifest",
            error_prefix="owner_segment_manifest",
            transaction=transaction,
        )
        entry = _owner_segment_manifest_entry(
            owner_manifest,
            session_dir=session_dir,
            artifact_path=artifact_path,
            segment_id=segment_id,
        )
        membership["segment_id"] = str(entry.get("segment_id") or "")
        receipt = entry.get("artifact_receipts") if isinstance(entry.get("artifact_receipts"), Mapping) else {}
        index_receipt = receipt.get("index") if isinstance(receipt.get("index"), Mapping) else {}
        if f"sha256:{index_receipt.get('sha256')}" != files["artifact"]["sha256"]:
            raise TelemetryAdmissionError("owner_segment_manifest_artifact_digest_mismatch")
    elif kind == "episode_component":
        if not component_ref:
            raise TelemetryAdmissionError("owner_component_ref_missing")
        _owner_bytes, owner_manifest = _owner_membership_json(
            {"files": files},
            "owner_manifest",
            error_prefix="owner_component_manifest",
            transaction=transaction,
        )
        entry = _owner_component_manifest_entry(
            owner_manifest,
            component_ref=component_ref,
            component_path=artifact_path,
            session_dir=session_dir,
        )
        if f"sha256:{entry.get('artifact_sha256')}" != files["artifact"]["sha256"]:
            raise TelemetryAdmissionError("owner_component_manifest_artifact_digest_mismatch")
        membership["component_ref"] = component_ref
    else:
        raise TelemetryAdmissionError("owner_membership_kind_invalid")
    witness = OwnerMembershipWitness(
        membership,
        owner_root_witness=owner_root_witness,
        token=_OWNER_MEMBERSHIP_WITNESS_TOKEN,
    )
    _verify_owner_membership_record_current(
        witness._record,
        owner_root_witness=owner_root_witness,
        currentness=currentness,
        transaction=transaction,
        finalize=False,
    )
    transaction.finalize()
    return witness


def _owner_segment_membership(
    *,
    session_dir: Path,
    index_path: Path,
    owner_root_witness: OwnerRootWitness,
) -> OwnerMembershipWitness:
    return _owner_membership_snapshot(
        kind="segment_index",
        session_dir=session_dir,
        artifact_path=index_path,
        owner_root_witness=owner_root_witness,
    )


def _owner_episode_component_membership(
    *,
    session_dir: Path,
    component_ref: str,
    component_path: Path,
    owner_root_witness: OwnerRootWitness,
) -> OwnerMembershipWitness:
    return _owner_membership_snapshot(
        kind="episode_component",
        session_dir=session_dir,
        artifact_path=component_path,
        component_ref=component_ref,
        owner_root_witness=owner_root_witness,
    )


def _safe_string(value: Any, field: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise TelemetryError(f"{field}_must_be_string")
    if not allow_empty and not value:
        raise TelemetryError(f"{field}_missing")
    if len(value) > MAX_STRING_LENGTH:
        raise TelemetryError(f"{field}_too_long")
    if any(ord(char) < 32 for char in value):
        raise TelemetryError(f"{field}_contains_control_character")
    return value


def _safe_ref(value: Any, field: str) -> str:
    text = _safe_string(value, field)
    if (
        text.startswith(("/", "~"))
        or any(ord(char) > 127 for char in text)
        or not SAFE_REF_RE.fullmatch(text)
        or re.search(r"%(?![0-9A-Fa-f]{2})", text)
    ):
        raise TelemetryError(f"{field}_not_public_safe_ref")
    return text


def public_ref_component(value: Any, field: str = "public_ref_component") -> str:
    """Encode a readable label without putting raw Unicode in a public ref."""

    normalized = unicodedata.normalize("NFC", _safe_string(value, field))
    encoded = "".join(
        chr(byte) if chr(byte) in PUBLIC_REF_COMPONENT_SAFE else f"%{byte:02X}"
        for byte in normalized.encode("utf-8")
    )
    if len(encoded) > MAX_STRING_LENGTH:
        raise TelemetryError(f"{field}_encoded_too_long")
    return encoded


_ALIAS_KEY_UNSET = object()


def _public_session_alias_key(
    explicit: object = _ALIAS_KEY_UNSET,
    *,
    owner_root_witness: OwnerRootWitness | None = None,
) -> Any:
    if explicit is not _ALIAS_KEY_UNSET:
        raise TelemetryError("session_alias_explicit_key_not_owner_controlled")
    if not isinstance(owner_root_witness, OwnerRootWitness):
        raise TelemetryError("session_alias_owner_witness_required")
    return owner_root_witness._alias_digest


def public_session_ref(
    session_label: Any,
    *,
    alias_key: object = _ALIAS_KEY_UNSET,
    owner_root_witness: OwnerRootWitness | None = None,
) -> str:
    """Return an owner-root-keyed public alias without exposing the label."""

    normalized = unicodedata.normalize("NFC", _safe_string(session_label, "session_label"))
    alias_digest = _public_session_alias_key(
        alias_key,
        owner_root_witness=owner_root_witness,
    )
    digest = alias_digest(normalized.encode("utf-8"))
    return _safe_ref(f"session:alias-{digest}", "session_ref")


def _owner_record_digest(record: Mapping[str, Any]) -> str:
    return canonical_sha256(
        {key: value for key, value in record.items() if key != "record_sha256"}
    )


def _issue_owner_source_evidence(
    record: Mapping[str, Any],
    *,
    paths: Mapping[str, Path] | None = None,
    membership: OwnerMembershipWitness | None = None,
) -> OwnerSourceEvidence:
    if paths and not membership:
        raise TelemetryAdmissionError("owner_source_membership_required")
    normalized = copy.deepcopy(dict(record))
    if membership is not None:
        if not isinstance(membership, OwnerMembershipWitness):
            raise TelemetryAdmissionError("owner_source_membership_witness_required")
        normalized.update(membership.public_metadata())
    normalized.setdefault("schema_version", OWNER_SOURCE_EVIDENCE_SCHEMA_VERSION)
    if membership is not None:
        normalized["record_sha256"] = _owner_record_digest(normalized)
    else:
        normalized.setdefault("record_sha256", _owner_record_digest(normalized))
    if normalized["record_sha256"] != _owner_record_digest(normalized):
        raise TelemetryAdmissionError("owner_source_record_digest_mismatch")
    evidence = OwnerSourceEvidence(
        normalized,
        paths=paths,
        membership=membership,
        token=_OWNER_SOURCE_EVIDENCE_TOKEN,
    )
    if paths:
        if not evidence.verify_current():
            raise TelemetryAdmissionError("owner_source_evidence_not_current")
    return evidence


def _attach_owner_source_evidence(
    event: Mapping[str, Any],
    *,
    source_ref: str,
    source_path: Path | None = None,
    owner_membership: OwnerMembershipWitness | None = None,
    owner_root_witness: OwnerRootWitness | None = None,
) -> OwnerCapturedEvent:
    """Attach source-artifact evidence to an event loaded by an owner reader."""

    if not isinstance(event, Mapping):
        raise TelemetryError("owner_event_must_be_object")
    source_ref = _safe_ref(source_ref, "owner_source_record.source_ref")
    event_copy = copy.deepcopy(dict(event))
    facets = event_copy.get("facets") if isinstance(event_copy.get("facets"), Mapping) else {}
    candidate = facets.get("identity_bound_telemetry_receipt")
    event_digest = canonical_sha256(event_copy)
    if source_path is not None:
        if owner_membership is None:
            if not isinstance(owner_root_witness, OwnerRootWitness):
                raise TelemetryAdmissionError("owner_event_source_membership_required")
            try:
                owner_membership = _owner_segment_membership(
                    session_dir=_absolute_path(source_path).parent.parent,
                    index_path=source_path,
                    owner_root_witness=owner_root_witness,
                )
            except (OSError, TelemetryError, TypeError, ValueError) as exc:
                raise TelemetryAdmissionError(
                    "owner_event_source_membership_required"
                ) from exc
        if not isinstance(owner_membership, OwnerMembershipWitness):
            raise TelemetryAdmissionError("owner_event_source_membership_witness_required")
        try:
            _verify_owner_membership_current(owner_membership)
        except (OSError, TelemetryError, TypeError, ValueError) as exc:
            raise TelemetryAdmissionError("owner_event_source_membership_invalid") from exc
        if owner_membership.kind != "segment_index":
            raise TelemetryAdmissionError("owner_event_source_membership_kind_invalid")
        files = owner_membership._record.get("files")
        membership_artifact = files.get("artifact") if isinstance(files, Mapping) else None
        if not isinstance(membership_artifact, Mapping):
            raise TelemetryAdmissionError("owner_event_source_membership_artifact_missing")
        if _absolute_path(source_path) != _absolute_path(Path(str(membership_artifact.get("path") or ""))):
            raise TelemetryAdmissionError("owner_event_source_membership_path_mismatch")
        try:
            artifact_bytes, _identity = _read_regular_file(
                source_path,
                error_prefix="owner_event_source_artifact",
            )
            artifact_digest = f"sha256:{hashlib.sha256(artifact_bytes).hexdigest()}"
        except (OSError, TelemetryError) as exc:
            raise TelemetryError("owner_event_source_artifact_unreadable") from exc
        status = "persistent_artifact"
        paths = {"artifact_sha256": source_path}
    else:
        artifact_digest = event_digest
        status = "process_local"
        paths = None
    facet_digest = canonical_sha256(candidate) if isinstance(candidate, Mapping) else None
    record: dict[str, Any] = {
        "schema_version": OWNER_SOURCE_EVIDENCE_SCHEMA_VERSION,
        "status": status,
        "source_ref": source_ref,
        "artifact_sha256": artifact_digest,
        "event_sha256": event_digest,
        "facet_sha256": facet_digest,
        "receipt_document_sha256": facet_digest,
    }
    if owner_membership is not None:
        if not isinstance(owner_membership, OwnerMembershipWitness):
            raise TelemetryAdmissionError("owner_event_source_membership_witness_required")
        record.update(owner_membership.public_metadata())
    record["record_sha256"] = _owner_record_digest(record)
    owner_source_evidence = _issue_owner_source_evidence(
        record,
        paths=paths,
        membership=owner_membership,
    )
    if source_path is not None and not owner_source_evidence.verify_event(event_copy):
        raise TelemetryAdmissionError("owner_event_source_semantic_mismatch")
    return OwnerCapturedEvent(
        event_copy,
        owner_source_evidence=owner_source_evidence,
    )


def _normalize_owner_source_record(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TelemetryAdmissionError(f"{field}_missing")
    required = {
        "schema_version",
        "status",
        "source_ref",
        "artifact_sha256",
        "event_sha256",
        "facet_sha256",
        "receipt_document_sha256",
        "record_sha256",
    }
    if not required.issubset(set(value)):
        raise TelemetryAdmissionError(f"{field}_shape_invalid")
    if value.get("schema_version") != OWNER_SOURCE_EVIDENCE_SCHEMA_VERSION:
        raise TelemetryAdmissionError(f"{field}_schema_unsupported")
    status = value.get("status")
    if status not in {"persistent_artifact", "process_local"}:
        raise TelemetryAdmissionError(f"{field}_status_invalid")
    normalized: dict[str, Any] = {
        key: copy.deepcopy(value[key])
        for key in value
    }
    _safe_ref(normalized["source_ref"], f"{field}.source_ref")
    for name in ("artifact_sha256", "event_sha256", "record_sha256"):
        if not isinstance(normalized[name], str) or not SHA256_RE.fullmatch(normalized[name]):
            raise TelemetryAdmissionError(f"{field}_{name}_invalid")
    for name in ("facet_sha256", "receipt_document_sha256"):
        if normalized[name] is not None and (
            not isinstance(normalized[name], str) or not SHA256_RE.fullmatch(normalized[name])
        ):
            raise TelemetryAdmissionError(f"{field}_{name}_invalid")
    for name in (
        "manifest_sha256",
        "session_manifest_sha256",
        "component_artifact_sha256",
        "component_payload_sha256",
        "source_raw_sha256",
        "owner_context_sha256",
        "owner_root_sha256",
        "owner_epoch_sha256",
        "membership_witness_sha256",
    ):
        if name in normalized and (
            not isinstance(normalized[name], str) or not SHA256_RE.fullmatch(normalized[name])
        ):
            raise TelemetryAdmissionError(f"{field}_{name}_invalid")
    if "component_ref" in normalized:
        _safe_ref(normalized["component_ref"], f"{field}.component_ref")
    if "source_raw_line_count" in normalized:
        line_count = normalized["source_raw_line_count"]
        if isinstance(line_count, bool) or not isinstance(line_count, int) or line_count < 1:
            raise TelemetryAdmissionError(f"{field}_source_raw_line_count_invalid")
    if "event_range" in normalized:
        event_range = normalized["event_range"]
        if (
            not isinstance(event_range, Mapping)
            or set(event_range) != {"from_line", "to_line"}
            or isinstance(event_range.get("from_line"), bool)
            or isinstance(event_range.get("to_line"), bool)
            or not isinstance(event_range.get("from_line"), int)
            or not isinstance(event_range.get("to_line"), int)
            or event_range["from_line"] < 1
            or event_range["to_line"] < event_range["from_line"]
        ):
            raise TelemetryAdmissionError(f"{field}_event_range_invalid")
    if normalized["record_sha256"] != _owner_record_digest(normalized):
        raise TelemetryAdmissionError(f"{field}_digest_mismatch")
    if status == "persistent_artifact" and not normalized.get("artifact_sha256"):
        raise TelemetryAdmissionError(f"{field}_persistent_artifact_missing")
    return normalized


def _walk_private_keys(value: Any, *, path: str = "receipt") -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            key_text = str(key).casefold()
            if key_text in _PRIVATE_KEYS:
                raise TelemetryError(f"private_field_rejected:{path}.{key_text}")
            _walk_private_keys(nested, path=f"{path}.{key_text}")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, nested in enumerate(value[:MAX_EVIDENCE_REFS]):
            _walk_private_keys(nested, path=f"{path}[{index}]")


def _field(
    state: str,
    value: Any = None,
    *,
    reason: str | None = None,
    source: str | None = None,
    ref: str | None = None,
    unit: str | None = None,
) -> dict[str, Any]:
    if state not in FIELD_STATES:
        raise TelemetryError(f"invalid_field_state:{state}")
    if state == "known" and value is None:
        raise TelemetryError("known_field_value_missing")
    if state != "known" and value is not None:
        raise TelemetryError(f"non_known_field_has_value:{state}")
    result: dict[str, Any] = {"state": state, "value": value}
    if state != "known":
        result["reason"] = _safe_string(reason or f"field_{state}", "field_reason")[:MAX_REASON_LENGTH]
    elif reason:
        result["reason"] = _safe_string(reason, "field_reason")[:MAX_REASON_LENGTH]
    if source:
        result["source"] = _safe_ref(source, "field_source")
    if ref:
        result["ref"] = _safe_ref(ref, "field_ref")
    if unit:
        result["unit"] = _safe_string(unit, "field_unit")
    return result


def known(value: Any, *, source: str, ref: str | None = None, unit: str | None = None) -> dict[str, Any]:
    if isinstance(value, (dict, list, tuple, set)):
        raise TelemetryError("known_field_value_must_be_scalar")
    if isinstance(value, float) and not math.isfinite(value):
        raise TelemetryError("known_field_value_must_be_finite")
    if isinstance(value, str):
        _safe_string(value, "known_field_value")
    if isinstance(value, bool):
        pass
    elif not isinstance(value, (str, int, float)):
        raise TelemetryError("known_field_value_unsupported")
    return _field("known", value, source=source, ref=ref, unit=unit)


def missing(reason: str, *, source: str | None = None) -> dict[str, Any]:
    return _field("missing", reason=reason, source=source)


def unknown(reason: str, *, source: str | None = None) -> dict[str, Any]:
    return _field("unknown", reason=reason, source=source)


def unobservable(reason: str, *, source: str | None = None, unit: str | None = None) -> dict[str, Any]:
    return _field("unobservable", reason=reason, source=source, unit=unit)


def excluded(reason: str, *, source: str | None = None) -> dict[str, Any]:
    return _field("excluded", reason=reason, source=source)


def explicit_null(reason: str, *, source: str | None = None) -> dict[str, Any]:
    return _field("null", reason=reason, source=source)


def _normalize_field(value: Any, field: str, *, unit: str | None = None) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TelemetryError(f"{field}_must_be_typed_field")
    allowed = {"state", "value", "reason", "source", "ref", "unit"}
    unexpected = set(value) - allowed
    if unexpected:
        raise TelemetryError(f"{field}_unexpected_keys:{','.join(sorted(map(str, unexpected)))}")
    state = _safe_string(value.get("state"), f"{field}.state")
    if state not in FIELD_STATES:
        raise TelemetryError(f"{field}_invalid_state:{state}")
    actual_unit = value.get("unit", unit)
    result = _field(
        state,
        value.get("value"),
        reason=value.get("reason"),
        source=value.get("source"),
        ref=value.get("ref"),
        unit=actual_unit,
    )
    if state == "known":
        known(result["value"], source=str(result.get("source") or "owner_receipt"), ref=result.get("ref"), unit=result.get("unit"))
    return result


def _normalize_field_map(
    value: Any,
    fields: Sequence[str],
    prefix: str,
    *,
    missing_reason: str,
) -> dict[str, dict[str, Any]]:
    source = value if isinstance(value, Mapping) else {}
    return {
        name: (
            _normalize_field(source[name], f"{prefix}.{name}")
            if name in source
            else missing(missing_reason)
        )
        for name in fields
    }


def _normalize_metric(value: Any, field: str, unit: str) -> dict[str, Any]:
    result = _normalize_field(value, field, unit=unit)
    if result["state"] == "known":
        metric = result["value"]
        if isinstance(metric, bool) or not isinstance(metric, (int, float)):
            raise TelemetryError(f"{field}_must_be_numeric")
        if not math.isfinite(float(metric)) or float(metric) < 0:
            raise TelemetryError(f"{field}_must_be_nonnegative_finite")
    return result


def _normalize_source(
    value: Any,
    *,
    missing_reason: str,
    allow_context_scalars: bool = False,
) -> dict[str, dict[str, Any]]:
    source = value if isinstance(value, Mapping) else {}
    result: dict[str, dict[str, Any]] = {}
    for name in SOURCE_FIELDS:
        if name not in source:
            result[name] = missing(missing_reason)
            continue
        unit = "bytes" if name == "raw_bytes" else "lines" if name == "raw_line_count" else None
        if allow_context_scalars and source[name] is None:
            result[name] = missing(missing_reason)
        elif allow_context_scalars and not isinstance(source[name], Mapping):
            result[name] = known(source[name], source="session_projection", unit=unit)
        else:
            result[name] = _normalize_field(source[name], f"source.{name}", unit=unit)
        if result[name]["state"] == "known":
            if name == "raw_sha256":
                value_text = str(result[name]["value"])
                if not (HEX_RE.fullmatch(value_text) or SHA256_RE.fullmatch(value_text)):
                    raise TelemetryError("source.raw_sha256_invalid")
                result[name]["value"] = value_text.removeprefix("sha256:")
            elif isinstance(result[name]["value"], bool) or not isinstance(result[name]["value"], int) or result[name]["value"] < 0:
                raise TelemetryError(f"source.{name}_must_be_nonnegative_integer")
    return result


def _normalize_refs(value: Any, field: str = "evidence_refs") -> list[dict[str, str]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise TelemetryError(f"{field}_must_be_list")
    if len(value) > MAX_EVIDENCE_REFS:
        raise TelemetryError(f"{field}_too_many")
    refs: list[dict[str, str]] = []
    for index, entry in enumerate(value):
        if not isinstance(entry, Mapping):
            raise TelemetryError(f"{field}[{index}]_must_be_object")
        if set(entry) - {"kind", "value", "basis"}:
            raise TelemetryError(f"{field}[{index}]_unexpected_keys")
        kind = _safe_string(entry.get("kind"), f"{field}[{index}].kind")
        ref_value = _safe_ref(entry.get("value"), f"{field}[{index}].value")
        item = {"kind": kind, "value": ref_value}
        if entry.get("basis") is not None:
            item["basis"] = _safe_ref(entry.get("basis"), f"{field}[{index}].basis")
        refs.append(item)
    return refs


def _normalize_step(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TelemetryError(f"trajectory.steps.{name}_must_be_object")
    allowed = {"state", "reason", "correlation_id", "timestamp", "outcome", "evidence_refs"}
    if set(value) - allowed:
        raise TelemetryError(f"trajectory.steps.{name}_unexpected_keys")
    state = _safe_string(value.get("state"), f"trajectory.steps.{name}.state")
    if state not in FIELD_STATES:
        raise TelemetryError(f"trajectory.steps.{name}_invalid_state")
    result = {
        "state": state,
        "reason": _safe_string(value.get("reason") or f"step_{state}", f"trajectory.steps.{name}.reason")[:MAX_REASON_LENGTH],
        "correlation_id": _normalize_field(
            value.get("correlation_id", missing("correlation_id_not_provided")),
            f"trajectory.steps.{name}.correlation_id",
        ),
        "timestamp": _normalize_field(
            value.get("timestamp", missing("timestamp_not_provided")),
            f"trajectory.steps.{name}.timestamp",
        ),
        "outcome": _normalize_field(
            value.get("outcome", missing("outcome_not_provided")),
            f"trajectory.steps.{name}.outcome",
        ),
        "evidence_refs": _normalize_refs(value.get("evidence_refs", []), f"trajectory.steps.{name}.evidence_refs"),
    }
    if state == "known":
        if any(result[key]["state"] != "known" for key in ("correlation_id", "timestamp", "outcome")):
            raise TelemetryError(f"trajectory.steps.{name}_known_without_complete_fields")
        if not result["evidence_refs"]:
            raise TelemetryError(f"trajectory.steps.{name}_known_without_evidence_refs")
    return result


def _normalize_trajectory(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TelemetryError("trajectory_must_be_object")
    if set(value) - {"chain_id", "steps"}:
        raise TelemetryError("trajectory_unexpected_keys")
    chain_id = _normalize_field(value.get("chain_id", missing("trajectory_chain_id_not_provided")), "trajectory.chain_id")
    steps_value = value.get("steps") if isinstance(value.get("steps"), Mapping) else {}
    steps = {
        name: _normalize_step(
            steps_value.get(name, {"state": "missing", "reason": "trajectory_step_not_provided"}),
            name,
        )
        for name in STEP_NAMES
    }
    if chain_id["state"] == "known":
        _safe_ref(chain_id["value"], "trajectory.chain_id.value")
    return {"chain_id": chain_id, "steps": steps}


def _normalize_timing(value: Any, *, reason: str) -> dict[str, dict[str, Any]]:
    source = value if isinstance(value, Mapping) else {}
    return {
        name: (
            _normalize_metric(source[name], f"timing.{name}", "seconds")
            if name in source
            else unobservable(reason, unit="seconds")
        )
        for name in TIMING_FIELDS
    }


def _normalize_cache(value: Any, *, reason: str) -> dict[str, Any]:
    source = value if isinstance(value, Mapping) else {}
    return {
        "posture": (
            _normalize_field(source["posture"], "cache.posture")
            if "posture" in source
            else missing(reason)
        ),
        "identity": (
            _normalize_field(source["identity"], "cache.identity")
            if "identity" in source
            else missing(reason)
        ),
        "observed_state": (
            _normalize_field(source["observed_state"], "cache.observed_state")
            if "observed_state" in source
            else unobservable(reason)
        ),
    }


def _normalize_resource(value: Any, *, reason: str) -> dict[str, Any]:
    source = value if isinstance(value, Mapping) else {}
    raw_metrics = source.get("metrics") if isinstance(source.get("metrics"), Mapping) else {}
    return {
        "posture": (
            _normalize_field(source["posture"], "resource.posture")
            if "posture" in source
            else missing(reason)
        ),
        "metrics": {
            name: (
                _normalize_metric(raw_metrics[name], f"resource.metrics.{name}", unit)
                if name in raw_metrics
                else unobservable(reason, unit=unit)
            )
            for name, unit in (
                ("cpu_ms", "milliseconds"),
                ("peak_rss_bytes", "bytes"),
                ("io_read_bytes", "bytes"),
                ("io_write_bytes", "bytes"),
            )
        },
    }


def _normalize_review(value: Any, *, fallback: str = "unknown") -> dict[str, Any]:
    source = value if isinstance(value, Mapping) else {}
    status = str(source.get("status") or fallback)
    if status not in REVIEW_STATES:
        raise TelemetryError(f"review_invalid_status:{status}")
    result: dict[str, Any] = {"status": status}
    if source.get("review_ref") is not None:
        result["review_ref"] = _safe_ref(source["review_ref"], "review.review_ref")
    else:
        result["review_ref"] = None
    if source.get("reason") is not None:
        result["reason"] = _safe_string(source["reason"], "review.reason")[:MAX_REASON_LENGTH]
    return result


def _normalize_producer(value: Any) -> dict[str, str]:
    source = value if isinstance(value, Mapping) else {}
    mode = _safe_string(source.get("mode"), "producer.mode")
    if mode not in {"capture_time_envelope", "post_hoc_projection", "owner_receipt_federation"}:
        raise TelemetryError(f"producer_invalid_mode:{mode}")
    return {
        "owner_repo": _safe_ref(source.get("owner_repo"), "producer.owner_repo"),
        "producer_ref": _safe_ref(source.get("producer_ref"), "producer.producer_ref"),
        "mode": mode,
    }


def _normalize_public_ref_object(value: Any, field: str) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise TelemetryError(f"{field}_must_be_object")
    if set(value) - {"kind", "value", "basis"} or "kind" not in value or "value" not in value:
        raise TelemetryError(f"{field}_shape_invalid")
    result = {
        "kind": _safe_string(value["kind"], f"{field}.kind"),
        "value": _safe_ref(value["value"], f"{field}.value"),
    }
    if value.get("basis") is not None:
        result["basis"] = _safe_ref(value["basis"], f"{field}.basis")
    return result


def _public_source_identity(value: Any, *, field: str) -> dict[str, Any]:
    normalized = _normalize_source(
        value,
        missing_reason=f"{field}_not_provided",
        allow_context_scalars=True,
    )
    result: dict[str, Any] = {}
    for name in SOURCE_FIELDS:
        source_field = normalized[name]
        if _field_state(source_field) != "known":
            raise TelemetryError(f"{field}_{name}_not_known")
        result[name] = _field_value(source_field)
    if result["raw_line_count"] < 1:
        raise TelemetryError(f"{field}_raw_line_count_must_be_positive")
    return result


def _normalize_component_identity(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TelemetryError("episode_binding.component_identity_must_be_object")
    required = {
        "component",
        "artifact_sha256",
        "payload_sha256",
        "task_episode_generation_id",
        "episode_source_sha256",
        "event_range",
        "privacy_policy_version",
        "redaction_policy_version",
    }
    if set(value) != required:
        raise TelemetryError("episode_binding.component_identity_shape_invalid")
    if value.get("component") != "task_episodes":
        raise TelemetryError("episode_binding.component_identity_component_invalid")
    result: dict[str, Any] = {"component": "task_episodes"}
    for name in (
        "artifact_sha256",
        "payload_sha256",
        "task_episode_generation_id",
        "episode_source_sha256",
    ):
        text = _safe_string(value.get(name), f"episode_binding.component_identity.{name}")
        if not HEX_RE.fullmatch(text):
            raise TelemetryError(f"episode_binding.component_identity_{name}_invalid")
        result[name] = text
    component_range = value.get("event_range")
    if not isinstance(component_range, Mapping) or set(component_range) != {"from_line", "to_line"}:
        raise TelemetryError("episode_binding.component_identity_event_range_invalid")
    from_line = component_range.get("from_line")
    to_line = component_range.get("to_line")
    if (
        isinstance(from_line, bool)
        or isinstance(to_line, bool)
        or not isinstance(from_line, int)
        or not isinstance(to_line, int)
        or from_line < 1
        or to_line < from_line
    ):
        raise TelemetryError("episode_binding.component_identity_event_range_invalid")
    result["event_range"] = {"from_line": from_line, "to_line": to_line}
    for name in ("privacy_policy_version", "redaction_policy_version"):
        version = value.get(name)
        if isinstance(version, bool) or not isinstance(version, int) or version < 0:
            raise TelemetryError(f"episode_binding.component_identity_{name}_invalid")
        result[name] = version
    return result


def _normalize_manifest_admission(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TelemetryError("episode_binding.manifest_admission_must_be_object")
    required = {"manifest_ref", "manifest_sha256", "component_ref"}
    if set(value) != required:
        raise TelemetryError("episode_binding.manifest_admission_shape_invalid")
    manifest_ref = _normalize_public_ref_object(
        value.get("manifest_ref"), "episode_binding.manifest_admission.manifest_ref"
    )
    if manifest_ref["kind"] != "task-episode-component-manifest":
        raise TelemetryError("episode_binding.manifest_admission_ref_kind_invalid")
    manifest_sha256 = _safe_string(
        value.get("manifest_sha256"), "episode_binding.manifest_admission.manifest_sha256"
    )
    if not HEX_RE.fullmatch(manifest_sha256):
        raise TelemetryError("episode_binding.manifest_admission_manifest_digest_invalid")
    component_ref = _safe_string(
        value.get("component_ref"), "episode_binding.manifest_admission.component_ref"
    )
    component_parts = component_ref.split("/")
    if (
        component_ref.startswith(("/", "~"))
        or "\\" in component_ref
        or ".." in component_parts
        or not component_ref.startswith("session-index-shards/task-episodes/")
        or not component_ref.endswith(".json")
        or not SAFE_REF_RE.fullmatch(component_ref)
    ):
        raise TelemetryError("episode_binding.manifest_admission_component_ref_invalid")
    return {
        "manifest_ref": manifest_ref,
        "manifest_sha256": manifest_sha256,
        "component_ref": component_ref,
    }


def _owner_validation_marker() -> dict[str, str]:
    return {
        "profile": OWNER_VALIDATION_PROFILE,
        "status": "validated",
        "validator": OWNER_VALIDATION_REF,
        "ordered_range": "checked",
    }


def _episode_binding_core(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: copy.deepcopy(value[key])
        for key in (
            "episode_id",
            "episode_ref",
            "episode_component_ref",
            "session_id",
            "session_ref",
            "source",
            "component_identity",
            "manifest_admission",
            "event_range",
            "binding_status",
            "owner_validation",
        )
        if key in value
    }


def _build_episode_admission_witness(binding: Mapping[str, Any]) -> dict[str, Any]:
    """Build a portable, non-circular digest chain for strict episode admission."""

    core = _episode_binding_core(binding)
    component_identity = core["component_identity"]
    manifest_admission = core["manifest_admission"]
    source = core["source"]
    witness: dict[str, Any] = {
        "schema_version": EPISODE_WITNESS_SCHEMA_VERSION,
        "issuer": "aoa-session-memory",
        "manifest_sha256": manifest_admission["manifest_sha256"],
        "component_ref": manifest_admission["component_ref"],
        "component_artifact_sha256": component_identity["artifact_sha256"],
        "component_payload_sha256": component_identity["payload_sha256"],
        "task_episode_generation_id": component_identity["task_episode_generation_id"],
        "episode_source_sha256": component_identity["episode_source_sha256"],
        "source_raw_sha256": source["raw_sha256"],
        "source_raw_line_count": source["raw_line_count"],
        "event_range": copy.deepcopy(core["event_range"]),
        "binding_sha256": canonical_sha256(core).removeprefix("sha256:"),
    }
    witness["witness_sha256"] = canonical_sha256(witness).removeprefix("sha256:")
    return witness


def _normalize_episode_admission_witness(
    value: Any,
    *,
    binding_core: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TelemetryError("episode_binding_portable_witness_missing")
    required = {
        "schema_version",
        "issuer",
        "manifest_sha256",
        "component_ref",
        "component_artifact_sha256",
        "component_payload_sha256",
        "task_episode_generation_id",
        "episode_source_sha256",
        "source_raw_sha256",
        "source_raw_line_count",
        "event_range",
        "binding_sha256",
        "witness_sha256",
    }
    if set(value) != required:
        raise TelemetryError("episode_binding_portable_witness_shape_invalid")
    if value.get("schema_version") != EPISODE_WITNESS_SCHEMA_VERSION:
        raise TelemetryError("episode_binding_portable_witness_schema_unsupported")
    if value.get("issuer") != "aoa-session-memory":
        raise TelemetryError("episode_binding_portable_witness_issuer_invalid")
    for name in (
        "manifest_sha256",
        "component_artifact_sha256",
        "component_payload_sha256",
        "task_episode_generation_id",
        "episode_source_sha256",
        "source_raw_sha256",
        "binding_sha256",
        "witness_sha256",
    ):
        text = _safe_string(value.get(name), f"episode_binding.portable_witness.{name}")
        if not HEX_RE.fullmatch(text):
            raise TelemetryError(f"episode_binding_portable_witness_{name}_invalid")
    component_ref = _safe_string(value.get("component_ref"), "episode_binding.portable_witness.component_ref")
    if (
        not component_ref.startswith("session-index-shards/task-episodes/")
        or not component_ref.endswith(".json")
        or not SAFE_REF_RE.fullmatch(component_ref)
    ):
        raise TelemetryError("episode_binding_portable_witness_component_ref_invalid")
    source_raw_line_count = value.get("source_raw_line_count")
    if (
        isinstance(source_raw_line_count, bool)
        or not isinstance(source_raw_line_count, int)
        or source_raw_line_count < 1
    ):
        raise TelemetryError("episode_binding_portable_witness_source_line_count_invalid")
    event_range = value.get("event_range")
    if not isinstance(event_range, Mapping) or set(event_range) != {"from_line", "to_line"}:
        raise TelemetryError("episode_binding_portable_witness_event_range_invalid")
    from_line = event_range.get("from_line")
    to_line = event_range.get("to_line")
    if (
        isinstance(from_line, bool)
        or isinstance(to_line, bool)
        or not isinstance(from_line, int)
        or not isinstance(to_line, int)
        or from_line < 1
        or to_line < from_line
    ):
        raise TelemetryError("episode_binding_portable_witness_event_range_invalid")
    normalized = {
        "schema_version": EPISODE_WITNESS_SCHEMA_VERSION,
        "issuer": "aoa-session-memory",
        "manifest_sha256": value["manifest_sha256"],
        "component_ref": component_ref,
        "component_artifact_sha256": value["component_artifact_sha256"],
        "component_payload_sha256": value["component_payload_sha256"],
        "task_episode_generation_id": value["task_episode_generation_id"],
        "episode_source_sha256": value["episode_source_sha256"],
        "source_raw_sha256": value["source_raw_sha256"],
        "source_raw_line_count": source_raw_line_count,
        "event_range": {"from_line": from_line, "to_line": to_line},
        "binding_sha256": value["binding_sha256"],
        "witness_sha256": value["witness_sha256"],
    }
    if normalized["binding_sha256"] != canonical_sha256(binding_core).removeprefix("sha256:"):
        raise TelemetryAdmissionError("episode_binding_portable_witness_binding_mismatch")
    expected = _build_episode_admission_witness(binding_core)
    if normalized != expected:
        raise TelemetryAdmissionError("episode_binding_portable_witness_chain_mismatch")
    component_identity = binding_core["component_identity"]
    manifest_admission = binding_core["manifest_admission"]
    source = binding_core["source"]
    if normalized["manifest_sha256"] != manifest_admission["manifest_sha256"]:
        raise TelemetryAdmissionError("episode_binding_portable_witness_manifest_mismatch")
    if normalized["component_ref"] != manifest_admission["component_ref"]:
        raise TelemetryAdmissionError("episode_binding_portable_witness_component_mismatch")
    if normalized["component_artifact_sha256"] != component_identity["artifact_sha256"]:
        raise TelemetryAdmissionError("episode_binding_portable_witness_artifact_mismatch")
    if normalized["component_payload_sha256"] != component_identity["payload_sha256"]:
        raise TelemetryAdmissionError("episode_binding_portable_witness_payload_mismatch")
    if normalized["task_episode_generation_id"] != component_identity["task_episode_generation_id"]:
        raise TelemetryAdmissionError("episode_binding_portable_witness_generation_mismatch")
    if normalized["episode_source_sha256"] != component_identity["episode_source_sha256"]:
        raise TelemetryAdmissionError("episode_binding_portable_witness_source_digest_mismatch")
    if normalized["source_raw_sha256"] != source["raw_sha256"]:
        raise TelemetryAdmissionError("episode_binding_portable_witness_raw_digest_mismatch")
    if normalized["source_raw_line_count"] != source["raw_line_count"]:
        raise TelemetryAdmissionError("episode_binding_portable_witness_raw_line_count_mismatch")
    if normalized["event_range"] != binding_core["event_range"]:
        raise TelemetryAdmissionError("episode_binding_portable_witness_range_mismatch")
    return normalized


def _normalize_episode_binding(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TelemetryError("episode_binding_must_be_object")
    allowed = {
        "episode_id",
        "episode_ref",
        "episode_component_ref",
        "session_id",
        "session_ref",
        "source",
        "component_identity",
        "manifest_admission",
        "event_range",
        "binding_status",
        "owner_validation",
        "portable_witness",
    }
    if set(value) != allowed:
        missing_keys = sorted(allowed - set(value))
        unexpected = sorted(set(value) - allowed)
        detail: list[str] = []
        if missing_keys:
            detail.append(f"missing={','.join(missing_keys)}")
        if unexpected:
            detail.append(f"unexpected={','.join(unexpected)}")
        raise TelemetryError(
            "episode_binding_shape_invalid:" + ";".join(detail)
        )
    episode_id = _safe_ref(value.get("episode_id"), "episode_binding.episode_id")
    if episode_id == "unknown":
        raise TelemetryError("episode_binding_episode_id_unresolved")
    episode_ref = _normalize_public_ref_object(value.get("episode_ref"), "episode_binding.episode_ref")
    episode_component_ref = _normalize_public_ref_object(
        value.get("episode_component_ref"), "episode_binding.episode_component_ref"
    )
    session_id = _safe_ref(value.get("session_id"), "episode_binding.session_id")
    session_ref = _safe_ref(value.get("session_ref"), "episode_binding.session_ref")
    if episode_ref["kind"] != "task-episode":
        raise TelemetryError("episode_binding_episode_ref_kind_invalid")
    if episode_ref["value"] != f"{session_ref}#task-episode:{episode_id}":
        raise TelemetryError("episode_binding_episode_ref_mismatch")
    if episode_component_ref["kind"] != "task-episode-component":
        raise TelemetryError("episode_binding_component_ref_kind_invalid")
    source = _public_source_identity(value.get("source"), field="episode_binding.source")
    component_identity = _normalize_component_identity(value.get("component_identity"))
    manifest_admission = _normalize_manifest_admission(value.get("manifest_admission"))

    event_range = value.get("event_range")
    if not isinstance(event_range, Mapping) or set(event_range) != {"from_line", "to_line"}:
        raise TelemetryError("episode_binding.event_range_invalid")
    from_line = event_range.get("from_line")
    to_line = event_range.get("to_line")
    if (
        isinstance(from_line, bool)
        or isinstance(to_line, bool)
        or not isinstance(from_line, int)
        or not isinstance(to_line, int)
        or from_line < 1
        or to_line < from_line
    ):
        raise TelemetryError("episode_binding.event_range_invalid")
    if value.get("binding_status") != "exact_episode_range":
        raise TelemetryError("episode_binding_status_must_be_exact_episode_range")
    owner_validation = value.get("owner_validation")
    if owner_validation != _owner_validation_marker():
        raise TelemetryError("episode_binding_owner_validator_admission_missing")
    if component_identity["event_range"] != {"from_line": from_line, "to_line": to_line}:
        raise TelemetryError("episode_binding_component_range_mismatch")
    if to_line > source["raw_line_count"]:
        raise TelemetryError("episode_binding_event_range_out_of_source")
    expected_episode_ref = f"{session_ref}#task-episode:{episode_id}"
    if episode_ref["value"] != expected_episode_ref:
        raise TelemetryError("episode_binding_episode_ref_mismatch")
    expected_component_ref = (
        f"{session_ref}#component:{public_ref_component(manifest_admission['component_ref'], 'episode_component_ref')}"
    )
    if episode_component_ref["value"] != expected_component_ref:
        raise TelemetryError("episode_binding_component_ref_mismatch")
    expected_manifest_ref = f"{session_ref}#session-index-shards/manifest.json"
    if manifest_admission["manifest_ref"]["value"] != expected_manifest_ref:
        raise TelemetryError("episode_binding_manifest_ref_mismatch")
    core = {
        "episode_id": episode_id,
        "episode_ref": episode_ref,
        "episode_component_ref": episode_component_ref,
        "session_id": session_id,
        "session_ref": session_ref,
        "source": source,
        "component_identity": component_identity,
        "manifest_admission": manifest_admission,
        "event_range": {"from_line": from_line, "to_line": to_line},
        "binding_status": "exact_episode_range",
        "owner_validation": _owner_validation_marker(),
    }
    portable_witness = _normalize_episode_admission_witness(
        value.get("portable_witness"),
        binding_core=core,
    )
    return {
        "episode_id": episode_id,
        "episode_ref": episode_ref,
        "episode_component_ref": episode_component_ref,
        "session_id": session_id,
        "session_ref": session_ref,
        "source": source,
        "component_identity": component_identity,
        "manifest_admission": manifest_admission,
        "event_range": {"from_line": from_line, "to_line": to_line},
        "binding_status": "exact_episode_range",
        "owner_validation": _owner_validation_marker(),
        "portable_witness": portable_witness,
    }


def validate_episode_binding(
    value: Mapping[str, Any],
    *,
    expected_context: Mapping[str, Any] | None = None,
    component_admission: EpisodeComponentAdmission | None = None,
    require_owner_admission: bool = True,
) -> dict[str, Any]:
    """Validate an episode coordinate through the current owner admission witness."""

    normalized = _normalize_episode_binding(value)
    if component_admission is not None:
        if not isinstance(component_admission, EpisodeComponentAdmission):
            raise TelemetryAdmissionError("episode_component_admission_witness_invalid")
        if not component_admission.verify_current():
            raise TelemetryAdmissionError("episode_component_owner_source_not_current")
        if normalized != component_admission.public_binding():
            raise TelemetryAdmissionError("episode_component_manifest_join_mismatch")
    else:
        # ``require_owner_admission`` remains for compatibility with older
        # callers; it can never downgrade this strict validator to a
        # shape-only or self-minted admission path.
        raise TelemetryAdmissionError("episode_component_admission_required")
    expected = expected_context or {}
    if expected:
        expected_session_id = _safe_ref(expected.get("session_id"), "expected_context.session_id")
        expected_session_ref = _safe_ref(expected.get("session_ref"), "expected_context.session_ref")
        if normalized["session_id"] != expected_session_id:
            raise TelemetryAdmissionError("episode_binding_session_id_mismatch")
        if normalized["session_ref"] != expected_session_ref:
            raise TelemetryAdmissionError("episode_binding_session_ref_mismatch")
        expected_source = _public_source_identity(
            expected.get("source"), field="expected_context.source"
        )
        if normalized["source"] != expected_source:
            raise TelemetryAdmissionError("episode_binding_source_identity_mismatch")
        for name in ("episode_id", "episode_ref", "episode_component_ref", "component_identity", "event_range"):
            if name in expected and normalized[name] != expected[name]:
                raise TelemetryAdmissionError(f"episode_binding_{name}_mismatch")
        expected_episode_prefix = f"{expected_session_ref}#task-episode:"
        if not normalized["episode_ref"]["value"].startswith(expected_episode_prefix):
            raise TelemetryAdmissionError("episode_binding_episode_ref_foreign")
        expected_component_prefix = f"{expected_session_ref}#component:"
        if not normalized["episode_component_ref"]["value"].startswith(expected_component_prefix):
            raise TelemetryAdmissionError("episode_binding_component_ref_foreign")
    return normalized


def _decode_owner_json_object(data: bytes, error: str) -> dict[str, Any]:
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TelemetryAdmissionError(error) from exc
    if not isinstance(value, dict):
        raise TelemetryAdmissionError(error)
    return value


def _validate_episode_component_artifacts(
    *,
    session_id: str,
    manifest_path: Path,
    component_path: Path,
    session_manifest_path: Path,
    episode_id: str,
    component_ref: str,
    manifest_sha256: str,
    artifact_sha256: str,
    payload_sha256: str,
    source: Mapping[str, Any],
    component_identity: Mapping[str, Any],
    expected_projection: Mapping[str, Any],
    expected_task_episode_generation: str,
    expected_generation_context: Mapping[str, Any] | None = None,
    source_evidence: OwnerSourceEvidence | None = None,
) -> dict[str, Any]:
    """Re-read and semantically validate one current owner component."""

    session_manifest_path = _absolute_path(session_manifest_path)
    manifest_path = _absolute_path(manifest_path)
    component_path = _absolute_path(component_path)
    expected_manifest_path = _absolute_path(
        session_manifest_path.parent / "session-index-shards" / "manifest.json"
    )
    expected_component_path = _absolute_path(session_manifest_path.parent / component_ref)
    if manifest_path != expected_manifest_path:
        raise TelemetryAdmissionError("episode_component_manifest_path_membership_mismatch")
    if component_path != expected_component_path:
        raise TelemetryAdmissionError("episode_component_path_membership_mismatch")
    if not isinstance(expected_projection, Mapping) or not expected_projection:
        raise TelemetryAdmissionError("episode_component_owner_projection_context_missing")
    required_generation_context = {
        "task_episode_generation",
        "segment_generation",
        "session_generation",
    }
    if (
        not isinstance(expected_generation_context, Mapping)
        or not required_generation_context.issubset(expected_generation_context)
    ):
        raise TelemetryAdmissionError("episode_component_owner_generation_context_missing")
    if not HEX_RE.fullmatch(str(expected_task_episode_generation)):
        raise TelemetryAdmissionError("episode_component_owner_generation_context_invalid")
    try:
        _safe_ref(component_ref, "component_admission.component_ref")
    except TelemetryError as exc:
        raise TelemetryAdmissionError("episode_component_component_ref_invalid") from exc

    try:
        if source_evidence is None:
            manifest_bytes, _manifest_identity = _read_regular_file(
                manifest_path,
                error_prefix="episode_component_manifest",
            )
            component_bytes, _component_identity = _read_regular_file(
                component_path,
                error_prefix="episode_component_artifact",
            )
            session_manifest_bytes, _session_manifest_identity = _read_regular_file(
                session_manifest_path,
                error_prefix="episode_component_session_manifest",
            )
        else:
            manifest_bytes = source_evidence._read_current("manifest_sha256")
            component_bytes = source_evidence._read_current("component_artifact_sha256")
            session_manifest_bytes = source_evidence._read_current("session_manifest_sha256")
    except (OSError, TelemetryError) as exc:
        raise TelemetryAdmissionError("episode_component_owner_source_unreadable") from exc
    if hashlib.sha256(manifest_bytes).hexdigest() != manifest_sha256:
        raise TelemetryAdmissionError("episode_component_manifest_digest_mismatch")
    if hashlib.sha256(component_bytes).hexdigest() != artifact_sha256:
        raise TelemetryAdmissionError("episode_component_artifact_digest_mismatch")

    normalized_source = _public_source_identity(source, field="component_admission.source")
    normalized_component_identity = _normalize_component_identity(
        {
            "component": "task_episodes",
            "artifact_sha256": artifact_sha256,
            "payload_sha256": payload_sha256,
            **dict(component_identity),
        }
    )
    if normalized_component_identity["task_episode_generation_id"] != expected_task_episode_generation:
        raise TelemetryAdmissionError("episode_component_owner_generation_mismatch")

    manifest = _decode_owner_json_object(manifest_bytes, "episode_component_manifest_unreadable")
    component = _decode_owner_json_object(component_bytes, "episode_component_unreadable")
    session_manifest = _decode_owner_json_object(
        session_manifest_bytes,
        "episode_session_manifest_unreadable",
    )
    session_manifest_sha256 = hashlib.sha256(session_manifest_bytes).hexdigest()
    if str(session_manifest.get("session_id") or "") != str(session_id):
        raise TelemetryAdmissionError("episode_component_session_identity_mismatch")
    session_raw = session_manifest.get("raw") if isinstance(session_manifest.get("raw"), Mapping) else {}
    for name, session_name in (("raw_sha256", "sha256"), ("raw_bytes", "bytes"), ("raw_line_count", "line_count")):
        if session_raw.get(session_name) != normalized_source[name]:
            raise TelemetryAdmissionError(f"episode_component_session_source_mismatch:{name}")

    if manifest.get("projection_publish") != dict(expected_projection):
        raise TelemetryAdmissionError("episode_component_projection_context_mismatch")
    generation_context = dict(expected_generation_context or {})
    for name in ("task_episode_generation", "segment_generation", "session_generation"):
        if name in generation_context and not HEX_RE.fullmatch(str(generation_context[name])):
            raise TelemetryAdmissionError("episode_component_owner_generation_context_invalid")
    if generation_context.get("task_episode_generation") not in (None, expected_task_episode_generation):
        raise TelemetryAdmissionError("episode_component_owner_generation_context_mismatch")
    if generation_context:
        session_index_schema = session_manifest.get("index_schema")
        if not isinstance(session_index_schema, Mapping):
            raise TelemetryAdmissionError("episode_component_session_generation_context_missing")
        if session_index_schema.get("projection_publish") != dict(expected_projection):
            raise TelemetryAdmissionError("episode_component_session_projection_context_mismatch")
        for name, manifest_name in (
            ("session_generation", "session_index_generation_id"),
            ("segment_generation", "segment_index_generation_id"),
        ):
            if name in generation_context and session_index_schema.get(manifest_name) != generation_context[name]:
                raise TelemetryAdmissionError("episode_component_session_generation_context_mismatch")
    manifest_source = manifest.get("source_identity")
    if not isinstance(manifest_source, Mapping):
        raise TelemetryAdmissionError("episode_component_source_identity_missing")
    for name in ("raw_sha256", "raw_bytes", "raw_line_count"):
        if manifest_source.get(name) != normalized_source[name]:
            raise TelemetryAdmissionError(f"episode_component_source_identity_mismatch:{name}")
    if str(manifest_source.get("task_episode_generation_id") or "") != expected_task_episode_generation:
        raise TelemetryAdmissionError("episode_component_generation_mismatch")

    components = manifest.get("components") if isinstance(manifest.get("components"), Mapping) else {}
    refs = components.get("task_episodes") if isinstance(components.get("task_episodes"), list) else []
    counts = manifest.get("component_counts") if isinstance(manifest.get("component_counts"), Mapping) else {}
    order = manifest.get("component_order") if isinstance(manifest.get("component_order"), Mapping) else {}
    if counts.get("task_episodes") != len(refs):
        raise TelemetryAdmissionError("episode_component_count_mismatch")
    declared_order = order.get("task_episodes")
    if (
        not isinstance(declared_order, list)
        or len(declared_order) != len(refs)
        or len(set(declared_order)) != len(declared_order)
        or [str(item.get("ref") or "") for item in refs if isinstance(item, Mapping)] != declared_order
    ):
        raise TelemetryAdmissionError("episode_component_order_mismatch")
    matching_entries = [entry for entry in refs if isinstance(entry, Mapping) and entry.get("ref") == component_ref]
    if len(matching_entries) != 1:
        raise TelemetryAdmissionError("episode_component_manifest_membership_missing")
    entry = matching_entries[0]
    if entry.get("artifact_sha256") != artifact_sha256:
        raise TelemetryAdmissionError("episode_component_manifest_artifact_mismatch")
    if entry.get("payload_sha256") != payload_sha256:
        raise TelemetryAdmissionError("episode_component_manifest_payload_mismatch")
    if component.get("component") != "task_episodes":
        raise TelemetryAdmissionError("episode_component_kind_mismatch")
    payload = component.get("payload")
    if not isinstance(payload, Mapping) or not payload:
        raise TelemetryAdmissionError("episode_component_payload_missing")
    if str(payload.get("episode_id") or "") != str(episode_id):
        raise TelemetryAdmissionError("episode_component_episode_id_mismatch")
    if _canonical_component_payload_sha256(payload) != payload_sha256:
        raise TelemetryAdmissionError("episode_component_payload_digest_mismatch")
    if component.get("payload_sha256") != payload_sha256:
        raise TelemetryAdmissionError("episode_component_envelope_payload_digest_mismatch")
    if normalized_component_identity["episode_source_sha256"] != canonical_episode_source_sha256(payload):
        raise TelemetryAdmissionError("episode_component_source_digest_mismatch")
    component_range = normalized_component_identity["event_range"]
    if component_range["to_line"] > normalized_source["raw_line_count"]:
        raise TelemetryAdmissionError("episode_component_range_out_of_source")
    actual_component_identity = component.get("source_identity")
    if not isinstance(actual_component_identity, Mapping):
        raise TelemetryAdmissionError("episode_component_identity_missing")
    for name in (
        "task_episode_generation_id",
        "episode_source_sha256",
        "event_range",
        "privacy_policy_version",
        "redaction_policy_version",
    ):
        if actual_component_identity.get(name) != normalized_component_identity.get(name):
            raise TelemetryAdmissionError(f"episode_component_identity_mismatch:{name}")
    if entry.get("component_key") != component.get("component_key"):
        raise TelemetryAdmissionError("episode_component_key_mismatch")
    return {
        "manifest": manifest,
        "component": component,
        "payload": dict(payload),
        "source": normalized_source,
        "component_identity": normalized_component_identity,
        "session_manifest_sha256": session_manifest_sha256,
    }


def _issue_episode_component_admission(
    *,
    session_id: str,
    session_ref: str,
    episode_id: str,
    component_ref: str,
    manifest_sha256: str,
    source: Mapping[str, Any],
    component_identity: Mapping[str, Any],
    artifact_sha256: str,
    payload_sha256: str,
    manifest_path: Path | None = None,
    component_path: Path | None = None,
    session_manifest_path: Path | None = None,
    expected_projection: Mapping[str, Any] | None = None,
    expected_task_episode_generation: str | None = None,
    expected_generation_context: Mapping[str, Any] | None = None,
    owner_membership: OwnerMembershipWitness | None = None,
) -> EpisodeComponentAdmission:
    """Issue a strict witness only through current owner artifacts."""

    if manifest_path is None or component_path is None or session_manifest_path is None:
        raise TelemetryAdmissionError("episode_component_owner_artifacts_required")
    if expected_projection is None or expected_task_episode_generation is None:
        raise TelemetryAdmissionError("episode_component_owner_context_required")
    if owner_membership is None:
        raise TelemetryAdmissionError("episode_component_owner_membership_required")
    if not isinstance(owner_membership, OwnerMembershipWitness):
        raise TelemetryAdmissionError("episode_component_owner_membership_witness_required")
    if owner_membership.kind != "episode_component":
        raise TelemetryAdmissionError("episode_component_owner_membership_kind_invalid")
    try:
        _verify_owner_membership_current(owner_membership)
    except (OSError, TelemetryError, TypeError, ValueError) as exc:
        raise TelemetryAdmissionError("episode_component_owner_membership_invalid") from exc
    files = owner_membership._record.get("files")
    membership_artifact = files.get("artifact") if isinstance(files, Mapping) else None
    if not isinstance(membership_artifact, Mapping):
        raise TelemetryAdmissionError("episode_component_owner_membership_artifact_missing")
    if component_path is None or _absolute_path(component_path) != _absolute_path(
        Path(str(membership_artifact.get("path") or ""))
    ):
        raise TelemetryAdmissionError("episode_component_owner_membership_path_mismatch")
    if (
        not isinstance(expected_generation_context, Mapping)
        or not {
            "task_episode_generation",
            "segment_generation",
            "session_generation",
        }.issubset(expected_generation_context)
    ):
        raise TelemetryAdmissionError("episode_component_owner_generation_context_required")

    encoded_episode_id = public_ref_component(episode_id, "episode_id")
    normalized_source = _public_source_identity(source, field="component_admission.source")
    normalized_component_identity = _normalize_component_identity(
        {
            "component": "task_episodes",
            "artifact_sha256": artifact_sha256,
            "payload_sha256": payload_sha256,
            **dict(component_identity),
        }
    )
    artifacts = _validate_episode_component_artifacts(
        session_id=session_id,
        manifest_path=manifest_path,
        component_path=component_path,
        session_manifest_path=session_manifest_path,
        episode_id=episode_id,
        component_ref=component_ref,
        manifest_sha256=manifest_sha256,
        artifact_sha256=artifact_sha256,
        payload_sha256=payload_sha256,
        source=normalized_source,
        component_identity=normalized_component_identity,
        expected_projection=expected_projection,
        expected_task_episode_generation=expected_task_episode_generation,
        expected_generation_context=expected_generation_context,
    )
    normalized_source = artifacts["source"]
    normalized_component_identity = artifacts["component_identity"]
    binding = {
        "episode_id": encoded_episode_id,
        "episode_ref": {
            "kind": "task-episode",
            "value": f"{session_ref}#task-episode:{encoded_episode_id}",
            "basis": "generated-task-episode-index",
        },
        "episode_component_ref": {
            "kind": "task-episode-component",
            "value": f"{session_ref}#component:{public_ref_component(component_ref, 'episode_component_ref')}",
            "basis": "generated-task-episode-component-manifest",
        },
        "session_id": session_id,
        "session_ref": session_ref,
        "source": normalized_source,
        "component_identity": normalized_component_identity,
        "manifest_admission": {
            "manifest_ref": {
                "kind": "task-episode-component-manifest",
                "value": f"{session_ref}#session-index-shards/manifest.json",
                "basis": "generated-task-episode-component-manifest",
            },
            "manifest_sha256": manifest_sha256,
            "component_ref": component_ref,
        },
        "event_range": dict(normalized_component_identity["event_range"]),
        "binding_status": "exact_episode_range",
        "owner_validation": _owner_validation_marker(),
    }
    owner_record: dict[str, Any] = {
        "schema_version": OWNER_SOURCE_EVIDENCE_SCHEMA_VERSION,
        "status": "persistent_artifact",
        "source_ref": _safe_ref(
            f"owner:episode-component:{component_ref}",
            "owner_source_record.source_ref",
        ),
        "artifact_sha256": f"sha256:{artifact_sha256}",
        "event_sha256": canonical_sha256(
            {
                "component_ref": component_ref,
                "event_range": binding["event_range"],
                "source": normalized_source,
            }
        ),
        "facet_sha256": None,
        "receipt_document_sha256": None,
        "manifest_sha256": f"sha256:{manifest_sha256}",
        "session_manifest_sha256": f"sha256:{artifacts['session_manifest_sha256']}",
        "component_ref": component_ref,
        "component_artifact_sha256": f"sha256:{artifact_sha256}",
        "component_payload_sha256": f"sha256:{payload_sha256}",
        "source_raw_sha256": f"sha256:{normalized_source['raw_sha256']}",
        "source_raw_line_count": normalized_source["raw_line_count"],
        "event_range": copy.deepcopy(binding["event_range"]),
    }
    owner_context = {
        "session_id": str(session_id),
        "session_ref": str(session_ref),
        "episode_id": str(episode_id),
        "component_ref": str(component_ref),
        "source": copy.deepcopy(normalized_source),
        "component_identity": copy.deepcopy(normalized_component_identity),
        "expected_projection": copy.deepcopy(dict(expected_projection)),
        "expected_task_episode_generation": str(expected_task_episode_generation),
        "expected_generation_context": copy.deepcopy(dict(expected_generation_context or {})),
    }
    owner_record["owner_context_sha256"] = canonical_sha256(owner_context)
    paths = {
        "manifest_sha256": manifest_path,
        "component_artifact_sha256": component_path,
        "session_manifest_sha256": session_manifest_path,
    }
    owner_record["record_sha256"] = _owner_record_digest(owner_record)
    owner_source_evidence = _issue_owner_source_evidence(
        owner_record,
        paths=paths,
        membership=owner_membership,
    )
    binding["portable_witness"] = _build_episode_admission_witness(binding)
    normalized = _normalize_episode_binding(binding)
    return EpisodeComponentAdmission(
        normalized,
        owner_source_evidence=owner_source_evidence,
        validation_context={
            **owner_context,
            "manifest_sha256": str(manifest_sha256),
            "artifact_sha256": str(artifact_sha256),
            "payload_sha256": str(payload_sha256),
        },
        token=_EPISODE_COMPONENT_ADMISSION_TOKEN,
    )


def _normalize_receipt_shape(receipt: Any, *, verify_id: bool) -> dict[str, Any]:
    if not isinstance(receipt, Mapping):
        raise TelemetryError("owner_receipt_must_be_object")
    _walk_private_keys(receipt)
    required = {
        "schema_version",
        "artifact_type",
        "receipt_id",
        "producer",
        "binding",
        "identity",
        "trajectory",
        "timing",
        "cache",
        "resource",
        "review",
        "evidence_refs",
        "claim_ceiling",
    }
    if set(receipt) != required:
        missing_keys = sorted(required - set(receipt))
        unexpected = sorted(set(receipt) - required)
        detail = []
        if missing_keys:
            detail.append(f"missing={','.join(missing_keys)}")
        if unexpected:
            detail.append(f"unexpected={','.join(unexpected)}")
        raise TelemetryError("owner_receipt_shape_invalid:" + ";".join(detail))
    if receipt.get("schema_version") != OWNER_RECEIPT_SCHEMA_VERSION:
        raise TelemetryError("owner_receipt_schema_unsupported")
    if receipt.get("artifact_type") != OWNER_RECEIPT_ARTIFACT:
        raise TelemetryError("owner_receipt_artifact_type_invalid")
    receipt_id = _safe_string(receipt.get("receipt_id"), "receipt_id")
    if not SHA256_RE.fullmatch(receipt_id):
        raise TelemetryError("receipt_id_invalid")
    producer = _normalize_producer(receipt.get("producer"))
    binding_raw = receipt.get("binding")
    if not isinstance(binding_raw, Mapping):
        raise TelemetryError("binding_must_be_object")
    if set(binding_raw) != {"session_id", "session_ref", "correlation_id", "source", "projection"}:
        raise TelemetryError("binding_shape_invalid")
    binding = {
        "session_id": _normalize_field(binding_raw["session_id"], "binding.session_id"),
        "session_ref": _normalize_field(binding_raw["session_ref"], "binding.session_ref"),
        "correlation_id": _normalize_field(binding_raw["correlation_id"], "binding.correlation_id"),
        "source": _normalize_source(binding_raw["source"], missing_reason="source_identity_not_provided"),
        "projection": {
            "prefix_identity": _normalize_field(
                (binding_raw["projection"] or {}).get("prefix_identity", missing("projection_identity_not_provided"))
                if isinstance(binding_raw["projection"], Mapping)
                else missing("projection_identity_not_provided"),
                "binding.projection.prefix_identity",
            ),
            "publish_id": _normalize_field(
                (binding_raw["projection"] or {}).get("publish_id", missing("projection_publish_not_provided"))
                if isinstance(binding_raw["projection"], Mapping)
                else missing("projection_publish_not_provided"),
                "binding.projection.publish_id",
            ),
        },
    }
    if binding["session_id"]["state"] != "known" or binding["session_ref"]["state"] != "known" or binding["correlation_id"]["state"] != "known":
        raise TelemetryError("binding_session_correlation_must_be_known")
    _safe_ref(binding["session_id"]["value"], "binding.session_id.value")
    _safe_ref(binding["session_ref"]["value"], "binding.session_ref.value")
    _safe_ref(binding["correlation_id"]["value"], "binding.correlation_id.value")
    identity = _normalize_field_map(
        receipt.get("identity"), IDENTITY_FIELDS, "identity", missing_reason="identity_field_not_provided"
    )
    trajectory = _normalize_trajectory(receipt.get("trajectory"))
    timing = _normalize_timing(receipt.get("timing"), reason="timing_not_provided")
    cache = _normalize_cache(receipt.get("cache"), reason="cache_posture_not_provided")
    resource = _normalize_resource(receipt.get("resource"), reason="resource_posture_not_provided")
    review = _normalize_review(receipt.get("review"))
    evidence_refs = _normalize_refs(receipt.get("evidence_refs"))
    claim_ceiling = _safe_string(receipt.get("claim_ceiling"), "claim_ceiling")
    if claim_ceiling != "identity_bound_observation_only":
        raise TelemetryError("claim_ceiling_must_remain_observation_only")
    normalized: dict[str, Any] = {
        "schema_version": OWNER_RECEIPT_SCHEMA_VERSION,
        "artifact_type": OWNER_RECEIPT_ARTIFACT,
        "receipt_id": receipt_id,
        "producer": producer,
        "binding": binding,
        "identity": identity,
        "trajectory": trajectory,
        "timing": timing,
        "cache": cache,
        "resource": resource,
        "review": review,
        "evidence_refs": evidence_refs,
        "claim_ceiling": claim_ceiling,
    }
    if verify_id:
        expected_id = canonical_sha256({key: normalized[key] for key in normalized if key != "receipt_id"})
        if receipt_id != expected_id:
            raise TelemetryError("owner_receipt_digest_mismatch")
    return normalized


def build_owner_telemetry_receipt(
    *,
    session_id: str,
    session_ref: str,
    correlation_id: str,
    source: Mapping[str, Any],
    identity: Mapping[str, Any],
    trajectory: Mapping[str, Any],
    timing: Mapping[str, Any],
    cache: Mapping[str, Any],
    resource: Mapping[str, Any],
    evidence_refs: Sequence[Mapping[str, Any]],
    review_status: str = "provisional",
    review_ref: str | None = None,
    projection: Mapping[str, Any] | None = None,
    owner_repo: str = "validation-owner",
    producer_ref: str = "owner:validation-telemetry",
    mode: str = "capture_time_envelope",
) -> dict[str, Any]:
    """Create one typed owner receipt without filling absent values."""

    binding_projection = projection if isinstance(projection, Mapping) else {}

    def projection_field(name: str, reason: str) -> dict[str, Any]:
        value = binding_projection.get(name)
        if value is None:
            return missing(reason)
        if isinstance(value, Mapping):
            return dict(value)
        return known(value, source="owner_receipt")

    payload: dict[str, Any] = {
        "schema_version": OWNER_RECEIPT_SCHEMA_VERSION,
        "artifact_type": OWNER_RECEIPT_ARTIFACT,
        "producer": {
            "owner_repo": owner_repo,
            "producer_ref": producer_ref,
            "mode": mode,
        },
        "binding": {
            "session_id": known(session_id, source="owner_receipt"),
            "session_ref": known(session_ref, source="owner_receipt"),
            "correlation_id": known(correlation_id, source="owner_receipt"),
            "source": dict(source),
            "projection": {
                "prefix_identity": projection_field(
                    "prefix_identity", "projection_identity_not_provided"
                ),
                "publish_id": projection_field(
                    "publish_id", "projection_publish_not_provided"
                ),
            },
        },
        "identity": dict(identity),
        "trajectory": dict(trajectory),
        "timing": dict(timing),
        "cache": dict(cache),
        "resource": dict(resource),
        "review": {"status": review_status, "review_ref": review_ref},
        "evidence_refs": list(evidence_refs),
        "claim_ceiling": "identity_bound_observation_only",
    }
    normalized_without_id = _normalize_receipt_shape(
        {**payload, "receipt_id": canonical_sha256({})}, verify_id=False
    )
    payload["receipt_id"] = canonical_sha256(
        {key: normalized_without_id[key] for key in normalized_without_id if key != "receipt_id"}
    )
    return _normalize_receipt_shape(payload, verify_id=True)


def _field_value(field: Mapping[str, Any] | None) -> Any:
    return field.get("value") if isinstance(field, Mapping) and field.get("state") == "known" else None


def _field_state(field: Mapping[str, Any] | None) -> str:
    return str(field.get("state") or "unknown") if isinstance(field, Mapping) else "unknown"


def _public_receipt_binding(
    receipt: Mapping[str, Any],
    *,
    carrying_event: Mapping[str, Any] | None = None,
    carrying_event_witness: CarryingEventWitness | None = None,
) -> dict[str, Any]:
    binding = receipt.get("binding") if isinstance(receipt.get("binding"), Mapping) else {}
    if not binding:
        raise TelemetryError("admitted_receipt_binding_missing")
    session_id = _safe_ref(_field_value(binding.get("session_id")), "receipt_binding.session_id")
    session_ref = _safe_ref(_field_value(binding.get("session_ref")), "receipt_binding.session_ref")
    correlation_id = _safe_ref(
        _field_value(binding.get("correlation_id")), "receipt_binding.correlation_id"
    )
    projection = binding.get("projection") if isinstance(binding.get("projection"), Mapping) else {}
    projection_values: dict[str, str | None] = {}
    for name in ("prefix_identity", "publish_id"):
        value = _field_value(projection.get(name))
        projection_values[name] = _safe_ref(value, f"receipt_binding.projection.{name}") if value is not None else None
    if carrying_event is not None and carrying_event_witness is not None:
        raise TelemetryError("receipt_carrying_event_metadata_and_witness_conflict")
    public_carrying_event: dict[str, Any] | None = None
    if carrying_event_witness is not None:
        if not isinstance(carrying_event_witness, CarryingEventWitness):
            raise TelemetryError("receipt_carrying_event_witness_invalid")
        public_carrying_event = carrying_event_witness.public_event()
        if public_carrying_event["correlation_id"] != correlation_id:
            raise TelemetryError("receipt_carrying_event_correlation_mismatch")
        if public_carrying_event["receipt_id"] != receipt.get("receipt_id"):
            raise TelemetryError("receipt_carrying_event_receipt_mismatch")
    elif carrying_event is not None:
        if set(carrying_event) != {"line", "event_id", "correlation_id"}:
            raise TelemetryError("receipt_carrying_event_shape_invalid")
        line = carrying_event.get("line")
        if isinstance(line, bool) or not isinstance(line, int) or line < 1:
            raise TelemetryError("receipt_carrying_event_line_invalid")
        event_id = _safe_ref(carrying_event.get("event_id"), "receipt_carrying_event.event_id")
        event_correlation = _safe_ref(
            carrying_event.get("correlation_id"), "receipt_carrying_event.correlation_id"
        )
        if event_correlation != correlation_id:
            raise TelemetryError("receipt_carrying_event_correlation_mismatch")
        public_carrying_event = {
            "line": line,
            "event_id": event_id,
            "correlation_id": event_correlation,
        }
    owner_record = (
        carrying_event_witness.public_owner_record()
        if carrying_event_witness is not None
        else _build_process_local_receipt_record(receipt)
    )
    return {
        "session_id": session_id,
        "session_ref": session_ref,
        "correlation_id": correlation_id,
        "source": _public_source_identity(binding.get("source"), field="receipt_binding.source"),
        "projection": projection_values,
        "carrying_event": public_carrying_event,
        "owner_record": owner_record,
    }


def _build_process_local_receipt_record(receipt: Mapping[str, Any]) -> dict[str, Any]:
    receipt_digest = canonical_sha256(receipt)
    record: dict[str, Any] = {
        "schema_version": OWNER_SOURCE_EVIDENCE_SCHEMA_VERSION,
        "status": "process_local",
        "source_ref": _safe_ref(
            f"owner:receipt:{str(receipt.get('receipt_id') or '')}",
            "owner_source_record.source_ref",
        ),
        "artifact_sha256": receipt_digest,
        "event_sha256": receipt_digest,
        "facet_sha256": receipt_digest,
        "receipt_document_sha256": receipt_digest,
    }
    record["record_sha256"] = _owner_record_digest(record)
    return record


def _validate_public_receipt_binding(
    value: Any,
    *,
    expected_context: Mapping[str, Any],
    require_carrying_event: bool = False,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TelemetryError("packet_receipt_binding_missing")
    if set(value) != {
        "session_id",
        "session_ref",
        "correlation_id",
        "source",
        "projection",
        "carrying_event",
        "owner_record",
    }:
        raise TelemetryError("packet_receipt_binding_shape_invalid")
    normalized = {
        "session_id": _safe_ref(value.get("session_id"), "packet_receipt_binding.session_id"),
        "session_ref": _safe_ref(value.get("session_ref"), "packet_receipt_binding.session_ref"),
        "correlation_id": _safe_ref(
            value.get("correlation_id"), "packet_receipt_binding.correlation_id"
        ),
        "source": _public_source_identity(
            value.get("source"), field="packet_receipt_binding.source"
        ),
    }
    projection = value.get("projection")
    if not isinstance(projection, Mapping) or set(projection) != {"prefix_identity", "publish_id"}:
        raise TelemetryError("packet_receipt_binding_projection_shape_invalid")
    normalized["projection"] = {
        name: (
            _safe_ref(projection[name], f"packet_receipt_binding.projection.{name}")
            if projection[name] is not None
            else None
        )
        for name in ("prefix_identity", "publish_id")
    }
    carrying_event = value.get("carrying_event")
    if carrying_event is None:
        if require_carrying_event:
            raise TelemetryError("packet_receipt_carrying_event_missing")
        normalized["carrying_event"] = None
    else:
        if not isinstance(carrying_event, Mapping) or set(carrying_event) not in (
            {"line", "event_id", "correlation_id"},
            {"line", "event_id", "correlation_id", "receipt_id", "facet_sha256"},
        ):
            raise TelemetryError("packet_receipt_carrying_event_shape_invalid")
        line = carrying_event.get("line")
        if isinstance(line, bool) or not isinstance(line, int) or line < 1:
            raise TelemetryError("packet_receipt_carrying_event_line_invalid")
        event_id = _safe_ref(carrying_event.get("event_id"), "packet_receipt_carrying_event.event_id")
        event_correlation = _safe_ref(
            carrying_event.get("correlation_id"), "packet_receipt_carrying_event.correlation_id"
        )
        if event_correlation != normalized["correlation_id"]:
            raise TelemetryError("packet_receipt_carrying_event_correlation_mismatch")
        normalized_event = {
            "line": line,
            "event_id": event_id,
            "correlation_id": event_correlation,
        }
        if set(carrying_event) == {"line", "event_id", "correlation_id", "receipt_id", "facet_sha256"}:
            receipt_id = _safe_string(carrying_event.get("receipt_id"), "packet_receipt_carrying_event.receipt_id")
            if not SHA256_RE.fullmatch(receipt_id):
                raise TelemetryError("packet_receipt_carrying_event_receipt_id_invalid")
            facet_sha256 = _safe_string(carrying_event.get("facet_sha256"), "packet_receipt_carrying_event.facet_sha256")
            if not SHA256_RE.fullmatch(facet_sha256):
                raise TelemetryError("packet_receipt_carrying_event_facet_digest_invalid")
            normalized_event.update({"receipt_id": receipt_id, "facet_sha256": facet_sha256})
        normalized["carrying_event"] = normalized_event
    normalized["owner_record"] = _normalize_owner_source_record(
        value.get("owner_record"),
        "packet_receipt_binding.owner_record",
    )
    if normalized["carrying_event"] is not None:
        carrying_facet = normalized["carrying_event"].get("facet_sha256")
        if carrying_facet is not None:
            if normalized["owner_record"].get("facet_sha256") is None:
                raise TelemetryAdmissionError("packet_receipt_binding_owner_facet_missing")
            if normalized["owner_record"].get("facet_sha256") != carrying_facet:
                raise TelemetryAdmissionError("packet_receipt_binding_owner_facet_mismatch")
    for name in ("session_id", "session_ref"):
        if normalized[name] != expected_context[name]:
            raise TelemetryAdmissionError(f"packet_receipt_binding_{name}_mismatch")
    if normalized["source"] != expected_context["source"]:
        raise TelemetryAdmissionError("packet_receipt_binding_source_identity_mismatch")
    for name in ("prefix_identity", "publish_id"):
        if normalized["projection"][name] != expected_context["projection"][name]:
            raise TelemetryAdmissionError(f"packet_receipt_binding_projection_{name}_mismatch")
    return normalized


def _receipt_projection_material(
    *,
    receipt_id: str,
    identity: Mapping[str, Any],
    trajectory: Mapping[str, Any],
    timing: Mapping[str, Any],
    cache: Mapping[str, Any],
    resource: Mapping[str, Any],
    review: Mapping[str, Any],
    evidence_refs: Sequence[Mapping[str, Any]],
    public_binding: Mapping[str, Any],
) -> dict[str, Any]:
    """Return the packet-visible owner material committed by receipt provenance."""

    return {
        "schema_version": OWNER_RECEIPT_SCHEMA_VERSION,
        "artifact_type": OWNER_RECEIPT_ARTIFACT,
        "receipt_id": receipt_id,
        "binding": copy.deepcopy(dict(public_binding)),
        "identity": copy.deepcopy(dict(identity)),
        "trajectory": copy.deepcopy(dict(trajectory)),
        "timing": copy.deepcopy(dict(timing)),
        "cache": copy.deepcopy(dict(cache)),
        "resource": copy.deepcopy(dict(resource)),
        "review": copy.deepcopy(dict(review)),
        "evidence_refs": copy.deepcopy(list(evidence_refs)),
        "claim_ceiling": "identity_bound_observation_only",
    }


def _packet_receipt_projection_sha256(
    packet: Mapping[str, Any],
    *,
    public_binding: Mapping[str, Any],
    receipt_id: str,
) -> str:
    return canonical_sha256(
        _receipt_projection_material(
            receipt_id=receipt_id,
            identity=packet.get("identity") if isinstance(packet.get("identity"), Mapping) else {},
            trajectory=packet.get("trajectory") if isinstance(packet.get("trajectory"), Mapping) else {},
            timing=packet.get("timing") if isinstance(packet.get("timing"), Mapping) else {},
            cache=packet.get("cache") if isinstance(packet.get("cache"), Mapping) else {},
            resource=packet.get("resource") if isinstance(packet.get("resource"), Mapping) else {},
            review=packet.get("review") if isinstance(packet.get("review"), Mapping) else {},
            evidence_refs=packet.get("evidence_refs") if isinstance(packet.get("evidence_refs"), Sequence) else [],
            public_binding=public_binding,
        )
    )


def _build_receipt_provenance_chain(
    receipt: Mapping[str, Any],
    *,
    public_binding: Mapping[str, Any],
    projection_sha256: str,
) -> dict[str, Any]:
    """Bind the federated receipt id to an owner receipt/facet digest chain."""

    receipt_id = str(receipt.get("receipt_id") or "")
    carrying_event = public_binding.get("carrying_event")
    owner_record = public_binding.get("owner_record")
    facet_sha256 = (
        str(carrying_event.get("facet_sha256"))
        if isinstance(carrying_event, Mapping) and carrying_event.get("facet_sha256")
        else str((owner_record or {}).get("facet_sha256") or canonical_sha256(receipt))
    )
    chain: dict[str, Any] = {
        "schema_version": RECEIPT_PROVENANCE_SCHEMA_VERSION,
        "issuer": str((receipt.get("producer") or {}).get("owner_repo") or ""),
        "receipt_id": receipt_id,
        "receipt_payload_sha256": receipt_id,
        "receipt_document_sha256": str(
            (owner_record or {}).get("receipt_document_sha256") or canonical_sha256(receipt)
        ),
        "facet_sha256": facet_sha256,
        "binding_sha256": canonical_sha256(public_binding),
        "projection_sha256": projection_sha256,
        "owner_record": copy.deepcopy(owner_record),
    }
    chain["chain_sha256"] = canonical_sha256(chain)
    return chain


def _normalize_receipt_provenance_chain(
    value: Any,
    *,
    receipt_id: str,
    public_binding: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TelemetryAdmissionError("receipt_provenance_chain_missing")
    required = {
        "schema_version",
        "issuer",
        "receipt_id",
        "receipt_payload_sha256",
        "receipt_document_sha256",
        "facet_sha256",
        "binding_sha256",
        "projection_sha256",
        "owner_record",
        "chain_sha256",
    }
    if set(value) != required:
        raise TelemetryAdmissionError("receipt_provenance_chain_shape_invalid")
    if value.get("schema_version") != RECEIPT_PROVENANCE_SCHEMA_VERSION:
        raise TelemetryAdmissionError("receipt_provenance_chain_schema_unsupported")
    issuer = _safe_string(value.get("issuer"), "receipt_provenance.issuer")
    normalized: dict[str, Any] = {
        "schema_version": RECEIPT_PROVENANCE_SCHEMA_VERSION,
        "issuer": issuer,
        "receipt_id": _safe_string(value.get("receipt_id"), "receipt_provenance.receipt_id"),
        "receipt_payload_sha256": _safe_string(
            value.get("receipt_payload_sha256"), "receipt_provenance.receipt_payload_sha256"
        ),
        "receipt_document_sha256": _safe_string(
            value.get("receipt_document_sha256"), "receipt_provenance.receipt_document_sha256"
        ),
        "facet_sha256": _safe_string(value.get("facet_sha256"), "receipt_provenance.facet_sha256"),
        "binding_sha256": _safe_string(
            value.get("binding_sha256"), "receipt_provenance.binding_sha256"
        ),
        "projection_sha256": _safe_string(
            value.get("projection_sha256"), "receipt_provenance.projection_sha256"
        ),
        "owner_record": _normalize_owner_source_record(
            value.get("owner_record"), "receipt_provenance.owner_record"
        ),
        "chain_sha256": _safe_string(value.get("chain_sha256"), "receipt_provenance.chain_sha256"),
    }
    for name in (
        "receipt_id",
        "receipt_payload_sha256",
        "receipt_document_sha256",
        "facet_sha256",
        "binding_sha256",
        "projection_sha256",
        "chain_sha256",
    ):
        if not SHA256_RE.fullmatch(normalized[name]):
            raise TelemetryAdmissionError(f"receipt_provenance_{name}_invalid")
    if normalized["receipt_id"] != receipt_id:
        raise TelemetryAdmissionError("receipt_provenance_receipt_id_mismatch")
    if normalized["receipt_payload_sha256"] != receipt_id:
        raise TelemetryAdmissionError("receipt_provenance_receipt_payload_mismatch")
    if normalized["binding_sha256"] != canonical_sha256(public_binding):
        raise TelemetryAdmissionError("receipt_provenance_binding_mismatch")
    if normalized["owner_record"] != public_binding.get("owner_record"):
        raise TelemetryAdmissionError("receipt_provenance_owner_record_mismatch")
    if normalized["receipt_document_sha256"] != normalized["owner_record"].get("receipt_document_sha256"):
        raise TelemetryAdmissionError("receipt_provenance_receipt_document_mismatch")
    expected_facet = normalized["owner_record"].get("facet_sha256")
    if isinstance(public_binding.get("carrying_event"), Mapping):
        expected_facet = public_binding["carrying_event"].get("facet_sha256") or expected_facet
    if normalized["facet_sha256"] != expected_facet:
        raise TelemetryAdmissionError("receipt_provenance_facet_mismatch")
    chain_core = {key: normalized[key] for key in normalized if key != "chain_sha256"}
    if normalized["chain_sha256"] != canonical_sha256(chain_core):
        raise TelemetryAdmissionError("receipt_provenance_chain_digest_mismatch")
    return normalized


def _issue_receipt_provenance_witness(
    receipt: Mapping[str, Any],
    *,
    public_binding: Mapping[str, Any],
    projection_sha256: str,
) -> ReceiptProvenanceWitness:
    chain = _build_receipt_provenance_chain(
        receipt,
        public_binding=public_binding,
        projection_sha256=projection_sha256,
    )
    return ReceiptProvenanceWitness(chain, token=_RECEIPT_PROVENANCE_WITNESS_TOKEN)


def _issue_carrying_event_witness(
    receipt: Mapping[str, Any],
    carrying_event: Mapping[str, Any],
    *,
    owner_source_evidence: OwnerSourceEvidence,
) -> CarryingEventWitness:
    """Issue an immutable event/facet witness from one captured event only."""

    public_binding = _public_receipt_binding(receipt, carrying_event=carrying_event)
    event = public_binding["carrying_event"]
    assert isinstance(event, dict)
    owner_record = owner_source_evidence.public_record()
    expected_receipt_digest = canonical_sha256(receipt)
    if owner_record.get("receipt_document_sha256") != expected_receipt_digest:
        raise TelemetryAdmissionError("owner_receipt_source_document_mismatch")
    if owner_record.get("facet_sha256") != expected_receipt_digest:
        raise TelemetryAdmissionError("owner_receipt_source_facet_mismatch")
    value = {
        "event": {
            **event,
            "receipt_id": str(receipt["receipt_id"]),
            "facet_sha256": str(owner_record["facet_sha256"]),
        },
        "session_id": public_binding["session_id"],
        "session_ref": public_binding["session_ref"],
        "source": public_binding["source"],
        "projection": public_binding["projection"],
        "owner_record": owner_record,
    }
    return CarryingEventWitness(
        value,
        owner_source_evidence=owner_source_evidence,
        token=_CARRYING_EVENT_WITNESS_TOKEN,
    )


def _same_field(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return _field_state(left) == "known" and _field_state(right) == "known" and _field_value(left) == _field_value(right)


def _context_source(context: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return _normalize_source(
        context.get("source"),
        missing_reason="projection_source_not_provided",
        allow_context_scalars=True,
    )


def admit_owner_telemetry_receipt(
    receipt: Mapping[str, Any],
    *,
    expected_context: Mapping[str, Any],
) -> dict[str, Any]:
    """Verify receipt digest and exact session/source/projection binding."""

    normalized = _normalize_receipt_shape(receipt, verify_id=True)
    binding = normalized["binding"]
    expected_session_id = _safe_ref(expected_context.get("session_id"), "expected_context.session_id")
    expected_session_ref = _safe_ref(expected_context.get("session_ref"), "expected_context.session_ref")
    if _field_value(binding["session_id"]) != expected_session_id:
        raise TelemetryAdmissionError("session_identity_mismatch")
    if _field_value(binding["session_ref"]) != expected_session_ref:
        raise TelemetryAdmissionError("session_ref_mismatch")
    if _field_state(binding["correlation_id"]) != "known":
        raise TelemetryAdmissionError("correlation_identity_missing")

    expected_source = _context_source(expected_context)
    for name in SOURCE_FIELDS:
        actual = binding["source"][name]
        expected = expected_source[name]
        if not _same_field(actual, expected):
            raise TelemetryAdmissionError(f"source_identity_mismatch:{name}")

    expected_prefix = expected_context.get("prefix_identity")
    expected_publish = expected_context.get("publish_id")
    for name, expected in (("prefix_identity", expected_prefix), ("publish_id", expected_publish)):
        actual = binding["projection"][name]
        if expected is None:
            if _field_state(actual) == "known":
                raise TelemetryAdmissionError(f"projection_identity_unexpected:{name}")
            continue
        expected_text = _safe_string(expected, f"expected_context.{name}")
        if _field_state(actual) != "known":
            raise TelemetryAdmissionError(f"projection_identity_missing:{name}")
        if _field_value(actual) != expected_text:
            raise TelemetryAdmissionError(f"projection_identity_mismatch:{name}")

    normalized["admission"] = {
        "status": "source_and_session_bound",
        "projection_join": "exact_context_joined" if any(
            _field_state(binding["projection"][name]) != "known"
            for name in ("prefix_identity", "publish_id")
        ) else "receipt_declared_exact_projection",
        "expected_session_id": expected_session_id,
    }
    return normalized


def _default_identity(reason: str) -> dict[str, dict[str, Any]]:
    return {name: missing(reason) for name in IDENTITY_FIELDS}


def _default_trajectory(reason: str) -> dict[str, Any]:
    return {
        "chain_id": missing(reason),
        "steps": {
            name: {
                "state": "missing",
                "reason": reason,
                "correlation_id": missing(reason),
                "timestamp": missing(reason),
                "outcome": missing(reason),
                "evidence_refs": [],
            }
            for name in STEP_NAMES
        },
    }


def _default_timing(reason: str) -> dict[str, dict[str, Any]]:
    return {name: unobservable(reason, unit="seconds") for name in TIMING_FIELDS}


def _default_cache(reason: str) -> dict[str, Any]:
    return {"posture": missing(reason), "identity": missing(reason), "observed_state": unobservable(reason)}


def _default_resource(reason: str) -> dict[str, Any]:
    return {
        "posture": missing(reason),
        "metrics": {
            name: unobservable(reason, unit=unit)
            for name, unit in (
                ("cpu_ms", "milliseconds"),
                ("peak_rss_bytes", "bytes"),
                ("io_read_bytes", "bytes"),
                ("io_write_bytes", "bytes"),
            )
        },
    }


def _scope(
    *,
    session_id: str,
    session_ref: str,
    source: Mapping[str, Any] | None,
    prefix_identity: str | None,
    publish_id: str | None,
    status: str,
) -> dict[str, Any]:
    source_fields = _normalize_source(
        source,
        missing_reason="projection_source_not_available",
        allow_context_scalars=True,
    )
    return {
        "status": _safe_string(status, "scope.status"),
        "session_id": _safe_ref(session_id, "scope.session_id"),
        "session_ref": _safe_ref(session_ref, "scope.session_ref"),
        "source": source_fields,
        "prefix_identity": known(prefix_identity, source="session_projection") if prefix_identity else missing("projection_prefix_identity_not_available"),
        "publish_id": known(publish_id, source="session_projection") if publish_id else missing("projection_publish_id_not_available"),
        "global_currentness": status == "current",
    }


def _post_hoc_projection(profile: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(profile, Mapping):
        return {
            "status": "missing",
            "schema_version": None,
            "stage_spans": None,
            "repeat_amplification": None,
            "unknown_reasons": ["post_hoc_profile_not_provided"],
        }
    return {
        "status": "observed",
        "schema_version": profile.get("schema_version") or profile.get("profiler", {}).get("version"),
        "stage_spans": copy.deepcopy(profile.get("stage_spans") or profile.get("aggregate", {}).get("stage_spans")),
        "repeat_amplification": copy.deepcopy(
            profile.get("repeat_amplification") or profile.get("aggregate", {}).get("repeat_amplification")
        ),
        "unknown_reasons": list(profile.get("unknown_reasons") or []),
        "claim_ceiling": "structured_observation_only_not_identity_or_effect",
    }


def _eligibility(
    *,
    identity: Mapping[str, Mapping[str, Any]],
    trajectory: Mapping[str, Any],
    timing: Mapping[str, Any],
    review: Mapping[str, Any],
    cache: Mapping[str, Any],
    resource: Mapping[str, Any],
    receipt_status: str,
) -> dict[str, Any]:
    reasons: list[str] = []
    if receipt_status != "admitted":
        reasons.append(f"owner_receipt_{receipt_status}")
    for name in IDENTITY_FIELDS:
        state = _field_state(identity.get(name))
        if state != "known":
            reasons.append(f"identity_{name}_{state}")
    if str(review.get("status") or "unknown") != "reviewed":
        reasons.append(f"review_{review.get('status') or 'unknown'}")
    if _field_state(trajectory.get("chain_id")) != "known":
        reasons.append("trajectory_chain_id_not_known")
    for name in STEP_NAMES:
        step = trajectory.get("steps", {}).get(name, {}) if isinstance(trajectory.get("steps"), Mapping) else {}
        if step.get("state") != "known":
            reasons.append(f"trajectory_{name}_{step.get('state') or 'unknown'}")
    posture = cache.get("posture") if isinstance(cache, Mapping) else None
    if _field_state(posture) != "known":
        reasons.append(f"cache_posture_{_field_state(posture)}")
    elif str(_field_value(posture)).casefold() == "partial":
        reasons.append("cache_posture_partial_unadmitted")
    resource_posture = resource.get("posture") if isinstance(resource, Mapping) else None
    if _field_state(resource_posture) != "known":
        reasons.append(f"resource_posture_{_field_state(resource_posture)}")
    typed_values: list[Any] = [*identity.values(), *timing.values(), trajectory.get("chain_id")]
    steps = trajectory.get("steps") if isinstance(trajectory.get("steps"), Mapping) else {}
    typed_values.extend(steps.values())
    if isinstance(cache, Mapping):
        typed_values.extend(cache.values())
    if isinstance(resource, Mapping):
        typed_values.append(resource.get("posture"))
        metrics = resource.get("metrics") if isinstance(resource.get("metrics"), Mapping) else {}
        typed_values.extend(metrics.values())
    if receipt_status == "missing":
        status = "missing"
    elif receipt_status != "admitted":
        status = "excluded"
    elif any(_field_state(value) == "unobservable" for value in typed_values):
        status = "unobservable"
    elif (
        any(_field_state(value) in {"missing", "unknown", "null"} for value in typed_values)
        or str(review.get("status") or "unknown") in {"unknown", "provisional"}
    ):
        status = "unknown"
    elif any(reason.startswith("cache_posture_partial") for reason in reasons) or review.get("status") == "excluded":
        status = "excluded"
    else:
        status = "eligible_identity_packet"
    return {
        "status": status,
        "reasons": reasons,
        "effect_verdict": None,
        "proof": False,
        "acceptance": False,
    }


def _packet_without_id(packet: Mapping[str, Any]) -> dict[str, Any]:
    return {key: copy.deepcopy(value) for key, value in packet.items() if key != "packet_id"}


def _build_route_admission(
    route: str,
    *,
    episode_binding: Mapping[str, Any] | None = None,
    owner_record: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if route not in {"generic", "episode_strict"}:
        raise TelemetryError("packet_route_invalid")
    core: dict[str, Any] = {
        "schema_version": PACKET_ROUTE_SCHEMA_VERSION,
        "route": route,
        "binding_sha256": (
            canonical_sha256(episode_binding) if episode_binding is not None else None
        ),
        "owner_validator": OWNER_VALIDATION_REF if route == "episode_strict" else None,
        "owner_record": copy.deepcopy(dict(owner_record)) if owner_record is not None else None,
    }
    core["route_sha256"] = canonical_sha256(core)
    return core


def _normalize_route_admission(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TelemetryAdmissionError("packet_route_admission_missing")
    required = {
        "schema_version",
        "route",
        "binding_sha256",
        "owner_validator",
        "owner_record",
        "route_sha256",
    }
    if set(value) != required:
        raise TelemetryAdmissionError("packet_route_admission_shape_invalid")
    route = value.get("route")
    if route not in {"generic", "episode_strict"}:
        raise TelemetryAdmissionError("packet_route_invalid")
    binding_sha256 = value.get("binding_sha256")
    if binding_sha256 is not None and (
        not isinstance(binding_sha256, str) or not SHA256_RE.fullmatch(binding_sha256)
    ):
        raise TelemetryAdmissionError("packet_route_binding_digest_invalid")
    owner_validator = value.get("owner_validator")
    if owner_validator is not None:
        owner_validator = _safe_string(owner_validator, "packet_route.owner_validator")
    owner_record = value.get("owner_record")
    if owner_record is not None:
        owner_record = _normalize_owner_source_record(owner_record, "packet_route.owner_record")
    normalized = {
        "schema_version": value.get("schema_version"),
        "route": route,
        "binding_sha256": binding_sha256,
        "owner_validator": owner_validator,
        "owner_record": owner_record,
        "route_sha256": value.get("route_sha256"),
    }
    if normalized["schema_version"] != PACKET_ROUTE_SCHEMA_VERSION:
        raise TelemetryAdmissionError("packet_route_schema_unsupported")
    if not isinstance(normalized["route_sha256"], str) or not SHA256_RE.fullmatch(normalized["route_sha256"]):
        raise TelemetryAdmissionError("packet_route_digest_invalid")
    core = {key: normalized[key] for key in normalized if key != "route_sha256"}
    if normalized["route_sha256"] != canonical_sha256(core):
        raise TelemetryAdmissionError("packet_route_digest_mismatch")
    if route == "episode_strict":
        if (
            binding_sha256 is None
            or owner_validator != OWNER_VALIDATION_REF
            or owner_record is None
        ):
            raise TelemetryAdmissionError("packet_route_owner_validator_barrier_missing")
    elif binding_sha256 is not None or owner_validator is not None or owner_record is not None:
        raise TelemetryAdmissionError("packet_route_generic_binding_unexpected")
    return normalized


def project_identity_bound_packet(
    *,
    session_id: str,
    session_ref: str,
    source: Mapping[str, Any] | None,
    prefix_identity: str | None,
    publish_id: str | None,
    projection_status: str,
    review_status: str,
    profile: Mapping[str, Any] | None = None,
    owner_receipt: Mapping[str, Any] | None = None,
    receipt_rejection: str | None = None,
    episode_binding: Mapping[str, Any] | None = None,
    receipt_carrying_event: Mapping[str, Any] | None = None,
    component_admission: EpisodeComponentAdmission | None = None,
    receipt_carrying_event_witness: CarryingEventWitness | None = None,
) -> dict[str, Any]:
    """Project post-hoc observations and an optional owner receipt.

    This function never derives identity from operation text.  A receipt that
    fails admission becomes a compact rejection state; callers can still
    inspect the bounded observation without accidentally admitting it.
    """

    scope = _scope(
        session_id=session_id,
        session_ref=session_ref,
        source=source,
        prefix_identity=prefix_identity,
        publish_id=publish_id,
        status=projection_status,
    )
    expected_context = {
        "session_id": session_id,
        "session_ref": session_ref,
        "source": source or {},
        "prefix_identity": prefix_identity,
        "publish_id": publish_id,
    }
    normalized_episode_binding = (
        validate_episode_binding(
            episode_binding,
            expected_context=expected_context,
            component_admission=component_admission,
            require_owner_admission=True,
        )
        if episode_binding is not None
        else None
    )
    admitted_receipt: dict[str, Any] | None = None
    receipt_status = "rejected" if receipt_rejection else "missing"
    rejection = receipt_rejection
    if owner_receipt is not None:
        try:
            admitted_receipt = admit_owner_telemetry_receipt(
                owner_receipt,
                expected_context=expected_context,
            )
            receipt_status = "admitted"
        except TelemetryError as exc:
            receipt_status = "rejected"
            rejection = str(exc)

    if admitted_receipt is not None:
        identity = admitted_receipt["identity"]
        trajectory = admitted_receipt["trajectory"]
        timing = admitted_receipt["timing"]
        cache = admitted_receipt["cache"]
        resource = admitted_receipt["resource"]
        review = admitted_receipt["review"]
        evidence_refs = admitted_receipt["evidence_refs"]
    else:
        identity = _default_identity("owner_receipt_not_federated")
        trajectory = _default_trajectory("owner_receipt_not_federated")
        timing = _default_timing("first_failure_and_resource_telemetry_not_observable_from_projection")
        cache = _default_cache("cache_posture_not_provided_by_owner")
        resource = _default_resource("resource_telemetry_not_observable_from_projection")
        review = _normalize_review({"status": review_status}, fallback="unknown")
        evidence_refs = []

    receipt_public_binding = (
        _public_receipt_binding(
            admitted_receipt,
            carrying_event=receipt_carrying_event,
            carrying_event_witness=receipt_carrying_event_witness,
        )
        if admitted_receipt
        else None
    )
    receipt_provenance_witness = (
        _issue_receipt_provenance_witness(
            admitted_receipt,
            public_binding=receipt_public_binding,
            projection_sha256=canonical_sha256(
                _receipt_projection_material(
                    receipt_id=str(admitted_receipt["receipt_id"]),
                    identity=identity,
                    trajectory=trajectory,
                    timing=timing,
                    cache=cache,
                    resource=resource,
                    review=review,
                    evidence_refs=evidence_refs,
                    public_binding=receipt_public_binding,
                )
            ),
        )
        if admitted_receipt and receipt_public_binding is not None
        else None
    )
    methods = {
        "capture_time_envelope": {
            "status": "admitted" if admitted_receipt and admitted_receipt["producer"]["mode"] == "capture_time_envelope" else "not_admitted",
            "claim_ceiling": "explicit_owner_fields_only",
        },
        "post_hoc_structured_projection": {
            "status": "observed" if profile is not None else "missing",
            "claim_ceiling": "normalized_spans_and_unknowns_only",
        },
        "owner_receipt_federation": {
            "status": receipt_status,
            "receipt_id": admitted_receipt.get("receipt_id") if admitted_receipt else None,
            "receipt_provenance": (
                receipt_provenance_witness.public_chain()
                if receipt_provenance_witness is not None
                else None
            ),
            "claim_ceiling": "identity_bound_observation_only",
            "rejection": rejection,
            "binding": receipt_public_binding,
        },
    }
    packet: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": PACKET_ARTIFACT,
        "producer": {
            "owner_repo": "aoa-session-memory",
            "producer_ref": "scripts/profile_session_stages.py",
            "mode": "owner_receipt_federation" if admitted_receipt else "post_hoc_projection",
        },
        "scope": scope,
        "identity": identity,
        "trajectory": trajectory,
        "timing": timing,
        "cache": cache,
        "resource": resource,
        "review": review,
        "evidence_refs": evidence_refs,
        "methods": methods,
        "post_hoc_projection": _post_hoc_projection(profile),
        "eligibility": _eligibility(
            identity=identity,
            trajectory=trajectory,
            timing=timing,
            review=review,
            cache=cache,
            resource=resource,
            receipt_status=receipt_status,
        ),
        "authority": {
            "owner": "aoa-session-memory",
            "claim_ceiling": "identity_bound_evidence_packet_only",
            "validation_claim_owner": "external_validation_owner",
            "comparison_verdict": None,
            "proof": False,
            "acceptance": False,
        },
        "integrity": {
            "status": "verified",
            "receipt_id": admitted_receipt.get("receipt_id") if admitted_receipt else None,
            "projection_binding": "exact_session_projection_context",
        },
        "route_admission": _build_route_admission(
            "episode_strict" if normalized_episode_binding is not None else "generic",
            episode_binding=normalized_episode_binding,
            owner_record=(
                component_admission.public_owner_record()
                if normalized_episode_binding is not None
                and isinstance(component_admission, EpisodeComponentAdmission)
                else None
            ),
        ),
    }
    packet["integrity"]["route_floor"] = packet["route_admission"]["route"]
    if normalized_episode_binding is not None:
        packet["episode_binding"] = normalized_episode_binding
    if admitted_receipt is not None and normalized_episode_binding is not None:
        if not isinstance(receipt_carrying_event_witness, CarryingEventWitness):
            raise TelemetryAdmissionError("receipt_carrying_event_witness_required_for_episode_route")
        public_binding = methods["owner_receipt_federation"]["binding"]
        _validate_carrying_event_witness(
            receipt_carrying_event_witness,
            public_binding=public_binding,
            episode_binding=normalized_episode_binding,
            expected_context=_packet_scope_context(packet, side="packet"),
            receipt_id=str(admitted_receipt["receipt_id"]),
            receipt_provenance=methods["owner_receipt_federation"]["receipt_provenance"],
        )
    packet["packet_id"] = canonical_sha256(_packet_without_id(packet))
    if (
        component_admission is not None
        or receipt_carrying_event_witness is not None
        or receipt_provenance_witness is not None
    ):
        return IdentityBoundPacket(
            packet,
            component_admission=component_admission,
            carrying_event_witness=receipt_carrying_event_witness,
            receipt_provenance_witness=receipt_provenance_witness,
        )
    return packet


def project_identity_bound_episode_packet(
    *,
    session_id: str,
    session_ref: str,
    source: Mapping[str, Any] | None,
    prefix_identity: str | None,
    publish_id: str | None,
    projection_status: str,
    review_status: str,
    episode_binding: Mapping[str, Any],
    profile: Mapping[str, Any] | None = None,
    owner_receipt: Mapping[str, Any] | None = None,
    receipt_rejection: str | None = None,
    component_admission: EpisodeComponentAdmission | None = None,
    receipt_carrying_event_witness: CarryingEventWitness | None = None,
    receipt_carrying_event: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Project an episode packet through the strict episode API boundary."""

    if episode_binding is None:
        raise TelemetryError("episode_binding_required_for_episode_route")
    if not isinstance(component_admission, EpisodeComponentAdmission):
        raise TelemetryError("episode_component_admission_required_for_episode_route")
    if receipt_carrying_event is not None:
        raise TelemetryError("receipt_carrying_event_caller_metadata_not_allowed")
    if owner_receipt is not None and not isinstance(receipt_carrying_event_witness, CarryingEventWitness):
        raise TelemetryError("receipt_carrying_event_witness_required_for_episode_route")
    packet = project_identity_bound_packet(
        session_id=session_id,
        session_ref=session_ref,
        source=source,
        prefix_identity=prefix_identity,
        publish_id=publish_id,
        projection_status=projection_status,
        review_status=review_status,
        profile=profile,
        owner_receipt=owner_receipt,
        receipt_rejection=receipt_rejection,
        episode_binding=episode_binding,
        component_admission=component_admission,
        receipt_carrying_event_witness=receipt_carrying_event_witness,
    )
    packet["schema_version"] = EPISODE_PACKET_SCHEMA_VERSION
    packet["artifact_type"] = EPISODE_PACKET_ARTIFACT
    packet["route_admission"] = _build_route_admission(
        "episode_strict",
        episode_binding=packet.get("episode_binding"),
        owner_record=component_admission.public_owner_record(),
    )
    packet["packet_id"] = canonical_sha256(_packet_without_id(packet))
    return packet


def _validate_carrying_event_public(
    event: Mapping[str, Any],
    *,
    public_binding: Mapping[str, Any],
    episode_binding: Mapping[str, Any],
    expected_context: Mapping[str, Any],
    receipt_id: str,
    receipt_provenance: Mapping[str, Any],
) -> None:
    if set(event) != {"line", "event_id", "correlation_id", "receipt_id", "facet_sha256"}:
        raise TelemetryAdmissionError("packet_carrying_event_shape_invalid")
    if public_binding.get("carrying_event") != event:
        raise TelemetryAdmissionError("packet_carrying_event_mismatch")
    if event["receipt_id"] != receipt_id:
        raise TelemetryAdmissionError("packet_carrying_event_receipt_mismatch")
    if not SHA256_RE.fullmatch(str(event["facet_sha256"])):
        raise TelemetryAdmissionError("packet_carrying_event_facet_digest_invalid")
    if event["facet_sha256"] != receipt_provenance.get("facet_sha256"):
        raise TelemetryAdmissionError("packet_carrying_event_provenance_facet_mismatch")
    if event["correlation_id"] != public_binding.get("correlation_id"):
        raise TelemetryAdmissionError("packet_carrying_event_correlation_mismatch")
    line = event["line"]
    event_range = episode_binding["event_range"]
    if not event_range["from_line"] <= line <= event_range["to_line"]:
        raise TelemetryAdmissionError("packet_carrying_event_outside_episode_range")
    if episode_binding["session_id"] != expected_context["session_id"] or episode_binding["session_ref"] != expected_context["session_ref"]:
        raise TelemetryAdmissionError("packet_carrying_event_episode_scope_mismatch")
    if episode_binding["source"] != expected_context["source"]:
        raise TelemetryAdmissionError("packet_carrying_event_source_identity_mismatch")


def _validate_carrying_event_witness(
    witness: CarryingEventWitness,
    *,
    public_binding: Mapping[str, Any],
    episode_binding: Mapping[str, Any],
    expected_context: Mapping[str, Any],
    receipt_id: str,
    receipt_provenance: Mapping[str, Any],
) -> None:
    if not isinstance(witness, CarryingEventWitness):
        raise TelemetryAdmissionError("packet_carrying_event_witness_invalid")
    if not witness.verify_source_current():
        raise TelemetryAdmissionError("packet_carrying_event_owner_source_not_current")
    event = witness.public_event()
    if witness.public_owner_record() != public_binding.get("owner_record"):
        raise TelemetryAdmissionError("packet_carrying_event_owner_record_mismatch")
    _validate_carrying_event_public(
        event,
        public_binding=public_binding,
        episode_binding=episode_binding,
        expected_context=expected_context,
        receipt_id=receipt_id,
        receipt_provenance=receipt_provenance,
    )
    context = witness.public_context()
    for name in ("session_id", "session_ref", "source", "projection"):
        if context.get(name) != expected_context.get(name):
            raise TelemetryAdmissionError(f"packet_carrying_event_{name}_mismatch")


def _packet_eligibility(packet: Mapping[str, Any]) -> dict[str, Any]:
    methods = packet.get("methods") if isinstance(packet.get("methods"), Mapping) else {}
    federation = methods.get("owner_receipt_federation")
    receipt_status = (
        str(federation.get("status") or "missing")
        if isinstance(federation, Mapping)
        else "missing"
    )
    return _eligibility(
        identity=packet.get("identity") if isinstance(packet.get("identity"), Mapping) else {},
        trajectory=packet.get("trajectory") if isinstance(packet.get("trajectory"), Mapping) else {},
        timing=packet.get("timing") if isinstance(packet.get("timing"), Mapping) else {},
        review=packet.get("review") if isinstance(packet.get("review"), Mapping) else {},
        cache=packet.get("cache") if isinstance(packet.get("cache"), Mapping) else {},
        resource=packet.get("resource") if isinstance(packet.get("resource"), Mapping) else {},
        receipt_status=receipt_status,
    )


def verify_packet_integrity(
    packet: Mapping[str, Any],
    *,
    component_admission: EpisodeComponentAdmission | None = None,
    carrying_event_witness: CarryingEventWitness | None = None,
) -> None:
    if not isinstance(packet, Mapping):
        raise TelemetryError("packet_must_be_object")
    packet_id = packet.get("packet_id")
    if not isinstance(packet_id, str) or not SHA256_RE.fullmatch(packet_id):
        raise TelemetryError("packet_id_invalid")
    if canonical_sha256(_packet_without_id(packet)) != packet_id:
        raise TelemetryError("packet_digest_mismatch")
    authority = packet.get("authority") if isinstance(packet.get("authority"), Mapping) else {}
    if authority.get("comparison_verdict") is not None:
        raise TelemetryError("comparison_verdict_must_remain_null")
    if authority.get("proof") is not False:
        raise TelemetryError("authority_proof_must_remain_false")
    if authority.get("acceptance") is not False:
        raise TelemetryError("authority_acceptance_must_remain_false")
    route = _normalize_route_admission(packet.get("route_admission"))
    episode_route = route["route"] == "episode_strict"
    artifact_is_episode = (
        packet.get("artifact_type") == EPISODE_PACKET_ARTIFACT
        or packet.get("schema_version") == EPISODE_PACKET_SCHEMA_VERSION
    )
    if episode_route != artifact_is_episode:
        raise TelemetryAdmissionError("packet_route_artifact_mismatch")
    integrity = packet.get("integrity")
    if not isinstance(integrity, Mapping):
        raise TelemetryAdmissionError("packet_integrity_marker_missing")
    if set(integrity) != {"status", "receipt_id", "projection_binding", "route_floor"}:
        raise TelemetryAdmissionError("packet_integrity_marker_shape_invalid")
    if integrity.get("status") != "verified":
        raise TelemetryAdmissionError("packet_integrity_status_invalid")
    if integrity.get("projection_binding") != "exact_session_projection_context":
        raise TelemetryAdmissionError("packet_integrity_projection_binding_invalid")
    route_floor = integrity.get("route_floor")
    if route_floor not in {"generic", "episode_strict"} or route_floor != route["route"]:
        raise TelemetryAdmissionError("packet_integrity_route_floor_mismatch")
    integrity_receipt_id = integrity.get("receipt_id")
    if integrity_receipt_id is not None and (
        not isinstance(integrity_receipt_id, str) or not SHA256_RE.fullmatch(integrity_receipt_id)
    ):
        raise TelemetryAdmissionError("packet_integrity_receipt_id_invalid")
    if episode_route and "episode_binding" not in packet:
        raise TelemetryError("episode_binding_required_for_episode_packet")
    if not episode_route and "episode_binding" in packet:
        raise TelemetryAdmissionError("generic_packet_episode_binding_unexpected")
    if episode_route:
        component_admission = component_admission or getattr(packet, "_component_admission", None)
        if not isinstance(component_admission, EpisodeComponentAdmission):
            raise TelemetryAdmissionError("episode_component_admission_required")
        if not component_admission.verify_current():
            raise TelemetryAdmissionError("episode_component_owner_source_not_current")
        scope = packet.get("scope") if isinstance(packet.get("scope"), Mapping) else {}
        normalized_binding = validate_episode_binding(
            packet["episode_binding"],
            expected_context={
                "session_id": scope.get("session_id"),
                "session_ref": scope.get("session_ref"),
                "source": scope.get("source"),
            },
            component_admission=component_admission,
            require_owner_admission=True,
        )
        if route["binding_sha256"] != canonical_sha256(normalized_binding):
            raise TelemetryAdmissionError("packet_route_binding_digest_mismatch")
        if route["owner_record"] != component_admission.public_owner_record():
            raise TelemetryAdmissionError("packet_route_owner_record_mismatch")
    else:
        normalized_binding = None
    methods = packet.get("methods") if isinstance(packet.get("methods"), Mapping) else {}
    federation = methods.get("owner_receipt_federation")
    if isinstance(federation, Mapping) and federation.get("status") == "admitted":
        if integrity_receipt_id != federation.get("receipt_id"):
            raise TelemetryAdmissionError("packet_integrity_receipt_id_mismatch")
        scope_context = _packet_scope_context(packet, side="packet")
        public_binding = _validate_public_receipt_binding(
            federation.get("binding"),
            expected_context=scope_context,
            require_carrying_event=episode_route,
        )
        receipt_provenance = _normalize_receipt_provenance_chain(
            federation.get("receipt_provenance"),
            receipt_id=str(federation.get("receipt_id") or ""),
            public_binding=public_binding,
        )
        provenance_witness = getattr(packet, "_receipt_provenance_witness", None)
        if not isinstance(provenance_witness, ReceiptProvenanceWitness):
            raise TelemetryAdmissionError("receipt_provenance_witness_required")
        if provenance_witness.public_chain() != receipt_provenance:
            raise TelemetryAdmissionError("receipt_provenance_witness_mismatch")
        if receipt_provenance["projection_sha256"] != _packet_receipt_projection_sha256(
            packet,
            public_binding=public_binding,
            receipt_id=str(federation.get("receipt_id") or ""),
        ):
            raise TelemetryAdmissionError("receipt_provenance_projection_mismatch")
        if episode_route:
            if normalized_binding is None:
                raise TelemetryAdmissionError("packet_episode_binding_missing")
            carrying_event = public_binding.get("carrying_event")
            if not isinstance(carrying_event, Mapping):
                raise TelemetryAdmissionError("packet_carrying_event_missing")
            _validate_carrying_event_public(
                carrying_event,
                public_binding=public_binding,
                episode_binding=normalized_binding,
                expected_context=scope_context,
                receipt_id=str(federation.get("receipt_id") or ""),
                receipt_provenance=receipt_provenance,
            )
            carrying_event_witness = carrying_event_witness or getattr(packet, "_carrying_event_witness", None)
            if not isinstance(carrying_event_witness, CarryingEventWitness):
                raise TelemetryAdmissionError("packet_carrying_event_witness_required")
            _validate_carrying_event_witness(
                carrying_event_witness,
                public_binding=public_binding,
                episode_binding=normalized_binding,
                expected_context=scope_context,
                receipt_id=str(federation.get("receipt_id") or ""),
                receipt_provenance=receipt_provenance,
            )
    elif integrity_receipt_id is not None:
        raise TelemetryAdmissionError("packet_integrity_receipt_without_admission")
    expected_eligibility = _packet_eligibility(packet)
    if packet.get("eligibility") != expected_eligibility:
        raise TelemetryAdmissionError("eligibility_not_recomputed_from_typed_fields")


def _packet_scope_context(packet: Mapping[str, Any], *, side: str) -> dict[str, Any]:
    scope = packet.get("scope") if isinstance(packet.get("scope"), Mapping) else None
    if scope is None:
        raise TelemetryError(f"{side}_scope_missing")
    session_id = _safe_ref(scope.get("session_id"), f"{side}.scope.session_id")
    session_ref = _safe_ref(scope.get("session_ref"), f"{side}.scope.session_ref")
    source = _public_source_identity(scope.get("source"), field=f"{side}.scope.source")
    projection: dict[str, str | None] = {}
    for name in ("prefix_identity", "publish_id"):
        field = scope.get(name)
        projection[name] = _safe_ref(_field_value(field), f"{side}.scope.{name}") if _field_state(field) == "known" else None
    return {
        "session_id": session_id,
        "session_ref": session_ref,
        "source": source,
        "projection": projection,
    }


def build_comparison_contract(
    *,
    design: str,
    required_equal_identity_fields: Sequence[str],
    allowed_identity_differences: Sequence[str],
    required_equal_scope_fields: Sequence[str],
    allowed_scope_differences: Sequence[str],
    left_role_value: str | None = None,
    right_role_value: str | None = None,
) -> dict[str, Any]:
    """Build an explicit design contract before admitting a cohort pair."""

    design_roles = COMPARISON_DESIGNS.get(design, ("", ""))
    if design == "paired" and (left_role_value is None or right_role_value is None):
        raise TelemetryError("comparison_contract_role_binding_values_required")
    return _normalize_comparison_contract(
        {
            "schema_version": COMPARISON_CONTRACT_SCHEMA_VERSION,
            "design": design,
            "left_role": COMPARISON_DESIGNS.get(design, ("", ""))[0],
            "right_role": COMPARISON_DESIGNS.get(design, ("", ""))[1],
            "required_equal_identity_fields": list(required_equal_identity_fields),
            "allowed_identity_differences": list(allowed_identity_differences),
            "required_equal_scope_fields": list(required_equal_scope_fields),
            "allowed_scope_differences": list(allowed_scope_differences),
            "equality_anchors": {
                "identity": list(required_equal_identity_fields),
                "scope": list(required_equal_scope_fields),
            },
            "role_binding": {
                "field": "route_or_treatment_identity",
                "left_value": left_role_value if left_role_value is not None else design_roles[0],
                "right_value": right_role_value if right_role_value is not None else design_roles[1],
            },
            "claim_ceiling": "admission_only_no_effect_or_verdict",
        }
    )


def _normalize_comparison_contract(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TelemetryError("comparison_contract_required")
    required = {
        "schema_version",
        "design",
        "left_role",
        "right_role",
        "required_equal_identity_fields",
        "allowed_identity_differences",
        "required_equal_scope_fields",
        "allowed_scope_differences",
        "equality_anchors",
        "role_binding",
        "claim_ceiling",
    }
    if set(value) != required:
        raise TelemetryError("comparison_contract_shape_invalid")
    if value.get("schema_version") != COMPARISON_CONTRACT_SCHEMA_VERSION:
        raise TelemetryError("comparison_contract_schema_unsupported")
    design = value.get("design")
    if design not in COMPARISON_DESIGNS:
        raise TelemetryError("comparison_contract_design_invalid")
    if (value.get("left_role"), value.get("right_role")) != COMPARISON_DESIGNS[design]:
        raise TelemetryError("comparison_contract_roles_invalid")

    def normalize_names(raw: Any, field: str, allowed: Sequence[str]) -> list[str]:
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes, bytearray)):
            raise TelemetryError(f"{field}_must_be_list")
        names = [str(item) for item in raw]
        if len(set(names)) != len(names) or any(name not in allowed for name in names):
            raise TelemetryError(f"{field}_invalid")
        return names

    required_identity = normalize_names(
        value.get("required_equal_identity_fields"),
        "comparison_contract.required_equal_identity_fields",
        IDENTITY_FIELDS,
    )
    allowed_identity = normalize_names(
        value.get("allowed_identity_differences"),
        "comparison_contract.allowed_identity_differences",
        IDENTITY_FIELDS,
    )
    if set(required_identity) & set(allowed_identity) or set(required_identity) | set(allowed_identity) != set(IDENTITY_FIELDS):
        raise TelemetryError("comparison_contract_identity_coverage_invalid")
    if not required_identity or not (
        set(required_identity) & COMPARISON_EQUALITY_ANCHOR_IDENTITY_FIELDS
    ):
        raise TelemetryError("comparison_contract_non_vacuous_identity_anchor_required")
    required_scope = normalize_names(
        value.get("required_equal_scope_fields"),
        "comparison_contract.required_equal_scope_fields",
        COMPARISON_SCOPE_FIELDS,
    )
    allowed_scope = normalize_names(
        value.get("allowed_scope_differences"),
        "comparison_contract.allowed_scope_differences",
        COMPARISON_SCOPE_FIELDS,
    )
    if set(required_scope) & set(allowed_scope) or set(required_scope) | set(allowed_scope) != set(COMPARISON_SCOPE_FIELDS):
        raise TelemetryError("comparison_contract_scope_coverage_invalid")
    if not required_scope:
        raise TelemetryError("comparison_contract_non_vacuous_scope_anchor_required")
    equality_anchors = value.get("equality_anchors")
    if not isinstance(equality_anchors, Mapping) or set(equality_anchors) != {"identity", "scope"}:
        raise TelemetryError("comparison_contract_equality_anchors_shape_invalid")
    anchor_identity = normalize_names(
        equality_anchors.get("identity"),
        "comparison_contract.equality_anchors.identity",
        IDENTITY_FIELDS,
    )
    anchor_scope = normalize_names(
        equality_anchors.get("scope"),
        "comparison_contract.equality_anchors.scope",
        COMPARISON_SCOPE_FIELDS,
    )
    if anchor_identity != required_identity or anchor_scope != required_scope:
        raise TelemetryError("comparison_contract_equality_anchors_mismatch")
    role_binding = value.get("role_binding")
    if not isinstance(role_binding, Mapping) or set(role_binding) != {"field", "left_value", "right_value"}:
        raise TelemetryError("comparison_contract_role_binding_shape_invalid")
    if role_binding.get("field") not in COMPARISON_ROLE_BINDING_FIELDS:
        raise TelemetryError("comparison_contract_role_binding_field_invalid")
    left_role_value = _safe_string(
        role_binding.get("left_value"), "comparison_contract.role_binding.left_value"
    )
    right_role_value = _safe_string(
        role_binding.get("right_value"), "comparison_contract.role_binding.right_value"
    )
    if design != "paired" and (left_role_value, right_role_value) != COMPARISON_DESIGNS[design]:
        raise TelemetryError("comparison_contract_role_binding_values_invalid")
    if value.get("claim_ceiling") != "admission_only_no_effect_or_verdict":
        raise TelemetryError("comparison_contract_claim_ceiling_invalid")
    return {
        "schema_version": COMPARISON_CONTRACT_SCHEMA_VERSION,
        "design": design,
        "left_role": COMPARISON_DESIGNS[design][0],
        "right_role": COMPARISON_DESIGNS[design][1],
        "required_equal_identity_fields": required_identity,
        "allowed_identity_differences": allowed_identity,
        "required_equal_scope_fields": required_scope,
        "allowed_scope_differences": allowed_scope,
        "equality_anchors": {
            "identity": anchor_identity,
            "scope": anchor_scope,
        },
        "role_binding": {
            "field": role_binding["field"],
            "left_value": left_role_value,
            "right_value": right_role_value,
        },
        "claim_ceiling": "admission_only_no_effect_or_verdict",
    }


def compare_identity_packets(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    *,
    comparison_contract: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Admit one explicitly designed pair; never calculate an effect or verdict."""

    reasons: list[str] = []
    try:
        contract = _normalize_comparison_contract(comparison_contract)
    except TelemetryError as exc:
        return {
            "schema_version": "identity_bound_session_comparison_admission_v1",
            "status": "excluded_identity_bound_pair",
            "eligible": False,
            "reasons": [str(exc)],
            "comparison_contract": None,
            "effect": None,
            "verdict": None,
            "proof": False,
            "acceptance": False,
            "authority": "session-memory-admission-only; validation-owner-and-eval-verdicts-external",
        }

    packets = {
        "left": left if isinstance(left, Mapping) else {},
        "right": right if isinstance(right, Mapping) else {},
    }
    integrity_ok: dict[str, bool] = {}
    for side, packet in packets.items():
        try:
            verify_packet_integrity(packet)
        except TelemetryError as exc:
            integrity_ok[side] = False
            reasons.append(f"{side}_{exc}")
        else:
            integrity_ok[side] = True
            eligibility = _packet_eligibility(packet)
            if eligibility.get("status") != "eligible_identity_packet":
                reasons.append(
                    f"{side}_eligibility_{eligibility.get('status') or 'unknown'}"
                )
                reasons.extend(
                    f"{side}_{reason}"
                    for reason in eligibility.get("reasons", [])
                    if reason
                )

    contexts: dict[str, dict[str, Any] | None] = {}
    for side, packet in packets.items():
        try:
            contexts[side] = _packet_scope_context(packet, side=side)
        except TelemetryError as exc:
            contexts[side] = None
            reasons.append(str(exc))
    if contexts["left"] is not None and contexts["right"] is not None:
        left_context = contexts["left"]
        right_context = contexts["right"]
        assert left_context is not None and right_context is not None
        for name in COMPARISON_SCOPE_FIELDS:
            if name == "episode_binding":
                left_value = packets["left"].get("episode_binding")
                right_value = packets["right"].get("episode_binding")
                left_present = isinstance(left_value, Mapping)
                right_present = isinstance(right_value, Mapping)
                differs = left_present != right_present or (
                    left_present and right_present and left_value != right_value
                )
                if differs and name not in contract["allowed_scope_differences"]:
                    reasons.append("episode_binding_exact_join_mismatch")
                continue
            if name == "source":
                differs = left_context["source"] != right_context["source"]
                if differs and name not in contract["allowed_scope_differences"]:
                    for source_name in SOURCE_FIELDS:
                        if left_context["source"][source_name] != right_context["source"][source_name]:
                            reasons.append(f"source_identity_mismatch:{source_name}")
            elif name == "projection":
                differs = left_context["projection"] != right_context["projection"]
                if differs and name not in contract["allowed_scope_differences"]:
                    reasons.append("scope_projection_mismatch")
            elif left_context[name] != right_context[name] and name not in contract["allowed_scope_differences"]:
                reasons.append(f"scope_{name}_mismatch")

    for name in IDENTITY_FIELDS:
        left_identity = packets["left"].get("identity", {}) if isinstance(packets["left"].get("identity"), Mapping) else {}
        right_identity = packets["right"].get("identity", {}) if isinstance(packets["right"].get("identity"), Mapping) else {}
        left_field = left_identity.get(name)
        right_field = right_identity.get(name)
        if _field_state(left_field) != "known":
            reasons.append(f"left_identity_{name}_{_field_state(left_field)}")
        if _field_state(right_field) != "known":
            reasons.append(f"right_identity_{name}_{_field_state(right_field)}")
        if (
            _field_state(left_field) == "known"
            and _field_state(right_field) == "known"
            and _field_value(left_field) != _field_value(right_field)
            and name not in contract["allowed_identity_differences"]
        ):
            reasons.append(f"identity_mismatch:{name}")

    role_binding = contract["role_binding"]
    for side, expected_value in (
        ("left", role_binding["left_value"]),
        ("right", role_binding["right_value"]),
    ):
        packet_identity = packets[side].get("identity")
        identity = packet_identity if isinstance(packet_identity, Mapping) else {}
        role_field = identity.get(role_binding["field"])
        if _field_state(role_field) != "known":
            reasons.append(
                f"{side}_role_binding_{role_binding['field']}_{_field_state(role_field)}"
            )
        elif _field_value(role_field) != expected_value:
            reasons.append(f"{side}_role_binding_mismatch:{role_binding['field']}")

    normalized_episode_bindings: dict[str, dict[str, Any] | None] = {}
    for side, packet in packets.items():
        review = packet.get("review", {}) if isinstance(packet.get("review"), Mapping) else {}
        if review.get("status") != "reviewed":
            reasons.append(f"{side}_review_{review.get('status') or 'unknown'}")
        scope = packet.get("scope", {}) if isinstance(packet.get("scope"), Mapping) else {}
        if scope.get("status") != "current":
            reasons.append(f"{side}_projection_{scope.get('status') or 'unknown'}")
        for name in ("prefix_identity", "publish_id"):
            projection_field = scope.get(name)
            if _field_state(projection_field) != "known":
                reasons.append(f"{side}_projection_identity_{name}_{_field_state(projection_field)}")
        methods = packet.get("methods", {}) if isinstance(packet.get("methods"), Mapping) else {}
        federation = methods.get("owner_receipt_federation", {})
        if not isinstance(federation, Mapping) or federation.get("status") != "admitted":
            reasons.append(
                f"{side}_owner_receipt_{federation.get('status') if isinstance(federation, Mapping) else 'unknown'}"
            )
        trajectory = packet.get("trajectory", {}) if isinstance(packet.get("trajectory"), Mapping) else {}
        if _field_state(trajectory.get("chain_id")) != "known":
            reasons.append(f"{side}_trajectory_chain_id_{_field_state(trajectory.get('chain_id'))}")
        steps = trajectory.get("steps") if isinstance(trajectory.get("steps"), Mapping) else {}
        for name in STEP_NAMES:
            step = steps.get(name) if isinstance(steps.get(name), Mapping) else {}
            if step.get("state") != "known":
                reasons.append(f"{side}_trajectory_{name}_{step.get('state') or 'unknown'}")
        cache = packet.get("cache", {}) if isinstance(packet.get("cache"), Mapping) else {}
        cache_posture = cache.get("posture")
        if _field_state(cache_posture) != "known":
            reasons.append(f"{side}_cache_posture_{_field_state(cache_posture)}")
        elif str(_field_value(cache_posture)).casefold() == "partial":
            reasons.append(f"{side}_cache_posture_partial_unadmitted")
        resource = packet.get("resource", {}) if isinstance(packet.get("resource"), Mapping) else {}
        if _field_state(resource.get("posture")) != "known":
            reasons.append(f"{side}_resource_posture_{_field_state(resource.get('posture'))}")

        episode_required = (
            packet.get("artifact_type") == EPISODE_PACKET_ARTIFACT
            or packet.get("schema_version") == EPISODE_PACKET_SCHEMA_VERSION
            or "episode_binding" in packet
        )
        if episode_required:
            if contexts.get(side) is None or not isinstance(packet.get("episode_binding"), Mapping):
                reasons.append(f"{side}_episode_binding_missing_or_unresolved")
            else:
                try:
                    admission = getattr(packet, "_component_admission", None)
                    normalized_episode_bindings[side] = validate_episode_binding(
                        packet["episode_binding"],
                        expected_context=contexts[side],
                        component_admission=admission,
                        require_owner_admission=True,
                    )
                except TelemetryError as exc:
                    reasons.append(f"{side}_{exc}")
                    normalized_episode_bindings[side] = None
        else:
            normalized_episode_bindings[side] = None

    left_requires_episode = normalized_episode_bindings.get("left") is not None
    right_requires_episode = normalized_episode_bindings.get("right") is not None
    if left_requires_episode != right_requires_episode:
        reasons.append("episode_binding_route_mismatch")

    unique_reasons = list(dict.fromkeys(reasons))
    return {
        "schema_version": "identity_bound_session_comparison_admission_v1",
        "status": "matched_identity_bound_pair" if not unique_reasons else "excluded_identity_bound_pair",
        "eligible": not unique_reasons,
        "reasons": unique_reasons,
        "comparison_contract": contract,
        "effect": None,
        "verdict": None,
        "proof": False,
        "acceptance": False,
        "authority": "session-memory-admission-only; validation-owner-and-eval-verdicts-external",
    }


def capture_receipts_from_events(events: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Read only a dedicated structured facet from generated events.

    Generic command, message, and result fields are intentionally ignored.  A
    malformed or private receipt is returned as no candidate so a caller can
    report an excluded packet without exposing its body.
    """

    return [
        entry["receipt"]
        for entry in capture_receipt_facets(events)
        if entry.get("status") == "admitted" and isinstance(entry.get("receipt"), dict)
    ]


def capture_receipt_facets(events: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Capture receipts with the exact event that carried each dedicated facet.

    The legacy adapter above intentionally returns only receipts for callers
    that already own a broader compatibility boundary.  Episode admission
    must use this stricter adapter so a receipt cannot be borrowed from a
    neighboring event or substituted across correlations.
    """

    captured: list[dict[str, Any]] = []
    for event in events:
        if not isinstance(event, Mapping):
            continue
        facets = event.get("facets") if isinstance(event.get("facets"), Mapping) else {}
        if "identity_bound_telemetry_receipt" not in facets:
            continue
        event_line = event.get("line")
        carrying_line = event_line if isinstance(event_line, int) and not isinstance(event_line, bool) and event_line >= 1 else None
        try:
            event_id = (
                _safe_ref(event.get("event_id"), "carrying_event.event_id")
                if isinstance(event.get("event_id"), str)
                else None
            )
        except TelemetryError:
            event_id = None
        try:
            carrying_correlation = (
                _safe_ref(event.get("correlation_id"), "carrying_event.correlation_id")
                if isinstance(event.get("correlation_id"), str)
                else None
            )
        except TelemetryError:
            carrying_correlation = None
        carrying_event = {
            "line": carrying_line,
            "event_id": event_id,
            "correlation_id": carrying_correlation,
        }
        candidate = facets.get("identity_bound_telemetry_receipt")
        owner_source_evidence = getattr(event, "_owner_source_evidence", None)
        if not isinstance(owner_source_evidence, OwnerSourceEvidence):
            captured.append(
                {
                    "status": "rejected",
                    "receipt": None,
                    "witness": None,
                    "carrying_event": None,
                    "rejection": "owner_event_source_evidence_missing",
                }
            )
            continue
        if not owner_source_evidence.is_persistent():
            captured.append(
                {
                    "status": "rejected",
                    "receipt": None,
                    "witness": None,
                    "carrying_event": None,
                    "rejection": "owner_event_source_evidence_not_persistent",
                }
            )
            continue
        if not owner_source_evidence.verify_event(event):
            captured.append(
                {
                    "status": "rejected",
                    "receipt": None,
                    "witness": None,
                    "carrying_event": None,
                    "rejection": "owner_event_source_evidence_mismatch",
                }
            )
            continue
        if carrying_event["correlation_id"] is None:
            captured.append(
                {
                    "status": "rejected",
                    "receipt": None,
                    "witness": None,
                    "carrying_event": carrying_event,
                    "rejection": "carrying_event_correlation_missing",
                }
            )
            continue
        if carrying_event["line"] is None or carrying_event["event_id"] is None:
            captured.append(
                {
                    "status": "rejected",
                    "receipt": None,
                    "witness": None,
                    "carrying_event": carrying_event,
                    "rejection": "carrying_event_identity_missing",
                }
            )
            continue
        try:
            receipt = _normalize_receipt_shape(candidate, verify_id=True)
            receipt_correlation = _field_value(receipt["binding"]["correlation_id"])
            if receipt_correlation != carrying_event["correlation_id"]:
                raise TelemetryError("carrying_event_correlation_mismatch")
        except TelemetryError as exc:
            captured.append(
                {
                    "status": "rejected",
                    "receipt": None,
                    "witness": None,
                    "carrying_event": carrying_event,
                    "rejection": str(exc),
                }
            )
            continue
        witness = _issue_carrying_event_witness(
            receipt,
            carrying_event,
            owner_source_evidence=owner_source_evidence,
        )
        captured.append(
            {
                "status": "admitted",
                "receipt": receipt,
                "witness": witness,
                "carrying_event": witness.public_event(),
                "rejection": None,
            }
        )
    return captured


def load_owner_receipt(path: str) -> dict[str, Any]:
    """Load one public-safe receipt file; never read a transcript body."""

    try:
        with open(path, encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise TelemetryError(f"owner_receipt_unreadable:{type(exc).__name__}") from exc
    return _normalize_receipt_shape(value, verify_id=True)
