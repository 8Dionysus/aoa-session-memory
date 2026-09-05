from __future__ import annotations

import copy
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


from session_memory_test_support import (
    module,
    write_jsonl,
)

def test_episode_projection_queue_releases_unstarted_budget_work_and_recovers_restart(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    for index in range(2):
        session_id = f"episode-queue-{index + 1}"
        transcript = tmp_path / f"rollout-2026-06-20T00-00-0{index}-{session_id}.jsonl"
        write_jsonl(
            transcript,
            [
                {
                    "timestamp": f"2026-06-20T00:00:0{index}Z",
                    "type": "session_meta",
                    "payload": {"id": session_id, "cwd": str(workspace)},
                },
                {
                    "timestamp": f"2026-06-20T00:00:1{index}Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": f"Inspect queue case {index + 1}"}],
                    },
                },
                {
                    "timestamp": f"2026-06-20T00:00:2{index}Z",
                    "type": "response_item",
                    "payload": {
                        "type": "function_call",
                        "name": "exec_command",
                        "call_id": f"call-{index + 1}",
                        "arguments": json.dumps({"cmd": f"printf queue-{index + 1}"}),
                    },
                },
                {
                    "timestamp": f"2026-06-20T00:00:3{index}Z",
                    "type": "response_item",
                    "payload": {
                        "type": "function_call_output",
                        "call_id": f"call-{index + 1}",
                        "output": f"Process exited with code 0\nFinal output:\nqueue-{index + 1}",
                    },
                },
            ],
        )
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

    records = module.chronological_session_records(aoa_root)
    assert len(records) == 2
    clock = {"value": 0.0}
    original_insert = module.insert_episode_semantic_projection_for_session

    def insert_then_exhaust_budget(*args: Any, **kwargs: Any) -> dict[str, Any]:
        result = original_insert(*args, **kwargs)
        clock["value"] = 2.0
        return result

    monkeypatch.setattr(module.time, "monotonic", lambda: clock["value"])
    monkeypatch.setattr(module, "insert_episode_semantic_projection_for_session", insert_then_exhaust_budget)

    partial = module.episode_semantic_index_sessions(
        aoa_root=aoa_root,
        target="all",
        selected_records=records,
        dirty_only=True,
        max_cost_class="light",
        limit=2,
        budget_seconds=1.0,
    )

    assert partial["budget_exhausted"] is True
    assert partial["processed_count"] == 1
    assert partial["remaining_count"] == 1
    assert partial["queue"]["final"]["status_counts"] == {"queued": 1}
    conn = sqlite3.connect(module.search_db_path(aoa_root))
    conn.row_factory = sqlite3.Row
    running_count = conn.execute(
        "SELECT COUNT(*) FROM episode_semantic_queue WHERE status = 'running'"
    ).fetchone()[0]
    remaining_id = conn.execute("SELECT session_id FROM episode_semantic_queue").fetchone()[0]
    assert running_count == 0
    conn.execute(
        "UPDATE episode_semantic_queue SET status = 'running' WHERE session_id = ?",
        (remaining_id,),
    )
    conn.commit()
    conn.close()

    clock["value"] = 0.0
    resumed = module.episode_semantic_index_sessions(
        aoa_root=aoa_root,
        target="all",
        selected_records=records,
        dirty_only=True,
        max_cost_class="light",
        limit=1,
        budget_seconds=30.0,
    )

    assert resumed["ok"] is True
    assert resumed["processed_count"] == 1
    assert resumed["remaining_count"] == 0
    assert resumed["queue"]["recovered_running_count"] == 1
    assert resumed["queue"]["final"]["remaining_count"] == 0

    clock["value"] = 0.0
    clean = module.episode_semantic_index_sessions(
        aoa_root=aoa_root,
        target="all",
        selected_records=records,
        dirty_only=True,
        max_cost_class="light",
        limit=1,
        budget_seconds=30.0,
    )
    assert clean["ok"] is True
    assert clean["processed_count"] == 0
    assert clean["remaining_count"] == 0
