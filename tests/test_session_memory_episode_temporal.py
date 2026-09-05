from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from session_memory_test_support import (
    module,
    write_json,
    write_jsonl,
)

def test_episode_temporal_span_requires_both_anchors_in_order() -> None:
    query = "что произошло между stale search-provider-status и git add README PIPELINE READINESS"
    temporal_span = module.episode_temporal_span_query(query)
    ordered_episode = {
        "representations": {
            "failures": [
                {
                    "text": "search-provider-status returned stale",
                    "line": 10,
                    "refs": {"raw": "raw:line:10", "segment": "segment-1"},
                }
            ],
            "actions": [
                {
                    "text": "git add README.md PIPELINE.md READINESS.md",
                    "line": 20,
                    "refs": {"raw": "raw:line:20", "segment": "segment-1"},
                }
            ],
        }
    }
    reversed_episode = {
        "representations": {
            "actions": [
                {
                    "text": "git add README.md PIPELINE.md READINESS.md",
                    "line": 5,
                    "refs": {"raw": "raw:line:5"},
                }
            ],
            "failures": [
                {
                    "text": "search-provider-status returned stale",
                    "line": 30,
                    "refs": {"raw": "raw:line:30"},
                }
            ],
        }
    }
    partial_common_word_episode = {
        "representations": {
            "failures": [
                {
                    "text": "search-provider-status returned stale",
                    "line": 10,
                    "refs": {"raw": "raw:line:10"},
                }
            ],
            "actions": [
                {
                    "text": "README PIPELINE READINESS",
                    "line": 20,
                    "refs": {"raw": "raw:line:20"},
                }
            ],
        }
    }

    ordered = module.episode_temporal_span_evidence(ordered_episode, temporal_span)
    reversed_result = module.episode_temporal_span_evidence(reversed_episode, temporal_span)
    partial_result = module.episode_temporal_span_evidence(partial_common_word_episode, temporal_span)
    qualified, relation_gate = module.episode_temporal_relation_gate(
        [{"doc_id": "partial", "task_episode_id": "task-partial", "temporal_span": partial_result}],
        temporal_span,
    )

    assert temporal_span["active"] is True
    assert ordered["status"] == "ordered_span_found"
    assert ordered["left"]["refs"]["raw"] == "raw:line:10"
    assert ordered["right"]["refs"]["raw"] == "raw:line:20"
    assert ordered["ranking_boost"] > 0
    assert reversed_result["status"] == "temporal_span_unresolved_or_unordered"
    assert reversed_result["ranking_boost"] == 0
    assert partial_result["status"] == "ordered_span_below_anchor_coverage"
    assert partial_result["ranking_boost"] == 0
    assert qualified == []
    assert relation_gate["status"] == "no_qualified_ordered_span"
    assert relation_gate["rejected_samples"][0]["task_episode_id"] == "task-partial"
def test_episode_temporal_span_accepts_event_frame_with_iso_date() -> None:
    """Regression derived from randomized manual wave W1 seeds 2026071601/02."""

    query = (
        "что происходило 2026-01-02 между cache readiness check "
        "и диагностикой missing owner alias"
    )
    temporal_span = module.episode_temporal_span_query(query)
    intent = module.memory_query_intent(query)

    assert temporal_span["active"] is True
    assert temporal_span["status"] == "temporal_span_anchors_parsed"
    assert temporal_span["temporal_intent_basis"] == "explicit_event_frame"
    assert temporal_span["query_date"] == "2026-01-02"
    assert temporal_span["query_time_from"] == "2026-01-02T00:00:00.000000Z"
    assert temporal_span["query_time_to"] == "2026-01-02T23:59:59.999999Z"
    assert temporal_span["query_time_basis"] == "explicit_event_frame_date"
    assert temporal_span["left_text"] == "cache readiness check"
    assert temporal_span["right_text"] == "диагностикой missing owner alias"
    assert intent["primary"] == "temporal_state"

    comparison = module.episode_temporal_span_query(
        "какая разница 2026-01-02 между cache readiness и owner alias"
    )
    assert comparison["active"] is False
    assert comparison["status"] == "between_relation_without_temporal_interval_intent"
def test_episode_temporal_span_prefers_explicit_quoted_message_anchors() -> None:
    query = (
        "Что произошло между сообщениями 'Ты завис' и 'Продолжай'?"
    )

    temporal_span = module.episode_temporal_span_query(query)

    assert temporal_span["active"] is True
    assert temporal_span["status"] == "temporal_span_anchors_parsed"
    assert temporal_span["anchor_parse_basis"] == (
        "explicit_quoted_anchor_pair"
    )
    assert temporal_span["left_match_policy"] == "normalized_exact_phrase"
    assert temporal_span["right_match_policy"] == "normalized_exact_phrase"
    assert temporal_span["quoted_anchor_source_policy"] == (
        "canonical_message_required"
    )
    assert temporal_span["left_text"] == "Ты завис"
    assert temporal_span["right_text"] == "Продолжай"
    assert [
        term["token"] for term in temporal_span["left_terms"]
    ] == ["ты", "завис"]
    assert [
        term["token"] for term in temporal_span["right_terms"]
    ] == ["продолжай"]
def test_episode_temporal_quoted_message_anchor_rejects_later_semantic_reflection(
    tmp_path: Path,
) -> None:
    """Regression derived from sealed real case EPI-RECOVERY-001."""
    raw_path = tmp_path / "quoted-message-interval.raw.jsonl"
    write_jsonl(
        raw_path,
        [
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
                            "text": "На связи. Не завис, но поздно дал статус.",
                        }
                    ],
                },
            },
            {
                "timestamp": "2026-06-11T01:58:52Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {"type": "output_text", "text": "Проверка продолжена."}
                    ],
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
        ],
    )
    temporal_span = module.episode_temporal_span_query(
        "Что произошло между сообщениями 'Ты завис' и 'Продолжай'?"
    )
    candidates = [
        {
            "doc_id": "episode_semantic:quoted-message-session:task-0001",
            "session_id": "quoted-message-session",
            "task_episode_id": "task-0001",
            "event_range": {"from_line": 1, "to_line": 4},
            "temporal_span": {
                "active": True,
                "status": "temporal_span_unresolved_or_unordered",
            },
        }
    ]

    hydrated, report = module.episode_temporal_scoped_raw_hydration(
        raw_path=raw_path,
        segments=[],
        results=candidates,
        temporal_span=temporal_span,
        max_raw_bytes=1024 * 1024,
        max_lines=100,
    )
    qualified, gate = module.episode_temporal_relation_gate(
        hydrated,
        temporal_span,
    )

    assert report["qualified_candidate_count"] == 1
    assert gate["status"] == "qualified_ordered_spans_available"
    evidence = qualified[0]["temporal_span"]
    assert evidence["left"]["refs"]["raw"] == "raw:line:1"
    assert evidence["right"]["refs"]["raw"] == "raw:line:4"
    assert evidence["left"]["explicit_quoted_anchor_proven"] is True
    assert evidence["right"]["explicit_quoted_anchor_proven"] is True
    assert [
        item["refs"]["raw"]
        for item in evidence["interval_contents"]["events"]
    ] == ["raw:line:2", "raw:line:3"]
def test_episode_temporal_span_query_parses_after_action_relation() -> None:
    temporal_span = module.episode_temporal_span_query(
        "где после проверки generated surfaces для 57 skills запускали export gate "
        "и перестраивали skill catalog"
    )

    assert temporal_span["active"] is True
    assert temporal_span["status"] == "temporal_after_anchors_parsed"
    assert temporal_span["temporal_intent_basis"] == "explicit_after_action_relation"
    assert temporal_span["left_text"] == "проверки generated surfaces для 57 skills"
    assert temporal_span["right_text"] == "запускали export gate и перестраивали skill catalog"
def test_episode_temporal_after_clause_keeps_compound_actor_anchor_and_action_sequence() -> None:
    """Manual-derived regression: actor text and read-only must not become a global seed."""
    temporal_span = module.episode_temporal_span_query(
        "После того как агент ошибочно свёл clean work к read-only, "
        "пользователь потребовал исправить. Какие временные tts hotpath test "
        "остатки были затем найдены, удалены и проверены?"
    )

    assert temporal_span["active"] is True
    assert temporal_span["status"] == "temporal_after_clause_anchors_parsed"
    assert temporal_span["left_text"].endswith("read-only")
    assert temporal_span["left_source_policy"] == "canonical_message_role_required"
    assert temporal_span["left_expected_message_role"] == "assistant"
    assert temporal_span["right_action_sequence_required"] is True
    assert temporal_span["right_action_requirements"] == [
        "discovery",
        "mutation",
        "verification",
    ]
    assert module.episode_temporal_raw_anchor_identifiers("read-only") == [
        "read-only"
    ]
    assert module.episode_temporal_exact_anchor_identifiers("read-only") == []
def test_episode_temporal_generated_evidence_accepts_adjacent_structured_partial_chain() -> None:
    temporal_span = module.episode_temporal_span_query(
        "где после docs proof переэкспортировали aoa-session-memory bundle "
        "и проверили portable audit"
    )
    episode = {
        "representations": {
            "verification": [
                {
                    "text": "Docs proof внесен.",
                    "line": 10,
                    "source_lane": "message_assistant",
                    "admission_basis": "verification_observation",
                    "refs": {"raw": "raw:line:10"},
                }
            ],
            "actions": [
                {
                    "text": "python3 scripts/aoa_session_memory.py export-bundle",
                    "line": 12,
                    "source_lane": "structured_tool_call",
                    "admission_basis": "structured_operational_action",
                    "correlation_id": "call-export",
                    "refs": {"raw": "raw:line:12"},
                }
            ],
            "outcomes": [
                {
                    "text": "python3 scripts/aoa_session_memory.py audit --portable-bundle -> succeeded",
                    "line": 19,
                    "source_lane": "structured_tool_result",
                    "admission_basis": "structured_result_status",
                    "correlation_id": "call-audit",
                    "refs": {"raw": "raw:line:19"},
                }
            ],
        }
    }

    evidence = module.episode_temporal_span_evidence(episode, temporal_span)

    assert evidence["status"] == "ordered_span_found"
    assert evidence["accepted"] is True
    assert evidence["admission_basis"] == "adjacent_structured_partial_lexical_coverage"
    assert evidence["left"]["refs"]["raw"] == "raw:line:10"
    assert evidence["right"]["refs"]["raw"] == "raw:line:19"
    assert evidence["minimum_anchor_coverage"] < module.EPISODE_TEMPORAL_SPAN_MIN_ANCHOR_COVERAGE
def test_episode_temporal_scoped_raw_readiness_keeps_verified_archive_readable_when_live_grows(
    tmp_path: Path,
) -> None:
    """Real-session regression: an active tail must not hide its verified archived prefix."""
    archived_raw = tmp_path / "session.raw.jsonl"
    archived_raw.write_text('{"type":"session_meta"}\n', encoding="utf-8")
    live_source = tmp_path / "rollout.jsonl"
    live_source.write_text(
        archived_raw.read_text(encoding="utf-8") + '{"type":"response_item"}\n',
        encoding="utf-8",
    )
    manifest = {
        "raw": {
            "path": str(archived_raw),
            "sha256": module.sha256_file(archived_raw),
            "source_snapshot": {
                "path": str(live_source),
                "size": archived_raw.stat().st_size,
                "mtime_ns": archived_raw.stat().st_mtime_ns,
            },
        }
    }

    readiness = module.episode_temporal_scoped_raw_readiness(manifest, archived_raw)

    assert readiness["readable"] is True
    assert readiness["status"] == "archived_raw_snapshot_readable"
    assert readiness["read_scope"] == "archived_raw_snapshot_only"
    assert readiness["archive_integrity"]["status"] == "verified"
    assert readiness["projection_freshness"]["status"] in {"deferred", "stale"}
