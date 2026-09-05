#!/usr/bin/env python3
"""Run one non-authoritative scheduler trial over the exact source test corpus."""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import json
import os
import signal
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import validation_identity


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_TEST_TARGETS = (
    "tests/test_session_memory.py",
    "tests/test_session_memory_doctor.py",
    "tests/test_session_memory_outbox.py",
    "tests/test_session_memory_task_lifecycle.py",
    "tests/test_session_memory_tool_usage.py",
    "tests/test_session_memory_episode_search.py",
    "tests/test_session_memory_episode_maintenance.py",
    "tests/test_session_memory_episode_temporal.py",
    "tests/test_session_memory_capture.py",
    "tests/test_session_memory_sweep.py",
    "tests/test_public_tree_audit.py",
    "tests/test_git_history_audit.py",
)
PROBE_MODULE = "pytest_scheduler_probe"
PROBE_LOG_ENV = "AOA_SESSION_MEMORY_PYTEST_REPORT_LOG"
TAIL_CHARACTERS = 16_000


@dataclass(frozen=True)
class Method:
    name: str
    workers: int
    scheduler: str
    assertion_mode: str = "rewrite"

    @property
    def static(self) -> bool:
        return self.scheduler.startswith("static-")

    @property
    def xdist(self) -> bool:
        return self.scheduler.startswith("xdist-")


METHODS = {
    method.name: method
    for method in (
        Method("serial", 1, "serial"),
        Method("serial-plain", 1, "serial", "plain"),
        Method("xdist2-loadfile", 2, "xdist-loadfile"),
        Method("xdist2-load", 2, "xdist-load"),
        Method("xdist2-worksteal", 2, "xdist-worksteal"),
        Method("xdist4-loadfile", 4, "xdist-loadfile"),
        Method("xdist4-load", 4, "xdist-load"),
        Method("xdist4-worksteal", 4, "xdist-worksteal"),
        Method("static2", 2, "static-round-robin"),
        Method("static2-plain", 2, "static-round-robin", "plain"),
        Method("static2-balanced", 2, "static-duration-balanced"),
        Method("static2-balanced-plain", 2, "static-duration-balanced", "plain"),
        Method("static4", 4, "static-round-robin"),
        Method("static4-plain", 4, "static-round-robin", "plain"),
        Method("static4-balanced", 4, "static-duration-balanced"),
        Method("static4-balanced-plain", 4, "static-duration-balanced", "plain"),
    )
}


class ExperimentError(RuntimeError):
    pass


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _require_external_path(path: Path, label: str) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(REPO_ROOT)
    except ValueError:
        return resolved
    raise ExperimentError(f"{label} must live outside the owner checkout: {resolved}")


def _tail(path: Path) -> str:
    if not path.exists():
        return ""
    with path.open("rb") as handle:
        size = path.stat().st_size
        handle.seek(max(0, size - TAIL_CHARACTERS))
        return handle.read().decode("utf-8", errors="replace")


def _terminate_process_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=5)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def _run_process(
    step_id: str,
    argv: Sequence[str],
    *,
    env: dict[str, str],
    artifact_root: Path,
    timeout_seconds: float,
) -> dict[str, Any]:
    stdout_path = artifact_root / f"{step_id}.stdout.txt"
    stderr_path = artifact_root / f"{step_id}.stderr.txt"
    started = time.monotonic()
    timed_out = False
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        process = subprocess.Popen(
            list(argv),
            cwd=REPO_ROOT,
            env=env,
            stdout=stdout,
            stderr=stderr,
            start_new_session=True,
        )
        try:
            returncode = process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            _terminate_process_group(process)
            returncode = process.returncode if process.returncode is not None else 124
    return {
        "id": step_id,
        "argv": list(argv),
        "returncode": returncode,
        "timed_out": timed_out,
        "duration_seconds": round(time.monotonic() - started, 6),
        "stdout": {
            "path": str(stdout_path),
            "sha256": validation_identity.sha256_file(stdout_path),
            "tail": _tail(stdout_path),
        },
        "stderr": {
            "path": str(stderr_path),
            "sha256": validation_identity.sha256_file(stderr_path),
            "tail": _tail(stderr_path),
        },
    }


