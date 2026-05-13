from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "aoa_session_memory.py"
spec = importlib.util.spec_from_file_location("aoa_session_memory", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules["aoa_session_memory"] = module
spec.loader.exec_module(module)


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def test_default_standalone_repo_prefers_bundles_topology(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    aoa_root.mkdir(parents=True)

    assert module.default_standalone_repo_for(aoa_root) == workspace / "bundles" / "aoa-session-memory"

    legacy_repo = workspace / "aoa-session-memory"
    legacy_repo.mkdir()
    assert module.default_standalone_repo_for(aoa_root) == legacy_repo

    bundled_repo = workspace / "bundles" / "aoa-session-memory"
    bundled_repo.mkdir(parents=True)
    assert module.default_standalone_repo_for(aoa_root) == bundled_repo


def test_readable_slug_removes_banned_topology_terms() -> None:
    slug = module.readable_slug("Task in /tmp/aoa wave4 review fixes")

    assert "tmp" not in slug.split("-")
    assert slug == "task-in-aoa-wave4-review-fixes"
    assert module.weak_title_text("# Files mentioned by the user: ## seed.zip")


def test_hook_archives_raw_and_builds_segments(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-12T00-00-00-session-1.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-12T00:00:00Z", "type": "session_meta", "payload": {"id": "session-1", "cwd": "/workspace/AbyssOS"}},
            {"timestamp": "2026-05-12T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Start hooks now"}]}},
            {"timestamp": "2026-05-12T00:00:02Z", "type": "response_item", "payload": {"type": "function_call", "name": "exec_command", "call_id": "call-1"}},
            {"timestamp": "2026-05-12T00:00:03Z", "type": "response_item", "payload": {"type": "function_call_output", "call_id": "call-1", "output": "stdout line"}},
            {"timestamp": "2026-05-12T00:00:04Z", "type": "turn_context", "payload": {"summary": "compacted prior work"}},
            {"timestamp": "2026-05-12T00:00:05Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "done"}]}},
        ],
    )

    receipt = module.handle_hook_event(
        "Stop",
        {
            "session_id": "session-1",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    assert receipt["ok"] is True
    session_dir = aoa_root / "sessions" / "2026-05-12__001__start-hooks-now"
    manifest = json.loads((session_dir / "session.manifest.json").read_text(encoding="utf-8"))
    assert manifest["archive_status"] == "indexed"
    assert manifest["display"]["label"] == "2026-05-12__001__start-hooks-now"
    assert manifest["display"]["title"] == "Start hooks now"
    assert manifest["display"]["path"] == str(session_dir)
    assert manifest["display"]["navigation_path"] == str(session_dir)
    assert receipt["display_name"] == "2026-05-12__001__start-hooks-now"
    assert receipt["navigation_path"] == str(session_dir)
    assert not (aoa_root / "sessions" / "session-1").exists()
    assert manifest["latest_event_count"] == 6
    assert len(manifest["segments"]) == 2
    assert (session_dir / "raw" / "session.raw.jsonl").exists()
    segment_index_path = session_dir / "segments" / "000__initial-to-compaction.index.json"
    assert segment_index_path.exists()
    segment_index = json.loads(segment_index_path.read_text(encoding="utf-8"))
    assert "COMMAND" in segment_index["by_type"]
    assert "COMMAND_OUTPUT" in segment_index["by_type"]
    segment_md = (session_dir / "segments" / "000__initial-to-compaction.md").read_text(encoding="utf-8")
    assert "index: ./000__initial-to-compaction.index.json" in segment_md
    assert "stdout line" in segment_md
    registry = json.loads((aoa_root / "session-registry.json").read_text(encoding="utf-8"))
    assert registry["sessions"][0]["session_label"] == "2026-05-12__001__start-hooks-now"


def test_segment_index_records_universal_facets_and_relationships(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-12T00-00-00-universal-events.jsonl"
    write_jsonl(
        transcript,
        [
            {
                "timestamp": "2026-05-12T00:00:00Z",
                "type": "session_meta",
                "payload": {"id": "universal-events", "cwd": str(workspace), "model": "final-assumption-compact"},
            },
            {"timestamp": "2026-05-12T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Inspect the repo"}]}},
            {"timestamp": "2026-05-12T00:00:02Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Decision: inspect before editing"}]}},
            {"timestamp": "2026-05-12T00:00:03Z", "type": "response_item", "payload": {"type": "function_call", "name": "exec_command", "call_id": "call-read", "arguments": json.dumps({"cmd": "rg -n TODO README.md"})}},
            {"timestamp": "2026-05-12T00:00:04Z", "type": "response_item", "payload": {"type": "function_call_output", "call_id": "call-read", "output": "Chunk ID: a\nProcess exited with code 0\nOutput:\nREADME.md:1:TODO\n"}},
        ],
    )

    receipt = module.handle_hook_event(
        "Stop",
        {
            "session_id": "universal-events",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    session_dir = aoa_root / "sessions" / "2026-05-12__001__inspect-the-repo"
    segment_index = json.loads((session_dir / "segments" / "000__initial-to-latest.index.json").read_text(encoding="utf-8"))
    records = {event["event_id"]: event for event in segment_index["events"]}

    assert "workspace_navigation" in segment_index["by_family"]
    assert "inspect" in segment_index["by_phase"]
    assert "succeeded" in segment_index["by_outcome"]
    read_event = records["000004"]
    output_event = records["000005"]
    assert read_event["type"] == "FILE_READ"
    assert read_event["family"] == "workspace_navigation"
    assert read_event["facets"]["command_kind"] == "read"
    assert "assumption_signal" not in records["000001"]["tags"]
    assert "final_state_signal" not in records["000001"]["tags"]
    assert "compaction" not in records["000001"]["tags"]
    assert output_event["outcome"] == "succeeded"
    assert output_event["correlation_id"] == "call-read"
    assert {"rel": "responds_to", "event_id": "000004", "correlation_id": "call-read"} in output_event["relationships"]

    record = module.registry_sessions(aoa_root)[0]
    profile = module.first_wave_session_profile(
        aoa_root,
        record,
        policy=module.default_batch_distillation_policy(),
        route_map={"COMMAND_OUTPUT": ["parser_candidate"]},
        workspace_root=workspace,
    )
    assert "mechanics_candidate" not in profile["lanes"]


def test_classifier_avoids_stream_status_and_policy_noise(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-12T00-00-00-noise.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-12T00:00:00Z", "type": "session_meta", "payload": {"id": "noise-session", "cwd": str(workspace)}},
            {
                "timestamp": "2026-05-12T00:00:00Z",
                "type": "response_item",
                "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Give a final judgment for the current review."}]},
            },
            {
                "timestamp": "2026-05-12T00:00:01Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "developer",
                    "content": [{"type": "input_text", "text": "Do not write secrets. Final assumption compact policy."}],
                },
            },
            {
                "timestamp": "2026-05-12T00:00:02Z",
                "type": "event_msg",
                "payload": {"type": "agent_message", "message": "Decision: inspect before editing"},
            },
            {
                "timestamp": "2026-05-12T00:00:03Z",
                "type": "response_item",
                "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Decision: inspect before editing"}]},
            },
            {
                "timestamp": "2026-05-12T00:00:04Z",
                "type": "event_msg",
                "payload": {
                    "type": "exec_command_end",
                    "call_id": "call-doc",
                    "exit_code": 0,
                    "status": "completed",
                    "aggregated_output": "docs mention error: examples, but the command succeeded",
                },
            },
        ],
    )

    receipt = module.handle_hook_event(
        "Stop",
        {
            "session_id": "noise-session",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    session_dir = Path(str(receipt["session_dir"]))
    segment_index = json.loads((session_dir / "segments" / "000__initial-to-latest.index.json").read_text(encoding="utf-8"))
    records = {event["event_id"]: event for event in segment_index["events"]}

    assert records["000002"]["type"] == "USER_INTENT"
    assert "final_state_signal" not in records["000002"]["tags"]
    assert records["000003"]["type"] == "CONTEXT_STATE"
    assert "security_policy_signal" in records["000003"]["tags"]
    assert "final_state_signal" not in records["000003"]["tags"]
    assert records["000004"]["type"] == "ASSISTANT_MESSAGE"
    assert "decision_signal" in records["000004"]["tags"]
    assert records["000005"]["type"] == "DECISION"
    assert records["000006"]["type"] == "COMMAND_OUTPUT"
    assert records["000006"]["outcome"] == "succeeded"
    assert "error_signal" not in records["000006"]["tags"]


def test_empty_nonzero_command_output_is_not_promoted_to_error(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-12T00-00-00-empty-nonzero.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-12T00:00:00Z", "type": "session_meta", "payload": {"id": "empty-nonzero", "cwd": str(workspace)}},
            {"timestamp": "2026-05-12T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Search for a marker"}]}},
            {"timestamp": "2026-05-12T00:00:02Z", "type": "response_item", "payload": {"type": "function_call", "name": "exec_command", "call_id": "call-rg", "arguments": json.dumps({"cmd": "rg -n missing-marker README.md"})}},
            {"timestamp": "2026-05-12T00:00:03Z", "type": "response_item", "payload": {"type": "function_call_output", "call_id": "call-rg", "output": "Chunk ID: x\nProcess exited with code 1\nOriginal token count: 0\nOutput:\n"}},
        ],
    )

    module.handle_hook_event(
        "Stop",
        {
            "session_id": "empty-nonzero",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    session_dir = aoa_root / "sessions" / "2026-05-12__001__search-for-a-marker"
    segment_index = json.loads((session_dir / "segments" / "000__initial-to-latest.index.json").read_text(encoding="utf-8"))
    output_event = {event["event_id"]: event for event in segment_index["events"]}["000004"]
    assert output_event["type"] == "COMMAND_OUTPUT"
    assert output_event["outcome"] == "failed"
    assert "empty_nonzero_output_signal" in output_event["tags"]
    assert "error_signal" not in output_event["tags"]


def test_security_risk_is_strict_and_tmp_cleanup_is_not_risk(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-12T00-00-00-security.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-12T00:00:00Z", "type": "session_meta", "payload": {"id": "security-session", "cwd": str(workspace)}},
            {
                "timestamp": "2026-05-12T00:00:01Z",
                "type": "response_item",
                "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Do not write secrets into exports."}]},
            },
            {
                "timestamp": "2026-05-12T00:00:02Z",
                "type": "response_item",
                "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Secret/data leak check completed before export."}]},
            },
            {
                "timestamp": "2026-05-12T00:00:03Z",
                "type": "response_item",
                "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "MAILERSEND_API_KEY is configured; value is not shown."}]},
            },
            {
                "timestamp": "2026-05-12T00:00:04Z",
                "type": "response_item",
                "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Token leaked in logs; rotate it."}]},
            },
            {
                "timestamp": "2026-05-12T00:00:05Z",
                "type": "response_item",
                "payload": {"type": "function_call", "name": "exec_command", "call_id": "call-tmp", "arguments": json.dumps({"cmd": "rm -rf /tmp/aoa-demo && mkdir -p /tmp/aoa-demo"})},
            },
            {
                "timestamp": "2026-05-12T00:00:06Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "exec_command",
                    "call_id": "call-cache",
                    "arguments": json.dumps({"cmd": "rm -rf /srv/AbyssOS/.aoa/scripts/__pycache__ /srv/AbyssOS/.aoa/tests/.pytest_cache"}),
                },
            },
            {
                "timestamp": "2026-05-12T00:00:07Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "exec_command",
                    "call_id": "call-find-cache",
                    "arguments": json.dumps({"cmd": "find /srv/AbyssOS/.aoa -type d -name __pycache__ -prune -exec rm -rf {} +"}),
                },
            },
            {
                "timestamp": "2026-05-12T00:00:08Z",
                "type": "response_item",
                "payload": {"type": "function_call", "name": "exec_command", "call_id": "call-risk", "arguments": json.dumps({"cmd": "rm -rf .aoa/recurrence"})},
            },
            {
                "timestamp": "2026-05-12T00:00:09Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "call-doc",
                    "output": (
                        "# AGENTS.md\n"
                        "## Hard no\n"
                        "- do not print or commit real secrets\n"
                        "- do not read or expose secret-bearing files from live hosts\n"
                        "## Review guidelines\n"
                        "- committed live secrets or secret-bearing rendered configs\n"
                    ),
                },
            },
        ],
    )

    receipt = module.handle_hook_event(
        "Stop",
        {
            "session_id": "security-session",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    session_dir = Path(str(receipt["session_dir"]))
    segment_index = json.loads((session_dir / "segments" / "000__initial-to-latest.index.json").read_text(encoding="utf-8"))
    records = {event["event_id"]: event for event in segment_index["events"]}

    assert records["000002"]["type"] == "ASSISTANT_MESSAGE"
    assert "security_policy_signal" in records["000002"]["tags"]
    assert records["000003"]["type"] == "ASSISTANT_MESSAGE"
    assert "security_policy_signal" in records["000003"]["tags"]
    assert records["000004"]["type"] == "SECURITY_TOUCHPOINT"
    assert "security_touchpoint_signal" in records["000004"]["tags"]
    assert records["000005"]["type"] == "SECURITY_OR_SECRET_RISK"
    assert records["000006"]["type"] == "FILE_WRITE"
    assert records["000006"]["facets"]["command_kind"] == "temporary_cleanup"
    assert records["000007"]["type"] == "FILE_WRITE"
    assert records["000007"]["facets"]["command_kind"] == "temporary_cleanup"
    assert records["000008"]["type"] == "FILE_WRITE"
    assert records["000008"]["facets"]["command_kind"] == "temporary_cleanup"
    assert records["000009"]["type"] == "SECURITY_OR_SECRET_RISK"
    assert records["000010"]["type"] == "SECURITY_TOUCHPOINT"
    assert "security_touchpoint_signal" in records["000010"]["tags"]


def test_reindex_sessions_regenerates_universal_indexes_from_raw(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-12T00-00-00-reindex.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-12T00:00:00Z", "type": "session_meta", "payload": {"id": "reindex-session", "cwd": str(workspace)}},
            {"timestamp": "2026-05-12T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Reindex this"}]}},
            {"timestamp": "2026-05-12T00:00:02Z", "type": "response_item", "payload": {"type": "function_call", "name": "exec_command", "call_id": "call-rg", "arguments": json.dumps({"cmd": "rg -n x README.md"})}},
            {"timestamp": "2026-05-12T00:00:03Z", "type": "response_item", "payload": {"type": "function_call_output", "call_id": "call-rg", "output": "Process exited with code 0\nOutput:\n"}},
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "reindex-session",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )
    session_dir = aoa_root / "sessions" / "2026-05-12__001__reindex-this"
    index_path = session_dir / "segments" / "000__initial-to-latest.index.json"
    broken = json.loads(index_path.read_text(encoding="utf-8"))
    broken.pop("by_family", None)
    for event in broken["events"]:
        event.pop("family", None)
    index_path.write_text(json.dumps(broken, ensure_ascii=False), encoding="utf-8")

    payload = module.reindex_sessions(aoa_root=aoa_root, target="all", write_report=True)

    rebuilt = json.loads(index_path.read_text(encoding="utf-8"))
    manifest = json.loads((session_dir / "session.manifest.json").read_text(encoding="utf-8"))
    assert payload["counts"] == {"reindexed": 1}
    assert Path(payload["report_json"]).exists()
    assert "workspace_navigation" in rebuilt["by_family"]
    assert rebuilt["events"][2]["family"] == "workspace_navigation"
    assert manifest["index_schema"]["universal_event_facets"] is True