def test_episode_dense_projection_exact_cosine_and_semantic_refresh_invalidation(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    aoa_root = tmp_path / ".aoa"
    db_path = module.search_db_path(aoa_root)
    episode_generation = (
        module.session_memory_expected_generation_identities(aoa_root)[
            "episode_semantic"
        ]
    )
    conn = module.init_search_db(db_path, rebuild=False, create_indexes=False)
    for index, text in enumerate(("downstream canary checked zero skipped four", "clipboard machine snapshot"), start=1):
        session_id = f"dense-session-{index}"
        doc_id = f"episode_semantic:{session_id}:task-0001"
        cursor = conn.execute(
            """
            INSERT INTO episode_semantic_meta (
                doc_id, session_id, session_label, session_title, session_date,
                episode_id, preview, session_index_path, projection_version,
                generation_id
            ) VALUES (?, ?, ?, ?, ?, 'task-0001', ?, ?, ?, ?)
            """,
            (
                doc_id,
                session_id,
                session_id,
                session_id,
                f"2026-06-0{index}",
                text,
                str(tmp_path / session_id / module.SESSION_INDEX_JSON),
                module.EPISODE_SEMANTIC_PROJECTION_VERSION,
                episode_generation["generation_id"],
            ),
        )
        episode = {
            "episode_id": "task-0001",
            "representations": {
                "outcomes": [
                    {
                        "text": text,
                        "refs": {
                            "raw": (
                                f"raw:line:{10 + index}"
                            ),
                            "session": (
                                f"sessions/{session_id}/session.json"
                            ),
                        },
                        "source_lane": "assistant",
                        "admission_basis": "assistant_observation",
                    }
                ]
            },
            "narrative": text,
        }
        conn.execute(
            "INSERT INTO episode_semantic_payloads(doc_rowid, payload_zlib) VALUES (?, ?)",
            (
                cursor.lastrowid,
                sqlite3.Binary(
                    module.zlib.compress(json.dumps(episode, separators=(",", ":")).encode("utf-8"))
                ),
            ),
        )
        conn.execute(
            """
            INSERT INTO episode_semantic_session_state (
                session_id, session_label, source_fingerprint, status,
                        episode_count, projection_version, indexed_at,
                        source_fingerprint_mode, route_signal_classifier_version,
                        generation_id, generation_identity_json
                    ) VALUES (?, ?, ?, 'current', 1, ?, '2026-06-03T00:00:00Z', ?, ?, ?, ?)
            """,
            (
                session_id,
                session_id,
                f"fingerprint-{index}",
                    module.EPISODE_SEMANTIC_PROJECTION_VERSION,
                        module.EPISODE_SEMANTIC_SOURCE_FINGERPRINT_MODE,
                        module.ROUTE_SIGNAL_CLASSIFIER_VERSION,
                        episode_generation["generation_id"],
                        json.dumps(
                            episode_generation,
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                    ),
        )
    conn.commit()
    conn.close()

    def fake_embed_texts(*, url: str, texts: list[str], batch_size: int = 4, timeout: int = 120) -> dict[str, Any]:
        vectors = []
        for text in texts:
            vector = [0.0] * module.EPISODE_DENSE_DEFAULT_DIMENSION
            vector[0 if "canary" in text else 1] = 1.0
            vectors.append(vector)
        return {
            "ok": True,
            "status": "embedded",
            "vectors": vectors,
            "model": module.EPISODE_DENSE_DEFAULT_MODEL,
            "dimension": module.EPISODE_DENSE_DEFAULT_DIMENSION,
            "prompt_tokens": len(texts),
            "elapsed_ms": 1,
            "diagnostics": [],
        }

    monkeypatch.setattr(module, "episode_dense_embed_texts", fake_embed_texts)
    built = module.episode_dense_index_sessions(aoa_root=aoa_root, dirty_only=True)
    assert built["ok"] is True
    assert built["coverage"]["status"] == "current"
    assert built["coverage"]["vector_count"] == 2
    assert built["coverage"]["representation_vector_count"] == 2
    assert built["generation_publish"]["status"] == "published"
    metadata_conn = module.connect_existing_search_db(db_path)
    stored_generations = module.projection_generation_from_json(
        metadata_conn.execute(
            "SELECT value FROM meta "
            "WHERE key = 'generation_identities_json'"
        ).fetchone()[0]
    )
    metadata_conn.close()
    assert stored_generations["episode_dense"]["generation_id"] == (
        module.session_memory_expected_generation_identities(aoa_root)[
            "episode_dense"
        ]["generation_id"]
    )
    stored_generations["episode_dense"] = {
        "generation_id": "stale-dense-generation"
    }
    metadata_conn = module.init_search_db(
        db_path,
        rebuild=False,
        create_indexes=False,
    )
    metadata_conn.execute(
        "INSERT OR REPLACE INTO meta(key, value) "
        "VALUES ('generation_identities_json', ?)",
        (
            json.dumps(
                stored_generations,
                sort_keys=True,
                separators=(",", ":"),
            ),
        ),
    )
    metadata_conn.commit()
    metadata_conn.close()
    metadata_repair = module.episode_dense_index_sessions(
        aoa_root=aoa_root,
        dirty_only=True,
    )
    assert metadata_repair["status"] == "no_work"
    assert metadata_repair["generation_publish"]["status"] == "published"
    assert metadata_repair["generation_publish"][
        "previous_generation_id"
    ] == "stale-dense-generation"

    ranking = module.episode_dense_search_ranking(
        aoa_root=aoa_root,
        query="why canary checked no repositories",
        filters=["episode_semantic_meta.projection_version = ?"],
        params=[module.EPISODE_SEMANTIC_PROJECTION_VERSION],
        limit=2,
    )
    assert ranking["ok"] is True
    assert ranking["ranking"][0]["doc_id"] == "episode_semantic:dense-session-1:task-0001"
    assert ranking["representation_vector_count"] == 2
    assert ranking["episode_fallback_vector_count"] == 0
    assert ranking["ranking"][0]["representation_matches"][0][
        "raw_ref"
    ] == "raw:line:11"
    assert ranking["scanned_vector_bytes"] == 2 * module.EPISODE_DENSE_DEFAULT_DIMENSION * 4

    indexed_classifier_version = module.ROUTE_SIGNAL_CLASSIFIER_VERSION
    monkeypatch.setattr(
        module,
        "ROUTE_SIGNAL_CLASSIFIER_VERSION",
        indexed_classifier_version + 1,
    )
    refreshed_episode_generation = (
        module.session_memory_expected_generation_identities(aoa_root)[
            "episode_semantic"
        ]
    )
    conn = module.init_search_db(db_path, rebuild=False, create_indexes=False)
    conn.execute(
        "UPDATE episode_semantic_session_state "
        "SET route_signal_classifier_version = ?, generation_id = ?, "
        "generation_identity_json = ?",
        (
            module.ROUTE_SIGNAL_CLASSIFIER_VERSION,
            refreshed_episode_generation["generation_id"],
            json.dumps(
                refreshed_episode_generation,
                sort_keys=True,
                separators=(",", ":"),
            ),
        ),
    )
    conn.execute(
        "UPDATE episode_semantic_meta SET generation_id = ?",
        (refreshed_episode_generation["generation_id"],),
    )
    conn.commit()
    conn.close()
    stale_dense = module.episode_dense_projection_state(aoa_root)
    assert stale_dense["dirty_session_count"] == 2
    stale_ranking = module.episode_dense_search_ranking(
        aoa_root=aoa_root,
        query="why canary checked no repositories",
        filters=["episode_semantic_meta.projection_version = ?"],
        params=[module.EPISODE_SEMANTIC_PROJECTION_VERSION],
        limit=2,
    )
    assert stale_ranking["ok"] is False
    assert stale_ranking["status"] == "dense_projection_empty_for_scope"
    refreshed_dense = module.episode_dense_index_sessions(aoa_root=aoa_root, dirty_only=True)
    assert refreshed_dense["ok"] is True
    assert refreshed_dense["processed_count"] == 2
    assert refreshed_dense["coverage"]["status"] == "current"

    conn = module.init_search_db(db_path, rebuild=False, create_indexes=False)
    removed = module.delete_episode_semantic_for_session(conn, session_id="dense-session-1")
    conn.commit()
    dense_vector_count = conn.execute(
        "SELECT COUNT(*) FROM episode_dense_vectors WHERE session_id = 'dense-session-1'"
    ).fetchone()[0]
    representation_vector_count = conn.execute(
        "SELECT COUNT(*) FROM episode_dense_representation_vectors "
        "WHERE session_id = 'dense-session-1'"
    ).fetchone()[0]
    dense_state_count = conn.execute(
        "SELECT COUNT(*) FROM episode_dense_session_state WHERE session_id = 'dense-session-1'"
    ).fetchone()[0]
    conn.close()
    assert removed == 1
    assert dense_vector_count == 0
    assert representation_vector_count == 0
    assert dense_state_count == 0
def test_episode_dense_rebuild_is_semantically_deterministic_and_failed_store_preserves_previous_generation(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    aoa_root = tmp_path / ".aoa"
    db_path = module.search_db_path(aoa_root)
    expected = module.session_memory_expected_generation_identities(
        aoa_root
    )
    episode_generation = expected["episode_semantic"]
    session_id = "dense-atomic-session"
    doc_id = f"episode_semantic:{session_id}:task-0001"
    conn = module.init_search_db(
        db_path,
        rebuild=False,
        create_indexes=False,
    )
    cursor = conn.execute(
        """
        INSERT INTO episode_semantic_meta (
            doc_id, session_id, session_label, session_title, session_date,
            episode_id, preview, session_index_path, projection_version,
            generation_id
        ) VALUES (?, ?, ?, ?, '2026-07-18', 'task-0001', ?, ?, ?, ?)
        """,
        (
            doc_id,
            session_id,
            session_id,
            session_id,
            "dense atomic projection evidence",
            str(tmp_path / session_id / module.SESSION_INDEX_JSON),
            module.EPISODE_SEMANTIC_PROJECTION_VERSION,
            episode_generation["generation_id"],
        ),
    )
    episode = {
        "episode_id": "task-0001",
        "representations": {
            "outcomes": [
                {
                    "text": "dense atomic projection evidence",
                    "refs": {
                        "raw": "raw:line:7",
                        "session": (
                            "sessions/dense-atomic-session/session.json"
                        ),
                    },
                    "source_lane": "assistant",
                    "admission_basis": "assistant_observation",
                }
            ]
        },
    }
    conn.execute(
        "INSERT INTO episode_semantic_payloads(doc_rowid, payload_zlib) "
        "VALUES (?, ?)",
        (
            cursor.lastrowid,
            sqlite3.Binary(
                module.zlib.compress(
                    json.dumps(
                        episode,
                        separators=(",", ":"),
                    ).encode("utf-8")
                )
            ),
        ),
    )
    conn.execute(
        """
        INSERT INTO episode_semantic_session_state (
            session_id, session_label, source_fingerprint, status,
            episode_count, projection_version, indexed_at,
            source_fingerprint_mode, route_signal_classifier_version,
            generation_id, generation_identity_json
        ) VALUES (?, ?, 'dense-atomic-source', 'current', 1, ?,
                  '2026-07-18T00:00:00Z', ?, ?, ?, ?)
        """,
        (
            session_id,
            session_id,
            module.EPISODE_SEMANTIC_PROJECTION_VERSION,
            module.EPISODE_SEMANTIC_SOURCE_FINGERPRINT_MODE,
            module.ROUTE_SIGNAL_CLASSIFIER_VERSION,
            episode_generation["generation_id"],
            json.dumps(
                episode_generation,
                sort_keys=True,
                separators=(",", ":"),
            ),
        ),
    )
    conn.commit()
    conn.close()

    def deterministic_embed(**kwargs: Any) -> dict[str, Any]:
        texts = list(kwargs.get("texts") or [])
        vector = [0.0] * module.EPISODE_DENSE_DEFAULT_DIMENSION
        vector[17] = 1.0
        return {
            "ok": True,
            "status": "embedded",
            "vectors": [list(vector) for _ in texts],
            "model": module.EPISODE_DENSE_DEFAULT_MODEL,
            "dimension": module.EPISODE_DENSE_DEFAULT_DIMENSION,
            "prompt_tokens": len(texts),
            "elapsed_ms": 1,
            "diagnostics": [],
        }

    monkeypatch.setattr(
        module,
        "episode_dense_embed_texts",
        deterministic_embed,
    )

    def semantic_snapshot() -> tuple[Any, ...]:
        snapshot_conn = module.connect_existing_search_db(db_path)
        row = snapshot_conn.execute(
            "SELECT doc_id, session_id, episode_id, document_sha256, "
            "hex(vector_f32), generation_id "
            "FROM episode_dense_vectors WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        state = snapshot_conn.execute(
            "SELECT status, episode_document_count, vector_count, "
            "representation_document_count, representation_vector_count, "
            "generation_id FROM episode_dense_session_state "
            "WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        representations = snapshot_conn.execute(
            "SELECT representation_id, doc_id, role, raw_ref, "
            "document_sha256, hex(vector_f32), generation_id "
            "FROM episode_dense_representation_vectors "
            "WHERE session_id = ? ORDER BY representation_id",
            (session_id,),
        ).fetchall()
        snapshot_conn.close()
        return (
            tuple(row)
            + tuple(state)
            + tuple(tuple(item) for item in representations)
        )

    first = module.episode_dense_index_sessions(
        aoa_root=aoa_root,
        dirty_only=True,
    )
    assert first["ok"] is True
    first_snapshot = semantic_snapshot()

    second = module.episode_dense_index_sessions(
        aoa_root=aoa_root,
        dirty_only=False,
    )
    assert second["ok"] is True
    assert semantic_snapshot() == first_snapshot

    monkeypatch.setattr(
        module,
        "episode_dense_vector_blob",
        lambda _values: (_ for _ in ()).throw(
            ValueError("fault after dense delete before commit")
        ),
    )
    failed = module.episode_dense_index_sessions(
        aoa_root=aoa_root,
        dirty_only=False,
    )

    assert failed["ok"] is False
    assert failed["sessions"][0]["status"] == "store_failed"
    assert semantic_snapshot() == first_snapshot
def test_episode_dense_provider_unavailable_is_one_preflight_defer_not_session_failures(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    aoa_root = tmp_path / ".aoa"
    db_path = module.search_db_path(aoa_root)
    episode_generation = (
        module.session_memory_expected_generation_identities(aoa_root)[
            "episode_semantic"
        ]
    )
    conn = module.init_search_db(db_path, rebuild=False, create_indexes=False)
    for index in range(1, 3):
        session_id = f"dense-provider-defer-{index}"
        cursor = conn.execute(
            """
            INSERT INTO episode_semantic_meta (
                doc_id, session_id, session_label, session_title, session_date,
                episode_id, preview, session_index_path, projection_version,
                generation_id
            ) VALUES (?, ?, ?, ?, ?, 'task-0001', ?, ?, ?, ?)
            """,
            (
                f"episode_semantic:{session_id}:task-0001",
                session_id,
                session_id,
                session_id,
                f"2026-07-0{index}",
                f"provider unavailable observed case {index}",
                    str(tmp_path / session_id / module.SESSION_INDEX_JSON),
                    module.EPISODE_SEMANTIC_PROJECTION_VERSION,
                    episode_generation["generation_id"],
            ),
        )
        episode = {
            "episode_id": "task-0001",
            "representations": {
                "outcomes": [{"text": f"provider unavailable observed case {index}"}],
            },
            "narrative": f"provider unavailable observed case {index}",
        }
        conn.execute(
            "INSERT INTO episode_semantic_payloads(doc_rowid, payload_zlib) VALUES (?, ?)",
            (
                cursor.lastrowid,
                sqlite3.Binary(
                    module.zlib.compress(json.dumps(episode, separators=(",", ":")).encode("utf-8"))
                ),
            ),
        )
        conn.execute(
            """
            INSERT INTO episode_semantic_session_state (
                session_id, session_label, source_fingerprint, status,
                    episode_count, projection_version, indexed_at,
                    source_fingerprint_mode, route_signal_classifier_version,
                    generation_id, generation_identity_json
                ) VALUES (?, ?, ?, 'current', 1, ?, '2026-07-15T00:00:00Z', ?, ?, ?, ?)
            """,
            (
                session_id,
                session_id,
                f"fingerprint-{index}",
                module.EPISODE_SEMANTIC_PROJECTION_VERSION,
                    module.EPISODE_SEMANTIC_SOURCE_FINGERPRINT_MODE,
                    module.ROUTE_SIGNAL_CLASSIFIER_VERSION,
                    episode_generation["generation_id"],
                    json.dumps(
                        episode_generation,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                ),
        )
    conn.commit()
    conn.close()

    calls: list[list[str]] = []

    def unavailable_embed_texts(**kwargs: Any) -> dict[str, Any]:
        calls.append(list(kwargs.get("texts") or []))
        return {
            "ok": False,
            "status": "error",
            "vectors": [],
            "elapsed_ms": 1,
            "diagnostics": ["connection refused"],
        }

    monkeypatch.setattr(module, "episode_dense_embed_texts", unavailable_embed_texts)

    result = module.episode_dense_index_sessions(
        aoa_root=aoa_root,
        dirty_only=True,
        limit=2,
    )

    assert calls == [[module.EPISODE_DENSE_PROVIDER_PROBE_TEXT]]
    assert result["ok"] is False
    assert result["status"] == "deferred_provider_unavailable"
    assert result["selected_count"] == 2
    assert result["processed_count"] == 0
    assert result["successful_count"] == 0
    assert result["deferred_count"] == 2
    assert result["sessions"] == []
    assert result["provider_preflight"]["status"] == "provider_unavailable"
    assert module.episode_dense_optional_provider_unavailable(result) is True
def test_episode_dense_explicit_records_are_not_dropped_by_session_date_filter(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    aoa_root = tmp_path / ".aoa"
    session_id = "dense-active-session-with-older-start-date"
    db_path = module.search_db_path(aoa_root)
    episode_generation = (
        module.session_memory_expected_generation_identities(aoa_root)[
            "episode_semantic"
        ]
    )
    conn = module.init_search_db(db_path, rebuild=False, create_indexes=False)
    doc_id = f"episode_semantic:{session_id}:task-0001"
    cursor = conn.execute(
        """
        INSERT INTO episode_semantic_meta (
            doc_id, session_id, session_label, session_title, session_date,
            episode_id, preview, session_index_path, projection_version,
            generation_id
        ) VALUES (?, ?, ?, ?, '2026-07-12', 'task-0001', ?, ?, ?, ?)
        """,
        (
            doc_id,
            session_id,
            session_id,
            session_id,
            "active session changed after the hot window began",
            str(tmp_path / session_id / module.SESSION_INDEX_JSON),
            module.EPISODE_SEMANTIC_PROJECTION_VERSION,
            episode_generation["generation_id"],
        ),
    )
    episode = {
        "episode_id": "task-0001",
        "representations": {
            "outcomes": [{"text": "active session changed after the hot window began"}],
        },
        "narrative": "active session changed after the hot window began",
    }
    conn.execute(
        "INSERT INTO episode_semantic_payloads(doc_rowid, payload_zlib) VALUES (?, ?)",
        (
            cursor.lastrowid,
            sqlite3.Binary(
                module.zlib.compress(json.dumps(episode, separators=(",", ":")).encode("utf-8"))
            ),
        ),
    )
    conn.execute(
        """
        INSERT INTO episode_semantic_session_state (
            session_id, session_label, source_fingerprint, status,
                episode_count, projection_version, indexed_at,
                source_fingerprint_mode, route_signal_classifier_version,
                generation_id, generation_identity_json
            ) VALUES (?, ?, 'fingerprint', 'current', 1, ?, '2026-07-15T00:00:00Z', ?, ?, ?, ?)
        """,
        (
            session_id,
            session_id,
            module.EPISODE_SEMANTIC_PROJECTION_VERSION,
            module.EPISODE_SEMANTIC_SOURCE_FINGERPRINT_MODE,
            module.ROUTE_SIGNAL_CLASSIFIER_VERSION,
            episode_generation["generation_id"],
            json.dumps(
                episode_generation,
                sort_keys=True,
                separators=(",", ":"),
            ),
        ),
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(
        module,
        "episode_dense_embed_texts",
        lambda **_: {
            "ok": True,
            "status": "embedded",
            "vectors": [[0.0] * module.EPISODE_DENSE_DEFAULT_DIMENSION],
            "model": module.EPISODE_DENSE_DEFAULT_MODEL,
            "dimension": module.EPISODE_DENSE_DEFAULT_DIMENSION,
            "prompt_tokens": 1,
            "elapsed_ms": 1,
            "diagnostics": [],
        },
    )

    result = module.episode_dense_index_sessions(
        aoa_root=aoa_root,
        target="all",
        since="2026-07-13",
        selected_records=[{"session_id": session_id}],
        dirty_only=True,
    )

    assert result["ok"] is True
    assert result["selected_count"] == 1
    assert result["processed_count"] == 1
    assert result["successful_count"] == 1
    assert result["coverage"]["dirty_session_count"] == 0
def test_episode_dense_limited_repair_does_not_spend_slot_on_zero_episode_session(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    aoa_root = tmp_path / ".aoa"
    db_path = module.search_db_path(aoa_root)
    episode_generation = (
        module.session_memory_expected_generation_identities(aoa_root)[
            "episode_semantic"
        ]
    )
    conn = module.init_search_db(db_path, rebuild=False, create_indexes=False)
    zero_session_id = "dense-zero-episode-session"
    useful_session_id = "dense-useful-session"
    conn.execute(
        """
        INSERT INTO episode_semantic_session_state (
            session_id, session_label, source_fingerprint, status,
                episode_count, projection_version, indexed_at,
                source_fingerprint_mode, route_signal_classifier_version,
                generation_id, generation_identity_json
            ) VALUES (?, ?, 'zero-fingerprint', 'no_task_episodes', 0, ?,
                      '2026-05-01T00:00:00Z', ?, ?, ?, ?)
        """,
        (
            zero_session_id,
            zero_session_id,
            module.EPISODE_SEMANTIC_PROJECTION_VERSION,
            module.EPISODE_SEMANTIC_SOURCE_FINGERPRINT_MODE,
            module.ROUTE_SIGNAL_CLASSIFIER_VERSION,
            episode_generation["generation_id"],
            json.dumps(
                episode_generation,
                sort_keys=True,
                separators=(",", ":"),
            ),
        ),
    )
    useful_doc_id = f"episode_semantic:{useful_session_id}:task-0001"
    cursor = conn.execute(
        """
        INSERT INTO episode_semantic_meta (
            doc_id, session_id, session_label, session_title, session_date,
            episode_id, preview, session_index_path, projection_version,
            generation_id
        ) VALUES (?, ?, ?, ?, '2026-07-15', 'task-0001', ?, ?, ?, ?)
        """,
        (
            useful_doc_id,
            useful_session_id,
            useful_session_id,
            useful_session_id,
            "bounded useful episode",
            str(tmp_path / useful_session_id / module.SESSION_INDEX_JSON),
            module.EPISODE_SEMANTIC_PROJECTION_VERSION,
            episode_generation["generation_id"],
        ),
    )
    useful_episode = {
        "episode_id": "task-0001",
        "representations": {"outcomes": [{"text": "bounded useful episode"}]},
        "narrative": "bounded useful episode",
    }
    conn.execute(
        "INSERT INTO episode_semantic_payloads(doc_rowid, payload_zlib) VALUES (?, ?)",
        (
            cursor.lastrowid,
            sqlite3.Binary(
                module.zlib.compress(json.dumps(useful_episode, separators=(",", ":")).encode("utf-8"))
            ),
        ),
    )
    conn.execute(
        """
        INSERT INTO episode_semantic_session_state (
            session_id, session_label, source_fingerprint, status,
                episode_count, projection_version, indexed_at,
                source_fingerprint_mode, route_signal_classifier_version,
                generation_id, generation_identity_json
            ) VALUES (?, ?, 'useful-fingerprint', 'current', 1, ?,
                      '2026-07-15T00:00:00Z', ?, ?, ?, ?)
        """,
        (
            useful_session_id,
            useful_session_id,
            module.EPISODE_SEMANTIC_PROJECTION_VERSION,
            module.EPISODE_SEMANTIC_SOURCE_FINGERPRINT_MODE,
            module.ROUTE_SIGNAL_CLASSIFIER_VERSION,
            episode_generation["generation_id"],
            json.dumps(
                episode_generation,
                sort_keys=True,
                separators=(",", ":"),
            ),
        ),
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(
        module,
        "episode_dense_embed_texts",
        lambda **_: {
            "ok": True,
            "status": "embedded",
            "vectors": [[0.0] * (module.EPISODE_DENSE_DEFAULT_DIMENSION - 1) + [1.0]],
            "model": module.EPISODE_DENSE_DEFAULT_MODEL,
            "dimension": module.EPISODE_DENSE_DEFAULT_DIMENSION,
            "prompt_tokens": 1,
            "elapsed_ms": 1,
            "diagnostics": [],
        },
    )

    result = module.episode_dense_index_sessions(
        aoa_root=aoa_root,
        dirty_only=True,
        limit=1,
    )

    assert result["selected_count"] == 1
    assert result["sessions"][0]["session_id"] == useful_session_id
    assert result["sessions"][0]["vector_count"] == 1
    assert result["coverage"]["status"] == "current"
    assert result["coverage"]["dirty_session_count"] == 0
    assert result["coverage"]["implicit_no_task_session_count"] == 1
def test_episode_dense_repair_selection_balances_recent_cost_and_oldest_fairness() -> None:
    rows = [
        {
            "session_id": "old-heavy",
            "session_date": "2026-04-10",
            "indexed_at": "2026-07-01T00:00:00Z",
            "episode_count": 124,
        },
        {
            "session_id": "middle-warm",
            "session_date": "2026-07-10",
            "indexed_at": "2026-07-10T00:00:00Z",
            "episode_count": 55,
        },
        {
            "session_id": "recent-light",
            "session_date": "2026-07-15",
            "indexed_at": "2026-07-15T00:00:00Z",
            "episode_count": 8,
        },
        {
            "session_id": "older-light",
            "session_date": "2026-07-13",
            "indexed_at": "2026-07-13T00:00:00Z",
            "episode_count": 1,
        },
    ]

    selected, selection = module.episode_dense_repair_selection(rows, limit=2)

    assert [row["session_id"] for row in selected] == ["recent-light", "old-heavy"]
    assert selection["policy"] == "cost_class_then_recent_with_oldest_fairness_v1"
    assert selection["oldest_fairness_reserved"] is True
    assert selection["oldest_fairness_session_id"] == "old-heavy"
    assert selection["candidate_cost_class_counts"] == {"heavy": 1, "light": 2, "warm": 1}
def test_episode_dense_repair_selection_prioritizes_same_cycle_upstream_change() -> None:
    rows = [
        {
            "session_id": "same-cycle-heavy",
            "session_date": "2026-07-10",
            "indexed_at": "2026-07-15T12:08:42Z",
            "episode_count": 68,
        },
        {
            "session_id": "unrelated-warm-backlog",
            "session_date": "2026-07-15",
            "indexed_at": "2026-07-15T12:00:00Z",
            "episode_count": 55,
        },
    ]

    selected, selection = module.episode_dense_repair_selection(
        rows,
        limit=1,
        priority_session_ids=["same-cycle-heavy"],
    )

    assert [row["session_id"] for row in selected] == ["same-cycle-heavy"]
    assert selection["policy"] == "same_cycle_dependency_then_cost_recent_fairness_v2"
    assert selection["selected_priority_session_ids"] == ["same-cycle-heavy"]
    assert selection["deferred_priority_session_ids"] == []
    assert selection["selected_cost_class_counts"] == {"heavy": 1}
def test_search_repair_selection_defers_observed_hot_heavy_cost_without_hiding_backlog() -> None:
    records = [
        {
            "session_id": "old-heavy",
            "session_label": "2026-06-18__003__old-heavy",
            "session_date": "2026-06-18",
        },
        {
            "session_id": "recent-warm",
            "session_label": "2026-07-10__046__recent-warm",
            "session_date": "2026-07-10",
        },
    ]
    dirty_sessions = [
        {
            "session_id": "old-heavy",
            "session_label": "2026-06-18__003__old-heavy",
            "estimated_raw_bytes": 245_634_536,
            "indexed_document_count": 138_723,
            "source_path_count": 439,
            "latest_source_mtime": 100.0,
        },
        {
            "session_id": "recent-warm",
            "session_label": "2026-07-10__046__recent-warm",
            "estimated_raw_bytes": 126_883_615,
            "indexed_document_count": 51_999,
            "source_path_count": 254,
            "latest_source_mtime": 200.0,
        },
    ]

    selected, selection = module.search_repair_selection(
        records,
        dirty_sessions=dirty_sessions,
        limit=4,
        max_cost_class="warm",
    )

    assert [record["session_id"] for record in selected] == ["recent-warm"]
    assert selection["policy"] == "cost_class_then_recent_with_profile_cost_gate_v1"
    assert selection["candidate_cost_class_counts"] == {"heavy": 1, "warm": 1}
    assert selection["selected_cost_class_counts"] == {"warm": 1}
    assert selection["deferred_cost_class_counts"] == {"heavy": 1}
    assert selection["deferred_cost_session_ids"] == ["old-heavy"]
    assert selection["remaining_session_ids"] == ["old-heavy"]
    assert selection["remaining_count"] == 1
def test_query_demand_projection_accepts_structured_cli_and_mcp_but_rejects_text_noise(
    tmp_path: Path,
) -> None:
    query_session_id = "019f540f-e0c9-78e3-8b0d-25747abc932a"
    cli_target = "019e9fc1-e993-72e0-8e5a-4558f65096cf"
    mcp_target = "019e1545-f43c-77f3-a31b-2d11dc2ca568"
    namespaced_mcp_target = "019e8eff-975c-7980-a114-b7637179bcbb"
    noise_target = "019e22f3-7322-7892-b919-cc260e5811a6"
    transcript = tmp_path / f"rollout-{query_session_id}.jsonl"
    rows = [
        {
            "timestamp": "2026-07-15T15:00:00Z",
            "type": "response_item",
            "payload": {
                "type": "custom_tool_call",
                "name": "exec",
                "call_id": "call-cli",
                "input": (
                    "const r = await tools.exec_command({"
                    "cmd: \"PYTHONDONTWRITEBYTECODE=1 python3 scripts/aoa_session_memory.py "
                    f"semantic-episode-search --query 'cache cleanup' --session {cli_target}\""
                    "}); text(r.output);"
                ),
            },
        },
        {
            "timestamp": "2026-07-15T15:01:00Z",
            "type": "response_item",
            "payload": {
                "type": "custom_tool_call",
                "name": "exec",
                "call_id": "call-mcp",
                "input": (
                    "const r = await "
                    "tools.mcp__aoa_session_memory__aoa_session_literal_query_plan({"
                    f"query: 'cache cleanup', filters: {{session_id: '{mcp_target}'}}"
                    "}); text(r.structuredContent);"
                ),
            },
        },
        {
            "timestamp": "2026-07-15T15:01:30Z",
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "aoa_session_entity_usage_chain",
                "namespace": "mcp__aoa_session_memory",
                "call_id": "call-namespaced-mcp",
                "arguments": json.dumps(
                    {
                        "anchor": "imagegen",
                        "kind": "skill",
                        "session": namespaced_mcp_target,
                    }
                ),
            },
        },
        {
            "timestamp": "2026-07-15T15:01:45Z",
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "aoa_session_entity_usage_chain",
                "namespace": "mcp__unrelated",
                "call_id": "call-foreign-namespace-noise",
                "arguments": json.dumps({"session": noise_target}),
            },
        },
        {
            "timestamp": "2026-07-15T15:02:00Z",
            "type": "response_item",
            "payload": {
                "type": "custom_tool_call",
                "name": "exec",
                "call_id": "call-inspection-noise",
                "input": (
                    "const r = await tools.exec_command({"
                    "cmd: \"jq -r 'capture(\\\"aoa_session_memory.py (?<command>[a-z-]+)\\\")' "
                    f"transcript.jsonl | rg '{noise_target}'\""
                    "}); text(r.output);"
                ),
            },
        },
        {
            "timestamp": "2026-07-15T15:03:00Z",
            "type": "response_item",
            "payload": {
                "type": "custom_tool_call",
                "name": "exec",
                "call_id": "call-string-noise",
                "input": (
                    "text(\"tools.mcp__aoa_session_memory__aoa_session_search("
                    f"{{filters:{{session_id:'{noise_target}'}}}})\");"
                ),
            },
        },
        {
            "timestamp": "2026-07-15T15:04:00Z",
            "type": "response_item",
            "payload": {
                "type": "custom_tool_call_output",
                "call_id": "call-output-noise",
                "output": (
                    "python3 scripts/aoa_session_memory.py search --session "
                    f"{noise_target}"
                ),
            },
        },
    ]
    transcript.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    records = [
        {
            "session_id": query_session_id,
            "session_label": "2026-07-15__query-session",
            "transcript_path": str(transcript),
        },
        {"session_id": cli_target, "session_label": "2026-06-07__cli-target"},
        {"session_id": mcp_target, "session_label": "2026-05-12__mcp-target"},
        {
            "session_id": namespaced_mcp_target,
            "session_label": "2026-06-03__namespaced-mcp-target",
        },
        {"session_id": noise_target, "session_label": "2026-04-20__noise-target"},
    ]

    projection = module.session_memory_query_demand_projection(
        records,
        now_epoch=datetime(2026, 7, 15, 15, 5, tzinfo=timezone.utc).timestamp(),
        ttl_seconds=6 * 60 * 60,
        max_source_files=4,
        max_tail_bytes=1024 * 1024,
    )

    assert projection["status"] == "observed"
    assert projection["classifier_version"] == 2
    assert projection["priority_session_ids"] == [
        namespaced_mcp_target,
        mcp_target,
        cli_target,
    ]
    assert projection["demand_counts"] == {
        cli_target: 1,
        mcp_target: 1,
        namespaced_mcp_target: 1,
    }
    assert projection["rejected_text_noise_count"] == 2
    assert {item["access_plane"] for item in projection["evidence"]} == {"cli", "mcp"}
    assert all(item["raw_ref"].startswith("raw:line:") for item in projection["evidence"])
    assert noise_target not in projection["priority_session_ids"]
def test_query_demand_cli_accepts_invocation_after_shell_loop_do() -> None:
    target = "019f4d69-2d3b-7c82-8f35-cd9cc061b2f4"
    command = (
        "for query in 'first' 'second'; do "
        "python3 scripts/aoa_session_memory.py search "
        f"--session {target} --query \"$query\"; "
        "done"
    )

    assert module.session_memory_query_demand_cli_targets(
        command,
        alias_to_session_id={target: target},
    ) == [
        {
            "session_id": target,
            "route": "search",
            "access_plane": "cli",
        }
    ]
def test_search_repair_selection_reserves_query_demand_before_oldest_fairness() -> None:
    records = [
        {
            "session_id": "oldest-light",
            "session_label": "2026-04-01__oldest-light",
            "session_date": "2026-04-01",
        },
        {
            "session_id": "recent-light",
            "session_label": "2026-07-15__recent-light",
            "session_date": "2026-07-15",
        },
        {
            "session_id": "demanded-light",
            "session_label": "2026-06-07__demanded-light",
            "session_date": "2026-06-07",
        },
        {
            "session_id": "demanded-heavy",
            "session_label": "2026-06-08__demanded-heavy",
            "session_date": "2026-06-08",
        },
    ]
    dirty_sessions = [
        {
            "session_id": session_id,
            "session_label": next(
                record["session_label"] for record in records if record["session_id"] == session_id
            ),
            "estimated_raw_bytes": 300_000_000 if session_id == "demanded-heavy" else 2_000_000,
            "indexed_document_count": 100_000 if session_id == "demanded-heavy" else 100,
            "source_path_count": 400 if session_id == "demanded-heavy" else 2,
        }
        for session_id in (
            "oldest-light",
            "recent-light",
            "demanded-light",
            "demanded-heavy",
        )
    ]

    selected, selection = module.search_repair_selection(
        records,
        dirty_sessions=dirty_sessions,
        limit=1,
        max_cost_class="warm",
        priority_session_ids=["already-current", "demanded-light", "demanded-heavy"],
    )

    assert [record["session_id"] for record in selected] == ["demanded-light"]
    assert selection["policy"] == "query_demand_then_cost_recent_fairness_v2"
    assert selection["priority_not_candidate_session_ids"] == ["already-current"]
    assert selection["selected_priority_session_ids"] == ["demanded-light"]
    assert selection["deferred_priority_cost_session_ids"] == ["demanded-heavy"]
    assert selection["oldest_fairness_reserved"] is False
    assert "demanded-heavy" in selection["remaining_session_ids"]
def test_episode_semantic_queue_selection_keeps_query_demand_ahead_of_heavy_fairness() -> None:
    now = "2026-07-15T15:05:00Z"
    rows = [
        {
            "session_id": "demanded-warm",
            "cost_class": "warm",
            "demand_count": 3,
            "priority_score": 100.0,
            "first_enqueued_at": "2026-07-15T14:00:00Z",
            "estimated_raw_bytes": 20_000_000,
            "session_label": "demanded-warm",
        },
        {
            "session_id": "recent-light",
            "cost_class": "light",
            "demand_count": 0,
            "priority_score": 150.0,
            "first_enqueued_at": "2026-07-15T14:30:00Z",
            "estimated_raw_bytes": 1_000_000,
            "session_label": "recent-light",
        },
        {
            "session_id": "aged-heavy",
            "cost_class": "heavy",
            "demand_count": 0,
            "priority_score": 90.0,
            "first_enqueued_at": "2026-07-15T06:00:00Z",
            "estimated_raw_bytes": 400_000_000,
            "session_label": "aged-heavy",
        },
    ]

    selected, selection = module.episode_semantic_queue_selection(
        rows,
        limit=1,
        allow_cost_classes={"light", "warm", "heavy"},
        now=now,
    )

    assert [row["session_id"] for row in selected] == ["demanded-warm"]
    assert selection["selected_query_demand_session_ids"] == ["demanded-warm"]
    assert selection["aged_heavy_fairness_reserved"] is False

    selected_same_cycle, same_cycle_selection = module.episode_semantic_queue_selection(
        rows,
        limit=1,
        allow_cost_classes={"light", "warm", "heavy"},
        now=now,
        priority_session_ids=["recent-light"],
    )
    assert [row["session_id"] for row in selected_same_cycle] == ["recent-light"]
    assert same_cycle_selection["policy"] == (
        "same_cycle_dependency_then_query_demand_projection_priority_cost_fairness_v3"
    )
    assert same_cycle_selection["selected_priority_session_ids"] == ["recent-light"]
    assert same_cycle_selection["deferred_priority_session_ids"] == []

    no_demand_rows = [{**row, "demand_count": 0} for row in rows]
    selected_without_demand, selection_without_demand = module.episode_semantic_queue_selection(
        no_demand_rows,
        limit=1,
        allow_cost_classes={"light", "warm", "heavy"},
        now=now,
    )

    assert [row["session_id"] for row in selected_without_demand] == ["aged-heavy"]
    assert selection_without_demand["aged_heavy_fairness_reserved"] is True
def test_graph_maintenance_sort_keeps_query_demand_ahead_of_cheaper_backlog() -> None:
    demanded = {
        "source_key": "segment:demanded",
        "session_id": "demanded-session",
        "stored_edge_count": 200,
        "stored_node_count": 100,
        "source_size_bytes": 2_000_000,
    }
    cheap = {
        "source_key": "segment:cheap",
        "session_id": "cheap-session",
        "stored_edge_count": 1,
        "stored_node_count": 1,
        "source_size_bytes": 100,
    }

    baseline = sorted(
        [demanded, cheap],
        key=module.graph_maintenance_actionable_sort_key,
    )
    candidate = sorted(
        [demanded, cheap],
        key=lambda item: module.graph_maintenance_priority_sort_key(
            item,
            {"demanded-session": 0},
        ),
    )

    assert [item["session_id"] for item in baseline] == ["cheap-session", "demanded-session"]
    assert [item["session_id"] for item in candidate] == ["demanded-session", "cheap-session"]
def test_search_repair_selection_waits_for_live_capture_before_reindexing_matching_archive() -> None:
    records = [
        {
            "session_id": "stale-live-only",
            "session_label": "2026-06-18__003__stale-live-only",
            "session_date": "2026-06-18",
        },
        {
            "session_id": "stale-archive-and-live",
            "session_label": "2026-07-10__046__stale-archive-and-live",
            "session_date": "2026-07-10",
        },
    ]
    dirty_sessions = [
        {
            "session_id": "stale-live-only",
            "session_label": "2026-06-18__003__stale-live-only",
            "estimated_raw_bytes": 126_883_615,
            "indexed_document_count": 51_999,
            "source_path_count": 254,
            "reasons": ["live_source_snapshot_changed"],
        },
        {
            "session_id": "stale-archive-and-live",
            "session_label": "2026-07-10__046__stale-archive-and-live",
            "estimated_raw_bytes": 8_000_000,
            "indexed_document_count": 1_000,
            "source_path_count": 20,
            "reasons": ["source_fingerprint_changed", "live_source_snapshot_changed"],
        },
    ]

    selected, selection = module.search_repair_selection(
        records,
        dirty_sessions=dirty_sessions,
        limit=4,
        max_cost_class="warm",
    )

    assert [record["session_id"] for record in selected] == ["stale-archive-and-live"]
    assert selection["upstream_deferred_count"] == 1
    assert selection["upstream_deferred_session_ids"] == ["stale-live-only"]
    assert selection["upstream_dependency"] == "raw_capture_before_search_repair"
    assert selection["remaining_session_ids"] == ["stale-live-only"]
def test_route_projection_coherence_defers_capture_stale_after_archived_search_repair() -> None:
    session_id = "archived-repaired-live-capture-stale"
    action_results = [
        {
            "id": "rebuild_search_index",
            "status": "applied",
            "result": {
                "ok": True,
                "completed_session_ids": [session_id],
            },
        },
        {
            "id": "refresh_episode_semantic_projection",
            "status": "applied",
            "result": {"completed_session_ids": [session_id]},
        },
        {
            "id": "rebuild_agent_atlas",
            "status": "applied",
            "result": {"completed_session_ids": [session_id]},
        },
    ]

    coherence = module.route_projection_dependency_coherence(
        action_results=action_results,
        final_search_state={
            "status": "stale",
            "dirty_session_ids": [session_id],
            "dirty_sessions": [
                {
                    "session_id": session_id,
                    "reasons": ["live_source_snapshot_changed"],
                    "live_source_status": "stale",
                }
            ],
        },
        final_episode_semantic_state={
            "status": "current",
            "dirty_session_ids": [],
        },
        final_atlas_state={
            "status": "current",
            "dirty_session_ids": [],
        },
        final_snapshot_captured=True,
        upstream_changed_session_ids=[session_id],
    )

    assert coherence["status"] == "remaining"
    assert coherence["deferred_by_projection"]["search"] == [session_id]
    assert coherence["upstream_capture_deferred_by_projection"]["search"] == [
        session_id
    ]
    assert coherence["completed_but_dirty_by_projection"]["search"] == []
    assert coherence["diagnostics"] == []

    true_search_regression = module.route_projection_dependency_coherence(
        action_results=action_results,
        final_search_state={
            "status": "stale",
            "dirty_session_ids": [session_id],
            "dirty_sessions": [
                {
                    "session_id": session_id,
                    "reasons": ["source_fingerprint_changed"],
                    "live_source_status": "fresh",
                }
            ],
        },
        final_episode_semantic_state={
            "status": "current",
            "dirty_session_ids": [],
        },
        final_atlas_state={
            "status": "current",
            "dirty_session_ids": [],
        },
        final_snapshot_captured=True,
        upstream_changed_session_ids=[session_id],
    )

    assert true_search_regression["status"] == "failed"
    assert true_search_regression["completed_but_dirty_by_projection"][
        "search"
    ] == [session_id]
    assert true_search_regression["diagnostics"] == [
        f"route_projection_completed_session_still_dirty:search:{session_id}"
    ]
def test_index_maintenance_reports_capture_deferral_after_archived_search_repair(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "AbyssOS"
    repo = workspace / "aoa-session-memory"
    repo.mkdir(parents=True)
    aoa_root = workspace / ".aoa"
    session_id = "archived-repaired-live-capture-stale"
    transcript = tmp_path / f"rollout-2026-06-18T00-00-00-{session_id}.jsonl"
    write_jsonl(
        transcript,
        [
            {
                "timestamp": "2026-06-18T00:00:00Z",
                "type": "session_meta",
                "payload": {"id": session_id, "cwd": str(repo)},
            },
            {
                "timestamp": "2026-06-18T00:00:01Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "Initial archive"}],
                },
            },
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": session_id,
            "transcript_path": str(transcript),
            "cwd": str(repo),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )
    module.search_index_sessions(aoa_root=aoa_root, target="all")
    module.build_agent_atlas(aoa_root=aoa_root, target="all")

    with transcript.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "timestamp": "2026-06-18T00:00:02Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {
                                "type": "output_text",
                                "text": "Archived semantic change requiring search repair.",
                            }
                        ],
                    },
                }
            )
            + "\n"
        )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": session_id,
            "transcript_path": str(transcript),
            "cwd": str(repo),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )
    record = module.resolve_session_record(aoa_root, session_id)
    session_index_path = (
        module.session_dir_from_record(record) / module.SESSION_INDEX_JSON
    )
    session_index = module.read_json(session_index_path, {})
    session_index["task_episode_schema_version"] = (
        module.TASK_EPISODE_SCHEMA_VERSION - 1
    )
    module.write_json(session_index_path, session_index)
    with transcript.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "timestamp": "2026-06-18T00:00:03Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {
                                "type": "output_text",
                                "text": "Live source changed after archive capture.",
                            }
                        ],
                    },
                }
            )
            + "\n"
        )

    applied = module.maintain_indexes(
        aoa_root=aoa_root,
        target="all",
        repair_limit=1,
        search_repair_limit=1,
        route_max_raw_bytes=1024 * 1024,
        repair_graph=False,
        repair_token_accounting=False,
        apply=True,
    )
    actions = {action["id"]: action for action in applied["actions"]}
    search_action = actions["rebuild_search_index"]

    assert applied["ok"] is True, json.dumps(applied, ensure_ascii=False, indent=2)
    assert search_action["status"] == "applied_partial_upstream_capture_deferred"
    assert search_action["upstream_capture_deferred_session_ids"] == [session_id]
    assert search_action["result"]["upstream_capture_deferred_session_ids"] == [
        session_id
    ]
    coherence = applied["route_projection_dependency_coherence"]
    assert coherence["status"] == "remaining"
    assert coherence["upstream_capture_deferred_by_projection"]["search"] == [
        session_id
    ]
    final_dirty = {
        item["session_id"]: item
        for item in applied["final_search_index"]["dirty_sessions"]
    }
    assert final_dirty[session_id]["reasons"] == ["live_source_snapshot_changed"]
