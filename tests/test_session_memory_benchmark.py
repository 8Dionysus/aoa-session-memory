from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import types
from pathlib import Path
from typing import Any, Iterable

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_SCRIPT = REPO_ROOT / "scripts" / "benchmark_session_projection.py"


benchmark_spec = importlib.util.spec_from_file_location(
    "session_projection_benchmark",
    BENCHMARK_SCRIPT,
)
assert benchmark_spec and benchmark_spec.loader
benchmark_module = importlib.util.module_from_spec(benchmark_spec)
sys.modules["session_projection_benchmark"] = benchmark_module
benchmark_spec.loader.exec_module(benchmark_module)


def write_jsonl(
    path: Path,
    rows: Iterable[dict[str, Any]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(
                json.dumps(row, ensure_ascii=False, separators=(",", ":"))
                + "\n"
            )


def test_session_projection_benchmark_ignores_foreign_cached_runtime_module(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    foreign_path = tmp_path / "foreign" / "aoa_session_memory.py"
    foreign_path.parent.mkdir()
    foreign_path.write_text("# foreign sentinel\n", encoding="utf-8")
    foreign = types.ModuleType("aoa_session_memory")
    foreign.__file__ = str(foreign_path)
    foreign.foreign_sentinel = True
    monkeypatch.setitem(sys.modules, "aoa_session_memory", foreign)
    private_name = "_aoa_session_memory_benchmark_source"
    monkeypatch.setitem(sys.modules, private_name, None)
    monkeypatch.setattr(benchmark_module, "session_memory", None)

    calls: list[tuple[str, Path]] = []

    class FakeLoader:
        def create_module(self, spec: Any) -> types.ModuleType:
            return types.ModuleType(spec.name)

        def exec_module(self, module: types.ModuleType) -> None:
            module.__file__ = str(
                BENCHMARK_SCRIPT.with_name("aoa_session_memory.py")
            )
            module.loaded_from_private_spec = True

    def fake_spec_from_file_location(
        name: str,
        path: str | Path,
        **_: Any,
    ) -> Any:
        calls.append((name, Path(path).resolve()))
        return importlib.util.spec_from_loader(
            name,
            FakeLoader(),
            origin=str(path),
        )

    monkeypatch.setattr(
        benchmark_module.importlib.util,
        "spec_from_file_location",
        fake_spec_from_file_location,
    )

    loaded = benchmark_module._session_memory_module()

    assert loaded is not foreign
    assert loaded.loaded_from_private_spec is True
    assert calls == [
        (
            private_name,
            BENCHMARK_SCRIPT.with_name("aoa_session_memory.py").resolve(),
        )
    ]
    assert sys.modules["aoa_session_memory"] is foreign


def test_session_projection_benchmark_smoke_proves_parity_and_reuse(
    tmp_path: Path,
) -> None:
    receipt_path = tmp_path / "benchmark-receipt.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(BENCHMARK_SCRIPT),
            "--segments",
            "3",
            "--payload-bytes",
            "64",
            "--workers",
            "2",
            "--fresh-segments",
            "1",
            "--growth-segments",
            "1",
            "--live-route-repetitions",
            "3",
            "--temp-root",
            str(tmp_path),
            "--output",
            str(receipt_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)

    assert completed.returncode == 0, completed.stderr
    assert payload["ok"] is True
    assert payload["status"] == "complete"
    assert json.loads(receipt_path.read_text(encoding="utf-8")) == payload
    assert payload["serial_parallel_semantic_parity"] is True
    assert payload["cold_serial"]["raw_unchanged"] is True
    assert payload["cold_parallel"]["raw_unchanged"] is True
    assert payload["cold_serial_summary"]["run_count"] == 1
    assert payload["cold_parallel_summary"]["run_count"] == 1
    assert payload["cold_serial_summary"]["wall_seconds_p95"] > 0
    assert payload["cold_parallel_summary"]["wall_seconds_p95"] > 0
    assert payload["initial_capture_execution"]["postings"][
        "historical_raw_bytes_read"
    ] == 0
    assert payload["live_route"]["ok"] is True
    assert payload["live_route"]["run_count"] == 3
    assert payload["live_route"]["overlay_p95_within_30_seconds"] is True
    assert payload["live_route"][
        "event_availability_p95_within_5_seconds"
    ] is True
    assert payload["live_route"]["historical_raw_bytes_read"] == 0
    assert payload["live_route"]["max_shards_read_for_update"] <= 1
    assert payload["live_route"]["max_posting_shards_examined"] <= 1
    assert payload["cold_parallel_summary"][
        "cgroup_measurement_run_count"
    ] in {0, 1}
    assert "cgroup_memory" in payload["cold_parallel"]
    assert "available" in payload["cold_parallel"]["cgroup_memory"]
    assert payload["growing_session"]["capture_execution"][
        "appended_bytes"
    ] == payload["growing_session"]["capture_execution"][
        "sha256_delta_bytes_hashed"
    ]
    growing_gate = payload["growing_incremental_gate"]
    assert growing_gate["ok"] is True
    assert 0 <= growing_gate[
        "sha256_state_bootstrap_bytes_read"
    ] < 64
    assert growing_gate["maximum_sha256_state_bootstrap_bytes"] == 63
    assert growing_gate["prefix_bytes_reused"] == payload["fixture"][
        "raw_bytes"
    ]
    assert growing_gate["tail_bytes_read"] == growing_gate[
        "appended_bytes"
    ]
    assert growing_gate["source_bytes_read"] <= growing_gate[
        "appended_bytes"
    ] + 1
    assert payload["growing_session"]["raw_scan_execution"][
        "scan_mode"
    ] == "attested_prefix_plus_captured_tail_v1"
    assert payload["growing_session"]["segment_execution"][
        "published_reused_segment_count"
    ] >= 2
    assert payload["growing_session"]["raw_block_execution"][
        "reused_block_count"
    ] >= 2
    for cold_run in (
        payload["cold_serial"],
        payload["cold_parallel"],
    ):
        assert cold_run["raw_block_execution"][
            "token_accounting_mode"
        ] == "derived_from_segment_components_v1"
        assert cold_run["raw_block_execution"][
            "segment_summary_backfill_count"
        ] == cold_run["segment_count"]
        assert cold_run["raw_block_execution"][
            "token_accounting_ms"
        ] < 100
        assert cold_run["projection_validation"][
            "raw_block_validation"
        ] == {
            "metadata_receipt_admitted_count": cold_run[
                "segment_count"
            ],
            "reused_last_good_count": 0,
            "full_sha256_count": 0,
            "policy": (
                "metadata_receipt_or_samefile_reuse_else_full_sha256_v1"
            ),
        }


def test_session_projection_benchmark_uses_stable_read_only_snapshot(
    tmp_path: Path,
) -> None:
    source = tmp_path / "owner-snapshot.raw.jsonl"
    write_jsonl(
        source,
        [
            {
                "timestamp": "2026-08-08T12:00:00Z",
                "type": "session_meta",
                "payload": {
                    "id": "private-source-id-not-in-receipt",
                    "cwd": str(tmp_path / "owner"),
                },
            },
            {
                "timestamp": "2026-08-08T12:00:01Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": "snapshot task"}
                    ],
                },
            },
            {
                "timestamp": "2026-08-08T12:00:02Z",
                "type": "turn_context",
                "payload": {"summary": "snapshot boundary"},
            },
        ],
    )
    source_before = hashlib.sha256(source.read_bytes()).hexdigest()
    completed = subprocess.run(
        [
            sys.executable,
            str(BENCHMARK_SCRIPT),
            "--source-transcript",
            str(source),
            "--fixture-alias",
            "read-only-owner-snapshot",
            "--payload-bytes",
            "64",
            "--workers",
            "2",
            "--fresh-segments",
            "1",
            "--growth-segments",
            "1",
            "--capture-only",
            "--temp-root",
            str(tmp_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)

    assert completed.returncode == 0, completed.stderr
    assert payload["ok"] is True
    assert payload["fixture"]["synthetic"] is False
    assert payload["fixture"]["source_kind"] == (
        "read_only_captured_snapshot"
    )
    assert payload["fixture"]["snapshot_copy"] == {
        "stable_during_copy": True,
        "source_bytes": source.stat().st_size,
        "snapshot_bytes": source.stat().st_size,
        "source_unchanged": True,
    }
    assert payload["truth_status"] == (
        "read_only_snapshot_measurement_not_live_runtime_mutation"
    )
    assert "private-source-id-not-in-receipt" not in completed.stdout
    assert str(source) not in completed.stdout
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_before


def test_session_projection_benchmark_supports_parallel_only_repetitions(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: Any,
) -> None:
    # The smoke test above keeps the real subprocess/CLI boundary covered.
    # Exercise this option matrix in-process so the suite does not pay for a
    # second interpreter importing the 10 MB projection module.
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(BENCHMARK_SCRIPT),
            "--segments",
            "2",
            "--payload-bytes",
            "32",
            "--workers",
            "2",
            "--fresh-segments",
            "1",
            "--growth-segments",
            "1",
            "--serial-repetitions",
            "0",
            "--parallel-repetitions",
            "2",
            "--cold-only",
            "--temp-root",
            str(tmp_path),
        ],
    )
    exit_code = benchmark_module.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["status"] == "cold_only_complete"
    assert payload["fixture"]["cold_only"] is True
    assert payload["cold_serial"] is None
    assert payload["cold_serial_summary"]["run_count"] == 0
    assert payload["cold_parallel_summary"]["run_count"] == 2
    assert payload["serial_parallel_semantic_parity"] is None
    assert payload["parallel_internal_semantic_parity"] is True
    assert "fresh_session" not in payload
    assert "growing_session" not in payload


