#!/usr/bin/env python3
"""Build a conservative, public-safe profile of archived session stages.

The profiler reads generated session and segment indexes.  A measured stage
span is admitted only for a structured call with a correlated result and a
valid pair of timestamps.  Everything else remains unknown or unattributed;
the profiler never turns a missing stage into a zero.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Iterable, Mapping

try:
    import identity_bound_session_telemetry as identity_telemetry
except ModuleNotFoundError:
    scripts_dir = str(Path(__file__).resolve().parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    import identity_bound_session_telemetry as identity_telemetry


SCHEMA_VERSION = "stage_profile_v1"
PROFILER_VERSION = "structured_segment_index_correlated_call_result_identity_episode_v1"
BOUNDED_MEASUREMENT_SCHEMA_VERSION = "bounded_measurement_v1"
BOUNDED_PREFIX_ROUTE = "last_good_stable_projection_exact_prefix_v1"
IDENTITY_EPISODE_COHORT_SCHEMA_VERSION = "identity_bound_episode_cohort_v1"

STAGES = (
    "kag_navigation_index_gate",
    "tests_validators",
    "diagnosis_repair",
    "ci_landing_waits",
    "rerun_after_fix",
    "agent_model_or_coordination",
    "coordination_idle_wait",
    "unknown",
)

RERUN_ELIGIBLE_STAGES = {
    "kag_navigation_index_gate",
    "tests_validators",
    "diagnosis_repair",
    "ci_landing_waits",
    "agent_model_or_coordination",
}

MAX_EPISODE_EVIDENCE_REFS = 12
MAX_AGGREGATE_EVIDENCE_REFS = 48
MAX_ATTEMPT_SAMPLES = 16

STAGE_CONTRACT: dict[str, Any] = {
    "attempt": (
        "A structured call event with a correlation id. A result is required "
        "for an observed call-to-result span; an unresolved call is retained "
        "as an attempt with unknown duration."
    ),
    "span": (
        "Wall-clock time from a structured call event to its first correlated "
        "result event in the same closed task episode. This is not model CPU "
        "time, active operator time, or causal proof."
    ),
    "rerun": (
        "A repeated normalized operation digest within one task episode. "
        "rerun_after_fix additionally requires a prior failed result and a "
        "later repeat of a substantive operation; validation_rerun_after_repair "
        "requires a prior validator attempt, a diagnosis_repair attempt, and a "
        "later validator attempt."
    ),
    "unknown_law": (
        "No structured stage evidence is emitted as zero. Missing, stale, "
        "unresolved, uncorrelated, or semantically ambiguous evidence is null "
        "with a status and reason; residual episode wall time is an explicit "
        "unknown span."
    ),
    "evaluator_boundary": (
        "The output is a normalized evidence product and method description. "
        "It does not compare methods, assign a universal policy, or issue an "
        "evaluation verdict."
    ),
}


class ProfileError(RuntimeError):
    """Raised when a selected session cannot be read safely."""


class BoundedPrefixError(ProfileError):
    """Raised when an exact prefix cannot be admitted fail-closed."""


def validate_max_episodes(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ProfileError("max_episodes_must_be_positive")
    return value


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProfileError(f"unreadable_json:{path.name}") from exc
    if not isinstance(value, dict):
        raise ProfileError(f"json_object_required:{path.name}")
    return value


def _owner_memory_module() -> Any:
    try:
        import aoa_session_memory as owner_memory
    except ModuleNotFoundError:
        scripts_dir = str(Path(__file__).resolve().parent)
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        import aoa_session_memory as owner_memory
    return owner_memory


def _owner_current_context(
    manifest: Mapping[str, Any],
    index: Mapping[str, Any],
    source: Mapping[str, Any],
) -> dict[str, Any]:
    """Recompute the current owner generation and publish context."""

    owner_memory = _owner_memory_module()
    session_manifest_raw = manifest.get("raw") if isinstance(manifest.get("raw"), Mapping) else {}
    for name, manifest_name in (
        ("raw_sha256", "sha256"),
        ("raw_bytes", "bytes"),
        ("raw_line_count", "line_count"),
    ):
        if session_manifest_raw.get(manifest_name) != source.get(name):
            raise ProfileError(f"owner_session_source_mismatch:{name}")

    stored_projection = index.get("projection_publish")
    if not isinstance(stored_projection, Mapping):
        raise ProfileError("owner_projection_context_missing")
    stored_source = stored_projection.get("source")
    watermark = stored_projection.get("processed_watermark")
    if not isinstance(stored_source, Mapping) or not isinstance(watermark, Mapping):
        raise ProfileError("owner_projection_context_incomplete")
    if any(stored_source.get(name) != source.get(name) for name in ("raw_sha256", "raw_bytes", "raw_line_count")):
        raise ProfileError("owner_projection_source_mismatch")
    processed_to_line = int_value(watermark.get("to_line"))
    processed_to_timestamp = str(watermark.get("to_timestamp") or "")
    if processed_to_line is None or processed_to_line < 1 or not processed_to_timestamp:
        raise ProfileError("owner_projection_watermark_incomplete")
    expected_projection = owner_memory.session_projection_publish_identity_from_scan(
        {
            "raw_sha256": source.get("raw_sha256"),
            "raw_bytes": source.get("raw_bytes"),
            "raw_line_count": source.get("raw_line_count"),
            "processed_to_line": processed_to_line,
            "processed_to_timestamp": processed_to_timestamp,
        }
    )
    if dict(stored_projection) != expected_projection:
        raise ProfileError("owner_projection_context_stale")

    expected_task = owner_memory.task_episode_source_generation_identity()
    expected_segment = owner_memory.segment_index_generation_identity()
    expected_session = owner_memory.session_index_generation_identity()
    stored_session = index.get("generation_identity")
    if not isinstance(stored_session, Mapping) or dict(stored_session) != expected_session:
        raise ProfileError("owner_session_generation_stale")
    dependencies = index.get("dependency_generation_identities")
    if not isinstance(dependencies, Mapping):
        raise ProfileError("owner_dependency_generation_context_missing")
    if dependencies.get("segment_index") != expected_segment:
        raise ProfileError("owner_segment_generation_stale")
    if dependencies.get("task_episode_source") != expected_task:
        raise ProfileError("owner_task_episode_generation_stale")
    index_schema = manifest.get("index_schema")
    if not isinstance(index_schema, Mapping) or index_schema.get("projection_publish") != expected_projection:
        raise ProfileError("owner_manifest_projection_context_stale")
    return {
        "projection": dict(expected_projection),
        "task_episode_generation": str(expected_task.get("generation_id") or ""),
        "segment_generation": str(expected_segment.get("generation_id") or ""),
        "session_generation": str(expected_session.get("generation_id") or ""),
    }


def _verify_published_source_identity(
    session_dir: Path,
    manifest: Mapping[str, Any],
    source: Mapping[str, Any],
) -> None:
    """Validate an optional published raw-source anchor without reading it."""

    raw = manifest.get("raw") if isinstance(manifest.get("raw"), Mapping) else None
    if raw is None:
        raise ProfileError("source_raw_identity_receipt_missing")
    declared_path = raw.get("path")
    if declared_path is not None:
        if not isinstance(declared_path, str) or not declared_path.strip():
            raise ProfileError("source_raw_snapshot_path_missing")
        raw_path = Path(declared_path)
        if any(part == ".." for part in raw_path.parts):
            raise ProfileError("source_raw_snapshot_path_invalid")
        try:
            session_root = session_dir.resolve(strict=True)
        except OSError as exc:
            raise ProfileError("source_session_root_unreadable") from exc
        if raw_path.is_absolute():
            try:
                relative_path = raw_path.relative_to(session_root)
            except ValueError as exc:
                raise ProfileError("source_raw_snapshot_path_outside_session") from exc
            anchored_path = raw_path
        else:
            relative_path = raw_path
            anchored_path = session_root / relative_path
        if not relative_path.parts or any(part in {"", "."} for part in relative_path.parts):
            raise ProfileError("source_raw_snapshot_path_invalid")
        current = session_root
        try:
            for part in relative_path.parts:
                current = current / part
                if current.is_symlink():
                    raise ProfileError("source_raw_snapshot_symlink")
            if not anchored_path.is_file():
                raise ProfileError("source_raw_snapshot_missing")
            resolved_path = anchored_path.resolve(strict=True)
            resolved_path.relative_to(session_root)
            if not resolved_path.is_file():
                raise ProfileError("source_raw_snapshot_missing")
        except ProfileError:
            raise
        except (OSError, RuntimeError, ValueError) as exc:
            raise ProfileError("source_raw_snapshot_unreadable") from exc

    for key, manifest_key in (
        ("raw_sha256", "sha256"),
        ("raw_bytes", "bytes"),
        ("raw_line_count", "line_count"),
    ):
        if raw.get(manifest_key) != source.get(key):
            raise ProfileError(f"source_raw_snapshot_identity_mismatch:{key}")


def int_value(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_timestamp(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def seconds_between(start: Any, end: Any) -> float | None:
    left = parse_timestamp(start)
    right = parse_timestamp(end)
    if left is None or right is None or right < left:
        return None
    return round((right - left).total_seconds(), 6)


def union_seconds(intervals: Iterable[tuple[datetime, datetime]]) -> float:
    ordered = sorted((start, end) for start, end in intervals if end >= start)
    if not ordered:
        return 0.0
    total = 0.0
    current_start, current_end = ordered[0]
    for start, end in ordered[1:]:
        if start <= current_end:
            current_end = max(current_end, end)
            continue
        total += (current_end - current_start).total_seconds()
        current_start, current_end = start, end
    total += (current_end - current_start).total_seconds()
    return round(total, 6)


def iso_or_none(value: Any) -> str | None:
    parsed = parse_timestamp(value)
    return parsed.isoformat().replace("+00:00", "Z") if parsed else None


def safe_text(value: Any, limit: int = 96) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text[:limit]


def safe_tool_name(event: dict[str, Any]) -> str:
    facets = event.get("facets") if isinstance(event.get("facets"), dict) else {}
    value = (
        facets.get("tool_qualified_name")
        or facets.get("tool_name")
        or facets.get("command_kind")
        or ""
    )
    text = safe_text(value)
    if re.fullmatch(r"[a-z0-9_.:-]{1,96}", text):
        return text
    return "unknown_tool"


def event_command(event: dict[str, Any]) -> str:
    facets = event.get("facets") if isinstance(event.get("facets"), dict) else {}
    return safe_text(facets.get("command"), limit=4000)


def event_tool_identity(event: dict[str, Any]) -> str:
    facets = event.get("facets") if isinstance(event.get("facets"), dict) else {}
    return " ".join(
        safe_text(facets.get(key), limit=240)
        for key in ("tool_qualified_name", "tool_name", "tool_namespace")
        if facets.get(key)
    )


def stage_for_call(event: dict[str, Any]) -> tuple[str, str]:
    """Return (stage, evidence basis) without treating text mentions as calls."""

    command = event_command(event)
    identity = event_tool_identity(event)
    haystack = f"{identity} {command}".strip()
    event_type = safe_text(event.get("type"))

    if (
        safe_tool_name(event) == "write_stdin"
        or re.search(r"\b(?:wait|sleep|poll|watch)\b", haystack)
    ):
        return "coordination_idle_wait", "structured_wait_or_poll_call"

    if re.search(
        r"(?:aoa[_-]kag|mcp__aoa_kag|\bkag(?:_|\b)|server[/_-]discover)",
        haystack,
    ):
        return "kag_navigation_index_gate", "structured_kag_tool_or_command"

    if re.search(
        r"(?:\bgh\b|github\.com|pull request|\bgit\s+(?:commit|push|merge|rebase|cherry-pick)\b|\blanding\b)",
        haystack,
    ):
        return "ci_landing_waits", "structured_landing_or_ci_call"

    if re.search(
        r"(?:apply_patch|git\s+apply|sed\s+-[^-]*i\b|perl\s+-[a-z]*i\b|\btee\b|\b(?:reindex|repair)\b|\b(?:mkdir|mv|cp|touch)\b)",
        haystack,
    ) or event_type in {"FILE_WRITE", "DIFF"}:
        return "diagnosis_repair", "structured_mutation_or_repair_call"

    if re.search(
        r"(?:\bpytest\b|\bunittest\b|py_compile|\bmypy\b|\bruff\b|\beslint\b|\btsc\b|\bvitest\b|\bcargo\s+test\b|\bgo\s+test\b|\bci_gate\b|\brelease_check\b|\bvalidate(?:[_ .-]|$)|\bdoctor\b|git\s+diff\s+--check)",
        haystack,
    ):
        return "tests_validators", "structured_test_or_validator_call"

    if re.search(
        r"(?:\bspawn_agent\b|\bsend_input\b|\bresume\b|\bcontinue_session\b|\bdelegate\b|\bcoordination\b)",
        haystack,
    ):
        return "agent_model_or_coordination", "structured_coordination_call"

    return "unknown", "structured_call_unmapped"


def normalized_operation(event: dict[str, Any], stage: str) -> tuple[str, str]:
    """Return a public-safe operation shape and digest; never return raw command text."""

    command = event_command(event)
    identity = event_tool_identity(event)
    normalized = f"{stage}|{identity}|{command}"
    normalized = re.sub(r"[0-9a-f]{8,}", "<hex>", normalized)
    normalized = re.sub(r"\b\d+\b", "<number>", normalized)
    normalized = re.sub(r"/(?:[^\s/]+/)+[^\s]+", "<path>", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    shape = f"{stage}:{safe_tool_name(event)}:{digest[:16]}"
    return shape, f"sha256:{digest}"


def is_call_event(event: dict[str, Any]) -> bool:
    if not isinstance(event, dict):
        return False
    if not event.get("correlation_id"):
        return False
    return str(event.get("type") or "") in {
        "COMMAND",
        "FILE_READ",
        "FILE_WRITE",
        "DIFF",
        "TOOL_CALL",
        "MCP_CALL",
    }


def is_result_event(event: dict[str, Any]) -> bool:
    if not isinstance(event, dict):
        return False
    if not event.get("correlation_id"):
        return False
    return str(event.get("type") or "") in {
        "COMMAND_OUTPUT",
        "TOOL_OUTPUT",
        "VERIFICATION",
        "ERROR",
        "TOOL_RESULT",
        "MCP_RESULT",
    }


def result_status(events: Iterable[dict[str, Any]]) -> str | None:
    values = [safe_text(event.get("outcome")) for event in events]
    if any(value in {"failed", "error", "timed_out", "timeout"} for value in values):
        return "failed"
    if any(value in {"succeeded", "passed", "observed", "completed", "compacted"} for value in values):
        return "succeeded"
    return next((value for value in values if value), None)


def _profile_session_ref(
    session_label: str,
    owner_root_witness: identity_telemetry.OwnerRootWitness | None,
) -> str:
    if owner_root_witness is None:
        # Direct in-memory episode profiling has no owner root to bind. This
        # fallback is content-free; persisted/report paths always provide the
        # owner-issued witness at their call boundary.
        return "session:sha256:" + hashlib.sha256(
            str(session_label).encode("utf-8")
        ).hexdigest()[:16]
    return identity_telemetry.public_session_ref(
        session_label,
        owner_root_witness=owner_root_witness,
    )


def logical_ref(
    session_label: str,
    event: dict[str, Any],
    *,
    owner_root_witness: identity_telemetry.OwnerRootWitness | None = None,
) -> dict[str, str]:
    line = int_value(event.get("line"))
    segment_id = "unknown"
    anchor = str(event.get("md_anchor") or "")
    if anchor:
        segment_id = anchor.split("__", 1)[0]
    raw = f"raw:line:{line}" if line is not None else "raw:line:unknown"
    session_ref = _profile_session_ref(session_label, owner_root_witness)
    return {
        "session": session_ref,
        "raw": raw,
        "segment": f"{session_ref}#segment:{identity_telemetry.public_ref_component(segment_id, 'segment_id')}",
        "event": identity_telemetry.public_ref_component(
            str(event.get("event_id") or "unknown"), "event_id"
        ),
    }


def select_session_dir(aoa_root: Path, selector: str) -> Path:
    candidate = Path(selector).expanduser()
    if candidate.is_dir():
        return candidate
    direct = aoa_root / "sessions" / selector
    if direct.is_dir():
        return direct
    sessions_root = aoa_root / "sessions"
    if not sessions_root.is_dir():
        raise ProfileError("sessions_root_missing")
    matches: list[Path] = []
    for path in sorted(sessions_root.iterdir()):
        if not path.is_dir():
            continue
        if selector == path.name or selector in path.name:
            matches.append(path)
            continue
        manifest_path = path / "session.manifest.json"
        if not manifest_path.is_file():
            continue
        try:
            manifest = read_json(manifest_path)
        except ProfileError:
            continue
        values = {
            str(manifest.get("session_id") or ""),
            str(manifest.get("session_label") or ""),
            str(manifest.get("session_title") or ""),
        }
        if selector in values:
            matches.append(path)
    if len(matches) != 1:
        status = "missing" if not matches else "ambiguous"
        raise ProfileError(f"session_{status}:{selector}")
    return matches[0]


def load_segment_events(
    session_dir: Path,
    index: dict[str, Any],
    *,
    owner_root_witness: identity_telemetry.OwnerRootWitness,
    expected_projection: dict[str, Any] | None = None,
    expected_segment_generation: str | None = None,
    expected_line_count: int | None = None,
) -> dict[int, dict[str, Any]]:
    events_by_line: dict[int, dict[str, Any]] = {}
    strict = expected_projection is not None
    observed_event_count = 0
    segments = index.get("segments") if isinstance(index.get("segments"), list) else []
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        index_value = str(segment.get("index") or "")
        index_path = Path(index_value)
        if not index_path.is_file():
            index_path = session_dir / "segments" / Path(index_value).name
        if not index_path.is_file():
            if strict:
                raise BoundedPrefixError("bounded_prefix_segment_index_missing")
            continue
        try:
            owner_membership = identity_telemetry._owner_segment_membership(
                session_dir=session_dir,
                index_path=index_path,
                owner_root_witness=owner_root_witness,
            )
        except identity_telemetry.TelemetryError as exc:
            if strict:
                raise BoundedPrefixError(
                    f"bounded_prefix_segment_owner_membership:{exc}"
                ) from exc
            owner_membership = None
        try:
            segment_index = read_json(index_path)
        except ProfileError:
            if strict:
                raise BoundedPrefixError("bounded_prefix_segment_index_unreadable")
            continue
        if strict:
            if segment_index.get("projection_publish") != expected_projection:
                raise BoundedPrefixError("bounded_prefix_segment_projection_mismatch")
            generation_id = str(segment_index.get("generation_id") or "")
            if generation_id != str(expected_segment_generation or ""):
                raise BoundedPrefixError("bounded_prefix_segment_generation_mismatch")
            generation_identity = segment_index.get("generation_identity")
            if not isinstance(generation_identity, dict):
                raise BoundedPrefixError("bounded_prefix_segment_generation_missing")
            if str(generation_identity.get("generation_id") or "") != generation_id:
                raise BoundedPrefixError("bounded_prefix_segment_generation_identity_mismatch")
            if generation_identity.get("projection") != "segment_index":
                raise BoundedPrefixError("bounded_prefix_segment_projection_unknown")
            if generation_identity.get("producer_contract_status") != "current":
                raise BoundedPrefixError("bounded_prefix_segment_producer_generation_unresolved")
        events = segment_index.get("events") if isinstance(segment_index.get("events"), list) else []
        for event in events:
            if not isinstance(event, dict):
                continue
            line = int_value(event.get("line"))
            if line is None:
                if strict:
                    raise BoundedPrefixError("bounded_prefix_segment_event_line_missing")
                continue
            facets = event.get("facets") if isinstance(event.get("facets"), Mapping) else {}
            if "identity_bound_telemetry_receipt" in facets and owner_membership is not None:
                try:
                    event = identity_telemetry._attach_owner_source_evidence(
                        event,
                        source_ref=f"owner:segment:{index_path.name}",
                        source_path=index_path,
                        owner_membership=owner_membership,
                        owner_root_witness=owner_root_witness,
                    )
                except identity_telemetry.TelemetryError:
                    # The event remains readable, but its owner receipt facet
                    # must fail closed without source-artifact evidence.
                    pass
            if strict:
                if expected_line_count is not None and not 1 <= line <= expected_line_count:
                    raise BoundedPrefixError("bounded_prefix_segment_event_outside_prefix")
                if line in events_by_line:
                    raise BoundedPrefixError("bounded_prefix_segment_event_duplicate")
                observed_event_count += 1
                events_by_line[line] = event
            else:
                events_by_line.setdefault(line, event)
    if strict and expected_line_count is not None:
        if observed_event_count != expected_line_count or len(events_by_line) != expected_line_count:
            raise BoundedPrefixError("bounded_prefix_segment_coverage_incomplete")
        if set(events_by_line) != set(range(1, expected_line_count + 1)):
            raise BoundedPrefixError("bounded_prefix_segment_line_range_incomplete")
    return events_by_line


def _canonical_payload_sha256(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_episode_records(
    session_dir: Path,
    *,
    owner_root_witness: identity_telemetry.OwnerRootWitness,
    session_id: str,
    session_ref: str,
    source_identity: Mapping[str, Any],
    expected_projection: Mapping[str, Any],
    expected_task_episode_generation: str,
    expected_generation_context: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Load only closed-safe generated episode metadata and its provenance."""

    manifest_path = session_dir / "session-index-shards" / "manifest.json"
    session_manifest_path = session_dir / "session.manifest.json"
    manifest = read_json(manifest_path)
    manifest_sha256 = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    components = manifest.get("components") if isinstance(manifest.get("components"), dict) else {}
    refs = components.get("task_episodes") if isinstance(components.get("task_episodes"), list) else []
    component_counts = manifest.get("component_counts")
    declared_count: int | None = None
    if not isinstance(component_counts, Mapping):
        raise ProfileError("episode_component_count_missing")
    declared_count = int_value(component_counts.get("task_episodes"))
    if declared_count is None or declared_count < 0:
        raise ProfileError("episode_component_count_invalid")
    if declared_count != len(refs):
        raise ProfileError("episode_component_count_mismatch")
    component_order = manifest.get("component_order")
    if not isinstance(component_order, Mapping):
        raise ProfileError("episode_component_order_missing")
    declared_order = component_order.get("task_episodes")
    if (
        not isinstance(declared_order, list)
        or any(not isinstance(item, str) or not item for item in declared_order)
        or len(declared_order) != declared_count
        or len(set(declared_order)) != len(declared_order)
        or [str(entry.get("ref") or "") for entry in refs if isinstance(entry, Mapping)] != declared_order
    ):
        raise ProfileError("episode_component_order_mismatch")
    manifest_source = manifest.get("source_identity")
    if not isinstance(manifest_source, Mapping):
        raise ProfileError("episode_component_source_identity_missing")
    if (
        not re.fullmatch(r"[0-9a-f]{64}", str(source_identity.get("raw_sha256") or ""))
        or int_value(source_identity.get("raw_bytes")) is None
        or int_value(source_identity.get("raw_line_count")) is None
        or int_value(source_identity.get("raw_line_count")) < 1
    ):
        raise ProfileError("episode_component_source_identity_incomplete")
    for name in ("raw_sha256", "raw_bytes", "raw_line_count"):
        if manifest_source.get(name) != source_identity.get(name):
            raise ProfileError(f"episode_component_source_identity_mismatch:{name}")
    task_generation = str(manifest_source.get("task_episode_generation_id") or "")
    if not re.fullmatch(r"[0-9a-f]{64}", task_generation):
        raise ProfileError("episode_component_generation_identity_missing")
    records: list[dict[str, Any]] = []
    seen_component_refs: set[str] = set()
    seen_episode_ids: set[str] = set()
    for entry in refs:
        if not isinstance(entry, dict):
            raise ProfileError("episode_component_manifest_entry_invalid")
        ref = str(entry.get("ref") or "")
        if ref in seen_component_refs:
            raise ProfileError("episode_component_ref_duplicate")
        seen_component_refs.add(ref)
        ref_parts = Path(ref).parts
        if (
            not ref.startswith("session-index-shards/task-episodes/")
            or ".." in ref_parts
            or not ref.endswith(".json")
        ):
            raise ProfileError("episode_component_ref_not_public_safe")
        component_path = session_dir / ref
        if not component_path.is_file():
            raise ProfileError("episode_component_missing")
        component = read_json(component_path)
        artifact_sha256 = hashlib.sha256(component_path.read_bytes()).hexdigest()
        if entry.get("artifact_sha256") != artifact_sha256:
            raise ProfileError("episode_component_artifact_digest_mismatch")
        if component.get("component") != "task_episodes":
            raise ProfileError("episode_component_kind_mismatch")
        payload = component.get("payload") if isinstance(component.get("payload"), dict) else {}
        if not payload:
            raise ProfileError("episode_component_payload_missing")
        payload_sha256 = _canonical_payload_sha256(payload)
        if entry.get("payload_sha256") != payload_sha256:
            raise ProfileError("episode_component_payload_digest_mismatch")
        component_identity = component.get("source_identity")
        if not isinstance(component_identity, Mapping):
            raise ProfileError("episode_component_identity_missing")
        if str(component_identity.get("task_episode_generation_id") or "") != task_generation:
            raise ProfileError("episode_component_generation_mismatch")
        episode_source_sha256 = str(component_identity.get("episode_source_sha256") or "")
        if not re.fullmatch(r"[0-9a-f]{64}", episode_source_sha256):
            raise ProfileError("episode_component_source_digest_missing")
        component_range = event_range(dict(component_identity))
        payload_range = event_range(payload)
        if component_range is None or payload_range is None or component_range != payload_range:
            raise ProfileError("episode_component_range_mismatch")
        if episode_source_sha256 != identity_telemetry.canonical_episode_source_sha256(payload):
            raise ProfileError("episode_component_source_digest_mismatch")
        if component_range[0] < 1 or component_range[1] > int(source_identity["raw_line_count"]):
            raise ProfileError("episode_component_range_out_of_source")
        privacy_version = int_value(component_identity.get("privacy_policy_version"))
        redaction_version = int_value(component_identity.get("redaction_policy_version"))
        if privacy_version is None or redaction_version is None or privacy_version < 0 or redaction_version < 0:
            raise ProfileError("episode_component_privacy_identity_missing")
        episode_id = str(payload.get("episode_id") or "")
        if not episode_id or episode_id == "unknown":
            raise ProfileError("episode_component_episode_id_unresolved")
        if episode_id in seen_episode_ids:
            raise ProfileError("episode_component_episode_id_duplicate")
        seen_episode_ids.add(episode_id)
        encoded_episode_id = identity_telemetry.public_ref_component(episode_id, "episode_id")
        try:
            owner_membership = identity_telemetry._owner_episode_component_membership(
                session_dir=session_dir,
                component_ref=ref,
                component_path=component_path,
                owner_root_witness=owner_root_witness,
            )
        except identity_telemetry.TelemetryError as exc:
            raise ProfileError(
                f"episode_component_owner_membership:{exc}"
            ) from exc
        component_admission = identity_telemetry._issue_episode_component_admission(
            session_id=session_id,
            session_ref=session_ref,
            episode_id=episode_id,
            component_ref=ref,
            manifest_sha256=manifest_sha256,
            source=source_identity,
            component_identity={
                "task_episode_generation_id": task_generation,
                "episode_source_sha256": episode_source_sha256,
                "event_range": {"from_line": component_range[0], "to_line": component_range[1]},
                "privacy_policy_version": privacy_version,
                "redaction_policy_version": redaction_version,
            },
            artifact_sha256=artifact_sha256,
            payload_sha256=payload_sha256,
            manifest_path=manifest_path,
            component_path=component_path,
            session_manifest_path=session_manifest_path,
            expected_projection=expected_projection,
            expected_task_episode_generation=expected_task_episode_generation,
            expected_generation_context=expected_generation_context,
            owner_membership=owner_membership,
        )
        records.append(
            {
                "payload": payload,
                "component_ref": ref,
                "session_id": session_id,
                "artifact_sha256": artifact_sha256,
                "payload_sha256": payload_sha256,
                "source_identity": {
                    "task_episode_generation_id": task_generation,
                    "episode_source_sha256": episode_source_sha256,
                    "event_range": {"from_line": component_range[0], "to_line": component_range[1]},
                    "privacy_policy_version": privacy_version,
                    "redaction_policy_version": redaction_version,
                },
                "encoded_episode_id": encoded_episode_id,
                "component_admission": component_admission,
                "declared_order": list(declared_order),
            }
        )
    expected_count = declared_count if declared_count is not None else len(refs)
    if len(records) != expected_count or len(seen_component_refs) != expected_count or len(seen_episode_ids) != expected_count:
        raise ProfileError("episode_component_closed_cardinality_mismatch")
    return records


