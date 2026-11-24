"""工具注册表：按名称注册与查找工具，校验参数，执行调用。

一次调用总是得到一条结果：未知工具、参数不合法、工具运行时出错，都作为出错的结果交回，
由回合循环继续交给模型（R12.2）。
"""

import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

from lime_star.protocol import Json, ToolCall, ToolResult, ToolSpec
from lime_star.tool_runtime.schema import problem


@dataclass(frozen=True)
class ToolOutput:
    """工具的一次输出。出错时 error 为真，text 是给模型看的原因。"""

    text: str
    error: bool = False


@dataclass(frozen=True)
class Tool:
    """一个工具：名称、描述、参数模式和执行函数。"""

    name: str
    description: str
    parameters: dict[str, Json]
    run: Callable[[Mapping[str, Json]], ToolOutput]


class BadArguments(Exception):
    """模型给出的参数不合法。消息可以直接交给模型。"""


class Registry:
    """一组工具。一个会话用一个实例。"""

    def __init__(self, tools: Iterable[Tool] = ()) -> None:
        self._tools: dict[str, Tool] = {}
        for tool in tools:
            self.register(tool)

    def register(self, tool: Tool) -> None:
        """登记一个工具。名称重复时抛 ValueError。"""
        if tool.name in self._tools:
            raise ValueError(f"工具 {tool.name} 已经注册。")
        self._tools[tool.name] = tool

    def find(self, name: str) -> Tool | None:
        """按名称查找；没有这个工具时返回 None。"""
        return self._tools.get(name)

    def specs(self) -> tuple[ToolSpec, ...]:
        """全部工具的说明，按登记顺序。"""
        return tuple(self._tools.values())

    def execute(self, call: ToolCall) -> ToolResult:
        """执行一次调用，总是返回一条结果。"""
        tool = self.find(call.name)
        if tool is None:
            return ToolResult(call.call_id, f"没有名为 {call.name} 的工具。", error=True)
        try:
            arguments = _arguments(call.arguments, tool.parameters)
        except BadArguments as exc:
            return ToolResult(call.call_id, str(exc), error=True)
        try:
            output = tool.run(arguments)
        except Exception as exc:
            # 只写异常类名：异常文本可能带着不该交给模型的内容。
            return ToolResult(call.call_id, f"工具运行出错（{type(exc).__name__}）。", error=True)
        return ToolResult(call.call_id, output.text, output.error)


def _arguments(raw: str, schema: Mapping[str, Json]) -> Mapping[str, Json]:
    """解析并校验模型给出的参数。空串当作没有参数。"""
    text = raw.strip()
    parsed: Json = {}
    if text:
        try:
            parsed = json.loads(text)
        except ValueError:
            raise BadArguments("参数不是合法的 JSON。") from None
    members = parsed if isinstance(parsed, dict) else None
    if members is None:
        raise BadArguments("参数必须是一个 JSON 对象。")
    found = problem(schema, parsed)
    if found is not None:
        raise BadArguments(f"{found}。")
    return members
