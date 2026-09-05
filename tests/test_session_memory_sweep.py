from __future__ import annotations

import fcntl
import json
import os
import time
from pathlib import Path
from typing import Any

import pytest

from session_memory_test_support import (
    module,
    write_jsonl,
)

def test_sweep_codex_sessions_repairs_missing_and_stale_transcripts(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    source_root = tmp_path / "codex-sessions"
    transcript = source_root / "2026" / "05" / "03" / "rollout-2026-05-03T12-00-00-sweep-session.jsonl"
    rows = [
        {
            "timestamp": "2026-05-03T12:00:00Z",
            "type": "session_meta",
            "payload": {"id": "sweep-session", "cwd": str(workspace), "timestamp": "2026-05-03T12:00:00Z"},
        },
        {
            "timestamp": "2026-05-03T12:00:01Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "Sweep the missing Codex transcript"}],
            },
        },
    ]
    write_jsonl(transcript, rows)
    old_transcript = source_root / "2026" / "04" / "01" / "rollout-2026-04-01T12-00-00-old-sweep-session.jsonl"
    write_jsonl(
        old_transcript,
        [
            {
                "timestamp": "2026-04-01T12:00:00Z",
                "type": "session_meta",
                "payload": {"id": "old-sweep-session", "cwd": str(workspace), "timestamp": "2026-04-01T12:00:00Z"},
            },
            {
                "timestamp": "2026-04-01T12:00:01Z",
                "type": "response_item",
                "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Old sweep session"}]},
            },
        ],
    )

    dry = module.sweep_codex_sessions(
        aoa_root=aoa_root,
        source_root=source_root,
        since="2026-05-01",
        min_age_seconds=0,
        write_report=True,
    )

    assert dry["ok"] is True
    assert dry["discovered_count"] == 1
    assert dry["counts"] == {"planned": 1}
    assert dry["repair_candidate_count"] == 1
    assert dry["results"][0]["freshness_reason"] == "missing_manifest"
    assert Path(dry["report_json"]).exists()
    assert Path(dry["report_markdown"]).exists()

    synced = module.sweep_codex_sessions(
        aoa_root=aoa_root,
        source_root=source_root,
        since="2026-05-01",
        apply=True,
        min_age_seconds=0,
    )
    assert synced["ok"] is True
    assert synced["counts"] == {"synced": 1}
    session_dir = Path(synced["results"][0]["session_dir"])
    manifest = json.loads((session_dir / "session.manifest.json").read_text(encoding="utf-8"))
    assert manifest["archive_status"] == "indexed"
    assert manifest["latest_event_count"] == 2
    assert "CodexSessionSweep" in manifest["hooks_seen"]

    fresh = module.sweep_codex_sessions(
        aoa_root=aoa_root,
        source_root=source_root,
        since="2026-05-01",
        min_age_seconds=0,
    )
    assert fresh["counts"] == {"skipped_fresh": 1}

    write_jsonl(
        transcript,
        rows
        + [
            {
                "timestamp": "2026-05-03T12:00:02Z",
                "type": "response_item",
                "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Sweeper catches stale transcripts."}]},
            }
        ],
    )

    stale = module.sweep_codex_sessions(
        aoa_root=aoa_root,
        source_root=source_root,
        since="2026-05-01",
        min_age_seconds=0,
    )
    assert stale["counts"] == {"planned": 1}
    assert stale["results"][0]["freshness_reason"] == "source_size_changed"

    resynced = module.sweep_codex_sessions(
        aoa_root=aoa_root,
        source_root=source_root,
        since="2026-05-01",
        apply=True,
        min_age_seconds=0,
    )
    manifest = json.loads((session_dir / "session.manifest.json").read_text(encoding="utf-8"))
    assert resynced["counts"] == {"synced": 1}
    assert resynced["results"][0]["pre_sync_freshness"]["reason"] == "source_size_changed"
    assert resynced["results"][0]["freshness"]["fresh"] is True
    assert resynced["results"][0]["freshness"]["reason"] == "indexed_archive_matches_transcript_snapshot"
    assert resynced["results"][0]["freshness_reason"] == "indexed_archive_matches_transcript_snapshot"
    assert resynced["results"][0]["retry_required"] is False
    assert manifest["latest_event_count"] == 3
