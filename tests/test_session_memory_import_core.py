from __future__ import annotations

import importlib.util
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType

import pytest


ROOT = Path(__file__).resolve().parents[1]
IMPORT_CORE = ROOT / "scripts" / "aoa_session_memory_import.py"


def load_import_core() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "aoa_session_memory_import_test_source",
        IMPORT_CORE,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


module = load_import_core()


def write_transcript(
    path: Path,
    *,
    session_id: str,
    timestamp: str,
    body: str = "event",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                '{"type":"session_meta","payload":'
                f'{{"id":"{session_id}","timestamp":"{timestamp}",'
                '"cwd":"/tmp/workspace"}}',
                f'{{"type":"event","body":"{body}"}}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def epoch(value: str) -> float:
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc).timestamp()


def candidate_record(path: Path) -> dict[str, object]:
    """Records for these synthetic fixtures, not another production parser."""
    payload = json.loads(path.read_text().splitlines()[0])["payload"]
    return {
        "session_id": payload["id"],
        "transcript_path": str(path),
        "session_date": payload["timestamp"][:10],
        "timestamp": payload["timestamp"],
    }


def unexpected_size_prefilter(*_args: object) -> dict[str, object]:
    pytest.fail("a transcript inside the size lane must use the producer probe")


def test_date_helpers_keep_bounded_normalization_and_reject_invalid_values() -> None:
    assert module.parse_date_arg("rollout_2026-09-07.jsonl") == "2026-09-07"
    assert module.parse_date_arg("20260907") == "2026-09-07"
    assert module.parse_timestamp_arg("2026-09-07") == "2026-09-07T00:00:00.000000Z"
    assert module.parse_timestamp_arg("2026-09-07T03:04:05-02:00") == (
        "2026-09-07T05:04:05.000000Z"
    )
    with pytest.raises(ValueError):
        module.parse_date_arg("not-a-date")
    with pytest.raises(ValueError):
        module.parse_timestamp_arg("not-a-timestamp")


def test_path_date_hint_uses_nested_codex_date_directories(tmp_path: Path) -> None:
    source_root = tmp_path / "sessions"
    transcript = source_root / "2026" / "09" / "07" / "rollout.jsonl"
    assert module.transcript_path_date_hint(transcript, source_root) == "2026-09-07"
    named = source_root / "rollout-2026_09_08.jsonl"
    assert module.transcript_path_date_hint(named, source_root) == "2026-09-08"
    invalid = source_root / "2026" / "99" / "99" / "rollout.jsonl"
    assert module.transcript_path_date_hint(invalid, source_root) is None


def test_discovery_applies_date_and_activity_windows_with_deterministic_order(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "sessions"
    old = source_root / "2026" / "09" / "01" / "old.jsonl"
    in_window = source_root / "2026" / "09" / "07" / "in-window.jsonl"
    active_old = source_root / "2026" / "08" / "31" / "active-old.jsonl"
    write_transcript(old, session_id="old", timestamp="2026-09-01T00:00:00Z")
    write_transcript(
        in_window,
        session_id="in-window",
        timestamp="2026-09-07T00:00:00Z",
    )
    write_transcript(
        active_old,
        session_id="active-old",
        timestamp="2026-08-31T00:00:00Z",
    )
    old_mtime = epoch("2026-09-01T00:00:00")
    active_mtime = epoch("2026-09-09T00:00:00")
    os.utime(old, (old_mtime, old_mtime))
    os.utime(in_window, (old_mtime, old_mtime))
    os.utime(active_old, (active_mtime, active_mtime))

    records = module.discover_codex_transcripts(
        source_root=source_root,
        transcript_probe=candidate_record,
        transcript_size_prefilter_record=unexpected_size_prefilter,
        since="2026-09-07",
        activity_since_epoch=epoch("2026-09-08T00:00:00"),
    )

    assert [item["session_id"] for item in records] == ["active-old", "in-window"]
    assert records[0]["selection_source"] == "activity_mtime_supplement"
    assert records[0]["activity_window_match"] is True
    assert records[1]["selection_source"] == "date_window"
    assert records[1]["activity_window_match"] is False


def test_discovery_size_lane_uses_identity_prefilter_without_full_probe(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "sessions"
    small = source_root / "2026" / "09" / "07" / "small.jsonl"
    normal = source_root / "2026" / "09" / "07" / "normal.jsonl"
    write_transcript(small, session_id="small", timestamp="2026-09-07T00:00:00Z")
    write_transcript(normal, session_id="normal", timestamp="2026-09-07T01:00:00Z")
    probe_calls: list[str] = []
    prefilter_calls: list[str] = []

    def probe(path: Path) -> dict[str, object]:
        probe_calls.append(path.name)
        return {
            "session_id": path.stem,
            "transcript_path": str(path),
            "session_date": "2026-09-07",
            "timestamp": "2026-09-07T01:00:00Z",
        }

    def prefilter(
        path: Path,
        stat_result: os.stat_result,
        path_date: str | None,
    ) -> dict[str, object]:
        prefilter_calls.append(path.name)
        return {
            "session_id": path.stem,
            "transcript_path": str(path),
            "session_date": path_date,
            "timestamp": None,
        }

    records = module.discover_codex_transcripts(
        source_root=source_root,
        min_raw_bytes=normal.stat().st_size + 1,
        transcript_probe=probe,
        transcript_size_prefilter_record=prefilter,
    )

    assert probe_calls == []
    assert prefilter_calls == ["normal.jsonl", "small.jsonl"]
    assert [item["session_id"] for item in records] == ["normal", "small"]


def test_discovery_reads_current_bytes_on_same_size_and_mtime_mutation(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "sessions"
    transcript = source_root / "2026" / "09" / "07" / "rollout.jsonl"
    write_transcript(
        transcript,
        session_id="alpha",
        timestamp="2026-09-07T00:00:00Z",
        body="alpha",
    )
    original_stat = transcript.stat()
    seen: list[str] = []

    def probe(path: Path) -> dict[str, object]:
        body = path.read_text(encoding="utf-8")
        seen.append(body)
        return {
            "session_id": "alpha" if "alpha" in body else "bravo",
            "transcript_path": str(path),
            "session_date": "2026-09-07",
            "timestamp": "2026-09-07T00:00:00Z",
        }

    first = module.discover_codex_transcripts(
        source_root=source_root,
        transcript_probe=probe,
        transcript_size_prefilter_record=unexpected_size_prefilter,
    )
    assert first[0]["session_id"] == "alpha"

    write_transcript(
        transcript,
        session_id="bravo",
        timestamp="2026-09-07T00:00:00Z",
        body="bravo",
    )
    assert transcript.stat().st_size == original_stat.st_size
    os.utime(transcript, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))

    second = module.discover_codex_transcripts(
        source_root=source_root,
        transcript_probe=probe,
        transcript_size_prefilter_record=unexpected_size_prefilter,
    )
    assert second[0]["session_id"] == "bravo"
    assert len(seen) == 2
    assert "bravo" in seen[1]
