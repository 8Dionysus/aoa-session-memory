from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from session_memory_test_support import (
    module,
    write_jsonl,
)

def test_agent_event_taxonomy_task_episodes_and_search_routes(tmp_path: Path, monkeypatch: Any) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-06-13T00-00-00-agent-events.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-06-13T00:00:00Z", "type": "session_meta", "payload": {"id": "agent-events", "cwd": str(workspace)}},
            {"timestamp": "2026-06-13T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Audit the session-memory MCP hook"}]}},
            {"timestamp": "2026-06-13T00:00:02Z", "type": "response_item", "payload": {"type": "reasoning", "summary": [{"type": "summary_text", "text": "Need inspect source before changing."}]}},
            {"timestamp": "2026-06-13T00:00:03Z", "type": "event_msg", "payload": {"type": "agent_message", "message": "Сейчас проверяю живой контур."}},
            {"timestamp": "2026-06-13T00:00:04Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Сейчас проверяю живой контур."}]}},
            {"timestamp": "2026-06-13T00:00:05Z", "type": "response_item", "payload": {"type": "function_call", "name": "exec_command", "call_id": "call-1", "arguments": "{\"cmd\":\"pytest -q\"}"}},
            {"timestamp": "2026-06-13T00:00:06Z", "type": "response_item", "payload": {"type": "function_call_output", "call_id": "call-1", "output": "1 passed"}},
            {"timestamp": "2026-06-13T00:00:07Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Почти готово, сейчас прогоню еще одну проверку."}]}},
            {"timestamp": "2026-06-13T00:00:08Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Готово. Итог: проверка прошла."}]}},
            {"timestamp": "2026-06-13T00:00:09Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Осталось проверить open thread отдельно."}]}},
            {"timestamp": "2026-06-13T00:00:10Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Продолжай"}]}},
            {"timestamp": "2026-06-13T00:00:11Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Дальше беру второй сценарий."}]}},
        ],
    )

    module.handle_hook_event(
        "Stop",
        {
            "session_id": "agent-events",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    session_dir = next(path for path in (aoa_root / "sessions").iterdir() if path.is_dir())
    segment_index = json.loads(next((session_dir / "segments").glob("*.index.json")).read_text(encoding="utf-8"))
    assert "assistant_reasoning_boundary" in segment_index["by_agent_event"]
    assert "assistant_progress_update" in segment_index["by_agent_event"]
    assert "assistant_final_closeout" in segment_index["by_agent_event"]
    assert "assistant_open_thread" in segment_index["by_agent_event"]

    reasoning_event = next(event for event in segment_index["events"] if event["type"] == "ASSISTANT_REASONING_BOUNDARY")
    assert reasoning_event["facets"]["conversation_act"]["kind"] == "assistant_reasoning_boundary"
    assert reasoning_event["facets"]["agent_event"]["class"] == "assistant_reasoning_boundary"
    assert reasoning_event["facets"]["agent_event"]["content_status"] == "boundary_only"

    false_closeout = next(event for event in segment_index["events"] if "Почти готово" in event["title"] or event["event_id"] == "000008")
    assert false_closeout["type"] != "FINAL_STATE"
    assert false_closeout["facets"]["agent_event"]["class"] == "assistant_progress_update"
    assert "final_marker_not_closeout" in false_closeout["facets"]["agent_event"]["ambiguity_flags"]

    final_closeout = next(event for event in segment_index["events"] if event["type"] == "FINAL_STATE")
    assert final_closeout["facets"]["agent_event"]["class"] == "assistant_final_closeout"

    open_thread = next(event for event in segment_index["events"] if event["type"] == "OPEN_THREAD")
    assert open_thread["facets"]["conversation_act"]["kind"] == "assistant_open_thread"
    assert open_thread["facets"]["agent_event"]["class"] == "assistant_open_thread"

    stream_event = next(event for event in segment_index["events"] if event.get("source_type") == "event_msg" and event["type"] == "ASSISTANT_MESSAGE")
    assert stream_event["facets"]["agent_event"]["canonical"] is False
    assert stream_event["facets"]["agent_event"]["source_lane"] == "event_msg_stream"

    session_index = json.loads((session_dir / "session.index.json").read_text(encoding="utf-8"))
    assert session_index["agent_event_counts"]["assistant_reasoning_boundary"] == 1
    assert session_index["task_episode_counts"]["total"] == 2
    assert session_index["task_episodes"] == []
    task_episodes = module.session_index_task_episode_components(
        session_dir,
        session_index,
    )
    assert len(task_episodes) == 2
    first_episode = task_episodes[0]
    assert first_episode["start_user_ref"]["raw_ref"] == "raw:line:2"
    assert first_episode["status"] == "closed"
    assert first_episode["reasoning_refs"]
    assert first_episode["progress_refs"]
    assert first_episode["verification_refs"]
    assert first_episode["closeout_refs"]
    assert first_episode["semantic_contract"]["source_aware_admission"] is True
    assert "Audit the session-memory MCP hook" in first_episode["intent"]
    assert any("pytest -q" in item["text"] for item in first_episode["representations"]["actions"])
    assert any("проверка прошла" in item["text"] for item in first_episode["representations"]["outcomes"])
    assert all(item["refs"]["raw"] for items in first_episode["representations"].values() for item in items)
    assert any(
        item.get("admission_basis") == "structured_compact_success_observation" and "1 passed" in item["text"]
        for item in first_episode["representations"]["outcomes"]
    )
    assert first_episode["time_span"]["from"] == "2026-06-13T00:00:01Z"
    assert first_episode["time_span"]["to"] == "2026-06-13T00:00:09Z"
    assert task_episodes[1]["transition"]["previous_episode_id"] == first_episode["episode_id"]
    recent_episode_route = module.task_episode_route_search(aoa_root=aoa_root, target="latest", limit=1)
    assert recent_episode_route["order"] == "recent"
    assert recent_episode_route["results"][0]["episode_id"] == "task-0002"
    chronological_episode_route = module.task_episode_route_search(
        aoa_root=aoa_root,
        target="latest",
        limit=1,
        order="chronological",
    )
    assert chronological_episode_route["order"] == "chronological"
    assert chronological_episode_route["results"][0]["episode_id"] == "task-0001"

    search_index = module.search_index_sessions(aoa_root=aoa_root, target="all", rebuild=True)
    assert search_index["ok"] is True
    assert search_index["episode_semantic_projection"]["episode_document_count"] == 2
    entity_state = module.episode_entity_state_search(
        aoa_root=aoa_root,
        anchor="exec_command",
        kind="tool",
        session="agent-events",
        limit=10,
    )
    assert entity_state["ok"] is True
    assert entity_state["entity_state"] == "invocation_observed"
    assert entity_state["relation_counts"]["invoked"] >= 1
    assert entity_state["cost_profile"]["monolith_scanned"] is False
    assert all(item["raw_ref"].startswith("raw:line:") for item in entity_state["results"])
    episode_hits = module.episode_semantic_search(
        aoa_root=aoa_root,
        query="audit session memory MCP hook",
        limit=5,
        explain=True,
    )
    assert episode_hits["ok"] is True
    assert episode_hits["result_count"] >= 1
    assert episode_hits["results"][0]["task_episode_id"] == "task-0001"
    assert episode_hits["results"][0]["candidate_id"] == (
        episode_hits["results"][0]["doc_id"]
    )
    assert episode_hits["candidate_ids"][0] == (
        episode_hits["results"][0]["candidate_id"]
    )
    assert episode_hits["results"][0]["match_channel"] == "episode_contextual_bm25"
    assert episode_hits["results"][0]["raw_ref"] == "raw:line:2"
    assert episode_hits["results"][0]["reading_contract"]["status"] == "candidate_navigation_only"
    assert episode_hits["results"][0]["supporting_evidence"]
    evidence_window_route = episode_hits["results"][0]["expansion_routes"]["evidence_window"]
    assert evidence_window_route.startswith("evidence-window agent-events raw:line:")
    assert any(
        str(item["refs"]["raw"]) in evidence_window_route
        for item in episode_hits["results"][0]["supporting_evidence"]
    )
    assert all(
        "1 passed" not in str(item.get("text") or "")
        for result in episode_hits["results"]
        for item in result.get("supporting_evidence", [])
    )
    assert episode_hits["cost_profile"]["monolith_raw_fts_scanned"] is False
    date_conn = sqlite3.connect(module.search_db_path(aoa_root))
    date_conn.execute("UPDATE episode_semantic_meta SET session_date = '2026-06-04'")
    date_conn.commit()
    date_conn.close()
    episode_hits_by_event_date = module.episode_semantic_search(
        aoa_root=aoa_root,
        query="audit session memory MCP hook",
        date_from="2026-06-13",
        date_to="2026-06-13",
        limit=5,
    )
    assert episode_hits_by_event_date["result_count"] >= 1
    assert episode_hits_by_event_date["results"][0]["task_episode_id"] == "task-0001"
    assert (
        episode_hits_by_event_date["filters"]["date_filter_basis"]
        == "episode_time_span_overlap_with_session_date_fallback"
    )
    episode_hits_by_event_time = module.episode_semantic_search(
        aoa_root=aoa_root,
        query="audit session memory MCP hook",
        time_from="2026-06-13T00:00:00Z",
        time_to="2026-06-13T00:00:09.500Z",
        limit=5,
    )
    assert episode_hits_by_event_time["result_count"] >= 1
    assert episode_hits_by_event_time["results"][0]["task_episode_id"] == "task-0001"
    assert (
        episode_hits_by_event_time["filters"]["time_filter_basis"]
        == "episode_time_span_overlap_with_session_date_fallback"
    )
    episode_hits_outside_event_time = module.episode_semantic_search(
        aoa_root=aoa_root,
        query="audit session memory MCP hook",
        time_from="2026-06-14T00:00:00Z",
        time_to="2026-06-14T00:00:01Z",
        limit=5,
    )
    assert episode_hits_outside_event_time["result_count"] == 0
    stale_conn = sqlite3.connect(module.search_db_path(aoa_root))
    stale_conn.execute(
        "UPDATE episode_semantic_meta SET projection_version = ?",
        (module.EPISODE_SEMANTIC_PROJECTION_VERSION - 1,),
    )
    stale_conn.execute(
        "UPDATE episode_semantic_session_state SET projection_version = ?",
        (module.EPISODE_SEMANTIC_PROJECTION_VERSION - 1,),
    )
    stale_conn.commit()
    stale_conn.close()
    stale_episode_hits = module.episode_semantic_search(
        aoa_root=aoa_root,
        query="audit session memory MCP hook",
        limit=5,
    )
    stale_entity_state = module.episode_entity_state_search(
        aoa_root=aoa_root,
        anchor="exec_command",
        kind="tool",
        session="agent-events",
        limit=10,
    )
    assert stale_episode_hits["result_count"] == 0
    assert stale_entity_state["result_count"] == 0
    assert stale_entity_state["projection"]["route_available"] is False
    stale_conn = sqlite3.connect(module.search_db_path(aoa_root))
    stale_conn.execute(
        "UPDATE episode_semantic_meta SET projection_version = ?",
        (module.EPISODE_SEMANTIC_PROJECTION_VERSION,),
    )
    stale_conn.execute(
        "UPDATE episode_semantic_session_state SET projection_version = ?",
        (module.EPISODE_SEMANTIC_PROJECTION_VERSION,),
    )
    stale_conn.commit()
    stale_conn.close()
    audit = module.agent_event_audit(
        aoa_root=aoa_root,
        target="latest",
        sample_limit=2,
        probe_routes=True,
        route_probe_limit=2,
    )
    assert audit["stream_canonical_neighbor_pair_count"] >= 1
    assert audit["stream_canonical_retrieval_guard_ok"] is True
    assert audit["quality_ok"] is True
    route_probes = {probe["route"]: probe for probe in audit["route_probes"]}
    assert route_probes["agent-reasoning-windows"]["route_kind"] == "window_route"
    assert route_probes["agent-reasoning-windows"]["window_count"] == 1
    assert route_probes["agent-reasoning-windows"]["sample_refs"][0]["agent_event"] == "assistant_reasoning_boundary"
    assert route_probes["agent-reasoning-windows"]["sample_refs"][0]["raw_ref"] == "raw:line:3"
    assert audit["raw_shape_samples"]
    assert any(sample["raw_shape"]["payload_type"] == "message" for sample in audit["raw_shape_samples"])
    ordered_audit = module.agent_event_audit(
        aoa_root=aoa_root,
        target="all",
        order="longest",
        min_events=1,
        limit=1,
    )
    assert ordered_audit["order"] == "longest"
    assert ordered_audit["selected_count"] == 1
    assert ordered_audit["selected_sessions"][0]["event_count"] >= 1
    monkeypatch.setattr(module, "compact_stamp", lambda: "20260614T000000Z")
    first_report = module.agent_event_audit(aoa_root=aoa_root, target="latest", write_report=True)
    second_report = module.agent_event_audit(aoa_root=aoa_root, target="latest", write_report=True)
    assert first_report["quality_ok"] is True
    assert first_report["report_json"] != second_report["report_json"]
    assert first_report["report_json"].endswith("__agent-event-audit.json")
    assert second_report["report_json"].endswith("__agent-event-audit__01.json")
    assert Path(first_report["report_json"]).exists()
    assert Path(second_report["report_json"]).exists()
    closeouts = module.search_sessions(aoa_root=aoa_root, doc_type="event", agent_event="assistant_final_closeout", limit=5)
    assert closeouts["result_count"] == 1
    assert closeouts["results"][0]["agent_event"] == "assistant_final_closeout"
    assert closeouts["results"][0]["task_episode_id"] == "task-0001"
    assert closeouts["results"][0]["freshness"]["basis"] == "indexed_snapshot"
    assert closeouts["cost_profile"]["lightweight_route"] is True
    assert closeouts["cost_profile"]["uses_fts"] is False
    assert closeouts["cost_profile"]["hydrates_body"] is False
    assert closeouts["cost_profile"]["semantic_preview"] is False
    default_response_route = module.agent_event_route_search(
        aoa_root=aoa_root,
        session=session_dir.name,
        limit=20,
    )
    assert default_response_route["result_count"] >= 1
    assert default_response_route["cost_profile"]["lightweight_route"] is True
    assert default_response_route["cost_profile"]["hydrates_body"] is False
    assert default_response_route["cost_profile"]["semantic_preview"] is False
    assert all(item["agent_event"] != "assistant_open_thread" for item in default_response_route["results"])
    open_thread_route = module.agent_event_route_search(
        aoa_root=aoa_root,
        session=session_dir.name,
        agent_events=["assistant_open_thread"],
        limit=5,
    )
    assert open_thread_route["result_count"] == 1
    assert open_thread_route["results"][0]["agent_event"] == "assistant_open_thread"
    assert open_thread_route["results"][0]["event_id"] == open_thread["event_id"]
    open_thread_alias_route = module.agent_event_route_search(
        aoa_root=aoa_root,
        session=session_dir.name,
        agent_events=["open_thread"],
        limit=5,
    )
    assert open_thread_alias_route["agent_events"] == ["assistant_open_thread"]
    assert open_thread_alias_route["requested_agent_events"] == ["open_thread"]
    assert open_thread_alias_route["result_count"] == 1
    assert open_thread_alias_route["results"][0]["event_id"] == open_thread["event_id"]
    open_thread_search_alias = module.search_sessions(
        aoa_root=aoa_root,
        session=session_dir.name,
        doc_type="event",
        agent_event="open_thread",
        limit=5,
    )
    assert open_thread_search_alias["result_count"] == 1
    assert open_thread_search_alias["results"][0]["agent_event"] == "assistant_open_thread"
    assert open_thread_search_alias["results"][0]["event_id"] == open_thread["event_id"]
    progress_route = module.agent_event_route_search(
        aoa_root=aoa_root,
        session=session_dir.name,
        agent_events=["assistant_progress_update"],
        limit=10,
    )
    assert progress_route["result_count"] == 2
    assert progress_route["search_projection"]["route_kind"] == "agent_event_session_segment_index"
    assert progress_route["cost_profile"]["uses_session_segment_indexes"] is True
    assert {item["event_id"] for item in progress_route["results"]} == {"000005", "000008"}
    assert all(item["agent_event_source"] != "event_msg_stream" for item in progress_route["results"])
    progress_hit = progress_route["results"][0]
    assert progress_hit["raw_ref"] == progress_hit["refs"]["raw"]
    assert progress_hit["raw_line"] == int(progress_hit["raw_ref"].split(":")[-1])
    assert progress_hit["segment_ref"] == progress_hit["refs"]["segment"]
    assert progress_hit["segment_index"] == progress_hit["refs"]["segment_index"]
    assert progress_hit["session_ref"] == progress_hit["refs"]["session"]
    assert progress_hit["preview"] == progress_hit["bounded_preview"]
    assert progress_hit["preview_source"] in {"raw_block_semantic_text", "raw_semantic_text"}
    assert "route_signal" not in progress_hit["bounded_preview"]
    assert progress_hit["bounded_preview"]
    assert any(text in progress_hit["bounded_preview"] for text in ["Сейчас проверяю", "Почти готово"])
    progress_with_stream = module.agent_event_route_search(
        aoa_root=aoa_root,
        session=session_dir.name,
        agent_events=["assistant_progress_update"],
        limit=10,
        include_stream_copies=True,
    )
    assert progress_with_stream["result_count"] == 3
    assert "event_msg_stream" in {item["agent_event_source"] for item in progress_with_stream["results"]}
    episodes = module.search_sessions(aoa_root=aoa_root, doc_type="task_episode", limit=5)
    assert episodes["result_count"] == 2
    windows = module.agent_event_windows(
        aoa_root=aoa_root,
        agent_events=["assistant_reasoning_boundary"],
        limit=1,
        before=1,
        after=2,
    )
    assert windows["window_count"] == 1
    assert windows["windows"][0]["ok"] is True
    reasoning_window = windows["windows"][0]
    assert reasoning_window["raw_ref"] == reasoning_window["refs"]["raw"]
    assert reasoning_window["raw_line"] == int(reasoning_window["raw_ref"].split(":")[-1])
    assert reasoning_window["segment_ref"] == reasoning_window["refs"]["segment"]
    assert reasoning_window["segment_index"] == reasoning_window["refs"]["segment_index"]
    assert reasoning_window["session_ref"] == reasoning_window["refs"]["session"]
    assert reasoning_window["anchor"]["event_id"] == reasoning_window["event_id"]
    assert reasoning_window["center"]["event_id"] == reasoning_window["event_id"]
    assert reasoning_window["preview_source"] == "raw_semantic_text"
    assert reasoning_window["bounded_preview"]
    assert "Need inspect source" in reasoning_window["bounded_preview"]
    windows_without_explain = module.agent_event_windows(
        aoa_root=aoa_root,
        agent_events=["assistant_reasoning_boundary"],
        limit=1,
        before=1,
        after=2,
        explain=False,
    )
    assert windows_without_explain["window_count"] == 1
    assert "explain" not in windows_without_explain["results"][0]
def test_search_event_inside_task_interval_keeps_episode_join_when_not_a_curated_ref(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = (
        tmp_path
        / "rollout-2026-07-11T00-00-00-episode-interval-search.jsonl"
    )
    write_jsonl(
        transcript,
        [
            {
                "timestamp": "2026-07-11T00:00:00Z",
                "type": "session_meta",
                "payload": {
                    "id": "episode-interval-search",
                    "cwd": str(workspace),
                },
            },
            {
                "timestamp": "2026-07-11T00:00:01Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "Review the live skill dispatch receipt.",
                        }
                    ],
                },
            },
            {
                "timestamp": "2026-07-11T00:00:02Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "exec_command",
                    "call_id": "call-receipt",
                    "arguments": json.dumps(
                        {"cmd": "show reviewed receipt"}
                    ),
                },
            },
            {
                "timestamp": "2026-07-11T00:00:03Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "call-receipt",
                    "output": (
                        "direct_procedure_gap\n"
                        + ("large reviewed receipt row\n" * 300)
                    ),
                },
            },
            {
                "timestamp": "2026-07-11T00:00:04Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",
                            "text": "Receipt review complete.",
                        }
                    ],
                },
            },
        ],
    )

    module.handle_hook_event(
        "Stop",
        {
            "session_id": "episode-interval-search",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    session_dir = next(
        path
        for path in (aoa_root / "sessions").iterdir()
        if path.is_dir()
    )
    session_index = module.read_json(
        session_dir / "session.index.json",
        {},
    )
    episode = module.session_index_task_episode_components(
        session_dir,
        session_index,
    )[0]
    assert episode["event_range"]["from_line"] == 2
    assert episode["event_range"]["to_line"] == 5
    assert all(
        str(ref.get("raw_ref") or "") != "raw:line:4"
        for bucket in (
            "reasoning_refs",
            "plan_refs",
            "progress_refs",
            "answer_refs",
            "action_refs",
            "tool_refs",
            "verification_refs",
            "error_refs",
            "closeout_refs",
            "blocker_refs",
            "transition_refs",
        )
        for ref in episode.get(bucket, [])
        if isinstance(ref, dict)
    )

    index_result = module.search_index_sessions(
        aoa_root=aoa_root,
        target="all",
        rebuild=True,
    )
    assert index_result["ok"] is True
    result = module.search_sessions(
        aoa_root=aoa_root,
        query="direct_procedure_gap",
        session=session_dir.name,
        task_episode_id=episode["episode_id"],
        limit=5,
        explain=True,
    )
    assert result["ok"] is True
    assert result["result_count"] == 1
    assert result["results"][0]["task_episode_id"] == (
        episode["episode_id"]
    )
    assert result["results"][0]["raw_ref"] == "raw:line:4"
    assert result["results"][0]["refs"]["raw"] == "raw:line:4"
def test_task_episode_semantics_admits_compact_success_observation_but_not_source_dump() -> None:
    rows = [
        {
            "timestamp": "2026-06-11T01:29:23Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "Inspect the terminal stack before installing Ghostty"}],
            },
        },
        {
            "timestamp": "2026-06-11T01:30:05Z",
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "exec_command",
                "arguments": json.dumps({"cmd": "dnf list --installed zsh tmux fzf starship ghostty 2>/dev/null || true"}),
                "call_id": "call-package-probe",
            },
        },
        {
            "timestamp": "2026-06-11T01:30:14Z",
            "type": "response_item",
            "payload": {
                "type": "function_call_output",
                "call_id": "call-package-probe",
                "output": (
                    "Chunk ID: probe\nWall time: 0.1 seconds\nProcess exited with code 0\n"
                    "Original token count: 20\nOutput:\nInstalled packages\n"
                    "fzf.x86_64 0.73\ntmux.x86_64 3.6b\nzsh.x86_64 5.9\n"
                ),
            },
        },
        {
            "timestamp": "2026-06-11T01:30:20Z",
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "exec_command",
                "arguments": json.dumps({"cmd": "sed -n '1,220p' /srv/example/AbyssOS/.aoa/skills/aoa-session-memory-global-route/SKILL.md"}),
                "call_id": "call-source-read",
            },
        },
        {
            "timestamp": "2026-06-11T01:30:21Z",
            "type": "response_item",
            "payload": {
                "type": "function_call_output",
                "call_id": "call-source-read",
                "output": (
                    "Chunk ID: source\nWall time: 0.1 seconds\nProcess exited with code 0\n"
                    "Original token count: 2000\nOutput:\n"
                    + "python scripts/aoa_session_memory.py hook worker; MCP session memory docs\n" * 80
                ),
            },
        },
    ]
    events = [
        module.classify_raw_event(json.dumps(row, ensure_ascii=False), row, line_no)
        for line_no, row in enumerate(rows, start=1)
    ]

    episode = module.generated_task_episodes_for_events(events, [])[0]
    outcomes = episode["representations"]["outcomes"]
    compact = [item for item in outcomes if item.get("admission_basis") == "structured_compact_success_observation"]

    assert compact
    assert "tmux.x86_64 3.6b" in compact[0]["text"]
    assert compact[0]["refs"]["raw"] == "raw:line:3"
    assert "MCP session memory docs" not in episode["semantic_text"]
    assert any(
        item.get("admission_basis") == "structured_result_status" and item["refs"]["raw"] == "raw:line:5"
        for item in outcomes
    )
    source_read = next(item for item in episode["representations"]["actions"] if item["refs"]["raw"] == "raw:line:4")
    source_result = next(item for item in outcomes if item["refs"]["raw"] == "raw:line:5")
    source_relations = {
        (anchor["layer"], anchor["key"], anchor["relation"])
        for anchor in source_read["typed_anchors"]
    }
    assert ("tool", "exec_command", "invoked") in source_relations
    assert ("skill", "aoa_session_memory_global_route", "inspected") in source_relations
    assert source_result.get("typed_anchors", []) == []