def _pytest_argv(
    method: Method,
    *,
    junit_path: Path,
    nodeids: Sequence[str] | None = None,
    collect_only: bool = False,
) -> list[str]:
    argv = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-p",
        "no:cacheprovider",
        "-p",
        PROBE_MODULE,
    ]
    if method.assertion_mode == "plain":
        argv.append("--assert=plain")
    if collect_only:
        argv.append("--collect-only")
    elif method.xdist:
        argv.extend(("-n", str(method.workers), "--dist", method.scheduler.removeprefix("xdist-")))
    if not collect_only:
        argv.extend(("--junitxml", str(junit_path)))
    argv.extend(nodeids if nodeids is not None else SOURCE_TEST_TARGETS)
    return argv


def _load_probe_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ExperimentError(f"invalid probe event at {path}:{line_number}") from exc
        if not isinstance(event, dict):
            raise ExperimentError(f"probe event at {path}:{line_number} is not an object")
        events.append(event)
    return events


def _collection_from_events(events: Sequence[dict[str, Any]]) -> dict[str, Any]:
    collections = [event for event in events if event.get("event") == "collection"]
    nodeid_lists = [event.get("nodeids") for event in collections]
    if not nodeid_lists or any(not isinstance(nodeids, list) for nodeids in nodeid_lists):
        raise ExperimentError("pytest probe did not emit a collection corpus")
    first = [str(nodeid) for nodeid in nodeid_lists[0]]
    if len(first) != len(set(first)):
        raise ExperimentError("pytest collection contains duplicate nodeids")
    mismatched_workers = [
        str(collections[index].get("worker"))
        for index, nodeids in enumerate(nodeid_lists)
        if [str(nodeid) for nodeid in nodeids] != first
    ]
    return {
        "nodeids": first,
        "worker_count": len(nodeid_lists),
        "workers_agree": not mismatched_workers,
        "mismatched_workers": mismatched_workers,
    }


def corpus_identity(nodeids: Sequence[str]) -> dict[str, Any]:
    ordered = list(nodeids)
    return {
        "count": len(ordered),
        "ordered_sha256": validation_identity.canonical_sha256(ordered),
        "set_sha256": validation_identity.canonical_sha256(sorted(ordered)),
    }


def static_shards(nodeids: Sequence[str], workers: int) -> list[list[str]]:
    if workers < 1:
        raise ExperimentError("static worker count must be positive")
    shards = [[] for _ in range(workers)]
    for index, nodeid in enumerate(nodeids):
        shards[index % workers].append(nodeid)
    flattened = [nodeid for shard in shards for nodeid in shard]
    if len(flattened) != len(set(flattened)) or set(flattened) != set(nodeids):
        raise ExperimentError("static shards are not an exact disjoint corpus partition")
    return shards