def episode_ref(
    session_label: str,
    episode: dict[str, Any],
    event_key: str,
    *,
    owner_root_witness: identity_telemetry.OwnerRootWitness | None = None,
) -> dict[str, str] | None:
    value = episode.get(event_key)
    if not isinstance(value, list) or not value:
        return None
    first = value[0] if isinstance(value[0], dict) else {}
    line = int_value(first.get("line"))
    event_id = str(first.get("event_id") or "")
    session_ref = _profile_session_ref(session_label, owner_root_witness)
    return {
        "session": session_ref,
        "raw": f"raw:line:{line}" if line is not None else "raw:line:unknown",
        "event": identity_telemetry.public_ref_component(event_id or "unknown", "event_id"),
    }


def event_range(episode: dict[str, Any]) -> tuple[int, int] | None:
    value = episode.get("event_range")
    if not isinstance(value, dict):
        return None
    start = int_value(value.get("from_line"))
    end = int_value(value.get("to_line"))
    if start is None or end is None or end < start:
        return None
    return start, end


def closed_episode_status(episode: dict[str, Any]) -> str:
    return safe_text(episode.get("status")) or "unknown"


def make_stage_bucket() -> dict[str, Any]:
    return {
        "status": "unknown",
        "attempt_count": None,
        "resolved_attempt_count": None,
        "span_seconds": None,
        "span_count": None,
        "unresolved_attempt_count": None,
        "evidence_ref_count": None,
        "evidence_refs": [],
        "evidence_refs_truncated": False,
    }


