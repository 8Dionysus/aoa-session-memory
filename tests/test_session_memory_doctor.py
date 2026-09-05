from __future__ import annotations

import contextlib
import io
import json
import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from session_memory_test_support import (
    build_doctor_root_with_missing_generated_segment,
    complete_doctor_segment_fixture,
    make_raw_unavailable_duplicate,
    module,
    run_doctor_payload,
)


def test_doctor_defers_generated_segment_gaps_for_recent_live_tail(tmp_path: Path) -> None:
    workspace, root = build_doctor_root_with_missing_generated_segment(tmp_path, recent_live=True)

    code, payload = run_doctor_payload(workspace, root)

    assert code == 0
    assert payload["ok"] is True
    assert payload["status"] == "current_with_deferred_live_updates"
    assert payload["deferred_live_problem_count"] >= 3
    assert payload["problems"] == []
    assert set(payload["installable_user_skills"]["skills"]) == set(module.USER_LEVEL_INSTALLABLE_SKILL_NAMES)
    assert payload["installable_user_skills"]["source_ok"] is True
    assert payload["deferred_live_problem_sessions"][0]["session_id"] == "doctor-live-tail"
    assert payload["live_tail"]["next_route"] == "wait_for_quiet_window_then_rerun_doctor_or_auto_maintenance"


def test_doctor_keeps_quiet_generated_segment_gaps_actionable(tmp_path: Path) -> None:
    workspace, root = build_doctor_root_with_missing_generated_segment(tmp_path, recent_live=False)

    code, payload = run_doctor_payload(workspace, root)

    assert code == 1
    assert payload["ok"] is False
    assert payload["status"] == "failed"
    assert payload["deferred_live_problem_count"] == 0
    assert any("missing segment markdown" in item for item in payload["problems"])
    assert any("missing segment index" in item for item in payload["problems"])


def test_doctor_default_skips_deep_segment_index_event_parse(tmp_path: Path, monkeypatch: Any) -> None:
    workspace, root = build_doctor_root_with_missing_generated_segment(tmp_path, recent_live=False)
    _session_dir, index_path = complete_doctor_segment_fixture(root)
    original_read_json = module.read_json

    def guarded_read_json(path: Path, default: Any = None) -> Any:
        if Path(path) == index_path:
            raise AssertionError("default doctor must not parse segment index event payloads")
        return original_read_json(path, default)

    monkeypatch.setattr(module, "read_json", guarded_read_json)

    code, payload = run_doctor_payload(workspace, root)

    assert code == 0
    assert payload["ok"] is True
    assert payload["segment_index_check"]["mode"] == "metadata_only"
    assert payload["segment_index_check"]["event_validation_skipped_index_count"] == 1
    assert payload["segment_index_check"]["deep_route"]


def test_doctor_deep_segment_indexes_validates_event_records(tmp_path: Path) -> None:
    workspace, root = build_doctor_root_with_missing_generated_segment(tmp_path, recent_live=False)
    complete_doctor_segment_fixture(
        root,
        event={
            "event_id": "000001",
            "type": "NOT_A_REAL_EVENT_TYPE",
            "raw_ref": "",
            "md_anchor": "",
        },
    )
    args = SimpleNamespace(
        workspace_root=str(workspace),
        aoa_root=str(root),
        check_live_hooks=False,
        check_user_skill=False,
        check_installable_user_skills=False,
        check_codex_grounding=False,
        deep_segment_indexes=True,
    )
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = module.command_doctor(args)
    payload = json.loads(out.getvalue())

    assert code == 1
    assert payload["ok"] is False
    assert payload["segment_index_check"]["mode"] == "deep_event_validation"
    assert payload["segment_index_check"]["event_validation_count"] == 1
    assert any("invalid event type NOT_A_REAL_EVENT_TYPE" in item for item in payload["problems"])
    assert any("event missing raw_ref or md_anchor" in item for item in payload["problems"])


def test_doctor_excludes_projection_stages_from_archive_health_counts(
    tmp_path: Path,
) -> None:
    workspace, root = build_doctor_root_with_missing_generated_segment(
        tmp_path,
        recent_live=False,
    )
    session_dir, _index_path = complete_doctor_segment_fixture(root)
    sessions_root = root / module.SESSION_ROOT
    complete_stage = sessions_root / (
        f".{session_dir.name}.projection-stage-987654-complete"
    )
    incomplete_stage = sessions_root / (
        f".{session_dir.name}.projection-stage-987654-incomplete"
    )
    shutil.copytree(session_dir, complete_stage)
    incomplete_stage.mkdir()

    code, payload = run_doctor_payload(workspace, root)

    assert code == 0
    assert payload["ok"] is True
    assert payload["archive_dir_count"] == 1
    assert payload["session_dir_count"] == 3
    assert payload["projection_stage_dir_count"] == 2
    assert payload["problems"] == []
    assert any(
        "session projection stages are excluded from archive health counts"
        in warning
        for warning in payload["warnings"]
    )


