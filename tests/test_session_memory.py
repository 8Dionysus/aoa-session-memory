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
    assert module.phase_candidate_name(
        "000",
        ["# AGENTS.md instructions for /srv\n<INSTRUCTIONS>policy</INSTRUCTIONS>", "Continue real naming work"],
        [],
        module.Counter(),
    )["name"] == "Continue real naming work"
    assert module.phase_candidate_name(
        "000",
        ["/home/dionysus/Загрузки/aoa-session-dist-exp(идея).md Вот тут лежит диалог с важной идеей"],
        [],
        module.Counter(),
    )["name"] == "Вот тут лежит диалог с важной идеей"
    generic_payload = module.phase_candidate_name(
        "000",
        ["Давай, действуй!"],
        ["scripts/aoa_session_memory.py"],
        module.Counter({"VERIFICATION": 1}),
    )
    assert generic_payload["name"] == "aoa_session_memory.py validation"
    assert generic_payload["basis"] == "linked_path_event_signals"
    assert "generic_user_intent_present" in generic_payload["quality_flags"]


def test_phase_candidate_review_turns_weak_names_into_actionable_queue_items() -> None:
    coverage = {"raw_ranges": [{"from_line": 10, "to_line": 30}], "note": "fixture"}
    review = module.phase_candidate_review(
        session_label="2026-05-20__001__large-session",
        segment_id="003",
        candidate_name=".aoa validation",
        confidence="low",
        name_basis="linked_path_event_signals",
        quality_flags=["no_specific_user_intent", "path_or_event_based_name"],
        coverage=coverage,
        evidence_refs=["raw:line:12"],
        linked_signals={
            "primary_user_intent": "",
            "support_paths": ["/srv/AbyssOS/.aoa/scripts/aoa_session_memory.py"],
            "support_event_types": {"COMMAND": 4, "VERIFICATION": 2},
        },
    )
    candidate = {
        "segment_id": "003",
        "name": ".aoa validation",
        "confidence": "low",
        "name_basis": "linked_path_event_signals",
        "quality_flags": ["no_specific_user_intent", "path_or_event_based_name"],
        "coverage": coverage,
        "evidence": ["raw:line:12"],
        "review": review,
    }
    payload = {
        "generated_at": "2026-05-20T00:00:00Z",
        "session_label": "2026-05-20__001__large-session",
        "archive_status": "indexed",
        "event_count": 20,
        "segment_count": 1,
        "candidate_count": 1,
        "review_queue_count": 1,
        "raw_path": "/tmp/session.raw.jsonl",
        "candidate_quality_counts": module.phase_candidate_quality_counts([candidate]),
        "review_queue": module.phase_review_queue([candidate]),
        "candidates": [candidate],
    }
    markdown = module.phase_discovery_markdown(payload)

    assert review["status"] == "needs_semantic_synthesis"
    assert review["action"] == "synthesize_reviewed_name_from_linked_signals"
    assert "review-phase-name" in review["apply_template"]
    assert "--segment 003" in review["apply_template"]
    assert "--reviewed-name '<reviewed phase name>'" in review["apply_template"]
    assert payload["review_queue"][0]["review"]["review_inputs"]["support_paths"]
    assert "## Review Apply Templates" in markdown
    assert "python3 scripts/aoa_session_memory.py review-phase-name" in markdown


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


