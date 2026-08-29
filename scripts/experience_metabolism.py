#!/usr/bin/env python3
"""Derive privacy-safe, review-gated experience candidates from stage profiles.

This module deliberately consumes the generated ``stage_profile_v1`` product,
not raw transcripts or capture ledgers.  It emits advisory packets only.  The
separate lifecycle reducer makes review, evaluation, shadow, owner acceptance,
and rollback explicit so recurrence can never become policy by itself.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import sys
from typing import Any, Iterable, Mapping


SCHEMA_VERSION = "experience_metabolism_v1"
PRODUCER_VERSION = "reviewed_stage_profile_motif_packet_v1"
PROFILE_SCHEMA_VERSION = "stage_profile_v1"
OBSERVATION_SCHEMA_VERSION = "aoa_observation_packet_v1"
REF_SCHEME = "privacy-hashed-logical-ref-v1"

REVIEWED_STATUSES = {
    "reviewed",
    "accepted",
    "owner-reviewed",
    "owner_reviewed",
    "owner-accepted",
    "owner_accepted",
}
FRESH_PROFILE_STATUSES = {"bounded_readable_snapshot"}
LIFECYCLE_STATES = {
    "candidate",
    "eval_pending",
    "shadow_pending",
    "owner_review_pending",
    "accepted",
    "adopted",
    "rejected",
    "superseded",
    "rolled_back",
}
MAX_EVIDENCE_REFS = 16
MAX_CANDIDATES = 256
MAX_OCCURRENCES_PER_GROUP = 4096
SAFE_WORD = re.compile(r"^[a-z0-9_.:-]{1,128}$")
SAFE_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
SAFE_SHAPE = re.compile(r"^[a-z0-9_.:-]{1,64}:[a-z0-9_.:-]{1,64}:[0-9a-f]{16}$")
SAFE_RAW_REF = re.compile(r"^raw:line:(?:[1-9][0-9]*|unknown)$")
SAFE_SESSION_REF = re.compile(r"^session:sha256:[0-9a-f]{16}$")
SAFE_SEGMENT_REF = re.compile(r"^segment:sha256:[0-9a-f]{16}$")
SAFE_EVENT_REF = re.compile(r"^event:sha256:[0-9a-f]{16}$")
RAW_SHA256 = re.compile(r"^[0-9a-f]{64}$")
SAFE_CANDIDATE_ID = re.compile(r"^experience-candidate:[0-9a-f]{24}$")

PROFILE_PROFILER_VERSION = "structured_segment_index_correlated_call_result_identity_episode_v1"
SUPPORTED_PROFILE_PROFILER_VERSIONS = frozenset(
    {
        PROFILE_PROFILER_VERSION,
        "structured_segment_index_correlated_call_result_v1",
    }
)
PROFILE_SOURCE_SURFACES = (
    "session.manifest.json",
    "session.index.json",
    "segment.index.json",
    "task_episode_components",
)
LOGICAL_REF_KEYS = {"scheme", "session", "raw", "segment", "event", "start", "end"}
COMPARISON_KINDS = ("paired", "held_out", "ablation")
COMPARISON_RESULT_STATUSES = {"observed", "passed", "accepted"}
SHADOW_COVERAGE_STATUSES = {"complete", "partial", "unknown"}
SHADOW_COMPARISON_MODES = {"paired", "held_out", "ablation"}
ALTERNATIVE_EXPLANATION_CODES = {
    "task_mix_or_repository_state",
    "association_does_not_establish_causality",
}
COMPARISON_PACKET_KEYS = {
    "comparison_type",
    "candidate_id",
    "source_binding_refs",
    "subject_ref",
    "baseline_ref",
    "shadow_ref",
    "context_ref",
    "result_ref",
    "source_fingerprint",
    "evidence_digest",
    "numeric_result",
    "result_status",
}
LIFECYCLE_BASE_FIELDS = (
    "candidate_id",
    "schema_version",
    "status",
    "motif",
    "recurrence",
    "evidence_diversity",
    "counterevidence",
    "alternative_explanations",
    "causal_attribution",
    "approval_sensitivity",
    "trajectory_cost",
    "provenance",
    "privacy",
    "advisory_observation",
)
EXPECTED_RECEIPT_OWNERS = {
    "review_verdict": "reviewer-office",
    "eval_verdict": "aoa-evals",
    "shadow_result": "abyss-stack",
    "owner_acceptance": "aoa-session-memory",
    "adoption": "aoa-session-memory",
    "reject": "aoa-session-memory",
    "supersede": "aoa-session-memory",
    "rollback": "aoa-session-memory",
}
EXPECTED_RECEIPT_TYPES = {
    "review_verdict": "review-verdict-v1",
    "eval_verdict": "eval-verdict-v1",
    "shadow_result": "shadow-result-v1",
    "owner_acceptance": "owner-acceptance-v1",
    "adoption": "adoption-v1",
    "reject": "rejection-v1",
    "supersede": "supersession-v1",
    "rollback": "rollback-v1",
}

RERUN_ELIGIBLE_STAGES = {
    "kag_navigation_index_gate",
    "tests_validators",
    "diagnosis_repair",
    "ci_landing_waits",
    "agent_model_or_coordination",
}
KNOWN_STAGES = RERUN_ELIGIBLE_STAGES | {"coordination_idle_wait"}


class MetabolismError(RuntimeError):
    """Raised when an input or lifecycle event cannot be admitted safely."""


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MetabolismError(f"unreadable_json:{path.name}") from exc
    if not isinstance(value, dict):
        raise MetabolismError(f"json_object_required:{path.name}")
    return value


def safe_text(value: Any, limit: int = 96) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text[:limit]


def safe_word(value: Any, *, fallback: str = "unknown") -> str:
    text = safe_text(value)
    return text if SAFE_WORD.fullmatch(text) else fallback


def int_value(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, float):
        if not math.isfinite(value) or not value.is_integer():
            return None
        parsed = int(value)
    elif isinstance(value, str) and re.fullmatch(r"[0-9]+", value.strip()):
        parsed = int(value.strip())
    else:
        return None
    return parsed if parsed >= 0 else None


def number_value(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return round(parsed, 6) if math.isfinite(parsed) and parsed >= 0 else None


def stable_digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def short_digest(value: Any) -> str:
    return f"sha256:{stable_digest(value)[:16]}"


def valid_operation_digest(value: Any) -> str | None:
    text = str(value or "")
    if SAFE_DIGEST.fullmatch(text):
        return text
    return None


def valid_operation_shape(value: Any) -> str | None:
    text = str(value or "")
    if SAFE_SHAPE.fullmatch(text):
        return text
    return None


def hashed_token(prefix: str, value: Any) -> str:
    return f"{prefix}:sha256:{stable_digest(str(value))[:16]}"


def safe_logical_ref(value: Any) -> dict[str, str] | None:
    """Hash identity-bearing ref components while retaining line coordinates."""

    if not isinstance(value, Mapping):
        return None
    if any(key not in LOGICAL_REF_KEYS for key in value):
        return None
    if "scheme" in value and value.get("scheme") not in {None, REF_SCHEME}:
        return None
    output: dict[str, str] = {"scheme": REF_SCHEME}
    if value.get("scheme") == REF_SCHEME:
        for key, pattern in (
            ("session", SAFE_SESSION_REF),
            ("raw", SAFE_RAW_REF),
            ("segment", SAFE_SEGMENT_REF),
            ("event", SAFE_EVENT_REF),
        ):
            candidate = value.get(key)
            if key in value:
                if not isinstance(candidate, str) or not pattern.fullmatch(candidate):
                    return None
                output[key] = candidate
        for key in ("start", "end"):
            candidate = value.get(key)
            if isinstance(candidate, Mapping):
                nested = safe_logical_ref(candidate)
                if nested is None:
                    return None
                output[key] = json.dumps(nested, sort_keys=True, separators=(",", ":"))
            elif isinstance(candidate, str):
                if len(candidate) > 512:
                    return None
                try:
                    decoded = json.loads(candidate)
                except json.JSONDecodeError:
                    return None
                if not isinstance(decoded, Mapping):
                    return None
                nested = safe_logical_ref(decoded)
                if nested is None:
                    return None
                canonical = json.dumps(nested, sort_keys=True, separators=(",", ":"))
                if canonical != candidate:
                    return None
                output[key] = canonical
            elif key in value:
                return None
        return output if len(output) > 1 else None
    session = value.get("session")
    if session is not None and not isinstance(session, str):
        return None
    if session:
        output["session"] = hashed_token("session", session.removeprefix("session:"))
    raw_value = value.get("raw")
    if raw_value is not None and not isinstance(raw_value, str):
        return None
    raw = raw_value or ""
    if raw and SAFE_RAW_REF.fullmatch(raw):
        output["raw"] = raw
    elif raw:
        return None
    segment = value.get("segment")
    if segment is not None and not isinstance(segment, str):
        return None
    if segment:
        output["segment"] = hashed_token("segment", segment)
    event = value.get("event")
    if event is not None and not isinstance(event, str):
        return None
    if event:
        output["event"] = hashed_token("event", event)
    return output if len(output) > 1 else None


def safe_event_reference(value: Any) -> dict[str, str] | None:
    """Hash a scalar provenance reference without ever returning its text."""

    if isinstance(value, Mapping):
        return safe_logical_ref(value)
    if value is None or not str(value).strip():
        return None
    return {"scheme": REF_SCHEME, "event": hashed_token("event", value)}


def safe_comparison_refs(values: Iterable[Any]) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    seen: set[str] = set()
    for value in values:
        ref = safe_event_reference(value)
        if ref is None:
            continue
        key = json.dumps(ref, sort_keys=True, separators=(",", ":"))
        if key in seen:
            continue
        seen.add(key)
        refs.append(ref)
        if len(refs) > MAX_EVIDENCE_REFS:
            raise MetabolismError("comparison_reference_limit_exceeded")
    return refs


def safe_source_ref(value: Any) -> str | None:
    if not value:
        return None
    return hashed_token("source", value)


def safe_evidence_refs(values: Iterable[Any]) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    seen: set[str] = set()
    for value in values:
        ref = safe_logical_ref(value)
        if ref is None:
            continue
        key = json.dumps(ref, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        refs.append(ref)
        if len(refs) >= MAX_EVIDENCE_REFS:
            break
    return refs


def normalized_review_status(value: Any) -> str:
    text = safe_text(value).replace(" ", "-")
    allowed = REVIEWED_STATUSES | {"provisional", "pending", "unknown", "rejected", "unreviewed"}
    return text if text in allowed else "unknown"


def validate_profile_input(profile: Mapping[str, Any]) -> Mapping[str, Any]:
    """Require the bounded generated-profile ABI before any measurement."""

    if not isinstance(profile, Mapping) or profile.get("schema_version") != PROFILE_SCHEMA_VERSION:
        raise MetabolismError("stage_profile_v1_required")
    if not isinstance(profile.get("sessions"), list):
        raise MetabolismError("stage_profile_sessions_required")
    profiler = profile.get("profiler")
    if not isinstance(profiler, Mapping):
        raise MetabolismError("stage_profile_profiler_required")
    if profiler.get("version") not in SUPPORTED_PROFILE_PROFILER_VERSIONS:
        raise MetabolismError("stage_profile_profiler_version_invalid")
    if profiler.get("owner") != "aoa-session-memory" or profiler.get("mode") != "read_only_generated_index_profile":
        raise MetabolismError("stage_profile_profiler_owner_or_mode_invalid")
    source_surfaces = profiler.get("source_surfaces")
    if source_surfaces != list(PROFILE_SOURCE_SURFACES):
        raise MetabolismError("stage_profile_source_surfaces_invalid")
    for session in profile["sessions"]:
        if not isinstance(session, Mapping):
            raise MetabolismError("stage_profile_session_object_required")
    return profile


def normalized_freshness_status(value: Any) -> str:
    text = safe_text(value)
    allowed = FRESH_PROFILE_STATUSES | {"stale-readable", "stale", "degraded", "unknown"}
    return text if text in allowed else "unknown"


def safe_observed_at(value: Any) -> str:
    text = str(value or "").strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d+)?Z", text):
        try:
            datetime.fromisoformat(text[:-1] + "+00:00")
        except ValueError:
            return "unknown"
        return text
    return "unknown"


def _line_number_from_ref(value: Any) -> int | None:
    if not isinstance(value, Mapping):
        return None
    raw = value.get("raw")
    if not isinstance(raw, str):
        return None
    match = re.fullmatch(r"raw:line:([1-9][0-9]*)", raw)
    return int(match.group(1)) if match else None


def _episode_line_range(episode: Mapping[str, Any]) -> tuple[int, int] | None:
    event_range = episode.get("event_range")
    if isinstance(event_range, Mapping):
        start = int_value(event_range.get("from_line"))
        end = int_value(event_range.get("to_line"))
        if start is not None and end is not None and start >= 1 and end >= start:
            return start, end
        return None
    boundary = episode.get("boundary_refs")
    if isinstance(boundary, Mapping):
        start = _line_number_from_ref(boundary.get("start"))
        end = _line_number_from_ref(boundary.get("end"))
        if start is not None and end is not None and end >= start:
            return start, end
    return None


def _ref_binds_to_episode(
    value: Any,
    *,
    session_id: str,
    expected_session_ref: str,
    episode: Mapping[str, Any],
    raw_line_count: int | None = None,
) -> bool:
    if not isinstance(value, Mapping) or safe_logical_ref(value) is None:
        return False
    raw_session = value.get("session")
    if raw_session not in {f"session:{session_id}", expected_session_ref}:
        return False
    line = _line_number_from_ref(value)
    line_range = _episode_line_range(episode)
    if line is None or line_range is None or not line_range[0] <= line <= line_range[1]:
        return False
    return raw_line_count is None or 1 <= line <= raw_line_count


def _episode_boundaries_bind(
    session: Mapping[str, Any],
    episode: Mapping[str, Any],
    *,
    session_id: str,
    expected_session_ref: str,
) -> bool:
    boundary = episode.get("boundary_refs")
    if not isinstance(boundary, Mapping):
        return False
    start_line = _line_number_from_ref(boundary.get("start"))
    end_line = _line_number_from_ref(boundary.get("end"))
    if start_line is None or end_line is None or start_line > end_line:
        return False
    return all(
        _ref_binds_to_episode(
            boundary.get(key),
            session_id=session_id,
            expected_session_ref=expected_session_ref,
            episode=episode,
            raw_line_count=int_value(
                (session.get("source_identity") or {}).get("raw_line_count")
            ) if isinstance(session.get("source_identity"), Mapping) else None,
        )
        for key in ("start", "end")
    )


def _attempt_refs_bind_to_episode(
    attempt: Mapping[str, Any],
    *,
    session_id: str,
    expected_session_ref: str,
    episode: Mapping[str, Any],
    raw_line_count: int | None,
) -> bool:
    """Require source-wide bounds and call-before-result ordering at consumption."""

    call_ref = attempt.get("call_ref")
    result_ref = attempt.get("result_ref")
    if not _ref_binds_to_episode(
        call_ref,
        session_id=session_id,
        expected_session_ref=expected_session_ref,
        episode=episode,
        raw_line_count=raw_line_count,
    ):
        return False
    if result_ref is None:
        return True
    if not _ref_binds_to_episode(
        result_ref,
        session_id=session_id,
        expected_session_ref=expected_session_ref,
        episode=episode,
        raw_line_count=raw_line_count,
    ):
        return False
    call_line = _line_number_from_ref(call_ref)
    result_line = _line_number_from_ref(result_ref)
    return (
        call_line is not None
        and result_line is not None
        and call_line < result_line
    )


def _recomputed_attempt_context(
    attempts: list[Mapping[str, Any]],
) -> list[dict[str, Any]] | None:
    """Recompute recurrence predecessors from the complete sampled call order.

    Repeat flags are producer output, not authority.  A current profile must
    retain every attempt in a closed episode, so the consumer can independently
    derive the predecessor count and failure/repair/validation context before
    admitting a motif signal.
    """

    ordered: list[tuple[int, int, Mapping[str, Any]]] = []
    seen_lines: set[int] = set()
    for index, attempt in enumerate(attempts):
        line = _line_number_from_ref(attempt.get("call_ref"))
        if line is None or line in seen_lines:
            return None
        digest = valid_operation_digest(attempt.get("operation_digest"))
        if digest is None:
            return None
        seen_lines.add(line)
        ordered.append((line, index, attempt))
    ordered.sort(key=lambda item: (item[0], item[1]))
    contexts: list[dict[str, Any] | None] = [None] * len(attempts)
    operation_counts: Counter[str] = Counter()
    failure_seen = False
    repair_epoch = 0
    last_failure_epoch: int | None = None
    validation_count = 0
    repair_validation_baseline = 0
    repair_had_prior_validation = False
    for line, index, attempt in ordered:
        digest = valid_operation_digest(attempt.get("operation_digest"))
        stage = safe_word(attempt.get("stage"))
        if digest is None:
            return None
        operation_counts[digest] += 1
        repeat_index = operation_counts[digest]
        repeat = repeat_index > 1
        after_failure = failure_seen
        validation_after_repair = (
            stage == "tests_validators"
            and repair_epoch > 0
            and repair_had_prior_validation
            and validation_count >= repair_validation_baseline
        )
        rerun_after_fix = (
            repeat
            and after_failure
            and last_failure_epoch is not None
            and repair_epoch > last_failure_epoch
            and stage in RERUN_ELIGIBLE_STAGES
        )
        contexts[index] = {
            "line": line,
            "stage": stage,
            "operation_digest": digest,
            "repeat_index": repeat_index,
            "repeat": repeat,
            "after_failure": after_failure,
            "rerun_after_fix": rerun_after_fix,
            "validation_rerun_after_repair": validation_after_repair,
        }
        if safe_text(attempt.get("result_status")) == "failed":
            failure_seen = True
            last_failure_epoch = repair_epoch
        if stage == "tests_validators":
            validation_count += 1
        if (
            stage == "diagnosis_repair"
            and safe_text(attempt.get("result_status")) in {"succeeded", "passed", "observed", "completed"}
        ):
            repair_epoch += 1
            repair_validation_baseline = validation_count
            repair_had_prior_validation = validation_count > 0
    return [context for context in contexts if context is not None]


def _profile_source_abi_reasons(session: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    session_id = str(session.get("session_id") or "").strip()
    if not session_id:
        reasons.append("session_identity_missing")
    if session.get("session_ref") != f"session:{session_id}" if session_id else True:
        reasons.append("session_ref_not_bound_to_session_id")
    source_identity = session.get("source_identity")
    if not isinstance(source_identity, Mapping):
        reasons.append("source_identity_missing")
    else:
        if set(source_identity) != {"raw_sha256", "raw_bytes", "raw_line_count"}:
            reasons.append("source_identity_shape_invalid")
        if not isinstance(source_identity.get("raw_sha256"), str) or not RAW_SHA256.fullmatch(source_identity["raw_sha256"]):
            reasons.append("source_identity_digest_invalid")
        for key in ("raw_bytes", "raw_line_count"):
            if int_value(source_identity.get(key)) is None:
                reasons.append(f"source_identity_{key}_invalid")
    coverage = session.get("coverage")
    if not isinstance(coverage, Mapping):
        reasons.append("coverage_missing")
    else:
        counts = [int_value(coverage.get(key)) for key in ("indexed_event_count", "segment_event_count", "raw_line_count")]
        if any(value is None for value in counts) or len(set(counts)) != 1:
            reasons.append("coverage_counts_not_aligned")
        if int_value(coverage.get("closed_episode_count")) is None:
            reasons.append("closed_episode_coverage_missing")
        episode_status_counts = coverage.get("episode_status_counts")
        if (
            not isinstance(episode_status_counts, Mapping)
            or not episode_status_counts
            or any(
                not isinstance(status, str)
                or not status
                or int_value(count) is None
                or int_value(count) < 1
                for status, count in episode_status_counts.items()
            )
        ):
            reasons.append("episode_status_coverage_missing")
    freshness = session.get("freshness")
    if not isinstance(freshness, Mapping):
        reasons.append("freshness_binding_missing")
    else:
        if freshness.get("status") != "bounded_readable_snapshot":
            reasons.append("freshness_status_invalid")
        if freshness.get("source_alignment") != "count_aligned":
            reasons.append("freshness_alignment_invalid")
        if freshness.get("currentness_scope") != "bounded_source_snapshot":
            reasons.append("freshness_scope_invalid")
        if freshness.get("currentness_claimed") is not False or freshness.get("global_currentness") is not None:
            reasons.append("freshness_currentness_claim_invalid")
        if not isinstance(freshness.get("basis"), str) or not freshness["basis"].strip():
            reasons.append("freshness_basis_missing")
    source_refs = session.get("source_refs")
    if not isinstance(source_refs, Mapping) or set(source_refs) != {"session_manifest", "session_index", "raw_capture"} or not all(
        isinstance(source_refs.get(key), str) and source_refs.get(key).strip()
        for key in ("session_manifest", "session_index")
    ) or source_refs.get("raw_capture") != "present":
        reasons.append("source_refs_not_complete")
    if session.get("archive_status") != "indexed":
        reasons.append("archive_status_not_indexed")
    if session.get("open_tail_excluded") is not False:
        reasons.append("open_tail_coverage_not_excluded")
    raw_block_statuses = session.get("raw_block_statuses")
    if not isinstance(raw_block_statuses, Mapping) or not raw_block_statuses:
        reasons.append("raw_block_coverage_unknown")
    elif any(
        status != "sealed"
        or int_value(count) is None
        or int_value(count) < 1
        for status, count in raw_block_statuses.items()
    ):
        reasons.append("raw_block_coverage_not_sealed")
    review_status = normalized_review_status(session.get("review_status"))
    binding = session.get("review_binding")
    if not isinstance(binding, Mapping) or set(binding) != {"status", "review_ref"} or normalized_review_status(binding.get("status")) != review_status:
        reasons.append("review_binding_status_missing")
    elif review_status in REVIEWED_STATUSES:
        if not isinstance(binding.get("review_ref"), str) or not binding["review_ref"].strip():
            reasons.append("review_receipt_ref_missing")
    elif binding.get("review_ref") is not None:
        reasons.append("review_receipt_ref_unexpected")
    episodes = session.get("episodes") if isinstance(session.get("episodes"), list) else []
    episode_status_counts_observed: Counter[str] = Counter()
    for episode in episodes:
        if not isinstance(episode, Mapping):
            reasons.append("episode_status_shape_invalid")
            continue
        episode_status_counts_observed[safe_text(episode.get("status")) or "unknown"] += 1
    closed_count = episode_status_counts_observed.get("closed", 0)
    coverage_map = coverage if isinstance(coverage, Mapping) else {}
    if int_value(coverage_map.get("closed_episode_count")) != closed_count:
        reasons.append("closed_episode_coverage_mismatch")
    if isinstance(source_identity, Mapping) and coverage_map:
        if int_value(source_identity.get("raw_line_count")) != int_value(coverage_map.get("raw_line_count")):
            reasons.append("source_identity_coverage_mismatch")
        if int_value(source_identity.get("raw_line_count")) is not None and int_value(source_identity.get("raw_line_count")) <= 0 and closed_count:
            reasons.append("source_identity_empty_for_closed_episode")
    if not coverage_map or "skipped_episode_counts" not in coverage_map:
        reasons.append("episode_coverage_omission_status_missing")
    else:
        skipped = coverage_map.get("skipped_episode_counts")
        all_episode_status_counts = coverage_map.get("episode_status_counts")
        declared_counts: dict[str, int] = {}
        if isinstance(all_episode_status_counts, Mapping):
            for status, count in all_episode_status_counts.items():
                normalized_status = safe_text(status)
                parsed_count = int_value(count)
                if (
                    not isinstance(status, str)
                    or normalized_status != status
                    or parsed_count is None
                    or parsed_count < 1
                    or normalized_status in declared_counts
                ):
                    reasons.append("episode_status_coverage_missing")
                    continue
                declared_counts[normalized_status] = parsed_count
        # Only closed entries are usable recurrence input. Non-closed entries
        # may be present in the profile, but must still be represented by the
        # explicit omission counter below.
        observed_counts = {
            status: count
            for status, count in episode_status_counts_observed.items()
            if status == "closed"
        }
        omitted_counts: dict[str, int] = {}
        if isinstance(skipped, Mapping):
            for status, count in skipped.items():
                normalized_status = safe_text(status)
                parsed_count = int_value(count)
                if parsed_count is None or parsed_count < 1:
                    reasons.append("episode_coverage_omitted")
                    continue
                if normalized_status == "limit":
                    # A bounded episode limit is an explicit but unsafe omission for
                    # recurrence: it must not be treated as a complete session slice.
                    reasons.append("episode_coverage_omitted")
                    continue
                if normalized_status not in declared_counts:
                    reasons.append("episode_status_coverage_mismatch")
                    reasons.append("episode_coverage_omitted")
                    continue
                omitted_counts[normalized_status] = parsed_count
        elif skipped is not None:
            reasons.append("episode_coverage_omitted")
        if declared_counts != {
            status: observed_counts.get(status, 0) + omitted_counts.get(status, 0)
            for status in set(declared_counts) | set(observed_counts) | set(omitted_counts)
        }:
            reasons.append("episode_status_coverage_mismatch")
        expected_non_closed = {
            status: count
            for status, count in declared_counts.items()
            if status != "closed"
        }
        if expected_non_closed and any(
            omitted_counts.get(status, 0) != count
            for status, count in expected_non_closed.items()
        ):
            reasons.append("episode_coverage_omitted")
        if not expected_non_closed and omitted_counts:
            reasons.append("episode_coverage_omitted")
        if isinstance(skipped, Mapping) and any(
            int_value(count) is None or int_value(count) < 1
            for count in skipped.values()
        ):
            reasons.append("episode_coverage_omitted")
    for episode in episodes:
        if not isinstance(episode, Mapping) or safe_text(episode.get("status")) != "closed":
            continue
        expected_session_ref = hashed_token("session", session_id) if session_id else ""
        if not _episode_boundaries_bind(
            session,
            episode,
            session_id=session_id,
            expected_session_ref=expected_session_ref,
        ):
            reasons.append("episode_boundary_ref_not_bound")
        attempt_count = int_value(episode.get("attempt_count"))
        attempt_values = episode.get("attempt_samples")
        if attempt_count is None:
            if attempt_values not in (None, []):
                reasons.append("attempt_sample_shape_invalid")
        elif not isinstance(attempt_values, list) or len(attempt_values) != attempt_count:
            reasons.append("attempt_sample_coverage_truncated")
        repeat = episode.get("repeat_amplification")
        repeat_count = int_value(repeat.get("repeated_attempt_count")) if isinstance(repeat, Mapping) else None
        repeat_values = episode.get("repeat_evidence_samples")
        if repeat_count is None:
            if repeat_values not in (None, []):
                reasons.append("repeat_sample_shape_invalid")
        elif not isinstance(repeat_values, list) or len(repeat_values) != repeat_count:
            reasons.append("repeat_sample_coverage_truncated")
        primary_values = episode.get("attempt_samples")
        if isinstance(primary_values, list) and any(
            not isinstance(value, Mapping) for value in primary_values
        ):
            reasons.append("attempt_sample_shape_invalid")
        if isinstance(repeat_values, list) and any(
            not isinstance(value, Mapping) for value in repeat_values
        ):
            reasons.append("repeat_sample_shape_invalid")
        if (
            isinstance(primary_values, list)
            and all(isinstance(value, Mapping) for value in primary_values)
            and isinstance(repeat_values, list)
            and all(isinstance(value, Mapping) for value in repeat_values)
        ):
            primary_markers = Counter(
                json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
                for value in primary_values
                if isinstance(value, Mapping)
            )
            repeat_markers = Counter(
                json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
                for value in repeat_values
                if isinstance(value, Mapping)
            )
            if any(
                count > primary_markers.get(marker, 0)
                for marker, count in repeat_markers.items()
            ):
                reasons.append("repeat_samples_not_subset_of_attempts")
            if any(
                isinstance(value, Mapping)
                and not (value.get("repeat") is True or value.get("rerun_after_fix") is True)
                for value in repeat_values
            ):
                reasons.append("repeat_sample_flag_invalid")
        if isinstance(primary_values, list) and all(
            isinstance(value, Mapping) for value in primary_values
        ):
            sequence_context = _recomputed_attempt_context(primary_values)
            if sequence_context is None:
                reasons.append("attempt_sequence_ambiguous")
        for bucket_group in (
            episode.get("stage_spans"),
        ):
            if not isinstance(bucket_group, Mapping):
                reasons.append("stage_coverage_missing")
                continue
            for bucket in bucket_group.values():
                if not isinstance(bucket, Mapping):
                    reasons.append("stage_coverage_invalid")
                    continue
                if bucket.get("evidence_refs_truncated") is True:
                    reasons.append("stage_evidence_coverage_truncated")
        attempt_values: list[Any] = []
        for sample_key in ("attempt_samples", "repeat_evidence_samples"):
            values = episode.get(sample_key)
            if isinstance(values, list):
                attempt_values.extend(values)
        for attempt in attempt_values:
            if not isinstance(attempt, Mapping):
                reasons.append("attempt_sample_shape_invalid")
                continue
            raw_line_count = int_value(
                (source_identity or {}).get("raw_line_count")
            ) if isinstance(source_identity, Mapping) else None
            call_ref = attempt.get("call_ref")
            result_ref = attempt.get("result_ref")
            if not _ref_binds_to_episode(
                call_ref,
                session_id=session_id,
                expected_session_ref=expected_session_ref,
                episode=episode,
                raw_line_count=raw_line_count,
            ):
                reasons.append(
                    "call_ref_out_of_source_bounds"
                    if _ref_binds_to_episode(
                        call_ref,
                        session_id=session_id,
                        expected_session_ref=expected_session_ref,
                        episode=episode,
                    )
                    else "call_ref_not_bound_to_episode"
                )
            elif result_ref is not None and not _ref_binds_to_episode(
                result_ref,
                session_id=session_id,
                expected_session_ref=expected_session_ref,
                episode=episode,
                raw_line_count=raw_line_count,
            ):
                reasons.append(
                    "result_ref_out_of_source_bounds"
                    if _ref_binds_to_episode(
                        result_ref,
                        session_id=session_id,
                        expected_session_ref=expected_session_ref,
                        episode=episode,
                    )
                    else "result_ref_not_bound_to_episode"
                )
            elif result_ref is not None:
                call_line = _line_number_from_ref(call_ref)
                result_line = _line_number_from_ref(result_ref)
                if call_line is None or result_line is None or call_line >= result_line:
                    reasons.append("call_result_order_invalid")
    return reasons


def session_gate(session: Mapping[str, Any]) -> dict[str, Any]:
    reasons: list[str] = _profile_source_abi_reasons(session)
    review_status = normalized_review_status(session.get("review_status"))
    if review_status not in REVIEWED_STATUSES:
        reasons.append("session_not_reviewed")
    freshness = session.get("freshness") if isinstance(session.get("freshness"), Mapping) else {}
    freshness_status = normalized_freshness_status(freshness.get("status"))
    if freshness_status not in FRESH_PROFILE_STATUSES:
        reasons.append("profile_freshness_not_current")
    if freshness.get("source_alignment") != "count_aligned":
        reasons.append("source_alignment_unknown")
    if safe_text(session.get("scope_status")) != "usable_closed_episode_slice":
        reasons.append("closed_episode_slice_not_usable")
    episodes = session.get("episodes") if isinstance(session.get("episodes"), list) else []
    if not any(
        isinstance(episode, Mapping) and safe_text(episode.get("status")) == "closed"
        for episode in episodes
    ):
        reasons.append("closed_episode_missing")
    source_refs = session.get("source_refs") if isinstance(session.get("source_refs"), Mapping) else {}
    if not source_refs.get("session_manifest") or not source_refs.get("session_index"):
        reasons.append("provenance_refs_missing")
    session_id = str(session.get("session_id") or "").strip()
    if not session_id:
        reasons.append("session_identity_missing")
    binding = session.get("review_binding") if isinstance(session.get("review_binding"), Mapping) else {}
    review_ref = (
        safe_logical_ref({"session": f"session:{session_id}", "event": binding.get("review_ref")})
        if review_status in REVIEWED_STATUSES and session_id and isinstance(binding.get("review_ref"), str)
        else None
    )
    return {
        "eligible": not reasons,
        "review_status": review_status,
        "freshness_status": freshness_status or "unknown",
        "reasons": reasons,
        "session_ref": hashed_token("session", session_id or "missing"),
        "source_binding_ref": (
            f"sha256:{stable_digest(dict(session.get('source_identity') or {}))}"
            if isinstance(session.get("source_identity"), Mapping)
            else "sha256:" + "0" * 64
        ),
        "profile_ref": short_digest(
            {
                "session_id": session_id,
                "session_ref": session.get("session_ref"),
                "source_refs": source_refs,
            }
        ),
        "review_ref": review_ref,
    }


def episode_ref(session: Mapping[str, Any], episode: Mapping[str, Any]) -> dict[str, str] | None:
    session_id = str(session.get("session_id") or "").strip()
    expected_session_ref = hashed_token("session", session_id) if session_id else ""
    if not _episode_boundaries_bind(
        session,
        episode,
        session_id=session_id,
        expected_session_ref=expected_session_ref,
    ):
        return None
    boundary = episode.get("boundary_refs") if isinstance(episode.get("boundary_refs"), Mapping) else {}
    start = safe_logical_ref(boundary.get("start"))
    end = safe_logical_ref(boundary.get("end"))
    if start is None and end is None:
        return None
    output = {"scheme": REF_SCHEME, "session": session_gate(session)["session_ref"]}
    if start is not None:
        output["start"] = json.dumps(start, sort_keys=True, separators=(",", ":"))
    if end is not None:
        output["end"] = json.dumps(end, sort_keys=True, separators=(",", ":"))
    return output


def attempt_samples(episode: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    output: list[Mapping[str, Any]] = []
    seen: set[str] = set()
    # The complete primary sample is the sequence authority.  Repeat samples
    # are an indexed view and must never introduce extra observations.
    values = episode.get("attempt_samples")
    if not isinstance(values, list):
        return output
    for value in values:
        if not isinstance(value, Mapping):
            continue
        # Only byte-for-byte equivalent structured observations are duplicates.
        # In particular, keep differing result refs/statuses for counterevidence.
        marker = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
        if marker in seen:
            continue
        seen.add(marker)
        output.append(value)
    return output


def operation_shape_matches(shape: str, stage: str, tool: str, digest: str) -> bool:
    """Check the producer's shape/digest cross-field invariant."""

    return shape == f"{stage}:{tool}:{digest.removeprefix('sha256:')[:16]}"