def compact_attempt(attempt: dict[str, Any]) -> dict[str, Any]:
    return {
        "stage": attempt["stage"],
        "basis": attempt["basis"],
        "operation_shape": attempt["operation_shape"],
        "operation_digest": attempt["operation_digest"],
        "tool": attempt["tool"],
        "result_status": attempt["result_status"],
        "span_seconds": attempt["span_seconds"],
        "repeat_index": attempt["repeat_index"],
        "repeat": attempt["repeat"],
        "after_failure": attempt["after_failure"],
        "rerun_after_fix": attempt["rerun_after_fix"],
        "validation_rerun_after_repair": attempt["validation_rerun_after_repair"],
        "call_ref": attempt["call_ref"],
        "result_ref": attempt["result_ref"],
    }


def profile_episode(
    *,
    session_label: str,
    episode: dict[str, Any],
    events_by_line: dict[int, dict[str, Any]],
    owner_root_witness: identity_telemetry.OwnerRootWitness | None = None,
) -> dict[str, Any]:
    line_range = event_range(episode)
    if line_range is None:
        raise ProfileError("episode_event_range_missing")
    start_line, end_line = line_range
    events = [
        event
        for line, event in sorted(events_by_line.items())
        if start_line <= line <= end_line
    ]
    if not events:
        raise ProfileError("episode_segment_events_missing")

    timestamps = [parse_timestamp(event.get("timestamp")) for event in events]
    timestamps = [value for value in timestamps if value is not None]
    start_time = min(timestamps) if timestamps else None
    end_time = max(timestamps) if timestamps else None
    duration = seconds_between(start_time, end_time) if start_time and end_time else None

    results_by_correlation: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        if is_result_event(event):
            results_by_correlation[str(event.get("correlation_id"))].append(event)

    attempts: list[dict[str, Any]] = []
    for event in events:
        if not is_call_event(event):
            continue
        correlation_id = str(event.get("correlation_id"))
        stage, basis = stage_for_call(event)
        shape, digest = normalized_operation(event, stage)
        call_time = parse_timestamp(event.get("timestamp"))
        correlated = [
            result
            for result in results_by_correlation.get(correlation_id, [])
            if parse_timestamp(result.get("timestamp")) is not None
            and call_time is not None
            and parse_timestamp(result.get("timestamp")) >= call_time
        ]
        correlated.sort(key=lambda item: parse_timestamp(item.get("timestamp")) or datetime.max.replace(tzinfo=timezone.utc))
        first_result = correlated[0] if correlated else None
        span = seconds_between(event.get("timestamp"), first_result.get("timestamp")) if first_result else None
        attempts.append(
            {
                "line": int_value(event.get("line")),
                "event_id": str(event.get("event_id") or "unknown"),
                "stage": stage,
                "basis": basis,
                "operation_shape": shape,
                "operation_digest": digest,
                "tool": safe_tool_name(event),
                "result_status": result_status(correlated) if correlated else None,
                "span_seconds": span,
                "call_ref": logical_ref(
                    session_label,
                    event,
                    owner_root_witness=owner_root_witness,
                ),
                "result_ref": (
                    logical_ref(
                        session_label,
                        first_result,
                        owner_root_witness=owner_root_witness,
                    )
                    if first_result
                    else None
                ),
                "result_event_id": str(first_result.get("event_id") or "") if first_result else None,
                "repeat_index": None,
                "repeat": None,
                "after_failure": None,
                "rerun_after_fix": None,
                "validation_rerun_after_repair": None,
            }
        )

    attempts.sort(key=lambda item: (item.get("line") is None, item.get("line") or 0))
    operation_counts: Counter[str] = Counter()
    failure_seen = False
    repair_epoch = 0
    last_failure_epoch: int | None = None
    validation_count = 0
    repair_validation_baseline = 0
    repair_had_prior_validation = False
    for attempt in attempts:
        digest = str(attempt["operation_digest"])
        operation_counts[digest] += 1
        repeat_index = operation_counts[digest]
        repeat = repeat_index > 1
        after_failure = failure_seen
        validation_after_repair = (
            attempt["stage"] == "tests_validators"
            and repair_epoch > 0
            and repair_had_prior_validation
            and validation_count >= repair_validation_baseline
        )
        rerun_after_fix = (
            repeat
            and after_failure
            and last_failure_epoch is not None
            and repair_epoch > last_failure_epoch
            and attempt["stage"] in RERUN_ELIGIBLE_STAGES
        )
        attempt["repeat_index"] = repeat_index
        attempt["repeat"] = repeat
        attempt["after_failure"] = after_failure
        attempt["rerun_after_fix"] = rerun_after_fix
        attempt["validation_rerun_after_repair"] = validation_after_repair
        if attempt.get("result_status") == "failed":
            failure_seen = True
            last_failure_epoch = repair_epoch
        if attempt["stage"] == "tests_validators":
            validation_count += 1
        if (
            attempt["stage"] == "diagnosis_repair"
            and safe_text(attempt.get("result_status"))
            in {"succeeded", "passed", "observed", "completed"}
        ):
            repair_epoch += 1
            repair_validation_baseline = validation_count
            repair_had_prior_validation = validation_count > 0

    observed_spans = [
        (attempt["stage"], float(attempt["span_seconds"]))
        for attempt in attempts
        if isinstance(attempt.get("span_seconds"), (int, float))
        and attempt.get("stage") in STAGES
        and attempt.get("stage") != "unknown"
    ]
    observed_intervals: list[tuple[datetime, datetime]] = []
    for attempt in attempts:
        if attempt.get("span_seconds") is None:
            continue
        call_event = next(
            (event for event in events if str(event.get("event_id") or "") == attempt["event_id"]),
            None,
        )
        result_event = next(
            (event for event in events if str(event.get("event_id") or "") == str(attempt.get("result_event_id") or "")),
            None,
        )
        call_timestamp = parse_timestamp(call_event.get("timestamp")) if call_event else None
        result_timestamp = parse_timestamp(result_event.get("timestamp")) if result_event else None
        if call_timestamp is not None and result_timestamp is not None:
            observed_intervals.append((call_timestamp, result_timestamp))
    attributed = union_seconds(observed_intervals)
    residual = max(0.0, duration - attributed) if duration is not None else None
    by_stage: dict[str, dict[str, Any]] = {stage: make_stage_bucket() for stage in STAGES}
    for stage in STAGES:
        stage_attempts = [attempt for attempt in attempts if attempt["stage"] == stage]
        resolved = [attempt for attempt in stage_attempts if attempt.get("span_seconds") is not None]
        if not stage_attempts:
            continue
        bucket = by_stage[stage]
        bucket["status"] = "observed" if resolved else "partial"
        bucket["attempt_count"] = len(stage_attempts)
        bucket["resolved_attempt_count"] = len(resolved)
        bucket["span_seconds"] = round(sum(float(item["span_seconds"]) for item in resolved), 6) if resolved else None
        bucket["span_count"] = len(resolved) if resolved else None
        bucket["unresolved_attempt_count"] = len(stage_attempts) - len(resolved) or None
        bucket["evidence_ref_count"] = len(stage_attempts)
        refs = [
            {
                "call": item["call_ref"],
                "result": item["result_ref"],
                "operation_digest": item["operation_digest"],
            }
            for item in stage_attempts
        ]
        bucket["evidence_refs"] = refs[:MAX_EPISODE_EVIDENCE_REFS]
        bucket["evidence_refs_truncated"] = len(refs) > MAX_EPISODE_EVIDENCE_REFS
    rerun_attempts = [attempt for attempt in attempts if attempt.get("rerun_after_fix") is True]
    if rerun_attempts:
        bucket = by_stage["rerun_after_fix"]
        resolved_reruns = [item for item in rerun_attempts if item.get("span_seconds") is not None]
        bucket["status"] = "observed" if resolved_reruns else "partial"
        bucket["attempt_count"] = len(rerun_attempts)
        bucket["resolved_attempt_count"] = len(resolved_reruns)
        bucket["span_seconds"] = (
            round(sum(float(item["span_seconds"]) for item in resolved_reruns), 6)
            if resolved_reruns
            else None
        )
        bucket["span_count"] = len(resolved_reruns) if resolved_reruns else None
        bucket["unresolved_attempt_count"] = len(rerun_attempts) - len(resolved_reruns) or None
        bucket["evidence_ref_count"] = len(rerun_attempts)
        refs = [
            {
                "call": item["call_ref"],
                "result": item["result_ref"],
                "operation_digest": item["operation_digest"],
            }
            for item in rerun_attempts
        ]
        bucket["evidence_refs"] = refs[:MAX_EPISODE_EVIDENCE_REFS]
        bucket["evidence_refs_truncated"] = len(refs) > MAX_EPISODE_EVIDENCE_REFS
    unknown_bucket = by_stage["unknown"]
    unknown_events = [event for event in events if not is_call_event(event) and not is_result_event(event)]
    if residual is not None or unknown_events or any(attempt["stage"] == "unknown" for attempt in attempts):
        unknown_bucket["status"] = "observed" if residual is not None else "partial"
        unknown_bucket["span_seconds"] = round(residual, 6) if residual is not None else None
        unknown_bucket["span_count"] = 1 if residual is not None else None
        unknown_attempts = [attempt for attempt in attempts if attempt["stage"] == "unknown"]
        unknown_bucket["attempt_count"] = len(unknown_attempts) or None
        unknown_bucket["resolved_attempt_count"] = sum(item.get("span_seconds") is not None for item in unknown_attempts) or None
        unknown_bucket["unresolved_attempt_count"] = (
            len(unknown_attempts) - int(unknown_bucket["resolved_attempt_count"] or 0)
            or None
        )
        unknown_bucket["evidence_ref_count"] = len(unknown_attempts) or None
        refs = [
            {
                "call": item["call_ref"],
                "result": item["result_ref"],
                "operation_digest": item["operation_digest"],
            }
            for item in unknown_attempts
        ]
        unknown_bucket["evidence_refs"] = refs[:MAX_EPISODE_EVIDENCE_REFS]
        unknown_bucket["evidence_refs_truncated"] = len(refs) > MAX_EPISODE_EVIDENCE_REFS

    repeat_samples = [
        compact_attempt(attempt)
        for attempt in attempts
        if attempt["repeat"] is True or attempt["rerun_after_fix"] is True
    ][:MAX_ATTEMPT_SAMPLES]
    attempt_samples = [compact_attempt(attempt) for attempt in attempts[:MAX_ATTEMPT_SAMPLES]]

    return {
        "episode_id": str(episode.get("episode_id") or "unknown"),
        "status": closed_episode_status(episode),
        "confidence": safe_text(episode.get("confidence")) or None,
        "event_range": {"from_line": start_line, "to_line": end_line},
        "duration_seconds": duration,
        "duration_status": "observed" if duration is not None else "unknown",
        "boundary_refs": {
            "start": episode_ref(
                session_label,
                episode,
                "intent_refs",
                owner_root_witness=owner_root_witness,
            )
            or {
                "session": _profile_session_ref(session_label, owner_root_witness),
                "raw": f"raw:line:{start_line}",
            },
            "end": {
                "session": _profile_session_ref(session_label, owner_root_witness),
                "raw": f"raw:line:{end_line}",
            },
        },
        "event_count": len(events),
        "attempt_count": len(attempts) or None,
        "resolved_attempt_count": sum(item.get("span_seconds") is not None for item in attempts) or None,
        "unresolved_attempt_count": (
            len(attempts) - sum(item.get("span_seconds") is not None for item in attempts) or None
        ),
        "stage_spans": by_stage,
        "attempt_samples": attempt_samples,
        "repeat_evidence_samples": repeat_samples,
        "repeat_amplification": {
            "status": "observed" if attempts else "unknown",
            "attempt_count": len(attempts) or None,
            "distinct_operation_count": len(operation_counts) or None,
            "repeated_attempt_count": sum(item["repeat"] is True for item in attempts) or None,
            "attempts_after_failure": sum(item["after_failure"] is True for item in attempts) or None,
            "rerun_after_fix_count": sum(item["rerun_after_fix"] is True for item in attempts) or None,
            "validation_attempt_count": sum(item["stage"] == "tests_validators" for item in attempts) or None,
            "validation_rerun_after_repair_count": sum(
                item["validation_rerun_after_repair"] is True for item in attempts
            )
            or None,
            "attempts_per_distinct_operation": (
                round(len(attempts) / len(operation_counts), 6) if operation_counts else None
            ),
        },
        "unknown_reasons": [
            reason
            for reason, present in (
                ("model_or_operator_time_not_structurally_bracketed", duration is not None),
                ("unresolved_call_result", any(item.get("result_ref") is None for item in attempts)),
                ("unmapped_structured_calls", any(item["stage"] == "unknown" for item in attempts)),
            )
            if present
        ],
    }


