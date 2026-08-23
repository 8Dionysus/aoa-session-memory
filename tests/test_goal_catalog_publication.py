from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "aoa_session_memory.py"
SPEC = importlib.util.spec_from_file_location("aoa_session_memory_goal_catalog_test", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def public_catalog_schema() -> dict[str, Any]:
    return json.loads(
        (REPO_ROOT / "schemas" / "goal.catalog.schema.json").read_text(
            encoding="utf-8"
        )
    )


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def create_real_goal_session(
    tmp_path: Path,
    session_id: str,
    objective: str,
    *,
    complete: bool = False,
) -> Path:
    """Create an archive through the real hook/index owner route, not a catalog fixture."""
    workspace = tmp_path / "workspace"
    repo = workspace / "owner-repo"
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "AGENTS.md").write_text("# owner\n", encoding="utf-8")
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / f"{session_id}.jsonl"
    rows = [
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
                "call_id": f"create-{session_id}",
                "arguments": json.dumps({"objective": objective}),
            },
        },
        {
            "timestamp": "2026-08-23T10:00:02Z",
            "type": "response_item",
            "payload": {
                "type": "function_call_output",
                "call_id": f"create-{session_id}",
                "output": json.dumps({"goal": {"status": "active"}}),
            },
        },
    ]
    if complete:
        rows.extend(
            [
                {
                    "timestamp": "2026-08-23T10:00:03Z",
                    "type": "response_item",
                    "payload": {
                        "type": "function_call",
                        "name": "update_goal",
                        "call_id": f"complete-{session_id}",
                        "arguments": json.dumps({"status": "complete"}),
                    },
                },
                {
                    "timestamp": "2026-08-23T10:00:04Z",
                    "type": "response_item",
                    "payload": {
                        "type": "function_call_output",
                        "call_id": f"complete-{session_id}",
                        "output": json.dumps({"goal": {"status": "complete"}}),
                    },
                },
            ]
        )
    write_jsonl(transcript, rows)
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
    return aoa_root


