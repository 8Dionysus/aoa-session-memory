from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "profile_session_stages.py"
SPEC = importlib.util.spec_from_file_location("profile_session_stages_test", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_fixture_session(tmp_path: Path) -> Path:
    aoa_root = tmp_path / "workspace" / ".aoa"
    session_dir = aoa_root / "sessions" / "2026-08-20__001__fixture"
    segments_dir = session_dir / "segments"
    shard_dir = session_dir / "session-index-shards" / "task-episodes"
    raw_dir = session_dir / "raw"
    raw_dir.mkdir(parents=True)

    events = [
        {
            "event_id": "000001",
            "line": 1,
            "type": "USER_INTENT",
            "timestamp": "2026-08-20T10:00:00Z",
            "correlation_id": None,
            "facets": {},
        },
        {
            "event_id": "000002",
            "line": 2,
            "type": "COMMAND",
            "timestamp": "2026-08-20T10:00:01Z",
            "correlation_id": "call-test-1",
            "facets": {"command": "pytest -q tests", "tool_name": "exec_command", "command_kind": "verification"},
        },
        {
            "event_id": "000003",
            "line": 3,
            "type": "ERROR",
            "timestamp": "2026-08-20T10:00:03Z",
            "correlation_id": "call-test-1",
            "outcome": "failed",
            "facets": {},
        },
        {
            "event_id": "000004",
            "line": 4,
            "type": "FILE_WRITE",
            "timestamp": "2026-08-20T10:00:04Z",
            "correlation_id": "call-repair",
            "facets": {"command": "apply_patch", "tool_name": "apply_patch", "command_kind": "write"},
        },
        {
            "event_id": "000005",
            "line": 5,
            "type": "TOOL_OUTPUT",
            "timestamp": "2026-08-20T10:00:05Z",
            "correlation_id": "call-repair",
            "outcome": "observed",
            "facets": {},
        },
        {
            "event_id": "000006",
            "line": 6,
            "type": "COMMAND",
            "timestamp": "2026-08-20T10:00:06Z",
            "correlation_id": "call-test-2",
            "facets": {"command": "pytest -q tests", "tool_name": "exec_command", "command_kind": "verification"},
        },
        {
            "event_id": "000007",
            "line": 7,
            "type": "VERIFICATION",
            "timestamp": "2026-08-20T10:00:08Z",
            "correlation_id": "call-test-2",
            "outcome": "succeeded",
            "facets": {},
        },
        {
            "event_id": "000008",
            "line": 8,
            "type": "ASSISTANT_MESSAGE",
            "timestamp": "2026-08-20T10:00:10Z",
            "correlation_id": None,
            "facets": {},
        },
    ]
    segment_path = segments_dir / "000__initial-to-latest.index.json"
    write_json(segment_path, {"segment_id": "000", "events": events})
    raw_path = raw_dir / "session.raw.jsonl"
    raw_path.write_text("\n".join(json.dumps({"line": i}) for i in range(1, 9)) + "\n", encoding="utf-8")

    episode_ref = "session-index-shards/task-episodes/episode.json"
    episode = {
        "schema_version": 1,
        "component": "task_episodes",
        "payload": {
            "episode_id": "task-0001",
            "status": "closed",
            "confidence": "high",
            "event_range": {"from_line": 1, "to_line": 8},
            "intent_refs": [{"line": 1, "event_id": "000001"}],
        },
    }
    write_json(shard_dir / "episode.json", episode)
    write_json(
        session_dir / "session-index-shards" / "manifest.json",
        {"components": {"task_episodes": [{"ref": episode_ref}]}},
    )
    write_json(
        session_dir / "session.manifest.json",
        {
            "session_id": "fixture-session",
            "session_label": "2026-08-20__001__fixture",
            "archive_status": "indexed",
            "review_status": "provisional",
            "raw": {"line_count": 8},
            "raw_blocks": [{"status": "open"}],
        },
    )
    write_json(
        session_dir / "session.index.json",
        {
            "session_id": "fixture-session",
            "archive_status": "indexed",
            "event_count": 8,
            "segments": [{"index": str(segment_path), "source_range": {"from_line": 1, "to_line": 8}}],
        },
    )
    return aoa_root


def write_bounded_prefix_fixture(tmp_path: Path) -> tuple[Path, Path, dict[str, str]]:
    aoa_root = write_fixture_session(tmp_path)
    session_dir = aoa_root / "sessions" / "2026-08-20__001__fixture"
    raw_path = session_dir / "raw" / "session.raw.jsonl"
    raw_bytes = raw_path.stat().st_size
    raw_sha256 = hashlib.sha256(raw_path.read_bytes()).hexdigest()
    session_generation = "1" * 64
    segment_generation = "2" * 64
    task_generation = "3" * 64
    publish_id = "4" * 64
    projection = {
        "schema_version": 1,
        "source": {
            "raw_sha256": raw_sha256,
            "raw_bytes": raw_bytes,
            "raw_line_count": 8,
        },
        "processed_watermark": {
            "to_line": 8,
            "to_timestamp": "2026-08-20T10:00:10Z",
        },
        "dependency_generations": {
            "session_index": session_generation,
            "segment_index": segment_generation,
            "task_episode_source": task_generation,
        },
        "publish_id": publish_id,
    }
    manifest_path = session_dir / "session.manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update(
        {
            "session_id": "fixture-session",
            "raw": {
                "line_count": 8,
                "bytes": raw_bytes,
                "sha256": raw_sha256,
                "indexing_status": "indexed",
            },
            "index_schema": {
                "session_index_generation_id": session_generation,
                "segment_index_generation_id": segment_generation,
                "projection_publish": projection,
            },
            "raw_blocks": {
                "blocks": [{"status": "open"}],
                "projection_publish": projection,
            },
        }
    )
    write_json(manifest_path, manifest)

    index_path = session_dir / "session.index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index.update(
        {
            "session_id": "fixture-session",
            "event_count": 8,
            "generation_id": session_generation,
            "generation_identity": {
                "generation_id": session_generation,
                "producer_sha256": "5" * 64,
                "projection": "session_index",
                "producer_contract_status": "current",
            },
            "dependency_generation_identities": {
                "segment_index": {
                    "generation_id": segment_generation,
                    "producer_sha256": "6" * 64,
                    "producer_contract_status": "current",
                },
                "task_episode_source": {
                    "generation_id": task_generation,
                    "producer_sha256": "7" * 64,
                    "producer_contract_status": "current",
                },
            },
            "projection_publish": projection,
        }
    )
    write_json(index_path, index)

    segment_path = session_dir / "segments" / "000__initial-to-latest.index.json"
    segment = json.loads(segment_path.read_text(encoding="utf-8"))
    segment.update(
        {
            "generation_id": segment_generation,
            "generation_identity": {
                "generation_id": segment_generation,
                "producer_sha256": "6" * 64,
                "projection": "segment_index",
                "producer_contract_status": "current",
            },
            "projection_publish": projection,
            "source_range": {"from_line": 1, "to_line": 8},
        }
    )
    write_json(segment_path, segment)

    component_manifest_path = session_dir / "session-index-shards" / "manifest.json"
    component_manifest = json.loads(component_manifest_path.read_text(encoding="utf-8"))
    component_manifest.update(
        {
            "projection_publish": projection,
            "source_identity": {
                "raw_sha256": raw_sha256,
                "raw_bytes": raw_bytes,
                "raw_line_count": 8,
                "task_episode_generation_id": task_generation,
            },
            "component_counts": {"task_episodes": 1},
        }
    )
    episode_path = session_dir / "session-index-shards" / "task-episodes" / "episode.json"
    episode = json.loads(episode_path.read_text(encoding="utf-8"))
    episode["source_identity"] = {
        "task_episode_generation_id": task_generation,
        "episode_source_sha256": "8" * 64,
        "event_range": {"from_line": 1, "to_line": 8},
        "privacy_policy_version": 1,
        "redaction_policy_version": 1,
    }
    write_json(episode_path, episode)
    entry = component_manifest["components"]["task_episodes"][0]
    entry["artifact_sha256"] = hashlib.sha256(episode_path.read_bytes()).hexdigest()
    entry["payload_sha256"] = "9" * 64
    write_json(component_manifest_path, component_manifest)

    tail_path = session_dir / "raw" / "fixture-live-source.jsonl"
    tail_path.write_bytes(b"x" * (raw_bytes + 4))
    write_json(
        session_dir / "raw" / "capture.latest.json",
        {
            "artifact_type": "raw_capture_state",
            "capture_mode": "append_only_immutable_block_ledger_v1",
            "raw_bytes": raw_bytes + 4,
            "source_path": str(tail_path),
            "projection_raw_sha256_at_capture": raw_sha256,
            "projection_publish_id_at_capture": publish_id,
        },
    )
    return aoa_root, session_dir, {
        "raw_sha256": raw_sha256,
        "raw_bytes": str(raw_bytes),
        "publish_id": publish_id,
        "session_generation": session_generation,
        "segment_generation": segment_generation,
        "task_generation": task_generation,
    }