def test_hot_profile_bounds_search_repair_while_catchup_accepts_heavy_backlog() -> None:
    hot = module.auto_maintenance_profile("hot")
    catchup = module.auto_maintenance_profile("catchup")

    assert hot["search_repair_limit"] == 4
    assert hot["search_shard_repair_limit"] == 4
    assert hot["search_max_cost_class"] == "warm"
    assert catchup["search_repair_limit"] == 25
    assert catchup["search_shard_repair_limit"] == 24
    assert catchup["search_max_cost_class"] == "heavy"
    assert catchup["episode_max_cost_class"] == "heavy"
def test_catchup_general_repair_override_keeps_independent_search_shard_batch(
    tmp_path: Path, monkeypatch: Any
) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    aoa_root.mkdir(parents=True)
    calls: dict[str, Any] = {}
    freshness = {
        "ok": False,
        "target": "all",
        "selected_count": 3,
        "needs_index_maintenance": True,
        "needs_graph_maintenance": False,
        "search_index": {
            "status": "stale",
            "has_documents": True,
            "has_route_index": True,
            "has_route_terms": True,
            "search_schema_version": str(module.SEARCH_SCHEMA_VERSION),
            "expected_search_schema_version": module.SEARCH_SCHEMA_VERSION,
            "reasons": ["session_projection_dirty"],
            "diagnostics": [],
        },
        "diagnostics": ["index_maintenance_needed"],
    }

    def fake_maintenance(**kwargs: Any) -> dict[str, Any]:
        calls["maintenance"] = kwargs
        return {
            "ok": True,
            "apply": kwargs["apply"],
            "target": kwargs["target"],
            "selected_count": 3,
            "repair_indexes": kwargs["repair_indexes"],
            "repair_graph": kwargs["repair_graph"],
            "repair_limit": kwargs["repair_limit"],
            "search_repair_limit": kwargs["search_repair_limit"],
            "search_shard_repair_limit": kwargs[
                "search_shard_repair_limit"
            ],
            "action_counts": {"applied": 1},
            "diagnostics": [],
        }

    monkeypatch.setattr(
        module,
        "route_cache_freshness_gates",
        lambda **_kwargs: json.loads(json.dumps(freshness)),
    )
    monkeypatch.setattr(
        module,
        "graph_freshness_gates",
        lambda **_kwargs: json.loads(json.dumps(freshness)),
    )
    monkeypatch.setattr(module, "maintain_indexes", fake_maintenance)

    payload = module.auto_maintenance(
        workspace_root=workspace,
        aoa_root=aoa_root,
        profile="catchup",
        repair_limit=3,
        apply=True,
    )

    assert payload["repair_limit"] == 3
    assert payload["search_repair_limit"] == 3
    assert payload["search_shard_repair_limit"] == 24
    assert calls["maintenance"]["repair_limit"] == 3
    assert calls["maintenance"]["search_repair_limit"] == 3
    assert calls["maintenance"]["search_shard_repair_limit"] == 24