def test_task_episode_builder_computes_semantic_text_once_per_event(
    monkeypatch: Any,
) -> None:
    rows = [
        {
            "timestamp": "2026-08-11T00:00:00Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": "Inspect the current projection",
                    }
                ],
            },
        },
        {
            "timestamp": "2026-08-11T00:00:01Z",
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "exec_command",
                "arguments": json.dumps({"cmd": "session-memory status"}),
                "call_id": "call-semantic-once",
            },
        },
        {
            "timestamp": "2026-08-11T00:00:02Z",
            "type": "response_item",
            "payload": {
                "type": "function_call_output",
                "call_id": "call-semantic-once",
                "output": "Process exited with code 0",
            },
        },
    ]
    events = [
        module.classify_raw_event(json.dumps(row), row, line_no)
        for line_no, row in enumerate(rows, start=1)
    ]
    original = module.event_semantic_text
    observed_lines: list[int] = []

    def counted(event: Any) -> str:
        observed_lines.append(event.line_no)
        return original(event)

    monkeypatch.setattr(module, "event_semantic_text", counted)
    episodes = module.generated_task_episodes_for_events(events, [])

    assert episodes
    assert observed_lines == [1, 2, 3]
def test_segment_for_line_uses_ordered_ranges_without_losing_boundaries() -> None:
    segments = [
        {
            "segment_id": f"{ordinal:03d}",
            "source_range": {
                "from_line": (ordinal * 10) + 1,
                "to_line": (ordinal * 10) + 8,
            },
        }
        for ordinal in range(644)
    ]

    assert module.segment_for_line(segments, 1)["segment_id"] == "000"
    assert module.segment_for_line(segments, 3211)["segment_id"] == "321"
    assert module.segment_for_line(segments, 6438)["segment_id"] == "643"
    assert module.segment_for_line(segments, 9) == {}
    assert module.segment_for_line(segments, 0) == {}
    assert module.segment_for_line([], 1) == {}
