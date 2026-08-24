from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "aoa_session_memory.py"
SPEC = importlib.util.spec_from_file_location("aoa_session_memory_goal_thread_board_test", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "goal_thread_board"
GOAL_REF = "thread:fixture-master"
MASTER_THREAD_ID = "thread:fixture-master"


def schema() -> dict[str, Any]:
    return json.loads(
        (REPO_ROOT / "schemas" / "goal.thread.board.schema.json").read_text(
            encoding="utf-8"
        )
    )


def owner_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def create_goal_source(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    repo = workspace / "owner-repo"
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "AGENTS.md").write_text("# fixture owner\n", encoding="utf-8")
    aoa_root = workspace / ".aoa"
    session_id = "session-fixture"
    transcript = tmp_path / f"{session_id}.jsonl"
    write_jsonl(
        transcript,
        [
            {
                "timestamp": "2026-08-23T10:00:00Z",
                "type": "session_meta",
                "payload": {"id": session_id, "cwd": str(repo)},
            },
            {
                "timestamp": "2026-08-23T10:00:01Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "create_goal",
                    "call_id": "create-fixture",
                    "arguments": json.dumps({"objective": "PRIVATE_INDEX_OBJECTIVE"}),
                },
            },
            {
                "timestamp": "2026-08-23T10:00:02Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "create-fixture",
                    "output": json.dumps(
                        {
                            "goal": {
                                "threadId": GOAL_REF,
                                "status": "active",
                                "createdAt": 1720000000,
                                "updatedAt": 1720000010,
                            }
                        }
                    ),
                },
            },
            {
                "timestamp": "2026-08-23T10:00:03Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "update_goal",
                    "call_id": "update-fixture",
                    "arguments": json.dumps({"status": "active"}),
                },
            },
        ],
    )
    MODULE.handle_hook_event(
        "Stop",
        {
            "session_id": session_id,
            "transcript_path": str(transcript),
            "cwd": str(repo),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )
    registry = json.loads((aoa_root / MODULE.REGISTRY_NAME).read_text(encoding="utf-8"))
    session_dir = Path(str(registry["sessions"][0]["path"]))
    index_path = session_dir / MODULE.SESSION_INDEX_JSON
    index = json.loads(index_path.read_text(encoding="utf-8"))
    for lifecycle in index.get("goal_lifecycles", []):
        if isinstance(lifecycle, dict):
            observed = lifecycle.setdefault("observed_goal", {})
            if isinstance(observed, dict):
                observed["threadId"] = GOAL_REF
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return aoa_root


def assert_public_safe(payload: dict[str, Any]) -> None:
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    for secret in (
        "PRIVATE_OBJECTIVE",
        "PRIVATE_PROMPT",
        "PRIVATE_TRANSCRIPT",
        "PRIVATE_COMMAND",
        "PRIVATE_OUTPUT",
        "PRIVATE_PREVIEW",
        "/private/",
        "private-pid",
    ):
        assert secret not in rendered
    forbidden_keys = {
        "content",
        "text",
        "command",
        "aggregatedOutput",
        "cwd",
        "path",
        "preview",
        "prompt",
        "arguments",
        "result",
        "error",
        "processId",
        "sessionId",
        "modelProvider",
    }

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            if "item_ref" in value or "relation_ref" in value:
                assert not forbidden_keys.intersection(value)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(payload)


def validate(payload: dict[str, Any]) -> None:
    Draft202012Validator(schema()).validate(payload)


def test_bound_board_is_exact_public_safe_and_paginated(tmp_path: Path) -> None:
    aoa_root = create_goal_source(tmp_path)
    owner = owner_fixture("owner_observation_bound.json")
    first = MODULE.goal_thread_board_publication(
        aoa_root=aoa_root,
        goal_ref=GOAL_REF,
        master_thread_id=MASTER_THREAD_ID,
        page_size=1,
        owner_observation=owner,
    )
    assert first["ok"] is True
    assert first["state"] == "current"
    assert first["goal_ref"] == GOAL_REF
    assert first["master_thread_id"] == MASTER_THREAD_ID
    assert first["pagination"]["supports_immutable_snapshot"] is True
    assert first["pagination"]["next_cursor"]
    assert first["branch"]["state"] == "missing"
    assert first["ordering"]["event_ordering"]["state"] == "missing"
    assert any(item["item_kind"] == "codex_thread_item_observation" for item in first["items"])
    assert first["relations"][0]["relation_kind"] == "spawn_parent"
    validate(first)
    assert_public_safe(first)

    second = MODULE.goal_thread_board_publication(
        aoa_root=aoa_root,
        goal_ref=GOAL_REF,
        master_thread_id=MASTER_THREAD_ID,
        page_size=1,
        cursor=first["pagination"]["next_cursor"],
        owner_observation=owner,
    )
    assert second["ok"] is True
    assert second["snapshot_digest"] == first["snapshot_digest"]
    assert second["items"][0]["item_ref"] != first["items"][0]["item_ref"]
    validate(second)
    assert_public_safe(second)


def test_owner_page_cursor_and_missing_branch_are_preserved(tmp_path: Path) -> None:
    aoa_root = create_goal_source(tmp_path)
    payload = MODULE.goal_thread_board_publication(
        aoa_root=aoa_root,
        goal_ref=GOAL_REF,
        master_thread_id=MASTER_THREAD_ID,
        owner_observation=owner_fixture("owner_observation_deferred.json"),
    )
    assert payload["ok"] is True
    assert payload["pagination"]["owner_next_cursor"] == "owner-cursor-2"
    assert payload["pagination"]["complete_for_query"] is False
    assert payload["pagination"]["owner_page_complete"] is False
    assert "codex_owner_items_page_deferred" in payload["diagnostics"]
    assert payload["relation_state"] == "deferred"
    assert payload["branch"]["branch_ref"] is None
    validate(payload)
    assert_public_safe(payload)


def test_app_server_item_envelope_is_unwrapped_without_leaking_turn_or_body() -> None:
    owner = owner_fixture("owner_observation_bound.json")
    direct_item = owner["items"]["data"][0]
    owner["items"]["data"] = [
        {
            "turnId": "turn:private-correlation",
            "item": direct_item,
        }
    ]

    projection = MODULE.goal_thread_board_public_owner_projection(
        owner,
        goal_ref=GOAL_REF,
        master_thread_id=MASTER_THREAD_ID,
    )

    assert projection["state"] == "bound"
    assert projection["pagination"]["complete_for_query"] is True
    assert [item["item_id"] for item in projection["items"]] == ["item:fixture-user"]
    assert projection["items"][0]["owner_item_type"] == "userMessage"
    assert projection["items"][0]["body_state"] == "withheld"
    assert "owner_item_identity_missing" not in projection["diagnostics"]
    assert "owner_relation_child_identity_missing" not in projection["diagnostics"]
    assert "turn:private-correlation" not in json.dumps(projection)
    assert_public_safe(projection)


def test_exact_binding_mismatch_is_invalid_and_does_not_leak_foreign_data(tmp_path: Path) -> None:
    aoa_root = create_goal_source(tmp_path)
    payload = MODULE.goal_thread_board_publication(
        aoa_root=aoa_root,
        goal_ref=GOAL_REF,
        master_thread_id="thread:other-master",
        owner_observation=owner_fixture("owner_observation_mismatch.json"),
    )
    assert payload["ok"] is False
    assert payload["state"] == "invalid"
    assert payload["items"] == []
    assert "goal_thread_board_exact_binding_mismatch" in payload["diagnostics"]
    validate(payload)
    assert_public_safe(payload)


def test_invalid_owner_status_is_kept_separate_from_safe_index_items(tmp_path: Path) -> None:
    aoa_root = create_goal_source(tmp_path)
    payload = MODULE.goal_thread_board_publication(
        aoa_root=aoa_root,
        goal_ref=GOAL_REF,
        master_thread_id=MASTER_THREAD_ID,
        owner_observation=owner_fixture("owner_observation_invalid.json"),
    )
    assert payload["ok"] is True
    assert payload["owner_read"]["state"] == "invalid"
    assert "codex_owner_goal_status_invalid" in payload["diagnostics"]
    assert all(item["source_ref"] != "codex-app-server:thread/items/list" for item in payload["items"])
    validate(payload)
    assert_public_safe(payload)


def test_unknown_owner_items_keep_state_explicit_and_do_not_leak_error(tmp_path: Path) -> None:
    aoa_root = create_goal_source(tmp_path)
    payload = MODULE.goal_thread_board_publication(
        aoa_root=aoa_root,
        goal_ref=GOAL_REF,
        master_thread_id=MASTER_THREAD_ID,
        owner_observation=owner_fixture("owner_observation_items_unknown.json"),
    )
    assert payload["ok"] is True
    assert payload["owner_read"]["state"] == "unknown"
    assert payload["pagination"]["owner_page_complete"] is False
    assert "codex_owner_items_unknown" in payload["diagnostics"]
    assert "PRIVATE_OWNER_ERROR_DETAIL" not in json.dumps(payload)
    validate(payload)
    assert_public_safe(payload)


def test_source_diagnostic_suffixes_are_not_public_join_keys() -> None:
    assert MODULE.goal_thread_board_public_source_diagnostics(
        ["session_index_stale:private-session:/private/raw/path"]
    ) == ["session_index_stale"]


def test_owner_method_allowlist_drops_private_method_names(tmp_path: Path) -> None:
    aoa_root = create_goal_source(tmp_path)
    owner = owner_fixture("owner_observation_bound.json")
    owner["methods"] = ["thread/goal/get", "/private/owner-method"]
    payload = MODULE.goal_thread_board_publication(
        aoa_root=aoa_root,
        goal_ref=GOAL_REF,
        master_thread_id=MASTER_THREAD_ID,
        owner_observation=owner,
    )
    assert payload["owner_read"]["state"] == "invalid"
    assert "/private/owner-method" not in json.dumps(payload)
    validate(payload)
    assert_public_safe(payload)


def test_missing_and_unknown_owner_states_are_not_zero_or_success(tmp_path: Path) -> None:
    missing = MODULE.goal_thread_board_publication(
        aoa_root=tmp_path / "missing-aoa",
        goal_ref=GOAL_REF,
        master_thread_id=MASTER_THREAD_ID,
    )
    assert missing["ok"] is False
    assert missing["state"] == "missing"
    assert missing["items"] == []
    validate(missing)

    unknown = MODULE.goal_thread_board_publication(
        aoa_root=tmp_path / "missing-aoa",
        goal_ref=GOAL_REF,
        master_thread_id=MASTER_THREAD_ID,
        owner_observation={
            "owner": "codex-app-server",
            "currentness": "unknown",
            "methods": ["thread/goal/get"],
            "goal": None,
            "thread": None,
            "items": [],
            "relations": [],
        },
    )
    assert unknown["ok"] is False
    assert unknown["state"] == "unknown"
    assert unknown["items"] == []
    validate(unknown)


def test_arbitrary_binding_is_public_safe_and_not_complete_without_catalog(
    tmp_path: Path,
) -> None:
    raw_binding = "/private/goal-ref"
    owner = {
        "owner": "codex-app-server",
        "currentness": "current_at_read",
        "methods": ["thread/goal/get", "thread/read", "thread/items/list"],
        "goal": {"threadId": raw_binding, "status": "active"},
        "thread": {"id": raw_binding, "status": {"type": "idle"}},
        "items": [],
        "relations": [],
    }
    payload = MODULE.goal_thread_board_publication(
        aoa_root=tmp_path / "missing-aoa",
        goal_ref=raw_binding,
        master_thread_id=raw_binding,
        owner_observation=owner,
    )
    assert payload["ok"] is True
    assert payload["goal_ref"].startswith("opaque:")
    assert payload["goal_ref"] == payload["master_thread_id"]
    assert payload["pagination"]["complete_for_query"] is False
    assert raw_binding not in json.dumps(payload)
    validate(payload)


def test_unknown_owner_items_are_not_admitted_as_current(tmp_path: Path) -> None:
    payload = MODULE.goal_thread_board_publication(
        aoa_root=tmp_path / "missing-aoa",
        goal_ref=GOAL_REF,
        master_thread_id=MASTER_THREAD_ID,
        owner_observation={
            "owner": "codex-app-server",
            "currentness": "unknown",
            "methods": ["thread/goal/get", "thread/read", "thread/items/list"],
            "goal": {"threadId": GOAL_REF, "status": "active"},
            "thread": {"id": MASTER_THREAD_ID, "status": {"type": "idle"}},
            "items": [{"id": "item:unknown", "type": "plan"}],
            "relations": [],
        },
    )
    assert payload["ok"] is False
    assert payload["state"] == "unknown"
    assert payload["items"] == []
    validate(payload)


def test_board_retries_a_moving_catalog_source(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    aoa_root = create_goal_source(tmp_path)
    original_read = MODULE.goal_catalog_public_read_json
    calls = {"index": 0}

    def moving_read(path: Path) -> dict[str, Any]:
        result = original_read(path)
        if path.name == MODULE.SESSION_INDEX_JSON and calls["index"] == 0:
            calls["index"] += 1
            return {
                **result,
                "state": "deferred",
                "value": None,
                "digest": None,
                "stable": False,
                "diagnostic": "source_file_changed_during_read",
            }
        return result

    monkeypatch.setattr(MODULE, "goal_catalog_public_read_json", moving_read)
    payload = MODULE.goal_thread_board_publication(
        aoa_root=aoa_root,
        goal_ref=GOAL_REF,
        master_thread_id=MASTER_THREAD_ID,
        owner_observation=owner_fixture("owner_observation_bound.json"),
    )
    assert payload["ok"] is True
    assert calls["index"] == 1
    assert payload["snapshot"]["read_attempts"] == 2
    assert payload["snapshot"]["retry_exhausted"] is False
    validate(payload)


def test_stale_generated_index_does_not_render_as_current(tmp_path: Path) -> None:
    aoa_root = create_goal_source(tmp_path)
    registry = json.loads((aoa_root / MODULE.REGISTRY_NAME).read_text(encoding="utf-8"))
    session_dir = Path(str(registry["sessions"][0]["path"]))
    index_path = session_dir / MODULE.SESSION_INDEX_JSON
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index["generation_identity"] = {"generation_id": "fixture-incompatible"}
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    payload = MODULE.goal_thread_board_publication(
        aoa_root=aoa_root,
        goal_ref=GOAL_REF,
        master_thread_id=MASTER_THREAD_ID,
    )
    assert payload["ok"] is False
    assert payload["state"] == "stale"
    assert payload["items"] == []
    assert "session-fixture" not in json.dumps(payload)
    validate(payload)
