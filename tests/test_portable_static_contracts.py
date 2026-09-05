"""Focused tests for portable static contract artifacts.

These checks only inspect the authored portable tree and its generators.
They intentionally avoid importing the session-memory runtime monolith.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "aoa_session_memory.py"
)


def test_portable_artifact_manifest_fingerprints_complete_skill_system() -> None:
    source_aoa = SCRIPT.parents[1]
    manifest = json.loads(
        (
            source_aoa
            / "manifests"
            / "artifact_bundles"
            / "portable_bundle.bundle.json"
        ).read_text(encoding="utf-8")
    )
    subjects: set[str] = set()
    for spec in manifest["artifact_subjects"]:
        if "path" in spec:
            path = source_aoa / spec["path"]
            assert path.is_file(), spec["path"]
            subjects.add(spec["path"])
            continue
        matches = sorted(
            path
            for path in source_aoa.glob(spec["glob"])
            if path.is_file()
        )
        assert matches, spec["glob"]
        subjects.update(
            path.relative_to(source_aoa).as_posix() for path in matches
        )

    expected: set[str] = set()
    for directory in ("capabilities", "evals", "skills"):
        expected.update(
            path.relative_to(source_aoa).as_posix()
            for path in (source_aoa / directory).rglob("*")
            if path.is_file()
            and "__pycache__" not in path.parts
            and not path.name.endswith(".pyc")
        )
    expected.update(
        path.relative_to(source_aoa).as_posix()
        for path in (source_aoa / "scripts").glob("*.py")
        if path.is_file()
    )
    expected.update(
        path.relative_to(source_aoa).as_posix()
        for path in (source_aoa / "tests").glob("test_*.py")
        if path.is_file()
    )
    expected.update(
        path.relative_to(source_aoa).as_posix()
        for path in (source_aoa / "generated").glob("capability_graph.*")
        if path.is_file()
    )

    assert expected <= subjects
    assert not any("__pycache__" in Path(path).parts for path in subjects)
    assert not any(path.endswith(".pyc") for path in subjects)
    for path in (source_aoa / "skills").rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {
            ".json",
            ".md",
            ".txt",
            ".yaml",
            ".yml",
        }:
            continue
        text = path.read_text(encoding="utf-8")
        assert "/srv/example/AbyssOS" not in text, path
        assert "/home/" not in text, path
        assert "~/.codex" not in text, path


def test_decision_indexes_match_canonical_records() -> None:
    source_aoa = SCRIPT.parents[1]
    result = subprocess.run(
        [
            sys.executable,
            str(source_aoa / "scripts" / "generate_decision_indexes.py"),
            "--check",
            "--repo-root",
            str(source_aoa),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_agent_atlas_policy_matches_source_skeleton() -> None:
    source_aoa = SCRIPT.parents[1]
    policy = json.loads((source_aoa / "config" / "atlas-policy.json").read_text(encoding="utf-8"))
    axis_names = [axis["name"] for axis in policy["axes"]]

    assert policy["entry_contract"]["truth_status"] == "route_signal_not_reviewed_truth"
    assert "by-work-context" in axis_names
    assert "by-route-next-action" in axis_names
    assert "by-evidence-provenance" in axis_names
    assert "by-operator-preference" in axis_names

    for axis_name in axis_names:
        axis_dir = source_aoa / "maps" / axis_name
        assert axis_dir.is_dir()
        assert (axis_dir / "README.md").exists()
        assert (axis_dir / "entries" / ".gitkeep").exists()

    schema = json.loads((source_aoa / "schemas" / "atlas-route-entry.schema.json").read_text(encoding="utf-8"))
    assert "artifact_identity" in schema["required"]
    assert "generation_identity" in schema["required"]
    assert schema["properties"]["axis"]["pattern"] == "^by-[a-z0-9-]+$"
    assert schema["$defs"]["generationIdentity"]["properties"][
        "projection"
    ]["const"] == "agent_atlas"
    assert schema["$defs"]["artifactIdentity"]["properties"]["owner_repo"]["const"] == "aoa-session-memory"
