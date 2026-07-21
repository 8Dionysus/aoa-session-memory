from __future__ import annotations

import importlib.util
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = PACKAGE_ROOT / "scripts" / "validate_package_projection.py"
SPEC = importlib.util.spec_from_file_location("aoa_session_memory_projection_validator", VALIDATOR_PATH)
assert SPEC and SPEC.loader
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


def test_committed_package_projection_matches_its_manifest() -> None:
    assert validator.validate(PACKAGE_ROOT) == []