def test_temporal_raw_hydration_uses_structured_mcp_receipts_as_endpoints(
    tmp_path: Path,
) -> None:
    """Regression derived from the W3 raw:746 receipt omission."""
    raw_path = tmp_path / "session.raw.jsonl"

    def receipt(
        *,
        timestamp: str,
        call_id: str,
        server: str,
        tool: str,
        arguments: dict[str, Any],
        failed: bool = False,
    ) -> dict[str, Any]:
        return {
            "timestamp": timestamp,
            "type": "event_msg",
            "payload": {
                "type": "mcp_tool_call_end",
                "call_id": call_id,
                "invocation": {
                    "server": server,
                    "tool": tool,
                    "arguments": arguments,
                },
                "result": (
                    {"Err": {"message": "synthetic failure"}}
                    if failed
                    else {
                        "Ok": {
                            "content": [],
                            "structuredContent": {
                                "query": arguments.get("query", ""),
                            },
                            "isError": False,
                        }
                    }
                ),
            },
        }

    write_jsonl(
        raw_path,
        [
            {
                "timestamp": "2026-07-10T10:05:00Z",
                "type": "session_meta",
                "payload": {"id": "temporal-mcp-receipts"},
            },
            receipt(
                timestamp="2026-07-10T10:05:01Z",
                call_id="exec-left",
                server="aoa_session_memory",
                tool="aoa_session_entity_usage_chain",
                arguments={"anchor": "aoa_memo", "kind": "mcp"},
            ),
            {
                "timestamp": "2026-07-10T10:05:02Z",
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call",
                    "name": "exec",
                    "call_id": "call-listing",
                    "input": "text(ALL_TOOLS.filter(x => /aoa_memo/i.test(x.name)));",
                },
            },
            {
                "timestamp": "2026-07-10T10:05:03Z",
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call_output",
                    "call_id": "call-listing",
                    "output": "aoa_memo_search is available",
                },
            },
            receipt(
                timestamp="2026-07-10T10:05:04Z",
                call_id="exec-right",
                server="aoa_memo",
                tool="aoa_memo_search",
                arguments={
                    "query": "distributed memory organ foundation",
                    "mode": "inspect",
                    "scope": "central",
                },
            ),
        ],
    )
    query = (
        "что происходило между успешным MCP receipt "
        "aoa_session_entity_usage_chain для aoa_memo и успешным MCP "
        "receipt aoa_memo_search distributed memory organ foundation"
    )
    temporal = module.episode_temporal_span_query(query)
    candidates = [
        {
            "doc_id": "episode:temporal-mcp-receipts:task-0001",
            "session_id": "temporal-mcp-receipts",
            "task_episode_id": "task-0001",
            "event_range": {"from_line": 1, "to_line": 5},
            "supporting_evidence": [],
        }
    ]

    hydrated, report = module.episode_temporal_scoped_raw_hydration(
        raw_path=raw_path,
        segments=[],
        results=candidates,
        temporal_span=temporal,
    )

    assert report["status"] == "applied"
    span = hydrated[0]["temporal_span"]
    assert span["left"]["refs"]["raw"] == "raw:line:2"
    assert span["right"]["refs"]["raw"] == "raw:line:5"
    assert span["left"]["event_kind"] == "structured_mcp_receipt"
    assert span["right"]["event_kind"] == "structured_mcp_receipt"
    assert span["left"]["result_outcome"] == "succeeded"
    assert span["right"]["result_outcome"] == "succeeded"
    assert span["left"]["required_structured_outcome"] == "succeeded"
    assert span["right"]["required_structured_outcome"] == "succeeded"
    assert span["left"]["structured_outcome_proven"] is True
    assert span["right"]["structured_outcome_proven"] is True
    assert span["interval_contents"]["event_raw_refs"] == [
        "raw:line:3",
        "raw:line:4",
    ]

    failed_raw_path = tmp_path / "failed-session.raw.jsonl"
    write_jsonl(
        failed_raw_path,
        [
            {
                "timestamp": "2026-07-10T10:05:00Z",
                "type": "session_meta",
                "payload": {"id": "temporal-mcp-receipts"},
            },
            receipt(
                timestamp="2026-07-10T10:05:01Z",
                call_id="exec-left",
                server="aoa_session_memory",
                tool="aoa_session_entity_usage_chain",
                arguments={"anchor": "aoa_memo", "kind": "mcp"},
            ),
            {
                "timestamp": "2026-07-10T10:05:02Z",
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call",
                    "name": "exec",
                    "call_id": "call-listing",
                    "input": "text(ALL_TOOLS.filter(x => /aoa_memo/i.test(x.name)));",
                },
            },
            receipt(
                timestamp="2026-07-10T10:05:04Z",
                call_id="exec-right-failed",
                server="aoa_memo",
                tool="aoa_memo_search",
                arguments={
                    "query": "distributed memory organ foundation",
                    "mode": "inspect",
                    "scope": "central",
                },
                failed=True,
            ),
        ],
    )
    failed_hydrated, _failed_report = (
        module.episode_temporal_scoped_raw_hydration(
            raw_path=failed_raw_path,
            segments=[],
            results=candidates,
            temporal_span=temporal,
        )
    )
    assert (
        failed_hydrated[0].get("temporal_span", {}).get("accepted")
        is not True
    )
    failed_query = query.replace(
        "и успешным MCP receipt aoa_memo_search",
        "и failed MCP receipt aoa_memo_search",
    )
    failed_temporal = module.episode_temporal_span_query(failed_query)
    requested_failure, _requested_failure_report = (
        module.episode_temporal_scoped_raw_hydration(
            raw_path=failed_raw_path,
            segments=[],
            results=candidates,
            temporal_span=failed_temporal,
        )
    )
    failed_span = requested_failure[0]["temporal_span"]
    assert failed_span["accepted"] is True
    assert failed_span["right"]["refs"]["raw"] == "raw:line:4"
    assert failed_span["right"]["result_outcome"] == "failed"
    assert failed_span["right"]["required_structured_outcome"] == "failed"
    assert failed_span["right"]["structured_outcome_proven"] is True
def test_temporal_structured_outcome_ignores_identifier_collisions() -> None:
    """Adjacent return-review of outcome terms embedded in entity anchors."""
    assert (
        module.episode_temporal_required_structured_outcome(
            "successful MCP receipt error_report",
        )
        == "succeeded"
    )
    assert (
        module.episode_temporal_required_structured_outcome(
            "successful MCP receipt failed_jobs_lookup",
        )
        == "succeeded"
    )
    assert (
        module.episode_temporal_required_structured_outcome(
            "successful MCP receipt error-report",
        )
        == "succeeded"
    )
    assert (
        module.episode_temporal_required_structured_outcome(
            "успешный MCP receipt поиск_ошибок",
        )
        == "succeeded"
    )
def test_literal_embedded_entity_does_not_promote_iso_year_over_tool(
    tmp_path: Path,
) -> None:
    """Manual generic-tool query: the timestamp year is not an eval anchor."""
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-temporal-tool-anchor.jsonl"
    write_jsonl(
        transcript,
        [
            {
                "timestamp": "2026-07-10T10:05:00Z",
                "type": "session_meta",
                "payload": {
                    "id": "temporal-tool-anchor",
                    "cwd": str(workspace),
                },
            },
            {
                "timestamp": "2026-07-10T10:05:00.500Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "Run pwd with exec.",
                        }
                    ],
                },
            },
            {
                "timestamp": "2026-07-10T10:05:01Z",
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call",
                    "name": "exec",
                    "call_id": "call-exec",
                    "input": "pwd",
                },
            },
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "temporal-tool-anchor",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )
    assert module.search_index_sessions(
        aoa_root=aoa_root,
        target="all",
        rebuild=True,
    )["ok"] is True
    # Model a stale materialized registry that retained the noisy year entity
    # but omitted the exact observed tool still present in route terms.
    write_json(
        aoa_root / module.ENTITY_REGISTRY_PATH,
        {
            "schema_version": module.ENTITY_REGISTRY_SCHEMA_VERSION,
            "artifact_type": "entity_registry_snapshot",
            "generated_at": "2100-01-01T00:00:00Z",
            "generated_at_epoch": 4102444800.0,
            "entries": [
                {
                    "entity_id": "eval:2026",
                    "kind": "eval",
                    "canonical_key": "2026",
                    "aliases": ["eval:2026"],
                    "status": "observed",
                },
            ],
        },
    )
    query = (
        "Был ли exec уже реально вызван к "
        "2026-07-10T10:05:10.500Z, а не только упомянут?"
    )

    candidate = module.literal_query_embedded_entity_anchor(
        aoa_root=aoa_root,
        query=query,
        kind="auto",
    )
    assert candidate["anchor"] == "exec"
    assert candidate["kind"] == "tool"

    plan = module.literal_query_plan(
        aoa_root=aoa_root,
        query=query,
        time_to="2026-07-10T10:05:10.500Z",
    )
    assert plan["route_anchor"] == "exec"
    assert plan["route_anchor_kind"] == "tool"
    assert plan["route_anchor_source"] == "embedded_entity_registry"

    invoked_state = module.episode_entity_state_search(
        aoa_root=aoa_root,
        anchor="exec",
        kind="tool",
        session="temporal-tool-anchor",
        time_to="2026-07-10T10:05:01.500Z",
        limit=8,
    )
    assert invoked_state["answer_admission"]["admitted"] is True
    assert invoked_state["answer_admission"]["status"] == (
        "invoked_in_requested_time_scope"
    )
    assert invoked_state["answer_admission"]["basis"] == (
        "current_time_filtered_typed_invocation_posting"
    )
    assert invoked_state["results"][0]["raw_ref"] == "raw:line:3"

    before_invocation = module.episode_entity_state_search(
        aoa_root=aoa_root,
        anchor="exec",
        kind="tool",
        session="temporal-tool-anchor",
        time_to="2026-07-10T10:05:00.750Z",
        limit=8,
    )
    assert before_invocation["answer_admission"]["admitted"] is False
    assert before_invocation["answer_admission"]["status"] == "unresolved"
    assert before_invocation["entity_state"] == (
        "time_scoped_entity_state_unresolved"
    )

    unresolved_mcp_identity = module.episode_entity_state_search(
        aoa_root=aoa_root,
        anchor="exec",
        kind="mcp_tool",
        session="temporal-tool-anchor",
        time_to="2026-07-10T10:05:01.500Z",
        limit=8,
    )
    assert unresolved_mcp_identity["mcp_tool_resolution"]["status"] == (
        "unresolved"
    )
    assert unresolved_mcp_identity["relation_counts"] == {"invoked": 1}
    assert unresolved_mcp_identity["answer_admission"]["admitted"] is False
    assert unresolved_mcp_identity["answer_admission"]["status"] == (
        "unresolved"
    )
def test_time_scoped_mcp_tool_state_distinguishes_listing_from_invocation(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """Regression derived from W3 raw:742 listing versus raw:745 call."""
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = (
        tmp_path
        / "rollout-2026-07-10T10-05-00-time-scoped-mcp-state.jsonl"
    )
    write_jsonl(
        transcript,
        [
            {
                "timestamp": "2026-07-10T10:05:00Z",
                "type": "session_meta",
                "payload": {
                    "id": "time-scoped-mcp-state",
                    "cwd": str(workspace),
                },
            },
            {
                "timestamp": "2026-07-10T10:05:01Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "Check whether aoa_memo_search was actually "
                                "called, not merely listed."
                            ),
                        }
                    ],
                },
            },
            {
                "timestamp": "2026-07-10T10:05:02Z",
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call",
                    "name": "exec",
                    "call_id": "call-listing",
                    "input": (
                        "text(ALL_TOOLS.filter(x => "
                        "/aoa_memo/i.test(x.name)));"
                    ),
                },
            },
            {
                "timestamp": "2026-07-10T10:05:03Z",
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call_output",
                    "call_id": "call-listing",
                    "output": (
                        "available: "
                        "mcp__aoa_memo__aoa_memo_search"
                    ),
                },
            },
            {
                "timestamp": "2026-07-10T10:05:04Z",
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call",
                    "name": "exec",
                    "call_id": "call-invocation",
                    "input": (
                        "const r = await tools."
                        "mcp__aoa_memo__aoa_memo_search("
                        '{query:"foundation"}); text(r);'
                    ),
                },
            },
            {
                "timestamp": "2026-07-10T10:05:05Z",
                "type": "event_msg",
                "payload": {
                    "type": "mcp_tool_call_end",
                    "call_id": "exec-invocation",
                    "invocation": {
                        "server": "aoa_memo",
                        "tool": "aoa_memo_search",
                        "arguments": {"query": "foundation"},
                    },
                    "result": {
                        "Ok": {
                            "content": [],
                            "structuredContent": {"hits": []},
                            "isError": False,
                        }
                    },
                },
            },
            {
                "timestamp": "2026-07-10T10:05:06Z",
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call",
                    "name": "exec",
                    "call_id": "call-failed-invocation",
                    "input": (
                        "const r = await tools."
                        "mcp__aoa_memo__aoa_memo_search("
                        '{query:"missing"}); text(r);'
                    ),
                },
            },
            {
                "timestamp": "2026-07-10T10:05:07Z",
                "type": "event_msg",
                "payload": {
                    "type": "mcp_tool_call_end",
                    "call_id": "exec-failed-invocation",
                    "invocation": {
                        "server": "aoa_memo",
                        "tool": "aoa_memo_search",
                        "arguments": {"query": "missing"},
                    },
                    "result": {
                        "Ok": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": "tool failed",
                                }
                            ],
                            "isError": True,
                        }
                    },
                },
            },
            {
                "timestamp": "2026-07-10T10:05:07.100Z",
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call_output",
                    "call_id": "exec-failed-invocation",
                    "output": (
                        "Error executing tool aoa_memo_search: "
                        "synthetic failure"
                    ),
                },
            },
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "time-scoped-mcp-state",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )
    empty_codex_home = tmp_path / "empty-codex-home"
    empty_mcp_root = tmp_path / "empty-mcp-root"
    empty_codex_home.mkdir()
    empty_mcp_root.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(empty_codex_home))
    monkeypatch.setenv(
        "AOA_ENTITY_REGISTRY_MCP_SERVICES_ROOTS",
        str(empty_mcp_root),
    )
    indexed = module.search_index_sessions(
        aoa_root=aoa_root,
        target="all",
        rebuild=True,
    )
    assert indexed["ok"] is True
    # The rebuild refreshes the generated registry from source surfaces.  Add
    # the owner-neutral identity afterward so this fixture tests the consumer
    # route rather than depending on this host's configured MCP services.
    write_json(
        aoa_root / module.ENTITY_REGISTRY_PATH,
        {
            "schema_version": module.ENTITY_REGISTRY_SCHEMA_VERSION,
            "artifact_type": "entity_registry_snapshot",
            "generated_at": "2026-07-10T10:05:06Z",
            "generated_at_epoch": 1783677906.0,
            "ok": True,
            "aoa_root": str(aoa_root),
            "registry_path": str(
                aoa_root / module.ENTITY_REGISTRY_PATH
            ),
            "source_surfaces": ["synthetic_owner_neutral_mcp_fixture"],
            "counts_by_kind": {"mcp_tool": 1},
            "counts_by_status": {"active": 1},
            "entries": [
                {
                    "entity_id": "mcp_tool:aoa_memo_mcp_search",
                    "kind": "mcp_tool",
                    "canonical_key": "aoa_memo_mcp_search",
                    "aliases": [
                        "aoa_memo_search",
                        "aoa_memo_mcp:aoa_memo_search",
                    ],
                    "status": "active",
                    "source_surface": (
                        "synthetic_owner_neutral_mcp_fixture"
                    ),
                    "source_refs": [],
                }
            ],
        },
    )

    before_call = module.episode_entity_state_search(
        aoa_root=aoa_root,
        anchor="aoa_memo_search",
        kind="mcp_tool",
        session="time-scoped-mcp-state",
        time_to="2026-07-10T10:05:03.500Z",
        limit=20,
    )
    assert before_call["answer_admission"]["admitted"] is True
    assert (
        before_call["answer_admission"]["status"]
        == "not_invoked_in_requested_time_scope"
    )
    assert before_call["entity_state"] == (
        "mention_only_without_observed_invocation_in_requested_time_scope"
    )
    assert before_call["relation_counts"] == {"mentioned": 1}
    assert before_call["results"][0]["raw_ref"] == "raw:line:4"
    assert (
        before_call["results"][0]["admission_basis"]
        == "exact_tool_name_in_result_body_not_invocation"
    )
    assert (
        before_call["time_scoped_raw_state"]["source_integrity"][
            "status"
        ]
        == "verified"
    )
    assert before_call["time_scoped_raw_state"]["scan_complete"] is True

    after_call = module.episode_entity_state_search(
        aoa_root=aoa_root,
        anchor="aoa_memo_search",
        kind="mcp_tool",
        session="time-scoped-mcp-state",
        time_to="2026-07-10T10:05:04.500Z",
        limit=20,
    )
    assert (
        after_call["answer_admission"]["status"]
        == "invoked_in_requested_time_scope"
    )
    assert after_call["time_scoped_raw_state"]["invocation_count"] == 1
    assert after_call["time_scoped_raw_state"]["receipt_count"] == 0
    assert any(
        item["raw_ref"] == "raw:line:5"
        and item["source_lane"] == "structured_mcp_tool_invocation"
        for item in after_call["results"]
    )

    after_receipt = module.episode_entity_state_search(
        aoa_root=aoa_root,
        anchor="aoa_memo_search",
        kind="mcp_tool",
        session="time-scoped-mcp-state",
        time_to="2026-07-10T10:05:05.500Z",
        limit=20,
    )
    assert after_receipt["time_scoped_raw_state"]["invocation_count"] == 1
    assert (
        after_receipt["time_scoped_raw_state"][
            "invocation_evidence_count"
        ]
        == 2
    )
    assert after_receipt["time_scoped_raw_state"]["receipt_count"] == 1
    assert any(
        item["raw_ref"] == "raw:line:6"
        and item["source_lane"] == "structured_mcp_receipt"
        and item["relation"] == "verified_by"
        and item["outcome"] == "succeeded"
        for item in after_receipt["results"]
    )

    failed_window = module.episode_entity_state_search(
        aoa_root=aoa_root,
        anchor="aoa_memo_search",
        kind="mcp_tool",
        session="time-scoped-mcp-state",
        time_from="2026-07-10T10:05:05.600Z",
        time_to="2026-07-10T10:05:07.500Z",
        limit=20,
    )
    assert failed_window["time_scoped_raw_state"]["invocation_count"] == 1
    assert (
        failed_window["time_scoped_raw_state"]["invocation_evidence_count"]
        == 2
    )
    assert failed_window["time_scoped_raw_state"]["receipt_count"] == 1
    assert failed_window["relation_counts"] == {
        "failed_with": 1,
        "invoked": 1,
        "mentioned": 1,
    }
    assert any(
        item["raw_ref"] == "raw:line:8"
        and item["source_lane"] == "structured_mcp_receipt"
        and item["relation"] == "failed_with"
        and item["outcome"] == "failed"
        for item in failed_window["results"]
    )
    assert any(
        item["raw_ref"] == "raw:line:9"
        and item["source_lane"]
        == "correlated_mcp_tool_output_mirror"
        and item["relation"] == "mentioned"
        for item in failed_window["results"]
    )

    latest_limited = module.episode_entity_state_search(
        aoa_root=aoa_root,
        anchor="aoa_memo_search",
        kind="mcp_tool",
        session="time-scoped-mcp-state",
        time_to="2026-07-10T10:05:07.500Z",
        limit=2,
    )
    assert [
        item["raw_ref"]
        for item in latest_limited["results"]
    ] == ["raw:line:7", "raw:line:8"]
    assert latest_limited["truncation"]["truncated"] is True
    assert latest_limited["truncation"]["result_limit"] == 2

    session_dir = module.session_dir_from_record(
        module.resolve_session_record(
            aoa_root,
            "time-scoped-mcp-state",
        )
    )
    manifest = json.loads(
        (session_dir / "session.manifest.json").read_text(
            encoding="utf-8"
        )
    )
    truncated = module.episode_entity_time_scoped_raw_state(
        session_dir=session_dir,
        manifest=manifest,
        identities=after_receipt["mcp_tool_resolution"]["identities"],
        time_from="",
        time_to="2026-07-10T10:05:05.500000Z",
        max_lines=4,
    )
    assert truncated["invocation_count"] == 0
    assert truncated["line_budget_exhausted"] is True
    assert truncated["absence_claim_allowed"] is False
    assert truncated["answer_state"] == "unresolved"

    bounded_observations = module.episode_entity_time_scoped_raw_state(
        session_dir=session_dir,
        manifest=manifest,
        identities=after_receipt["mcp_tool_resolution"]["identities"],
        time_from="",
        time_to="2026-07-10T10:05:07.500000Z",
        max_observations=2,
    )
    assert bounded_observations["invocation_evidence_count"] == 4
    assert (
        bounded_observations["returned_invocation_evidence_count"]
        == 2
    )
    assert (
        bounded_observations["omitted_invocation_evidence_count"]
        == 2
    )
    assert bounded_observations["invocation_observations_truncated"] is True
    assert [
        item["raw_ref"]
        for item in bounded_observations["invocation_observations"]
    ] == ["raw:line:7", "raw:line:8"]

    query = (
        "Был ли aoa_memo_search уже реально вызван к "
        "2026-07-10T10:05:03.500Z, а не только перечислен "
        "среди доступных tools?"
    )
    plan = module.memory_query_plan(
        aoa_root=aoa_root,
        query=query,
        session="time-scoped-mcp-state",
        time_to="2026-07-10T10:05:03.500Z",
    )
    assert plan["primary_route"]["route_id"] == "episode_entity_state"
    assert (
        "episode-entity-state aoa_memo_mcp_search --kind mcp_tool"
        in plan["next_command"]
    )
    assert "--time-to 2026-07-10T10:05:03.500Z" in plan["next_command"]

    with transcript.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "timestamp": "2026-07-10T10:05:08Z",
                    "type": "event_msg",
                    "payload": {
                        "type": "agent_message",
                        "message": "live tail changed after archive snapshot",
                    },
                },
                ensure_ascii=False,
            )
            + "\n"
        )
    stale_source = module.episode_entity_state_search(
        aoa_root=aoa_root,
        anchor="aoa_memo_search",
        kind="mcp_tool",
        session="time-scoped-mcp-state",
        time_to="2026-07-10T10:05:03.500Z",
        limit=20,
    )
    assert stale_source["time_scoped_raw_state"]["scan_complete"] is True
    assert stale_source["time_scoped_raw_state"]["absence_claim_allowed"] is False
    assert stale_source["time_scoped_raw_state"]["source_freshness"][
        "status"
    ] in {"deferred", "stale"}
    assert stale_source["answer_admission"]["admitted"] is False
    assert stale_source["answer_admission"]["status"] == "unresolved"
