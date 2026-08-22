#!/usr/bin/env python3
"""Typed, public-safe identity binding for session validation evidence.

This module is deliberately an adapter and admission surface, not a validation
owner.  It accepts only structured owner receipts, joins them to an exact
session/projection context, and preserves missing or unobservable fields
instead of inferring them from command text or session prose.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from typing import Any


SCHEMA_VERSION = "identity_bound_session_telemetry_v1"
OWNER_RECEIPT_SCHEMA_VERSION = "validation_owner_telemetry_receipt_v1"
OWNER_RECEIPT_ARTIFACT = "validation_owner_telemetry_receipt"
PACKET_ARTIFACT = "identity_bound_session_telemetry"

FIELD_STATES = (
    "known",
    "unknown",
    "missing",
    "null",
    "unobservable",
    "excluded",
)
REVIEW_STATES = ("provisional", "reviewed", "excluded", "unknown")
ELIGIBILITY_STATES = ("eligible_identity_packet", "excluded", "unknown", "unobservable")

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

SAFE_REF_RE = re.compile(r"^[A-Za-z0-9_.:/#@-]{1,512}$")
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
HEX_RE = re.compile(r"^[0-9a-f]{64}$")

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


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


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
    if text.startswith(("/", "~")) or not SAFE_REF_RE.fullmatch(text):
        raise TelemetryError(f"{field}_not_public_safe_ref")
    return text


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
    expected_session_id = _safe_string(expected_context.get("session_id"), "expected_context.session_id")
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
        "session_id": _safe_string(session_id, "scope.session_id"),
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
    return {
        "status": "eligible_identity_packet" if not reasons else "excluded",
        "reasons": reasons,
        "effect_verdict": None,
        "proof": False,
        "acceptance": False,
    }


def _packet_without_id(packet: Mapping[str, Any]) -> dict[str, Any]:
    return {key: copy.deepcopy(value) for key, value in packet.items() if key != "packet_id"}


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
    admitted_receipt: dict[str, Any] | None = None
    receipt_status = "missing"
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
            "claim_ceiling": "identity_bound_observation_only",
            "rejection": rejection,
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
    }
    packet["packet_id"] = canonical_sha256(_packet_without_id(packet))
    return packet


def verify_packet_integrity(packet: Mapping[str, Any]) -> None:
    if not isinstance(packet, Mapping):
        raise TelemetryError("packet_must_be_object")
    packet_id = packet.get("packet_id")
    if not isinstance(packet_id, str) or not SHA256_RE.fullmatch(packet_id):
        raise TelemetryError("packet_id_invalid")
    if canonical_sha256(_packet_without_id(packet)) != packet_id:
        raise TelemetryError("packet_digest_mismatch")
    if packet.get("authority", {}).get("comparison_verdict") is not None:
        raise TelemetryError("comparison_verdict_must_remain_null")


def compare_identity_packets(left: Mapping[str, Any], right: Mapping[str, Any]) -> dict[str, Any]:
    """Admit or exclude a pair; never calculate an effect or select a winner."""

    reasons: list[str] = []
    try:
        verify_packet_integrity(left)
    except TelemetryError as exc:
        reasons.append(f"left_{exc}")
    try:
        verify_packet_integrity(right)
    except TelemetryError as exc:
        reasons.append(f"right_{exc}")

    for name in IDENTITY_FIELDS:
        left_field = left.get("identity", {}).get(name) if isinstance(left.get("identity"), Mapping) else None
        right_field = right.get("identity", {}).get(name) if isinstance(right.get("identity"), Mapping) else None
        if _field_state(left_field) != "known":
            reasons.append(f"left_identity_{name}_{_field_state(left_field)}")
        if _field_state(right_field) != "known":
            reasons.append(f"right_identity_{name}_{_field_state(right_field)}")
        if _field_state(left_field) == "known" and _field_state(right_field) == "known" and _field_value(left_field) != _field_value(right_field):
            reasons.append(f"identity_mismatch:{name}")

    for side, packet in (("left", left), ("right", right)):
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
            reasons.append(f"{side}_owner_receipt_{federation.get('status') if isinstance(federation, Mapping) else 'unknown'}")
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

    unique_reasons = list(dict.fromkeys(reasons))
    return {
        "schema_version": "identity_bound_session_comparison_admission_v1",
        "status": "matched_identity_bound_pair" if not unique_reasons else "excluded_identity_bound_pair",
        "eligible": not unique_reasons,
        "reasons": unique_reasons,
        "effect": None,
        "verdict": None,
        "authority": "session-memory-admission-only; validation-owner-and-eval-verdicts-external",
    }


def capture_receipts_from_events(events: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Read only a dedicated structured facet from generated events.

    Generic command, message, and result fields are intentionally ignored.  A
    malformed or private receipt is returned as no candidate so a caller can
    report an excluded packet without exposing its body.
    """

    receipts: list[dict[str, Any]] = []
    for event in events:
        facets = event.get("facets") if isinstance(event, Mapping) and isinstance(event.get("facets"), Mapping) else {}
        candidate = facets.get("identity_bound_telemetry_receipt")
        if not isinstance(candidate, Mapping):
            continue
        try:
            receipts.append(_normalize_receipt_shape(candidate, verify_id=True))
        except TelemetryError:
            continue
    return receipts


def load_owner_receipt(path: str) -> dict[str, Any]:
    """Load one public-safe receipt file; never read a transcript body."""

    try:
        with open(path, encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise TelemetryError(f"owner_receipt_unreadable:{type(exc).__name__}") from exc
    return _normalize_receipt_shape(value, verify_id=True)
