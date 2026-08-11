#!/usr/bin/env python3
"""Reproducible synthetic or read-only snapshot projection benchmark."""

from __future__ import annotations

import argparse
import json
import os
import resource
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Iterable, Iterator

import aoa_session_memory as session_memory


def write_jsonl(
    path: Path, rows: Iterable[dict[str, Any]]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(
                json.dumps(row, ensure_ascii=False, separators=(",", ":"))
                + "\n"
            )


def synthetic_rows(
    *,
    session_id: str,
    cwd: Path,
    segments: int,
    payload_bytes: int,
    events_per_segment: int = 2,
    start_minute: int = 0,
) -> Iterator[dict[str, Any]]:
    yield {
        "timestamp": f"2026-08-08T12:{start_minute:02d}:00Z",
        "type": "session_meta",
        "payload": {"id": session_id, "cwd": str(cwd)},
    }
    filler = "x" * max(0, payload_bytes)
    for ordinal in range(max(1, segments)):
        second = ordinal % 50 + 1
        for event_ordinal in range(max(1, events_per_segment)):
            role = "user" if event_ordinal == 0 else "assistant"
            content_type = (
                "input_text" if role == "user" else "output_text"
            )
            yield {
                "timestamp": f"2026-08-08T12:{start_minute:02d}:{second:02d}Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": role,
                    "content": [
                        {
                            "type": content_type,
                            "text": (
                                f"benchmark segment {ordinal} event "
                                f"{event_ordinal} " + filler
                            ),
                        }
                    ],
                },
            }
        yield {
            "timestamp": f"2026-08-08T12:{start_minute:02d}:{second:02d}Z",
            "type": "turn_context",
            "payload": {"summary": f"boundary {ordinal}"},
        }


def transcript_session_id(path: Path) -> str:
    """Read only the bounded transcript prefix needed for session identity."""
    with path.open("r", encoding="utf-8") as handle:
        for ordinal, line in enumerate(handle):
            if ordinal >= 256:
                break
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict) or row.get("type") != "session_meta":
                continue
            payload = row.get("payload")
            if not isinstance(payload, dict):
                continue
            session_id = str(payload.get("id") or "").strip()
            if session_id:
                return session_id
    raise ValueError("source transcript has no session_meta id in first 256 rows")


def copy_stable_source_snapshot(source: Path, target: Path) -> dict[str, Any]:
    """Copy a read-only source while proving its identity did not drift."""
    before = source.stat()
    shutil.copyfile(source, target)
    after = source.stat()
    stable = (
        before.st_dev == after.st_dev
        and before.st_ino == after.st_ino
        and before.st_size == after.st_size
        and before.st_mtime_ns == after.st_mtime_ns
    )
    if not stable:
        target.unlink(missing_ok=True)
        raise RuntimeError("source transcript changed during snapshot copy")
    return {
        "stable_during_copy": True,
        "source_bytes": int(before.st_size),
        "snapshot_bytes": int(target.stat().st_size),
        "source_unchanged": True,
    }


def mirror_session(
    *,
    aoa_root: Path,
    workspace: Path,
    transcript: Path,
    session_id: str,
) -> dict[str, Any]:
    session_memory.mirror_transcript_without_indexing(
        aoa_root=aoa_root,
        event={
            "session_id": session_id,
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Benchmark",
        },
        transcript_path=transcript,
        hook_event_name="Benchmark",
        now=session_memory.utc_now(),
        registry_lock_timeout_sec=0.0,
    )
    return session_memory.resolve_session_record(aoa_root, session_id)


def usage_snapshot() -> dict[str, float]:
    self_usage = resource.getrusage(resource.RUSAGE_SELF)
    child_usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    return {
        "cpu_seconds": (
            self_usage.ru_utime
            + self_usage.ru_stime
            + child_usage.ru_utime
            + child_usage.ru_stime
        ),
        "self_max_rss_kib": float(self_usage.ru_maxrss),
        "child_max_rss_kib": float(child_usage.ru_maxrss),
        "input_blocks": float(
            self_usage.ru_inblock + child_usage.ru_inblock
        ),
        "output_blocks": float(
            self_usage.ru_oublock + child_usage.ru_oublock
        ),
        "swaps": float(self_usage.ru_nswap + child_usage.ru_nswap),
    }


