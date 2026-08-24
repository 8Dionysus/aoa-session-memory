from __future__ import annotations

import importlib.util
import json
import sys
import threading
from pathlib import Path
from typing import Any

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "aoa_session_memory.py"
spec = importlib.util.spec_from_file_location(
    "aoa_session_memory_capture_retry_identity",
    SCRIPT,
)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules["aoa_session_memory_capture_retry_identity"] = module
spec.loader.exec_module(module)


def _write_transcript(path: Path, marker: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "timestamp": "2026-08-24T00:00:00Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": marker}],
                    },
                },
                sort_keys=True,
            )
            + "\n"
        )


def _fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    session_id: str = "capture-retry-identity",
    schedule: bool = True,
) -> dict[str, Any]:
    monkeypatch.setattr(
        module,
        "SESSION_PROJECTION_HEAVY_LANE_RAW_BYTES",
        1,
    )
    workspace = tmp_path / "workspace"
    aoa_root = workspace / ".aoa"
    session_dir = aoa_root / "sessions" / session_id
    transcript = tmp_path / f"{session_id}.jsonl"
    _write_transcript(transcript, "initial")
    manifest = {
        "session_id": session_id,
        "archive_status": "indexed",
        "raw": {
            "bytes": 0,
            "sha256": "",
            "indexing_status": "indexed",
            "source_path": str(transcript),
        },
    }
    session_dir.mkdir(parents=True, exist_ok=True)
    module.write_json(session_dir / "session.manifest.json", manifest)
    initial_capture = module.preserve_unindexed_raw_capture(
        session_dir=session_dir,
        session_id=session_id,
        transcript_path=transcript,
        manifest=manifest,
        hook_event_name="PostToolUse",
        now="2026-08-24T00:00:01Z",
    )
    if schedule:
        scheduled = module.reconcile_session_projection_freshness_obligation(
            aoa_root=aoa_root,
            session_id=session_id,
            session_dir=session_dir,
            transcript_path=transcript,
            freshness_reason="fixture_initial",
            now_epoch=100.0,
            create_if_missing=True,
        )
        assert scheduled["status"] == "scheduled"
    return {
        "workspace": workspace,
        "aoa_root": aoa_root,
        "session_dir": session_dir,
        "transcript": transcript,
        "manifest": manifest,
        "session_id": session_id,
        "initial_capture": initial_capture,
    }


def _queue_item(fixture: dict[str, Any]) -> dict[str, Any]:
    status = module.auto_maintenance_retry_queue_status(
        fixture["aoa_root"],
        now_epoch=100.0,
    )
    return status["items"][f"deep:{fixture['session_id']}"]


def _identity(item: dict[str, Any]) -> tuple[Any, ...]:
    options = item["options"]
    return (
        options.get("required_capture_epoch_id"),
        options.get("required_capture_epoch_index"),
        options.get("required_capture_bytes"),
        options.get("required_capture_sha256"),
        options.get("required_capture_chain_sha256"),
        options.get("required_capture_ref"),
    )


def _append_capture(fixture: dict[str, Any], marker: str, now: str) -> dict[str, Any]:
    _write_transcript(fixture["transcript"], marker)
    return module.preserve_unindexed_raw_capture(
        session_dir=fixture["session_dir"],
        session_id=fixture["session_id"],
        transcript_path=fixture["transcript"],
        manifest=fixture["manifest"],
        hook_event_name="TimerWatchRecovery",
        now=now,
    )


def _publish_current_projection(fixture: dict[str, Any]) -> None:
    capture = module.raw_capture_state_for_session(fixture["session_dir"])
    manifest_path = fixture["session_dir"] / "session.manifest.json"
    manifest = module.read_json(manifest_path, {})
    raw = manifest["raw"]
    raw.update(
        {
            "bytes": capture["raw_bytes"],
            "sha256": capture["raw_sha256"],
            "indexing_status": "indexed",
            "capture_ref": capture["capture_ref"],
            "capture_ledger": {
                "epoch_id": capture["ledger_epoch_id"],
                "processed_watermark_bytes": capture["raw_bytes"],
                "chain_sha256": capture["ledger_chain_sha256"],
            },
        }
    )
    module.write_json(manifest_path, manifest)


