from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "aoa_session_memory.py"
)
spec = importlib.util.spec_from_file_location(
    "aoa_session_memory_projection_outbox_reconcile",
    SCRIPT,
)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _fixture(tmp_path: Path) -> dict[str, Any]:
    aoa_root = tmp_path / "aoa"
    session_id = "019f82f8-5192-7093-8811-df034572e9c7"
    session_dir = aoa_root / "sessions" / session_id
    session_dir.mkdir(parents=True)
    publish_id = "b" * 64
    module.write_json(
        session_dir / "session.manifest.json",
        {
            "session_id": session_id,
            "index_schema": {"projection_publish": {"publish_id": publish_id}},
        },
    )
    record = module.session_projection_outbox_record(
        session_dir=session_dir,
        old_snapshot={},
        new_snapshot={
            "component:one": {
                "component_type": "unknown",
                "digest": "d" * 64,
                "source_ref": "tests/projection/component-one",
                "generation_identity": {"generation_id": "generation-one"},
            }
        },
        old_publish_id="a" * 64,
        new_publish_id=publish_id,
        session_id=session_id,
    )
    module.write_projection_outbox_record(session_dir, record)
    fixture = {
        "aoa_root": aoa_root,
        "session_dir": session_dir,
        "session_id": session_id,
        "publish_id": publish_id,
        "record": record,
        "record_id": str(record["record_id"]),
    }
    _seed_owner_search_sources(fixture)
    return fixture


def _authority_generation_id(consumer: str) -> str:
    return f"{consumer}-generation-one"


def _authority_payload(
    fixture: dict[str, Any],
    context: dict[str, Any],
    consumer: str,
) -> dict[str, Any]:
    generation_id = _authority_generation_id(consumer)
    authority = {
        "schema_version": module.PROJECTION_OUTBOX_CONSUMER_AUTHORITY_SCHEMA_VERSION,
        "artifact_type": module._projection_outbox_authority_artifact_type(consumer),
        "status": (
            "committed"
            if consumer in {"exact_and_lexical_search", "graph"}
            else "current"
        ),
        "truth_status": "owner_authoritative_consumer_artifact_not_handler_output",
        "consumer": consumer,
        "session_id": fixture["session_id"],
        "record_id": fixture["record_id"],
        "publish_id": fixture["publish_id"],
        "operation": module.PROJECTION_OUTBOX_CONSUMER_OPERATION,
        "operation_key": context["operation_key"],
        "attempt": context["attempt"],
        "authority_key": module._projection_outbox_authority_key(
            consumer=consumer,
            session_id=fixture["session_id"],
            record_id=fixture["record_id"],
            publish_id=fixture["publish_id"],
            operation_key=context["operation_key"],
            attempt=context["attempt"],
        ),
        "generation_id": generation_id,
        "generation_identity": {
            "generation_id": generation_id,
            "publish_id": fixture["publish_id"],
            "owner": "aoa-session-memory",
        },
        "changed_component_digests": module._projection_outbox_expected_changed_component_digests(
            fixture["record"],
            consumer,
        ),
        "source_ref": module._projection_outbox_authority_source_ref(consumer),
        "owner_provenance": {
            "owner_repo": module.PROJECTION_OUTBOX_CONSUMER_AUTHORITY_OWNER_REPO,
            "source_ref": module._projection_outbox_authority_source_ref(consumer),
            "authority_kind": module._projection_outbox_authority_artifact_type(consumer),
            "authority_version": module.PROJECTION_OUTBOX_CONSUMER_AUTHORITY_SCHEMA_VERSION,
        },
        "source_keys": [f"session:{fixture['session_id']}"] if consumer == "graph" else [],
        "mutation_id": "graph-mutation-one" if consumer == "graph" else "",
        "source_ledger_ref": "graph/source-state-ledger.json" if consumer == "graph" else "",
        "committed_at": "2026-08-23T00:00:00Z",
    }
    authority["authority_sha256"] = module._projection_outbox_authority_digest(authority)
    return authority