def _read_cgroup_counter(path: Path) -> int | str | None:
    try:
        value = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return None
    if value == "max":
        return value
    try:
        return int(value)
    except ValueError:
        return None


def cgroup_memory_snapshot(
    *,
    proc_cgroup: Path = Path("/proc/self/cgroup"),
    cgroup_root: Path = Path("/sys/fs/cgroup"),
) -> dict[str, Any]:
    """Read non-identifying cgroup-v2 memory counters for the current unit."""
    try:
        rows = proc_cgroup.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        rows = []
    relative: str | None = None
    for row in rows:
        parts = row.split(":", 2)
        if len(parts) == 3 and parts[0] == "0" and parts[1] == "":
            relative = parts[2].lstrip("/")
            break
    if relative is None:
        return {
            "available": False,
            "reason": "cgroup_v2_membership_unavailable",
        }
    base = cgroup_root / relative
    counters = {
        "memory_current_bytes": _read_cgroup_counter(
            base / "memory.current"
        ),
        "memory_peak_bytes": _read_cgroup_counter(base / "memory.peak"),
        "swap_current_bytes": _read_cgroup_counter(
            base / "memory.swap.current"
        ),
        "swap_peak_bytes": _read_cgroup_counter(
            base / "memory.swap.peak"
        ),
        "swap_max_bytes": _read_cgroup_counter(base / "memory.swap.max"),
    }
    if not any(value is not None for value in counters.values()):
        return {
            "available": False,
            "reason": "cgroup_v2_memory_counters_unavailable",
        }
    return {
        "available": True,
        **counters,
        "truth_status": "current_process_cgroup_v2_counters_without_path",
    }


def cgroup_memory_delta(
    before: dict[str, Any],
    after: dict[str, Any],
) -> dict[str, Any]:
    available = bool(before.get("available") and after.get("available"))
    if not available:
        return {
            "available": False,
            "reason": str(
                after.get("reason")
                or before.get("reason")
                or "cgroup_v2_memory_counters_unavailable"
            ),
        }

    def integer(key: str, source: dict[str, Any]) -> int | None:
        value = source.get(key)
        return value if isinstance(value, int) else None

    swap_current_before = integer("swap_current_bytes", before)
    swap_current_after = integer("swap_current_bytes", after)
    swap_peak_before = integer("swap_peak_bytes", before)
    swap_peak_after = integer("swap_peak_bytes", after)
    return {
        "available": True,
        "memory_current_before_bytes": integer(
            "memory_current_bytes", before
        ),
        "memory_current_after_bytes": integer(
            "memory_current_bytes", after
        ),
        "memory_peak_after_bytes": integer("memory_peak_bytes", after),
        "swap_current_before_bytes": swap_current_before,
        "swap_current_after_bytes": swap_current_after,
        "swap_current_delta_bytes": (
            swap_current_after - swap_current_before
            if swap_current_before is not None
            and swap_current_after is not None
            else None
        ),
        "swap_peak_before_bytes": swap_peak_before,
        "swap_peak_after_bytes": swap_peak_after,
        "swap_peak_delta_bytes": (
            max(0, swap_peak_after - swap_peak_before)
            if swap_peak_before is not None
            and swap_peak_after is not None
            else None
        ),
        "swap_max_bytes": after.get("swap_max_bytes"),
        "truth_status": "current_process_cgroup_v2_delta_without_path",
    }


def percentile(values: list[float], percentile_value: float) -> float:
    """Return a deterministic nearest-rank percentile for benchmark receipts."""
    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    rank = max(
        1,
        min(
            len(ordered),
            int((percentile_value * len(ordered) + 0.999999)),
        ),
    )
    return ordered[rank - 1]


