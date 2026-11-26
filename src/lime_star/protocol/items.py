"""会话记录里的项，以及回合循环与工具、会话记录之间的接口。

一个会话里按发生顺序写下的每一件事是一项：用户消息、模型文本、推理、工具调用、工具结果、批准、
回合开始、回合结局。带信封的一项是 Entry：序号、时间、所属的会话和回合。
每类项的 kind 是它写进会话记录时的类型名；一行记录的 JSON 形状由仓库根的
protocol/thread-items.schema.json 约定（契约 thread-items）。
边界以 internal/aiprompts/architecture.md 为准：这里只有数据形状和接口，没有运行时逻辑，也不做 I/O。
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import ClassVar, Literal, Protocol

Json = str | int | float | bool | None | list["Json"] | dict[str, "Json"]
"""JSON 里能出现的一个值。工具的参数模式和工具参数都用它表示。"""


class Outcome(StrEnum):
    """回合的结局（R12.7）。步数上限见 R12.3。

    interrupted 是进程没有收尾就结束的回合：它有开始、没有结局，
    由读取会话记录的一方判为中断并补上（R9.3）。它和 cancelled 分开：后者是用户按 Ctrl+C 取消的。
    """

    DONE = "done"
    ERROR = "error"
    CANCELLED = "cancelled"
    STEP_LIMIT = "step_limit"
    INTERRUPTED = "interrupted"


@dataclass(frozen=True)
class UserMessage:
    """用户提交的一条消息。"""

    kind: ClassVar[str] = "user_message"
    content: str


@dataclass(frozen=True)
class ModelText:
    """模型产出的一段文本。"""

    kind: ClassVar[str] = "model_text"
    content: str


@dataclass(frozen=True)
class Reasoning:
    """模型产出的一段推理。"""

    kind: ClassVar[str] = "reasoning"
    content: str


@dataclass(frozen=True)
class ToolCall:
    """模型请求的一次工具调用。arguments 是模型给出的原始 JSON 文本，原样记录，不改写。"""

    kind: ClassVar[str] = "tool_call"
    call_id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class ToolResult:
    """一次工具调用的结果。出错的结果也是结果，照样交给模型（R12.2）。

    content 是交给模型的内容；summary 是给终端看的一行摘要，不交给模型。
    """

    kind: ClassVar[str] = "tool_result"
    call_id: str
    content: str
    error: bool = False
    summary: str = ""


Decision = Literal["approved", "rejected"]
"""用户对一次危险操作的回应，只有这两种。"""


@dataclass(frozen=True)
class Approval:
    """用户对一次危险操作的回应（R7.12）。

    决定做出之后、操作执行之前写下，所以它夹在这次工具调用和它的结果之间。
    等待中被 Ctrl+C 打断的操作没有决定，也就没有这一项。
    """

    kind: ClassVar[str] = "approval"
    call_id: str
    name: str
    arguments: str
    decision: Decision


@dataclass(frozen=True)
class Pending:
    """等待用户决定的一次危险操作（R7.6）。

    note 是工具边界给出的说明，给用户看：批准提示显示它，比如目标路径、新建还是覆盖、
    全部要写入的内容，或者原样的命令（R7.7、R7.8）。
    """

    call_id: str
    name: str
    arguments: str
    note: str


@dataclass(frozen=True)
class TurnStart:
    """一个回合的开始。"""

    kind: ClassVar[str] = "turn_start"


@dataclass(frozen=True)
class TurnEnd:
    """一个回合的结局和原因（R12.7）。完成时原因为空串。"""

    kind: ClassVar[str] = "turn_end"
    outcome: Outcome
    reason: str


Item = UserMessage | ModelText | Reasoning | ToolCall | ToolResult | Approval | TurnStart | TurnEnd
"""会话记录里的一项。"""

ITEM_KINDS: tuple[type[Item], ...] = (
    UserMessage,
    ModelText,
    Reasoning,
    ToolCall,
    ToolResult,
    Approval,
    TurnStart,
    TurnEnd,
)
"""全部项的类型，顺序同 JSON Schema 里的枚举。"""

ENVELOPE = ("seq", "time", "thread_id", "turn_id")
"""信封的字段：序号、时间、所属的会话和回合。"""


@dataclass(frozen=True)
class Entry:
    """会话记录里带信封的一项。"""

    seq: int
    time: datetime
    thread_id: str
    turn_id: str
    item: Item


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


Approver = Callable[[Pending], bool]
"""批准来源：工具边界在执行危险操作之前请求一次批准，返回 True 才算批准。

拿不到批准就是拒绝，包括没有人可问的情形。等待期间按 Ctrl+C，中断照常向上传，操作不会执行。
"""


class Halted(KeyboardInterrupt):
    """工具执行到一半被 Ctrl+C 打断（R12.5）。text 和 summary 是它截至那一刻的结果。

    run_command 用它带回已经产生的输出；循环把它作为这次调用的结果写进会话记录，再以取消结束回合。
    它也是一次 KeyboardInterrupt，所以谁都没有接住它时，回合照样按取消处理。
    """

    def __init__(self, text: str, *, summary: str = "") -> None:
        super().__init__(text)
        self.text = text
        self.summary = summary


Journal = Callable[[Item, str], Entry]
"""会话记录的写入端：追加一项并落盘，返回带信封的这一项。"""
