"""Focused tests for the standalone pure privacy projection core."""

from __future__ import annotations

import json

import pytest

import scripts.aoa_session_memory_privacy as module


def _synthetic_value() -> str:
    return "".join(("abcdefghijklmnop", "123456"))


def test_benign_text_does_not_enter_named_rewrite(monkeypatch) -> None:
    class ForbiddenSubMatcher:
        def sub(self, _replacement, _source: str):
            raise AssertionError("candidate matcher scanned benign text")

    for name in (
        "DERIVED_TEXT_NAMED_QUOTED_ASSIGNMENT_RE",
        "DERIVED_TEXT_NAMED_BARE_ASSIGNMENT_RE",
        "DERIVED_TEXT_SENSITIVE_FLAG_RE",
    ):
        monkeypatch.setattr(module, name, ForbiddenSubMatcher())

    benign = "ordinary transcript payload " + ("x" * 450_000)
    projection = module.derived_text_privacy_projection(benign)

    assert projection["status"] == "unchanged"
    assert projection["text"] == benign


def test_benign_opaque_candidates_do_not_enter_rewrite(monkeypatch) -> None:
    original = module.DERIVED_TEXT_OPAQUE_CREDENTIAL_RE

    class FindOnlyOpaqueMatcher:
        def finditer(self, source: str):
            return original.finditer(source)

        def sub(self, _replacement, _source: str):
            raise AssertionError("benign opaque candidates triggered rewrite")

    monkeypatch.setattr(
        module,
        "DERIVED_TEXT_OPAQUE_CREDENTIAL_RE",
        FindOnlyOpaqueMatcher(),
    )
    benign = (
        "source_sha256="
        "0123456789abcdef0123456789abcdef"
        "0123456789abcdef0123456789abcdef"
    )

    projection = module.derived_text_privacy_projection(benign)

    assert projection["status"] == "unchanged"
    assert projection["text"] == benign
    assert projection["redaction_count"] == 0


def test_safe_named_metadata_does_not_enter_rewrite(monkeypatch) -> None:
    class FindOnlyNamedMatcher:
        def __init__(self, original):
            self.original = original

        def match(self, source: str, start: int = 0):
            return self.original.match(source, start)

        def sub(self, _replacement, _source: str):
            raise AssertionError("safe named metadata triggered rewrite")

    for name in (
        "DERIVED_TEXT_NAMED_QUOTED_ASSIGNMENT_RE",
        "DERIVED_TEXT_NAMED_BARE_ASSIGNMENT_RE",
        "DERIVED_TEXT_SENSITIVE_FLAG_RE",
    ):
        monkeypatch.setattr(
            module,
            name,
            FindOnlyNamedMatcher(getattr(module, name)),
        )
    benign = (
        'API_KEY_STATUS="configured" '
        "token_status_path=/srv/example/token-status.json "
        "--access-token '${ACCESS_TOKEN}'"
    )

    projection = module.derived_text_privacy_projection(benign)

    assert projection["status"] == "unchanged"
    assert projection["text"] == benign
    assert projection["redaction_count"] == 0


@pytest.mark.parametrize(
    "text",
    [
        "API_KEY_STATUS=configured",
        "token_status_path=/srv/example/token-status.json",
        "max_output_tokens=10000",
        "tokenizer_name=cl100k_base",
        "The API key is configured; value not shown.",
        "${OVMS_EMBEDDINGS_API_KEY}",
        "source_sha256=0123456789abcdef0123456789abcdef",
    ],
)
def test_safe_metadata_projection_is_stable(text: str) -> None:
    first = module.derived_text_privacy_projection(text)
    second = module.derived_text_privacy_projection(text)

    assert first == second
    assert first["status"] == "unchanged"
    assert first["text"] == text
    assert first["redaction_count"] == 0


@pytest.mark.parametrize(
    "text,marker,kind",
    [
        (
            "".join(("service.", "pass", "word=")) + _synthetic_value(),
            "<redacted:password>",
            "password",
        ),
        (
            "".join(("--access", "-token ")) + _synthetic_value(),
            "<redacted:token>",
            "token",
        ),
        (
            "".join(("Author", "ization: Bearer ")) + _synthetic_value(),
            "<redacted:token>",
            "token",
        ),
        (
            "".join(("https://agent:", "secret", "-value-12345678@"))
            + "example.test/path",
            "<redacted:password>",
            "password",
        ),
        (
            "".join(("-----BEGIN ", "PRIVATE KEY-----\n"))
            + _synthetic_value()
            + "\n-----END PRIVATE KEY-----",
            "<redacted:private_key>",
            "private_key",
        ),
    ],
)
def test_sensitive_projection_redacts_without_persisting_values(
    text: str,
    marker: str,
    kind: str,
) -> None:
    projection = module.derived_text_privacy_projection(text)

    assert projection["status"] == "redacted"
    assert marker in projection["text"]
    assert projection["redaction_count"] >= 1
    assert kind in projection["kinds"]
    assert text not in json.dumps(projection, ensure_ascii=False)


def test_unicode_position_hazards_use_safe_fallback() -> None:
    for text in (
        "".join(("service.", "ſ", "ecret=")) + _synthetic_value(),
        "".join(("pass", "word=")) + _synthetic_value() + " ı",
        "".join(("pass", "word=")) + _synthetic_value() + " İ",
        "".join(("pass", "word=")) + _synthetic_value() + " K",
    ):
        projection = module.derived_text_privacy_projection(text)
        assert projection["status"] == "redacted"
        assert "abcdefghijklmnop123456" not in projection["text"]

    benign = module.derived_text_privacy_projection(
        "".join(("Key=", _synthetic_value()))
    )
    assert benign["status"] == "unchanged"