def test_capture_watch_creates_missing_current_epoch_zero_obligation_idempotently(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(
        tmp_path,
        monkeypatch,
        session_id="capture-watch-missing-obligation",
        schedule=False,
    )
    module.register_capture_watch(
        aoa_root=fixture["aoa_root"],
        session_id=fixture["session_id"],
        session_dir=fixture["session_dir"],
        transcript_path=fixture["transcript"],
        observed_at="2026-08-24T00:00:02Z",
    )

    first = module.reconcile_capture_watch(
        aoa_root=fixture["aoa_root"],
        limit=1,
        apply=True,
        now="2026-08-24T00:00:03Z",
    )
    queue = module.auto_maintenance_retry_queue_status(
        fixture["aoa_root"],
        now_epoch=100.0,
    )
    item = queue["items"][f"deep:{fixture['session_id']}"]
    options = item["options"]
    current = module._capture_identity_current(
        aoa_root=fixture["aoa_root"],
        session_id=fixture["session_id"],
        configured_session_dir=fixture["session_dir"],
    )
    assert current["ok"] is True
    identity = current["identity"]
    assert first["results"][0]["queue_reconciliation"]["status"] == (
        "scheduled"
    )
    assert item["queue_key"] == f"deep:{fixture['session_id']}"
    assert options["required_capture_epoch_id"] == identity["epoch_id"]
    assert options["required_capture_epoch_index"] == 0
    assert options["required_capture_bytes"] == identity["bytes"]
    assert options["required_capture_sha256"] == identity["sha256"]
    assert options["required_capture_chain_sha256"] == identity["chain_sha256"]
    assert options["required_capture_ref"] == identity["capture_ref"]
    assert options["required_capture_stable"] is True
    assert queue["freshness_obligation_count"] == 1

    before_repeat = dict(item)
    repeated = module.reconcile_capture_watch(
        aoa_root=fixture["aoa_root"],
        limit=1,
        apply=True,
        now="2026-08-24T00:00:04Z",
    )
    after_repeat = module.auto_maintenance_retry_queue_status(
        fixture["aoa_root"],
        now_epoch=100.0,
    )["items"][f"deep:{fixture['session_id']}"]
    assert repeated["results"][0]["queue_reconciliation"]["status"] == (
        "identity_already_current"
    )
    assert after_repeat == before_repeat


def test_satisfied_unchanged_capture_stays_absent_from_retry_queue(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(
        tmp_path,
        monkeypatch,
        session_id="capture-watch-satisfied",
        schedule=False,
    )
    _publish_current_projection(fixture)
    monkeypatch.setattr(
        module,
        "session_projection_freshness_vector",
        lambda **_kwargs: {
            "axes": {
                "stable_session_projection": {"current": True},
                "search": {"current": True},
            }
        },
    )

    first = module.reconcile_session_projection_freshness_obligation(
        aoa_root=fixture["aoa_root"],
        session_id=fixture["session_id"],
        session_dir=fixture["session_dir"],
        transcript_path=fixture["transcript"],
        freshness_reason="satisfied_unchanged",
        now_epoch=120.0,
        create_if_missing=True,
    )
    second = module.reconcile_session_projection_freshness_obligation(
        aoa_root=fixture["aoa_root"],
        session_id=fixture["session_id"],
        session_dir=fixture["session_dir"],
        transcript_path=fixture["transcript"],
        freshness_reason="satisfied_unchanged_replay",
        now_epoch=121.0,
        create_if_missing=True,
    )
    queue = module.auto_maintenance_retry_queue_status(
        fixture["aoa_root"],
        now_epoch=121.0,
    )
    assert first["status"] == "freshness_obligation_already_satisfied"
    assert second["status"] == "freshness_obligation_already_satisfied"
    assert first["changed"] is False
    assert second["changed"] is False
    assert queue["items"] == {}
    assert queue["freshness_obligation_count"] == 0


def test_strict_obligation_accepts_exact_legacy_monolithic_projection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(
        tmp_path,
        monkeypatch,
        session_id="capture-watch-legacy-monolithic",
        schedule=False,
    )
    capture = module.raw_capture_state_for_session(fixture["session_dir"])
    manifest_path = fixture["session_dir"] / "session.manifest.json"
    manifest = module.read_json(manifest_path, {})
    raw = manifest["raw"]
    raw.update(
        {
            "bytes": capture["raw_bytes"],
            "sha256": capture["raw_sha256"],
            "indexing_status": "indexed",
            "storage_mode": "monolithic_snapshot_v1",
        }
    )
    raw.pop("capture_ref", None)
    raw.pop("capture_ledger", None)
    module.write_json(manifest_path, manifest)
    options = {
        "persistent_obligation": True,
        "obligation_kind": module.SESSION_PROJECTION_FRESHNESS_OBLIGATION_KIND,
        "session_id": fixture["session_id"],
        "session_dir": str(fixture["session_dir"]),
        "required_capture_epoch_id": capture["ledger_epoch_id"],
        "required_capture_epoch_index": 0,
        "required_capture_bytes": capture["raw_bytes"],
        "required_capture_sha256": capture["raw_sha256"],
        "required_capture_chain_sha256": capture["ledger_chain_sha256"],
        "required_capture_ref": capture["capture_ref"],
        "required_capture_stable": True,
        "capture_identity_contract": module.SESSION_CAPTURE_RETRY_IDENTITY_CONTRACT,
        "required_stable_projection": False,
        "required_search_consumer": False,
    }

    status = module.session_projection_freshness_obligation_status(
        fixture["aoa_root"],
        options,
    )
    assert status["ok"] is True
    assert status["proof_mode"] == (
        "exact_monolithic_capture_digest_fallback"
    )
    assert status["capture_identity_satisfied"] is True


def test_missing_obligation_unresolved_identity_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(
        tmp_path,
        monkeypatch,
        session_id="capture-watch-unresolved-missing",
        schedule=False,
    )
    (fixture["session_dir"] / "raw" / module.RAW_CAPTURE_STATE_JSON).unlink()

    result = module.reconcile_session_projection_freshness_obligation(
        aoa_root=fixture["aoa_root"],
        session_id=fixture["session_id"],
        session_dir=fixture["session_dir"],
        transcript_path=fixture["transcript"],
        freshness_reason="unresolved_identity",
        now_epoch=130.0,
        create_if_missing=True,
    )
    queue = module.auto_maintenance_retry_queue_status(
        fixture["aoa_root"],
        now_epoch=130.0,
    )
    assert result["status"] == "identity_reconciliation_unresolved"
    assert result["diagnostic"] == (
        "capture_retry_queue_identity_reconciliation_unresolved"
    )
    assert result["persistent_obligation"] is False
    assert result["changed"] is False
    assert queue["items"] == {}


def test_same_epoch_append_capture_watch_reconciles_exact_queue_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path, monkeypatch, session_id="same-epoch")
    before = _queue_item(fixture)
    module.register_capture_watch(
        aoa_root=fixture["aoa_root"],
        session_id=fixture["session_id"],
        session_dir=fixture["session_dir"],
        transcript_path=fixture["transcript"],
        observed_at="2026-08-24T00:00:02Z",
    )
    before_identity = _identity(before)
    _write_transcript(fixture["transcript"], "same-epoch-append")
    watch = module.reconcile_capture_watch(
        aoa_root=fixture["aoa_root"],
        limit=1,
        apply=True,
        now="2026-08-24T00:00:03Z",
    )
    after = _queue_item(fixture)
    assert watch["status"] == "applied"
    assert watch["results"][0]["queue_reconciliation"]["status"] == (
        "identity_reconciled_updated"
    )
    assert _identity(after) != before_identity
    assert after["options"]["required_capture_bytes"] == fixture["transcript"].stat().st_size


def test_new_epoch_retargets_obligation_without_resetting_retry_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path, monkeypatch, session_id="new-epoch")
    old_item = _queue_item(fixture)
    old_identity = _identity(old_item)

    def seed(payload: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        item = payload["items"][f"deep:{fixture['session_id']}"]
        item["attempts_started"] = 2
        item["next_attempt_epoch"] = 777.0
        item["next_attempt_at"] = module.auto_maintenance_retry_iso(777.0)
        item["exhaustion_cycles"] = 3
        payload["history"] = [{"disposition": "preserve-history"}]
        return {"status": "seeded"}, True

    module.mutate_auto_maintenance_retry_queue(
        fixture["aoa_root"],
        seed,
        now_epoch=101.0,
    )
    replacement = fixture["transcript"].with_suffix(".replacement.jsonl")
    _write_transcript(replacement, "new-epoch")
    replacement.replace(fixture["transcript"])
    module.preserve_unindexed_raw_capture(
        session_dir=fixture["session_dir"],
        session_id=fixture["session_id"],
        transcript_path=fixture["transcript"],
        manifest=fixture["manifest"],
        hook_event_name="TimerWatchRecovery",
        now="2026-08-24T00:01:00Z",
    )
    result = module.reconcile_session_projection_freshness_obligation(
        aoa_root=fixture["aoa_root"],
        session_id=fixture["session_id"],
        session_dir=fixture["session_dir"],
        transcript_path=fixture["transcript"],
        freshness_reason="new_epoch",
        now_epoch=102.0,
        create_if_missing=False,
    )
    after = _queue_item(fixture)
    assert result["status"] == "identity_reconciled_updated"
    assert _identity(after) != old_identity
    assert after["options"]["required_capture_epoch_index"] > old_item["options"]["required_capture_epoch_index"]
    assert after["attempts_started"] == 2
    assert after["next_attempt_epoch"] == 777.0
    assert after["exhaustion_cycles"] == 3
    assert module.auto_maintenance_retry_queue_status(fixture["aoa_root"])["history"][0]["disposition"] == "preserve-history"


def test_identical_capture_replay_is_idempotent_and_does_not_increment_occurrence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path, monkeypatch, session_id="identical-replay")
    before = _queue_item(fixture)
    first = module.reconcile_session_projection_freshness_obligation(
        aoa_root=fixture["aoa_root"],
        session_id=fixture["session_id"],
        session_dir=fixture["session_dir"],
        transcript_path=fixture["transcript"],
        freshness_reason="replay",
        now_epoch=103.0,
        create_if_missing=False,
    )
    after = _queue_item(fixture)
    second = module.reconcile_session_projection_freshness_obligation(
        aoa_root=fixture["aoa_root"],
        session_id=fixture["session_id"],
        session_dir=fixture["session_dir"],
        transcript_path=fixture["transcript"],
        freshness_reason="replay",
        now_epoch=104.0,
        create_if_missing=False,
    )
    final = _queue_item(fixture)
    assert first["status"] == "identity_already_current"
    assert second["status"] == "identity_already_current"
    assert second["changed"] is False
    assert after["occurrence_count"] == before["occurrence_count"]
    assert final == after