def test_session_projection_benchmark_reads_cgroup_v2_without_path(
    tmp_path: Path,
) -> None:
    cgroup_root = tmp_path / "cgroup"
    unit_root = cgroup_root / "user.slice" / "benchmark.scope"
    unit_root.mkdir(parents=True)
    proc_cgroup = tmp_path / "proc-self-cgroup"
    proc_cgroup.write_text(
        "0::/user.slice/benchmark.scope\n", encoding="utf-8"
    )
    counters = {
        "memory.current": "1024\n",
        "memory.peak": "4096\n",
        "memory.swap.current": "0\n",
        "memory.swap.peak": "0\n",
        "memory.swap.max": "0\n",
    }
    for name, value in counters.items():
        (unit_root / name).write_text(value, encoding="utf-8")

    snapshot = benchmark_module.cgroup_memory_snapshot(
        proc_cgroup=proc_cgroup,
        cgroup_root=cgroup_root,
    )

    assert snapshot == {
        "available": True,
        "memory_current_bytes": 1024,
        "memory_peak_bytes": 4096,
        "swap_current_bytes": 0,
        "swap_peak_bytes": 0,
        "swap_max_bytes": 0,
        "truth_status": (
            "current_process_cgroup_v2_counters_without_path"
        ),
    }
    assert "benchmark.scope" not in json.dumps(snapshot)


