#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from aoa_session_memory_mcp.core import AoASessionMemoryMCPState, RootDiscoveryError


ROOT_ENV_KEYS = ("AOA_WORKSPACE_ROOT", "AOA_SESSION_MEMORY_ROOT", "AOA_SESSION_MEMORY_SCRIPT")
HTTP_ENV_KEYS = ("AOA_MCP_HTTP_BEARER_TOKEN", "CREDENTIALS_DIRECTORY")


@contextmanager
def patched_environment(values: dict[str, str | None]) -> Iterator[None]:
    previous = {key: os.environ.get(key) for key in values}
    try:
        for key, value in values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def snapshot(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
            continue
        result[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def run(argv: list[str], *, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=120,
    )


def record(cases: list[dict[str, Any]], name: str, **signals: Any) -> None:
    cases.append({"name": name, "ok": True, "signals": signals})


def require(condition: bool, name: str) -> None:
    if not condition:
        raise RuntimeError(name)


async def unavailable_http_probe(port: int) -> bool:
    token = "negative-matrix-" + "a" * 48
    try:
        async with httpx.AsyncClient(
            headers={"Authorization": f"Bearer {token}"},
            timeout=1.0,
        ) as client:
            async with streamable_http_client(
                f"http://127.0.0.1:{port}/mcp",
                http_client=client,
            ) as (read_stream, write_stream, _get_session_id):
                async with ClientSession(read_stream, write_stream) as session:
                    await asyncio.wait_for(session.initialize(), timeout=2.0)
                    return False
    except Exception:
        return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Run installed-package standalone negative cases without live state")
    parser.add_argument("--workspace-root", type=Path, required=True)
    parser.add_argument("--scratch-root", type=Path, required=True)
    parser.add_argument("--server-command", type=Path, default=Path(sys.executable).parent / "aoa-session-memory-mcp-server")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    package_root = repo_root / "packages" / "aoa-session-memory-mcp"
    validator = package_root / "scripts" / "validate_package_projection.py"
    bootstrap = repo_root / "examples" / "synthetic" / "bootstrap_demo.py"
    workspace = args.workspace_root.expanduser().resolve()
    archive = workspace / ".aoa"
    scratch = args.scratch_root.expanduser().resolve()
    scratch.mkdir(parents=True, exist_ok=True)
    require(archive.is_dir(), "synthetic archive missing")
    require(args.server_command.is_file(), "installed server command missing")

    before = snapshot(archive)
    cases: list[dict[str, Any]] = []
    clean_path = f"{Path(sys.executable).parent}:/usr/bin:/bin"
    clean_env = {**os.environ, "PATH": clean_path, "PYTHONDONTWRITEBYTECODE": "1"}
    for key in (*ROOT_ENV_KEYS, *HTTP_ENV_KEYS):
        clean_env.pop(key, None)

    try:
        with tempfile.TemporaryDirectory(prefix="negative-matrix-", dir=scratch) as raw_temp:
            temp = Path(raw_temp)

            empty = temp / "empty"
            empty.mkdir()
            with patched_environment({key: None for key in ROOT_ENV_KEYS}):
                try:
                    AoASessionMemoryMCPState.discover(cwd=empty)
                except RootDiscoveryError as exc:
                    detail = str(exc)
                    require("marker-valid" in detail and "--aoa-root" in detail, "missing-root diagnostic")
                else:
                    raise RuntimeError("missing root was accepted")
            record(cases, "missing_root", actionable=True)

            invalid = temp / "invalid root"
            (invalid / "scripts").mkdir(parents=True)
            (invalid / "scripts" / "aoa_session_memory.py").write_text("#!/usr/bin/env python3\n", encoding="utf-8")
            try:
                AoASessionMemoryMCPState.discover(aoa_root=invalid)
            except RootDiscoveryError as exc:
                require("search-providers.json" in str(exc), "invalid-root diagnostic")
            else:
                raise RuntimeError("invalid root was accepted")
            record(cases, "invalid_root", marker_validation=True)

            nested = workspace / "nested directory" / "ещё глубже"
            nested.mkdir(parents=True, exist_ok=True)
            with patched_environment({key: None for key in ROOT_ENV_KEYS}):
                discovered = AoASessionMemoryMCPState.discover(cwd=nested)
            require(discovered.aoa_root == archive.resolve(), "cwd discovery selected wrong root")
            record(cases, "space_unicode_different_cwd", discovery_source=discovered.discovery_source)

            explicit = AoASessionMemoryMCPState.discover(aoa_root=archive)
            require(explicit.aoa_root == archive.resolve(), "explicit root selected wrong root")
            record(cases, "explicit_root", discovery_source=explicit.discovery_source)

            linked = temp / "linked root"
            linked.symlink_to(archive, target_is_directory=True)
            linked_state = AoASessionMemoryMCPState.discover(aoa_root=linked)
            require(linked_state.aoa_root == archive.resolve(), "symlink root did not resolve")
            record(cases, "symlink_root", resolved=True)

            other = temp / "other root"
            shutil.copytree(archive, other)
            with patched_environment(
                {
                    "AOA_WORKSPACE_ROOT": workspace.as_posix(),
                    "AOA_SESSION_MEMORY_ROOT": other.as_posix(),
                    "AOA_SESSION_MEMORY_SCRIPT": None,
                }
            ):
                try:
                    AoASessionMemoryMCPState.discover()
                except RootDiscoveryError as exc:
                    require("conflicting explicit environment roots" in str(exc), "conflicting-root diagnostic")
                else:
                    raise RuntimeError("conflicting environment roots were accepted")
            record(cases, "conflicting_environment_roots", fail_closed=True)

            with patched_environment({"PATH": clean_path, **{key: None for key in ROOT_ENV_KEYS}}):
                require(shutil.which("abyss-machine") is None, "abyss-machine unexpectedly present in clean PATH")
                status = AoASessionMemoryMCPState.discover(workspace_root=workspace).session_memory_status(include_live=False)
            require(status.get("authority_boundary", {}).get("mcp_role"), "standalone status missing authority boundary")
            record(cases, "host_runtime_absent", standalone_status=True)

            provider_config = json.loads((archive / "config" / "search-providers.json").read_text(encoding="utf-8"))
            providers = provider_config.get("providers", {})
            require(providers.get("portable_sqlite", {}).get("enabled") is True, "portable provider disabled")
            require(providers.get("abyss_machine_nervous", {}).get("enabled") is False, "optional provider enabled")
            require(providers.get("abyss_stack_rag", {}).get("enabled") is False, "future provider enabled")
            record(cases, "optional_providers_disabled", portable_route_available=True)

            state = AoASessionMemoryMCPState.discover(workspace_root=workspace)
            missing_proc = temp / "no-proc"

            malformed_home = temp / "codex malformed"
            malformed_home.mkdir()
            (malformed_home / "config.toml").write_text("[mcp_servers.aoa_session_memory\n", encoding="utf-8")
            with patched_environment({"CODEX_HOME": malformed_home.as_posix(), **{key: None for key in HTTP_ENV_KEYS}}):
                malformed = state.session_mcp_transport_preflight(proc_root=missing_proc)
            diagnostics = malformed["configured_server"].get("diagnostics", [])
            require(diagnostics and str(diagnostics[0]).startswith("config_read_error:"), "malformed config accepted")
            record(cases, "malformed_codex_config", configured=False)

            nonloopback_home = temp / "codex nonloopback"
            nonloopback_home.mkdir()
            (nonloopback_home / "config.toml").write_text(
                "[mcp_servers.aoa_session_memory]\n"
                'url = "http://192.0.2.1:5422/mcp"\n'
                'bearer_token_env_var = "AOA_MCP_HTTP_BEARER_TOKEN"\n',
                encoding="utf-8",
            )
            with patched_environment({"CODEX_HOME": nonloopback_home.as_posix(), **{key: None for key in HTTP_ENV_KEYS}}):
                nonloopback = state.session_mcp_transport_preflight(proc_root=missing_proc)
            require(
                nonloopback["configured_server"].get("diagnostics") == ["http_endpoint_must_be_loopback_mcp"],
                "nonloopback HTTP endpoint accepted",
            )
            record(cases, "nonloopback_http_config", fail_closed=True)

            no_bearer_home = temp / "codex no bearer"
            no_bearer_home.mkdir()
            (no_bearer_home / "config.toml").write_text(
                "[mcp_servers.aoa_session_memory]\n"
                'url = "http://127.0.0.1:5422/mcp"\n'
                'bearer_token_env_var = "AOA_MCP_HTTP_BEARER_TOKEN"\n',
                encoding="utf-8",
            )
            with patched_environment({"CODEX_HOME": no_bearer_home.as_posix(), **{key: None for key in HTTP_ENV_KEYS}}):
                no_bearer = state.session_mcp_transport_preflight(proc_root=missing_proc)
            require(no_bearer.get("direct_tool_transport_status") == "http_auth_unavailable", "missing bearer accepted")
            require(
                no_bearer["configured_server"].get("diagnostics") == ["http_client_credential_unavailable"],
                "missing bearer diagnostic",
            )
            record(cases, "http_client_bearer_absent", auth_ready=False)

            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as unavailable_socket:
                unavailable_socket.bind(("127.0.0.1", 0))
                unavailable_port = int(unavailable_socket.getsockname()[1])
                refused = asyncio.run(unavailable_http_probe(unavailable_port))
            require(refused, "unavailable HTTP transport unexpectedly connected")
            record(cases, "unavailable_loopback_http", connection_refused=True)

            server_result = run(
                [args.server_command.as_posix(), "--workspace-root", workspace.as_posix()],
                cwd=temp,
                env={**clean_env, "AOA_MCP_TRANSPORT": "streamable-http"},
            )
            require(server_result.returncode != 0, "HTTP server started without bearer")
            require("requires bearer authentication" in server_result.stderr, "HTTP server bearer diagnostic")
            record(cases, "http_server_bearer_absent", refused=True)

            invalid_transport = run(
                [args.server_command.as_posix(), "--workspace-root", workspace.as_posix()],
                cwd=temp,
                env={**clean_env, "AOA_MCP_TRANSPORT": "invalid-transport"},
            )
            require(invalid_transport.returncode != 0, "invalid transport accepted")
            require("unsupported AOA_MCP_TRANSPORT" in invalid_transport.stderr, "invalid transport diagnostic")
            record(cases, "unsupported_transport", refused=True)

            drifted_package = temp / "drifted package"
            shutil.copytree(package_root, drifted_package)
            with (drifted_package / "README.md").open("a", encoding="utf-8") as handle:
                handle.write("\nprojection drift fixture\n")
            drift = run(
                [sys.executable, validator.as_posix(), "--package-root", drifted_package.as_posix()],
                cwd=repo_root,
                env=clean_env,
            )
            require(drift.returncode == 1, "package manifest drift accepted")
            drift_payload = json.loads(drift.stdout)
            require(
                any("manifest digest mismatch: README.md" in item for item in drift_payload.get("errors", [])),
                "package drift diagnostic",
            )
            record(cases, "package_manifest_drift", refused=True)

            stale_workspace = temp / "stale synthetic workspace"
            stale_bootstrap = run(
                [sys.executable, bootstrap.as_posix(), "--destination", stale_workspace.as_posix()],
                cwd=repo_root,
                env=clean_env,
            )
            require(stale_bootstrap.returncode == 0, "stale-case bootstrap failed")
            raw_files = list((stale_workspace / ".aoa" / "sessions").glob("*/raw/session.raw.jsonl"))
            require(len(raw_files) == 1, "stale-case raw fixture count")
            with raw_files[0].open("a", encoding="utf-8") as handle:
                handle.write("{}\n")
            stale_state = AoASessionMemoryMCPState.discover(workspace_root=stale_workspace)
            stale = stale_state.session_freshness_check(["raw:line:17"], session="latest")
            require(stale.get("ok") is False, "stale projection admitted")
            require(stale.get("projection_freshness", {}).get("status") == "stale", "stale projection not exposed")
            record(cases, "stale_projection", freshness="stale", answer_admitted=False)

        after = snapshot(archive)
        require(before == after, "negative matrix changed the primary synthetic archive")
        result = {
            "schema": "aoa_session_memory_installed_negative_matrix_v1",
            "ok": True,
            "case_count": len(cases),
            "cases": cases,
            "primary_archive_unchanged": True,
            "value_exposure": "case names and bounded boolean/status signals only",
        }
    except Exception as exc:
        result = {
            "schema": "aoa_session_memory_installed_negative_matrix_v1",
            "ok": False,
            "completed_case_count": len(cases),
            "error_class": type(exc).__name__,
            "value_exposure": "exception class only",
        }

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