def test_lifecycle_hooks_defer_indexing_and_manual_sync_full_syncs(tmp_path: Path, monkeypatch) -> None:
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
    light_session_dir = aoa_root / "sessions" / "2026-05-14__001__codex-in-abyssos"
    light_manifest = json.loads((light_session_dir / "session.manifest.json").read_text(encoding="utf-8"))
    assert light_manifest["archive_status"] == "raw_mirrored_index_deferred"
    assert light_manifest["hooks_seen"] == ["PostCompact", "PreCompact"]
    assert light_manifest["segments"] == []
    assert (light_session_dir / "raw" / "session.raw.jsonl").exists()

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

    assert stop["ok"] is True
    assert "indexing_deferred" in stop["actions"]
    light_manifest = json.loads((light_session_dir / "session.manifest.json").read_text(encoding="utf-8"))
    assert light_manifest["archive_status"] == "raw_mirrored_index_deferred"
    assert light_manifest["hooks_seen"] == ["PostCompact", "PreCompact", "Stop"]
    assert light_manifest["segments"] == []

    deferred_audit = module.completion_audit(workspace_root=workspace, aoa_root=aoa_root, check_codex=False)
    topology = [
        item for item in deferred_audit["checklist"] if item["requirement"] == "Segment topology matches raw compaction boundaries"
    ][0]
    assert topology["status"] == "missing"
    assert topology["evidence"]["indexed_archives"] == []
    assert topology["evidence"]["deferred_archives"][0]["archive_status"] == "raw_mirrored_index_deferred"

    reindexed = module.reindex_sessions(aoa_root=aoa_root, target="latest")
    assert reindexed["counts"] == {"reindexed": 1}
    light_manifest = json.loads((light_session_dir / "session.manifest.json").read_text(encoding="utf-8"))
    assert light_manifest["archive_status"] == "indexed"
    assert [segment["role"] for segment in light_manifest["segments"]] == ["initial-to-compaction", "compaction-to-latest"]

    synced = module.sync_session_from_transcript(
        aoa_root=aoa_root,
        event={"session_id": "session-compact", "transcript_path": str(transcript), "cwd": str(workspace)},
        transcript_path=transcript,
        hook_event_name="ManualSync",
    )
    assert synced["segment_count"] == 2
    session_dir = aoa_root / "sessions" / "2026-05-14__001__archive-compaction-intervals"
    manifest = json.loads((session_dir / "session.manifest.json").read_text(encoding="utf-8"))
    assert manifest["archive_status"] == "indexed"
    assert manifest["hooks_seen"] == ["ManualSync", "PostCompact", "PreCompact", "Stop"]
    assert [segment["role"] for segment in manifest["segments"]] == ["initial-to-compaction", "compaction-to-latest"]
    assert not light_session_dir.exists()
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
    assert (aoa_root / "DESIGN.AGENTS.md").exists()
    assert (aoa_root / "config" / "AGENTS.md").exists()
    assert (aoa_root / "hooks" / "AGENTS.md").exists()
    assert (aoa_root / "schemas" / "AGENTS.md").exists()
    assert (aoa_root / "scripts" / "AGENTS.md").exists()
    assert (aoa_root / "sessions" / "AGENTS.md").exists()
    assert (aoa_root / "skills" / "AGENTS.md").exists()
    assert (aoa_root / "tests" / "AGENTS.md").exists()
    assert (aoa_root / "scripts" / "aoa_session_memory.py").exists()
    assert (aoa_root / "tests" / "test_session_memory.py").exists()
    registry = json.loads((aoa_root / "session-registry.json").read_text(encoding="utf-8"))
    assert registry["sessions"] == []
    session_entries = sorted(path.name for path in (aoa_root / "sessions").iterdir())
    sessions_index = json.loads((aoa_root / "sessions" / module.SESSIONS_INDEX_JSON).read_text(encoding="utf-8"))
    assert session_entries == [module.SESSIONS_AGENTS_MARKDOWN, module.SESSIONS_INDEX_MARKDOWN, module.SESSIONS_INDEX_JSON]
    assert sessions_index["read_order"][0] == module.SESSIONS_AGENTS_MARKDOWN
    assert sessions_index["session_count"] == 0
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


