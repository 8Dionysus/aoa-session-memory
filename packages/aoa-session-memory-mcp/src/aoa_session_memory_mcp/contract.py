from __future__ import annotations

from pathlib import Path
from typing import Any


ROOT_DISCOVERY_CONTRACT: dict[str, Any] = {
    "schema": "aoa_session_memory_root_discovery_v1",
    "precedence": [
        "explicit CLI argument",
        "explicit environment variable",
        "marker-valid standalone repository root",
        "marker-valid workspace/.aoa root",
        "actionable failure",
    ],
    "environment": {
        "workspace_root": "AOA_WORKSPACE_ROOT",
        "session_memory_root": "AOA_SESSION_MEMORY_ROOT",
        "script_path": "AOA_SESSION_MEMORY_SCRIPT",
    },
    "standalone_markers": [
        "scripts/aoa_session_memory.py",
        "config/search-providers.json",
        "schemas/session.manifest.schema.json",
    ],
    "workspace_markers": [
        ".aoa/scripts/aoa_session_memory.py",
        ".aoa/config/search-providers.json",
        ".aoa/schemas/session.manifest.schema.json",
    ],
    "conflict_posture": "conflicting explicit session-memory and workspace roots fail closed",
    "symlink_posture": "resolve roots before marker validation and report the resolved path",
    "host_specific_default": None,
}


def _model_payload(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(by_alias=True, exclude_none=False)
    if hasattr(value, "dict"):
        return value.dict(by_alias=True, exclude_none=False)
    return value


def surface_catalog(server: Any | None = None) -> dict[str, Any]:
    if server is None:
        from .server import build_server

        server = build_server()

    tools = []
    for item in server._tool_manager._tools.values():
        tools.append(
            {
                "name": item.name,
                "description": item.description or "",
                "input_schema": item.parameters,
                "annotations": _model_payload(item.annotations),
            }
        )

    resources = []
    for item in server._resource_manager._resources.values():
        resources.append(
            {
                "uri": str(item.uri),
                "name": item.name,
                "description": item.description or "",
                "mime_type": item.mime_type,
            }
        )

    templates = []
    for item in server._resource_manager._templates.values():
        templates.append(
            {
                "uri_template": str(item.uri_template),
                "name": item.name,
                "description": item.description or "",
                "mime_type": item.mime_type,
                "input_schema": item.parameters,
            }
        )

    prompts = []
    for item in server._prompt_manager._prompts.values():
        prompts.append(
            {
                "name": item.name,
                "description": item.description or "",
                "arguments": [_model_payload(argument) for argument in item.arguments or []],
            }
        )

    return {
        "schema": "aoa_session_memory_mcp_surface_catalog_v1",
        "tools": sorted(tools, key=lambda entry: entry["name"]),
        "resources": sorted(resources, key=lambda entry: entry["uri"]),
        "resource_templates": sorted(templates, key=lambda entry: entry["uri_template"]),
        "prompts": sorted(prompts, key=lambda entry: entry["name"]),
    }


def export_contract() -> dict[str, Any]:
    from .core import AoASessionMemoryMCPState

    inert = Path("/")
    state = AoASessionMemoryMCPState(
        workspace_root=inert,
        aoa_root=inert,
        script_path=inert / "aoa_session_memory.py",
    )
    return {
        "schema": "aoa_session_memory_mcp_export_contract_v1",
        "root_discovery": ROOT_DISCOVERY_CONTRACT,
        "authority_boundary": state.authority_boundary(),
        "mcp_surface": surface_catalog(),
    }
