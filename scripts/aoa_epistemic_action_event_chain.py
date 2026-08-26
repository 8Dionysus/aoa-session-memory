#!/usr/bin/env python3
"""Portable, privacy-safe Epistemic Action event-chain source.

The ledger in this module is deliberately smaller than the session
projection.  It stores only public-safe identifiers, opaque SHA-256 digests,
typed state, and content-addressed relations.  Raw prompts, tool arguments,
tool outputs, transcript paths, and free-form notes are not accepted by the
event contract.

The chain is append-only JSONL.  A lock protects one append, an optimistic
head check detects stale writers, and every record carries a predecessor and
record digest.  Identical logical appends are idempotent; a different record
with the same logical identity is a conflict.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


EPISTEMIC_ACTION_SCHEMA_VERSION = "aoa_epistemic_action_event_chain_v2"
EPISTEMIC_ACTION_EVENT_SCHEMA_VERSION = "aoa_epistemic_action_event_v2"
EPISTEMIC_ACTION_ARTIFACT_TYPE = "epistemic_action_event_chain"
EPISTEMIC_ACTION_CLAIM_CEILING = "storage_source_correctness_candidate_only"
EPISTEMIC_ACTION_CANDIDATE_CLAIM_CEILING = (
    "candidate_only_no_model_update_no_benefit"
)
EPISTEMIC_ACTION_GENESIS = "genesis"

_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_TIMESTAMP_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$"
)

EPISTEMIC_ACTION_EVENT_TYPES = frozenset(
    {
        "prediction_commitment",
        "action_binding",
        "observation",
        "observation_conflict",
        "discrepancy",
        "model_update_candidate",
        "refusal",
    }
)
EPISTEMIC_ACTION_STATES = frozenset(
    {
        "committed",
        "bound",
        "observed",
        "ready",
        "unknown",
        "ambiguous",
        "refused",
        "shadow_only",
    }
)
EPISTEMIC_ACTION_OBSERVATION_STATUSES = frozenset(
    {"observed", "missing", "unknown", "ambiguous", "refused"}
)
EPISTEMIC_ACTION_DISCREPANCY_KINDS = frozenset(
    {"match", "partial_match", "mismatch", "unknown", "ambiguous"}
)
EPISTEMIC_ACTION_UPDATE_KINDS = frozenset(
    {"review_prediction", "withhold_update", "inspect_only"}
)
EPISTEMIC_ACTION_REASON_CODES = frozenset(
    {
        "action_before_prediction",
        "action_binding_conflict",
        "chain_scope_mismatch",
        "compaction_boundary",
        "conflicting_observation",
        "concurrency_conflict",
        "digest_invalid",
        "digest_required",
        "duplicate_observation_conflict",
        "duplicate_prediction_conflict",
        "event_digest_mismatch",
        "event_identity_conflict",
        "event_predecessor_mismatch",
        "event_sequence_gap",
        "event_shape_invalid",
        "event_type_invalid",
        "interrupted",
        "missing_action",
        "missing_observation",
        "missing_prediction",
        "model_update_conflict",
        "observation_conflict",
        "observation_digest_forbidden",
        "observation_status_invalid",
        "post_hoc_prediction",
        "prediction_conflict",
        "prediction_action_mismatch",
        "prediction_immutable_conflict",
        "pre_action_marker_required",
        "prediction_fields_invalid",
        "observation_recorded",
        "safe_identifier_invalid",
        "safe_identifier_required",
        "store_not_regular",
        "timestamp_invalid",
        "attempt_identity_conflict",
        "tool_use_identity_conflict",
        "unsupported_event_state",
        "unsupported_reason_code",
    }
)

_EVENT_FIELDS = frozenset(
    {
        "schema_version",
        "event_type",
        "event_id",
        "sequence",
        "prev_event_digest",
        "event_digest",
        "state",
        "created_at",
        "session_id",
        "turn_id",
        "request_id",
        "attempt_id",
        "tool_use_id",
        "prediction_id",
        "prediction_commitment_digest",
        "pre_action_marker",
        "observation_window_digest",
        "hypothesis_digest",
        "expected_change_digest",
        "falsifier_digest",
        "confidence",
        "action_plan_digest",
        "action_id",
        "action_digest",
        "action_kind",
        "effect_class",
        "action_started_at",
        "observation_id",
        "expected_observation_digest",
        "observation_digest",
        "observed_observation_digest",
        "observation_status",
        "evidence_ref_ids",
        "reason_code",
        "related_event_ids",
        "source_event_ids",
        "discrepancy_kind",
        "candidate_id",
        "candidate_status",
        "alternative_explanation_digest",
        "model_update_digest",
        "next_distinguishing_action_digest",
        "update_kind",
        "claim_ceiling",
    }
)
_VOLATILE_EVENT_FIELDS = frozenset(
    {"sequence", "prev_event_digest", "event_digest", "created_at"}
)


class EpistemicActionError(ValueError):
    """Base error whose fields are safe to return to an owner reviewer."""

    def __init__(
        self,
        reason_code: str,
        *,
        state: str = "refused",
        event: dict[str, Any] | None = None,
    ) -> None:
        self.reason_code = reason_code
        self.state = state
        self.event = dict(event) if isinstance(event, dict) else None
        super().__init__(reason_code)

    def result(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "ok": False,
            "state": self.state,
            "reason_code": self.reason_code,
        }
        if self.event is not None:
            result["event"] = dict(self.event)
        return result


class EpistemicActionPrivacyError(EpistemicActionError):
    """Raised before an unsafe identifier or digest can enter the ledger."""


class EpistemicActionOrderingError(EpistemicActionError):
    """Raised when a prediction/action/observation order is not admissible."""


class EpistemicActionConflictError(EpistemicActionError):
    """Raised for immutable, duplicate, or contradictory evidence."""


class EpistemicActionConcurrencyError(EpistemicActionError):
    """Raised when a writer's observed chain head is stale."""


class EpistemicActionIntegrityError(EpistemicActionError):
    """Raised when replay cannot verify the persisted hash chain."""


class EpistemicActionHead:
    __slots__ = ("sequence", "event_id", "event_digest")

    def __init__(
        self,
        sequence: int,
        event_id: str | None,
        event_digest: str,
    ) -> None:
        self.sequence = sequence
        self.event_id = event_id
        self.event_digest = event_digest

    def as_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "event_id": self.event_id,
            "event_digest": self.event_digest,
        }


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def _hash_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def epistemic_digest(value: str | bytes) -> str:
    """Return an opaque digest without retaining the input in an event."""

    if isinstance(value, str):
        return _hash_bytes(value.encode("utf-8"))
    if isinstance(value, bytes):
        return _hash_bytes(value)
    raise EpistemicActionPrivacyError("digest_required")


def epistemic_public_id(namespace: str, value: str | bytes) -> str:
    """Derive a stable public-safe identifier from an external value.

    Callers should use this for private session, turn, action, or observation
    identities.  The value is used only while deriving the digest and is never
    serialized by this module.
    """

    namespace_value = _safe_identifier(namespace, "namespace")
    if isinstance(value, str):
        raw = value.encode("utf-8")
    elif isinstance(value, bytes):
        raw = value
    else:
        raise EpistemicActionPrivacyError("safe_identifier_required")
    digest = hashlib.sha256(namespace_value.encode("ascii") + b"\0" + raw)
    return "id:" + digest.hexdigest()


def _safe_identifier(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise EpistemicActionPrivacyError("safe_identifier_required")
    if not _IDENTIFIER_RE.fullmatch(value):
        raise EpistemicActionPrivacyError("safe_identifier_invalid")
    return value


def _safe_digest(value: Any, field: str, *, required: bool = True) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str):
        raise EpistemicActionPrivacyError("digest_required")
    if not _DIGEST_RE.fullmatch(value):
        raise EpistemicActionPrivacyError("digest_invalid")
    return value


