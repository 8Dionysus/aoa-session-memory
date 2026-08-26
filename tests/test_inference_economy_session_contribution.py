from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

from jsonschema import Draft202012Validator


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "aoa_session_memory.py"
SCHEMA = REPO_ROOT / "schemas" / "inference-economy-session-contribution.schema.json"
spec = importlib.util.spec_from_file_location("aoa_session_memory", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules["aoa_session_memory"] = module
spec.loader.exec_module(module)


def raw_event(
    line_no: int,
    payload: dict[str, object],
    *,
    event_type: str = "response_item",
    compaction_boundary: bool = False,
) -> object:
    return module.RawEvent(
        event_id=f"event-{line_no}",
        line_no=line_no,
        raw=json.dumps({"payload": payload}),
        parsed={"payload": payload},
        event_type=event_type,
        source_type="response_item",
        title="fixture event",
        timestamp=f"2026-08-26T00:00:{line_no:02d}Z",
        tags=[],
        importance="normal",
        compaction_boundary=compaction_boundary,
    )


def validate(payload: dict[str, object]) -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    errors = sorted(Draft202012Validator(schema).iter_errors(payload), key=str)
    assert not errors, [error.message for error in errors]


def test_provider_reported_contribution_is_schema_valid_and_default_off() -> None:
    events = [
        raw_event(
            1,
            {
                "type": "token_count",
                "input_tokens": 10,
                "cached_tokens": 2,
                "output_tokens": 5,
                "total_tokens": 15,
            },
        ),
        raw_event(2, {"type": "message", "role": "assistant"}, compaction_boundary=True),
    ]

    contribution = module.inference_economy_session_contribution(
        events,
        observation_id="fixture:provider-reported",
        source_ref={"kind": "session-manifest", "ref": "source:fixture"},
        source_revision="fixture-revision",
    )

    validate(contribution)
    assert contribution["observation_status"] == "complete"
    assert contribution["tokens"]["input"]["value"] == 10
    assert contribution["tokens"]["cached_input"]["value"] == 2
    assert contribution["tokens"]["output"]["value"] == 5
    assert contribution["compactions"]["value"] == 1
    assert contribution["unknown_fields"] == []
    assert contribution["default_off"] is True
    assert contribution["activation_allowed"] is False


def test_missing_basis_remains_explicit_and_does_not_claim_lifecycle() -> None:
    contribution = module.inference_economy_session_contribution(
        [raw_event(3, {"type": "message", "role": "user"})],
        observation_id="fixture:missing-provider",
        source_ref={"kind": "session-manifest", "ref": "source:fixture"},
        source_revision="fixture-revision",
    )

    validate(contribution)
    assert contribution["observation_status"] == "partial"
    assert contribution["unknown_fields"] == [
        "tokens.cached_input",
        "tokens.input",
        "tokens.output",
    ]
    assert all(
        metric["status"] == "unknown"
        for metric in contribution["tokens"].values()
    )
    assert contribution["compactions"]["status"] == "observed"
    assert "runtime_outcome" not in contribution
    assert "eval_verdict" not in contribution
    assert "owner_acceptance" not in contribution


def test_nonportable_source_ref_is_rejected() -> None:
    try:
        module.inference_economy_session_contribution(
            [],
            observation_id="fixture:unsafe",
            source_ref={"kind": "source", "ref": "/srv/private/session"},
            source_revision="fixture-revision",
        )
    except ValueError as exc:
        assert str(exc) == "inference_economy_evidence_ref_must_be_portable"
    else:
        raise AssertionError("nonportable source ref was accepted")
