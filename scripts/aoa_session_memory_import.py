"""Small, source-only boundary for Codex transcript candidate collection.

The session-memory producer owns enrichment and archive synchronization.  This
module owns only the bounded, read-only part of historical import selection so
that collection policy can be tested without importing the full producer.
Callbacks let the producer keep its richer title/lineage probe while the
standalone route remains useful with its conservative metadata probe.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable


TranscriptProbe = Callable[[Path], dict[str, Any]]
SizePrefilter = Callable[
    [Path, os.stat_result, str | None],
    dict[str, Any],
]


def parse_date_arg(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(r"(20\d{2})[-_]?([01]\d)[-_]?([0-3]\d)", value)
    if not match:
        raise ValueError(f"expected date like YYYY-MM-DD, got {value!r}")
    return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"


def parse_timestamp_arg(value: str | None) -> str | None:
    if not value:
        return None
    candidate = str(value).strip()
    if re.fullmatch(r"20\d{2}-[01]\d-[0-3]\d", candidate):
        candidate = f"{candidate}T00:00:00Z"
    normalized = candidate[:-1] + "+00:00" if candidate.endswith("Z") else candidate
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"expected ISO-8601 timestamp, got {value!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def since_date_from_args(since: str | None, since_days: int | None) -> str | None:
    explicit = parse_date_arg(since)
    if explicit:
        return explicit
    if since_days is None:
        return None
    return (datetime.now(timezone.utc) - timedelta(days=since_days)).strftime(
        "%Y-%m-%d"
    )


def transcript_path_date_hint(raw_path: Path, source_root: Path) -> str | None:
    """Read a YYYY/MM/DD path hint without opening the transcript."""

    try:
        parts = raw_path.relative_to(source_root).parts
    except ValueError:
        parts = raw_path.parts
    for index in range(max(0, len(parts) - 2)):
        year, month, day = parts[index : index + 3]
        if not (
            re.fullmatch(r"20\d{2}", year)
            and re.fullmatch(r"[01]\d", month)
            and re.fullmatch(r"[0-3]\d", day)
        ):
            continue
        try:
            datetime(int(year), int(month), int(day), tzinfo=timezone.utc)
        except ValueError:
            continue
        return f"{year}-{month}-{day}"
    try:
        return parse_date_arg(raw_path.name)
    except ValueError:
        return None


def _default_metadata_probe(
    raw_path: Path,
    *,
    source_root: Path | None = None,
) -> dict[str, Any]:
    """Conservatively identify a transcript without importing the producer."""

    event: dict[str, Any] = {"transcript_path": str(raw_path)}
    try:
        with raw_path.open("r", encoding="utf-8", errors="replace") as handle:
            for line_no, line in enumerate(handle, start=1):
                if line_no > 40:
                    break
                try:
                    parsed = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(parsed, dict) or parsed.get("type") != "session_meta":
                    continue
                payload = parsed.get("payload")
                if not isinstance(payload, dict):
                    continue
                for key in (
                    "id",
                    "cwd",
                    "timestamp",
                    "model",
                    "model_provider",
                    "cli_version",
                ):
                    if payload.get(key):
                        event[key] = payload[key]
                break
    except OSError:
        pass
    source_stat = raw_path.stat()
    path_date = transcript_path_date_hint(
        raw_path,
        source_root if source_root is not None else raw_path.parent,
    )
    timestamp = str(event.get("timestamp") or "")
    try:
        session_date = parse_date_arg(timestamp)
    except ValueError:
        session_date = None
    session_id = str(event.get("id") or raw_path.stem)
    return {
        "session_id": session_id,
        "transcript_path": str(raw_path),
        "session_date": session_date or path_date or datetime.fromtimestamp(
            source_stat.st_mtime, timezone.utc
        ).strftime("%Y-%m-%d"),
        "title": raw_path.stem,
        "title_source": "transcript_path_metadata_probe",
        "cwd": event.get("cwd"),
        "timestamp": event.get("timestamp"),
        "model": event.get("model"),
        "model_provider": event.get("model_provider"),
        "cli_version": event.get("cli_version"),
        "lineage": {},
        "bytes": source_stat.st_size,
        "mtime": datetime.fromtimestamp(
            source_stat.st_mtime, timezone.utc
        ).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _default_size_prefilter(
    raw_path: Path,
    source_stat: os.stat_result,
    path_date: str | None,
) -> dict[str, Any]:
    """Read only the identity prefix for a transcript outside the size lane."""

    event: dict[str, Any] = {"transcript_path": str(raw_path)}
    try:
        with raw_path.open("r", encoding="utf-8", errors="replace") as handle:
            for line_no, line in enumerate(handle, start=1):
                if line_no > 40:
                    break
                try:
                    parsed = json.loads(line)
                except json.JSONDecodeError:
                    continue
                payload = (
                    parsed.get("payload")
                    if isinstance(parsed, dict)
                    and isinstance(parsed.get("payload"), dict)
                    else {}
                )
                if not isinstance(parsed, dict) or parsed.get("type") != "session_meta":
                    continue
                if payload.get("id"):
                    event["id"] = payload["id"]
                for key in (
                    "cwd",
                    "timestamp",
                    "model",
                    "model_provider",
                    "cli_version",
                ):
                    if payload.get(key):
                        event[key] = payload[key]
                break
    except OSError:
        pass
    try:
        timestamp_date = parse_date_arg(str(event.get("timestamp") or ""))
    except ValueError:
        timestamp_date = None
    return {
        "session_id": str(event.get("id") or raw_path.stem),
        "transcript_path": str(raw_path),
        "session_date": timestamp_date or path_date or datetime.fromtimestamp(
            source_stat.st_mtime, timezone.utc
        ).strftime("%Y-%m-%d"),
        "title": raw_path.stem,
        "title_source": "transcript_path_size_prefilter",
        "cwd": event.get("cwd"),
        "timestamp": event.get("timestamp"),
        "model": event.get("model"),
        "model_provider": event.get("model_provider"),
        "cli_version": event.get("cli_version"),
        "lineage": {},
        "bytes": source_stat.st_size,
        "mtime": datetime.fromtimestamp(
            source_stat.st_mtime, timezone.utc
        ).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "metadata_probe_status": "identity_only_size_prefilter",
    }


def discover_codex_transcripts(
    *,
    source_root: Path,
    since: str | None = None,
    until: str | None = None,
    activity_since_epoch: float | None = None,
    min_raw_bytes: int | None = None,
    max_raw_bytes: int | None = None,
    transcript_probe: TranscriptProbe | None = None,
    transcript_size_prefilter_record: SizePrefilter | None = None,
) -> list[dict[str, Any]]:
    """Collect candidate transcripts using only bounded source metadata.

    No result cache is consulted.  Every invocation stats the current files,
    and the supplied callbacks are called after that stat, preserving the
    producer's richer source/title/lineage behavior when it is available.
    """

    source_root = source_root.expanduser()
    if not source_root.exists():
        return []
    since_date = parse_date_arg(since)
    until_date = parse_date_arg(until)
    probe = transcript_probe or (
        lambda raw_path: _default_metadata_probe(
            raw_path,
            source_root=source_root,
        )
    )
    size_prefilter = transcript_size_prefilter_record or _default_size_prefilter
    records: list[dict[str, Any]] = []
    for raw_path in sorted(source_root.rglob("*.jsonl")):
        if not raw_path.is_file():
            continue
        try:
            source_stat = raw_path.stat()
        except OSError:
            continue
        activity_window_match = bool(
            activity_since_epoch is not None
            and source_stat.st_mtime >= float(activity_since_epoch)
        )
        path_date = transcript_path_date_hint(raw_path, source_root)
        path_date_outside_window = False
        if path_date:
            if since_date and path_date < since_date:
                path_date_outside_window = True
            if until_date and path_date > until_date:
                path_date_outside_window = True
            if path_date_outside_window and not activity_window_match:
                continue
        outside_size_lane = bool(
            (
                min_raw_bytes is not None
                and source_stat.st_size < int(min_raw_bytes)
            )
            or (
                max_raw_bytes is not None
                and source_stat.st_size > int(max_raw_bytes)
            )
        )
        if outside_size_lane:
            record = size_prefilter(raw_path, source_stat, path_date)
        else:
            record = probe(raw_path)
        session_date = str(record.get("session_date") or "")
        session_date_outside_window = bool(
            (since_date and session_date < since_date)
            or (until_date and session_date > until_date)
        )
        if session_date_outside_window and not activity_window_match:
            continue
        activity_supplement = bool(
            activity_window_match
            and (path_date_outside_window or session_date_outside_window)
        )
        record["source_mtime_epoch"] = source_stat.st_mtime
        record["selection_source"] = (
            "activity_mtime_supplement"
            if activity_supplement
            else "date_window"
        )
        record["activity_window_match"] = activity_window_match
        records.append(record)
    records.sort(
        key=lambda item: (
            str(item.get("session_date") or ""),
            str(item.get("timestamp") or ""),
            str(item.get("transcript_path") or ""),
        )
    )
    return records


__all__ = [
    "discover_codex_transcripts",
    "parse_date_arg",
    "parse_timestamp_arg",
    "since_date_from_args",
    "transcript_path_date_hint",
]