def producer_flags_consistent(
    attempt: Mapping[str, Any],
    stage: str,
    *,
    expected_context: Mapping[str, Any] | None,
) -> bool:
    """Reject contextless or contradictory repeat flags from a profile producer."""

    if stage == "unknown" or not isinstance(expected_context, Mapping):
        return False
    repeat_index = int_value(attempt.get("repeat_index"))
    repeat = attempt.get("repeat")
    after_failure = attempt.get("after_failure")
    rerun_after_fix = attempt.get("rerun_after_fix")
    validation_rerun = attempt.get("validation_rerun_after_repair")
    if repeat is not None and not isinstance(repeat, bool):
        return False
    if after_failure is not None and not isinstance(after_failure, bool):
        return False
    if rerun_after_fix is not None and not isinstance(rerun_after_fix, bool):
        return False
    if validation_rerun is not None and not isinstance(validation_rerun, bool):
        return False
    if repeat_index is None or repeat_index < 1 or not all(
        isinstance(value, bool)
        for value in (repeat, after_failure, rerun_after_fix, validation_rerun)
    ):
        return False
    expected = {
        "stage": stage,
        "operation_digest": valid_operation_digest(attempt.get("operation_digest")),
        "repeat_index": expected_context.get("repeat_index"),
        "repeat": expected_context.get("repeat"),
        "after_failure": expected_context.get("after_failure"),
        "rerun_after_fix": expected_context.get("rerun_after_fix"),
        "validation_rerun_after_repair": expected_context.get("validation_rerun_after_repair"),
    }
    if (
        expected["operation_digest"] is None
        or expected_context.get("stage") != stage
        or repeat_index != expected["repeat_index"]
        or repeat != expected["repeat"]
        or after_failure != expected["after_failure"]
        or rerun_after_fix != expected["rerun_after_fix"]
        or validation_rerun != expected["validation_rerun_after_repair"]
    ):
        return False
    return True