def test_episode_dense_post_write_coherence_rejects_completed_session_still_dirty() -> None:
    action_results = [
        {
            "id": "refresh_episode_dense_projection",
            "status": "applied",
            "result": {
                "successful_count": 1,
                "completed_session_ids": ["dense-lost-session"],
            },
        }
    ]

    failed = module.episode_dense_post_write_coherence(
        action_results=action_results,
        final_dense_state={
            "status": "partial",
            "dirty_session_count": 1,
            "dirty_session_ids": ["dense-lost-session"],
        },
        final_snapshot_captured=True,
    )
    passed = module.episode_dense_post_write_coherence(
        action_results=action_results,
        final_dense_state={
            "status": "current",
            "dirty_session_count": 0,
            "dirty_session_ids": [],
        },
        final_snapshot_captured=True,
    )
    not_applicable = module.episode_dense_post_write_coherence(
        action_results=[
            {
                "id": "refresh_episode_dense_projection",
                "status": "deferred_optional_provider_unavailable",
                "result": {"completed_session_ids": None},
            }
        ],
        final_dense_state={
            "status": "partial",
            "dirty_session_count": 1,
            "dirty_session_ids": ["dense-pending-session"],
        },
        final_snapshot_captured=True,
    )
    unavailable = module.episode_dense_post_write_coherence(
        action_results=action_results,
        final_dense_state={
            "status": "sqlite_locked",
            "dirty_session_count": 0,
            "dirty_session_ids": [],
            "diagnostics": ["database is locked"],
        },
        final_snapshot_captured=True,
    )
    upstream_not_restored = module.episode_dense_post_write_coherence(
        action_results=[
            {
                "id": "refresh_episode_dense_projection",
                "status": "applied_partial",
                "result": {
                    "completed_session_ids": ["unrelated-backlog-session"],
                    "selection": {
                        "selected_session_ids": ["unrelated-backlog-session"],
                        "selected_priority_session_ids": [],
                        "deferred_priority_session_ids": [],
                    },
                },
            }
        ],
        final_dense_state={
            "status": "partial",
            "dirty_session_count": 1,
            "dirty_session_ids": ["same-cycle-upstream-session"],
        },
        final_snapshot_captured=True,
        upstream_changed_session_ids=["same-cycle-upstream-session"],
    )
    upstream_deferred_by_bound = module.episode_dense_post_write_coherence(
        action_results=[
            {
                "id": "refresh_episode_dense_projection",
                "status": "applied_partial",
                "result": {
                    "completed_session_ids": ["priority-a"],
                    "selection": {
                        "selected_priority_session_ids": ["priority-a"],
                        "deferred_priority_session_ids": ["priority-b"],
                    },
                },
            }
        ],
        final_dense_state={
            "status": "partial",
            "dirty_session_count": 1,
            "dirty_session_ids": ["priority-b"],
        },
        final_snapshot_captured=True,
        upstream_changed_session_ids=["priority-a", "priority-b"],
    )

    assert failed["status"] == "failed"
    assert failed["lost_completed_session_ids"] == ["dense-lost-session"]
    assert failed["diagnostics"] == ["episode_dense_completed_session_still_dirty:dense-lost-session"]
    assert passed["status"] == "passed"
    assert passed["lost_completed_session_ids"] == []
    assert not_applicable["status"] == "not_applicable"
    assert not_applicable["completed_session_ids"] == []
    assert unavailable["status"] == "unverified"
    assert unavailable["diagnostics"] == ["episode_dense_post_write_coherence_unverified"]
    assert upstream_not_restored["status"] == "failed"
    assert upstream_not_restored["unrestored_upstream_session_ids"] == [
        "same-cycle-upstream-session"
    ]
    assert upstream_not_restored["diagnostics"] == [
        "episode_dense_upstream_session_not_restored:same-cycle-upstream-session"
    ]
    assert upstream_deferred_by_bound["status"] == "remaining"
    assert upstream_deferred_by_bound["deferred_upstream_session_ids"] == ["priority-b"]
    assert upstream_deferred_by_bound["diagnostics"] == []