def identity_episode_binding(
    episode: Mapping[str, Any],
    *,
    session_id: str,
    component_admission: identity_telemetry.EpisodeComponentAdmission,
) -> dict[str, Any]:
    """Return the loader-issued public coordinate for one generated component."""

    episode_id = str(episode.get("episode_id") or "")
    line_range = event_range(dict(episode))
    if not episode_id or line_range is None:
        raise ProfileError("episode_event_range_or_id_missing")
    if not isinstance(component_admission, identity_telemetry.EpisodeComponentAdmission):
        raise ProfileError("episode_component_admission_missing")
    encoded_episode_id = identity_telemetry.public_ref_component(episode_id, "episode_id")
    binding = component_admission.public_binding()
    if binding["episode_id"] != identity_telemetry.public_ref_component(episode_id, "episode_id"):
        raise ProfileError("episode_binding_episode_id_mismatch")
    if binding["event_range"] != {"from_line": line_range[0], "to_line": line_range[1]}:
        raise ProfileError("episode_binding_event_range_mismatch")
    try:
        return identity_telemetry.validate_episode_binding(
            binding,
            expected_context={
                "session_id": str(session_id),
                "session_ref": binding["session_ref"],
                "source": binding["source"],
                "episode_id": encoded_episode_id,
                "episode_ref": binding["episode_ref"],
                "episode_component_ref": binding["episode_component_ref"],
                "component_identity": binding["component_identity"],
                "event_range": binding["event_range"],
            },
            component_admission=component_admission,
        )
    except identity_telemetry.TelemetryError as exc:
        raise ProfileError(f"episode_binding_not_exact:{exc}") from exc


def episode_owner_receipt_with_event(
    events_by_line: dict[int, dict[str, Any]],
    episode: dict[str, Any],
) -> tuple[
    dict[str, Any] | None,
    str | None,
    identity_telemetry.CarryingEventWitness | None,
]:
    """Select one dedicated receipt only when its facet is bound to this episode."""

    line_range = event_range(episode)
    if line_range is None:
        return None, "episode_event_range_missing", None
    events = [
        event
        for line, event in sorted(events_by_line.items())
        if line_range[0] <= line <= line_range[1]
    ]
    captured = identity_telemetry.capture_receipt_facets(events)
    rejected = [entry for entry in captured if entry.get("status") != "admitted"]
    if rejected:
        return None, f"identity_bound_receipt_facet_rejected:{rejected[0].get('rejection') or 'unknown'}", None
    bound = [entry.get("receipt") for entry in captured if isinstance(entry.get("receipt"), dict)]
    receipt_ids = [str(receipt.get("receipt_id")) for receipt in bound]
    if len(bound) > 1 or len(set(receipt_ids)) != len(receipt_ids):
        return None, "duplicate_identity_bound_receipt", None
    if bound:
        witness = captured[0].get("witness") if captured else None
        return (
            bound[0],
            None,
            witness if isinstance(witness, identity_telemetry.CarryingEventWitness) else None,
        )
    return None, None, None


