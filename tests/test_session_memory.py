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
        "compaction-to-compaction",
        "compaction-to-latest",
    ]
    first_index = json.loads(Path(manifest["segments"][0]["index"]).read_text(encoding="utf-8"))
    second_index = json.loads(Path(manifest["segments"][1]["index"]).read_text(encoding="utf-8"))
    assert "COMPACTION_EVENT" in first_index["by_type"]
    assert "COMPACTION_EVENT" in second_index["by_type"]


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
    assert statuses["Live PreCompact and PostCompact hook receipts observed in archived sessions"] == "remaining"


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