def motif_signals(attempt: Mapping[str, Any]) -> list[str]:
    signals = ["operation_observed"]
    if not attempt.get("producer_flags_consistent", True):
        return signals
    if attempt.get("repeat") is True:
        signals.append("repeated_operation")
    if attempt.get("rerun_after_fix") is True:
        signals.append("rerun_after_fix")
    if attempt.get("validation_rerun_after_repair") is True:
        signals.append("validation_rerun_after_repair")
    if safe_text(attempt.get("stage")) == "coordination_idle_wait":
        signals.append("coordination_idle_wait")
    if safe_text(attempt.get("stage")) == "unknown":
        signals.append("unknown_stage")
    return signals


def extract_occurrences(session: Mapping[str, Any], episode: Mapping[str, Any], gate: Mapping[str, Any]) -> list[dict[str, Any]]:
    episode_status = safe_text(episode.get("status"))
    if episode_status != "closed" or not gate.get("eligible"):
        return []
    episode_coordinate = episode_ref(session, episode)
    if episode_coordinate is None:
        return []
    occurrences: list[dict[str, Any]] = []
    samples = attempt_samples(episode)
    sequence_context = _recomputed_attempt_context(samples)
    if sequence_context is None or len(sequence_context) != len(samples):
        return []
    for index, attempt in enumerate(samples):
        digest = valid_operation_digest(attempt.get("operation_digest"))
        raw_shape = valid_operation_shape(attempt.get("operation_shape"))
        if digest is None or raw_shape is None:
            continue
        call_ref = safe_logical_ref(attempt.get("call_ref"))
        result_ref = safe_logical_ref(attempt.get("result_ref"))
        session_id = str(session.get("session_id") or "").strip()
        if (
            call_ref is None
            or not _attempt_refs_bind_to_episode(
                attempt,
                session_id=session_id,
                expected_session_ref=gate["session_ref"],
                episode=episode,
                raw_line_count=int_value(
                    (session.get("source_identity") or {}).get("raw_line_count")
                ) if isinstance(session.get("source_identity"), Mapping) else None,
            )
        ):
            continue
        tool = safe_word(attempt.get("tool"))
        raw_stage = safe_word(attempt.get("stage"))
        stage = raw_stage if raw_stage in KNOWN_STAGES or raw_stage == "unknown" else "unknown"
        shape = raw_shape if stage != "unknown" else f"unknown:{tool}:{digest.removeprefix('sha256:')[:16]}"
        result_status = safe_text(attempt.get("result_status"))
        if result_status not in {"succeeded", "failed", "error", "timed_out", "timeout"}:
            result_status = "unknown"
        flags_consistent = producer_flags_consistent(
            attempt,
            stage,
            expected_context=sequence_context[index],
        )
        if not operation_shape_matches(shape, stage, tool, digest):
            flags_consistent = False
        if result_ref is None or not flags_consistent:
            result_status = "unknown"
        normalized_attempt = dict(attempt)
        normalized_attempt["producer_flags_consistent"] = flags_consistent
        for signal in motif_signals(normalized_attempt):
            occurrences.append(
                {
                    "key": f"{signal}|{stage}|{digest}",
                    "signal": signal,
                    "stage": stage,
                    "tool": tool,
                    "operation_shape": shape,
                    "operation_digest": digest,
                    "result_status": result_status,
                    "evidence_status": "verified" if flags_consistent and result_ref is not None else "unknown",
                    "span_seconds": number_value(attempt.get("span_seconds")),
                    "session_ref": gate["session_ref"],
                    "source_binding_ref": gate["source_binding_ref"],
                    "profile_ref": gate["profile_ref"],
                    "review_ref": gate.get("review_ref"),
                    "episode_ref": episode_coordinate,
                    "call_ref": call_ref,
                    "result_ref": result_ref,
                    "repeat_index": attempt.get("repeat_index"),
                    "repeat": attempt.get("repeat"),
                    "after_failure": attempt.get("after_failure"),
                    "rerun_after_fix": attempt.get("rerun_after_fix"),
                    "validation_rerun_after_repair": attempt.get("validation_rerun_after_repair"),
                    "producer_flags_consistent": flags_consistent,
                    "evidence_refs": safe_evidence_refs(
                        [attempt.get("call_ref"), attempt.get("result_ref")]
                    ),
                }
            )
    return occurrences


def median_or_none(values: Iterable[float | int | None]) -> float | None:
    numbers = [float(value) for value in values if isinstance(value, (int, float))]
    return round(statistics.median(numbers), 6) if numbers else None


def _profile_binding(profile: Mapping[str, Any]) -> dict[str, Any]:
    """Return a content-free identity for one bounded generated profile."""

    validate_profile_input(profile)
    sessions = profile.get("sessions") if isinstance(profile.get("sessions"), list) else []
    session_bindings: list[dict[str, Any]] = []
    source_binding_refs: set[str] = set()
    for session in sessions:
        if not isinstance(session, Mapping):
            continue
        gate = session_gate(session)
        session_bindings.append(
            {
                "session_ref": gate["session_ref"],
                "source_binding_ref": gate["source_binding_ref"],
                "profile_ref": gate["profile_ref"],
                "eligible": bool(gate["eligible"]),
            }
        )
        source_binding_refs.add(gate["source_binding_ref"])
    session_bindings.sort(key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":")))
    sources = sorted(source_binding_refs)
    if len(session_bindings) > MAX_CANDIDATES or len(sources) > MAX_CANDIDATES:
        raise MetabolismError("profile_binding_limit_exceeded")
    identity_seed = {
        "schema_version": PROFILE_SCHEMA_VERSION,
        "profiler_version": profile.get("profiler", {}).get("version"),
        "sessions": session_bindings,
        "source_binding_refs": sources,
    }
    profile_ref = {
        "scheme": REF_SCHEME,
        "event": f"event:sha256:{stable_digest(identity_seed)[:16]}",
    }
    return {"profile_ref": profile_ref, "source_binding_refs": sources}


def profile_metrics(profile: Mapping[str, Any], *, eligible_only: bool = True) -> dict[str, Any]:
    validate_profile_input(profile)
    profile_binding = _profile_binding(profile)
    sessions = profile.get("sessions") if isinstance(profile.get("sessions"), list) else []
    durations: list[float] = []
    residual_unknown: list[float] = []
    repeats = 0
    attempts = 0
    reruns = 0
    unknown_episodes = 0
    episode_count = 0
    eligible_sessions = 0
    excluded_sessions = 0
    for session in sessions:
        if not isinstance(session, Mapping):
            continue
        gate = session_gate(session)
        if gate["eligible"]:
            eligible_sessions += 1
        else:
            excluded_sessions += 1
        if eligible_only and not gate["eligible"]:
            continue
        episodes = session.get("episodes") if isinstance(session.get("episodes"), list) else []
        for episode in episodes:
            if not isinstance(episode, Mapping) or safe_text(episode.get("status")) != "closed":
                continue
            episode_count += 1
            duration = number_value(episode.get("duration_seconds"))
            if duration is not None:
                durations.append(duration)
            stages = episode.get("stage_spans") if isinstance(episode.get("stage_spans"), Mapping) else {}
            unknown = stages.get("unknown") if isinstance(stages.get("unknown"), Mapping) else {}
            unknown_seconds = number_value(unknown.get("span_seconds"))
            if unknown_seconds is not None:
                residual_unknown.append(unknown_seconds)
            else:
                unknown_episodes += 1
            repeat = episode.get("repeat_amplification") if isinstance(episode.get("repeat_amplification"), Mapping) else {}
            repeats += int_value(repeat.get("repeated_attempt_count")) or 0
            attempts += int_value(repeat.get("attempt_count")) or 0
            reruns += int_value(repeat.get("rerun_after_fix_count")) or 0
    coverage_status = (
        "unknown"
        if not sessions
        else "partial"
        if excluded_sessions or not episode_count
        else "complete"
    )
    return {
        "profile_ref": profile_binding["profile_ref"],
        "source_binding_refs": profile_binding["source_binding_refs"],
        "episode_count": episode_count,
        "eligible_session_count": eligible_sessions,
        "excluded_session_count": excluded_sessions,
        "median_episode_wall_seconds": median_or_none(durations),
        "total_episode_wall_seconds": round(sum(durations), 6) if durations else None,
        "median_residual_unknown_seconds": median_or_none(residual_unknown),
        "total_residual_unknown_seconds": round(sum(residual_unknown), 6) if residual_unknown else None,
        "unknown_episode_count": unknown_episodes,
        "unknown_episode_rate": round(unknown_episodes / episode_count, 6) if episode_count else None,
        "repeat_overhead_attempts": repeats if attempts else None,
        "rerun_after_fix_rate": round(reruns / attempts, 6) if attempts else None,
        "measurement_basis": "closed reviewed episodes and correlated stage-profile spans",
        "activity_counts_are_context_only": True,
        "coverage_status": coverage_status,
    }


def trajectory_cost(occurrences: list[Mapping[str, Any]], episode_count: int) -> dict[str, Any]:
    spans = [number_value(item.get("span_seconds")) for item in occurrences]
    known_spans = [value for value in spans if value is not None]
    unknown_occurrences = sum(value is None for value in spans)
    return {
        "status": "observed" if known_spans else "unknown",
        "episode_count": episode_count,
        "operation_span_seconds": {
            "total": round(sum(known_spans), 6) if known_spans else None,
            "median": median_or_none(known_spans),
            "known_occurrence_count": len(known_spans),
            "unknown_occurrence_count": unknown_occurrences,
        },
        "residual_unknown_cost": {
            "status": "unknown_not_zero" if unknown_occurrences else "none_observed",
            "occurrence_count": unknown_occurrences,
        },
        "proxies": {
            "repeat_occurrence_count": sum(item.get("signal") == "repeated_operation" for item in occurrences),
            "rerun_after_fix_occurrence_count": sum(item.get("signal") == "rerun_after_fix" for item in occurrences),
            "interpretation": "diagnostic pressure only; not a universal cost or benefit score",
        },
    }


def counterevidence(occurrences: list[Mapping[str, Any]]) -> dict[str, Any]:
    outcomes = Counter(str(item.get("result_status") or "unknown") for item in occurrences)
    has_positive = outcomes.get("succeeded", 0) > 0
    has_negative = any(outcomes.get(key, 0) > 0 for key in ("failed", "error", "timed_out", "timeout"))
    unknown = outcomes.get("unknown", 0) > 0
    if has_positive and has_negative:
        status = "conflicting"
    elif unknown:
        status = "unknown"
    else:
        status = "no_negative_observation" if has_positive else "unknown"
    refs = [ref for item in occurrences for ref in item.get("evidence_refs", [])]
    return {
        "status": status,
        "outcome_counts": dict(sorted(outcomes.items())),
        "negative_evidence_refs": safe_evidence_refs(
            ref for item in occurrences if item.get("result_status") in {"failed", "error", "timed_out", "timeout"} for ref in item.get("evidence_refs", [])
        ),
        "unknown_evidence_refs": safe_evidence_refs(
            ref for item in occurrences if item.get("result_status") == "unknown" for ref in item.get("evidence_refs", [])
        ),
        "all_evidence_refs": safe_evidence_refs(refs),
        "admission_rule": "unknown or conflicting outcomes cannot become an accepted candidate",
    }


def recurrence(occurrences: list[Mapping[str, Any]], minimum_sessions: int, minimum_occurrences: int) -> dict[str, Any]:
    session_refs = sorted({str(item["session_ref"]) for item in occurrences})
    source_binding_refs = sorted({str(item["source_binding_ref"]) for item in occurrences})
    episode_refs = sorted(
        {
            json.dumps(item["episode_ref"], sort_keys=True, separators=(",", ":"))
            for item in occurrences
        }
    )
    if (
        len(session_refs) > MAX_CANDIDATES
        or len(source_binding_refs) > MAX_CANDIDATES
    ):
        raise MetabolismError("recurrence_reference_limit_exceeded")
    count = len(occurrences)
    distinct_sessions = len(session_refs)
    distinct_source_bindings = len(source_binding_refs)
    if (
        distinct_sessions >= minimum_sessions
        and distinct_source_bindings >= minimum_sessions
        and count >= minimum_occurrences
    ):
        readiness = "review_ready"
        reason = "cross_session_and_occurrence_thresholds_met"
    elif distinct_sessions < minimum_sessions:
        readiness = "watch"
        reason = "same_session_repetition_is_not_recurrence"
    elif distinct_source_bindings < minimum_sessions:
        readiness = "insufficient_evidence"
        reason = "source_binding_diversity_not_met"
    else:
        readiness = "insufficient_evidence"
        reason = "occurrence_threshold_not_met"
    return {
        "status": readiness,
        "occurrence_count": count,
        "distinct_session_count": distinct_sessions,
        "distinct_source_binding_count": distinct_source_bindings,
        "distinct_episode_count": len(episode_refs),
        "session_refs": session_refs,
        "source_binding_refs": source_binding_refs,
        "thresholds": {
            "minimum_distinct_sessions": minimum_sessions,
            "minimum_occurrences": minimum_occurrences,
        },
        "reason": reason,
    }