def episode_owner_receipt(
    events_by_line: dict[int, dict[str, Any]],
    episode: dict[str, Any],
) -> tuple[dict[str, Any] | None, str | None]:
    """Compatibility wrapper that omits the carrying-event detail."""

    receipt, rejection, _witness = episode_owner_receipt_with_event(events_by_line, episode)
    return receipt, rejection


def _typed_state(value: Any) -> str:
    if isinstance(value, dict) and value.get("state") in identity_telemetry.FIELD_STATES:
        return str(value["state"])
    return "unknown"


def identity_episode_cohort(
    packets: list[dict[str, Any]],
    *,
    expected_episode_count: int | None = None,
    expected_component_order: list[str] | None = None,
    selection_status: str = "admitted",
) -> dict[str, Any]:
    """Summarize admission coverage without manufacturing metric observations."""

    if selection_status not in {"admitted", "rejected", "unknown"}:
        raise ProfileError("episode_cohort_selection_status_invalid")

    packet_statuses: Counter[str] = Counter()
    receipt_statuses: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    identity_states: Counter[str] = Counter()
    trajectory_states: Counter[str] = Counter()
    timing_states: Counter[str] = Counter()
    cache_states: Counter[str] = Counter()
    resource_states: Counter[str] = Counter()
    seen_components: set[str] = set()
    seen_episode_ids: set[str] = set()
    observed_component_order: list[str] = []
    duplicate_or_invalid_route = False
    for packet in packets:
        try:
            route = packet.get("route_admission") if isinstance(packet, Mapping) else None
            if not isinstance(route, Mapping) or route.get("route") != "episode_strict":
                raise identity_telemetry.TelemetryAdmissionError("episode_cohort_strict_route_required")
            identity_telemetry.verify_packet_integrity(packet)
            eligibility = identity_telemetry._packet_eligibility(packet)
            binding = packet.get("episode_binding")
            manifest_admission = binding.get("manifest_admission") if isinstance(binding, Mapping) else None
            component_ref = manifest_admission.get("component_ref") if isinstance(manifest_admission, Mapping) else None
            episode_id = binding.get("episode_id") if isinstance(binding, Mapping) else None
            key = (str(component_ref), str(episode_id))
            if key in seen_components or str(episode_id) in seen_episode_ids:
                duplicate_or_invalid_route = True
                raise identity_telemetry.TelemetryAdmissionError("episode_cohort_component_or_episode_duplicate")
            seen_components.add(key)
            seen_episode_ids.add(str(episode_id))
            observed_component_order.append(str(component_ref))
        except identity_telemetry.TelemetryError as exc:
            packet_statuses["excluded"] += 1
            reasons[f"packet_integrity_rejected:{exc}"] += 1
            continue
        packet_statuses[str(eligibility.get("status") or "unknown")] += 1
        reasons.update(str(reason) for reason in eligibility.get("reasons", []) if reason)
        methods = packet.get("methods") if isinstance(packet.get("methods"), dict) else {}
        federation = methods.get("owner_receipt_federation")
        if isinstance(federation, dict):
            receipt_statuses[str(federation.get("status") or "unknown")] += 1
        identity = packet.get("identity") if isinstance(packet.get("identity"), dict) else {}
        identity_states.update(_typed_state(identity.get(name)) for name in identity_telemetry.IDENTITY_FIELDS)
        trajectory = packet.get("trajectory") if isinstance(packet.get("trajectory"), dict) else {}
        trajectory_states[_typed_state(trajectory.get("chain_id"))] += 1
        steps = trajectory.get("steps") if isinstance(trajectory.get("steps"), dict) else {}
        trajectory_states.update(
            str(step.get("state") or "unknown")
            for step in steps.values()
            if isinstance(step, dict)
        )
        timing = packet.get("timing") if isinstance(packet.get("timing"), dict) else {}
        timing_states.update(_typed_state(timing.get(name)) for name in identity_telemetry.TIMING_FIELDS)
        cache = packet.get("cache") if isinstance(packet.get("cache"), dict) else {}
        cache_states.update(_typed_state(cache.get(name)) for name in ("posture", "identity", "observed_state"))
        resource = packet.get("resource") if isinstance(packet.get("resource"), dict) else {}
        resource_states[_typed_state(resource.get("posture"))] += 1
        metrics = resource.get("metrics") if isinstance(resource.get("metrics"), dict) else {}
        resource_states.update(_typed_state(metrics.get(name)) for name in identity_telemetry.RESOURCE_FIELDS)

    expected_count = expected_episode_count
    order_is_closed = (
        isinstance(expected_component_order, list)
        and observed_component_order == expected_component_order
    )
    cardinality_status = (
        "rejected"
        if selection_status != "admitted"
        else "closed"
        if isinstance(expected_count, int)
        and not isinstance(expected_count, bool)
        and expected_count >= 0
        and expected_count == len(packets)
        and not duplicate_or_invalid_route
        and len(seen_components) == len(packets)
        and order_is_closed
        else "rejected"
    )
    eligible_count = (
        packet_statuses.get("eligible_identity_packet", 0)
        if cardinality_status == "closed"
        else 0
    )
    if cardinality_status != "closed":
        reasons["admission_cardinality_rejected"] += 1
    return {
        "schema_version": IDENTITY_EPISODE_COHORT_SCHEMA_VERSION,
        "artifact_type": "identity_bound_episode_cohort",
        "status": (
            "rejected_selector_scope"
            if selection_status == "rejected"
            else "unknown_selector_scope"
            if selection_status == "unknown"
            else
            "empty_episode_scope"
            if not packets
            else "eligible_identity_packets_observed"
            if eligible_count
            else "no_eligible_identity_packets"
        ),
        "selection_status": selection_status,
        "episode_count": len(packets),
        "admission_cardinality": {
            "expected_episode_count": expected_count,
            "observed_episode_count": len(packets),
            "unique_component_count": len(seen_components),
            "unique_episode_id_count": len(seen_episode_ids),
            "declared_component_order": (
                list(expected_component_order)
                if isinstance(expected_component_order, list)
                else None
            ),
            "observed_component_order": observed_component_order,
            "status": cardinality_status,
            "selection_status": selection_status,
        },
        "eligible_count": eligible_count,
        "missing_count": packet_statuses.get("missing", 0),
        "excluded_count": packet_statuses.get("excluded", 0),
        "unknown_count": packet_statuses.get("unknown", 0),
        "unobservable_count": packet_statuses.get("unobservable", 0),
        "packet_status_counts": dict(sorted(packet_statuses.items())),
        "receipt_status_counts": dict(sorted(receipt_statuses.items())),
        "field_state_counts": {
            "identity": dict(sorted(identity_states.items())),
            "trajectory": dict(sorted(trajectory_states.items())),
            "timing": dict(sorted(timing_states.items())),
            "cache": dict(sorted(cache_states.items())),
            "resource": dict(sorted(resource_states.items())),
        },
        "reason_counts": dict(sorted(reasons.items())),
        "comparison_ready": False,
        "comparison_status": "session_memory_admission_only_no_effect_or_verdict",
        "effect": None,
        "verdict": None,
        "proof": False,
        "acceptance": False,
        "claim_ceiling": "episode_identity_and_observation_admission_only",
    }


