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
import threading
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
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?Z$"
)
_UNSET = object()

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
        "duplicate_logical_identity",
        "prediction_commitment_mismatch",
        "observation_window_invalid",
        "observation_outside_window",
        "observation_before_action",
        "observation_evidence_required",
        "observation_timestamp_required",
        "observation_facets_required",
        "action_outside_observation_window",
        "discrepancy_classification_conflict",
        "discrepancy_derivation_mismatch",
        "candidate_derivation_mismatch",
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
        "observation_window_start_at",
        "observation_window_end_at",
        "expected_observation_facet_ids",
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
        "prediction_sequence",
        "observation_id",
        "expected_observation_digest",
        "observation_digest",
        "observed_observation_digest",
        "observed_at",
        "observed_observation_facet_ids",
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
_EVENT_COMMON_FIELDS = frozenset(
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
    }
)
_EVENT_TYPE_FIELDS = {
    "prediction_commitment": _EVENT_COMMON_FIELDS
    | {
        "request_id",
        "attempt_id",
        "tool_use_id",
        "prediction_id",
        "prediction_commitment_digest",
        "pre_action_marker",
        "observation_window_digest",
        "observation_window_start_at",
        "observation_window_end_at",
        "expected_observation_facet_ids",
        "hypothesis_digest",
        "expected_change_digest",
        "falsifier_digest",
        "confidence",
        "action_plan_digest",
        "action_id",
        "expected_observation_digest",
    },
    "action_binding": _EVENT_COMMON_FIELDS
    | {
        "request_id",
        "attempt_id",
        "tool_use_id",
        "prediction_id",
        "prediction_commitment_digest",
        "action_id",
        "action_digest",
        "action_kind",
        "effect_class",
        "action_started_at",
        "prediction_sequence",
        "related_event_ids",
    },
    "observation": _EVENT_COMMON_FIELDS
    | {
        "request_id",
        "attempt_id",
        "tool_use_id",
        "action_id",
        "observation_id",
        "observation_digest",
        "observation_status",
        "evidence_ref_ids",
        "observed_at",
        "observed_observation_facet_ids",
        "reason_code",
        "related_event_ids",
    },
    "observation_conflict": _EVENT_COMMON_FIELDS
    | {
        "request_id",
        "attempt_id",
        "tool_use_id",
        "action_id",
        "observation_id",
        "observation_digest",
        "observation_status",
        "evidence_ref_ids",
        "observed_at",
        "observed_observation_facet_ids",
        "reason_code",
        "related_event_ids",
    },
    "discrepancy": _EVENT_COMMON_FIELDS
    | {
        "request_id",
        "attempt_id",
        "tool_use_id",
        "prediction_id",
        "action_id",
        "expected_observation_digest",
        "observed_observation_digest",
        "discrepancy_kind",
        "related_event_ids",
        "source_event_ids",
    },
    "model_update_candidate": _EVENT_COMMON_FIELDS
    | {
        "request_id",
        "attempt_id",
        "tool_use_id",
        "action_id",
        "candidate_id",
        "candidate_status",
        "discrepancy_kind",
        "update_kind",
        "source_event_ids",
        "related_event_ids",
        "claim_ceiling",
        "hypothesis_digest",
        "expected_change_digest",
        "falsifier_digest",
        "confidence",
        "action_plan_digest",
        "observation_window_digest",
        "pre_action_marker",
        "alternative_explanation_digest",
        "model_update_digest",
        "next_distinguishing_action_digest",
    },
    # Refusals carry bounded context fields selected by the rejecting owner
    # operation. Their values are still validated below.
    "refusal": _EVENT_FIELDS,
}


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


