#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "docs" / "validation" / "validation_lanes.json"
REQUIRED_RUNNER_CONTEXTS = {
    "owner_local_cli",
    "host_resource_scheduler",
    "release_pipeline",
}


@dataclass(frozen=True)
class CommandStep:
    label: str
    command: tuple[str, ...]


class ManifestError(ValueError):
    pass


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ManifestError(f"missing validation lane manifest: {path}") from exc
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ManifestError(f"invalid validation lane manifest: {exc}") from exc
    if not isinstance(payload, dict):
        raise ManifestError("validation lane manifest must contain a JSON object")
    validate_manifest(payload)
    return payload


def _nonempty_strings(value: Any, location: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ManifestError(f"{location} must be a non-empty list")
    if any(not isinstance(item, str) or not item for item in value):
        raise ManifestError(f"{location} must contain non-empty strings")
    return value


def validate_manifest(payload: dict[str, Any]) -> None:
    if payload.get("schema_version") != 1:
        raise ManifestError("validation lane manifest schema_version must be 1")
    contexts = payload.get("runner_contexts")
    sequences = payload.get("command_sequences")
    lanes = payload.get("lanes")
    if not isinstance(contexts, dict) or not contexts:
        raise ManifestError("validation lane manifest must define runner_contexts")
    missing_contexts = sorted(REQUIRED_RUNNER_CONTEXTS - set(contexts))
    if missing_contexts:
        raise ManifestError(
            "validation lane manifest missing runner_contexts: "
            + ", ".join(missing_contexts)
        )
    for context_id, context in contexts.items():
        if not isinstance(context, dict):
            raise ManifestError(f"runner_context {context_id!r} must be an object")
        for key in ("role", "runner_type"):
            if not isinstance(context.get(key), str) or not context[key]:
                raise ManifestError(f"runner_context {context_id!r} must define {key}")
        if not isinstance(context.get("requires_private_host_state"), bool):
            raise ManifestError(
                f"runner_context {context_id!r} must define boolean requires_private_host_state"
            )
    if not isinstance(sequences, dict) or not sequences:
        raise ManifestError("validation lane manifest must define command_sequences")
    for sequence_id, steps in sequences.items():
        if not isinstance(steps, list) or not steps:
            raise ManifestError(f"command_sequence {sequence_id!r} must be non-empty")
        labels: list[str] = []
        for index, step in enumerate(steps):
            if not isinstance(step, dict) or set(step) != {"label", "command"}:
                raise ManifestError(
                    f"command_sequence {sequence_id!r}[{index}] must contain label and command"
                )
            label = step["label"]
            if not isinstance(label, str) or not label:
                raise ManifestError(
                    f"command_sequence {sequence_id!r}[{index}] must have a label"
                )
            labels.append(label)
            _nonempty_strings(
                step["command"], f"command_sequence {sequence_id!r}[{index}].command"
            )
        if len(set(labels)) != len(labels):
            raise ManifestError(f"command_sequence {sequence_id!r} labels must be unique")
    if not isinstance(lanes, dict) or not lanes:
        raise ManifestError("validation lane manifest must define lanes")
    for lane_id, lane in lanes.items():
        if not isinstance(lane, dict):
            raise ManifestError(f"lane {lane_id!r} must be an object")
        sequence_id = lane.get("command_sequence")
        if sequence_id not in sequences:
            raise ManifestError(
                f"lane {lane_id!r} references missing command_sequence {sequence_id!r}"
            )
        for key in ("owner_surface", "failure_route"):
            if not isinstance(lane.get(key), str) or not lane[key]:
                raise ManifestError(f"lane {lane_id!r} must define {key}")
        lane_contexts = _nonempty_strings(
            lane.get("runner_contexts"), f"lane {lane_id!r}.runner_contexts"
        )
        unknown = sorted(set(lane_contexts) - set(contexts))
        if unknown:
            raise ManifestError(
                f"lane {lane_id!r} references unknown runner_contexts: {', '.join(unknown)}"
            )
        if not isinstance(lane.get("public_safe"), bool):
            raise ManifestError(f"lane {lane_id!r} must define boolean public_safe")
        if lane["public_safe"]:
            private = sorted(
                item
                for item in lane_contexts
                if contexts[item]["requires_private_host_state"]
            )
            if private:
                raise ManifestError(
                    f"lane {lane_id!r} is public_safe but uses private contexts: "
                    + ", ".join(private)
                )


def command_sequence(
    sequence_id: str, path: Path = MANIFEST_PATH
) -> tuple[CommandStep, ...]:
    manifest = load_manifest(path)
    sequences = manifest["command_sequences"]
    if sequence_id not in sequences:
        available = ", ".join(sorted(sequences))
        raise ManifestError(
            f"unknown command sequence {sequence_id!r}; available: {available}"
        )
    return tuple(
        CommandStep(
            label=step["label"],
            command=tuple(
                sys.executable if token == "python" else token
                for token in step["command"]
            ),
        )
        for step in sequences[sequence_id]
    )


def lane_command_sequence(
    lane_id: str, path: Path = MANIFEST_PATH
) -> tuple[CommandStep, ...]:
    manifest = load_manifest(path)
    lane = manifest["lanes"].get(lane_id)
    if lane is None:
        available = ", ".join(sorted(manifest["lanes"]))
        raise ManifestError(f"unknown validation lane {lane_id!r}; available: {available}")
    return command_sequence(lane["command_sequence"], path)


def main() -> int:
    try:
        manifest = load_manifest()
    except ManifestError as exc:
        print(f"[fail] validation lane manifest failed: {exc}")
        return 1
    print("[ok] validation lane manifest passed")
    for lane_id in sorted(manifest["lanes"]):
        lane = manifest["lanes"][lane_id]
        print(
            f"- {lane_id}: {lane['command_sequence']} "
            f"[{', '.join(lane['runner_contexts'])}] -> {lane['failure_route']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