def test_semantic_session_name_anchors_raw_without_renaming_archive(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-18T00-00-00-semantic-name.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-18T00:00:00Z", "type": "session_meta", "payload": {"id": "semantic-name-session", "cwd": str(workspace)}},
            {"timestamp": "2026-05-18T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Continue the work"}]}},
            {"timestamp": "2026-05-18T00:00:02Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Finish the aoa-techniques final residual promotion pass"}]}},
            {"timestamp": "2026-05-18T00:00:03Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Decision: use raw refs before promotion."}]}},
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "semantic-name-session",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    session_dir = aoa_root / "sessions" / "2026-05-18__001__continue-the-work"
    manifest_before = json.loads((session_dir / "session.manifest.json").read_text(encoding="utf-8"))
    raw_sha = manifest_before["raw"]["sha256"]
    payload = module.set_session_semantic_name(
        aoa_root=aoa_root,
        target="continue-the-work",
        name="aoa-techniques continuation",
        scope="session",
        kind="session_essence",
        evidence_refs=["raw:line:2", "raw:line:3"],
        from_line=2,
        to_line=4,
        coverage_note="Umbrella continuation intent and later specific phase.",
        source="operator",
        note="Mutable session-level name, anchored to raw evidence.",
        apply=True,
        verify_raw_hash=True,
    )
    phase_payload = module.set_session_semantic_name(
        aoa_root=aoa_root,
        target="continue-the-work",
        name="aoa-techniques final residual promotion pass",
        scope="phase",
        kind="dominant_topic",
        evidence_refs=["raw:line:3"],
        from_line=3,
        to_line=4,
        coverage_note="Later phase, not the umbrella session name.",
        source="operator",
        note="Dominant later topic, anchored to raw evidence.",
        apply=True,
        verify_raw_hash=True,
    )

    manifest = json.loads((session_dir / "session.manifest.json").read_text(encoding="utf-8"))
    semantic_by_slug = {item["slug"]: item for item in manifest["semantic_names"]["names"]}
    semantic = semantic_by_slug["aoa-techniques-continuation"]
    phase = semantic_by_slug["aoa-techniques-final-residual-promotion-pass"]
    registry_record = module.resolve_session_record(aoa_root, "aoa-techniques-continuation")
    phase_record = module.resolve_session_record(aoa_root, "aoa-techniques-final-residual-promotion-pass")
    packet = module.rehydrate_packet(aoa_root, "aoa-techniques-final-residual-promotion-pass")
    session_md = (session_dir / "SESSION.md").read_text(encoding="utf-8")
    name_index = json.loads((aoa_root / module.SESSION_NAME_INDEX_JSON).read_text(encoding="utf-8"))
    name_index_md = (aoa_root / module.SESSION_NAME_INDEX_MARKDOWN).read_text(encoding="utf-8")
    sessions_index = json.loads((aoa_root / "sessions" / module.SESSIONS_INDEX_JSON).read_text(encoding="utf-8"))
    sessions_index_md = (aoa_root / "sessions" / module.SESSIONS_INDEX_MARKDOWN).read_text(encoding="utf-8")

    assert payload["ok"] is True
    assert phase_payload["ok"] is True
    assert payload["status"] == "applied"
    assert session_dir.exists()
    assert manifest["display"]["label"] == "2026-05-18__001__continue-the-work"
    assert manifest["raw"]["sha256"] == raw_sha
    assert manifest["semantic_names"]["active_session"] == "aoa-techniques-continuation"
    assert manifest["semantic_names"]["active"] == "aoa-techniques-final-residual-promotion-pass"
    assert semantic["scope"] == "session"
    assert phase["scope"] == "phase"
    assert semantic["anchor"]["session_id"] == "semantic-name-session"
    assert semantic["anchor"]["canonical_label"] == "2026-05-18__001__continue-the-work"
    assert semantic["anchor"]["raw_sha256"] == raw_sha
    assert semantic["evidence"] == ["raw:line:2", "raw:line:3"]
    assert phase["evidence"] == ["raw:line:3"]
    assert phase["coverage"]["raw_ranges"] == [{"from_line": 3, "to_line": 4}]
    assert registry_record["session_id"] == "semantic-name-session"
    assert phase_record["session_id"] == "semantic-name-session"
    assert "Session Name Anchor" in packet
    assert "Phase And Topic Names" in packet
    assert "raw:line:3" in packet
    assert "semantic_active_session" in session_md
    assert name_index["named_session_count"] == 1
    assert "aoa-techniques-final-residual-promotion-pass" in name_index["slug_index"]
    assert "aoa-techniques-continuation" in name_index_md
    assert sessions_index["artifact_type"] == "sessions_directory_index"
    assert sessions_index["session_count"] == 1
    assert sessions_index["named_session_count"] == 1
    assert sessions_index["sessions"][0]["entry"] == "2026-05-18__001__continue-the-work/SESSION.md"
    assert "aoa-techniques-continuation" in sessions_index_md
    assert "aoa-techniques-final-residual-promotion-pass" in sessions_index_md
    assert "2026-05-18__001__continue-the-work/SESSION.md" in sessions_index_md


def test_deferred_mirror_preserves_semantic_name_verified_anchor(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-18T00-00-00-anchor-preserve.jsonl"
    rows = [
        {"timestamp": "2026-05-18T00:00:00Z", "type": "session_meta", "payload": {"id": "anchor-preserve", "cwd": str(workspace)}},
        {"timestamp": "2026-05-18T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Preserve the semantic naming bridge"}]}},
        {"timestamp": "2026-05-18T00:00:02Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Use verified raw anchors."}]}},
    ]
    write_jsonl(transcript, rows)
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "anchor-preserve",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    session_dir = aoa_root / "sessions" / "2026-05-18__001__preserve-the-semantic-naming-bridge"
    manifest = json.loads((session_dir / "session.manifest.json").read_text(encoding="utf-8"))
    raw_sha = manifest["raw"]["sha256"]
    raw_line_count = manifest["raw"]["line_count"]
    module.set_session_semantic_name(
        aoa_root=aoa_root,
        target="anchor-preserve",
        name="semantic naming bridge preservation",
        scope="session",
        evidence_refs=["raw:line:2"],
        from_line=1,
        to_line=raw_line_count,
        coverage_note="Initial named raw snapshot.",
        apply=True,
        verify_raw_hash=True,
    )

    write_jsonl(
        transcript,
        rows
        + [
            {
                "timestamp": "2026-05-18T00:00:03Z",
                "type": "response_item",
                "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "The session continued after naming."}]},
            }
        ],
    )
    module.mirror_transcript_without_indexing(
        aoa_root=aoa_root,
        event={"session_id": "anchor-preserve", "transcript_path": str(transcript), "cwd": str(workspace)},
        transcript_path=transcript,
        hook_event_name="PreCompact",
        now="2026-05-18T00:01:00Z",
    )

    deferred_manifest = json.loads((session_dir / "session.manifest.json").read_text(encoding="utf-8"))
    semantic = deferred_manifest["semantic_names"]["names"][0]
    anchor = semantic["anchor"]
    readiness = module.session_naming_readiness(aoa_root, session_dir, deferred_manifest)

    assert deferred_manifest["archive_status"] == "raw_mirrored_index_deferred"
    assert deferred_manifest["raw"]["sha256"] is None
    assert deferred_manifest["raw"]["line_count"] is None
    assert anchor["raw_sha256"] == raw_sha
    assert anchor["raw_line_count"] == raw_line_count
    assert anchor["raw_anchor_status"] == "deferred_refresh_preserved_verified_anchor"
    assert readiness["status"] == "needs_reindex"
    assert readiness["evidence"]["observed_raw_line_count"] == raw_line_count + 1
    assert readiness["evidence"]["raw_line_count_source"] == "raw_probe_deferred"
    assert f"active_session_name_coverage_stale:{raw_line_count}<{raw_line_count + 1}" in readiness["warnings"]

    write_jsonl(
        transcript,
        rows
        + [
            {
                "timestamp": "2026-05-18T00:00:03Z",
                "type": "response_item",
                "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "The session continued after naming."}]},
            },
            {
                "timestamp": "2026-05-18T00:00:04Z",
                "type": "response_item",
                "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Source is now ahead of the archive."}]},
            },
        ],
    )
    source_ahead_readiness = module.session_naming_readiness(aoa_root, session_dir, deferred_manifest)

    assert source_ahead_readiness["status"] == "needs_sync"
    assert source_ahead_readiness["route"] == "sync_source_transcript_before_naming"
    assert "source_transcript_newer_than_raw_archive" in source_ahead_readiness["reasons"]
    assert source_ahead_readiness["evidence"]["source_transcript_newer_than_raw_archive"] is True


