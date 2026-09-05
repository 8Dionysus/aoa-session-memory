from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import Any


from session_memory_test_support import (
    module,
    write_jsonl,
)

def test_structured_tool_transport_status_outranks_words_inside_displayed_data() -> None:
    displayed_history = {
        "type": "response_item",
        "payload": {
            "type": "custom_tool_call_output",
            "call_id": "call-history-read",
            "output": [
                {
                    "type": "input_text",
                    "text": "Script completed\nWall time 0.2 seconds\nOutput:\n",
                },
                {
                    "type": "input_text",
                    "text": json.dumps(
                        {
                            "records": [
                                {"role": "failures", "text": "3 failed, 7 passed in an earlier run"},
                                {"role": "docs", "text": "error: is a documented example"},
                                {
                                    "role": "route_metadata",
                                    "text": "risk:security_or_secret is an indexed route token",
                                },
                            ]
                        }
                    ),
                },
            ],
        },
    }
    displayed_event = module.classify_raw_event(
        json.dumps(displayed_history),
        displayed_history,
        1,
    )

    assert displayed_event.event_type == "TOOL_OUTPUT"
    assert displayed_event.outcome == "observed"
    assert displayed_event.facets["tool_transport_status"] == "completed"
    assert "error_signal" not in displayed_event.tags

    failed_command = {
        "type": "response_item",
        "payload": {
            "type": "function_call_output",
            "call_id": "call-failed-tests",
            "output": "Process exited with code 1\nOutput:\nFFF [100%]\n3 failed, 7 passed\n",
        },
    }
    failed_event = module.classify_raw_event(json.dumps(failed_command), failed_command, 2)

    assert failed_event.event_type == "ERROR"
    assert failed_event.outcome == "failed"
    assert "error_signal" in failed_event.tags
def test_structured_mcp_tool_result_preserves_hook_identity_and_error_status() -> None:
    failed_result = {
        "type": "event_msg",
        "payload": {
            "type": "mcp_tool_call_end",
            "call_id": "call-mcp-failed",
            "invocation": {
                "server": "example",
                "tool": "create_candidate",
            },
            "result": {
                "Ok": {
                    "content": [{"type": "text", "text": "Candidate was rejected."}],
                    "isError": True,
                }
            },
        },
    }
    failed_event = module.classify_raw_event(
        json.dumps(failed_result),
        failed_result,
        1,
    )

    assert failed_event.event_type == "HOOK_EVENT"
    assert failed_event.outcome == "failed"
    assert "structured_mcp_tool_result" in failed_event.tags
    assert "error_signal" in failed_event.tags
    assert failed_event.facets["session_act"]["kind"] == "hook_receipt"
    assert failed_event.facets["session_act"]["outcome"] == "failed"

    successful_result_with_error_documentation = {
        "type": "event_msg",
        "payload": {
            "type": "mcp_tool_call_end",
            "call_id": "call-mcp-succeeded",
            "result": {
                "Ok": {
                    "content": [
                        {
                            "type": "text",
                            "text": "Documentation example: Error: invalid alias.",
                        }
                    ],
                    "isError": False,
                }
            },
        },
    }
    successful_event = module.classify_raw_event(
        json.dumps(successful_result_with_error_documentation),
        successful_result_with_error_documentation,
        2,
    )

    assert successful_event.event_type == "HOOK_EVENT"
    assert successful_event.outcome == "succeeded"
    assert "structured_mcp_tool_result" in successful_event.tags
    assert "success_signal" in successful_event.tags
    assert "error_signal" not in successful_event.tags
    assert module.structured_payload_outcome(
        {
            "type": "mcp_tool_call_end",
            "result": {"Err": {"message": "transport failed"}},
        }
    ) == "failed"
def test_custom_exec_mixed_read_and_write_does_not_promote_skill_to_inspected() -> None:
    mixed = {
        "type": "response_item",
        "payload": {
            "type": "custom_tool_call",
            "name": "exec",
            "call_id": "call-mixed-custom-exec",
            "input": (
                "const reads = await Promise.all(["
                "tools.exec_command({cmd: 'sed -n \'1,80p\' /srv/example/AbyssOS/.aoa/skills/example/SKILL.md'}),"
                "tools.exec_command({cmd: 'cp source.txt generated.txt'})"
                "]); text(reads.length);"
            ),
        },
    }

    event = module.classify_raw_event(json.dumps(mixed), mixed, 1)
    entry = module.task_episode_representation_entry(event, [])

    assert event.event_type == "TOOL_CALL"
    assert isinstance(entry, dict)
    anchors = {
        (item["layer"], item["key"]): item["relation"]
        for item in entry["typed_anchors"]
    }
    assert anchors[("skill", "example")] == "referenced_by_action"
    assert anchors[("tool", "exec")] == "invoked"
def test_captured_invalid_escape_literal_does_not_leak_syntax_warning() -> None:
    source = (
        r'''const r = await tools.exec_command({cmd: "rg '\$HOME' README.md"}); '''
        "text(r.output);"
    )
    payload = {
        "type": "custom_tool_call",
        "name": "exec",
        "input": source,
    }

    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        shell_commands = module.custom_exec_shell_commands(payload)
        entity_commands = module.entity_usage_execution_command_candidates(
            payload
        )

    expected = r"rg '\$HOME' README.md"
    assert shell_commands == [expected]
    assert entity_commands == [expected]
    assert not [item for item in captured if item.category is SyntaxWarning]
def test_structured_shell_reference_to_mcp_service_is_not_invocation() -> None:
    shell_reference = {
        "type": "response_item",
        "payload": {
            "type": "custom_tool_call",
            "name": "exec",
            "call_id": "call-mcp-process-reference",
            "input": (
                "const r = await tools.exec_command({"
                "cmd: \"ps -eo pid,cmd | rg 'aoa-session-memory-mcp-server'\""
                "}); text(r.output);"
            ),
        },
    }

    event = module.classify_raw_event(json.dumps(shell_reference), shell_reference, 1)
    entry = module.task_episode_representation_entry(event, [])

    assert event.event_type == "TOOL_CALL"
    assert isinstance(entry, dict)
    anchors = {
        (item["layer"], item["key"]): item["relation"]
        for item in entry["typed_anchors"]
    }
    assert anchors[("mcp", "aoa_session_memory_mcp")] == "referenced_by_action"
    assert anchors[("tool", "exec")] == "invoked"
    assert anchors[("tool", "exec_command")] == "invoked"
def test_structured_mcp_namespace_proves_service_invocation() -> None:
    mcp_call = {
        "type": "response_item",
        "payload": {
            "type": "function_call",
            "name": "aoa_session_retrieve",
            "namespace": "mcp__aoa_session_memory",
            "arguments": '{"query":"bounded evidence"}',
            "call_id": "call-real-session-memory-mcp",
        },
    }

    event = module.classify_raw_event(json.dumps(mcp_call), mcp_call, 1)
    entry = module.task_episode_representation_entry(event, [])

    assert event.event_type == "TOOL_CALL"
    assert event.facets["tool_transport_namespace"] == "mcp__aoa_session_memory"
    assert event.facets["session_act"]["kind"] == "mcp_tool_call"
    assert isinstance(entry, dict)
    matching = [
        item
        for item in entry["typed_anchors"]
        if (item["layer"], item["key"]) == ("mcp", "aoa_session_memory_mcp")
    ]
    assert matching == [
        {
            "layer": "mcp",
            "key": "aoa_session_memory_mcp",
            "route_signal": "mcp:aoa_session_memory_mcp",
            "relation": "invoked",
        }
    ]
def test_mcp_tool_anchor_resolves_service_for_invocation_admission(
    tmp_path: Path,
) -> None:
    """Regression derived from the manual W0-B MCP call/result review."""
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-mcp-tool-anchor-admission.jsonl"
    write_jsonl(
        transcript,
        [
            {
                "timestamp": "2026-07-17T00:00:00Z",
                "type": "session_meta",
                "payload": {
                    "id": "mcp-tool-anchor-admission",
                    "cwd": str(workspace),
                },
            },
            {
                "timestamp": "2026-07-17T00:00:01Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "aoa_decisions_repo",
                    "namespace": "mcp__aoa_decisions",
                    "call_id": "call-mcp-tool-anchor-admission",
                    "arguments": '{"repo_path":"/tmp/example"}',
                },
            },
            {
                "timestamp": "2026-07-17T00:00:02Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "call-mcp-tool-anchor-admission",
                    "output": '{"ok":true}',
                },
            },
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "mcp-tool-anchor-admission",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )
    record = module.resolve_session_record(
        aoa_root,
        "mcp-tool-anchor-admission",
    )
    assert module.search_index_sessions(
        aoa_root=aoa_root,
        target="all",
        rebuild=True,
    )["ok"] is True

    chain = module.entity_usage_chain(
        aoa_root=aoa_root,
        anchor="aoa_decisions_repo",
        kind="mcp",
        session=str(record["session_label"]),
        limit=4,
        per_route_limit=4,
        consequence_window=4,
    )

    assert chain["ok"] is True
    assert chain["counts"]["usage_event_count"] == 1
    assert chain["quality"]["queried_route_candidate_count"] == 1
    assert chain["quality"]["mcp_usage_invocation_admission_applied"] is True
    assert chain["quality"]["mcp_usage_invocation_admitted_count"] == 1
    assert chain["quality"]["mcp_usage_requested_service_keys"] == [
        "aoa_decisions_mcp"
    ]
    assert (
        chain["quality"]["mcp_usage_anchor_service_resolution"]
        == "tool_name_to_service"
    )
    usage = chain["usage_chain"]["chains"][0]["usage_event"]
    assert usage["refs"]["raw"] == "raw:line:2"
    assert usage["mcp_usage_admission"] == "structured_invocation_proven"
    assert (
        usage["mcp_usage_admission_service_key"]
        == "aoa_decisions_mcp"
    )
    assert chain["usage_chain"]["chains"][0][
        "result_or_consequence_events"
    ][0]["refs"]["raw"] == "raw:line:3"
