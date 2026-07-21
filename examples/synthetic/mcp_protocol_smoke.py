#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


MUTATION_TOKENS = ("_apply", "_distill", "_export", "_install", "_promote", "_reindex", "_relabel", "_repair", "_write")


def default_server_command() -> str:
    installed = Path(sys.executable).parent / "aoa-session-memory-mcp-server"
    return installed.as_posix() if installed.is_file() else "aoa-session-memory-mcp-server"


def tree_snapshot(root: Path) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if "__pycache__" in relative.parts or path.suffix in {".pyc", ".pyo"}:
            continue
        snapshot[relative.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return snapshot


def payload(result: Any) -> dict[str, Any]:
    if result.isError:
        raise RuntimeError(f"MCP tool returned an error: {result.content}")
    if not result.content or not hasattr(result.content[0], "text"):
        raise RuntimeError("MCP tool returned no JSON text content")
    parsed = json.loads(result.content[0].text)
    if not isinstance(parsed, dict):
        raise RuntimeError("MCP tool returned non-object JSON")
    return parsed


def open_evidence_refs(search: dict[str, Any]) -> dict[str, str | int]:
    for result in search.get("results", []):
        refs = result.get("refs") if isinstance(result, dict) else None
        if not isinstance(refs, dict) or not refs.get("raw") or not refs.get("session"):
            continue
        raw_ref = str(refs["raw"])
        line = int(raw_ref.rsplit(":", 1)[-1])
        raw_path = Path(str(refs["session"])).parent / "raw" / "session.raw.jsonl"
        raw_line = raw_path.read_text(encoding="utf-8").splitlines()[line - 1]
        segment_ref = str(refs.get("segment") or "")
        segment_name, _separator, segment_anchor = segment_ref.partition("#")
        segment_path = Path(str(refs["session"])).parent / "segments" / segment_name
        if not segment_name or not segment_path.is_file():
            continue
        segment_text = segment_path.read_text(encoding="utf-8")
        if segment_anchor and f'id="{segment_anchor}"' not in segment_text:
            continue
        return {
            "raw_ref": raw_ref,
            "raw_line": line,
            "raw_path": raw_path.as_posix(),
            "raw_line_sha256": hashlib.sha256(raw_line.encode("utf-8")).hexdigest(),
            "segment_ref": segment_ref,
            "segment_sha256": hashlib.sha256(segment_text.encode("utf-8")).hexdigest(),
        }
    raise RuntimeError("search returned no resolvable raw and segment refs")


async def run(args: argparse.Namespace) -> dict[str, Any]:
    workspace_root = args.workspace_root.expanduser().resolve()
    aoa_root = workspace_root / ".aoa"
    before = tree_snapshot(aoa_root)
    env = dict(os.environ)
    for key in ("AOA_WORKSPACE_ROOT", "AOA_SESSION_MEMORY_ROOT", "AOA_SESSION_MEMORY_SCRIPT"):
        env.pop(key, None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    params = StdioServerParameters(
        command=args.server_command,
        args=["--workspace-root", workspace_root.as_posix()],
        cwd=args.cwd.expanduser().resolve().as_posix(),
        env=env,
    )
    timeout = timedelta(seconds=args.timeout)
    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            initialized = await session.initialize()
            tools = (await session.list_tools()).tools
            resources = (await session.list_resources()).resources
            templates = (await session.list_resource_templates()).resourceTemplates
            prompts = (await session.list_prompts()).prompts

            for tool in tools:
                annotations = tool.annotations
                if annotations is None or not (
                    annotations.readOnlyHint is True
                    and annotations.destructiveHint is False
                    and annotations.idempotentHint is True
                    and annotations.openWorldHint is False
                ):
                    raise RuntimeError(f"unsafe or missing annotations: {tool.name}")
                if any(token in tool.name.casefold() for token in MUTATION_TOKENS):
                    raise RuntimeError(f"unexpected mutation tool: {tool.name}")

            search = payload(
                await session.call_tool(
                    "aoa_session_search",
                    {"query": "DEMO-ANCHOR-42", "limit": 5},
                    read_timeout_seconds=timeout,
                )
            )
            usage = payload(
                await session.call_tool(
                    "aoa_session_entity_usage_chain",
                    {"anchor": "query_component", "kind": "mcp_tool", "limit": 4, "per_route_limit": 6},
                    read_timeout_seconds=timeout,
                )
            )
            episodes = payload(
                await session.call_tool(
                    "aoa_session_task_episodes",
                    {"target": "latest", "limit": 5},
                    read_timeout_seconds=timeout,
                )
            )
            graph = payload(
                await session.call_tool(
                    "aoa_session_graph_neighborhood",
                    {"anchor": "synthetic-catalog-mcp", "kind": "mcp", "limit": 12},
                    read_timeout_seconds=timeout,
                )
            )
            opened = open_evidence_refs(search)
            freshness = payload(
                await session.call_tool(
                    "aoa_session_freshness_check",
                    {"refs": [opened["raw_ref"]], "session": "latest"},
                    read_timeout_seconds=timeout,
                )
            )
            missing = payload(
                await session.call_tool(
                    "aoa_session_freshness_check",
                    {"refs": ["raw:line:9999"], "session": "latest"},
                    read_timeout_seconds=timeout,
                )
            )
            candidate = payload(
                await session.call_tool(
                    "aoa_session_evidence_packet",
                    {
                        "intent": "prove that DEMO-ANCHOR-42 caused the recovery",
                        "query": "DEMO-ANCHOR-42",
                        "anchors": ["DEMO-ANCHOR-42"],
                        "limit": 4,
                    },
                    read_timeout_seconds=timeout,
                )
            )

    after = tree_snapshot(aoa_root)
    if before != after:
        raise RuntimeError("read-only MCP smoke changed the synthetic archive tree")
    if (
        search.get("result_count", 0) < 1
        or usage.get("ok") is not True
        or episodes.get("ok") is not True
        or episodes.get("result_count", 0) < 1
    ):
        raise RuntimeError("exact, usage, or episode route returned no usable packet")
    if graph.get("ok") is not True or not graph.get("evidence_refs") or graph.get("edge_count", 0) < 1:
        raise RuntimeError("graph route returned no relation edge or evidence refs")
    if freshness.get("ok") is not True or missing.get("ok") is not False:
        raise RuntimeError("freshness positive or missing-evidence negative case failed")
    authority = candidate.get("authority_boundary")
    candidate_posture = str(candidate.get("candidate_posture") or "")
    if (
        not authority
        or "truth" not in json.dumps(authority).casefold()
        or "not a verdict" not in candidate_posture
    ):
        raise RuntimeError("causal-claim packet did not preserve candidate-only authority")

    return {
        "schema": "aoa_session_memory_synthetic_mcp_smoke_v1",
        "ok": True,
        "protocol_version": str(initialized.protocolVersion),
        "catalog": {
            "tools": len(tools),
            "resources": len(resources),
            "resource_templates": len(templates),
            "prompts": len(prompts),
        },
        "routes": {
            "exact_result_count": search.get("result_count"),
            "usage_ok": usage.get("ok"),
            "episode_count": episodes.get("result_count"),
            "graph_node_count": graph.get("node_count"),
            "graph_edge_count": graph.get("edge_count"),
            "graph_evidence_ref_count": graph.get("evidence_ref_count"),
            "freshness": freshness.get("projection_freshness", {}).get("status"),
            "missing_evidence_ok": missing.get("ok"),
            "causal_claim_posture": candidate_posture,
        },
        "opened_evidence": opened,
        "archive_unchanged": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a real stdio MCP handshake and synthetic evidence-route smoke")
    parser.add_argument("--workspace-root", type=Path, required=True)
    parser.add_argument("--server-command", default=default_server_command())
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()
    result = asyncio.run(run(args))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
