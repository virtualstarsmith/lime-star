"""会话记录一行的 JSON Schema 与 protocol 的数据类是否一致（契约 thread-items）。

证据等级：Unit。不为校验 JSON Schema 引入依赖，核对三件事：类型枚举、每个类型分支的字段名、
会话记录实际写出的一行带的字段。schema 变更后的显式确认由 node scripts/check-contracts.mjs 负责。
"""

import json
from dataclasses import fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, get_args

import pytest

from lime_star.protocol import (
    ENVELOPE,
    ITEM_KINDS,
    Approval,
    Entry,
    Item,
    ModelText,
    Outcome,
    Reasoning,
    ToolCall,
    ToolResult,
    TurnEnd,
    TurnStart,
    UserMessage,
)
from lime_star.thread_store import encode

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "protocol" / "thread-items.schema.json"
WHEN = datetime(2026, 11, 25, tzinfo=UTC)
SAMPLES: list[Item] = [
    UserMessage("你好"),
    ModelText("答"),
    Reasoning("想一想"),
    ToolCall(call_id="c1", name="read_file", arguments="{}"),
    ToolResult(call_id="c1", content="内容", error=True, summary="摘要"),
    Approval(call_id="c2", name="run_command", arguments="{}", decision="rejected"),
    TurnStart(),
    TurnEnd(outcome=Outcome.DONE, reason=""),
]


@pytest.fixture(scope="module")
def schema() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(SCHEMA.read_text(encoding="utf-8"))
    return loaded


def names(item: Item) -> list[str]:
    return sorted(field.name for field in fields(type(item)))


def test_the_envelope_is_fixed(schema: dict[str, Any]) -> None:
    assert schema["required"] == [*ENVELOPE, "type"]
    assert sorted(schema["properties"]) == sorted([*ENVELOPE, "type"])


def test_the_type_enum_lists_every_item_kind_in_order(schema: dict[str, Any]) -> None:
    kinds = [kind.kind for kind in ITEM_KINDS]
    assert schema["properties"]["type"]["enum"] == kinds
    assert sorted(defs := schema["$defs"]) == sorted(kinds)
    assert sorted(
        ref.rsplit("/", 1)[1] for ref in (branch["$ref"] for branch in schema["oneOf"])
    ) == sorted(defs)


@pytest.mark.parametrize("sample", SAMPLES, ids=lambda sample: type(sample).kind)
def test_each_branch_matches_its_dataclass(schema: dict[str, Any], sample: Item) -> None:
    """每个类型分支要求的字段、列出的字段，与数据类的字段逐一相同。"""
    branch = schema["$defs"][type(sample).kind]
    assert branch["properties"]["type"]["const"] == type(sample).kind
    assert sorted(branch["required"]) == names(sample)
    assert sorted(branch["properties"]) == sorted(["type", *names(sample)])


def test_written_lines_carry_exactly_the_schema_fields(schema: dict[str, Any]) -> None:
    """会话记录写出的一行不多不少，正好是信封、类型名和这个类型的字段。"""
    for sample in SAMPLES:
        record = encode(Entry(1, WHEN, "thread-1", "turn-1", sample))
        kind = type(sample).kind
        expected = {*ENVELOPE, "type", *schema["$defs"][kind]["required"]}
        assert sorted(record) == sorted(expected), kind


def test_the_enums_inside_branches_match_their_types(schema: dict[str, Any]) -> None:
    outcomes = [outcome.value for outcome in Outcome]
    assert schema["$defs"]["turn_end"]["properties"]["outcome"]["enum"] == outcomes
    decisions = list(get_args(fields(Approval)[3].type))
    assert (
        schema["$defs"]["approval"]["properties"]["decision"]["enum"]
        == decisions
        == [
            "approved",
            "rejected",
        ]
    )


def test_booleans_and_strings_are_typed_in_the_schema(schema: dict[str, Any]) -> None:
    result = schema["$defs"]["tool_result"]["properties"]
    assert result["error"]["type"] == "boolean"
    assert {
        name: prop["type"] for name, prop in result.items() if name not in ("type", "error")
    } == {
        "call_id": "string",
        "content": "string",
        "summary": "string",
    }