def test_custom_exec_nested_mcp_call_tracks_callee_not_query_target(
    tmp_path: Path,
) -> None:
    """Regression derived from the raw-first 20260716 MCP usage wave."""
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-07-16T00-00-00-nested-mcp-call.jsonl"
    call_id = "call-nested-session-memory-mcp"
    call_payload = {
        "type": "custom_tool_call",
        "name": "exec",
        "call_id": call_id,
        "input": (
            "const r = await "
            "tools.mcp__aoa_session_memory__aoa_session_entity_usage_chain({"
            "anchor: 'aoa_decisions_mcp', kind: 'mcp', limit: 4"
            "}); text(r);"
        ),
    }
    call_row = {
        "timestamp": "2026-07-16T00:00:01Z",
        "type": "response_item",
        "payload": call_payload,
    }
    output_row = {
        "timestamp": "2026-07-16T00:00:02Z",
        "type": "response_item",
        "payload": {
            "type": "custom_tool_call_output",
            "call_id": call_id,
            "output": [
                {
                    "type": "input_text",
                    "text": "Script completed\nWall time 0.1 seconds\nOutput:\n",
                },
                {
                    "type": "input_text",
                    "text": json.dumps(
                        {
                            "ok": True,
                            "anchor": "aoa_decisions_mcp",
                            "route_metadata": ["risk:security_or_secret"],
                        }
                    ),
                },
            ],
        },
    }
    write_jsonl(
        transcript,
        [
            {
                "timestamp": "2026-07-16T00:00:00Z",
                "type": "session_meta",
                "payload": {"id": "nested-mcp-call", "cwd": str(workspace)},
            },
            call_row,
            output_row,
        ],
    )

    call_event = module.classify_raw_event(json.dumps(call_row), call_row, 2)
    entry = module.task_episode_representation_entry(call_event, [])
    route_signals = {
        (item["layer"], item["key"]): item
        for item in call_event.facets["route_signals"]
    }

    assert call_event.event_type == "TOOL_CALL"
    assert call_event.facets["session_act"]["kind"] == "mcp_tool_call"
    assert call_event.facets["nested_tool_invocations"] == [
        {
            "name": "mcp__aoa_session_memory__aoa_session_entity_usage_chain",
            "namespace": "mcp",
            "mcp_service_key": "aoa_session_memory_mcp",
        }
    ]
    assert route_signals[("mcp", "aoa_session_memory_mcp")]["source"] == "mcp_tool_service"
    assert ("mcp", "aoa_decisions_mcp") not in route_signals
    assert ("entity", "aoa_decisions_mcp") not in route_signals
    assert isinstance(entry, dict)
    assert next(
        item
        for item in entry["typed_anchors"]
        if (item["layer"], item["key"]) == ("mcp", "aoa_session_memory_mcp")
    )["relation"] == "invoked"

    module.handle_hook_event(
        "Stop",
        {
            "session_id": "nested-mcp-call",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )
    record = module.resolve_session_record(aoa_root, "nested-mcp-call")
    session_dir = Path(record["path"])
    segment_index = json.loads(
        next((session_dir / "segments").glob("*.index.json")).read_text(encoding="utf-8")
    )
    records = {event["event_id"]: event for event in segment_index["events"]}
    assert records["000003"]["type"] == "TOOL_OUTPUT"
    assert module.search_index_sessions(aoa_root=aoa_root, target="all", rebuild=True)["ok"] is True

    actual_service = module.entity_usage_chain(
        aoa_root=aoa_root,
        anchor="aoa_session_memory_mcp",
        kind="mcp",
        session="nested-mcp-call",
        limit=8,
        per_route_limit=12,
        consequence_window=2,
    )
    query_target = module.entity_usage_chain(
        aoa_root=aoa_root,
        anchor="aoa_decisions_mcp",
        kind="mcp",
        session="nested-mcp-call",
        limit=8,
        per_route_limit=12,
        consequence_window=2,
    )

    assert actual_service["ok"] is True
    assert actual_service["counts"]["usage_event_count"] == 1
    chain = actual_service["usage_chain"]["chains"][0]
    assert chain["usage_event"]["refs"]["raw"] == "raw:line:2"
    assert chain["result_or_consequence_events"][0]["refs"]["raw"] == "raw:line:3"
    assert chain["result_or_consequence_events"][0]["relation"] == "same_correlation_id"
    assert query_target["counts"]["usage_event_count"] == 0
    assert query_target["quality"]["direct_usage_present"] is False
    query_call_context = next(
        event
        for event in query_target["usage_chain"]["context_events"]
        if event["refs"]["raw"] == "raw:line:2"
    )
    assert query_call_context["role"] == "context"
    assert query_call_context["mcp_usage_admission"] == "mention_or_query_target_not_invocation"
    assert query_target["quality"]["mcp_usage_invocation_admission_applied"] is True
    assert query_target["quality"]["mcp_usage_mention_only_rejected_count"] == 1
    assert "mcp_mention_or_query_target_not_invocation" in query_target["noise_flags"]
def test_tool_usage_chain_admits_raw_verified_nested_call_and_rejects_string_mention(
    tmp_path: Path,
) -> None:
    """Owner-neutral regression derived from the manual W3 nested-tool span."""
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    session_id = "nested-tool-invocation-admission"
    transcript = tmp_path / "rollout-nested-tool-invocation-admission.jsonl"
    write_jsonl(
        transcript,
        [
            {
                "timestamp": "2026-07-17T00:00:00Z",
                "type": "session_meta",
                "payload": {"id": session_id, "cwd": str(workspace)},
            },
            {
                "timestamp": "2026-07-17T00:00:01Z",
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call",
                    "name": "exec",
                    "call_id": "call-nested-patch",
                    "input": (
                        "const patch = '*** Begin Patch\\n*** Update File: "
                        "/repo/example.py\\n@@\\n+ok'; "
                        "text(await tools.apply_patch(patch));"
                    ),
                },
            },
            {
                "timestamp": "2026-07-17T00:00:02Z",
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call_output",
                    "call_id": "call-nested-patch",
                    "output": "Success. Updated /repo/example.py",
                },
            },
            {
                "timestamp": "2026-07-17T00:00:03Z",
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call",
                    "name": "exec",
                    "call_id": "call-string-mention",
                    "input": "text('Documentation: tools.apply_patch(patch)');",
                },
            },
            {
                "timestamp": "2026-07-17T00:00:04Z",
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call_output",
                    "call_id": "call-string-mention",
                    "output": "Documentation rendered",
                },
            },
            {
                "timestamp": "2026-07-17T00:00:05Z",
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call",
                    "name": "apply_patch",
                    "call_id": "call-direct-patch",
                    "input": (
                        "*** Begin Patch\\n*** Update File: "
                        "/repo/other.py\\n@@\\n+ok"
                    ),
                },
            },
            {
                "timestamp": "2026-07-17T00:00:06Z",
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call_output",
                    "call_id": "call-direct-patch",
                    "output": "Success. Updated /repo/other.py",
                },
            },
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
    record = module.resolve_session_record(aoa_root, session_id)
    assert module.search_index_sessions(
        aoa_root=aoa_root,
        target="all",
        rebuild=True,
    )["ok"] is True

    payload = module.entity_usage_chain(
        aoa_root=aoa_root,
        anchor="apply_patch",
        kind="tool",
        session=str(record["session_label"]),
        limit=8,
        per_route_limit=12,
        consequence_window=3,
    )

    assert payload["ok"] is True
    assert payload["counts"]["usage_event_count"] == 2
    assert payload["quality"]["tool_usage_invocation_admitted_count"] == 2
    assert payload["quality"]["tool_usage_mention_only_rejected_count"] == 1
    assert payload["quality"]["tool_usage_invocation_unverifiable_count"] == 0
    assert payload["quality"]["tool_usage_invocation_admission_scope"] == (
        "all_candidates_structured_identity_or_raw_nested_invocation"
    )

    chains = {
        item["usage_event"]["refs"]["raw"]: item
        for item in payload["usage_chain"]["chains"]
    }
    assert set(chains) == {"raw:line:2", "raw:line:6"}
    nested_usage = chains["raw:line:2"]["usage_event"]
    assert nested_usage["tool_usage_admission"] == (
        "structured_nested_invocation_proven"
    )
    assert nested_usage["tool_usage_admission_key"] == "apply_patch"
    assert nested_usage["tool_usage_invocation_name"] == "apply_patch"
    assert nested_usage["tool_usage_invocation_namespace"] == (
        "codex_developer_tool"
    )
    assert "raw:line:3" in {
        event["refs"]["raw"]
        for event in chains["raw:line:2"]["result_or_consequence_events"]
    }

    direct_usage = chains["raw:line:6"]["usage_event"]
    assert direct_usage["tool_usage_admission"] == "structured_invocation_proven"
    assert direct_usage["tool_usage_admission_key"] == "apply_patch"
    assert "raw:line:7" in {
        event["refs"]["raw"]
        for event in chains["raw:line:6"]["result_or_consequence_events"]
    }

    mention = next(
        event
        for event in payload["usage_chain"]["context_events"]
        if event["refs"]["raw"] == "raw:line:4"
    )
    assert mention["role"] == "context"
    assert mention["tool_usage_admission"] == (
        "mention_not_structured_tool_invocation"
    )
    assert "tool_text_mention_not_structured_invocation" in payload["noise_flags"]
    accepted_consequence_refs = {
        event["refs"]["raw"]
        for item in payload["usage_chain"]["chains"]
        for event in item["result_or_consequence_events"]
    }
    assert "raw:line:5" not in accepted_consequence_refs
