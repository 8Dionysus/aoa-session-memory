from __future__ import annotations

import json
from pathlib import Path
from typing import Any


from session_memory_test_support import (
    module,
    write_json,
    write_jsonl,
)

def test_graph_timeline_recovers_exact_segment_peer_from_stale_search_seed(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """A stale one-sided search seed must not truncate an exact causal pair."""
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-07-18T00-20-00-correlation-peer.jsonl"
    correlation_id = "call_exact_peer_123456789"
    foreign_correlation_id = "call_foreign_peer_987654321"
    write_jsonl(
        transcript,
        [
            {
                "timestamp": "2026-07-18T00:20:00Z",
                "type": "session_meta",
                "payload": {"id": "correlation-peer", "cwd": str(workspace)},
            },
            {
                "timestamp": "2026-07-18T00:20:01Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "exec_command",
                    "arguments": json.dumps(
                        {
                            "cmd": (
                                "python -m pytest -q "
                                "tests/test_validation_topology.py"
                            )
                        }
                    ),
                    "call_id": correlation_id,
                },
            },
            {
                "timestamp": "2026-07-18T00:20:02Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "exec_command",
                    "arguments": json.dumps({"cmd": "printf foreign"}),
                    "call_id": foreign_correlation_id,
                },
            },
            {
                "timestamp": "2026-07-18T00:20:03Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": foreign_correlation_id,
                    "output": (
                        "Chunk ID: foreign\n"
                        "Process exited with code 0\n"
                        "Final output:\nforeign\n"
                    ),
                },
            },
            {
                "timestamp": "2026-07-18T00:20:04Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": correlation_id,
                    "output": (
                        "Chunk ID: selected\n"
                        "Process exited with code 0\n"
                        "Final output:\n8 passed, 12 subtests passed\n"
                    ),
                },
            },
        ],
    )

    receipt = module.handle_hook_event(
        "Stop",
        {
            "session_id": "correlation-peer",
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

    baseline_trace = module.trace_route(
        aoa_root=aoa_root,
        anchor=correlation_id,
        kind="auto",
        limit=20,
        per_route_limit=20,
        doc_type="event",
        explain=True,
    )
    result_hit = next(
        hit
        for hit in baseline_trace["results"]
        if hit["refs"]["raw"] == "raw:line:5"
    )
    result_hit = json.loads(json.dumps(result_hit))
    result_hit["freshness"] = {
        "status": "stale",
        "reasons": ["segment_index_sha_mismatch"],
        "readability": "stale-readable",
    }
    segment_index_path = Path(result_hit["refs"]["segment_index"])
    segment_index = json.loads(segment_index_path.read_text(encoding="utf-8"))
    foreign_result = next(
        event
        for event in segment_index["events"]
        if event["raw_ref"] == "raw:line:4"
    )
    foreign_result["correlation_id"] = correlation_id
    segment_index_path.write_text(
        json.dumps(segment_index, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        module,
        "trace_route",
        lambda **_kwargs: {
            "ok": True,
            "result_count": 1,
            "results": [result_hit],
            "diagnostics": ["portable_sqlite:stale"],
        },
    )

    timeline = module.graph_source_verified_correlation_timeline(
        aoa_root=aoa_root,
        anchor=correlation_id,
        kind="auto",
        limit=8,
    )
    assert timeline is not None
    timeline_by_raw = {
        node["refs"]["raw"]: node
        for node in timeline["nodes"]
    }
    assert set(timeline_by_raw) == {"raw:line:2", "raw:line:5"}
    assert all(
        node["correlation_id"] == correlation_id
        for node in timeline_by_raw.values()
    )
    assert timeline["edge_count"] == 2
    assert {
        relation["type"]
        for relation in timeline["edges"]
    } == {"answered_by", "responds_to"}
    assert timeline["freshness"]["status"] == "stale_readable"
    assert timeline["freshness"]["selected_seed_route"] == (
        "exact_literal_postings"
    )
    assert timeline["quality"][
        "structured_correlation_segment_peer_admitted_count"
    ] == 0
    assert timeline["quality"][
        "structured_correlation_segment_peer_candidate_count"
    ] == 1
    assert timeline["quality"][
        "structured_correlation_segment_peer_unverifiable_count"
    ] == 0
    assert timeline["quality"][
        "structured_correlation_segment_peer_raw_mismatch_count"
    ] == 1
def test_episode_postings_cooccurrence_uses_true_mcp_call_and_rejects_shell_reference(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """Regression derived from the manually adjudicated 20260716 cooccurrence wave."""
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    false_transcript = tmp_path / "rollout-2026-07-16T00-00-00-false-mcp-reference.jsonl"
    true_transcript = tmp_path / "rollout-2026-07-16T00-10-00-true-mcp-call.jsonl"
    write_jsonl(
        false_transcript,
        [
            {
                "timestamp": "2026-07-16T00:00:00Z",
                "type": "session_meta",
                "payload": {"id": "false-mcp-reference", "cwd": str(workspace)},
            },
            {
                "timestamp": "2026-07-16T00:00:01Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "Inspect the process list only."}],
                },
            },
            {
                "timestamp": "2026-07-16T00:00:02Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "exec_command",
                    "arguments": json.dumps(
                        {"cmd": "ps -eo pid,cmd | rg 'aoa-session-memory-mcp-server|PreCompact'"}
                    ),
                    "call_id": "call-false-mcp-reference",
                },
            },
            {
                "timestamp": "2026-07-16T00:00:03Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "call-false-mcp-reference",
                    "output": "no matching process",
                },
            },
            {
                "timestamp": "2026-07-16T00:00:04Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "Process inspection finished."}],
                },
            },
        ],
    )
    write_jsonl(
        true_transcript,
        [
            {
                "timestamp": "2026-07-16T00:10:00Z",
                "type": "session_meta",
                "payload": {"id": "true-mcp-call", "cwd": str(workspace)},
            },
            {
                "timestamp": "2026-07-16T00:10:01Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "Retrieve evidence and apply the bounded change."}],
                },
            },
            {
                "timestamp": "2026-07-16T00:10:02Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "aoa_session_retrieve",
                    "namespace": "mcp__aoa_session_memory",
                    "arguments": json.dumps({"query": "bounded evidence"}),
                    "call_id": "call-real-session-memory-mcp",
                },
            },
            {
                "timestamp": "2026-07-16T00:10:03Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "call-real-session-memory-mcp",
                    "output": json.dumps({"ok": True, "refs": ["raw:line:9"]}),
                },
            },
            {
                "timestamp": "2026-07-16T00:10:04Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "apply_patch",
                    "arguments": json.dumps({"patch": "bounded owner-neutral change"}),
                    "call_id": "call-apply-after-mcp",
                },
            },
            {
                "timestamp": "2026-07-16T00:10:05Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "call-apply-after-mcp",
                    "output": "Done!",
                },
            },
            {
                "timestamp": "2026-07-16T00:10:06Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "Evidence read and change applied."}],
                },
            },
        ],
    )
    for session_id, transcript in (
        ("false-mcp-reference", false_transcript),
        ("true-mcp-call", true_transcript),
    ):
        receipt = module.handle_hook_event(
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
        assert receipt["ok"] is True

    indexed = module.search_index_sessions(aoa_root=aoa_root, target="all", rebuild=True)
    assert indexed["ok"] is True

    hook_chain = module.entity_usage_chain(
        aoa_root=aoa_root,
        anchor="PreCompact",
        kind="hook",
        session="false-mcp-reference",
        limit=8,
    )
    assert hook_chain["ok"] is True
    assert hook_chain["counts"]["usage_event_count"] == 0
    hook_context = next(
        event
        for event in hook_chain["usage_chain"]["context_events"]
        if event["refs"]["raw"] == "raw:line:3"
    )
    assert hook_context["hook_usage_admission"] == "session_activity_not_hook_invocation"
    assert hook_chain["quality"]["hook_usage_invocation_admission_applied"] is True
    assert hook_chain["quality"]["hook_usage_session_activity_rejected_count"] == 1
    assert "hook_session_activity_not_hook_invocation" in hook_chain["noise_flags"]
    assert hook_chain["next_expansion"][0]["id"] == "hook_receipts"

    packet = module.graph_cooccurrence(
        aoa_root=aoa_root,
        anchor="aoa-session-memory-mcp",
        kind="mcp",
        limit=8,
    )

    assert packet["ok"] is True
    assert packet["source"] == "episode_entity_postings_direct_relations"
    assert packet["cooccurrence_basis"] == "same_task_episode_direct_typed_relations"
    assert packet["anchor_relation_counts"]["invoked"] == 1
    assert packet["anchor_context_session_count"] == 1
    assert packet["quality"]["uses_mention_or_reference_relations"] is False
    assert packet["quality"]["uses_graph_store"] is False
    assert packet["quality"]["raw_ref_count"] >= 1
    assert packet["quality"]["segment_ref_count"] >= 1
    assert packet["quality"]["session_ref_count"] >= 1
    assert {
        item["node"]["id"] for item in packet["cooccurrences"]
    } >= {module.graph_route_node_id("tool", "apply_patch")}
    assert all(
        ref["session_id"] == "true-mcp-call"
        for ref in packet["evidence_refs"]
        if ref.get("session_id")
    )
    assert all(
        item["node"]["id"] != module.graph_route_node_id("tool", "namespace_codex_developer_tool")
        for item in packet["cooccurrences"]
    )

    cardinality = module.episode_direct_relation_postings_cardinality(aoa_root)
    assert cardinality["ok"] is True
    assert cardinality["status"] == "current"
    assert cardinality["proof_ready"] is True
    assert cardinality["current_epoch_only"] is True
    assert cardinality["metadata_complete_session_count"] == 2
    assert cardinality["physical_direct_posting_count"] > 0
    assert cardinality["physical_all_posting_count"] > cardinality["physical_direct_posting_count"]
    assert cardinality["excluded_non_direct_posting_count"] > 0
    assert cardinality["relation_counts"]["invoked"] > 0
    assert cardinality["relation_counts"]["referenced_by_action"] > 0
    expected_all_postings = cardinality["physical_all_posting_count"]
    expected_direct_postings = cardinality["physical_direct_posting_count"]

    cardinality_conn = module.init_search_db(
        module.search_db_path(aoa_root),
        rebuild=False,
        create_indexes=False,
    )
    try:
        cardinality_conn.execute(
            "UPDATE episode_semantic_session_state SET "
            "entity_posting_count = -1, direct_relation_posting_count = -1, "
            "posting_relation_counts_json = '', posting_cardinality_metadata_version = 0"
        )
        cardinality_conn.commit()
    finally:
        cardinality_conn.close()
    missing_metadata = module.episode_direct_relation_postings_cardinality(aoa_root)
    assert missing_metadata["status"] == "partial"
    assert missing_metadata["metadata_incomplete_session_count"] == 2
    metadata_plan = module.maintain_indexes(
        aoa_root=aoa_root,
        target="all",
        repair_graph=False,
        repair_token_accounting=False,
    )
    metadata_action = next(
        action
        for action in metadata_plan["actions"]
        if action["id"] == "refresh_episode_posting_cardinality_metadata"
    )
    assert metadata_plan["episode_posting_cardinality_repair_needed"] is True
    assert metadata_action["needed"] is True
    assert metadata_action["selection_count"] == 2
    assert metadata_action["command"][1:3] == [
        "scripts/aoa_session_memory.py",
        "episode-posting-cardinality-refresh",
    ]
    metadata_freshness = module.route_cache_freshness_gates(aoa_root=aoa_root)
    assert metadata_freshness["episode_posting_cardinality_repair_needed"] is True
    assert metadata_freshness["episode_posting_cardinality"]["metadata_incomplete_session_count"] == 2
    assert module.auto_maintenance_clean_noop_reason(metadata_freshness) == ""

    first_refresh = module.refresh_episode_posting_cardinality_metadata(
        aoa_root=aoa_root,
        limit=1,
    )
    assert first_refresh["ok"] is True
    assert first_refresh["status"] == "partial_limit"
    assert first_refresh["processed_count"] == 1
    assert first_refresh["remaining_count"] == 1
    second_refresh = module.refresh_episode_posting_cardinality_metadata(
        aoa_root=aoa_root,
        limit=1,
    )
    assert second_refresh["ok"] is True
    assert second_refresh["status"] == "current"
    assert second_refresh["processed_count"] == 1
    assert second_refresh["remaining_count"] == 0
    refreshed_cardinality = module.episode_direct_relation_postings_cardinality(aoa_root)
    assert refreshed_cardinality["status"] == "current"
    assert refreshed_cardinality["physical_all_posting_count"] == expected_all_postings
    assert refreshed_cardinality["physical_direct_posting_count"] == expected_direct_postings
    refreshed_freshness = module.route_cache_freshness_gates(aoa_root=aoa_root)
    assert refreshed_freshness["episode_posting_cardinality_repair_needed"] is False

    hook_packet = module.graph_cooccurrence(
        aoa_root=aoa_root,
        anchor="PreCompact",
        kind="hook",
        limit=8,
    )
    assert hook_packet["source"] == "episode_entity_postings_direct_relations"
    assert hook_packet["ok"] is False
    assert hook_packet["cooccurrences"] == []
    assert hook_packet["anchor_relation_counts"].get("invoked", 0) == 0
    assert hook_packet["abstention"]["status"] == "reference_only_or_unobserved"

    indexed_classifier_version = module.ROUTE_SIGNAL_CLASSIFIER_VERSION
    monkeypatch.setattr(module, "ROUTE_SIGNAL_CLASSIFIER_VERSION", indexed_classifier_version + 1)
    stale_packet = module.graph_cooccurrence(
        aoa_root=aoa_root,
        anchor="aoa-session-memory-mcp",
        kind="mcp",
        limit=8,
    )
    assert stale_packet["source"] == "episode_entity_postings_direct_relations"
    assert stale_packet["ok"] is False
    assert stale_packet["cooccurrences"] == []
    assert stale_packet["abstention"]["status"] == "insufficient_projection_coverage"

    stale_cardinality = module.episode_direct_relation_postings_cardinality(aoa_root)
    assert stale_cardinality["ok"] is False
    assert stale_cardinality["status"] == "stale"
    assert stale_cardinality["proof_ready"] is False
    assert stale_cardinality["physical_direct_posting_count"] == 0
def test_current_episode_sidecar_reclassifies_stale_failure_and_suppresses_query_echo(
    tmp_path: Path,
) -> None:
    raw_path = tmp_path / "session.raw.jsonl"
    write_jsonl(
        raw_path,
        [
            {
                "timestamp": "2026-07-14T00:00:00Z",
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call",
                    "name": "exec",
                    "call_id": "call-episode-search",
                    "input": (
                        "const r = await tools.exec_command({"
                        "cmd: 'python3 scripts/aoa_session_memory.py episode-search --query noisy-query'"
                        "}); text(r.output);"
                    ),
                },
            },
            {
                "timestamp": "2026-07-14T00:00:01Z",
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call_output",
                    "call_id": "call-episode-search",
                    "output": [
                        {
                            "type": "input_text",
                            "text": "Script completed\nWall time 0.2 seconds\nOutput:\n",
                        },
                        {
                            "type": "input_text",
                            "text": '{"query":"noisy-query","results":[{"text":"error: prior evidence"}]}',
                        },
                    ],
                },
            },
        ],
    )
    episode = {
        "episode_id": "task-0001",
        "event_range": {"from_line": 1, "to_line": 2},
        "representations": {
            "actions": [],
            "outcomes": [],
            "failures": [
                {
                    "text": "noisy-query error: prior evidence",
                    "source_lane": "structured_tool_result",
                    "admission_basis": "structured_failed_result",
                    "event_type": "ERROR",
                    "outcome": "failed",
                    "correlation_id": "call-episode-search",
                    "line": 2,
                    "refs": {"raw": "raw:line:2"},
                }
            ],
        },
        "action_refs": [],
        "tool_refs": [],
        "plan_refs": [],
        "progress_refs": [],
        "answer_refs": [],
        "closeout_refs": [],
        "verification_refs": [],
        "error_refs": [{"line": 2, "raw_ref": "raw:line:2", "source_type": "response_item"}],
        "blocker_refs": [],
    }

    limits = module.episode_semantic_ref_line_limits([episode])
    assert set(limits) == {1, 2}
    records = module.raw_event_semantic_records_by_line(raw_path, line_limits=limits)
    assert records[1]["retrieval_control_command"] == "episode-search"
    assert records[2]["event_type"] == "TOOL_OUTPUT"
    assert records[2]["outcome"] == "observed"

    enriched = module.episode_semantic_enrich_from_refs(
        episode,
        raw_records_by_line=records,
        source_task_episode_schema_version=module.TASK_EPISODE_SCHEMA_VERSION,
    )
    result = next(
        item
        for item in enriched["representations"]["outcomes"]
        if item.get("line") == 2
    )

    assert all(item.get("line") != 2 for item in enriched["representations"]["failures"])
    assert result["event_type"] == "TOOL_OUTPUT"
    assert result["outcome"] == "observed"
    assert result["admission_basis"] == "retrieval_control_result_payload_suppressed"
    assert result["text"] == "aoa-session-memory retrieval control result: episode-search; outcome=observed"
    assert enriched["semantic_contract"]["raw_result_reclassification"]["reclassified_entry_count"] == 1
    assert enriched["semantic_contract"]["retrieval_control_echo_suppression"]["suppressed_entry_count"] == 1