def test_sweep_codex_sessions_reports_post_sync_staleness_when_source_grows(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """Regression derived from the timer catch-up and active-tail manual wave."""

    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    source_root = tmp_path / "codex-sessions"
    session_id = "sweep-growing-source"
    transcript = source_root / "2026" / "05" / "03" / f"rollout-2026-05-03T12-00-00-{session_id}.jsonl"
    initial_rows = [
        {
            "timestamp": "2026-05-03T12:00:00Z",
            "type": "session_meta",
            "payload": {"id": session_id, "cwd": str(workspace)},
        },
        {
            "timestamp": "2026-05-03T12:00:01Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "Observe sweep post-sync freshness"}],
            },
        },
    ]
    write_jsonl(transcript, initial_rows)
    original_sync = module.sync_session_from_transcript

    def sync_then_grow(**kwargs):
        synced = original_sync(**kwargs)
        write_jsonl(
            transcript,
            initial_rows
            + [
                {
                    "timestamp": "2026-05-03T12:00:02Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "Source advanced during sweep"}],
                    },
                }
            ],
        )
        return synced

    monkeypatch.setattr(module, "sync_session_from_transcript", sync_then_grow)

    payload = module.sweep_codex_sessions(
        aoa_root=aoa_root,
        source_root=source_root,
        since="2026-05-01",
        apply=True,
        min_age_seconds=0,
    )

    result = payload["results"][0]
    assert payload["counts"] == {"synced_stale_readable": 1}
    assert result["status"] == "synced_stale_readable"
    assert result["pre_sync_freshness"]["reason"] == "missing_manifest"
    assert result["freshness"]["fresh"] is False
    assert result["freshness"]["reason"] == "source_size_changed"
    assert result["freshness_reason"] == "source_size_changed"
    assert result["retry_required"] is True