def test_mcp_tool_usage_chain_resolves_bare_registry_alias_and_structured_receipt(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """Regression derived from the gold-first W3 aoa-memo MCP-tool span."""
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    codex_home = tmp_path / ".codex"
    codex_home.mkdir()
    mcp_services_root = tmp_path / "mcp-services"
    service_dir = mcp_services_root / "aoa-memo-mcp"
    server_path = service_dir / "src" / "aoa_memo_mcp" / "server.py"
    server_path.parent.mkdir(parents=True)
    server_path.write_text(
        "def build_server():\n"
        "    @mcp.tool(name=\"aoa_memo_search\")\n"
        "    def search(query: str = \"\") -> dict:\n"
        "        return {\"ok\": True, \"query\": query}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv(
        "AOA_ENTITY_REGISTRY_MCP_SERVICES_ROOTS",
        str(mcp_services_root),
    )

    transcript = tmp_path / "rollout-2026-07-10T00-00-00-mcp-tool-gold.jsonl"
    listing_call_id = "call-mcp-tool-listing-only"
    invocation_call_id = "call-mcp-tool-real-invocation"
    write_jsonl(
        transcript,
        [
            {
                "timestamp": "2026-07-10T10:05:00Z",
                "type": "session_meta",
                "payload": {
                    "id": "mcp-tool-gold",
                    "cwd": str(workspace),
                    "evidence_origin": "synthetic_from_manual_w3",
                },
            },
            {
                "timestamp": "2026-07-10T10:05:10Z",
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call",
                    "name": "exec",
                    "call_id": listing_call_id,
                    "input": (
                        "text(ALL_TOOLS.filter("
                        "x => /aoa_memo/i.test(x.name)));"
                    ),
                },
            },
            {
                "timestamp": "2026-07-10T10:05:11Z",
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call_output",
                    "call_id": listing_call_id,
                    "output": (
                        "available only: "
                        "mcp__aoa_memo__aoa_memo_search"
                    ),
                },
            },
            {
                "timestamp": "2026-07-10T10:05:14Z",
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call",
                    "name": "exec",
                    "call_id": invocation_call_id,
                    "input": (
                        "const r = await "
                        "tools.mcp__aoa_memo__aoa_memo_search({"
                        "query: 'distributed memory organ foundation', "
                        "mode: 'inspect', scope: 'central'"
                        "}); text(r);"
                    ),
                },
            },
            {
                "timestamp": "2026-07-10T10:05:14.500Z",
                "type": "event_msg",
                "payload": {
                    "type": "mcp_tool_call_end",
                    "call_id": "exec-runtime-receipt",
                    "invocation": {
                        "server": "aoa_memo",
                        "tool": "aoa_memo_search",
                        "arguments": {
                            "query": "distributed memory organ foundation",
                            "mode": "inspect",
                            "scope": "central",
                        },
                    },
                    "result": {
                        "Ok": {
                            "isError": False,
                            "structuredContent": {
                                "hits": [
                                    {
                                        "id": (
                                            "memo.decision.2026-05-25."
                                            "distributed-memory-organ-foundation"
                                        )
                                    }
                                ]
                            },
                        }
                    },
                },
            },
            {
                "timestamp": "2026-07-10T10:05:15Z",
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call_output",
                    "call_id": invocation_call_id,
                    "output": json.dumps(
                        {
                            "ok": True,
                            "hit": (
                                "memo.decision.2026-05-25."
                                "distributed-memory-organ-foundation"
                            ),
                        }
                    ),
                },
            },
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "mcp-tool-gold",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )
    record = module.resolve_session_record(aoa_root, "mcp-tool-gold")
    session_dir = Path(record["path"])
    segment_index = json.loads(
        next((session_dir / "segments").glob("*.index.json")).read_text(
            encoding="utf-8"
        )
    )
    events = {
        event["event_id"]: event
        for event in segment_index["events"]
    }
    assert module.search_index_sessions(
        aoa_root=aoa_root,
        target="all",
        rebuild=True,
    )["ok"] is True

    receipt_identity = events["000005"]["facets"]["mcp_result_identity"]
    assert receipt_identity == {
        "service_key": "aoa_memo_mcp",
        "tool_key": "aoa_memo_search",
        "route_key": "mcp_aoa_memo_aoa_memo_search",
    }

    chain = module.entity_usage_chain(
        aoa_root=aoa_root,
        anchor="aoa_memo_search",
        kind="mcp_tool",
        session="mcp-tool-gold",
        limit=8,
        per_route_limit=12,
        consequence_window=4,
    )

    assert chain["ok"] is True
    assert chain["requested_kind"] == "mcp_tool"
    assert chain["normalized_entity"]["kind"] == "mcp_tool"
    assert chain["counts"]["usage_event_count"] == 1
    assert chain["quality"]["mcp_tool_identity_status"] == "resolved"
    assert chain["quality"]["mcp_tool_requested_route_keys"] == [
        "mcp_aoa_memo_aoa_memo_search"
    ]
    assert chain["quality"]["mcp_tool_invocation_admitted_count"] == 1
    usage_chain = chain["usage_chain"]["chains"][0]
    assert usage_chain["usage_event"]["refs"]["raw"] == "raw:line:4"
    assert usage_chain["usage_event"]["mcp_tool_usage_admission"] == (
        "structured_invocation_proven"
    )
    attached = {
        event["refs"]["raw"]: event
        for event in usage_chain["result_or_consequence_events"]
    }
    assert set(attached) == {"raw:line:5", "raw:line:6"}
    assert attached["raw:line:5"]["relation"] == (
        "structured_mcp_receipt_identity_match"
    )
    assert attached["raw:line:5"]["mcp_result_identity"] == receipt_identity
    assert attached["raw:line:5"]["result_status"] == "succeeded"
    context_raw_refs = {
        event["refs"]["raw"]
        for event in chain["usage_chain"]["context_events"]
    }
    assert context_raw_refs.isdisjoint(attached)
    assert (
        chain["counts"]["attached_context_duplicate_suppressed_count"]
        == 1
    )
    assert (
        chain["counts"]["duplicate_accepted_event_association_count"]
        == 0
    )
    assert {
        event["refs"]["raw"]
        for item in chain["usage_chain"]["chains"]
        for event in [item["usage_event"]]
    }.isdisjoint({"raw:line:2", "raw:line:3"})