def test_public_catalog_enumerates_two_real_current_goals_with_stable_pages(
    tmp_path: Path,
) -> None:
    aoa_root = create_real_goal_session(tmp_path / "one", "goal-source-one", "private objective one")
    second_root = create_real_goal_session(tmp_path / "two", "goal-source-two", "private objective two")
    # The two independent hook-produced roots are joined into one owner source
    # only for this bounded test corpus, preserving their generated indexes.
    first_registry = json.loads((aoa_root / MODULE.REGISTRY_NAME).read_text(encoding="utf-8"))
    second_registry = json.loads((second_root / MODULE.REGISTRY_NAME).read_text(encoding="utf-8"))
    first_registry["sessions"].extend(second_registry["sessions"])
    for session in second_registry["sessions"]:
        source = Path(str(session["path"]))
        destination = aoa_root / "sessions" / f"copy-{source.name}"
        destination.parent.mkdir(parents=True, exist_ok=True)
        # This test uses generated source artifacts only; raw transcripts remain
        # in their independent temporary roots and are not read by the catalog.
        shutil.copytree(source, destination)
        session["path"] = str(destination)
    first_registry["sessions"] = [
        *json.loads((aoa_root / MODULE.REGISTRY_NAME).read_text(encoding="utf-8"))["sessions"][:1],
        *second_registry["sessions"],
    ]
    (aoa_root / MODULE.REGISTRY_NAME).write_text(
        json.dumps(first_registry, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    first = MODULE.goal_catalog_publication(
        aoa_root=aoa_root,
        page_size=1,
        order="chronological",
    )
    assert first["ok"] is True
    assert first["state"] == "current"
    assert first["source_item_count"] == 2
    assert first["item_count"] == 1
    assert first["pagination"]["mode"] == "immutable_snapshot"
    assert first["pagination"]["next_cursor"]
    assert first["items"][0]["item_digest"].startswith("sha256:")
    assert first["page_digest"].startswith("sha256:")
    assert first["snapshot_digest"].startswith("sha256:")
    assert first["source_watermark"]["coverage"] == "complete"
    assert first["items"][0]["safe_title_state"] == "withheld"
    assert first["items"][0]["lifecycle_state"] == "active"
    rendered = json.dumps(first, ensure_ascii=False)
    assert "objective one" not in rendered
    assert "objective two" not in rendered
    assert str(tmp_path) not in rendered
    assert "owner-repo" not in rendered
    assert all("raw_session_path" not in item for item in first["items"])

    repeat = MODULE.goal_catalog_publication(
        aoa_root=aoa_root,
        page_size=1,
        order="chronological",
        cursor=first["pagination"]["cursor"],
    )
    assert repeat["items"] == first["items"]
    assert repeat["page_digest"] == first["page_digest"]
    assert repeat["snapshot_digest"] == first["snapshot_digest"]

    second = MODULE.goal_catalog_publication(
        aoa_root=aoa_root,
        page_size=1,
        order="chronological",
        cursor=first["pagination"]["next_cursor"],
    )
    assert second["ok"] is True
    assert second["item_count"] == 1
    assert second["pagination"]["complete_for_query"] is True
    assert second["items"][0]["goal_ref"] != first["items"][0]["goal_ref"]
    assert second["snapshot_digest"] == first["snapshot_digest"]

    schema = public_catalog_schema()
    Draft202012Validator(schema).validate(first)
    Draft202012Validator(schema).validate(second)


def test_public_catalog_keeps_historical_lifecycle_state_explicit(
    tmp_path: Path,
) -> None:
    aoa_root = create_real_goal_session(
        tmp_path,
        "goal-historical",
        "private historical objective",
        complete=True,
    )
    publication = MODULE.goal_catalog_publication(aoa_root=aoa_root)
    assert publication["ok"] is True
    assert publication["source_item_count"] == 1
    item = publication["items"][0]
    assert item["lifecycle_state"] == "complete"
    assert item["lifecycle_group"]["history_state"] == "complete"
    assert item["lifecycle_group"]["current_member_count"] == 0
    assert item["lifecycle_group"]["historical_member_count"] == 1
    assert item["lifecycle_group"]["unknown_member_count"] == 0
    Draft202012Validator(public_catalog_schema()).validate(publication)


def test_public_catalog_fails_closed_for_cursor_drift_and_malformed_cursor(
    tmp_path: Path,
) -> None:
    aoa_root = create_real_goal_session(tmp_path, "goal-source", "private objective")
    first = MODULE.goal_catalog_publication(aoa_root=aoa_root, page_size=1)
    assert first["ok"] is True
    assert first["pagination"]["next_cursor"] is None

    malformed = MODULE.goal_catalog_publication(
        aoa_root=aoa_root,
        page_size=1,
        cursor="not-an-opaque-goal-catalog-cursor",
    )
    assert malformed["ok"] is False
    assert malformed["state"] == "invalid"
    assert malformed["items"] == []
    Draft202012Validator(public_catalog_schema()).validate(malformed)

    invalid_page_size = MODULE.goal_catalog_publication(
        aoa_root=aoa_root,
        page_size=0,
    )
    assert invalid_page_size["ok"] is False
    assert invalid_page_size["state"] == "invalid"
    assert invalid_page_size["items"] == []
    Draft202012Validator(public_catalog_schema()).validate(invalid_page_size)

    registry_path = aoa_root / MODULE.REGISTRY_NAME
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    session_dir = Path(str(registry["sessions"][0]["path"]))
    index_path = session_dir / MODULE.SESSION_INDEX_JSON
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index["updated_at"] = "2026-08-23T10:00:05Z"
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    drift_cursor = MODULE.goal_catalog_public_encode_cursor(
        {
            "version": MODULE.GOAL_CATALOG_CURSOR_VERSION,
            "snapshot_digest": first["snapshot_digest"],
            "target": "all",
            "order": "recent",
            "offset": 0,
            "page_size": 1,
        }
    )
    drifted = MODULE.goal_catalog_publication(
        aoa_root=aoa_root,
        page_size=1,
        cursor=drift_cursor,
    )
    assert drifted["ok"] is False
    assert drifted["state"] in {"stale", "deferred"}
    assert drifted["items"] == []
    Draft202012Validator(public_catalog_schema()).validate(drifted)


def test_public_catalog_fails_closed_for_malformed_and_incompatible_sources(
    tmp_path: Path,
) -> None:
    malformed_root = create_real_goal_session(tmp_path / "malformed", "goal-malformed", "private objective")
    registry = json.loads((malformed_root / MODULE.REGISTRY_NAME).read_text(encoding="utf-8"))
    malformed_index = Path(str(registry["sessions"][0]["path"])) / MODULE.SESSION_INDEX_JSON
    malformed_index.write_text("{not-json\n", encoding="utf-8")
    malformed = MODULE.goal_catalog_publication(aoa_root=malformed_root)
    assert malformed["ok"] is False
    assert malformed["state"] == "invalid"
    assert malformed["items"] == []
    Draft202012Validator(public_catalog_schema()).validate(malformed)

    stale_root = create_real_goal_session(tmp_path / "stale", "goal-stale", "private objective")
    stale_registry = json.loads((stale_root / MODULE.REGISTRY_NAME).read_text(encoding="utf-8"))
    stale_index_path = Path(str(stale_registry["sessions"][0]["path"])) / MODULE.SESSION_INDEX_JSON
    stale_index = json.loads(stale_index_path.read_text(encoding="utf-8"))
    stale_index["generation_identity"] = {"generation_id": "incompatible"}
    stale_index_path.write_text(json.dumps(stale_index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    stale = MODULE.goal_catalog_publication(aoa_root=stale_root)
    assert stale["ok"] is False
    assert stale["state"] == "stale"
    assert stale["items"] == []
    Draft202012Validator(public_catalog_schema()).validate(stale)


def test_public_catalog_retries_source_movement_during_capture(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    aoa_root = create_real_goal_session(
        tmp_path,
        "goal-moving-source",
        "private objective",
    )
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
    publication = MODULE.goal_catalog_publication(aoa_root=aoa_root)

    assert publication["ok"] is True
    assert publication["state"] == "current"
    assert calls["index"] == 1
    assert publication["snapshot"]["read_attempts"] == 2
    assert publication["snapshot"]["retry_exhausted"] is False
    assert publication["snapshot"]["stable_source"] is True
    Draft202012Validator(public_catalog_schema()).validate(publication)


def test_public_catalog_retries_when_raw_capture_source_moves(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    aoa_root = create_real_goal_session(
        tmp_path,
        "goal-moving-raw-source",
        "private objective",
    )
    original_read = MODULE.goal_catalog_public_read_json
    calls = {"capture": 0}

    def moving_capture_read(path: Path) -> dict[str, Any]:
        result = original_read(path)
        if path.name == MODULE.RAW_CAPTURE_STATE_JSON and calls["capture"] == 0:
            calls["capture"] += 1
            return {
                **result,
                "state": "deferred",
                "value": None,
                "digest": None,
                "stable": False,
                "diagnostic": "source_file_changed_during_read",
            }
        return result

    monkeypatch.setattr(MODULE, "goal_catalog_public_read_json", moving_capture_read)
    publication = MODULE.goal_catalog_publication(aoa_root=aoa_root)

    assert publication["ok"] is True
    assert publication["state"] == "current"
    assert calls["capture"] == 1
    assert publication["snapshot"]["read_attempts"] == 2
    assert publication["snapshot"]["retry_exhausted"] is False
    Draft202012Validator(public_catalog_schema()).validate(publication)


def test_public_catalog_defers_torn_projection_indexes_without_records(
    tmp_path: Path,
) -> None:
    aoa_root = create_real_goal_session(
        tmp_path,
        "goal-torn-index",
        "private objective",
    )
    registry = json.loads((aoa_root / MODULE.REGISTRY_NAME).read_text(encoding="utf-8"))
    session_dir = Path(str(registry["sessions"][0]["path"]))
    index_path = session_dir / MODULE.SESSION_INDEX_JSON
    index = json.loads(index_path.read_text(encoding="utf-8"))
    projection_publish = index.get("projection_publish")
    assert isinstance(projection_publish, dict)
    projection_publish = dict(projection_publish)
    projection_publish["publish_id"] = "torn-projection-publish"
    index["projection_publish"] = projection_publish
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    publication = MODULE.goal_catalog_publication(aoa_root=aoa_root)

    assert publication["ok"] is False
    assert publication["state"] == "deferred"
    assert publication["items"] == []
    assert "session_projection_publish_identity_torn" in " ".join(publication["diagnostics"])
    assert publication["snapshot"]["retry_exhausted"] is True
    Draft202012Validator(public_catalog_schema()).validate(publication)


def test_public_catalog_defers_when_preserved_raw_is_ahead_of_projection(
    tmp_path: Path,
) -> None:
    aoa_root = create_real_goal_session(
        tmp_path,
        "goal-raw-ahead",
        "private objective",
    )
    registry = json.loads((aoa_root / MODULE.REGISTRY_NAME).read_text(encoding="utf-8"))
    session_dir = Path(str(registry["sessions"][0]["path"]))
    capture_path = session_dir / "raw" / MODULE.RAW_CAPTURE_STATE_JSON
    capture = json.loads(capture_path.read_text(encoding="utf-8"))
    capture["status"] = "preserved_unindexed"
    capture["raw_sha256"] = "capture-ahead-of-projection"
    capture["source_stable_during_capture"] = True
    capture_path.write_text(json.dumps(capture, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    publication = MODULE.goal_catalog_publication(aoa_root=aoa_root)

    assert publication["ok"] is False
    assert publication["state"] == "deferred"
    assert publication["items"] == []
    assert publication["source_watermark"]["live_tail"]["state"] == "ahead"
    assert "preserved_raw_capture_ahead_of_session_projection" in " ".join(publication["diagnostics"])
    assert "zero admitted records does not establish Goal absence" in publication["claim_limit"]
    Draft202012Validator(public_catalog_schema()).validate(publication)


def test_public_catalog_exposes_bounded_retry_exhaustion(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    aoa_root = create_real_goal_session(
        tmp_path,
        "goal-retry-exhausted",
        "private objective",
    )
    original_read = MODULE.goal_catalog_public_read_json
    calls = {"index": 0}

    def always_moving(path: Path) -> dict[str, Any]:
        result = original_read(path)
        if path.name == MODULE.SESSION_INDEX_JSON:
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

    monkeypatch.setattr(MODULE, "goal_catalog_public_read_json", always_moving)
    publication = MODULE.goal_catalog_publication(aoa_root=aoa_root)

    assert publication["ok"] is False
    assert publication["state"] == "deferred"
    assert publication["items"] == []
    assert calls["index"] == MODULE.GOAL_CATALOG_SOURCE_SNAPSHOT_MAX_ATTEMPTS
    assert publication["snapshot"]["retry_exhausted"] is True
    assert publication["snapshot"]["read_attempts"] == MODULE.GOAL_CATALOG_SOURCE_SNAPSHOT_MAX_ATTEMPTS
    assert "goal_catalog_source_snapshot_retry_exhausted" in publication["diagnostics"]
    Draft202012Validator(public_catalog_schema()).validate(publication)


def test_public_catalog_stable_snapshot_reports_watermark_and_read_budget(
    tmp_path: Path,
) -> None:
    aoa_root = create_real_goal_session(
        tmp_path,
        "goal-stable-snapshot",
        "private objective",
    )

    publication = MODULE.goal_catalog_publication(aoa_root=aoa_root)

    assert publication["ok"] is True
    assert publication["state"] == "current"
    assert publication["source_watermark"]["coverage"] == "complete"
    assert publication["source_watermark"]["live_tail"]["state"] == "current"
    assert publication["snapshot"]["read_attempts"] == 1
    assert publication["snapshot"]["retry_exhausted"] is False
    assert publication["snapshot"]["stable_source"] is True
    Draft202012Validator(public_catalog_schema()).validate(publication)