def test_task_episode_replayed_intent_after_turn_abort_stays_in_one_semantic_lifecycle() -> None:
    rows = [
        {
            "timestamp": "2026-06-12T02:41:08Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": "Надо распространить по остальным репо",
                    }
                ],
            },
        },
        {
            "timestamp": "2026-06-12T02:41:09Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "<turn_aborted>\n"
                            "The user interrupted the previous turn on purpose.\n"
                            "</turn_aborted>"
                        ),
                    }
                ],
            },
        },
        {
            "timestamp": "2026-06-12T02:41:09.500Z",
            "type": "event_msg",
            "payload": {"type": "turn_aborted", "turn_id": "turn-one"},
        },
        {
            "timestamp": "2026-06-12T02:41:21Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": "Надо распространить по остальным репо",
                    }
                ],
            },
        },
        {
            "timestamp": "2026-06-12T02:41:44Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": "Сначала построю карту остальных репозиториев.",
                    }
                ],
            },
        },
    ]
    events = [
        module.classify_raw_event(json.dumps(row, ensure_ascii=False), row, line_no)
        for line_no, row in enumerate(rows, start=1)
    ]

    episodes = module.generated_task_episodes_for_events(events, [])

    assert len(episodes) == 1
    episode = episodes[0]
    assert episode["event_range"] == {
        "from_event_id": "000001",
        "to_event_id": "000005",
        "from_line": 1,
        "to_line": 5,
    }
    assert [item["raw_ref"] for item in episode["intent_refs"]] == [
        "raw:line:1",
        "raw:line:4",
    ]
    assert [
        (item["relation"], item["raw_ref"])
        for item in episode["semantic_continuations"]
    ] == [("replayed_intent", "raw:line:4")]
    assert {
        item["raw_ref"]
        for item in episode["transition_refs"]
    } >= {"raw:line:2"}
    assert "<turn_aborted>" not in episode["semantic_text"]
    assert "interrupted_by_new_user_prompt" not in episode["ambiguity_flags"]
