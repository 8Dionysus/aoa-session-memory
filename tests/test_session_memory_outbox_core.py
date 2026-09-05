from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from scripts.aoa_session_memory_outbox import (
    _projection_outbox_record_recomputed_id,
    _projection_outbox_record_valid,
    projection_component_required_consumers,
    projection_outbox_completion_receipt_identity_valid,
    projection_outbox_record_identity_digest,
    projection_outbox_record_identity_matches,
    projection_outbox_record_integrity_valid,
    projection_outbox_rotate_after_cursor,
)


def _record(
    *,
    session_dir: Path | None = None,
    session_id: str = "session-one",
) -> dict[str, object]:
    publication_dir = session_dir or Path("/tmp/aoa/sessions/session-one")
    record: dict[str, object] = {
        "schema_version": 1,
        "artifact_type": "session_projection_component_outbox",
        "session_id": session_id,
        "old_publish_id": "a" * 64,
        "new_publish_id": "b" * 64,
        "changes": [
            {
                "component_id": "component-one",
                "component_type": "unknown",
                "operation": "replace",
                "old_digest": "c" * 64,
                "new_digest": "d" * 64,
                "source_ref": "tests/component-one",
                "generation_identity": {"generation_id": "generation-one"},
                "required_consumers": [
                    "exact_and_lexical_search",
                    "episode_semantic",
                    "entity_registry",
                    "graph",
                ],
            }
        ],
        "required_consumers": [
            "exact_and_lexical_search",
            "episode_semantic",
            "entity_registry",
            "graph",
        ],
        "created_at": "2026-09-05T00:00:00Z",
        "status": "pending",
        "retry_policy": {
            "mode": "bounded_idempotent_consumer_replay_v1",
            "max_attempts_per_cycle": 3,
        },
        "publication_receipt": {
            "session_dir": str(publication_dir),
            "publish_id": "b" * 64,
        },
        "truth_status": (
            "changed_component_work_intent_not_downstream_completion"
        ),
    }
    record["record_id"] = _projection_outbox_record_recomputed_id(record)
    return record


def test_component_consumer_policy_is_canonical() -> None:
    assert projection_component_required_consumers("task_episode") == [
        "episode_semantic",
        "entity_registry",
        "exact_and_lexical_search",
        "graph",
    ]
    assert projection_component_required_consumers("raw_block") == [
        "exact_and_lexical_search",
        "entity_registry",
    ]
    assert projection_component_required_consumers("unknown") == [
        "exact_and_lexical_search",
        "episode_semantic",
        "entity_registry",
        "graph",
    ]


def test_valid_record_has_stable_identity_and_strict_shape() -> None:
    record = _record()
    valid, diagnostics = _projection_outbox_record_valid(record)

    assert valid, diagnostics
    assert projection_outbox_record_integrity_valid(record)
    assert projection_outbox_record_identity_matches(record, deepcopy(record))
    assert projection_outbox_record_identity_digest(record) == (
        projection_outbox_record_identity_digest(deepcopy(record))
    )


@pytest.mark.parametrize(
    ("field", "value", "diagnostic"),
    [
        ("extra", True, "record_unknown_field:extra"),
        (
            "required_consumers",
            ["graph", "entity_registry", "episode_semantic", "exact_and_lexical_search"],
            "record_required_consumers_not_canonical",
        ),
        ("status", "complete", "record_status_not_pending"),
        (
            "new_publish_id",
            "not-a-sha",
            "record_new_publish_id_invalid",
        ),
    ],
)
def test_strict_record_validator_preserves_shape_negatives(
    field: str,
    value: object,
    diagnostic: str,
) -> None:
    record = _record()
    record[field] = value
    valid, diagnostics = _projection_outbox_record_valid(record)

    assert not valid
    assert diagnostic in diagnostics


def test_strict_record_validator_reads_only_manifest_for_explicit_root_check(
    tmp_path: Path,
) -> None:
    aoa_root = tmp_path / "aoa"
    session_dir = aoa_root / "sessions" / "session-one"
    session_dir.mkdir(parents=True)
    (session_dir / "session.manifest.json").write_text(
        '{"session_id":"session-one"}',
        encoding="utf-8",
    )
    record = _record(session_dir=session_dir)

    valid, diagnostics = _projection_outbox_record_valid(record, aoa_root=aoa_root)
    assert valid, diagnostics

    outside = deepcopy(record)
    outside["publication_receipt"] = {
        "session_dir": str(tmp_path / "outside"),
        "publish_id": "b" * 64,
    }
    outside["record_id"] = _projection_outbox_record_recomputed_id(outside)
    valid, diagnostics = _projection_outbox_record_valid(
        outside,
        aoa_root=aoa_root,
    )
    assert not valid
    assert "record_publication_session_dir_outside_root" in diagnostics


def test_legacy_integrity_keeps_identity_digest_compatibility() -> None:
    record = _record()
    record["record_id"] = projection_outbox_record_identity_digest(record)

    assert projection_outbox_record_integrity_valid(record)
    valid, diagnostics = _projection_outbox_record_valid(record)
    assert not valid
    assert "record_id_content_hash_mismatch" in diagnostics


def test_receipt_identity_and_round_robin_order_fail_closed() -> None:
    record = _record()
    receipt = {
        "consumer": "graph",
        "outbox_record_id": record["record_id"],
        "publish_id": record["new_publish_id"],
        "detail": "legacy-compatible",
    }
    assert projection_outbox_completion_receipt_identity_valid(
        receipt,
        record=record,
        consumer="graph",
    )
    receipt["publish_id"] = "c" * 64
    assert not projection_outbox_completion_receipt_identity_valid(
        receipt,
        record=record,
        consumer="graph",
    )

    records = [{"outbox_record_id": item} for item in ("a", "b", "c")]
    assert [item["outbox_record_id"] for item in projection_outbox_rotate_after_cursor(records, "b")] == [
        "c",
        "a",
        "b",
    ]
    assert projection_outbox_rotate_after_cursor(records, "missing") == records
