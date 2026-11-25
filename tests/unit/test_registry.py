"""注册表与参数校验的单元测试：注册与查找、未知工具、参数不合法、运行时出错。

证据等级：Unit。对应路线图 P2 的退出条件 3，以及 R12.2 里"工具出错也是结果"。
"""

import json
from collections.abc import Mapping
from pathlib import Path

import pytest

from lime_star.protocol import Json, ToolCall, ToolResult
from lime_star.tool_runtime import Registry, Tool, ToolOutput, default_tools, read_file

SCHEMA: dict[str, Json] = {
    "type": "object",
    "properties": {"path": {"type": "string"}, "count": {"type": "integer"}},
    "required": ["path"],
}


def echo(arguments: Mapping[str, Json]) -> ToolOutput:
    return ToolOutput(f"读到 {arguments['path']!r}")


def call(name: str, arguments: str = '{"path": "a.txt"}', call_id: str = "c1") -> ToolCall:
    return ToolCall(call_id=call_id, name=name, arguments=arguments)


def failed(reason: str) -> ToolResult:
    """出错的工具结果：同一句说明既交给模型，也是给终端看的摘要。"""
    return ToolResult("c1", reason, error=True, summary=reason)


def test_a_tool_is_registered_by_name_and_found() -> None:
    tool = Tool("echo", "照读参数", SCHEMA, echo)
    registry = Registry()
    assert registry.find("echo") is None
    registry.register(tool)
    assert registry.find("echo") is tool
    assert registry.find("nope") is None


def test_specs_keep_the_registration_order() -> None:
    first = Tool("a", "甲", SCHEMA, echo)
    second = Tool("b", "乙", SCHEMA, echo)
    specs = Registry([second, first]).specs()
    assert [(spec.name, spec.description, spec.parameters) for spec in specs] == [
        ("b", "乙", SCHEMA),
        ("a", "甲", SCHEMA),
    ]


def test_a_duplicate_name_is_rejected() -> None:
    registry = Registry([Tool("echo", "一", SCHEMA, echo)])
    with pytest.raises(ValueError, match="echo 已经注册"):
        registry.register(Tool("echo", "二", SCHEMA, echo))


def test_an_unknown_tool_is_an_error_result() -> None:
    assert Registry().execute(call("nope")) == failed("没有名为 nope 的工具。")


@pytest.mark.parametrize(
    ("arguments", "content"),
    [
        ("{not json", "参数不是合法的 JSON。"),
        ("[1, 2]", "参数必须是一个 JSON 对象。"),
        ("", "缺少必填的参数：path。"),
        ('{"count": 1}', "缺少必填的参数：path。"),
        ('{"path": 7}', "参数 path：应当是字符串，实际是整数。"),
        ('{"path": "a.txt", "count": "3"}', "参数 count：应当是整数，实际是字符串。"),
        ('{"path": "a.txt", "count": true}', "参数 count：应当是整数，实际是布尔值。"),
    ],
)
def test_bad_arguments_never_reach_the_tool(arguments: str, content: str) -> None:
    """参数不合法时工具函数不会被调用，模型收到的是说出原因的结果。"""
    calls: list[Mapping[str, Json]] = []

    def spy(arguments: Mapping[str, Json]) -> ToolOutput:
        calls.append(arguments)
        return ToolOutput("不该走到这里")

    registry = Registry([Tool("echo", "", SCHEMA, spy)])
    assert registry.execute(call("echo", arguments)) == failed(content)
    assert calls == []


def test_valid_arguments_reach_the_tool() -> None:
    registry = Registry([Tool("echo", "", SCHEMA, echo)])
    result = registry.execute(call("echo", '{"path": "a.txt", "count": 2, "extra": "随它"}'))
    assert result == ToolResult("c1", "读到 'a.txt'", summary="读到 'a.txt'")


def test_nested_values_are_checked_against_items() -> None:
    schema: dict[str, Json] = {
        "type": "object",
        "properties": {"paths": {"type": "array", "items": {"type": "string"}}},
        "required": ["paths"],
    }
    registry = Registry([Tool("echo", "", schema, echo)])
    result = registry.execute(call("echo", '{"paths": ["a", 2]}'))
    assert result == failed("参数 paths 的第 2 项：应当是字符串，实际是整数。")


def test_a_tool_that_raises_gives_an_error_result_naming_only_the_exception() -> None:
    """异常文本可能带着不该交给模型的内容，所以只写异常类名。"""

    def boom(_arguments: Mapping[str, Json]) -> ToolOutput:
        raise RuntimeError("DETAIL-THAT-MUST-NOT-LEAK")

    registry = Registry([Tool("boom", "", SCHEMA, boom)])
    result = registry.execute(call("boom"))
    assert result == failed("工具运行出错（RuntimeError）。")


def test_an_error_output_keeps_its_error_flag() -> None:
    def refuse(_arguments: Mapping[str, Json]) -> ToolOutput:
        return ToolOutput("被拒绝。", error=True)

    registry = Registry([Tool("refuse", "", SCHEMA, refuse)])
    assert registry.execute(call("refuse")) == ToolResult("c1", "被拒绝。", True, "被拒绝。")


def test_read_file_is_offered_with_name_description_and_schema(tmp_path: Path) -> None:
    """路线图 P2 的退出条件 3：名称、描述、JSON Schema 参数和执行函数齐备。"""
    tool = read_file(tmp_path)
    [spec] = Registry([tool]).specs()
    assert (spec.name, spec.description, spec.parameters) == (
        "read_file",
        tool.description,
        {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "相对工作目录的文件路径。"}},
            "required": ["path"],
        },
    )
    assert "2000 行" in spec.description
    assert callable(tool.run)
    assert json.dumps(spec.parameters)  # 参数模式必须是能原样发给接口的 JSON


def test_a_summary_is_kept_or_taken_from_the_first_line() -> None:
    """R13.15 的依据：工具给出的摘要原样保留，没给时取内容的第一行；摘要不进交给模型的内容。"""

    def brief(_arguments: Mapping[str, Json]) -> ToolOutput:
        return ToolOutput("第一行\n第二行", summary="一共两行")

    def plain(_arguments: Mapping[str, Json]) -> ToolOutput:
        return ToolOutput("第一行\n第二行")

    registry = Registry([Tool("brief", "", SCHEMA, brief), Tool("plain", "", SCHEMA, plain)])
    brief_result = registry.execute(call("brief"))
    assert (brief_result.content, brief_result.summary) == ("第一行\n第二行", "一共两行")
    assert registry.execute(call("plain")).summary == "第一行"


def test_the_default_tools_register_read_file(tmp_path: Path) -> None:
    """正式命令的工具集：路线图 P3 只有 read_file。"""
    [spec] = default_tools(tmp_path).specs()
    assert spec.name == "read_file"