def benchmark_run_summary(
    runs: list[dict[str, Any]],
) -> dict[str, Any]:
    wall = [float(run.get("wall_seconds") or 0.0) for run in runs]
    cpu = [float(run.get("cpu_seconds") or 0.0) for run in runs]
    cgroup_rows = [
        run.get("cgroup_memory", {})
        for run in runs
        if isinstance(run.get("cgroup_memory"), dict)
        and run.get("cgroup_memory", {}).get("available") is True
    ]
    swap_peaks = [
        int(row["swap_peak_after_bytes"])
        for row in cgroup_rows
        if isinstance(row.get("swap_peak_after_bytes"), int)
    ]
    swap_peak_growth = [
        int(row["swap_peak_delta_bytes"])
        for row in cgroup_rows
        if isinstance(row.get("swap_peak_delta_bytes"), int)
    ]
    swap_limits = {
        row.get("swap_max_bytes")
        for row in cgroup_rows
        if row.get("swap_max_bytes") is not None
    }
    return {
        "run_count": len(runs),
        "wall_seconds_p50": round(percentile(wall, 0.50), 6),
        "wall_seconds_p95": round(percentile(wall, 0.95), 6),
        "cpu_seconds_p50": round(percentile(cpu, 0.50), 6),
        "cpu_seconds_p95": round(percentile(cpu, 0.95), 6),
        "max_self_rss_kib": max(
            (int(run.get("self_max_rss_kib") or 0) for run in runs),
            default=0,
        ),
        "max_child_rss_kib": max(
            (int(run.get("child_max_rss_kib") or 0) for run in runs),
            default=0,
        ),
        "swap_delta": sum(
            int(run.get("swap_delta") or 0) for run in runs
        ),
        "cgroup_measurement_run_count": len(cgroup_rows),
        "cgroup_swap_peak_bytes": max(swap_peaks, default=None),
        "cgroup_swap_peak_growth_bytes": max(
            swap_peak_growth, default=None
        ),
        "cgroup_swap_max_bytes": (
            next(iter(swap_limits)) if len(swap_limits) == 1 else None
        ),
        "cgroup_swap_disabled": bool(
            cgroup_rows
            and len(cgroup_rows) == len(runs)
            and swap_limits == {0}
        ),
        "cgroup_swap_observed": bool(
            swap_peaks and max(swap_peaks) > 0
        ),
        "semantic_digests": sorted(
            {
                str(run.get("semantic_digest", {}).get("sha256") or "")
                for run in runs
                if isinstance(run.get("semantic_digest"), dict)
                and run.get("semantic_digest", {}).get("sha256")
            }
        ),
    }


def benchmark_build(
    *,
    aoa_root: Path,
    record: dict[str, Any],
    workers: int,
) -> dict[str, Any]:
    session_dir = session_memory.session_dir_from_record(record)
    raw_path = Path(
        session_memory.read_json(
            session_dir / "session.manifest.json", {}
        )["raw"]["path"]
    )
    raw_sha_before = session_memory.sha256_file(raw_path)
    usage_before = usage_snapshot()
    cgroup_before = cgroup_memory_snapshot()
    started = time.monotonic()
    result = session_memory.reindex_session_from_raw(
        aoa_root,
        record,
        segment_workers=workers,
    )
    wall_seconds = time.monotonic() - started
    usage_after = usage_snapshot()
    cgroup_after = cgroup_memory_snapshot()
    cpu_seconds = max(
        0.0,
        usage_after["cpu_seconds"] - usage_before["cpu_seconds"],
    )
    validation = (
        result.get("publish_result", {}).get("validation", {})
        if isinstance(result.get("publish_result"), dict)
        else {}
    )
    return {
        "status": result.get("status"),
        "action": result.get("action"),
        "diagnostics": result.get("diagnostics", []),
        "checkpoint_phase": result.get("checkpoint_phase"),
        "workers_requested": workers,
        "wall_seconds": round(wall_seconds, 6),
        "cpu_seconds": round(cpu_seconds, 6),
        "cpu_utilization_percent_of_one_core": round(
            cpu_seconds / wall_seconds * 100.0
            if wall_seconds > 0
            else 0.0,
            2,
        ),
        "self_max_rss_kib": int(usage_after["self_max_rss_kib"]),
        "child_max_rss_kib": int(usage_after["child_max_rss_kib"]),
        "input_blocks_delta": int(
            usage_after["input_blocks"] - usage_before["input_blocks"]
        ),
        "output_blocks_delta": int(
            usage_after["output_blocks"] - usage_before["output_blocks"]
        ),
        "swap_delta": int(
            usage_after["swaps"] - usage_before["swaps"]
        ),
        "cgroup_memory": cgroup_memory_delta(
            cgroup_before, cgroup_after
        ),
        "event_count": int(result.get("event_count") or 0),
        "segment_count": int(result.get("segment_count") or 0),
        "phase_timings_ms": result.get("phase_timings_ms", {}),
        "raw_block_execution": result.get(
            "raw_block_execution", {}
        ),
        "raw_scan_execution": result.get(
            "raw_scan_execution", {}
        ),
        "parent_rehydration_execution": result.get(
            "parent_rehydration_execution", {}
        ),
        "classification_execution": result.get(
            "classification_execution", {}
        ),
        "segment_execution": result.get("segment_execution", {}),
        "session_index_execution": result.get(
            "session_index_execution", {}
        ),
        "projection_validation": {
            "raw_validation_mode": validation.get(
                "raw_validation_mode"
            ),
            "raw_block_validation": validation.get(
                "raw_block_validation", {}
            ),
        },
        "semantic_digest": validation.get("semantic_digest", {}),
        "raw_sha256_before": raw_sha_before,
        "raw_sha256_after": session_memory.sha256_file(raw_path),
        "raw_unchanged": (
            raw_sha_before == session_memory.sha256_file(raw_path)
        ),
    }


