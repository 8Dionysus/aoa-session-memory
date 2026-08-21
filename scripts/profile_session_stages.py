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
from typing import Any, Iterable


SCHEMA_VERSION = "stage_profile_v1"
PROFILER_VERSION = "structured_segment_index_correlated_call_result_v1"

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


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProfileError(f"unreadable_json:{path.name}") from exc
    if not isinstance(value, dict):
        raise ProfileError(f"json_object_required:{path.name}")
    return value


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


def logical_ref(session_label: str, event: dict[str, Any]) -> dict[str, str]:
    line = int_value(event.get("line"))
    segment_id = "unknown"
    anchor = str(event.get("md_anchor") or "")
    if anchor:
        segment_id = anchor.split("__", 1)[0]
    raw = f"raw:line:{line}" if line is not None else "raw:line:unknown"
    return {
        "session": f"session:{session_label}",
        "raw": raw,
        "segment": f"session:{session_label}#segment:{segment_id}",
        "event": str(event.get("event_id") or "unknown"),
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


def load_segment_events(session_dir: Path, index: dict[str, Any]) -> dict[int, dict[str, Any]]:
    events_by_line: dict[int, dict[str, Any]] = {}
    segments = index.get("segments") if isinstance(index.get("segments"), list) else []
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        index_value = str(segment.get("index") or "")
        index_path = Path(index_value)
        if not index_path.is_file():
            index_path = session_dir / "segments" / Path(index_value).name
        if not index_path.is_file():
            continue
        try:
            segment_index = read_json(index_path)
        except ProfileError:
            continue
        events = segment_index.get("events") if isinstance(segment_index.get("events"), list) else []
        for event in events:
            if not isinstance(event, dict):
                continue
            line = int_value(event.get("line"))
            if line is None:
                continue
            events_by_line.setdefault(line, event)
    return events_by_line


def load_episode_payloads(session_dir: Path) -> list[dict[str, Any]]:
    manifest = read_json(session_dir / "session-index-shards" / "manifest.json")
    components = manifest.get("components") if isinstance(manifest.get("components"), dict) else {}
    refs = components.get("task_episodes") if isinstance(components.get("task_episodes"), list) else []
    episodes: list[dict[str, Any]] = []
    for entry in refs:
        if not isinstance(entry, dict):
            continue
        ref = str(entry.get("ref") or "")
        if not ref:
            continue
        component_path = session_dir / ref
        if not component_path.is_file():
            continue
        try:
            component = read_json(component_path)
        except ProfileError:
            continue
        payload = component.get("payload") if isinstance(component.get("payload"), dict) else {}
        if payload:
            episodes.append(payload)
    return episodes


def episode_ref(session_label: str, episode: dict[str, Any], event_key: str) -> dict[str, str] | None:
    value = episode.get(event_key)
    if not isinstance(value, list) or not value:
        return None
    first = value[0] if isinstance(value[0], dict) else {}
    line = int_value(first.get("line"))
    event_id = str(first.get("event_id") or "")
    return {
        "session": f"session:{session_label}",
        "raw": f"raw:line:{line}" if line is not None else "raw:line:unknown",
        "event": event_id or "unknown",
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
                "call_ref": logical_ref(session_label, event),
                "result_ref": logical_ref(session_label, first_result) if first_result else None,
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
    repair_seen = False
    validation_seen = False
    for attempt in attempts:
        digest = str(attempt["operation_digest"])
        operation_counts[digest] += 1
        repeat_index = operation_counts[digest]
        repeat = repeat_index > 1
        after_failure = failure_seen
        validation_after_repair = (
            attempt["stage"] == "tests_validators"
            and repair_seen
            and validation_seen
        )
        rerun_after_fix = (
            repeat
            and after_failure
            and attempt["stage"] in RERUN_ELIGIBLE_STAGES
        )
        attempt["repeat_index"] = repeat_index
        attempt["repeat"] = repeat
        attempt["after_failure"] = after_failure
        attempt["rerun_after_fix"] = rerun_after_fix
        attempt["validation_rerun_after_repair"] = validation_after_repair
        if attempt.get("result_status") == "failed":
            failure_seen = True
        if attempt["stage"] == "diagnosis_repair":
            repair_seen = True
        if attempt["stage"] == "tests_validators":
            validation_seen = True

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
            "start": episode_ref(session_label, episode, "intent_refs")
            or {"session": f"session:{session_label}", "raw": f"raw:line:{start_line}"},
            "end": {"session": f"session:{session_label}", "raw": f"raw:line:{end_line}"},
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


def profile_session(aoa_root: Path, selector: str, *, max_episodes: int) -> dict[str, Any]:
    session_dir = select_session_dir(aoa_root, selector)
    manifest = read_json(session_dir / "session.manifest.json")
    index = read_json(session_dir / "session.index.json")
    session_label = str(manifest.get("session_label") or session_dir.name)
    events_by_line = load_segment_events(session_dir, index)
    episodes = load_episode_payloads(session_dir)
    raw = manifest.get("raw") if isinstance(manifest.get("raw"), dict) else {}
    raw_line_count = int_value(raw.get("line_count"))
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
    skipped: Counter[str] = Counter()
    for episode in episodes:
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
                )
            )
        except ProfileError as exc:
            skipped[str(exc)] += 1

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
    return {
        "session_label": session_label,
        "session_ref": f"session:{session_label}",
        "session_id": str(manifest.get("session_id") or index.get("session_id") or "unknown"),
        "archive_status": safe_text(manifest.get("archive_status") or index.get("archive_status")) or "unknown",
        "review_status": safe_text(manifest.get("review_status")) or "unknown",
        "scope_status": "usable_closed_episode_slice" if selected else "unknown",
        "freshness": {
            "status": "bounded_readable_snapshot",
            "source_alignment": source_alignment,
            "global_currentness": None,
            "currentness_claimed": False,
            "basis": "manifest, session index, segment indexes, and raw line-count alignment; open tails remain excluded",
        },
        "open_tail_excluded": block_statuses.get("open", 0) > 0,
        "raw_block_statuses": dict(sorted(block_statuses.items())) or None,
        "source_refs": {
            "session_manifest": f"session:{session_label}#session.manifest.json",
            "session_index": f"session:{session_label}#session.index.json",
            "raw_capture": "present" if raw_line_count is not None else "unknown",
        },
        "coverage": {
            "indexed_event_count": indexed_event_count,
            "segment_event_count": len(events_by_line) or None,
            "raw_line_count": raw_line_count,
            "closed_episode_count": len(selected) or None,
            "closed_episode_duration_seconds": round(closed_duration, 6) if selected else None,
            "skipped_episode_counts": dict(sorted(skipped.items())) or None,
        },
        "stage_spans": stage_spans,
        "repeat_amplification": aggregate_repeats(selected),
        "episodes": selected,
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


def build_report(
    aoa_root: Path,
    selectors: list[str],
    *,
    max_episodes: int,
    delivery: dict[str, Any] | None = None,
) -> dict[str, Any]:
    sessions: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for selector in selectors:
        try:
            sessions.append(profile_session(aoa_root, selector, max_episodes=max_episodes))
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
    return {
        "schema_version": SCHEMA_VERSION,
        "profiler": {
            "version": PROFILER_VERSION,
            "owner": "aoa-session-memory",
            "mode": "read_only_generated_index_profile",
            "source_surfaces": ["session.manifest.json", "session.index.json", "segment.index.json", "task_episode_components"],
        },
        "corpus": {
            "selection_status": "bounded_explicit_session_selectors",
            "selectors": selectors,
            "session_count": len(sessions) or None,
            "failed_selector_count": len(errors) or None,
            "failed_selectors": errors or None,
            "scope": "closed_task_episodes_only; live/open session tails are excluded",
        },
        "stage_contract": {
            "stages": list(STAGES),
            **STAGE_CONTRACT,
        },
        "sessions": sessions,
        "aggregate": aggregate,
        "evaluator_input": {
            "method_id": PROFILER_VERSION,
            "comparison_posture": "data_and_support_basis_only",
            "supported_claims": [
                "correlated structured call-to-result wall-clock spans",
                "normalized operation repeat counts within a closed task episode",
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
    parser.add_argument("--output", type=Path)
    parser.add_argument("--changed-path", action="append", default=[])
    parser.add_argument("--commit")
    parser.add_argument("--verification", action="append", default=[])
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.max_episodes < 1:
        print("--max-episodes must be positive", file=sys.stderr)
        return 2
    try:
        report = build_report(
            args.aoa_root.expanduser(),
            args.session,
            max_episodes=args.max_episodes,
            delivery={
                "changed_paths": args.changed_path or None,
                "commit": args.commit,
                "focused_verification": args.verification or None,
                "no_change": False,
            },
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