def test_task_episode_filters_runtime_content_items_but_keeps_mixed_operator_intent() -> None:
    rows = [
        {
            "timestamp": "2026-07-20T01:00:00Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "<recommended_plugins>\n"
                            "Use the repository helper.\n"
                            "</recommended_plugins>"
                        ),
                    },
                    {
                        "type": "input_text",
                        "text": (
                            "# AGENTS.md instructions for /workspace\n"
                            "<INSTRUCTIONS>Keep owner evidence authoritative.</INSTRUCTIONS>"
                        ),
                    },
                    {
                        "type": "input_text",
                        "text": (
                            "<environment_context><cwd>/workspace</cwd>"
                            "</environment_context>"
                        ),
                    },
                    {
                        "type": "input_text",
                        "text": (
                            "Проверь конкретную causal chain и сохрани raw refs."
                        ),
                    },
                ],
            },
        },
        {
            "timestamp": "2026-07-20T01:00:01Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": "Готово: causal chain проверена.",
                    }
                ],
            },
        },
    ]
    events = [
        module.classify_raw_event(
            json.dumps(row, ensure_ascii=False),
            row,
            line_no,
        )
        for line_no, row in enumerate(rows, start=1)
    ]

    user_event = events[0]
    components = user_event.facets["runtime_context_components"]
    assert components["runtime_component_count"] == 3
    assert components["operator_component_count"] == 1
    assert components["mixed_runtime_and_operator"] is True
    assert "source_envelope" not in user_event.facets
    assert user_event.facets["conversation_act"]["kind"] == (
        "operator_instruction"
    )

    episode = module.generated_task_episodes_for_events(events, [])[0]
    assert episode["intent"] == (
        "Проверь конкретную causal chain и сохрани raw refs."
    )
    assert "<recommended_plugins>" not in episode["semantic_text"]
    assert "AGENTS.md instructions" not in episode["semantic_text"]
    assert "<environment_context>" not in episode["semantic_text"]
def test_task_episode_accepts_only_correlation_matched_explicit_verification_result() -> None:
    rows = [
        {
            "timestamp": "2026-07-20T02:00:00Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": "Проверь topology validator и focused tests.",
                    }
                ],
            },
        },
        {
            "timestamp": "2026-07-20T02:00:01Z",
            "type": "response_item",
            "payload": {
                "type": "custom_tool_call",
                "name": "exec",
                "call_id": "call-verification",
                "input": (
                    "const r = await tools.exec_command({"
                    '"cmd":"python scripts/validate_topology.py && '
                    'python -m pytest -q tests/test_topology.py"'
                    "}); text(r.output);"
                ),
            },
        },
        {
            "timestamp": "2026-07-20T02:00:02Z",
            "type": "response_item",
            "payload": {
                "type": "custom_tool_call_output",
                "call_id": "call-verification",
                "output": [
                    {
                        "type": "input_text",
                        "text": (
                            "Script completed\nOutput:\n"
                            "[ok] topology\n14 passed in 0.09s"
                        ),
                    }
                ],
            },
        },
        {
            "timestamp": "2026-07-20T02:00:03Z",
            "type": "response_item",
            "payload": {
                "type": "custom_tool_call_output",
                "call_id": "call-foreign",
                "output": [
                    {
                        "type": "input_text",
                        "text": "Script completed\nOutput:\n99 passed",
                    }
                ],
            },
        },
        {
            "timestamp": "2026-07-20T02:00:04Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": "Готово: validator и tests проверены.",
                    }
                ],
            },
        },
    ]
    events = [
        module.classify_raw_event(
            json.dumps(row, ensure_ascii=False),
            row,
            line_no,
        )
        for line_no, row in enumerate(rows, start=1)
    ]

    assert events[1].facets["command_kind"] == "verification"
    assert events[1].event_type == "COMMAND"
    episode = module.generated_task_episodes_for_events(events, [])[0]
    assert {
        ref["raw_ref"]
        for ref in episode["verification_refs"]
    } == {"raw:line:2", "raw:line:3"}
    verification = episode["representations"]["verification"]
    assert len(verification) == 1
    assert verification[0]["refs"]["raw"] == "raw:line:3"
    assert verification[0]["admission_basis"] == (
        "correlation_matched_structured_verification_result"
    )
    assert verification[0]["correlation_id"] == "call-verification"
    assert all(
        item["refs"]["raw"] != "raw:line:4"
        for item in verification
    )
def test_runtime_complete_overrides_only_noncanonical_stream_terminal_status() -> None:
    def build(blocker_source: str) -> dict[str, Any]:
        blocker = (
            {
                "timestamp": "2026-07-20T03:00:01Z",
                "type": "event_msg",
                "payload": {
                    "type": "agent_message",
                    "message": "Blocked: cannot proceed without a dependency.",
                },
            }
            if blocker_source == "stream"
            else {
                "timestamp": "2026-07-20T03:00:01Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",
                            "text": (
                                "Blocked: cannot proceed without a dependency."
                            ),
                        }
                    ],
                },
            }
        )
        rows = [
            {
                "timestamp": "2026-07-20T03:00:00Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "Проверь текущий slice.",
                        }
                    ],
                },
            },
            blocker,
            {
                "timestamp": "2026-07-20T03:00:02Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",
                            "text": "Checkpoint: bounded slice inspected.",
                        }
                    ],
                },
            },
            {
                "timestamp": "2026-07-20T03:00:03Z",
                "type": "event_msg",
                "payload": {
                    "type": "task_complete",
                    "turn_id": "turn-proof",
                },
            },
        ]
        events = [
            module.classify_raw_event(
                json.dumps(row, ensure_ascii=False),
                row,
                line_no,
            )
            for line_no, row in enumerate(rows, start=1)
        ]
        return module.generated_task_episodes_for_events(
            events,
            [],
        )[0]

    stream_episode = build("stream")
    canonical_episode = build("canonical")

    assert stream_episode["status"] == "closed"
    assert (
        "noncanonical_terminal_status_overridden_by_runtime_complete"
        in stream_episode["ambiguity_flags"]
    )
    assert canonical_episode["status"] == "blocked"
    assert (
        "noncanonical_terminal_status_overridden_by_runtime_complete"
        not in canonical_episode["ambiguity_flags"]
    )
def test_task_episode_failure_observation_and_resume_stay_with_open_lifecycle() -> None:
    rows = [
        {
            "timestamp": "2026-06-11T01:29:23Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": "Поставь мне эту связку Ghostty + tmux + zsh + fzf + starship",
                    }
                ],
            },
        },
        {
            "timestamp": "2026-06-11T01:36:05Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": "Сейчас проверяю zsh и fzf.",
                    }
                ],
            },
        },
        {
            "timestamp": "2026-06-11T01:55:19Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "<turn_aborted>\n"
                            "The user interrupted the previous turn on purpose.\n"
                            "</turn_aborted>"
                        ),
                    }
                ],
            },
        },
        {
            "timestamp": "2026-06-11T01:55:21Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "Ты завис"}],
            },
        },
        {
            "timestamp": "2026-06-11T01:58:33Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": "На связи. Я слишком долго не дал нормальный статус.",
                    }
                ],
            },
        },
        {
            "timestamp": "2026-06-11T01:58:37Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "????"}],
            },
        },
        {
            "timestamp": "2026-06-11T01:59:07Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "Продолжай"}],
            },
        },
        {
            "timestamp": "2026-06-11T01:59:27Z",
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "exec_command",
                "call_id": "call-resume",
                "arguments": json.dumps({"cmd": "ghostty --version"}),
            },
        },
        {
            "timestamp": "2026-06-11T01:59:28Z",
            "type": "response_item",
            "payload": {
                "type": "function_call_output",
                "call_id": "call-resume",
                "output": "Process exited with code 0\nOutput:\nghostty 1.3.1",
            },
        },
        {
            "timestamp": "2026-06-11T01:59:36Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": "Готово. Итог: Ghostty установлен и проверен.",
                    }
                ],
            },
        },
    ]
    events = [
        module.classify_raw_event(json.dumps(row, ensure_ascii=False), row, line_no)
        for line_no, row in enumerate(rows, start=1)
    ]

    episodes = module.generated_task_episodes_for_events(events, [])

    assert len(episodes) == 1
    episode = episodes[0]
    assert episode["status"] == "closed"
    assert [item["raw_ref"] for item in episode["intent_refs"]] == [
        "raw:line:1",
        "raw:line:4",
        "raw:line:6",
        "raw:line:7",
    ]
    assert [
        item["relation"]
        for item in episode["semantic_continuations"]
    ] == [
        "failure_observation",
        "failure_observation",
        "resume",
    ]
    assert any(
        item["refs"]["raw"] == "raw:line:8"
        for item in episode["representations"]["actions"]
    )
    assert any(
        item["refs"]["raw"] == "raw:line:9"
        for item in episode["representations"]["outcomes"]
    )