def test_episode_dense_document_keeps_several_recent_evidence_items() -> None:
    episode = {
        "representations": {
            "verification": [
                {"text": ("old-noise " * 90) + f"verification-marker-{index}"}
                for index in range(5)
            ]
        }
    }

    document = module.episode_dense_document(episode)

    assert "verification-marker-0" not in document
    assert all(f"verification-marker-{index}" in document for index in range(1, 5))
    assert len(document) <= module.EPISODE_DENSE_DOCUMENT_MAX_CHARS
def test_episode_dense_representation_documents_are_stable_bounded_and_raw_ref_backed() -> None:
    entries = [
        {
            "text": f"verification evidence {index}",
            "refs": {
                "raw": f"raw:line:{index}",
                "segment": f"sessions/representation/segments/{index}.json",
                "session": "sessions/representation/session.json",
            },
            "source_lane": "assistant",
            "admission_basis": "verification_observation",
            "outcome": "success",
        }
        for index in range(1, 7)
    ]
    entries.insert(
        0,
        {
            "text": "projection text without a raw ref must not be embedded",
            "refs": {"segment": "sessions/representation/segments/0.json"},
        },
    )
    episode = {"representations": {"verification": entries}}

    first = module.episode_dense_representation_documents(
        episode,
        doc_id="episode_semantic:representation:task-0001",
        session_id="representation",
        episode_id="task-0001",
    )
    second = module.episode_dense_representation_documents(
        copy.deepcopy(episode),
        doc_id="episode_semantic:representation:task-0001",
        session_id="representation",
        episode_id="task-0001",
    )

    assert first == second
    assert len(first) == module.EPISODE_DENSE_REPRESENTATION_PER_ROLE_LIMIT
    assert [item["raw_ref"] for item in first] == [
        "raw:line:3",
        "raw:line:4",
        "raw:line:5",
        "raw:line:6",
    ]
    assert all(
        len(item["document"])
        <= module.EPISODE_DENSE_REPRESENTATION_TEXT_MAX_CHARS + 160
        for item in first
    )