def test_episode_operational_group_query_parses_parallel_read_cardinality() -> None:
    parsed = module.episode_operational_group_query(
        "где параллельно читали шесть eval skill bundles перед добавлением локального corpus"
    )

    assert parsed["active"] is True
    assert parsed["status"] == "parallel_operational_group_parsed"
    assert parsed["relation_basis"] == "explicit_parallel_cardinality"
    assert parsed["requested_cardinality"] == 6
    assert parsed["operation"] == "read"
    assert [term["token"] for term in parsed["subject_terms"]] == ["eval", "skill", "bundles"]
    assert [term["token"] for term in parsed["context_terms"]] == [
        "добавлением",
        "локального",
        "corpus",
    ]
    assert [term["token"] for term in parsed["retrieval_terms"]] == [
        "eval",
        "skill",
        "bundles",
        "добавлением",
        "локального",
        "corpus",
    ]
    assert parsed["retrieval_term_basis"] == (
        "typed_subject_plus_context_without_relation_words"
    )
    assert module.episode_operational_group_query(
        "все шесть aoa-eval subskills уже на месте"
    )["active"] is False
def test_episode_quantitative_comparison_requires_correlated_count_result(
    tmp_path: Path,
) -> None:
    raw_path = tmp_path / "session.raw.jsonl"
    rows = [
        {"type": "session_meta", "payload": {"id": "quantitative-session"}},
        {
            "timestamp": "2026-06-20T10:00:00Z",
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "exec_command",
                "call_id": "call_changed_parts",
                "arguments": json.dumps(
                    {
                        "cmd": (
                            "git diff --name-only v1.0.0..HEAD | "
                            "awk -F/ '$1==\"mechanics\"{print $2}' | "
                            "sort | uniq -c | sort -nr"
                        ),
                        "workdir": "/workspace/sdk-repo",
                    }
                ),
            },
        },
        {
            "timestamp": "2026-06-20T10:00:01Z",
            "type": "response_item",
            "payload": {
                "type": "function_call_output",
                "call_id": "call_changed_parts",
                "output": (
                    "Process exited with code 0\n"
                    "Final output:\n"
                    "  12 core\n"
                    "   8 runtime\n"
                    "   2 docs\n"
                ),
            },
        },
        {
            "timestamp": "2026-06-20T10:01:00Z",
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "exec_command",
                "call_id": "call_current_tree",
                "arguments": json.dumps(
                    {
                        "cmd": (
                            "git ls-tree -r --name-only HEAD sdk mechanics | "
                            "awk -F/ '$1==\"mechanics\"{parts[$2]++} "
                            "END{for (p in parts) print p, parts[p]}' | sort"
                        ),
                        "workdir": "/workspace/sdk-repo",
                    }
                ),
            },
        },
        {
            "timestamp": "2026-06-20T10:01:01Z",
            "type": "response_item",
            "payload": {
                "type": "function_call_output",
                "call_id": "call_current_tree",
                "output": (
                    "Process exited with code 0\n"
                    "Final output:\n"
                    "core 120\n"
                    "runtime 80\n"
                ),
            },
        },
        {
            "timestamp": "2026-06-20T10:02:00Z",
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "exec_command",
                "call_id": "call_version_mentions",
                "arguments": json.dumps(
                    {
                        "cmd": "rg -n 'v1\\.0\\.0' README.md mechanics",
                        "workdir": "/workspace/sdk-repo",
                    }
                ),
            },
        },
        {
            "timestamp": "2026-06-20T10:02:01Z",
            "type": "response_item",
            "payload": {
                "type": "function_call_output",
                "call_id": "call_version_mentions",
                "output": (
                    "Process exited with code 0\n"
                    "Final output:\n"
                    "README.md:3:Previous release v1.0.0\n"
                ),
            },
        },
    ]
    write_jsonl(raw_path, rows)
    query = module.episode_quantitative_comparison_query(
        "Какие части mechanics в sdk-repo сильнее всего изменились после v1.0.0?"
    )
    candidates = [
        {
            "doc_id": "episode_semantic:quantitative-session:task-target",
            "session_id": "quantitative-session",
            "task_episode_id": "task-target",
            "event_range": {"from_line": 2, "to_line": 3},
            "query_coverage": {
                "coverage": 0.75,
                "matched_term_count": 6,
                "coherent_term_count": 4,
            },
            "supporting_evidence": [],
        },
        {
            "doc_id": "episode_semantic:quantitative-session:task-false",
            "session_id": "quantitative-session",
            "task_episode_id": "task-false",
            "event_range": {"from_line": 4, "to_line": 7},
            "query_coverage": {
                "coverage": 0.75,
                "matched_term_count": 6,
                "coherent_term_count": 4,
            },
            "supporting_evidence": [],
        },
    ]

    hydrated, hydration = (
        module.episode_quantitative_comparison_scoped_raw_hydration(
            raw_path=raw_path,
            segments=[],
            results=candidates,
            comparison_query=query,
            max_raw_bytes=1024 * 1024,
            max_lines=100,
        )
    )
    qualified, gate = module.episode_quantitative_comparison_relation_gate(
        hydrated,
        query,
    )

    assert query["active"] is True
    assert query["status"] == "quantitative_comparison_parsed"
    assert [term["token"] for term in query["subject_terms"]] == ["mechanics"]
    assert [term["token"] for term in query["context_terms"]] == ["sdk", "repo"]
    assert [term["token"] for term in query["baseline_terms"]] == ["v1", "0"]
    assert hydration["status"] == "applied"
    assert hydration["qualified_candidate_count"] == 1
    assert [item["task_episode_id"] for item in qualified] == ["task-target"]
    assert gate["status"] == "qualified_quantitative_comparison_available"
    evidence = qualified[0]["quantitative_comparison"]
    assert evidence["correlation_id"] == "call_changed_parts"
    assert evidence["action"]["refs"]["raw"] == "raw:line:2"
    assert evidence["result"]["refs"]["raw"] == "raw:line:3"
    assert evidence["numeric_row_count"] == 3
    assert evidence["result_status"] == "succeeded"
    assert [item["refs"]["raw"] for item in qualified[0]["supporting_evidence"][:2]] == [
        "raw:line:2",
        "raw:line:3",
    ]
    admission = module.episode_answer_admission(
        qualified[0],
        query_term_count=8,
        quantitative_comparison_gate=gate,
    )
    assert admission["admitted"] is True
    assert admission["basis"] == "typed_quantitative_comparison_evidence"
    assert admission["relation_gate"]["required"] is True
    english_query = module.episode_quantitative_comparison_query(
        "Which mechanics parts in sdk-repo changed most since v1.0.0?"
    )
    assert [term["token"] for term in english_query["subject_terms"]] == [
        "mechanics"
    ]
    assert [term["token"] for term in english_query["context_terms"]] == [
        "sdk",
        "repo",
    ]
    english_hydrated, _english_hydration = (
        module.episode_quantitative_comparison_scoped_raw_hydration(
            raw_path=raw_path,
            segments=[],
            results=candidates,
            comparison_query=english_query,
            max_raw_bytes=1024 * 1024,
            max_lines=100,
        )
    )
    english_qualified, english_gate = (
        module.episode_quantitative_comparison_relation_gate(
            english_hydrated,
            english_query,
        )
    )
    assert [item["task_episode_id"] for item in english_qualified] == [
        "task-target"
    ]
    shadowed_top = {
        **english_qualified[0],
        "asserted_mutation": {
            "active": True,
            "status": "asserted_mutation_evidence_unresolved",
        },
    }
    shadowed_admission = module.episode_answer_admission(
        shadowed_top,
        query_term_count=8,
        quantitative_comparison_gate=english_gate,
    )
    assert shadowed_admission["admitted"] is True
    assert (
        shadowed_admission[
            "asserted_mutation_shadowed_by_quantitative_comparison"
        ]
        is True
    )
    assert module.episode_quantitative_comparison_query(
        "mechanics and sdk-repo both mention v1.0.0"
    )["active"] is False