def test_episode_search_reports_ambiguous_session_selector(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    aoa_root = tmp_path / ".aoa"
    conn = module.init_search_db(module.search_db_path(aoa_root), rebuild=False)
    conn.close()

    def ambiguous_resolver(_aoa_root: Path, target: str | None) -> dict[str, Any]:
        raise ValueError(
            f"ambiguous session target {target!r}: 2026-07-10__001__alpha, 2026-07-10__002__beta"
        )

    monkeypatch.setattr(module, "resolve_session_record", ambiguous_resolver)

    result = module.episode_semantic_search(
        aoa_root=aoa_root,
        query="why did the downstream check skip every neighbor",
        session="019f4e1d",
        mode="sparse",
    )

    assert result["ok"] is False
    assert result["result_count"] == 0
    assert result["session_selector"]["status"] == "ambiguous"
    assert result["session_selector"]["requested"] == "019f4e1d"
    assert result["diagnostics"][0].startswith("episode_session_selector_ambiguous:")
def test_episode_ref_expansion_recovers_source_aware_typed_anchors(tmp_path: Path) -> None:
    raw_path = tmp_path / "session.raw.jsonl"
    write_jsonl(
        raw_path,
        [
            {
                "timestamp": "2026-06-02T15:56:11Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "exec_command",
                    "arguments": json.dumps(
                        {"cmd": "sed -n '1,220p' /srv/example/AbyssOS/aoa-skills/tests/test_validate_skills_questbook_contract.py"}
                    ),
                    "call_id": "call-source-read",
                },
            },
            {
                "timestamp": "2026-06-02T15:56:12Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "exec_command",
                    "arguments": json.dumps({"cmd": "sed -n '1,80p' /home/example/.codex/memories/MEMORY.md"}),
                    "call_id": "call-memory-read",
                },
            },
        ],
    )
    records = module.raw_event_semantic_records_by_line(raw_path, line_limits={1: 900, 2: 900})
    episode = {
        "representations": {"actions": []},
        "action_refs": [
            {
                "line": 1,
                "raw_ref": "raw:line:1",
                "source_type": "response_item",
                "event_type": "FILE_READ",
            },
            {
                "line": 2,
                "raw_ref": "raw:line:2",
                "source_type": "response_item",
                "event_type": "FILE_READ",
            },
        ],
        "tool_refs": [],
        "plan_refs": [],
        "progress_refs": [],
        "answer_refs": [],
        "closeout_refs": [],
        "verification_refs": [],
        "error_refs": [],
        "blocker_refs": [],
    }

    enriched = module.episode_semantic_enrich_from_refs(episode, raw_records_by_line=records)
    action = next(item for item in enriched["representations"]["actions"] if item["line"] == 1)
    relations = {
        (anchor["layer"], anchor["key"], anchor["relation"])
        for anchor in action["typed_anchors"]
    }

    assert ("tool", "exec_command", "invoked") in relations
    assert ("test", "test_validate_skills_questbook_contract", "inspected") in relations
