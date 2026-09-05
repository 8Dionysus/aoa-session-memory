"""Focused contract tests for bounded JavaScript/Python command parsers.

These tests load the parser source directly.  They intentionally avoid the
session-memory runtime monolith so parser feedback remains useful on its own.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
import warnings
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "aoa_session_memory_entity_usage_parsers.py"
)
spec = importlib.util.spec_from_file_location(
    "aoa_session_memory_entity_usage_parsers_test_source",
    SCRIPT,
)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_javascript_mask_and_delimiter_ignore_inert_text() -> None:
    source = (
        'const text = ") /* ignored */"; '
        "/* ignored ( ) */ tools.exec_command({cmd: 'printf ok'}); "
        "// ignored tools.exec_command(\n"
    )
    mask = module.entity_usage_javascript_code_mask(source)
    call_start = source.index("tools.exec_command")
    opening = source.index("(", call_start)
    closing = module.entity_usage_javascript_matching_delimiter(
        source,
        start=opening,
        opening="(",
        closing=")",
        code_mask=mask,
    )

    assert closing is not None
    assert source[closing] == ")"
    quoted_start = source.index('"')
    quoted_end = source.index('"', quoted_start + 1)
    assert not any(mask[quoted_start : quoted_end + 1])
    assert mask[source.index("tools.exec_command")] == 1


def test_javascript_custom_exec_parser_resolves_literals_variables_and_maps() -> None:
    source = (
        "const first = 'printf one'; "
        "const rows = [['printf two'], ['printf three']]; "
        "rows.map(([cmd]) => tools.exec_command({cmd})); "
        "tools.exec_command({command: first});"
    )
    payload = {"type": "custom_tool_call", "name": "exec", "input": source}

    assert module.entity_usage_custom_exec_command_candidates(payload) == [
        "printf two",
        "printf three",
        "printf one",
    ]


def test_javascript_custom_exec_parser_suppresses_literal_syntax_warnings() -> None:
    source = (
        r'''const r = await tools.exec_command({cmd: "rg '\$HOME' README.md"}); '''
        "text(r.output);"
    )
    payload = {"type": "custom_tool_call", "name": "exec", "input": source}

    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        commands = module.entity_usage_custom_exec_command_candidates(payload)

    assert commands == [r"rg '\$HOME' README.md"]
    assert not [item for item in captured if item.category is SyntaxWarning]


def test_python_command_vectors_accept_literal_argv_shapes_only() -> None:
    scalar = ast.parse("['python3', '-m', 'example']").body[0].value
    nested = ast.parse("[['python3', '-m', 'one'], ['python3', '-m', 'two']]").body[0].value
    invalid = ast.parse("[Path('not-a-literal')]").body[0].value

    assert module.entity_usage_python_command_vectors(scalar) == [
        ["python3", "-m", "example"]
    ]
    assert module.entity_usage_python_command_vectors(nested) == [
        ["python3", "-m", "one"],
        ["python3", "-m", "two"],
    ]
    assert module.entity_usage_python_command_vectors(invalid) == []


def test_python_heredoc_parser_recovers_direct_and_loop_subprocess_calls() -> None:
    command = """python3 - <<'PY'
import subprocess
argv = ['python3', '-m', 'direct']
subprocess.run(argv)
for item in [['python3', '-m', 'loop']]:
    subprocess.check_call(item)
PY
"""

    commands = module.entity_usage_python_heredoc_subprocess_commands(command)
    assert set(commands) == {
        "python3 -m direct",
        "python3 -m loop",
    }
    assert len(commands) == 2


def test_custom_exec_parser_requires_structured_custom_exec_payload() -> None:
    direct = {
        "type": "function_call",
        "name": "exec",
        "input": "tools.exec_command({cmd: 'printf safe'});",
    }
    foreign = {
        "type": "custom_tool_call",
        "name": "read_file",
        "input": "tools.exec_command({cmd: 'printf hidden'});",
    }

    assert module.entity_usage_custom_exec_command_candidates(direct) == []
    assert module.entity_usage_custom_exec_command_candidates(foreign) == []