def benchmark_receipt_base(
    args: argparse.Namespace,
    *,
    raw_bytes: int,
) -> dict[str, Any]:
    source_transcript = bool(args.source_transcript)
    fixture: dict[str, Any] = {
        "synthetic": not source_transcript,
        "source_kind": (
            "read_only_captured_snapshot"
            if source_transcript
            else "synthetic_live_equivalent"
        ),
        "fixture_alias": str(args.fixture_alias or ""),
        "raw_bytes": raw_bytes,
        "fresh_segments": args.fresh_segments,
        "growth_segments": args.growth_segments,
        "repetitions": args.repetitions,
        "serial_repetitions": args.serial_repetitions,
        "parallel_repetitions": args.parallel_repetitions,
    }
    if source_transcript:
        fixture["snapshot_copy"] = dict(
            getattr(args, "source_snapshot", {}) or {}
        )
    else:
        fixture.update(
            {
                "segments_requested": args.segments,
                "payload_bytes_per_primary_event": args.payload_bytes,
                "events_per_segment": args.events_per_segment,
            }
        )
    return {
        "schema_version": 1,
        "artifact_type": "session_projection_incremental_benchmark",
        "generated_at": session_memory.utc_now(),
        "fixture": fixture,
        "host": {
            "cpu_count": os.cpu_count(),
            "affinity_cpu_count": (
                len(os.sched_getaffinity(0))
                if hasattr(os, "sched_getaffinity")
                else None
            ),
            "python": sys.version.split()[0],
        },
        "truth_status": (
            "read_only_snapshot_measurement_not_live_runtime_mutation"
            if source_transcript
            else "synthetic_target_host_measurement_not_live_archive_freshness"
        ),
    }


def write_partial_receipt(
    args: argparse.Namespace,
    *,
    raw_bytes: int,
    completed_runs: dict[str, Any],
) -> None:
    if not args.output:
        return
    payload = {
        **benchmark_receipt_base(args, raw_bytes=raw_bytes),
        "ok": False,
        "status": "partial",
        "completed_runs": list(completed_runs),
        **completed_runs,
    }
    session_memory.write_json(Path(args.output), payload)