def test_session_projection_benchmark_summarizes_cgroup_swap_gate() -> None:
    summary = benchmark_module.benchmark_run_summary(
        [
            {
                "wall_seconds": 1.0,
                "cpu_seconds": 2.0,
                "cgroup_memory": {
                    "available": True,
                    "swap_peak_after_bytes": 0,
                    "swap_peak_delta_bytes": 0,
                    "swap_max_bytes": 0,
                },
            },
            {
                "wall_seconds": 2.0,
                "cpu_seconds": 3.0,
                "cgroup_memory": {
                    "available": True,
                    "swap_peak_after_bytes": 0,
                    "swap_peak_delta_bytes": 0,
                    "swap_max_bytes": 0,
                },
            },
        ]
    )

    assert summary["cgroup_measurement_run_count"] == 2
    assert summary["cgroup_swap_peak_bytes"] == 0
    assert summary["cgroup_swap_peak_growth_bytes"] == 0
    assert summary["cgroup_swap_max_bytes"] == 0
    assert summary["cgroup_swap_disabled"] is True
    assert summary["cgroup_swap_observed"] is False


def test_session_projection_benchmark_capture_only_proves_live_route(
    tmp_path: Path,
) -> None:
    receipt_path = tmp_path / "capture-only-receipt.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(BENCHMARK_SCRIPT),
            "--segments",
            "3",
            "--payload-bytes",
            "64",
            "--capture-only",
            "--live-route-repetitions",
            "3",
            "--temp-root",
            str(tmp_path),
            "--output",
            str(receipt_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)

    assert completed.returncode == 0, completed.stderr
    assert payload["ok"] is True
    assert payload["status"] == "capture_only_complete"
    assert json.loads(receipt_path.read_text(encoding="utf-8")) == payload
    assert payload["initial_capture_execution"]["raw_bytes"] == payload[
        "fixture"
    ]["raw_bytes"]
    assert payload["initial_capture_execution"]["postings"][
        "processed_bytes"
    ] == payload["fixture"]["raw_bytes"]
    assert payload["initial_capture_execution"]["postings"][
        "historical_raw_bytes_read"
    ] == 0
    assert payload["initial_history_read_gate"]["ok"] is True
    assert payload["initial_capture_execution"]["cgroup_memory"][
        "available"
    ] in {True, False}
    assert payload["live_route"]["ok"] is True
    assert payload["live_route"]["run_count"] == 3
    assert payload["live_route"][
        "event_availability_p95_within_5_seconds"
    ] is True
    assert payload["live_route"]["historical_raw_bytes_read"] == 0
    assert payload["live_route"]["max_shards_read_for_update"] <= 1
    assert payload["live_route"]["max_posting_shards_examined"] <= 1