def test_sweep_codex_sessions_preserves_oversized_raw_before_deferred_indexing(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    source_root = tmp_path / "codex-sessions"
    session_id = "sweep-oversized-capture"
    transcript = (
        source_root
        / "2026"
        / "05"
        / "03"
        / f"rollout-2026-05-03T12-00-00-{session_id}.jsonl"
    )
    initial_rows = [
        {
            "timestamp": "2026-05-03T12:00:00Z",
            "type": "session_meta",
            "payload": {"id": session_id, "cwd": str(workspace)},
        },
        {
            "timestamp": "2026-05-03T12:00:01Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": "Preserve oversized raw independently",
                    }
                ],
            },
        },
    ]
    write_jsonl(transcript, initial_rows)
    initial = module.sweep_codex_sessions(
        aoa_root=aoa_root,
        source_root=source_root,
        since="2026-05-01",
        apply=True,
        min_age_seconds=0,
        index_max_raw_bytes=None,
    )
    session_dir = Path(initial["results"][0]["session_dir"])
    initial_manifest = json.loads(
        (session_dir / "session.manifest.json").read_text(
            encoding="utf-8"
        )
    )
    initial_raw_sha256 = initial_manifest["raw"]["sha256"]

    write_jsonl(
        transcript,
        initial_rows
        + [
            {
                "timestamp": "2026-05-03T12:00:02Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",
                            "text": "New tail remains raw-accessible",
                        }
                    ],
                },
            }
        ],
    )

    probed_paths: list[Path] = []
    original_transcript_probe = module.transcript_probe

    def recording_transcript_probe(path: Path) -> dict[str, Any]:
        probed_paths.append(path)
        return original_transcript_probe(path)

    monkeypatch.setattr(module, "transcript_probe", recording_transcript_probe)
    planned = module.sweep_codex_sessions(
        aoa_root=aoa_root,
        source_root=source_root,
        since="2026-05-01",
        min_age_seconds=0,
        index_max_raw_bytes=1,
    )
    assert planned["counts"] == {"planned_raw_mirror": 1}
    assert planned["mirror_only_candidate_count"] == 1
    assert planned["metadata_probe_max_raw_bytes"] == 1
    assert probed_paths == []

    monkeypatch.setattr(
        module, "SESSION_PROJECTION_HEAVY_LANE_RAW_BYTES", 1
    )
    mirrored = module.sweep_codex_sessions(
        aoa_root=aoa_root,
        source_root=source_root,
        since="2026-05-01",
        apply=True,
        min_age_seconds=0,
        index_max_raw_bytes=1,
    )
    result = mirrored["results"][0]
    assert mirrored["counts"] == {"mirrored_index_deferred": 1}
    assert mirrored["mirror_only_candidate_count"] == 1
    assert result["raw_capture_current"] is True
    assert result["indexing_deferred"] is True
    assert result["heavy_lane_lease"]["status"] == "acquired"
    assert result["last_good_projection_preserved"] is True
    assert result["freshness_reason"] == (
        "preserved_capture_ahead_of_projection"
    )

    final_manifest = json.loads(
        (session_dir / "session.manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert final_manifest["archive_status"] == "indexed"
    assert final_manifest["raw"]["sha256"] == initial_raw_sha256
    capture = json.loads(
        (session_dir / "raw" / module.RAW_CAPTURE_STATE_JSON).read_text(
            encoding="utf-8"
        )
    )
    capture_path = Path(capture["capture_path"])
    assert capture["status"] == "preserved_unindexed"
    assert capture_path.is_file()
    assert capture_path.read_bytes() == transcript.read_bytes()
    retry_queue = module.auto_maintenance_retry_queue_status(
        aoa_root
    )
    queue_key = f"deep:{session_id}"
    assert retry_queue["freshness_obligation_count"] == 1
    assert retry_queue["freshness_obligation_due_count"] == 1
    assert queue_key in retry_queue["items"]
    obligation = retry_queue["items"][queue_key]["options"]
    assert obligation["persistent_obligation"] is True
    assert obligation["obligation_kind"] == (
        module.SESSION_PROJECTION_FRESHNESS_OBLIGATION_KIND
    )
    assert obligation["required_capture_bytes"] == transcript.stat().st_size
    assert obligation["required_capture_epoch_id"] == capture[
        "ledger_epoch_id"
    ]
def test_sweep_codex_sessions_defers_large_capture_for_heavy_lane_lease(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    source_root = tmp_path / "codex-sessions"
    session_id = "sweep-heavy-lease"
    transcript = (
        source_root
        / "2026"
        / "05"
        / "04"
        / f"rollout-2026-05-04T12-00-00-{session_id}.jsonl"
    )
    write_jsonl(
        transcript,
        [
            {
                "timestamp": "2026-05-04T12:00:00Z",
                "type": "session_meta",
                "payload": {"id": session_id, "cwd": str(workspace)},
            },
            {
                "timestamp": "2026-05-04T12:00:01Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "large capture must serialize",
                        }
                    ],
                },
            },
        ],
    )
    monkeypatch.setattr(
        module, "SESSION_PROJECTION_HEAVY_LANE_RAW_BYTES", 1
    )
    lease_path = module.heavy_projection_lane_lock_path(aoa_root)
    lease_path.parent.mkdir(parents=True, exist_ok=True)
    with lease_path.open("a+", encoding="utf-8") as lease_handle:
        fcntl.flock(lease_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        module.write_maintenance_lock_owner(
            lease_handle,
            {
                "status": "active",
                "pid": 7331,
                "lane": "auto_maintenance_projection",
            },
        )
        payload = module.sweep_codex_sessions(
            aoa_root=aoa_root,
            source_root=source_root,
            since="2026-05-01",
            apply=True,
            min_age_seconds=0,
            index_max_raw_bytes=1,
        )
        fcntl.flock(lease_handle, fcntl.LOCK_UN)

    result = payload["results"][0]
    assert payload["counts"] == {"deferred_heavy_lane_lease": 1}
    assert result["retry_required"] is True
    assert result["heavy_lane_lease"]["status"] == "deferred"
    assert result["heavy_lane_lease"]["blocking_owner"]["pid"] == 7331
    assert not (aoa_root / module.SESSION_ROOT).exists()
def test_sweep_codex_sessions_supplements_date_window_with_recent_transcript_activity(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    source_root = tmp_path / "codex-sessions"
    active_transcript = (
        source_root
        / "2020"
        / "01"
        / "02"
        / "rollout-2020-01-02T12-00-00-old-date-recent-activity.jsonl"
    )
    initial_rows = [
        {
            "timestamp": "2020-01-02T12:00:00Z",
            "type": "session_meta",
            "payload": {
                "id": "old-date-recent-activity",
                "cwd": str(workspace),
                "timestamp": "2020-01-02T12:00:00Z",
            },
        },
        {
            "timestamp": "2020-01-02T12:00:01Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "Initial old session"}],
            },
        },
    ]
    write_jsonl(active_transcript, initial_rows)
    initial = module.sweep_codex_sessions(
        aoa_root=aoa_root,
        source_root=source_root,
        since="2020-01-01",
        apply=True,
        min_age_seconds=0,
    )
    assert initial["counts"] == {"synced": 1}
    write_jsonl(
        active_transcript,
        initial_rows
        + [
            {
                "timestamp": "2020-01-02T12:00:02Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "Recently resumed old session"}],
                },
            }
        ],
    )
    cold_transcript = (
        source_root
        / "2020"
        / "01"
        / "03"
        / "rollout-2020-01-03T12-00-00-old-date-cold-activity.jsonl"
    )
    write_jsonl(
        cold_transcript,
        [
            {
                "timestamp": "2020-01-03T12:00:00Z",
                "type": "session_meta",
                "payload": {"id": "old-date-cold-activity", "cwd": str(workspace)},
            }
        ],
    )
    cold_epoch = time.time() - 3 * 86400
    os.utime(cold_transcript, (cold_epoch, cold_epoch))
    planned = module.sweep_codex_sessions(
        aoa_root=aoa_root,
        source_root=source_root,
        since="2026-01-01",
        activity_since_seconds=2 * 86400,
        min_age_seconds=0,
    )

    assert planned["discovered_count"] == 1
    assert planned["activity_supplement_discovered_count"] == 1
    assert planned["counts"] == {"planned": 1}
    assert planned["results"][0]["session_id"] == "old-date-recent-activity"
    assert planned["results"][0]["selection_source"] == "activity_mtime_supplement"
    assert planned["results"][0]["freshness_reason"] == "source_size_changed"
