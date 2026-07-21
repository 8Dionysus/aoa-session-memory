from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "aoa_session_memory.py"
)
spec = importlib.util.spec_from_file_location(
    "aoa_session_memory_graph_rebuild_freshness_test",
    SCRIPT,
)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def write_jsonl(
    path: Path,
    rows: list[dict[str, object]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            json.dumps(row, ensure_ascii=False)
            for row in rows
        )
        + "\n",
        encoding="utf-8",
    )


def archive_session(
    *,
    workspace: Path,
    aoa_root: Path,
    transcript: Path,
    session_id: str,
    timestamp: str,
    prompt: str,
) -> None:
    write_jsonl(
        transcript,
        [
            {
                "timestamp": timestamp,
                "type": "session_meta",
                "payload": {
                    "id": session_id,
                    "cwd": str(workspace),
                },
            },
            {
                "timestamp": timestamp,
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": prompt,
                        }
                    ],
                },
            },
        ],
    )
    result = module.handle_hook_event(
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
    assert result["ok"] is True


def test_global_graph_rebuild_publishes_clean_ledger_and_queue(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    archive_session(
        workspace=workspace,
        aoa_root=aoa_root,
        transcript=tmp_path / "first.jsonl",
        session_id="graph-rebuild-first",
        timestamp="2026-07-18T00:00:00Z",
        prompt="Remember the first graph rebuild anchor.",
    )
    archive_session(
        workspace=workspace,
        aoa_root=aoa_root,
        transcript=tmp_path / "second.jsonl",
        session_id="graph-rebuild-second",
        timestamp="2026-07-18T01:00:00Z",
        prompt="Remember the second graph rebuild anchor.",
    )
    prebuild_states = module.graph_source_states(
        aoa_root=aoa_root
    )["states"]
    module.update_graph_source_state_ledger_from_states(
        aoa_root,
        prebuild_states,
        reason="test_prebuild_missing_sources",
    )
    module.update_graph_maintenance_queue_from_states(
        aoa_root,
        prebuild_states,
        reason="test_prebuild_missing_sources",
    )

    stale_key = "segment:removed-generated-source:000"
    retired_key = "session:retired-evidence-source"
    ledger = module.read_graph_source_state_ledger(
        aoa_root
    )
    ledger["sources"][stale_key] = {
        "source_key": stale_key,
        "status": "dirty",
    }
    ledger["sources"][retired_key] = {
        "source_key": retired_key,
        "status": "tombstoned_evidence_source",
        "retired_at": "2026-07-18T01:30:00Z",
    }
    module.write_graph_source_state_ledger(
        aoa_root,
        ledger,
    )
    queue = module.read_graph_maintenance_queue(aoa_root)
    queue["items"][stale_key] = {
        "source_key": stale_key,
        "status": "dirty",
    }
    module.write_graph_maintenance_queue(
        aoa_root,
        queue,
    )

    built = module.build_session_graph(
        aoa_root=aoa_root,
        target="all",
        write=True,
        include_rows=False,
        export_sidecar=False,
    )

    assert built["ok"] is True
    published = built["source_state_publish"]
    assert published["status"] == "published"
    assert published["global_selection"] is True
    assert published["pruned_ledger_source_count"] == 1
    assert published["pruned_queue_source_count"] == 1
    assert published["final_queue_source_count"] == 0

    final_ledger = module.read_graph_source_state_ledger(
        aoa_root
    )["sources"]
    assert stale_key not in final_ledger
    assert final_ledger[retired_key]["status"] == (
        "tombstoned_evidence_source"
    )
    assert {
        entry["status"]
        for key, entry in final_ledger.items()
        if key != retired_key
    } == {"clean"}
    assert module.read_graph_maintenance_queue(
        aoa_root
    )["items"] == {}

    hot_state = module.graph_store_hot_state(aoa_root)
    assert hot_state["status"] == (
        "current_with_retired_sources"
    )
    assert hot_state["needs_maintenance"] is False


def test_bounded_graph_rebuild_keeps_excluded_sources_dirty(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    archive_session(
        workspace=workspace,
        aoa_root=aoa_root,
        transcript=tmp_path / "bounded-first.jsonl",
        session_id="graph-bounded-first",
        timestamp="2026-07-18T00:00:00Z",
        prompt="Remember bounded graph source one.",
    )
    archive_session(
        workspace=workspace,
        aoa_root=aoa_root,
        transcript=tmp_path / "bounded-second.jsonl",
        session_id="graph-bounded-second",
        timestamp="2026-07-18T01:00:00Z",
        prompt="Remember bounded graph source two.",
    )
    prebuild_states = module.graph_source_states(
        aoa_root=aoa_root
    )["states"]
    module.update_graph_source_state_ledger_from_states(
        aoa_root,
        prebuild_states,
        reason="test_prebuild_missing_sources",
    )
    module.update_graph_maintenance_queue_from_states(
        aoa_root,
        prebuild_states,
        reason="test_prebuild_missing_sources",
    )
    assert len(
        module.read_graph_maintenance_queue(
            aoa_root
        )["items"]
    ) > 0

    built = module.build_session_graph(
        aoa_root=aoa_root,
        target="all",
        limit=1,
        write=True,
        include_rows=False,
        export_sidecar=False,
    )

    assert built["ok"] is True
    published = built["source_state_publish"]
    assert published["global_selection"] is False
    assert published["selected_source_count"] > 0
    assert published["final_queue_source_count"] > 0

    statuses = {
        str(entry.get("status") or "")
        for entry in module.read_graph_source_state_ledger(
            aoa_root
        )["sources"].values()
    }
    assert "clean" in statuses
    assert statuses & module.GRAPH_ACTIONABLE_SOURCE_STATUSES
    hot_state = module.graph_store_hot_state(aoa_root)
    assert hot_state["status"] == "dirty"
    assert hot_state["needs_maintenance"] is True
    assert (
        "graph_source_ledger_store_count_mismatch"
        in hot_state["diagnostics"]
    )


def test_failed_atomic_graph_rebuild_does_not_publish_freshness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    archive_session(
        workspace=workspace,
        aoa_root=aoa_root,
        transcript=tmp_path / "failed-rebuild.jsonl",
        session_id="graph-failed-rebuild",
        timestamp="2026-07-18T00:00:00Z",
        prompt="Keep failed graph rebuild state conservative.",
    )
    prebuild_states = module.graph_source_states(
        aoa_root=aoa_root
    )["states"]
    module.update_graph_source_state_ledger_from_states(
        aoa_root,
        prebuild_states,
        reason="test_prebuild_missing_sources",
    )
    module.update_graph_maintenance_queue_from_states(
        aoa_root,
        prebuild_states,
        reason="test_prebuild_missing_sources",
    )
    ledger_path = module.graph_paths(aoa_root)[
        "source_state_ledger"
    ]
    queue_path = module.graph_paths(aoa_root)[
        "maintenance_queue"
    ]
    ledger_before = ledger_path.read_bytes()
    queue_before = queue_path.read_bytes()

    def fail_rebuild(
        _store: object,
        _contributions: object,
    ) -> dict[str, object]:
        raise RuntimeError("injected graph rebuild failure")

    monkeypatch.setattr(
        module.GraphSqliteStore,
        "rebuild",
        fail_rebuild,
    )
    with pytest.raises(
        RuntimeError,
        match="injected graph rebuild failure",
    ):
        module.build_session_graph(
            aoa_root=aoa_root,
            target="all",
            write=True,
            include_rows=False,
            export_sidecar=False,
        )

    assert ledger_path.read_bytes() == ledger_before
    assert queue_path.read_bytes() == queue_before
    assert not module.graph_paths(aoa_root)["store"].exists()
