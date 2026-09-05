#!/usr/bin/env python3
"""Portable JavaScript/Python command-shape parsers.

The parser functions intentionally depend only on bounded source text and
structured payloads.  Privacy projection and direct-shell admission remain
owned by the session-memory runtime integration wrapper.
"""

from __future__ import annotations

import ast
import re
import shlex
import warnings
from typing import Any


def literal_eval_untrusted_source(value: Any) -> Any:
    """Parse captured literals without leaking source-authored warnings."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        return ast.literal_eval(value)


def tool_name_from_payload(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("name") or payload.get("tool_name") or "").strip()


def normalized_tool_name(tool_name: str) -> str:
    name = str(tool_name or "").strip()
    if not name:
        return ""
    return name.split(".")[-1]


ENTITY_USAGE_CUSTOM_EXEC_CALL_RE = re.compile(
    r"\btools\.exec_command\s*\(",
)
ENTITY_USAGE_CUSTOM_EXEC_COMMAND_PROPERTY_RE = re.compile(
    r"(?:(?P<quote>['\"])(?:cmd|command|shell_command)(?P=quote)"
    r"|\b(?:cmd|command|shell_command))\s*:"
)
ENTITY_USAGE_CUSTOM_EXEC_COMMAND_SHORTHAND_RE = re.compile(
    r"(?P<prefix>[{,])\s*(?P<name>cmd|command|shell_command)\s*(?P<suffix>[,}])"
)
ENTITY_USAGE_CUSTOM_EXEC_DESTRUCTURED_MAP_RE = re.compile(
    r"\b(?P<collection>[A-Za-z_$][A-Za-z0-9_$]*)"
    r"\.map\s*\(\s*\(\s*\[(?P<bindings>[A-Za-z0-9_$,\s]+)\]\s*\)\s*=>"
)


def entity_usage_javascript_code_mask(source: str) -> bytearray:
    """Mark JavaScript code while excluding quoted text and comments.

    Custom ``exec`` calls are JavaScript wrappers around nested tools.  A
    validator command inside a patch, regex, or documentation string is not a
    shell invocation, so command recovery must first distinguish executable
    wrapper syntax from inert string content.
    """
    mask = bytearray(b"\x01" * len(source))
    index = 0
    while index < len(source):
        if source.startswith("//", index):
            end = source.find("\n", index + 2)
            end = len(source) if end < 0 else end
            mask[index:end] = b"\x00" * (end - index)
            index = end
            continue
        if source.startswith("/*", index):
            end = source.find("*/", index + 2)
            end = len(source) if end < 0 else end + 2
            mask[index:end] = b"\x00" * (end - index)
            index = end
            continue
        quote = source[index]
        if quote not in {"'", '"', "`"}:
            index += 1
            continue
        start = index
        index += 1
        while index < len(source):
            if source[index] == "\\":
                index = min(len(source), index + 2)
                continue
            if source[index] == quote:
                index += 1
                break
            index += 1
        mask[start:index] = b"\x00" * (index - start)
    return mask


def entity_usage_javascript_matching_delimiter(
    source: str,
    *,
    start: int,
    opening: str,
    closing: str,
    code_mask: bytearray,
) -> int | None:
    depth = 0
    for index in range(start, len(source)):
        if not code_mask[index]:
            continue
        if source[index] == opening:
            depth += 1
        elif source[index] == closing:
            depth -= 1
            if depth == 0:
                return index
    return None


def entity_usage_javascript_literal_value(
    source: str,
    *,
    start: int,
    code_mask: bytearray,
) -> str | None:
    if start >= len(source) or source[start] not in {"'", '"', "`"}:
        return None
    end = start + 1
    while end < len(source) and not code_mask[end]:
        end += 1
    literal = source[start:end]
    if len(literal) < 2:
        return None
    if literal[0] == "`" and literal[-1] == "`":
        return literal[1:-1].strip()
    try:
        value = literal_eval_untrusted_source(literal)
    except (SyntaxError, ValueError):
        return None
    return value.strip() if isinstance(value, str) and value.strip() else None


def entity_usage_javascript_variable_expression_start(
    source: str,
    *,
    name: str,
    before: int,
    code_mask: bytearray,
) -> int | None:
    declaration_re = re.compile(
        rf"\b(?:const|let|var)\s+{re.escape(name)}\s*="
    )
    starts = [
        match.end()
        for match in declaration_re.finditer(source, 0, before)
        if code_mask[match.start()]
    ]
    if not starts:
        return None
    start = starts[-1]
    while start < before and source[start].isspace():
        start += 1
    return start


def entity_usage_javascript_array_item_starts(
    source: str,
    *,
    start: int,
    code_mask: bytearray,
) -> list[int]:
    if start >= len(source) or source[start] != "[":
        return []
    end = entity_usage_javascript_matching_delimiter(
        source,
        start=start,
        opening="[",
        closing="]",
        code_mask=code_mask,
    )
    if end is None:
        return []
    item_starts = [start + 1]
    depths = {"(": 0, "[": 0, "{": 0}
    closing_to_opening = {")": "(", "]": "[", "}": "{"}
    for index in range(start + 1, end):
        if not code_mask[index]:
            continue
        char = source[index]
        if char in depths:
            depths[char] += 1
        elif char in closing_to_opening:
            opening = closing_to_opening[char]
            depths[opening] = max(0, depths[opening] - 1)
        elif char == "," and not any(depths.values()):
            item_starts.append(index + 1)
    normalized: list[int] = []
    for item_start in item_starts:
        while item_start < end and source[item_start].isspace():
            item_start += 1
        if item_start < end:
            normalized.append(item_start)
    return normalized


def entity_usage_javascript_array_item_start(
    source: str,
    *,
    start: int,
    item_index: int,
    code_mask: bytearray,
) -> int | None:
    item_starts = entity_usage_javascript_array_item_starts(
        source,
        start=start,
        code_mask=code_mask,
    )
    if item_index >= len(item_starts):
        return None
    return item_starts[item_index]


def entity_usage_javascript_mapped_command_values(
    source: str,
    *,
    name: str,
    call_start: int,
    code_mask: bytearray,
) -> list[str]:
    values: list[str] = []
    for map_match in ENTITY_USAGE_CUSTOM_EXEC_DESTRUCTURED_MAP_RE.finditer(
        source,
        0,
        call_start,
    ):
        if not code_mask[map_match.start()]:
            continue
        bindings = [
            value.strip()
            for value in map_match.group("bindings").split(",")
        ]
        if name not in bindings:
            continue
        map_opening = source.find("(", map_match.start(), map_match.end())
        map_closing = entity_usage_javascript_matching_delimiter(
            source,
            start=map_opening,
            opening="(",
            closing=")",
            code_mask=code_mask,
        )
        if map_closing is None or call_start > map_closing:
            continue
        collection_start = entity_usage_javascript_variable_expression_start(
            source,
            name=map_match.group("collection"),
            before=map_match.start(),
            code_mask=code_mask,
        )
        if collection_start is None:
            continue
        for row_start in entity_usage_javascript_array_item_starts(
            source,
            start=collection_start,
            code_mask=code_mask,
        ):
            value_start = entity_usage_javascript_array_item_start(
                source,
                start=row_start,
                item_index=bindings.index(name),
                code_mask=code_mask,
            )
            if value_start is None:
                continue
            value = entity_usage_javascript_literal_value(
                source,
                start=value_start,
                code_mask=code_mask,
            )
            if value:
                values.append(value)
    return list(dict.fromkeys(values))


def entity_usage_javascript_command_expression(
    source: str,
    *,
    start: int,
    before: int,
    code_mask: bytearray,
    depth: int = 0,
) -> str | None:
    if depth > 4:
        return None
    while start < len(source) and source[start].isspace():
        start += 1
    direct = entity_usage_javascript_literal_value(
        source,
        start=start,
        code_mask=code_mask,
    )
    if direct:
        return direct
    reference = re.match(
        r"(?P<name>[A-Za-z_$][A-Za-z0-9_$]*)(?:\[(?P<index>\d+)\])?",
        source[start:],
    )
    if not reference:
        return None
    variable_start = entity_usage_javascript_variable_expression_start(
        source,
        name=reference.group("name"),
        before=before,
        code_mask=code_mask,
    )
    if variable_start is None:
        return None
    if reference.group("index") is not None:
        variable_start = entity_usage_javascript_array_item_start(
            source,
            start=variable_start,
            item_index=int(reference.group("index")),
            code_mask=code_mask,
        )
        if variable_start is None:
            return None
    return entity_usage_javascript_command_expression(
        source,
        start=variable_start,
        before=before,
        code_mask=code_mask,
        depth=depth + 1,
    )


def entity_usage_custom_exec_command_candidates(payload: dict[str, Any]) -> list[str]:
    if (
        str(payload.get("type") or "") != "custom_tool_call"
        or normalized_tool_name(tool_name_from_payload(payload)) != "exec"
    ):
        return []
    raw_source = payload.get("input")
    if not isinstance(raw_source, str) or not raw_source.strip():
        return []
    source = raw_source[:131072]
    code_mask = entity_usage_javascript_code_mask(source)
    candidates: list[str] = []
    for call_match in ENTITY_USAGE_CUSTOM_EXEC_CALL_RE.finditer(source):
        if not code_mask[call_match.start()]:
            continue
        opening = source.find("(", call_match.start(), call_match.end())
        closing = entity_usage_javascript_matching_delimiter(
            source,
            start=opening,
            opening="(",
            closing=")",
            code_mask=code_mask,
        )
        if closing is None:
            continue
        for property_match in ENTITY_USAGE_CUSTOM_EXEC_COMMAND_PROPERTY_RE.finditer(
            source,
            opening + 1,
            closing,
        ):
            # A JSON-style property key (``{"cmd": ...}``) is quoted and
            # therefore masked as inert string content.  Its trailing colon is
            # still executable object syntax; checking that position admits
            # real quoted keys without matching ``"cmd: ..."`` inside a value
            # or documentation string.
            property_syntax_index = max(
                property_match.start(),
                property_match.end() - 1,
            )
            if not code_mask[property_syntax_index]:
                continue
            value = entity_usage_javascript_command_expression(
                source,
                start=property_match.end(),
                before=call_match.start(),
                code_mask=code_mask,
            )
            if value:
                candidates.append(value)
            else:
                reference = re.match(
                    r"(?P<name>[A-Za-z_$][A-Za-z0-9_$]*)",
                    source[property_match.end() :],
                )
                if reference:
                    candidates.extend(
                        entity_usage_javascript_mapped_command_values(
                            source,
                            name=reference.group("name"),
                            call_start=call_match.start(),
                            code_mask=code_mask,
                        )
                    )
        for shorthand_match in ENTITY_USAGE_CUSTOM_EXEC_COMMAND_SHORTHAND_RE.finditer(
            source,
            opening + 1,
            closing,
        ):
            name_start = shorthand_match.start("name")
            if not code_mask[name_start]:
                continue
            value = entity_usage_javascript_command_expression(
                source,
                start=name_start,
                before=call_match.start(),
                code_mask=code_mask,
            )
            if value:
                candidates.append(value)
            else:
                candidates.extend(
                    entity_usage_javascript_mapped_command_values(
                        source,
                        name=shorthand_match.group("name"),
                        call_start=call_match.start(),
                        code_mask=code_mask,
                    )
                )
        if len(candidates) >= 16:
            break
    return list(dict.fromkeys(candidate for candidate in candidates if candidate))


def entity_usage_python_command_vectors(node: ast.AST) -> list[list[str]]:
    try:
        value = literal_eval_untrusted_source(node)
    except (TypeError, ValueError, SyntaxError):
        return []
    if (
        isinstance(value, (list, tuple))
        and value
        and all(isinstance(item, str) for item in value)
    ):
        return [[str(item) for item in value]]
    if isinstance(value, (list, tuple)):
        return [
            [str(item) for item in candidate]
            for candidate in value
            if (
                isinstance(candidate, (list, tuple))
                and candidate
                and all(isinstance(item, str) for item in candidate)
            )
        ]
    return []


def entity_usage_python_subprocess_call(node: ast.Call) -> bool:
    function = node.func
    if not isinstance(function, ast.Attribute):
        return False
    if function.attr not in {"Popen", "call", "check_call", "check_output", "run"}:
        return False
    return isinstance(function.value, ast.Name) and function.value.id == "subprocess"


def entity_usage_python_heredoc_subprocess_commands(command: str) -> list[str]:
    """Recover static argv vectors that an executed Python heredoc invokes."""
    commands: list[str] = []
    heredoc_re = re.compile(
        r"<<-?\s*(?P<quote>['\"]?)(?P<marker>[A-Za-z_][A-Za-z0-9_]*)"
        r"(?P=quote)[^\n]*\n"
    )
    for heredoc in heredoc_re.finditer(command):
        marker = heredoc.group("marker")
        terminator = re.search(
            rf"(?m)^{re.escape(marker)}\s*$",
            command[heredoc.end() :],
        )
        if not terminator:
            continue
        body = command[
            heredoc.end() : heredoc.end() + terminator.start()
        ]
        try:
            tree = ast.parse(body)
        except SyntaxError:
            continue
        assigned_vectors: dict[str, list[list[str]]] = {}
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            value = node.value
            vectors = entity_usage_python_command_vectors(value)
            if not vectors:
                continue
            targets = (
                node.targets
                if isinstance(node, ast.Assign)
                else [node.target]
            )
            for target in targets:
                if isinstance(target, ast.Name):
                    assigned_vectors[target.id] = vectors
        for node in ast.walk(tree):
            if isinstance(node, ast.For) and isinstance(node.target, ast.Name):
                vectors = entity_usage_python_command_vectors(node.iter)
                if vectors and any(
                    isinstance(candidate, ast.Call)
                    and entity_usage_python_subprocess_call(candidate)
                    and candidate.args
                    and isinstance(candidate.args[0], ast.Name)
                    and candidate.args[0].id == node.target.id
                    for candidate in ast.walk(node)
                ):
                    commands.extend(shlex.join(vector) for vector in vectors)
            if not isinstance(node, ast.Call) or not entity_usage_python_subprocess_call(node):
                continue
            if not node.args:
                continue
            vectors = entity_usage_python_command_vectors(node.args[0])
            if isinstance(node.args[0], ast.Name):
                vectors = assigned_vectors.get(node.args[0].id, [])
            commands.extend(shlex.join(vector) for vector in vectors)
    return list(dict.fromkeys(commands))
