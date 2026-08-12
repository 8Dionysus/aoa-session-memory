from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_auditor():
    scripts = REPO_ROOT / "scripts"
    if scripts.as_posix() not in sys.path:
        sys.path.insert(0, scripts.as_posix())
    path = scripts / "audit_git_history.py"
    spec = importlib.util.spec_from_file_location("audit_git_history", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", repo.as_posix(), *args], check=True, stdout=subprocess.DEVNULL)


def test_history_audit_finds_deleted_session_secret_without_exposing_value(
    tmp_path: Path,
) -> None:
    auditor = load_auditor()
    repo = tmp_path / "repo"
    repo.mkdir()
    run(repo, "init", "-q")
    run(repo, "config", "user.name", "History Audit Fixture")
    run(repo, "config", "user.email", "12345+fixture@users.noreply.github.com")
    (repo / "README.md").write_text("safe\n", encoding="utf-8")
    run(repo, "add", "README.md")
    run(repo, "commit", "-qm", "safe root")

    session = repo / "sessions" / "private" / "session.raw.jsonl"
    session.parent.mkdir(parents=True)
    secrets = ["sk-" + "B" * 32, "sk-" + "D" * 32]
    session.write_text("\n".join(secrets) + "\n", encoding="utf-8")
    run(repo, "add", "sessions/private/session.raw.jsonl")
    run(repo, "commit", "-qm", "add private fixture")
    session.unlink()
    run(repo, "add", "-u")
    run(repo, "commit", "-qm", "delete private fixture")
    dangling_secret = "sk-" + "E" * 32
    subprocess.run(
        ["git", "-C", repo.as_posix(), "hash-object", "-w", "--stdin"],
        input=dangling_secret + "\n",
        text=True,
        check=True,
        stdout=subprocess.DEVNULL,
    )

    report = auditor.audit(repo)
    classes = {item["class"] for item in report["findings"]}

    assert report["ok"] is False
    assert "historical_session_material" in classes
    assert sum(item["class"] == "openai_api_key" for item in report["findings"]) == 2
    assert report["coverage"]["historical_only_blob_count"] >= 1
    assert report["coverage"]["refs_stable"] is True
    assert report["coverage"]["refs_before_digest"] == report["coverage"]["refs_after_digest"]
    assert report["coverage"]["object_reader"] == "single_git_cat_file_batch_stream"
    assert (
        report["coverage"]["content_matcher"]
        == "literal_start_candidates_with_exact_regex_confirmation"
    )
    assert all(
        secret not in json.dumps(report) for secret in [*secrets, dangling_secret]
    )
    assert all(item["fingerprint"].startswith("sha256:") for item in report["findings"])
    assert auditor.audit_exit_code(report, "none") == 0
    assert auditor.audit_exit_code(report, "blocking") == 1


def test_history_audit_fails_closed_when_refs_change(
    tmp_path: Path,
    monkeypatch,
) -> None:
    auditor = load_auditor()
    repo = tmp_path / "repo"
    repo.mkdir()
    run(repo, "init", "-q")
    run(repo, "config", "user.name", "History Audit Fixture")
    run(repo, "config", "user.email", "12345+fixture@users.noreply.github.com")
    (repo / "README.md").write_text("safe\n", encoding="utf-8")
    run(repo, "add", "README.md")
    run(repo, "commit", "-qm", "safe root")
    initial = auditor.ref_snapshot(repo)
    changed = {**initial, "digest": "sha256:" + "0" * 64}
    snapshots = iter((initial, changed))
    monkeypatch.setattr(auditor, "ref_snapshot", lambda _repo: next(snapshots))

    report = auditor.audit(repo)

    assert report["ok"] is False
    assert report["coverage"]["refs_stable"] is False
    assert auditor.audit_exit_code(report, "none") == 1
    assert any(
        item["class"] == "history_ref_drift"
        and item["severity"] == "blocking"
        for item in report["findings"]
    )
