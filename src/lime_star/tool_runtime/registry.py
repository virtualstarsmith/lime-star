"""工具注册表：按名称注册与查找工具，校验参数，执行调用；危险操作执行前先取得批准。

一次调用总是得到一条结果：未知工具、参数不合法、没有取得批准、工具运行时出错，都作为出错的结果交回，
由回合循环继续交给模型（R12.2、R7.13）。结果带一行摘要，随结果项写进会话记录，只用于终端显示。

危险与否按工具固定（决策 D-19）：带 danger 的工具是危险操作。注册表在调用它的执行函数之前，
一定先经批准来源取得批准。这是结构性的保证，不靠每个工具自觉（R7.6）：批准来源由 app 回合入口
在每个回合绑上，它负责向用户提问并把决定写进会话记录；这里不做终端交互。
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

from lime_star.protocol import Approver, Json, Pending, ToolCall, ToolResult, ToolSpec
from lime_star.tool_runtime.schema import problem

REJECTED = "用户拒绝了这次操作，没有执行。"
"""没有取得批准的危险操作的结果：交给模型（R7.13），也是终端上的摘要（R13.15）。"""


@dataclass(frozen=True)
class ToolOutput:
    """工具的一次输出。

    text 是交给模型的内容；出错时 error 为真，text 是给模型看的原因。
    summary 是给终端看的一行摘要（R13.15），不交给模型；留空时取 text 的第一行。
    """

    text: str
    error: bool = False
    summary: str = ""


@dataclass(frozen=True)
class Tool:
    """一个工具：名称、描述、参数模式和执行函数。

    danger 只有危险工具有，注册表在调用执行函数之前先调用它。它返回字符串，就是给用户看的说明，
    批准提示显示它。它返回 ToolOutput，说明这次调用不必批准也不会执行，例如目标越界、父目录不存在：
    那就是这次调用的结果，不进入批准提示（R8.2-S2、R7.2-S1）。
    """

    name: str
    description: str
    parameters: dict[str, Json]
    run: Callable[[Mapping[str, Json]], ToolOutput]
    danger: Callable[[Mapping[str, Json]], str | ToolOutput] | None = None


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

    def execute(self, call: ToolCall, approve: Approver | None = None) -> ToolResult:
        """执行一次调用，总是返回一条结果。

        危险工具要先经 approve 取得批准；没有给 approve，或者批准来源不给批准，它就不执行。
        """
        tool = self.find(call.name)
        if tool is None:
            return _failed(call.call_id, f"没有名为 {call.name} 的工具。")
        try:
            arguments = _arguments(call.arguments, tool.parameters)
        except BadArguments as exc:
            return _failed(call.call_id, str(exc))
        try:
            if tool.danger is not None:
                plan = tool.danger(arguments)
                if isinstance(plan, ToolOutput):
                    return _result(call.call_id, plan)
                granted = approve is not None and approve(
                    Pending(call.call_id, call.name, call.arguments, plan)
                )
                if not granted:
                    return _failed(call.call_id, REJECTED)
            output = tool.run(arguments)
        except Exception as exc:
            # 只写异常类名：异常文本可能带着不该交给模型的内容。
            # Ctrl+C 不是 Exception，不在这里接：它由回合循环处理。
            return _failed(call.call_id, f"工具运行出错（{type(exc).__name__}）。")
        return _result(call.call_id, output)

    def approved_by(self, approve: Approver) -> Granted:
        """把这个注册表和一个批准来源绑成一个工具集，它的危险操作都要先经这个来源批准。"""
        return Granted(self, approve)


@dataclass(frozen=True)
class Granted:
    """注册表加上一个批准来源。回合循环拿到的工具集就是它。"""

    registry: Registry
    approve: Approver

    def specs(self) -> tuple[ToolSpec, ...]:
        return self.registry.specs()

    def execute(self, call: ToolCall) -> ToolResult:
        return self.registry.execute(call, self.approve)


def _failed(call_id: str, reason: str) -> ToolResult:
    """出错的工具结果：同一句说明既交给模型，也作为给终端看的摘要。"""
    return ToolResult(call_id, reason, error=True, summary=reason)


def _result(call_id: str, output: ToolOutput) -> ToolResult:
    """工具的输出落成一条结果：摘要留空时取内容的第一行。"""
    return ToolResult(
        call_id, output.text, output.error, output.summary or output.text.split("\n")[0]
    )


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