def test_mcp_tool_usage_chain_requires_namespace_for_colliding_bare_alias(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """A bare MCP-tool alias cannot merge invocations from two services."""
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    codex_home = tmp_path / ".codex"
    codex_home.mkdir()
    mcp_services_root = tmp_path / "mcp-services"
    for service_name in ("alpha-mcp", "beta-mcp"):
        service_dir = mcp_services_root / service_name
        server_path = (
            service_dir
            / "src"
            / service_name.replace("-", "_")
            / "server.py"
        )
        server_path.parent.mkdir(parents=True)
        server_path.write_text(
            "def build_server():\n"
            "    @mcp.tool(name=\"lookup\")\n"
            "    def lookup(query: str = \"\") -> dict:\n"
            "        return {\"ok\": True, \"query\": query}\n",
            encoding="utf-8",
        )
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv(
        "AOA_ENTITY_REGISTRY_MCP_SERVICES_ROOTS",
        str(mcp_services_root),
    )

    transcript = tmp_path / "rollout-mcp-tool-alias-collision.jsonl"
    write_jsonl(
        transcript,
        [
            {
                "timestamp": "2026-07-10T00:00:00Z",
                "type": "session_meta",
                "payload": {
                    "id": "mcp-tool-alias-collision",
                    "cwd": str(workspace),
                    "evidence_origin": "synthetic_from_manual_w3",
                },
            },
            {
                "timestamp": "2026-07-10T00:00:01Z",
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call",
                    "name": "exec",
                    "call_id": "call-alpha-lookup",
                    "input": (
                        "const r = await tools.mcp__alpha__lookup({"
                        "query: 'one'}); text(r);"
                    ),
                },
            },
            {
                "timestamp": "2026-07-10T00:00:02Z",
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call_output",
                    "call_id": "call-alpha-lookup",
                    "output": '{"ok":true,"service":"alpha"}',
                },
            },
            {
                "timestamp": "2026-07-10T00:00:03Z",
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call",
                    "name": "exec",
                    "call_id": "call-beta-lookup",
                    "input": (
                        "const r = await tools.mcp__beta__lookup({"
                        "query: 'two'}); text(r);"
                    ),
                },
            },
            {
                "timestamp": "2026-07-10T00:00:04Z",
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call_output",
                    "call_id": "call-beta-lookup",
                    "output": '{"ok":true,"service":"beta"}',
                },
            },
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "mcp-tool-alias-collision",
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

    ambiguous = module.entity_usage_chain(
        aoa_root=aoa_root,
        anchor="lookup",
        kind="mcp_tool",
        session="mcp-tool-alias-collision",
        limit=8,
        per_route_limit=12,
        consequence_window=2,
    )
    alpha = module.entity_usage_chain(
        aoa_root=aoa_root,
        anchor="mcp__alpha__lookup",
        kind="mcp_tool",
        session="mcp-tool-alias-collision",
        limit=8,
        per_route_limit=12,
        consequence_window=2,
    )

    assert ambiguous["quality"]["mcp_tool_identity_status"] == "ambiguous"
    assert ambiguous["quality"]["mcp_tool_requested_route_keys"] == [
        "mcp_alpha_lookup",
        "mcp_beta_lookup",
    ]
    assert ambiguous["counts"]["usage_event_count"] == 0
    assert ambiguous["quality"]["mcp_tool_invocation_admitted_count"] == 0
    assert ambiguous["quality"]["mcp_tool_mention_only_rejected_count"] == 2
    assert "mcp_tool_identity_ambiguous" in ambiguous["noise_flags"]

    assert alpha["quality"]["mcp_tool_identity_status"] == "resolved"
    assert alpha["quality"]["mcp_tool_requested_route_keys"] == [
        "mcp_alpha_lookup"
    ]
    assert alpha["counts"]["usage_event_count"] == 1
    assert alpha["usage_chain"]["chains"][0]["usage_event"]["refs"][
        "raw"
    ] == "raw:line:2"
    assert alpha["quality"]["mcp_tool_invocation_admitted_count"] == 1

    ambiguous_state = module.episode_entity_state_search(
        aoa_root=aoa_root,
        anchor="lookup",
        kind="mcp_tool",
        session="mcp-tool-alias-collision",
        time_to="2026-07-10T00:00:04.500Z",
        limit=8,
    )
    assert ambiguous_state["mcp_tool_resolution"]["status"] == "ambiguous"
    assert ambiguous_state["answer_admission"]["admitted"] is False
    assert (
        ambiguous_state["time_scoped_raw_state"]["status"]
        == "mcp_tool_identity_unresolved"
    )
    assert ambiguous_state["entity_state"] == (
        "time_scoped_entity_state_unresolved"
    )

    alpha_state = module.episode_entity_state_search(
        aoa_root=aoa_root,
        anchor="mcp__alpha__lookup",
        kind="mcp_tool",
        session="mcp-tool-alias-collision",
        time_to="2026-07-10T00:00:04.500Z",
        limit=8,
    )
    assert alpha_state["mcp_tool_resolution"]["status"] == "resolved"
    assert alpha_state["answer_admission"]["status"] == (
        "invoked_in_requested_time_scope"
    )
    assert alpha_state["relation_counts"] == {"invoked": 1}
    assert alpha_state["results"][0]["raw_ref"] == "raw:line:2"
def test_mcp_tool_bare_name_uses_scoped_raw_identity_without_registry_projection(
    tmp_path: Path,
) -> None:
    """A bare live tool name is admissible only after raw service resolution."""
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-scoped-raw-mcp-identity.jsonl"
    write_jsonl(
        transcript,
        [
            {
                "timestamp": "2026-07-10T10:00:00Z",
                "type": "session_meta",
                "payload": {
                    "id": "scoped-raw-mcp-identity",
                    "cwd": str(workspace),
                    "evidence_origin": "synthetic_from_manual_mcp_raw_span",
                },
            },
            {
                "timestamp": "2026-07-10T10:00:01Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "lookup",
                    "namespace": "mcp__alpha",
                    "call_id": "call-scoped-lookup",
                    "arguments": '{"query":"needle"}',
                },
            },
            {
                "timestamp": "2026-07-10T10:00:02Z",
                "type": "event_msg",
                "payload": {
                    "type": "mcp_tool_call_end",
                    "call_id": "call-scoped-lookup",
                    "invocation": {
                        "server": "alpha",
                        "tool": "lookup",
                        "arguments": {"query": "needle"},
                    },
                    "result": {"Ok": {"content": []}},
                },
            },
            {
                "timestamp": "2026-07-10T10:00:03Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "call-scoped-lookup",
                    "output": '{"ok":true,"value":"needle"}',
                },
            },
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "scoped-raw-mcp-identity",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    chain = module.entity_usage_chain(
        aoa_root=aoa_root,
        anchor="lookup",
        kind="mcp_tool",
        session="scoped-raw-mcp-identity",
        limit=8,
        per_route_limit=8,
        consequence_window=4,
    )

    resolution = chain["quality"]["mcp_tool_resolution"]
    assert resolution["status"] == "resolved"
    assert resolution["resolution_source"] == (
        "session_scoped_structured_raw_identity"
    )
    assert resolution["identities"] == [
        {
            "service_key": "alpha_mcp",
            "tool_key": "lookup",
            "route_key": "mcp_alpha_lookup",
        }
    ]
    probe = resolution["session_identity_probe"]
    assert probe["source_scan"]["status"] == "complete"
    source_fingerprint = probe["source_scan"]["source_fingerprint"]
    assert source_fingerprint
    assert probe["raw_ref_verified_count"] == 2
    assert probe["structured_call_count"] == 1
    assert probe["structured_receipt_count"] == 1
    assert chain["counts"]["usage_event_count"] == 1
    usage = chain["usage_chain"]["chains"][0]["usage_event"]
    assert usage["refs"]["raw"] == "raw:line:2"
    assert usage["mcp_tool_usage_admission"] == (
        "structured_invocation_proven"
    )
    assert chain["usage_lifecycle"]["states"]["invoked"][
        "positive_instance_admitted"
    ] is True
    assert chain["usage_lifecycle"]["states"]["completed"][
        "positive_instance_admitted"
    ] is True
    assert chain["usage_lifecycle"]["states"]["verified"]["present"] is False
    assert chain["generation_identities"]["compatible"] is False
    assert chain["generation_identities"]["observed"]["query_source"][
        "session_index"
    ]
    scoped_freshness = chain["freshness"]["scoped"]
    assert scoped_freshness["status"] == "current"
    assert scoped_freshness["does_not_upgrade_global_freshness"] is True
    assert scoped_freshness["source_contributions"] == [
        {
            "candidate_id": (
                "archived-raw-session:scoped-raw-mcp-identity"
            ),
            "session_id": "scoped-raw-mcp-identity",
            "status": "current",
            "observed_status": "bounded_current",
            "source_fingerprint": source_fingerprint,
            "source_ref": probe["source_scan"]["session_manifest"],
            "basis": "session_scoped_query_time_raw_ref_verification",
        }
    ]
    envelope_scoped = chain["evidence_envelope"]["freshness"]["scoped"]
    assert envelope_scoped["status"] == "current"
    assert envelope_scoped["source_contributions"] == (
        scoped_freshness["source_contributions"]
    )
    assert chain["freshness"]["global"]["scope"] == (
        "selected_search_provider_projection"
    )
def test_mcp_tool_usage_chain_keeps_parallel_same_tool_receipts_correlated(
    tmp_path: Path,
) -> None:
    """Regression derived from the real parallel aoa-stats span."""
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-parallel-mcp-tool-receipts.jsonl"
    qualified_name = "mcp__aoa_stats__stats_surface_read"
    write_jsonl(
        transcript,
        [
            {
                "timestamp": "2026-04-16T14:49:41.000Z",
                "type": "session_meta",
                "payload": {
                    "id": "parallel-mcp-tool-receipts",
                    "cwd": str(workspace),
                    "evidence_origin": "synthetic_from_manual_parallel_span",
                },
            },
            {
                "timestamp": "2026-04-16T14:49:41.100Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": qualified_name,
                    "call_id": "call-alpha",
                    "arguments": '{"surface":"alpha"}',
                },
            },
            {
                "timestamp": "2026-04-16T14:49:41.110Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": qualified_name,
                    "call_id": "call-beta",
                    "arguments": '{"surface":"beta"}',
                },
            },
            {
                "timestamp": "2026-04-16T14:49:41.120Z",
                "type": "event_msg",
                "payload": {
                    "type": "mcp_tool_call_end",
                    "call_id": "call-beta",
                    "invocation": {
                        "server": "aoa_stats",
                        "tool": "stats_surface_read",
                    },
                    "result": {"Ok": {"isError": False}},
                },
            },
            {
                "timestamp": "2026-04-16T14:49:41.130Z",
                "type": "event_msg",
                "payload": {
                    "type": "mcp_tool_call_end",
                    "call_id": "call-alpha",
                    "invocation": {
                        "server": "aoa_stats",
                        "tool": "stats_surface_read",
                    },
                    "result": {"Ok": {"isError": False}},
                },
            },
            {
                "timestamp": "2026-04-16T14:49:41.140Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "call-beta",
                    "output": '{"ok":true,"surface":"beta"}',
                },
            },
            {
                "timestamp": "2026-04-16T14:49:41.150Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "call-alpha",
                    "output": '{"ok":true,"surface":"alpha"}',
                },
            },
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "parallel-mcp-tool-receipts",
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

    chain = module.entity_usage_chain(
        aoa_root=aoa_root,
        anchor=qualified_name,
        kind="mcp_tool",
        session="parallel-mcp-tool-receipts",
        limit=8,
        per_route_limit=12,
        consequence_window=6,
    )

    assert chain["counts"]["usage_event_count"] == 2
    assert chain["quality"]["mcp_tool_invocation_admitted_count"] == 2
    chains_by_correlation = {
        item["usage_event"]["correlation_id"]: item
        for item in chain["usage_chain"]["chains"]
    }
    assert set(chains_by_correlation) == {"call-alpha", "call-beta"}
    for correlation_id, item in chains_by_correlation.items():
        consequences = item["result_or_consequence_events"]
        assert len(consequences) == 2
        assert {
            event["correlation_id"]
            for event in consequences
        } == {correlation_id}
        receipt = next(
            event
            for event in consequences
            if event["mcp_result_identity"]
        )
        assert receipt["relation"] == (
            "structured_mcp_receipt_correlation_identity_match"
        )
        assert receipt["source_correlation_id"] == correlation_id