def test_sweep_codex_sessions_targets_heavy_stale_lane_without_registry_rescan(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    source_root = tmp_path / "codex-sessions"
    transcripts: dict[str, tuple[Path, list[dict[str, Any]]]] = {}
    for session_id, body in (
        ("small-stale-session", "small"),
        ("heavy-stale-session", "heavy " * 4000),
    ):
        transcript = source_root / "2026" / "05" / "05" / f"rollout-2026-05-05T12-00-00-{session_id}.jsonl"
        rows = [
            {
                "timestamp": "2026-05-05T12:00:00Z",
                "type": "session_meta",
                "payload": {"id": session_id, "cwd": str(workspace), "timestamp": "2026-05-05T12:00:00Z"},
            },
            {
                "timestamp": "2026-05-05T12:00:01Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": body}],
                },
            },
        ]
        write_jsonl(transcript, rows)
        transcripts[session_id] = (transcript, rows)

    initial = module.sweep_codex_sessions(
        aoa_root=aoa_root,
        source_root=source_root,
        since="2026-05-05",
        until="2026-05-05",
        apply=True,
        min_age_seconds=0,
    )
    assert initial["counts"] == {"synced": 2}

    for session_id, (transcript, rows) in transcripts.items():
        write_jsonl(
            transcript,
            rows
            + [
                {
                    "timestamp": "2026-05-05T12:00:02Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": f"stale {session_id}"}],
                    },
                }
            ],
        )

    small_bytes = transcripts["small-stale-session"][0].stat().st_size
    heavy_bytes = transcripts["heavy-stale-session"][0].stat().st_size
    threshold = (small_bytes + heavy_bytes) // 2
    registry_reads = 0
    original_read_json = module.read_json
    original_transcript_probe = module.transcript_probe
    probed_paths: list[Path] = []

    def counting_read_json(path: Path, default: Any) -> Any:
        nonlocal registry_reads
        if path == aoa_root / module.REGISTRY_NAME:
            registry_reads += 1
        return original_read_json(path, default)

    def recording_transcript_probe(path: Path) -> dict[str, Any]:
        probed_paths.append(path)
        return original_transcript_probe(path)

    monkeypatch.setattr(module, "read_json", counting_read_json)
    monkeypatch.setattr(module, "transcript_probe", recording_transcript_probe)
    planned = module.sweep_codex_sessions(
        aoa_root=aoa_root,
        source_root=source_root,
        since="2026-05-05",
        until="2026-05-05",
        min_age_seconds=0,
        min_raw_bytes=threshold,
        max_raw_bytes=heavy_bytes + 1,
        limit=1,
    )

    by_session = {str(item["session_id"]): item for item in planned["results"]}
    assert planned["counts"] == {"skipped_under_min_raw": 1, "planned": 1}
    assert planned["repair_candidate_count"] == 1
    assert planned["selected_repair_count"] == 1
    assert by_session["small-stale-session"]["status"] == "skipped_under_min_raw"
    assert by_session["heavy-stale-session"]["status"] == "planned"
    assert probed_paths == [transcripts["heavy-stale-session"][0]]
    assert registry_reads == 1
