"""Small, dependency-free projection-outbox record contract.

This module owns the outbox record identity, shape validation, component
consumer derivation, and restart-safe ordering primitive.  It intentionally
does not import the session-memory runtime: durable writes, manifest
publication/lifecycle, consumer routes, and reconciliation remain in
``aoa_session_memory``.  The optional ``aoa_root`` validator argument performs
only the existing bounded containment and session-manifest identity read.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable


PROJECTION_OUTBOX_SCHEMA_VERSION = 1
PROJECTION_OUTBOX_CONSUMER_MAX_ATTEMPTS = 3
PROJECTION_OUTBOX_CONSUMERS = (
    "exact_and_lexical_search",
    "episode_semantic",
    "entity_registry",
    "graph",
)
PROJECTION_OUTBOX_CONSUMER_RECONCILE_ORDER = (
    "exact_and_lexical_search",
    "episode_semantic",
    "entity_registry",
    "graph",
)
PROJECTION_OUTBOX_RECORD_IDENTITY_KEYS = (
    "schema_version",
    "artifact_type",
    "record_id",
    "session_id",
    "old_publish_id",
    "new_publish_id",
    "changes",
    "required_consumers",
)


def projection_component_required_consumers(
    component_type: str,
) -> list[str]:
    if component_type == "task_episode":
        return [
            "episode_semantic",
            "entity_registry",
            "exact_and_lexical_search",
            "graph",
        ]
    if component_type == "raw_block":
        return ["exact_and_lexical_search", "entity_registry"]
    return list(PROJECTION_OUTBOX_CONSUMERS)


def _json_digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def projection_outbox_record_identity_digest(record: dict[str, Any]) -> str:
    identity_payload = {
        key: record.get(key)
        for key in (
            "schema_version",
            "session_id",
            "old_publish_id",
            "new_publish_id",
            "changes",
            "required_consumers",
        )
    }
    return _json_digest(identity_payload)


def projection_outbox_record_identity_matches(
    left: dict[str, Any],
    right: dict[str, Any],
) -> bool:
    return all(
        left.get(key) == right.get(key)
        for key in PROJECTION_OUTBOX_RECORD_IDENTITY_KEYS
    )


def projection_outbox_record_integrity_valid(
    record: dict[str, Any],
) -> bool:
    record_id = str(record.get("record_id") or "")
    session_id = record.get("session_id")
    old_publish_id = record.get("old_publish_id")
    new_publish_id = record.get("new_publish_id")
    changes = record.get("changes")
    publication_receipt = record.get("publication_receipt")
    required_consumers = record.get("required_consumers")
    retry_policy = record.get("retry_policy")
    valid_changes = bool(
        isinstance(changes, list)
        and all(
            isinstance(change, dict)
            and isinstance(change.get("component_id"), str)
            and bool(change.get("component_id"))
            and isinstance(change.get("component_type"), str)
            and bool(change.get("component_type"))
            and change.get("operation") in {"publish", "replace", "tombstone"}
            and isinstance(change.get("old_digest"), str)
            and isinstance(change.get("new_digest"), str)
            and isinstance(change.get("source_ref"), str)
            and isinstance(change.get("generation_identity"), dict)
            and isinstance(change.get("required_consumers"), list)
            and all(
                isinstance(consumer, str)
                for consumer in change.get("required_consumers", [])
            )
            and len(change.get("required_consumers", []))
            == len(set(change.get("required_consumers", [])))
            and all(
                consumer in PROJECTION_OUTBOX_CONSUMERS
                for consumer in change.get("required_consumers", [])
            )
            for change in changes
        )
    )
    return bool(
        record.get("schema_version") == PROJECTION_OUTBOX_SCHEMA_VERSION
        and record.get("artifact_type")
        == "session_projection_component_outbox"
        and re.fullmatch(r"[a-f0-9]{64}", record_id)
        and (
            projection_outbox_record_identity_digest(record) == record_id
            or _projection_outbox_record_recomputed_id(record) == record_id
        )
        and isinstance(session_id, str)
        and bool(session_id)
        and isinstance(old_publish_id, str)
        and isinstance(new_publish_id, str)
        and bool(new_publish_id)
        and record.get("status") == "pending"
        and record.get("truth_status")
        == "changed_component_work_intent_not_downstream_completion"
        and valid_changes
        and isinstance(required_consumers, list)
        and all(isinstance(consumer, str) for consumer in required_consumers)
        and len(required_consumers) == len(set(required_consumers))
        and all(
            consumer in PROJECTION_OUTBOX_CONSUMERS
            for consumer in required_consumers
        )
        and isinstance(record.get("created_at"), str)
        and bool(record.get("created_at"))
        and isinstance(retry_policy, dict)
        and isinstance(publication_receipt, dict)
        and isinstance(publication_receipt.get("session_dir"), str)
        and bool(publication_receipt.get("session_dir"))
        and str(publication_receipt.get("publish_id") or "")
        == new_publish_id
    )


def projection_outbox_rotate_after_cursor(
    records: list[dict[str, Any]],
    cursor: str,
) -> list[dict[str, Any]]:
    if not records or not cursor:
        return list(records)
    cursor_index = next(
        (
            index
            for index, record in enumerate(records)
            if str(record.get("outbox_record_id") or "") == cursor
        ),
        None,
    )
    if cursor_index is None:
        return list(records)
    return [*records[cursor_index + 1 :], *records[: cursor_index + 1]]


def projection_outbox_completion_receipt_identity_valid(
    receipt: Any,
    *,
    record: dict[str, Any],
    consumer: str,
) -> bool:
    """Validate optional receipt identity without constraining legacy detail."""
    if not isinstance(receipt, dict) or not receipt:
        return False
    expected_record_id = str(record.get("record_id") or "")
    expected_publish_id = str(record.get("new_publish_id") or "")
    identity_pairs = (
        ("consumer", consumer),
        ("outbox_record_id", expected_record_id),
        ("record_id", expected_record_id),
        ("source_publish_id", expected_publish_id),
        ("publish_id", expected_publish_id),
    )
    return all(
        key not in receipt or receipt.get(key) == expected
        for key, expected in identity_pairs
    )


def _projection_outbox_json_digest(value: Any) -> str:
    return _json_digest(value)


def _projection_outbox_record_identity_payload(
    record: dict[str, Any],
) -> dict[str, Any]:
    return {
        key: record.get(key)
        for key in (
            "schema_version",
            "artifact_type",
            "session_id",
            "old_publish_id",
            "new_publish_id",
            "changes",
            "required_consumers",
            "created_at",
            "status",
            "retry_policy",
            "publication_receipt",
            "truth_status",
        )
    }


def _projection_outbox_record_recomputed_id(record: dict[str, Any]) -> str:
    return _projection_outbox_json_digest(
        _projection_outbox_record_identity_payload(record)
    )


def _projection_outbox_sha256_or_empty(value: Any) -> bool:
    return value == "" or bool(
        isinstance(value, str)
        and re.fullmatch(r"[a-f0-9]{64}", value)
    )


def _projection_outbox_unique_strings(value: Any) -> bool:
    return isinstance(value, list) and all(
        isinstance(item, str) and bool(item) for item in value
    ) and len(value) == len(set(value))


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _int_value(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _unique_preserving_order(
    values: Iterable[Any],
    *,
    limit: int = 200,
) -> list[str]:
    selected: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "")
        if not text or text in seen:
            continue
        seen.add(text)
        selected.append(text)
        if len(selected) >= limit:
            break
    return selected


def _projection_outbox_record_valid(
    record: Any,
    *,
    aoa_root: Path | None = None,
) -> tuple[bool, list[str]]:
    diagnostics: list[str] = []
    if not isinstance(record, dict) or not record:
        return False, ["record_not_object"]
    required = {
        "schema_version",
        "artifact_type",
        "record_id",
        "session_id",
        "old_publish_id",
        "new_publish_id",
        "changes",
        "required_consumers",
        "created_at",
        "status",
        "publication_receipt",
        "truth_status",
        "retry_policy",
    }
    allowed = required
    diagnostics.extend(
        f"record_unknown_field:{key}"
        for key in sorted(set(record) - allowed)
    )
    diagnostics.extend(
        f"record_required_field_missing:{key}"
        for key in sorted(required - set(record))
    )
    if _int_value(record.get("schema_version"), -1) != PROJECTION_OUTBOX_SCHEMA_VERSION:
        diagnostics.append("record_schema_version_mismatch")
    if record.get("artifact_type") != "session_projection_component_outbox":
        diagnostics.append("record_artifact_type_mismatch")
    record_id = record.get("record_id")
    if not isinstance(record_id, str) or not re.fullmatch(
        r"[a-f0-9]{64}", record_id
    ):
        diagnostics.append("record_id_must_be_sha256")
    session_id = record.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        diagnostics.append("record_session_id_missing")
    if not _projection_outbox_sha256_or_empty(record.get("old_publish_id")):
        diagnostics.append("record_old_publish_id_invalid")
    if not (
        isinstance(record.get("new_publish_id"), str)
        and re.fullmatch(r"[a-f0-9]{64}", record.get("new_publish_id"))
    ):
        diagnostics.append("record_new_publish_id_invalid")
    if not isinstance(record.get("created_at"), str) or not record.get(
        "created_at"
    ):
        diagnostics.append("record_created_at_missing")
    if record.get("status") != "pending":
        diagnostics.append("record_status_not_pending")
    if not isinstance(record.get("retry_policy"), dict):
        diagnostics.append("record_retry_policy_invalid")
    elif set(record["retry_policy"]) != {
        "mode",
        "max_attempts_per_cycle",
    }:
        diagnostics.append("record_retry_policy_shape_invalid")
    elif record["retry_policy"].get("mode") != (
        "bounded_idempotent_consumer_replay_v1"
    ) or not (
        1
        <= _int_value(record["retry_policy"].get("max_attempts_per_cycle"), 0)
        <= PROJECTION_OUTBOX_CONSUMER_MAX_ATTEMPTS
    ):
        diagnostics.append("record_retry_policy_value_invalid")
    if record.get("truth_status") != (
        "changed_component_work_intent_not_downstream_completion"
    ):
        diagnostics.append("record_truth_status_invalid")

    required_consumers = record.get("required_consumers")
    if not _projection_outbox_unique_strings(required_consumers):
        diagnostics.append("record_required_consumers_not_unique_strings")
        required_consumers = []
    canonical_required = [
        consumer
        for consumer in PROJECTION_OUTBOX_CONSUMER_RECONCILE_ORDER
        if consumer in required_consumers
    ]
    if required_consumers != canonical_required or not canonical_required:
        diagnostics.append("record_required_consumers_not_canonical")
    if any(
        consumer not in PROJECTION_OUTBOX_CONSUMER_RECONCILE_ORDER
        for consumer in required_consumers
    ):
        diagnostics.append("record_required_consumer_not_allowlisted")

    changes = record.get("changes")
    if not isinstance(changes, list) or not changes:
        diagnostics.append("record_changes_missing")
        changes = []
    observed_consumers: set[str] = set()
    component_ids: list[str] = []
    for index, change in enumerate(changes):
        prefix = f"record_change_{index}"
        if not isinstance(change, dict):
            diagnostics.append(f"{prefix}_not_object")
            continue
        change_required = {
            "component_id",
            "component_type",
            "operation",
            "old_digest",
            "new_digest",
            "source_ref",
            "generation_identity",
            "required_consumers",
        }
        diagnostics.extend(
            f"{prefix}_unknown_field:{key}"
            for key in sorted(set(change) - change_required)
        )
        diagnostics.extend(
            f"{prefix}_required_field_missing:{key}"
            for key in sorted(change_required - set(change))
        )
        component_id = change.get("component_id")
        if not isinstance(component_id, str) or not component_id:
            diagnostics.append(f"{prefix}_component_id_invalid")
        else:
            component_ids.append(component_id)
        if not isinstance(change.get("component_type"), str) or not change.get(
            "component_type"
        ):
            diagnostics.append(f"{prefix}_component_type_invalid")
        if change.get("operation") not in {"publish", "replace", "tombstone"}:
            diagnostics.append(f"{prefix}_operation_invalid")
        if not _projection_outbox_sha256_or_empty(change.get("old_digest")):
            diagnostics.append(f"{prefix}_old_digest_invalid")
        if not _projection_outbox_sha256_or_empty(change.get("new_digest")):
            diagnostics.append(f"{prefix}_new_digest_invalid")
        if not isinstance(change.get("source_ref"), str):
            diagnostics.append(f"{prefix}_source_ref_invalid")
        if not isinstance(change.get("generation_identity"), dict):
            diagnostics.append(f"{prefix}_generation_identity_invalid")
        change_consumers = change.get("required_consumers")
        if not _projection_outbox_unique_strings(change_consumers):
            diagnostics.append(f"{prefix}_consumers_not_unique_strings")
            change_consumers = []
        expected_change_consumers = projection_component_required_consumers(
            str(change.get("component_type") or "")
        )
        if change_consumers != expected_change_consumers:
            diagnostics.append(f"{prefix}_consumers_not_owner_derived")
        observed_consumers.update(change_consumers)
    if len(component_ids) != len(set(component_ids)):
        diagnostics.append("record_component_ids_not_unique")
    if set(canonical_required) != observed_consumers:
        diagnostics.append("record_consumers_do_not_cover_changes")

    publication = record.get("publication_receipt")
    if not isinstance(publication, dict):
        diagnostics.append("record_publication_receipt_invalid")
        publication = {}
    if set(publication) != {"session_dir", "publish_id"}:
        diagnostics.append("record_publication_receipt_shape_invalid")
    publication_session_dir = publication.get("session_dir")
    if not isinstance(publication_session_dir, str) or not publication_session_dir:
        diagnostics.append("record_publication_session_dir_missing")
    if publication.get("publish_id") != record.get("new_publish_id"):
        diagnostics.append("record_publication_publish_id_mismatch")
    if aoa_root is not None and isinstance(publication_session_dir, str):
        session_dir = Path(publication_session_dir)
        if not session_dir.is_absolute():
            session_dir = aoa_root / session_dir
        try:
            under_root = session_dir.resolve().parent.parent == aoa_root.resolve()
        except OSError:
            under_root = False
        if not under_root:
            diagnostics.append("record_publication_session_dir_outside_root")
        if isinstance(session_id, str):
            manifest = _read_json(session_dir / "session.manifest.json", {})
            if not isinstance(manifest, dict) or not manifest:
                diagnostics.append(
                    "record_publication_session_manifest_missing"
                )
            elif str(manifest.get("session_id") or "") != session_id:
                diagnostics.append(
                    "record_publication_session_manifest_mismatch"
                )

    if isinstance(record_id, str) and re.fullmatch(r"[a-f0-9]{64}", record_id):
        if _projection_outbox_record_recomputed_id(record) != record_id:
            diagnostics.append("record_id_content_hash_mismatch")
    return not diagnostics, _unique_preserving_order(diagnostics)
