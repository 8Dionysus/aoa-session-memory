from __future__ import annotations

import importlib.util
import json
from pathlib import Path


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
