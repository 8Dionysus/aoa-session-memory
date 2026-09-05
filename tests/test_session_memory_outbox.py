from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from session_memory_test_support import (
    module,
)

def test_outbox_consumers_complete_only_from_exact_committed_dependencies(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    aoa_root = tmp_path / ".aoa"
    session_dir = aoa_root / "sessions" / "outbox-session"
    session_dir.mkdir(parents=True)
    publish_id = "c" * 64
    module.write_json(
        session_dir / "session.manifest.json",
        {
            "session_id": "outbox-session",
            "archive_status": "indexed",
            "display": {"label": "outbox-session"},
            "index_schema": {
                "projection_publish": {
                    "publish_id": publish_id,
                }
            },
        },
    )
    record = module.session_projection_outbox_record(
        session_dir=session_dir,
        old_snapshot={},
        new_snapshot={
            "task_episode:episode-1": {
                "component_type": "task_episode",
                "digest": "d" * 64,
                "source_ref": "session-index-shards/task-episodes/episode-1.json",
                "generation_identity": {"generation_id": "episode-v1"},
            }
        },
        old_publish_id="",
        new_publish_id=publish_id,
        session_id="outbox-session",
    )
    module.write_projection_outbox_record(session_dir, record)

    blocked_entity = module.complete_entity_registry_outbox_consumers(
        aoa_root
    )
    assert blocked_entity["completed_count"] == 0

    module.write_projection_outbox_consumer_state(
        session_dir,
        record=record,
        consumer="exact_and_lexical_search",
        status="progress",
        reason="legacy_progress_only",
        completion_receipt={"db_commit": "exact"},
    )
    monkeypatch.setattr(
        module,
        "entity_registry_maintenance_status",
        lambda _aoa_root: {
            "status": "current",
            "path": str(aoa_root / module.ENTITY_REGISTRY_PATH),
            "generated_at": "2026-08-10T00:00:00Z",
            "semantic_digest": {"sha256": "registry-digest"},
            "observed_route_source": "operational_route_rollup",
            "observed_source_dependency": {
                "semantic_sha256": "observed-digest"
            },
        },
    )
    monkeypatch.setattr(
        module,
        "entity_registry_observed_rollup_ready",
        lambda _aoa_root: {"ready": True, "status": "current"},
    )
    entity = module.complete_entity_registry_outbox_consumers(
        aoa_root
    )
    assert entity["completed_count"] == 0

    module.write_graph_source_state_ledger(
        aoa_root,
        {
            "sources": {
                module.graph_source_key(
                    "session", "outbox-session", ""
                ): {
                    "status": "current",
                    "source_projection_publish_id": publish_id,
                }
            }
        },
    )
    graph = module.complete_graph_outbox_consumers_from_ledger(
        aoa_root
    )
    assert graph["completed_count"] == 1
    ready = module.projection_outbox_ready_sessions(aoa_root)
    assert ready["records"][0]["pending_consumers"] == [
        "exact_and_lexical_search",
        "episode_semantic",
        "entity_registry",
        "graph",
    ]
def test_projection_component_snapshot_uses_manifest_segment_identity(
    tmp_path: Path,
) -> None:
    projection_dir = tmp_path / "projection"
    segment_dir = projection_dir / "segments"
    segment_dir.mkdir(parents=True)
    segment_index = segment_dir / "000.index.json"
    segment_index.write_text(
        "not-json-and-must-not-be-hydrated", encoding="utf-8"
    )
    input_digest = "a" * 64
    generation_id = "b" * 64
    module.write_json(
        projection_dir / "session.manifest.json",
        {
            "index_schema": {
                "session_index_generation_id": "c" * 64,
            },
            "segments": [
                {
                    "segment_id": "000",
                    "index": str(segment_index),
                    "input_digest": input_digest,
                    "component_identity": {
                        "input_digest": input_digest,
                        "generation_id": generation_id,
                    },
                }
            ],
        },
    )
    module.write_json(
        projection_dir / module.SESSION_INDEX_JSON,
        {"payload": "index"},
    )

    snapshot = module.projection_component_snapshot(projection_dir)

    expected_digest = hashlib.sha256(
        json.dumps(
            {
                "input_digest": input_digest,
                "generation_id": generation_id,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    assert snapshot["segment:000"] == {
        "component_id": "segment:000",
        "component_type": "segment_index",
        "digest": expected_digest,
        "source_ref": "segments/000.index.json",
        "generation_identity": {"generation_id": generation_id},
    }
    assert snapshot["session:index"]["generation_identity"] == {
        "generation_id": "c" * 64,
    }
def test_outbox_completion_crash_replay_is_durable_and_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    aoa_root = tmp_path / ".aoa"
    session_dir = aoa_root / "sessions" / "outbox-crash-session"
    session_dir.mkdir(parents=True)
    publish_id = "e" * 64
    module.write_json(
        session_dir / "session.manifest.json",
        {
            "session_id": "outbox-crash-session",
            "archive_status": "indexed",
            "index_schema": {
                "projection_publish": {"publish_id": publish_id}
            },
        },
    )
    record = module.session_projection_outbox_record(
        session_dir=session_dir,
        old_snapshot={},
        new_snapshot={
            "segment:000": {
                "component_type": "segment_index",
                "digest": "f" * 64,
                "source_ref": "segments/000.index.json",
                "generation_identity": {"generation_id": "segment-v1"},
            }
        },
        old_publish_id="",
        new_publish_id=publish_id,
        session_id="outbox-crash-session",
    )
    written = module.write_projection_outbox_record(
        session_dir, record
    )
    assert written["status"] == "written"

    with pytest.raises(
        ValueError,
        match="projection_outbox_authoritative_receipt_required",
    ):
        module.write_projection_outbox_consumer_state(
            session_dir,
            record=record,
            consumer="exact_and_lexical_search",
            status="complete",
            reason="generic completion is not authoritative",
            completion_receipt={"db_commit": "commit-1"},
        )
    monkeypatch.setattr(module, "utc_now", lambda: "2026-08-23T00:00:00Z")
    progress = module.write_projection_outbox_consumer_state(
        session_dir,
        record=record,
        consumer="exact_and_lexical_search",
        status="progress",
        reason="legacy progress after restart",
        completion_receipt={"db_commit": "commit-1"},
    )
    replay = module.write_projection_outbox_consumer_state(
        session_dir,
        record=record,
        consumer="exact_and_lexical_search",
        status="progress",
        reason="replayed progress",
        completion_receipt={"db_commit": "commit-1"},
    )
    state_path = module.projection_outbox_consumer_state_path(
        session_dir,
        consumer="exact_and_lexical_search",
        record_id=record["record_id"],
    )
    state = module.read_json(state_path, {})
    assert progress["status"] == "progress"
    assert replay["status"] == "progress"
    assert state["attempt_count"] == 2
    assert state["semantic_completion"] is False
    assert state["progress_receipt"] == {"db_commit": "commit-1"}
def test_outbox_terminal_retirement_requires_all_exact_receipts_and_is_replayable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    aoa_root = tmp_path / ".aoa"
    session_dir = aoa_root / "sessions" / "outbox-retirement"
    session_dir.mkdir(parents=True)
    monkeypatch.setattr(
        module,
        "_projection_outbox_completion_receipt_valid",
        lambda *_args, **_kwargs: (True, ""),
    )
    publish_id = "a" * 64
    module.write_json(
        session_dir / "session.manifest.json",
        {
            "session_id": "outbox-retirement",
            "archive_status": "indexed",
            "index_schema": {"projection_publish": {"publish_id": publish_id}},
        },
    )
    record = module.session_projection_outbox_record(
        session_dir=session_dir,
        old_snapshot={},
        new_snapshot={
            "task_episode:episode-1": {
                "component_type": "task_episode",
                "digest": "b" * 64,
                "source_ref": "session-index-shards/task-episodes/episode-1.json",
                "generation_identity": {"generation_id": "episode-v1"},
            }
        },
        old_publish_id="",
        new_publish_id=publish_id,
        session_id="outbox-retirement",
    )
    record_write = module.write_projection_outbox_record(session_dir, record)
    record_path = Path(record_write["path"])
    original_record_bytes = record_path.read_bytes()
    record_path.write_text("{malformed outbox", encoding="utf-8")
    with pytest.raises(
        ValueError,
        match="projection_outbox_record_collision",
    ):
        module.write_projection_outbox_record(session_dir, record)
    assert record_path.read_bytes() == b"{malformed outbox"
    record_path.write_bytes(original_record_bytes)

    partial = module.projection_outbox_retirement_status(
        aoa_root,
        session_dir=session_dir,
        record_path=record_path,
        record=record,
    )
    assert partial["status"] == "consumer_completion_pending"
    assert set(partial["pending_consumers"]) == set(
        module.PROJECTION_OUTBOX_CONSUMERS
    )
    assert module.write_projection_outbox_retirement(
        aoa_root,
        session_dir=session_dir,
        record_path=record_path,
        record=record,
    )["status"] == "deferred"
    assert not list(
        (aoa_root / module.PROJECTION_OUTBOX_RETIREMENTS_DIR).glob("*.json")
    )

    for consumer in record["required_consumers"]:
        module.write_projection_outbox_consumer_state(
            session_dir,
            record=record,
            consumer=consumer,
            status="complete",
            reason="test_exact_commit",
            completion_receipt={"consumer": consumer, "commit": "exact"},
            authoritative=True,
        )
    retirement_path = module.projection_outbox_retirement_path(
        aoa_root,
        record["record_id"],
    )
    retirement_path.parent.mkdir(parents=True, exist_ok=True)
    retirement_path.write_text("{malformed retirement", encoding="utf-8")
    malformed_retirement_bytes = retirement_path.read_bytes()
    with pytest.raises(
        ValueError,
        match="projection_outbox_retirement_collision",
    ):
        module.write_projection_outbox_retirement(
            aoa_root,
            session_dir=session_dir,
            record_path=record_path,
            record=record,
        )
    assert retirement_path.read_bytes() == malformed_retirement_bytes
    retirement_path.unlink()
    ready_before_retirement = module.projection_outbox_ready_sessions(aoa_root)
    assert ready_before_retirement["ready_session_count"] == 1
    assert ready_before_retirement["records"][0]["pending_consumers"] == []
    assert ready_before_retirement["records"][0]["outbox_retirement_pending"] is True

    written = module.write_projection_outbox_retirement(
        aoa_root,
        session_dir=session_dir,
        record_path=record_path,
        record=record,
    )
    replay = module.write_projection_outbox_retirement(
        aoa_root,
        session_dir=session_dir,
        record_path=record_path,
        record=record,
    )
    assert written["status"] == "written"
    assert replay["status"] == "reused"
    retirement_payload = module.read_json(retirement_path, {})
    module.write_json(
        retirement_path,
        {
            **retirement_payload,
            "outbox_record_ref": str(tmp_path / "wrong-outbox-record.json"),
        },
    )
    invalid_ref = module.projection_outbox_retirement_status(
        aoa_root,
        session_dir=session_dir,
        record_path=record_path,
        record=record,
    )
    assert invalid_ref["status"] == "retirement_invalid"
    module.write_json(retirement_path, retirement_payload)
    retired = module.projection_outbox_retirement_status(
        aoa_root,
        session_dir=session_dir,
        record_path=record_path,
        record=record,
    )
    assert retired["ok"] is True
    assert retired["status"] == "retired"
    assert module.read_json(Path(record_write["path"]), {})["status"] == "pending"
    assert module.projection_outbox_ready_sessions(aoa_root)[
        "ready_session_count"
    ] == 0
def test_entity_outbox_ack_requires_exact_search_completion_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    aoa_root = tmp_path / ".aoa"
    session_dir = aoa_root / "sessions" / "entity-predecessor"
    session_dir.mkdir(parents=True)
    publish_id = "c" * 64
    module.write_json(
        session_dir / "session.manifest.json",
        {
            "session_id": "entity-predecessor",
            "archive_status": "indexed",
            "index_schema": {
                "projection_publish": {"publish_id": publish_id}
            },
        },
    )
    record = module.session_projection_outbox_record(
        session_dir=session_dir,
        old_snapshot={},
        new_snapshot={
            "raw_block:block-1": {
                "component_type": "raw_block",
                "digest": "d" * 64,
                "source_ref": "raw/blocks/block-1.jsonl",
                "generation_identity": {},
            }
        },
        old_publish_id="",
        new_publish_id=publish_id,
        session_id="entity-predecessor",
    )
    module.write_projection_outbox_record(session_dir, record)
    search_state_path = module.projection_outbox_consumer_state_path(
        session_dir,
        consumer="exact_and_lexical_search",
        record_id=record["record_id"],
    )
    module.write_json(
        search_state_path,
        {
            "schema_version": 1,
            "artifact_type": "projection_outbox_consumer_state",
            "record_id": record["record_id"],
            "session_id": "entity-predecessor",
            "consumer": "exact_and_lexical_search",
            "source_publish_id": publish_id,
            "status": "complete",
            "semantic_completion": False,
            "completion_receipt": {},
        },
    )
    search_db = module.search_db_path(aoa_root)
    search_db.parent.mkdir(parents=True, exist_ok=True)
    search_db.touch()
    monkeypatch.setattr(
        module,
        "entity_registry_maintenance_status",
        lambda _aoa_root: {
            "status": "current",
            "observed_route_source": "archived_route_terms",
            "path": str(aoa_root / "entity-registry.json"),
            "generated_at": "2026-08-26T00:00:00Z",
            "semantic_digest": "registry-digest",
        },
    )

    result = module.complete_entity_registry_outbox_consumers(aoa_root)

    assert result["status"] == "no_completion"
    assert result["completed_count"] == 0
    assert result["deferred"][0]["reason"] == (
        "exact_search_predecessor_not_complete"
    )
    assert result["deferred"][0]["predecessor_diagnostic"] == (
        "consumer_completion_receipt_missing_or_mismatched"
    )
    assert not module.projection_outbox_consumer_state_path(
        session_dir,
        consumer="entity_registry",
        record_id=record["record_id"],
    ).exists()
def test_outbox_consumer_lanes_are_fair_restart_safe_and_fail_closed(
    tmp_path: Path,
) -> None:
    aoa_root = tmp_path / ".aoa"

    def write_task_episode_record(
        session_id: str,
        publish_id: str,
        created_at: str,
    ) -> tuple[Path, dict[str, Any]]:
        session_dir = aoa_root / "sessions" / session_id
        session_dir.mkdir(parents=True)
        module.write_json(
            session_dir / "session.manifest.json",
            {
                "session_id": session_id,
                "archive_status": "indexed",
                "index_schema": {
                    "projection_publish": {"publish_id": publish_id}
                },
            },
        )
        record = module.session_projection_outbox_record(
            session_dir=session_dir,
            old_snapshot={},
            new_snapshot={
                "task_episode:episode-1": {
                    "component_type": "task_episode",
                    "digest": f"digest-{session_id}",
                    "source_ref": "session-index-shards/task-episodes/episode-1.json",
                    "generation_identity": {"generation_id": "episode-v1"},
                }
            },
            old_publish_id="",
            new_publish_id=publish_id,
            session_id=session_id,
        )
        record["created_at"] = created_at
        record["record_id"] = module._projection_outbox_record_recomputed_id(
            record
        )
        module.write_projection_outbox_record(session_dir, record)
        return session_dir, record

    sessions = [
        write_task_episode_record(
            "fair-a", "a" * 64, "2026-08-26T00:00:01Z"
        ),
        write_task_episode_record(
            "fair-b", "b" * 64, "2026-08-26T00:00:02Z"
        ),
        write_task_episode_record(
            "fair-c", "c" * 64, "2026-08-26T00:00:03Z"
        ),
    ]
    records_by_session = {record["session_id"]: record for _, record in sessions}

    first = module.projection_outbox_ready_sessions(
        aoa_root,
        limit=1,
        consumer="graph",
        advance_cursor=True,
    )
    assert first["records"][0]["session_id"] == "fair-a"
    assert first["missing_consumer_state_record_count"] == 3
    assert first["blocked_record_count"] == 0

    second = module.projection_outbox_ready_sessions(
        aoa_root,
        limit=1,
        consumer="graph",
        advance_cursor=True,
    )
    third = module.projection_outbox_ready_sessions(
        aoa_root,
        limit=1,
        consumer="graph",
        advance_cursor=True,
    )
    fourth_after_restart = module.projection_outbox_ready_sessions(
        aoa_root,
        limit=1,
        consumer="graph",
        advance_cursor=True,
    )
    assert [
        second["records"][0]["session_id"],
        third["records"][0]["session_id"],
        fourth_after_restart["records"][0]["session_id"],
    ] == ["fair-b", "fair-c", "fair-a"]
    fairness_state = module.projection_outbox_fairness_state(aoa_root)
    assert fairness_state["ok"] is True
    assert fairness_state["cursor_by_consumer"]["graph"] == records_by_session[
        "fair-a"
    ]["record_id"]

    entity_lane = module.projection_outbox_ready_sessions(
        aoa_root,
        limit=3,
        consumer="entity_registry",
    )
    assert [
        item["session_id"] for item in entity_lane["records"]
    ] == ["fair-a", "fair-b", "fair-c"]

    invalid_session_dir, invalid_record = sessions[0]
    invalid_path = Path(
        module.projection_outbox_record_path(
            invalid_session_dir,
            invalid_record["record_id"],
        )
    )
    invalid_payload = module.read_json(invalid_path, {})
    invalid_payload["created_at"] = ""
    module.write_json(invalid_path, invalid_payload)
    invalid_bytes = invalid_path.read_bytes()
    after_invalid = module.projection_outbox_ready_sessions(
        aoa_root,
        limit=3,
        consumer="graph",
    )
    assert after_invalid["blocked_record_count"] == 1
    assert "record_created_at_missing" in after_invalid["blocked_records"][0][
        "diagnostics"
    ]
    assert "fair-a" not in {
        item["session_id"] for item in after_invalid["records"]
    }
    assert invalid_path.read_bytes() == invalid_bytes

    fairness_path = module.projection_outbox_fairness_state_path(aoa_root)
    module.write_json(fairness_path, {"schema_version": 999})
    fairness_bytes = fairness_path.read_bytes()
    scheduler_blocked = module.projection_outbox_ready_sessions(
        aoa_root,
        limit=3,
        consumer="graph",
    )
    assert scheduler_blocked["status"] == "scheduler_state_invalid"
    assert scheduler_blocked["records"] == []
    assert fairness_path.read_bytes() == fairness_bytes
def test_outbox_receipt_identity_and_unverified_child_reconcile_are_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    aoa_root = tmp_path / ".aoa"
    session_dir = aoa_root / "sessions" / "receipt-identity"
    session_dir.mkdir(parents=True)
    publish_id = "d" * 64
    module.write_json(
        session_dir / "session.manifest.json",
        {
            "session_id": "receipt-identity",
            "archive_status": "indexed",
            "index_schema": {"projection_publish": {"publish_id": publish_id}},
        },
    )
    record = module.session_projection_outbox_record(
        session_dir=session_dir,
        old_snapshot={},
        new_snapshot={
            "task_episode:episode-1": {
                "component_type": "task_episode",
                "digest": "e" * 64,
                "source_ref": "episode.json",
                "generation_identity": {"generation_id": "episode-v1"},
            }
        },
        old_publish_id="",
        new_publish_id=publish_id,
        session_id="receipt-identity",
    )
    with pytest.raises(
        ValueError,
        match="projection_outbox_authoritative_receipt_invalid",
    ):
        module.write_projection_outbox_consumer_state(
            session_dir,
            record=record,
            consumer="graph",
            status="complete",
            reason="wrong receipt identity",
            completion_receipt={"consumer": "entity_registry"},
            authoritative=True,
        )

    calls: list[str] = []

    def graph(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        calls.append("graph")
        return {"completed_count": 0}

    def entity(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        calls.append("entity")
        return {"completed_count": 0}

    def retirement(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        calls.append("retirement")
        return {"written_count": 0}

    monkeypatch.setattr(module, "complete_graph_outbox_consumers_from_ledger", graph)
    monkeypatch.setattr(module, "complete_entity_registry_outbox_consumers", entity)
    monkeypatch.setattr(module, "reconcile_projection_outbox_retirements", retirement)
    reconciled = module.automatic_outbox_convergence_postpass(
        aoa_root=aoa_root,
        target="receipt-identity",
        launch_result_verified=False,
    )
    assert reconciled["status"] == "completed_after_unverified_child"
    assert reconciled["child_result_verified"] is False
    assert calls == ["graph", "entity", "retirement"]
def test_retry_dispatch_hands_projection_to_downstream_and_closes_only_after_retirement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    aoa_root.mkdir(parents=True)
    session_id = "outbox-stage-session"
    options = {
        "persistent_obligation": True,
        "obligation_kind": module.SESSION_PROJECTION_FRESHNESS_OBLIGATION_KIND,
        "session_id": session_id,
        "session_dir": str(aoa_root / "sessions" / session_id),
        "required_stable_projection": True,
        "required_search_consumer": True,
        "outbox_convergence_required": True,
        "convergence_stage": "projection",
    }

    def schedule(queue_payload: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        return (
            module.auto_maintenance_retry_upsert_item(
                queue_payload,
                profile="backlog",
                target=session_id,
                reason="timer_backlog",
                launch_status="freshness_obligation_enqueued",
                options=options,
                now_epoch=1_000.0,
                initial_delay_seconds=0,
            ),
            True,
        )

    module.mutate_auto_maintenance_retry_queue(
        aoa_root,
        schedule,
        now_epoch=1_000.0,
    )
    phase = 1
    obligation_calls = 0
    convergence_calls = 0
    launches: list[dict[str, Any]] = []

    def fake_obligation(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        nonlocal obligation_calls
        obligation_calls += 1
        satisfied = phase == 2 or obligation_calls >= 2
        return {
            "ok": satisfied,
            "status": "satisfied" if satisfied else "remaining",
            "projected_capture_bytes": 20 if satisfied else 10,
            "satisfied_axes": ["capture", "stable_session_projection", "search"]
            if satisfied
            else [],
            "remaining_axes": [] if satisfied else ["capture"],
        }

    def fake_convergence(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        nonlocal convergence_calls
        convergence_calls += 1
        if phase == 1:
            return {
                "ok": False,
                "status": "remaining",
                "outbox_present": True,
                "pending_consumers": ["entity_registry", "graph"],
            }
        return {
            "ok": convergence_calls >= 2,
            "status": "converged" if convergence_calls >= 2 else "remaining",
            "outbox_present": True,
            "pending_consumers": []
            if convergence_calls >= 2
            else ["graph"],
        }

    def fake_launch(**kwargs: Any) -> dict[str, Any]:
        launches.append(kwargs)
        return {
            "schema_version": 1,
            "artifact_type": "auto_maintenance_resource_launch",
            "ok": True,
            "status": "completed",
            "child_result_verified": True,
        }

    monkeypatch.setattr(module, "session_projection_freshness_obligation_status", fake_obligation)
    monkeypatch.setattr(module, "session_projection_outbox_convergence_status", fake_convergence)
    monkeypatch.setattr(module, "auto_maintenance_resource_launch", fake_launch)
    monkeypatch.setattr(
        module,
        "automatic_outbox_convergence_postpass",
        lambda **_kwargs: {
            "status": "completed",
            "graph": {"completed_count": 1},
            "entity": {"completed_count": 1},
            "retirement": {"written_count": 1},
        },
    )

    first = module.auto_maintenance_retry_dispatch(
        workspace_root=workspace,
        aoa_root=aoa_root,
        apply=True,
        limit=1,
        now_epoch=1_001.0,
    )
    first_result = first["results"][0]
    assert first_result["disposition"] == (
        "projection_stage_completed_downstream_pending"
    )
    assert first_result["convergence_stage_after"] == "downstream"
    assert "projection-catchup" in launches[0]["child_command_override"]
    assert launches[0]["repair_indexes"] is False
    assert launches[0]["repair_graph"] is False
    staged = module.auto_maintenance_retry_queue_status(
        aoa_root,
        now_epoch=1_001.0,
    )
    assert staged["items"]["backlog:" + session_id]["options"][
        "convergence_stage"
    ] == "downstream"

    phase = 2
    obligation_calls = 0
    convergence_calls = 0
    second = module.auto_maintenance_retry_dispatch(
        workspace_root=workspace,
        aoa_root=aoa_root,
        apply=True,
        limit=1,
        now_epoch=1_003.0,
    )
    second_result = second["results"][0]
    assert second_result["launch_status"] == "outbox_convergence_satisfied"
    assert second_result["disposition"] == "completed"
    assert second_result["convergence_stage_before"] == "downstream"
    assert "auto-maintenance" in launches[1]["child_command_override"]
    assert session_id in launches[1]["child_command_override"]
    assert launches[1]["repair_indexes"] is True
    assert launches[1]["repair_graph"] is True
    assert module.auto_maintenance_retry_queue_status(aoa_root)[
        "queued_count"
    ] == 0
