#!/usr/bin/env python3
"""Reproducible synthetic benchmark for incremental session projection work."""

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
from typing import Any

import aoa_session_memory as session_memory


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
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
    start_minute: int = 0,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = [
        {
            "timestamp": f"2026-08-08T12:{start_minute:02d}:00Z",
            "type": "session_meta",
            "payload": {"id": session_id, "cwd": str(cwd)},
        }
    ]
    filler = "x" * max(0, payload_bytes)
    for ordinal in range(max(1, segments)):
        second = ordinal % 50 + 1
        rows.extend(
            [
                {
                    "timestamp": f"2026-08-08T12:{start_minute:02d}:{second:02d}Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": (
                                    f"benchmark segment {ordinal} " + filler
                                ),
                            }
                        ],
                    },
                },
                {
                    "timestamp": f"2026-08-08T12:{start_minute:02d}:{second:02d}Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {
                                "type": "output_text",
                                "text": f"completed segment {ordinal}",
                            }
                        ],
                    },
                },
                {
                    "timestamp": f"2026-08-08T12:{start_minute:02d}:{second:02d}Z",
                    "type": "turn_context",
                    "payload": {"summary": f"boundary {ordinal}"},
                },
            ]
        )
    return rows


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
    started = time.monotonic()
    result = session_memory.reindex_session_from_raw(
        aoa_root,
        record,
        segment_workers=workers,
    )
    wall_seconds = time.monotonic() - started
    usage_after = usage_snapshot()
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
        "event_count": int(result.get("event_count") or 0),
        "segment_count": int(result.get("segment_count") or 0),
        "phase_timings_ms": result.get("phase_timings_ms", {}),
        "raw_block_execution": result.get(
            "raw_block_execution", {}
        ),
        "segment_execution": result.get("segment_execution", {}),
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
    return {
        "schema_version": 1,
        "artifact_type": "session_projection_incremental_benchmark",
        "generated_at": session_memory.utc_now(),
        "fixture": {
            "synthetic": True,
            "raw_bytes": raw_bytes,
            "segments_requested": args.segments,
            "payload_bytes_per_primary_event": args.payload_bytes,
            "fresh_segments": args.fresh_segments,
            "growth_segments": args.growth_segments,
        },
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
            "synthetic_target_host_measurement_not_live_archive_freshness"
        ),
    }


def write_partial_receipt(
    args: argparse.Namespace,
    *,
    raw_bytes: int,
    completed_runs: dict[str, dict[str, Any]],
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
        write_jsonl(
            transcript,
            synthetic_rows(
                session_id="benchmark-representative",
                cwd=workspace,
                segments=args.segments,
                payload_bytes=args.payload_bytes,
            ),
        )
        raw_bytes = transcript.stat().st_size

        benchmark_root = workspace / "benchmark" / ".aoa"
        serial_record = mirror_session(
            aoa_root=benchmark_root,
            workspace=workspace,
            transcript=transcript,
            session_id="benchmark-representative",
        )
        baseline_snapshot = root / "cold-baseline-snapshot"
        shutil.copytree(benchmark_root, baseline_snapshot)
        serial = benchmark_build(
            aoa_root=benchmark_root,
            record=serial_record,
            workers=1,
        )
        completed_runs = {"cold_serial": serial}
        write_partial_receipt(
            args,
            raw_bytes=raw_bytes,
            completed_runs=completed_runs,
        )
        # Reset only the benchmark-owned temporary projection root so the
        # parallel run is a true cold build from the exact same captured
        # authority and metadata at the same logical paths.
        shutil.rmtree(benchmark_root)
        shutil.copytree(baseline_snapshot, benchmark_root)
        parallel_record = session_memory.resolve_session_record(
            benchmark_root, "benchmark-representative"
        )
        parallel = benchmark_build(
            aoa_root=benchmark_root,
            record=parallel_record,
            workers=args.workers,
        )
        completed_runs["cold_parallel"] = parallel
        write_partial_receipt(
            args,
            raw_bytes=raw_bytes,
            completed_runs=completed_runs,
        )

        fresh_transcript = root / "fresh.jsonl"
        write_jsonl(
            fresh_transcript,
            synthetic_rows(
                session_id="benchmark-fresh",
                cwd=workspace,
                segments=args.fresh_segments,
                payload_bytes=min(args.payload_bytes, 4096),
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
        growing_raw_path = Path(
            session_memory.read_json(
                parallel_session_dir / "session.manifest.json", {}
            )["raw"]["path"]
        )
        with growing_raw_path.open("a", encoding="utf-8") as handle:
            for row in synthetic_rows(
                session_id="benchmark-tail",
                cwd=workspace,
                segments=args.growth_segments,
                payload_bytes=min(args.payload_bytes, 4096),
                start_minute=2,
            )[1:]:
                handle.write(
                    json.dumps(
                        row,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                    + "\n"
                )
        growing = benchmark_build(
            aoa_root=benchmark_root,
            record=parallel_record,
            workers=args.workers,
        )
        completed_runs["growing_session"] = growing
        write_partial_receipt(
            args,
            raw_bytes=raw_bytes,
            completed_runs=completed_runs,
        )

    serial_digest = str(
        serial.get("semantic_digest", {}).get("sha256") or ""
    )
    parallel_digest = str(
        parallel.get("semantic_digest", {}).get("sha256") or ""
    )
    speedup = (
        float(serial["wall_seconds"]) / float(parallel["wall_seconds"])
        if float(parallel["wall_seconds"]) > 0
        else 0.0
    )
    return {
        **benchmark_receipt_base(args, raw_bytes=raw_bytes),
        "ok": bool(
            serial.get("status") == "reindexed"
            and parallel.get("status") == "reindexed"
            and fresh.get("status") == "reindexed"
            and growing.get("status") == "reindexed"
            and serial_digest
            and serial_digest == parallel_digest
            and serial.get("raw_unchanged") is True
            and parallel.get("raw_unchanged") is True
        ),
        "status": "complete",
        "cold_serial": serial,
        "cold_parallel": parallel,
        "fresh_session": fresh,
        "growing_session": growing,
        "serial_parallel_semantic_parity": serial_digest == parallel_digest,
        "parallel_speedup": round(speedup, 4),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--segments", type=int, default=40)
    parser.add_argument("--payload-bytes", type=int, default=4096)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--fresh-segments", type=int, default=2)
    parser.add_argument("--growth-segments", type=int, default=2)
    parser.add_argument("--temp-root")
    parser.add_argument("--output")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.segments < 1 or args.fresh_segments < 1:
        raise SystemExit("segment counts must be positive")
    if args.payload_bytes < 0 or not 1 <= args.workers <= 6:
        raise SystemExit("payload must be nonnegative and workers must be 1..6")
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