def test_episode_enrichment_promotes_canonical_response_over_stream_mirror(
    tmp_path: Path,
) -> None:
    raw_path = tmp_path / "session.raw.jsonl"
    text = "На связи. Не завис, проверяю состояние."
    write_jsonl(
        raw_path,
        [
            {
                "timestamp": "2026-06-10T19:00:00Z",
                "type": "event_msg",
                "payload": {
                    "type": "agent_message",
                    "message": text,
                },
            },
            {
                "timestamp": "2026-06-10T19:00:00.100Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {"type": "output_text", "text": text}
                    ],
                },
            },
        ],
    )
    episode = {
        "event_range": {"from_line": 1, "to_line": 2},
        "representations": {
            "outcomes": [
                {
                    "text": text,
                    "source_lane": "event_msg_stream",
                    "admission_basis": "runtime_stream_observation",
                    "line": 1,
                    "refs": {"raw": "raw:line:1"},
                }
            ]
        },
        "action_refs": [],
        "tool_refs": [],
        "plan_refs": [],
        "progress_refs": [],
        "answer_refs": [
            {
                "line": 2,
                "raw_ref": "raw:line:2",
                "source_type": "response_item",
            }
        ],
        "closeout_refs": [],
        "verification_refs": [],
        "error_refs": [],
        "blocker_refs": [],
    }

    limits = module.episode_semantic_ref_line_limits([episode])
    assert set(limits) == {1, 2}
    records = module.raw_event_semantic_records_by_line(
        raw_path,
        line_limits=limits,
    )
    enriched = module.episode_semantic_enrich_from_refs(
        episode,
        raw_records_by_line=records,
        session_ref="session.manifest.json",
    )

    outcomes = enriched["representations"]["outcomes"]
    assert len(outcomes) == 1
    assert outcomes[0]["line"] == 2
    assert outcomes[0]["source_lane"] == "episode_ref_response_item"
    assert outcomes[0]["mirror_refs"] == [
        {
            "raw": "raw:line:1",
            "session": "session.manifest.json",
        }
    ]
    assert outcomes[0]["mirror_evidence"]["status"] == (
        "proven_adjacent_runtime_mirror_collapsed"
    )
    assert enriched["semantic_contract"][
        "assistant_runtime_mirror_collapse"
    ]["collapsed_entry_count"] == 1