def test_raw_unavailable_writes_diagnostic(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    missing = tmp_path / "missing.jsonl"

    receipt = module.handle_hook_event(
        "SessionStart",
        {
            "session_id": "missing-session",
            "transcript_path": str(missing),
            "cwd": str(workspace),
            "hook_event_name": "SessionStart",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    assert receipt["ok"] is True
    session_dir = Path(receipt["session_dir"])
    manifest = json.loads((session_dir / "session.manifest.json").read_text(encoding="utf-8"))
    assert manifest["archive_status"] == "raw_unavailable"
    assert manifest["session_id"] == "missing-session"
    assert manifest["display"]["label"].endswith("__codex-in-abyssos")
    assert manifest["display"]["path"] == str(session_dir)
    assert list((session_dir / "incidents").glob("*__INCIDENT.md"))
    assert list((session_dir / "incidents").glob("*__DIAGNOSTIC.json"))


def test_user_prompt_submit_is_light_by_default(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-12T00-00-00-session-light.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-12T00:00:00Z", "type": "session_meta", "payload": {"id": "session-light"}},
            {"timestamp": "2026-05-12T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user"}},
        ],
    )
    monkeypatch.delenv("AOA_SESSION_MEMORY_FULL_PROMPT_SYNC", raising=False)

    receipt = module.handle_hook_event(
        "UserPromptSubmit",
        {
            "session_id": "session-light",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "UserPromptSubmit",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    session_dir = aoa_root / "sessions" / "session-light"
    assert receipt["ok"] is True
    assert "prompt_hook_light_recorded" in receipt["actions"]
    assert (session_dir / "hooks" / "events.jsonl").exists()
    assert not (session_dir / "raw" / "session.raw.jsonl").exists()
    assert not (session_dir / "session.manifest.json").exists()


def test_codex_hook_output_uses_only_protocol_fields() -> None:
    receipt = {
        "ok": True,
        "session_dir": "/workspace/.aoa/sessions/demo",
        "display_name": "2026-05-12__001__demo",
        "navigation_path": "/workspace/.aoa/sessions/demo",
        "actions": ["hook_event_recorded"],
    }

    prompt_payload = module.codex_hook_output("UserPromptSubmit", receipt)
    stop_payload = module.codex_hook_output("Stop", receipt)
    pre_compact_payload = module.codex_hook_output("PreCompact", receipt)
    post_compact_payload = module.codex_hook_output("PostCompact", receipt)
    start_payload = module.codex_hook_output("SessionStart", receipt)

    assert prompt_payload == {"continue": True}
    assert stop_payload == {"continue": True}
    assert pre_compact_payload == {"continue": True}
    assert post_compact_payload == {"continue": True}
    assert "aoaSessionMemory" not in start_payload
    assert set(start_payload) == {"continue", "hookSpecificOutput"}
    assert start_payload["hookSpecificOutput"]["hookEventName"] == "SessionStart"


def test_hooks_config_builder_uses_supplied_roots(tmp_path: Path) -> None:
    workspace = tmp_path / "portable-workspace"
    aoa_root = workspace / ".aoa"

    config = module.build_user_hooks_config(workspace, aoa_root)

    assert set(config["hooks"]) == {"SessionStart", "UserPromptSubmit", "PreCompact", "PostCompact", "Stop"}
    assert config["hooks"]["SessionStart"][0]["matcher"] == "startup|resume"
    rendered = json.dumps(config, ensure_ascii=False)
    assert str(module.default_source_aoa_root()) not in rendered
    for event_name in config["hooks"]:
        command = config["hooks"][event_name][0]["hooks"][0]["command"]
        assert str(workspace) in command
        assert str(aoa_root / "scripts" / "aoa_session_memory.py") in command
        assert f"--event-name {event_name}" in command


def test_codex_hook_lookup_tracks_trust_and_expected_commands(tmp_path: Path) -> None:
    workspace = tmp_path / "portable-workspace"
    aoa_root = workspace / ".aoa"
    expected_commands = module.expected_hook_commands(workspace, aoa_root)
    hooks = [
        {
            "key": "/home/user/.codex/hooks.json:pre_compact:0:0",
            "eventName": "preCompact",
            "command": expected_commands["PreCompact"],
            "currentHash": "sha256:pre",
            "trustStatus": "trusted",
            "enabled": True,
        },
        {
            "key": "/home/user/.codex/hooks.json:post_compact:0:0",
            "eventName": "postCompact",
            "command": expected_commands["PostCompact"],
            "currentHash": "sha256:post",
            "trustStatus": "untrusted",
            "enabled": True,
        },
        {
            "key": "/home/user/.codex/hooks.json:stop:0:0",
            "eventName": "stop",
            "command": "python3 wrong.py",
            "currentHash": "sha256:wrong",
            "trustStatus": "trusted",
            "enabled": True,
        },
    ]

    lookup = module.hook_lookup_from_app_hooks(hooks, expected_commands)
    trust_state = module.hook_trust_state_from_lookup(lookup)

    assert lookup["PreCompact"]["present"] is True
    assert lookup["PreCompact"]["trusted"] is True
    assert lookup["PostCompact"]["present"] is True
    assert lookup["PostCompact"]["trusted"] is False
    assert lookup["Stop"]["present"] is False
    assert trust_state == {
        "/home/user/.codex/hooks.json:pre_compact:0:0": {"trusted_hash": "sha256:pre"},
        "/home/user/.codex/hooks.json:post_compact:0:0": {"trusted_hash": "sha256:post"},
    }


def test_default_aoa_root_uses_script_parent() -> None:
    assert module.aoa_root_for() == SCRIPT.parents[1]


def test_compaction_hooks_full_sync_and_rehydrate_packet(tmp_path: Path) -> None:
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
    session_dir = aoa_root / "sessions" / "2026-05-14__001__archive-compaction-intervals"
    manifest = json.loads((session_dir / "session.manifest.json").read_text(encoding="utf-8"))
    assert manifest["hooks_seen"] == ["PostCompact", "PreCompact"]
    assert [segment["role"] for segment in manifest["segments"]] == ["initial-to-compaction", "compaction-to-latest"]
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
    assert checks["precompact_receipt_ok"] is True
    assert checks["postcompact_receipt_ok"] is True
    assert checks["stop_receipt_ok"] is True
    assert checks["segments_include_compaction_interval"] is True
    assert checks["rehydrate_packet_preserves_decision_route"] is True
    assert checks["first_pass_distillation_has_candidates"] is True


def test_install_portable_bundle_creates_clean_target(tmp_path: Path) -> None:
    source_aoa = SCRIPT.parents[1]
    workspace = tmp_path / "TargetWorkspace"
    aoa_root = workspace / ".aoa"

    payload = module.install_portable_bundle(
        source_aoa_root=source_aoa,
        workspace_root=workspace,
        aoa_root=aoa_root,
        overwrite=True,
    )

    assert payload["ok"] is True
    assert (aoa_root / "INSTALL.md").exists()
    assert (aoa_root / "scripts" / "aoa_session_memory.py").exists()
    assert (aoa_root / "tests" / "test_session_memory.py").exists()
    registry = json.loads((aoa_root / "session-registry.json").read_text(encoding="utf-8"))
    assert registry["sessions"] == []
    assert list((aoa_root / "sessions").iterdir()) == []
    hook_example = json.loads((aoa_root / "hooks" / "codex-hooks.user.example.json").read_text(encoding="utf-8"))
    rendered_hooks = json.dumps(hook_example, ensure_ascii=False)
    assert str(module.default_source_aoa_root()) not in rendered_hooks
    assert str(workspace) in rendered_hooks
    assert str(aoa_root) in rendered_hooks

    validation = module.validate_pipeline(workspace_root=workspace, aoa_root=aoa_root)
    assert validation["ok"] is True


def test_force_export_clear_preserves_git_metadata(tmp_path: Path) -> None:
    target = tmp_path / "repo"
    git_dir = target / ".git"
    stale_dir = target / "stale"
    stale_file = target / "stale.txt"
    git_dir.mkdir(parents=True)
    (git_dir / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    stale_dir.mkdir()
    (stale_dir / "old.txt").write_text("old\n", encoding="utf-8")
    stale_file.write_text("old\n", encoding="utf-8")

    module.clear_export_target_for_force(target)

    assert git_dir.exists()
    assert (git_dir / "HEAD").exists()
    assert not stale_dir.exists()
    assert not stale_file.exists()


def test_install_portable_bundle_preserves_existing_sessions(tmp_path: Path) -> None:
    source_aoa = SCRIPT.parents[1]
    workspace = tmp_path / "ExistingWorkspace"
    aoa_root = workspace / ".aoa"
    session_dir = aoa_root / "sessions" / "2026-05-12__001__existing-session"
    session_dir.mkdir(parents=True)
    registry_path = aoa_root / "session-registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "sessions": [
                    {
                        "session_id": "existing-session",
                        "session_label": "2026-05-12__001__existing-session",
                        "path": str(session_dir),
                    }
                ],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    module.install_portable_bundle(
        source_aoa_root=source_aoa,
        workspace_root=workspace,
        aoa_root=aoa_root,
        overwrite=True,
    )

    assert session_dir.exists()
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    assert registry["sessions"][0]["session_id"] == "existing-session"


def test_install_user_skill_symlinks_router_and_is_idempotent(tmp_path: Path) -> None:
    source_aoa = SCRIPT.parents[1]
    skills_dir = tmp_path / "skills"
    source_skill = source_aoa / "skills" / module.USER_LEVEL_SKILL_NAME

    payload = module.install_user_skill(aoa_root=source_aoa, skills_dir=skills_dir)

    target = skills_dir / module.USER_LEVEL_SKILL_NAME
    assert payload["ok"] is True
    assert payload["installed"] is True
    assert target.is_symlink()
    assert target.resolve() == source_skill.resolve()
    state = module.user_skill_install_state(source_aoa, skills_dir)
    assert state["ok"] is True
    assert state["linked_to_source"] is True

    second = module.install_user_skill(aoa_root=source_aoa, skills_dir=skills_dir)
    assert second["ok"] is True
    assert second["already_installed"] is True
    assert second["installed"] is False


def test_install_user_skill_backs_up_conflicting_target_on_force(tmp_path: Path) -> None:
    source_aoa = SCRIPT.parents[1]
    skills_dir = tmp_path / "skills"
    target = skills_dir / module.USER_LEVEL_SKILL_NAME
    target.mkdir(parents=True)
    (target / "SKILL.md").write_text("---\nname: old\ndescription: old\n---\n", encoding="utf-8")

    blocked = module.install_user_skill(aoa_root=source_aoa, skills_dir=skills_dir)
    assert blocked["ok"] is False
    assert blocked["installed"] is False
    assert target.is_dir()

    replaced = module.install_user_skill(aoa_root=source_aoa, skills_dir=skills_dir, force=True)
    assert replaced["ok"] is True
    assert replaced["installed"] is True
    assert replaced["backup_path"]
    assert Path(replaced["backup_path"]).exists()
    assert target.is_symlink()


def test_install_user_skill_accepts_relative_aoa_root(tmp_path: Path, monkeypatch) -> None:
    aoa_root = tmp_path / "bundle"
    source = aoa_root / "skills" / module.USER_LEVEL_SKILL_NAME
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text(
        "---\nname: aoa-session-memory-global-route\ndescription: route\n---\n",
        encoding="utf-8",
    )
    skills_dir = tmp_path / "user-skills"

    monkeypatch.chdir(aoa_root)
    payload = module.install_user_skill(aoa_root=Path("."), skills_dir=skills_dir)

    target = skills_dir / module.USER_LEVEL_SKILL_NAME
    assert payload["ok"] is True
    assert target.is_symlink()
    assert target.resolve() == source.resolve()


def test_import_codex_sessions_dry_run_import_and_skip(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    source_root = tmp_path / "codex-sessions"
    transcript = source_root / "2026" / "05" / "02" / "rollout-2026-05-02T12-00-00-import-session.jsonl"
    write_jsonl(
        transcript,
        [
            {
                "timestamp": "2026-05-02T12:00:00Z",
                "type": "session_meta",
                "payload": {"id": "import-session", "cwd": str(workspace), "timestamp": "2026-05-02T12:00:00Z"},
            },
            {
                "timestamp": "2026-05-02T12:00:01Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "Import old session properly"}],
                },
            },
        ],
    )

    dry = module.import_codex_sessions(
        aoa_root=aoa_root,
        source_root=source_root,
        since="2026-05-01",
        dry_run=True,
        write_report=True,
    )

    assert dry["ok"] is True
    assert dry["counts"] == {"planned": 1}
    assert Path(dry["report_json"]).exists()
    assert Path(dry["report_markdown"]).exists()

    imported = module.import_codex_sessions(aoa_root=aoa_root, source_root=source_root, since="2026-05-01")
    assert imported["ok"] is True
    assert imported["counts"] == {"imported": 1}
    session_dir = Path(imported["results"][0]["session_dir"])
    assert session_dir.name == "2026-05-02__001__import-session-properly"
    assert (session_dir / "raw" / "session.raw.jsonl").exists()

    skipped = module.import_codex_sessions(aoa_root=aoa_root, source_root=source_root, since="2026-05-01")
    assert skipped["ok"] is True
    assert skipped["counts"] == {"skipped_existing": 1}


def test_codex_grounding_accepts_expected_config_and_markers(tmp_path: Path) -> None:
    workspace = tmp_path / "Workspace"
    aoa_root = workspace / ".aoa"
    (workspace / ".codex").mkdir(parents=True)
    (workspace / ".codex" / "config.toml").write_text(
        "\n".join(
            [
                "model_context_window = 400000",
                "model_auto_compact_token_limit = 320000",
                "",
                "[features]",
                "hooks = true",
                "",
            ]
        ),
        encoding="utf-8",
    )
    native = tmp_path / "codex-native"
    native.write_bytes(
        b"SessionStart user-prompt-submit.command.input PreCompact pre-compact.command "
        b"PostCompact post-compact.command stopReason"
    )
    native.chmod(0o755)

    payload = module.codex_grounding(
        workspace_root=workspace,
        aoa_root=aoa_root,
        codex_native_bin=native,
        codex_version_output="codex-cli 0.130.0",
    )

    assert payload["ok"] is True
    assert payload["compact_ratio"] == 0.8
    assert all(payload["schema_markers"].values())


def test_completion_audit_reports_covered_segments_and_remaining_live_hooks(tmp_path: Path) -> None:
    workspace = tmp_path / "Workspace"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-14T02-00-00-session-audit.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-14T02:00:00Z", "type": "session_meta", "payload": {"id": "session-audit"}},
            {"timestamp": "2026-05-14T02:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Audit compact markers"}]}},
            {"timestamp": "2026-05-14T02:00:02Z", "type": "compacted", "payload": {"replacement_history": []}},
            {"timestamp": "2026-05-14T02:00:03Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "done"}]}},
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "session-audit",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    payload = module.completion_audit(workspace_root=workspace, aoa_root=aoa_root, check_codex=False)

    assert payload["ok"] is False
    statuses = {item["requirement"]: item["status"] for item in payload["checklist"]}
    assert statuses["Real Codex compaction boundaries are detected from raw transcripts"] == "covered"
    assert statuses["Segment topology matches raw compaction boundaries"] == "covered"
    assert statuses["User-level router skill is installed for the current Codex user"] == "remaining"
    assert statuses["Live PreCompact and PostCompact hook receipts observed in archived sessions"] == "remaining"


def test_completion_audit_handles_raw_unavailable_archives(tmp_path: Path) -> None:
    workspace = tmp_path / "Workspace"
    aoa_root = workspace / ".aoa"
    missing = tmp_path / "missing-transcript.jsonl"
    module.handle_hook_event(
        "SessionStart",
        {
            "session_id": "missing-audit-session",
            "transcript_path": str(missing),
            "cwd": str(workspace),
            "hook_event_name": "SessionStart",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    payload = module.completion_audit(workspace_root=workspace, aoa_root=aoa_root, check_codex=False)

    unavailable = [
        item for item in payload["archive_compaction_audit"] if item["session_id"] == "missing-audit-session"
    ][0]
    assert unavailable["archive_status"] == "raw_unavailable"
    assert unavailable["raw_exists"] is False
    assert unavailable["expected_segment_count"] == 0


def test_first_pass_distillation_writes_reviewable_route_map(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    (aoa_root / "config").mkdir(parents=True, exist_ok=True)
    (aoa_root / "config" / "event-distillation-routes.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "routes": {
                    "DECISION": ["adr", "principle"],
                    "ERROR": ["root_cause"],
                    "COMMAND": ["command_recipe"],
                    "COMMAND_OUTPUT": ["verification_signal"],
                },
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    transcript = tmp_path / "rollout-2026-05-15T00-00-00-session-distill.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-15T00:00:00Z", "type": "session_meta", "payload": {"id": "session-distill"}},
            {"timestamp": "2026-05-15T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Distill route map"}]}},
            {"timestamp": "2026-05-15T00:00:02Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Decision: route events through review"}]}},
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "session-distill",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    payload = module.distill_session_first_pass(aoa_root, "latest")

    assert payload["ok"] is True
    session_dir = aoa_root / "sessions" / "2026-05-15__001__distill-route-map"
    manifest = json.loads((session_dir / "session.manifest.json").read_text(encoding="utf-8"))
    distillation_index = json.loads((session_dir / "distillation" / "distillation.index.json").read_text(encoding="utf-8"))
    distillation_md = (session_dir / "distillation" / "001__first-pass__experience-map.md").read_text(encoding="utf-8")
    assert manifest["distillation_status"] == "first_pass_distilled"
    assert manifest["distillation_iteration"] == 1
    assert manifest["distillation"]["candidate_count"] >= 1
    assert distillation_index["status"] == "provisional"
    assert "DECISION" in distillation_index["candidates_by_type"]
    assert "raw=`raw:line:" in distillation_md


