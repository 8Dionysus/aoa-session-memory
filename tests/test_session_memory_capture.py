from __future__ import annotations

import json
from pathlib import Path


from session_memory_test_support import (
    SCRIPT,
    module,
    write_jsonl,
)

def test_lifecycle_hooks_queue_compaction_archive_and_worker_indexes(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-14T00-00-00-session-compact.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-14T00:00:00Z", "type": "session_meta", "payload": {"id": "session-compact"}},
            {"timestamp": "2026-05-14T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Archive compaction intervals"}]}},
            {"timestamp": "2026-05-14T00:00:02Z", "type": "turn_context", "payload": {"summary": "first compaction"}},
            {"timestamp": "2026-05-14T00:00:03Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Decision: keep interval archive"}]}},
        ],
    )
    monkeypatch.delenv("AOA_SESSION_MEMORY_FULL_COMPACT_SYNC", raising=False)
    monkeypatch.delenv("AOA_SESSION_MEMORY_FULL_STOP_SYNC", raising=False)
    monkeypatch.setenv("AOA_SESSION_MEMORY_STOP_SYNC_MAX_BYTES", "0")

    pre = module.handle_hook_event(
        "PreCompact",
        {
            "session_id": "session-compact",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "PreCompact",
            "trigger": "auto",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )
    post = module.handle_hook_event(
        "PostCompact",
        {
            "session_id": "session-compact",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "PostCompact",
            "trigger": "auto",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    assert pre["ok"] is True
    assert post["ok"] is True
    assert "indexing_deferred" in pre["actions"]
    assert "indexing_deferred" in post["actions"]
    assert "background_sync_queued" in pre["actions"]
    assert "background_sync_queued" in post["actions"]
    light_session_dir = aoa_root / "sessions" / "2026-05-14__001__codex-in-abyssos"
    light_manifest = json.loads((light_session_dir / "session.manifest.json").read_text(encoding="utf-8"))
    assert light_manifest["archive_status"] == "raw_mirrored_index_deferred"
    assert light_manifest["hooks_seen"] == ["PostCompact", "PreCompact"]
    assert light_manifest["segments"] == []
    light_capture = module.raw_capture_state_for_session(
        light_session_dir
    )
    assert light_capture["status"] == "preserved_unindexed"
    assert Path(light_capture["capture_path"]).is_file()
    assert light_manifest["raw"]["path"] == light_capture["capture_path"]

    worker = module.run_hook_worker(workspace_root=workspace, aoa_root=aoa_root, limit=5)
    assert worker["ok"] is True
    assert worker["processed"] == 1
    assert worker["results"][0]["status"] == "synced"
    session_dir = aoa_root / "sessions" / "2026-05-14__001__archive-compaction-intervals"
    manifest = json.loads((session_dir / "session.manifest.json").read_text(encoding="utf-8"))
    assert manifest["archive_status"] == "indexed"
    assert manifest["archive_format_version"] == 2
    assert set(manifest["hooks_seen"]).issubset(
        set(
            module.operational_hooks_seen(
                session_dir,
                manifest,
            )
        )
    )
    assert module.operational_hooks_seen(
        session_dir,
        manifest,
    ) == [
        "HookWorker:PostCompact",
        "PostCompact",
        "PreCompact",
    ]
    assert [segment["role"] for segment in manifest["segments"]] == ["initial-to-compaction", "compaction-to-latest"]
    assert not light_session_dir.exists()
    raw_blocks = manifest["raw_blocks"]["blocks"]
    assert [block["role"] for block in raw_blocks] == ["initial-to-compaction", "compaction-to-latest"]
    assert raw_blocks[0]["status"] == "sealed"
    assert raw_blocks[1]["status"] == "open"
    assert (session_dir / "raw" / "blocks.index.json").exists()
    assert (session_dir / "raw" / "compaction-events.jsonl").exists()
    assert (session_dir / "raw" / "blocks" / "000__initial-to-compaction.raw.jsonl").exists()
    first_segment_index = json.loads((session_dir / "segments" / "000__initial-to-compaction.index.json").read_text(encoding="utf-8"))
    assert first_segment_index["source_block"]["rel"] == "raw/blocks/000__initial-to-compaction.raw.jsonl"
    assert manifest["segments"][0]["raw_block"]["rel"] == "raw/blocks/000__initial-to-compaction.raw.jsonl"
    compaction_events = [
        json.loads(line)
        for line in (session_dir / "raw" / "compaction-events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert compaction_events
    assert compaction_events[0]["segment_id"] == "000"

    stop = module.handle_hook_event(
        "Stop",
        {
            "session_id": "session-compact",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    assert stop["ok"] is True, stop
    assert "indexing_deferred" in stop["actions"]
    assert "background_sync_queued" in stop["actions"]
    stop_manifest = json.loads((session_dir / "session.manifest.json").read_text(encoding="utf-8"))
    assert stop_manifest["archive_status"] == "indexed"
    assert [segment["role"] for segment in stop_manifest["segments"]] == [
        "initial-to-compaction",
        "compaction-to-latest",
    ]
    assert stop_manifest["latest_event_count"] == 4
    stop_capture = module.raw_capture_state_for_session(
        session_dir
    )
    assert (
        stop_capture["status"]
        == "captured_matches_indexed_projection"
    )
    assert stop_capture["projection_freshness"] == "current"
    assert "Stop" in stop_capture["hooks_seen"]
    assert stop["archive"]["last_good_projection_preserved"] is True

    deferred_audit = module.completion_audit(workspace_root=workspace, aoa_root=aoa_root, check_codex=False)
    topology = [
        item for item in deferred_audit["checklist"] if item["requirement"] == "Segment topology matches raw compaction boundaries"
    ][0]
    assert topology["status"] == "covered"
    assert topology["evidence"]["deferred_archives"] == []

    stop_worker = module.run_hook_worker(workspace_root=workspace, aoa_root=aoa_root, limit=5)
    assert stop_worker["ok"] is True
    assert stop_worker["processed"] == 1
    assert stop_worker["results"][0]["status"] == "already_synced"
    manifest = json.loads((session_dir / "session.manifest.json").read_text(encoding="utf-8"))
    assert manifest["archive_status"] == "indexed"
    assert [segment["role"] for segment in manifest["segments"]] == ["initial-to-compaction", "compaction-to-latest"]
    assert "HookWorker:Stop" in module.operational_hooks_seen(
        session_dir,
        manifest,
    )

    synced = module.sync_session_from_transcript(
        aoa_root=aoa_root,
        event={"session_id": "session-compact", "transcript_path": str(transcript), "cwd": str(workspace)},
        transcript_path=transcript,
        hook_event_name="ManualSync",
    )
    assert synced["segment_count"] == 2
    manifest = json.loads((session_dir / "session.manifest.json").read_text(encoding="utf-8"))
    assert manifest["archive_status"] == "indexed"
    assert manifest["archive_format_version"] == 2
    assert "ManualSync" in manifest["hooks_seen"]
    assert "Stop" in manifest["hooks_seen"]
    assert [segment["role"] for segment in manifest["segments"]] == ["initial-to-compaction", "compaction-to-latest"]
    assert manifest["segments"][0]["raw_block"]["sha256"]
    packet = module.rehydrate_packet(aoa_root, "latest")
    assert "AoA Session Rehydration Packet" in packet
    assert "2026-05-14__001__archive-compaction-intervals" in packet
    assert "`DECISION`" in packet
def test_real_codex_compacted_events_define_segments(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-14T01-00-00-session-real-compact.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-14T01:00:00Z", "type": "session_meta", "payload": {"id": "session-real-compact"}},
            {"timestamp": "2026-05-14T01:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Real compact markers"}]}},
            {"timestamp": "2026-05-14T01:00:02Z", "type": "compacted", "payload": {"message": "", "replacement_history": [{"type": "message", "role": "user"}]}},
            {"timestamp": "2026-05-14T01:00:03Z", "type": "event_msg", "payload": {"type": "context_compacted"}},
            {"timestamp": "2026-05-14T01:00:04Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Decision: real markers are boundaries"}]}},
        ],
    )

    receipt = module.handle_hook_event(
        "Stop",
        {
            "session_id": "session-real-compact",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    assert receipt["ok"] is True
    session_dir = aoa_root / "sessions" / "2026-05-14__001__real-compact-markers"
    manifest = json.loads((session_dir / "session.manifest.json").read_text(encoding="utf-8"))
    assert [segment["role"] for segment in manifest["segments"]] == [
        "initial-to-compaction",
        "compaction-to-latest",
    ]
    first_index = json.loads(Path(manifest["segments"][0]["index"]).read_text(encoding="utf-8"))
    assert first_index["source_range"] == {"from_line": 1, "to_line": 4}
    assert first_index["by_type"]["COMPACTION_EVENT"] == ["000003", "000004"]
def test_stress_pass_audits_first_compaction_intervals(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-14T03-00-00-session-stress.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-14T03:00:00Z", "type": "session_meta", "payload": {"id": "session-stress"}},
            {"timestamp": "2026-05-14T03:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Stress compact intervals"}]}},
            {"timestamp": "2026-05-14T03:00:02Z", "type": "compacted", "payload": {"replacement_history": []}},
            {"timestamp": "2026-05-14T03:00:03Z", "type": "turn_context", "payload": {"summary": "none"}},
            {"timestamp": "2026-05-14T03:00:04Z", "type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_count": 100}}},
            {"timestamp": "2026-05-14T03:00:05Z", "type": "event_msg", "payload": {"type": "context_compacted"}},
            {"timestamp": "2026-05-14T03:00:06Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "first interval closed"}]}},
            {"timestamp": "2026-05-14T03:00:07Z", "type": "compacted", "payload": {"replacement_history": []}},
            {"timestamp": "2026-05-14T03:00:08Z", "type": "event_msg", "payload": {"type": "context_compacted"}},
            {"timestamp": "2026-05-14T03:00:09Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "tail"}]}},
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "session-stress",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    stress = module.session_stress_pass(aoa_root, "latest", compaction_count=2, write=True)

    assert stress["ok"] is True
    assert stress["selected_segment_ids"] == ["000", "001"]
    assert stress["selected_source_span"] == {"from_line": 1, "to_line": 9}
    assert stress["selected_event_counts"]["COMPACTION_EVENT"] == 4
    assert Path(stress["artifacts"]["json"]).exists()
    assert Path(stress["artifacts"]["markdown"]).exists()
    compact_print = module.stress_pass_print_payload(stress)
    assert "segment_summaries" not in compact_print
    assert compact_print["segment_summary_count"] == 2
    assert compact_print["segment_summaries_omitted"] == 0

    show = module.session_show_payload(aoa_root, "latest", max_segments=1)
    assert show["manifest"]["segment_count"] == 3
    assert len(show["manifest"]["segments_preview"]) == 1
    assert show["manifest"]["segments_truncated"] is True
    full = module.session_show_payload(aoa_root, "latest", full=True)
    assert len(full["manifest"]["segments"]) == 3
def test_session_source_uses_hook_metadata_for_manual_sync(tmp_path: Path) -> None:
    session_dir = tmp_path / "session"
    write_jsonl(
        session_dir / "hooks" / "events.jsonl",
        [
            {
                "schema_version": 1,
                "timestamp": "2026-05-14T04:00:00Z",
                "hook_event_name": "Stop",
                "event": {
                    "cwd": "/workspace/AbyssOS",
                    "model": "gpt-5.5",
                    "permission_mode": "bypassPermissions",
                    "turn_id": "turn-from-hook",
                },
            }
        ],
    )

    source = module.session_source(
        {"cwd": "/workspace/AbyssOS"},
        tmp_path / "session.raw.jsonl",
        hook_source=module.hook_source_metadata(session_dir),
    )

    assert source["model"] == "gpt-5.5"
    assert source["permission_mode"] == "bypassPermissions"
    assert source["last_turn_id"] == "turn-from-hook"
def test_validate_pipeline_runs_end_to_end(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    payload = module.validate_pipeline(workspace_root=workspace, aoa_root=workspace / ".aoa")

    assert payload["ok"] is True
    checks = {check["name"]: check["ok"] for check in payload["checks"]}
    assert checks["generated_hook_config_events"] is True
    assert checks["generated_hook_commands_use_thin_ingress"] is True
    assert checks["thin_hook_ingress_source_exists"] is True
    assert checks["precompact_receipt_ok"] is True
    assert checks["postcompact_receipt_ok"] is True
    assert checks["stop_receipt_ok"] is True
    assert checks["segments_include_compaction_interval"] is True
    assert checks["raw_capture_state_committed_with_projection"] is True
    assert checks["session_projection_generation_and_publish_current"] is True
    assert checks["segment_projection_generation_and_publish_current"] is True
    assert checks["raw_block_referential_integrity"] is True
    assert checks["rehydrate_packet_preserves_decision_route"] is True
    assert checks["first_pass_distillation_has_candidates"] is True
def test_generated_session_projection_validates_against_json_schemas(
    tmp_path: Path,
) -> None:
    from jsonschema import Draft202012Validator

    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-schema-validation.jsonl"
    write_jsonl(transcript, module.validation_transcript_rows())
    synced = module.sync_session_from_transcript(
        aoa_root=aoa_root,
        event={
            "session_id": "aoa-validate-session",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
        },
        transcript_path=transcript,
        hook_event_name="ManualSync",
    )
    session_dir = Path(str(synced["session_dir"]))
    module.preserve_unindexed_raw_capture(
        session_dir=session_dir,
        session_id="aoa-validate-session",
        transcript_path=transcript,
        manifest=module.read_json(
            session_dir / "session.manifest.json", {}
        ),
        hook_event_name="SchemaValidationCapture",
        now="2026-08-10T00:00:00Z",
    )
    source_root = SCRIPT.parents[1]
    contracts = [
        (
            source_root
            / "schemas"
            / "session.manifest.schema.json",
            session_dir / "session.manifest.json",
        ),
        (
            source_root
            / "schemas"
            / "projection-outbox.schema.json",
            Path(str(synced["publish_result"]["outbox"]["path"])),
        ),
        (
            source_root
            / "schemas"
            / "raw-capture-state.schema.json",
            session_dir
            / "raw"
            / module.RAW_CAPTURE_STATE_JSON,
        ),
        (
            source_root
            / "schemas"
            / "live-tail.postings.schema.json",
            session_dir
            / "raw"
            / module.PERSISTENT_LIVE_TAIL_POSTINGS_JSON,
        ),
    ]
    postings_manifest = module.read_json(
        session_dir
        / "raw"
        / module.PERSISTENT_LIVE_TAIL_POSTINGS_JSON,
        {},
    )
    contracts.extend(
        (
            source_root
            / "schemas"
            / "live-tail.postings-shard.schema.json",
            session_dir / str(shard["rel"]),
        )
        for shard in postings_manifest.get("shards", [])
        if isinstance(shard, dict)
        and shard.get("format") == "sharded_postings_v1"
    )
    manifest = module.read_json(
        session_dir / "session.manifest.json",
        {},
    )
    contracts.extend(
        (
            source_root
            / "schemas"
            / "segment.index.schema.json",
            Path(str(segment["index"])),
        )
        for segment in manifest["segments"]
    )

    for schema_path, payload_path in contracts:
        schema = module.read_json(schema_path, {})
        payload = module.read_json(payload_path, {})
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(payload)