def test_profile_keeps_missing_stages_unknown_and_measures_correlated_spans(tmp_path: Path) -> None:
    aoa_root = write_fixture_session(tmp_path)
    report = MODULE.build_report(
        aoa_root,
        ["2026-08-20__001__fixture"],
        max_episodes=10,
    )

    session = report["sessions"][0]
    episode = session["episodes"][0]
    assert session["scope_status"] == "usable_closed_episode_slice"
    assert session["open_tail_excluded"] is True
    assert episode["stage_spans"]["tests_validators"]["span_seconds"] == 4.0
    assert episode["stage_spans"]["diagnosis_repair"]["span_seconds"] == 1.0
    assert episode["stage_spans"]["kag_navigation_index_gate"]["status"] == "unknown"
    assert episode["stage_spans"]["kag_navigation_index_gate"]["span_seconds"] is None
    assert episode["repeat_amplification"]["repeated_attempt_count"] == 1
    assert episode["repeat_amplification"]["rerun_after_fix_count"] == 1
    assert episode["repeat_amplification"]["validation_rerun_after_repair_count"] == 1
    assert report["evaluator_input"]["verdict"] is None


def test_unresolved_call_does_not_become_zero_duration(tmp_path: Path) -> None:
    aoa_root = write_fixture_session(tmp_path)
    session_dir = aoa_root / "sessions" / "2026-08-20__001__fixture"
    segment = json.loads(
        (session_dir / "segments" / "000__initial-to-latest.index.json").read_text(encoding="utf-8")
    )
    segment["events"].append(
        {
            "event_id": "000009",
            "line": 9,
            "type": "TOOL_CALL",
            "timestamp": "2026-08-20T10:00:11Z",
            "correlation_id": "call-kag-unresolved",
            "facets": {"tool_qualified_name": "mcp__aoa_kag__search"},
        }
    )
    episode_path = session_dir / "session-index-shards" / "task-episodes" / "episode.json"
    episode = json.loads(episode_path.read_text(encoding="utf-8"))
    episode["payload"]["event_range"]["to_line"] = 9
    episode_path.write_text(json.dumps(episode, indent=2) + "\n", encoding="utf-8")
    manifest_path = session_dir / "session.manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["raw"]["line_count"] = 9
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    write_json(session_dir / "segments" / "000__initial-to-latest.index.json", segment)
    report = MODULE.build_report(aoa_root, ["2026-08-20__001__fixture"], max_episodes=10)
    stage = report["sessions"][0]["episodes"][0]["stage_spans"]["kag_navigation_index_gate"]
    assert stage["status"] == "partial"
    assert stage["attempt_count"] == 1
    assert stage["span_seconds"] is None