def test_batch_distill_builds_first_wave_queue_and_applies(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    (workspace / "AGENTS.md").parent.mkdir(parents=True, exist_ok=True)
    (workspace / "AGENTS.md").write_text("project law\n", encoding="utf-8")
    (workspace / "DESIGN.md").write_text("project design\n", encoding="utf-8")
    (aoa_root / "config").mkdir(parents=True, exist_ok=True)
    (aoa_root / "config" / "event-distillation-routes.json").write_text(
        json.dumps({"schema_version": 1, "routes": {"PROCESS_LESSON": ["skill_amendment"]}}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    transcript = tmp_path / "rollout-2026-05-16T00-00-00-batch-distill.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-16T00:00:00Z", "type": "session_meta", "payload": {"id": "batch-distill"}},
            {"timestamp": "2026-05-16T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Build the conveyor"}]}},
            {"timestamp": "2026-05-16T00:00:02Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Process lesson: first wave writes only provisional evidence maps"}]}},
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "batch-distill",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    planned = module.batch_distill_sessions(aoa_root=aoa_root, since="2026-05-16", write_report=True)

    assert planned["ok"] is True
    assert planned["counts"] == {"planned": 1}
    assert Path(planned["report_json"]).exists()
    assert "manual_review" in planned["results"][0]["lanes"]
    assert "mechanics_candidate" in planned["results"][0]["lanes"]
    assert planned["results"][0]["auto_actions"] == ["write_provisional_first_pass_distillation"]
    assert planned["results"][0]["project_grounding"]["status"] == "grounded"
    assert {item["name"] for item in planned["results"][0]["project_grounding"]["files"]} == {"AGENTS.md", "DESIGN.md"}

    applied = module.batch_distill_sessions(aoa_root=aoa_root, since="2026-05-16", apply=True)

    session_dir = aoa_root / "sessions" / "2026-05-16__001__build-the-conveyor"
    manifest = json.loads((session_dir / "session.manifest.json").read_text(encoding="utf-8"))
    assert applied["counts"] == {"distilled": 1}
    assert manifest["distillation_status"] == "first_pass_distilled"
    assert (session_dir / "distillation" / "distillation.index.json").exists()