def test_replacing_active_session_name_does_not_create_implicit_alias(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-18T00-00-00-no-alias.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-18T00:00:00Z", "type": "session_meta", "payload": {"id": "no-implicit-alias", "cwd": str(workspace)}},
            {"timestamp": "2026-05-18T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Name the whole session correctly"}]}},
            {"timestamp": "2026-05-18T00:00:02Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "First name is too narrow."}]}},
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "no-implicit-alias",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    first = module.set_session_semantic_name(
        aoa_root=aoa_root,
        target="no-implicit-alias",
        name="narrow session name",
        scope="session",
        evidence_refs=["raw:line:2"],
        from_line=1,
        to_line=2,
        apply=True,
        verify_raw_hash=True,
    )
    second = module.set_session_semantic_name(
        aoa_root=aoa_root,
        target="no-implicit-alias",
        name="correct session name",
        scope="session",
        evidence_refs=["raw:line:2", "raw:line:3"],
        from_line=1,
        to_line=3,
        apply=True,
        verify_raw_hash=True,
    )

    session_dir = aoa_root / "sessions" / "2026-05-18__001__name-the-whole-session-correctly"
    manifest = json.loads((session_dir / "session.manifest.json").read_text(encoding="utf-8"))
    names = manifest["semantic_names"]["names"]
    name_index = json.loads((aoa_root / module.SESSION_NAME_INDEX_JSON).read_text(encoding="utf-8"))

    assert first["status"] == "applied"
    assert second["status"] == "applied"
    assert manifest["semantic_names"]["active_session"] == "correct-session-name"
    assert [item["slug"] for item in names if item["scope"] == "session"] == ["correct-session-name"]
    assert not any(item.get("status") == "alias" for item in names)
    assert "narrow-session-name" not in name_index["slug_index"]


def test_naming_readiness_routes_before_bulk_renaming(tmp_path: Path) -> None:
    aoa_root = tmp_path / ".aoa"

    def add_manifest(
        label: str,
        title: str,
        *,
        session_id: str,
        status: str,
        segment_count: int,
        event_count: int,
        title_source: str = "first_user_message",
        with_transcript_hint: bool | None = None,
    ) -> None:
        session_dir = aoa_root / "sessions" / label
        raw_path = session_dir / "raw" / "session.raw.jsonl"
        segment_dir = session_dir / "segments"
        if with_transcript_hint is None:
            with_transcript_hint = status != "raw_unavailable"
        source_transcript_path = str(tmp_path / f"{session_id}.jsonl") if with_transcript_hint else None
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        segment_dir.mkdir(parents=True, exist_ok=True)
        if status != "raw_unavailable":
            raw_path.write_text("\n".join("{}" for _ in range(max(event_count, 1))) + "\n", encoding="utf-8")
        segments = []
        for index in range(segment_count):
            stem = f"{index:03}__initial-to-latest"
            md_path = segment_dir / f"{stem}.md"
            index_path = segment_dir / f"{stem}.index.json"
            md_path.write_text("# segment\n", encoding="utf-8")
            index_path.write_text('{"events":[]}\n', encoding="utf-8")
            segments.append(
                {
                    "segment_id": f"{index:03}",
                    "role": "initial-to-latest",
                    "markdown": str(md_path),
                    "index": str(index_path),
                    "event_count": 1,
                    "source_range": {"from_line": index + 1, "to_line": index + 1},
                }
            )
        manifest = {
            "schema_version": 1,
            "session_id": session_id,
            "display": {
                "date": label[:10],
                "sequence": 1,
                "title": title,
                "title_source": title_source,
                "label": label,
                "path": str(session_dir),
                "archive_path": str(session_dir),
                "navigation_path": str(session_dir),
            },
            "session_label": label,
            "session_title": title,
            "created_at": "2026-05-20T00:00:00Z",
            "updated_at": "2026-05-20T00:00:00Z",
            "source": {"cwd": str(tmp_path), "transcript_path": source_transcript_path},
            "archive_status": status,
            "distillation_status": "first_pass_distilled",
            "raw": {
                "path": str(raw_path),
                "bytes": raw_path.stat().st_size if raw_path.exists() else 0,
                "sha256": "sha256-fixture" if raw_path.exists() else None,
                "line_count": event_count if raw_path.exists() else None,
            },
            "segments": segments,
            "latest_event_count": event_count,
        }
        (session_dir / "session.manifest.json").write_text(json.dumps(manifest, ensure_ascii=False) + "\n", encoding="utf-8")
        module.update_registry(aoa_root, manifest, session_dir)

    add_manifest(
        "2026-05-20__001__large-real-work",
        "Large real work",
        session_id="large-real-work",
        status="indexed",
        segment_count=25,
        event_count=2500,
    )
    add_manifest(
        "2026-05-20__002__codex-in-abyssos",
        "Codex in AbyssOS",
        session_id="weak-cwd-title",
        status="indexed",
        segment_count=3,
        event_count=300,
        title_source="cwd",
    )
    add_manifest(
        "2026-05-20__003__missing-raw",
        "Codex in memories",
        session_id="missing-raw",
        status="raw_unavailable",
        segment_count=0,
        event_count=0,
        title_source="cwd",
    )
    add_manifest(
        "2026-05-20__004__missing-raw-with-path",
        "Codex in memories",
        session_id="missing-raw-with-path",
        status="raw_unavailable",
        segment_count=0,
        event_count=0,
        title_source="cwd",
        with_transcript_hint=True,
    )
    add_manifest(
        "2026-05-20__005__deferred-index",
        "Deferred index",
        session_id="deferred-index",
        status="raw_mirrored_index_deferred",
        segment_count=2,
        event_count=200,
    )
    add_manifest(
        "2026-05-20__006__named-with-open-phase-queue",
        "Named with open phase queue",
        session_id="named-open-phase-queue",
        status="indexed",
        segment_count=25,
        event_count=2500,
    )
    named_session_dir = aoa_root / "sessions" / "2026-05-20__006__named-with-open-phase-queue"
    named_manifest_path = named_session_dir / "session.manifest.json"
    named_manifest = json.loads(named_manifest_path.read_text(encoding="utf-8"))
    named_manifest["semantic_names"] = {
        "schema_version": 1,
        "active": "named-open-phase-queue",
        "active_session": "named-open-phase-queue",
        "names": [
            {
                "schema_version": 1,
                "name": "Named open phase queue",
                "slug": "named-open-phase-queue",
                "scope": "session",
                "kind": "session_essence",
                "status": "active",
                "coverage": {"raw_ranges": [{"from_line": 1, "to_line": 2500}]},
            }
        ],
    }
    named_manifest_path.write_text(json.dumps(named_manifest, ensure_ascii=False) + "\n", encoding="utf-8")
    module.update_registry(aoa_root, named_manifest, named_session_dir)
    named_phase_dir = named_session_dir / "naming"
    named_phase_dir.mkdir(parents=True, exist_ok=True)
    (named_phase_dir / "phase-discovery.json").write_text(
        json.dumps(
            {
                "artifact_type": "session_phase_discovery",
                "session_dir": str(named_session_dir),
                "raw_path": str(named_session_dir / "raw" / "session.raw.jsonl"),
                "candidate_count": 3,
                "review_queue_count": 2,
                "candidates": [
                    {
                        "segment_id": "000",
                        "name": "raw validation",
                        "slug": "raw-validation",
                        "confidence": "low",
                        "name_basis": "linked_path_event_signals",
                        "quality_flags": ["no_specific_user_intent"],
                        "coverage": {"raw_ranges": [{"from_line": 1, "to_line": 10}]},
                        "evidence": ["raw:line:1"],
                        "review": {"status": "needs_semantic_synthesis"},
                    },
                    {
                        "segment_id": "001",
                        "name": "docs implementation",
                        "slug": "docs-implementation",
                        "confidence": "low",
                        "name_basis": "linked_path_event_signals",
                        "quality_flags": ["no_specific_user_intent"],
                        "coverage": {"raw_ranges": [{"from_line": 11, "to_line": 20}]},
                        "evidence": ["raw:line:11"],
                        "review": {"status": "needs_semantic_synthesis"},
                    },
                    {
                        "segment_id": "002",
                        "name": "ready phase",
                        "slug": "ready-phase",
                        "confidence": "high",
                        "name_basis": "specific_user_intent",
                        "quality_flags": [],
                        "coverage": {"raw_ranges": [{"from_line": 21, "to_line": 30}]},
                        "evidence": ["raw:line:21"],
                        "review": {"status": "ready_for_raw_check"},
                    },
                ],
                "review_queue": [
                    {"segment_id": "000", "name": "raw validation", "review": {"status": "needs_semantic_synthesis"}},
                    {"segment_id": "001", "name": "docs implementation", "review": {"status": "needs_semantic_synthesis"}},
                ],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    payload = module.build_naming_readiness_report(aoa_root, refresh_indexes=True)
    by_label = {item["session_label"]: item["naming_readiness"] for item in payload["results"]}
    name_index = json.loads((aoa_root / module.SESSION_NAME_INDEX_JSON).read_text(encoding="utf-8"))
    sessions_index_md = (aoa_root / "sessions" / module.SESSIONS_INDEX_MARKDOWN).read_text(encoding="utf-8")

    assert by_label["2026-05-20__001__large-real-work"]["status"] == "needs_phase_discovery"
    assert by_label["2026-05-20__001__large-real-work"]["route"] == "phase_topic_discovery_before_session_name"
    assert by_label["2026-05-20__002__codex-in-abyssos"]["status"] == "ready_for_semantic_name"
    assert by_label["2026-05-20__002__codex-in-abyssos"]["route"] == "direct_semantic_name_from_index_and_raw_refs"
    assert by_label["2026-05-20__003__missing-raw"]["status"] == "diagnostic_only"
    assert by_label["2026-05-20__003__missing-raw"]["route"] == "leave_raw_unavailable_diagnostic"
    assert by_label["2026-05-20__004__missing-raw-with-path"]["status"] == "blocked"
    assert by_label["2026-05-20__004__missing-raw-with-path"]["route"] == "recover_raw_before_naming"
    assert by_label["2026-05-20__005__deferred-index"]["status"] == "needs_reindex"
    assert by_label["2026-05-20__005__deferred-index"]["route"] == "reindex_before_naming"
    assert by_label["2026-05-20__006__named-with-open-phase-queue"]["status"] == "named"
    assert by_label["2026-05-20__006__named-with-open-phase-queue"]["route"] == "review_open_phase_discovery_for_named_session"
    assert by_label["2026-05-20__006__named-with-open-phase-queue"]["priority"] > 0
    assert "phase_discovery_review_queue_open" in by_label["2026-05-20__006__named-with-open-phase-queue"]["reasons"]
    assert "phase_discovery_review_queue_open:2" in by_label["2026-05-20__006__named-with-open-phase-queue"]["warnings"]
    assert by_label["2026-05-20__006__named-with-open-phase-queue"]["evidence"]["phase_discovery_review_queue_count"] == 2
    assert by_label["2026-05-20__006__named-with-open-phase-queue"]["evidence"]["phase_discovery_review_queue_sample"][0]["name"] == "raw validation"
    assert name_index["naming_readiness_counts"]["by_status"]["needs_phase_discovery"] == 1
    assert name_index["naming_readiness_counts"]["by_status"]["ready_for_semantic_name"] == 1
    assert name_index["naming_readiness_counts"]["by_status"]["diagnostic_only"] == 1
    assert name_index["naming_readiness_counts"]["by_status"]["blocked"] == 1
    assert name_index["naming_readiness_counts"]["by_status"]["needs_reindex"] == 1
    assert name_index["naming_readiness_counts"]["by_status"]["named"] == 1
    assert "Naming Work Queue" in sessions_index_md
    assert "phase_topic_discovery_before_session_name" in sessions_index_md
    assert "review_open_phase_discovery_for_named_session" in sessions_index_md

    applied = module.review_phase_name_candidate(
        aoa_root,
        "2026-05-20__006__named-with-open-phase-queue",
        "000",
        reviewed_name="Raw route review",
        apply=True,
    )
    assert applied["status"] == "applied"
    updated_phase_discovery = json.loads((named_phase_dir / "phase-discovery.json").read_text(encoding="utf-8"))
    assert updated_phase_discovery["candidates"][0]["review"]["status"] == "applied_reviewed_name"
    assert updated_phase_discovery["candidates"][0]["review"]["applied_name"] == "Raw route review"
    assert updated_phase_discovery["review_queue_count"] == 1
    assert updated_phase_discovery["review_queue"][0]["segment_id"] == "001"


def test_phase_discovery_writes_open_candidates_and_updates_readiness(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-21T00-00-00-phase-discovery.jsonl"
    rows: list[dict[str, object]] = [
        {"timestamp": "2026-05-21T00:00:00Z", "type": "session_meta", "payload": {"id": "phase-discovery", "cwd": str(workspace)}},
        {
            "timestamp": "2026-05-21T00:00:01Z",
            "type": "response_item",
            "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Repair session naming layers in .aoa"}]},
        },
        {
            "timestamp": "2026-05-21T00:00:02Z",
            "type": "response_item",
            "payload": {"type": "function_call", "name": "exec_command", "call_id": "call-rg", "arguments": json.dumps({"cmd": "rg -n naming .aoa/NAMING.md"})},
        },
        {
            "timestamp": "2026-05-21T00:00:03Z",
            "type": "response_item",
            "payload": {"type": "function_call_output", "call_id": "call-rg", "output": "NAMING.md:1:naming\nProcess exited with code 0"},
        },
    ]
    for index in range(4, 23):
        rows.append(
            {
                "timestamp": f"2026-05-21T00:00:{index:02d}Z",
                "type": "response_item",
                "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": f"Checkpoint {index}"}]},
            }
        )
    rows.extend(
        [
            {"timestamp": "2026-05-21T00:00:23Z", "type": "turn_context", "payload": {"summary": "context compacted after naming layer work"}},
            {
                "timestamp": "2026-05-21T00:00:24Z",
                "type": "response_item",
                "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Continue phase naming from raw anchors"}]},
            },
            {
                "timestamp": "2026-05-21T00:00:25Z",
                "type": "response_item",
                "payload": {"type": "function_call", "name": "apply_patch", "call_id": "call-patch"},
            },
            {
                "timestamp": "2026-05-21T00:00:26Z",
                "type": "response_item",
                "payload": {"type": "function_call_output", "call_id": "call-patch", "output": "Success. Updated the following files:\nM .aoa/NAMING.md"},
            },
        ]
    )
    write_jsonl(transcript, rows)

    module.handle_hook_event(
        "Stop",
        {
            "session_id": "phase-discovery",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    payload = module.discover_session_phases(aoa_root, "phase-discovery", write=True)
    assert payload["candidate_count"] == 2
    assert payload["candidates"][0]["status"] == "candidate_unreviewed"
    assert payload["candidates"][0]["evidence"][0].startswith("raw:line:")
    assert payload["candidates"][0]["name_basis"] == "specific_user_intent"
    assert payload["candidates"][0]["linked_signals"]["support_event_types"]["USER_INTENT"] == 1
    assert payload["candidates"][0]["review"]["status"] == "ready_for_raw_check"
    assert payload["review_queue_count"] == 0
    assert payload["candidate_quality_counts"]["by_review_status"]["ready_for_raw_check"] == 2
    assert (Path(payload["artifact_json"])).exists()
    assert (Path(payload["artifact_markdown"])).exists()

    readiness = module.build_naming_readiness_report(aoa_root, target="phase-discovery")
    item = readiness["results"][0]["naming_readiness"]
    assert item["status"] == "phase_discovery_ready"
    assert item["route"] == "review_phase_discovery_before_session_name"

    preview = module.review_phase_name_candidate(aoa_root, "phase-discovery", "000")
    assert preview["ok"]
    assert preview["status"] == "ready_for_raw_check"
    assert preview["raw_samples"]
    assert "--use-candidate --apply --write-report" in preview["next_command"]

    applied = module.review_phase_name_candidate(
        aoa_root,
        "phase-discovery",
        "000",
        reviewed_name="Naming layer repair",
        apply=True,
        write_report=True,
    )
    manifest = json.loads(next((aoa_root / "sessions").glob("*/session.manifest.json")).read_text(encoding="utf-8"))
    phase_names = [
        item
        for item in manifest["semantic_names"]["names"]
        if item["scope"] == "phase" and item["name"] == "Naming layer repair"
    ]
    assert applied["status"] == "applied"
    assert applied["semantic_name_result"]["status"] == "applied"
    assert phase_names
    assert (aoa_root / module.SESSION_NAME_INDEX_JSON).exists()
    assert (aoa_root / "sessions" / module.SESSIONS_INDEX_JSON).exists()
    assert Path(applied["report_json"]).exists()
    assert Path(applied["report_markdown"]).exists()

    phase_artifact = Path(payload["artifact_json"])
    weak_payload = json.loads(phase_artifact.read_text(encoding="utf-8"))
    weak_payload["candidates"][0]["name"] = ".aoa validation"
    weak_payload["candidates"][0]["review"]["status"] = "needs_semantic_synthesis"
    phase_artifact.write_text(json.dumps(weak_payload, ensure_ascii=False) + "\n", encoding="utf-8")
    rejected = module.review_phase_name_candidate(aoa_root, "phase-discovery", "000", use_candidate=True, apply=True)
    assert not rejected["ok"]
    assert "weak_candidate_requires_reviewed_name" in rejected["diagnostics"]

    assist = module.build_phase_review_assist(
        aoa_root,
        "phase-discovery",
        limit=2,
        from_segment="000",
        write=True,
        write_report=True,
    )
    assert assist["ok"]
    assert assist["selected_count"] == 2
    assert assist["packets"][0]["segment_id"] == "000"
    assert assist["packets"][0]["existing_phase_name"] == "Naming layer repair"
    assert assist["packets"][0]["read_first"]
    assert (
        assist["packets"][0]["synthesis_inputs"]["progress_markers"]
        or assist["packets"][0]["synthesis_inputs"]["decisions_and_closeout"]
        or assist["packets"][0]["synthesis_inputs"]["commands"]
    )
    assert assist["plan_template"]["items"][0]["segment_id"] == "000"
    assert Path(assist["artifact_json"]).exists()
    assert Path(assist["artifact_markdown"]).exists()
    assert Path(assist["plan_template_path"]).exists()
    assist_markdown = Path(assist["artifact_markdown"]).read_text(encoding="utf-8")
    assert "## Fast Queue" in assist_markdown
    assert "#### Commands" in assist_markdown or "#### Decisions And Closeout" in assist_markdown

    plan = assist["plan_template"]
    plan["items"][0]["reviewed_name"] = ""
    plan["items"][1]["reviewed_name"] = "Plan applied phase name"
    plan_path = Path(assist["plan_template_path"]).with_name("phase-review-plan.json")
    plan_path.write_text(json.dumps(plan, ensure_ascii=False) + "\n", encoding="utf-8")

    preview_plan = module.apply_phase_review_plan(aoa_root, "phase-discovery", plan_path=plan_path)
    assert preview_plan["ok"]
    assert preview_plan["status"] == "preview_ready"
    assert preview_plan["preview_count"] == 1
    assert preview_plan["skipped_count"] == 1

    applied_plan = module.apply_phase_review_plan(
        aoa_root,
        "phase-discovery",
        plan_path=plan_path,
        apply=True,
        write_report=True,
    )
    assert applied_plan["ok"]
    assert applied_plan["status"] == "applied"
    assert applied_plan["applied_count"] == 1
    assert applied_plan["skipped_count"] == 1
    assert Path(applied_plan["report_json"]).exists()
    assert Path(applied_plan["report_markdown"]).exists()
    manifest = json.loads(next((aoa_root / "sessions").glob("*/session.manifest.json")).read_text(encoding="utf-8"))
    assert any(
        item["scope"] == "phase" and item["name"] == "Plan applied phase name"
        for item in manifest["semantic_names"]["names"]
    )


def test_semantic_session_name_rejects_unanchored_out_of_range_evidence(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-18T00-00-00-bad-semantic-name.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-18T00:00:00Z", "type": "session_meta", "payload": {"id": "bad-semantic-name", "cwd": str(workspace)}},
            {"timestamp": "2026-05-18T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Short session"}]}},
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "bad-semantic-name",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    payload = module.set_session_semantic_name(
        aoa_root=aoa_root,
        target="short-session",
        name="aoa-techniques final residual promotion pass",
        evidence_refs=["raw:line:99"],
        apply=True,
    )
    session_dir = aoa_root / "sessions" / "2026-05-18__001__short-session"
    manifest = json.loads((session_dir / "session.manifest.json").read_text(encoding="utf-8"))

    assert payload["ok"] is False
    assert payload["status"] == "diagnostic"
    assert any("semantic_name_evidence_out_of_range" in item for item in payload["diagnostics"])
    assert "semantic_names" not in manifest