def run_benchmark(args: argparse.Namespace) -> dict[str, Any]:
    temp_parent = Path(args.temp_root).resolve() if args.temp_root else None
    if temp_parent is not None:
        temp_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="aoa-session-projection-benchmark-",
        dir=str(temp_parent) if temp_parent is not None else None,
    ) as temp_value:
        root = Path(temp_value)
        workspace = root / "AbyssOS"
        workspace.mkdir(parents=True)
        transcript = root / "representative.jsonl"
        if args.source_transcript:
            source = Path(args.source_transcript).resolve()
            args.source_snapshot = copy_stable_source_snapshot(
                source, transcript
            )
            session_id = transcript_session_id(transcript)
        else:
            session_id = "benchmark-representative"
            write_jsonl(
                transcript,
                synthetic_rows(
                    session_id=session_id,
                    cwd=workspace,
                    segments=args.segments,
                    payload_bytes=args.payload_bytes,
                    events_per_segment=args.events_per_segment,
                ),
            )
        raw_bytes = transcript.stat().st_size

        benchmark_root = workspace / "benchmark" / ".aoa"
        serial_record = mirror_session(
            aoa_root=benchmark_root,
            workspace=workspace,
            transcript=transcript,
            session_id=session_id,
        )
        baseline_snapshot = root / "cold-baseline-snapshot"
        shutil.copytree(benchmark_root, baseline_snapshot)
        serial_runs: list[dict[str, Any]] = []
        parallel_runs: list[dict[str, Any]] = []
        completed_runs: dict[str, Any] = {}
        parallel_record = serial_record
        for _repetition in range(args.serial_repetitions):
            # Reset only the benchmark-owned temporary projection root so
            # every run starts from the exact same captured authority and
            # metadata at the same logical paths.
            shutil.rmtree(benchmark_root)
            shutil.copytree(baseline_snapshot, benchmark_root)
            serial_record = session_memory.resolve_session_record(
                benchmark_root, session_id
            )
            serial_runs.append(
                benchmark_build(
                    aoa_root=benchmark_root,
                    record=serial_record,
                    workers=1,
                )
            )
            completed_runs["cold_serial_runs"] = serial_runs
            write_partial_receipt(
                args,
                raw_bytes=raw_bytes,
                completed_runs=completed_runs,
            )

        for _repetition in range(args.parallel_repetitions):
            shutil.rmtree(benchmark_root)
            shutil.copytree(baseline_snapshot, benchmark_root)
            parallel_record = session_memory.resolve_session_record(
                benchmark_root, session_id
            )
            parallel_runs.append(
                benchmark_build(
                    aoa_root=benchmark_root,
                    record=parallel_record,
                    workers=args.workers,
                )
            )
            completed_runs["cold_parallel_runs"] = parallel_runs
            write_partial_receipt(
                args,
                raw_bytes=raw_bytes,
                completed_runs=completed_runs,
            )
        serial = serial_runs[0] if serial_runs else None
        parallel = parallel_runs[0]

        fresh_transcript = root / "fresh.jsonl"
        write_jsonl(
            fresh_transcript,
            synthetic_rows(
                session_id="benchmark-fresh",
                cwd=workspace,
                segments=args.fresh_segments,
                payload_bytes=min(args.payload_bytes, 4096),
                events_per_segment=args.events_per_segment,
                start_minute=1,
            ),
        )
        fresh_record = mirror_session(
            aoa_root=benchmark_root,
            workspace=workspace,
            transcript=fresh_transcript,
            session_id="benchmark-fresh",
        )
        fresh = benchmark_build(
            aoa_root=benchmark_root,
            record=fresh_record,
            workers=args.workers,
        )
        completed_runs["fresh_session"] = fresh
        write_partial_receipt(
            args,
            raw_bytes=raw_bytes,
            completed_runs=completed_runs,
        )

        parallel_session_dir = session_memory.session_dir_from_record(
            parallel_record
        )
        growth_rows = synthetic_rows(
                session_id="benchmark-tail",
                cwd=workspace,
                segments=args.growth_segments,
                payload_bytes=min(args.payload_bytes, 4096),
                events_per_segment=args.events_per_segment,
                start_minute=2,
            )
        next(growth_rows, None)
        with transcript.open("a", encoding="utf-8") as handle:
            for row in growth_rows:
                handle.write(
                    json.dumps(
                        row,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                    + "\n"
                )
        growth_manifest = session_memory.read_json(
            parallel_session_dir / "session.manifest.json", {}
        )
        capture = session_memory.preserve_unindexed_raw_capture(
            session_dir=parallel_session_dir,
            session_id=session_id,
            transcript_path=transcript,
            manifest=growth_manifest,
            hook_event_name="BenchmarkAppend",
            now=session_memory.utc_now(),
        )
        growing = benchmark_build(
            aoa_root=benchmark_root,
            record=parallel_record,
            workers=args.workers,
        )
        growing["capture_execution"] = {
            "appended_bytes": int(capture.get("appended_bytes") or 0),
            "appended_block_count": int(
                capture.get("appended_block_count") or 0
            ),
            "sha256_state_bootstrap_bytes_read": int(
                capture.get("sha256_state_bootstrap_bytes_read") or 0
            ),
            "sha256_delta_bytes_hashed": int(
                capture.get("sha256_delta_bytes_hashed") or 0
            ),
        }
        completed_runs["growing_session"] = growing
        write_partial_receipt(
            args,
            raw_bytes=raw_bytes,
            completed_runs=completed_runs,
        )

    serial_summary = benchmark_run_summary(serial_runs)
    parallel_summary = benchmark_run_summary(parallel_runs)
    serial_digests = set(serial_summary["semantic_digests"])
    parallel_digests = set(parallel_summary["semantic_digests"])
    serial_digest = next(iter(serial_digests), "")
    parallel_digest = next(iter(parallel_digests), "")
    speedup = (
        float(serial_summary["wall_seconds_p50"])
        / float(parallel_summary["wall_seconds_p50"])
        if serial_runs
        and float(parallel_summary["wall_seconds_p50"]) > 0
        else 0.0
    )
    parallel_internal_parity = bool(
        parallel_digest and len(parallel_digests) == 1
    )
    serial_parallel_parity = (
        bool(
            serial_digest
            and serial_digests == parallel_digests
            and len(serial_digests) == 1
        )
        if serial_runs
        else None
    )
    return {
        **benchmark_receipt_base(args, raw_bytes=raw_bytes),
        "ok": bool(
            (not serial_runs or all(
                run.get("status") == "reindexed"
                for run in serial_runs
            ))
            and all(
                run.get("status") == "reindexed"
                for run in parallel_runs
            )
            and fresh.get("status") == "reindexed"
            and growing.get("status") == "reindexed"
            and parallel_internal_parity
            and (
                serial_parallel_parity is True
                if serial_runs
                else True
            )
            and all(
                run.get("raw_unchanged") is True
                for run in serial_runs + parallel_runs
            )
        ),
        "status": "complete",
        "cold_serial": serial,
        "cold_parallel": parallel,
        "cold_serial_runs": serial_runs,
        "cold_parallel_runs": parallel_runs,
        "cold_serial_summary": serial_summary,
        "cold_parallel_summary": parallel_summary,
        "fresh_session": fresh,
        "growing_session": growing,
        "serial_parallel_semantic_parity": serial_parallel_parity,
        "parallel_internal_semantic_parity": parallel_internal_parity,
        "parallel_speedup": round(speedup, 4),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--segments", type=int, default=40)
    parser.add_argument("--payload-bytes", type=int, default=4096)
    parser.add_argument("--events-per-segment", type=int, default=2)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--fresh-segments", type=int, default=2)
    parser.add_argument("--growth-segments", type=int, default=2)
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument(
        "--serial-repetitions",
        type=int,
        help="Override cold serial repetitions; zero admits parallel-only receipts.",
    )
    parser.add_argument(
        "--parallel-repetitions",
        type=int,
        help="Override cold worker-pool repetitions; must remain positive.",
    )
    parser.add_argument(
        "--source-transcript",
        help=(
            "Read-only raw JSONL source. The benchmark copies a stable "
            "snapshot and never writes the supplied path."
        ),
    )
    parser.add_argument(
        "--fixture-alias",
        default="",
        help="Public-safe receipt label; source paths and session ids are omitted.",
    )
    parser.add_argument("--temp-root")
    parser.add_argument("--output")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    args.serial_repetitions = (
        args.repetitions
        if args.serial_repetitions is None
        else args.serial_repetitions
    )
    args.parallel_repetitions = (
        args.repetitions
        if args.parallel_repetitions is None
        else args.parallel_repetitions
    )
    if (
        args.segments < 1
        or args.fresh_segments < 1
        or args.events_per_segment < 1
        or args.repetitions < 1
        or args.serial_repetitions < 0
        or args.parallel_repetitions < 1
    ):
        raise SystemExit("segment counts must be positive")
    if args.payload_bytes < 0 or not 1 <= args.workers <= 6:
        raise SystemExit("payload must be nonnegative and workers must be 1..6")
    if args.source_transcript and not Path(args.source_transcript).is_file():
        raise SystemExit("source transcript must be a readable file")
    payload = run_benchmark(args)
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