def test_entity_usage_test_and_validator_admission_rejects_source_inspection(
    tmp_path: Path,
) -> None:
    """Regression derived from manual raw review of the 20260717 tail-entity wave."""
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-07-17T00-00-00-execution-admission.jsonl"

    def custom_call(call_id: str, command_source: str) -> dict[str, Any]:
        return {
            "timestamp": "2026-07-17T00:00:01Z",
            "type": "response_item",
            "payload": {
                "type": "custom_tool_call",
                "name": "exec",
                "call_id": call_id,
                "input": command_source,
            },
        }

    def custom_result(call_id: str) -> dict[str, Any]:
        return {
            "timestamp": "2026-07-17T00:00:02Z",
            "type": "response_item",
            "payload": {
                "type": "custom_tool_call_output",
                "call_id": call_id,
                "output": "Script completed\nWall time 0.1 seconds\nOutput:\npassed\n",
            },
        }

    rows = [
        {
            "timestamp": "2026-07-17T00:00:00Z",
            "type": "session_meta",
            "payload": {"id": "execution-admission", "cwd": str(workspace)},
        },
        custom_call(
            "call-test-inspection",
            (
                "const r = await tools.exec_command({"
                "cmd: \"rg -n '^def test_' tests/test_session_memory.py\""
                "}); text(r.output);"
            ),
        ),
        custom_result("call-test-inspection"),
        custom_call(
            "call-test-run",
            (
                "const jobs = ["
                "\"PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/test_session_memory.py\""
                "]; const r = await tools.exec_command({cmd: jobs[0]}); text(r.output);"
            ),
        ),
        custom_result("call-test-run"),
        custom_call(
            "call-test-mapped-run",
            (
                "const specs = ["
                "[\"smoke\", \"python3 -m pytest -q tests/test_session_memory.py\", \"/tmp\"],"
                "[\"other\", \"echo ok\", \"/tmp\"]"
                "]; const results = await Promise.all(specs.map("
                "([name,cmd,workdir]) => tools.exec_command({cmd,workdir})"
                ")); text(results.length);"
            ),
        ),
        custom_result("call-test-mapped-run"),
        custom_call(
            "call-validator-existence",
            (
                "const r = await tools.exec_command({"
                "cmd: \"test -f scripts/validate_session_memory_mcp.py && echo present\""
                "}); text(r.output);"
            ),
        ),
        custom_result("call-validator-existence"),
        custom_call(
            "call-validator-helper-import",
            (
                "const r = await tools.exec_command({"
                "cmd: \"python3 - <<'PY'\n"
                "from pathlib import Path\n"
                "validator_path = Path('scripts/validate_session_memory_mcp.py')\n"
                "print(validator_path)\n"
                "PY\""
                "}); text(r.output);"
            ),
        ),
        custom_result("call-validator-helper-import"),
        custom_call(
            "call-validator-regex-filter",
            (
                "const out = await tools.exec_command({"
                "cmd: `git diff-tree --name-status ${commit}`"
                "});"
                "const selected = out.output.split('\\n').filter("
                "x => /scripts\\/(validate_session_memory_mcp|other)/.test(x)"
                "); text(selected);"
            ),
        ),
        custom_result("call-validator-regex-filter"),
        custom_call(
            "call-validator-patch-reference",
            (
                "const patch = \"*** Begin Patch\\n"
                "*** Update File: README.md\\n"
                "@@\\n"
                "-python3 scripts/validate_session_memory_mcp.py\\n"
                "*** End Patch\";"
                "const r = await tools.apply_patch(patch); text(r);"
            ),
        ),
        custom_result("call-validator-patch-reference"),
        custom_call(
            "call-validator-run",
            (
                "const cmd = \"python3 scripts/validate_session_memory_mcp.py\";"
                "const r = await tools.exec_command({cmd}); text(r.output);"
            ),
        ),
        custom_result("call-validator-run"),
        custom_call(
            "call-validator-nested-run",
            (
                "const r = await tools.exec_command({cmd: `python3 - <<'PY'\n"
                "import subprocess\n"
                "for cmd in (['python', 'scripts/validate_session_memory_mcp.py'],):\n"
                "    subprocess.run(cmd, check=True)\n"
                "PY`}); text(r.output);"
            ),
        ),
        custom_result("call-validator-nested-run"),
        {
            "timestamp": "2026-07-17T00:00:03Z",
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "exec_command",
                "arguments": json.dumps({"cmd": "python scripts/release_check.py"}),
                "call_id": "call-validator-runner",
            },
        },
        {
            "timestamp": "2026-07-17T00:00:04Z",
            "type": "response_item",
            "payload": {
                "type": "function_call_output",
                "call_id": "call-validator-runner",
                "output": (
                    "[run] validate memory route: "
                    "/usr/bin/python scripts/validate_session_memory_mcp.py\n"
                    "[ok] validated memory route\n"
                ),
            },
        },
        {
            "timestamp": "2026-07-17T00:00:05Z",
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "exec_command",
                "arguments": json.dumps({"cmd": "cat README.md"}),
                "call_id": "call-validator-doc-read",
            },
        },
        {
            "timestamp": "2026-07-17T00:00:06Z",
            "type": "response_item",
            "payload": {
                "type": "function_call_output",
                "call_id": "call-validator-doc-read",
                "output": (
                    "[run] example only: "
                    "/usr/bin/python scripts/validate_session_memory_mcp.py\n"
                    "[ok] documentation example\n"
                ),
            },
        },
        custom_call(
            "call-validator-async-origin",
            (
                "const r = await tools.exec_command({"
                "cmd: \"python scripts/release_check.py\""
                "}); text(r.output);"
            ),
        ),
        {
            "timestamp": "2026-07-17T00:00:07Z",
            "type": "response_item",
            "payload": {
                "type": "custom_tool_call_output",
                "call_id": "call-validator-async-origin",
                "output": "Script running with cell ID 42\nWall time 10 seconds\nOutput:\n",
            },
        },
        {
            "timestamp": "2026-07-17T00:00:08Z",
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "wait",
                "arguments": json.dumps({"cell_id": "42"}),
                "call_id": "call-validator-async-wait",
            },
        },
        {
            "timestamp": "2026-07-17T00:00:09Z",
            "type": "response_item",
            "payload": {
                "type": "function_call_output",
                "call_id": "call-validator-async-wait",
                "output": (
                    "Script completed\nWall time 12 seconds\nOutput:\n"
                    "[run] validate memory route: "
                    "/usr/bin/python scripts/validate_session_memory_mcp.py\n"
                    "[ok] validated memory route\n"
                ),
            },
        },
        {
            "timestamp": "2026-07-17T00:00:10Z",
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "exec_command",
                "arguments": json.dumps(
                    {
                        "cmd": (
                            "sed -n '1,20p' "
                            "scripts/validate_session_memory_mcp.py"
                        )
                    }
                ),
                "call_id": "call-validator-source-read",
            },
        },
        {
            "timestamp": "2026-07-17T00:00:11Z",
            "type": "response_item",
            "payload": {
                "type": "function_call_output",
                "call_id": "call-validator-source-read",
                "output": "#!/usr/bin/env python3\n",
            },
        },
    ]
    write_jsonl(transcript, rows)

    receipt = module.handle_hook_event(
        "Stop",
        {
            "session_id": "execution-admission",
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
    assert module.entity_usage_execution_command_proves_inspection_read(
        "sed -n '1,20p' scripts/validate_session_memory_mcp.py",
        anchor="validate_session_memory_mcp",
    )
    assert not module.entity_usage_execution_command_proves_inspection_read(
        "rg -n validate_session_memory_mcp README.md",
        anchor="validate_session_memory_mcp",
    )

    test_chain = module.entity_usage_chain(
        aoa_root=aoa_root,
        anchor="test_session_memory",
        kind="test",
        session="execution-admission",
        limit=8,
        per_route_limit=12,
        consequence_window=2,
    )
    assert test_chain["counts"]["usage_event_count"] == 2
    assert test_chain["usage_chain"]["chains"][0]["usage_event"]["refs"]["raw"] == "raw:line:6"
    assert test_chain["usage_chain"]["chains"][1]["usage_event"]["refs"]["raw"] == "raw:line:4"
    assert all(
        chain["usage_event"]["usage_actions"]
        == ["called", "validated", "invoked"]
        for chain in test_chain["usage_chain"]["chains"]
    )
    test_context = next(
        event
        for event in test_chain["usage_chain"]["context_events"]
        if event["refs"]["raw"] == "raw:line:2"
    )
    assert test_context["execution_entity_usage_admission"] == (
        "inspection_or_reference_not_invocation"
    )
    assert test_chain["quality"]["execution_usage_invocation_admitted_count"] == 2
    assert test_chain["quality"]["execution_usage_reference_rejected_count"] == 1
    assert "test_or_validator_reference_not_invocation" in test_chain["noise_flags"]

    validator_chain = module.entity_usage_chain(
        aoa_root=aoa_root,
        anchor="validate_session_memory_mcp",
        kind="validator",
        session="execution-admission",
        limit=12,
        per_route_limit=12,
        consequence_window=2,
    )
    assert validator_chain["counts"]["usage_event_count"] == 4
    validator_usage_by_raw = {
        chain["usage_event"]["refs"]["raw"]: chain["usage_event"]
        for chain in validator_chain["usage_chain"]["chains"]
    }
    assert set(validator_usage_by_raw) == {
        "raw:line:16",
        "raw:line:18",
        "raw:line:21",
        "raw:line:27",
    }
    assert validator_usage_by_raw["raw:line:21"]["execution_parent_refs"][
        "raw"
    ] == "raw:line:20"
    assert validator_usage_by_raw["raw:line:21"]["usage_actions"] == [
        "called",
        "validated",
        "invoked",
    ]
    assert validator_usage_by_raw["raw:line:27"]["execution_parent_refs"][
        "raw"
    ] == "raw:line:24"
    assert validator_usage_by_raw["raw:line:16"]["usage_actions"] == [
        "called",
        "validated",
        "invoked",
    ]
    validator_contexts = {
        event["refs"]["raw"]: event
        for event in validator_chain["usage_chain"]["context_events"]
    }
    assert set(validator_contexts) >= {
        "raw:line:8",
        "raw:line:10",
        "raw:line:12",
        "raw:line:14",
    }
    assert validator_contexts["raw:line:8"][
        "execution_entity_usage_admission"
    ] == "inspection_or_reference_not_invocation"
    assert validator_contexts["raw:line:10"][
        "execution_entity_usage_admission"
    ] == "inspection_or_reference_not_invocation"
    assert validator_contexts["raw:line:10"]["usage_actions"] == ["referenced"]
    assert validator_contexts["raw:line:12"][
        "execution_entity_usage_admission"
    ] == "inspection_or_reference_not_invocation"
    assert validator_contexts["raw:line:14"][
        "execution_entity_usage_admission"
    ] == "inspection_or_reference_not_invocation"
    assert validator_contexts["raw:line:28"][
        "execution_entity_usage_admission"
    ] == "structured_inspection_read_proven"
    assert validator_contexts["raw:line:28"][
        "execution_read_result_refs"
    ]["raw"] == "raw:line:29"
    assert validator_contexts["raw:line:28"]["usage_actions"] == ["read"]
    assert validator_chain["quality"]["execution_usage_invocation_admitted_count"] == 4
    assert validator_chain["quality"][
        "execution_usage_structured_result_admitted_count"
    ] == 2
    assert validator_chain["quality"][
        "execution_usage_structured_result_parent_rejected_count"
    ] == 1
    assert all(
        chain["usage_event"]["refs"]["raw"] != "raw:line:23"
        for chain in validator_chain["usage_chain"]["chains"]
    )
    assert validator_chain["quality"]["execution_usage_reference_rejected_count"] == 5

    compact_validator_chain = module.entity_usage_chain(
        aoa_root=aoa_root,
        anchor="validate_session_memory_mcp",
        kind="validator",
        session="execution-admission",
        limit=5,
        per_route_limit=12,
        consequence_window=2,
    )
    assert compact_validator_chain["counts"]["usage_event_count"] == 4
    assert compact_validator_chain["usage_action_counts"]["read"] == 1
    assert compact_validator_chain["quality"]["action_diversity"][
        "read_sample_present"
    ] is True
    assert compact_validator_chain["quality"]["action_diversity"][
        "selected_event_id"
    ] == "000028"
    read_state = validator_chain["usage_lifecycle"]["states"]["read"]
    assert read_state["present"] is True
    assert read_state["positive_instance_admitted"] is True
    assert read_state["evidence_sample"][0]["refs"]["raw"] == (
        "raw:line:28"
    )
    assert read_state["evidence_sample"][0]["read_result_refs"][
        "raw"
    ] == "raw:line:29"
def test_entity_usage_lifecycle_uses_owned_transport_and_test_result_proof(
    tmp_path: Path,
) -> None:
    """Regression derived from sealed raw-first test/validator/script cases."""
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = (
        tmp_path
        / "rollout-2026-07-18T00-05-00-owned-lifecycle-proof.jsonl"
    )

    def custom_call(call_id: str, command: str) -> dict[str, Any]:
        return {
            "timestamp": "2026-07-18T00:05:01Z",
            "type": "response_item",
            "payload": {
                "type": "custom_tool_call",
                "name": "exec",
                "call_id": call_id,
                "input": (
                    "const r = await tools.exec_command({"
                    f'"cmd":{json.dumps(command)}'
                    "}); text(r.output);"
                ),
            },
        }

    def custom_result(
        call_id: str,
        output: str,
    ) -> dict[str, Any]:
        return {
            "timestamp": "2026-07-18T00:05:02Z",
            "type": "response_item",
            "payload": {
                "type": "custom_tool_call_output",
                "call_id": call_id,
                "output": [
                    {
                        "type": "input_text",
                        "text": (
                            "Script completed\n"
                            "Wall time 0.2 seconds\n"
                            "Output:\n"
                        ),
                    },
                    {"type": "input_text", "text": output},
                ],
            },
        }

    write_jsonl(
        transcript,
        [
            {
                "timestamp": "2026-07-18T00:05:00Z",
                "type": "session_meta",
                "payload": {
                    "id": "owned-lifecycle-proof",
                    "cwd": str(workspace),
                },
            },
            custom_call(
                "call-test-validator",
                (
                    "python scripts/validate_mechanics_topology.py && "
                    "python -m pytest -q "
                    "tests/test_mechanics_topology.py"
                ),
            ),
            custom_result(
                "call-foreign",
                "999 passed in 0.01s\n",
            ),
            custom_result(
                "call-test-validator",
                (
                    "[ok] mechanics topology valid\n"
                    "14 passed in 0.12s\n"
                ),
            ),
            custom_call(
                "call-script",
                (
                    "python scripts/build_local_eval_port_inventory.py "
                    "--json"
                ),
            ),
            custom_result(
                "call-script",
                (
                    '{"repo_id":"aoa-skills",'
                    '"validator_ok":true}\n'
                ),
            ),
        ],
    )

    receipt = module.handle_hook_event(
        "Stop",
        {
            "session_id": "owned-lifecycle-proof",
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

    test_chain = module.entity_usage_chain(
        aoa_root=aoa_root,
        anchor="test_mechanics_topology.py",
        kind="test",
        session="owned-lifecycle-proof",
        limit=8,
        per_route_limit=12,
        consequence_window=4,
    )
    test_states = test_chain["usage_lifecycle"]["states"]
    assert test_states["invoked"]["present"] is True
    assert test_states["completed"]["status"] == "source_observed"
    assert test_states["verified"]["status"] == "source_observed"
    assert test_states["consequence-producing"]["present"] is False
    assert test_states["failed"]["present"] is False
    assert test_states["completed"]["evidence_sample"][0]["refs"]["raw"] == (
        "raw:line:4"
    )
    assert test_states["verified"]["evidence_sample"][0]["refs"]["raw"] == (
        "raw:line:4"
    )
    test_result = test_chain["usage_chain"]["chains"][0][
        "result_or_consequence_events"
    ][0]
    assert test_result["refs"]["raw"] == "raw:line:4"
    assert test_result["relation"] == "same_correlation_id"
    assert test_result["tool_transport_status"] == "completed"
    assert test_result["result_status"] is None
    assert test_result["verification_signals"] == [
        "delivery_state:tests_green"
    ]
    assert all(
        event["refs"]["raw"] != "raw:line:3"
        for event in test_chain["usage_chain"]["chains"][0][
            "result_or_consequence_events"
        ]
    )
    assert (
        test_chain["usage_lifecycle"]["correlation"][
            "rejected_context_count"
        ]
        >= 1
    )

    validator_chain = module.entity_usage_chain(
        aoa_root=aoa_root,
        anchor="validate_mechanics_topology.py",
        kind="validator",
        session="owned-lifecycle-proof",
        limit=8,
        per_route_limit=12,
        consequence_window=4,
    )
    validator_states = validator_chain["usage_lifecycle"]["states"]
    assert validator_states["invoked"]["present"] is True
    assert validator_states["completed"]["status"] == "source_observed"
    assert validator_states["verified"]["present"] is False
    assert validator_states["consequence-producing"]["present"] is False

    script_chain = module.entity_usage_chain(
        aoa_root=aoa_root,
        anchor="build_local_eval_port_inventory.py",
        kind="script",
        session="owned-lifecycle-proof",
        limit=8,
        per_route_limit=12,
        consequence_window=4,
    )
    script_states = script_chain["usage_lifecycle"]["states"]
    assert script_states["invoked"]["present"] is True
    assert script_states["completed"]["status"] == "source_observed"
    assert script_states["verified"]["present"] is False
    assert script_states["consequence-producing"]["present"] is False
def test_entity_usage_script_admission_distinguishes_request_from_observed_invocation(
    tmp_path: Path,
) -> None:
    """Regression from a randomized raw-first script pre-launch failure."""
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-07-18T00-00-00-script-admission.jsonl"

    def custom_call(call_id: str, command: str) -> dict[str, Any]:
        return {
            "timestamp": "2026-07-18T00:00:01Z",
            "type": "response_item",
            "payload": {
                "type": "custom_tool_call",
                "name": "exec",
                "call_id": call_id,
                "input": (
                    "const r = await tools.exec_command({"
                    f'"cmd":{json.dumps(command)}'
                    "}); text(r.output);"
                ),
            },
        }

    def custom_result(call_id: str, output: str) -> dict[str, Any]:
        return {
            "timestamp": "2026-07-18T00:00:02Z",
            "type": "response_item",
            "payload": {
                "type": "custom_tool_call_output",
                "call_id": call_id,
                "output": output,
            },
        }

    write_jsonl(
        transcript,
        [
            {
                "timestamp": "2026-07-18T00:00:00Z",
                "type": "session_meta",
                "payload": {"id": "script-admission", "cwd": str(workspace)},
            },
            custom_call(
                "call-script-prelaunch-failure",
                (
                    "set -u\n"
                    "path=docs/input.md\n"
                    'mv "$path" "$path.__hold"\n'
                    "out=$(python scripts/build_projection_index.py --check 2>&1); rc=$?\n"
                    "printf '[projection_check] rc=%s\\n' \"$rc\"\n"
                    "printf '%s\\n' \"$out\""
                ),
            ),
            custom_result(
                "call-script-prelaunch-failure",
                (
                    "Script completed\nWall time 0.1 seconds\nOutput:\n"
                    "zsh:3: command not found: mv\n"
                    "[projection_check] rc=127\n"
                ),
            ),
            custom_call(
                "call-script-observed",
                "python scripts/build_projection_index.py --check",
            ),
            custom_result(
                "call-script-observed",
                (
                    "Script completed\nWall time 0.2 seconds\nOutput:\n"
                    "[projection-index] check passed\n"
                ),
            ),
            custom_call(
                "call-script-observed-failure",
                (
                    "out=$(python scripts/build_projection_index.py --check 2>&1); "
                    "rc=$?; printf '[projection_check] rc=%s\\n' \"$rc\"; "
                    "printf '%s\\n' \"$out\""
                ),
            ),
            custom_result(
                "call-script-observed-failure",
                (
                    "Script completed\nWall time 0.2 seconds\nOutput:\n"
                    "[projection_check] rc=2\n"
                    "[projection-index] drift detected\n"
                ),
            ),
            custom_call(
                "call-script-time-wrapper",
                (
                    "/usr/bin/time -f 'wall=%e' "
                    "python scripts/build_projection_index.py --check"
                ),
            ),
            custom_result(
                "call-script-time-wrapper",
                (
                    "Script completed\nWall time 0.2 seconds\nOutput:\n"
                    "wall=0.1\n"
                ),
            ),
            custom_call(
                "call-script-forwarding-wrapper",
                (
                    "run_capture() { label=$1; shift; "
                    'out=$("$@" 2>&1); rc=$?; '
                    "printf '[%s] rc=%s\\n' \"$label\" \"$rc\"; }\n"
                    "run_capture projection_check "
                    "python scripts/build_projection_index.py --check"
                ),
            ),
            custom_result(
                "call-script-forwarding-wrapper",
                (
                    "Script completed\nWall time 0.2 seconds\nOutput:\n"
                    "[projection_check] rc=0\n"
                ),
            ),
            custom_call(
                "call-script-reference",
                "test -f scripts/build_projection_index.py && echo present",
            ),
            custom_result(
                "call-script-reference",
                "present\n",
            ),
        ],
    )

    receipt = module.handle_hook_event(
        "Stop",
        {
            "session_id": "script-admission",
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

    chain = module.entity_usage_chain(
        aoa_root=aoa_root,
        anchor="build_projection_index.py",
        kind="script",
        session="script-admission",
        limit=8,
        per_route_limit=12,
        consequence_window=2,
    )

    assert chain["ok"] is True
    assert chain["counts"]["usage_event_count"] == 4
    usage_by_raw = {
        item["usage_event"]["refs"]["raw"]: item["usage_event"]
        for item in chain["usage_chain"]["chains"]
    }
    assert set(usage_by_raw) == {
        "raw:line:4",
        "raw:line:6",
        "raw:line:8",
        "raw:line:10",
    }
    assert usage_by_raw["raw:line:4"]["execution_entity_usage_admission"] == (
        "structured_command_invocation_proven"
    )
    assert usage_by_raw["raw:line:4"]["usage_actions"] == ["called", "invoked"]
    assert usage_by_raw["raw:line:6"]["execution_entity_usage_result_status"] == (
        "failed"
    )
    assert usage_by_raw["raw:line:6"]["execution_entity_usage_result_code"] == 2
    assert usage_by_raw["raw:line:6"]["usage_actions"] == [
        "called",
        "invoked",
        "failed",
    ]
    contexts = {
        event["refs"]["raw"]: event
        for event in chain["usage_chain"]["context_events"]
    }
    assert contexts["raw:line:2"]["execution_entity_usage_admission"] == (
        "invocation_prelaunch_failure_observed"
    )
    assert contexts["raw:line:2"]["correlation_id"] == (
        "call-script-prelaunch-failure"
    )
    assert contexts["raw:line:2"]["usage_actions"] == ["requested", "failed"]
    assert contexts["raw:line:12"]["execution_entity_usage_admission"] == (
        "inspection_or_reference_not_invocation"
    )
    assert contexts["raw:line:12"]["usage_actions"] == ["referenced"]
    assert chain["quality"]["execution_usage_invocation_admission_applied"] is True
    assert chain["quality"]["execution_usage_invocation_admission_kind"] == "script"
    assert chain["quality"]["execution_usage_invocation_admitted_count"] == 4
    assert chain["quality"]["execution_usage_prelaunch_failure_rejected_count"] == 1
    assert chain["quality"]["execution_usage_reference_rejected_count"] == 1
    assert "script_invocation_prelaunch_failure_observed" in chain["noise_flags"]
def test_entity_usage_script_admission_tracks_env_path_async_process_and_rejects_reference(
    tmp_path: Path,
) -> None:
    """Regression derived from a sealed raw-first process-session script case."""
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-07-18T01-00-00-path-script-async.jsonl"
    command = (
        "PYTHONDONTWRITEBYTECODE=1 "
        "tools/abyss-machine-test quick --json"
    )
    write_jsonl(
        transcript,
        [
            {
                "timestamp": "2026-07-18T01:00:00Z",
                "type": "session_meta",
                "payload": {"id": "path-script-async", "cwd": str(workspace)},
            },
            {
                "timestamp": "2026-07-18T01:00:01Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "exec_command",
                    "call_id": "call-path-script",
                    "arguments": json.dumps({"cmd": command}),
                },
            },
            {
                "timestamp": "2026-07-18T01:00:02Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "call-path-script",
                    "output": (
                        "Chunk ID: running\nWall time: 30.0 seconds\n"
                        "Process running with session ID 16410\nOutput:\n"
                    ),
                },
            },
            {
                "timestamp": "2026-07-18T01:00:03Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "write_stdin",
                    "call_id": "call-wrong-process",
                    "arguments": json.dumps(
                        {"session_id": 99999, "chars": ""}
                    ),
                },
            },
            {
                "timestamp": "2026-07-18T01:00:04Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "call-wrong-process",
                    "output": (
                        "Process exited with code 0\n"
                        "Output:\nforeign success\n"
                    ),
                },
            },
            {
                "timestamp": "2026-07-18T01:00:05Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "write_stdin",
                    "call_id": "call-path-script-poll",
                    "arguments": json.dumps(
                        {"session_id": 16410, "chars": ""}
                    ),
                },
            },
            {
                "timestamp": "2026-07-18T01:00:06Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "call-path-script-poll",
                    "output": (
                        "Chunk ID: done\nWall time: 0.2 seconds\n"
                        "Process exited with code 0\nOutput:\n"
                        '{"ok":true,"returncode":0,"stdout":"196 passed"}\n'
                    ),
                },
            },
            {
                "timestamp": "2026-07-18T01:00:07Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "exec_command",
                    "call_id": "call-path-script-reference",
                    "arguments": json.dumps(
                        {
                            "cmd": (
                                "test -f tools/abyss-machine-test "
                                "&& echo present"
                            )
                        }
                    ),
                },
            },
            {
                "timestamp": "2026-07-18T01:00:08Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "call-path-script-reference",
                    "output": "present\n",
                },
            },
        ],
    )

    receipt = module.handle_hook_event(
        "Stop",
        {
            "session_id": "path-script-async",
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

    shape = module.literal_query_shape(command)
    assert shape["signals"][:2] == ["command", "path"]
    assert shape["primary"] == "command"
    assert shape["command_anchor"] == "tools/abyss-machine-test"
    assert shape["path_anchor"] == "tools/abyss-machine-test"
    assert module.literal_query_shape("tools/abyss-machine-test")["primary"] == (
        "path"
    )
    assert module.literal_query_shape(
        "test -f tools/abyss-machine-test && echo present"
    )["primary"] == "path"
    assert module.entity_usage_execution_command_proves_invocation(
        command,
        anchor="tools/abyss-machine-test",
        kind="script",
    )
    assert not module.entity_usage_execution_command_proves_invocation(
        "test -f tools/abyss-machine-test && echo present",
        anchor="tools/abyss-machine-test",
        kind="script",
    )

    chain = module.entity_usage_chain(
        aoa_root=aoa_root,
        anchor="tools/abyss-machine-test",
        kind="script",
        session="path-script-async",
        limit=8,
        per_route_limit=12,
        consequence_window=8,
    )

    assert chain["ok"] is True
    assert chain["counts"]["usage_event_count"] == 1
    assert chain["counts"]["async_completed_chain_count"] == 1
    assert chain["quality"]["execution_usage_invocation_admitted_count"] == 1
    assert chain["quality"]["execution_usage_reference_rejected_count"] == 1
    usage_chain = chain["usage_chain"]["chains"][0]
    assert usage_chain["usage_event"]["refs"]["raw"] == "raw:line:2"
    assert usage_chain["usage_event"]["execution_entity_usage_admission"] == (
        "structured_command_invocation_proven"
    )
    linked = {
        event["refs"]["raw"]: event
        for event in usage_chain["result_or_consequence_events"]
    }
    assert set(linked) == {"raw:line:3", "raw:line:6", "raw:line:7"}
    assert linked["raw:line:3"]["role"] == "result"
    assert linked["raw:line:6"]["relation"] == "async_process_session_id"
    assert linked["raw:line:7"]["relation"] == "async_wait_result"
    assert linked["raw:line:7"]["role"] == "result"
    assert all(
        event["refs"]["raw"] != "raw:line:5"
        for event in usage_chain["result_or_consequence_events"]
    )
    contexts = {
        event["refs"]["raw"]: event
        for event in chain["usage_chain"]["context_events"]
    }
    assert contexts["raw:line:8"]["execution_entity_usage_admission"] == (
        "inspection_or_reference_not_invocation"
    )
    assert contexts["raw:line:8"]["usage_actions"] == ["referenced"]
def test_entity_usage_tool_result_admission_distinguishes_structured_timeout(
    tmp_path: Path,
) -> None:
    """Regression from a randomized raw-first wait-agent timeout."""
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-07-18T00-10-00-tool-timeout.jsonl"
    write_jsonl(
        transcript,
        [
            {
                "timestamp": "2026-07-18T00:10:00Z",
                "type": "session_meta",
                "payload": {"id": "tool-timeout", "cwd": str(workspace)},
            },
            {
                "timestamp": "2026-07-18T00:10:01Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "wait_agent",
                    "arguments": json.dumps({"timeout_ms": 10000}),
                    "call_id": "call_timeout_123456789",
                },
            },
            {
                "timestamp": "2026-07-18T00:10:02Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "call-foreign",
                    "output": json.dumps(
                        {
                            "message": "Foreign timeout.",
                            "timed_out": True,
                        }
                    ),
                },
            },
            {
                "timestamp": "2026-07-18T00:10:03Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "call_timeout_123456789",
                    "output": json.dumps(
                        {
                            "message": "Wait timed out.",
                            "timed_out": True,
                        }
                    ),
                },
            },
            {
                "timestamp": "2026-07-18T00:10:04Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "wait_agent",
                    "arguments": json.dumps({"timeout_ms": 10000}),
                    "call_id": "call-observed",
                },
            },
            {
                "timestamp": "2026-07-18T00:10:05Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "call-observed",
                    "output": json.dumps(
                        {
                            "message": (
                                'Mailbox update; documentation example: '
                                '{"timed_out": true}'
                            ),
                            "timed_out": False,
                        }
                    ),
                },
            },
            {
                "timestamp": "2026-07-18T00:10:06Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "exec_command",
                    "arguments": json.dumps(
                        {"cmd": "printf '%s\\n' '{\"timed_out\": true}'"}
                    ),
                    "call_id": "call-json-document",
                },
            },
            {
                "timestamp": "2026-07-18T00:10:07Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "call-json-document",
                    "output": json.dumps({"timed_out": True}),
                },
            },
        ],
    )

    receipt = module.handle_hook_event(
        "Stop",
        {
            "session_id": "tool-timeout",
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

    chain = module.entity_usage_chain(
        aoa_root=aoa_root,
        anchor="wait_agent",
        kind="tool",
        session="tool-timeout",
        limit=8,
        per_route_limit=12,
        consequence_window=2,
    )

    assert chain["ok"] is True
    assert chain["counts"]["usage_event_count"] == 2
    chains_by_raw = {
        item["usage_event"]["refs"]["raw"]: item
        for item in chain["usage_chain"]["chains"]
    }
    timeout_result = chains_by_raw["raw:line:2"][
        "result_or_consequence_events"
    ][0]
    observed_result = chains_by_raw["raw:line:5"][
        "result_or_consequence_events"
    ][0]
    assert timeout_result["refs"]["raw"] == "raw:line:4"
    assert timeout_result["relation"] == "same_correlation_id"
    assert timeout_result["result_status"] == "timed_out"
    assert timeout_result["result_status_basis"] == (
        "source_verified_output_json_timed_out_true"
    )
    assert timeout_result["outcome"] == "failed"
    assert timeout_result["usage_actions"] == ["timed_out", "failed"]
    assert observed_result["refs"]["raw"] == "raw:line:6"
    assert observed_result["result_status"] == "observed"
    assert observed_result["result_status_basis"] == (
        "source_verified_output_json_timed_out_false"
    )
    assert observed_result["outcome"] == "observed"
    assert observed_result["usage_actions"] == ["observed"]
    assert chain["quality"]["causal_admission"][
        "structured_result_status_admitted_count"
    ] == 2
    assert chain["quality"]["causal_admission"][
        "structured_result_timeout_count"
    ] == 1
    assert chain["counts"]["false_correlation_event_count"] == 1
    false_correlation = chain["usage_chain"]["false_correlation_events"][0]
    assert false_correlation["refs"]["raw"] == "raw:line:3"
    assert false_correlation["rejected_correlation_id"] == "call-foreign"

    document_chain = module.entity_usage_chain(
        aoa_root=aoa_root,
        anchor="exec_command",
        kind="tool",
        session="tool-timeout",
        limit=8,
        per_route_limit=12,
        consequence_window=2,
    )
    document_result = document_chain["usage_chain"]["chains"][0][
        "result_or_consequence_events"
    ][0]
    assert document_result["refs"]["raw"] == "raw:line:8"
    assert document_result["result_status"] is None
    assert document_result["outcome"] == "observed"
    assert document_result["usage_actions"] == ["observed"]

    record = module.resolve_session_record(aoa_root, "tool-timeout")
    session_dir = Path(record["path"])
    manifest = json.loads(
        (session_dir / "session.manifest.json").read_text(encoding="utf-8")
    )
    window = module.raw_evidence_window_from_session(
        session_dir=session_dir,
        manifest=manifest,
        raw_ref="raw:line:2",
        before=0,
        after=6,
    )
    window_by_raw = {
        event["refs"]["raw"]: event
        for event in window["events"]
    }
    assert window_by_raw["raw:line:4"]["result_status"] == "timed_out"
    assert window_by_raw["raw:line:4"]["result_status_basis"] == (
        "source_verified_output_json_timed_out_true"
    )
    assert window_by_raw["raw:line:4"]["result_status_tool"] == "wait_agent"
    assert window_by_raw["raw:line:6"]["result_status"] == "observed"
    assert window_by_raw["raw:line:6"]["result_status_basis"] == (
        "source_verified_output_json_timed_out_false"
    )
    assert window_by_raw["raw:line:8"]["result_status"] == "observed"
    assert window_by_raw["raw:line:8"]["result_status_basis"] == (
        "structured_result_without_outcome"
    )

    timeline = module.graph_source_verified_correlation_timeline(
        aoa_root=aoa_root,
        anchor="call_timeout_123456789",
        kind="auto",
        limit=8,
    )
    assert timeline is not None
    timeline_by_raw = {
        node["refs"]["raw"]: node
        for node in timeline["nodes"]
    }
    assert timeline["source"] == "source_verified_correlation_trace"
    assert timeline_by_raw["raw:line:4"]["result_status"] == "timed_out"
    assert timeline_by_raw["raw:line:4"]["result_status_basis"] == (
        "source_verified_output_json_timed_out_true"
    )
    assert timeline_by_raw["raw:line:4"]["result_status_tool"] == "wait_agent"
    assert timeline_by_raw["raw:line:4"]["outcome"] == "failed"
    assert timeline["quality"]["structured_result_status_admitted_count"] == 1
    assert timeline["quality"]["structured_result_timeout_count"] == 1