def test_manual_review_wave_writes_packets_and_promotion_layer(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    (workspace / "AGENTS.md").parent.mkdir(parents=True, exist_ok=True)
    (workspace / "AGENTS.md").write_text("project law\n", encoding="utf-8")
    (aoa_root / "config").mkdir(parents=True, exist_ok=True)
    (aoa_root / "config" / "event-distillation-routes.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "routes": {
                    "DECISION": ["adr"],
                    "PROCESS_LESSON": ["skill_amendment"],
                    "ERROR": ["root_cause"],
                },
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    transcript = tmp_path / "rollout-2026-05-16T00-00-00-manual-review.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-16T00:00:00Z", "type": "session_meta", "payload": {"id": "manual-review", "cwd": str(workspace)}},
            {"timestamp": "2026-05-16T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Review this session"}]}},
            {"timestamp": "2026-05-16T00:00:02Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Decision: keep raw evidence before summaries"}]}},
            {"timestamp": "2026-05-16T00:00:03Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Process lesson: review packets must stay provisional"}]}},
            {"timestamp": "2026-05-16T00:00:04Z", "type": "response_item", "payload": {"type": "function_call_output", "call_id": "call-fail", "output": "Process exited with code 1\nOutput:\nerror: broken fixture\n"}},
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "manual-review",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    planned = module.manual_review_wave(aoa_root=aoa_root, workspace_root=workspace, since="2026-05-16", priority="sample")
    applied = module.manual_review_wave(aoa_root=aoa_root, workspace_root=workspace, since="2026-05-16", priority="sample", apply=True, write_report=True)
    layer = module.build_promotion_review_layer(aoa_root=aoa_root, since="2026-05-16", write_report=True)

    session_dir = aoa_root / "sessions" / "2026-05-16__001__review-this-session"
    manifest = json.loads((session_dir / "session.manifest.json").read_text(encoding="utf-8"))
    packet_path = Path(applied["results"][0]["manual_review_packet"])
    promotion_path = Path(applied["results"][0]["promotion_index"])
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    promotion = json.loads(promotion_path.read_text(encoding="utf-8"))
    assert planned["counts"] == {"planned": 1}
    assert planned["wave_id"] == "manual-review-wave1"
    assert applied["counts"] == {"packet_written": 1}
    assert applied["wave_id"] == "manual-review-wave1"
    assert applied["results"][0]["wave_sequence"] == 1
    assert applied["results"][0]["manual_review_priority"] == "sample"
    assert applied["results"][0]["owner_resolution"]["status"] == "resolved"
    assert Path(applied["report_json"]).exists()
    assert manifest["review_status"] == "manual_review_open"
    assert manifest["manual_review"]["wave_count"] == 1
    assert manifest["promotion"]["wave_count"] == 1
    assert manifest["review_index"]["status"] == "open_for_future_passes"
    assert packet_path.name == "001__manual-review-wave1__manual-review-packet.json"
    assert packet_path.parent.name == "waves"
    assert packet["review_truth_status"] == "not_reviewed_truth"
    assert packet["open_status"] == "open_for_future_passes"
    assert packet["wave_sequence"] == 1
    assert packet["promotion_candidate_count"] >= 2
    assert promotion["promoted_claim_count"] == 0
    assert promotion["status"] == "promotion_candidates_unreviewed"
    assert promotion["open_status"] == "open_for_future_passes"
    assert layer["selected_count"] == 1
    assert layer["candidate_count"] == promotion["candidate_count"]
    assert layer["raw_candidate_count"] == promotion["candidate_count"]
    assert layer["promoted_claim_count"] == 0

    second = module.manual_review_wave(aoa_root=aoa_root, workspace_root=workspace, since="2026-05-16", priority="sample", apply=True)
    second_packet_path = Path(second["results"][0]["manual_review_packet"])
    second_promotion_path = Path(second["results"][0]["promotion_index"])
    second_manifest = json.loads((session_dir / "session.manifest.json").read_text(encoding="utf-8"))
    second_layer = module.build_promotion_review_layer(aoa_root=aoa_root, since="2026-05-16")

    assert second["wave_id"] == "manual-review-wave2"
    assert second["results"][0]["wave_sequence"] == 2
    assert second_packet_path.name == "002__manual-review-wave2__manual-review-packet.json"
    assert packet_path.exists()
    assert second_packet_path.exists()
    assert promotion_path.exists()
    assert second_promotion_path.exists()
    assert second_manifest["manual_review"]["wave_count"] == 2
    assert second_manifest["promotion"]["wave_count"] == 2
    assert (session_dir / "distillation" / "review.index.json").exists()
    assert second_layer["selected_count"] == 1
    assert second_layer["candidate_count"] == promotion["candidate_count"]
    assert second_layer["raw_candidate_count"] == promotion["candidate_count"] * 2
    assert second_layer["promoted_claim_count"] == 0