def test_episode_dense_representation_match_selection_preserves_primary_and_adds_distinct_roles() -> None:
    candidates = [
        {
            "representation_id": f"rep-{index}",
            "role": role,
            "raw_ref": f"raw:line:{40 + index}",
            "score": round(0.99 - index / 100, 2),
            "rank_within_episode": index,
        }
        for index, role in enumerate(
            (
                "actions",
                "actions",
                "outcomes",
                "outcomes",
                "failures",
                "verification",
            ),
            start=1,
        )
    ]

    selected = module.episode_dense_select_representation_matches(
        candidates
    )

    assert [item["representation_id"] for item in selected] == [
        "rep-1",
        "rep-2",
        "rep-3",
        "rep-5",
    ]
    assert [item["selection_basis"] for item in selected] == [
        "primary_similarity",
        "primary_similarity",
        "role_diversity",
        "role_diversity",
    ]
    assert [item["rank_within_episode"] for item in selected] == [
        1,
        2,
        3,
        5,
    ]
    assert len(selected) == (
        module.EPISODE_DENSE_REPRESENTATION_MATCH_LIMIT
    )
def test_episode_dense_representation_support_hydrates_distinct_raw_refs_only() -> None:
    raw_one = "raw:line:40"
    raw_two = "raw:line:41"
    episode = {
        "representations": {
            "actions": [
                {
                    "text": "ran the bounded command",
                    "refs": {"raw": raw_one},
                    "admission_basis": "structured_operational_action",
                }
            ],
            "verification": [
                {
                    "text": "verified the bounded outcome",
                    "refs": {"raw": raw_two},
                    "admission_basis": "verification_observation",
                }
            ],
        }
    }
    matches = [
        {
            "representation_id": "rep-one",
            "role": "actions",
            "raw_ref": raw_one,
            "score": 0.91,
            "rank_within_episode": 1,
        },
        {
            "representation_id": "rep-one-duplicate",
            "role": "actions",
            "raw_ref": raw_one,
            "score": 0.90,
            "rank_within_episode": 2,
        },
        {
            "representation_id": "rep-two",
            "role": "verification",
            "raw_ref": raw_two,
            "score": 0.89,
            "rank_within_episode": 3,
        },
    ]

    result = module.episode_dense_hydrate_result_support(
        {
            "supporting_evidence": [
                {
                    "role": "outcomes",
                    "text": "duplicate existing evidence",
                    "refs": {"raw": raw_one},
                }
            ]
        },
        episode,
        matches,
    )

    returned_raw_refs = [
        str(item.get("refs", {}).get("raw") or "")
        for item in result["supporting_evidence"]
    ]
    assert returned_raw_refs == [raw_one, raw_two]
    assert all(
        item["dense_representation"]["truth_status"]
        == "dense_representation_navigation_not_claim_truth"
        for item in result["supporting_evidence"]
    )