def test_task_episode_real_context_addition_bridges_runtime_turn_boundary() -> None:
    rows = [
        {
            "timestamp": "2026-06-13T17:26:26Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "Тут как-будто нужен aoa-eval-skill с подскиллами, "
                            "чтобы проверять доступные evals и применять их."
                        ),
                    }
                ],
            },
        },
        {
            "timestamp": "2026-06-13T17:27:30Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": (
                            "После MCP/local ports следующий орган — "
                            "aoa-eval skill family."
                        ),
                    }
                ],
            },
        },
        {
            "timestamp": "2026-06-13T17:27:33Z",
            "type": "event_msg",
            "payload": {
                "type": "task_complete",
                "turn_id": "turn-plan",
            },
        },
        {
            "timestamp": "2026-06-13T17:29:55Z",
            "type": "event_msg",
            "payload": {
                "type": "task_started",
                "turn_id": "turn-context-addition",
            },
        },
        {
            "timestamp": "2026-06-13T17:29:55.100Z",
            "type": "turn_context",
            "payload": {
                "turn_id": "turn-context-addition",
            },
        },
        {
            "timestamp": "2026-06-13T17:29:56Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "Да, всё именно так. Но ещё бы лучше на каждый "
                            "перечисленный тобою пункт изучил бы инфу в вебе "
                            "и всех репо, перед тем как пойти в сессии."
                        ),
                    }
                ],
            },
        },
    ]
    events = [
        module.classify_raw_event(
            json.dumps(row, ensure_ascii=False),
            row,
            line_no,
        )
        for line_no, row in enumerate(rows, start=1)
    ]

    episodes = module.generated_task_episodes_for_events(events, [])

    assert len(episodes) == 1
    assert events[5].facets["conversation_act"]["kind"] == (
        "operator_context_addition"
    )
    episode = episodes[0]
    assert [item["raw_ref"] for item in episode["intent_refs"]] == [
        "raw:line:1",
        "raw:line:6",
    ]
    assert len(episode["semantic_continuations"]) == 1
    continuation = episode["semantic_continuations"][0]
    assert continuation["event_id"] == "000006"
    assert continuation["raw_ref"] == "raw:line:6"
    assert continuation["conversation_act"] == "operator_context_addition"
    assert continuation["relation"] == "context_addition"
    assert continuation["admission_basis"] == (
        "typed_operator_conversation_act"
    )
    assert (
        "runtime_turn_boundary_bridged_by_typed_continuation"
        in episode["ambiguity_flags"]
    )
    assert any(
        ref["raw_ref"] == "raw:line:4"
        and ref.get("runtime_boundary_role")
        == "bridged_runtime_task_started"
        for ref in episode["transition_refs"]
    )
    assert any(
        item["refs"]["raw"] == "raw:line:6"
        and item["semantic_continuation_relation"] == "context_addition"
        for item in episode["representations"]["intents"]
    )
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("И ещё учти ограничение по времени.", True),
        ("Дополнение: не изменяй канонический репозиторий.", True),
        ("Also keep in mind the repository is frozen.", True),
        ("Теперь новая задача: подготовь отчёт по календарю.", False),
        ("И ещё одна новая задача: подготовь отчёт по календарю.", False),
        ("Перейдём к другой задаче.", False),
    ],
)
def test_operator_context_addition_signal_is_bounded(
    text: str,
    expected: bool,
) -> None:
    assert module.operator_context_addition_signal(text) is expected
def test_task_episode_standalone_context_addition_starts_one_lifecycle() -> None:
    rows = [
        {
            "timestamp": "2026-07-18T00:00:02Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": "И ещё учти ограничение по времени.",
                    }
                ],
            },
        },
    ]
    events = [
        module.classify_raw_event(
            json.dumps(row, ensure_ascii=False),
            row,
            line_no,
        )
        for line_no, row in enumerate(rows, start=1)
    ]

    episodes = module.generated_task_episodes_for_events(events, [])

    assert len(episodes) == 1
    assert episodes[0]["event_range"]["from_line"] == 1
    assert episodes[0]["transition"]["reason"] == "operator_context_addition"
    assert episodes[0]["semantic_continuations"] == []
def test_task_episode_unrelated_prompt_adopts_empty_runtime_turn_boundary() -> None:
    rows = [
        {
            "timestamp": "2026-07-18T00:00:00Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": "Проверь индексы aoa-session-memory",
                    }
                ],
            },
        },
        {
            "timestamp": "2026-07-18T00:00:01Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": "Индексы проверены.",
                    }
                ],
            },
        },
        {
            "timestamp": "2026-07-18T00:00:02Z",
            "type": "event_msg",
            "payload": {
                "type": "task_complete",
                "turn_id": "turn-indexes",
            },
        },
        {
            "timestamp": "2026-07-18T00:01:00Z",
            "type": "event_msg",
            "payload": {
                "type": "task_started",
                "turn_id": "turn-calendar",
            },
        },
        {
            "timestamp": "2026-07-18T00:01:00.100Z",
            "type": "turn_context",
            "payload": {
                "turn_id": "turn-calendar",
            },
        },
        {
            "timestamp": "2026-07-18T00:01:01Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": "Подготовь отдельный отчёт по календарю",
                    }
                ],
            },
        },
    ]
    events = [
        module.classify_raw_event(
            json.dumps(row, ensure_ascii=False),
            row,
            line_no,
        )
        for line_no, row in enumerate(rows, start=1)
    ]

    episodes = module.generated_task_episodes_for_events(events, [])

    assert len(episodes) == 2
    assert episodes[0]["event_range"]["to_line"] == 3
    second = episodes[1]
    assert second["event_range"]["from_line"] == 4
    assert second["intent_refs"][0]["raw_ref"] == "raw:line:6"
    assert second["transition"]["previous_episode_id"] == "task-0001"
    assert second["transition"]["first_semantic_intent_ref"] == (
        "raw:line:6"
    )
    assert second["transition"]["user_conversation_act"] == (
        "operator_instruction"
    )
    assert second["semantic_continuations"] == []
def test_task_episode_generic_exact_prompt_does_not_bridge_runtime_turn() -> None:
    rows = [
        {
            "timestamp": "2026-06-18T23:51:04Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": "Давай",
                    }
                ],
            },
        },
        {
            "timestamp": "2026-06-18T23:57:47Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": "Практический smoke завершён.",
                    }
                ],
            },
        },
        {
            "timestamp": "2026-06-18T23:57:50Z",
            "type": "event_msg",
            "payload": {
                "type": "task_complete",
                "turn_id": "turn-smoke",
            },
        },
        {
            "timestamp": "2026-06-18T23:58:24Z",
            "type": "event_msg",
            "payload": {
                "type": "task_started",
                "turn_id": "turn-next",
            },
        },
        {
            "timestamp": "2026-06-18T23:58:26Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": "Давай",
                    }
                ],
            },
        },
    ]
    events = [
        module.classify_raw_event(
            json.dumps(row, ensure_ascii=False),
            row,
            line_no,
        )
        for line_no, row in enumerate(rows, start=1)
    ]

    episodes = module.generated_task_episodes_for_events(events, [])

    assert len(episodes) == 2
    assert episodes[0]["intent_refs"][0]["raw_ref"] == "raw:line:1"
    assert episodes[1]["intent_refs"][0]["raw_ref"] == "raw:line:5"
    assert episodes[1]["transition"]["first_semantic_intent_ref"] == (
        "raw:line:5"
    )
    assert episodes[1]["semantic_continuations"] == []
    assert not any(
        "runtime_turn_boundary_bridged_by_typed_continuation"
        in episode["ambiguity_flags"]
        for episode in episodes
    )
def test_task_episode_context_addition_does_not_bridge_evidence_bearing_runtime_episode() -> None:
    rows = [
        {
            "timestamp": "2026-07-18T00:00:00Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": "Проверь индексы aoa-session-memory",
                    }
                ],
            },
        },
        {
            "timestamp": "2026-07-18T00:00:01Z",
            "type": "event_msg",
            "payload": {
                "type": "task_complete",
                "turn_id": "turn-indexes",
            },
        },
        {
            "timestamp": "2026-07-18T00:01:00Z",
            "type": "event_msg",
            "payload": {
                "type": "task_started",
                "turn_id": "turn-intervening",
            },
        },
        {
            "timestamp": "2026-07-18T00:01:00.500Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": "Выполняю отдельное восстановление runtime.",
                    }
                ],
            },
        },
        {
            "timestamp": "2026-07-18T00:01:01Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": "И ещё учти ограничение по времени.",
                    }
                ],
            },
        },
    ]
    events = [
        module.classify_raw_event(
            json.dumps(row, ensure_ascii=False),
            row,
            line_no,
        )
        for line_no, row in enumerate(rows, start=1)
    ]

    episodes = module.generated_task_episodes_for_events(events, [])

    assert len(episodes) == 2
    assert episodes[0]["intent_refs"][0]["raw_ref"] == "raw:line:1"
    assert any(
        ref["raw_ref"] == "raw:line:4"
        for ref in episodes[1]["answer_refs"]
    )
    assert any(
        continuation["raw_ref"] == "raw:line:5"
        and continuation["relation"] == "context_addition"
        for continuation in episodes[1]["semantic_continuations"]
    )
    assert not any(
        "runtime_turn_boundary_bridged_by_typed_continuation"
        in episode["ambiguity_flags"]
        for episode in episodes
    )
def test_task_episode_unrelated_open_task_prompt_remains_a_new_episode() -> None:
    rows = [
        {
            "timestamp": "2026-07-18T00:00:00Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": "Проверь индексы aoa-session-memory",
                    }
                ],
            },
        },
        {
            "timestamp": "2026-07-18T00:00:01Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": "Сейчас читаю состояние индексов.",
                    }
                ],
            },
        },
        {
            "timestamp": "2026-07-18T00:00:02Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": "Подготовь отдельный отчет по календарю",
                    }
                ],
            },
        },
        {
            "timestamp": "2026-07-18T00:00:03Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": "Перехожу к отдельному отчету.",
                    }
                ],
            },
        },
    ]
    events = [
        module.classify_raw_event(json.dumps(row, ensure_ascii=False), row, line_no)
        for line_no, row in enumerate(rows, start=1)
    ]

    episodes = module.generated_task_episodes_for_events(events, [])

    assert len(episodes) == 2
    assert episodes[0]["event_range"]["to_line"] == 2
    assert episodes[1]["event_range"]["from_line"] == 3
    assert episodes[1]["transition"]["previous_episode_id"] == "task-0001"
    assert episodes[1]["semantic_continuations"] == []