def make_candidate(
    key: str,
    occurrences: list[Mapping[str, Any]],
    *,
    minimum_sessions: int,
    minimum_occurrences: int,
) -> dict[str, Any]:
    first = occurrences[0]
    recurrence_data = recurrence(occurrences, minimum_sessions, minimum_occurrences)
    counter = counterevidence(occurrences)
    if counter["status"] in {"unknown", "conflicting"}:
        recurrence_data["status"] = "insufficient_evidence"
        recurrence_data["reason"] = f"counterevidence_{counter['status']}"
    candidate_seed = {
        "key": key,
        "operation_digest": first["operation_digest"],
        "signal": first["signal"],
        "session_refs": recurrence_data["session_refs"],
    }
    candidate_id = f"experience-candidate:{stable_digest(candidate_seed)[:24]}"
    profile_refs = sorted({str(item["profile_ref"]) for item in occurrences})
    if len(profile_refs) > MAX_CANDIDATES:
        raise MetabolismError("candidate_profile_reference_limit_exceeded")
    raw_review_refs = [item.get("review_ref") for item in occurrences]
    canonical_review_refs = {
        _ref_key(ref)
        for ref in raw_review_refs
        if isinstance(ref, Mapping) and safe_logical_ref(ref) is not None
    }
    review_refs = safe_evidence_refs(raw_review_refs)
    episode_count = len({json.dumps(item["episode_ref"], sort_keys=True) for item in occurrences})
    evidence_refs = safe_evidence_refs(ref for item in occurrences for ref in item.get("evidence_refs", []))
    occurrence_rows = [
        {
            "session_ref": item["session_ref"],
            "source_binding_ref": item["source_binding_ref"],
            "profile_ref": item["profile_ref"],
            "episode_ref": item["episode_ref"],
            "review_ref": item["review_ref"],
            "result_status": item["result_status"],
            "evidence_status": item["evidence_status"],
            "span_seconds": item["span_seconds"],
            "evidence_refs": item["evidence_refs"],
        }
        for item in occurrences[:MAX_EVIDENCE_REFS]
    ]
    omitted_occurrences = occurrences[MAX_EVIDENCE_REFS:]
    omitted_occurrence_digest = (
        f"sha256:{stable_digest([
            {
                "key": item.get("key"),
                "session_ref": item.get("session_ref"),
                "profile_ref": item.get("profile_ref"),
                "episode_ref": item.get("episode_ref"),
                "evidence_refs": item.get("evidence_refs"),
            }
            for item in omitted_occurrences
        ])}"
        if omitted_occurrences
        else None
    )
    if omitted_occurrences:
        recurrence_data["status"] = "insufficient_evidence"
        recurrence_data["reason"] = "occurrence_evidence_truncated"
    blocked = (
        recurrence_data["status"] != "review_ready"
        or counter["status"] in {"unknown", "conflicting"}
        or bool(omitted_occurrences)
    )
    candidate = {
        "candidate_id": candidate_id,
        "schema_version": SCHEMA_VERSION,
        "status": "insufficient_evidence" if blocked else "candidate",
        "motif": {
            "signal": first["signal"],
            "stage": first["stage"],
            "tool": first["tool"],
            "operation_shape": first["operation_shape"],
            "operation_digest": first["operation_digest"],
            "key_is_content_free": True,
        },
        "recurrence": recurrence_data,
        "evidence_diversity": {
            "distinct_profile_count": len(profile_refs),
            "distinct_session_count": recurrence_data["distinct_session_count"],
            "distinct_source_binding_count": recurrence_data["distinct_source_binding_count"],
            "distinct_episode_count": recurrence_data["distinct_episode_count"],
            "profile_refs": profile_refs,
            "source_binding_refs": recurrence_data["source_binding_refs"],
            "occurrence_rows": occurrence_rows,
            "total_occurrence_count": len(occurrences),
            "emitted_occurrence_count": len(occurrence_rows),
            "omitted_occurrence_count": len(omitted_occurrences),
            "omitted_occurrence_digest": omitted_occurrence_digest,
            "truncated": bool(omitted_occurrences),
        },
        "counterevidence": counter,
        "alternative_explanations": [
            "task_mix_or_repository_state",
            "association_does_not_establish_causality",
        ],
        "causal_attribution": {
            "status": "not_established",
            "claim": "association_only",
            "paired_comparison": {"status": "missing", "evidence_refs": []},
            "held_out_comparison": {"status": "missing", "evidence_refs": []},
            "ablation_comparison": {"status": "missing", "evidence_refs": []},
            "confounders": ["workload", "repository_state", "model", "environment", "operator", "route"],
        },
        "approval_sensitivity": {
            "status": "pending",
            "review_eligibility_is_not_owner_acceptance": True,
            "removing_reviewed_status_must_remove_the_observation_from_recurrence": True,
        },
        "trajectory_cost": trajectory_cost(occurrences, episode_count),
        "provenance": {
            "source_schema": PROFILE_SCHEMA_VERSION,
            "source_ref_scheme": REF_SCHEME,
            "profile_refs": profile_refs,
            "review_refs": review_refs,
            "review_ref_count": len(canonical_review_refs),
            "review_refs_truncated": len(canonical_review_refs) > MAX_EVIDENCE_REFS,
            "evidence_refs": evidence_refs,
            "raw_transcript_scanned": False,
            "raw_transcript_refs_emitted": False,
            "source_authority": "generated_stage_profile_only",
        },
        "privacy": {
            "policy": "normalized_shapes_digests_and_hashed_logical_refs_only",
            "raw_content_emitted": False,
            "raw_paths_emitted": False,
            "sensitive_fields_emitted": False,
            "bounded_refs": True,
        },
        "lifecycle": {
            "state": "candidate",
            "history": [],
            "history_digest": _history_digest([]),
            "reversible": True,
            "adoption_allowed": False,
            "required_order": LIFECYCLE_REQUIRED_ORDER,
            "base_digest": "",
        },
        "routes": {
            "owner": {"owner": "aoa-session-memory", "status": "candidate"},
            "review": {"owner": "reviewer-office", "status": "pending"},
            "eval": {"owner": "aoa-evals", "status": "blocked_until_review"},
            "shadow": {"owner": "abyss-stack", "status": "blocked_until_eval"},
            "adoption": {"owner": "aoa-session-memory", "status": "blocked_until_owner_acceptance"},
            "rejection": {"owner": "aoa-session-memory", "status": "available"},
        },
        "evaluation_requirements": {
            "verdict": None,
            "independent_review_required": True,
            "comparisons_required": ["paired", "held_out", "ablation"],
            "live_shadow_required": True,
            "live_canary_required_before_benefit_claim": True,
        },
        "next_route": "reviewer-office" if recurrence_data["status"] == "review_ready" else "aoa-session-memory:manual-review",
        "advisory_observation": {
            "schema_version": OBSERVATION_SCHEMA_VERSION,
            "component_ref": "component:aoa-session-memory:experience-metabolism",
            "owner_repo": "aoa-session-memory",
            "category": "repeat_pattern",
            "signal": "experience_motif_candidate",
            "source_inputs": [PROFILE_SCHEMA_VERSION],
            "evidence_refs": evidence_refs,
            "attributes": {
                "candidate_id": candidate_id,
                "signal": first["signal"],
                "operation_digest": first["operation_digest"],
                "distinct_session_count": recurrence_data["distinct_session_count"],
                "occurrence_count": recurrence_data["occurrence_count"],
                "readiness": recurrence_data["status"],
            },
            "notes": "Advisory observation only; no semantic adoption or policy is implied.",
        },
    }
    candidate["lifecycle"]["base_digest"] = _candidate_base_digest(candidate)
    return candidate


def build_shadow_measurement(
    baseline_profile: Mapping[str, Any],
    shadow_profile: Mapping[str, Any],
    *,
    comparison_mode: str = "descriptive_unpaired",
    comparison_refs: Iterable[Any] = (),
) -> dict[str, Any]:
    """Compare bounded measurements without issuing an eval or benefit verdict."""

    validate_profile_input(baseline_profile)
    validate_profile_input(shadow_profile)
    if comparison_mode not in {"descriptive_unpaired", "paired", "held_out", "ablation"}:
        raise MetabolismError("comparison_mode_invalid")
    baseline = profile_metrics(baseline_profile)
    shadow = profile_metrics(shadow_profile)
    if baseline["coverage_status"] != "complete" or shadow["coverage_status"] != "complete":
        raise MetabolismError("shadow_profile_coverage_incomplete")
    comparison_evidence, refs = _normalize_shadow_comparisons(comparison_mode, comparison_refs)
    if comparison_mode != "descriptive_unpaired":
        baseline_profile_ref = baseline["profile_ref"]
        shadow_profile_ref = shadow["profile_ref"]
        expected_source_binding_refs = sorted(
            set(baseline["source_binding_refs"]) | set(shadow["source_binding_refs"])
        )
        packets = comparison_evidence[comparison_mode]
        if not packets:
            raise MetabolismError("comparison_packet_required")
        for packet in packets:
            if (
                packet["baseline_ref"] != baseline_profile_ref
                or packet["shadow_ref"] != shadow_profile_ref
                or packet["source_binding_refs"] != expected_source_binding_refs
            ):
                raise MetabolismError("comparison_profile_binding_mismatch")
    metric_names = (
        "median_episode_wall_seconds",
        "median_residual_unknown_seconds",
        "unknown_episode_rate",
        "rerun_after_fix_rate",
    )
    components: dict[str, dict[str, Any]] = {}
    for name in metric_names:
        before = baseline.get(name)
        after = shadow.get(name)
        delta = round(float(before) - float(after), 6) if isinstance(before, (int, float)) and isinstance(after, (int, float)) else None
        components[name] = {
            "baseline": before,
            "shadow": after,
            "directional_delta_baseline_minus_shadow": delta,
            "lower_is_better": True,
            "status": "observed" if delta is not None else "unknown",
        }
    comparable = comparison_mode in {"paired", "held_out", "ablation"} and bool(comparison_evidence[comparison_mode])
    return {
        "schema_version": "experience_shadow_measurement_v1",
        "mode": "shadow_only",
        "comparison_mode": comparison_mode,
        "comparison_refs": refs,
        "comparison_evidence": comparison_evidence,
        "baseline": baseline,
        "shadow": shadow,
        "trajectory_cost": {
            "baseline": {
                "wall_clock_seconds": baseline.get("total_episode_wall_seconds"),
                "residual_unknown_seconds": baseline.get("total_residual_unknown_seconds"),
            },
            "shadow": {
                "wall_clock_seconds": shadow.get("total_episode_wall_seconds"),
                "residual_unknown_seconds": shadow.get("total_residual_unknown_seconds"),
            },
            "activity_counts_are_not_benefit": True,
        },
        "net_benefit": {
            "status": "descriptive_directional_delta" if comparable else "not_admitted",
            "claim": "not_established",
            "scalar": None,
            "components": components,
            "reason": "A vector of baseline-relative measurements is retained; owner/eval verdict remains separate.",
        },
        "admission": {
            "comparable": comparable,
            "accepted_eval": False,
            "owner_acceptance": False,
            "live_canary": False,
        },
    }


LIFECYCLE_REQUIRED_ORDER = [
    "review_verdict",
    "eval_verdict",
    "shadow_result",
    "owner_acceptance",
    "adoption",
]
RECEIPT_INTEGRITIES = {"verified"}
RECEIPT_STATUSES = {"accepted", "rejected", "superseded", "rolled_back"}
ROUTE_OWNERS = {
    "owner": "aoa-session-memory",
    "review": "reviewer-office",
    "eval": "aoa-evals",
    "shadow": "abyss-stack",
    "adoption": "aoa-session-memory",
    "rejection": "aoa-session-memory",
}


