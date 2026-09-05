"""Focused tests for the portable epistemic action event-chain source.

These tests intentionally load the small event-chain implementation directly.
The session-memory integration test module remains responsible for the wider
runtime surface; these contract tests do not need to import that monolith.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

import pytest


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "aoa_epistemic_action_event_chain.py"
)
spec = importlib.util.spec_from_file_location(
    "aoa_epistemic_action_event_chain_test_source",
    SCRIPT,
)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _epistemic_prediction_kwargs(
    label: str,
    *,
    expected_facets: list[str] | None = None,
    window_start: str = "9999-12-31T23:59:59Z",
    window_end: str = "9999-12-31T23:59:59.999999Z",
) -> dict[str, object]:
    return {
        "request_id": f"request-{label}",
        "attempt_id": f"attempt-{label}",
        "pre_action_marker": module.epistemic_digest(f"pre-action-{label}"),
        "observation_window_digest": module.epistemic_digest(
            f"window-{label}"
        ),
        "observation_window_start_at": window_start,
        "observation_window_end_at": window_end,
        "expected_observation_facet_ids": list(expected_facets or []),
        "hypothesis_digest": module.epistemic_digest(f"hypothesis-{label}"),
        "expected_change_digest": module.epistemic_digest(
            f"expected-change-{label}"
        ),
        "falsifier_digest": module.epistemic_digest(f"falsifier-{label}"),
        "confidence": 0.75,
        "action_plan_digest": module.epistemic_digest(f"plan-{label}"),
        "tool_use_id": f"tool-{label}",
    }


def _epistemic_action_kwargs(label: str) -> dict[str, object]:
    return {
        "attempt_id": f"attempt-{label}",
        "tool_use_id": f"tool-{label}",
        "action_kind": "bounded_action",
        "effect_class": "repo_mutation",
        "action_started_at": "9999-12-31T23:59:59Z",
    }


def _epistemic_observation_kwargs(
    label: str,
    *,
    observed_at: str | None = "9999-12-31T23:59:59.500000Z",
    observed_facets: list[str] | None = None,
) -> dict[str, object]:
    return {
        "attempt_id": f"attempt-{label}",
        "tool_use_id": f"tool-{label}",
        "evidence_ref_ids": [f"evidence-{label}"],
        "observed_at": observed_at,
        "observed_observation_facet_ids": list(observed_facets or []),
    }


def _canonical_epistemic_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def _epistemic_event_id(event_type: str, identity: object) -> str:
    return "event:" + hashlib.sha256(
        _canonical_epistemic_json(
            {"event_type": event_type, "identity": identity}
        ).encode("utf-8")
    ).hexdigest()


def _epistemic_prediction_commitment_digest(event: dict[str, object]) -> str:
    material = {
        "request_id": event["request_id"],
        "attempt_id": event["attempt_id"],
        "prediction_id": event["prediction_id"],
        "action_id": event["action_id"],
        "tool_use_id": event.get("tool_use_id"),
        "expected_observation_digest": event[
            "expected_observation_digest"
        ],
        "pre_action_marker": event["pre_action_marker"],
        "observation_window_digest": event["observation_window_digest"],
        "observation_window_start_at": event[
            "observation_window_start_at"
        ],
        "observation_window_end_at": event["observation_window_end_at"],
        "expected_observation_facet_ids": event[
            "expected_observation_facet_ids"
        ],
        "hypothesis_digest": event["hypothesis_digest"],
        "expected_change_digest": event["expected_change_digest"],
        "falsifier_digest": event["falsifier_digest"],
        "confidence": event["confidence"],
        "action_plan_digest": event["action_plan_digest"],
    }
    return module.epistemic_digest(_canonical_epistemic_json(material))


def _rehash_epistemic_store(
    store: Path,
    events: list[dict[str, object]] | None = None,
) -> list[dict[str, object]]:
    if events is None:
        events = [
            json.loads(line)
            for line in store.read_text(encoding="utf-8").splitlines()
        ]
    previous_digest = "genesis"
    for sequence, event in enumerate(events, start=1):
        event["sequence"] = sequence
        event["prev_event_digest"] = previous_digest
        material = {
            key: value for key, value in event.items() if key != "event_digest"
        }
        event["event_digest"] = module.epistemic_digest(
            _canonical_epistemic_json(material)
        )
        previous_digest = str(event["event_digest"])
    store.write_text(
        "".join(
            _canonical_epistemic_json(event) + "\n" for event in events
        ),
        encoding="utf-8",
    )
    return events


def _create_epistemic_candidate_store(store: Path, label: str) -> None:
    chain = module.EpistemicActionChain.create(
        store,
        session_id=f"session-{label}",
        turn_id=f"turn-{label}",
    )
    chain.commit_prediction(
        f"action-{label}",
        module.epistemic_digest(f"expected-{label}"),
        **_epistemic_prediction_kwargs(label),
        prediction_id=f"prediction-{label}",
        created_at="2026-08-26T00:00:00Z",
    )
    chain.bind_action(
        f"action-{label}",
        module.epistemic_digest(f"action-{label}"),
        **_epistemic_action_kwargs(label),
        created_at="2026-08-26T00:00:01Z",
    )
    chain.record_observation(
        f"action-{label}",
        module.epistemic_digest(f"actual-{label}"),
        **_epistemic_observation_kwargs(label),
        observation_id=f"observation-{label}",
        created_at="2026-08-26T00:00:02Z",
    )
    chain.derive_discrepancy(
        f"action-{label}",
        created_at="2026-08-26T00:00:03Z",
    )


def test_epistemic_action_chain_replays_prediction_action_observation_and_candidate(
    tmp_path: Path,
) -> None:
    store = tmp_path / "epistemic-action.jsonl"
    chain = module.EpistemicActionChain.create(
        store,
        session_id="session-epistemic-1",
        turn_id="turn-epistemic-1",
    )
    expected = module.epistemic_digest("expected-observation-1")
    action_digest = module.epistemic_digest("action-1")
    observed = module.epistemic_digest("actual-observation-1")

    prediction = chain.commit_prediction(
        "action-epistemic-1",
        expected,
        **_epistemic_prediction_kwargs("epistemic-1"),
        prediction_id="prediction-epistemic-1",
        created_at="2026-08-26T00:00:00Z",
    )
    action = chain.bind_action(
        "action-epistemic-1",
        action_digest,
        **_epistemic_action_kwargs("epistemic-1"),
        created_at="2026-08-26T00:00:01Z",
    )
    observation = chain.record_observation(
        "action-epistemic-1",
        observed,
        **_epistemic_observation_kwargs("epistemic-1"),
        observation_id="observation-epistemic-1",
        created_at="2026-08-26T00:00:02Z",
    )
    derived = chain.derive_discrepancy(
        "action-epistemic-1",
        alternative_explanation_digest=module.epistemic_digest(
            "alternative-epistemic-1"
        ),
        model_update_digest=module.epistemic_digest("model-update-epistemic-1"),
        next_distinguishing_action_digest=module.epistemic_digest(
            "next-action-epistemic-1"
        ),
        created_at="2026-08-26T00:00:03Z",
    )

    assert [
        prediction["sequence"],
        action["sequence"],
        observation["sequence"],
    ] == [1, 2, 3]
    assert derived["discrepancy"]["kind"] == "mismatch"
    assert derived["model_update_candidate"]["status"] == "shadow_only"
    assert derived["model_update_candidate"]["update_kind"] == "review_prediction"

    replayed = module.EpistemicActionChain.load(store)
    assert replayed.commit_prediction(
        "action-epistemic-1",
        expected,
        **_epistemic_prediction_kwargs("epistemic-1"),
        prediction_id="prediction-epistemic-1",
    )["event_id"] == prediction["event_id"]
    assert replayed.bind_action(
        "action-epistemic-1",
        action_digest,
        **_epistemic_action_kwargs("epistemic-1"),
    )["event_id"] == action["event_id"]
    assert replayed.record_observation(
        "action-epistemic-1",
        observed,
        **_epistemic_observation_kwargs("epistemic-1"),
        observation_id="observation-epistemic-1",
    )["event_id"] == observation["event_id"]
    replayed_derived = replayed.derive_discrepancy("action-epistemic-1")
    artifact = replayed.inspect()

    assert replayed_derived["event"]["event_id"] == derived["event"]["event_id"]
    assert artifact["event_count"] == 5
    assert [event["sequence"] for event in artifact["events"]] == [1, 2, 3, 4, 5]
    assert module.validate_epistemic_action_chain_artifact(artifact)["ok"] is True
    from jsonschema import Draft202012Validator

    schema = json.loads(
        (
            SCRIPT.parents[1]
            / "schemas"
            / "epistemic-action-event-chain.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(artifact)
    forbidden_fields = {"prompt", "payload", "tool_input", "tool_output", "transcript"}
    for event in artifact["events"]:
        assert not forbidden_fields.intersection(event)
        assert "PRIVATE_EPISTEMIC_RAW_SENTINEL" not in json.dumps(event)


def test_epistemic_action_chain_rejects_ordering_post_hoc_and_immutable_prediction_conflicts(
    tmp_path: Path,
) -> None:
    before_store = tmp_path / "before-prediction.jsonl"
    before = module.EpistemicActionChain.create(
        before_store,
        session_id="session-ordering",
        turn_id="turn-ordering",
    )
    with pytest.raises(module.EpistemicActionOrderingError) as ordering:
        before.bind_action(
            "action-ordering",
            module.epistemic_digest("action"),
            **_epistemic_action_kwargs("ordering"),
        )
    assert ordering.value.reason_code == "action_before_prediction"
    assert ordering.value.state == "refused"
    assert json.loads(json.dumps(before.inspect()))["chain_status"] == "refused"

    store = tmp_path / "immutable-prediction.jsonl"
    chain = module.EpistemicActionChain.create(
        store,
        session_id="session-immutable",
        turn_id="turn-immutable",
    )
    first = chain.commit_prediction(
        "action-immutable",
        module.epistemic_digest("expected-a"),
        **_epistemic_prediction_kwargs("immutable"),
        prediction_id="prediction-immutable",
    )
    chain.bind_action(
        "action-immutable",
        module.epistemic_digest("action"),
        **_epistemic_action_kwargs("immutable"),
    )
    with pytest.raises(module.EpistemicActionOrderingError) as post_hoc:
        chain.commit_prediction(
            "action-immutable",
            module.epistemic_digest("expected-b"),
            **_epistemic_prediction_kwargs("immutable"),
            prediction_id="prediction-late",
        )
    assert post_hoc.value.reason_code == "post_hoc_prediction"
    with pytest.raises(module.EpistemicActionConflictError) as immutable:
        chain.commit_prediction(
            "action-immutable",
            module.epistemic_digest("expected-b"),
            **_epistemic_prediction_kwargs("immutable"),
            prediction_id="prediction-immutable",
        )
    assert immutable.value.reason_code == "prediction_immutable_conflict"
    assert immutable.value.state == "ambiguous"
    assert first["sequence"] == 1
    events = chain.inspect()["events"]
    assert len(events) == 4
    assert [event["event_type"] for event in events] == [
        "prediction_commitment",
        "action_binding",
        "refusal",
        "refusal",
    ]
    assert [event["state"] for event in events] == [
        "committed",
        "bound",
        "refused",
        "ambiguous",
    ]
    assert [event["reason_code"] for event in events[2:]] == [
        "post_hoc_prediction",
        "prediction_immutable_conflict",
    ]
    assert sum(
        event["event_type"] == "prediction_commitment" for event in events
    ) == 1
    assert sum(event["event_type"] == "action_binding" for event in events) == 1


def test_epistemic_action_chain_preserves_interruption_missing_and_shadow_only_candidate(
    tmp_path: Path,
) -> None:
    store = tmp_path / "epistemic-interruption.jsonl"
    chain = module.EpistemicActionChain.create(
        store,
        session_id="session-interruption",
        turn_id="turn-interruption",
    )
    chain.commit_prediction(
        "action-interruption",
        module.epistemic_digest("expected"),
        **_epistemic_prediction_kwargs("interruption"),
        prediction_id="prediction-interruption",
    )
    chain.bind_action(
        "action-interruption",
        module.epistemic_digest("action"),
        **_epistemic_action_kwargs("interruption"),
    )
    missing = chain.record_observation(
        "action-interruption",
        **_epistemic_observation_kwargs("interruption", observed_at=None),
        observation_id="observation-interruption",
        observation_status="unknown",
        reason_code="interrupted",
    )
    derived = chain.derive_discrepancy("action-interruption")
    candidate = chain.inspect_model_update_candidate("action-interruption")

    assert missing["state"] == "unknown"
    assert missing["observation_status"] == "unknown"
    assert derived["state"] == "unknown"
    assert derived["discrepancy"]["kind"] == "unknown"
    assert derived["model_update_candidate"]["status"] == "shadow_only"
    assert derived["model_update_candidate"]["update_kind"] == "withhold_update"
    assert candidate["state"] == "shadow_only"
    assert chain.inspect()["chain_status"] == "unknown"
    assert module.validate_epistemic_action_chain(store)["ok"] is True

    compaction_store = tmp_path / "epistemic-compaction.jsonl"
    compaction = module.EpistemicActionChain.create(
        compaction_store,
        session_id="session-compaction",
        turn_id="turn-compaction",
    )
    compaction.commit_prediction(
        "action-compaction",
        module.epistemic_digest("expected-compaction"),
        **_epistemic_prediction_kwargs("compaction"),
        prediction_id="prediction-compaction",
    )
    compaction.bind_action(
        "action-compaction",
        module.epistemic_digest("action-compaction"),
        **_epistemic_action_kwargs("compaction"),
    )
    compaction.record_observation(
        "action-compaction",
        **_epistemic_observation_kwargs("compaction", observed_at=None),
        observation_id="observation-compaction",
        observation_status="missing",
        reason_code="compaction_boundary",
    )
    compaction_result = compaction.derive_discrepancy("action-compaction")
    assert compaction_result["state"] == "unknown"
    assert compaction_result["discrepancy"]["kind"] == "unknown"
    assert module.validate_epistemic_action_chain(compaction_store)["ok"] is True


def test_epistemic_action_chain_rejects_conflicting_observations_as_ambiguous(
    tmp_path: Path,
) -> None:
    store = tmp_path / "epistemic-conflict.jsonl"
    chain = module.EpistemicActionChain.create(
        store,
        session_id="session-conflict",
        turn_id="turn-conflict",
    )
    chain.commit_prediction(
        "action-conflict",
        module.epistemic_digest("expected"),
        **_epistemic_prediction_kwargs("conflict"),
        prediction_id="prediction-conflict",
    )
    chain.bind_action(
        "action-conflict",
        module.epistemic_digest("action"),
        **_epistemic_action_kwargs("conflict"),
    )
    first = chain.record_observation(
        "action-conflict",
        module.epistemic_digest("actual-a"),
        **_epistemic_observation_kwargs("conflict"),
        observation_id="observation-a",
    )
    assert chain.record_observation(
        "action-conflict",
        module.epistemic_digest("actual-a"),
        **_epistemic_observation_kwargs("conflict"),
        observation_id="observation-a",
    )["event_id"] == first["event_id"]
    with pytest.raises(module.EpistemicActionConflictError) as conflict:
        chain.record_observation(
            "action-conflict",
            module.epistemic_digest("actual-b"),
            **_epistemic_observation_kwargs("conflict"),
            observation_id="observation-b",
        )
    assert conflict.value.reason_code == "conflicting_observation"
    assert conflict.value.state == "ambiguous"
    derived = chain.derive_discrepancy("action-conflict")
    assert derived["discrepancy"]["kind"] == "ambiguous"
    assert chain.inspect()["chain_status"] == "ambiguous"
    assert any(
        event["event_type"] == "observation_conflict"
        for event in chain.inspect()["events"]
    )


def test_epistemic_action_chain_enforces_public_safe_identifiers_and_digests(
    tmp_path: Path,
) -> None:
    store = tmp_path / "epistemic-privacy.jsonl"
    public_session = module.epistemic_public_id(
        "session",
        "private session coordinate",
    )
    public_turn = module.epistemic_public_id("turn", "private turn coordinate")
    chain = module.EpistemicActionChain.create(
        store,
        session_id=public_session,
        turn_id=public_turn,
    )
    with pytest.raises(module.EpistemicActionPrivacyError) as unsafe_id:
        chain.commit_prediction(
            "raw action coordinate with spaces",
            module.epistemic_digest("expected"),
            **_epistemic_prediction_kwargs("privacy"),
        )
    assert unsafe_id.value.reason_code == "safe_identifier_invalid"
    with pytest.raises(module.EpistemicActionPrivacyError) as unsafe_digest:
        chain.record_observation(
            "action-safe",
            "raw tool output is not a digest",
            **_epistemic_observation_kwargs("privacy"),
        )
    assert unsafe_digest.value.reason_code == "digest_invalid"
    assert not store.exists()
    assert public_session.startswith("id:")
    assert public_turn.startswith("id:")
    assert "private session coordinate" not in json.dumps(chain.inspect())
    assert "raw tool output is not a digest" not in json.dumps(chain.inspect())


def test_epistemic_action_chain_detects_stale_writers_and_tampered_replay(
    tmp_path: Path,
) -> None:
    store = tmp_path / "epistemic-concurrency.jsonl"
    writer = module.EpistemicActionChain.create(
        store,
        session_id="session-concurrency",
        turn_id="turn-concurrency",
    )
    stale = module.EpistemicActionChain.load(
        store,
        session_id="session-concurrency",
        turn_id="turn-concurrency",
    )
    writer.commit_prediction(
        "action-concurrency-a",
        module.epistemic_digest("expected-a"),
        **_epistemic_prediction_kwargs("concurrency-a"),
    )
    with pytest.raises(module.EpistemicActionConcurrencyError) as concurrency:
        stale.commit_prediction(
            "action-concurrency-b",
            module.epistemic_digest("expected-b"),
            **_epistemic_prediction_kwargs("concurrency-b"),
        )
    assert concurrency.value.reason_code == "concurrency_conflict"
    stale_artifact = module.EpistemicActionChain.load(store).inspect()
    assert stale_artifact["event_count"] == 1
    assert [event["event_type"] for event in stale_artifact["events"]] == [
        "prediction_commitment"
    ]
    assert not any(
        event.get("action_id") == "action-concurrency-b"
        for event in stale_artifact["events"]
    )
    current = module.EpistemicActionChain.load(store)
    with pytest.raises(module.EpistemicActionConcurrencyError) as sequence:
        current.commit_prediction(
            "action-concurrency-c",
            module.epistemic_digest("expected-c"),
            **_epistemic_prediction_kwargs("concurrency-c"),
            expected_sequence=0,
        )
    assert sequence.value.reason_code == "concurrency_conflict"

    lines = store.read_text(encoding="utf-8").splitlines()
    tampered = json.loads(lines[0])
    tampered["state"] = "ready"
    store.write_text(
        json.dumps(tampered, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(module.EpistemicActionIntegrityError) as integrity:
        module.EpistemicActionChain.load(store)
    assert integrity.value.reason_code in {
        "event_digest_mismatch",
        "event_shape_invalid",
    }


def test_epistemic_action_chain_binds_attempt_and_tool_use_identity(
    tmp_path: Path,
) -> None:
    store = tmp_path / "epistemic-tool-use.jsonl"
    chain = module.EpistemicActionChain.create(
        store,
        session_id="session-tool-use",
        turn_id="turn-tool-use",
    )
    chain.commit_prediction(
        "action-tool-use",
        module.epistemic_digest("expected"),
        **_epistemic_prediction_kwargs("tool-use"),
    )
    mismatched_action = _epistemic_action_kwargs("tool-use")
    mismatched_action["tool_use_id"] = "tool-other"
    with pytest.raises(module.EpistemicActionConflictError) as mismatch:
        chain.bind_action(
            "action-tool-use",
            module.epistemic_digest("action"),
            **mismatched_action,
        )
    assert mismatch.value.reason_code == "tool_use_identity_conflict"
    assert not any(
        event["event_type"] == "action_binding"
        for event in chain.inspect()["events"]
    )


def test_epistemic_action_chain_rejects_timestamp_post_hoc_commitment(
    tmp_path: Path,
) -> None:
    store = tmp_path / "epistemic-timestamp.jsonl"
    chain = module.EpistemicActionChain.create(
        store,
        session_id="session-timestamp",
        turn_id="turn-timestamp",
    )
    chain.commit_prediction(
        "action-timestamp",
        module.epistemic_digest("expected"),
        **_epistemic_prediction_kwargs("timestamp"),
        created_at="2026-08-26T00:00:02Z",
    )
    action_kwargs = _epistemic_action_kwargs("timestamp")
    action_kwargs["action_started_at"] = "2026-08-26T00:00:01Z"
    with pytest.raises(module.EpistemicActionOrderingError) as post_hoc:
        chain.bind_action(
            "action-timestamp",
            module.epistemic_digest("action"),
            **action_kwargs,
        )
    assert post_hoc.value.reason_code == "post_hoc_prediction"
    assert not any(
        event["event_type"] == "action_binding"
        for event in chain.inspect()["events"]
    )


def test_epistemic_action_chain_enforces_strict_time_and_observation_window(
    tmp_path: Path,
) -> None:
    equal_store = tmp_path / "epistemic-equal-time.jsonl"
    equal = module.EpistemicActionChain.create(
        equal_store,
        session_id="session-equal-time",
        turn_id="turn-equal-time",
    )
    equal.commit_prediction(
        "action-equal-time",
        module.epistemic_digest("expected-equal-time"),
        **_epistemic_prediction_kwargs("equal-time"),
        created_at="2026-08-26T00:00:00.000000Z",
    )
    equal_action = _epistemic_action_kwargs("equal-time")
    equal_action["action_started_at"] = "2026-08-26T00:00:00.000000Z"
    with pytest.raises(module.EpistemicActionOrderingError) as equal_error:
        equal.bind_action(
            "action-equal-time",
            module.epistemic_digest("action-equal-time"),
            **equal_action,
        )
    assert equal_error.value.reason_code == "post_hoc_prediction"

    def build_windowed(label: str) -> module.EpistemicActionChain:
        chain = module.EpistemicActionChain.create(
            tmp_path / f"epistemic-window-{label}.jsonl",
            session_id=f"session-window-{label}",
            turn_id=f"turn-window-{label}",
        )
        chain.commit_prediction(
            f"action-window-{label}",
            module.epistemic_digest(f"expected-window-{label}"),
            **_epistemic_prediction_kwargs(
                label,
                window_start="2026-08-26T00:00:01.000000Z",
                window_end="2026-08-26T00:00:04.000000Z",
            ),
            created_at="2026-08-26T00:00:00.000000Z",
        )
        action = _epistemic_action_kwargs(label)
        action["action_started_at"] = "2026-08-26T00:00:01.000000Z"
        chain.bind_action(
            f"action-window-{label}",
            module.epistemic_digest(f"action-window-{label}"),
            **action,
        )
        return chain

    early = build_windowed("early")
    early_observation = _epistemic_observation_kwargs(
        "early",
        observed_at="2026-08-26T00:00:00.500000Z",
    )
    with pytest.raises(module.EpistemicActionOrderingError) as early_error:
        early.record_observation(
            "action-window-early",
            module.epistemic_digest("actual-early"),
            **early_observation,
        )
    assert early_error.value.reason_code == "observation_outside_window"

    late = build_windowed("late")
    late_observation = _epistemic_observation_kwargs(
        "late",
        observed_at="2026-08-26T00:00:05.000000Z",
    )
    with pytest.raises(module.EpistemicActionOrderingError) as late_error:
        late.record_observation(
            "action-window-late",
            module.epistemic_digest("actual-late"),
            **late_observation,
        )
    assert late_error.value.reason_code == "observation_outside_window"


def test_epistemic_action_chain_requires_observed_evidence_and_timestamp(
    tmp_path: Path,
) -> None:
    store = tmp_path / "epistemic-observation-admission.jsonl"
    chain = module.EpistemicActionChain.create(
        store,
        session_id="session-observation-admission",
        turn_id="turn-observation-admission",
    )
    chain.commit_prediction(
        "action-observation-admission",
        module.epistemic_digest("expected-observation-admission"),
        **_epistemic_prediction_kwargs("observation-admission"),
    )
    chain.bind_action(
        "action-observation-admission",
        module.epistemic_digest("action-observation-admission"),
        **_epistemic_action_kwargs("observation-admission"),
    )
    with pytest.raises(module.EpistemicActionPrivacyError) as evidence_error:
        chain.record_observation(
            "action-observation-admission",
            module.epistemic_digest("actual-observation-admission"),
            attempt_id="attempt-observation-admission",
            tool_use_id="tool-observation-admission",
            evidence_ref_ids=[],
            observed_at="9999-12-31T23:59:59.500000Z",
        )
    assert evidence_error.value.reason_code == "observation_evidence_required"
    with pytest.raises(module.EpistemicActionPrivacyError) as timestamp_error:
        chain.record_observation(
            "action-observation-admission",
            module.epistemic_digest("actual-observation-admission"),
            attempt_id="attempt-observation-admission",
            tool_use_id="tool-observation-admission",
            evidence_ref_ids=["evidence-observation-admission"],
        )
    assert timestamp_error.value.reason_code == "observation_timestamp_required"
    assert not any(
        event["event_type"] == "observation" for event in chain.inspect()["events"]
    )


def test_epistemic_action_chain_rejects_null_required_timestamps(
    tmp_path: Path,
) -> None:
    prediction_store = tmp_path / "epistemic-null-created-at.jsonl"
    prediction_chain = module.EpistemicActionChain.create(
        prediction_store,
        session_id="session-null-created-at",
        turn_id="turn-null-created-at",
    )
    with pytest.raises(module.EpistemicActionPrivacyError) as created_error:
        prediction_chain.commit_prediction(
            "action-null-created-at",
            module.epistemic_digest("expected-null-created-at"),
            **_epistemic_prediction_kwargs("null-created-at"),
            created_at=None,
        )
    assert created_error.value.reason_code == "timestamp_invalid"
    assert prediction_chain.inspect()["event_count"] == 0
    assert not prediction_store.exists()

    action_store = tmp_path / "epistemic-null-action-started-at.jsonl"
    action_chain = module.EpistemicActionChain.create(
        action_store,
        session_id="session-null-action-started-at",
        turn_id="turn-null-action-started-at",
    )
    action_chain.commit_prediction(
        "action-null-action-started-at",
        module.epistemic_digest("expected-null-action-started-at"),
        **_epistemic_prediction_kwargs("null-action-started-at"),
        created_at="2026-08-26T00:00:00Z",
    )
    null_action = _epistemic_action_kwargs("null-action-started-at")
    null_action["action_started_at"] = None
    with pytest.raises(module.EpistemicActionPrivacyError) as action_error:
        action_chain.bind_action(
            "action-null-action-started-at",
            module.epistemic_digest("action-null-action-started-at"),
            **null_action,
        )
    assert action_error.value.reason_code == "timestamp_invalid"
    assert [event["event_type"] for event in action_chain.inspect()["events"]] == [
        "prediction_commitment"
    ]

    valid_action = _epistemic_action_kwargs("null-action-started-at")
    action_chain.bind_action(
        "action-null-action-started-at",
        module.epistemic_digest("action-null-action-started-at"),
        **valid_action,
        created_at="2026-08-26T00:00:01Z",
    )
    null_observation = _epistemic_observation_kwargs(
        "null-action-started-at",
        observed_at=None,
    )
    with pytest.raises(module.EpistemicActionPrivacyError) as observation_error:
        action_chain.record_observation(
            "action-null-action-started-at",
            module.epistemic_digest("actual-null-observed-at"),
            **null_observation,
            observation_id="observation-null-observed-at",
        )
    assert observation_error.value.reason_code == "timestamp_invalid"
    assert [event["event_type"] for event in action_chain.inspect()["events"]] == [
        "prediction_commitment",
        "action_binding",
    ]


def test_epistemic_action_chain_rejects_invalid_required_timestamps_before_replay(
    tmp_path: Path,
) -> None:
    missing = object()
    cases = [
        ("created-at-missing", 0, "created_at", missing),
        ("created-at-null", 0, "created_at", None),
        ("created-at-non-string", 0, "created_at", 17),
        ("created-at-malformed", 0, "created_at", "2026-13-26T00:00:00Z"),
        (
            "window-start-null",
            0,
            "observation_window_start_at",
            None,
        ),
        ("action-started-missing", 1, "action_started_at", missing),
        (
            "action-started-malformed",
            1,
            "action_started_at",
            "2026-08-26T00:00:00+00:00",
        ),
        ("observed-at-missing", 2, "observed_at", missing),
        ("observed-at-null", 2, "observed_at", None),
        ("observed-at-non-string", 2, "observed_at", 23),
    ]
    for label, event_index, field, value in cases:
        store = tmp_path / f"epistemic-invalid-timestamp-{label}.jsonl"
        _create_epistemic_candidate_store(store, label)
        events = _rehash_epistemic_store(store)
        if value is missing:
            del events[event_index][field]
        else:
            events[event_index][field] = value
        _rehash_epistemic_store(store, events)

        result = module.validate_epistemic_action_chain(store)

        assert result["ok"] is False, label
        assert result["diagnostics"] == ["timestamp_invalid"], label
        with pytest.raises(module.EpistemicActionError) as replay_error:
            module.EpistemicActionChain.load(store)
        assert replay_error.value.reason_code == "timestamp_invalid", label


def test_epistemic_action_event_schema_requires_type_specific_timestamps(
    tmp_path: Path,
) -> None:
    from jsonschema import Draft202012Validator

    store = tmp_path / "epistemic-schema-timestamps.jsonl"
    chain = module.EpistemicActionChain.create(
        store,
        session_id="session-schema-timestamps",
        turn_id="turn-schema-timestamps",
    )
    chain.commit_prediction(
        "action-schema-timestamps",
        module.epistemic_digest("expected-schema-timestamps"),
        **_epistemic_prediction_kwargs("schema-timestamps"),
        prediction_id="prediction-schema-timestamps",
    )
    chain.bind_action(
        "action-schema-timestamps",
        module.epistemic_digest("action-schema-timestamps"),
        **_epistemic_action_kwargs("schema-timestamps"),
    )
    chain.record_observation(
        "action-schema-timestamps",
        module.epistemic_digest("actual-schema-timestamps"),
        **_epistemic_observation_kwargs("schema-timestamps"),
        observation_id="observation-schema-timestamps",
    )
    chain.derive_discrepancy(
        "action-schema-timestamps",
        alternative_explanation_digest=module.epistemic_digest(
            "alternative-schema-timestamps"
        ),
        model_update_digest=module.epistemic_digest("update-schema-timestamps"),
        next_distinguishing_action_digest=module.epistemic_digest(
            "next-schema-timestamps"
        ),
    )
    artifact = chain.inspect()
    schema = json.loads(
        (
            SCRIPT.parents[1]
            / "schemas"
            / "epistemic-action-event-chain.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    validator.validate(artifact)

    for event_index, field in (
        (0, "observation_window_start_at"),
        (1, "action_started_at"),
        (2, "observed_at"),
    ):
        invalid = copy.deepcopy(artifact)
        del invalid["events"][event_index][field]
        assert list(validator.iter_errors(invalid)), field


def test_epistemic_action_chain_derives_partial_and_rejects_conflicting_classification(
    tmp_path: Path,
) -> None:
    store = tmp_path / "epistemic-partial.jsonl"
    chain = module.EpistemicActionChain.create(
        store,
        session_id="session-partial",
        turn_id="turn-partial",
    )
    chain.commit_prediction(
        "action-partial",
        module.epistemic_digest("expected"),
        **_epistemic_prediction_kwargs(
            "partial",
            expected_facets=["facet-partial-a", "facet-partial-b"],
        ),
    )
    chain.bind_action(
        "action-partial",
        module.epistemic_digest("action"),
        **_epistemic_action_kwargs("partial"),
    )
    chain.record_observation(
        "action-partial",
        module.epistemic_digest("actual"),
        **_epistemic_observation_kwargs(
            "partial",
            observed_facets=["facet-partial-a"],
        ),
    )
    derived = chain.derive_discrepancy(
        "action-partial",
        discrepancy_kind="partial_match",
        model_update_digest=module.epistemic_digest("update"),
    )
    assert derived["discrepancy"]["kind"] == "partial_match"
    assert derived["model_update_candidate"]["update_kind"] == "review_prediction"
    candidate = derived["model_update_candidate"]
    assert candidate["discrepancy_kind"] == "partial_match"
    assert candidate["update_kind"] == "review_prediction"
    assert candidate["model_update_digest"] == module.epistemic_digest("update")
    with pytest.raises(module.EpistemicActionConflictError) as candidate_conflict:
        chain.derive_discrepancy(
            "action-partial",
            model_update_digest=module.epistemic_digest("different-update"),
        )
    assert candidate_conflict.value.reason_code == "model_update_conflict"
    with pytest.raises(module.EpistemicActionConflictError) as classification:
        chain.derive_discrepancy(
            "action-partial",
            discrepancy_kind="mismatch",
        )
    assert classification.value.reason_code == "discrepancy_classification_conflict"


def test_epistemic_action_chain_rejects_conflicting_rederivation(
    tmp_path: Path,
) -> None:
    store = tmp_path / "epistemic-rederivation.jsonl"
    _create_epistemic_candidate_store(store, "rederivation")
    chain = module.EpistemicActionChain.load(store)

    with pytest.raises(module.EpistemicActionConflictError) as conflict:
        chain.derive_discrepancy(
            "action-rederivation",
            discrepancy_kind="match",
        )

    assert conflict.value.reason_code == (
        "discrepancy_classification_conflict"
    )
    assert conflict.value.state == "ambiguous"
    assert chain.inspect()["chain_status"] == "ambiguous"
    assert not any(
        event["event_type"] == "discrepancy"
        and event["discrepancy_kind"] == "match"
        for event in chain.inspect()["events"]
    )


def test_epistemic_action_chain_serializes_concurrent_writers_and_duplicate_json(
    tmp_path: Path,
) -> None:
    store = tmp_path / "epistemic-race.jsonl"
    first = module.EpistemicActionChain.create(
        store,
        session_id="session-race",
        turn_id="turn-race",
    )
    second = module.EpistemicActionChain.load(
        store,
        session_id="session-race",
        turn_id="turn-race",
    )
    barrier = threading.Barrier(2)
    results: list[str] = []

    def commit(chain: object, label: str) -> None:
        barrier.wait()
        try:
            chain.commit_prediction(
                f"action-{label}",
                module.epistemic_digest(f"expected-{label}"),
                **_epistemic_prediction_kwargs(label),
            )
            results.append("committed")
        except module.EpistemicActionConcurrencyError:
            results.append("concurrency_conflict")

    workers = [
        threading.Thread(target=commit, args=(first, "race-a")),
        threading.Thread(target=commit, args=(second, "race-b")),
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()
    assert sorted(results) == ["committed", "concurrency_conflict"]

    line = store.read_text(encoding="utf-8").splitlines()[0]
    store.write_text(
        line.replace(
            '"state":"committed"',
            '"state":"committed","state":"unknown"',
            1,
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(module.EpistemicActionIntegrityError) as duplicate:
        module.EpistemicActionChain.load(store)
    assert duplicate.value.reason_code == "event_shape_invalid"


def test_epistemic_action_chain_rejects_rehashed_semantic_tampering(
    tmp_path: Path,
) -> None:
    cases = [
        (
            "prediction",
            0,
            "hypothesis_digest",
            module.epistemic_digest("tampered-hypothesis"),
            "prediction_commitment_mismatch",
        ),
        (
            "discrepancy",
            3,
            "discrepancy_kind",
            "match",
            "discrepancy_derivation_mismatch",
        ),
        (
            "candidate",
            4,
            "update_kind",
            "inspect_only",
            "candidate_derivation_mismatch",
        ),
    ]
    for name, event_index, field, value, reason_code in cases:
        store = tmp_path / f"rehashed-{name}.jsonl"
        _create_epistemic_candidate_store(store, f"tamper-{name}")
        events = _rehash_epistemic_store(store)
        events[event_index][field] = value
        _rehash_epistemic_store(store, events)

        result = module.validate_epistemic_action_chain(store)

        assert result["ok"] is False
        assert result["diagnostics"] == [reason_code]
        with pytest.raises(module.EpistemicActionIntegrityError) as integrity:
            module.EpistemicActionChain.load(store)
        assert integrity.value.reason_code == reason_code


def test_epistemic_action_chain_rejects_rehashed_duplicate_logical_identity(
    tmp_path: Path,
) -> None:
    store = tmp_path / "rehashed-duplicate.jsonl"
    _create_epistemic_candidate_store(store, "duplicate")
    events = _rehash_epistemic_store(store)
    duplicate = copy.deepcopy(events[0])
    duplicate["prediction_id"] = "prediction-duplicate-other"
    duplicate["prediction_commitment_digest"] = (
        _epistemic_prediction_commitment_digest(duplicate)
    )
    duplicate["event_id"] = _epistemic_event_id(
        "prediction_commitment",
        {"prediction_id": duplicate["prediction_id"]},
    )
    events.append(duplicate)
    _rehash_epistemic_store(store, events)

    result = module.validate_epistemic_action_chain(store)

    assert result["ok"] is False
    assert result["diagnostics"] == ["duplicate_logical_identity"]


def test_epistemic_action_chain_malformed_enum_values_return_diagnostics(
    tmp_path: Path,
) -> None:
    cases = [
        ("event_type", 0, []),
        ("state", 0, {}),
        ("observation_status", 2, []),
        ("reason_code", 2, {}),
        ("discrepancy_kind", 3, []),
        ("candidate_status", 4, {}),
        ("update_kind", 4, []),
    ]
    for name, event_index, value in cases:
        store = tmp_path / f"malformed-{name}.jsonl"
        _create_epistemic_candidate_store(store, f"malformed-{name}")
        events = _rehash_epistemic_store(store)
        events[event_index][name] = value
        _rehash_epistemic_store(store, events)

        result = module.validate_epistemic_action_chain(store)

        assert result["ok"] is False
        assert isinstance(result["diagnostics"], list)
        assert result["diagnostics"]
        assert all(isinstance(item, str) for item in result["diagnostics"])

    cli_store = tmp_path / "malformed-cli.jsonl"
    _create_epistemic_candidate_store(cli_store, "malformed-cli")
    cli_events = _rehash_epistemic_store(cli_store)
    cli_events[0]["event_type"] = []
    _rehash_epistemic_store(cli_store, cli_events)
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT.with_name("aoa_epistemic_action_event_chain.py")),
            "--store",
            str(cli_store),
            "validate",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 1
    payload = json.loads(completed.stdout)
    assert payload["ok"] is False
    assert payload["diagnostics"] == ["event_type_invalid"]


def test_epistemic_action_chain_rejects_rehashed_refusal_state_tampering(
    tmp_path: Path,
) -> None:
    store = tmp_path / "rehashed-refusal-state.jsonl"
    chain = module.EpistemicActionChain.create(
        store,
        session_id="session-refusal-state",
        turn_id="turn-refusal-state",
    )
    with pytest.raises(module.EpistemicActionOrderingError):
        chain.bind_action(
            "action-refusal-state",
            module.epistemic_digest("action-refusal-state"),
            **_epistemic_action_kwargs("refusal-state"),
        )
    events = _rehash_epistemic_store(store)
    assert events[0]["event_type"] == "refusal"
    events[0]["state"] = "ready"
    _rehash_epistemic_store(store, events)

    result = module.validate_epistemic_action_chain(store)

    assert result["ok"] is False
    assert result["diagnostics"] == ["event_shape_invalid"]


def test_epistemic_action_chain_serializes_same_instance_concurrency(
    tmp_path: Path,
) -> None:
    store = tmp_path / "epistemic-same-instance-race.jsonl"
    chain = module.EpistemicActionChain.create(
        store,
        session_id="session-same-instance-race",
        turn_id="turn-same-instance-race",
    )
    barrier = threading.Barrier(2)
    results: list[str] = []

    def commit(label: str) -> None:
        barrier.wait()
        try:
            chain.commit_prediction(
                f"action-same-instance-{label}",
                module.epistemic_digest(f"expected-same-instance-{label}"),
                **_epistemic_prediction_kwargs(f"same-instance-{label}"),
            )
            results.append("committed")
        except module.EpistemicActionError as exc:
            results.append(exc.reason_code)

    workers = [
        threading.Thread(target=commit, args=("a",)),
        threading.Thread(target=commit, args=("b",)),
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()

    assert sorted(results) == ["committed", "committed"]
    artifact = chain.inspect()
    assert artifact["event_count"] == 2
    assert [event["sequence"] for event in artifact["events"]] == [1, 2]
    assert module.validate_epistemic_action_chain(store)["ok"] is True


def test_epistemic_action_chain_rejects_cross_instance_same_action_prediction_race(
    tmp_path: Path,
) -> None:
    store = tmp_path / "epistemic-cross-instance-prediction-race.jsonl"
    first = module.EpistemicActionChain.create(
        store,
        session_id="session-cross-instance-prediction",
        turn_id="turn-cross-instance-prediction",
    )
    second = module.EpistemicActionChain.load(
        store,
        session_id="session-cross-instance-prediction",
        turn_id="turn-cross-instance-prediction",
    )
    barrier = threading.Barrier(2)
    results: list[tuple[str, str | None, str | None]] = []

    def commit(chain: object, label: str) -> None:
        barrier.wait()
        try:
            chain.commit_prediction(
                "action-cross-instance-prediction",
                module.epistemic_digest(f"expected-{label}"),
                **_epistemic_prediction_kwargs(label),
                prediction_id=f"prediction-{label}",
            )
            results.append(("committed", None, None))
        except module.EpistemicActionError as exc:
            results.append(("rejected", exc.reason_code, exc.state))

    workers = [
        threading.Thread(target=commit, args=(first, "prediction-a")),
        threading.Thread(target=commit, args=(second, "prediction-b")),
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()

    assert sorted(result[0] for result in results) == ["committed", "rejected"]
    rejected = next(result for result in results if result[0] == "rejected")
    assert rejected[1] == "duplicate_logical_identity"
    assert rejected[2] == "ambiguous"
    loaded = module.EpistemicActionChain.load(
        store,
        session_id="session-cross-instance-prediction",
        turn_id="turn-cross-instance-prediction",
    )
    assert loaded.inspect()["event_count"] == 1
    assert loaded.inspect()["chain_status"] == "ready"
    assert [event["event_type"] for event in loaded.inspect()["events"]] == [
        "prediction_commitment"
    ]
    assert module.validate_epistemic_action_chain(store)["ok"] is True


def test_epistemic_action_chain_rejects_cross_instance_same_action_observation_race(
    tmp_path: Path,
) -> None:
    store = tmp_path / "epistemic-cross-instance-observation-race.jsonl"
    seed = module.EpistemicActionChain.create(
        store,
        session_id="session-cross-instance-observation",
        turn_id="turn-cross-instance-observation",
    )
    seed.commit_prediction(
        "action-cross-instance-observation",
        module.epistemic_digest("expected-observation"),
        **_epistemic_prediction_kwargs("observation-race"),
        prediction_id="prediction-observation-race",
    )
    seed.bind_action(
        "action-cross-instance-observation",
        module.epistemic_digest("action-observation"),
        **_epistemic_action_kwargs("observation-race"),
    )
    first = module.EpistemicActionChain.load(
        store,
        session_id="session-cross-instance-observation",
        turn_id="turn-cross-instance-observation",
    )
    second = module.EpistemicActionChain.load(
        store,
        session_id="session-cross-instance-observation",
        turn_id="turn-cross-instance-observation",
    )
    barrier = threading.Barrier(2)
    results: list[tuple[str, str | None, str | None]] = []

    def observe(chain: object, observation_id: str, digest: str) -> None:
        barrier.wait()
        try:
            chain.record_observation(
                "action-cross-instance-observation",
                module.epistemic_digest(digest),
                **_epistemic_observation_kwargs("observation-race"),
                observation_id=observation_id,
            )
            results.append(("committed", None, None))
        except module.EpistemicActionError as exc:
            results.append(("rejected", exc.reason_code, exc.state))

    workers = [
        threading.Thread(target=observe, args=(first, "observation-a", "actual-a")),
        threading.Thread(target=observe, args=(second, "observation-b", "actual-b")),
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()

    assert sorted(result[0] for result in results) == ["committed", "rejected"]
    rejected = next(result for result in results if result[0] == "rejected")
    assert rejected[1] == "duplicate_logical_identity"
    assert rejected[2] == "ambiguous"
    loaded = module.EpistemicActionChain.load(
        store,
        session_id="session-cross-instance-observation",
        turn_id="turn-cross-instance-observation",
    )
    assert loaded.inspect()["event_count"] == 3
    assert loaded.inspect()["chain_status"] == "ready"
    assert [event["event_type"] for event in loaded.inspect()["events"]] == [
        "prediction_commitment",
        "action_binding",
        "observation",
    ]
    assert module.validate_epistemic_action_chain(store)["ok"] is True


def test_epistemic_action_chain_rejects_store_symlink_alias(
    tmp_path: Path,
) -> None:
    target = tmp_path / "real-store.jsonl"
    alias = tmp_path / "alias-store.jsonl"
    alias.symlink_to(target)

    with pytest.raises(module.EpistemicActionIntegrityError) as error:
        module.EpistemicActionChain.create(
            alias,
            session_id="session-symlink",
            turn_id="turn-symlink",
        )
    assert error.value.reason_code == "store_not_regular"