def test_doctor_separates_logical_registry_from_preserved_physical_duplicates(
    tmp_path: Path,
) -> None:
    workspace, root = build_doctor_root_with_missing_generated_segment(
        tmp_path,
        recent_live=False,
    )
    session_dir, _index_path = complete_doctor_segment_fixture(root)
    registry = module.read_json(root / module.REGISTRY_NAME, {})
    registry["sessions"][0]["archive_status"] = "raw_unavailable"
    module.write_json(root / module.REGISTRY_NAME, registry)
    manifest = module.read_json(session_dir / "session.manifest.json", {})
    manifest["archive_status"] = "raw_unavailable"
    module.write_json(session_dir / "session.manifest.json", manifest)
    incidents = session_dir / "incidents"
    incidents.mkdir()
    (incidents / "20260822T000000Z__raw-session-unavailable__INCIDENT.md").write_text(
        "# preserved test incident\n",
        encoding="utf-8",
    )
    module.write_json(
        incidents / "20260822T000000Z__raw-session-unavailable__DIAGNOSTIC.json",
        {"session_id": manifest["session_id"], "incident_type": "raw_session_unavailable"},
    )
    duplicate = make_raw_unavailable_duplicate(
        root,
        session_dir,
        label="2026-06-11__007__doctor-duplicate",
    )

    code, payload = run_doctor_payload(workspace, root)

    assert code == 0
    assert payload["ok"] is True
    assert payload["session_count"] == 1
    assert payload["logical_registry_count"] == 1
    assert payload["archive_dir_count"] == 2
    assert payload["physical_archive_count"] == 2
    assert payload["physical_archive_duplicate_count"] == 1
    lineage = next(
        item
        for item in payload["physical_archive_lineage"]
        if item["session_id"] == manifest["session_id"]
    )
    assert lineage["lineage_status"] == "preserved_duplicate_reported"
    assert lineage["current_path_match_count"] == 1
    assert str(duplicate) in payload["warnings"][0]


@pytest.mark.parametrize("failure", ["unregistered", "mismatched", "malformed", "ambiguous"])
def test_doctor_fails_closed_for_unresolved_physical_archive_lineage(
    tmp_path: Path,
    failure: str,
) -> None:
    workspace, root = build_doctor_root_with_missing_generated_segment(
        tmp_path,
        recent_live=False,
    )
    session_dir, _index_path = complete_doctor_segment_fixture(root)
    if failure == "unregistered":
        make_raw_unavailable_duplicate(
            root,
            session_dir,
            label="2026-06-11__007__unregistered",
            session_id="unregistered-session",
        )
    elif failure == "mismatched":
        manifest = module.read_json(session_dir / "session.manifest.json", {})
        manifest["session_id"] = "mismatched-session"
        module.write_json(session_dir / "session.manifest.json", manifest)
    elif failure == "malformed":
        (session_dir / "session.manifest.json").write_text("{not-json\n", encoding="utf-8")
    else:
        registry = module.read_json(root / module.REGISTRY_NAME, {})
        registry["sessions"][0]["path"] = str(session_dir.parent / "missing-current")
        module.write_json(root / module.REGISTRY_NAME, registry)

    code, payload = run_doctor_payload(workspace, root)

    assert code == 1
    assert payload["ok"] is False
    if failure == "unregistered":
        assert any("unregistered physical archive" in item for item in payload["problems"])
    elif failure == "mismatched":
        assert any("session_id mismatch" in item for item in payload["problems"])
    elif failure == "malformed":
        assert any("malformed archive manifest" in item for item in payload["problems"])
    else:
        assert any("not an unambiguous physical archive" in item for item in payload["problems"])


def test_registry_rebuild_keeps_one_logical_record_and_explicit_physical_lineage(
    tmp_path: Path,
) -> None:
    _workspace, root = build_doctor_root_with_missing_generated_segment(
        tmp_path,
        recent_live=False,
    )
    session_dir, _index_path = complete_doctor_segment_fixture(root)
    duplicate = make_raw_unavailable_duplicate(
        root,
        session_dir,
        label="2026-06-11__007__registry-duplicate",
    )
    manifest = module.read_json(session_dir / "session.manifest.json", {})
    manifest["archive_status"] = "raw_unavailable"
    module.write_json(session_dir / "session.manifest.json", manifest)

    records = module.registry_records_from_manifests(root)
    matching = [record for record in records if record["session_id"] == manifest["session_id"]]

    assert len(matching) == 1
    lineage = matching[0]["physical_archive_lineage"]
    assert lineage["logical_session_id"] == manifest["session_id"]
    assert lineage["physical_archive_count"] == 2
    assert str(session_dir) in lineage["physical_paths"]
    assert str(duplicate) in lineage["physical_paths"]