def test_fork_lineage_splits_replayed_history_from_local_work_and_closes_on_task_complete() -> None:
    child_session_id = "11111111-2222-4333-8444-555555555555"
    parent_session_id = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
    declared_timestamp = "2026-07-10T22:19:38Z"
    declared_epoch = module.parse_utc_timestamp(declared_timestamp).timestamp()
    rows = [
        {
            "timestamp": declared_timestamp,
            "type": "session_meta",
            "payload": {
                "id": child_session_id,
                "timestamp": declared_timestamp,
                "session_id": parent_session_id,
                "forked_from_id": parent_session_id,
                "parent_thread_id": parent_session_id,
                "thread_source": "subagent",
                "history_mode": "legacy",
                "source": {
                    "subagent": {
                        "thread_spawn": {
                            "parent_thread_id": parent_session_id,
                            "agent_path": "/root/evidence_consistency",
                            "agent_nickname": "Socrates",
                            "depth": 1,
                        }
                    }
                },
            },
        },
        {
            "timestamp": "2026-07-10T20:00:00Z",
            "type": "session_meta",
            "payload": {"id": parent_session_id, "timestamp": "2026-07-10T20:00:00Z"},
        },
        {
            "timestamp": "2026-07-10T20:00:01Z",
            "type": "event_msg",
            "payload": {"type": "task_started", "turn_id": "parent-turn", "started_at": declared_epoch - 1000},
        },
        {
            "timestamp": "2026-07-10T20:00:02Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "Inspect the parent canary state"}],
            },
        },
        {
            "timestamp": "2026-07-10T20:00:03Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "The parent investigation is still in progress."}],
            },
        },
        {
            "timestamp": declared_timestamp,
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "developer",
                "content": [
                    {
                        "type": "input_text",
                        "text": "You are an agent in a team of agents collaborating to complete a task.",
                    }
                ],
            },
        },
        {
            "timestamp": "2026-07-10T22:19:39Z",
            "type": "event_msg",
            "payload": {"type": "task_started", "turn_id": "child-turn", "started_at": declared_epoch + 1},
        },
        {
            "timestamp": "2026-07-10T22:19:40Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "Now inspect provenance in the child task."}],
            },
        },
        {
            "timestamp": "2026-07-10T22:19:41Z",
            "type": "event_msg",
            "payload": {"type": "task_complete", "turn_id": "child-turn"},
        },
    ]
    events = [
        module.classify_raw_event(json.dumps(row, ensure_ascii=False), row, line_no)
        for line_no, row in enumerate(rows, start=1)
    ]

    lineage = module.session_lineage_for_events(events, session_id=child_session_id)
    episodes = module.generated_task_episodes_for_events(events, [], lineage=lineage)

    assert lineage["parent_session_id"] == parent_session_id
    assert lineage["evidence"]["raw_ref"] == "raw:line:1"
    assert lineage["evidence"]["parent_session_meta_ref"] == "raw:line:2"
    assert lineage["history_prefix"]["status"] == "bounded"
    assert lineage["history_prefix"]["to_line"] == 6
    assert lineage["history_prefix"]["replayed_history_to_line"] == 5
    assert lineage["history_prefix"]["bootstrap_control_ref"] == "raw:line:6"
    assert lineage["history_prefix"]["local_work_from_line"] == 7
    assert lineage["history_prefix"]["child_task_start_ref"] == "raw:line:7"
    assert lineage["ambiguity_flags"] == []
    assert len(episodes) == 2
    inherited, local = episodes
    assert inherited["event_range"] == {
        "from_event_id": events[3].event_id,
        "to_event_id": events[4].event_id,
        "from_line": 4,
        "to_line": 5,
    }
    assert inherited["status"] == "interrupted"
    assert "bounded_by_structural_lineage_boundary" in inherited["ambiguity_flags"]
    assert "interrupted_by_new_user_prompt" not in inherited["ambiguity_flags"]
    assert local["event_range"]["from_line"] == 7
    assert local["event_range"]["to_line"] == 9
    assert local["transition"]["boundary_kind"] == "fork_local_task_start"
    assert local["transition"]["boundary_is_semantic_intent"] is False
    assert local["intent_refs"] == []
    assert local["status"] == "closed"
    assert "runtime_task_complete_observed" in local["ambiguity_flags"]
    assert module.task_episode_lineage_for_range(lineage, inherited["event_range"])["episode_scope"] == (
        "pre_child_task_history_candidate"
    )
    assert module.task_episode_lineage_for_range(lineage, local["event_range"])["episode_scope"] == "local_fork_work"
    inherited["lineage"] = module.task_episode_lineage_for_range(lineage, inherited["event_range"])
    local["lineage"] = module.task_episode_lineage_for_range(lineage, local["event_range"])
    compact_inherited = module.compact_task_episode(
        inherited,
        session_label="fork-session",
        session_id=child_session_id,
    )
    compact_local = module.compact_task_episode(
        local,
        session_label="fork-session",
        session_id=child_session_id,
    )
    assert compact_inherited["lineage"]["episode_scope"] == "pre_child_task_history_candidate"
    assert compact_inherited["reading_contract"]["lineage_requirement"].startswith("compare declared parent")
    assert compact_inherited["expansion_routes"]["parent_session"] == f"task-episodes {parent_session_id}"
    assert compact_local["lineage"]["episode_scope"] == "local_fork_work"
    assert compact_local["reading_contract"]["lineage_requirement"] == "preserve child-local attribution"
    assert compact_local["expansion_routes"]["parent_session"] == f"task-episodes {parent_session_id}"
def test_fork_local_episode_admits_structured_new_task_but_not_developer_bootstrap_as_intent() -> None:
    child_session_id = "11111111-2222-4333-8444-555555555555"
    parent_session_id = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
    declared_timestamp = "2026-07-10T22:19:38Z"
    declared_epoch = module.parse_utc_timestamp(
        declared_timestamp
    ).timestamp()
    rows = [
        {
            "timestamp": declared_timestamp,
            "type": "session_meta",
            "payload": {
                "id": child_session_id,
                "timestamp": declared_timestamp,
                "forked_from_id": parent_session_id,
                "parent_thread_id": parent_session_id,
                "thread_source": "subagent",
            },
        },
        {
            "timestamp": declared_timestamp,
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "developer",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "You are an agent in a team of agents "
                            "collaborating to complete a task."
                        ),
                    }
                ],
            },
        },
        {
            "timestamp": "2026-07-10T22:19:39Z",
            "type": "event_msg",
            "payload": {
                "type": "task_started",
                "turn_id": "child-turn",
                "started_at": declared_epoch + 1,
            },
        },
        {
            "timestamp": "2026-07-10T22:19:40Z",
            "type": "inter_agent_communication_metadata",
            "payload": {"trigger_turn": True},
        },
        {
            "timestamp": "2026-07-10T22:19:40Z",
            "type": "response_item",
            "payload": {
                "type": "agent_message",
                "author": "/root",
                "recipient": "/root/evidence_consistency",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "Message Type: NEW_TASK\n"
                            "Task name: /root/evidence_consistency\n"
                            "Sender: /root\n"
                            "Payload:\n"
                        ),
                    },
                    {
                        "type": "encrypted_content",
                        "encrypted_content": "opaque-fixture",
                    },
                ],
            },
        },
        {
            "timestamp": "2026-07-10T22:19:41Z",
            "type": "response_item",
            "payload": {
                "type": "agent_message",
                "author": "/root",
                "recipient": "/root/evidence_consistency",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "Message Type: NEW_TASK\n"
                            "Task name: /root/evidence_consistency\n"
                            "Sender: /root\n"
                            "Payload:\n"
                        ),
                    },
                    {
                        "type": "encrypted_content",
                        "encrypted_content": "opaque-replayed-fixture",
                    },
                ],
            },
        },
        {
            "timestamp": "2026-07-10T22:19:42Z",
            "type": "event_msg",
            "payload": {
                "type": "task_complete",
                "turn_id": "child-turn",
            },
        },
    ]
    events = [
        module.classify_raw_event(
            json.dumps(row, ensure_ascii=False),
            row,
            line_no,
        )
        for line_no, row in enumerate(rows, start=1)
    ]

    lineage = module.session_lineage_for_events(
        events,
        session_id=child_session_id,
    )
    episodes = module.generated_task_episodes_for_events(
        events,
        [],
        lineage=lineage,
    )

    assert lineage["history_prefix"]["bootstrap_control_ref"] == "raw:line:2"
    assert lineage["history_prefix"]["local_work_from_line"] == 3
    assert events[4].event_type == "INTER_AGENT_TASK"
    assert events[4].facets["inter_agent_message"]["content_status"] == (
        "encrypted_payload_unavailable"
    )
    assert len(episodes) == 1
    local = episodes[0]
    assert local["event_range"] == {
        "from_event_id": events[2].event_id,
        "to_event_id": events[6].event_id,
        "from_line": 3,
        "to_line": 7,
    }
    assert local["status"] == "closed"
    assert [
        ref["raw_ref"] for ref in local["intent_refs"]
    ] == ["raw:line:5", "raw:line:6"]
    assert local["transition"]["delegated_task_ref"] == "raw:line:5"
    assert local["transition"]["delegated_task_content_status"] == (
        "encrypted_payload_unavailable"
    )
    assert local["representations"]["intents"][0][
        "admission_basis"
    ] == "structured_inter_agent_task_delegation"
    assert "do not infer encrypted or absent task details" in local[
        "representations"
    ]["intents"][0]["text"]
    assert "You are an agent in a team" not in local["intent"]