def test_episode_legacy_normalization_rebuilds_raw_evidence_and_scrubs_old_edges(tmp_path: Path) -> None:
    raw_path = tmp_path / "session.raw.jsonl"
    write_jsonl(
        raw_path,
        [
            {
                "timestamp": "2026-06-11T01:29:23Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "Inspect memory routing and installed terminal packages"}],
                },
            },
            {
                "timestamp": "2026-06-11T01:30:05Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "exec_command",
                    "arguments": json.dumps(
                        {"cmd": "sed -n '1,220p' /srv/example/AbyssOS/.aoa/skills/aoa-session-memory-global-route/SKILL.md"}
                    ),
                    "call_id": "call-source-read",
                },
            },
            {
                "timestamp": "2026-06-11T01:30:06Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "call-source-read",
                    "output": "Chunk ID: source\nWall time: 0.1 seconds\nProcess exited with code 0\nOutput:\nMCP docs mention aoa_session_memory_mcp",
                },
            },
            {
                "timestamp": "2026-06-11T01:30:07Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "exec_command",
                    "arguments": json.dumps({"cmd": "dnf list --installed tmux zsh ghostty 2>/dev/null || true"}),
                    "call_id": "call-package-probe",
                },
            },
            {
                "timestamp": "2026-06-11T01:30:08Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "call-package-probe",
                    "output": (
                        "Chunk ID: probe\nWall time: 0.1 seconds\nProcess exited with code 0\n"
                        "Output:\ntmux.x86_64 3.6b\nzsh.x86_64 5.9"
                    ),
                },
            },
        ],
    )
    correlation_chain = [
        {
            "correlation_id": "call-source-read",
            "role": "action",
            "event_type": "FILE_READ",
            "refs": {"raw": "raw:line:2"},
        },
        {
            "correlation_id": "call-source-read",
            "role": "result",
            "event_type": "COMMAND_OUTPUT",
            "outcome": "succeeded",
            "linked_action": "sed -n '1,220p' /srv/example/AbyssOS/.aoa/skills/aoa-session-memory-global-route/SKILL.md",
            "refs": {"raw": "raw:line:3"},
        },
        {
            "correlation_id": "call-package-probe",
            "role": "action",
            "event_type": "COMMAND",
            "refs": {"raw": "raw:line:4"},
        },
        {
            "correlation_id": "call-package-probe",
            "role": "result",
            "event_type": "COMMAND_OUTPUT",
            "outcome": "succeeded",
            "linked_action": "dnf list --installed tmux zsh ghostty 2>/dev/null || true",
            "refs": {"raw": "raw:line:5"},
        },
    ]
    episode = {
        "episode_id": "task-0001",
        "start_user_ref": {"line": 1, "raw_ref": "raw:line:1"},
        "representations": {
            "intents": [],
            "actions": [
                {
                    "text": "legacy source read",
                    "line": 2,
                    "refs": {"raw": "raw:line:2"},
                    "typed_anchors": [
                        {
                            "layer": "skill",
                            "key": "aoa_session_memory_global_route",
                            "route_signal": "skill:aoa_session_memory_global_route",
                            "relation": "used_in",
                        }
                    ],
                }
            ],
            "outcomes": [
                {
                    "text": "legacy result copied stdout",
                    "line": 3,
                    "refs": {"raw": "raw:line:3"},
                    "typed_anchors": [
                        {
                            "layer": "mcp",
                            "key": "aoa_session_memory_mcp",
                            "route_signal": "mcp:aoa_session_memory_mcp",
                            "relation": "produced",
                        }
                    ],
                }
            ],
        },
        "anchors": {
            "operational": [
                {
                    "layer": "mcp",
                    "key": "aoa_session_memory_mcp",
                    "route_signal": "mcp:aoa_session_memory_mcp",
                    "relation": "produced",
                }
            ]
        },
        "correlation_chain": correlation_chain,
        "action_refs": [{"line": 2, "raw_ref": "raw:line:2", "source_type": "response_item"}],
        "tool_refs": [],
        "plan_refs": [],
        "progress_refs": [],
        "answer_refs": [],
        "closeout_refs": [],
        "verification_refs": [],
        "error_refs": [],
        "blocker_refs": [],
    }

    limits = module.episode_semantic_ref_line_limits([episode])
    assert set(limits) == {1, 2, 3, 4, 5}
    records = module.raw_event_semantic_records_by_line(raw_path, line_limits=limits)
    enriched = module.episode_semantic_enrich_from_refs(
        episode,
        raw_records_by_line=records,
        source_task_episode_schema_version=4,
    )
    all_entries = [
        entry
        for entries in enriched["representations"].values()
        for entry in entries
    ]
    relations = {
        (anchor["layer"], anchor["key"], anchor["relation"])
        for entry in all_entries
        for anchor in entry.get("typed_anchors", [])
    }

    assert ("skill", "aoa_session_memory_global_route", "inspected") in relations
    assert all(relation not in {"used_in", "produced"} for _layer, _key, relation in relations)
    assert ("mcp", "aoa_session_memory_mcp", "produced") not in relations
    assert any(item.get("line") == 1 for item in enriched["representations"]["intents"])
    compact = [
        item
        for item in enriched["representations"]["outcomes"]
        if item.get("admission_basis") == "structured_compact_success_observation"
    ]
    assert len(compact) == 1
    assert compact[0]["line"] == 5
    assert "tmux.x86_64 3.6b" in compact[0]["text"]
    assert "aoa_session_memory_mcp" not in compact[0]["text"]
    assert enriched["semantic_contract"]["legacy_normalization"]["source_task_episode_schema_version"] == 4
    assert enriched["semantic_contract"]["legacy_normalization"]["inherited_typed_anchors"] is False