def test_registry_update_recovers_from_invalid_registry_when_manifests_exist(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    for session_id, title in [("registry-a", "First recovery session"), ("registry-b", "Second recovery session")]:
        transcript = tmp_path / f"{session_id}.jsonl"
        write_jsonl(
            transcript,
            [
                {"timestamp": "2026-05-19T00:00:00Z", "type": "session_meta", "payload": {"id": session_id, "cwd": str(workspace)}},
                {"timestamp": "2026-05-19T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": title}]}},
            ],
        )
        module.handle_hook_event(
            "Stop",
            {
                "session_id": session_id,
                "transcript_path": str(transcript),
                "cwd": str(workspace),
                "hook_event_name": "Stop",
            },
            workspace_root=workspace,
            aoa_root=aoa_root,
        )

    registry_path = aoa_root / module.REGISTRY_NAME
    registry_path.write_text('{"sessions":[]}\n{"broken":true}\n', encoding="utf-8")
    session_dir = aoa_root / "sessions" / "2026-05-19__001__first-recovery-session"
    manifest = json.loads((session_dir / "session.manifest.json").read_text(encoding="utf-8"))
    module.update_registry(aoa_root, manifest, session_dir)

    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    name_index = json.loads((aoa_root / module.SESSION_NAME_INDEX_JSON).read_text(encoding="utf-8"))
    sessions_index = json.loads((aoa_root / "sessions" / module.SESSIONS_INDEX_JSON).read_text(encoding="utf-8"))
    assert len(registry["sessions"]) == 2
    assert name_index["session_count"] == 2
    assert sessions_index["session_count"] == 2


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