def _ref_key(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _normalize_ref_group(value: Any) -> list[dict[str, str]]:
    """Normalize structured lifecycle references and fail closed on every member."""

    if value is None:
        return []
    if isinstance(value, list):
        values = value
    elif isinstance(value, Mapping):
        values = [value]
    else:
        raise MetabolismError("lifecycle_reference_invalid")
    refs: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in values:
        if not isinstance(item, Mapping):
            raise MetabolismError("lifecycle_reference_invalid")
        ref = safe_logical_ref(item)
        if ref is None:
            raise MetabolismError("lifecycle_reference_invalid")
        key = _ref_key(ref)
        if key in seen:
            raise MetabolismError("lifecycle_reference_duplicate")
        seen.add(key)
        refs.append(ref)
        if len(refs) > MAX_EVIDENCE_REFS:
            raise MetabolismError("lifecycle_reference_limit_exceeded")
    return refs


def _strict_ref_group(value: Any, error: str) -> list[dict[str, str]]:
    try:
        refs = _normalize_ref_group(value)
    except MetabolismError as exc:
        raise MetabolismError(error) from exc
    if not refs:
        raise MetabolismError(error)
    return refs


def _receipt_unsigned_digest(
    *,
    owner_repo: str,
    receipt_type: str,
    candidate_id: str,
    base_digest: str,
    object_ref: Mapping[str, Any],
    verification_ref: Mapping[str, Any],
    event_kind: str,
    event_status: str,
    evidence_digest: str,
) -> str:
    payload = {
        "owner_repo": owner_repo,
        "receipt_type": receipt_type,
        "candidate_id": candidate_id,
        "base_digest": base_digest,
        "object_ref": object_ref,
        "verification_ref": verification_ref,
        "event_kind": event_kind,
        "event_status": event_status,
        "evidence_digest": evidence_digest,
    }
    return f"sha256:{stable_digest(payload)}"


def _evidence_digest(evidence: Mapping[str, Any]) -> str:
    return f"sha256:{stable_digest(evidence)}"


def _normalize_receipt(
    value: Any,
    *,
    kind: str | None = None,
    expected_status: str | None = None,
    expected_candidate_id: str | None = None,
    expected_base_digest: str | None = None,
) -> dict[str, Any]:
    """Admit only typed, integrity-bearing receipts and hash their identity."""

    if not isinstance(value, Mapping):
        raise MetabolismError("lifecycle_receipt_required")
    if set(value) != {
        "owner_repo", "receipt_type", "candidate_id", "base_digest",
        "object_ref", "verification_ref", "event_kind", "event_status",
        "evidence_digest", "digest", "integrity",
    }:
        raise MetabolismError("lifecycle_receipt_invalid")
    owner = safe_word(value.get("owner_repo"), fallback="unknown")
    receipt_type = safe_word(value.get("receipt_type"), fallback="unknown")
    candidate_id = value.get("candidate_id")
    base_digest = valid_operation_digest(value.get("base_digest"))
    digest = valid_operation_digest(value.get("digest"))
    integrity = safe_word(value.get("integrity"), fallback="unknown")
    object_ref_value = value.get("object_ref")
    object_ref = safe_logical_ref(object_ref_value) if isinstance(object_ref_value, Mapping) else None
    verification_ref_value = value.get("verification_ref")
    verification_ref = (
        safe_logical_ref(verification_ref_value)
        if isinstance(verification_ref_value, Mapping)
        else None
    )
    event_kind = safe_word(value.get("event_kind"), fallback="unknown")
    event_status = safe_word(value.get("event_status"), fallback="unknown")
    evidence_digest = valid_operation_digest(value.get("evidence_digest"))
    if (
        owner == "unknown"
        or receipt_type == "unknown"
        or not isinstance(candidate_id, str)
        or not SAFE_CANDIDATE_ID.fullmatch(candidate_id)
        or base_digest is None
        or digest is None
        or integrity not in RECEIPT_INTEGRITIES
        or object_ref is None
        or verification_ref is None
        or event_kind not in EXPECTED_RECEIPT_OWNERS
        or event_status not in RECEIPT_STATUSES
        or evidence_digest is None
    ):
        raise MetabolismError("lifecycle_receipt_invalid")
    if expected_candidate_id is not None and candidate_id != expected_candidate_id:
        raise MetabolismError("lifecycle_receipt_candidate_mismatch")
    if expected_base_digest is not None and base_digest != expected_base_digest:
        raise MetabolismError("lifecycle_receipt_base_digest_mismatch")
    if kind is not None:
        if kind not in EXPECTED_RECEIPT_OWNERS or owner != EXPECTED_RECEIPT_OWNERS[kind]:
            raise MetabolismError("lifecycle_receipt_owner_invalid")
        if receipt_type != EXPECTED_RECEIPT_TYPES[kind]:
            raise MetabolismError("lifecycle_receipt_type_invalid")
    if kind is not None and event_kind != kind:
        raise MetabolismError("lifecycle_receipt_event_kind_mismatch")
    if expected_status is not None and event_status != expected_status:
        raise MetabolismError("lifecycle_receipt_event_status_mismatch")
    if digest != _receipt_unsigned_digest(
        owner_repo=owner,
        receipt_type=receipt_type,
        candidate_id=candidate_id,
        base_digest=base_digest,
        object_ref=object_ref,
        verification_ref=verification_ref,
        event_kind=event_kind,
        event_status=event_status,
        evidence_digest=evidence_digest,
    ):
        raise MetabolismError("lifecycle_receipt_digest_invalid")
    return {
        "owner_repo": owner,
        "receipt_type": receipt_type,
        "candidate_id": candidate_id,
        "base_digest": base_digest,
        "object_ref": object_ref,
        "verification_ref": verification_ref,
        "event_kind": event_kind,
        "event_status": event_status,
        "evidence_digest": evidence_digest,
        "digest": digest,
        "integrity": "verified",
    }


def _validate_receipt_evidence_binding(
    receipt: Mapping[str, Any],
    evidence: Mapping[str, Any],
) -> None:
    if receipt.get("evidence_digest") != _evidence_digest(evidence):
        raise MetabolismError("lifecycle_receipt_evidence_mismatch")


def _normalize_comparison_packet(value: Any, expected_kind: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != COMPARISON_PACKET_KEYS:
        raise MetabolismError("comparison_packet_invalid")
    if value.get("comparison_type") != expected_kind:
        raise MetabolismError("comparison_packet_kind_mismatch")
    candidate_id = value.get("candidate_id")
    if not isinstance(candidate_id, str) or not SAFE_CANDIDATE_ID.fullmatch(candidate_id):
        raise MetabolismError("comparison_packet_candidate_invalid")
    source_binding_refs = value.get("source_binding_refs")
    if (
        not isinstance(source_binding_refs, list)
        or not source_binding_refs
        or len(source_binding_refs) > 256
        or not all(isinstance(item, str) and SAFE_DIGEST.fullmatch(item) for item in source_binding_refs)
        or source_binding_refs != sorted(set(source_binding_refs))
    ):
        raise MetabolismError("comparison_packet_source_binding_invalid")
    refs: dict[str, dict[str, str]] = {}
    for key in ("subject_ref", "baseline_ref", "shadow_ref", "context_ref", "result_ref"):
        ref = safe_logical_ref(value.get(key))
        if ref is None:
            raise MetabolismError("comparison_packet_ref_invalid")
        refs[key] = ref
    if _ref_key(refs["baseline_ref"]) == _ref_key(refs["shadow_ref"]):
        raise MetabolismError("comparison_packet_baseline_shadow_identical")
    source_fingerprint = valid_operation_digest(value.get("source_fingerprint"))
    evidence_digest = valid_operation_digest(value.get("evidence_digest"))
    numeric_result = number_value(value.get("numeric_result"))
    result_status = safe_text(value.get("result_status"))
    if (
        source_fingerprint is None
        or evidence_digest is None
        or numeric_result is None
        or not math.isfinite(numeric_result)
        or result_status not in COMPARISON_RESULT_STATUSES
    ):
        raise MetabolismError("comparison_packet_measurement_invalid")
    return {
        "comparison_type": expected_kind,
        "candidate_id": candidate_id,
        "source_binding_refs": source_binding_refs,
        **refs,
        "source_fingerprint": source_fingerprint,
        "evidence_digest": evidence_digest,
        "numeric_result": numeric_result,
        "result_status": result_status,
    }


def _normalize_comparison_groups(
    value: Any,
    *,
    expected_candidate_id: str | None = None,
    expected_source_binding_refs: list[str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(value, Mapping) or set(value) != set(COMPARISON_KINDS):
        raise MetabolismError("comparison_groups_invalid")
    groups: dict[str, list[dict[str, Any]]] = {}
    packets: list[dict[str, Any]] = []
    for kind in COMPARISON_KINDS:
        raw_values = value.get(kind)
        if (
            not isinstance(raw_values, list)
            or not raw_values
            or len(raw_values) > MAX_EVIDENCE_REFS
        ):
            raise MetabolismError("comparison_group_missing")
        normalized = [_normalize_comparison_packet(item, kind) for item in raw_values]
        if len({_ref_key(item["result_ref"]) for item in normalized}) != len(normalized):
            raise MetabolismError("comparison_group_duplicate_result")
        groups[kind] = normalized
        packets.extend(normalized)
    fingerprints = {item["source_fingerprint"] for item in packets}
    contexts = {_ref_key(item["context_ref"]) for item in packets}
    subjects = {_ref_key(item["subject_ref"]) for item in packets}
    candidate_ids = {item["candidate_id"] for item in packets}
    source_bindings = {
        tuple(item["source_binding_refs"])
        for item in packets
    }
    if len(fingerprints) != 1:
        raise MetabolismError("comparison_source_fingerprint_mismatch")
    if len(contexts) != 1:
        raise MetabolismError("comparison_context_mismatch")
    if len(subjects) != 1:
        raise MetabolismError("comparison_subject_mismatch")
    if len(candidate_ids) != 1:
        raise MetabolismError("comparison_candidate_mismatch")
    if len(source_bindings) != 1:
        raise MetabolismError("comparison_source_binding_mismatch")
    result_refs = [
        _ref_key(item["result_ref"])
        for item in packets
    ]
    evidence_digests = [item["evidence_digest"] for item in packets]
    if len(set(result_refs)) != len(result_refs):
        raise MetabolismError("comparison_cross_mode_result_duplicate")
    if len(set(evidence_digests)) != len(evidence_digests):
        raise MetabolismError("comparison_cross_mode_evidence_duplicate")
    if expected_candidate_id is not None and candidate_ids != {expected_candidate_id}:
        raise MetabolismError("comparison_candidate_binding_mismatch")
    if expected_source_binding_refs is not None and source_bindings != {tuple(expected_source_binding_refs)}:
        raise MetabolismError("comparison_source_binding_mismatch")
    return groups


def _normalize_shadow_metric(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {
        "ref", "profile_ref", "source_binding_refs", "wall_clock_seconds",
        "residual_unknown_seconds", "coverage_status",
    }:
        raise MetabolismError("shadow_metric_invalid")
    ref = safe_logical_ref(value.get("ref"))
    profile_ref = safe_logical_ref(value.get("profile_ref"))
    source_binding_refs = value.get("source_binding_refs")
    coverage_status = safe_word(value.get("coverage_status"))
    wall_clock_seconds = (
        number_value(value.get("wall_clock_seconds"))
        if value.get("wall_clock_seconds") is not None
        else None
    )
    residual_unknown_seconds = (
        number_value(value.get("residual_unknown_seconds"))
        if value.get("residual_unknown_seconds") is not None
        else None
    )
    if (
        ref is None
        or profile_ref is None
        or (
            not isinstance(source_binding_refs, list)
            or not source_binding_refs
            or len(source_binding_refs) > MAX_CANDIDATES
            or source_binding_refs != sorted(set(source_binding_refs))
            or not all(
                isinstance(item, str) and SAFE_DIGEST.fullmatch(item)
                for item in source_binding_refs
            )
        )
        or coverage_status not in SHADOW_COVERAGE_STATUSES
        or (value.get("wall_clock_seconds") is not None and wall_clock_seconds is None)
        or (value.get("residual_unknown_seconds") is not None and residual_unknown_seconds is None)
        or (
            coverage_status == "complete"
            and (wall_clock_seconds is None or residual_unknown_seconds is None)
        )
    ):
        raise MetabolismError("shadow_metric_invalid")
    return {
        "ref": ref,
        "profile_ref": profile_ref,
        "source_binding_refs": source_binding_refs,
        "wall_clock_seconds": wall_clock_seconds,
        "residual_unknown_seconds": residual_unknown_seconds,
        "coverage_status": coverage_status,
    }


def _normalize_shadow_measurement(
    value: Any,
    *,
    candidate: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Admit a typed, immutable shadow result; metrics remain descriptive."""

    required = {
        "schema_version", "measurement_digest", "candidate_id",
        "candidate_source_binding_refs", "comparison_source_binding_refs",
        "comparison_mode", "baseline", "shadow", "net_benefit", "trajectory_cost", "admission",
    }
    if not isinstance(value, Mapping) or set(value) != required:
        raise MetabolismError("shadow_measurement_required")
    if value.get("schema_version") != "experience_shadow_measurement_binding_v1":
        raise MetabolismError("shadow_measurement_schema_invalid")
    candidate_id = value.get("candidate_id")
    if not isinstance(candidate_id, str) or not SAFE_CANDIDATE_ID.fullmatch(candidate_id):
        raise MetabolismError("shadow_measurement_candidate_invalid")
    if candidate is not None and candidate_id != candidate.get("candidate_id"):
        raise MetabolismError("shadow_measurement_candidate_mismatch")
    candidate_source_binding_refs = value.get("candidate_source_binding_refs")
    comparison_source_binding_refs = value.get("comparison_source_binding_refs")
    for refs, error, allow_empty in (
        (candidate_source_binding_refs, "shadow_measurement_candidate_source_binding_invalid", candidate is None),
        (comparison_source_binding_refs, "shadow_measurement_comparison_source_binding_invalid", False),
    ):
        if (
            not isinstance(refs, list)
            or len(refs) > MAX_CANDIDATES
            or (not allow_empty and not refs)
            or not all(isinstance(item, str) and SAFE_DIGEST.fullmatch(item) for item in refs)
            or refs != sorted(set(refs))
        ):
            raise MetabolismError(error)
    if candidate is not None:
        recurrence_data = candidate.get("recurrence")
        expected_sources = (
            recurrence_data.get("source_binding_refs")
            if isinstance(recurrence_data, Mapping)
            else None
        )
        if candidate_source_binding_refs != expected_sources:
            raise MetabolismError("shadow_measurement_source_binding_mismatch")
    comparison_mode = value.get("comparison_mode")
    if comparison_mode not in SHADOW_COMPARISON_MODES:
        raise MetabolismError("shadow_measurement_comparison_mode_invalid")
    baseline = _normalize_shadow_metric(value.get("baseline"))
    shadow = _normalize_shadow_metric(value.get("shadow"))
    if (
        _ref_key(baseline["ref"]) == _ref_key(shadow["ref"])
        or _ref_key(baseline["profile_ref"]) == _ref_key(shadow["profile_ref"])
    ):
        raise MetabolismError("shadow_measurement_baseline_shadow_identical")
    combined_source_binding_refs = sorted(
        set(baseline["source_binding_refs"]) | set(shadow["source_binding_refs"])
    )
    if comparison_source_binding_refs != combined_source_binding_refs:
        raise MetabolismError("shadow_measurement_source_binding_mismatch")

    net_benefit_value = value.get("net_benefit")
    if not isinstance(net_benefit_value, Mapping) or set(net_benefit_value) != {
        "ref", "status", "claim", "evidence_digest",
    }:
        raise MetabolismError("shadow_net_benefit_invalid")
    net_ref = safe_logical_ref(net_benefit_value.get("ref"))
    net_status = safe_word(net_benefit_value.get("status"))
    net_evidence_digest = valid_operation_digest(net_benefit_value.get("evidence_digest"))
    if (
        net_ref is None
        or net_status not in {"descriptive_directional_delta", "not_admitted"}
        or net_benefit_value.get("claim") != "not_established"
        or net_evidence_digest is None
    ):
        raise MetabolismError("shadow_net_benefit_invalid")
    net_benefit = {
        "ref": net_ref,
        "status": net_status,
        "claim": "not_established",
        "evidence_digest": net_evidence_digest,
    }

    trajectory_value = value.get("trajectory_cost")
    if not isinstance(trajectory_value, Mapping) or set(trajectory_value) != {
        "baseline_ref", "shadow_ref", "activity_counts_are_not_benefit",
    }:
        raise MetabolismError("shadow_trajectory_cost_invalid")
    trajectory_baseline_ref = safe_logical_ref(trajectory_value.get("baseline_ref"))
    trajectory_shadow_ref = safe_logical_ref(trajectory_value.get("shadow_ref"))
    if (
        trajectory_baseline_ref is None
        or trajectory_shadow_ref is None
        or trajectory_baseline_ref != baseline["ref"]
        or trajectory_shadow_ref != shadow["ref"]
        or trajectory_value.get("activity_counts_are_not_benefit") is not True
    ):
        raise MetabolismError("shadow_trajectory_cost_invalid")
    trajectory_cost = {
        "baseline_ref": trajectory_baseline_ref,
        "shadow_ref": trajectory_shadow_ref,
        "activity_counts_are_not_benefit": True,
    }

    admission_value = value.get("admission")
    if not isinstance(admission_value, Mapping) or set(admission_value) != {
        "comparable", "accepted_eval", "owner_acceptance", "live_canary",
    } or any(not isinstance(admission_value.get(key), bool) for key in admission_value):
        raise MetabolismError("shadow_admission_invalid")
    comparable = admission_value["comparable"]
    if (
        not comparable
        or admission_value["accepted_eval"] is not False
        or admission_value["owner_acceptance"] is not False
        or admission_value["live_canary"] is not False
        or net_status != "descriptive_directional_delta"
    ):
        raise MetabolismError("shadow_admission_not_comparable")
    admission = {
        "comparable": True,
        "accepted_eval": False,
        "owner_acceptance": False,
        "live_canary": False,
    }
    unsigned = {
        "schema_version": "experience_shadow_measurement_binding_v1",
        "candidate_id": candidate_id,
        "candidate_source_binding_refs": candidate_source_binding_refs,
        "comparison_source_binding_refs": comparison_source_binding_refs,
        "comparison_mode": comparison_mode,
        "baseline": baseline,
        "shadow": shadow,
        "net_benefit": net_benefit,
        "trajectory_cost": trajectory_cost,
        "admission": admission,
    }
    measurement_digest = valid_operation_digest(value.get("measurement_digest"))
    expected_digest = f"sha256:{stable_digest(unsigned)}"
    if measurement_digest != expected_digest:
        raise MetabolismError("shadow_measurement_digest_invalid")
    return {"measurement_digest": measurement_digest, **unsigned}


def _normalize_canary_evidence(
    value: Any,
    *,
    candidate: Mapping[str, Any],
) -> dict[str, Any]:
    """Require an identity-bound, externally verifiable live-canary packet."""

    required = {
        "schema_version", "candidate_id", "base_digest", "runtime_ref",
        "execution_ref", "treatment_ref", "baseline_ref", "shadow_ref",
        "result_ref", "rollback_ref", "verification_ref", "source_binding_refs",
        "shadow_measurement_digest", "status", "coverage_status",
    }
    if not isinstance(value, Mapping) or set(value) != required:
        raise MetabolismError("live_canary_evidence_required")
    lifecycle = candidate.get("lifecycle")
    expected_base_digest = lifecycle.get("base_digest") if isinstance(lifecycle, Mapping) else None
    if (
        value.get("schema_version") != "experience_live_canary_binding_v1"
        or value.get("candidate_id") != candidate.get("candidate_id")
        or value.get("base_digest") != expected_base_digest
        or value.get("status") != "completed"
        or value.get("coverage_status") != "complete"
    ):
        raise MetabolismError("live_canary_evidence_identity_invalid")
    refs: dict[str, dict[str, str]] = {}
    for key in (
        "runtime_ref", "execution_ref", "treatment_ref", "baseline_ref",
        "shadow_ref", "result_ref", "rollback_ref", "verification_ref",
    ):
        ref = safe_logical_ref(value.get(key))
        if ref is None or ref != value.get(key):
            raise MetabolismError("live_canary_evidence_ref_invalid")
        refs[key] = ref
    if len({_ref_key(ref) for ref in refs.values()}) != len(refs):
        raise MetabolismError("live_canary_evidence_ref_duplicate")
    source_binding_refs = value.get("source_binding_refs")
    if (
        not isinstance(source_binding_refs, list)
        or not source_binding_refs
        or len(source_binding_refs) > MAX_CANDIDATES
        or source_binding_refs != sorted(set(source_binding_refs))
        or not all(isinstance(item, str) and SAFE_DIGEST.fullmatch(item) for item in source_binding_refs)
    ):
        raise MetabolismError("live_canary_evidence_source_binding_invalid")
    shadow_measurement_digest = valid_operation_digest(value.get("shadow_measurement_digest"))
    requirements = candidate.get("evaluation_requirements")
    measurement = requirements.get("shadow_measurement") if isinstance(requirements, Mapping) else None
    measurement_baseline = measurement.get("baseline") if isinstance(measurement, Mapping) else None
    measurement_shadow = measurement.get("shadow") if isinstance(measurement, Mapping) else None
    if (
        shadow_measurement_digest is None
        or not isinstance(measurement, Mapping)
        or not isinstance(measurement_baseline, Mapping)
        or not isinstance(measurement_shadow, Mapping)
        or shadow_measurement_digest != measurement.get("measurement_digest")
        or refs["baseline_ref"] != measurement_baseline.get("ref")
        or refs["shadow_ref"] != measurement_shadow.get("ref")
    ):
        raise MetabolismError("live_canary_evidence_measurement_mismatch")
    expected_canary_sources = measurement.get("candidate_source_binding_refs")
    if source_binding_refs != expected_canary_sources:
        raise MetabolismError("live_canary_evidence_source_binding_mismatch")
    return {
        "schema_version": "experience_live_canary_binding_v1",
        "candidate_id": candidate["candidate_id"],
        "base_digest": expected_base_digest,
        **refs,
        "source_binding_refs": source_binding_refs,
        "shadow_measurement_digest": shadow_measurement_digest,
        "status": "completed",
        "coverage_status": "complete",
    }


def _comparison_ref_map(groups: Mapping[str, list[Mapping[str, Any]]]) -> dict[str, list[dict[str, str]]]:
    return {
        kind: [dict(packet["result_ref"]) for packet in groups[kind]]
        for kind in COMPARISON_KINDS
    }


def _normalize_shadow_comparisons(
    comparison_mode: str,
    comparison_refs: Any,
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, str]]]:
    groups: dict[str, list[dict[str, Any]]] = {kind: [] for kind in COMPARISON_KINDS}
    if comparison_mode == "descriptive_unpaired":
        values = comparison_refs if isinstance(comparison_refs, Iterable) and not isinstance(comparison_refs, (str, bytes, Mapping)) else []
        return groups, safe_comparison_refs(values)
    if isinstance(comparison_refs, Mapping):
        if set(comparison_refs) != {comparison_mode}:
            raise MetabolismError("comparison_packet_group_mismatch")
        raw_values = comparison_refs.get(comparison_mode)
    else:
        raw_values = comparison_refs
    if isinstance(raw_values, Mapping):
        raw_values = [raw_values]
    if (
        not isinstance(raw_values, list)
        or not raw_values
        or len(raw_values) > MAX_EVIDENCE_REFS
    ):
        raise MetabolismError("comparison_packet_required")
    groups[comparison_mode] = [
        _normalize_comparison_packet(value, comparison_mode)
        for value in raw_values
    ]
    fingerprints = {packet["source_fingerprint"] for packet in groups[comparison_mode]}
    contexts = {_ref_key(packet["context_ref"]) for packet in groups[comparison_mode]}
    subjects = {_ref_key(packet["subject_ref"]) for packet in groups[comparison_mode]}
    candidate_ids = {packet["candidate_id"] for packet in groups[comparison_mode]}
    source_bindings = {tuple(packet["source_binding_refs"]) for packet in groups[comparison_mode]}
    if (
        len(fingerprints) != 1
        or len(contexts) != 1
        or len(subjects) != 1
        or len(candidate_ids) != 1
        or len(source_bindings) != 1
    ):
        raise MetabolismError("comparison_packet_identity_mismatch")
    return groups, [dict(packet["result_ref"]) for packet in groups[comparison_mode]]


def _event_evidence(
    kind: str,
    status: str,
    event: Mapping[str, Any],
    *,
    candidate: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize every gate reference into the lifecycle record itself."""

    if kind == "review_verdict" and status == "accepted":
        if event.get("independent_reviewer") is not True:
            raise MetabolismError("independent_review_required")
        return {"independent_reviewer": True}
    if kind == "eval_verdict" and status == "accepted":
        comparison_refs = event.get("comparison_refs")
        expected_candidate_id = candidate.get("candidate_id") if isinstance(candidate, Mapping) else None
        recurrence_data = candidate.get("recurrence") if isinstance(candidate, Mapping) else None
        expected_source_binding_refs = (
            recurrence_data.get("source_binding_refs")
            if isinstance(recurrence_data, Mapping)
            else None
        )
        try:
            normalized = _normalize_comparison_groups(
                comparison_refs,
                expected_candidate_id=expected_candidate_id,
                expected_source_binding_refs=expected_source_binding_refs,
            )
        except MetabolismError as exc:
            raise MetabolismError("paired_held_out_ablation_refs_required") from exc
        if not all(
            packet["result_status"] in {"passed", "accepted"}
            for packets in normalized.values()
            for packet in packets
        ):
            raise MetabolismError("comparison_results_not_accepted")
        return {
            "comparison_evidence": normalized,
            "comparison_refs": _comparison_ref_map(normalized),
        }
    if kind == "shadow_result" and status == "accepted":
        try:
            measurement = _normalize_shadow_measurement(event.get("shadow_measurement"), candidate=candidate)
        except MetabolismError as exc:
            raise MetabolismError("shadow_measurement_required") from exc
        if measurement["baseline"]["coverage_status"] != "complete" or measurement["shadow"]["coverage_status"] != "complete":
            raise MetabolismError("shadow_coverage_incomplete")
        return {
            "measurement": measurement,
            "measurement_refs": {
                "baseline": [measurement["baseline"]["ref"]],
                "shadow": [measurement["shadow"]["ref"]],
                "net_benefit": [measurement["net_benefit"]["ref"]],
            },
        }
    if kind == "owner_acceptance" and status == "accepted":
        normalized = {
            "owner": _strict_ref_group(event.get("owner_ref"), "owner_and_live_canary_refs_required"),
            "live_canary": _strict_ref_group(event.get("live_canary_ref"), "owner_and_live_canary_refs_required"),
        }
        if not all(normalized.values()):
            raise MetabolismError("owner_and_live_canary_refs_required")
        try:
            canary = _normalize_canary_evidence(event.get("canary_evidence"), candidate=candidate or {})
        except MetabolismError as exc:
            raise MetabolismError("live_canary_evidence_required") from exc
        return {"acceptance_refs": normalized, "canary_evidence": canary}
    if kind == "adoption" and status == "accepted":
        refs = _strict_ref_group(event.get("adoption_ref"), "adoption_ref_required")
        return {"adoption_refs": refs}
    if kind == "supersede":
        refs = _strict_ref_group(
            event.get("replacement_ref"),
            "supersession_requires_accepted_candidate_and_replacement",
        )
        return {"replacement_refs": refs}
    if kind == "rollback":
        refs = _strict_ref_group(
            event.get("rollback_ref"),
            "rollback_requires_accepted_candidate_and_rollback_ref",
        )
        return {"rollback_refs": refs}
    return {}


def _flatten_evidence_refs(evidence: Mapping[str, Any]) -> list[dict[str, str]]:
    values: list[Any] = []

    def collect(value: Any) -> None:
        if isinstance(value, Mapping):
            if value.get("scheme") == REF_SCHEME:
                values.append(value)
                return
            for nested in value.values():
                collect(nested)
        elif isinstance(value, list):
            for nested in value:
                collect(nested)

    collect(evidence)
    return safe_evidence_refs(values)


def _transition_target(state: str, kind: str, status: str) -> str | None:
    if kind == "review_verdict" and state == "candidate":
        return "eval_pending" if status == "accepted" else "rejected" if status == "rejected" else None
    if kind == "eval_verdict" and state == "eval_pending":
        return "shadow_pending" if status == "accepted" else "rejected" if status == "rejected" else None
    if kind == "shadow_result" and state == "shadow_pending":
        return "owner_review_pending" if status == "accepted" else "rejected" if status == "rejected" else None
    if kind == "owner_acceptance" and state == "owner_review_pending" and status == "accepted":
        return "accepted"
    if kind == "reject" and state in {"candidate", "eval_pending", "shadow_pending", "owner_review_pending"} and status == "rejected":
        return "rejected"
    if kind == "adoption" and state == "accepted" and status == "accepted":
        return "adopted"
    if kind == "supersede" and state in {"accepted", "adopted"} and status == "superseded":
        return "superseded"
    if kind == "rollback" and state in {"accepted", "adopted"} and status == "rolled_back":
        return "rolled_back"
    return None


def _record_digest(record: Mapping[str, Any]) -> str:
    unsigned = {key: value for key, value in record.items() if key != "chain_digest"}
    return f"sha256:{stable_digest(unsigned)}"


def _history_digest(history: list[Mapping[str, Any]]) -> str:
    return f"sha256:{stable_digest(history)}"


def _candidate_base(packet: Mapping[str, Any]) -> dict[str, Any]:
    return {key: packet.get(key) for key in LIFECYCLE_BASE_FIELDS}


def _candidate_base_digest(packet: Mapping[str, Any]) -> str:
    return f"sha256:{stable_digest(_candidate_base(packet))}"


def _canonical_ref_list(value: Any, *, allow_empty: bool = True) -> bool:
    if not isinstance(value, list) or len(value) > MAX_EVIDENCE_REFS:
        return False
    if not allow_empty and not value:
        return False
    try:
        normalized = _normalize_ref_group(value)
    except MetabolismError:
        return False
    return normalized == value and len({_ref_key(item) for item in value}) == len(value)


def _canonical_ref_session(value: Any) -> str | None:
    ref = safe_logical_ref(value)
    return ref.get("session") if ref is not None else None


def _validate_comparison_shape(value: Any, expected_kind: str | None = None) -> dict[str, Any]:
    try:
        return _normalize_comparison_packet(value, expected_kind or str(value.get("comparison_type")))
    except (AttributeError, MetabolismError) as exc:
        raise MetabolismError("comparison_packet_invalid") from exc


def _validate_trajectory_cost(value: Any) -> None:
    if not isinstance(value, Mapping) or set(value) != {
        "status", "episode_count", "operation_span_seconds", "residual_unknown_cost", "proxies",
    }:
        raise MetabolismError("candidate_trajectory_cost_invalid")
    if value.get("status") not in {"observed", "unknown"}:
        raise MetabolismError("candidate_trajectory_cost_invalid")
    episode_count = int_value(value.get("episode_count"))
    operation_span = value.get("operation_span_seconds")
    if episode_count is None or not isinstance(operation_span, Mapping) or set(operation_span) != {
        "total", "median", "known_occurrence_count", "unknown_occurrence_count",
    }:
        raise MetabolismError("candidate_trajectory_cost_invalid")
    for key in ("total", "median"):
        number = operation_span.get(key)
        if number is not None and number_value(number) != number:
            raise MetabolismError("candidate_trajectory_cost_invalid")
    for key in ("known_occurrence_count", "unknown_occurrence_count"):
        parsed_count = int_value(operation_span.get(key))
        if parsed_count is None or parsed_count != operation_span.get(key):
            raise MetabolismError("candidate_trajectory_cost_invalid")
    residual = value.get("residual_unknown_cost")
    if not isinstance(residual, Mapping) or set(residual) != {"status", "occurrence_count"}:
        raise MetabolismError("candidate_trajectory_cost_invalid")
    if residual.get("status") not in {"unknown_not_zero", "none_observed"}:
        raise MetabolismError("candidate_trajectory_cost_invalid")
    residual_count = int_value(residual.get("occurrence_count"))
    if residual_count is None or residual_count != residual.get("occurrence_count"):
        raise MetabolismError("candidate_trajectory_cost_invalid")
    proxies = value.get("proxies")
    if not isinstance(proxies, Mapping) or set(proxies) != {
        "repeat_occurrence_count", "rerun_after_fix_occurrence_count", "interpretation",
    }:
        raise MetabolismError("candidate_trajectory_cost_invalid")
    repeat_count = int_value(proxies.get("repeat_occurrence_count"))
    rerun_count = int_value(proxies.get("rerun_after_fix_occurrence_count"))
    if (
        repeat_count is None
        or repeat_count != proxies.get("repeat_occurrence_count")
        or rerun_count is None
        or rerun_count != proxies.get("rerun_after_fix_occurrence_count")
        or proxies.get("interpretation") != "diagnostic pressure only; not a universal cost or benefit score"
    ):
        raise MetabolismError("candidate_trajectory_cost_invalid")


def _validate_candidate_packet_static(packet: Mapping[str, Any]) -> None:
    required = set(LIFECYCLE_BASE_FIELDS) | {"lifecycle", "routes", "evaluation_requirements", "next_route"}
    if not isinstance(packet, Mapping) or set(packet) != required:
        raise MetabolismError("candidate_packet_shape_invalid")
    if packet.get("candidate_id") is None or not SAFE_CANDIDATE_ID.fullmatch(str(packet.get("candidate_id"))):
        raise MetabolismError("candidate_id_invalid")
    if packet.get("schema_version") != SCHEMA_VERSION or packet.get("status") != "candidate":
        raise MetabolismError("candidate_status_invalid")
    lifecycle = packet.get("lifecycle")
    if not isinstance(lifecycle, Mapping) or set(lifecycle) != {
        "state", "history", "history_digest", "reversible", "adoption_allowed", "required_order", "base_digest",
    }:
        raise MetabolismError("lifecycle_contract_invalid")
    if lifecycle.get("base_digest") != _candidate_base_digest(packet):
        raise MetabolismError("lifecycle_base_digest_invalid")

    motif = packet.get("motif")
    if not isinstance(motif, Mapping) or set(motif) != {
        "signal", "stage", "tool", "operation_shape", "operation_digest", "key_is_content_free"
    }:
        raise MetabolismError("candidate_motif_invalid")
    digest = valid_operation_digest(motif.get("operation_digest"))
    shape = valid_operation_shape(motif.get("operation_shape"))
    stage = safe_word(motif.get("stage"))
    tool = safe_word(motif.get("tool"))
    if (
        digest is None
        or shape is None
        or motif.get("key_is_content_free") is not True
        or motif.get("signal") not in {
            "operation_observed", "repeated_operation", "rerun_after_fix",
            "validation_rerun_after_repair", "coordination_idle_wait", "unknown_stage",
        }
        or stage not in KNOWN_STAGES | {"unknown"}
        or not operation_shape_matches(shape, stage, tool, digest)
    ):
        raise MetabolismError("candidate_motif_invalid")

    recurrence_data = packet.get("recurrence")
    if not isinstance(recurrence_data, Mapping) or set(recurrence_data) != {
        "status", "occurrence_count", "distinct_session_count", "distinct_source_binding_count",
        "distinct_episode_count", "session_refs", "source_binding_refs", "thresholds", "reason",
    }:
        raise MetabolismError("candidate_recurrence_invalid")
    sessions = recurrence_data.get("session_refs")
    if not isinstance(sessions, list) or len(sessions) > 256 or sessions != sorted(set(sessions)):
        raise MetabolismError("candidate_recurrence_invalid")
    if not all(isinstance(item, str) and SAFE_SESSION_REF.fullmatch(item) for item in sessions):
        raise MetabolismError("candidate_recurrence_invalid")
    source_binding_refs = recurrence_data.get("source_binding_refs")
    if not isinstance(source_binding_refs, list) or len(source_binding_refs) > 256 or source_binding_refs != sorted(set(source_binding_refs)):
        raise MetabolismError("candidate_recurrence_invalid")
    if not all(isinstance(item, str) and SAFE_DIGEST.fullmatch(item) for item in source_binding_refs):
        raise MetabolismError("candidate_recurrence_invalid")
    occurrence_count = int_value(recurrence_data.get("occurrence_count"))
    distinct_session_count = int_value(recurrence_data.get("distinct_session_count"))
    distinct_source_binding_count = int_value(recurrence_data.get("distinct_source_binding_count"))
    distinct_episode_count = int_value(recurrence_data.get("distinct_episode_count"))
    thresholds = recurrence_data.get("thresholds")
    minimum_distinct_sessions = (
        int_value(thresholds.get("minimum_distinct_sessions"))
        if isinstance(thresholds, Mapping)
        else None
    )
    minimum_occurrences = (
        int_value(thresholds.get("minimum_occurrences"))
        if isinstance(thresholds, Mapping)
        else None
    )
    if (
        occurrence_count is None
        or distinct_session_count is None
        or distinct_source_binding_count is None
        or distinct_episode_count is None
        or distinct_session_count != len(sessions)
        or distinct_source_binding_count != len(source_binding_refs)
        or not isinstance(thresholds, Mapping)
        or set(thresholds) != {"minimum_distinct_sessions", "minimum_occurrences"}
        or minimum_distinct_sessions is None
        or minimum_occurrences is None
        or minimum_distinct_sessions < 2
        or minimum_occurrences < 1
        or recurrence_data.get("status") not in {"review_ready", "watch", "insufficient_evidence"}
        or recurrence_data.get("status") == "review_ready"
        and (
            distinct_session_count < minimum_distinct_sessions
            or distinct_source_binding_count < minimum_distinct_sessions
            or occurrence_count < minimum_occurrences
        )
    ):
        raise MetabolismError("candidate_recurrence_invalid")

    diversity = packet.get("evidence_diversity")
    if not isinstance(diversity, Mapping) or set(diversity) != {
        "distinct_profile_count", "distinct_session_count", "distinct_episode_count", "profile_refs",
        "source_binding_refs", "distinct_source_binding_count", "occurrence_rows", "total_occurrence_count", "emitted_occurrence_count",
        "omitted_occurrence_count", "omitted_occurrence_digest", "truncated",
    }:
        raise MetabolismError("candidate_evidence_diversity_invalid")
    profile_refs = diversity.get("profile_refs")
    if not isinstance(profile_refs, list) or not profile_refs or len(profile_refs) > 256 or profile_refs != sorted(set(profile_refs)):
        raise MetabolismError("candidate_evidence_diversity_invalid")
    if not all(isinstance(item, str) and SAFE_WORD.fullmatch(item) for item in profile_refs):
        raise MetabolismError("candidate_evidence_diversity_invalid")
    occurrence_rows = diversity.get("occurrence_rows")
    if not isinstance(occurrence_rows, list) or len(occurrence_rows) > MAX_EVIDENCE_REFS:
        raise MetabolismError("candidate_evidence_diversity_invalid")
    for row in occurrence_rows:
        if not isinstance(row, Mapping) or set(row) != {
            "session_ref", "source_binding_ref", "profile_ref", "episode_ref", "review_ref", "result_status", "evidence_status",
            "span_seconds", "evidence_refs",
        }:
            raise MetabolismError("candidate_occurrence_row_invalid")
        if not isinstance(row.get("session_ref"), str) or not SAFE_SESSION_REF.fullmatch(row["session_ref"]):
            raise MetabolismError("candidate_occurrence_row_invalid")
        if not isinstance(row.get("source_binding_ref"), str) or not SAFE_DIGEST.fullmatch(row["source_binding_ref"]):
            raise MetabolismError("candidate_occurrence_row_invalid")
        if not isinstance(row.get("profile_ref"), str) or not SAFE_WORD.fullmatch(row["profile_ref"]):
            raise MetabolismError("candidate_occurrence_row_invalid")
        if safe_logical_ref(row.get("episode_ref")) != row.get("episode_ref"):
            raise MetabolismError("candidate_occurrence_row_invalid")
        if safe_logical_ref(row.get("review_ref")) != row.get("review_ref"):
            raise MetabolismError("candidate_occurrence_row_invalid")
        if (
            row["session_ref"] not in sessions
            or row["source_binding_ref"] not in source_binding_refs
            or row["profile_ref"] not in profile_refs
            or _canonical_ref_session(row["episode_ref"]) != row["session_ref"]
            or _canonical_ref_session(row["review_ref"]) != row["session_ref"]
            or any(_canonical_ref_session(ref) != row["session_ref"] for ref in row["evidence_refs"])
        ):
            raise MetabolismError("candidate_occurrence_row_invalid")
        if row.get("result_status") not in {"succeeded", "failed", "error", "timed_out", "timeout", "unknown"}:
            raise MetabolismError("candidate_occurrence_row_invalid")
        if row.get("evidence_status") not in {"verified", "unknown"} or not _canonical_ref_list(row.get("evidence_refs"), allow_empty=False):
            raise MetabolismError("candidate_occurrence_row_invalid")
        if row.get("span_seconds") is not None and number_value(row.get("span_seconds")) != row.get("span_seconds"):
            raise MetabolismError("candidate_occurrence_row_invalid")
    occurrence_review_refs = safe_evidence_refs(row.get("review_ref") for row in occurrence_rows)
    occurrence_review_ref_count = len({
        _ref_key(row.get("review_ref"))
        for row in occurrence_rows
        if isinstance(row.get("review_ref"), Mapping)
        and safe_logical_ref(row.get("review_ref")) is not None
    })
    total_count = int_value(diversity.get("total_occurrence_count"))
    emitted_count = int_value(diversity.get("emitted_occurrence_count"))
    omitted_count = int_value(diversity.get("omitted_occurrence_count"))
    truncated = diversity.get("truncated")
    omitted_digest = diversity.get("omitted_occurrence_digest")
    if (
        total_count is None
        or emitted_count != len(occurrence_rows)
        or omitted_count != total_count - emitted_count
        or total_count != occurrence_count
        or truncated is not (omitted_count > 0)
        or (omitted_count and (not isinstance(omitted_digest, str) or not SAFE_DIGEST.fullmatch(omitted_digest)))
        or (not omitted_count and omitted_digest is not None)
        or int_value(diversity.get("distinct_session_count")) != distinct_session_count
        or diversity.get("source_binding_refs") != source_binding_refs
        or int_value(diversity.get("distinct_source_binding_count")) != distinct_source_binding_count
        or int_value(diversity.get("distinct_episode_count")) != distinct_episode_count
        or int_value(diversity.get("distinct_profile_count")) != len(profile_refs)
        or not occurrence_review_refs
    ):
        raise MetabolismError("candidate_evidence_diversity_invalid")

    counter = packet.get("counterevidence")
    if not isinstance(counter, Mapping) or set(counter) != {
        "status", "outcome_counts", "negative_evidence_refs", "unknown_evidence_refs", "all_evidence_refs", "admission_rule",
    }:
        raise MetabolismError("candidate_counterevidence_invalid")
    if counter.get("status") not in {"no_negative_observation", "unknown", "conflicting"}:
        raise MetabolismError("candidate_counterevidence_invalid")
    outcomes = counter.get("outcome_counts")
    if not isinstance(outcomes, Mapping) or not all(
        key in {"succeeded", "failed", "error", "timed_out", "timeout", "unknown"} and int_value(value) is not None
        for key, value in outcomes.items()
    ) or sum(int_value(value) or 0 for value in outcomes.values()) != occurrence_count:
        raise MetabolismError("candidate_counterevidence_invalid")
    if (
        not _canonical_ref_list(counter.get("negative_evidence_refs"))
        or not _canonical_ref_list(counter.get("unknown_evidence_refs"))
        or not _canonical_ref_list(counter.get("all_evidence_refs"))
        or counter.get("admission_rule") != "unknown or conflicting outcomes cannot become an accepted candidate"
    ):
        raise MetabolismError("candidate_counterevidence_invalid")
    expected_blocked = (
        counter.get("status") in {"unknown", "conflicting"}
        or recurrence_data.get("status") != "review_ready"
        or diversity.get("truncated") is True
    )
    if packet.get("status") != "candidate" or expected_blocked:
        raise MetabolismError("candidate_not_admissible_for_lifecycle")

    alternatives = packet.get("alternative_explanations")
    if (
        not isinstance(alternatives, list)
        or not alternatives
        or len(alternatives) > 16
        or len(set(alternatives)) != len(alternatives)
        or any(item not in ALTERNATIVE_EXPLANATION_CODES for item in alternatives)
    ):
        raise MetabolismError("candidate_alternative_explanations_invalid")
    causal = packet.get("causal_attribution")
    if not isinstance(causal, Mapping) or set(causal) != {
        "status", "claim", "paired_comparison", "held_out_comparison", "ablation_comparison", "confounders",
    }:
        raise MetabolismError("candidate_causal_attribution_invalid")
    if causal.get("status") != "not_established" or causal.get("claim") != "association_only":
        raise MetabolismError("candidate_causal_attribution_invalid")
    for name in ("paired_comparison", "held_out_comparison", "ablation_comparison"):
        comparison = causal.get(name)
        if not isinstance(comparison, Mapping) or set(comparison) != {"status", "evidence_refs"}:
            raise MetabolismError("candidate_causal_attribution_invalid")
        if comparison.get("status") not in {"missing", "accepted", "observed", "passed"} or not _canonical_ref_list(comparison.get("evidence_refs")):
            raise MetabolismError("candidate_causal_attribution_invalid")
    if not isinstance(causal.get("confounders"), list) or not all(
        isinstance(item, str) and SAFE_WORD.fullmatch(item) for item in causal["confounders"]
    ):
        raise MetabolismError("candidate_causal_attribution_invalid")
    approval = packet.get("approval_sensitivity")
    if approval != {
        "status": "pending",
        "review_eligibility_is_not_owner_acceptance": True,
        "removing_reviewed_status_must_remove_the_observation_from_recurrence": True,
    }:
        raise MetabolismError("candidate_approval_sensitivity_invalid")
    trajectory = packet.get("trajectory_cost")
    _validate_trajectory_cost(trajectory)

    provenance = packet.get("provenance")
    if not isinstance(provenance, Mapping) or set(provenance) != {
        "source_schema", "source_ref_scheme", "profile_refs", "review_refs", "review_ref_count",
        "review_refs_truncated", "evidence_refs",
        "raw_transcript_scanned", "raw_transcript_refs_emitted", "source_authority",
    }:
        raise MetabolismError("candidate_provenance_invalid")
    review_ref_count = int_value(provenance.get("review_ref_count"))
    if (
        provenance.get("source_schema") != PROFILE_SCHEMA_VERSION
        or provenance.get("source_ref_scheme") != REF_SCHEME
        or provenance.get("profile_refs") != profile_refs
        or provenance.get("review_refs") != occurrence_review_refs
        or not _canonical_ref_list(provenance.get("review_refs"), allow_empty=False)
        or review_ref_count is None
        or review_ref_count < occurrence_review_ref_count
        or provenance.get("review_refs_truncated") is not (
            review_ref_count > MAX_EVIDENCE_REFS
            if review_ref_count is not None
            else False
        )
        or len(provenance.get("review_refs", [])) != min(
            review_ref_count or 0,
            MAX_EVIDENCE_REFS,
        )
        or not _canonical_ref_list(provenance.get("evidence_refs"))
        or provenance.get("raw_transcript_scanned") is not False
        or provenance.get("raw_transcript_refs_emitted") is not False
        or provenance.get("source_authority") != "generated_stage_profile_only"
    ):
        raise MetabolismError("candidate_provenance_invalid")
    if packet.get("privacy") != {
        "policy": "normalized_shapes_digests_and_hashed_logical_refs_only",
        "raw_content_emitted": False,
        "raw_paths_emitted": False,
        "sensitive_fields_emitted": False,
        "bounded_refs": True,
    }:
        raise MetabolismError("candidate_privacy_invalid")
    observation = packet.get("advisory_observation")
    expected_observation = {
        "schema_version": OBSERVATION_SCHEMA_VERSION,
        "component_ref": "component:aoa-session-memory:experience-metabolism",
        "owner_repo": "aoa-session-memory",
        "category": "repeat_pattern",
        "signal": "experience_motif_candidate",
        "source_inputs": [PROFILE_SCHEMA_VERSION],
        "evidence_refs": provenance["evidence_refs"],
        "attributes": {
            "candidate_id": packet["candidate_id"],
            "signal": motif["signal"],
            "operation_digest": digest,
            "distinct_session_count": recurrence_data["distinct_session_count"],
            "occurrence_count": recurrence_data["occurrence_count"],
            "readiness": recurrence_data["status"],
        },
        "notes": "Advisory observation only; no semantic adoption or policy is implied.",
    }
    if observation != expected_observation:
        raise MetabolismError("candidate_observation_invalid")

def _derived_route_statuses(history: list[Mapping[str, Any]]) -> dict[str, str]:
    statuses = {
        "owner": "candidate",
        "review": "pending",
        "eval": "blocked_until_review",
        "shadow": "blocked_until_eval",
        "adoption": "blocked_until_owner_acceptance",
        "rejection": "available",
    }
    for record in history:
        kind = record["kind"]
        status = record["status"]
        if kind == "review_verdict":
            statuses["review"] = status
            statuses["eval"] = "pending" if status == "accepted" else "blocked"
            if status == "rejected":
                statuses["rejection"] = "rejected"
        elif kind == "eval_verdict":
            statuses["eval"] = status
            statuses["shadow"] = "pending" if status == "accepted" else "blocked"
            if status == "rejected":
                statuses["rejection"] = "rejected"
        elif kind == "shadow_result":
            statuses["shadow"] = status
            statuses["adoption"] = "pending_owner_acceptance" if status == "accepted" else "blocked"
            if status == "rejected":
                statuses["rejection"] = "rejected"
        elif kind == "owner_acceptance":
            statuses["adoption"] = "pending_explicit_adoption"
        elif kind == "adoption":
            statuses["adoption"] = "adopted"
        elif kind == "reject":
            statuses["rejection"] = "rejected"
        elif kind in {"supersede", "rollback"}:
            statuses["rejection"] = kind
            statuses["adoption"] = "blocked"
    return statuses


def _expected_next_route(state: str, recurrence_status: str) -> str:
    if state == "candidate":
        return "reviewer-office" if recurrence_status == "review_ready" else "aoa-session-memory:manual-review"
    return {
        "eval_pending": "aoa-evals",
        "shadow_pending": "abyss-stack",
        "owner_review_pending": "aoa-session-memory:owner-acceptance",
        "accepted": "aoa-session-memory:adoption-review",
        "adopted": "aoa-session-memory:closeout",
        "rejected": "aoa-session-memory:closeout",
        "superseded": "aoa-session-memory:closeout",
        "rolled_back": "aoa-session-memory:closeout",
    }.get(state, "aoa-session-memory:manual-review")


def _validate_record_evidence(
    kind: str,
    status: str,
    evidence: Any,
    *,
    candidate: Mapping[str, Any] | None = None,
) -> None:
    if not isinstance(evidence, Mapping):
        raise MetabolismError("lifecycle_evidence_invalid")
    if kind == "review_verdict" and status == "accepted":
        if dict(evidence) != {"independent_reviewer": True}:
            raise MetabolismError("lifecycle_evidence_invalid")
        return
    if kind == "eval_verdict" and status == "accepted":
        comparison_evidence = evidence.get("comparison_evidence")
        comparison_refs = evidence.get("comparison_refs")
        if set(evidence) != {"comparison_evidence", "comparison_refs"}:
            raise MetabolismError("lifecycle_evidence_invalid")
        expected_candidate_id = candidate.get("candidate_id") if isinstance(candidate, Mapping) else None
        recurrence_data = candidate.get("recurrence") if isinstance(candidate, Mapping) else None
        expected_source_binding_refs = (
            recurrence_data.get("source_binding_refs")
            if isinstance(recurrence_data, Mapping)
            else None
        )
        try:
            normalized = _normalize_comparison_groups(
                comparison_evidence,
                expected_candidate_id=expected_candidate_id,
                expected_source_binding_refs=expected_source_binding_refs,
            )
        except MetabolismError as exc:
            raise MetabolismError("lifecycle_evidence_invalid") from exc
        if comparison_refs != _comparison_ref_map(normalized):
            raise MetabolismError("lifecycle_evidence_invalid")
        if not all(
            packet["result_status"] in {"passed", "accepted"}
            for packets in normalized.values()
            for packet in packets
        ):
            raise MetabolismError("lifecycle_evidence_invalid")
        return
    if kind == "shadow_result" and status == "accepted":
        measurement = evidence.get("measurement")
        measurement_refs = evidence.get("measurement_refs")
        if set(evidence) != {"measurement", "measurement_refs"} or not isinstance(measurement_refs, Mapping):
            raise MetabolismError("lifecycle_evidence_invalid")
        try:
            normalized_measurement = _normalize_shadow_measurement(measurement, candidate=candidate)
        except MetabolismError as exc:
            raise MetabolismError("lifecycle_evidence_invalid") from exc
        if normalized_measurement != measurement:
            raise MetabolismError("lifecycle_evidence_invalid")
        if (
            normalized_measurement["baseline"]["coverage_status"] != "complete"
            or normalized_measurement["shadow"]["coverage_status"] != "complete"
        ):
            raise MetabolismError("lifecycle_evidence_invalid")
        if set(measurement_refs) != {"baseline", "shadow", "net_benefit"}:
            raise MetabolismError("lifecycle_evidence_invalid")
        expected_measurement_refs = {
            "baseline": [normalized_measurement["baseline"]["ref"]],
            "shadow": [normalized_measurement["shadow"]["ref"]],
            "net_benefit": [normalized_measurement["net_benefit"]["ref"]],
        }
        if measurement_refs != expected_measurement_refs:
            raise MetabolismError("lifecycle_evidence_invalid")
        for key in ("baseline", "shadow", "net_benefit"):
            _strict_ref_group(measurement_refs.get(key), "lifecycle_evidence_invalid")
        return
    if kind == "owner_acceptance" and status == "accepted":
        acceptance_refs = evidence.get("acceptance_refs")
        canary = evidence.get("canary_evidence")
        if set(evidence) != {"acceptance_refs", "canary_evidence"} or not isinstance(acceptance_refs, Mapping):
            raise MetabolismError("lifecycle_evidence_invalid")
        if set(acceptance_refs) != {"owner", "live_canary"}:
            raise MetabolismError("lifecycle_evidence_invalid")
        for key in ("owner", "live_canary"):
            _strict_ref_group(acceptance_refs.get(key), "lifecycle_evidence_invalid")
        try:
            normalized_canary = _normalize_canary_evidence(canary, candidate=candidate or {})
        except MetabolismError as exc:
            raise MetabolismError("lifecycle_evidence_invalid") from exc
        if normalized_canary != canary:
            raise MetabolismError("lifecycle_evidence_invalid")
        return
    if kind == "adoption" and status == "accepted":
        if set(evidence) != {"adoption_refs"}:
            raise MetabolismError("lifecycle_evidence_invalid")
        _strict_ref_group(evidence.get("adoption_refs"), "lifecycle_evidence_invalid")
        return
    if kind == "supersede":
        if set(evidence) != {"replacement_refs"}:
            raise MetabolismError("lifecycle_evidence_invalid")
        _strict_ref_group(evidence.get("replacement_refs"), "lifecycle_evidence_invalid")
        return
    if kind == "rollback":
        if set(evidence) != {"rollback_refs"}:
            raise MetabolismError("lifecycle_evidence_invalid")
        _strict_ref_group(evidence.get("rollback_refs"), "lifecycle_evidence_invalid")
        return
    if evidence:
        raise MetabolismError("lifecycle_evidence_invalid")


def _derived_requirements(history: list[Mapping[str, Any]]) -> dict[str, Any]:
    derived: dict[str, Any] = {}
    for record in history:
        kind = str(record["kind"])
        status = str(record["status"])
        receipt = record["receipt"]
        evidence = record["evidence"]
        if kind == "review_verdict":
            derived.update({"review_verdict": status, "review_receipt": receipt})
        elif kind == "eval_verdict":
            derived.update({"eval_verdict": status, "verdict": status, "eval_receipt": receipt})
            if status == "accepted":
                derived["eval_comparison_evidence"] = evidence["comparison_evidence"]
                derived["eval_comparison_refs"] = evidence["comparison_refs"]
        elif kind == "shadow_result":
            derived.update({"shadow_verdict": status, "shadow_receipt": receipt})
            if status == "accepted":
                derived["shadow_measurement"] = evidence["measurement"]
                derived["shadow_evidence_refs"] = evidence["measurement_refs"]
        elif kind == "owner_acceptance":
            derived.update(
                {
                    "owner_acceptance": status,
                    "owner_receipt": receipt,
                    "owner_acceptance_refs": evidence["acceptance_refs"]["owner"],
                    "live_canary_refs": evidence["acceptance_refs"]["live_canary"],
                    "live_canary_evidence": evidence["canary_evidence"],
                    "live_canary": True,
                }
            )
        elif kind == "adoption":
            derived.update(
                {
                    "adoption": status,
                    "adoption_receipt": receipt,
                    "adoption_refs": evidence["adoption_refs"],
                }
            )
        elif kind == "reject":
            derived["reject_receipt"] = receipt
        elif kind == "supersede":
            derived.update({"supersede_receipt": receipt, "replacement_refs": evidence["replacement_refs"]})
        elif kind == "rollback":
            derived.update({"rollback_receipt": receipt, "rollback_refs": evidence["rollback_refs"]})
    return derived


def _validate_lifecycle_packet(packet: Mapping[str, Any]) -> tuple[str, list[Mapping[str, Any]]]:
    """Validate state from the complete authenticated transition chain."""

    _validate_candidate_packet_static(packet)
    lifecycle = packet.get("lifecycle")
    if not isinstance(lifecycle, Mapping):
        raise MetabolismError("lifecycle_history_invalid")
    state = lifecycle.get("state")
    history = lifecycle.get("history")
    if state not in LIFECYCLE_STATES or not isinstance(history, list):
        raise MetabolismError("lifecycle_history_invalid")
    if lifecycle.get("reversible") is not True or lifecycle.get("required_order") != LIFECYCLE_REQUIRED_ORDER:
        raise MetabolismError("lifecycle_contract_invalid")
    if lifecycle.get("adoption_allowed") is not (state == "adopted"):
        raise MetabolismError("lifecycle_adoption_state_invalid")
    if len(history) > 64:
        raise MetabolismError("lifecycle_history_invalid")
    expected_state = "candidate"
    previous_digest: str | None = None
    for index, raw_record in enumerate(history):
        if not isinstance(raw_record, Mapping):
            raise MetabolismError("lifecycle_history_invalid")
        required = {
            "chain_index", "from_state", "kind", "status", "to_state", "receipt",
            "evidence", "evidence_refs", "previous_chain_digest", "chain_digest",
        }
        if set(raw_record) != required:
            raise MetabolismError("lifecycle_record_invalid")
        if raw_record.get("chain_index") != index or raw_record.get("from_state") != expected_state:
            raise MetabolismError("lifecycle_transition_chain_invalid")
        kind = raw_record.get("kind")
        status = raw_record.get("status")
        if kind not in EXPECTED_RECEIPT_OWNERS or status not in {"accepted", "rejected", "superseded", "rolled_back"}:
            raise MetabolismError("lifecycle_transition_chain_invalid")
        target = _transition_target(expected_state, str(kind), str(status))
        if target is None or raw_record.get("to_state") != target:
            raise MetabolismError("lifecycle_transition_chain_invalid")
        receipt = _normalize_receipt(
            raw_record.get("receipt"),
            kind=str(kind),
            expected_status=str(status),
            expected_candidate_id=str(packet["candidate_id"]),
            expected_base_digest=str(lifecycle["base_digest"]),
        )
        if receipt != raw_record.get("receipt"):
            raise MetabolismError("lifecycle_receipt_not_canonical")
        evidence = raw_record.get("evidence")
        _validate_record_evidence(str(kind), str(status), evidence, candidate=packet)
        _validate_receipt_evidence_binding(receipt, evidence)
        if not isinstance(evidence, Mapping) or raw_record.get("evidence_refs") != _flatten_evidence_refs(evidence):
            raise MetabolismError("lifecycle_evidence_not_canonical")
        if raw_record.get("previous_chain_digest") != previous_digest:
            raise MetabolismError("lifecycle_transition_chain_invalid")
        if raw_record.get("chain_digest") != _record_digest(raw_record):
            raise MetabolismError("lifecycle_chain_digest_invalid")
        expected_state = target
        previous_digest = raw_record["chain_digest"]
    if lifecycle.get("history_digest") != _history_digest(history):
        raise MetabolismError("lifecycle_history_digest_invalid")
    if expected_state != state:
        raise MetabolismError("lifecycle_state_not_derived_from_history")
    requirements = packet.get("evaluation_requirements")
    if not isinstance(requirements, Mapping):
        raise MetabolismError("lifecycle_requirements_invalid")
    derived = _derived_requirements(history)
    expected_requirements: dict[str, Any] = {
        "verdict": derived.get("verdict"),
        "independent_review_required": True,
        "comparisons_required": list(COMPARISON_KINDS),
        "live_shadow_required": True,
        "live_canary_required_before_benefit_claim": True,
    }
    expected_requirements.update(derived)
    if dict(requirements) != expected_requirements:
        raise MetabolismError("lifecycle_requirements_not_derived")
    routes = packet.get("routes")
    if not isinstance(routes, Mapping) or set(routes) != set(ROUTE_OWNERS):
        raise MetabolismError("lifecycle_routes_invalid")
    route_statuses = _derived_route_statuses(history)
    for route_name, owner in ROUTE_OWNERS.items():
        route = routes.get(route_name)
        if not isinstance(route, Mapping) or set(route) != {"owner", "status"}:
            raise MetabolismError("lifecycle_routes_invalid")
        if route.get("owner") != owner or route.get("status") != route_statuses[route_name]:
            raise MetabolismError("lifecycle_routes_not_derived")
    recurrence_status = packet["recurrence"]["status"]
    if packet.get("next_route") != _expected_next_route(state, recurrence_status):
        raise MetabolismError("lifecycle_next_route_not_derived")
    return state, history


def _occurrence_identity(occurrence: Mapping[str, Any]) -> str:
    """Identify one fully identical observation, without hiding conflicting outcomes."""

    return _ref_key(
        {
            "signal": occurrence.get("signal"),
            "stage": occurrence.get("stage"),
            "tool": occurrence.get("tool"),
            "operation_shape": occurrence.get("operation_shape"),
            "operation_digest": occurrence.get("operation_digest"),
            "result_status": occurrence.get("result_status"),
            "evidence_status": occurrence.get("evidence_status"),
            "span_seconds": occurrence.get("span_seconds"),
            "session_ref": occurrence.get("session_ref"),
            "source_binding_ref": occurrence.get("source_binding_ref"),
            "episode_ref": occurrence.get("episode_ref"),
            "review_ref": occurrence.get("review_ref"),
            "call_ref": occurrence.get("call_ref"),
            "result_ref": occurrence.get("result_ref"),
            "repeat_index": occurrence.get("repeat_index"),
            "repeat": occurrence.get("repeat"),
            "after_failure": occurrence.get("after_failure"),
            "rerun_after_fix": occurrence.get("rerun_after_fix"),
            "validation_rerun_after_repair": occurrence.get("validation_rerun_after_repair"),
            "producer_flags_consistent": occurrence.get("producer_flags_consistent"),
            "evidence_refs": occurrence.get("evidence_refs"),
        }
    )


def _require_comparisons(event: Mapping[str, Any], candidate: Mapping[str, Any]) -> bool:
    values = event.get("comparisons")
    refs = event.get("comparison_refs")
    if not isinstance(values, Mapping) or set(values) != set(COMPARISON_KINDS):
        return False
    recurrence_data = candidate.get("recurrence") if isinstance(candidate, Mapping) else None
    try:
        groups = _normalize_comparison_groups(
            refs,
            expected_candidate_id=candidate.get("candidate_id") if isinstance(candidate, Mapping) else None,
            expected_source_binding_refs=(
                recurrence_data.get("source_binding_refs")
                if isinstance(recurrence_data, Mapping)
                else None
            ),
        )
    except MetabolismError:
        return False
    return all(
        values.get(key) in {"accepted", "passed"}
        and all(packet["result_status"] in {"accepted", "passed"} for packet in groups[key])
        for key in COMPARISON_KINDS
    )


def apply_lifecycle_event(packet: Mapping[str, Any], event: Mapping[str, Any]) -> dict[str, Any]:
    """Apply one typed, receipted lifecycle event; never infer an event."""

    if not isinstance(event, Mapping):
        raise MetabolismError("lifecycle_event_required")
    result = deepcopy(dict(packet))
    state, history = _validate_lifecycle_packet(result)
    kind = safe_text(event.get("kind"))
    status = safe_word(event.get("status"), fallback="unknown")
    lifecycle = result["lifecycle"]
    receipt = _normalize_receipt(
        event.get("receipt"),
        kind=kind,
        expected_status=status,
        expected_candidate_id=str(result["candidate_id"]),
        expected_base_digest=str(lifecycle["base_digest"]),
    )
    evidence: dict[str, Any]
    if kind == "review_verdict":
        if state != "candidate":
            raise MetabolismError("review_event_not_allowed_in_state")
        if event.get("status") not in {"accepted", "rejected"}:
            raise MetabolismError("review_verdict_must_be_accepted_or_rejected")
        if event.get("status") == "accepted" and event.get("independent_reviewer") is not True:
            raise MetabolismError("independent_review_required")
        state = "eval_pending" if status == "accepted" else "rejected"
        evidence = _event_evidence(kind, status, event, candidate=result)
        result.setdefault("routes", {}).setdefault("review", {})["status"] = status
        requirements = result.setdefault("evaluation_requirements", {})
        requirements["review_verdict"] = status
        requirements["review_receipt"] = receipt
    elif kind == "eval_verdict":
        if state != "eval_pending":
            raise MetabolismError("eval_event_requires_review_acceptance")
        if event.get("status") not in {"accepted", "rejected"}:
            raise MetabolismError("eval_verdict_must_be_accepted_or_rejected")
        if status == "accepted":
            if not _require_comparisons(event, result):
                raise MetabolismError("paired_held_out_ablation_required")
            if result.get("counterevidence", {}).get("status") in {"unknown", "conflicting"}:
                raise MetabolismError("counterevidence_unresolved")
            state = "shadow_pending"
        else:
            state = "rejected"
        evidence = _event_evidence(kind, status, event, candidate=result)
        requirements = result.setdefault("evaluation_requirements", {})
        requirements["eval_verdict"] = status
        requirements["verdict"] = status
        requirements["eval_receipt"] = receipt
        if evidence:
            requirements["eval_comparison_evidence"] = evidence["comparison_evidence"]
            requirements["eval_comparison_refs"] = evidence["comparison_refs"]
        result.setdefault("routes", {}).setdefault("eval", {})["status"] = status
    elif kind == "shadow_result":
        if state != "shadow_pending":
            raise MetabolismError("shadow_event_requires_eval_acceptance")
        if event.get("status") not in {"accepted", "rejected"}:
            raise MetabolismError("shadow_result_must_be_accepted_or_rejected")
        state = "owner_review_pending" if status == "accepted" else "rejected"
        evidence = _event_evidence(kind, status, event, candidate=result)
        requirements = result.setdefault("evaluation_requirements", {})
        requirements["shadow_verdict"] = status
        requirements["shadow_receipt"] = receipt
        if evidence:
            requirements["shadow_evidence_refs"] = evidence["measurement_refs"]
            requirements["shadow_measurement"] = evidence["measurement"]
        result.setdefault("routes", {}).setdefault("shadow", {})["status"] = status
    elif kind == "owner_acceptance":
        if state != "owner_review_pending":
            raise MetabolismError("owner_acceptance_requires_shadow_acceptance")
        if event.get("status") != "accepted":
            raise MetabolismError("owner_acceptance_must_be_accepted")
        requirements = result.get("evaluation_requirements")
        if not isinstance(requirements, Mapping) or requirements.get("review_verdict") != "accepted" or requirements.get("eval_verdict") != "accepted" or requirements.get("shadow_verdict") != "accepted":
            raise MetabolismError("review_eval_shadow_gates_incomplete")
        state = "accepted"
        evidence = _event_evidence(kind, status, event, candidate=result)
        requirements = result.setdefault("evaluation_requirements", {})
        requirements["owner_acceptance"] = "accepted"
        requirements["owner_receipt"] = receipt
        requirements["owner_acceptance_refs"] = evidence["acceptance_refs"]["owner"]
        requirements["live_canary_refs"] = evidence["acceptance_refs"]["live_canary"]
        requirements["live_canary_evidence"] = evidence["canary_evidence"]
        requirements["live_canary"] = True
        result.setdefault("routes", {}).setdefault("adoption", {})["status"] = "pending_explicit_adoption"
    elif kind == "adoption":
        if state != "accepted":
            raise MetabolismError("adoption_requires_owner_acceptance")
        if event.get("status") != "accepted":
            raise MetabolismError("adoption_must_be_accepted")
        requirements = result.get("evaluation_requirements")
        if (
            not isinstance(requirements, Mapping)
            or requirements.get("review_verdict") != "accepted"
            or requirements.get("eval_verdict") != "accepted"
            or requirements.get("shadow_verdict") != "accepted"
            or requirements.get("owner_acceptance") != "accepted"
            or requirements.get("live_canary") is not True
        ):
            raise MetabolismError("owner_acceptance_gates_incomplete")
        state = "adopted"
        evidence = _event_evidence(kind, status, event, candidate=result)
        requirements = result.setdefault("evaluation_requirements", {})
        requirements["adoption"] = "accepted"
        requirements["adoption_receipt"] = receipt
        requirements["adoption_refs"] = evidence["adoption_refs"]
        result.setdefault("routes", {}).setdefault("adoption", {})["status"] = "adopted"
    elif kind in {"reject", "supersede", "rollback"}:
        target = _transition_target(state, kind, status)
        if target is None:
            if kind == "supersede":
                raise MetabolismError("supersession_requires_accepted_candidate_and_replacement")
            if kind == "rollback":
                raise MetabolismError("rollback_requires_accepted_candidate_and_rollback_ref")
            raise MetabolismError("accepted_candidate_requires_rollback_or_supersession")
        state = target
        evidence = _event_evidence(kind, status, event, candidate=result)
        requirements = result.setdefault("evaluation_requirements", {})
        requirements[f"{kind}_receipt"] = receipt
        if kind == "supersede":
            requirements["replacement_refs"] = evidence["replacement_refs"]
        if kind == "rollback":
            requirements["rollback_refs"] = evidence["rollback_refs"]
        result.setdefault("routes", {}).setdefault("rejection", {})["status"] = kind
    else:
        raise MetabolismError(f"unknown_lifecycle_event:{kind or 'missing'}")
    _validate_receipt_evidence_binding(receipt, evidence)
    record: dict[str, Any] = {
        "chain_index": len(history),
        "from_state": history[-1]["to_state"] if history else "candidate",
        "kind": kind,
        "status": status,
        "to_state": state,
        "receipt": receipt,
        "evidence": evidence,
        "evidence_refs": _flatten_evidence_refs(evidence),
        "previous_chain_digest": history[-1]["chain_digest"] if history else None,
    }
    record["chain_digest"] = _record_digest(record)
    new_history = [*history, record]
    lifecycle = dict(result["lifecycle"])
    lifecycle.update(
        {
            "state": state,
            "history": new_history,
            "history_digest": _history_digest(new_history),
            "adoption_allowed": state == "adopted",
        }
    )
    result["lifecycle"] = lifecycle
    route_statuses = _derived_route_statuses(new_history)
    result["routes"] = {
        route_name: {"owner": owner, "status": route_statuses[route_name]}
        for route_name, owner in ROUTE_OWNERS.items()
    }
    result["next_route"] = _expected_next_route(state, result["recurrence"]["status"])
    _validate_lifecycle_packet(result)
    return result


def build_report(
    profiles: list[Mapping[str, Any]],
    *,
    minimum_sessions: int = 2,
    minimum_occurrences: int = 3,
    observed_at: str | None = None,
) -> dict[str, Any]:
    if minimum_sessions < 2 or minimum_occurrences < 1:
        raise MetabolismError("recurrence_thresholds_invalid")
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    gate_rows: list[dict[str, Any]] = []
    source_versions: set[str] = set()
    seen_occurrences: set[str] = set()
    duplicate_occurrence_keys: list[str] = []
    for profile in profiles:
        validate_profile_input(profile)
        source_versions.add(safe_word(profile.get("profiler", {}).get("version")))
        if len(source_versions) > 64:
            raise MetabolismError("source_version_limit_exceeded")
        sessions = profile.get("sessions") if isinstance(profile.get("sessions"), list) else []
        for session in sessions:
            if not isinstance(session, Mapping):
                continue
            if len(gate_rows) >= MAX_CANDIDATES:
                raise MetabolismError("session_gate_limit_exceeded")
            gate = session_gate(session)
            gate_rows.append(
                {
                    "session_ref": gate["session_ref"],
                    "profile_ref": gate["profile_ref"],
                    "eligible": gate["eligible"],
                    "review_status": gate["review_status"],
                    "review_ref": gate["review_ref"],
                    "freshness_status": gate["freshness_status"],
                    "reasons": gate["reasons"],
                }
            )
            episodes = session.get("episodes") if isinstance(session.get("episodes"), list) else []
            for episode in episodes:
                if not isinstance(episode, Mapping):
                    continue
                for occurrence in extract_occurrences(session, episode, gate):
                    identity = _occurrence_identity(occurrence)
                    if identity in seen_occurrences:
                        duplicate_occurrence_keys.append(identity)
                        continue
                    seen_occurrences.add(identity)
                    if occurrence["key"] not in groups and len(groups) >= MAX_CANDIDATES:
                        raise MetabolismError("candidate_group_limit_exceeded")
                    if len(groups[occurrence["key"]]) >= MAX_OCCURRENCES_PER_GROUP:
                        raise MetabolismError("candidate_occurrence_limit_exceeded")
                    groups[occurrence["key"]].append(occurrence)
    candidates = [
        make_candidate(
            key,
            occurrences,
            minimum_sessions=minimum_sessions,
            minimum_occurrences=minimum_occurrences,
        )
        for key, occurrences in sorted(groups.items())
    ]
    candidate_count_before_limit = len(candidates)
    deduplicated_occurrence_count = sum(len(occurrences) for occurrences in groups.values())
    eligible_count = sum(bool(row["eligible"]) for row in gate_rows)
    excluded = Counter(reason for row in gate_rows if not row["eligible"] for reason in row["reasons"])
    return {
        "schema_version": SCHEMA_VERSION,
        "producer": {
            "version": PRODUCER_VERSION,
            "owner": "aoa-session-memory",
            "mode": "read_only_stage_profile_consumer",
            "source_schema": PROFILE_SCHEMA_VERSION,
            "source_versions": sorted(source_versions),
        },
        "corpus": {
            "profile_count": len(profiles),
            "session_count": len(gate_rows),
            "eligible_reviewed_session_count": eligible_count,
            "excluded_session_count": len(gate_rows) - eligible_count,
            "excluded_reason_counts": dict(sorted(excluded.items())) or None,
            "deduplicated_occurrence_count": deduplicated_occurrence_count,
            "duplicate_occurrence_count": len(duplicate_occurrence_keys),
            "duplicate_occurrence_digest": (
                f"sha256:{stable_digest(sorted(duplicate_occurrence_keys))}"
                if duplicate_occurrence_keys
                else None
            ),
            "scope": "closed episodes from reviewed, aligned, bounded-readable generated profiles",
        },
        "candidate_output": {
            "candidate_count_before_limit": candidate_count_before_limit,
            "candidate_count_emitted": len(candidates),
            "max_candidates": MAX_CANDIDATES,
            "truncated": candidate_count_before_limit > MAX_CANDIDATES,
        },
        "eligibility_contract": {
            "review_statuses": sorted(REVIEWED_STATUSES),
            "freshness_statuses": sorted(FRESH_PROFILE_STATUSES),
            "closed_episode_required": True,
            "same_session_repetition_is_not_recurrence": True,
            "unknown_or_conflicting_evidence_is_not_adoptable": True,
        },
        "session_gates": gate_rows,
        "candidates": candidates,
        "shadow": {
            "status": "not_run",
            "required_comparison_modes": ["paired", "held_out", "ablation"],
            "baseline_required": True,
            "net_benefit_claim": "not_established",
            "trajectory_cost_required": True,
        },
        "privacy": {
            "raw_transcript_scanned": False,
            "raw_transcript_emitted": False,
            "raw_paths_emitted": False,
            "content_fields_copied": [],
            "ref_scheme": REF_SCHEME,
        },
        "evaluator_input": {
            "candidate_only": True,
            "correlation_is_not_causality": True,
            "verdict": None,
            "owner_acceptance": None,
            "adoption": None,
        },
        "observed_at": safe_observed_at(observed_at),
        "return_status": "candidates_emitted" if candidates else "no_admissible_motif",
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", action="append", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--minimum-sessions", type=int, default=2)
    parser.add_argument("--minimum-occurrences", type=int, default=3)
    parser.add_argument("--observed-at")
    parser.add_argument("--baseline-profile", type=Path)
    parser.add_argument("--shadow-profile", type=Path)
    parser.add_argument("--comparison-mode", choices=("descriptive_unpaired", "paired", "held_out", "ablation"), default="descriptive_unpaired")
    parser.add_argument("--comparison-ref", action="append", default=[])
    parser.add_argument("--comparison-packet", action="append", type=Path, default=[])
    parser.add_argument("--packet", type=Path, help="Apply one explicit lifecycle event to a candidate packet.")
    parser.add_argument("--event", type=Path)
    args = parser.parse_args(argv)
    has_packet = args.packet is not None
    has_event = args.event is not None
    has_baseline = args.baseline_profile is not None
    has_shadow = args.shadow_profile is not None
    has_comparison_refs = bool(args.comparison_ref)
    has_comparison_packets = bool(args.comparison_packet)
    if has_packet != has_event:
        parser.error("--packet and --event must be supplied together")
    if has_baseline != has_shadow:
        parser.error("--baseline-profile and --shadow-profile must be supplied together")
    if has_packet and (has_baseline or has_comparison_refs or has_comparison_packets):
        parser.error("lifecycle mode cannot be mixed with shadow comparison inputs")
    if not has_baseline and (has_comparison_refs or has_comparison_packets or args.comparison_mode != "descriptive_unpaired"):
        parser.error("comparison inputs require baseline and shadow profiles")
    if has_baseline:
        if args.comparison_mode == "descriptive_unpaired" and has_comparison_packets:
            parser.error("descriptive_unpaired mode accepts comparison refs, not typed packets")
        if args.comparison_mode != "descriptive_unpaired" and has_comparison_refs:
            parser.error("typed comparison mode requires --comparison-packet inputs")
        if args.comparison_mode != "descriptive_unpaired" and not has_comparison_packets:
            parser.error("typed comparison mode requires at least one --comparison-packet")
    return args


def emit(payload: Mapping[str, Any], output: Path | None) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    print(text, end="")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        profiles = [read_json(path.expanduser()) for path in args.profile]
        if args.packet:
            if len(profiles) != 1 or args.event is None:
                raise MetabolismError("lifecycle_requires_one_profile_packet_and_event")
            packet_root = profiles[0]
            packet = packet_root
            if isinstance(packet_root.get("candidates"), list):
                if len(packet_root["candidates"]) != 1:
                    raise MetabolismError("lifecycle_requires_one_candidate_packet")
                packet = packet_root["candidates"][0]
            result = apply_lifecycle_event(packet, read_json(args.event))
        elif args.baseline_profile and args.shadow_profile:
            comparison_inputs: Any = args.comparison_ref
            if args.comparison_packet:
                comparison_inputs = [read_json(path.expanduser()) for path in args.comparison_packet]
            result = build_shadow_measurement(
                read_json(args.baseline_profile.expanduser()),
                read_json(args.shadow_profile.expanduser()),
                comparison_mode=args.comparison_mode,
                comparison_refs=comparison_inputs,
            )
        else:
            result = build_report(
                profiles,
                minimum_sessions=args.minimum_sessions,
                minimum_occurrences=args.minimum_occurrences,
                observed_at=args.observed_at,
            )
    except MetabolismError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    emit(result, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
