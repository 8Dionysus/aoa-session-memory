"""Pytest plugin emitting exact collection and execution events for shadow trials."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest


REPORT_LOG_ENV = "AOA_SESSION_MEMORY_PYTEST_REPORT_LOG"
_report_path: Path | None = None


def _write(payload: dict[str, Any]) -> None:
    if _report_path is None:
        return
    with _report_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, ensure_ascii=False) + "\n")


def pytest_configure(config: pytest.Config) -> None:
    global _report_path
    if hasattr(config, "workerinput"):
        _report_path = None
        return
    raw_path = os.environ.get(REPORT_LOG_ENV)
    if not raw_path:
        _report_path = None
        return
    _report_path = Path(raw_path)
    _report_path.parent.mkdir(parents=True, exist_ok=True)
    _report_path.write_text("", encoding="utf-8")


def pytest_collection_finish(session: pytest.Session) -> None:
    nodeids = [item.nodeid for item in session.items]
    if nodeids:
        _write({"event": "collection", "worker": "controller", "nodeids": nodeids})


@pytest.hookimpl(optionalhook=True)
def pytest_xdist_node_collection_finished(node: Any, ids: list[str]) -> None:
    _write(
        {
            "event": "collection",
            "worker": str(getattr(node, "gateway", node).id),
            "nodeids": list(ids),
        }
    )


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    _write(
        {
            "event": "report",
            "nodeid": report.nodeid,
            "when": report.when,
            "outcome": report.outcome,
            "duration_seconds": round(float(report.duration), 9),
            "worker": getattr(report, "worker_id", "controller"),
            "wasxfail": bool(getattr(report, "wasxfail", False)),
        }
    )