def test_quantitative_length_comparison_requires_successful_measurement_chain(
    tmp_path: Path,
) -> None:
    query_text = "Какие AGENTS.md были длиннее?"
    query = module.episode_quantitative_comparison_query(query_text)
    intent = module.memory_query_intent(query_text)

    assert query["active"] is True
    assert query["operation"] == "line_count"
    assert query["relation_basis"] == (
        "line_count_comparison_requires_correlated_numeric_result"
    )
    assert [term["token"] for term in query["subject_terms"]] == [
        "agents",
        "md",
    ]
    assert intent["primary"] == "quantitative_comparison"
    assert intent["claim_shape"]["kind"] == "quantitative_comparison"

    raw_path = tmp_path / "rollout-length-comparison.jsonl"
    write_jsonl(
        raw_path,
        [
            {
                "timestamp": "2026-07-17T06:23:00Z",
                "type": "session_meta",
                "payload": {"id": "length-session"},
            },
            {
                "timestamp": "2026-07-17T06:23:01Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "exec_command",
                    "call_id": "call_lengths",
                    "arguments": json.dumps(
                        {
                            "cmd": (
                                "wc -l /workspace/one/AGENTS.md "
                                "/workspace/two/AGENTS.md"
                            )
                        }
                    ),
                },
            },
            {
                "timestamp": "2026-07-17T06:23:02Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "call_lengths",
                    "output": (
                        "Process exited with code 1\n"
                        "Final output:\n"
                        "196 /workspace/one/AGENTS.md\n"
                        "wc: /workspace/two/AGENTS.md: No such file\n"
                    ),
                },
            },
        ],
    )
    candidates = [
        {
            "doc_id": "episode_semantic:length-session:task-0001",
            "session_id": "length-session",
            "task_episode_id": "task-0001",
            "event_range": {"from_line": 1, "to_line": 3},
            "supporting_evidence": [],
        }
    ]
    hydrated, hydration = (
        module.episode_quantitative_comparison_scoped_raw_hydration(
            raw_path=raw_path,
            segments=[],
            results=candidates,
            comparison_query=query,
            max_raw_bytes=1024 * 1024,
            max_lines=100,
        )
    )
    qualified, gate = module.episode_quantitative_comparison_relation_gate(
        hydrated,
        query,
    )

    assert hydration["candidate_action_count"] == 1
    assert hydration["rejected_action_count"] == 1
    assert hydration["qualified_candidate_count"] == 0
    assert qualified == []
    assert gate["status"] == "no_qualified_quantitative_comparison"

    successful_path = tmp_path / "rollout-length-comparison-success.jsonl"
    write_jsonl(
        successful_path,
        [
            {
                "timestamp": "2026-07-17T06:23:00Z",
                "type": "session_meta",
                "payload": {"id": "length-session"},
            },
            {
                "timestamp": "2026-07-17T06:23:01Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "exec_command",
                    "call_id": "call_lengths",
                    "arguments": json.dumps(
                        {
                            "cmd": (
                                "wc -l /workspace/one/AGENTS.md "
                                "/workspace/two/AGENTS.md"
                            )
                        }
                    ),
                },
            },
            {
                "timestamp": "2026-07-17T06:23:02Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "call_lengths",
                    "output": (
                        "Process exited with code 0\n"
                        "Final output:\n"
                        "196 /workspace/one/AGENTS.md\n"
                        "246 /workspace/two/AGENTS.md\n"
                        "442 total\n"
                    ),
                },
            },
        ],
    )
    successful_hydrated, successful_hydration = (
        module.episode_quantitative_comparison_scoped_raw_hydration(
            raw_path=successful_path,
            segments=[],
            results=candidates,
            comparison_query=query,
            max_raw_bytes=1024 * 1024,
            max_lines=100,
        )
    )
    successful_qualified, successful_gate = (
        module.episode_quantitative_comparison_relation_gate(
            successful_hydrated,
            query,
        )
    )
    assert successful_hydration["qualified_candidate_count"] == 1
    assert successful_gate["status"] == (
        "qualified_quantitative_comparison_available"
    )
    successful_evidence = successful_qualified[0][
        "quantitative_comparison"
    ]
    assert successful_evidence["numeric_row_count"] == 2
    assert [
        row["label"]
        for row in successful_evidence["numeric_rows"]
    ] == [
        "/workspace/one/AGENTS.md",
        "/workspace/two/AGENTS.md",
    ]
    successful_admission = module.episode_answer_admission(
        successful_qualified[0],
        query_term_count=3,
        quantitative_comparison_gate=successful_gate,
    )
    assert successful_admission["admitted"] is True
    assert successful_admission["basis"] == (
        "typed_quantitative_comparison_evidence"
    )
    assert successful_admission["policy_version"] == 10
def test_episode_search_quantitative_comparison_is_wired_to_raw_relation_gate(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "AbyssOS"
    workspace.mkdir()
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-quantitative-integration.jsonl"
    write_jsonl(
        transcript,
        [
            {
                "timestamp": "2026-06-20T10:00:00Z",
                "type": "session_meta",
                "payload": {
                    "id": "quantitative-integration",
                    "cwd": str(workspace),
                },
            },
            {
                "timestamp": "2026-06-20T10:00:01Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "Inspect changes since v1.0.0.",
                        }
                    ],
                },
            },
            {
                "timestamp": "2026-06-20T10:00:02Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "exec_command",
                    "call_id": "call_changed_parts",
                    "arguments": json.dumps(
                        {
                            "cmd": (
                                "git diff --name-only v1.0.0..HEAD | "
                                "awk -F/ '$1==\"mechanics\"{print $2}' | "
                                "sort | uniq -c | sort -nr"
                            ),
                            "workdir": "/workspace/sdk-repo",
                        }
                    ),
                },
            },
            {
                "timestamp": "2026-06-20T10:00:03Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "call_changed_parts",
                    "output": (
                        "Process exited with code 0\n"
                        "Final output:\n"
                        "  12 core\n"
                        "   8 runtime\n"
                        "   2 docs\n"
                    ),
                },
            },
            {
                "timestamp": "2026-06-20T10:00:04Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "exec_command",
                    "call_id": "call_current_tree",
                    "arguments": json.dumps(
                        {
                            "cmd": (
                                "git ls-tree -r --name-only HEAD sdk mechanics | "
                                "awk -F/ '$1==\"mechanics\"{parts[$2]++} "
                                "END{for (p in parts) print p, parts[p]}' | sort"
                            ),
                            "workdir": "/workspace/sdk-repo",
                        }
                    ),
                },
            },
            {
                "timestamp": "2026-06-20T10:00:05Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "call_current_tree",
                    "output": (
                        "Process exited with code 0\n"
                        "Final output:\n"
                        "core 120\n"
                        "runtime 80\n"
                    ),
                },
            },
            {
                "timestamp": "2026-06-20T10:00:06Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",
                            "text": "Inspection complete.",
                        }
                    ],
                },
            },
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "quantitative-integration",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )
    index_result = module.search_index_sessions(
        aoa_root=aoa_root,
        target="all",
        rebuild=True,
    )
    assert index_result["ok"] is True

    result = module.episode_semantic_search(
        aoa_root=aoa_root,
        query=(
            "Какие части mechanics в sdk-repo сильнее всего "
            "изменились после v1.0.0?"
        ),
        session="quantitative-integration",
        mode="sparse",
        limit=5,
        explain=True,
    )

    assert result["result_count"] == 1
    assert (
        result["retrieval"]["quantitative_comparison_relation_gate"][
            "status"
        ]
        == "qualified_quantitative_comparison_available"
    )
    assert result["retrieval"]["answer_admission"]["admitted"] is True
    assert (
        result["retrieval"]["answer_admission"]["basis"]
        == "typed_quantitative_comparison_evidence"
    )
    top = result["results"][0]
    assert top["quantitative_comparison"]["correlation_id"] == (
        "call_changed_parts"
    )
    assert [
        item["refs"]["raw"] for item in top["supporting_evidence"][:2]
    ] == ["raw:line:3", "raw:line:4"]

    negative = module.episode_semantic_search(
        aoa_root=aoa_root,
        query=(
            "Какие части plugins в sdk-repo сильнее всего "
            "изменились после v1.0.0?"
        ),
        session="quantitative-integration",
        mode="sparse",
        limit=5,
    )
    assert negative["result_count"] == 0
    assert negative["retrieval"]["answer_admission"]["admitted"] is False
    assert (
        negative["abstention"]["status"]
        == "insufficient_quantitative_comparison_evidence"
    )

    negative_usage = module.episode_semantic_search(
        aoa_root=aoa_root,
        query="В этой сессии вообще не запускали git?",
        session="quantitative-integration",
        mode="sparse",
        limit=5,
        explain=True,
    )
    assert negative_usage["result_count"] == 1
    assert negative_usage["answer_admission"]["admitted"] is False
    assert negative_usage["answer_admission"]["status"] == (
        "negative_claim_scope_unresolved"
    )
    assert negative_usage["abstention"]["status"] == (
        "negative_claim_scope_unresolved"
    )
    assert negative_usage["next_route"]["status"] == "ready"
    assert "archived-raw-search" in negative_usage["next_command"]
    assert negative_usage["next_route"]["seed_anchor"] == "git"

    current_state = module.episode_semantic_search(
        aoa_root=aoa_root,
        query="Git repository aoa-sdk сейчас содержит эти mechanics changes?",
        session="quantitative-integration",
        mode="sparse",
        limit=5,
        explain=True,
    )
    assert current_state["result_count"] == 1
    assert current_state["answer_admission"]["admitted"] is False
    assert current_state["answer_admission"]["status"] == (
        "requires_current_owner_evidence"
    )
    assert current_state["next_route"]["route_id"] == (
        "external_current_owner_handoff"
    )
    assert current_state["next_route"]["handoff"]["owner_scope"] == (
        "repository_owner"
    )
def test_episode_operational_group_raw_hydration_requires_six_parallel_reads(
    tmp_path: Path,
) -> None:
    raw_path = tmp_path / "session.raw.jsonl"
    skill_names = (
        "aoa-eval",
        "aoa-eval-select",
        "aoa-eval-apply",
        "aoa-eval-local-need",
        "aoa-eval-design",
        "aoa-eval-session-mining",
    )
    rows: list[dict[str, Any]] = [
        {"type": "session_meta", "payload": {"id": "parallel-group-session"}},
        {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "Сейчас прочитаю skill bundles."}],
            },
        },
    ]
    for index, skill_name in enumerate(skill_names, start=1):
        rows.append(
            {
                "timestamp": f"2026-06-15T16:42:10.{300 + index:03d}Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "exec_command",
                    "call_id": f"call_parallel_read_{index}",
                    "arguments": json.dumps(
                        {
                            "cmd": f"sed -n '1,220p' skills/core/engineering/{skill_name}/SKILL.md",
                            "workdir": "/workspace/aoa-skills",
                        }
                    ),
                },
            }
        )
    for index in range(1, 7):
        rows.append(
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": f"call_parallel_read_{index}",
                    "output": "Process exited with code 0\nOutput:\n---\nname: aoa-eval",
                },
            }
        )
    rows.append(
        {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "Теперь проверю live skill pack."}],
            },
        }
    )
    for index, command in enumerate(
        (
            "python scripts/bundles/verify_skill_pack.py --format json",
            "python scripts/bundles/install_skill_pack.py --help",
            "sha256sum .agents/skills/aoa-eval/SKILL.md",
            "find /home/user/.codex/skills -maxdepth 1 -type d",
        ),
        start=1,
    ):
        rows.append(
            {
                "timestamp": f"2026-06-18T23:53:06.{100 + index:03d}Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "exec_command",
                    "call_id": f"call_parallel_verify_{index}",
                    "arguments": json.dumps({"cmd": command}),
                },
            }
        )
    for index in range(1, 5):
        rows.append(
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": f"call_parallel_verify_{index}",
                    "output": "Process exited with code 0\nOutput:\nok",
                },
            }
        )
    write_jsonl(raw_path, rows)
    query = module.episode_operational_group_query(
        "где параллельно читали шесть eval skill bundles перед добавлением локального corpus"
    )
    candidates = [
        {
            "doc_id": "episode_semantic:parallel-group-session:task-target",
            "session_id": "parallel-group-session",
            "task_episode_id": "task-target",
            "event_range": {"from_line": 2, "to_line": 14},
        },
        {
            "doc_id": "episode_semantic:parallel-group-session:task-false",
            "session_id": "parallel-group-session",
            "task_episode_id": "task-false",
            "event_range": {"from_line": 15, "to_line": len(rows)},
        },
    ]

    hydrated, report = module.episode_operational_group_scoped_raw_hydration(
        raw_path=raw_path,
        segments=[],
        results=candidates,
        group_query=query,
        max_raw_bytes=1024 * 1024,
        max_lines=100,
    )
    qualified, gate = module.episode_operational_group_relation_gate(hydrated, query)

    assert report["status"] == "applied"
    assert report["observed_parallel_group_count"] == 2
    assert report["qualified_candidate_count"] == 1
    assert [item["task_episode_id"] for item in qualified] == ["task-target"]
    assert gate["status"] == "qualified_operational_groups_available"
    evidence = qualified[0]["operational_group"]
    assert evidence["kind"] == "parallel_tool_call_group"
    assert evidence["cardinality"] == 6
    assert evidence["read_member_count"] == 6
    assert evidence["distinct_target_count"] == 6
    assert len(evidence["members"]) == 6
    assert evidence["members"][0]["refs"]["raw"] == "raw:line:3"
    assert evidence["members"][0]["refs"]["result_raw"] == "raw:line:9"
    assert hydrated[1].get("operational_group", {}).get("accepted") is not True
