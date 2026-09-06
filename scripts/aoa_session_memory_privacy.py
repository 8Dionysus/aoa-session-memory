#!/usr/bin/env python3
"""Standalone privacy projection core used by the session-memory runtime.

This module deliberately owns only pure text classification and projection.
It has no archive, host, subprocess, or local AoA dependencies so an agent can
validate a privacy-source edit without compiling the full session-memory CLI.
The main runtime imports these functions from this exact sibling source and
continues to expose the historical names.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any


DERIVED_TEXT_PRIVACY_POLICY_VERSION = 1
DERIVED_TEXT_PRIVACY_LOOKAHEAD_CHARS = 8192

DERIVED_TEXT_SENSITIVE_LABEL_PATTERN = (
    r"(?:[A-Za-z0-9]+(?:[_-][A-Za-z0-9]+)*[_-])?"
    r"(?:api[_-]?key|apikey|secret(?:[_-]?key)?|client[_-]?secret|"
    r"private[_-]?key|password|passwd|credential(?:s)?|"
    r"access[_-]?token|refresh[_-]?token|auth[_-]?token|"
    r"bearer[_-]?token|session[_-]?token)"
    r"(?:[_-][A-Za-z0-9]+)*"
)

# ``str.find`` over the folded source keeps the admission check in C while
# retaining the exact matchers below for the authoritative rewrite.  The
# tuple is also the source for the legacy regex fallback, keeping both paths
# on the same complete set of admissible stems.
DERIVED_TEXT_SENSITIVE_LABEL_LITERALS = (
    "apikey",
    "api_key",
    "api-key",
    "secret",
    "clientsecret",
    "client_secret",
    "client-secret",
    "privatekey",
    "private_key",
    "private-key",
    "password",
    "passwd",
    "credential",
    "access_token",
    "access-token",
    "accesstoken",
    "refresh_token",
    "refresh-token",
    "refreshtoken",
    "auth_token",
    "auth-token",
    "authtoken",
    "bearer_token",
    "bearer-token",
    "bearertoken",
    "session_token",
    "session-token",
    "sessiontoken",
)
DERIVED_TEXT_SENSITIVE_LABEL_PREFILTER_RE = re.compile(
    "(?:"
    + "|".join(
        re.escape(stem) for stem in DERIVED_TEXT_SENSITIVE_LABEL_LITERALS
    )
    + ")",
    flags=re.IGNORECASE,
)

# Python's case-insensitive ASCII regex admits these Unicode equivalents, but
# their case-folded positions are not a safe basis for indexing the source.
DERIVED_TEXT_CASEFOLD_POSITION_UNSAFE_RE = re.compile(
    "[\u0130\u0131\u017f\u212a]"
)
DERIVED_TEXT_SENSITIVE_METADATA_SUFFIX_RE = re.compile(
    r"(?:[_-](?:name|status|state|path|file|filename|id|present|configured|"
    r"enabled|source|owner|kind|type|count|length|len|label|risk|signal|"
    r"event|boundary|policy|route|category|class|facet|tag))+$",
    flags=re.IGNORECASE,
)
DERIVED_TEXT_SAFE_NAMED_VALUE_RE = re.compile(
    r"(?:none|null|nil|missing|absent|present|configured|unconfigured|"
    r"enabled|disabled|true|false|required|optional|placeholder|example|"
    r"not[ _-]?shown|redacted|masked|unknown|unset|empty|str|string|bytes|"
    r"int|integer|float|bool|boolean|\*{3,}|<redacted(?::[^>]+)?>|"
    r"\[redacted(?::[^\]]+)?\]|\$\{?[A-Za-z_][A-Za-z0-9_]*\}?|"
    r"\{[A-Za-z_][A-Za-z0-9_]*\})",
    flags=re.IGNORECASE,
)
DERIVED_TEXT_NAMED_QUOTED_ASSIGNMENT_RE = re.compile(
    rf"(?P<prefix>(?<![A-Za-z0-9_])(?:export\s+)?[\"']?"
    rf"(?P<label>{DERIVED_TEXT_SENSITIVE_LABEL_PATTERN})[\"']?\s*[:=]\s*)"
    r"(?P<value>\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*')",
    flags=re.IGNORECASE,
)
DERIVED_TEXT_NAMED_BARE_ASSIGNMENT_RE = re.compile(
    rf"(?P<prefix>(?<![A-Za-z0-9_])(?:export\s+)?[\"']?"
    rf"(?P<label>{DERIVED_TEXT_SENSITIVE_LABEL_PATTERN})[\"']?\s*[:=]\s*)"
    r"(?P<value>\{[A-Za-z_][A-Za-z0-9_]*\}|[^\s,;}\]]+)",
    flags=re.IGNORECASE,
)
DERIVED_TEXT_SENSITIVE_FLAG_RE = re.compile(
    r"(?P<prefix>(?<![A-Za-z0-9_])--(?P<label>"
    r"api[-_]?key|client[-_]?secret|password|passwd|access[-_]?token|"
    r"refresh[-_]?token|auth[-_]?token)"
    r"(?:\s*=\s*|\s+))"
    r"(?P<value>\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|[^\s,;]+)",
    flags=re.IGNORECASE,
)
DERIVED_TEXT_AUTHORIZATION_RE = re.compile(
    r"(?P<prefix>\bAuthorization\s*[:=]\s*(?:Bearer\s+)?|\bBearer\s+)"
    r"(?P<value>[A-Za-z0-9._~+/=-]{8,})",
    flags=re.IGNORECASE,
)
DERIVED_TEXT_URL_CREDENTIAL_RE = re.compile(
    r"(?P<prefix>\b[a-z][a-z0-9+.-]*://[^:/@\s]+:)"
    r"(?P<value>[^@\s/]+)(?P<suffix>@)",
    flags=re.IGNORECASE,
)
DERIVED_TEXT_KNOWN_CREDENTIAL_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:"
    r"sk-(?:proj-)?[A-Za-z0-9_-]{16,}|"
    r"ghp_[A-Za-z0-9_]{20,}|"
    r"github_pat_[A-Za-z0-9_]{20,}|"
    r"xox[baprs]-[A-Za-z0-9-]{20,}|"
    r"AIza[0-9A-Za-z_-]{30,}|"
    r"(?:AKIA|ASIA)[0-9A-Z]{16}|"
    r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"
    r")(?![A-Za-z0-9])",
    flags=re.IGNORECASE,
)
DERIVED_TEXT_KNOWN_CREDENTIAL_PREFILTER_RE = re.compile(
    r"(?:sk-|ghp_|github_pat_|xox[baprs]-|AIza|AKIA|ASIA|eyJ)",
    flags=re.IGNORECASE,
)
DERIVED_TEXT_OPAQUE_CREDENTIAL_RE = re.compile(
    r"(?<![A-Za-z0-9])(?P<value>[A-Za-z0-9+/_=-]{32,256})(?![A-Za-z0-9])"
)
DERIVED_TEXT_PRIVACY_KINDS = frozenset(
    {
        "credential",
        "opaque_credential",
        "password",
        "private_key",
        "token",
    }
)
DERIVED_TEXT_PEM_PRIVATE_KEY_RE = re.compile(
    r"(?P<begin>-----BEGIN (?P<label>[A-Z0-9 ]*PRIVATE KEY)-----)"
    r".*?"
    r"(?P<end>-----END [A-Z0-9 ]*PRIVATE KEY-----)",
    flags=re.DOTALL,
)


def short_text(value: Any, *, max_chars: int = 120) -> str:
    text = str(value or "").replace("\n", " ").strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "..."


def derived_text_privacy_unquote(value: str) -> tuple[str, str]:
    text = str(value or "")
    if len(text) >= 2 and text[0] in {"'", '"'} and text[-1] == text[0]:
        return text[1:-1], text[0]
    return text, ""


def derived_text_privacy_named_value_is_safe(label: str, value: str) -> bool:
    unquoted, _quote = derived_text_privacy_unquote(value)
    normalized_label = str(label or "").strip()
    normalized_value = unquoted.strip()
    if DERIVED_TEXT_SENSITIVE_METADATA_SUFFIX_RE.search(normalized_label):
        return True
    if not normalized_value:
        return True
    return bool(
        normalized_value
        and DERIVED_TEXT_SAFE_NAMED_VALUE_RE.fullmatch(normalized_value)
    )


def derived_text_privacy_label_kind(label: str) -> str:
    normalized = str(label or "").casefold().replace("-", "_")
    if "private_key" in normalized:
        return "private_key"
    if "password" in normalized or "passwd" in normalized:
        return "password"
    if "token" in normalized:
        return "token"
    return "credential"


def derived_text_privacy_safe_label(label: Any) -> str:
    normalized = str(label or "").strip()
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,79}", normalized):
        return ""
    if DERIVED_TEXT_KNOWN_CREDENTIAL_RE.search(normalized):
        return ""
    if derived_text_looks_like_opaque_credential(normalized):
        return ""
    return normalized


def derived_text_looks_like_opaque_credential(
    value: str,
    *,
    nearby_text: str = "",
) -> bool:
    text = str(value or "")
    if len(text) < 32 or len(text) > 256:
        return False
    if re.fullmatch(r"[A-Fa-f0-9]{32,128}", text):
        return False
    if text.startswith(("/", "./", "../")):
        return False
    if text.count("/") > 2 and "+" not in text and "=" not in text:
        return False
    character_classes = sum(
        bool(re.search(pattern, text))
        for pattern in (r"[a-z]", r"[A-Z]", r"[0-9]")
    )
    if character_classes < 3:
        return False
    counts = Counter(text)
    length = len(text)
    entropy = -sum(
        (count / length) * math.log2(count / length)
        for count in counts.values()
    )
    if entropy < 4.2:
        return False
    strong_base64_shape = bool(
        ("+" in text or "=" in text or 0 < text.count("/") <= 2)
        and "-" not in text
        and "_" not in text
    )
    sensitive_context = bool(
        re.search(
            r"(?i)(?:api[_ -]?key|secret(?:[_ -]?key)?|client[_ -]?secret|"
            r"private[_ -]?key|password|passwd|credential(?:s)?|"
            r"access[_ -]?token|refresh[_ -]?token|auth[_ -]?token|"
            r"bearer[_ -]?token|session[_ -]?token)"
            r"\s*(?:value\s*)?(?:is|=|:)\s*[\"']?$",
            str(nearby_text or "")[-80:],
        )
    )
    return bool(strong_base64_shape or sensitive_context)


def derived_text_named_redaction_required(value: Any) -> bool:
    """Admit the exact named-value matchers with a bounded stem scan."""
    source = str(value or "")
    folded = source.casefold()
    if (
        len(folded) != len(source)
        or DERIVED_TEXT_CASEFOLD_POSITION_UNSAFE_RE.search(source)
    ):
        folded = None

    def label_character(character: str) -> bool:
        return bool(
            character
            and (
                "a" <= character <= "z"
                or "A" <= character <= "Z"
                or "0" <= character <= "9"
                or character in {"_", "-"}
            )
        )

    def admitted(stem_start: int, stem_end: int) -> bool:
        run_start = stem_start
        while run_start > 0 and label_character(source[run_start - 1]):
            run_start -= 1
        candidate_starts = {run_start}
        candidate_starts.update(
            index + 1
            for index in range(run_start, stem_start)
            if source[index] == "-"
        )
        for start in sorted(candidate_starts):
            for pattern in (
                DERIVED_TEXT_NAMED_QUOTED_ASSIGNMENT_RE,
                DERIVED_TEXT_NAMED_BARE_ASSIGNMENT_RE,
            ):
                match = pattern.match(source, start)
                if (
                    match is not None
                    and match.start("label") <= stem_start
                    and match.end("label") >= stem_end
                    and not derived_text_privacy_named_value_is_safe(
                        str(match.group("label") or ""),
                        str(match.group("value") or ""),
                    )
                ):
                    return True
            flag_start = start - 2
            if flag_start >= 0 and source[flag_start:start] == "--":
                match = DERIVED_TEXT_SENSITIVE_FLAG_RE.match(
                    source,
                    flag_start,
                )
                if (
                    match is not None
                    and match.start("label") <= stem_start
                    and match.end("label") >= stem_end
                    and not derived_text_privacy_named_value_is_safe(
                        str(match.group("label") or ""),
                        str(match.group("value") or ""),
                    )
                ):
                    return True
        return False

    if folded is None:
        return any(
            admitted(stem.start(), stem.end())
            for stem in DERIVED_TEXT_SENSITIVE_LABEL_PREFILTER_RE.finditer(
                source
            )
        )

    for stem_text in DERIVED_TEXT_SENSITIVE_LABEL_LITERALS:
        stem_length = len(stem_text)
        stem_start = folded.find(stem_text)
        while stem_start >= 0:
            if admitted(stem_start, stem_start + stem_length):
                return True
            stem_start = folded.find(stem_text, stem_start + 1)
    return False


def derived_text_privacy_projection(
    value: Any,
    *,
    max_chars: int | None = None,
) -> dict[str, Any]:
    """Create one safe derived-text view while leaving raw evidence untouched."""
    source = str(value or "")
    redactions: list[dict[str, str]] = []

    def record(kind: str, label: str = "") -> str:
        safe_kind = (
            str(kind)
            if str(kind) in DERIVED_TEXT_PRIVACY_KINDS
            else "credential"
        )
        item = {"kind": safe_kind}
        normalized_label = derived_text_privacy_safe_label(label)
        if normalized_label:
            item["label"] = normalized_label
        redactions.append(item)
        return f"<redacted:{safe_kind}>"

    def redact_pem(match: re.Match[str]) -> str:
        marker = str(match.group("label") or "PRIVATE KEY")
        return (
            f"{match.group('begin')}\n"
            f"{record('private_key', marker)}\n"
            f"{match.group('end')}"
        )

    def redact_named(match: re.Match[str]) -> str:
        label = str(match.group("label") or "")
        value_text = str(match.group("value") or "")
        if derived_text_privacy_named_value_is_safe(label, value_text):
            return match.group(0)
        _unquoted, quote = derived_text_privacy_unquote(value_text)
        placeholder = record(derived_text_privacy_label_kind(label), label)
        return f"{match.group('prefix')}{quote}{placeholder}{quote}"

    redacted = source
    if "-----BEGIN" in redacted:
        if DERIVED_TEXT_PEM_PRIVATE_KEY_RE.search(redacted):
            redacted = DERIVED_TEXT_PEM_PRIVATE_KEY_RE.sub(
                redact_pem,
                redacted,
            )
    if derived_text_named_redaction_required(redacted):
        redacted = DERIVED_TEXT_NAMED_QUOTED_ASSIGNMENT_RE.sub(
            redact_named,
            redacted,
        )
        redacted = DERIVED_TEXT_NAMED_BARE_ASSIGNMENT_RE.sub(
            redact_named,
            redacted,
        )
        redacted = DERIVED_TEXT_SENSITIVE_FLAG_RE.sub(
            redact_named,
            redacted,
        )

    def redact_url(match: re.Match[str]) -> str:
        return (
            f"{match.group('prefix')}"
            f"{record('password', 'url_userinfo')}"
            f"{match.group('suffix')}"
        )

    if "://" in redacted and "@" in redacted:
        if DERIVED_TEXT_URL_CREDENTIAL_RE.search(redacted):
            redacted = DERIVED_TEXT_URL_CREDENTIAL_RE.sub(
                redact_url,
                redacted,
            )

    def redact_authorization(match: re.Match[str]) -> str:
        return f"{match.group('prefix')}{record('token', 'Authorization')}"

    redacted_casefold = redacted.casefold()
    if "authorization" in redacted_casefold or "bearer" in redacted_casefold:
        if DERIVED_TEXT_AUTHORIZATION_RE.search(redacted):
            redacted = DERIVED_TEXT_AUTHORIZATION_RE.sub(
                redact_authorization,
                redacted,
            )
    if DERIVED_TEXT_KNOWN_CREDENTIAL_PREFILTER_RE.search(redacted):
        if DERIVED_TEXT_KNOWN_CREDENTIAL_RE.search(redacted):
            redacted = DERIVED_TEXT_KNOWN_CREDENTIAL_RE.sub(
                lambda _match: record("token"),
                redacted,
            )

    def redact_opaque(match: re.Match[str]) -> str:
        token = str(match.group("value") or "")
        start = max(0, match.start() - 80)
        nearby = redacted[start:match.start()]
        if not derived_text_looks_like_opaque_credential(
            token,
            nearby_text=nearby,
        ):
            return token
        return record("opaque_credential")

    # Most authored source files contain many long identifiers and digests,
    # but none that pass the entropy/context admission below.  Calling
    # ``Pattern.sub`` unconditionally still rebuilds the complete string and
    # pays callback overhead for every benign match.  The read-only pass uses
    # the exact same predicate; only a value that would be redacted admits the
    # rewriting pass, so this skips work without weakening detection.
    opaque_redaction_required = any(
        derived_text_looks_like_opaque_credential(
            str(match.group("value") or ""),
            nearby_text=redacted[
                max(0, match.start() - 80):match.start()
            ],
        )
        for match in DERIVED_TEXT_OPAQUE_CREDENTIAL_RE.finditer(redacted)
    )
    if opaque_redaction_required:
        redacted = DERIVED_TEXT_OPAQUE_CREDENTIAL_RE.sub(
            redact_opaque,
            redacted,
        )
    safe_text = (
        short_text(redacted, max_chars=max_chars)
        if max_chars is not None
        else redacted
    )
    kinds = sorted(
        {
            str(item.get("kind") or "")
            for item in redactions
            if item.get("kind")
        }
    )
    labels = sorted(
        {
            str(item.get("label") or "")
            for item in redactions
            if item.get("label")
        }
    )[:24]
    return {
        "policy_version": DERIVED_TEXT_PRIVACY_POLICY_VERSION,
        "status": "redacted" if redactions else "unchanged",
        "text": safe_text,
        "redaction_count": len(redactions),
        "kinds": kinds,
        "labels": labels,
        "raw_authority_preserved": True,
    }


def derived_text_privacy_text(
    value: Any,
    *,
    max_chars: int | None = None,
) -> str:
    return str(
        derived_text_privacy_projection(
            value,
            max_chars=max_chars,
        ).get("text")
        or ""
    )


__all__ = [
    name
    for name in globals()
    if name.startswith("DERIVED_TEXT_") or name.startswith("derived_text_")
]