def test_batch_distill_uses_workspace_grounding_fallback(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    (workspace / "AGENTS.md").parent.mkdir(parents=True, exist_ok=True)
    (workspace / "AGENTS.md").write_text("workspace law\n", encoding="utf-8")
    transcript = tmp_path / "rollout-2026-05-16T00-00-00-grounding-fallback.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-16T00:00:00Z", "type": "session_meta", "payload": {"id": "grounding-fallback"}},
            {"timestamp": "2026-05-16T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Ground this session"}]}},
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "grounding-fallback",
            "transcript_path": str(transcript),
            "cwd": str(tmp_path / "missing-cwd"),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    planned = module.batch_distill_sessions(aoa_root=aoa_root, workspace_root=workspace, since="2026-05-16")

    grounding = planned["results"][0]["project_grounding"]
    assert grounding["status"] == "workspace_fallback_grounded"
    assert grounding["fallback_used"] is True
    assert grounding["files"][0]["path"] == str(workspace / "AGENTS.md")


def test_owner_path_inference_is_fail_open_when_home_is_missing(monkeypatch) -> None:
    monkeypatch.delenv("HOME", raising=False)

    owner = module.inferred_owner_root_for_path("~/missing")
    assert owner in {None, "/home/dionysus"}


def test_owner_resolution_uses_indexed_paths_when_grounding_falls_back(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    (workspace / "AGENTS.md").parent.mkdir(parents=True, exist_ok=True)
    (workspace / "AGENTS.md").write_text("workspace law\n", encoding="utf-8")
    transcript = tmp_path / "rollout-2026-05-16T00-00-00-owner-resolution.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-16T00:00:00Z", "type": "session_meta", "payload": {"id": "owner-resolution"}},
            {"timestamp": "2026-05-16T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Find the real owner"}]}},
            {
                "timestamp": "2026-05-16T00:00:02Z",
                "type": "response_item",
                "payload": {"type": "function_call", "name": "exec_command", "call_id": "call-owner", "arguments": json.dumps({"cmd": "rg -n TODO /srv/aoa-sdk/README.md"})},
            },
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "owner-resolution",
            "transcript_path": str(transcript),
            "cwd": str(tmp_path / "missing-cwd"),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    planned = module.batch_distill_sessions(aoa_root=aoa_root, workspace_root=workspace, since="2026-05-16")
    owner = planned["results"][0]["owner_resolution"]

    assert planned["results"][0]["project_grounding"]["status"] == "workspace_fallback_grounded"
    assert owner["status"] == "resolved_from_evidence"
    assert owner["owner_root"] == "/srv/aoa-sdk"
    assert owner["confidence"] == "medium"