def test_episode_operational_group_global_candidate_blocks_preserve_raw_lines(
    tmp_path: Path,
) -> None:
    session_dir = tmp_path / "session-target"
    blocks_dir = session_dir / "raw" / "blocks"
    blocks_dir.mkdir(parents=True)
    block_path = blocks_dir / "000__initial-to-compaction.raw.jsonl.gz"
    rows: list[dict[str, Any]] = []
    for index in range(1, 7):
        rows.append(
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "exec_command",
                    "call_id": f"call_global_parallel_{index}",
                    "arguments": json.dumps(
                        {
                            "cmd": (
                                "sed -n '1,180p' "
                                f"skills/core/engineering/aoa-eval-{index}/SKILL.md"
                            )
                        }
                    ),
                },
            }
        )
    for index in range(1, 7):
        rows.append(
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": f"call_global_parallel_{index}",
                    "output": "Process exited with code 0\nOutput:\nname: aoa-eval",
                },
            }
        )
    raw_text = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    with module.gzip.open(block_path, "wt", encoding="utf-8") as handle:
        handle.write(raw_text)
    manifest_path = session_dir / "session.manifest.json"
    write_json(
        manifest_path,
        {
            "session_id": "global-parallel-session",
            "segments": [
                {
                    "segment_id": "000",
                    "markdown": str(session_dir / "segments" / "000.md"),
                    "index": str(session_dir / "segments" / "000.index.json"),
                    "source_range": {"from_line": 100, "to_line": 111},
                    "raw_block": {
                        "compressed_path": str(block_path),
                        "compressed_sha256": module.sha256_file(block_path),
                        "compressed_bytes": block_path.stat().st_size,
                        "uncompressed_bytes": len(raw_text.encode("utf-8")),
                        "source_range": {"from_line": 100, "to_line": 111},
                    },
                }
            ],
        },
    )
    candidates = [
        {
            "doc_id": "episode_semantic:wrong-session:task-wrong",
            "session_id": "wrong-session",
            "task_episode_id": "task-wrong",
            "event_range": {"from_line": 1, "to_line": 20},
            "session_ref": str(tmp_path / "missing-session.manifest.json"),
        },
        {
            "doc_id": "episode_semantic:global-parallel-session:task-target",
            "session_id": "global-parallel-session",
            "task_episode_id": "task-target",
            "event_range": {"from_line": 100, "to_line": 111},
            "session_ref": str(manifest_path),
        },
    ]
    query = module.episode_operational_group_query(
        "where six eval skill bundles were read in parallel before local corpus"
    )

    raw_sources, selection = module.episode_operational_group_candidate_raw_blocks(
        candidates
    )
    hydrated, hydration = module.episode_operational_group_scoped_raw_hydration(
        raw_path=None,
        raw_sources=raw_sources,
        segments=[],
        results=candidates,
        group_query=query,
        max_raw_bytes=1024 * 1024,
        max_lines=100,
    )
    qualified, gate = module.episode_operational_group_relation_gate(hydrated, query)

    assert selection["status"] == "candidate_raw_blocks_selected"
    assert selection["selected_block_count"] == 1
    assert hydration["read_scope"] == "candidate_raw_blocks"
    assert hydration["source_integrity"]["verified_count"] == 1
    assert gate["status"] == "qualified_operational_groups_available"
    assert [item["task_episode_id"] for item in qualified] == ["task-target"]
    evidence = qualified[0]["operational_group"]
    assert evidence["from_line"] == 100
    assert evidence["to_line"] == 105
    assert evidence["members"][0]["refs"]["raw"] == "raw:line:100"
    assert evidence["members"][0]["refs"]["result_raw"] == "raw:line:106"

    corrupt_sources = [{**raw_sources[0], "expected_sha256": "0" * 64}]
    corrupt_hydrated, corrupt_report = module.episode_operational_group_scoped_raw_hydration(
        raw_path=None,
        raw_sources=corrupt_sources,
        segments=[],
        results=candidates,
        group_query=query,
        max_raw_bytes=1024 * 1024,
        max_lines=100,
    )
    corrupt_qualified, corrupt_gate = module.episode_operational_group_relation_gate(
        corrupt_hydrated,
        query,
    )

    assert corrupt_report["status"] == "candidate_raw_block_integrity_failed"
    assert corrupt_report["source_integrity"]["verified_count"] == 0
    assert corrupt_report["source_integrity"]["failed_count"] == 1
    assert corrupt_qualified == []
    assert corrupt_gate["status"] == "no_qualified_operational_group"
def test_episode_operational_group_global_blocks_isolate_correlation_ids_by_session(
    tmp_path: Path,
) -> None:
    call_ids = [f"shared-call-{index}" for index in range(1, 7)]
    calls_path = tmp_path / "session-a.jsonl.gz"
    results_path = tmp_path / "session-b.jsonl.gz"
    call_rows = [
        {
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "exec_command",
                "call_id": call_id,
                "arguments": json.dumps(
                    {
                        "cmd": (
                            "sed -n '1,180p' "
                            f"skills/core/engineering/aoa-eval-{index}/SKILL.md"
                        )
                    }
                ),
            },
        }
        for index, call_id in enumerate(call_ids, start=1)
    ]
    result_rows = [
        {
            "type": "response_item",
            "payload": {
                "type": "function_call_output",
                "call_id": call_id,
                "output": "Process exited with code 0\nOutput:\nok",
            },
        }
        for call_id in call_ids
    ]
    call_text = "".join(json.dumps(row) + "\n" for row in call_rows)
    result_text = "".join(json.dumps(row) + "\n" for row in result_rows)
    with module.gzip.open(calls_path, "wt", encoding="utf-8") as handle:
        handle.write(call_text)
    with module.gzip.open(results_path, "wt", encoding="utf-8") as handle:
        handle.write(result_text)
    raw_sources = [
        {
            "path": str(calls_path),
            "compression": "gzip",
            "expected_sha256": module.sha256_file(calls_path),
            "session_id": "session-a",
            "from_line": 100,
            "to_line": 105,
            "line_count": 6,
            "stored_bytes": calls_path.stat().st_size,
            "uncompressed_bytes": len(call_text.encode()),
        },
        {
            "path": str(results_path),
            "compression": "gzip",
            "expected_sha256": module.sha256_file(results_path),
            "session_id": "session-b",
            "from_line": 200,
            "to_line": 205,
            "line_count": 6,
            "stored_bytes": results_path.stat().st_size,
            "uncompressed_bytes": len(result_text.encode()),
        },
    ]
    candidates = [
        {
            "doc_id": "episode_semantic:session-a:task-a",
            "session_id": "session-a",
            "task_episode_id": "task-a",
            "event_range": {"from_line": 100, "to_line": 105},
        },
        {
            "doc_id": "episode_semantic:session-b:task-b",
            "session_id": "session-b",
            "task_episode_id": "task-b",
            "event_range": {"from_line": 200, "to_line": 205},
        },
    ]
    query = module.episode_operational_group_query(
        "where six eval skill bundles were read in parallel"
    )

    hydrated, report = module.episode_operational_group_scoped_raw_hydration(
        raw_path=None,
        raw_sources=raw_sources,
        segments=[],
        results=candidates,
        group_query=query,
        max_raw_bytes=1024 * 1024,
        max_lines=100,
    )
    qualified, gate = module.episode_operational_group_relation_gate(hydrated, query)

    assert report["source_integrity"]["verified_count"] == 2
    assert report["observed_parallel_group_count"] == 1
    assert qualified == []
    assert gate["status"] == "no_qualified_operational_group"
    assert hydrated[0].get("operational_group", {}).get("accepted") is not True
def test_episode_temporal_scoped_raw_hydration_recovers_correlated_action_results(
    tmp_path: Path,
) -> None:
    raw_path = tmp_path / "session.raw.jsonl"
    write_jsonl(
        raw_path,
        [
            {
                "timestamp": "2026-06-11T00:00:00Z",
                "type": "session_meta",
                "payload": {"id": "temporal-raw-session", "cwd": "/workspace/project"},
            },
            {
                "timestamp": "2026-06-11T00:00:01Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "exec_command",
                    "call_id": "call-compile-anchor",
                    "arguments": json.dumps({"cmd": "python -m py_compile src/runtime.py"}),
                },
            },
            {
                "timestamp": "2026-06-11T00:00:02Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "call-compile-anchor",
                    "output": "Process exited with code 0\nFinal output:\n",
                },
            },
            {
                "timestamp": "2026-06-11T00:00:03Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "exec_command",
                    "call_id": "call-contract-anchor",
                    "arguments": json.dumps({"cmd": "pytest -q tests/test_runtime_contract.py"}),
                },
            },
            {
                "timestamp": "2026-06-11T00:00:04Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "call-contract-anchor",
                    "output": "Process exited with code 1\nFinal output:\n1 failed\n",
                },
            },
            {
                "timestamp": "2026-06-11T00:00:05Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",
                            "text": (
                                "A later narrative only mentions call-compile-anchor and "
                                "call-contract-anchor; it is not the operational chain."
                            ),
                        }
                    ],
                },
            },
        ],
    )
    query = (
        "what happened between call-compile-anchor py_compile exit 0 and "
        "call-contract-anchor pytest exit 1"
    )
    temporal_span = module.episode_temporal_span_query(query)
    candidates = [
        {
            "doc_id": "episode_semantic:temporal-raw-session:task-0001",
            "session_id": "temporal-raw-session",
            "task_episode_id": "task-0001",
            "event_range": {"from_line": 1, "to_line": 6},
            "temporal_span": {
                "active": True,
                "status": "temporal_span_unresolved_or_unordered",
                "ranking_boost": 0.0,
            },
        }
    ]

    hydrated, hydration = module.episode_temporal_scoped_raw_hydration(
        raw_path=raw_path,
        segments=[],
        results=candidates,
        temporal_span=temporal_span,
        max_raw_bytes=1024 * 1024,
        max_lines=100,
    )

    evidence = hydrated[0]["temporal_span"]
    assert hydration["status"] == "applied"
    assert hydration["qualified_candidate_count"] == 1
    assert evidence["status"] == "ordered_span_found"
    assert evidence["evidence_source"] == "scoped_raw_structured_chain"
    assert evidence["authority"] == "raw_session_transcript"
    assert evidence["left"]["refs"]["raw"] == "raw:line:3"
    assert evidence["left"]["chain_from_raw_ref"] == "raw:line:2"
    assert evidence["right"]["refs"]["raw"] == "raw:line:5"
    assert evidence["right"]["chain_from_raw_ref"] == "raw:line:4"
    assert evidence["left"]["correlation_id"] == "call-compile-anchor"
    assert evidence["right"]["correlation_id"] == "call-contract-anchor"
def test_episode_temporal_scoped_raw_hydration_preserves_weak_compound_status_qualifiers(
    tmp_path: Path,
) -> None:
    """Manual-derived regression for a failed nested patch followed by retry."""
    raw_path = tmp_path / "session.raw.jsonl"
    write_jsonl(
        raw_path,
        [
            {
                "timestamp": "2026-07-11T04:43:20Z",
                "type": "session_meta",
                "payload": {
                    "id": "temporal-patch-recovery-session",
                    "cwd": "/workspace/project",
                },
            },
            {
                "timestamp": "2026-07-11T04:43:21Z",
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call",
                    "name": "exec",
                    "call_id": "call_failed_patch_123",
                    "input": (
                        "const patch = 'first attempt'; "
                        "text(await tools.apply_patch(patch));"
                    ),
                },
            },
            {
                "timestamp": "2026-07-11T04:43:22Z",
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call_output",
                    "call_id": "call_failed_patch_123",
                    "output": [
                        {"type": "input_text", "text": "Script failed"},
                        {
                            "type": "input_text",
                            "text": (
                                "apply_patch verification failed: "
                                "Failed to find context"
                            ),
                        },
                    ],
                },
            },
            {
                "timestamp": "2026-07-11T04:43:23Z",
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call",
                    "name": "exec",
                    "call_id": "call_retry_patch_456",
                    "input": (
                        "const patch = 'corrected attempt'; "
                        "text(await tools.apply_patch(patch));"
                    ),
                },
            },
            {
                "timestamp": "2026-07-11T04:43:24Z",
                "type": "event_msg",
                "payload": {
                    "type": "patch_apply_end",
                    "call_id": "exec_retry_patch_456",
                    "status": "completed",
                },
            },
            {
                "timestamp": "2026-07-11T04:43:24.5Z",
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call_output",
                    "call_id": "call_retry_patch_456",
                    "output": [
                        {"type": "input_text", "text": "Script completed"},
                        {"type": "input_text", "text": "{}"},
                    ],
                },
            },
            {
                "timestamp": "2026-07-11T04:43:24.700Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",
                            "text": (
                                "A planning note merely mentions apply_patch "
                                "verification succeeded; it is not a "
                                "structured result."
                            ),
                        }
                    ],
                },
            },
            {
                "timestamp": "2026-07-11T04:43:25Z",
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call",
                    "name": "exec",
                    "call_id": "call_focused_pytest_789",
                    "input": (
                        "const result = await tools.exec_command({"
                        "cmd: 'python -m pytest -q tests/test_target.py'});"
                    ),
                },
            },
            {
                "timestamp": "2026-07-11T04:43:26Z",
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call_output",
                    "call_id": "call_focused_pytest_789",
                    "output": [
                        {"type": "input_text", "text": "Script completed"},
                        {"type": "input_text", "text": "44 passed in 0.17s"},
                    ],
                },
            },
        ],
    )
    candidates = [
        {
            "doc_id": "episode_semantic:temporal-patch-recovery-session:task-0001",
            "session_id": "temporal-patch-recovery-session",
            "task_episode_id": "task-0001",
            "event_range": {"from_line": 1, "to_line": 9},
            "temporal_span": {
                "active": True,
                "status": "temporal_span_unresolved_or_unordered",
            },
        }
    ]

    def run_query(query_text: str) -> tuple[
        list[dict[str, Any]], dict[str, Any], dict[str, Any]
    ]:
        temporal_span = module.episode_temporal_span_query(query_text)
        hydrated, report = module.episode_temporal_scoped_raw_hydration(
            raw_path=raw_path,
            segments=[],
            results=candidates,
            temporal_span=temporal_span,
            max_raw_bytes=1024 * 1024,
            max_lines=100,
        )
        qualified, gate = module.episode_temporal_relation_gate(
            hydrated,
            temporal_span,
        )
        return qualified, report, gate

    qualified, report, gate = run_query(
        "что происходило 2026-07-11 между "
        "apply_patch verification failed и 44 passed"
    )

    assert report["left_anchor_term_basis"] == "multiple_code_anchor_terms"
    assert report["left_effective_anchor_term_count"] == 4
    assert report["left_required_qualifier_terms"] == [
        "verification",
        "failed",
    ]
    assert report["right_required_qualifier_terms"] == ["44", "passed"]
    assert report["qualified_candidate_count"] == 1
    assert gate["status"] == "qualified_ordered_spans_available"
    evidence = qualified[0]["temporal_span"]
    assert evidence["left"]["refs"]["raw"] == "raw:line:3"
    assert evidence["left"]["chain_from_raw_ref"] == "raw:line:2"
    assert evidence["left"]["matched_query_terms"] == [
        "apply",
        "failed",
        "patch",
        "verification",
    ]
    assert evidence["right"]["refs"]["raw"] == "raw:line:9"
    assert evidence["right"]["chain_from_raw_ref"] == "raw:line:8"
    assert evidence["interval_contents_status"] == (
        "bounded_interval_contents_read"
    )
    assert [
        item["refs"]["raw"]
        for item in evidence["interval_contents"]["events"]
    ] == [
        "raw:line:4",
        "raw:line:5",
        "raw:line:6",
        "raw:line:7",
        "raw:line:8",
    ]
    assert evidence["interval_contents"]["events"][1]["event_kind"] == (
        "structured_status_event"
    )
    assert evidence["interval_contents"]["events"][1]["payload_type"] == (
        "patch_apply_end"
    )
    assert evidence["interval_contents"]["events"][1]["result_outcome"] == (
        "completed"
    )
    admission = module.episode_answer_admission(
        qualified[0],
        query_term_count=6,
        temporal_relation_gate=gate,
    )
    assert admission["admitted"] is True
    assert admission["basis"] == "typed_temporal_interval_contents_evidence"

    false_success, false_success_report, false_success_gate = run_query(
        "что происходило 2026-07-11 между "
        "apply_patch verification succeeded и 44 passed"
    )
    assert false_success_report["left_anchor_term_basis"] == (
        "multiple_code_anchor_terms"
    )
    assert false_success_report["left_effective_anchor_term_count"] == 4
    assert false_success_report["left_required_qualifier_terms"] == [
        "verification",
        "succeeded",
    ]
    assert false_success_report["matched_unit_observed_count"] >= 2
    assert false_success == []
    assert false_success_gate["status"] == "no_qualified_ordered_span"

    wrong_order, wrong_order_report, wrong_order_gate = run_query(
        "что происходило 2026-07-11 между "
        "44 passed и apply_patch verification failed"
    )
    assert wrong_order_report["qualified_pair_count"] == 0
    assert wrong_order == []
    assert wrong_order_gate["status"] == "no_qualified_ordered_span"
