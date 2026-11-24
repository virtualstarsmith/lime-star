"""会话记录里的项，以及回合循环与工具、会话记录之间的接口。

项是一个会话里按发生顺序写下的东西：用户消息、模型文本、推理、工具调用、工具结果。
批准、回合开始、回合结局三类项，以及每项的标识、序号和时间，随路线图 P3 登记。
边界以 internal/aiprompts/architecture.md 为准：这里只有数据形状和接口，没有运行时逻辑，也不做 I/O。
"""

from dataclasses import dataclass
from typing import Protocol

Json = str | int | float | bool | None | list["Json"] | dict[str, "Json"]
"""JSON 里能出现的一个值。工具的参数模式和工具参数都用它表示。"""


@dataclass(frozen=True)
class UserMessage:
    """用户提交的一条消息。"""

    content: str


@dataclass(frozen=True)
class ModelText:
    """模型产出的一段文本。"""

    content: str


@dataclass(frozen=True)
class Reasoning:
    """模型产出的一段推理。"""

    content: str


@dataclass(frozen=True)
class ToolCall:
    """模型请求的一次工具调用。arguments 是模型给出的原始 JSON 文本，原样记录，不改写。"""

    call_id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class ToolResult:
    """一次工具调用的结果。出错的结果也是结果，照样交给模型（R12.2）。"""

    call_id: str
    content: str
    error: bool = False


Item = UserMessage | ModelText | Reasoning | ToolCall | ToolResult
"""会话记录里的一项。"""


class ToolSpec(Protocol):
    """工具向外的说明：模型边界把它转成接口里的工具定义，注册表按它校验参数。"""

    @property
    def name(self) -> str: ...

    @property
    def description(self) -> str: ...

    @property
    def parameters(self) -> dict[str, Json]: ...


class ToolSet(Protocol):
    """回合循环眼里的工具边界：说出有哪些工具，执行一次调用并总是给出结果。"""

    def specs(self) -> tuple[ToolSpec, ...]: ...

    def execute(self, call: ToolCall) -> ToolResult: ...


class Transcript(Protocol):
    """会话记录的写入端：按发生顺序追加一项。"""

    def append(self, item: Item) -> None: ...