def _safe_discrepancy_kind(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or value not in EPISTEMIC_ACTION_DISCREPANCY_KINDS:
        raise EpistemicActionPrivacyError("prediction_fields_invalid")
    return value


def _current_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _safe_timestamp(value: Any = None) -> str:
    # A missing or explicit null timestamp is never a request for the current
    # time.  Creation-time omission is handled explicitly by
    # _event_timestamp; replay and stored values always take this path.
    if not isinstance(value, str) or not _TIMESTAMP_RE.fullmatch(value):
        raise EpistemicActionPrivacyError("timestamp_invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EpistemicActionPrivacyError("timestamp_invalid") from exc
    if parsed.tzinfo is None:
        raise EpistemicActionPrivacyError("timestamp_invalid")
    normalized = parsed.astimezone(timezone.utc)
    if "." in value:
        result = normalized.isoformat(timespec="microseconds").replace(
            "+00:00", "Z"
        )
    else:
        if normalized.microsecond:
            raise EpistemicActionPrivacyError("timestamp_invalid")
        result = normalized.strftime("%Y-%m-%dT%H:%M:%SZ")
    if "." not in value and result != value:
        raise EpistemicActionPrivacyError("timestamp_invalid")
    if "." in value and not result.startswith(value[:-1]):
        raise EpistemicActionPrivacyError("timestamp_invalid")
    return result


def _event_timestamp(value: Any) -> str:
    if value is _UNSET:
        return _current_timestamp()
    return _safe_timestamp(value)


def _provided_created_at(value: Any) -> Any:
    if value is _UNSET:
        return _UNSET
    return _safe_timestamp(value)


def _timestamp_value(value: Any) -> datetime:
    """Parse a validated UTC timestamp for causal/window comparisons."""

    safe_value = _safe_timestamp(value)
    try:
        return datetime.fromisoformat(safe_value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise EpistemicActionIntegrityError("timestamp_invalid") from exc


def _validate_observation_window(
    start_at: str,
    end_at: str,
) -> tuple[str, str]:
    safe_start = _safe_timestamp(start_at)
    safe_end = _safe_timestamp(end_at)
    if _timestamp_value(safe_start) >= _timestamp_value(safe_end):
        raise EpistemicActionPrivacyError("observation_window_invalid")
    return safe_start, safe_end


def _observation_in_window(
    observed_at: str,
    *,
    start_at: str,
    end_at: str,
) -> bool:
    observed = _timestamp_value(observed_at)
    return _timestamp_value(start_at) <= observed <= _timestamp_value(end_at)


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


def _event_id_for(event_type: str, identity: Any) -> str:
    return _derived_id(
        "event",
        {"event_type": event_type, "identity": identity},
    )


def _prediction_commitment_digest(event: dict[str, Any]) -> str:
    return _hash_bytes(
        _canonical_json(
            {
                "request_id": event["request_id"],
                "attempt_id": event["attempt_id"],
                "prediction_id": event["prediction_id"],
                "action_id": event["action_id"],
                "tool_use_id": event.get("tool_use_id"),
                "expected_observation_digest": event[
                    "expected_observation_digest"
                ],
                "pre_action_marker": event["pre_action_marker"],
                "observation_window_digest": event[
                    "observation_window_digest"
                ],
                "observation_window_start_at": event[
                    "observation_window_start_at"
                ],
                "observation_window_end_at": event[
                    "observation_window_end_at"
                ],
                "expected_observation_facet_ids": list(
                    event.get("expected_observation_facet_ids", [])
                ),
                "hypothesis_digest": event["hypothesis_digest"],
                "expected_change_digest": event["expected_change_digest"],
                "falsifier_digest": event["falsifier_digest"],
                "confidence": event["confidence"],
                "action_plan_digest": event["action_plan_digest"],
            }
        ).encode("utf-8")
    )


def _legacy_discrepancy_event_id(event: dict[str, Any]) -> str:
    return _event_id_for(
        "discrepancy",
        {
            "action_id": event["action_id"],
            "source_event_ids": list(event["source_event_ids"]),
            "discrepancy_kind": event["discrepancy_kind"],
        },
    )


def _expected_event_id(event: dict[str, Any]) -> str | None:
    event_type = event["event_type"]
    if event_type == "prediction_commitment":
        identity = {"prediction_id": event["prediction_id"]}
    elif event_type == "action_binding":
        identity = {"action_id": event["action_id"]}
    elif event_type == "observation":
        identity = {"observation_id": event["observation_id"]}
    elif event_type == "observation_conflict":
        identity = {
            "request_id": event["request_id"],
            "action_id": event["action_id"],
            "attempt_id": event["attempt_id"],
            "tool_use_id": event.get("tool_use_id"),
            "observation_id": event["observation_id"],
            "observation_digest": event.get("observation_digest"),
            "observation_status": event["observation_status"],
            "evidence_ref_ids": list(event["evidence_ref_ids"]),
            "observed_at": event.get("observed_at"),
            "observed_observation_facet_ids": list(
                event.get("observed_observation_facet_ids", [])
            ),
            "related_event_ids": list(event.get("related_event_ids", [])),
        }
    elif event_type == "discrepancy":
        identity = {
            "action_id": event["action_id"],
            "source_event_ids": list(event["source_event_ids"]),
        }
    elif event_type == "model_update_candidate":
        related_event_ids = event.get("related_event_ids", [])
        discrepancy_event_id = (
            related_event_ids[0] if len(related_event_ids) == 1 else None
        )
        identity = {
            "candidate_id": event["candidate_id"],
            "discrepancy_event_id": discrepancy_event_id,
        }
    elif event_type == "refusal":
        identity = {
            "reason_code": event["reason_code"],
            "related_event_ids": list(event.get("related_event_ids", [])),
            "fields": {
                key: value
                for key, value in event.items()
                if key
                not in {
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
                    "reason_code",
                    "related_event_ids",
                }
            },
        }
    else:
        return None
    return _event_id_for(event_type, identity)


def _logical_identity_key(event: dict[str, Any]) -> tuple[Any, ...] | None:
    # The action is the semantic uniqueness fence.  Prediction and observation
    # IDs remain useful for exact replay identity, but allowing two different
    # IDs for one action would let cross-instance writers race past the
    # pre-append checks and make replay fail only after a second record landed.
    event_type = event["event_type"]
    if event_type == "prediction_commitment":
        return ("prediction", event["action_id"])
    if event_type == "action_binding":
        return ("action", event["action_id"])
    if event_type == "observation":
        return ("observation", event["action_id"])
    if event_type == "observation_conflict":
        return (
            "observation_conflict",
            event["action_id"],
            event["observation_id"],
            event.get("observation_digest"),
            event["observation_status"],
            tuple(event["evidence_ref_ids"]),
            tuple(event.get("related_event_ids", [])),
        )
    if event_type == "discrepancy":
        return (
            "discrepancy",
            event["action_id"],
            tuple(event["source_event_ids"]),
        )
    if event_type == "model_update_candidate":
        return ("candidate", event["candidate_id"])
    return None


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


def _discrepancy_context(
    events: Iterable[dict[str, Any]],
    action_id: str,
) -> dict[str, Any]:
    prior_events = list(events)
    predictions = [
        event
        for event in prior_events
        if event.get("event_type") == "prediction_commitment"
        and event.get("action_id") == action_id
    ]
    actions = [
        event
        for event in prior_events
        if event.get("event_type") == "action_binding"
        and event.get("action_id") == action_id
    ]
    observations = [
        event
        for event in prior_events
        if event.get("event_type") == "observation"
        and event.get("action_id") == action_id
    ]
    conflict_events = [
        event
        for event in prior_events
        if (
            event.get("event_type") == "observation_conflict"
            or (
                event.get("event_type") == "refusal"
                and event.get("state") == "ambiguous"
            )
        )
        and event.get("action_id") == action_id
    ]
    prediction = predictions[0] if len(predictions) == 1 else None
    action = actions[0] if len(actions) == 1 else None
    source_event_ids: list[str] = []
    if prediction is not None:
        source_event_ids.append(str(prediction["event_id"]))
    if action is not None:
        source_event_ids.append(str(action["event_id"]))
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
    elif prediction is None or action is None:
        discrepancy_kind = "unknown"
    elif observation.get("observation_digest") == prediction.get(
        "expected_observation_digest"
    ):
        discrepancy_kind = "match"
    elif prediction.get("expected_observation_facet_ids"):
        expected_facets = set(
            prediction.get("expected_observation_facet_ids", [])
        )
        observed_facets = set(
            observation.get("observed_observation_facet_ids", [])
        )
        discrepancy_kind = (
            "partial_match"
            if expected_facets.intersection(observed_facets)
            and observed_facets != expected_facets
            else "mismatch"
        )
    else:
        discrepancy_kind = "mismatch"
    return {
        "prediction": prediction,
        "action": action,
        "observations": observations,
        "conflict_events": conflict_events,
        "observation": observation,
        "source_event_ids": source_event_ids,
        "discrepancy_kind": discrepancy_kind,
    }


def _candidate_source_event_ids(discrepancy_event: dict[str, Any]) -> list[str]:
    return list(
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


def _candidate_update_kind(discrepancy_kind: str) -> str:
    return {
        "mismatch": "review_prediction",
        "partial_match": "review_prediction",
        "match": "inspect_only",
        "unknown": "withhold_update",
        "ambiguous": "withhold_update",
    }[discrepancy_kind]


def _validate_event_shape(
    event: Any,
    *,
    expected_session_id: str | None = None,
    expected_turn_id: str | None = None,
) -> dict[str, Any]:
    if not isinstance(event, dict):
        raise EpistemicActionIntegrityError("event_shape_invalid")
    if "created_at" not in event:
        raise EpistemicActionIntegrityError("timestamp_invalid")
    _safe_timestamp(event["created_at"])
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
    if not isinstance(event_type, str):
        raise EpistemicActionIntegrityError("event_type_invalid")
    if event_type not in EPISTEMIC_ACTION_EVENT_TYPES:
        raise EpistemicActionIntegrityError("event_type_invalid")
    required_timestamps = {
        "prediction_commitment": (
            "observation_window_start_at",
            "observation_window_end_at",
        ),
        "action_binding": ("action_started_at",),
    }.get(event_type, ())
    if event_type in {"observation", "observation_conflict"} and event.get(
        "observation_status"
    ) == "observed":
        required_timestamps = (*required_timestamps, "observed_at")
    for field in required_timestamps:
        if field not in event:
            raise EpistemicActionIntegrityError("timestamp_invalid")
        _safe_timestamp(event[field])
    if set(event) - _EVENT_TYPE_FIELDS[event_type]:
        raise EpistemicActionIntegrityError("event_shape_invalid")
    if not isinstance(event.get("state"), str):
        raise EpistemicActionIntegrityError("unsupported_event_state")
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
        "observation_window_start_at",
        "observation_window_end_at",
        "action_started_at",
        "expected_observation_digest",
        "observation_digest",
        "observed_observation_digest",
        "observed_at",
        "alternative_explanation_digest",
        "model_update_digest",
        "next_distinguishing_action_digest",
    ):
        if field in {
            "observation_window_start_at",
            "observation_window_end_at",
            "action_started_at",
            "observed_at",
        }:
            if field in event:
                _safe_timestamp(event[field])
        elif field in event:
            _safe_digest(event[field], field)
    if "confidence" in event:
        _safe_confidence(event["confidence"])
    if "observation_status" in event:
        if (
            not isinstance(event["observation_status"], str)
            or event["observation_status"]
            not in EPISTEMIC_ACTION_OBSERVATION_STATUSES
        ):
            raise EpistemicActionIntegrityError("observation_status_invalid")
    if "reason_code" in event:
        if (
            not isinstance(event["reason_code"], str)
            or event["reason_code"] not in EPISTEMIC_ACTION_REASON_CODES
        ):
            raise EpistemicActionIntegrityError("unsupported_reason_code")
    for field in (
        "related_event_ids",
        "source_event_ids",
        "evidence_ref_ids",
        "expected_observation_facet_ids",
        "observed_observation_facet_ids",
    ):
        if field in event:
            _unique_safe_ids(event[field], field)
    if "discrepancy_kind" in event and (
        not isinstance(event["discrepancy_kind"], str)
        or event["discrepancy_kind"] not in EPISTEMIC_ACTION_DISCREPANCY_KINDS
    ):
        raise EpistemicActionIntegrityError("event_shape_invalid")
    if "candidate_status" in event and (
        not isinstance(event["candidate_status"], str)
        or event["candidate_status"]
        not in {"shadow_only", "unknown", "ambiguous", "refused"}
    ):
        raise EpistemicActionIntegrityError("event_shape_invalid")
    if "update_kind" in event and (
        not isinstance(event["update_kind"], str)
        or event["update_kind"] not in EPISTEMIC_ACTION_UPDATE_KINDS
    ):
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
        "observation_window_start_at",
        "observation_window_end_at",
        "expected_observation_facet_ids",
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
        "prediction_sequence",
    } <= set(event):
        raise EpistemicActionIntegrityError("event_shape_invalid")
    if event_type in {"observation", "observation_conflict"} and not {
        "request_id",
        "attempt_id",
        "action_id",
        "observation_id",
        "observation_status",
        "evidence_ref_ids",
        "observed_observation_facet_ids",
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
    if event_type == "refusal":
        if "reason_code" not in event:
            raise EpistemicActionIntegrityError("event_shape_invalid")
        if event.get("state") not in {"refused", "ambiguous"}:
            raise EpistemicActionIntegrityError("event_shape_invalid")
    status = event.get("observation_status")
    if status is not None:
        if status == "observed" and "observation_digest" not in event:
            raise EpistemicActionIntegrityError("event_shape_invalid")
        if status != "observed" and "observation_digest" in event:
            raise EpistemicActionIntegrityError("event_shape_invalid")
        if status == "observed":
            if "observed_at" not in event or not event.get("evidence_ref_ids"):
                raise EpistemicActionIntegrityError("event_shape_invalid")
        elif "observed_at" in event:
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
    seen_logical_identities: set[tuple[Any, ...]] = set()
    seen_prediction_actions: set[str] = set()
    seen_observation_actions: set[str] = set()
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
            raise EpistemicActionIntegrityError("duplicate_logical_identity")
        expected_event_id = _expected_event_id(event)
        if expected_event_id is not None:
            expected_event_ids = {expected_event_id}
            if event["event_type"] == "discrepancy":
                # v2 artifacts written before the stable discrepancy identity
                # repair remain readable when their evidence is otherwise valid.
                expected_event_ids.add(_legacy_discrepancy_event_id(event))
            if event["event_id"] not in expected_event_ids:
                raise EpistemicActionIntegrityError("event_identity_conflict")
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
        if event_type == "prediction_commitment":
            if event["prediction_commitment_digest"] != _prediction_commitment_digest(
                event
            ):
                raise EpistemicActionIntegrityError(
                    "prediction_commitment_mismatch"
                )
            _validate_observation_window(
                event["observation_window_start_at"],
                event["observation_window_end_at"],
            )
            if event["action_id"] in seen_prediction_actions:
                raise EpistemicActionIntegrityError(
                    "duplicate_logical_identity"
                )
            seen_prediction_actions.add(event["action_id"])
        elif event_type == "action_binding":
            related_events = [
                prior_by_id[item]
                for item in event.get("related_event_ids", [])
                if item in prior_by_id
            ]
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
                or event.get("related_event_ids")
                != [str(predictions[0]["event_id"])]
            ):
                raise EpistemicActionIntegrityError("event_predecessor_mismatch")
            if event.get("prediction_sequence") != predictions[0].get(
                "sequence"
            ):
                raise EpistemicActionIntegrityError("event_predecessor_mismatch")
            if _timestamp_value(event["action_started_at"]) <= _timestamp_value(
                predictions[0]["created_at"]
            ):
                raise EpistemicActionIntegrityError("event_predecessor_mismatch")
            if _timestamp_value(event["action_started_at"]) >= _timestamp_value(
                predictions[0]["observation_window_end_at"]
            ):
                raise EpistemicActionIntegrityError(
                    "action_outside_observation_window"
                )
        elif event_type == "observation":
            related_events = [
                prior_by_id[item]
                for item in event.get("related_event_ids", [])
                if item in prior_by_id
            ]
            actions = [
                item
                for item in related_events
                if item.get("event_type") == "action_binding"
            ]
            if (
                len(actions) != 1
                or actions[0].get("action_id") != event.get("action_id")
                or actions[0].get("request_id") != event.get("request_id")
                or actions[0].get("attempt_id") != event.get("attempt_id")
                or actions[0].get("tool_use_id") != event.get("tool_use_id")
                or event.get("related_event_ids")
                != [str(actions[0]["event_id"])]
            ):
                raise EpistemicActionIntegrityError("event_predecessor_mismatch")
            if event["action_id"] in seen_observation_actions:
                raise EpistemicActionIntegrityError(
                    "duplicate_logical_identity"
                )
            seen_observation_actions.add(event["action_id"])
            prediction = next(
                (
                    item
                    for item in result
                    if item.get("event_type") == "prediction_commitment"
                    and item.get("action_id") == event.get("action_id")
                ),
                None,
            )
            if prediction is None:
                raise EpistemicActionIntegrityError("event_predecessor_mismatch")
            if event.get("observation_status") == "observed":
                observed_at = event.get("observed_at")
                if not isinstance(observed_at, str) or not _observation_in_window(
                    observed_at,
                    start_at=prediction["observation_window_start_at"],
                    end_at=prediction["observation_window_end_at"],
                ):
                    raise EpistemicActionIntegrityError(
                        "observation_outside_window"
                    )
                action = actions[0]
                if _timestamp_value(observed_at) < _timestamp_value(
                    action["action_started_at"]
                ):
                    raise EpistemicActionIntegrityError(
                        "observation_before_action"
                    )
                if prediction.get("expected_observation_facet_ids") and not event.get(
                    "observed_observation_facet_ids"
                ):
                    raise EpistemicActionIntegrityError(
                        "observation_facets_required"
                    )
        elif event_type == "observation_conflict":
            related_events = [
                prior_by_id[item]
                for item in event.get("related_event_ids", [])
                if item in prior_by_id
            ]
            actions = [
                item
                for item in result
                if item.get("event_type") == "action_binding"
                and item.get("action_id") == event.get("action_id")
            ]
            if len(actions) != 1 or not related_events or not any(
                item.get("event_type") == "observation"
                and item.get("action_id") == event.get("action_id")
                for item in related_events
            ):
                raise EpistemicActionIntegrityError("event_predecessor_mismatch")
            if any(
                item.get("action_id") != event.get("action_id")
                or item.get("event_type") not in {"observation", "observation_conflict"}
                for item in related_events
            ):
                raise EpistemicActionIntegrityError("event_predecessor_mismatch")
            if (
                event.get("request_id") != actions[0].get("request_id")
                or event.get("attempt_id") != actions[0].get("attempt_id")
                or event.get("tool_use_id") != actions[0].get("tool_use_id")
            ):
                raise EpistemicActionIntegrityError("event_predecessor_mismatch")
        elif event_type == "discrepancy":
            context = _discrepancy_context(result, event["action_id"])
            prediction = context["prediction"]
            action = context["action"]
            if prediction is None or action is None:
                raise EpistemicActionIntegrityError("event_predecessor_mismatch")
            expected_source_event_ids = context["source_event_ids"]
            expected_discrepancy_kind = context["discrepancy_kind"]
            expected_observation = context["observation"]
            if (
                event["source_event_ids"] != expected_source_event_ids
                or event.get("related_event_ids") != expected_source_event_ids
                or event["discrepancy_kind"] != expected_discrepancy_kind
                or event.get("request_id") != prediction.get("request_id")
                or event.get("attempt_id") != prediction.get("attempt_id")
                or event.get("tool_use_id") != prediction.get("tool_use_id")
                or event.get("prediction_id") != prediction.get("prediction_id")
                or event.get("expected_observation_digest")
                != prediction.get("expected_observation_digest")
            ):
                raise EpistemicActionIntegrityError(
                    "discrepancy_derivation_mismatch"
                )
            expected_observed_digest = (
                expected_observation.get("observation_digest")
                if expected_observation is not None
                and expected_observation.get("observation_status") == "observed"
                else None
            )
            if event.get("observed_observation_digest") != expected_observed_digest:
                raise EpistemicActionIntegrityError(
                    "discrepancy_derivation_mismatch"
                )
        elif event_type == "model_update_candidate":
            related_event_ids = event.get("related_event_ids", [])
            if len(related_event_ids) != 1:
                raise EpistemicActionIntegrityError("candidate_derivation_mismatch")
            discrepancy = prior_by_id.get(related_event_ids[0])
            if discrepancy is None or discrepancy.get("event_type") != "discrepancy":
                raise EpistemicActionIntegrityError("event_predecessor_mismatch")
            context = _discrepancy_context(result, discrepancy["action_id"])
            prediction = context["prediction"]
            action = context["action"]
            if prediction is None or action is None:
                raise EpistemicActionIntegrityError("event_predecessor_mismatch")
            candidate_id = _derived_id(
                "candidate",
                {
                    "action_id": discrepancy["action_id"],
                    "discrepancy_event_id": discrepancy["event_id"],
                },
            )
            expected_source_event_ids = _candidate_source_event_ids(discrepancy)
            expected_update_kind = _candidate_update_kind(
                discrepancy["discrepancy_kind"]
            )
            expected_candidate = {
                "request_id": prediction["request_id"],
                "attempt_id": prediction["attempt_id"],
                "action_id": discrepancy["action_id"],
                "candidate_id": candidate_id,
                "candidate_status": "shadow_only",
                "discrepancy_kind": discrepancy["discrepancy_kind"],
                "update_kind": expected_update_kind,
                "source_event_ids": expected_source_event_ids,
                "related_event_ids": [str(discrepancy["event_id"])],
                "claim_ceiling": EPISTEMIC_ACTION_CANDIDATE_CLAIM_CEILING,
                "tool_use_id": prediction.get("tool_use_id"),
                "hypothesis_digest": prediction["hypothesis_digest"],
                "expected_change_digest": prediction["expected_change_digest"],
                "falsifier_digest": prediction["falsifier_digest"],
                "confidence": prediction["confidence"],
                "action_plan_digest": prediction["action_plan_digest"],
                "observation_window_digest": prediction[
                    "observation_window_digest"
                ],
                "pre_action_marker": prediction["pre_action_marker"],
            }
            if any(
                event.get(key) != expected_value
                for key, expected_value in expected_candidate.items()
            ):
                raise EpistemicActionIntegrityError(
                    "candidate_derivation_mismatch"
                )
        logical_identity = _logical_identity_key(event)
        if logical_identity is not None:
            if logical_identity in seen_logical_identities:
                raise EpistemicActionIntegrityError(
                    "duplicate_logical_identity"
                )
            seen_logical_identities.add(logical_identity)
        seen_event_ids.add(event["event_id"])
        result.append(dict(event))
        expected_sequence += 1
        previous_digest = event["event_digest"]
    return result


def _reject_symlink_ancestors(path: Path) -> None:
    current = path
    while current != current.parent:
        if current.is_symlink():
            raise EpistemicActionIntegrityError("store_not_regular")
        current = current.parent


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
        _reject_symlink_ancestors(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        _reject_symlink_ancestors(self.path)
        flags = os.O_CREAT | os.O_RDWR
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(self.path, flags, 0o600)
        except OSError as exc:
            raise EpistemicActionIntegrityError("store_not_regular") from exc
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
        _reject_symlink_ancestors(self.store_path)
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
        self._append_lock = threading.RLock()

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
        created_at: Any = _UNSET,
        expected_sequence: int | None = None,
    ) -> tuple[dict[str, Any], bool]:
        if not isinstance(event_type, str) or event_type not in EPISTEMIC_ACTION_EVENT_TYPES:
            raise EpistemicActionError("event_type_invalid")
        if not isinstance(state, str) or state not in EPISTEMIC_ACTION_STATES:
            raise EpistemicActionError("unsupported_event_state")
        logical: dict[str, Any] = {
            "schema_version": EPISTEMIC_ACTION_EVENT_SCHEMA_VERSION,
            "event_type": event_type,
            "event_id": _event_id_for(event_type, identity),
            "state": state,
            "created_at": _event_timestamp(created_at),
            "session_id": self.session_id,
            "turn_id": self.turn_id,
        }
        logical.update(fields)
        with self._append_lock, _StoreLock(self._lock_path()):
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
            logical_identity = _logical_identity_key(logical)
            if logical_identity is not None and any(
                _logical_identity_key(event) == logical_identity
                for event in current
            ):
                # The losing cross-instance attempt is deliberately refused
                # before append.  The owner ABI does not retain a durable
                # race-loser record or infer a causal winner/loser verdict.
                raise EpistemicActionConflictError(
                    "duplicate_logical_identity",
                    state="ambiguous",
                )
            observed_sequence = len(current)
            required_sequence = (
                self._observed_sequence
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
            store_flags = os.O_CREAT | os.O_WRONLY | os.O_APPEND
            if hasattr(os, "O_NOFOLLOW"):
                store_flags |= os.O_NOFOLLOW
            try:
                store_descriptor = os.open(self.store_path, store_flags, 0o600)
            except OSError as exc:
                raise EpistemicActionIntegrityError("store_not_regular") from exc
            with os.fdopen(store_descriptor, "a", encoding="utf-8") as handle:
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
        observation_window_start_at: Any = _UNSET,
        observation_window_end_at: Any = _UNSET,
        expected_observation_facet_ids: Iterable[str] = (),
        tool_use_id: str | None = None,
        expected_digest: str | None = None,
        prediction_id: str | None = None,
        created_at: Any = _UNSET,
        expected_sequence: int | None = None,
    ) -> dict[str, Any]:
        """Commit a prediction before an action can be bound."""

        safe_created_at = _provided_created_at(created_at)
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
        safe_window_start, safe_window_end = _validate_observation_window(
            observation_window_start_at,
            observation_window_end_at,
        )
        safe_expected_facets = _unique_safe_ids(
            list(expected_observation_facet_ids),
            "expected_observation_facet_ids",
        )
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
                    "observation_window_start_at": safe_window_start,
                    "observation_window_end_at": safe_window_end,
                    "expected_observation_facet_ids": safe_expected_facets,
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
                "observation_window_start_at": safe_window_start,
                "observation_window_end_at": safe_window_end,
                "expected_observation_facet_ids": safe_expected_facets,
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
        commitment_digest = _prediction_commitment_digest(
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
                "observation_window_start_at": safe_window_start,
                "observation_window_end_at": safe_window_end,
                "expected_observation_facet_ids": safe_expected_facets,
            }
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
                "observation_window_start_at": safe_window_start,
                "observation_window_end_at": safe_window_end,
                "expected_observation_facet_ids": safe_expected_facets,
                "action_id": safe_action_id,
                "expected_observation_digest": safe_expected,
                **(
                    {"tool_use_id": safe_tool_use_id}
                    if safe_tool_use_id is not None
                    else {}
                ),
            },
            identity={"prediction_id": safe_prediction_id},
            created_at=safe_created_at,
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
        action_started_at: Any = _UNSET,
        tool_use_id: str | None = None,
        prediction_id: str | None = None,
        created_at: Any = _UNSET,
        expected_sequence: int | None = None,
    ) -> dict[str, Any]:
        """Bind an action only to an already committed prediction."""

        safe_created_at = _provided_created_at(created_at)
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
        if _timestamp_value(safe_action_started_at) <= _timestamp_value(
            prediction["created_at"]
        ):
            refusal = self._record_refusal(
                "post_hoc_prediction",
                related_event_ids=[str(prediction["event_id"])],
                fields={"action_id": safe_action_id},
            )
            raise EpistemicActionOrderingError(
                "post_hoc_prediction",
                event=refusal,
            )
        if _timestamp_value(safe_action_started_at) >= _timestamp_value(
            prediction["observation_window_end_at"]
        ):
            refusal = self._record_refusal(
                "action_outside_observation_window",
                related_event_ids=[str(prediction["event_id"])],
                fields={"action_id": safe_action_id},
            )
            raise EpistemicActionOrderingError(
                "action_outside_observation_window",
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
                "prediction_sequence": prediction["sequence"],
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
            created_at=safe_created_at,
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
        observed_at: Any = _UNSET,
        observed_observation_facet_ids: Iterable[str] = (),
        observation_id: str | None = None,
        observation_status: str = "observed",
        reason_code: str | None = None,
        created_at: Any = _UNSET,
        expected_sequence: int | None = None,
    ) -> dict[str, Any]:
        """Append one observation or an explicit missing/unknown state."""

        safe_created_at = _provided_created_at(created_at)
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
        safe_observed_facets = _unique_safe_ids(
            list(observed_observation_facet_ids),
            "observed_observation_facet_ids",
        )
        if observation_digest is None:
            observation_digest = observed_digest
        elif observed_digest is not None and observed_digest != observation_digest:
            raise EpistemicActionPrivacyError("digest_invalid")
        if (
            not isinstance(observation_status, str)
            or observation_status not in EPISTEMIC_ACTION_OBSERVATION_STATUSES
        ):
            raise EpistemicActionPrivacyError("observation_status_invalid")
        if observation_status == "observed":
            safe_observation_digest = _safe_digest(
                observation_digest,
                "observation_digest",
            )
            if not safe_evidence_ref_ids:
                raise EpistemicActionPrivacyError(
                    "observation_evidence_required"
                )
            if observed_at is _UNSET:
                raise EpistemicActionPrivacyError(
                    "observation_timestamp_required"
                )
            safe_observed_at = _safe_timestamp(observed_at)
        else:
            if observation_digest is not None:
                raise EpistemicActionPrivacyError("observation_digest_forbidden")
            safe_observation_digest = None
            if observed_at is not _UNSET and observed_at is not None:
                raise EpistemicActionPrivacyError("observation_outside_window")
            safe_observed_at = None
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
        prediction_event = next(
            (
                event
                for event in self._prediction_events()
                if event.get("action_id") == safe_action_id
            ),
            None,
        )
        if prediction_event is None:
            raise EpistemicActionIntegrityError("event_predecessor_mismatch")
        if observation_status == "observed":
            if not _observation_in_window(
                safe_observed_at,
                start_at=prediction_event["observation_window_start_at"],
                end_at=prediction_event["observation_window_end_at"],
            ):
                refusal = self._record_refusal(
                    "observation_outside_window",
                    related_event_ids=[str(action_event["event_id"])],
                    fields={"action_id": safe_action_id},
                )
                raise EpistemicActionOrderingError(
                    "observation_outside_window",
                    event=refusal,
                )
            if _timestamp_value(safe_observed_at) < _timestamp_value(
                action_event["action_started_at"]
            ):
                refusal = self._record_refusal(
                    "observation_before_action",
                    related_event_ids=[str(action_event["event_id"])],
                    fields={"action_id": safe_action_id},
                )
                raise EpistemicActionOrderingError(
                    "observation_before_action",
                    event=refusal,
                )
            if prediction_event.get("expected_observation_facet_ids") and not safe_observed_facets:
                raise EpistemicActionPrivacyError("observation_facets_required")
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
                and same_id.get("observed_at") == safe_observed_at
                and same_id.get("observed_observation_facet_ids", [])
                == safe_observed_facets
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
                safe_observed_at,
                safe_observed_facets,
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
                safe_observed_at,
                safe_observed_facets,
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
            "observed_observation_facet_ids": safe_observed_facets,
            "related_event_ids": [str(action_event["event_id"])],
        }
        if safe_tool_use_id is not None:
            fields["tool_use_id"] = safe_tool_use_id
        if safe_observation_digest is not None:
            fields["observation_digest"] = safe_observation_digest
        if safe_observed_at is not None:
            fields["observed_at"] = safe_observed_at
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
            created_at=safe_created_at,
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
        observed_at: str | None,
        observed_observation_facet_ids: list[str],
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
            "observed_observation_facet_ids": observed_observation_facet_ids,
            "related_event_ids": related_event_ids,
        }
        if tool_use_id is not None:
            fields["tool_use_id"] = tool_use_id
        if observation_digest is not None:
            fields["observation_digest"] = observation_digest
        if observed_at is not None:
            fields["observed_at"] = observed_at
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
                "observed_at": observed_at,
                "observed_observation_facet_ids": observed_observation_facet_ids,
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
        created_at: Any = _UNSET,
        expected_sequence: int | None = None,
    ) -> dict[str, Any]:
        """Derive a bounded discrepancy and persist only a shadow candidate."""

        safe_created_at = _provided_created_at(created_at)
        safe_action_id = _safe_identifier(action_id, "action_id")
        requested_discrepancy_kind = _safe_discrepancy_kind(discrepancy_kind)
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
        context = _discrepancy_context(self._events, safe_action_id)
        prediction = context["prediction"]
        action = context["action"]
        if prediction is None or action is None:
            return {
                "ok": False,
                "state": "unknown",
                "reason_code": "missing_action",
                "action_id": safe_action_id,
                "discrepancy": None,
                "model_update_candidate": None,
            }
        discrepancy_kind = str(context["discrepancy_kind"])
        if (
            requested_discrepancy_kind is not None
            and requested_discrepancy_kind != discrepancy_kind
        ):
            refusal = self._record_refusal(
                "discrepancy_classification_conflict",
                related_event_ids=[
                    str(prediction["event_id"]),
                    str(action["event_id"]),
                    *[
                        str(event["event_id"])
                        for event in context["observations"]
                    ],
                    *[
                        str(event["event_id"])
                        for event in context["conflict_events"]
                    ],
                ][:8],
                fields={
                    "action_id": safe_action_id,
                    "discrepancy_kind": requested_discrepancy_kind,
                },
                state="ambiguous",
            )
            raise EpistemicActionConflictError(
                "discrepancy_classification_conflict",
                state="ambiguous",
                event=refusal,
            )
        observation = context["observation"]
        source_event_ids = context["source_event_ids"]
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
        discrepancy_identity = {
            "action_id": safe_action_id,
            "source_event_ids": source_event_ids,
        }
        existing_discrepancy = next(
            (
                event
                for event in self._events
                if event.get("event_type") == "discrepancy"
                and event.get("action_id") == safe_action_id
                and event.get("source_event_ids") == source_event_ids
            ),
            None,
        )
        if existing_discrepancy is None:
            discrepancy_event, _created = self._append_event(
                event_type="discrepancy",
                state=discrepancy_state,
                fields=fields,
                identity=discrepancy_identity,
                created_at=safe_created_at,
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
        source_event_ids = _candidate_source_event_ids(discrepancy_event)
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
        update_kind = _candidate_update_kind(discrepancy_kind)
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
    except (KeyError, TypeError, ValueError):
        # Malformed JSON values must remain a bounded artifact diagnostic, not
        # leak an implementation exception through validation.
        diagnostics.append("event_shape_invalid")
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
    except (KeyError, TypeError, ValueError):
        return {
            "ok": False,
            "status": "invalid",
            "chain_status": "unknown",
            "event_count": 0,
            "diagnostics": ["event_shape_invalid"],
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
    commit.add_argument("--observation-window-start-at", required=True)
    commit.add_argument("--observation-window-end-at", required=True)
    commit.add_argument(
        "--expected-observation-facet-id",
        action="append",
        default=[],
    )
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
    observe.add_argument("--observed-at")
    observe.add_argument(
        "--observed-observation-facet-id",
        action="append",
        default=[],
    )
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
                    observation_window_start_at=args.observation_window_start_at,
                    observation_window_end_at=args.observation_window_end_at,
                    expected_observation_facet_ids=(
                        args.expected_observation_facet_id
                    ),
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
                observation_kwargs: dict[str, Any] = {
                    "attempt_id": args.attempt_id,
                    "tool_use_id": args.tool_use_id,
                    "evidence_ref_ids": args.evidence_ref_id,
                    "observed_observation_facet_ids": (
                        args.observed_observation_facet_id
                    ),
                    "observation_id": args.observation_id,
                    "observation_status": args.observation_status,
                    "reason_code": args.reason_code,
                }
                if args.observed_at is not None:
                    observation_kwargs["observed_at"] = args.observed_at
                payload = chain.record_observation(
                    args.action_id,
                    args.observation_digest,
                    **observation_kwargs,
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
    except (KeyError, TypeError, ValueError):
        print(
            json.dumps(
                {
                    "ok": False,
                    "state": "refused",
                    "reason_code": "event_shape_invalid",
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