def test_fork_runtime_task_started_after_terminal_opens_distinct_delegated_lifecycles(
    tmp_path: Path,
) -> None:
    child_session_id = "11111111-2222-4333-8444-555555555555"
    parent_session_id = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
    declared_timestamp = "2026-07-11T14:44:21Z"
    declared_epoch = module.parse_utc_timestamp(
        declared_timestamp
    ).timestamp()

    def delegated_task(
        ciphertext: str,
        turn_id: str,
        recipient: str = "/root/operational_use_wave_e",
    ) -> dict[str, Any]:
        return {
            "type": "agent_message",
            "author": "/root",
            "recipient": recipient,
            "internal_chat_message_metadata_passthrough": {
                "turn_id": turn_id,
            },
            "content": [
                {
                    "type": "input_text",
                    "text": (
                        "Message Type: NEW_TASK\n"
                        "Task name: /root/operational_use_wave_e\n"
                        "Sender: /root\n"
                        "Payload:\n"
                    ),
                },
                {
                    "type": "encrypted_content",
                    "encrypted_content": ciphertext,
                },
            ],
        }

    rows = [
        {
            "timestamp": declared_timestamp,
            "type": "session_meta",
            "payload": {
                "id": child_session_id,
                "timestamp": declared_timestamp,
                "forked_from_id": parent_session_id,
                "parent_thread_id": parent_session_id,
                "thread_source": "subagent",
            },
        },
        {
            "timestamp": declared_timestamp,
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "developer",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "You are an agent in a team of agents "
                            "collaborating to complete a task."
                        ),
                    }
                ],
            },
        },
        {
            "timestamp": "2026-07-11T14:44:21.292Z",
            "type": "event_msg",
            "payload": {
                "type": "task_started",
                "turn_id": "turn-one",
                "started_at": declared_epoch + 0.292,
            },
        },
        {
            "timestamp": "2026-07-11T14:44:23.163Z",
            "type": "response_item",
            "payload": delegated_task("opaque-one", "turn-one"),
        },
        {
            "timestamp": "2026-07-11T14:59:51.454Z",
            "type": "event_msg",
            "payload": {
                "type": "task_complete",
                "turn_id": "turn-one",
            },
        },
        {
            "timestamp": "2026-07-11T15:00:23.871Z",
            "type": "event_msg",
            "payload": {
                "type": "task_started",
                "turn_id": "turn-two",
                "started_at": declared_epoch + 962.871,
            },
        },
        {
            "timestamp": "2026-07-11T15:00:24.002Z",
            "type": "turn_context",
            "payload": {"turn_id": "turn-two"},
        },
        {
            "timestamp": "2026-07-11T15:00:24.108Z",
            "type": "inter_agent_communication_metadata",
            "payload": {"trigger_turn": True},
        },
        {
            "timestamp": "2026-07-11T15:00:24.108Z",
            "type": "response_item",
            "payload": delegated_task("opaque-two", "turn-two"),
        },
        {
            "timestamp": "2026-07-11T15:04:54.736Z",
            "type": "event_msg",
            "payload": {
                "type": "task_complete",
                "turn_id": "turn-two",
            },
        },
        {
            "timestamp": "2026-07-11T15:13:23.357Z",
            "type": "event_msg",
            "payload": {
                "type": "task_started",
                "turn_id": "turn-three",
                "started_at": declared_epoch + 1742.357,
            },
        },
        {
            "timestamp": "2026-07-11T15:13:23.490Z",
            "type": "turn_context",
            "payload": {"turn_id": "turn-three"},
        },
        {
            "timestamp": "2026-07-11T15:13:23.594Z",
            "type": "inter_agent_communication_metadata",
            "payload": {"trigger_turn": True},
        },
        {
            "timestamp": "2026-07-11T15:13:23.594Z",
            "type": "response_item",
            "payload": delegated_task("opaque-three", "turn-three"),
        },
        {
            "timestamp": "2026-07-11T15:29:33.330Z",
            "type": "event_msg",
            "payload": {
                "type": "task_complete",
                "turn_id": "turn-three",
            },
        },
    ]
    events = [
        module.classify_raw_event(
            json.dumps(row, ensure_ascii=False),
            row,
            line_no,
        )
        for line_no, row in enumerate(rows, start=1)
    ]
    lineage = module.session_lineage_for_events(
        events,
        session_id=child_session_id,
    )

    episodes = module.generated_task_episodes_for_events(
        events,
        [],
        lineage=lineage,
    )
    for episode in episodes:
        episode["lineage"] = module.task_episode_lineage_for_range(
            lineage,
            episode["event_range"],
        )

    assert len(episodes) == 3
    assert [episode["event_range"] for episode in episodes] == [
        {
            "from_event_id": events[2].event_id,
            "to_event_id": events[4].event_id,
            "from_line": 3,
            "to_line": 5,
        },
        {
            "from_event_id": events[5].event_id,
            "to_event_id": events[9].event_id,
            "from_line": 6,
            "to_line": 10,
        },
        {
            "from_event_id": events[10].event_id,
            "to_event_id": events[14].event_id,
            "from_line": 11,
            "to_line": 15,
        },
    ]
    assert [
        [ref["raw_ref"] for ref in episode["intent_refs"]]
        for episode in episodes
    ] == [
        ["raw:line:4"],
        ["raw:line:9"],
        ["raw:line:14"],
    ]
    assert [episode["status"] for episode in episodes] == [
        "closed",
        "closed",
        "closed",
    ]
    assert episodes[0]["start_ref_role"] == (
        "structural_lineage_boundary"
    )
    assert [
        episode["start_ref_role"] for episode in episodes[1:]
    ] == [
        "runtime_task_started_boundary",
        "runtime_task_started_boundary",
    ]
    assert [
        episode["transition"]["previous_episode_id"]
        for episode in episodes
    ] == ["", "task-0001", "task-0002"]
    assert [
        episode["transition"].get("boundary_kind")
        for episode in episodes
    ] == [
        "fork_local_task_start",
        "runtime_task_started_boundary",
        "runtime_task_started_boundary",
    ]
    assert all(
        "inter_agent_task_content_unresolved"
        in episode["ambiguity_flags"]
        for episode in episodes
    )
    assert all(
        episode["semantic_continuations"] == []
        for episode in episodes
    )
    count_query = module.episode_delegated_lifecycle_query(
        "Сколько было NEW_TASK для /root/operational_use_wave_e? Три?"
    )
    path_query = module.episode_delegated_lifecycle_query(
        "Пройди пути task_started -> NEW_TASK -> task_complete"
    )
    replay_query = module.episode_delegated_lifecycle_query(
        "Почему три NEW_TASK с одинаковым task name нельзя назвать replay одного задания?"
    )
    assert count_query["mode"] == "count"
    assert count_query["requested_cardinality"] == 3
    assert count_query["target"] == "/root/operational_use_wave_e"
    assert path_query["mode"] == "ordered_path"
    assert replay_query["mode"] == "semantic_identity"
    assert module.memory_query_intent(
        "Пройди пути task_started -> NEW_TASK -> task_complete"
    )["primary"] == "relationship_topology"
    assert module.memory_query_intent(
        "Почему три NEW_TASK с одинаковым task name нельзя назвать replay одного задания?"
    )["primary"] == "relationship_topology"
    for episode in episodes:
        alignment = module.episode_delegated_lifecycle_alignment(
            episode,
            query=path_query,
        )
        assert alignment["status"] == (
            "typed_delegated_lifecycle_candidate"
        )
        assert alignment["accepted"] is False

    workspace = tmp_path / "AbyssOS"
    workspace.mkdir()
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-delegated-lifecycle.jsonl"
    rows[0]["payload"]["cwd"] = str(workspace)
    transcript_rows = [
        *rows,
        {
            "timestamp": "2026-07-11T15:30:00Z",
            "type": "event_msg",
            "payload": {
                "type": "task_started",
                "turn_id": "turn-other",
            },
        },
        {
            "timestamp": "2026-07-11T15:30:01Z",
            "type": "response_item",
            "payload": delegated_task(
                "opaque-other",
                "turn-other",
                "/root/other_worker",
            ),
        },
        {
            "timestamp": "2026-07-11T15:30:02Z",
            "type": "event_msg",
            "payload": {
                "type": "task_complete",
                "turn_id": "turn-other",
            },
        },
    ]
    write_jsonl(transcript, transcript_rows)
    receipt = module.handle_hook_event(
        "Stop",
        {
            "session_id": child_session_id,
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )
    assert receipt["ok"] is True
    assert module.search_index_sessions(
        aoa_root=aoa_root,
        target="all",
        rebuild=True,
    )["ok"] is True

    structural = module.episode_semantic_search(
        aoa_root=aoa_root,
        query=(
            "Сколько было NEW_TASK для "
            "/root/operational_use_wave_e? Три?"
        ),
        session=child_session_id,
        mode="sparse",
        limit=8,
        explain=True,
    )
    gate = structural["retrieval"][
        "delegated_lifecycle_relation_gate"
    ]
    assert gate["status"] == "qualified_delegated_lifecycle_group"
    assert gate["group_selection_status"] == (
        "exact_target_group_selected"
    )
    assert gate["qualified_count"] == 3
    assert gate["candidate_count"] == 4
    assert gate["out_of_scope_candidate_count"] == 1
    assert gate["structural_claim_admitted"] is True
    assert structural["answer_admission"]["admitted"] is True
    assert structural["answer_admission"]["claim_shape"] == (
        "delegated_lifecycle"
    )
    assert [
        chain["refs"]["delegation"] for chain in gate["chains"]
    ] == ["raw:line:4", "raw:line:9", "raw:line:14"]

    replay = module.episode_semantic_search(
        aoa_root=aoa_root,
        query=(
            "Почему три NEW_TASK с одинаковым task name нельзя "
            "назвать replay одного задания?"
        ),
        session=child_session_id,
        mode="sparse",
        limit=8,
    )
    assert replay["answer_admission"]["admitted"] is False
    assert replay["answer_admission"]["status"] == (
        "delegated_lifecycle_semantic_identity_unresolved"
    )
    assert replay["retrieval"][
        "delegated_lifecycle_relation_gate"
    ]["structural_claim_admitted"] is True
def test_inter_agent_new_task_after_terminal_is_a_semantic_fallback_without_task_started() -> None:
    def delegated_task(ciphertext: str) -> dict[str, Any]:
        return {
            "type": "agent_message",
            "author": "/root",
            "recipient": "/root/fallback",
            "content": [
                {
                    "type": "input_text",
                    "text": (
                        "Message Type: NEW_TASK\n"
                        "Task name: /root/fallback\n"
                        "Sender: /root\n"
                        "Payload:\n"
                    ),
                },
                {
                    "type": "encrypted_content",
                    "encrypted_content": ciphertext,
                },
            ],
        }

    rows = [
        {
            "timestamp": "2026-07-11T15:00:24Z",
            "type": "response_item",
            "payload": delegated_task("opaque-one"),
        },
        {
            "timestamp": "2026-07-11T15:01:24Z",
            "type": "event_msg",
            "payload": {
                "type": "task_complete",
                "turn_id": "turn-one",
            },
        },
        {
            "timestamp": "2026-07-11T15:02:24Z",
            "type": "response_item",
            "payload": delegated_task("opaque-two"),
        },
        {
            "timestamp": "2026-07-11T15:03:24Z",
            "type": "event_msg",
            "payload": {
                "type": "task_complete",
                "turn_id": "turn-two",
            },
        },
    ]
    events = [
        module.classify_raw_event(
            json.dumps(row, ensure_ascii=False),
            row,
            line_no,
        )
        for line_no, row in enumerate(rows, start=1)
    ]

    episodes = module.generated_task_episodes_for_events(
        events,
        [],
    )

    assert len(episodes) == 2
    assert [episode["event_range"] for episode in episodes] == [
        {
            "from_event_id": events[0].event_id,
            "to_event_id": events[1].event_id,
            "from_line": 1,
            "to_line": 2,
        },
        {
            "from_event_id": events[2].event_id,
            "to_event_id": events[3].event_id,
            "from_line": 3,
            "to_line": 4,
        },
    ]
    assert [
        episode["transition"]["reason"]
        for episode in episodes
    ] == [
        "structured_inter_agent_task_start",
        "structured_inter_agent_task_after_terminal",
    ]
    assert [
        episode["intent_refs"][0]["raw_ref"]
        for episode in episodes
    ] == ["raw:line:1", "raw:line:3"]
    assert all(
        episode["start_ref_role"]
        == "structured_inter_agent_task"
        for episode in episodes
    )
def test_lineage_consolidation_requires_exact_relevant_parent_evidence_and_keeps_physical_refs() -> None:
    parent_session_id = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
    fork_session_id = "11111111-2222-4333-8444-555555555555"
    duplicate_fork_session_id = "66666666-7777-4888-8999-aaaaaaaaaaaa"
    distinct_ref_fork_session_id = "bbbbbbbb-cccc-4ddd-8eee-ffffffffffff"
    shared_text = (
        "The downstream canary declares four owners but can yield zero checked and four skipped "
        "because the release wrapper ignores dependency roots."
    )

    def candidate(
        *,
        session_id: str,
        episode_id: str,
        text: str,
        raw_ref: str,
        scope: str = "",
    ) -> dict[str, Any]:
        item: dict[str, Any] = {
            "session_id": session_id,
            "task_episode_id": episode_id,
            "raw_ref": raw_ref,
            "segment_ref": f"segment:{episode_id}",
            "session_ref": f"session:{session_id}",
            "supporting_evidence": [
                {
                    "text": text,
                    "matched_query_terms": ["downstream", "canary", "skipped"],
                    "refs": {"raw": raw_ref},
                }
            ],
        }
        if scope:
            item["lineage"] = {
                "relationship": "forked_from",
                "parent_session_id": parent_session_id,
                "episode_scope": scope,
            }
        return item

    parent = candidate(
        session_id=parent_session_id,
        episode_id="task-0010",
        text=shared_text,
        raw_ref="raw:line:2988",
    )
    replay = candidate(
        session_id=fork_session_id,
        episode_id="task-0010",
        text=shared_text,
        raw_ref="raw:line:937",
        scope="pre_child_task_history_candidate",
    )
    duplicate_replay = candidate(
        session_id=duplicate_fork_session_id,
        episode_id="task-0010",
        text=shared_text,
        raw_ref="raw:line:937",
        scope="pre_child_task_history_candidate",
    )
    distinct_ref_replay = candidate(
        session_id=distinct_ref_fork_session_id,
        episode_id="task-0010",
        text=shared_text,
        raw_ref="raw:line:939",
        scope="pre_child_task_history_candidate",
    )
    local = candidate(
        session_id=fork_session_id,
        episode_id="task-0018",
        text=shared_text,
        raw_ref="raw:line:2100",
        scope="local_fork_work",
    )

    consolidated, summary = module.episode_lineage_consolidate_results(
        [replay, duplicate_replay, distinct_ref_replay, parent, local],
        explain=True,
    )

    assert summary["status"] == "applied"
    assert summary["group_count"] == 1
    assert summary["collapsed_duplicate_count"] == 3
    assert len(consolidated) == 2
    representative = consolidated[0]
    assert representative["session_id"] == parent_session_id
    assert representative["task_episode_id"] == "task-0010"
    assert representative["lineage_group"]["physical_refs_retained"] is True
    assert representative["lineage_group"]["member_count"] == 4
    assert {member["session_id"] for member in representative["lineage_group"]["members"]} == {
        parent_session_id,
        fork_session_id,
        duplicate_fork_session_id,
        distinct_ref_fork_session_id,
    }
    assert {member["raw_ref"] for member in representative["lineage_group"]["members"]} == {
        "raw:line:2988",
        "raw:line:937",
        "raw:line:939",
    }
    assert representative["lineage_group"]["shared_evidence_input_count"] == 3
    assert representative["lineage_group"]["shared_evidence_count"] == 2
    assert representative["lineage_group"]["shared_evidence_duplicate_count"] == 1
    assert [
        item["fork_raw_refs"]
        for item in representative["lineage_group"]["shared_evidence"]
    ] == [["raw:line:937"], ["raw:line:939"]]
    assert consolidated[1]["task_episode_id"] == "task-0018"
    assert "lineage_group" not in consolidated[1]

    without_exact_clone, _ = module.episode_lineage_consolidate_results(
        [replay, distinct_ref_replay, parent, local]
    )
    assert (
        without_exact_clone[0]["lineage_group"]["group_id"]
        == representative["lineage_group"]["group_id"]
    )

    near_but_not_exact = candidate(
        session_id=fork_session_id,
        episode_id="task-0011",
        text=shared_text.replace("four skipped", "three skipped"),
        raw_ref="raw:line:938",
        scope="pre_child_task_history_candidate",
    )
    separate, separate_summary = module.episode_lineage_consolidate_results([parent, near_but_not_exact])
    assert len(separate) == 2
    assert separate_summary["status"] == "no_exact_lineage_duplicates"
    assert separate[1]["lineage_duplicate_status"] == "no_exact_relevant_parent_evidence_overlap"
    assert module.episode_lineage_relevant_evidence_fingerprints(
        {"supporting_evidence": [{"text": shared_text, "matched_query_terms": None}]}
    ) == {}
def test_rerank_candidate_view_consolidates_global_replays_before_model_scoring() -> None:
    parent_session_id = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
    shared_text = (
        "The recovery packet preserved the original provenance hash while replacing temporary "
        "archive links with canonical evidence files."
    )

    def candidate(
        session_id: str,
        raw_ref: str,
        *,
        fork: bool = False,
    ) -> dict[str, Any]:
        item: dict[str, Any] = {
            "session_id": session_id,
            "task_episode_id": "task-0007",
            "raw_ref": raw_ref,
            "segment_ref": f"segment:{session_id}",
            "session_ref": f"session:{session_id}",
            "supporting_evidence": [
                {
                    "text": shared_text,
                    "matched_query_terms": ["recovery", "provenance", "canonical"],
                    "refs": {"raw": raw_ref},
                }
            ],
        }
        if fork:
            item["lineage"] = {
                "relationship": "forked_from",
                "parent_session_id": parent_session_id,
                "episode_scope": "pre_child_task_history_candidate",
            }
        return item

    candidates = [
        candidate("11111111-2222-4333-8444-555555555555", "raw:line:937", fork=True),
        candidate("66666666-7777-4888-8999-aaaaaaaaaaaa", "raw:line:937", fork=True),
        candidate(parent_session_id, "raw:line:2988"),
    ]

    global_view, summary, packet = module.episode_rerank_candidate_view(
        candidates,
        session=None,
        explain=True,
    )

    assert summary is not None
    assert summary["status"] == "applied"
    assert summary["input_count"] == 3
    assert summary["output_count"] == 1
    assert packet["collapsed_duplicate_count"] == 2
    assert packet["physical_refs_retained"] is True
    assert global_view[0]["lineage_group"]["member_count"] == 3

    session_view, session_summary, session_packet = module.episode_rerank_candidate_view(
        candidates,
        session="11111111-2222-4333-8444-555555555555",
    )
    assert session_view == candidates
    assert session_summary is None
    assert session_packet["status"] == "not_applied"