def test_episode_dense_projection_state_remains_readable_during_search_writer(tmp_path: Path) -> None:
    aoa_root = tmp_path / ".aoa"
    db_path = module.search_db_path(aoa_root)
    initial = module.init_search_db(db_path, rebuild=False, create_indexes=False)
    initial.close()

    writer: sqlite3.Connection | None = None
    try:
        writer = module.init_search_db(db_path, rebuild=False, create_indexes=False)
        assert str(writer.execute("PRAGMA journal_mode").fetchone()[0]).lower() == "wal"
        writer.execute("BEGIN EXCLUSIVE")
        writer.execute("INSERT OR REPLACE INTO meta(key, value) VALUES ('dense_state_writer_probe', 'open')")

        state = module.episode_dense_projection_state(aoa_root)
    finally:
        if writer is not None:
            writer.rollback()
            writer.close()

    assert state["status"] == "empty"
    assert state["diagnostics"] == []
    assert state["truth_status"] == "dense_state_compared_to_current_episode_projection"
def test_task_episode_bounded_sequences_keep_head_and_moving_tail() -> None:
    items: list[int] = []
    displaced = 0
    for index in range(100):
        displaced += int(module.bounded_head_tail_append(items, index, limit=80))

    assert displaced == 20
    assert items[:20] == list(range(20))
    assert items[20:] == list(range(40, 100))

    representations = module.task_episode_select_representations(
        [
            {
                "text": f"action-{index}",
                "score": 90,
                "line": index,
                "evidence_role": "actions",
            }
            for index in range(100)
        ],
        limit=28,
    )
    selected_lines = [item["line"] for item in representations]
    assert selected_lines[:3] == [0, 1, 2]
    assert selected_lines[-14:] == list(range(86, 100))