def test_repair_session_titles_skips_ide_context_prompt(tmp_path: Path) -> None:
    aoa_root = tmp_path / ".aoa"
    session_dir = aoa_root / "sessions" / "2026-05-17__001__files-mentioned-by-the-user"
    raw_path = session_dir / "raw" / "session.raw.jsonl"
    write_jsonl(
        raw_path,
        [
            {"timestamp": "2026-05-17T10:00:00Z", "type": "session_meta", "payload": {"id": "weak-title-session"}},
            {
                "timestamp": "2026-05-17T10:00:01Z",
                "type": "response_item",
                "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Files mentioned by the user:\n- /srv/AbyssOS/.aoa/DESIGN.md"}]},
            },
            {
                "timestamp": "2026-05-17T10:00:02Z",
                "type": "response_item",
                "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Repair the session naming topology"}]},
            },
        ],
    )
    manifest = {
        "schema_version": 1,
        "session_id": "weak-title-session",
        "created_at": "2026-05-17T10:00:00Z",
        "updated_at": "2026-05-17T10:00:03Z",
        "source": {"transcript_path": "/tmp/rollout-2026-05-17T10-00-00-weak-title-session.jsonl"},
        "archive_status": "indexed",
        "distillation_status": "raw_archived",
        "raw": {"path": str(raw_path)},
        "segments": [],
        "latest_event_count": 3,
        "display": {
            "date": "2026-05-17",
            "sequence": 1,
            "title": "Files mentioned by the user",
            "title_source": "first_user_message",
            "label": "2026-05-17__001__files-mentioned-by-the-user",
            "path": str(session_dir),
            "archive_path": str(session_dir),
            "navigation_path": str(session_dir),
        },
        "session_label": "2026-05-17__001__files-mentioned-by-the-user",
        "session_title": "Files mentioned by the user",
    }
    (session_dir / "session.manifest.json").write_text(json.dumps(manifest, ensure_ascii=False) + "\n", encoding="utf-8")
    module.update_registry(aoa_root, manifest, session_dir)

    planned = module.repair_session_titles(aoa_root=aoa_root, since="2026-05-17")
    applied = module.repair_session_titles(aoa_root=aoa_root, since="2026-05-17", apply=True)

    repaired_dir = aoa_root / "sessions" / "2026-05-17__001__repair-the-session-naming-topology"
    repaired_manifest = json.loads((repaired_dir / "session.manifest.json").read_text(encoding="utf-8"))
    assert planned["counts"] == {"planned": 1}
    assert "weak_title" in planned["results"][0]["reasons"]
    assert applied["counts"] == {"repaired": 1}
    assert repaired_manifest["display"]["title"] == "Repair the session naming topology"
    assert repaired_manifest["raw"]["path"] == str(repaired_dir / "raw" / "session.raw.jsonl")
    assert not session_dir.exists()


