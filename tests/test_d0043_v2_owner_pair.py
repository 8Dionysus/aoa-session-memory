from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any

from scripts.d0043_v2_owner_pair import (
    NATIVE_DEPENDENCY_ROUTES,
    NATIVE_SOURCE_ROUTES,
    OWNER,
    OWNER_BINDING_SCHEMA_VERSION,
    REVIEWED_PROCEDURE_IDENTITY_DIGEST,
    REVIEWED_PROCEDURE_PATHS,
    build_owner_pair,
    load_reviewed_procedure,
    owner_witness,
    run_negative_cases,
    sha256_bytes,
    validate_published_pair,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
PROCEDURE_FILE = (
    Path(os.environ["AOA_KAG_REVIEWED_PROCEDURE"])
    if os.environ.get("AOA_KAG_REVIEWED_PROCEDURE")
    else None
)
REPORT_PATH = os.environ.get("D0043_REPORT_PATH")


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ("git", *args),
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def run_generator(root: Path, procedure_file: Path, *, check: bool = False) -> dict[str, Any]:
    procedure_root = procedure_file.parents[2]
    generator = procedure_file.parents[1] / "generate_repo_local_kag_index.py"
    command = [
        sys.executable,
        str(generator),
        "--repo-root",
        str(root),
        "--portable-family",
    ]
    if check:
        command.append("--check")
    started = time.perf_counter_ns()
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(procedure_root)
    result = subprocess.run(
        command,
        cwd=procedure_root,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise AssertionError(
            "canonical KAG generator failed\n"
            f"command={command!r}\nstdout={result.stdout}\nstderr={result.stderr}"
        )
    return {
        "command": command,
        "return_code": result.returncode,
        "check": check,
        "wall_ms": round((time.perf_counter_ns() - started) / 1_000_000, 3),
        "stdout_sha256": sha256_bytes(result.stdout.encode()),
        "stderr_sha256": sha256_bytes(result.stderr.encode()),
    }


def create_owner_fixture(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=False)
    for route in NATIVE_SOURCE_ROUTES:
        source = REPO_ROOT / route
        destination = root / route
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    (root / "README.md").write_text(
        "# owner pair fixture\n\n"
        "This is a disposable canonical-generator fixture.\n",
        encoding="utf-8",
    )
    (root / "config").mkdir()
    (root / "config" / "owner-pair.yaml").write_text(
        "owner: aoa-session-memory\nroute: d0043-v2\n",
        encoding="utf-8",
    )
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.name", "aoa-session-memory-d0043-test")
    git(root, "config", "user.email", "d0043-test@example.invalid")
    git(root, "add", ".")
    git(root, "commit", "-qm", "owner source fixture")


def copy_native_routes(root: Path) -> None:
    for route in (*NATIVE_SOURCE_ROUTES, *NATIVE_DEPENDENCY_ROUTES):
        source = REPO_ROOT / route
        destination = root / route
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)


def copy_procedure_fixture(
    procedure_file: Path,
    root: Path,
    *,
    mutate_route: str | None = None,
) -> Path:
    source_root = procedure_file.resolve().parents[2]
    for route in REVIEWED_PROCEDURE_PATHS:
        source = source_root / route
        destination = root / route
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    if mutate_route is not None:
        mutated = root / mutate_route
        mutated.write_bytes(
            mutated.read_bytes() + b"\n# same-version procedure substitution\n"
        )
    return root / REVIEWED_PROCEDURE_PATHS[0]


def portable_surface_digest(root: Path, procedure_file: Path) -> str:
    procedure = load_reviewed_procedure(procedure_file)
    manifest_path = root / "kag/indexes/index_family.manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    paths = {Path("kag/indexes/index_family.manifest.json")}
    paths.update(procedure.expected_portable_paths(manifest))
    entries = []
    for path in sorted(paths):
        content = (root / path).read_bytes()
        entries.append({"path": path.as_posix(), "sha256": sha256_bytes(content)})
    return sha256_bytes(
        json.dumps(
            entries,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    )


def canonical_converge(root: Path, procedure_file: Path) -> dict[str, Any]:
    """Run the owner generator to a stable surface, then use its check gate."""

    passes: list[dict[str, Any]] = []
    previous_digest: str | None = None
    for _ in range(4):
        generation = run_generator(root, procedure_file)
        digest = portable_surface_digest(root, procedure_file)
        passes.append({"generation": generation, "surface_digest": digest})
        if digest == previous_digest:
            break
        previous_digest = digest
    else:
        raise AssertionError("canonical portable family did not reach a fixed point")
    check = run_generator(root, procedure_file, check=True)
    checked_digest = portable_surface_digest(root, procedure_file)
    if checked_digest != passes[-1]["surface_digest"]:
        raise AssertionError("canonical check changed the fixed-point surface")
    return {
        "passes": passes,
        "check": check,
        "surface_digest": checked_digest,
        "equal": checked_digest == passes[-1]["surface_digest"],
    }


class D0043V2OwnerPairTests(unittest.TestCase):
    def setUp(self) -> None:
        if PROCEDURE_FILE is None or not PROCEDURE_FILE.is_file():
            self.skipTest(
                "set AOA_KAG_REVIEWED_PROCEDURE to the exact reviewed procedure"
            )

    def write_report(self, report: dict[str, Any]) -> None:
        if REPORT_PATH:
            path = Path(REPORT_PATH)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )

    def test_owner_pair_fixed_point_and_five_negatives(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aoa-session-memory-d0043-v2-") as tmp:
            assert PROCEDURE_FILE is not None
            root = Path(tmp) / OWNER
            create_owner_fixture(root)
            base_generation = canonical_converge(root, PROCEDURE_FILE)
            git(root, "add", ".")
            git(root, "commit", "-qm", "canonical portable base")
            base_ref = git(root, "rev-parse", "HEAD")

            changed_route = NATIVE_SOURCE_ROUTES[-1]
            transition = root / changed_route
            transition.write_text(
                transition.read_text(encoding="utf-8")
                + "\n\n## D-0043 v2 owner-pair transition\n\n"
                "This bounded source transition is intentionally regenerated.\n",
                encoding="utf-8",
            )
            git(root, "add", changed_route)
            git(root, "commit", "-qm", "owner source transition")
            head_generation = canonical_converge(root, PROCEDURE_FILE)
            git(root, "add", ".")
            git(root, "commit", "-qm", "canonical portable head")
            head_ref = git(root, "rev-parse", "HEAD")

            first_surface = head_generation["passes"][0]["surface_digest"]
            second_surface = head_generation["surface_digest"]
            self.assertTrue(head_generation["equal"])

            manifest = json.loads(
                (root / "kag/indexes/index_family.manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            pair = build_owner_pair(
                root,
                base_ref=base_ref,
                manifest=manifest,
                procedure_file=PROCEDURE_FILE,
                owner_source_root=REPO_ROOT,
                changed_source_route=changed_route,
            )
            evidence_path = Path(pair["evidence_path"])
            receipt_path = Path(pair["receipt_path"])
            evidence = json.loads((root / evidence_path).read_text(encoding="utf-8"))
            receipt = json.loads((root / receipt_path).read_text(encoding="utf-8"))
            negatives = run_negative_cases(
                root,
                base_ref=base_ref,
                manifest=manifest,
                procedure_file=PROCEDURE_FILE,
                evidence_path=evidence_path,
                receipt_path=receipt_path,
                evidence=evidence,
                receipt=receipt,
            )
            post_pair_check = run_generator(root, PROCEDURE_FILE, check=True)
            validate_published_pair(
                root,
                base_ref=base_ref,
                manifest=manifest,
                procedure_file=PROCEDURE_FILE,
                evidence_path=evidence_path,
                receipt_path=receipt_path,
                owner_source_root=REPO_ROOT,
                owner_binding=pair["owner_binding"],
            )
            git(root, "add", evidence_path.as_posix(), receipt_path.as_posix())
            git(root, "commit", "-qm", "publish D-0043 v2 owner pair")
            status = git(root, "status", "--porcelain")
            pair_commit = git(root, "rev-parse", "HEAD")

            self.assertEqual(head_ref, pair["head_ref"])
            self.assertEqual(
                REVIEWED_PROCEDURE_IDENTITY_DIGEST,
                pair["procedure_identity"]["digest"],
            )
            self.assertEqual("supported", pair["state"])
            self.assertEqual(
                pair["family_digest"],
                pair["fixed_point"]["family_digest"],
            )
            self.assertEqual("required_external_gate", pair["fixed_point"]["state"])
            self.assertEqual("supported", evidence["state"])
            self.assertEqual(OWNER, evidence["owner"]["name"])
            self.assertEqual("supported", receipt["semantic_admission"])
            self.assertTrue(evidence["measurements"]["source_dependency"]["state"] == "matched")
            self.assertTrue(all(result["rejected"] for result in negatives.values()))
            self.assertEqual(
                OWNER_BINDING_SCHEMA_VERSION,
                pair["owner_binding"]["schema_version"],
            )
            self.assertEqual(
                pair["evidence_sha256"],
                pair["owner_binding"]["common_pair"]["evidence_sha256"],
            )
            self.assertEqual(
                pair["receipt_sha256"],
                pair["owner_binding"]["common_pair"]["receipt_sha256"],
            )
            self.assertEqual(
                pair["owner_witness"]["witness_digest"],
                pair["owner_binding"]["native_witness"]["witness_digest"],
            )
            self.assertEqual(set(negatives), {
                "stale_head",
                "producer_substitution",
                "dependency_substitution",
                "receipt_evidence_mismatch",
                "tampered_currentness",
            })

            def expect_rejection(name: str, callback: Any) -> dict[str, Any]:
                started = time.perf_counter_ns()
                try:
                    callback()
                except Exception as exc:
                    return {
                        "case": name,
                        "rejected": True,
                        "exception": type(exc).__name__,
                        "message": str(exc),
                        "wall_ms": round(
                            (time.perf_counter_ns() - started) / 1_000_000,
                            3,
                        ),
                    }
                return {
                    "case": name,
                    "rejected": False,
                    "unexpected": f"{name} was accepted",
                    "wall_ms": round(
                        (time.perf_counter_ns() - started) / 1_000_000,
                        3,
                    ),
                }

            with tempfile.TemporaryDirectory(
                prefix="aoa-session-memory-d0043-procedure-substitution-"
            ) as procedure_tmp:
                substituted_procedure = copy_procedure_fixture(
                    PROCEDURE_FILE,
                    Path(procedure_tmp) / "aoa-kag",
                    mutate_route=REVIEWED_PROCEDURE_PATHS[0],
                )
                procedure_substitution = expect_rejection(
                    "procedure_source_substitution",
                    lambda: load_reviewed_procedure(substituted_procedure),
                )

            with tempfile.TemporaryDirectory(
                prefix="aoa-session-memory-d0043-native-substitution-"
            ) as native_tmp:
                substituted_native = Path(native_tmp) / OWNER
                copy_native_routes(substituted_native)
                dependency = substituted_native / NATIVE_DEPENDENCY_ROUTES[0]
                dependency.write_bytes(
                    dependency.read_bytes() + b"\n# native dependency substitution\n"
                )
                native_dependency_substitution = expect_rejection(
                    "native_dependency_substitution",
                    lambda: validate_published_pair(
                        root,
                        base_ref=base_ref,
                        manifest=manifest,
                        procedure_file=PROCEDURE_FILE,
                        evidence_path=evidence_path,
                        receipt_path=receipt_path,
                        owner_source_root=substituted_native,
                        owner_binding=pair["owner_binding"],
                    ),
                )

            tampered_binding = copy.deepcopy(pair["owner_binding"])
            tampered_binding["native_witness"]["dependency_digest"] = "0" * 64
            owner_binding_tamper = expect_rejection(
                "owner_binding_tamper",
                lambda: validate_published_pair(
                    root,
                    base_ref=base_ref,
                    manifest=manifest,
                    procedure_file=PROCEDURE_FILE,
                    evidence_path=evidence_path,
                    receipt_path=receipt_path,
                    owner_source_root=REPO_ROOT,
                    owner_binding=tampered_binding,
                ),
            )

            with tempfile.TemporaryDirectory(
                prefix="aoa-session-memory-d0043-containment-"
            ) as containment_tmp:
                containment_root = Path(containment_tmp) / OWNER
                containment_root.mkdir()
                outside = Path(containment_tmp) / "outside.txt"
                outside.write_text("outside\n", encoding="utf-8")
                witness_escape = containment_root / "escape"
                witness_escape.symlink_to(outside)
                route_escape = expect_rejection(
                    "owner_witness_symlink_escape",
                    lambda: owner_witness(
                        containment_root,
                        source_routes=("escape",),
                        dependency_routes=(),
                    ),
                )

            outside_pair = Path(tmp) / "outside-pair.json"
            outside_pair.write_text("{}\n", encoding="utf-8")
            pair_escape = root / "escape-evidence.json"
            pair_escape.symlink_to(outside_pair)
            pair_path_escape = expect_rejection(
                "owner_pair_symlink_escape",
                lambda: validate_published_pair(
                    root,
                    base_ref=base_ref,
                    manifest=manifest,
                    procedure_file=PROCEDURE_FILE,
                    evidence_path=Path("escape-evidence.json"),
                    receipt_path=receipt_path,
                    owner_source_root=REPO_ROOT,
                    owner_binding=pair["owner_binding"],
                ),
            )
            pair_escape.unlink()

            repair_negatives = {
                result["case"]: result
                for result in (
                    procedure_substitution,
                    native_dependency_substitution,
                    owner_binding_tamper,
                    route_escape,
                    pair_path_escape,
                )
            }
            self.assertTrue(all(result["rejected"] for result in repair_negatives.values()))
            self.assertEqual("", status)

            self.write_report(
                {
                    "schema_version": "aoa-session-memory-d0043-v2-owner-pair-test-v1",
                    "procedure_file": str(PROCEDURE_FILE),
                    "procedure_version": pair["procedure_version"],
                    "base_ref": base_ref,
                    "head_ref": head_ref,
                    "pair_commit": pair_commit,
                    "pair": pair,
                    "canonical_fixed_point": {
                        "first_surface_digest": first_surface,
                        "second_surface_digest": second_surface,
                        "equal": first_surface == second_surface,
                        "base_generation": base_generation,
                        "head_generation": head_generation,
                        "post_pair_check": post_pair_check,
                    },
                    "negative_cases": negatives,
                    "repair_negatives": repair_negatives,
                    "worktree_clean": not status,
                }
            )

    def test_current_family_stays_unknown_when_dependency_is_unmatched(self) -> None:
        assert PROCEDURE_FILE is not None
        procedure = load_reviewed_procedure(PROCEDURE_FILE)
        manifest = json.loads(
            (REPO_ROOT / "kag/indexes/index_family.manifest.json").read_text(
                encoding="utf-8"
            )
        )
        legacy_receipt = json.loads(
            (
                REPO_ROOT
                / "kag/receipts/index_family_budget/"
                f"{manifest['family_identity']['content_digest']}.json"
            ).read_text(encoding="utf-8")
        )
        evidence_path, evidence = procedure.build_budget_evidence(
            REPO_ROOT,
            base_ref=legacy_receipt["base_ref"],
            manifest=manifest,
            reason="owner-local unknown-preservation probe",
            cause_class="legitimate_bulk_authored_change",
            review_ref=(
                "aoa-kag:docs/decisions/"
                "AOA-KAG-D-0042-semantic-owner-evidence-for-budget-admission.md"
            ),
        )
        self.assertEqual(
            "unknown",
            evidence["state"],
            msg=f"unexpected evidence state for {evidence_path}",
        )
        self.assertEqual(
            "unmatched",
            evidence["measurements"]["source_dependency"]["state"],
        )


if __name__ == "__main__":
    unittest.main()
