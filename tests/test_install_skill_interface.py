"""Focused tests for the bounded session-memory skill projection installer."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import install_skill_interface as installer  # noqa: E402


SOURCE_IDENTITY = {
    "status": "current",
    "identity_status": "current",
    "source_ref": "a" * 40,
    "source_commit": "a" * 40,
    "source_tree": "b" * 40,
    "source_script": "scripts/aoa_session_memory.py",
    "source_script_sha256": "sha256:" + "c" * 64,
    "source_worktree_clean": True,
    "diagnostics": [],
}
OWNER_CONTRACT = {
    "owner_repo": "aoa-skills",
    "schema_path": "schemas/capability_family.schema.json",
    "schema_sha256": "d" * 64,
    "validator_path": "scripts/validate_capability_home_port.py",
    "validator_sha256": "e" * 64,
    "validator_entrypoint_sha256": "f" * 64,
    "contract_validator_path": "scripts/validation/validate_capability_home_port.py",
    "contract_files": [],
    "digest": "sha256:" + "1" * 64,
}


def _write_profile(workspace: Path, target: Path) -> bytes:
    payload = {
        "schema_version": "aoa_session_memory_install_profile_v2",
        "artifact_type": "runtime_install_profile",
        "installation_kind": "workspace_runtime",
        "workspace_root": str(workspace.resolve()),
        "aoa_root": str(target.resolve()),
        "include_tests": True,
        "install_id": "sha256:" + "2" * 64,
        "source_ref": "3" * 40,
        "source_commit": "3" * 40,
        "source_commit_ref": "3" * 40,
        "source_tree": "4" * 40,
        "source_root": str(REPO_ROOT.resolve()),
        "source_script": "scripts/aoa_session_memory.py",
        "source_script_sha256": "sha256:" + "5" * 64,
        "source_worktree_clean": True,
        "source_identity_status": "current",
        "installed_at": "2026-01-01T00:00:00Z",
    }
    path = target / installer._session_memory.INSTALL_PROFILE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n").encode()
    path.write_bytes(raw)
    return raw


@pytest.fixture
def overlay_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """Build a target topology while keeping owner validation self-contained.

    The repository's graph intentionally names an external ``aoa-skills``
    contract.  These filesystem/receipt tests exercise this installer without
    making the standalone CI job depend on a sibling checkout; the real owner
    validator is run by the integration lane.
    """
    source = REPO_ROOT.resolve()
    workspace = tmp_path / "workspace"
    target = workspace / ".aoa"
    target.mkdir(parents=True)
    for relative in ("capabilities", "generated", "skills"):
        shutil.copytree(source / relative, target / relative)
    skills_root = tmp_path / "aoa-skills"
    skills_root.mkdir()
    profile_raw = _write_profile(workspace, target)

    sessions_sentinel = target / "sessions" / "sentinel.raw"
    sessions_sentinel.parent.mkdir(parents=True)
    sessions_sentinel.write_bytes(b"raw evidence stays\n")
    maps_sentinel = target / "maps" / "index.json"
    maps_sentinel.parent.mkdir(parents=True)
    maps_sentinel.write_bytes(b'{"generated":"last-good"}\n')
    sqlite_sentinel = target / "search.sqlite"
    sqlite_sentinel.write_bytes(b"generated store\n")
    hooks_sentinel = target / "hooks" / "sentinel.json"
    hooks_sentinel.parent.mkdir(parents=True)
    hooks_sentinel.write_bytes(b'{"hook":"untouched"}\n')
    script_sentinel = target / "scripts" / "aoa_session_memory.py"
    script_sentinel.parent.mkdir(parents=True)
    script_sentinel.write_bytes(b"# target kernel producer sentinel\n")
    unselected = target / "skills" / "aoa-session-batch-distill" / "SKILL.md"
    unselected_raw = unselected.read_bytes()

    def source_provenance(_root: Path) -> dict[str, Any]:
        return {**SOURCE_IDENTITY, "source_root": str(source)}

    monkeypatch.setattr(installer, "runtime_install_source_provenance", source_provenance)
    monkeypatch.setattr(
        installer,
        "runtime_install_profile_status",
        lambda *, root, workspace_root: {
            "path": str(root / installer._session_memory.INSTALL_PROFILE_PATH),
            "present": True,
            "valid": True,
            "include_tests": True,
            "diagnostics": [],
        },
    )
    monkeypatch.setattr(
        installer,
        "_run_owner_validation",
        lambda _skills_root, _source_root: {
            "ok": True,
            "status": "validated",
            "returncode": 0,
            "stdout": "fixture owner validator\n",
            "stderr": "",
            "shared_contract": OWNER_CONTRACT,
        },
    )
    return {
        "source": source,
        "skills": skills_root,
        "workspace": workspace,
        "target": target,
        "profile_raw": profile_raw,
        "sessions": sessions_sentinel,
        "maps": maps_sentinel,
        "sqlite": sqlite_sentinel,
        "hooks": hooks_sentinel,
        "script": script_sentinel,
        "unselected": unselected,
        "unselected_raw": unselected_raw,
    }


def _args(env: dict[str, Path]) -> dict[str, Path]:
    return {
        "source_aoa_root": env["source"],
        "skills_root": env["skills"],
        "workspace_root": env["workspace"],
        "aoa_root": env["target"],
    }


def _mutate_selected(env: dict[str, Path]) -> None:
    (env["target"] / "skills/aoa-session-memory-global-route/SKILL.md").write_text(
        "old global package\n",
        encoding="utf-8",
    )
    (env["target"] / "skills/aoa-session-memory-evidence-route/SKILL.md").write_text(
        "old evidence package\n",
        encoding="utf-8",
    )


def test_check_install_preserves_kernel_runtime_and_records_exact_receipt(
    overlay_fixture: dict[str, Path],
) -> None:
    env = overlay_fixture
    _mutate_selected(env)
    before = {
        key: path.read_bytes()
        for key, path in (
            ("profile", env["target"] / installer._session_memory.INSTALL_PROFILE_PATH),
            ("sessions", env["sessions"]),
            ("maps", env["maps"]),
            ("sqlite", env["sqlite"]),
            ("hooks", env["hooks"]),
            ("script", env["script"]),
            ("unselected", env["unselected"]),
        )
    }

    plan = installer.inspect_skill_projection(**_args(env))
    assert plan["ok"] is True
    assert plan["status"] == "ready"
    assert set(plan["selected_skills"]) == set(installer.DEFAULT_SKILLS)

    result = installer.install_skill_projection(**_args(env), force=True)
    assert result["ok"] is True
    assert result["status"] == "installed"
    receipt_path = env["target"] / installer.RECEIPT_RELATIVE
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["schema_version"] == installer.SCHEMA_VERSION
    assert receipt["selected_skills"] == list(installer.DEFAULT_SKILLS)
    assert receipt["selected_paths"] == sorted(plan["selected_paths"])
    assert receipt["base_profile_sha256"] == plan["base_profile"]["sha256"]
    assert receipt["base_install_id"] == plan["base_profile"]["install_id"]
    assert receipt["graph"]["content_hash"] == plan["source_metadata"]["graph_source_content_hash"]
    expected_packages = {
        item["name"]: item
        for item in plan["source_metadata"]["packages"]
    }
    assert {item["name"] for item in receipt["packages"]} == set(expected_packages)
    assert {
        item["name"]: item["version"] for item in receipt["packages"]
    } == {
        name: item["version"] for name, item in expected_packages.items()
    }
    assert all(
        isinstance(item["fingerprint"], str) and len(item["fingerprint"]) == 64
        for item in receipt["packages"]
    )
    for key, path in (
        ("profile", env["target"] / installer._session_memory.INSTALL_PROFILE_PATH),
        ("sessions", env["sessions"]),
        ("maps", env["maps"]),
        ("sqlite", env["sqlite"]),
        ("hooks", env["hooks"]),
        ("script", env["script"]),
        ("unselected", env["unselected"]),
    ):
        assert path.read_bytes() == before[key]
    assert not list(env["target"].glob(f"{installer.STAGE_PREFIX}*"))
    assert Path(receipt["backup_root"]).is_dir()

    current = installer.install_skill_projection(**_args(env), force=False)
    assert current["ok"] is True
    assert current["status"] == "already_current"


def test_install_requires_force_for_selected_difference(overlay_fixture: dict[str, Path]) -> None:
    env = overlay_fixture
    _mutate_selected(env)
    before = (env["target"] / "skills/aoa-session-memory-global-route/SKILL.md").read_bytes()
    result = installer.install_skill_projection(**_args(env), force=False)
    assert result["ok"] is False
    assert result["status"] == "force_required"
    assert (env["target"] / "skills/aoa-session-memory-global-route/SKILL.md").read_bytes() == before
    assert not (env["target"] / installer.RECEIPT_RELATIVE).exists()


def test_stale_base_profile_receipt_is_not_reported_as_already_current(
    overlay_fixture: dict[str, Path],
) -> None:
    env = overlay_fixture
    _mutate_selected(env)
    installed = installer.install_skill_projection(**_args(env), force=True)
    assert installed["status"] == "installed"
    receipt_path = env["target"] / installer.RECEIPT_RELATIVE
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["base_profile_sha256"] = "sha256:" + "9" * 64
    receipt_path.write_text(
        json.dumps(receipt, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    stale_raw = receipt_path.read_bytes()
    result = installer.install_skill_projection(**_args(env), force=False)
    assert result["ok"] is False
    assert result["status"] == "receipt_stale"
    assert "component_receipt_base_profile_sha256_mismatch" in result["diagnostics"]

    forced = installer.install_skill_projection(**_args(env), force=True)
    assert forced["ok"] is True
    assert forced["status"] == "installed"
    refreshed = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert refreshed["base_profile_sha256"] == forced["plan"]["base_profile"]["sha256"]
    assert refreshed["previous_component_receipt_sha256"] == installer._sha256_bytes(stale_raw)


def test_unselected_target_mismatch_fails_before_any_write(
    overlay_fixture: dict[str, Path],
) -> None:
    env = overlay_fixture
    _mutate_selected(env)
    env["unselected"].write_bytes(b"unselected drift\n")
    profile_before = (env["target"] / installer._session_memory.INSTALL_PROFILE_PATH).read_bytes()
    result = installer.install_skill_projection(**_args(env), force=True)
    assert result["ok"] is False
    assert result["status"] == "preflight_failed"
    assert any("unselected_target_mismatch" in item for item in result["diagnostics"])
    assert (env["target"] / installer._session_memory.INSTALL_PROFILE_PATH).read_bytes() == profile_before
    assert not (env["target"] / installer.RECEIPT_RELATIVE).exists()


def test_dirty_source_and_symlink_roots_fail_closed(
    overlay_fixture: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = overlay_fixture
    dirty = {**SOURCE_IDENTITY, "source_root": str(env["source"]), "source_worktree_clean": False}
    monkeypatch.setattr(installer, "runtime_install_source_provenance", lambda _root: dirty)
    result = installer.inspect_skill_projection(**_args(env))
    assert result["ok"] is False
    assert "source_worktree_dirty" in result["diagnostics"]

    link = env["target"].parent / "target-link"
    link.symlink_to(env["target"], target_is_directory=True)
    result = installer.inspect_skill_projection(
        source_aoa_root=env["source"],
        skills_root=env["skills"],
        workspace_root=env["workspace"],
        aoa_root=link,
    )
    assert result["ok"] is False
    assert any("must not be a symlink" in item for item in result["diagnostics"])


def test_compare_and_swap_conflict_does_not_restore_concurrent_target_edit(
    overlay_fixture: dict[str, Path],
) -> None:
    env = overlay_fixture
    _mutate_selected(env)
    concurrent = env["target"] / "skills/aoa-session-memory-global-route/SKILL.md"

    def edit_after_stage(_plan: installer.Plan) -> None:
        concurrent.write_text("concurrent edit\n", encoding="utf-8")

    result = installer.install_skill_projection(
        **_args(env),
        force=True,
        before_commit_hook=edit_after_stage,
    )
    assert result["ok"] is False
    assert result["status"] == "compare_and_swap_conflict"
    assert concurrent.read_text(encoding="utf-8") == "concurrent edit\n"
    assert not (env["target"] / installer.RECEIPT_RELATIVE).exists()
    assert not list(env["target"].glob(f"{installer.STAGE_PREFIX}*"))


def test_failure_after_replacement_restores_only_owned_roots_and_receipt(
    overlay_fixture: dict[str, Path],
) -> None:
    env = overlay_fixture
    _mutate_selected(env)
    before = installer.inspect_skill_projection(**_args(env))
    before_global = (env["target"] / "skills/aoa-session-memory-global-route/SKILL.md").read_bytes()

    def fail_on_second(_relative: str, index: int) -> None:
        if index == 1:
            raise RuntimeError("synthetic replacement failure")

    result = installer.install_skill_projection(
        **_args(env),
        force=True,
        replace_hook=fail_on_second,
    )
    assert result["ok"] is False
    assert result["status"] == "install_failed_rolled_back"
    assert (env["target"] / "skills/aoa-session-memory-global-route/SKILL.md").read_bytes() == before_global
    assert not (env["target"] / installer.RECEIPT_RELATIVE).exists()
    assert not list(env["target"].glob(f"{installer.STAGE_PREFIX}*"))
    assert before["ok"] is True


def test_receipt_publish_failure_restores_previous_receipt(
    overlay_fixture: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = overlay_fixture
    _mutate_selected(env)
    first = installer.install_skill_projection(**_args(env), force=True)
    assert first["status"] == "installed"
    receipt_path = env["target"] / installer.RECEIPT_RELATIVE
    prior_receipt = receipt_path.read_bytes()
    # Make a second selected change and fail only the final receipt publish.
    (env["target"] / "skills/aoa-session-memory-global-route/SKILL.md").write_text(
        "second candidate\n",
        encoding="utf-8",
    )
    original_atomic_write = installer._atomic_write

    def fail_receipt(path: Path, raw: bytes, *, prefix: str) -> None:
        if path == receipt_path:
            raise OSError("synthetic receipt publish failure")
        original_atomic_write(path, raw, prefix=prefix)

    monkeypatch.setattr(installer, "_atomic_write", fail_receipt)
    result = installer.install_skill_projection(**_args(env), force=True)
    assert result["ok"] is False
    assert result["status"] == "install_failed_rolled_back"
    assert receipt_path.read_bytes() == prior_receipt
    assert not list(env["target"].glob(f"{installer.STAGE_PREFIX}*"))


def test_explicit_rollback_without_source_or_validator_restores_backup(
    overlay_fixture: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = overlay_fixture
    _mutate_selected(env)
    before_global = (env["target"] / "skills/aoa-session-memory-global-route/SKILL.md").read_bytes()
    before_evidence = (env["target"] / "skills/aoa-session-memory-evidence-route/SKILL.md").read_bytes()
    installed = installer.install_skill_projection(**_args(env), force=True)
    assert installed["status"] == "installed"
    monkeypatch.setattr(
        installer,
        "runtime_install_source_provenance",
        lambda _root: (_ for _ in ()).throw(AssertionError("source must not be read")),
    )
    monkeypatch.setattr(
        installer,
        "_run_owner_validation",
        lambda _skills_root, _source_root: (_ for _ in ()).throw(
            AssertionError("owner validator must not be read")
        ),
    )
    result = installer.rollback_skill_projection(
        workspace_root=env["workspace"],
        aoa_root=env["target"],
    )
    assert result["ok"] is True
    assert result["status"] == "rolled_back"
    assert (env["target"] / "skills/aoa-session-memory-global-route/SKILL.md").read_bytes() == before_global
    assert (env["target"] / "skills/aoa-session-memory-evidence-route/SKILL.md").read_bytes() == before_evidence
    assert not (env["target"] / installer.RECEIPT_RELATIVE).exists()
    assert (env["sessions"]).read_bytes() == b"raw evidence stays\n"
    assert (env["maps"]).read_bytes() == b'{"generated":"last-good"}\n'
    assert (env["target"] / installer.ROLLBACK_OUTCOME_RELATIVE).is_file()


def test_rollback_rejects_tampered_backup_before_mutation(
    overlay_fixture: dict[str, Path],
) -> None:
    env = overlay_fixture
    _mutate_selected(env)
    installed = installer.install_skill_projection(**_args(env), force=True)
    receipt = json.loads(
        (env["target"] / installer.RECEIPT_RELATIVE).read_text(encoding="utf-8")
    )
    backup = Path(receipt["backup_root"])
    stored = next(path for path in (backup / "paths").iterdir() if path.is_file())
    stored.write_bytes(b"tampered backup\n")
    selected_after = (env["target"] / "skills/aoa-session-memory-global-route/SKILL.md").read_bytes()
    result = installer.rollback_skill_projection(**_args(env))
    assert result["ok"] is False
    assert result["status"] == "rollback_precondition_failed"
    assert (env["target"] / "skills/aoa-session-memory-global-route/SKILL.md").read_bytes() == selected_after
    assert installed["status"] == "installed"


def test_malformed_receipt_after_rows_are_not_current() -> None:
    # Exercise the strict shape guard directly without constructing a full
    # runtime fixture; this protects against ``all([])`` accepting malformed
    # rows in future receipt readers.
    plan = SimpleNamespace(
        selected_roots=(Path("skills/example"),),
        target_root=Path("/tmp/unused"),
    )
    receipt = {
        "selected_roots": ["skills/example"],
        "selected_after": [None],
    }
    original = installer._selected_post_records
    installer._selected_post_records = lambda _plan: ({"path": "skills/example", "state": "absent", "files": []},)  # type: ignore[assignment]
    try:
        assert installer._receipt_after_matches(plan, receipt) is False
    finally:
        installer._selected_post_records = original