def test_bounded_prefix_is_identity_bound_and_excludes_a_moving_tail(tmp_path: Path) -> None:
    aoa_root, session_dir, pin = write_bounded_prefix_fixture(tmp_path)
    report = MODULE.build_bounded_report(
        aoa_root,
        ["2026-08-20__001__fixture"],
        max_episodes=10,
    )
    scope = report["measurement_scope"]
    assert report["schema_version"] == "bounded_measurement_v1"
    assert scope["scope_currentness"] == "identity_bound_prefix_only"
    assert scope["prefix"]["source"]["bytes"] == int(pin["raw_bytes"])
    assert scope["returned_positive_evidence"]["episode_count"] == 1
    assert scope["global_recall"]["complete"] is False
    assert scope["negative_claims"]["admitted"] is False
    assert scope["excluded_live_tail"]["status"] == "excluded_beyond_prefix"
    assert "pytest -q tests" not in json.dumps(report, ensure_ascii=False)

    capture_path = session_dir / "raw" / "capture.latest.json"
    capture = json.loads(capture_path.read_text(encoding="utf-8"))
    capture["raw_bytes"] = int(pin["raw_bytes"]) + 12
    tail_path = Path(capture["source_path"])
    tail_path.write_bytes(b"x" * (int(pin["raw_bytes"]) + 12))
    write_json(capture_path, capture)
    advanced = MODULE.build_bounded_report(
        aoa_root,
        ["2026-08-20__001__fixture"],
        max_episodes=10,
    )
    assert advanced["measurement_scope"]["prefix"]["identity"] == scope["prefix"]["identity"]
    assert advanced["measurement_scope"]["returned_positive_evidence"]["episode_count"] == 1
    assert advanced["measurement_scope"]["excluded_live_tail"]["status"] == "excluded_beyond_prefix"