def test_rebuild_session_labels_backfills_existing_archive(tmp_path: Path) -> None:
    aoa_root = tmp_path / ".aoa"
    legacy_dir = aoa_root / "codex-sessions" / "legacy-session"
    raw_path = legacy_dir / "raw" / "session.raw.jsonl"
    write_jsonl(
        raw_path,
        [
            {"timestamp": "2026-05-13T10:00:00Z", "type": "session_meta", "payload": {"id": "legacy-session"}},
            {"timestamp": "2026-05-13T10:00:00Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "# AGENTS.md instructions for /tmp\n\n<INSTRUCTIONS>skip me</INSTRUCTIONS>"}]}},
            {"timestamp": "2026-05-13T10:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Backfill readable names"}]}},
        ],
    )
    (legacy_dir / "session.manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "session_id": "legacy-session",
                "created_at": "2026-05-13T10:00:00Z",
                "updated_at": "2026-05-13T10:00:02Z",
                "source": {"transcript_path": "/tmp/rollout-2026-05-13T10-00-00-legacy-session.jsonl"},
                "archive_status": "indexed",
                "distillation_status": "raw_archived",
                "raw": {"path": str(raw_path)},
                "segments": [],
                "latest_event_count": 3,
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    payload = module.rebuild_session_labels(aoa_root)

    session_dir = aoa_root / "sessions" / "2026-05-13__001__backfill-readable-names"
    manifest = json.loads((session_dir / "session.manifest.json").read_text(encoding="utf-8"))
    assert payload["sessions"][0]["label"] == "2026-05-13__001__backfill-readable-names"
    assert manifest["display"]["label"] == "2026-05-13__001__backfill-readable-names"
    assert manifest["display"]["path"] == str(session_dir)
    assert manifest["raw"]["path"] == str(session_dir / "raw" / "session.raw.jsonl")
    assert not legacy_dir.exists()
    registry = json.loads((aoa_root / "session-registry.json").read_text(encoding="utf-8"))
    assert registry["sessions"][0]["session_label"] == "2026-05-13__001__backfill-readable-names"