def test_decisive_sparse_evidence_anchor_survives_two_weak_rrf_votes() -> None:
    ranked = [
        {
            "doc_id": "episode:truth",
            "rerank_score": 205.0,
            "query_coverage": {"coverage": 1.0, "matched_term_count": 10},
            "supporting_evidence": [{"matched_query_terms": [f"term-{index}" for index in range(7)]}],
        },
        {
            "doc_id": "episode:neighbor",
            "rerank_score": 185.0,
            "query_coverage": {"coverage": 0.9, "matched_term_count": 9},
            "supporting_evidence": [{"matched_query_terms": ["term-1", "term-2"]}],
        },
    ]

    decision = module.episode_sparse_anchor_decision(ranked)
    anchored_score, bonus = module.episode_hybrid_rrf_score(
        sparse_rank=1,
        dense_rank=None,
        sparse_anchor=decision["active"],
    )
    weak_consensus_score, _ = module.episode_hybrid_rrf_score(
        sparse_rank=2,
        dense_rank=1,
    )

    assert decision["status"] == "decisive_coherent_sparse_evidence"
    assert bonus > 0
    assert anchored_score > weak_consensus_score
    ranked[0]["rerank_score"] = 190.0
    assert module.episode_sparse_anchor_decision(ranked)["active"] is False
def test_dense_top_missing_from_sparse_candidates_survives_mechanical_rrf_consensus() -> None:
    dense_ranking = [
        {"doc_id": "episode:dense-truth", "rank": 1, "score": 0.82},
        {"doc_id": "episode:lexical-neighbor", "rank": 2, "score": 0.79},
    ]
    sparse_ranks = {"episode:lexical-neighbor": 1}

    decision = module.episode_dense_recall_guard_decision(
        dense_ranking,
        sparse_ranks,
        sparse_anchor={"active": False},
        temporal_sparse_anchor={"active": False},
    )
    dense_top_score, _ = module.episode_hybrid_rrf_score(
        sparse_rank=None,
        dense_rank=1,
    )
    guarded_dense_top_score = (
        dense_top_score + decision["bonus"]
    )
    weak_consensus_score, _ = module.episode_hybrid_rrf_score(
        sparse_rank=1,
        dense_rank=2,
    )

    assert decision["active"] is True
    assert decision["status"] == (
        "dense_top_absent_from_sparse_candidates"
    )
    assert decision["claim_admission"] is False
    assert guarded_dense_top_score > weak_consensus_score

    shared = module.episode_dense_recall_guard_decision(
        dense_ranking,
        {
            "episode:dense-truth": 2,
            "episode:lexical-neighbor": 1,
        },
    )
    assert shared["active"] is False
    assert shared["status"] == "dense_top_also_has_sparse_vote"

    typed_sparse = module.episode_dense_recall_guard_decision(
        dense_ranking,
        sparse_ranks,
        sparse_anchor={"active": True},
    )
    assert typed_sparse["active"] is False
    assert typed_sparse["status"] == (
        "decisive_sparse_anchor_takes_precedence"
    )