def duration_balanced_static_shards(
    nodeids: Sequence[str],
    workers: int,
    duration_by_nodeid: dict[str, float],
) -> tuple[list[list[str]], list[float]]:
    if workers < 1:
        raise ExperimentError("static worker count must be positive")
    matched = [duration_by_nodeid[nodeid] for nodeid in nodeids if nodeid in duration_by_nodeid]
    default_duration = sorted(matched)[len(matched) // 2] if matched else 1.0
    weighted = [
        (max(float(duration_by_nodeid.get(nodeid, default_duration)), 0.000001), nodeid)
        for nodeid in nodeids
    ]
    shards = [[] for _ in range(workers)]
    projected = [0.0 for _ in range(workers)]
    for duration, nodeid in sorted(weighted, key=lambda item: (-item[0], item[1])):
        index = min(range(workers), key=lambda item: (projected[item], len(shards[item]), item))
        shards[index].append(nodeid)
        projected[index] += duration
    flattened = [nodeid for shard in shards for nodeid in shard]
    if len(flattened) != len(set(flattened)) or set(flattened) != set(nodeids):
        raise ExperimentError("duration-balanced shards are not an exact disjoint corpus partition")
    return shards, [round(value, 6) for value in projected]


def _junit_duration_hints(path: Path, nodeids: Sequence[str]) -> tuple[dict[str, float], dict[str, Any]]:
    path = _require_external_path(path, "timing JUnit")
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as exc:
        raise ExperimentError(f"cannot parse timing JUnit: {path}") from exc
    by_stem_and_name: dict[tuple[str, str], str] = {}
    by_name: dict[str, list[str]] = {}
    for nodeid in nodeids:
        file_part, _, remainder = nodeid.partition("::")
        name = remainder.rsplit("::", 1)[-1]
        stem = Path(file_part).stem
        by_stem_and_name[(stem, name)] = nodeid
        by_name.setdefault(name, []).append(nodeid)
    durations: dict[str, float] = {}
    unmatched_cases = 0
    for case in root.findall(".//testcase"):
        name = str(case.get("name") or "")
        stem = str(case.get("classname") or "").rsplit(".", 1)[-1]
        nodeid = by_stem_and_name.get((stem, name))
        if nodeid is None and len(by_name.get(name, [])) == 1:
            nodeid = by_name[name][0]
        if nodeid is None:
            unmatched_cases += 1
            continue
        try:
            duration = float(case.get("time") or 0.0)
        except ValueError:
            duration = 0.0
        durations[nodeid] = durations.get(nodeid, 0.0) + max(duration, 0.0)
    return durations, {
        "kind": "historical_junit_hint",
        "path": str(path),
        "sha256": validation_identity.sha256_file(path),
        "matched_nodeid_count": len(durations),
        "unmatched_current_nodeid_count": len(set(nodeids) - set(durations)),
        "unmatched_junit_case_count": unmatched_cases,
        "authority": False,
    }


def _receipt_duration_hints(path: Path, nodeids: Sequence[str]) -> tuple[dict[str, float], dict[str, Any]]:
    path = _require_external_path(path, "timing receipt")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExperimentError(f"cannot parse timing receipt: {path}") from exc
    if payload.get("schema_version") != "aoa_session_memory_pytest_scheduler_trial_v1":
        raise ExperimentError("timing receipt has an unsupported schema")
    raw_durations = payload.get("execution", {}).get("duration_by_nodeid")
    if not isinstance(raw_durations, dict):
        raise ExperimentError("timing receipt has no per-node duration map")
    durations = {
        str(nodeid): max(float(duration), 0.0)
        for nodeid, duration in raw_durations.items()
        if str(nodeid) in set(nodeids)
    }
    return durations, {
        "kind": "scheduler_trial_receipt_hint",
        "path": str(path),
        "sha256": validation_identity.sha256_file(path),
        "source_repository_identity": payload.get("repository_identity", {}).get("before"),
        "source_corpus": payload.get("corpus"),
        "source_method": payload.get("method"),
        "matched_nodeid_count": len(durations),
        "unmatched_current_nodeid_count": len(set(nodeids) - set(durations)),
        "authority": False,
    }


def _execution_from_events(
    events: Sequence[dict[str, Any]], expected_nodeids: Sequence[str]
) -> dict[str, Any]:
    reports = [event for event in events if event.get("event") == "report"]
    observed = sorted({str(event.get("nodeid")) for event in reports if event.get("nodeid")})
    expected = set(expected_nodeids)
    observed_set = set(observed)
    failures = sorted(
        {
            str(event["nodeid"])
            for event in reports
            if event.get("outcome") == "failed" and event.get("nodeid")
        }
    )
    skipped = sorted(
        {
            str(event["nodeid"])
            for event in reports
            if event.get("outcome") == "skipped" and event.get("nodeid")
        }
    )
    durations: dict[str, float] = {}
    for event in reports:
        nodeid = event.get("nodeid")
        duration = event.get("duration_seconds")
        if nodeid and isinstance(duration, (int, float)):
            durations[str(nodeid)] = durations.get(str(nodeid), 0.0) + float(duration)
    return {
        "observed_count": len(observed),
        "observed_set_sha256": validation_identity.canonical_sha256(observed),
        "coverage_complete": observed_set == expected,
        "missing_nodeids": sorted(expected - observed_set),
        "unexpected_nodeids": sorted(observed_set - expected),
        "failed_nodeids": failures,
        "skipped_nodeids": skipped,
        "duration_sum_seconds": round(sum(durations.values()), 6),
        "duration_by_nodeid": {
            nodeid: round(duration, 9) for nodeid, duration in sorted(durations.items())
        },
        "slowest": [
            {"nodeid": nodeid, "duration_seconds": round(duration, 6)}
            for nodeid, duration in sorted(
                durations.items(), key=lambda item: (-item[1], item[0])
            )[:30]
        ],
    }


def _cache_environment(
    base: dict[str, str],
    *,
    pycache_root: Path | None,
    repository: dict[str, Any],
    environment: dict[str, Any],
    method: Method,
) -> tuple[dict[str, str], dict[str, Any]]:
    env = dict(base)
    env["PYTHONPATH"] = os.pathsep.join(
        filter(None, (str(REPO_ROOT / "scripts"), env.get("PYTHONPATH")))
    )
    if pycache_root is None:
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        return env, {"enabled": False, "observed_state_before": "disabled"}
    root = _require_external_path(pycache_root, "pycache root")
    key_payload = {
        "repository_identity": repository["identity_sha256"],
        "environment_identity": environment["identity_sha256"],
        "assertion_mode": method.assertion_mode,
    }
    key = validation_identity.canonical_sha256(key_payload)
    leaf = root / f"py{sys.version_info.major}{sys.version_info.minor}" / key
    metadata_path = leaf / "identity.json"
    expected_metadata = {"schema_version": 1, **key_payload, "key": key}
    if metadata_path.exists():
        try:
            actual_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ExperimentError(f"cannot read exact pycache identity: {metadata_path}") from exc
        if actual_metadata != expected_metadata:
            raise ExperimentError("exact pycache identity metadata does not match its key")
        state = "warm"
    else:
        leaf.mkdir(parents=True, exist_ok=True)
        _write_json(metadata_path, expected_metadata)
        state = "cold"
    env.pop("PYTHONDONTWRITEBYTECODE", None)
    env["PYTHONPYCACHEPREFIX"] = str(leaf)
    return env, {
        "enabled": True,
        "observed_state_before": state,
        "key": key,
        "path": str(leaf),
        "identity": expected_metadata,
    }


def _run_static(
    method: Method,
    *,
    env: dict[str, str],
    artifact_root: Path,
    timeout_seconds: float,
    timing_junit: Path | None,
    timing_receipt: Path | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str], dict[str, Any]]:
    collection_log = artifact_root / "collection.probe.jsonl"
    collect_env = {**env, PROBE_LOG_ENV: str(collection_log)}
    collection_started = time.monotonic()
    collection_result = _run_process(
        "collection",
        _pytest_argv(
            method,
            junit_path=artifact_root / "unused.xml",
            collect_only=True,
        ),
        env=collect_env,
        artifact_root=artifact_root,
        timeout_seconds=timeout_seconds,
    )
    collection_wall = time.monotonic() - collection_started
    if collection_result["returncode"] != 0:
        raise ExperimentError("static corpus collection failed")
    collection = _collection_from_events(_load_probe_events(collection_log))
    nodeids = collection["nodeids"]
    timing_source: dict[str, Any] | None = None
    if method.scheduler == "static-duration-balanced":
        if timing_receipt is not None:
            durations, timing_source = _receipt_duration_hints(timing_receipt, nodeids)
        elif timing_junit is not None:
            durations, timing_source = _junit_duration_hints(timing_junit, nodeids)
        else:
            raise ExperimentError(
                "duration-balanced static methods require --timing-receipt or --timing-junit"
            )
        shards, projected = duration_balanced_static_shards(
            nodeids, method.workers, durations
        )
        strategy = "longest-processing-time-first"
    else:
        shards = static_shards(nodeids, method.workers)
        projected = [None for _ in shards]
        strategy = "collection-order-round-robin"

    def run_shard(index: int, shard: list[str]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        step_id = f"shard-{index + 1}"
        probe_log = artifact_root / f"{step_id}.probe.jsonl"
        shard_env = {**env, PROBE_LOG_ENV: str(probe_log)}
        result = _run_process(
            step_id,
            _pytest_argv(
                method,
                junit_path=artifact_root / f"{step_id}.junit.xml",
                nodeids=shard,
            ),
            env=shard_env,
            artifact_root=artifact_root,
            timeout_seconds=timeout_seconds,
        )
        result["selection"] = corpus_identity(shard)
        return result, _load_probe_events(probe_log)

    started = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=method.workers) as pool:
        completed = list(pool.map(lambda pair: run_shard(*pair), enumerate(shards)))
    execution_wall = time.monotonic() - started
    results = [item[0] for item in completed]
    events = [event for item in completed for event in item[1]]
    sharding = {
        "strategy": strategy,
        "timing_source": timing_source,
        "collection_wall_seconds": round(collection_wall, 6),
        "execution_wall_seconds": round(execution_wall, 6),
        "shards": [
            {
                "index": index + 1,
                **corpus_identity(shard),
                "projected_duration_seconds": projected[index],
            }
            for index, shard in enumerate(shards)
        ],
    }
    return [collection_result, *results], events, nodeids, sharding