def _write_owner_authority(
    fixture: dict[str, Any],
    context: dict[str, Any],
    consumer: str,
) -> dict[str, Any]:
    authority = _authority_payload(fixture, context, consumer)
    authority_key = authority["authority_key"]
    if consumer in {"exact_and_lexical_search", "episode_semantic"}:
        conn = module.init_search_db(
            module.search_db_path(fixture["aoa_root"]),
            rebuild=False,
            create_indexes=False,
        )
        conn.execute(
            f"INSERT OR REPLACE INTO {module.PROJECTION_OUTBOX_CONSUMER_AUTHORITY_TABLE} "
            "(authority_key, consumer, session_id, record_id, publish_id, operation, operation_key, attempt, authority_json, authority_sha256, committed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                authority_key,
                consumer,
                fixture["session_id"],
                fixture["record_id"],
                fixture["publish_id"],
                module.PROJECTION_OUTBOX_CONSUMER_OPERATION,
                context["operation_key"],
                context["attempt"],
                json.dumps(authority, sort_keys=True),
                authority["authority_sha256"],
                authority["committed_at"],
            ),
        )
        conn.commit()
        conn.close()
    elif consumer == "entity_registry":
        path = fixture["aoa_root"] / module.ENTITY_REGISTRY_PATH
        payload = module.read_json(path, {})
        if not isinstance(payload, dict) or not payload:
            payload = {
                "schema_version": 1,
                "artifact_type": "entity_registry_snapshot",
                "generation_identity": {
                    "generation_id": authority["generation_id"],
                    "publish_id": fixture["publish_id"],
                },
                "entries": [],
                "semantic_digest": {"sha256": "e" * 64},
            }
        payload.setdefault("projection_authorities", {})
        payload["projection_authorities"][authority_key] = authority
        payload.setdefault("generation_identity", authority["generation_identity"])
        payload.setdefault("semantic_digest", {"sha256": "e" * 64})
        module.write_json(path, payload)
    else:
        path = module.graph_paths(fixture["aoa_root"])["source_state_ledger"]
        payload = module.read_json(path, {})
        if not isinstance(payload, dict) or not payload:
            payload = module.empty_graph_source_state_ledger()
        payload["projection_authorities"] = payload.get("projection_authorities") if isinstance(payload.get("projection_authorities"), dict) else {}
        payload["projection_authorities"][authority_key] = authority
        payload.setdefault("sources", {})
        payload["sources"][f"session:{fixture['session_id']}"] = {
            "source_key": f"session:{fixture['session_id']}",
            "source_projection_publish_id": fixture["publish_id"],
            "expected_generation_id": authority["generation_id"],
            "authority_key": authority_key,
            "record_id": fixture["record_id"],
            "mutation_id": authority["mutation_id"],
            "status": "clean",
        }
        module.write_json(path, payload)
        graph_store = module.graph_paths(fixture["aoa_root"])["store"]
        graph_store.parent.mkdir(parents=True, exist_ok=True)
        conn = module.sqlite3.connect(graph_store)
        conn.execute("CREATE TABLE IF NOT EXISTS projection_outbox_mutations (mutation_id TEXT PRIMARY KEY, session_id TEXT NOT NULL, record_id TEXT NOT NULL, publish_id TEXT NOT NULL, authority_key TEXT NOT NULL, generation_id TEXT NOT NULL, source_ledger_ref TEXT NOT NULL, committed_at TEXT NOT NULL)")
        conn.execute("INSERT OR REPLACE INTO projection_outbox_mutations VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (authority["mutation_id"], fixture["session_id"], fixture["record_id"], fixture["publish_id"], authority_key, authority["generation_id"], "graph/source-state-ledger.json", authority["committed_at"]))
        conn.commit()
        conn.close()
    return authority


def _seed_owner_search_sources(fixture: dict[str, Any]) -> None:
    conn = module.init_search_db(
        module.search_db_path(fixture["aoa_root"]),
        rebuild=False,
        create_indexes=False,
    )
    session_id = fixture["session_id"]
    generation_json = json.dumps(
        {
            "generation_id": _authority_generation_id("exact_and_lexical_search"),
            "publish_id": fixture["publish_id"],
        },
        sort_keys=True,
    )
    conn.execute(
        "INSERT OR REPLACE INTO session_index_state (session_id, source_fingerprint, indexed_at, generation_id, generation_identity_json) VALUES (?, ?, ?, ?, ?)",
        (session_id, "s" * 64, "2026-08-23T00:00:00Z", _authority_generation_id("exact_and_lexical_search"), generation_json),
    )
    conn.execute(
        "INSERT OR REPLACE INTO search_freshness_state (session_id, session_dir, source_fingerprint, status, updated_at, generation_id, generation_identity_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (session_id, str(fixture["session_dir"]), "s" * 64, "current", "2026-08-23T00:00:00Z", _authority_generation_id("exact_and_lexical_search"), generation_json),
    )
    conn.execute(
        "INSERT OR REPLACE INTO exact_literal_session_state (session_id, session_label, source_fingerprint, status, posting_document_count, projection_version, indexed_at, generation_id, generation_identity_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (session_id, session_id, "s" * 64, "current", 1, 1, "2026-08-23T00:00:00Z", _authority_generation_id("exact_and_lexical_search"), generation_json),
    )
    episode_json = json.dumps(
        {
            "generation_id": _authority_generation_id("episode_semantic"),
            "publish_id": fixture["publish_id"],
        },
        sort_keys=True,
    )
    conn.execute(
        "INSERT OR REPLACE INTO episode_semantic_session_state (session_id, session_label, source_fingerprint, status, episode_count, projection_version, indexed_at, generation_id, generation_identity_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (session_id, session_id, "e" * 64, "current", 1, 1, "2026-08-23T00:00:00Z", _authority_generation_id("episode_semantic"), episode_json),
    )
    conn.commit()
    conn.close()


def _resource_admission(
    fixture: dict[str, Any],
    consumer: str,
    *,
    attempt: int = 1,
    operation: str | None = None,
    expires_at: str = "2099-01-01T00:00:00Z",
) -> dict[str, Any]:
    route = module._projection_outbox_route_registry_identity(consumer)
    operation_name = operation or module.PROJECTION_OUTBOX_CONSUMER_OPERATION
    operation_key = module._projection_outbox_operation_key(
        session_id=fixture["session_id"],
        record_id=fixture["record_id"],
        publish_id=fixture["publish_id"],
        consumer=consumer,
        operation=operation_name,
        attempt=attempt,
        route_id=route["route_id"],
    )
    lease_id = f"lease-{operation_key}"
    admission = {
        "schema_version": 1,
        "artifact_type": "projection_outbox_consumer_resource_admission",
        "status": "admitted",
        "decision": "allow",
        "admitted": True,
        "admission_id": f"admission-{operation_key}",
        "lease_id": lease_id,
        "resource_id": module.PROJECTION_OUTBOX_CONSUMER_RESOURCE_ID,
        "holder_id": "test-holder",
        "session_id": fixture["session_id"],
        "record_id": fixture["record_id"],
        "publish_id": fixture["publish_id"],
        "consumer": consumer,
        "operation": operation_name,
        "operation_key": operation_key,
        "attempt": attempt,
        "concurrency": 1,
        "lease": {
            "lease_id": lease_id,
            "resource_id": module.PROJECTION_OUTBOX_CONSUMER_RESOURCE_ID,
            "holder_id": "test-holder",
            "status": "active",
            "expires_at": expires_at,
        },
        "source_ref": module.PROJECTION_OUTBOX_CONSUMER_RESOURCE_AUTHORITY_SOURCE_REF,
    }
    authority_path = module._projection_outbox_resource_authority_path(
        fixture["aoa_root"],
        operation_key,
    )
    authority_path.parent.mkdir(parents=True, exist_ok=True)
    owner_authority = {
        "schema_version": module.PROJECTION_OUTBOX_CONSUMER_AUTHORITY_SCHEMA_VERSION,
        "artifact_type": module.PROJECTION_OUTBOX_CONSUMER_RESOURCE_AUTHORITY_ARTIFACT_TYPE,
        "status": "active",
        "owner_repo": module.PROJECTION_OUTBOX_CONSUMER_AUTHORITY_OWNER_REPO,
        "source_ref": module.PROJECTION_OUTBOX_CONSUMER_RESOURCE_AUTHORITY_SOURCE_REF,
        "resource_id": module.PROJECTION_OUTBOX_CONSUMER_RESOURCE_ID,
        "admission_key": operation_key,
        "admission_core_sha256": module._projection_outbox_resource_admission_core_digest(admission),
        "holder_id": admission["holder_id"],
        "lease": admission["lease"],
    }
    module.write_json(authority_path, owner_authority)
    admission["authority_ref"] = {
        "kind": "owner_resource_authority_ref_v1",
        "reference": str(authority_path),
        "sha256": module.sha256_file(authority_path),
    }
    admission["receipt_sha256"] = module._projection_outbox_resource_admission_digest(
        admission
    )
    return admission


def _semantic_evidence(
    fixture: dict[str, Any],
    consumer: str,
) -> dict[str, Any]:
    session_id = fixture["session_id"]
    publish_id = fixture["publish_id"]
    record_id = fixture["record_id"]
    route = module._projection_outbox_route_registry_identity(consumer)
    if consumer == "exact_and_lexical_search":
        return {
            "status": "committed",
            "generation_id": "search-generation-one",
            "session_id": session_id,
            "publish_id": publish_id,
            "changed_component_digests": {
                "component:one": "d" * 64,
            },
        }
    if consumer == "episode_semantic":
        return {
            "status": "current",
            "generation_id": "episode-generation-one",
            "session_id": session_id,
            "publish_id": publish_id,
        }
    if consumer == "entity_registry":
        search_state = module.read_json(
            module.projection_outbox_consumer_state_path(
                fixture["session_dir"],
                consumer="exact_and_lexical_search",
                record_id=record_id,
            ),
            {},
        )
        return {
            "status": "current",
            "session_id": session_id,
            "publish_id": publish_id,
            "search_receipt": {
                "consumer": "exact_and_lexical_search",
                "record_id": record_id,
                "publish_id": publish_id,
                "receipt_sha256": search_state["receipt_sha256"],
            },
            "route_dependency": {
                "status": "current",
                "session_id": session_id,
                "publish_id": publish_id,
                "registry_id": route["registry_id"],
                "registry_digest": route["registry_digest"],
                "route_id": route["route_id"],
            },
        }
    return {
        "status": "committed",
        "session_id": session_id,
        "publish_id": publish_id,
        "source_ledger_publish_id": publish_id,
        "mutation_id": "graph-mutation-one",
        "source_keys": [f"session:{session_id}"],
    }


def _route(
    fixture: dict[str, Any],
    calls: list[dict[str, Any]],
    consumer: str,
    *,
    result: dict[str, Any] | None = None,
    child_command: list[str] | None = None,
    mutate_manifest_publish: str | None = None,
    raise_if_called: bool = False,
    skip_authority: bool = False,
    raise_after_receipt: bool = False,
    mutate_receipt: Any | None = None,
) -> dict[str, Any]:
    registry = module._projection_outbox_route_registry_identity(consumer)

    def handler(context: dict[str, Any]) -> dict[str, Any]:
        if raise_if_called:
            raise AssertionError("handler re-executed during recovery")
        calls.append(dict(context))
        if result is not None:
            return dict(result)
        authority = (
            None
            if skip_authority
            else _write_owner_authority(fixture, context, consumer)
        )
        receipt = {
            "schema_version": module.PROJECTION_OUTBOX_CONSUMER_RECEIPT_SCHEMA_VERSION,
            "artifact_type": f"projection_outbox_{consumer}_committed_receipt",
            "status": "committed",
            "truth_status": "authoritative_consumer_commit_not_global_freshness",
            "consumer": consumer,
            "consumer_aliases": registry["consumer_aliases"],
            "session_id": context["session_id"],
            "record_id": context["record_id"],
            "outbox_record_id": context["record_id"],
            "source_publish_id": context["expected_publish_id"],
            "expected_publish_id": context["expected_publish_id"],
            "publication_identity": context["publication_identity"],
            "publication_aliases": context["publication_aliases"],
            "operation": context["operation"],
            "operation_aliases": registry["operation_aliases"],
            "operation_key": context["operation_key"],
            "route_registry": registry,
            "route_id": registry["route_id"],
            "handler_id": registry["handler_id"],
            "attempt": context["attempt"],
            "resource_admission": context["resource_admission"],
            "commit_ref": {},
            "authority_ref": (
                module._projection_outbox_authority_reference(authority)
                if authority is not None
                else {
                    "kind": "owner_authority_ref_v1",
                    "artifact_type": module._projection_outbox_authority_artifact_type(consumer),
                    "source_ref": module._projection_outbox_authority_source_ref(consumer),
                    "authority_key": module._projection_outbox_authority_key(
                        consumer=consumer,
                        session_id=context["session_id"],
                        record_id=context["record_id"],
                        publish_id=context["expected_publish_id"],
                        operation_key=context["operation_key"],
                        attempt=context["attempt"],
                    ),
                    "sha256": "0" * 64,
                }
            ),
            "semantic_evidence": _semantic_evidence(fixture, consumer),
            "committed_at": "2026-08-23T00:00:00Z",
        }
        receipt_path = Path(context["operation_receipt_path"])
        receipt["commit_ref"] = {
            "kind": "owner_committed_operation_receipt_v1",
            "reference": str(receipt_path),
            "sha256": module._projection_outbox_receipt_digest(receipt),
        }
        if callable(mutate_receipt):
            mutate_receipt(receipt)
            receipt["commit_ref"]["sha256"] = module._projection_outbox_receipt_digest(receipt)
        module.write_json_durable(receipt_path, receipt)
        if mutate_manifest_publish is not None:
            module.write_json(
                fixture["session_dir"] / "session.manifest.json",
                {
                    "session_id": fixture["session_id"],
                    "index_schema": {
                        "projection_publish": {
                            "publish_id": mutate_manifest_publish,
                        }
                    },
                },
            )
        if raise_after_receipt:
            raise RuntimeError("injected post-receipt handler exception")
        return {
            "ok": True,
            "status": "committed",
            "consumer": consumer,
            "consumer_aliases": registry["consumer_aliases"],
            "session_id": context["session_id"],
            "record_id": context["record_id"],
            "outbox_record_id": context["record_id"],
            "expected_publish_id": context["expected_publish_id"],
            "source_publish_id": context["expected_publish_id"],
            "publication_identity": context["publication_identity"],
            "publication_aliases": context["publication_aliases"],
            "operation": context["operation"],
            "operation_aliases": registry["operation_aliases"],
            "operation_key": context["operation_key"],
            "route_registry": registry,
            "route_id": registry["route_id"],
            "handler_id": registry["handler_id"],
            "attempt": context["attempt"],
            "resource_admission_id": context["resource_admission"][
                "admission_id"
            ],
            "lease_id": context["resource_admission"]["lease_id"],
            "commit_ref": receipt["commit_ref"],
        }

    route = {
        **registry,
        "registry_entry_id": registry["entry_id"],
        "consumer": consumer,
        "available": True,
        "targeted": True,
        "global_scope": False,
        "scope": "exact_session",
        "target_session_id": fixture["session_id"],
        "handler": handler,
    }
    if child_command is not None:
        route["child_command"] = child_command
    return route


def _apply(
    fixture: dict[str, Any],
    consumer: str,
    routes: dict[str, Any],
    *,
    max_attempts: int = 3,
    resource_admission: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return module.reconcile_projection_outbox_consumer(
        aoa_root=fixture["aoa_root"],
        session_id=fixture["session_id"],
        record_id=fixture["record_id"],
        expected_publish_id=fixture["publish_id"],
        consumer=consumer,
        apply=True,
        max_attempts=max_attempts,
        resource_admission=(
            resource_admission
            if resource_admission is not None
            else _resource_admission(fixture, consumer)
        ),
        consumer_routes=routes,
    )


def test_exact_identity_binding_and_supersession_refusal(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    calls: list[dict[str, Any]] = []
    routes = {
        "exact_and_lexical_search": _route(
            fixture, calls, "exact_and_lexical_search"
        )
    }
    wrong_publish = module.reconcile_projection_outbox_consumer(
        aoa_root=fixture["aoa_root"],
        session_id=fixture["session_id"],
        record_id=fixture["record_id"],
        expected_publish_id="c" * 64,
        consumer="exact_and_lexical_search",
        consumer_routes=routes,
    )
    assert wrong_publish["status"] == "superseded_identity"
    assert wrong_publish["effects"] == []
    assert calls == []
    module.write_json(
        fixture["session_dir"] / "session.manifest.json",
        {
            "session_id": fixture["session_id"],
            "index_schema": {"projection_publish": {"publish_id": "d" * 64}},
        },
    )
    superseded = module.reconcile_projection_outbox_consumer(
        aoa_root=fixture["aoa_root"],
        session_id=fixture["session_id"],
        record_id=fixture["record_id"],
        expected_publish_id=fixture["publish_id"],
        consumer="exact_and_lexical_search",
        consumer_routes=routes,
    )
    assert superseded["status"] == "superseded_identity"
    assert calls == []


def test_allowlist_dependency_order_and_one_consumer_per_invocation(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    calls: list[dict[str, Any]] = []
    entity_route = _route(fixture, calls, "entity_registry")
    blocked = module.reconcile_projection_outbox_consumer(
        aoa_root=fixture["aoa_root"],
        session_id=fixture["session_id"],
        record_id=fixture["record_id"],
        expected_publish_id=fixture["publish_id"],
        consumer="entity_registry",
        consumer_routes={"entity_registry": entity_route},
    )
    assert blocked["status"] == "missing_dependency"
    assert calls == []
    exact = _apply(
        fixture,
        "exact_and_lexical_search",
        {
            "exact_and_lexical_search": _route(
                fixture, calls, "exact_and_lexical_search"
            )
        },
    )
    assert exact["status"] == "consumer_completed"
    entity = _apply(fixture, "entity_registry", {"entity_registry": entity_route})
    assert entity["status"] == "consumer_completed"
    assert [item["consumer"] for item in calls] == [
        "exact_and_lexical_search",
        "entity_registry",
    ]
    unknown = module.reconcile_projection_outbox_consumer(
        aoa_root=fixture["aoa_root"],
        session_id=fixture["session_id"],
        record_id=fixture["record_id"],
        expected_publish_id=fixture["publish_id"],
        consumer="not_allowlisted",
        consumer_routes={},
    )
    assert unknown["status"] == "unavailable_targeted_consumer_route"
    assert len(calls) == 2


def test_dry_run_has_no_effect_and_does_not_call_handler(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    calls: list[dict[str, Any]] = []
    route = _route(fixture, calls, "exact_and_lexical_search")
    before = sorted(
        str(path.relative_to(fixture["aoa_root"]))
        for path in fixture["aoa_root"].rglob("*")
        if path.is_file()
    )
    result = module.reconcile_projection_outbox_consumer(
        aoa_root=fixture["aoa_root"],
        session_id=fixture["session_id"],
        record_id=fixture["record_id"],
        expected_publish_id=fixture["publish_id"],
        consumer="exact_and_lexical_search",
        apply=False,
        consumer_routes={"exact_and_lexical_search": route},
    )
    after = sorted(
        str(path.relative_to(fixture["aoa_root"]))
        for path in fixture["aoa_root"].rglob("*")
        if path.is_file()
    )
    assert result["status"] == "dry_run_ready"
    assert result["dry_run"] is True
    assert result["mutates"] is False
    assert result["effects"] == []
    assert result["write_paths"] == []
    assert calls == []
    assert after == before


def test_route_registry_and_resource_lease_are_required(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    calls: list[dict[str, Any]] = []
    route = _route(fixture, calls, "exact_and_lexical_search")
    route["registry_digest"] = "0" * 64
    denied_route = _apply(
        fixture,
        "exact_and_lexical_search",
        {"exact_and_lexical_search": route},
    )
    assert denied_route["status"] in {
        "global_child_forbidden",
        "unavailable_targeted_consumer_route",
    }
    assert calls == []
    denied_resource = _apply(
        fixture,
        "exact_and_lexical_search",
        {
            "exact_and_lexical_search": _route(
                fixture, calls, "exact_and_lexical_search"
            )
        },
        resource_admission={"admitted": True, "concurrency": 1},
    )
    assert denied_resource["status"] == "resource_denied"
    assert calls == []


def test_no_global_child_proof_blocks_rebuild_attempt(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    calls: list[dict[str, Any]] = []
    route = _route(
        fixture,
        calls,
        "exact_and_lexical_search",
        child_command=["search-index", "--session-id", fixture["session_id"], "--rebuild"],
    )
    result = module.reconcile_projection_outbox_consumer(
        aoa_root=fixture["aoa_root"],
        session_id=fixture["session_id"],
        record_id=fixture["record_id"],
        expected_publish_id=fixture["publish_id"],
        consumer="exact_and_lexical_search",
        consumer_routes={"exact_and_lexical_search": route},
    )
    assert result["status"] == "global_child_forbidden"
    assert calls == []
    assert result["mutates"] is False


def test_consumer_specific_evidence_and_retirement_replay(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    calls: list[dict[str, Any]] = []
    consumers = list(module.PROJECTION_OUTBOX_CONSUMER_RECONCILE_ORDER)
    routes = {
        consumer: _route(fixture, calls, consumer)
        for consumer in consumers
    }
    for consumer in consumers:
        result = _apply(fixture, consumer, {consumer: routes[consumer]})
        assert result["status"] in {"consumer_completed", "retired"}
        assert result["completion_receipt"]["status"] == "committed"
        assert result["completion_receipt"]["truth_status"] == (
            "authoritative_consumer_commit_not_global_freshness"
        )
    retirement_path = module.projection_outbox_consumer_retirement_path(
        fixture["aoa_root"], fixture["record_id"]
    )
    assert retirement_path.exists()
    before_calls = len(calls)
    replay = _apply(fixture, "graph", {"graph": routes["graph"]})
    assert replay["status"] == "already_retired"
    assert len(calls) == before_calls
    retirement = module.read_json(retirement_path, {})
    assert retirement["required_consumers"] == consumers
    assert set(retirement["completion_receipts"]) == set(consumers)


def test_bare_commit_ref_and_semantic_evidence_fail_closed(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    calls: list[dict[str, Any]] = []
    result = _apply(
        fixture,
        "exact_and_lexical_search",
        {
            "exact_and_lexical_search": _route(
                fixture,
                calls,
                "exact_and_lexical_search",
                result={
                    "ok": True,
                    "status": "committed",
                    "commit_ref": "bare-commit-ref",
                },
            )
        },
    )
    assert result["status"] == "consumer_route_failed"
    assert calls == [{}] or len(calls) == 1
    state = module.read_json(
        module.projection_outbox_consumer_state_path(
            fixture["session_dir"],
            consumer="exact_and_lexical_search",
            record_id=fixture["record_id"],
        ),
        {},
    )
    assert state["semantic_completion"] is False


def test_post_handler_current_publication_recheck_blocks_completion(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    calls: list[dict[str, Any]] = []
    result = _apply(
        fixture,
        "exact_and_lexical_search",
        {
            "exact_and_lexical_search": _route(
                fixture,
                calls,
                "exact_and_lexical_search",
                mutate_manifest_publish="c" * 64,
            )
        },
    )
    assert result["status"] == "superseded_identity"
    assert result["effects"] == []
    assert not module.projection_outbox_consumer_state_path(
        fixture["session_dir"],
        consumer="exact_and_lexical_search",
        record_id=fixture["record_id"],
    ).exists()


def test_committed_operation_recovery_conflict_and_no_reexecution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    calls: list[dict[str, Any]] = []
    route = _route(fixture, calls, "exact_and_lexical_search")
    admission = _resource_admission(fixture, "exact_and_lexical_search")
    original_state_writer = module.write_projection_outbox_consumer_state

    def crash_before_semantic_state(*args: Any, **kwargs: Any) -> dict[str, Any]:
        if kwargs.get("status") == "complete":
            raise OSError("injected semantic-state crash")
        return original_state_writer(*args, **kwargs)

    monkeypatch.setattr(
        module,
        "write_projection_outbox_consumer_state",
        crash_before_semantic_state,
    )
    with pytest.raises(OSError, match="injected semantic-state crash"):
        _apply(
            fixture,
            "exact_and_lexical_search",
            {"exact_and_lexical_search": route},
            resource_admission=admission,
        )
    assert len(calls) == 1
    journal_path = module.projection_outbox_consumer_operation_journal_path(
        fixture["aoa_root"],
        module._projection_outbox_operation_key(
            session_id=fixture["session_id"],
            record_id=fixture["record_id"],
            publish_id=fixture["publish_id"],
            consumer="exact_and_lexical_search",
            operation=module.PROJECTION_OUTBOX_CONSUMER_OPERATION,
            attempt=1,
            route_id=module._projection_outbox_route_registry_identity(
                "exact_and_lexical_search"
            )["route_id"],
        ),
    )
    assert journal_path.exists()
    monkeypatch.setattr(module, "write_projection_outbox_consumer_state", original_state_writer)
    recovered = _apply(
        fixture,
        "exact_and_lexical_search",
        {
            "exact_and_lexical_search": _route(
                fixture,
                calls,
                "exact_and_lexical_search",
                raise_if_called=True,
            )
        },
        resource_admission=admission,
    )
    assert recovered["replayed"] is True
    assert recovered["status"] == "consumer_completed"
    assert len(calls) == 1
    state_path = module.projection_outbox_consumer_state_path(
        fixture["session_dir"],
        consumer="exact_and_lexical_search",
        record_id=fixture["record_id"],
    )
    state_path.unlink()
    receipt_path = module.projection_outbox_consumer_operation_receipt_path(
        fixture["aoa_root"], recovered["completion_receipt"]["operation_key"]
    )
    module.write_json(receipt_path, {"conflicting": True})
    conflict = _apply(
        fixture,
        "exact_and_lexical_search",
        {
            "exact_and_lexical_search": _route(
                fixture,
                calls,
                "exact_and_lexical_search",
                raise_if_called=True,
            )
        },
        resource_admission=admission,
    )
    assert conflict["status"] == "committed_operation_conflict"
    assert len(calls) == 1


def test_complete_record_schema_and_legacy_progress_do_not_make_freshness(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    record_path = module.projection_outbox_record_path(
        fixture["session_dir"], fixture["record_id"]
    )
    tampered = module.read_json(record_path, {})
    tampered["required_consumers"] = ["exact_and_lexical_search"] * 2
    module.write_json(record_path, tampered)
    rejected = module.reconcile_projection_outbox_consumer(
        aoa_root=fixture["aoa_root"],
        session_id=fixture["session_id"],
        record_id=fixture["record_id"],
        expected_publish_id=fixture["publish_id"],
        consumer="exact_and_lexical_search",
        consumer_routes={},
    )
    assert rejected["status"] == "invalid_record"
    assert any("record_required_consumers_not_unique_strings" in item for item in rejected["diagnostics"])

    fixture = _fixture(tmp_path / "progress")
    progress = module.complete_projection_outbox_consumers_for_session(
        aoa_root=fixture["aoa_root"],
        session_dir=fixture["session_dir"],
        consumers=["exact_and_lexical_search"],
        completion_receipt={"legacy": "progress"},
    )
    assert progress["status"] == "progressed"
    assert progress["semantic_completion"] is False
    freshness = module.session_projection_freshness_vector(
        aoa_root=fixture["aoa_root"],
        session_dir=fixture["session_dir"],
    )
    assert freshness["axes"]["search"]["current"] is False
    assert freshness["axes"]["search"]["semantic_completion"] is False


def test_legacy_manual_completion_rejects_generic_authoritative_receipt(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    with pytest.raises(
        ValueError,
        match="projection_outbox_authoritative_receipt_required",
    ):
        module.write_projection_outbox_consumer_state(
            fixture["session_dir"],
            record=fixture["record"],
            consumer="exact_and_lexical_search",
            status="complete",
            reason="manual generic result",
            completion_receipt={"db_commit": "not-authoritative"},
        )


def test_retirement_write_crash_replays_without_handler_dispatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    calls: list[dict[str, Any]] = []
    consumers = list(module.PROJECTION_OUTBOX_CONSUMER_RECONCILE_ORDER)
    routes = {
        consumer: _route(fixture, calls, consumer)
        for consumer in consumers
    }
    retirement_path = module.projection_outbox_consumer_retirement_path(
        fixture["aoa_root"], fixture["record_id"]
    )
    for consumer in consumers[:-1]:
        result = _apply(
            fixture,
            consumer,
            {consumer: routes[consumer]},
        )
        assert result["status"] in {"consumer_completed", "retired"}
    assert len(calls) == len(consumers) - 1
    original_write = module.write_json_durable

    def crash_retirement_write(path: Path, payload: Any) -> None:
        if Path(path) == retirement_path:
            raise OSError("injected retirement write crash")
        original_write(path, payload)

    monkeypatch.setattr(module, "write_json_durable", crash_retirement_write)
    with pytest.raises(OSError, match="injected retirement write crash"):
        _apply(fixture, "graph", {"graph": routes["graph"]})
    assert len(calls) == len(consumers)
    assert not retirement_path.exists()

    monkeypatch.setattr(module, "write_json_durable", original_write)
    retirement_admission = _resource_admission(
        fixture,
        "graph",
        operation="retirement",
        attempt=1,
    )
    replay = _apply(
        fixture,
        "graph",
        {
            "graph": _route(
                fixture,
                calls,
                "graph",
                raise_if_called=True,
            )
        },
        resource_admission=retirement_admission,
    )
    assert replay["status"] == "retired"
    assert len(calls) == len(consumers)
    assert retirement_path.exists()


@pytest.mark.parametrize(
    "consumer",
    ["exact_and_lexical_search", "episode_semantic", "entity_registry", "graph"],
)
def test_missing_default_targeted_route_fails_closed(
    tmp_path: Path,
    consumer: str,
) -> None:
    fixture = _fixture(tmp_path)
    result = module.reconcile_projection_outbox_consumer(
        aoa_root=fixture["aoa_root"],
        session_id=fixture["session_id"],
        record_id=fixture["record_id"],
        expected_publish_id=fixture["publish_id"],
        consumer=consumer,
        consumer_routes=None,
    )
    assert result["status"] in {
        "unavailable_targeted_consumer_route",
        "missing_dependency",
    }
    assert result["mutates"] is False


def test_missing_consumer_authority_artifact_fails_closed(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    calls: list[dict[str, Any]] = []
    result = _apply(
        fixture,
        "exact_and_lexical_search",
        {
            "exact_and_lexical_search": _route(
                fixture,
                calls,
                "exact_and_lexical_search",
                skip_authority=True,
            )
        },
    )
    assert result["status"] == "consumer_route_failed"
    assert any("consumer_authority" in item for item in result["diagnostics"])
    state = module.read_json(
        module.projection_outbox_consumer_state_path(
            fixture["session_dir"],
            consumer="exact_and_lexical_search",
            record_id=fixture["record_id"],
        ),
        {},
    )
    assert state["status"] == "failed_retryable"
    assert state["semantic_completion"] is False
    assert calls


def test_receipt_then_exception_recovers_same_operation_without_duplicate_dispatch(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    calls: list[dict[str, Any]] = []
    result = _apply(
        fixture,
        "exact_and_lexical_search",
        {
            "exact_and_lexical_search": _route(
                fixture,
                calls,
                "exact_and_lexical_search",
                raise_after_receipt=True,
            )
        },
    )
    assert result["status"] == "consumer_completed"
    assert result["replayed"] is True
    assert len(calls) == 1
    state = module.read_json(
        module.projection_outbox_consumer_state_path(
            fixture["session_dir"],
            consumer="exact_and_lexical_search",
            record_id=fixture["record_id"],
        ),
        {},
    )
    assert state["attempt_count"] == 1


def test_publication_advance_at_semantic_write_rolls_back_complete_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    calls: list[dict[str, Any]] = []
    original = module.write_projection_outbox_consumer_state

    def advance_at_write(*args: Any, **kwargs: Any) -> dict[str, Any]:
        if kwargs.get("status") == "complete":
            module.write_json(
                fixture["session_dir"] / "session.manifest.json",
                {
                    "session_id": fixture["session_id"],
                    "index_schema": {
                        "projection_publish": {"publish_id": "c" * 64}
                    },
                },
            )
        return original(*args, **kwargs)

    monkeypatch.setattr(
        module,
        "write_projection_outbox_consumer_state",
        advance_at_write,
    )
    result = _apply(
        fixture,
        "exact_and_lexical_search",
        {
            "exact_and_lexical_search": _route(
                fixture,
                calls,
                "exact_and_lexical_search",
            )
        },
    )
    assert result["status"] == "publication_fence_drift"
    assert result["ok"] is False
    assert not module.projection_outbox_consumer_state_path(
        fixture["session_dir"],
        consumer="exact_and_lexical_search",
        record_id=fixture["record_id"],
    ).exists()
    assert not module.projection_outbox_consumer_retirement_path(
        fixture["aoa_root"], fixture["record_id"]
    ).exists()


def test_expired_lease_is_not_admitted_even_when_json_is_self_consistent(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    calls: list[dict[str, Any]] = []
    result = _apply(
        fixture,
        "exact_and_lexical_search",
        {
            "exact_and_lexical_search": _route(
                fixture,
                calls,
                "exact_and_lexical_search",
            )
        },
        resource_admission=_resource_admission(
            fixture,
            "exact_and_lexical_search",
            expires_at="2000-01-01T00:00:00Z",
        ),
    )
    assert result["status"] == "resource_denied"
    assert any("expired" in item for item in result["resource"]["diagnostics"])
    assert calls == []


@pytest.mark.parametrize("field", ["holder_id", "source_ref"])
def test_forged_resource_identity_is_rejected_by_owner_authority(
    tmp_path: Path,
    field: str,
) -> None:
    fixture = _fixture(tmp_path)
    admission = _resource_admission(fixture, "exact_and_lexical_search")
    admission[field] = "forged-holder" if field == "holder_id" else "tests/forged-source"
    if field == "holder_id":
        admission["lease"]["holder_id"] = admission[field]
    admission["receipt_sha256"] = module._projection_outbox_resource_admission_digest(admission)
    calls: list[dict[str, Any]] = []
    result = _apply(
        fixture,
        "exact_and_lexical_search",
        {"exact_and_lexical_search": _route(fixture, calls, "exact_and_lexical_search")},
        resource_admission=admission,
    )
    assert result["status"] == "resource_denied"
    assert calls == []


def test_created_at_mutation_changes_content_addressed_record_id(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    record_path = module.projection_outbox_record_path(
        fixture["session_dir"], fixture["record_id"]
    )
    tampered = module.read_json(record_path, {})
    tampered["created_at"] = "2000-01-01T00:00:00Z"
    valid, diagnostics = module._projection_outbox_record_valid(tampered, aoa_root=fixture["aoa_root"])
    assert valid is False
    assert "record_id_content_hash_mismatch" in diagnostics


def test_record_retry_policy_one_cannot_be_widened_by_caller(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    original_path = module.projection_outbox_record_path(
        fixture["session_dir"], fixture["record_id"]
    )
    record = module.read_json(original_path, {})
    record["retry_policy"]["max_attempts_per_cycle"] = 1
    record["record_id"] = module._projection_outbox_record_recomputed_id(record)
    new_path = module.projection_outbox_record_path(
        fixture["session_dir"], record["record_id"]
    )
    module.write_json(new_path, record)
    fixture["record"] = record
    fixture["record_id"] = record["record_id"]
    calls: list[dict[str, Any]] = []
    route = _route(
        fixture,
        calls,
        "exact_and_lexical_search",
        result={"ok": False, "status": "retryable"},
    )
    first = _apply(
        fixture,
        "exact_and_lexical_search",
        {"exact_and_lexical_search": route},
        max_attempts=3,
    )
    assert first["status"] == "consumer_route_failed"
    second = module.reconcile_projection_outbox_consumer(
        aoa_root=fixture["aoa_root"],
        session_id=fixture["session_id"],
        record_id=fixture["record_id"],
        expected_publish_id=fixture["publish_id"],
        consumer="exact_and_lexical_search",
        apply=True,
        max_attempts=3,
        resource_admission=_resource_admission(
            fixture,
            "exact_and_lexical_search",
            attempt=2,
        ),
        consumer_routes={"exact_and_lexical_search": route},
    )
    assert second["status"] == "attempt_limit_exhausted"
    assert len(calls) == 1


def test_entity_cannot_remain_current_after_search_demotion(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    calls: list[dict[str, Any]] = []
    search = _apply(
        fixture,
        "exact_and_lexical_search",
        {"exact_and_lexical_search": _route(fixture, calls, "exact_and_lexical_search")},
    )
    assert search["status"] == "consumer_completed"
    entity = _apply(
        fixture,
        "entity_registry",
        {"entity_registry": _route(fixture, calls, "entity_registry")},
    )
    assert entity["status"] == "consumer_completed"
    conn = module.init_search_db(
        module.search_db_path(fixture["aoa_root"]),
        rebuild=False,
        create_indexes=False,
    )
    conn.execute(
        "UPDATE search_freshness_state SET status = 'stale' WHERE session_id = ?",
        (fixture["session_id"],),
    )
    conn.commit()
    conn.close()
    freshness = module.session_projection_freshness_vector(
        aoa_root=fixture["aoa_root"],
        session_dir=fixture["session_dir"],
    )
    assert freshness["axes"]["search"]["current"] is False
    assert freshness["axes"]["entity_registry"]["current"] is False


@pytest.mark.parametrize("field", ["handler_id", "consumer_aliases", "operation_aliases"])
def test_route_handler_alias_mismatch_fails_closed(
    tmp_path: Path,
    field: str,
) -> None:
    fixture = _fixture(tmp_path)
    calls: list[dict[str, Any]] = []
    route = _route(fixture, calls, "exact_and_lexical_search")
    route[field] = (
        "forged-handler"
        if field == "handler_id"
        else ["forged-consumer-alias"]
        if field == "consumer_aliases"
        else ["forged-operation-alias"]
    )
    denied_route = _apply(
        fixture,
        "exact_and_lexical_search",
        {"exact_and_lexical_search": route},
    )
    assert denied_route["status"] in {"global_child_forbidden", "unavailable_targeted_consumer_route"}


def test_attempt_mismatch_fails_closed(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path / "attempt")
    calls = []
    route = _route(fixture, calls, "exact_and_lexical_search")
    first = _apply(fixture, "exact_and_lexical_search", {"exact_and_lexical_search": route})
    assert first["status"] == "consumer_completed"
    # The current operation is already complete; a stale attempt/lease cannot
    # be reused as an authoritative retirement admission.
    stale = _apply(
        fixture,
        "exact_and_lexical_search",
        {"exact_and_lexical_search": route},
        resource_admission=_resource_admission(
            fixture,
            "exact_and_lexical_search",
            attempt=2,
        ),
    )
    assert stale["status"] in {"resource_denied", "already_retired", "consumer_already_complete"}
