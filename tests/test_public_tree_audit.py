from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_auditor():
    path = REPO_ROOT / "scripts" / "audit_public_tree.py"
    spec = importlib.util.spec_from_file_location("audit_public_tree", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_audit_reports_secret_fingerprints_without_values(tmp_path: Path) -> None:
    auditor = load_auditor()
    secrets = ["sk-" + "A" * 32, "sk-" + "C" * 32]
    (tmp_path / "config.txt").write_text("\n".join(secrets) + "\n", encoding="utf-8")

    report = auditor.audit(tmp_path)

    assert report["ok"] is False
    assert sum(item["class"] == "openai_api_key" for item in report["findings"]) == 2
    assert all(secret not in json.dumps(report) for secret in secrets)
    assert all(item["fingerprint"].startswith("sha256:") for item in report["findings"])


def test_audit_blocks_runtime_material_and_non_generic_home_paths(tmp_path: Path) -> None:
    auditor = load_auditor()
    session_dir = tmp_path / "sessions" / "private-session"
    session_dir.mkdir(parents=True)
    (session_dir / "session.raw.jsonl").write_text("{}\n", encoding="utf-8")
    personal_home = "/home/" + "alice" + "/project"
    (tmp_path / "fixture.txt").write_text(personal_home, encoding="utf-8")

    report = auditor.audit(tmp_path)
    classes = {item["class"] for item in report["findings"]}

    assert "session_material" in classes
    assert "personal_home_path" in classes
    assert personal_home not in json.dumps(report)


def test_audit_keeps_generic_examples_and_host_profiles_distinct(tmp_path: Path) -> None:
    auditor = load_auditor()
    host_profile = "/srv/" + "AbyssOS" + "/.aoa"
    (tmp_path / "examples.txt").write_text(f"/home/example/project\n{host_profile}\n", encoding="utf-8")

    report = auditor.audit(tmp_path)

    assert report["ok"] is True
    assert report["counts"] == {"blocking": 0, "review": 1}
    assert report["findings"][0]["class"] == "host_profile_path"
    assert host_profile not in json.dumps(report)