def test_episode_raw_ref_reader_does_not_retain_large_result_event(tmp_path: Path) -> None:
    raw_path = tmp_path / "session.raw.jsonl"
    write_jsonl(
        raw_path,
        [
            {
                "timestamp": "2026-06-11T01:30:08Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "call-large-output",
                    "output": "large source dump marker\n" + ("x" * 100_000),
                },
            }
        ],
    )

    records = module.raw_event_semantic_records_by_line(raw_path, line_limits={1: 900})

    assert len(records[1]["text"]) < 1_000
    assert "classified_event" not in records[1]
def test_episode_projection_rejects_legacy_empty_source_without_generation_identity(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    aoa_root = tmp_path / ".aoa"
    session_dir = aoa_root / "sessions" / "2026-06-19__001__legacy-empty-episodes"
    raw_path = session_dir / "raw" / "session.raw.jsonl"
    write_jsonl(raw_path, [{"timestamp": "2026-06-19T00:00:00Z", "type": "session_meta", "payload": {}}])
    write_json(
        session_dir / "session.manifest.json",
        {
            "session_id": "legacy-empty-episodes",
            "session_label": session_dir.name,
            "display": {"label": session_dir.name, "date": "2026-06-19"},
            "raw": {"path": str(raw_path)},
        },
    )
    write_json(
        session_dir / module.SESSION_INDEX_JSON,
        {
            "session_id": "legacy-empty-episodes",
            "task_episodes": [],
        },
    )
    record = {
        "session_id": "legacy-empty-episodes",
        "session_label": session_dir.name,
        "path": str(session_dir),
    }
    conn = module.init_search_db(module.search_db_path(aoa_root), rebuild=False, create_indexes=False)
    result = module.insert_episode_semantic_projection_for_session(
        conn,
        session_dir=session_dir,
        projection_state=module.session_projection_fingerprint(record, include_rendered_markdown=False),
        indexed_at="2026-06-19T00:00:01Z",
    )
    conn.commit()
    state = conn.execute(
        "SELECT status, source_task_episode_schema_version, normalization_mode, "
        "route_signal_classifier_version "
        "FROM episode_semantic_session_state WHERE session_id = ?",
        ("legacy-empty-episodes",),
    ).fetchone()
    conn.close()

    assert result["status"] == (
        "source_generation_incompatible_requires_raw_reindex"
    )
    assert result["source_task_episode_schema_version"] == 0
    assert result["normalization_mode"] == "no_task_episodes_in_source_index"
    assert result["source_generation_compatible"] is False
    assert (
        "session_index_generation_identity_changed"
        in result["source_generation_reasons"]
    )
    assert result["route_signal_classifier_version"] == module.ROUTE_SIGNAL_CLASSIFIER_VERSION
    assert state["status"] == (
        "source_generation_incompatible_requires_raw_reindex"
    )
    assert state["source_task_episode_schema_version"] == 0
    assert state["normalization_mode"] == "no_task_episodes_in_source_index"
    assert state["route_signal_classifier_version"] == module.ROUTE_SIGNAL_CLASSIFIER_VERSION

    session_index_path = session_dir / module.SESSION_INDEX_JSON
    session_index_path.write_text(session_index_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    original_read_json = module.read_json

    def reject_full_session_index_parse(path: Path, default: Any = None) -> Any:
        if Path(path) == session_index_path:
            raise AssertionError("episode freshness must not parse the full session index")
        return original_read_json(path, default)

    monkeypatch.setattr(module, "read_json", reject_full_session_index_parse)
    freshness = module.episode_semantic_projection_state(aoa_root, records=[record])
    assert freshness["dirty_session_count"] == 1
    assert freshness["source_fingerprint_mode"] == module.EPISODE_SEMANTIC_SOURCE_FINGERPRINT_MODE
    assert freshness["truth_status"] == (
        "bounded_declared_semantic_digest_plus_stat_observation_compared_episode_projection_state"
    )
    assert "episode_semantic_source_fingerprint_changed" in freshness["dirty_sessions"][0]["reasons"]
def test_episode_source_identity_is_semantic_and_rejects_digest_tampering(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "AbyssOS"
    repo = workspace / "aoa-techniques"
    repo.mkdir(parents=True)
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-06-19T01-00-00-semantic-digest.jsonl"
    write_jsonl(
        transcript,
        [
            {
                "timestamp": "2026-06-19T01:00:00Z",
                "type": "session_meta",
                "payload": {
                    "id": "episode-semantic-digest",
                    "cwd": str(repo),
                },
            },
            {
                "timestamp": "2026-06-19T01:00:01Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "Inspect semantic episode digest stability",
                        }
                    ],
                },
            },
            {
                "timestamp": "2026-06-19T01:00:02Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",
                            "text": "The semantic episode digest is verified.",
                        }
                    ],
                },
            },
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "episode-semantic-digest",
            "transcript_path": str(transcript),
            "cwd": str(repo),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )
    record = module.resolve_session_record(
        aoa_root,
        "episode-semantic-digest",
    )
    session_dir = Path(record["path"])
    manifest = module.read_json(
        session_dir / "session.manifest.json",
        {},
    )
    index_path = session_dir / module.SESSION_INDEX_JSON
    session_index = module.read_json(index_path, {})
    declared_digest = session_index["task_episode_semantic_digest"]
    assert declared_digest["version"] == (
        module.TASK_EPISODE_SEMANTIC_DIGEST_VERSION
    )
    assert declared_digest["mode"] == (
        module.TASK_EPISODE_SEMANTIC_DIGEST_MODE
    )
    assert declared_digest == (
        module.task_episode_semantic_digest_for_session_index(
            session_index,
            logical_root=session_dir,
        )
    )

    before = module.episode_semantic_source_fingerprint(
        record,
        manifest=manifest,
        source_probe=module.episode_semantic_source_index_probe(index_path),
    )
    module.write_json(index_path, session_index)
    after_clock_only_rewrite = module.episode_semantic_source_fingerprint(
        record,
        manifest=manifest,
        source_probe=module.episode_semantic_source_index_probe(index_path),
    )
    assert after_clock_only_rewrite["fingerprint"] == before["fingerprint"]

    tampered_index = module.read_json(index_path, {})
    assert tampered_index["task_episodes"] == []
    component_manifest = module.read_json(
        session_dir / tampered_index["component_storage"]["manifest_ref"],
        {},
    )
    shard_ref = component_manifest["components"]["task_episodes"][0][
        "ref"
    ]
    shard_path = session_dir / shard_ref
    tampered_shard = module.read_json(shard_path, {})
    tampered_shard["payload"]["status"] = "tampered-status"
    module.write_json(shard_path, tampered_shard)
    tampered = module.episode_semantic_source_fingerprint(
        record,
        manifest=manifest,
        source_probe=module.episode_semantic_source_index_probe(index_path),
        session_index=tampered_index,
    )
    assert tampered["task_episode_semantic_digest_integrity"] == "mismatch"
    assert tampered["fingerprint"] != before["fingerprint"]
    assert "task_episode_semantic_digest_mismatch" in (
        module.generated_session_index_stale_reasons_for_session(
            session_dir,
            tampered_index,
        )
    )

    conn = module.init_search_db(
        module.search_db_path(aoa_root),
        rebuild=False,
        create_indexes=False,
    )
    rejected = module.insert_episode_semantic_projection_for_session(
        conn,
        session_dir=session_dir,
        projection_state=module.session_projection_fingerprint(
            record,
            include_rendered_markdown=False,
        ),
        indexed_at="2026-06-19T01:01:00Z",
        generation_identity=(
            module.session_memory_expected_generation_identities(aoa_root)[
                "episode_semantic"
            ]
        ),
    )
    conn.close()
    assert rejected["source_generation_compatible"] is False
    assert "task_episode_semantic_digest_mismatch" in (
        rejected["source_generation_reasons"]
    )