def test_bounded_prefix_rejects_wrong_watermark_and_preserves_inputs(tmp_path: Path) -> None:
    aoa_root, session_dir, _pin = write_bounded_prefix_fixture(tmp_path)
    index_path = session_dir / "session.index.json"
    before = index_path.read_bytes()
    with pytest.raises(MODULE.BoundedPrefixError, match="expected_pin_mismatch:raw_bytes"):
        MODULE.build_bounded_report(
            aoa_root,
            ["2026-08-20__001__fixture"],
            max_episodes=10,
            expected_pin={"raw_bytes": 999},
        )
    assert index_path.read_bytes() == before


def test_bounded_prefix_rejects_generation_drift_and_partial_coverage(tmp_path: Path) -> None:
    aoa_root, session_dir, _pin = write_bounded_prefix_fixture(tmp_path)
    index_path = session_dir / "session.index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index["generation_id"] = "a" * 64
    write_json(index_path, index)
    with pytest.raises(MODULE.BoundedPrefixError, match="session_generation_mismatch"):
        MODULE.build_bounded_report(
            aoa_root,
            ["2026-08-20__001__fixture"],
            max_episodes=10,
        )

    aoa_root, session_dir, _pin = write_bounded_prefix_fixture(tmp_path / "partial")
    segment_path = session_dir / "segments" / "000__initial-to-latest.index.json"
    segment = json.loads(segment_path.read_text(encoding="utf-8"))
    segment["events"] = segment["events"][:-1]
    write_json(segment_path, segment)
    after_fixture_mutation = segment_path.read_bytes()
    with pytest.raises(MODULE.BoundedPrefixError, match="segment_coverage_incomplete"):
        MODULE.build_bounded_report(
            aoa_root,
            ["2026-08-20__001__fixture"],
            max_episodes=10,
        )
    assert segment_path.read_bytes() == after_fixture_mutation


def test_bounded_zero_results_do_not_admit_absence(tmp_path: Path) -> None:
    aoa_root, session_dir, _pin = write_bounded_prefix_fixture(tmp_path)
    episode_path = session_dir / "session-index-shards" / "task-episodes" / "episode.json"
    episode = json.loads(episode_path.read_text(encoding="utf-8"))
    episode["payload"]["status"] = "open"
    write_json(episode_path, episode)
    report = MODULE.build_bounded_report(
        aoa_root,
        ["2026-08-20__001__fixture"],
        max_episodes=10,
    )
    positive = report["measurement_scope"]["returned_positive_evidence"]
    assert report["return_status"] == "empty_bounded_scope_not_absence"
    assert positive["episode_count"] == 0
    assert positive["semantic_absence_admitted"] is False
    assert report["measurement_scope"]["negative_claims"]["admitted"] is False