def run_trial(args: argparse.Namespace) -> dict[str, Any]:
    method = METHODS[args.method]
    artifact_root = _require_external_path(args.artifact_root, "artifact root")
    receipt_path = _require_external_path(args.receipt, "receipt")
    artifact_root.mkdir(parents=True, exist_ok=True)
    if any(artifact_root.iterdir()):
        raise ExperimentError(f"artifact root must start empty: {artifact_root}")
    started_at = dt.datetime.now(dt.UTC)
    started = time.monotonic()
    before = validation_identity.repository_identity()
    environment = validation_identity.environment_identity()
    env, cache = _cache_environment(
        os.environ.copy(),
        pycache_root=args.pycache_root,
        repository=before,
        environment=environment,
        method=method,
    )
    error: str | None = None
    steps: list[dict[str, Any]] = []
    nodeids: list[str] = []
    execution: dict[str, Any] = {
        "observed_count": 0,
        "coverage_complete": False,
        "missing_nodeids": [],
        "unexpected_nodeids": [],
        "failed_nodeids": [],
        "skipped_nodeids": [],
    }
    sharding: dict[str, Any] | None = None
    try:
        if method.static:
            steps, events, nodeids, sharding = _run_static(
                method,
                env=env,
                artifact_root=artifact_root,
                timeout_seconds=args.timeout_seconds,
                timing_junit=args.timing_junit,
                timing_receipt=args.timing_receipt,
            )
        else:
            probe_log = artifact_root / "trial.probe.jsonl"
            run_env = {**env, PROBE_LOG_ENV: str(probe_log)}
            result = _run_process(
                "pytest",
                _pytest_argv(
                    method,
                    junit_path=artifact_root / "pytest.junit.xml",
                ),
                env=run_env,
                artifact_root=artifact_root,
                timeout_seconds=args.timeout_seconds,
            )
            steps = [result]
            events = _load_probe_events(probe_log)
            collection = _collection_from_events(events)
            if not collection["workers_agree"]:
                raise ExperimentError(
                    "xdist workers did not collect one identical ordered corpus"
                )
            nodeids = collection["nodeids"]
        execution = _execution_from_events(events, nodeids)
    except (ExperimentError, OSError, subprocess.SubprocessError) as exc:
        error = str(exc)
    after = validation_identity.repository_identity()
    stable = before == after
    corpus = corpus_identity(nodeids)
    all_steps_passed = bool(steps) and all(
        step.get("returncode") == 0 and not step.get("timed_out") for step in steps
    )
    ok = bool(
        error is None
        and stable
        and all_steps_passed
        and execution.get("coverage_complete") is True
        and not execution.get("failed_nodeids")
    )
    payload = {
        "schema_version": "aoa_session_memory_pytest_scheduler_trial_v1",
        "owner_repo": "aoa-session-memory",
        "method": {
            "name": method.name,
            "workers": method.workers,
            "scheduler": method.scheduler,
            "assertion_mode": method.assertion_mode,
        },
        "pair_id": args.pair_id,
        "trial": args.trial,
        "started_at": started_at.isoformat(),
        "completed_at": dt.datetime.now(dt.UTC).isoformat(),
        "wall_seconds": round(time.monotonic() - started, 6),
        "ok": ok,
        "error": error,
        "repository_identity": {"before": before, "after": after, "stable": stable},
        "environment_identity": environment,
        "cache": cache,
        "targets": list(SOURCE_TEST_TARGETS),
        "corpus": corpus,
        "execution": execution,
        "sharding": sharding,
        "steps": steps,
        "receipt_path": str(receipt_path),
        "authority_boundary": (
            "non-authoritative owner-local scheduler comparison only; no owner gate, "
            "routing, reuse, release, publication, or sibling-rollout authority"
        ),
    }
    _write_json(receipt_path, payload)
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--method", required=True, choices=sorted(METHODS))
    parser.add_argument("--artifact-root", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--pycache-root", type=Path)
    timing = parser.add_mutually_exclusive_group()
    timing.add_argument("--timing-junit", type=Path)
    timing.add_argument("--timing-receipt", type=Path)
    parser.add_argument("--pair-id")
    parser.add_argument("--trial", type=int)
    parser.add_argument("--timeout-seconds", type=float, default=1800.0)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = run_trial(args)
    except (ExperimentError, validation_identity.IdentityError, OSError) as exc:
        print(f"pytest scheduler experiment: {exc}", file=sys.stderr)
        return 2
    summary = {
        "ok": payload["ok"],
        "method": payload["method"]["name"],
        "wall_seconds": payload["wall_seconds"],
        "corpus_count": payload["corpus"]["count"],
        "coverage_complete": payload["execution"]["coverage_complete"],
        "failed_nodeids": payload["execution"]["failed_nodeids"],
        "receipt": payload["receipt_path"],
    }
    print(
        json.dumps(summary, sort_keys=True, ensure_ascii=False)
        if args.json
        else summary
    )
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