def _safe_confidence(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EpistemicActionPrivacyError("prediction_fields_invalid")
    if value != value or value < 0 or value > 1:
        raise EpistemicActionPrivacyError("prediction_fields_invalid")
    return float(value)


def _reject_duplicate_members(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object member")
        result[key] = value
    return result


def _safe_reason_code(value: Any, *, default: str) -> str:
    if value is None or value == "":
        return default
    if not isinstance(value, str) or value not in EPISTEMIC_ACTION_REASON_CODES:
        raise EpistemicActionPrivacyError("unsupported_reason_code")
    return value


def _safe_timestamp(value: Any = None) -> str:
    if value is None:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if not isinstance(value, str) or not _TIMESTAMP_RE.fullmatch(value):
        raise EpistemicActionPrivacyError("timestamp_invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EpistemicActionPrivacyError("timestamp_invalid") from exc
    if parsed.tzinfo is None:
        raise EpistemicActionPrivacyError("timestamp_invalid")
    normalized = parsed.astimezone(timezone.utc).replace(microsecond=0)
    result = normalized.strftime("%Y-%m-%dT%H:%M:%SZ")
    if result != value:
        raise EpistemicActionPrivacyError("timestamp_invalid")
    return result


def _derived_id(prefix: str, value: Any) -> str:
    material = _canonical_json(value).encode("utf-8")
    return f"{prefix}:{hashlib.sha256(material).hexdigest()}"


def _event_digest(event: dict[str, Any]) -> str:
    material = {
        key: value
        for key, value in event.items()
        if key != "event_digest"
    }
    return _hash_bytes(_canonical_json(material).encode("utf-8"))


def _event_semantics(event: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in event.items()
        if key not in _VOLATILE_EVENT_FIELDS
    }


def _unique_safe_ids(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or len(value) > 8:
        raise EpistemicActionIntegrityError("event_shape_invalid")
    result = [_safe_identifier(item, field) for item in value]
    if len(set(result)) != len(result):
        raise EpistemicActionIntegrityError("event_shape_invalid")
    return result


def _validate_event_shape(
    event: Any,
    *,
    expected_session_id: str | None = None,
    expected_turn_id: str | None = None,
) -> dict[str, Any]:
    if not isinstance(event, dict):
        raise EpistemicActionIntegrityError("event_shape_invalid")
    if set(event) - _EVENT_FIELDS:
        raise EpistemicActionIntegrityError("event_shape_invalid")
    required = {
        "schema_version",
        "event_type",
        "event_id",
        "sequence",
        "prev_event_digest",
        "event_digest",
        "state",
        "created_at",
        "session_id",
        "turn_id",
    }
    if not required <= set(event):
        raise EpistemicActionIntegrityError("event_shape_invalid")
    if event.get("schema_version") != EPISTEMIC_ACTION_EVENT_SCHEMA_VERSION:
        raise EpistemicActionIntegrityError("event_shape_invalid")
    event_type = event.get("event_type")
    if event_type not in EPISTEMIC_ACTION_EVENT_TYPES:
        raise EpistemicActionIntegrityError("event_type_invalid")
    if event.get("state") not in EPISTEMIC_ACTION_STATES:
        raise EpistemicActionIntegrityError("unsupported_event_state")
    if not isinstance(event.get("sequence"), int) or isinstance(
        event.get("sequence"), bool
    ):
        raise EpistemicActionIntegrityError("event_shape_invalid")
    if int(event["sequence"]) < 1:
        raise EpistemicActionIntegrityError("event_shape_invalid")
    session_id = _safe_identifier(event.get("session_id"), "session_id")
    turn_id = _safe_identifier(event.get("turn_id"), "turn_id")
    if expected_session_id is not None and session_id != expected_session_id:
        raise EpistemicActionIntegrityError("chain_scope_mismatch")
    if expected_turn_id is not None and turn_id != expected_turn_id:
        raise EpistemicActionIntegrityError("chain_scope_mismatch")
    _safe_identifier(event.get("event_id"), "event_id")
    _safe_timestamp(event.get("created_at"))
    previous = event.get("prev_event_digest")
    if previous != EPISTEMIC_ACTION_GENESIS:
        _safe_digest(previous, "prev_event_digest")
    _safe_digest(event.get("event_digest"), "event_digest")
    for field in (
        "request_id",
        "attempt_id",
        "tool_use_id",
        "prediction_id",
        "action_id",
        "action_kind",
        "effect_class",
        "observation_id",
        "candidate_id",
    ):
        if field in event:
            _safe_identifier(event[field], field)
    for field in (
        "prediction_commitment_digest",
        "pre_action_marker",
        "observation_window_digest",
        "hypothesis_digest",
        "expected_change_digest",
        "falsifier_digest",
        "action_plan_digest",
        "action_digest",
        "action_started_at",
        "expected_observation_digest",
        "observation_digest",
        "observed_observation_digest",
        "alternative_explanation_digest",
        "model_update_digest",
        "next_distinguishing_action_digest",
    ):
        if field == "action_started_at":
            if field in event:
                _safe_timestamp(event[field])
        elif field in event:
            _safe_digest(event[field], field)
    if "confidence" in event:
        _safe_confidence(event["confidence"])
    if "observation_status" in event and event["observation_status"] not in EPISTEMIC_ACTION_OBSERVATION_STATUSES:
        raise EpistemicActionIntegrityError("observation_status_invalid")
    if "reason_code" in event:
        if event["reason_code"] not in EPISTEMIC_ACTION_REASON_CODES:
            raise EpistemicActionIntegrityError("unsupported_reason_code")
    for field in ("related_event_ids", "source_event_ids", "evidence_ref_ids"):
        if field in event:
            _unique_safe_ids(event[field], field)
    if "discrepancy_kind" in event and event["discrepancy_kind"] not in EPISTEMIC_ACTION_DISCREPANCY_KINDS:
        raise EpistemicActionIntegrityError("event_shape_invalid")
    if "candidate_status" in event and event["candidate_status"] not in {
        "shadow_only",
        "unknown",
        "ambiguous",
        "refused",
    }:
        raise EpistemicActionIntegrityError("event_shape_invalid")
    if "update_kind" in event and event["update_kind"] not in EPISTEMIC_ACTION_UPDATE_KINDS:
        raise EpistemicActionIntegrityError("event_shape_invalid")
    if "claim_ceiling" in event and event["claim_ceiling"] != EPISTEMIC_ACTION_CANDIDATE_CLAIM_CEILING:
        raise EpistemicActionIntegrityError("event_shape_invalid")
    if event_type == "prediction_commitment" and not {
        "request_id",
        "attempt_id",
        "prediction_id",
        "prediction_commitment_digest",
        "action_id",
        "expected_observation_digest",
        "pre_action_marker",
        "observation_window_digest",
        "hypothesis_digest",
        "expected_change_digest",
        "falsifier_digest",
        "confidence",
        "action_plan_digest",
    } <= set(event):
        raise EpistemicActionIntegrityError("event_shape_invalid")
    if event_type == "action_binding" and not {
        "request_id",
        "attempt_id",
        "prediction_id",
        "action_id",
        "action_digest",
        "action_kind",
        "effect_class",
        "action_started_at",
    } <= set(event):
        raise EpistemicActionIntegrityError("event_shape_invalid")
    if event_type in {"observation", "observation_conflict"} and not {
        "request_id",
        "attempt_id",
        "action_id",
        "observation_id",
        "observation_status",
        "evidence_ref_ids",
    } <= set(event):
        raise EpistemicActionIntegrityError("event_shape_invalid")
    if event_type == "discrepancy" and not {
        "request_id",
        "attempt_id",
        "action_id",
        "discrepancy_kind",
        "source_event_ids",
    } <= set(event):
        raise EpistemicActionIntegrityError("event_shape_invalid")
    if event_type == "model_update_candidate" and not {
        "request_id",
        "attempt_id",
        "action_id",
        "candidate_id",
        "candidate_status",
        "discrepancy_kind",
        "update_kind",
        "source_event_ids",
        "claim_ceiling",
        "hypothesis_digest",
        "expected_change_digest",
        "falsifier_digest",
        "confidence",
        "action_plan_digest",
        "observation_window_digest",
        "pre_action_marker",
    } <= set(event):
        raise EpistemicActionIntegrityError("event_shape_invalid")
    if event_type == "refusal" and "reason_code" not in event:
        raise EpistemicActionIntegrityError("event_shape_invalid")
    status = event.get("observation_status")
    if status is not None:
        if status == "observed" and "observation_digest" not in event:
            raise EpistemicActionIntegrityError("event_shape_invalid")
        if status != "observed" and "observation_digest" in event:
            raise EpistemicActionIntegrityError("event_shape_invalid")
    expected_state = {
        "prediction_commitment": "committed",
        "action_binding": "bound",
        "observation": {
            "observed": "observed",
            "missing": "unknown",
            "unknown": "unknown",
            "ambiguous": "ambiguous",
            "refused": "refused",
        },
        "observation_conflict": "ambiguous",
        "discrepancy": {
            "match": "ready",
            "partial_match": "ready",
            "mismatch": "ready",
            "unknown": "unknown",
            "ambiguous": "ambiguous",
        },
        "model_update_candidate": "shadow_only",
    }.get(event_type)
    if event_type == "observation":
        if event.get("state") != expected_state.get(status):
            raise EpistemicActionIntegrityError("event_shape_invalid")
    elif event_type == "discrepancy":
        if event.get("state") != expected_state.get(
            event.get("discrepancy_kind")
        ):
            raise EpistemicActionIntegrityError("event_shape_invalid")
    elif expected_state is not None and event.get("state") != expected_state:
        raise EpistemicActionIntegrityError("event_shape_invalid")
    return event


def _replay_records(
    records: Iterable[Any],
    *,
    expected_session_id: str | None = None,
    expected_turn_id: str | None = None,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    expected_sequence = 1
    previous_digest = EPISTEMIC_ACTION_GENESIS
    seen_event_ids: set[str] = set()
    for raw in records:
        event = _validate_event_shape(
            raw,
            expected_session_id=expected_session_id,
            expected_turn_id=expected_turn_id,
        )
        if event["sequence"] != expected_sequence:
            raise EpistemicActionIntegrityError("event_sequence_gap")
        if event["prev_event_digest"] != previous_digest:
            raise EpistemicActionIntegrityError("event_predecessor_mismatch")
        if event["event_id"] in seen_event_ids:
            raise EpistemicActionIntegrityError("event_shape_invalid")
        if event["event_digest"] != _event_digest(event):
            raise EpistemicActionIntegrityError("event_digest_mismatch")
        prior_by_id = {
            str(item["event_id"]): item for item in result
        }
        relation_ids = [
            str(item)
            for field in ("related_event_ids", "source_event_ids")
            for item in event.get(field, [])
        ]
        for relation_id in relation_ids:
            related = prior_by_id.get(relation_id)
            if related is None:
                raise EpistemicActionIntegrityError("event_predecessor_mismatch")
        event_type = event["event_type"]
        related_events = [
            prior_by_id[item]
            for item in event.get("related_event_ids", [])
            if item in prior_by_id
        ]
        if event_type == "action_binding":
            predictions = [
                item
                for item in related_events
                if item.get("event_type") == "prediction_commitment"
            ]
            if len(predictions) != 1 or (
                predictions[0].get("prediction_id")
                != event.get("prediction_id")
                or predictions[0].get("action_id") != event.get("action_id")
                or predictions[0].get("request_id")
                != event.get("request_id")
                or predictions[0].get("attempt_id")
                != event.get("attempt_id")
                or predictions[0].get("tool_use_id")
                != event.get("tool_use_id")
                or predictions[0].get("prediction_commitment_digest")
                != event.get("prediction_commitment_digest")
            ):
                raise EpistemicActionIntegrityError("event_predecessor_mismatch")
            if event.get("action_started_at", "") < predictions[0].get(
                "created_at", ""
            ):
                raise EpistemicActionIntegrityError("event_predecessor_mismatch")
        elif event_type in {"observation", "observation_conflict"}:
            actions = [
                item
                for item in related_events
                if item.get("event_type") == "action_binding"
            ]
            if event_type == "observation_conflict":
                actions = [
                    item
                    for item in related_events
                    if item.get("action_id") == event.get("action_id")
                ]
            if event_type == "observation" and (
                len(actions) != 1
                or actions[0].get("action_id") != event.get("action_id")
                or actions[0].get("request_id") != event.get("request_id")
                or actions[0].get("attempt_id") != event.get("attempt_id")
                or actions[0].get("tool_use_id") != event.get("tool_use_id")
            ):
                raise EpistemicActionIntegrityError("event_predecessor_mismatch")
            if event_type == "observation_conflict" and not actions:
                raise EpistemicActionIntegrityError("event_predecessor_mismatch")
        elif event_type == "discrepancy":
            source_events = [
                prior_by_id[item]
                for item in event.get("source_event_ids", [])
                if item in prior_by_id
            ]
            if any(
                item.get("request_id") != event.get("request_id")
                or item.get("attempt_id") != event.get("attempt_id")
                or item.get("tool_use_id") != event.get("tool_use_id")
                for item in source_events
                if item.get("event_type")
                in {"prediction_commitment", "action_binding"}
            ):
                raise EpistemicActionIntegrityError("event_predecessor_mismatch")
            if not any(
                item.get("event_type") == "prediction_commitment"
                and item.get("action_id") == event.get("action_id")
                for item in source_events
            ) or not any(
                item.get("event_type") == "action_binding"
                and item.get("action_id") == event.get("action_id")
                for item in source_events
            ):
                raise EpistemicActionIntegrityError("event_predecessor_mismatch")
        elif event_type == "model_update_candidate":
            source_events = [
                prior_by_id[item]
                for item in event.get("source_event_ids", [])
                if item in prior_by_id
            ]
            if any(
                item.get("request_id") != event.get("request_id")
                or item.get("attempt_id") != event.get("attempt_id")
                or item.get("tool_use_id") != event.get("tool_use_id")
                for item in source_events
                if item.get("event_type")
                in {"prediction_commitment", "action_binding"}
            ):
                raise EpistemicActionIntegrityError("event_predecessor_mismatch")
            if not any(
                item.get("event_type") == "discrepancy"
                and item.get("action_id") == event.get("action_id")
                and item.get("discrepancy_kind")
                == event.get("discrepancy_kind")
                for item in source_events
            ):
                raise EpistemicActionIntegrityError("event_predecessor_mismatch")
        seen_event_ids.add(event["event_id"])
        result.append(dict(event))
        expected_sequence += 1
        previous_digest = event["event_digest"]
    return result


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    if path.is_symlink() or not path.is_file():
        raise EpistemicActionIntegrityError("store_not_regular")
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise EpistemicActionIntegrityError("store_not_regular") from exc
    if not text:
        return []
    records: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not line.strip():
            raise EpistemicActionIntegrityError("event_shape_invalid")
        try:
            record = json.loads(line, object_pairs_hook=_reject_duplicate_members)
        except (ValueError, UnicodeDecodeError) as exc:
            raise EpistemicActionIntegrityError("event_shape_invalid") from exc
        records.append(record)
    return records


def _chain_status_for_events(events: Iterable[dict[str, Any]]) -> str:
    records = list(events)
    if any(event.get("state") == "ambiguous" for event in records):
        return "ambiguous"
    if any(event.get("state") == "unknown" for event in records):
        return "unknown"
    if any(event.get("state") == "refused" for event in records):
        return "refused"
    if any(
        event.get("event_type") == "model_update_candidate"
        for event in records
    ):
        return "shadow_only"
    if records:
        return "ready"
    return "unknown"


class _StoreLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.handle: Any = None

    def __enter__(self) -> "_StoreLock":
        if self.path.is_symlink():
            raise EpistemicActionIntegrityError("store_not_regular")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(
            self.path,
            os.O_CREAT | os.O_RDWR,
            0o600,
        )
        os.fchmod(descriptor, 0o600)
        self.handle = os.fdopen(descriptor, "r+")
        fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self.handle is not None:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            self.handle.close()
            self.handle = None


class EpistemicActionChain:
    """An append-only prediction/action/observation evidence chain."""

    def __init__(
        self,
        store_path: str | Path,
        *,
        session_id: str | None = None,
        turn_id: str | None = None,
    ) -> None:
        self.store_path = Path(store_path)
        if self.store_path.is_symlink():
            raise EpistemicActionIntegrityError("store_not_regular")
        supplied_session = (
            _safe_identifier(session_id, "session_id")
            if session_id is not None
            else None
        )
        supplied_turn = (
            _safe_identifier(turn_id, "turn_id")
            if turn_id is not None
            else None
        )
        records = _read_jsonl(self.store_path)
        if records:
            first = _validate_event_shape(records[0])
            self.session_id = str(first["session_id"])
            self.turn_id = str(first["turn_id"])
            if supplied_session is not None and supplied_session != self.session_id:
                raise EpistemicActionIntegrityError("chain_scope_mismatch")
            if supplied_turn is not None and supplied_turn != self.turn_id:
                raise EpistemicActionIntegrityError("chain_scope_mismatch")
        else:
            if supplied_session is None or supplied_turn is None:
                raise EpistemicActionPrivacyError("safe_identifier_required")
            self.session_id = supplied_session
            self.turn_id = supplied_turn
        self._events = _replay_records(
            records,
            expected_session_id=self.session_id,
            expected_turn_id=self.turn_id,
        )
        self._observed_sequence = len(self._events)
        self.chain_id = _derived_id(
            "chain",
            {"session_id": self.session_id, "turn_id": self.turn_id},
        )

    @classmethod
    def create(
        cls,
        store_path: str | Path,
        *,
        session_id: str,
        turn_id: str,
    ) -> "EpistemicActionChain":
        return cls(store_path, session_id=session_id, turn_id=turn_id)

    @classmethod
    def load(
        cls,
        store_path: str | Path,
        *,
        session_id: str | None = None,
        turn_id: str | None = None,
    ) -> "EpistemicActionChain":
        return cls(
            store_path,
            session_id=session_id,
            turn_id=turn_id,
        )

    @property
    def events(self) -> list[dict[str, Any]]:
        return [dict(event) for event in self._events]

    @property
    def head(self) -> EpistemicActionHead:
        if not self._events:
            return EpistemicActionHead(0, None, EPISTEMIC_ACTION_GENESIS)
        event = self._events[-1]
        return EpistemicActionHead(
            int(event["sequence"]),
            str(event["event_id"]),
            str(event["event_digest"]),
        )

    def refresh(self) -> "EpistemicActionChain":
        records = _read_jsonl(self.store_path)
        self._events = _replay_records(
            records,
            expected_session_id=self.session_id,
            expected_turn_id=self.turn_id,
        )
        self._observed_sequence = len(self._events)
        return self

    def _lock_path(self) -> Path:
        return self.store_path.with_name(self.store_path.name + ".lock")

    def _append_event(
        self,
        *,
        event_type: str,
        state: str,
        fields: dict[str, Any],
        identity: Any,
        created_at: str | None = None,
        expected_sequence: int | None = None,
    ) -> tuple[dict[str, Any], bool]:
        if event_type not in EPISTEMIC_ACTION_EVENT_TYPES:
            raise EpistemicActionError("event_type_invalid")
        if state not in EPISTEMIC_ACTION_STATES:
            raise EpistemicActionError("unsupported_event_state")
        logical: dict[str, Any] = {
            "schema_version": EPISTEMIC_ACTION_EVENT_SCHEMA_VERSION,
            "event_type": event_type,
            "event_id": _derived_id(
                "event",
                {"event_type": event_type, "identity": identity},
            ),
            "state": state,
            "created_at": _safe_timestamp(created_at),
            "session_id": self.session_id,
            "turn_id": self.turn_id,
        }
        logical.update(fields)
        with _StoreLock(self._lock_path()):
            current_records = _read_jsonl(self.store_path)
            current = _replay_records(
                current_records,
                expected_session_id=self.session_id,
                expected_turn_id=self.turn_id,
            )
            existing = next(
                (
                    event
                    for event in current
                    if event.get("event_id") == logical["event_id"]
                ),
                None,
            )
            if existing is not None:
                if _event_semantics(existing) == _event_semantics(logical):
                    self._events = current
                    self._observed_sequence = len(current)
                    return dict(existing), False
                raise EpistemicActionConflictError(
                    "event_identity_conflict",
                    state="ambiguous",
                )
            observed_sequence = len(current)
            required_sequence = (
                observed_sequence
                if expected_sequence is None
                else expected_sequence
            )
            if not isinstance(required_sequence, int) or isinstance(
                required_sequence, bool
            ):
                raise EpistemicActionConcurrencyError("concurrency_conflict")
            if required_sequence != self._observed_sequence:
                raise EpistemicActionConcurrencyError("concurrency_conflict")
            if required_sequence != observed_sequence:
                raise EpistemicActionConcurrencyError("concurrency_conflict")
            event = {
                **logical,
                "sequence": observed_sequence + 1,
                "prev_event_digest": (
                    current[-1]["event_digest"]
                    if current
                    else EPISTEMIC_ACTION_GENESIS
                ),
            }
            event["event_digest"] = _event_digest(event)
            _validate_event_shape(event)
            self.store_path.parent.mkdir(parents=True, exist_ok=True)
            if self.store_path.exists() and (
                self.store_path.is_symlink() or not self.store_path.is_file()
            ):
                raise EpistemicActionIntegrityError("store_not_regular")
            with self.store_path.open("a", encoding="utf-8") as handle:
                handle.write(_canonical_json(event) + "\n")
                handle.flush()
                os.fchmod(handle.fileno(), 0o600)
                os.fsync(handle.fileno())
            self._events = [*current, event]
            self._observed_sequence = len(self._events)
            return dict(event), True

    def _record_refusal(
        self,
        reason_code: str,
        *,
        related_event_ids: Iterable[str] = (),
        fields: dict[str, Any] | None = None,
        state: str = "refused",
    ) -> dict[str, Any]:
        reason = _safe_reason_code(reason_code, default="event_shape_invalid")
        related = list(related_event_ids)
        for item in related:
            _safe_identifier(item, "related_event_ids")
        event_fields: dict[str, Any] = {
            "reason_code": reason,
            "related_event_ids": related,
        }
        if fields:
            event_fields.update(fields)
        event, _created = self._append_event(
            event_type="refusal",
            state=state,
            fields=event_fields,
            identity={
                "reason_code": reason,
                "related_event_ids": related,
                "fields": fields or {},
            },
        )
        return event

    def _prediction_events(self) -> list[dict[str, Any]]:
        return [
            event
            for event in self._events
            if event.get("event_type") == "prediction_commitment"
        ]

    def _action_events(self) -> list[dict[str, Any]]:
        return [
            event
            for event in self._events
            if event.get("event_type") == "action_binding"
        ]

    def _observation_events(self, action_id: str) -> list[dict[str, Any]]:
        return [
            event
            for event in self._events
            if event.get("event_type") == "observation"
            and event.get("action_id") == action_id
        ]

    def _candidate_events(self, action_id: str) -> list[dict[str, Any]]:
        return [
            event
            for event in self._events
            if event.get("event_type") == "model_update_candidate"
            and event.get("action_id") == action_id
        ]

    def commit_prediction(
        self,
        action_id: str,
        expected_observation_digest: str | None = None,
        *,
        request_id: str,
        attempt_id: str,
        pre_action_marker: str,
        observation_window_digest: str,
        hypothesis_digest: str,
        expected_change_digest: str,
        falsifier_digest: str,
        confidence: float,
        action_plan_digest: str,
        tool_use_id: str | None = None,
        expected_digest: str | None = None,
        prediction_id: str | None = None,
        created_at: str | None = None,
        expected_sequence: int | None = None,
    ) -> dict[str, Any]:
        """Commit a prediction before an action can be bound."""

        safe_request_id = _safe_identifier(request_id, "request_id")
        safe_attempt_id = _safe_identifier(attempt_id, "attempt_id")
        safe_action_id = _safe_identifier(action_id, "action_id")
        safe_tool_use_id = (
            _safe_identifier(tool_use_id, "tool_use_id")
            if tool_use_id is not None
            else None
        )
        safe_pre_action_marker = _safe_digest(
            pre_action_marker,
            "pre_action_marker",
        )
        safe_window = _safe_digest(
            observation_window_digest,
            "observation_window_digest",
        )
        safe_hypothesis = _safe_digest(hypothesis_digest, "hypothesis_digest")
        safe_expected_change = _safe_digest(
            expected_change_digest,
            "expected_change_digest",
        )
        safe_falsifier = _safe_digest(falsifier_digest, "falsifier_digest")
        safe_confidence = _safe_confidence(confidence)
        safe_action_plan = _safe_digest(action_plan_digest, "action_plan_digest")
        assert (
            safe_pre_action_marker is not None
            and safe_window is not None
            and safe_hypothesis is not None
            and safe_expected_change is not None
            and safe_falsifier is not None
            and safe_action_plan is not None
        )
        if expected_observation_digest is None:
            expected_observation_digest = expected_digest
        elif expected_digest is not None and expected_digest != expected_observation_digest:
            raise EpistemicActionPrivacyError("digest_invalid")
        safe_expected = _safe_digest(
            expected_observation_digest,
            "expected_observation_digest",
        )
        assert safe_expected is not None
        safe_prediction_id = (
            _safe_identifier(prediction_id, "prediction_id")
            if prediction_id is not None
            else _derived_id(
                "prediction",
                {
                    "request_id": safe_request_id,
                    "attempt_id": safe_attempt_id,
                    "action_id": safe_action_id,
                    "tool_use_id": safe_tool_use_id,
                    "expected_observation_digest": safe_expected,
                    "pre_action_marker": safe_pre_action_marker,
                    "observation_window_digest": safe_window,
                    "hypothesis_digest": safe_hypothesis,
                    "expected_change_digest": safe_expected_change,
                    "falsifier_digest": safe_falsifier,
                    "confidence": safe_confidence,
                    "action_plan_digest": safe_action_plan,
                },
            )
        )
        existing_prediction = next(
            (
                event
                for event in self._prediction_events()
                if event.get("prediction_id") == safe_prediction_id
            ),
            None,
        )
        if existing_prediction is not None:
            expected_semantics = {
                "request_id": safe_request_id,
                "attempt_id": safe_attempt_id,
                "action_id": safe_action_id,
                "tool_use_id": safe_tool_use_id,
                "expected_observation_digest": safe_expected,
                "pre_action_marker": safe_pre_action_marker,
                "observation_window_digest": safe_window,
                "hypothesis_digest": safe_hypothesis,
                "expected_change_digest": safe_expected_change,
                "falsifier_digest": safe_falsifier,
                "confidence": safe_confidence,
                "action_plan_digest": safe_action_plan,
                "prediction_id": safe_prediction_id,
            }
            actual_semantics = {
                key: existing_prediction.get(key)
                for key in expected_semantics
            }
            if actual_semantics == expected_semantics:
                return dict(existing_prediction)
            refusal = self._record_refusal(
                "prediction_immutable_conflict",
                related_event_ids=[str(existing_prediction["event_id"])],
                fields={
                    "prediction_id": safe_prediction_id,
                    "action_id": safe_action_id,
                    "expected_observation_digest": safe_expected,
                },
                state="ambiguous",
            )
            raise EpistemicActionConflictError(
                "prediction_immutable_conflict",
                state="ambiguous",
                event=refusal,
            )
        action_event = next(
            (
                event
                for event in self._action_events()
                if event.get("action_id") == safe_action_id
            ),
            None,
        )
        same_action_predictions = [
            event
            for event in self._prediction_events()
            if event.get("action_id") == safe_action_id
        ]
        if action_event is not None:
            refusal = self._record_refusal(
                "post_hoc_prediction",
                related_event_ids=[str(action_event["event_id"])],
                fields={"action_id": safe_action_id},
            )
            raise EpistemicActionOrderingError(
                "post_hoc_prediction",
                event=refusal,
            )
        if same_action_predictions:
            refusal = self._record_refusal(
                "duplicate_prediction_conflict",
                related_event_ids=[
                    str(event["event_id"]) for event in same_action_predictions
                ],
                fields={
                    "prediction_id": safe_prediction_id,
                    "action_id": safe_action_id,
                    "expected_observation_digest": safe_expected,
                },
                state="ambiguous",
            )
            raise EpistemicActionConflictError(
                "duplicate_prediction_conflict",
                state="ambiguous",
                event=refusal,
            )
        commitment_digest = _hash_bytes(
            _canonical_json(
                {
                    "request_id": safe_request_id,
                    "attempt_id": safe_attempt_id,
                    "prediction_id": safe_prediction_id,
                    "action_id": safe_action_id,
                    "tool_use_id": safe_tool_use_id,
                    "expected_observation_digest": safe_expected,
                    "pre_action_marker": safe_pre_action_marker,
                    "observation_window_digest": safe_window,
                    "hypothesis_digest": safe_hypothesis,
                    "expected_change_digest": safe_expected_change,
                    "falsifier_digest": safe_falsifier,
                    "confidence": safe_confidence,
                    "action_plan_digest": safe_action_plan,
                }
            ).encode("utf-8")
        )
        event, _created = self._append_event(
            event_type="prediction_commitment",
            state="committed",
            fields={
                "request_id": safe_request_id,
                "attempt_id": safe_attempt_id,
                "prediction_id": safe_prediction_id,
                "prediction_commitment_digest": commitment_digest,
                "pre_action_marker": safe_pre_action_marker,
                "observation_window_digest": safe_window,
                "hypothesis_digest": safe_hypothesis,
                "expected_change_digest": safe_expected_change,
                "falsifier_digest": safe_falsifier,
                "confidence": safe_confidence,
                "action_plan_digest": safe_action_plan,
                "action_id": safe_action_id,
                "expected_observation_digest": safe_expected,
                **(
                    {"tool_use_id": safe_tool_use_id}
                    if safe_tool_use_id is not None
                    else {}
                ),
            },
            identity={"prediction_id": safe_prediction_id},
            created_at=created_at,
            expected_sequence=expected_sequence,
        )
        return event

    def bind_action(
        self,
        action_id: str,
        action_digest: str,
        *,
        attempt_id: str,
        action_kind: str,
        effect_class: str,
        action_started_at: str,
        tool_use_id: str | None = None,
        prediction_id: str | None = None,
        created_at: str | None = None,
        expected_sequence: int | None = None,
    ) -> dict[str, Any]:
        """Bind an action only to an already committed prediction."""

        safe_action_id = _safe_identifier(action_id, "action_id")
        safe_action_digest = _safe_digest(action_digest, "action_digest")
        safe_attempt_id = _safe_identifier(attempt_id, "attempt_id")
        safe_tool_use_id = (
            _safe_identifier(tool_use_id, "tool_use_id")
            if tool_use_id is not None
            else None
        )
        safe_action_kind = _safe_identifier(action_kind, "action_kind")
        safe_effect_class = _safe_identifier(effect_class, "effect_class")
        safe_action_started_at = _safe_timestamp(action_started_at)
        assert safe_action_digest is not None
        existing_action = next(
            (
                event
                for event in self._action_events()
                if event.get("action_id") == safe_action_id
            ),
            None,
        )
        if existing_action is not None:
            same = (
                existing_action.get("action_digest") == safe_action_digest
                and existing_action.get("attempt_id") == safe_attempt_id
                and existing_action.get("tool_use_id") == safe_tool_use_id
                and existing_action.get("action_kind") == safe_action_kind
                and existing_action.get("effect_class") == safe_effect_class
                and existing_action.get("action_started_at")
                == safe_action_started_at
                and (
                    prediction_id is None
                    or existing_action.get("prediction_id")
                    == _safe_identifier(prediction_id, "prediction_id")
                )
            )
            if same:
                return dict(existing_action)
            refusal = self._record_refusal(
                "action_binding_conflict",
                related_event_ids=[str(existing_action["event_id"])],
                fields={
                    "action_id": safe_action_id,
                    "action_digest": safe_action_digest,
                },
                state="ambiguous",
            )
            raise EpistemicActionConflictError(
                "action_binding_conflict",
                state="ambiguous",
                event=refusal,
            )
        prediction = next(
            (
                event
                for event in self._prediction_events()
                if event.get("action_id") == safe_action_id
            ),
            None,
        )
        if prediction is None:
            refusal = self._record_refusal(
                "action_before_prediction",
                fields={"action_id": safe_action_id},
            )
            raise EpistemicActionOrderingError(
                "action_before_prediction",
                event=refusal,
            )
        safe_prediction_id = str(prediction["prediction_id"])
        if prediction.get("attempt_id") != safe_attempt_id:
            refusal = self._record_refusal(
                "attempt_identity_conflict",
                related_event_ids=[str(prediction["event_id"])],
                fields={
                    "action_id": safe_action_id,
                    "attempt_id": safe_attempt_id,
                },
                state="ambiguous",
            )
            raise EpistemicActionConflictError(
                "attempt_identity_conflict",
                state="ambiguous",
                event=refusal,
            )
        if prediction.get("tool_use_id") != safe_tool_use_id:
            refusal = self._record_refusal(
                "tool_use_identity_conflict",
                related_event_ids=[str(prediction["event_id"])],
                fields={"action_id": safe_action_id},
                state="ambiguous",
            )
            raise EpistemicActionConflictError(
                "tool_use_identity_conflict",
                state="ambiguous",
                event=refusal,
            )
        if str(prediction["created_at"]) > safe_action_started_at:
            refusal = self._record_refusal(
                "post_hoc_prediction",
                related_event_ids=[str(prediction["event_id"])],
                fields={"action_id": safe_action_id},
            )
            raise EpistemicActionOrderingError(
                "post_hoc_prediction",
                event=refusal,
            )
        if prediction_id is not None:
            requested_prediction_id = _safe_identifier(
                prediction_id,
                "prediction_id",
            )
            if requested_prediction_id != safe_prediction_id:
                refusal = self._record_refusal(
                    "prediction_action_mismatch",
                    related_event_ids=[str(prediction["event_id"])],
                    fields={
                        "action_id": safe_action_id,
                        "prediction_id": requested_prediction_id,
                    },
                    state="ambiguous",
                )
                raise EpistemicActionConflictError(
                    "prediction_action_mismatch",
                    state="ambiguous",
                    event=refusal,
                )
        event, _created = self._append_event(
            event_type="action_binding",
            state="bound",
            fields={
                "request_id": prediction["request_id"],
                "attempt_id": safe_attempt_id,
                "prediction_id": safe_prediction_id,
                "action_id": safe_action_id,
                "action_digest": safe_action_digest,
                "action_kind": safe_action_kind,
                "effect_class": safe_effect_class,
                "action_started_at": safe_action_started_at,
                "prediction_commitment_digest": prediction[
                    "prediction_commitment_digest"
                ],
                "related_event_ids": [str(prediction["event_id"])],
                **(
                    {"tool_use_id": safe_tool_use_id}
                    if safe_tool_use_id is not None
                    else {}
                ),
            },
            identity={"action_id": safe_action_id},
            created_at=created_at,
            expected_sequence=expected_sequence,
        )
        return event

    def record_observation(
        self,
        action_id: str,
        observation_digest: str | None = None,
        *,
        attempt_id: str,
        tool_use_id: str | None = None,
        evidence_ref_ids: Iterable[str] = (),
        observed_digest: str | None = None,
        observation_id: str | None = None,
        observation_status: str = "observed",
        reason_code: str | None = None,
        created_at: str | None = None,
        expected_sequence: int | None = None,
    ) -> dict[str, Any]:
        """Append one observation or an explicit missing/unknown state."""

        safe_action_id = _safe_identifier(action_id, "action_id")
        safe_attempt_id = _safe_identifier(attempt_id, "attempt_id")
        safe_tool_use_id = (
            _safe_identifier(tool_use_id, "tool_use_id")
            if tool_use_id is not None
            else None
        )
        safe_evidence_ref_ids = _unique_safe_ids(
            list(evidence_ref_ids),
            "evidence_ref_ids",
        )
        if observation_digest is None:
            observation_digest = observed_digest
        elif observed_digest is not None and observed_digest != observation_digest:
            raise EpistemicActionPrivacyError("digest_invalid")
        if observation_status not in EPISTEMIC_ACTION_OBSERVATION_STATUSES:
            raise EpistemicActionPrivacyError("observation_status_invalid")
        if observation_status == "observed":
            safe_observation_digest = _safe_digest(
                observation_digest,
                "observation_digest",
            )
        else:
            if observation_digest is not None:
                raise EpistemicActionPrivacyError("observation_digest_forbidden")
            safe_observation_digest = None
        action_event = next(
            (
                event
                for event in self._action_events()
                if event.get("action_id") == safe_action_id
            ),
            None,
        )
        if action_event is None:
            refusal = self._record_refusal(
                "missing_action",
                fields={"action_id": safe_action_id},
            )
            raise EpistemicActionOrderingError(
                "missing_action",
                event=refusal,
            )
        if action_event.get("attempt_id") != safe_attempt_id:
            refusal = self._record_refusal(
                "attempt_identity_conflict",
                related_event_ids=[str(action_event["event_id"])],
                fields={
                    "action_id": safe_action_id,
                    "attempt_id": safe_attempt_id,
                },
                state="ambiguous",
            )
            raise EpistemicActionConflictError(
                "attempt_identity_conflict",
                state="ambiguous",
                event=refusal,
            )
        if action_event.get("tool_use_id") != safe_tool_use_id:
            refusal = self._record_refusal(
                "tool_use_identity_conflict",
                related_event_ids=[str(action_event["event_id"])],
                fields={"action_id": safe_action_id},
                state="ambiguous",
            )
            raise EpistemicActionConflictError(
                "tool_use_identity_conflict",
                state="ambiguous",
                event=refusal,
            )
        safe_reason = _safe_reason_code(
            reason_code,
            default=(
                "observation_recorded"
                if observation_status == "observed"
                else "missing_observation"
            ),
        )
        safe_observation_id = (
            _safe_identifier(observation_id, "observation_id")
            if observation_id is not None
            else _derived_id(
                "observation",
                {
                    "action_id": safe_action_id,
                    "observation_status": observation_status,
                    "observation_digest": safe_observation_digest,
                    "reason_code": safe_reason,
                },
            )
        )
        same_id = next(
            (
                event
                for event in self._observation_events(safe_action_id)
                if event.get("observation_id") == safe_observation_id
            ),
            None,
        )
        if same_id is not None:
            same = (
                same_id.get("observation_status") == observation_status
                and same_id.get("observation_digest") == safe_observation_digest
                and same_id.get("reason_code") == safe_reason
                and same_id.get("attempt_id") == safe_attempt_id
                and same_id.get("tool_use_id") == safe_tool_use_id
                and same_id.get("evidence_ref_ids", []) == safe_evidence_ref_ids
            )
            if same:
                return dict(same_id)
            conflict = self._record_observation_conflict(
                safe_action_id,
                action_event["request_id"],
                safe_observation_id,
                safe_observation_digest,
                observation_status,
                safe_reason,
                safe_attempt_id,
                safe_tool_use_id,
                safe_evidence_ref_ids,
                [str(same_id["event_id"])],
            )
            raise EpistemicActionConflictError(
                "duplicate_observation_conflict",
                state="ambiguous",
                event=conflict,
            )
        prior_observations = self._observation_events(safe_action_id)
        if prior_observations:
            conflict = self._record_observation_conflict(
                safe_action_id,
                action_event["request_id"],
                safe_observation_id,
                safe_observation_digest,
                observation_status,
                safe_reason,
                safe_attempt_id,
                safe_tool_use_id,
                safe_evidence_ref_ids,
                [str(event["event_id"]) for event in prior_observations],
            )
            raise EpistemicActionConflictError(
                "conflicting_observation",
                state="ambiguous",
                event=conflict,
            )
        fields: dict[str, Any] = {
            "request_id": action_event["request_id"],
            "attempt_id": safe_attempt_id,
            "action_id": safe_action_id,
            "observation_id": safe_observation_id,
            "observation_status": observation_status,
            "reason_code": safe_reason,
            "evidence_ref_ids": safe_evidence_ref_ids,
            "related_event_ids": [str(action_event["event_id"])],
        }
        if safe_tool_use_id is not None:
            fields["tool_use_id"] = safe_tool_use_id
        if safe_observation_digest is not None:
            fields["observation_digest"] = safe_observation_digest
        state = {
            "observed": "observed",
            "missing": "unknown",
            "unknown": "unknown",
            "ambiguous": "ambiguous",
            "refused": "refused",
        }[observation_status]
        event, _created = self._append_event(
            event_type="observation",
            state=state,
            fields=fields,
            identity={"observation_id": safe_observation_id},
            created_at=created_at,
            expected_sequence=expected_sequence,
        )
        return event

    def _record_observation_conflict(
        self,
        action_id: str,
        request_id: str,
        observation_id: str,
        observation_digest: str | None,
        observation_status: str,
        reason_code: str,
        attempt_id: str,
        tool_use_id: str | None,
        evidence_ref_ids: list[str],
        related_event_ids: list[str],
    ) -> dict[str, Any]:
        fields: dict[str, Any] = {
            "request_id": request_id,
            "attempt_id": attempt_id,
            "action_id": action_id,
            "observation_id": observation_id,
            "observation_status": observation_status,
            "reason_code": reason_code,
            "evidence_ref_ids": evidence_ref_ids,
            "related_event_ids": related_event_ids,
        }
        if tool_use_id is not None:
            fields["tool_use_id"] = tool_use_id
        if observation_digest is not None:
            fields["observation_digest"] = observation_digest
        event, _created = self._append_event(
            event_type="observation_conflict",
            state="ambiguous",
            fields=fields,
            identity={
                "request_id": request_id,
                "action_id": action_id,
                "attempt_id": attempt_id,
                "tool_use_id": tool_use_id,
                "observation_id": observation_id,
                "observation_digest": observation_digest,
                "observation_status": observation_status,
                "evidence_ref_ids": evidence_ref_ids,
                "related_event_ids": related_event_ids,
            },
        )
        return event

    def derive_discrepancy(
        self,
        action_id: str,
        *,
        discrepancy_kind: str | None = None,
        alternative_explanation_digest: str | None = None,
        model_update_digest: str | None = None,
        next_distinguishing_action_digest: str | None = None,
        created_at: str | None = None,
        expected_sequence: int | None = None,
    ) -> dict[str, Any]:
        """Derive a bounded discrepancy and persist only a shadow candidate."""

        safe_action_id = _safe_identifier(action_id, "action_id")
        if discrepancy_kind is not None and discrepancy_kind not in {
            "match",
            "partial_match",
            "mismatch",
        }:
            raise EpistemicActionPrivacyError("prediction_fields_invalid")
        safe_alternative = _safe_digest(
            alternative_explanation_digest,
            "alternative_explanation_digest",
            required=False,
        )
        safe_model_update = _safe_digest(
            model_update_digest,
            "model_update_digest",
            required=False,
        )
        safe_next_action = _safe_digest(
            next_distinguishing_action_digest,
            "next_distinguishing_action_digest",
            required=False,
        )
        prediction = next(
            (
                event
                for event in self._prediction_events()
                if event.get("action_id") == safe_action_id
            ),
            None,
        )
        action = next(
            (
                event
                for event in self._action_events()
                if event.get("action_id") == safe_action_id
            ),
            None,
        )
        if prediction is None or action is None:
            return {
                "ok": False,
                "state": "unknown",
                "reason_code": "missing_action",
                "action_id": safe_action_id,
                "discrepancy": None,
                "model_update_candidate": None,
            }
        observations = self._observation_events(safe_action_id)
        conflict_events = [
            event
            for event in self._events
            if (
                event.get("event_type") == "observation_conflict"
                or (
                    event.get("event_type") == "refusal"
                    and event.get("state") == "ambiguous"
                )
            )
            and event.get("action_id") == safe_action_id
        ]
        source_event_ids = [str(prediction["event_id"]), str(action["event_id"])]
        observation: dict[str, Any] | None = None
        if len(observations) == 1 and not conflict_events:
            observation = observations[0]
            source_event_ids.append(str(observation["event_id"]))
        elif observations or conflict_events:
            source_event_ids.extend(
                str(event["event_id"])
                for event in [*observations, *conflict_events]
            )
        source_event_ids = list(dict.fromkeys(source_event_ids))[:8]
        if conflict_events or len(observations) > 1:
            discrepancy_kind = "ambiguous"
        elif observation is None:
            discrepancy_kind = "unknown"
        elif observation.get("observation_status") != "observed":
            discrepancy_kind = (
                "ambiguous"
                if observation.get("observation_status") == "ambiguous"
                else "unknown"
            )
        elif discrepancy_kind is not None:
            pass
        elif observation.get("observation_digest") == prediction.get(
            "expected_observation_digest"
        ):
            discrepancy_kind = "match"
        else:
            discrepancy_kind = "mismatch"
        if discrepancy_kind is None:
            discrepancy_kind = "unknown"
        fields: dict[str, Any] = {
            "request_id": prediction["request_id"],
            "attempt_id": prediction["attempt_id"],
            "action_id": safe_action_id,
            "prediction_id": prediction["prediction_id"],
            "expected_observation_digest": prediction[
                "expected_observation_digest"
            ],
            "discrepancy_kind": discrepancy_kind,
            "source_event_ids": source_event_ids,
            "related_event_ids": source_event_ids,
        }
        if prediction.get("tool_use_id") is not None:
            fields["tool_use_id"] = prediction["tool_use_id"]
        if observation is not None and observation.get("observation_digest"):
            fields["observed_observation_digest"] = observation[
                "observation_digest"
            ]
        discrepancy_state = {
            "match": "ready",
            "partial_match": "ready",
            "mismatch": "ready",
            "unknown": "unknown",
            "ambiguous": "ambiguous",
        }[discrepancy_kind]
        discrepancy_event_id = _derived_id(
            "event",
            {
                "event_type": "discrepancy",
                "identity": {
                    "action_id": safe_action_id,
                    "source_event_ids": source_event_ids,
                    "discrepancy_kind": discrepancy_kind,
                },
            },
        )
        existing_discrepancy = next(
            (
                event
                for event in self._events
                if event.get("event_id") == discrepancy_event_id
            ),
            None,
        )
        if existing_discrepancy is None:
            discrepancy_event, _created = self._append_event(
                event_type="discrepancy",
                state=discrepancy_state,
                fields=fields,
                identity={
                    "action_id": safe_action_id,
                    "source_event_ids": source_event_ids,
                    "discrepancy_kind": discrepancy_kind,
                },
                created_at=created_at,
                expected_sequence=expected_sequence,
            )
        else:
            discrepancy_event = existing_discrepancy
        candidate_event = self._ensure_model_update_candidate(
            safe_action_id,
            discrepancy_event,
            prediction_event=prediction,
            alternative_explanation_digest=safe_alternative,
            model_update_digest=safe_model_update,
            next_distinguishing_action_digest=safe_next_action,
        )
        discrepancy = {
            "kind": discrepancy_kind,
            "state": discrepancy_state,
            "prediction_event_id": prediction["event_id"],
            "action_event_id": action["event_id"],
            "observation_event_id": (
                observation["event_id"] if observation is not None else None
            ),
            "source_event_ids": source_event_ids,
        }
        return {
            "ok": True,
            "state": discrepancy_state,
            "action_id": safe_action_id,
            "discrepancy": discrepancy,
            "event": dict(discrepancy_event),
            "model_update_candidate": self._candidate_projection(candidate_event),
        }

    def _ensure_model_update_candidate(
        self,
        action_id: str,
        discrepancy_event: dict[str, Any],
        *,
        prediction_event: dict[str, Any],
        alternative_explanation_digest: str | None,
        model_update_digest: str | None,
        next_distinguishing_action_digest: str | None,
    ) -> dict[str, Any]:
        source_event_ids = list(
            dict.fromkeys(
                [
                    str(discrepancy_event["event_id"]),
                    *[
                        str(item)
                        for item in discrepancy_event.get("source_event_ids", [])
                    ],
                ]
            )
        )[:8]
        candidate_id = _derived_id(
            "candidate",
            {
                "action_id": action_id,
                "discrepancy_event_id": discrepancy_event["event_id"],
            },
        )
        existing = next(
            (
                event
                for event in self._candidate_events(action_id)
                if event.get("candidate_id") == candidate_id
            ),
            None,
        )
        if existing is not None:
            if not any(
                value is not None
                for value in (
                    alternative_explanation_digest,
                    model_update_digest,
                    next_distinguishing_action_digest,
                )
            ):
                return existing
            requested_semantics = {
                "alternative_explanation_digest": alternative_explanation_digest,
                "model_update_digest": model_update_digest,
                "next_distinguishing_action_digest": next_distinguishing_action_digest,
            }
            existing_semantics = {
                key: existing.get(key) for key in requested_semantics
            }
            if existing_semantics == requested_semantics:
                return existing
            refusal = self._record_refusal(
                "model_update_conflict",
                related_event_ids=[str(existing["event_id"])],
                fields={"action_id": action_id},
                state="ambiguous",
            )
            raise EpistemicActionConflictError(
                "model_update_conflict",
                state="ambiguous",
                event=refusal,
            )
        discrepancy_kind = str(discrepancy_event["discrepancy_kind"])
        update_kind = {
            "mismatch": "review_prediction",
            "partial_match": "review_prediction",
            "match": "inspect_only",
            "unknown": "withhold_update",
            "ambiguous": "withhold_update",
        }[discrepancy_kind]
        fields = {
            "request_id": prediction_event["request_id"],
            "attempt_id": prediction_event["attempt_id"],
            "candidate_id": candidate_id,
            "action_id": action_id,
            "candidate_status": "shadow_only",
            "discrepancy_kind": discrepancy_kind,
            "update_kind": update_kind,
            "source_event_ids": source_event_ids,
            "related_event_ids": [str(discrepancy_event["event_id"])],
            "claim_ceiling": EPISTEMIC_ACTION_CANDIDATE_CLAIM_CEILING,
            "hypothesis_digest": prediction_event["hypothesis_digest"],
            "expected_change_digest": prediction_event["expected_change_digest"],
            "falsifier_digest": prediction_event["falsifier_digest"],
            "confidence": prediction_event["confidence"],
            "action_plan_digest": prediction_event["action_plan_digest"],
            "observation_window_digest": prediction_event[
                "observation_window_digest"
            ],
            "pre_action_marker": prediction_event["pre_action_marker"],
        }
        if prediction_event.get("tool_use_id") is not None:
            fields["tool_use_id"] = prediction_event["tool_use_id"]
        if alternative_explanation_digest is not None:
            fields["alternative_explanation_digest"] = (
                alternative_explanation_digest
            )
        if model_update_digest is not None:
            fields["model_update_digest"] = model_update_digest
        if next_distinguishing_action_digest is not None:
            fields["next_distinguishing_action_digest"] = (
                next_distinguishing_action_digest
            )
        event, _created = self._append_event(
            event_type="model_update_candidate",
            state="shadow_only",
            fields=fields,
            identity={
                "candidate_id": candidate_id,
                "discrepancy_event_id": discrepancy_event["event_id"],
            },
        )
        return event

    @staticmethod
    def _candidate_projection(event: dict[str, Any]) -> dict[str, Any]:
        return {
            "request_id": event["request_id"],
            "attempt_id": event["attempt_id"],
            "action_id": event["action_id"],
            "candidate_id": event["candidate_id"],
            "candidate_event_id": event["event_id"],
            "status": event["candidate_status"],
            "discrepancy_kind": event["discrepancy_kind"],
            "update_kind": event["update_kind"],
            "source_event_ids": list(event.get("source_event_ids", [])),
            "claim_ceiling": event["claim_ceiling"],
            "hypothesis_digest": event.get("hypothesis_digest"),
            "expected_change_digest": event.get("expected_change_digest"),
            "falsifier_digest": event.get("falsifier_digest"),
            "confidence": event.get("confidence"),
            "action_plan_digest": event.get("action_plan_digest"),
            "observation_window_digest": event.get(
                "observation_window_digest"
            ),
            "pre_action_marker": event.get("pre_action_marker"),
            "tool_use_id": event.get("tool_use_id"),
            "alternative_explanation_digest": event.get(
                "alternative_explanation_digest"
            ),
            "model_update_digest": event.get("model_update_digest"),
            "next_distinguishing_action_digest": event.get(
                "next_distinguishing_action_digest"
            ),
        }

    def inspect_model_update_candidate(
        self,
        action_id: str,
    ) -> dict[str, Any]:
        self.refresh()
        safe_action_id = _safe_identifier(action_id, "action_id")
        candidates = self._candidate_events(safe_action_id)
        if not candidates:
            return {
                "ok": False,
                "state": "unknown",
                "action_id": safe_action_id,
                "candidate": None,
                "claim_ceiling": EPISTEMIC_ACTION_CLAIM_CEILING,
            }
        return {
            "ok": True,
            "state": "shadow_only",
            "action_id": safe_action_id,
            "candidate": self._candidate_projection(candidates[-1]),
            "claim_ceiling": EPISTEMIC_ACTION_CLAIM_CEILING,
        }

    def _chain_status(self) -> str:
        return _chain_status_for_events(self._events)

    def inspect(self) -> dict[str, Any]:
        self.refresh()
        candidates = [
            self._candidate_projection(event)
            for event in self._events
            if event.get("event_type") == "model_update_candidate"
        ]
        return {
            "schema_version": EPISTEMIC_ACTION_SCHEMA_VERSION,
            "artifact_type": EPISTEMIC_ACTION_ARTIFACT_TYPE,
            "chain_id": self.chain_id,
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "chain_status": self._chain_status(),
            "claim_ceiling": EPISTEMIC_ACTION_CLAIM_CEILING,
            "head": self.head.as_dict(),
            "event_count": len(self._events),
            "events": self.events,
            "model_update_candidates": candidates,
            "diagnostics": [],
        }

    replay = inspect
    snapshot = inspect
    append_observation = record_observation
    record_prediction = commit_prediction
    record_action = bind_action


def create_epistemic_action_chain(
    store_path: str | Path,
    *,
    session_id: str,
    turn_id: str,
) -> EpistemicActionChain:
    return EpistemicActionChain.create(
        store_path,
        session_id=session_id,
        turn_id=turn_id,
    )


def load_epistemic_action_chain(
    store_path: str | Path,
    *,
    session_id: str | None = None,
    turn_id: str | None = None,
) -> EpistemicActionChain:
    return EpistemicActionChain.load(
        store_path,
        session_id=session_id,
        turn_id=turn_id,
    )


def replay_epistemic_action_events(store_path: str | Path) -> list[dict[str, Any]]:
    return load_epistemic_action_chain(store_path).events


def validate_epistemic_action_chain_artifact(
    artifact: Any,
) -> dict[str, Any]:
    diagnostics: list[str] = []
    try:
        if not isinstance(artifact, dict):
            raise EpistemicActionIntegrityError("event_shape_invalid")
        required = {
            "schema_version",
            "artifact_type",
            "chain_id",
            "session_id",
            "turn_id",
            "chain_status",
            "claim_ceiling",
            "head",
            "event_count",
            "events",
            "model_update_candidates",
            "diagnostics",
        }
        if set(artifact) != required:
            raise EpistemicActionIntegrityError("event_shape_invalid")
        if artifact["schema_version"] != EPISTEMIC_ACTION_SCHEMA_VERSION:
            raise EpistemicActionIntegrityError("event_shape_invalid")
        if artifact["artifact_type"] != EPISTEMIC_ACTION_ARTIFACT_TYPE:
            raise EpistemicActionIntegrityError("event_shape_invalid")
        session_id = _safe_identifier(artifact["session_id"], "session_id")
        turn_id = _safe_identifier(artifact["turn_id"], "turn_id")
        _safe_identifier(artifact["chain_id"], "chain_id")
        if artifact["chain_id"] != _derived_id(
            "chain",
            {"session_id": session_id, "turn_id": turn_id},
        ):
            raise EpistemicActionIntegrityError("chain_scope_mismatch")
        if artifact["claim_ceiling"] != EPISTEMIC_ACTION_CLAIM_CEILING:
            raise EpistemicActionIntegrityError("event_shape_invalid")
        events = artifact["events"]
        if not isinstance(events, list):
            raise EpistemicActionIntegrityError("event_shape_invalid")
        replayed = _replay_records(
            events,
            expected_session_id=session_id,
            expected_turn_id=turn_id,
        )
        if artifact["event_count"] != len(replayed):
            raise EpistemicActionIntegrityError("event_shape_invalid")
        head = artifact["head"]
        if not isinstance(head, dict) or set(head) != {
            "sequence",
            "event_id",
            "event_digest",
        }:
            raise EpistemicActionIntegrityError("event_shape_invalid")
        expected_head = (
            EpistemicActionHead(0, None, EPISTEMIC_ACTION_GENESIS)
            if not replayed
            else EpistemicActionHead(
                int(replayed[-1]["sequence"]),
                str(replayed[-1]["event_id"]),
                str(replayed[-1]["event_digest"]),
            )
        ).as_dict()
        if head != expected_head:
            raise EpistemicActionIntegrityError("event_shape_invalid")
        if artifact["chain_status"] not in {
            "ready",
            "unknown",
            "ambiguous",
            "refused",
            "shadow_only",
        }:
            raise EpistemicActionIntegrityError("event_shape_invalid")
        if artifact["chain_status"] != _chain_status_for_events(replayed):
            raise EpistemicActionIntegrityError("event_shape_invalid")
        if not isinstance(artifact["diagnostics"], list):
            raise EpistemicActionIntegrityError("event_shape_invalid")
        for diagnostic in artifact["diagnostics"]:
            _safe_reason_code(diagnostic, default="event_shape_invalid")
        candidates = artifact["model_update_candidates"]
        if not isinstance(candidates, list):
            raise EpistemicActionIntegrityError("event_shape_invalid")
        expected_candidates = [
            EpistemicActionChain._candidate_projection(event)
            for event in replayed
            if event.get("event_type") == "model_update_candidate"
        ]
        if candidates != expected_candidates:
            raise EpistemicActionIntegrityError("event_shape_invalid")
    except EpistemicActionError as exc:
        diagnostics.append(exc.reason_code)
    return {
        "ok": not diagnostics,
        "status": "current" if not diagnostics else "invalid",
        "chain_status": artifact.get("chain_status")
        if isinstance(artifact, dict)
        else "unknown",
        "event_count": artifact.get("event_count", 0)
        if isinstance(artifact, dict)
        else 0,
        "diagnostics": diagnostics,
        "claim_ceiling": EPISTEMIC_ACTION_CLAIM_CEILING,
    }


def validate_epistemic_action_chain(
    target: str | Path | dict[str, Any],
) -> dict[str, Any]:
    if isinstance(target, dict):
        return validate_epistemic_action_chain_artifact(target)
    try:
        artifact = load_epistemic_action_chain(target).inspect()
    except EpistemicActionError as exc:
        return {
            "ok": False,
            "status": "invalid",
            "chain_status": exc.state,
            "event_count": 0,
            "diagnostics": [exc.reason_code],
            "claim_ceiling": EPISTEMIC_ACTION_CLAIM_CEILING,
        }
    return validate_epistemic_action_chain_artifact(artifact)


def record_prediction_commitment(
    chain: EpistemicActionChain,
    action_id: str,
    expected_observation_digest: str,
    **kwargs: Any,
) -> dict[str, Any]:
    return chain.commit_prediction(
        action_id,
        expected_observation_digest,
        **kwargs,
    )


def commit_prediction(
    chain: EpistemicActionChain,
    action_id: str,
    expected_observation_digest: str,
    **kwargs: Any,
) -> dict[str, Any]:
    return record_prediction_commitment(
        chain,
        action_id,
        expected_observation_digest,
        **kwargs,
    )


def bind_epistemic_action(
    chain: EpistemicActionChain,
    action_id: str,
    action_digest: str,
    **kwargs: Any,
) -> dict[str, Any]:
    return chain.bind_action(action_id, action_digest, **kwargs)


def bind_action(
    chain: EpistemicActionChain,
    action_id: str,
    action_digest: str,
    **kwargs: Any,
) -> dict[str, Any]:
    return bind_epistemic_action(chain, action_id, action_digest, **kwargs)


def record_epistemic_observation(
    chain: EpistemicActionChain,
    action_id: str,
    observation_digest: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    return chain.record_observation(
        action_id,
        observation_digest,
        **kwargs,
    )


def record_observation(
    chain: EpistemicActionChain,
    action_id: str,
    observation_digest: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    return record_epistemic_observation(
        chain,
        action_id,
        observation_digest,
        **kwargs,
    )


def derive_epistemic_discrepancy(
    chain: EpistemicActionChain,
    action_id: str,
    **kwargs: Any,
) -> dict[str, Any]:
    return chain.derive_discrepancy(action_id, **kwargs)


def derive_discrepancy(
    chain: EpistemicActionChain,
    action_id: str,
    **kwargs: Any,
) -> dict[str, Any]:
    return derive_epistemic_discrepancy(chain, action_id, **kwargs)


def inspect_model_update_candidate(
    chain: EpistemicActionChain,
    action_id: str,
) -> dict[str, Any]:
    return chain.inspect_model_update_candidate(action_id)


def _cli_error(exc: EpistemicActionError) -> dict[str, Any]:
    return exc.result()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Operate on a privacy-safe Epistemic Action event chain."
    )
    parser.add_argument("--store", required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("--session-id", required=True)
    init.add_argument("--turn-id", required=True)
    commit = sub.add_parser("commit-prediction")
    commit.add_argument("--session-id", required=True)
    commit.add_argument("--turn-id", required=True)
    commit.add_argument("--action-id", required=True)
    commit.add_argument("--expected-observation-digest", required=True)
    commit.add_argument("--request-id", required=True)
    commit.add_argument("--attempt-id", required=True)
    commit.add_argument("--tool-use-id")
    commit.add_argument("--pre-action-marker", required=True)
    commit.add_argument("--observation-window-digest", required=True)
    commit.add_argument("--hypothesis-digest", required=True)
    commit.add_argument("--expected-change-digest", required=True)
    commit.add_argument("--falsifier-digest", required=True)
    commit.add_argument("--confidence", required=True, type=float)
    commit.add_argument("--action-plan-digest", required=True)
    commit.add_argument("--prediction-id")
    bind = sub.add_parser("bind-action")
    bind.add_argument("--session-id", required=True)
    bind.add_argument("--turn-id", required=True)
    bind.add_argument("--action-id", required=True)
    bind.add_argument("--action-digest", required=True)
    bind.add_argument("--attempt-id", required=True)
    bind.add_argument("--tool-use-id")
    bind.add_argument("--action-kind", required=True)
    bind.add_argument("--effect-class", required=True)
    bind.add_argument("--action-started-at", required=True)
    bind.add_argument("--prediction-id")
    observe = sub.add_parser("observe")
    observe.add_argument("--session-id", required=True)
    observe.add_argument("--turn-id", required=True)
    observe.add_argument("--action-id", required=True)
    observe.add_argument("--attempt-id", required=True)
    observe.add_argument("--tool-use-id")
    observe.add_argument("--evidence-ref-id", action="append", default=[])
    observe.add_argument("--observation-id")
    observe.add_argument("--observation-digest")
    observe.add_argument(
        "--observation-status",
        choices=sorted(EPISTEMIC_ACTION_OBSERVATION_STATUSES),
        default="observed",
    )
    observe.add_argument("--reason-code")
    derive = sub.add_parser("derive-discrepancy")
    derive.add_argument("--session-id", required=True)
    derive.add_argument("--turn-id", required=True)
    derive.add_argument("--action-id", required=True)
    derive.add_argument(
        "--discrepancy-kind",
        choices=["match", "partial_match", "mismatch"],
    )
    derive.add_argument("--alternative-explanation-digest")
    derive.add_argument("--model-update-digest")
    derive.add_argument("--next-distinguishing-action-digest")
    candidate = sub.add_parser("inspect-candidate")
    candidate.add_argument("--session-id", required=True)
    candidate.add_argument("--turn-id", required=True)
    candidate.add_argument("--action-id", required=True)
    sub.add_parser("inspect")
    sub.add_parser("validate")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "init":
            chain = EpistemicActionChain.create(
                args.store,
                session_id=args.session_id,
                turn_id=args.turn_id,
            )
            chain.store_path.parent.mkdir(parents=True, exist_ok=True)
            if not chain.store_path.exists():
                chain.store_path.touch(mode=0o600)
                os.chmod(chain.store_path, 0o600)
            payload = chain.inspect()
        elif args.command == "inspect":
            payload = load_epistemic_action_chain(args.store).inspect()
        elif args.command == "validate":
            payload = validate_epistemic_action_chain(args.store)
        else:
            store = Path(args.store)
            if store.exists() and store.stat().st_size:
                chain = load_epistemic_action_chain(store)
            else:
                chain = EpistemicActionChain.create(
                    store,
                    session_id=args.session_id,
                    turn_id=args.turn_id,
                )
            if args.command == "commit-prediction":
                payload = chain.commit_prediction(
                    args.action_id,
                    args.expected_observation_digest,
                    request_id=args.request_id,
                    attempt_id=args.attempt_id,
                    tool_use_id=args.tool_use_id,
                    pre_action_marker=args.pre_action_marker,
                    observation_window_digest=args.observation_window_digest,
                    hypothesis_digest=args.hypothesis_digest,
                    expected_change_digest=args.expected_change_digest,
                    falsifier_digest=args.falsifier_digest,
                    confidence=args.confidence,
                    action_plan_digest=args.action_plan_digest,
                    prediction_id=args.prediction_id,
                )
            elif args.command == "bind-action":
                payload = chain.bind_action(
                    args.action_id,
                    args.action_digest,
                    attempt_id=args.attempt_id,
                    tool_use_id=args.tool_use_id,
                    action_kind=args.action_kind,
                    effect_class=args.effect_class,
                    action_started_at=args.action_started_at,
                    prediction_id=args.prediction_id,
                )
            elif args.command == "observe":
                payload = chain.record_observation(
                    args.action_id,
                    args.observation_digest,
                    attempt_id=args.attempt_id,
                    tool_use_id=args.tool_use_id,
                    evidence_ref_ids=args.evidence_ref_id,
                    observation_id=args.observation_id,
                    observation_status=args.observation_status,
                    reason_code=args.reason_code,
                )
            elif args.command == "derive-discrepancy":
                payload = chain.derive_discrepancy(
                    args.action_id,
                    discrepancy_kind=args.discrepancy_kind,
                    alternative_explanation_digest=(
                        args.alternative_explanation_digest
                    ),
                    model_update_digest=args.model_update_digest,
                    next_distinguishing_action_digest=(
                        args.next_distinguishing_action_digest
                    ),
                )
            elif args.command == "inspect-candidate":
                payload = chain.inspect_model_update_candidate(args.action_id)
            else:
                raise EpistemicActionError("event_shape_invalid")
        print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))
        return 0 if payload.get("ok", True) else 1
    except EpistemicActionError as exc:
        print(json.dumps(_cli_error(exc), indent=2, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