def test_stale_writer_cannot_downgrade_capture_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path, monkeypatch, session_id="stale-writer")
    old_options = dict(_queue_item(fixture)["options"])
    _append_capture(fixture, "newer", "2026-08-24T00:02:00Z")
    module.reconcile_session_projection_freshness_obligation(
        aoa_root=fixture["aoa_root"],
        session_id=fixture["session_id"],
        session_dir=fixture["session_dir"],
        transcript_path=fixture["transcript"],
        freshness_reason="newer",
        now_epoch=105.0,
        create_if_missing=False,
    )
    newer_identity = _identity(_queue_item(fixture))

    def stale_writer(payload: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        result = module.auto_maintenance_retry_upsert_item(
            payload,
            profile="deep",
            target=fixture["session_id"],
            reason="stale-writer",
            launch_status="stale_writer",
            options=old_options,
            now_epoch=106.0,
            initial_delay_seconds=0,
        )
        return result, True

    module.mutate_auto_maintenance_retry_queue(
        fixture["aoa_root"],
        stale_writer,
        now_epoch=106.0,
    )
    assert _identity(_queue_item(fixture)) == newer_identity


def test_concurrent_queue_writer_preserves_identity_and_unrelated_retry_update(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path, monkeypatch, session_id="concurrent-writer")
    _append_capture(fixture, "concurrent-newer", "2026-08-24T00:03:00Z")
    barrier = threading.Barrier(2)

    def reconcile() -> None:
        barrier.wait()
        module.reconcile_session_projection_freshness_obligation(
            aoa_root=fixture["aoa_root"],
            session_id=fixture["session_id"],
            session_dir=fixture["session_dir"],
            transcript_path=fixture["transcript"],
            freshness_reason="concurrent-reconcile",
            now_epoch=107.0,
            create_if_missing=False,
        )

    def writer() -> None:
        barrier.wait()

        def mutate(payload: dict[str, Any]) -> tuple[dict[str, Any], bool]:
            item = payload["items"][f"deep:{fixture['session_id']}"]
            item["writer_marker"] = "preserved"
            item["attempts_started"] = 3
            return {"status": "writer_updated"}, True

        module.mutate_auto_maintenance_retry_queue(
            fixture["aoa_root"],
            mutate,
            now_epoch=107.0,
        )

    threads = [threading.Thread(target=reconcile), threading.Thread(target=writer)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    item = _queue_item(fixture)
    assert item["writer_marker"] == "preserved"
    assert item["attempts_started"] == 3
    assert item["options"]["required_capture_bytes"] == fixture["transcript"].stat().st_size


def test_in_flight_capture_supersession_reasserts_new_identity_after_old_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path, monkeypatch, session_id="in-flight")

    def claim_due(payload: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        item = payload["items"][f"deep:{fixture['session_id']}"]
        item["next_attempt_epoch"] = 0.0
        item["next_attempt_at"] = module.auto_maintenance_retry_iso(0.0)
        return {"status": "due"}, True

    module.mutate_auto_maintenance_retry_queue(
        fixture["aoa_root"],
        claim_due,
        now_epoch=108.0,
    )
    launch_calls: list[str] = []

    def fake_launch(**_kwargs: Any) -> dict[str, Any]:
        launch_calls.append("called")
        _append_capture(fixture, "in-flight-newer", "2026-08-24T00:04:00Z")
        result = module.reconcile_session_projection_freshness_obligation(
            aoa_root=fixture["aoa_root"],
            session_id=fixture["session_id"],
            session_dir=fixture["session_dir"],
            transcript_path=fixture["transcript"],
            freshness_reason="capture_during_in_flight",
            now_epoch=109.0,
            create_if_missing=False,
        )
        assert result["status"] == "identity_reconciled_updated"
        return {"ok": True, "status": "child_succeeded", "result_verified": True}

    monkeypatch.setattr(module, "auto_maintenance_resource_launch", fake_launch)
    dispatched = module.auto_maintenance_retry_dispatch(
        workspace_root=fixture["workspace"],
        aoa_root=fixture["aoa_root"],
        apply=True,
        limit=1,
        now_epoch=108.0,
    )
    item = _queue_item(fixture)
    assert launch_calls == ["called"]
    assert dispatched["results"][0]["disposition"] == (
        "reasserted_after_capture_identity_supersession"
    )
    assert item["in_flight"] is False
    assert item["status"] == "pending"
    assert item["options"]["required_capture_bytes"] == fixture["transcript"].stat().st_size
    assert dispatched["results"][0]["capture_identity_superseded"] is True


def test_capture_publication_without_queue_update_recovers_idempotently(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path, monkeypatch, session_id="crash-recovery")
    old_identity = _identity(_queue_item(fixture))
    _append_capture(fixture, "published-before-queue", "2026-08-24T00:05:00Z")
    assert _identity(_queue_item(fixture)) == old_identity
    recovered = module.reconcile_session_projection_freshness_obligation(
        aoa_root=fixture["aoa_root"],
        session_id=fixture["session_id"],
        session_dir=fixture["session_dir"],
        transcript_path=fixture["transcript"],
        freshness_reason="restart_recovery",
        now_epoch=110.0,
        create_if_missing=False,
    )
    replay = module.reconcile_session_projection_freshness_obligation(
        aoa_root=fixture["aoa_root"],
        session_id=fixture["session_id"],
        session_dir=fixture["session_dir"],
        transcript_path=fixture["transcript"],
        freshness_reason="restart_recovery_replay",
        now_epoch=111.0,
        create_if_missing=False,
    )
    assert recovered["status"] == "identity_reconciled_updated"
    assert replay["status"] == "identity_already_current"
    assert _identity(_queue_item(fixture)) != old_identity


def test_deep_admission_refuses_unresolved_capture_identity_without_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path, monkeypatch, session_id="admission-refusal")

    def make_due(payload: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        item = payload["items"][f"deep:{fixture['session_id']}"]
        item["next_attempt_epoch"] = 0.0
        item["next_attempt_at"] = module.auto_maintenance_retry_iso(0.0)
        return {"status": "due"}, True

    module.mutate_auto_maintenance_retry_queue(
        fixture["aoa_root"],
        make_due,
        now_epoch=112.0,
    )
    (fixture["session_dir"] / "raw" / module.RAW_CAPTURE_STATE_JSON).unlink()
    launch_called = False

    def forbidden_launch(**_kwargs: Any) -> dict[str, Any]:
        nonlocal launch_called
        launch_called = True
        raise AssertionError("unresolved capture identity must not launch deep work")

    monkeypatch.setattr(module, "auto_maintenance_resource_launch", forbidden_launch)
    dispatched = module.auto_maintenance_retry_dispatch(
        workspace_root=fixture["workspace"],
        aoa_root=fixture["aoa_root"],
        apply=True,
        limit=1,
        now_epoch=112.0,
    )
    item = _queue_item(fixture)
    result = dispatched["results"][0]
    assert launch_called is False
    assert result["launch_status"] == (
        "deep_admission_refused_capture_retry_queue_identity_"
        "reconciliation_unresolved"
    )
    assert result["disposition"] == "admission_refused"
    assert result["diagnostics"] == [
        "capture_retry_queue_identity_reconciliation_unresolved"
    ]
    assert item["attempts_started"] == 0
    assert item["in_flight"] is False
    assert item["next_attempt_epoch"] == 0.0


@pytest.mark.parametrize(
    ("index_case", "expected_relation"),
    (("wrong", "conflict"), ("missing", "unresolved"), ("invalid", "unresolved")),
    ids=("wrong-nonnegative", "missing", "invalid"),
)
def test_same_epoch_epoch_index_mismatch_preserves_obligation_and_refuses_deep_admission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    index_case: str,
    expected_relation: str,
) -> None:
    fixture = _fixture(tmp_path, monkeypatch, session_id=f"same-epoch-{index_case}")
    initial_options = dict(_queue_item(fixture)["options"])
    current_result = module._capture_identity_current(
        aoa_root=fixture["aoa_root"],
        session_id=fixture["session_id"],
        configured_session_dir=fixture["session_dir"],
    )
    assert current_result["ok"] is True
    assert current_result["identity"]["epoch_index"] == 0

    def corrupt_index(payload: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        item = payload["items"][f"deep:{fixture['session_id']}"]
        options = item["options"]
        if index_case == "missing":
            options.pop("required_capture_epoch_index", None)
        elif index_case == "invalid":
            options["required_capture_epoch_index"] = "not-an-index"
        else:
            options["required_capture_epoch_index"] = 999
        return {"status": "corrupted_same_epoch_index"}, True

    module.mutate_auto_maintenance_retry_queue(
        fixture["aoa_root"],
        corrupt_index,
        now_epoch=113.0,
    )
    corrupted_options = dict(_queue_item(fixture)["options"])
    for key in (
        "required_capture_epoch_id",
        "required_capture_bytes",
        "required_capture_sha256",
        "required_capture_chain_sha256",
        "required_capture_ref",
    ):
        assert corrupted_options[key] == initial_options[key]

    reconciled = module.reconcile_session_projection_freshness_obligation(
        aoa_root=fixture["aoa_root"],
        session_id=fixture["session_id"],
        session_dir=fixture["session_dir"],
        transcript_path=fixture["transcript"],
        freshness_reason="same_epoch_index_mismatch",
        now_epoch=114.0,
        create_if_missing=False,
    )
    assert reconciled["status"] == "identity_reconciliation_unresolved"
    assert reconciled["diagnostic"] == (
        "capture_retry_queue_identity_reconciliation_unresolved"
    )
    assert reconciled["reason"] == f"current_identity_relation:{expected_relation}"
    after_reconcile = _queue_item(fixture)
    after_reconcile_options = after_reconcile["options"]
    for key in (
        "required_capture_epoch_id",
        "required_capture_bytes",
        "required_capture_sha256",
        "required_capture_chain_sha256",
        "required_capture_ref",
    ):
        assert after_reconcile_options[key] == initial_options[key]
    if index_case == "missing":
        assert "required_capture_epoch_index" not in after_reconcile_options
    elif index_case == "invalid":
        assert after_reconcile_options["required_capture_epoch_index"] == "not-an-index"
    else:
        assert after_reconcile_options["required_capture_epoch_index"] == 999

    def make_due(payload: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        item = payload["items"][f"deep:{fixture['session_id']}"]
        item["next_attempt_epoch"] = 0.0
        item["next_attempt_at"] = module.auto_maintenance_retry_iso(0.0)
        return {"status": "due"}, True

    module.mutate_auto_maintenance_retry_queue(
        fixture["aoa_root"],
        make_due,
        now_epoch=115.0,
    )
    launch_called = False

    def forbidden_launch(**_kwargs: Any) -> dict[str, Any]:
        nonlocal launch_called
        launch_called = True
        raise AssertionError("same-epoch index mismatch must not launch deep work")

    monkeypatch.setattr(module, "auto_maintenance_resource_launch", forbidden_launch)
    dispatched = module.auto_maintenance_retry_dispatch(
        workspace_root=fixture["workspace"],
        aoa_root=fixture["aoa_root"],
        apply=True,
        limit=1,
        now_epoch=115.0,
    )
    result = dispatched["results"][0]
    assert launch_called is False
    assert result["launch_status"] == (
        "deep_admission_refused_capture_retry_queue_identity_"
        "reconciliation_unresolved"
    )
    assert result["disposition"] == "admission_refused"
    assert result["diagnostics"] == [
        "capture_retry_queue_identity_reconciliation_unresolved"
    ]
    item = _queue_item(fixture)
    assert item["attempts_started"] == 0
    assert item["in_flight"] is False
    assert item["status"] == "pending"
    assert item["options"] == after_reconcile_options