def aggregate_stage_buckets(episodes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    aggregate: dict[str, dict[str, Any]] = {}
    for stage in STAGES:
        buckets = [episode["stage_spans"][stage] for episode in episodes]
        observed = [bucket for bucket in buckets if bucket.get("attempt_count") is not None]
        resolved = [bucket for bucket in buckets if bucket.get("span_seconds") is not None]
        if not observed and not resolved:
            aggregate[stage] = make_stage_bucket()
            continue
        aggregate[stage] = {
            "status": "observed" if resolved else "partial",
            "attempt_count": sum(int(bucket["attempt_count"]) for bucket in observed) or None,
            "resolved_attempt_count": sum(int(bucket["resolved_attempt_count"] or 0) for bucket in observed) or None,
            "span_seconds": round(sum(float(bucket["span_seconds"]) for bucket in resolved), 6) if resolved else None,
            "span_count": sum(int(bucket["span_count"] or 0) for bucket in resolved) or None,
            "unresolved_attempt_count": sum(int(bucket["unresolved_attempt_count"] or 0) for bucket in observed) or None,
            "evidence_ref_count": sum(int(bucket["evidence_ref_count"] or 0) for bucket in observed) or None,
            "evidence_refs": [
                ref
                for bucket in observed
                for ref in bucket.get("evidence_refs", [])
            ][:MAX_AGGREGATE_EVIDENCE_REFS],
            "evidence_refs_truncated": (
                len(
                    [
                        ref
                        for bucket in observed
                        for ref in bucket.get("evidence_refs", [])
                    ]
                ) > MAX_AGGREGATE_EVIDENCE_REFS
                or any(bucket.get("evidence_refs_truncated") is True for bucket in observed)
            ),
        }
    return aggregate


def aggregate_repeats(episodes: list[dict[str, Any]]) -> dict[str, Any]:
    values = [episode["repeat_amplification"] for episode in episodes]
    observed = [value for value in values if value.get("attempt_count") is not None]
    if not observed:
        return {
            "status": "unknown",
            "attempt_count": None,
            "distinct_operation_count": None,
            "repeated_attempt_count": None,
            "attempts_after_failure": None,
            "rerun_after_fix_count": None,
            "validation_attempt_count": None,
            "validation_rerun_after_repair_count": None,
            "attempts_per_distinct_operation": None,
        }
    attempt_count = sum(int(value["attempt_count"]) for value in observed)
    distinct_count = sum(int(value["distinct_operation_count"] or 0) for value in observed)
    return {
        "status": "observed",
        "attempt_count": attempt_count or None,
        "distinct_operation_count": distinct_count or None,
        "repeated_attempt_count": sum(int(value["repeated_attempt_count"] or 0) for value in observed) or None,
        "attempts_after_failure": sum(int(value["attempts_after_failure"] or 0) for value in observed) or None,
        "rerun_after_fix_count": sum(int(value["rerun_after_fix_count"] or 0) for value in observed) or None,
        "validation_attempt_count": sum(int(value["validation_attempt_count"] or 0) for value in observed) or None,
        "validation_rerun_after_repair_count": sum(
            int(value["validation_rerun_after_repair_count"] or 0) for value in observed
        )
        or None,
        "attempts_per_distinct_operation": round(attempt_count / distinct_count, 6) if distinct_count else None,
    }


def bounded_required_int(value: Any, field: str) -> int:
    parsed = int_value(value)
    if parsed is None or parsed < 0:
        raise BoundedPrefixError(f"bounded_prefix_invalid:{field}")
    return parsed


def bounded_required_hex(value: Any, field: str) -> str:
    text = str(value or "")
    if not re.fullmatch(r"[0-9a-f]{64}", text):
        raise BoundedPrefixError(f"bounded_prefix_invalid:{field}")
    return text


def bounded_required_dict(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise BoundedPrefixError(f"bounded_prefix_missing:{field}")
    return value


def bounded_prefix_source_identity(
    manifest: dict[str, Any],
    projection_publish: dict[str, Any],
) -> dict[str, Any]:
    raw = bounded_required_dict(manifest.get("raw"), "manifest_raw")
    source = bounded_required_dict(projection_publish.get("source"), "projection_source")
    identity = {
        "raw_sha256": bounded_required_hex(raw.get("sha256"), "raw_sha256"),
        "raw_bytes": bounded_required_int(raw.get("bytes"), "raw_bytes"),
        "raw_line_count": bounded_required_int(raw.get("line_count"), "raw_line_count"),
    }
    for key in ("raw_sha256", "raw_bytes", "raw_line_count"):
        if source.get(key) != identity[key]:
            raise BoundedPrefixError(f"bounded_prefix_source_mismatch:{key}")
    if raw.get("indexing_status") != "indexed":
        raise BoundedPrefixError("bounded_prefix_projection_not_indexed")
    return identity


def bounded_projection_publish_identity(
    manifest: dict[str, Any],
    index: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    index_schema = bounded_required_dict(manifest.get("index_schema"), "manifest_index_schema")
    manifest_projection = bounded_required_dict(
        index_schema.get("projection_publish"),
        "manifest_projection_publish",
    )
    index_projection = bounded_required_dict(index.get("projection_publish"), "index_projection_publish")
    if manifest_projection != index_projection:
        raise BoundedPrefixError("bounded_prefix_projection_publish_mismatch")
    raw_blocks = manifest.get("raw_blocks")
    if isinstance(raw_blocks, dict) and raw_blocks.get("projection_publish") is not None:
        if raw_blocks.get("projection_publish") != manifest_projection:
            raise BoundedPrefixError("bounded_prefix_raw_blocks_projection_mismatch")
    source = bounded_prefix_source_identity(manifest, manifest_projection)
    watermark = bounded_required_dict(
        manifest_projection.get("processed_watermark"),
        "processed_watermark",
    )
    to_line = bounded_required_int(watermark.get("to_line"), "processed_watermark.to_line")
    if to_line != source["raw_line_count"]:
        raise BoundedPrefixError("bounded_prefix_watermark_line_mismatch")
    publish_id = bounded_required_hex(manifest_projection.get("publish_id"), "publish_id")
    dependencies = bounded_required_dict(
        manifest_projection.get("dependency_generations"),
        "dependency_generations",
    )
    dependency_ids = {
        name: bounded_required_hex(dependencies.get(name), f"dependency_generations.{name}")
        for name in ("session_index", "segment_index", "task_episode_source")
    }
    index_generation_id = bounded_required_hex(index.get("generation_id"), "session_index_generation_id")
    if index_generation_id != dependency_ids["session_index"]:
        raise BoundedPrefixError("bounded_prefix_session_generation_mismatch")
    if str(index_schema.get("session_index_generation_id") or "") != index_generation_id:
        raise BoundedPrefixError("bounded_prefix_manifest_session_generation_mismatch")
    if str(index_schema.get("segment_index_generation_id") or "") != dependency_ids["segment_index"]:
        raise BoundedPrefixError("bounded_prefix_manifest_segment_generation_mismatch")
    generation_identity = bounded_required_dict(index.get("generation_identity"), "session_generation_identity")
    if str(generation_identity.get("generation_id") or "") != index_generation_id:
        raise BoundedPrefixError("bounded_prefix_session_generation_identity_mismatch")
    if generation_identity.get("projection") != "session_index":
        raise BoundedPrefixError("bounded_prefix_session_projection_unknown")
    if generation_identity.get("producer_contract_status") != "current":
        raise BoundedPrefixError("bounded_prefix_session_producer_generation_unresolved")
    dependency_identities = bounded_required_dict(
        index.get("dependency_generation_identities"),
        "dependency_generation_identities",
    )
    producer_generations: dict[str, dict[str, Any]] = {}
    for name in ("segment_index", "task_episode_source"):
        identity = bounded_required_dict(dependency_identities.get(name), f"dependency_generation_identities.{name}")
        if str(identity.get("generation_id") or "") != dependency_ids[name]:
            raise BoundedPrefixError(f"bounded_prefix_{name}_generation_mismatch")
        producer_generations[name] = {
            "generation_id": dependency_ids[name],
            "producer_sha256": bounded_required_hex(
                identity.get("producer_sha256"),
                f"dependency_generation_identities.{name}.producer_sha256",
            ),
            "producer_contract_status": identity.get("producer_contract_status"),
        }
        if identity.get("producer_contract_status") != "current":
            raise BoundedPrefixError(f"bounded_prefix_{name}_producer_generation_unresolved")
    producer_generations["session_index"] = {
        "generation_id": index_generation_id,
        "producer_sha256": bounded_required_hex(
            generation_identity.get("producer_sha256"),
            "session_generation_identity.producer_sha256",
        ),
        "producer_contract_status": generation_identity.get("producer_contract_status"),
    }
    projection = {
        "publish_id": publish_id,
        "source": source,
        "processed_watermark": {
            "to_line": to_line,
            "to_timestamp": iso_or_none(watermark.get("to_timestamp")),
        },
        "dependency_generations": dependency_ids,
    }
    if projection["processed_watermark"]["to_timestamp"] is None:
        raise BoundedPrefixError("bounded_prefix_watermark_timestamp_missing")
    return manifest_projection, projection, {
        "session_index": index_generation_id,
        "segment_index": dependency_ids["segment_index"],
        "task_episode_source": dependency_ids["task_episode_source"],
        "producer_generations": producer_generations,
    }


def bounded_component_source_identity(
    session_dir: Path,
    *,
    owner_root_witness: identity_telemetry.OwnerRootWitness,
    session_id: str,
    projection_publish: dict[str, Any],
    source: dict[str, Any],
    task_episode_generation: str,
    expected_projection: Mapping[str, Any],
    expected_task_episode_generation: str,
    expected_generation_context: Mapping[str, Any],
) -> None:
    component_manifest_path = session_dir / "session-index-shards" / "manifest.json"
    component_manifest = read_json(component_manifest_path)
    if component_manifest.get("projection_publish") != projection_publish:
        raise BoundedPrefixError("bounded_prefix_task_episode_projection_mismatch")
    component_source = bounded_required_dict(
        component_manifest.get("source_identity"),
        "task_episode_source_identity",
    )
    for key in ("raw_sha256", "raw_bytes", "raw_line_count"):
        expected = source[key]
        actual = component_source.get(key)
        if key == "raw_sha256":
            actual = bounded_required_hex(actual, f"task_episode_source_identity.{key}")
        else:
            actual = bounded_required_int(actual, f"task_episode_source_identity.{key}")
        if actual != expected:
            raise BoundedPrefixError(f"bounded_prefix_task_episode_source_mismatch:{key}")
    if str(component_source.get("task_episode_generation_id") or "") != task_episode_generation:
        raise BoundedPrefixError("bounded_prefix_task_episode_generation_mismatch")
    try:
        load_episode_records(
            session_dir,
            owner_root_witness=owner_root_witness,
            session_id=session_id,
            session_ref=identity_telemetry.public_session_ref(
                session_id,
                owner_root_witness=owner_root_witness,
            ),
            source_identity=source,
            expected_projection=expected_projection,
            expected_task_episode_generation=expected_task_episode_generation,
            expected_generation_context=expected_generation_context,
        )
    except (ProfileError, identity_telemetry.TelemetryError) as exc:
        raise BoundedPrefixError(f"bounded_prefix_owner_component_admission:{exc}") from exc


def _optional_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def observe_bounded_tail(session_dir: Path, prefix_source: dict[str, Any], publish_id: str) -> dict[str, Any]:
    capture = _optional_json(session_dir / "raw" / "capture.latest.json") or {}
    capture_bytes = int_value(capture.get("raw_bytes"))
    source_path = Path(str(capture.get("source_path") or ""))
    source_bytes: int | None = None
    try:
        if source_path.is_file():
            source_bytes = source_path.stat().st_size
    except OSError:
        source_bytes = None
    observed_sizes = [value for value in (capture_bytes, source_bytes) if value is not None]
    beyond = [value for value in observed_sizes if value > prefix_source["raw_bytes"]]
    if beyond:
        status = "excluded_beyond_prefix"
        reasons = ["observed_tail_beyond_exact_prefix"]
    elif observed_sizes:
        status = "no_tail_observed"
        reasons = ["tail_not_observed_beyond_exact_prefix"]
    else:
        status = "unresolved"
        reasons = ["live_tail_metadata_unavailable"]
    capture_anchor = "unresolved"
    if capture:
        anchor_matches = (
            capture.get("projection_raw_sha256_at_capture") == prefix_source["raw_sha256"]
            and capture.get("projection_publish_id_at_capture") == publish_id
        )
        capture_anchor = "matched" if anchor_matches else "different_or_missing"
        if not anchor_matches:
            reasons.append("capture_prefix_anchor_not_required_for_exact_prefix")
    return {
        "status": status,
        "source_bytes_observed": source_bytes,
        "capture_bytes_observed": capture_bytes,
        "capture_prefix_anchor": capture_anchor,
        "moved_during_measurement": False,
        "reasons": reasons,
        "absence_not_admitted": True,
    }


def bounded_scope_identity(material: dict[str, Any]) -> str:
    encoded = json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def validate_bounded_prefix(
    aoa_root: Path,
    selector: str,
    *,
    expected_pin: dict[str, Any] | None = None,
    owner_root_witness: identity_telemetry.OwnerRootWitness | None = None,
) -> dict[str, Any]:
    owner_root_witness = owner_root_witness or identity_telemetry._owner_root_witness_for_root(aoa_root)
    session_dir = select_session_dir(aoa_root, selector)
    manifest = read_json(session_dir / "session.manifest.json")
    index = read_json(session_dir / "session.index.json")
    session_id = str(manifest.get("session_id") or index.get("session_id") or "")
    if not session_id or session_id != str(index.get("session_id") or ""):
        raise BoundedPrefixError("bounded_prefix_session_identity_mismatch")
    manifest_projection, projection, generation = bounded_projection_publish_identity(manifest, index)
    try:
        owner_context = _owner_current_context(manifest, index, projection["source"])
    except ProfileError as exc:
        raise BoundedPrefixError(f"bounded_prefix_owner_context:{exc}") from exc
    if owner_context["projection"] != manifest_projection:
        raise BoundedPrefixError("bounded_prefix_owner_projection_context_mismatch")
    if owner_context["task_episode_generation"] != generation["task_episode_source"]:
        raise BoundedPrefixError("bounded_prefix_owner_task_generation_mismatch")
    source = projection["source"]
    load_segment_events(
        session_dir,
        index,
        owner_root_witness=owner_root_witness,
        expected_projection=manifest_projection,
        expected_segment_generation=generation["segment_index"],
        expected_line_count=source["raw_line_count"],
    )
    bounded_component_source_identity(
        session_dir,
        owner_root_witness=owner_root_witness,
        session_id=session_id,
        projection_publish=manifest_projection,
        source=source,
        task_episode_generation=generation["task_episode_source"],
        expected_projection=owner_context["projection"],
        expected_task_episode_generation=owner_context["task_episode_generation"],
        expected_generation_context={
            "task_episode_generation": generation["task_episode_source"],
            "segment_generation": generation["segment_index"],
            "session_generation": generation["session_index"],
        },
    )
    observed_pin = {
        "raw_bytes": source["raw_bytes"],
        "raw_sha256": source["raw_sha256"],
        "raw_line_count": source["raw_line_count"],
        "publish_id": projection["publish_id"],
        "session_index_generation_id": generation["session_index"],
        "segment_index_generation_id": generation["segment_index"],
        "task_episode_generation_id": generation["task_episode_source"],
    }
    for key, expected in (expected_pin or {}).items():
        if expected is not None and str(expected) != str(observed_pin.get(key)):
            raise BoundedPrefixError(f"bounded_prefix_expected_pin_mismatch:{key}")
    identity_material = {
        "schema_version": BOUNDED_MEASUREMENT_SCHEMA_VERSION,
        "route": BOUNDED_PREFIX_ROUTE,
        "session_id": session_id,
        "source": source,
        "processed_watermark": projection["processed_watermark"],
        "publish_id": projection["publish_id"],
        "dependency_generations": generation,
    }
    return {
        "session_dir": session_dir,
        "session_id": session_id,
        "manifest": manifest,
        "index": index,
        "source": source,
        "projection": projection,
        "generation": generation,
        "identity_material": identity_material,
        "identity": bounded_scope_identity(identity_material),
        "pin": {
            "provided_fields": sorted((expected_pin or {}).keys()),
            "matched": True,
        },
    }


def profile_session(
    aoa_root: Path,
    selector: str,
    *,
    max_episodes: int,
    session_label_override: str | None = None,
    identity_source: dict[str, Any] | None = None,
    identity_prefix_identity: str | None = None,
    identity_publish_id: str | None = None,
    identity_projection_status: str | None = None,
    owner_root_witness: identity_telemetry.OwnerRootWitness | None = None,
) -> dict[str, Any]:
    validate_max_episodes(max_episodes)
    owner_root_witness = owner_root_witness or identity_telemetry._owner_root_witness_for_root(aoa_root)
    session_dir = select_session_dir(aoa_root, selector)
    manifest = read_json(session_dir / "session.manifest.json")
    index = read_json(session_dir / "session.index.json")
    session_label = session_label_override or str(manifest.get("session_label") or session_dir.name)
    session_public_ref = identity_telemetry.public_session_ref(
        session_label,
        owner_root_witness=owner_root_witness,
    )
    raw = manifest.get("raw") if isinstance(manifest.get("raw"), dict) else {}
    raw_line_count = int_value(raw.get("line_count"))
    source_identity = {
        key: raw.get(source_key)
        for key, source_key in (
            ("raw_sha256", "sha256"),
            ("raw_bytes", "bytes"),
            ("raw_line_count", "line_count"),
        )
        if raw.get(source_key) is not None
    }
    projection_source = identity_source if isinstance(identity_source, dict) else source_identity
    session_id = str(manifest.get("session_id") or index.get("session_id") or "unknown")
    _verify_published_source_identity(session_dir, manifest, projection_source)
    owner_context = _owner_current_context(manifest, index, projection_source)
    events_by_line = load_segment_events(
        session_dir,
        index,
        owner_root_witness=owner_root_witness,
        expected_projection=owner_context["projection"],
        expected_segment_generation=owner_context["segment_generation"],
        expected_line_count=int(projection_source["raw_line_count"]),
    )
    episode_records = load_episode_records(
        session_dir,
        owner_root_witness=owner_root_witness,
        session_id=session_id,
        session_ref=session_public_ref,
        source_identity=projection_source,
        expected_projection=owner_context["projection"],
        expected_task_episode_generation=owner_context["task_episode_generation"],
        expected_generation_context={
            "task_episode_generation": owner_context["task_episode_generation"],
            "segment_generation": owner_context["segment_generation"],
            "session_generation": owner_context["session_generation"],
        },
    )
    episodes = [record["payload"] for record in episode_records]
    raw_blocks_value = manifest.get("raw_blocks")
    if isinstance(raw_blocks_value, dict):
        raw_blocks = raw_blocks_value.get("blocks") if isinstance(raw_blocks_value.get("blocks"), list) else []
    elif isinstance(raw_blocks_value, list):
        raw_blocks = raw_blocks_value
    else:
        raw_blocks = []
    block_statuses = Counter(
        safe_text(block.get("status")) or "unknown"
        for block in raw_blocks
        if isinstance(block, dict)
    )
    selected: list[dict[str, Any]] = []
    selected_records: list[dict[str, Any]] = []
    skipped: Counter[str] = Counter()
    for record in episode_records:
        episode = record["payload"]
        status = closed_episode_status(episode)
        if status != "closed":
            skipped[status] += 1
            continue
        if len(selected) >= max_episodes:
            skipped["limit"] += 1
            continue
        line_range = event_range(episode)
        if line_range is None:
            skipped["missing_event_range"] += 1
            continue
        if raw_line_count is not None and line_range[1] > raw_line_count:
            skipped["raw_coverage_missing"] += 1
            continue
        try:
            selected.append(
                profile_episode(
                    session_label=session_label,
                    episode=episode,
                    events_by_line=events_by_line,
                    owner_root_witness=owner_root_witness,
                )
            )
            selected_records.append(record)
        except ProfileError as exc:
            skipped[str(exc)] += 1

    identity_packets: list[dict[str, Any]] = []
    for episode_profile, component_record in zip(selected, selected_records):
        owner_receipt, receipt_rejection, receipt_carrying_event_witness = episode_owner_receipt_with_event(
            events_by_line,
            episode_profile,
        )
        packet = identity_telemetry.project_identity_bound_episode_packet(
            session_id=session_id,
            session_ref=identity_telemetry.public_session_ref(
                session_label,
                owner_root_witness=owner_root_witness,
            ),
            source=projection_source,
            prefix_identity=identity_prefix_identity,
            publish_id=identity_publish_id,
            projection_status=identity_projection_status or "bounded_readable_snapshot",
            review_status=str(manifest.get("review_status") or "unknown"),
            profile=episode_profile,
            owner_receipt=owner_receipt,
            receipt_rejection=receipt_rejection,
            episode_binding=identity_episode_binding(
                episode_profile,
                session_id=session_id,
                component_admission=component_record["component_admission"],
            ),
            component_admission=component_record["component_admission"],
            receipt_carrying_event_witness=receipt_carrying_event_witness,
        )
        episode_profile["identity_bound_telemetry"] = packet
        identity_packets.append(packet)

    stage_spans = aggregate_stage_buckets(selected)
    indexed_event_count = int_value(index.get("event_count"))
    source_alignment = (
        "count_aligned"
        if indexed_event_count is not None
        and raw_line_count is not None
        and indexed_event_count == raw_line_count == len(events_by_line)
        else "unknown"
    )
    closed_duration = sum(
        float(episode["duration_seconds"])
        for episode in selected
        if episode.get("duration_seconds") is not None
    )
    identity_cohort = identity_episode_cohort(
        identity_packets,
        expected_episode_count=len(episode_records),
        expected_component_order=[
            str(record["component_ref"])
            for record in episode_records
        ],
    )
    return {
        "session_ref": session_public_ref,
        "session_id": session_id,
        "archive_status": safe_text(manifest.get("archive_status") or index.get("archive_status")) or "unknown",
        "review_status": safe_text(manifest.get("review_status")) or "unknown",
        "review_binding": {
            "status": safe_text(manifest.get("review_status")) or "unknown",
            "review_ref": manifest.get("review_ref"),
        },
        "scope_status": "usable_closed_episode_slice" if selected else "unknown",
        "freshness": {
            "status": "bounded_readable_snapshot",
            "source_alignment": source_alignment,
            "currentness_scope": "bounded_source_snapshot",
            "global_currentness": None,
            "currentness_claimed": False,
            "basis": "manifest, session index, segment indexes, and raw line-count alignment; open tails remain excluded",
        },
        "open_tail_excluded": block_statuses.get("open", 0) > 0,
        "raw_block_statuses": dict(sorted(block_statuses.items())) or None,
        "source_refs": {
            "session_manifest": f"{session_public_ref}#session.manifest.json",
            "session_index": f"{session_public_ref}#session.index.json",
            "raw_capture": "present" if raw_line_count is not None else "unknown",
        },
        "source_identity": source_identity,
        "coverage": {
            "indexed_event_count": indexed_event_count,
            "segment_event_count": len(events_by_line) or None,
            "raw_line_count": raw_line_count,
            "closed_episode_count": len(selected) or None,
            "component_episode_count": len(episode_records),
            "component_order": [
                str(record["component_ref"])
                for record in episode_records
            ],
            "component_cardinality": {
                "manifest_entries": len(episode_records),
                "selected_closed_episodes": len(selected),
                "status": identity_cohort["admission_cardinality"]["status"],
            },
            "closed_episode_duration_seconds": round(closed_duration, 6) if selected else None,
            "episode_status_counts": {
                status: count
                for status, count in sorted(
                    Counter(closed_episode_status(record["payload"]) for record in episode_records).items()
                )
            },
            "skipped_episode_counts": dict(sorted(skipped.items())) or None,
        },
        "stage_spans": stage_spans,
        "repeat_amplification": aggregate_repeats(selected),
        "episodes": selected,
        "identity_bound_episode_cohort": identity_cohort,
        "unknown_reasons": [
            reason
            for reason, present in (
                ("session_tail_open_or_not_terminal", block_statuses.get("open", 0) > 0),
                ("non_closed_episodes_excluded", bool(skipped)),
                ("indexed_event_count_unavailable", int_value(index.get("event_count")) is None),
            )
            if present
        ],
    }


def build_bounded_report(
    aoa_root: Path,
    selectors: list[str],
    *,
    max_episodes: int,
    expected_pin: dict[str, Any] | None = None,
    delivery: dict[str, Any] | None = None,
    owner_receipt: dict[str, Any] | None = None,
    owner_receipt_rejection: str | None = None,
) -> dict[str, Any]:
    validate_max_episodes(max_episodes)
    if len(selectors) != 1:
        raise BoundedPrefixError("bounded_prefix_requires_one_session_selector")
    owner_root_witness = identity_telemetry._owner_root_witness_for_root(aoa_root)
    scope = validate_bounded_prefix(
        aoa_root,
        selectors[0],
        expected_pin=expected_pin,
        owner_root_witness=owner_root_witness,
    )
    session_id = scope["session_id"]
    tail_before = observe_bounded_tail(
        scope["session_dir"],
        scope["source"],
        scope["projection"]["publish_id"],
    )
    session_profile = profile_session(
        aoa_root,
        selectors[0],
        max_episodes=max_episodes,
        session_label_override=session_id,
        identity_source=scope["source"],
        identity_prefix_identity=scope["identity"],
        identity_publish_id=f"sha256:{scope['projection']['publish_id']}",
        identity_projection_status="stale-readable",
        owner_root_witness=owner_root_witness,
    )
    tail_after = observe_bounded_tail(
        scope["session_dir"],
        scope["source"],
        scope["projection"]["publish_id"],
    )
    if (
        tail_before.get("source_bytes_observed") != tail_after.get("source_bytes_observed")
        or tail_before.get("capture_bytes_observed") != tail_after.get("capture_bytes_observed")
    ):
        tail_after["status"] = "moving_tail_observed"
        tail_after["moved_during_measurement"] = True
        tail_after["reasons"] = [
            *tail_after.get("reasons", []),
            "tail_observation_advanced_during_measurement",
        ]
    episodes = session_profile.get("episodes") if isinstance(session_profile.get("episodes"), list) else []
    positive_event_count = sum(
        int(episode.get("event_count") or 0)
        for episode in episodes
        if isinstance(episode, dict)
    )
    measurement_scope = {
        "status": "stale-readable",
        "scope_currentness": "identity_bound_prefix_only",
        "session_ref": identity_telemetry.public_session_ref(
            session_id,
            owner_root_witness=owner_root_witness,
        ),
        "prefix": {
            "identity": scope["identity"],
            "source": {
                "sha256": f"sha256:{scope['source']['raw_sha256']}",
                "bytes": scope["source"]["raw_bytes"],
                "line_count": scope["source"]["raw_line_count"],
            },
            "processed_watermark": scope["projection"]["processed_watermark"],
            "projection_publish_id": f"sha256:{scope['projection']['publish_id']}",
            "producer_generations": scope["generation"]["producer_generations"],
            "dependency_generation_ids": {
                key: value
                for key, value in scope["generation"].items()
                if key != "producer_generations"
            },
        },
        "returned_positive_evidence": {
            "status": "observed" if episodes else "empty_bounded_scope",
            "episode_count": len(episodes),
            "event_count": positive_event_count or 0,
            "basis": "closed task episodes with event ranges and generated segment coverage inside the exact prefix",
            "semantic_absence_admitted": False,
        },
        "excluded_live_tail": tail_after,
        "global_recall": {
            "status": "incomplete",
            "complete": False,
            "reason": "prefix_scope_does_not_cover_the_moving_or_unprojected_tail",
        },
        "negative_claims": {
            "admitted": False,
            "reason": "zero_or_missing_results_under_prefix_scope_are_not_semantic_absence",
        },
        "profiler_semantics": {
            "stage_profile_schema_version": SCHEMA_VERSION,
            "correlated_call_result_spans": True,
            "agent_model_time": "unknown",
            "operator_active_time": "unknown",
            "unresolved_calls": "unknown_not_zero",
            "open_tail": "excluded",
            "raw_transcript_scanned": False,
            "capture_ledger_blocks_scanned": False,
            "privacy": "public_safe_normalized_shapes_and_logical_refs_only",
        },
    }
    aggregate = {
        "session_count": 1,
        "profiled_closed_episode_count": len(episodes) or None,
        "stage_spans": aggregate_stage_buckets(episodes),
        "repeat_amplification": aggregate_repeats(episodes),
        "unknown_stage_count": (
            1
            if session_profile.get("stage_spans", {}).get("unknown", {}).get("span_seconds") is not None
            else None
        ),
    }
    identity_bound_telemetry = identity_telemetry.project_identity_bound_packet(
        session_id=session_id,
        session_ref=identity_telemetry.public_session_ref(
            session_id,
            owner_root_witness=owner_root_witness,
        ),
        source=scope["source"],
        prefix_identity=scope["identity"],
        publish_id=f"sha256:{scope['projection']['publish_id']}",
        projection_status="stale-readable",
        review_status=str(session_profile.get("review_status") or "unknown"),
        profile=session_profile,
        owner_receipt=owner_receipt,
        receipt_rejection=owner_receipt_rejection,
    )
    identity_bound_episode_cohort = session_profile["identity_bound_episode_cohort"]
    return {
        "schema_version": BOUNDED_MEASUREMENT_SCHEMA_VERSION,
        "route": {
            "id": BOUNDED_PREFIX_ROUTE,
            "owner": "aoa-session-memory",
            "mode": "read_only_generated_index_profile",
            "mutation": False,
            "scope": "one identity-bound stable projection prefix",
        },
        "corpus": {
            "selection_status": "one_explicit_session_selector",
            "session_ref": identity_telemetry.public_session_ref(
                session_id,
                owner_root_witness=owner_root_witness,
            ),
            "scope": "closed_task_episodes_only; live/open tails are excluded",
        },
        "measurement_scope": measurement_scope,
        "session": session_profile,
        "aggregate": aggregate,
        "identity_bound_telemetry": identity_bound_telemetry,
        "identity_bound_episode_cohort": identity_bound_episode_cohort,
        "stage_contract": {
            "stages": list(STAGES),
            **STAGE_CONTRACT,
        },
        "evaluator_input": {
            "method_id": BOUNDED_PREFIX_ROUTE,
            "comparison_posture": "bounded_positive_measurement_only",
            "supported_claims": [
                "positive evidence from eligible closed episodes inside one exact stable prefix",
                "identity-bound correlated structured call-to-result wall-clock spans",
                "episode-level identity binding and explicit cohort eligibility states",
                "explicit excluded-tail, unknown, and zero-result claim boundaries",
            ],
            "not_supported": [
                "global recall completeness",
                "negative or semantic absence claims",
                "effectiveness, causality, policy, or evaluator verdict",
                "model compute time or human active time",
            ],
            "verdict": None,
        },
        "delivery": delivery
        or {
            "changed_paths": None,
            "commit": None,
            "focused_verification": None,
            "no_change": False,
        },
        "return_status": "positive_evidence_observed" if episodes else "empty_bounded_scope_not_absence",
    }


def build_report(
    aoa_root: Path,
    selectors: list[str],
    *,
    max_episodes: int,
    delivery: dict[str, Any] | None = None,
    owner_receipt: dict[str, Any] | None = None,
    owner_receipt_rejection: str | None = None,
) -> dict[str, Any]:
    validate_max_episodes(max_episodes)
    owner_root_witness = identity_telemetry._owner_root_witness_for_root(aoa_root)
    sessions: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for selector in selectors:
        try:
            sessions.append(
                profile_session(
                    aoa_root,
                    selector,
                    max_episodes=max_episodes,
                    owner_root_witness=owner_root_witness,
                )
            )
        except ProfileError as exc:
            errors.append({"selector": selector, "error": str(exc)})

    episodes = [episode for session in sessions for episode in session.get("episodes", [])]
    aggregate = {
        "session_count": len(sessions) or None,
        "profiled_closed_episode_count": len(episodes) or None,
        "stage_spans": aggregate_stage_buckets(episodes),
        "repeat_amplification": aggregate_repeats(episodes),
        "unknown_stage_count": sum(
            session.get("stage_spans", {}).get("unknown", {}).get("span_seconds") is not None
            for session in sessions
        )
        or None,
    }
    identity_bound_telemetry = []
    for index, session in enumerate(sessions):
        receipt = owner_receipt if len(sessions) == 1 and index == 0 else None
        rejection = owner_receipt_rejection if len(sessions) == 1 and index == 0 else None
        if len(sessions) != 1 and owner_receipt is not None:
            rejection = "owner_receipt_requires_one_session_selector"
        identity_bound_telemetry.append(
            identity_telemetry.project_identity_bound_packet(
                session_id=str(session.get("session_id") or "unknown"),
                session_ref=str(session.get("session_ref") or "unknown"),
                source=session.get("source_identity") if isinstance(session.get("source_identity"), dict) else {},
                prefix_identity=None,
                publish_id=None,
                projection_status=str(session.get("freshness", {}).get("status") or "unknown"),
                review_status=str(session.get("review_status") or "unknown"),
                profile=session,
                owner_receipt=receipt,
                receipt_rejection=rejection,
            )
        )
    identity_packets = [
        episode.get("identity_bound_telemetry")
        for session in sessions
        for episode in session.get("episodes", [])
        if isinstance(episode, dict) and isinstance(episode.get("identity_bound_telemetry"), dict)
    ]
    public_selector_refs = [
        str(session.get("session_ref"))
        for session in sessions
        if isinstance(session.get("session_ref"), str)
    ]
    public_failed_selectors = [
        {
            "selector_ref": identity_telemetry.public_session_ref(
                str(error["selector"]),
                owner_root_witness=owner_root_witness,
            ),
            "error": str(error["error"]).split(":", 1)[0],
        }
        for error in errors
    ]
    expected_episode_count = sum(
        int(session.get("coverage", {}).get("component_episode_count") or len(session.get("episodes", [])))
        for session in sessions
        if isinstance(session, dict)
    )
    expected_component_order = [
        str(component_ref)
        for session in sessions
        for component_ref in (
            session.get("coverage", {}).get("component_order", [])
            if isinstance(session.get("coverage", {}).get("component_order", []), list)
            else []
        )
    ]
    selection_status = "rejected" if errors or not selectors else "admitted"
    return {
        "schema_version": SCHEMA_VERSION,
        "profiler": {
            "version": PROFILER_VERSION,
            "owner": "aoa-session-memory",
            "mode": "read_only_generated_index_profile",
            "source_surfaces": ["session.manifest.json", "session.index.json", "segment.index.json", "task_episode_components"],
        },
        "corpus": {
            "selection_status": (
                "rejected_selector_scope"
                if selection_status == "rejected"
                else "bounded_explicit_session_selectors"
            ),
            "selectors": public_selector_refs,
            "session_count": len(sessions) or None,
            "failed_selector_count": len(errors) or None,
            "failed_selectors": public_failed_selectors or None,
            "scope": "closed_task_episodes_only; live/open session tails are excluded",
        },
        "stage_contract": {
            "stages": list(STAGES),
            **STAGE_CONTRACT,
        },
        "sessions": sessions,
        "aggregate": aggregate,
        "identity_bound_telemetry": identity_bound_telemetry,
        "identity_bound_episode_cohort": identity_episode_cohort(
            identity_packets,
            expected_episode_count=expected_episode_count,
            expected_component_order=expected_component_order,
            selection_status=selection_status,
        ),
        "evaluator_input": {
            "method_id": PROFILER_VERSION,
            "comparison_posture": "data_and_support_basis_only",
            "supported_claims": [
                "correlated structured call-to-result wall-clock spans",
                "normalized operation repeat counts within a closed task episode",
                "episode-level identity binding and explicit cohort eligibility states",
                "explicit unknown or excluded coverage reasons",
            ],
            "not_supported": [
                "model compute time or human active time",
                "causal attribution from a route mention alone",
                "method comparison, universal policy, or evaluator verdict",
            ],
            "verdict": None,
        },
        "delivery": delivery
        or {
            "changed_paths": None,
            "commit": None,
            "focused_verification": None,
            "no_change": None,
        },
        "return_status": "profiled" if sessions and episodes else "partial_no_usable_closed_episode_slice",
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aoa-root", type=Path, required=True)
    parser.add_argument("--session", action="append", required=True, help="Session label, id, fragment, or explicit session directory.")
    parser.add_argument("--max-episodes", type=int, default=500)
    parser.add_argument(
        "--bounded-prefix",
        action="store_true",
        help="Require and report one fail-closed exact stable-projection prefix.",
    )
    parser.add_argument("--expected-raw-bytes", type=int)
    parser.add_argument("--expected-raw-sha256")
    parser.add_argument("--expected-raw-line-count", type=int)
    parser.add_argument("--expected-publish-id")
    parser.add_argument("--expected-session-index-generation-id")
    parser.add_argument("--expected-segment-index-generation-id")
    parser.add_argument("--expected-task-episode-generation-id")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--changed-path", action="append", default=[])
    parser.add_argument("--commit")
    parser.add_argument("--verification", action="append", default=[])
    parser.add_argument(
        "--owner-telemetry-receipt",
        type=Path,
        help="Optional public-safe validation-owner telemetry receipt; it is admitted only on an exact session/source join.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.max_episodes < 1:
        print("--max-episodes must be positive", file=sys.stderr)
        return 2
    try:
        delivery = {
            "changed_paths": args.changed_path or None,
            "commit": args.commit,
            "focused_verification": args.verification or None,
            "no_change": False,
        }
        owner_receipt = None
        owner_receipt_rejection = None
        if args.owner_telemetry_receipt:
            try:
                owner_receipt = identity_telemetry.load_owner_receipt(str(args.owner_telemetry_receipt.expanduser()))
            except identity_telemetry.TelemetryError as exc:
                owner_receipt_rejection = str(exc)
        if args.bounded_prefix:
            expected_pin = {
                key: value
                for key, value in {
                    "raw_bytes": args.expected_raw_bytes,
                    "raw_sha256": args.expected_raw_sha256,
                    "raw_line_count": args.expected_raw_line_count,
                    "publish_id": args.expected_publish_id,
                    "session_index_generation_id": args.expected_session_index_generation_id,
                    "segment_index_generation_id": args.expected_segment_index_generation_id,
                    "task_episode_generation_id": args.expected_task_episode_generation_id,
                }.items()
                if value is not None
            }
            report = build_bounded_report(
                args.aoa_root.expanduser(),
                args.session,
                max_episodes=args.max_episodes,
                expected_pin=expected_pin,
                delivery=delivery,
                owner_receipt=owner_receipt,
                owner_receipt_rejection=owner_receipt_rejection,
            )
        else:
            report = build_report(
                args.aoa_root.expanduser(),
                args.session,
                max_episodes=args.max_episodes,
                delivery=delivery,
                owner_receipt=owner_receipt,
                owner_receipt_rejection=owner_receipt_rejection,
            )
    except ProfileError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