def test_episode_temporal_scoped_raw_hydration_resolves_typed_parent_message_to_task_complete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression derived from a real subagent send_message temporal miss."""

    def run_case(
        target: str,
        *,
        terminal_event: bool = True,
        query_text: str = (
            "что происходило 2026-07-10 между отправкой сообщения "
            "родителю и task_complete"
        ),
    ) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
        case_suffix = "terminal" if terminal_event else "mention-only"
        raw_path = tmp_path / (
            f"session-{target.rsplit('/', 1)[-1] or 'root'}-{case_suffix}.raw.jsonl"
        )
        write_jsonl(
            raw_path,
            [
                {
                    "timestamp": "2026-07-10T22:54:29Z",
                    "type": "session_meta",
                    "payload": {
                        "id": "temporal-parent-message-session",
                        "agent_path": "/root/removal_proof_audit",
                    },
                },
                {
                    "timestamp": "2026-07-10T22:54:29.1Z",
                    "type": "session_meta",
                    "payload": {
                        "id": "replayed-parent-session-without-agent-path",
                    },
                },
                {
                    "timestamp": "2026-07-10T22:54:30Z",
                    "type": "event_msg",
                    "payload": {
                        "type": "task_complete",
                        "turn_id": "turn-earlier-independent",
                    },
                },
                {
                    "timestamp": "2026-07-10T22:54:34Z",
                    "type": "response_item",
                    "payload": {
                        "type": "function_call",
                        "name": "send_message",
                        "namespace": "collaboration",
                        "call_id": "call_ParentMessage123",
                        "arguments": json.dumps(
                            {
                                "target": target,
                                "message": "opaque-private-body",
                            }
                        ),
                    },
                },
                {
                    "timestamp": "2026-07-10T22:54:34.1Z",
                    "type": "event_msg",
                    "payload": {
                        "type": "sub_agent_activity",
                        "event_id": "call_ParentMessage123",
                    },
                },
                {
                    "timestamp": "2026-07-10T22:54:34.2Z",
                    "type": "response_item",
                    "payload": {
                        "type": "function_call_output",
                        "call_id": "call_ParentMessage123",
                        "output": "",
                    },
                },
                {
                    "timestamp": "2026-07-10T22:54:34.3Z",
                    "type": "event_msg",
                    "payload": {
                        "type": "token_count",
                        "info": {"total_token_usage": {"total_tokens": 17}},
                    },
                },
                {
                    "timestamp": "2026-07-10T22:54:34.4Z",
                    "type": "response_item",
                    "payload": {
                        "type": "reasoning",
                        "summary": [
                            {
                                "type": "summary_text",
                                "text": "hidden-reasoning-marker",
                            }
                        ],
                    },
                },
                {
                    "timestamp": "2026-07-10T22:54:35Z",
                    "type": "response_item",
                    "payload": {
                        "type": "custom_tool_call",
                        "name": "exec",
                        "call_id": "call_InteriorVerification123",
                        "input": "const result = await tools.exec_command({cmd: 'verify'});",
                    },
                },
                {
                    "timestamp": "2026-07-10T22:54:35.1Z",
                    "type": "response_item",
                    "payload": {
                        "type": "custom_tool_call_output",
                        "call_id": "call_InteriorVerification123",
                        "output": "verification completed",
                    },
                },
                {
                    "timestamp": "2026-07-10T22:54:35.2Z",
                    "type": "event_msg",
                    "payload": {
                        "type": "token_count",
                        "info": {"total_token_usage": {"total_tokens": 31}},
                    },
                },
                {
                    "timestamp": "2026-07-10T22:54:35.3Z",
                    "type": "response_item",
                    "payload": {
                        "type": "reasoning",
                        "summary": [
                            {
                                "type": "summary_text",
                                "text": "second-hidden-reasoning-marker",
                            }
                        ],
                    },
                },
                {
                    "timestamp": "2026-07-10T22:55:07.4Z",
                    "type": "event_msg",
                    "payload": {
                        "type": "agent_message",
                        "message": "runtime-mirror-marker Final removal proof audit.",
                    },
                },
                {
                    "timestamp": "2026-07-10T22:55:07.5Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {
                                "type": "output_text",
                                "text": "Final removal proof audit.",
                            }
                        ],
                    },
                },
                *(
                    [
                        {
                            "timestamp": "2026-07-10T22:55:07.6Z",
                            "type": "event_msg",
                            "payload": {
                                "type": "task_complete",
                                "turn_id": "turn-parent-message",
                            },
                        }
                    ]
                    if terminal_event
                    else [
                        {
                            "timestamp": "2026-07-10T22:55:07.6Z",
                            "type": "response_item",
                            "payload": {
                                "type": "message",
                                "role": "assistant",
                                "content": [
                                    {
                                        "type": "output_text",
                                        "text": (
                                            "The text task_complete is mentioned, but "
                                            "no terminal event was observed."
                                        ),
                                    }
                                ],
                            },
                        }
                    ]
                ),
            ],
        )
        temporal_span = module.episode_temporal_span_query(query_text)
        candidates = [
            {
                "doc_id": "episode_semantic:temporal-parent-message-session:task-0001",
                "session_id": "temporal-parent-message-session",
                "task_episode_id": "task-0001",
                "event_range": {"from_line": 1, "to_line": 15},
                "temporal_span": {
                    "active": True,
                    "status": "temporal_span_unresolved_or_unordered",
                },
            }
        ]
        hydrated, report = module.episode_temporal_scoped_raw_hydration(
            raw_path=raw_path,
            segments=[],
            results=candidates,
            temporal_span=temporal_span,
            max_raw_bytes=1024 * 1024,
            max_lines=100,
        )
        qualified, gate = module.episode_temporal_relation_gate(
            hydrated,
            temporal_span,
        )
        return qualified, report, gate

    qualified, report, gate = run_case("/root")

    assert report["typed_anchor_support_observed_count"] == 1
    assert report["qualified_candidate_count"] == 1
    assert gate["status"] == "qualified_ordered_spans_available"
    evidence = qualified[0]["temporal_span"]
    assert evidence["answer_scope"] == "interval_contents"
    assert evidence["left"]["refs"]["raw"] == "raw:line:4"
    assert evidence["left"]["event_kind"] == "structured_action"
    assert evidence["left"]["typed_alias_support"]["basis"] == (
        "structured_send_message_to_parent"
    )
    assert evidence["left"]["typed_alias_support"]["message_body_read"] is False
    assert "opaque-private-body" not in evidence["left"]["text"]
    assert evidence["right"]["refs"]["raw"] == "raw:line:15"
    assert evidence["right"]["event_kind"] == "structured_terminal_event"
    assert evidence["right"]["payload_type"] == "task_complete"
    assert evidence["right"]["event_identity"] == "turn-parent-message"
    assert evidence["right"]["equivalent_observation_count"] == 1
    assert evidence["evidence_time_scope"][
        "all_evidence_in_requested_window"
    ] is True
    assert {
        item["refs"]["raw"]
        for item in evidence["right"]["equivalent_observations"]
    } == {"raw:line:15"}
    assert evidence["interval_contents_status"] == (
        "bounded_interval_contents_read"
    )
    interval_contents = evidence["interval_contents"]
    assert interval_contents["truncated"] is False
    assert interval_contents["readable_event_count"] == 5
    assert [
        item["refs"]["raw"] for item in interval_contents["events"]
    ] == [
        "raw:line:5",
        "raw:line:6",
        "raw:line:9",
        "raw:line:10",
        "raw:line:14",
    ]
    assert [
        item["event_kind"] for item in interval_contents["events"]
    ] == [
        "structured_status_event",
        "structured_action_result_chain",
        "structured_action",
        "structured_action_result_chain",
        "canonical_message_observation",
    ]
    assert interval_contents["events"][-1]["text"] == (
        "Final removal proof audit."
    )
    interval_json = json.dumps(interval_contents, ensure_ascii=False)
    assert "opaque-private-body" not in interval_json
    assert "hidden-reasoning-marker" not in interval_json
    assert "runtime-mirror-marker" not in interval_json
    admission = module.episode_answer_admission(
        qualified[0],
        query_term_count=9,
        temporal_relation_gate=gate,
    )
    assert admission["admitted"] is True
    assert admission["basis"] == (
        "typed_temporal_interval_contents_evidence"
    )
    assert admission["typed_temporal_span_admitted"] is False
    assert admission["typed_temporal_interval_admitted"] is True
    assert admission["evidence_ref_gate"]["admitted"] is True
    assert admission["evidence_ref_gate"]["claim_evidence_ref_count"] == 7
    assert admission["evidence_ref_gate"]["basis"] == (
        "admitted_claim_chain_has_resolvable_refs"
    )

    mention_only_qualified, _mention_only_report, mention_only_gate = run_case(
        "/root",
        terminal_event=False,
    )
    assert mention_only_qualified == []
    assert mention_only_gate["status"] == "no_qualified_ordered_span"

    wrong_target_qualified, wrong_target_report, wrong_target_gate = run_case(
        "/root/unrelated_sibling"
    )
    assert wrong_target_report["typed_anchor_support_observed_count"] == 1
    assert wrong_target_qualified == []
    assert wrong_target_gate["status"] == "no_qualified_ordered_span"

    exact_wrong_target, _exact_wrong_report, exact_wrong_gate = run_case(
        "/root",
        query_text=(
            "что происходило 2026-07-10 между send_message target "
            "/root/unrelated_sibling и task_complete"
        ),
    )
    assert exact_wrong_target == []
    assert exact_wrong_gate["status"] == "no_qualified_ordered_span"

    wrong_date, wrong_date_report, wrong_date_gate = run_case(
        "/root",
        query_text=(
            "что происходило 2026-07-11 между отправкой сообщения "
            "родителю и task_complete"
        ),
    )
    assert wrong_date == []
    assert wrong_date_report["time_scope_requested"] is True
    assert wrong_date_report["time_scope_filtered_event_count"] > 0
    assert wrong_date_gate["status"] == "no_qualified_ordered_span"

    monkeypatch.setattr(
        module,
        "EPISODE_TEMPORAL_INTERVAL_OUTPUT_EVENT_LIMIT",
        2,
    )
    truncated_interval, _truncated_report, truncated_gate = run_case(
        "/root"
    )
    assert truncated_gate["status"] == (
        "qualified_ordered_spans_available"
    )
    truncated_evidence = truncated_interval[0]["temporal_span"]
    assert truncated_evidence["interval_contents_status"] == (
        "bounded_interval_contents_truncated"
    )
    assert truncated_evidence["interval_contents"]["truncated"] is True
    assert truncated_evidence["interval_contents"][
        "omitted_event_count"
    ] == 3
    truncated_admission = module.episode_answer_admission(
        truncated_interval[0],
        query_term_count=9,
        temporal_relation_gate=truncated_gate,
    )
    assert truncated_admission["admitted"] is False
    assert truncated_admission["basis"] == (
        "temporal_interval_contents_not_read"
    )
    assert truncated_admission[
        "typed_temporal_interval_admitted"
    ] is False
def test_episode_temporal_candidate_block_builds_source_aware_cross_episode_action_sequence(
    tmp_path: Path,
) -> None:
    """Manual-derived regression for a long-session correction and cleanup chain."""
    block_path = tmp_path / "bounded.raw.jsonl"
    rows = [
        {
            "timestamp": "2026-06-12T10:00:00Z",
            "type": "session_meta",
            "payload": {"id": "temporal-sequence-session"},
        },
        {
            "timestamp": "2026-06-12T10:00:01Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": (
                            "I incorrectly treated clean work as read-only; "
                            "the correction requires action."
                        ),
                    }
                ],
            },
        },
        {
            "timestamp": "2026-06-12T10:00:02Z",
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "exec_command",
                "call_id": "call_sequence_discovery",
                "arguments": json.dumps(
                    {"cmd": "find /tmp -name 'tts-hotpath-test-*' -print"}
                ),
            },
        },
        {
            "timestamp": "2026-06-12T10:00:03Z",
            "type": "response_item",
            "payload": {
                "type": "function_call_output",
                "call_id": "call_sequence_discovery",
                "output": (
                    "Process exited with code 0\nOutput:\n"
                    "/tmp/tts-hotpath-test-debris"
                ),
            },
        },
        {
            "timestamp": "2026-06-12T10:00:04Z",
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "exec_command",
                "call_id": "call_sequence_mutation",
                "arguments": json.dumps(
                    {"cmd": "rm -rf /tmp/tts-hotpath-test-debris"}
                ),
            },
        },
        {
            "timestamp": "2026-06-12T10:00:05Z",
            "type": "response_item",
            "payload": {
                "type": "function_call_output",
                "call_id": "call_sequence_mutation",
                "output": "Process exited with code 0\nOutput:\nremoved",
            },
        },
        {
            "timestamp": "2026-06-12T10:00:06Z",
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "exec_command",
                "call_id": "call_sequence_verification",
                "arguments": json.dumps(
                    {"cmd": "find /tmp -name 'tts-hotpath-test-*' -print"}
                ),
            },
        },
        {
            "timestamp": "2026-06-12T10:00:07Z",
            "type": "response_item",
            "payload": {
                "type": "function_call_output",
                "call_id": "call_sequence_verification",
                "output": "Process exited with code 0\nOutput:\n",
            },
        },
        {
            "timestamp": "2026-06-12T10:00:08Z",
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "exec_command",
                "call_id": "call_sequence_verification_markers",
                "arguments": json.dumps(
                    {"cmd": "rg -n 'tts|hotpath|test' /tmp || true"}
                ),
            },
        },
        {
            "timestamp": "2026-06-12T10:00:09Z",
            "type": "response_item",
            "payload": {
                "type": "function_call_output",
                "call_id": "call_sequence_verification_markers",
                "output": "Process exited with code 0\nOutput:\n",
            },
        },
    ]
    write_jsonl(block_path, rows)
    raw_source = {
        "path": str(block_path),
        "expected_sha256": module.sha256_file(block_path),
        "stored_bytes": block_path.stat().st_size,
        "uncompressed_bytes": block_path.stat().st_size,
        "compression": "plain",
        "session_id": "temporal-sequence-session",
        "from_line": 100,
        "to_line": 109,
        "line_count": 10,
        "raw_block_ref": "raw/blocks/sequence.raw.jsonl",
    }
    candidates = [
        {
            "doc_id": "episode_semantic:temporal-sequence-session:task-antecedent",
            "session_id": "temporal-sequence-session",
            "task_episode_id": "task-antecedent",
            "event_range": {"from_line": 101, "to_line": 101},
            "temporal_span": {
                "active": True,
                "status": "temporal_span_unresolved_or_unordered",
            },
        },
        {
            "doc_id": "episode_semantic:temporal-sequence-session:task-discovery",
            "session_id": "temporal-sequence-session",
            "task_episode_id": "task-discovery",
            "event_range": {"from_line": 102, "to_line": 103},
            "temporal_span": {
                "active": True,
                "status": "temporal_span_unresolved_or_unordered",
            },
        },
        {
            "doc_id": "episode_semantic:temporal-sequence-session:task-cleanup",
            "session_id": "temporal-sequence-session",
            "task_episode_id": "task-cleanup",
            "event_range": {"from_line": 104, "to_line": 109},
            "temporal_span": {
                "active": True,
                "status": "temporal_span_unresolved_or_unordered",
            },
        },
    ]
    query = (
        "После того как агент ошибочно свёл clean work к read-only, "
        "пользователь потребовал исправить. Какие временные tts hotpath test "
        "остатки были затем найдены, удалены и проверены?"
    )
    temporal_span = module.episode_temporal_span_query(query)

    hydrated, report = module.episode_temporal_scoped_raw_hydration(
        raw_path=None,
        raw_sources=[raw_source],
        segments=[],
        results=candidates,
        temporal_span=temporal_span,
        time_from="2026-06-12T09:59:00Z",
        time_to="2026-06-12T10:01:00Z",
        max_raw_bytes=1024 * 1024,
        max_lines=100,
    )
    qualified, gate = module.episode_temporal_relation_gate(
        hydrated,
        temporal_span,
    )

    assert report["status"] == "applied"
    assert report["read_scope"] == "candidate_raw_blocks"
    assert report["source_integrity"]["status"] == "verified"
    assert report["action_sequence"]["status"] == "applied_complete"
    assert [item["task_episode_id"] for item in qualified] == ["task-cleanup"]
    assert gate["status"] == "qualified_ordered_spans_available"
    evidence = qualified[0]["temporal_span"]
    assert evidence["admission_basis"] == "source_aware_complete_action_sequence"
    assert evidence["left"]["refs"]["raw"] == "raw:line:101"
    assert evidence["left"]["message_role"] == "assistant"
    assert evidence["source_episode_ids"] == [
        "task-antecedent",
        "task-discovery",
        "task-cleanup",
    ]
    assert [
        (item["stage"], item["anchor"]["refs"]["raw"])
        for item in evidence["action_sequence"]
    ] == [
        ("discovery", "raw:line:103"),
        ("mutation", "raw:line:105"),
        ("verification", "raw:line:107"),
    ]
    assert [
        item["refs"]["raw"]
        for item in evidence["action_sequence"][-1]["supporting_anchors"]
    ] == ["raw:line:109"]
    assert evidence["right"]["refs"]["raw"] == "raw:line:109"
    assert evidence["evidence_time_scope"][
        "all_evidence_in_requested_window"
    ] is True

    corrupt_hydrated, corrupt_report = (
        module.episode_temporal_scoped_raw_hydration(
            raw_path=None,
            raw_sources=[
                {
                    **raw_source,
                    "expected_sha256": "0" * 64,
                }
            ],
            segments=[],
            results=candidates,
            temporal_span=temporal_span,
            max_raw_bytes=1024 * 1024,
            max_lines=100,
        )
    )
    corrupt_qualified, corrupt_gate = module.episode_temporal_relation_gate(
        corrupt_hydrated,
        temporal_span,
    )
    assert corrupt_report["status"] == "candidate_raw_block_integrity_failed"
    assert corrupt_report["source_integrity"]["failed_count"] == 1
    assert corrupt_qualified == []
    assert corrupt_gate["status"] == "no_qualified_ordered_span"
def test_episode_temporal_raw_hydration_collapses_equivalent_async_anchor_observations(
    tmp_path: Path,
) -> None:
    raw_path = tmp_path / "session.raw.jsonl"
    write_jsonl(
        raw_path,
        [
            {"type": "session_meta", "payload": {"id": "temporal-async-session"}},
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "exec_command",
                    "call_id": "call_OriginIdentifier123",
                    "arguments": json.dumps({"cmd": "python generated_gate.py"}),
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "call_OriginIdentifier123",
                    "output": "Script running with cell ID 1705",
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "wait",
                    "call_id": "call_LeftWait999",
                    "arguments": json.dumps({"cell_id": "1705"}),
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "call_LeftWait999",
                    "output": "completed generated gate for 57 skills",
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "exec_command",
                    "call_id": "call_RightIdentifier456",
                    "arguments": json.dumps({"cmd": "pytest -q tests/test_export.py"}),
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "call_RightIdentifier456",
                    "output": "Process exited with code 1\n1 failed",
                },
            },
        ],
    )
    query = (
        "show commands between call_OriginIdentifier123 generated gate and "
        "call_RightIdentifier456 pytest exit 1"
    )
    temporal_span = module.episode_temporal_span_query(query)
    candidates = [
        {
            "doc_id": "episode_semantic:temporal-async-session:task-0001",
            "session_id": "temporal-async-session",
            "task_episode_id": "task-0001",
            "event_range": {"from_line": 1, "to_line": 7},
            "temporal_span": {"active": True, "status": "temporal_span_unresolved_or_unordered"},
        }
    ]

    hydrated, hydration = module.episode_temporal_scoped_raw_hydration(
        raw_path=raw_path,
        segments=[],
        results=candidates,
        temporal_span=temporal_span,
        max_raw_bytes=1024 * 1024,
        max_lines=100,
    )

    evidence = hydrated[0]["temporal_span"]
    assert hydration["qualified_candidate_count"] == 1
    assert evidence["qualified_pair_count"] == 1
    assert evidence["collapsed_equivalent_pair_count"] >= 1
    assert evidence["ambiguous_within_episode"] is False
    assert evidence["left"]["chain_from_raw_ref"] == "raw:line:2"
    assert evidence["right"]["chain_from_raw_ref"] == "raw:line:6"
def test_episode_temporal_raw_hydration_clusters_source_reflections_inside_time_scope(
    tmp_path: Path,
) -> None:
    """Owner-neutral regression derived from a gold-first archived-session case."""
    raw_path = tmp_path / "bounded.raw.jsonl"
    rows = [
        {
            "timestamp": "2026-06-30T23:59:58Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "cache writeback check"}],
            },
        },
        {
            "timestamp": "2026-06-30T23:59:59Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": "diagnosis missing repo alias",
                    }
                ],
            },
        },
        {
            "timestamp": "2026-07-01T00:00:03Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": "Starting the cache/writeback check before durable capture.",
                    }
                ],
            },
        },
        {
            "timestamp": "2026-07-01T00:00:04Z",
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "session_evidence_probe",
                "call_id": "call_CheckAlpha111",
                "arguments": json.dumps(
                    {
                        "intent": "cache writeback check",
                        "query": "owner adapter durable capture",
                    }
                ),
            },
        },
        {
            "timestamp": "2026-07-01T00:00:05Z",
            "type": "response_item",
            "payload": {
                "type": "function_call_output",
                "call_id": "call_CheckAlpha111",
                "output": json.dumps(
                    {"ok": True, "intent": "cache writeback check"}
                ),
            },
        },
        {
            "timestamp": "2026-07-01T00:00:06Z",
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "candidate_create",
                "call_id": "call_CreateAlpha222",
                "arguments": json.dumps({"repo": "/workspace/owner-adapter"}),
            },
        },
        {
            "timestamp": "2026-07-01T00:00:07Z",
            "type": "response_item",
            "payload": {
                "type": "function_call_output",
                "call_id": "call_CreateAlpha222",
                "output": "repo must be an approved alias, not a path",
            },
        },
        {
            "timestamp": "2026-07-01T00:00:08Z",
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "candidate_create",
                "call_id": "call_CreateBeta333",
                "arguments": json.dumps({"repo": "owner-adapter"}),
            },
        },
        {
            "timestamp": "2026-07-01T00:00:09Z",
            "type": "response_item",
            "payload": {
                "type": "function_call_output",
                "call_id": "call_CreateBeta333",
                "output": "unknown repo or missing source root: owner-adapter",
            },
        },
        {
            "timestamp": "2026-07-01T00:00:10Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": (
                            "Diagnosis: the registry does not know the alias for the "
                            "owner repo; the candidate cannot be created without a repo alias."
                        ),
                    }
                ],
            },
        },
    ]
    raw_bytes = (
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n"
    ).encode("utf-8")
    raw_path.write_bytes(raw_bytes)
    raw_source = {
        "path": str(raw_path),
        "compression": "plain",
        "expected_sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "session_id": "temporal-source-reflection-session",
        "from_line": 1,
        "to_line": len(rows),
        "line_count": len(rows),
        "stored_bytes": len(raw_bytes),
        "uncompressed_bytes": len(raw_bytes),
        "raw_block_ref": "raw/blocks/000.raw.jsonl",
        "segment": {},
    }
    temporal_span = module.episode_temporal_span_query(
        "what happened 2026-07-01 between cache/writeback check and "
        "diagnosis missing repo alias"
    )
    candidates = [
        {
            "doc_id": (
                "episode_semantic:temporal-source-reflection-session:task-0001"
            ),
            "session_id": "temporal-source-reflection-session",
            "task_episode_id": "task-0001",
            "event_range": {"from_line": 1, "to_line": len(rows)},
            "temporal_span": {
                "active": True,
                "status": "temporal_span_unresolved_or_unordered",
            },
        }
    ]

    hydrated, report = module.episode_temporal_scoped_raw_hydration(
        raw_path=None,
        raw_sources=[raw_source],
        segments=[],
        results=candidates,
        temporal_span=temporal_span,
        time_from="2026-07-01T00:00:03Z",
        time_to="2026-07-01T00:00:10Z",
        max_raw_bytes=1024 * 1024,
        max_lines=100,
    )
    qualified, gate = module.episode_temporal_relation_gate(
        hydrated,
        temporal_span,
    )

    assert report["status"] == "applied"
    assert report["read_scope"] == "candidate_raw_blocks"
    assert report["source_integrity"]["status"] == "verified"
    assert report["time_scope_filtered_event_count"] == 2
    assert report["qualified_pair_count"] == 1
    assert gate["status"] == "qualified_ordered_spans_available"
    assert [item["task_episode_id"] for item in qualified] == ["task-0001"]
    evidence = qualified[0]["temporal_span"]
    assert evidence["ambiguous_within_episode"] is False
    assert evidence["left"]["refs"]["raw"] == "raw:line:5"
    assert evidence["left"]["source_profile"] == (
        "structured_operational_observation"
    )
    assert evidence["left"]["equivalent_observation_count"] == 2
    assert {
        item["refs"]["raw"]
        for item in evidence["left"]["equivalent_observations"]
    } == {"raw:line:3", "raw:line:5"}
    assert evidence["right"]["refs"]["raw"] == "raw:line:10"
    assert evidence["right"]["source_profile"] == "interpretive_observation"
    assert evidence["answer_scope"] == "interval_contents"
    assert evidence["evidence_source"] == (
        "hash_verified_candidate_raw_blocks"
    )
    assert evidence["authority"] == "hash_verified_archived_raw_blocks"
    assert evidence["interval_contents"]["authority"] == (
        "hash_verified_archived_raw_blocks"
    )
    assert qualified[0]["reading_contract"]["authority"] == (
        "hash_verified_archived_raw_blocks"
    )
    assert evidence["evidence_time_scope"][
        "all_evidence_in_requested_window"
    ] is True
def test_episode_temporal_raw_hydration_keeps_distinct_correlations_ambiguous(
    tmp_path: Path,
) -> None:
    """Nearby retries with different correlation IDs are not one reflection."""
    raw_path = tmp_path / "ambiguous.raw.jsonl"
    write_jsonl(
        raw_path,
        [
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {"type": "output_text", "text": "begin cache check"}
                    ],
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "candidate_create",
                    "call_id": "call_RetryAlpha111",
                    "arguments": json.dumps({"repo": "alpha-alias"}),
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "call_RetryAlpha111",
                    "output": "Error: missing repo alias",
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "candidate_create",
                    "call_id": "call_RetryBeta222",
                    "arguments": json.dumps({"repo": "beta-alias"}),
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "call_RetryBeta222",
                    "output": "Error: missing repo alias",
                },
            },
        ],
    )
    temporal_span = module.episode_temporal_span_query(
        "what happened between cache check and error missing repo alias"
    )
    candidates = [
        {
            "doc_id": "episode_semantic:temporal-ambiguous-session:task-0001",
            "session_id": "temporal-ambiguous-session",
            "task_episode_id": "task-0001",
            "event_range": {"from_line": 1, "to_line": 5},
            "temporal_span": {
                "active": True,
                "status": "temporal_span_unresolved_or_unordered",
            },
        }
    ]

    hydrated, report = module.episode_temporal_scoped_raw_hydration(
        raw_path=raw_path,
        segments=[],
        results=candidates,
        temporal_span=temporal_span,
        max_raw_bytes=1024 * 1024,
        max_lines=100,
    )
    qualified, gate = module.episode_temporal_relation_gate(
        hydrated,
        temporal_span,
    )

    assert report["qualified_pair_count"] == 2
    assert len(qualified) == 1
    evidence = qualified[0]["temporal_span"]
    assert evidence["ambiguous_within_episode"] is True
    assert evidence["alternative_ordered_span_count"] == 1
    right_refs = {
        evidence["right"]["refs"]["raw"],
        evidence["alternative_ordered_spans"][0]["right"]["refs"]["raw"],
    }
    assert right_refs == {"raw:line:3", "raw:line:5"}
    assert gate["status"] == "ambiguous_ordered_spans_available"
    assert gate["ambiguous"] is True
def test_episode_temporal_raw_hydration_rejects_nested_running_transport_text(
    tmp_path: Path,
) -> None:
    raw_path = tmp_path / "session.raw.jsonl"
    write_jsonl(
        raw_path,
        [
            {"type": "session_meta", "payload": {"id": "temporal-nested-transport-session"}},
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "exec_command",
                    "call_id": "call_OriginIdentifier123",
                    "arguments": json.dumps({"cmd": "python actual_gate.py"}),
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "call_OriginIdentifier123",
                    "output": (
                        "Script completed\nWall time 0.1 seconds\nOutput:\n"
                        "old fixture: Script running with cell ID 1705"
                    ),
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "wait",
                    "call_id": "call_UnrelatedWait999",
                    "arguments": json.dumps({"cell_id": "1705"}),
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "call_UnrelatedWait999",
                    "output": "irrelevant completion",
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "exec_command",
                    "call_id": "call_RightIdentifier456",
                    "arguments": json.dumps({"cmd": "pytest -q tests/test_export.py"}),
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "call_RightIdentifier456",
                    "output": "Process exited with code 0\n1 passed",
                },
            },
        ],
    )
    temporal_span = module.episode_temporal_span_query(
        "show commands between call_OriginIdentifier123 actual_gate.py and "
        "call_RightIdentifier456 pytest"
    )
    candidates = [
        {
            "doc_id": "episode_semantic:temporal-nested-transport-session:task-0001",
            "session_id": "temporal-nested-transport-session",
            "task_episode_id": "task-0001",
            "event_range": {"from_line": 1, "to_line": 7},
            "temporal_span": {"active": True, "status": "temporal_span_unresolved_or_unordered"},
        }
    ]

    hydrated, hydration = module.episode_temporal_scoped_raw_hydration(
        raw_path=raw_path,
        segments=[],
        results=candidates,
        temporal_span=temporal_span,
        max_raw_bytes=1024 * 1024,
        max_lines=100,
    )

    evidence = hydrated[0]["temporal_span"]
    assert hydration["qualified_candidate_count"] == 1
    assert evidence["left"]["refs"]["raw"] == "raw:line:3"
    assert evidence["left"]["chain_from_raw_ref"] == "raw:line:2"
    assert evidence["right"]["refs"]["raw"] == "raw:line:7"
def test_episode_temporal_raw_hydration_prioritizes_identifiers_after_generic_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Synthetic regression derived from a large real session with generic-match pressure."""
    raw_path = tmp_path / "session.raw.jsonl"
    write_jsonl(
        raw_path,
        [
            {
                "timestamp": "2026-06-11T00:00:00Z",
                "type": "session_meta",
                "payload": {"id": "temporal-budget-session", "cwd": "/workspace/project"},
            },
            {
                "timestamp": "2026-06-11T00:00:01Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "generic call exit wording"}],
                },
            },
            {
                "timestamp": "2026-06-11T00:00:02Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "another generic call exit wording"}],
                },
            },
            {
                "timestamp": "2026-06-11T00:00:03Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "exec_command",
                    "call_id": "call_CompileIdentifier123",
                    "arguments": json.dumps({"cmd": "python -m py_compile src/runtime.py"}),
                },
            },
            {
                "timestamp": "2026-06-11T00:00:04Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "call_CompileIdentifier123",
                    "output": "Process exited with code 0\nFinal output:\n",
                },
            },
            {
                "timestamp": "2026-06-11T00:00:05Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "exec_command",
                    "call_id": "call_PytestIdentifier456",
                    "arguments": json.dumps({"cmd": "pytest -q tests/test_runtime_contract.py"}),
                },
            },
            {
                "timestamp": "2026-06-11T00:00:06Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "call_PytestIdentifier456",
                    "output": "Process exited with code 1\nFinal output:\n1 failed\n",
                },
            },
        ],
    )
    temporal_span = module.episode_temporal_span_query(
        "what happened between call_CompileIdentifier123 py_compile exit 0 and "
        "call_PytestIdentifier456 pytest exit 1"
    )
    candidates = [
        {
            "doc_id": "episode_semantic:temporal-budget-session:task-0001",
            "session_id": "temporal-budget-session",
            "task_episode_id": "task-0001",
            "event_range": {"from_line": 1, "to_line": 7},
            "temporal_span": {
                "active": True,
                "status": "temporal_span_unresolved_or_unordered",
                "ranking_boost": 0.0,
            },
        }
    ]
    monkeypatch.setattr(module, "EPISODE_TEMPORAL_SCOPED_RAW_MAX_MATCHED_UNITS", 2)

    hydrated, hydration = module.episode_temporal_scoped_raw_hydration(
        raw_path=raw_path,
        segments=[],
        results=candidates,
        temporal_span=temporal_span,
        max_raw_bytes=1024 * 1024,
        max_lines=100,
    )

    evidence = hydrated[0]["temporal_span"]
    assert hydration["qualified_candidate_count"] == 1
    assert hydration["retention_policy"] == "bounded_candidate_evidence_priority"
    assert evidence["left"]["correlation_id"] == "call_CompileIdentifier123"
    assert evidence["right"]["correlation_id"] == "call_PytestIdentifier456"
