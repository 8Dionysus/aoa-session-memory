from __future__ import annotations

import hashlib
import hmac
import importlib.util
import json
import os
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "profile_session_stages.py"
SPEC = importlib.util.spec_from_file_location("profile_session_stages_test", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_alias_source_contract(aoa_root: Path) -> None:
    aoa_root.mkdir(parents=True, exist_ok=True)
    owner_dir = aoa_root / ".owner"
    owner_dir.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(b"synthetic-profile-alias-fixture").digest()
    signer = hashlib.sha256(b"synthetic-profile-admission-signer").digest()
    anchor_ref = "owner:synthetic-profile-admission-anchor"

    def verify(message_digest: str, signature: str) -> bool:
        expected = "sha256:" + hmac.new(
            signer,
            message_digest.encode("ascii"),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    MODULE.identity_telemetry._provision_owner_alias_trust_anchor(
        anchor_ref,
        verify,
        token=MODULE.identity_telemetry._OWNER_ALIAS_TRUST_ANCHOR_PROVISION_TOKEN,
    )
    (owner_dir / "session-alias.key").write_bytes(key)
    root_sha256 = MODULE.identity_telemetry._owner_root_identity_digest(
        MODULE.identity_telemetry._owner_directory_identity_snapshot(aoa_root)
    )
    contract = {
        "schema_version": MODULE.identity_telemetry.OWNER_ALIAS_SOURCE_SCHEMA_VERSION,
        "issuer": "aoa-session-memory",
        "source_ref": "owner:profile-fixture-alias-source",
        "trust_anchor_ref": anchor_ref,
        "key_path": MODULE.identity_telemetry.OWNER_ALIAS_SOURCE_KEY_RELATIVE_PATH,
        "key_sha256": hashlib.sha256(key).hexdigest(),
        "root_sha256": root_sha256,
    }
    contract["epoch_sha256"] = MODULE.identity_telemetry._owner_alias_epoch_digest(
        root_sha256=root_sha256,
        source_ref=contract["source_ref"],
        trust_anchor_ref=contract["trust_anchor_ref"],
        key_sha256=contract["key_sha256"],
    )
    contract["admission_signature"] = "sha256:" + hmac.new(
        signer,
        MODULE.identity_telemetry._owner_alias_admission_message(contract).encode("ascii"),
        hashlib.sha256,
    ).hexdigest()
    contract["contract_sha256"] = MODULE.identity_telemetry.canonical_sha256(contract)
    write_json(owner_dir / "session-alias-source.json", contract)


def refresh_segment_receipt(session_dir: Path, segment_path: Path) -> None:
    manifest_path = session_dir / "session.manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    segments = manifest.get("segments") if isinstance(manifest.get("segments"), list) else []
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        declared = Path(str(segment.get("index") or ""))
        declared = declared if declared.is_absolute() else session_dir / declared
        if declared.resolve(strict=False) != segment_path.resolve(strict=False):
            continue
        stat = segment_path.stat()
        segment["artifact_receipts"] = {
            "index": {
                "bytes": stat.st_size,
                "sha256": hashlib.sha256(segment_path.read_bytes()).hexdigest(),
            }
        }
        break
    write_json(manifest_path, manifest)


def owner_context(raw_sha256: str, raw_bytes: int, raw_line_count: int, timestamp: str) -> dict[str, object]:
    owner = MODULE._owner_memory_module()
    task = owner.task_episode_source_generation_identity()
    segment = owner.segment_index_generation_identity()
    session = owner.session_index_generation_identity()
    projection = owner.session_projection_publish_identity_from_scan(
        {
            "raw_sha256": raw_sha256,
            "raw_bytes": raw_bytes,
            "raw_line_count": raw_line_count,
            "processed_to_line": raw_line_count,
            "processed_to_timestamp": timestamp,
        }
    )
    return {
        "task": task,
        "segment": segment,
        "session": session,
        "projection": projection,
    }


def write_fixture_session(tmp_path: Path) -> Path:
    aoa_root = tmp_path / "workspace" / ".aoa"
    write_alias_source_contract(aoa_root)
    session_dir = aoa_root / "sessions" / "2026-08-20__001__fixture"
    segments_dir = session_dir / "segments"
    shard_dir = session_dir / "session-index-shards" / "task-episodes"
    raw_dir = session_dir / "raw"
    raw_dir.mkdir(parents=True)

    events = [
        {
            "event_id": "000001",
            "line": 1,
            "type": "USER_INTENT",
            "timestamp": "2026-08-20T10:00:00Z",
            "correlation_id": None,
            "facets": {},
        },
        {
            "event_id": "000002",
            "line": 2,
            "type": "COMMAND",
            "timestamp": "2026-08-20T10:00:01Z",
            "correlation_id": "call-test-1",
            "facets": {"command": "pytest -q tests", "tool_name": "exec_command", "command_kind": "verification"},
        },
        {
            "event_id": "000003",
            "line": 3,
            "type": "ERROR",
            "timestamp": "2026-08-20T10:00:03Z",
            "correlation_id": "call-test-1",
            "outcome": "failed",
            "facets": {},
        },
        {
            "event_id": "000004",
            "line": 4,
            "type": "FILE_WRITE",
            "timestamp": "2026-08-20T10:00:04Z",
            "correlation_id": "call-repair",
            "facets": {"command": "apply_patch", "tool_name": "apply_patch", "command_kind": "write"},
        },
        {
            "event_id": "000005",
            "line": 5,
            "type": "TOOL_OUTPUT",
            "timestamp": "2026-08-20T10:00:05Z",
            "correlation_id": "call-repair",
            "outcome": "observed",
            "facets": {},
        },
        {
            "event_id": "000006",
            "line": 6,
            "type": "COMMAND",
            "timestamp": "2026-08-20T10:00:06Z",
            "correlation_id": "call-test-2",
            "facets": {"command": "pytest -q tests", "tool_name": "exec_command", "command_kind": "verification"},
        },
        {
            "event_id": "000007",
            "line": 7,
            "type": "VERIFICATION",
            "timestamp": "2026-08-20T10:00:08Z",
            "correlation_id": "call-test-2",
            "outcome": "succeeded",
            "facets": {},
        },
        {
            "event_id": "000008",
            "line": 8,
            "type": "ASSISTANT_MESSAGE",
            "timestamp": "2026-08-20T10:00:10Z",
            "correlation_id": None,
            "facets": {},
        },
    ]
    segment_path = segments_dir / "000__initial-to-latest.index.json"
    write_json(segment_path, {"segment_id": "000", "events": events})
    raw_path = raw_dir / "session.raw.jsonl"
    raw_path.write_text("\n".join(json.dumps({"line": i}) for i in range(1, 9)) + "\n", encoding="utf-8")
    raw_bytes = raw_path.stat().st_size
    raw_sha256 = hashlib.sha256(raw_path.read_bytes()).hexdigest()
    context = owner_context(raw_sha256, raw_bytes, 8, "2026-08-20T10:00:10Z")
    task_generation = str(context["task"]["generation_id"])
    segment_generation = str(context["segment"]["generation_id"])
    session_generation = str(context["session"]["generation_id"])
    projection = context["projection"]

    episode_ref = "session-index-shards/task-episodes/episode.json"
    payload = {
        "episode_id": "task-0001",
        "status": "closed",
        "confidence": "high",
        "event_range": {"from_line": 1, "to_line": 8},
        "intent_refs": [{"line": 1, "event_id": "000001"}],
    }
    episode = {
        "schema_version": 1,
        "artifact_type": "session_index_component_shard",
        "component": "task_episodes",
        "component_key": "0000:task-0001",
        "payload_sha256": hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "payload": payload,
        "source_identity": {
            "task_episode_generation_id": task_generation,
            "episode_source_sha256": MODULE.identity_telemetry.canonical_episode_source_sha256(payload),
            "event_range": {"from_line": 1, "to_line": 8},
            "privacy_policy_version": 1,
            "redaction_policy_version": 1,
        },
    }
    episode_path = shard_dir / "episode.json"
    write_json(episode_path, episode)
    payload_sha256 = hashlib.sha256(
        json.dumps(episode["payload"], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    write_json(
        session_dir / "session-index-shards" / "manifest.json",
        {
            "projection_publish": projection,
            "source_identity": {
                "raw_sha256": raw_sha256,
                "raw_bytes": raw_bytes,
                "raw_line_count": 8,
                "task_episode_generation_id": task_generation,
            },
            "components": {
                "task_episodes": [
                    {
                        "component_key": "0000:task-0001",
                        "ref": episode_ref,
                        "artifact_sha256": hashlib.sha256(episode_path.read_bytes()).hexdigest(),
                        "payload_sha256": payload_sha256,
                    }
                ]
            },
            "component_counts": {"task_episodes": 1},
            "component_order": {"task_episodes": [episode_ref]},
        },
    )
    write_json(
        session_dir / "session.manifest.json",
        {
            "session_id": "fixture-session",
            "session_label": "2026-08-20__001__fixture",
            "archive_status": "indexed",
            "review_status": "provisional",
            "raw": {"line_count": 8, "bytes": raw_bytes, "sha256": raw_sha256},
            "index_schema": {
                "session_index_generation_id": session_generation,
                "segment_index_generation_id": segment_generation,
                "projection_publish": projection,
            },
            "raw_blocks": [{"status": "open"}],
        },
    )
    write_json(
        session_dir / "session.index.json",
        {
            "session_id": "fixture-session",
            "archive_status": "indexed",
            "event_count": 8,
            "generation_id": session_generation,
            "generation_identity": context["session"],
            "dependency_generation_identities": {
                "segment_index": context["segment"],
                "task_episode_source": context["task"],
            },
            "projection_publish": projection,
            "segments": [{"index": str(segment_path), "source_range": {"from_line": 1, "to_line": 8}}],
        },
    )
    segment = json.loads(segment_path.read_text(encoding="utf-8"))
    segment.update(
        {
            "generation_id": segment_generation,
            "generation_identity": context["segment"],
            "projection_publish": projection,
            "source_range": {"from_line": 1, "to_line": 8},
        }
    )
    write_json(segment_path, segment)
    session_manifest_path = session_dir / "session.manifest.json"
    session_manifest = json.loads(session_manifest_path.read_text(encoding="utf-8"))
    segment_stat = segment_path.stat()
    session_manifest["segments"] = [
        {
            "segment_id": "000",
            "role": "initial-to-latest",
            "index": str(segment_path),
            "artifact_receipts": {
                "index": {
                    "bytes": segment_stat.st_size,
                    "sha256": hashlib.sha256(segment_path.read_bytes()).hexdigest(),
                }
            },
        }
    ]
    write_json(session_manifest_path, session_manifest)
    write_json(
        aoa_root / "session-registry.json",
        {
            "schema_version": 1,
            "sessions": [
                {
                    "session_id": "fixture-session",
                    "session_label": session_dir.name,
                    "path": str(session_dir),
                    "archive_status": "indexed",
                    "segment_count": 1,
                }
            ],
        },
    )
    return aoa_root


def write_bounded_prefix_fixture(tmp_path: Path) -> tuple[Path, Path, dict[str, str]]:
    aoa_root = write_fixture_session(tmp_path)
    session_dir = aoa_root / "sessions" / "2026-08-20__001__fixture"
    raw_path = session_dir / "raw" / "session.raw.jsonl"
    raw_bytes = raw_path.stat().st_size
    raw_sha256 = hashlib.sha256(raw_path.read_bytes()).hexdigest()
    owner = MODULE._owner_memory_module()
    context = owner_context(raw_sha256, raw_bytes, 8, "2026-08-20T10:00:10Z")
    session_generation = str(context["session"]["generation_id"])
    segment_generation = str(context["segment"]["generation_id"])
    task_generation = str(context["task"]["generation_id"])
    projection = context["projection"]
    publish_id = str(projection["publish_id"])
    manifest_path = session_dir / "session.manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update(
        {
            "session_id": "fixture-session",
            "raw": {
                "line_count": 8,
                "bytes": raw_bytes,
                "sha256": raw_sha256,
                "indexing_status": "indexed",
            },
            "index_schema": {
                "session_index_generation_id": session_generation,
                "segment_index_generation_id": segment_generation,
                "projection_publish": projection,
            },
            "raw_blocks": {
                "blocks": [{"status": "open"}],
                "projection_publish": projection,
            },
        }
    )
    write_json(manifest_path, manifest)

    index_path = session_dir / "session.index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index.update(
        {
            "session_id": "fixture-session",
            "event_count": 8,
            "generation_id": session_generation,
            "generation_identity": context["session"],
            "dependency_generation_identities": {
                "segment_index": context["segment"],
                "task_episode_source": context["task"],
            },
            "projection_publish": projection,
        }
    )
    write_json(index_path, index)

    segment_path = session_dir / "segments" / "000__initial-to-latest.index.json"
    segment = json.loads(segment_path.read_text(encoding="utf-8"))
    segment.update(
        {
            "generation_id": segment_generation,
            "generation_identity": context["segment"],
            "projection_publish": projection,
            "source_range": {"from_line": 1, "to_line": 8},
        }
    )
    write_json(segment_path, segment)
    refresh_segment_receipt(session_dir, segment_path)

    component_manifest_path = session_dir / "session-index-shards" / "manifest.json"
    component_manifest = json.loads(component_manifest_path.read_text(encoding="utf-8"))
    component_manifest.update(
        {
            "projection_publish": projection,
            "source_identity": {
                "raw_sha256": raw_sha256,
                "raw_bytes": raw_bytes,
                "raw_line_count": 8,
                "task_episode_generation_id": task_generation,
            },
            "component_counts": {"task_episodes": 1},
        }
    )
    episode_path = session_dir / "session-index-shards" / "task-episodes" / "episode.json"
    episode = json.loads(episode_path.read_text(encoding="utf-8"))
    episode["source_identity"] = {
        "task_episode_generation_id": task_generation,
        "episode_source_sha256": MODULE.identity_telemetry.canonical_episode_source_sha256(episode["payload"]),
        "event_range": {"from_line": 1, "to_line": 8},
        "privacy_policy_version": 1,
        "redaction_policy_version": 1,
    }
    write_json(episode_path, episode)
    entry = component_manifest["components"]["task_episodes"][0]
    entry["artifact_sha256"] = hashlib.sha256(episode_path.read_bytes()).hexdigest()
    entry["payload_sha256"] = hashlib.sha256(
        json.dumps(episode["payload"], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    write_json(component_manifest_path, component_manifest)

    tail_path = session_dir / "raw" / "fixture-live-source.jsonl"
    tail_path.write_bytes(b"x" * (raw_bytes + 4))
    write_json(
        session_dir / "raw" / "capture.latest.json",
        {
            "artifact_type": "raw_capture_state",
            "capture_mode": "append_only_immutable_block_ledger_v1",
            "raw_bytes": raw_bytes + 4,
            "source_path": str(tail_path),
            "projection_raw_sha256_at_capture": raw_sha256,
            "projection_publish_id_at_capture": publish_id,
        },
    )
    return aoa_root, session_dir, {
        "raw_sha256": raw_sha256,
        "raw_bytes": str(raw_bytes),
        "publish_id": publish_id,
        "session_generation": session_generation,
        "segment_generation": segment_generation,
        "task_generation": task_generation,
    }


def refresh_fixture_owner_context(session_dir: Path) -> None:
    raw_path = session_dir / "raw" / "session.raw.jsonl"
    raw_bytes = raw_path.stat().st_size
    raw_sha256 = hashlib.sha256(raw_path.read_bytes()).hexdigest()
    raw_line_count = len(raw_path.read_text(encoding="utf-8").splitlines())
    context = owner_context(raw_sha256, raw_bytes, raw_line_count, "2026-08-20T10:00:11Z")
    projection = context["projection"]

    manifest_path = session_dir / "session.manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["raw"].update({"line_count": raw_line_count, "bytes": raw_bytes, "sha256": raw_sha256})
    manifest["index_schema"] = {
        "session_index_generation_id": context["session"]["generation_id"],
        "segment_index_generation_id": context["segment"]["generation_id"],
        "projection_publish": projection,
    }
    if isinstance(manifest.get("raw_blocks"), dict):
        manifest["raw_blocks"]["projection_publish"] = projection
    write_json(manifest_path, manifest)

    index_path = session_dir / "session.index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index.update(
        {
            "event_count": raw_line_count,
            "generation_id": context["session"]["generation_id"],
            "generation_identity": context["session"],
            "dependency_generation_identities": {
                "segment_index": context["segment"],
                "task_episode_source": context["task"],
            },
            "projection_publish": projection,
        }
    )
    write_json(index_path, index)

    segment_path = session_dir / "segments" / "000__initial-to-latest.index.json"
    segment = json.loads(segment_path.read_text(encoding="utf-8"))
    segment.update(
        {
            "generation_id": context["segment"]["generation_id"],
            "generation_identity": context["segment"],
            "projection_publish": projection,
        }
    )
    write_json(segment_path, segment)
    refresh_segment_receipt(session_dir, segment_path)

    episode_path = session_dir / "session-index-shards" / "task-episodes" / "episode.json"
    episode = json.loads(episode_path.read_text(encoding="utf-8"))
    episode["source_identity"]["task_episode_generation_id"] = context["task"]["generation_id"]
    episode["source_identity"]["episode_source_sha256"] = MODULE.identity_telemetry.canonical_episode_source_sha256(
        episode["payload"]
    )
    episode["payload_sha256"] = hashlib.sha256(
        json.dumps(episode["payload"], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    write_json(episode_path, episode)

    component_manifest_path = session_dir / "session-index-shards" / "manifest.json"
    component_manifest = json.loads(component_manifest_path.read_text(encoding="utf-8"))
    component_manifest["projection_publish"] = projection
    component_manifest["source_identity"] = {
        "raw_sha256": raw_sha256,
        "raw_bytes": raw_bytes,
        "raw_line_count": raw_line_count,
        "task_episode_generation_id": context["task"]["generation_id"],
    }
    entry = component_manifest["components"]["task_episodes"][0]
    entry["artifact_sha256"] = hashlib.sha256(episode_path.read_bytes()).hexdigest()
    entry["payload_sha256"] = hashlib.sha256(
        json.dumps(episode["payload"], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    write_json(component_manifest_path, component_manifest)


def make_fixture_owner_receipt(
    pin: dict[str, str],
    prefix_identity: str,
    *,
    owner_root_witness: object,
) -> dict[str, object]:
    telemetry = MODULE.identity_telemetry

    def owner_field(value: object) -> dict[str, object]:
        return telemetry.known(value, source="fixture-owner")

    trajectory = {
        "chain_id": owner_field("fixture-chain-1"),
        "steps": {
            name: {
                "state": "known",
                "reason": "fixture-owner-observed",
                "correlation_id": owner_field(f"fixture-{name}"),
                "timestamp": owner_field("2026-08-20T10:00:00Z"),
                "outcome": owner_field("observed"),
                "evidence_refs": [{"kind": "owner-receipt", "value": f"owner:fixture#{name}"}],
            }
            for name in telemetry.STEP_NAMES
        },
    }
    return telemetry.build_owner_telemetry_receipt(
        session_id="fixture-session",
        session_ref=telemetry.public_session_ref(
            "fixture-session",
            owner_root_witness=owner_root_witness,
        ),
        correlation_id="call-test-1",
        source={
            "raw_sha256": owner_field(pin["raw_sha256"]),
            "raw_bytes": owner_field(int(pin["raw_bytes"])),
            "raw_line_count": owner_field(8),
        },
        identity={name: owner_field(f"fixture-{name}") for name in telemetry.IDENTITY_FIELDS},
        trajectory=trajectory,
        timing={name: owner_field(1.0) for name in telemetry.TIMING_FIELDS},
        cache={
            "posture": owner_field("observed"),
            "identity": owner_field("fixture-cache"),
            "observed_state": owner_field("warm"),
        },
        resource={
            "posture": owner_field("observed"),
            "metrics": {
                "cpu_ms": owner_field(12.0),
                "peak_rss_bytes": owner_field(2048),
                "io_read_bytes": owner_field(4096),
                "io_write_bytes": owner_field(512),
            },
        },
        evidence_refs=[{"kind": "owner-receipt", "value": "owner:fixture#root"}],
        review_status="reviewed",
        projection={
            "prefix_identity": prefix_identity,
            "publish_id": f"sha256:{pin['publish_id']}",
        },
    )


def test_profile_keeps_missing_stages_unknown_and_measures_correlated_spans(tmp_path: Path) -> None:
    aoa_root = write_fixture_session(tmp_path)
    report = MODULE.build_report(
        aoa_root,
        ["2026-08-20__001__fixture"],
        max_episodes=10,
    )

    session = report["sessions"][0]
    episode = session["episodes"][0]
    assert session["scope_status"] == "usable_closed_episode_slice"
    assert session["open_tail_excluded"] is True
    assert episode["stage_spans"]["tests_validators"]["span_seconds"] == 4.0
    assert episode["stage_spans"]["diagnosis_repair"]["span_seconds"] == 1.0
    assert episode["stage_spans"]["kag_navigation_index_gate"]["status"] == "unknown"
    assert episode["stage_spans"]["kag_navigation_index_gate"]["span_seconds"] is None
    assert episode["repeat_amplification"]["repeated_attempt_count"] == 1
    assert episode["repeat_amplification"]["rerun_after_fix_count"] == 1
    assert episode["repeat_amplification"]["validation_rerun_after_repair_count"] == 1
    identity_packet = episode["identity_bound_telemetry"]
    assert identity_packet["episode_binding"]["event_range"] == {"from_line": 1, "to_line": 8}
    assert identity_packet["methods"]["owner_receipt_federation"]["status"] == "missing"
    assert identity_packet["eligibility"]["status"] == "missing"
    assert session["identity_bound_episode_cohort"]["eligible_count"] == 0
    assert session["identity_bound_episode_cohort"]["missing_count"] == 1
    assert session["identity_bound_episode_cohort"]["excluded_count"] == 0
    assert session["identity_bound_episode_cohort"]["field_state_counts"]["identity"]["missing"] == 9
    assert report["evaluator_input"]["verdict"] is None


def test_library_entrypoints_reject_non_positive_episode_limits(tmp_path: Path) -> None:
    aoa_root = write_fixture_session(tmp_path)
    with pytest.raises(MODULE.ProfileError, match="max_episodes_must_be_positive"):
        MODULE.profile_session(aoa_root, "2026-08-20__001__fixture", max_episodes=0)
    with pytest.raises(MODULE.ProfileError, match="max_episodes_must_be_positive"):
        MODULE.build_report(aoa_root, ["2026-08-20__001__fixture"], max_episodes=0)
    report = MODULE.profile_session(aoa_root, "2026-08-20__001__fixture", max_episodes=1)
    assert report["coverage"]["component_cardinality"]["status"] == (
        report["identity_bound_episode_cohort"]["admission_cardinality"]["status"]
    )


def test_unresolved_call_does_not_become_zero_duration(tmp_path: Path) -> None:
    aoa_root = write_fixture_session(tmp_path)
    session_dir = aoa_root / "sessions" / "2026-08-20__001__fixture"
    segment = json.loads(
        (session_dir / "segments" / "000__initial-to-latest.index.json").read_text(encoding="utf-8")
    )
    segment["events"].append(
        {
            "event_id": "000009",
            "line": 9,
            "type": "TOOL_CALL",
            "timestamp": "2026-08-20T10:00:11Z",
            "correlation_id": "call-kag-unresolved",
            "facets": {"tool_qualified_name": "mcp__aoa_kag__search"},
        }
    )
    episode_path = session_dir / "session-index-shards" / "task-episodes" / "episode.json"
    episode = json.loads(episode_path.read_text(encoding="utf-8"))
    episode["payload"]["event_range"]["to_line"] = 9
    episode["source_identity"]["event_range"]["to_line"] = 9
    episode_path.write_text(json.dumps(episode, indent=2) + "\n", encoding="utf-8")
    manifest_path = session_dir / "session.manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw_path = session_dir / "raw" / "session.raw.jsonl"
    raw_path.write_text(
        raw_path.read_text(encoding="utf-8") + json.dumps({"line": 9}) + "\n",
        encoding="utf-8",
    )
    component_manifest_path = session_dir / "session-index-shards" / "manifest.json"
    component_manifest = json.loads(component_manifest_path.read_text(encoding="utf-8"))
    entry = component_manifest["components"]["task_episodes"][0]
    entry["artifact_sha256"] = hashlib.sha256(episode_path.read_bytes()).hexdigest()
    entry["payload_sha256"] = hashlib.sha256(
        json.dumps(episode["payload"], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    write_json(component_manifest_path, component_manifest)
    write_json(session_dir / "segments" / "000__initial-to-latest.index.json", segment)
    refresh_fixture_owner_context(session_dir)
    report = MODULE.build_report(aoa_root, ["2026-08-20__001__fixture"], max_episodes=10)
    stage = report["sessions"][0]["episodes"][0]["stage_spans"]["kag_navigation_index_gate"]
    assert stage["status"] == "partial"
    assert stage["attempt_count"] == 1
    assert stage["span_seconds"] is None


def test_bounded_prefix_is_identity_bound_and_excludes_a_moving_tail(tmp_path: Path) -> None:
    aoa_root, session_dir, pin = write_bounded_prefix_fixture(tmp_path)
    report = MODULE.build_bounded_report(
        aoa_root,
        ["2026-08-20__001__fixture"],
        max_episodes=10,
    )
    scope = report["measurement_scope"]
    assert report["schema_version"] == "bounded_measurement_v1"
    assert scope["scope_currentness"] == "identity_bound_prefix_only"
    assert scope["prefix"]["source"]["bytes"] == int(pin["raw_bytes"])
    assert scope["returned_positive_evidence"]["episode_count"] == 1
    assert scope["global_recall"]["complete"] is False
    assert scope["negative_claims"]["admitted"] is False
    assert scope["excluded_live_tail"]["status"] == "excluded_beyond_prefix"
    assert "pytest -q tests" not in json.dumps(report, ensure_ascii=False)

    capture_path = session_dir / "raw" / "capture.latest.json"
    capture = json.loads(capture_path.read_text(encoding="utf-8"))
    capture["raw_bytes"] = int(pin["raw_bytes"]) + 12
    tail_path = Path(capture["source_path"])
    tail_path.write_bytes(b"x" * (int(pin["raw_bytes"]) + 12))
    write_json(capture_path, capture)
    advanced = MODULE.build_bounded_report(
        aoa_root,
        ["2026-08-20__001__fixture"],
        max_episodes=10,
    )
    assert advanced["measurement_scope"]["prefix"]["identity"] == scope["prefix"]["identity"]
    assert advanced["measurement_scope"]["returned_positive_evidence"]["episode_count"] == 1
    assert advanced["measurement_scope"]["excluded_live_tail"]["status"] == "excluded_beyond_prefix"


def test_bounded_prefix_admits_one_episode_facet_without_raw_body(tmp_path: Path) -> None:
    aoa_root, session_dir, pin = write_bounded_prefix_fixture(tmp_path)
    scope = MODULE.validate_bounded_prefix(aoa_root, "2026-08-20__001__fixture")
    owner_root_witness = MODULE.identity_telemetry._owner_root_witness_for_root(aoa_root)
    segment_path = session_dir / "segments" / "000__initial-to-latest.index.json"
    segment = json.loads(segment_path.read_text(encoding="utf-8"))
    segment["events"][1]["facets"]["identity_bound_telemetry_receipt"] = make_fixture_owner_receipt(
        pin,
        scope["identity"],
        owner_root_witness=owner_root_witness,
    )
    write_json(segment_path, segment)
    refresh_segment_receipt(session_dir, segment_path)

    report = MODULE.build_bounded_report(
        aoa_root,
        ["2026-08-20__001__fixture"],
        max_episodes=10,
    )
    episode = report["session"]["episodes"][0]
    packet = episode["identity_bound_telemetry"]
    assert packet["methods"]["owner_receipt_federation"]["status"] == "admitted"
    assert packet["eligibility"]["status"] == "eligible_identity_packet"
    assert packet["episode_binding"]["episode_id"] == "task-0001"
    cohort = report["identity_bound_episode_cohort"]
    assert cohort["eligible_count"] == 1
    assert cohort["missing_count"] == 0
    assert cohort["excluded_count"] == 0
    assert cohort["comparison_ready"] is False
    assert cohort["effect"] is None
    schema = json.loads(
        (REPO_ROOT / "schemas" / "identity-bound-session-telemetry.schema.json").read_text(encoding="utf-8")
    )
    assert list(Draft202012Validator(schema).iter_errors(cohort)) == []
    assert "pytest -q tests" not in json.dumps(report, ensure_ascii=False)


@pytest.mark.parametrize(
    "variant",
    ["absolute", "relative", "traversal", "owner_like_sibling", "manifest_substitution"],
)
def test_bounded_prefix_rejects_noncanonical_same_byte_segment_membership(
    tmp_path: Path,
    variant: str,
) -> None:
    aoa_root, session_dir, _pin = write_bounded_prefix_fixture(tmp_path)
    canonical_path = session_dir / "segments" / "000__initial-to-latest.index.json"
    if variant == "owner_like_sibling":
        external_path = (
            tmp_path
            / "owner-root-sibling"
            / "sessions"
            / session_dir.name
            / "segments"
            / canonical_path.name
        )
    else:
        external_path = tmp_path / "external-same-byte" / canonical_path.name
    external_path.parent.mkdir(parents=True, exist_ok=True)
    external_path.write_bytes(canonical_path.read_bytes())
    if variant in {"absolute", "owner_like_sibling", "manifest_substitution"}:
        selected_path = str(external_path)
    elif variant == "relative":
        selected_path = os.path.relpath(external_path, start=Path.cwd())
    else:
        (external_path.parent / "nested").mkdir()
        selected_path = f"{external_path.parent}/nested/../{external_path.name}"

    index_path = session_dir / "session.index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index["segments"][0]["index"] = selected_path
    write_json(index_path, index)
    if variant == "manifest_substitution":
        manifest_path = session_dir / "session.manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["segments"][0]["index"] = selected_path
        write_json(manifest_path, manifest)

    with pytest.raises(MODULE.BoundedPrefixError, match="bounded_prefix_segment_owner_membership"):
        MODULE.validate_bounded_prefix(
            aoa_root,
            "2026-08-20__001__fixture",
        )


def test_profile_public_source_refs_encode_multilingual_session_labels(tmp_path: Path) -> None:
    aoa_root = write_fixture_session(tmp_path)
    report = MODULE.profile_session(
        aoa_root,
        "2026-08-20__001__fixture",
        max_episodes=10,
        session_label_override="Сессия/é/会议",
    )

    session_ref = report["session_ref"]
    assert session_ref.startswith("session:")
    assert "Сессия" not in session_ref
    assert "会议" not in session_ref
    assert "session_label" not in report
    assert "Сессия/é/会议" not in json.dumps(report, ensure_ascii=False)
    assert "%" not in session_ref
    assert report["source_refs"]["session_manifest"].startswith(
        f"{session_ref}#session.manifest.json"
    )
    assert report["source_refs"]["session_index"].startswith(
        f"{session_ref}#session.index.json"
    )


def test_build_report_does_not_echo_raw_selector_in_public_failure_corpus(tmp_path: Path) -> None:
    aoa_root = write_fixture_session(tmp_path)
    raw_selector = "Сессия/é/会议"
    report = MODULE.build_report(aoa_root, [raw_selector], max_episodes=10)

    encoded = json.dumps(report, ensure_ascii=False)
    assert raw_selector not in encoded
    assert report["corpus"]["failed_selector_count"] == 1
    assert report["corpus"]["failed_selectors"][0]["selector_ref"].startswith("session:alias-")
    assert report["corpus"]["failed_selectors"][0]["error"] == "session_missing"


def test_rejected_selector_scope_cannot_close_empty_cohort(tmp_path: Path) -> None:
    aoa_root = write_fixture_session(tmp_path)
    report = MODULE.build_report(aoa_root, ["missing-selector"], max_episodes=10)
    cohort = report["identity_bound_episode_cohort"]

    assert report["corpus"]["selection_status"] == "rejected_selector_scope"
    assert cohort["selection_status"] == "rejected"
    assert cohort["status"] == "rejected_selector_scope"
    assert cohort["admission_cardinality"]["status"] == "rejected"
    assert cohort["eligible_count"] == 0
    assert "admission_cardinality_rejected" in cohort["reason_counts"]


def test_duplicate_episode_component_ref_is_rejected_before_ordinary_profile_admission(tmp_path: Path) -> None:
    aoa_root = write_fixture_session(tmp_path)
    session_dir = aoa_root / "sessions" / "2026-08-20__001__fixture"
    manifest_path = session_dir / "session-index-shards" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["components"]["task_episodes"].append(
        dict(manifest["components"]["task_episodes"][0])
    )
    write_json(manifest_path, manifest)

    report = MODULE.build_report(aoa_root, ["2026-08-20__001__fixture"], max_episodes=10)

    assert report["sessions"] == []
    assert report["identity_bound_episode_cohort"]["episode_count"] == 0
    assert report["corpus"]["failed_selectors"][0]["error"] == "episode_component_count_mismatch"


@pytest.mark.parametrize(
    ("missing_field", "expected_error"),
    [
        ("component_counts", "episode_component_count_missing"),
        ("component_order", "episode_component_order_missing"),
    ],
)
def test_ordinary_profile_requires_declared_episode_cardinality_and_order(
    tmp_path: Path,
    missing_field: str,
    expected_error: str,
) -> None:
    aoa_root = write_fixture_session(tmp_path / missing_field)
    manifest_path = aoa_root / "sessions" / "2026-08-20__001__fixture" / "session-index-shards" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.pop(missing_field)
    write_json(manifest_path, manifest)

    report = MODULE.build_report(aoa_root, ["2026-08-20__001__fixture"], max_episodes=10)

    assert report["sessions"] == []
    assert report["identity_bound_episode_cohort"]["eligible_count"] == 0
    assert report["corpus"]["failed_selectors"][0]["error"] == expected_error


def test_bounded_owner_validator_rechecks_actual_artifact_payload_and_range(tmp_path: Path) -> None:
    aoa_root, session_dir, _pin = write_bounded_prefix_fixture(tmp_path / "wrong-digest")
    manifest_path = session_dir / "session-index-shards" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["components"]["task_episodes"][0]["payload_sha256"] = "0" * 64
    write_json(manifest_path, manifest)
    with pytest.raises(MODULE.BoundedPrefixError, match="bounded_prefix_owner_component_admission:episode_component_payload_digest_mismatch"):
        MODULE.validate_bounded_prefix(aoa_root, "2026-08-20__001__fixture")

    aoa_root, session_dir, _pin = write_bounded_prefix_fixture(tmp_path / "reversed-range")
    episode_path = session_dir / "session-index-shards" / "task-episodes" / "episode.json"
    episode = json.loads(episode_path.read_text(encoding="utf-8"))
    reversed_range = {"from_line": 8, "to_line": 3}
    episode["payload"]["event_range"] = reversed_range
    episode["source_identity"]["event_range"] = reversed_range
    episode["source_identity"]["episode_source_sha256"] = MODULE.identity_telemetry.canonical_episode_source_sha256(
        episode["payload"]
    )
    episode["payload_sha256"] = hashlib.sha256(
        json.dumps(episode["payload"], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    write_json(episode_path, episode)
    manifest_path = session_dir / "session-index-shards" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entry = manifest["components"]["task_episodes"][0]
    entry["artifact_sha256"] = hashlib.sha256(episode_path.read_bytes()).hexdigest()
    entry["payload_sha256"] = hashlib.sha256(
        json.dumps(episode["payload"], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    write_json(manifest_path, manifest)
    with pytest.raises(MODULE.BoundedPrefixError, match="bounded_prefix_owner_component_admission:episode_component_range_mismatch"):
        MODULE.validate_bounded_prefix(aoa_root, "2026-08-20__001__fixture")


def test_strict_packet_rejects_stale_owner_manifest_after_initial_admission(tmp_path: Path) -> None:
    aoa_root, session_dir, _pin = write_bounded_prefix_fixture(tmp_path)
    report = MODULE.build_bounded_report(
        aoa_root,
        ["2026-08-20__001__fixture"],
        max_episodes=10,
    )
    packet = report["session"]["episodes"][0]["identity_bound_telemetry"]
    manifest_path = session_dir / "session-index-shards" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["owner_test_mutation"] = "stale"
    write_json(manifest_path, manifest)

    with pytest.raises(MODULE.identity_telemetry.TelemetryError, match="episode_component_owner_source_not_current"):
        MODULE.identity_telemetry.verify_packet_integrity(packet)


def test_cohort_cardinality_rejection_zeroes_eligible_admission(tmp_path: Path) -> None:
    aoa_root, _session_dir, _pin = write_bounded_prefix_fixture(tmp_path)
    report = MODULE.build_bounded_report(
        aoa_root,
        ["2026-08-20__001__fixture"],
        max_episodes=10,
    )
    packet = report["session"]["episodes"][0]["identity_bound_telemetry"]
    cohort = MODULE.identity_episode_cohort(
        [packet],
        expected_episode_count=2,
        expected_component_order=["session-index-shards/task-episodes/episode.json"],
    )

    assert cohort["admission_cardinality"]["status"] == "rejected"
    assert cohort["eligible_count"] == 0
    assert "admission_cardinality_rejected" in cohort["reason_counts"]


def test_episode_receipt_requires_carrying_event_and_rejects_duplicate_facets(tmp_path: Path) -> None:
    aoa_root, session_dir, pin = write_bounded_prefix_fixture(tmp_path / "missing-carrying")
    scope = MODULE.validate_bounded_prefix(aoa_root, "2026-08-20__001__fixture")
    owner_root_witness = MODULE.identity_telemetry._owner_root_witness_for_root(aoa_root)
    segment_path = session_dir / "segments" / "000__initial-to-latest.index.json"
    segment = json.loads(segment_path.read_text(encoding="utf-8"))
    receipt = make_fixture_owner_receipt(
        pin,
        scope["identity"],
        owner_root_witness=owner_root_witness,
    )
    segment["events"][0]["facets"]["identity_bound_telemetry_receipt"] = receipt
    write_json(segment_path, segment)
    refresh_segment_receipt(session_dir, segment_path)
    report = MODULE.build_bounded_report(
        aoa_root,
        ["2026-08-20__001__fixture"],
        max_episodes=10,
    )
    packet = report["session"]["episodes"][0]["identity_bound_telemetry"]
    assert packet["methods"]["owner_receipt_federation"]["status"] == "rejected"
    assert "carrying_event_correlation_missing" in packet["methods"]["owner_receipt_federation"]["rejection"]

    aoa_root, session_dir, pin = write_bounded_prefix_fixture(tmp_path / "duplicate")
    scope = MODULE.validate_bounded_prefix(aoa_root, "2026-08-20__001__fixture")
    owner_root_witness = MODULE.identity_telemetry._owner_root_witness_for_root(aoa_root)
    segment_path = session_dir / "segments" / "000__initial-to-latest.index.json"
    segment = json.loads(segment_path.read_text(encoding="utf-8"))
    receipt = make_fixture_owner_receipt(
        pin,
        scope["identity"],
        owner_root_witness=owner_root_witness,
    )
    segment["events"][1]["facets"]["identity_bound_telemetry_receipt"] = receipt
    segment["events"][2]["facets"]["identity_bound_telemetry_receipt"] = receipt
    write_json(segment_path, segment)
    refresh_segment_receipt(session_dir, segment_path)
    report = MODULE.build_bounded_report(
        aoa_root,
        ["2026-08-20__001__fixture"],
        max_episodes=10,
    )
    packet = report["session"]["episodes"][0]["identity_bound_telemetry"]
    assert packet["methods"]["owner_receipt_federation"]["status"] == "rejected"
    assert packet["methods"]["owner_receipt_federation"]["rejection"] == "duplicate_identity_bound_receipt"


def test_bounded_prefix_rejects_wrong_watermark_and_preserves_inputs(tmp_path: Path) -> None:
    aoa_root, session_dir, _pin = write_bounded_prefix_fixture(tmp_path)
    index_path = session_dir / "session.index.json"
    before = index_path.read_bytes()
    with pytest.raises(MODULE.BoundedPrefixError, match="expected_pin_mismatch:raw_bytes"):
        MODULE.build_bounded_report(
            aoa_root,
            ["2026-08-20__001__fixture"],
            max_episodes=10,
            expected_pin={"raw_bytes": 999},
        )
    assert index_path.read_bytes() == before


def test_bounded_prefix_rejects_generation_drift_and_partial_coverage(tmp_path: Path) -> None:
    aoa_root, session_dir, _pin = write_bounded_prefix_fixture(tmp_path)
    index_path = session_dir / "session.index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index["generation_id"] = "a" * 64
    write_json(index_path, index)
    with pytest.raises(MODULE.BoundedPrefixError, match="session_generation_mismatch"):
        MODULE.build_bounded_report(
            aoa_root,
            ["2026-08-20__001__fixture"],
            max_episodes=10,
        )

    aoa_root, session_dir, _pin = write_bounded_prefix_fixture(tmp_path / "partial")
    segment_path = session_dir / "segments" / "000__initial-to-latest.index.json"
    segment = json.loads(segment_path.read_text(encoding="utf-8"))
    segment["events"] = segment["events"][:-1]
    write_json(segment_path, segment)
    refresh_segment_receipt(session_dir, segment_path)
    after_fixture_mutation = segment_path.read_bytes()
    with pytest.raises(MODULE.BoundedPrefixError, match="segment_coverage_incomplete"):
        MODULE.build_bounded_report(
            aoa_root,
            ["2026-08-20__001__fixture"],
            max_episodes=10,
        )
    assert segment_path.read_bytes() == after_fixture_mutation


def test_bounded_zero_results_do_not_admit_absence(tmp_path: Path) -> None:
    aoa_root, session_dir, _pin = write_bounded_prefix_fixture(tmp_path)
    episode_path = session_dir / "session-index-shards" / "task-episodes" / "episode.json"
    episode = json.loads(episode_path.read_text(encoding="utf-8"))
    episode["payload"]["status"] = "open"
    episode["source_identity"]["episode_source_sha256"] = MODULE.identity_telemetry.canonical_episode_source_sha256(
        episode["payload"]
    )
    episode["payload_sha256"] = hashlib.sha256(
        json.dumps(episode["payload"], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    write_json(episode_path, episode)
    component_manifest_path = session_dir / "session-index-shards" / "manifest.json"
    component_manifest = json.loads(component_manifest_path.read_text(encoding="utf-8"))
    entry = component_manifest["components"]["task_episodes"][0]
    entry["artifact_sha256"] = hashlib.sha256(episode_path.read_bytes()).hexdigest()
    entry["payload_sha256"] = hashlib.sha256(
        json.dumps(episode["payload"], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    write_json(component_manifest_path, component_manifest)
    report = MODULE.build_bounded_report(
        aoa_root,
        ["2026-08-20__001__fixture"],
        max_episodes=10,
    )
    positive = report["measurement_scope"]["returned_positive_evidence"]
    assert report["return_status"] == "empty_bounded_scope_not_absence"
    assert positive["episode_count"] == 0
    assert positive["semantic_absence_admitted"] is False
    assert report["measurement_scope"]["negative_claims"]["admitted"] is False