def test_sweep_codex_sessions_repairs_deferred_stop_archive(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    source_root = tmp_path / "codex-sessions"
    transcript = source_root / "2026" / "05" / "04" / "rollout-2026-05-04T12-00-00-sweep-deferred.jsonl"
    write_jsonl(
        transcript,
        [
            {
                "timestamp": "2026-05-04T12:00:00Z",
                "type": "session_meta",
                "payload": {"id": "sweep-deferred", "cwd": str(workspace), "timestamp": "2026-05-04T12:00:00Z"},
            },
            {
                "timestamp": "2026-05-04T12:00:01Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "Close with deferred Stop archive"}],
                },
            },
        ],
    )
    monkeypatch.delenv("AOA_SESSION_MEMORY_FULL_STOP_SYNC", raising=False)
    monkeypatch.setenv("AOA_SESSION_MEMORY_STOP_SYNC_MAX_BYTES", "0")

    receipt = module.handle_hook_event(
        "Stop",
        {
            "session_id": "sweep-deferred",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )
    assert receipt["ok"] is True
    assert "indexing_deferred" in receipt["actions"]
    assert "background_sync_queued" in receipt["actions"]
    deferred_dir = module.session_dir_for_id(aoa_root, "sweep-deferred")
    deferred_manifest = json.loads((deferred_dir / "session.manifest.json").read_text(encoding="utf-8"))
    assert deferred_manifest["archive_status"] == "raw_mirrored_index_deferred"

    dry = module.sweep_codex_sessions(
        aoa_root=aoa_root,
        source_root=source_root,
        since="2026-05-01",
        min_age_seconds=0,
    )
    assert dry["counts"] == {"planned": 1}
    assert dry["results"][0]["freshness_reason"] == "archive_not_indexed"

    synced = module.sweep_codex_sessions(
        aoa_root=aoa_root,
        source_root=source_root,
        since="2026-05-01",
        apply=True,
        min_age_seconds=0,
    )
    session_dir = module.session_dir_for_id(aoa_root, "sweep-deferred")
    manifest = json.loads((session_dir / "session.manifest.json").read_text(encoding="utf-8"))
    assert synced["counts"] == {"synced": 1}
    assert manifest["archive_status"] == "indexed"
    assert manifest["latest_event_count"] == 2
    assert "CodexSessionSweep" in manifest["hooks_seen"]