def test_episode_temporal_raw_hydration_requires_query_identifiers_on_each_anchor(
    tmp_path: Path,
) -> None:
    """A structurally similar foreign chain must not satisfy identifier-scoped anchors."""
    raw_path = tmp_path / "session.raw.jsonl"

    def call(call_id: str, command: str) -> dict[str, Any]:
        return {
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "exec_command",
                "call_id": call_id,
                "arguments": json.dumps({"cmd": command}),
            },
        }

    def result(call_id: str, exit_code: int) -> dict[str, Any]:
        return {
            "type": "response_item",
            "payload": {
                "type": "function_call_output",
                "call_id": call_id,
                "output": f"Process exited with code {exit_code}\nFinal output:\n",
            },
        }

    write_jsonl(
        raw_path,
        [
            {"type": "session_meta", "payload": {"id": "temporal-collision-session"}},
            call("call_ForeignCompile999", "python -m py_compile src/foreign.py"),
            result("call_ForeignCompile999", 0),
            call("call_ForeignPytest999", "pytest -q tests/test_foreign.py"),
            result("call_ForeignPytest999", 1),
            call("call_CompileIdentifier123", "python -m py_compile src/runtime.py"),
            result("call_CompileIdentifier123", 0),
            call("call_PytestIdentifier456", "pytest -q tests/test_runtime.py"),
            result("call_PytestIdentifier456", 1),
        ],
    )
    temporal_span = module.episode_temporal_span_query(
        "what happened between call_CompileIdentifier123 py_compile exit 0 and "
        "call_PytestIdentifier456 pytest exit 1"
    )
    candidates = [
        {
            "doc_id": "episode_semantic:temporal-collision-session:task-wrong",
            "session_id": "temporal-collision-session",
            "task_episode_id": "task-wrong",
            "event_range": {"from_line": 2, "to_line": 5},
            "temporal_span": {"active": True, "status": "temporal_span_unresolved_or_unordered"},
        },
        {
            "doc_id": "episode_semantic:temporal-collision-session:task-target",
            "session_id": "temporal-collision-session",
            "task_episode_id": "task-target",
            "event_range": {"from_line": 6, "to_line": 9},
            "temporal_span": {"active": True, "status": "temporal_span_unresolved_or_unordered"},
        },
    ]

    hydrated, hydration = module.episode_temporal_scoped_raw_hydration(
        raw_path=raw_path,
        segments=[],
        results=candidates,
        temporal_span=temporal_span,
        max_raw_bytes=1024 * 1024,
        max_lines=100,
    )

    assert hydration["qualified_candidate_count"] == 1
    assert hydrated[0]["temporal_span"]["status"] != "ordered_span_found"
    assert hydrated[1]["temporal_span"]["status"] == "ordered_span_found"
    assert hydrated[1]["temporal_span"]["admission_basis"].startswith("identifier_backed")
def test_episode_temporal_exact_anchor_seed_adds_episode_missing_from_semantic_pool(
    tmp_path: Path,
) -> None:
    """Synthetic regression derived from a real rank-58 episode outside the BM25 pool."""
    aoa_root = tmp_path / ".aoa"
    aoa_root.mkdir()
    conn = module.init_search_db(module.search_db_path(aoa_root), rebuild=True)
    session_id = "temporal-exact-seed-session"
    for doc_id, raw_line, exact_text in (
        (
            "event:temporal-exact-seed-session:left",
            106,
            "call_CompileIdentifier123 py_compile exit 0",
        ),
        (
            "event:temporal-exact-seed-session:right",
            109,
            "call_PytestIdentifier456 pytest exit 1",
        ),
    ):
        module.insert_search_document(
            conn,
            {
                "id": doc_id,
                "doc_type": "event",
                "session_id": session_id,
                "session_label": session_id,
                "session_title": "Temporal exact seed",
                "session_date": "2026-06-11",
                "event_id": str(raw_line),
                "event_type": "COMMAND_OUTPUT",
                "raw_ref": f"raw:line:{raw_line}",
                "manifest_path": "session.manifest.json",
                "title": exact_text,
                "body": exact_text,
                "payload_json": "{}",
                "exact_literal_text": exact_text,
                "exact_literal_source_lane": "response_item",
            },
        )
    conn.execute(
        """
        INSERT INTO exact_literal_session_state(
          session_id, session_label, source_fingerprint, status,
          posting_document_count, projection_version, indexed_at
        ) VALUES (?, ?, 'synthetic', 'current', 2, ?, '2026-06-11T00:00:00Z')
        """,
        (session_id, session_id, module.SEARCH_EXACT_LITERAL_POSTINGS_VERSION),
    )
    episode_cursor = conn.execute(
        """
        INSERT INTO episode_semantic_meta(
          doc_id, session_id, session_label, session_title, session_date,
          episode_id, episode_status, from_line, to_line,
          from_timestamp, to_timestamp, raw_ref, segment_ref, session_ref,
          session_index_path, preview, source_fingerprint, freshness_status,
          projection_version
        ) VALUES (?, ?, ?, 'Temporal exact seed', '2026-06-11',
                  'task-target', 'closed', 100, 120,
                  '', '', 'raw:line:100', '001.md', 'session.manifest.json',
                  'session.index.json', 'bounded text omitted exact call identifiers',
                  'synthetic', 'fresh', ?)
        """,
        (
            f"episode_semantic:{session_id}:task-target",
            session_id,
            session_id,
            module.EPISODE_SEMANTIC_PROJECTION_VERSION,
        ),
    )
    episode_payload = {
        "episode_id": "task-target",
        "status": "closed",
        "event_range": {"from_line": 100, "to_line": 120},
        "time_span": {},
        "representations": {},
        "anchors": {},
        "narrative": "bounded text omitted exact call identifiers",
        "semantic_contract": {},
        "lineage": {},
        "provenance": {},
    }
    conn.execute(
        "INSERT INTO episode_semantic_payloads(doc_rowid, payload_zlib) VALUES (?, ?)",
        (
            episode_cursor.lastrowid,
            sqlite3.Binary(
                module.zlib.compress(
                    json.dumps(episode_payload, separators=(",", ":")).encode("utf-8"),
                    level=6,
                )
            ),
        ),
    )
    conn.commit()
    conn.close()
    query = (
        "what happened between call_CompileIdentifier123 py_compile exit 0 and "
        "call_PytestIdentifier456 pytest exit 1"
    )
    temporal_span = module.episode_temporal_span_query(query)
    semantic_only_candidates = [
        {
            "doc_id": f"episode_semantic:{session_id}:task-wrong",
            "session_id": session_id,
            "task_episode_id": "task-wrong",
            "event_range": {"from_line": 1, "to_line": 20},
        }
    ]

    seeded, report = module.episode_temporal_exact_anchor_seed_candidates(
        aoa_root=aoa_root,
        session_id=session_id,
        results=semantic_only_candidates,
        temporal_span=temporal_span,
        terms=module.episode_semantic_query_terms(query),
        query_text=query,
        normalized_query=module.episode_semantic_fts_query(module.episode_semantic_query_terms(query)),
        explain=True,
    )

    assert report["status"] == "applied"
    assert report["anchor_hit_count"] == 2
    assert report["added_episode_count"] == 1
    assert seeded[0]["task_episode_id"] == "task-target"
    assert seeded[0]["match_channel"] == "episode_exact_temporal_anchor_seed"
    assert {hit["raw_ref"] for hit in seeded[0]["temporal_exact_anchor_seed"]["hits"]} == {
        "raw:line:106",
        "raw:line:109",
    }
def test_episode_temporal_span_requires_interval_intent_not_generic_between_relation() -> None:
    non_temporal_queries = [
        "где contract test поймал рассинхрон stable_fields между exporter и константой",
        "какая разница между pending receipt и reviewed commit",
        "what distinction was made between fixture consistency and runtime effectiveness",
    ]
    temporal_queries = [
        "что произошло между compile exit 0 и pytest exit 1",
        "покажи команды между generated gate и completed export wait",
        "show the commands between the generated gate and the completed export wait",
    ]

    for query in non_temporal_queries:
        temporal_span = module.episode_temporal_span_query(query)
        assert temporal_span["active"] is False, (query, temporal_span)

    for query in temporal_queries:
        temporal_span = module.episode_temporal_span_query(query)
        assert temporal_span["active"] is True, (query, temporal_span)
        assert temporal_span["left_terms"]
        assert temporal_span["right_terms"]
