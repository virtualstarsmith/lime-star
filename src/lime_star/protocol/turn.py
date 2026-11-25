"""回合的结局怎样回到调用方，以及回合循环与模型边界之间的数据形状。

边界以 internal/aiprompts/architecture.md 为准：这里没有运行时逻辑，也不做 I/O。
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from lime_star.protocol.items import Entry, Outcome, ToolCall, ToolSpec

Clock = Callable[[], datetime]
NewId = Callable[[], str]


@dataclass(frozen=True)
class TurnResult:
    """一个回合的结局，回到调用方手里：出错、取消或达到上限时的原因，以及模型的最终回复。

    同样的事实也写在会话记录的回合结局项里（R12.7）；这里带上最终回复，方便只关心结果的调用方。
    """

    turn_id: str
    outcome: Outcome
    reason: str
    reply: str


@dataclass(frozen=True)
class ModelReply:
    """模型的一次完整响应：文本、推理、工具调用可以只有其中一种，也可以兼有。"""

    text: str = ""
    reasoning: str = ""
    calls: tuple[ToolCall, ...] = ()


@dataclass(frozen=True)
class ModelFailure:
    """一次模型请求失败。reason 是给用户看的类别说明，不带接口返回的错误正文（R3.3、R12.4）。"""

    reason: str


ModelResult = ModelReply | ModelFailure
"""模型边界的一次请求的结局：一次响应，或者一次失败。"""


class Model(Protocol):
    """回合循环眼里的模型边界：带上到此刻为止的全部项和可用的工具，发起一次请求。"""

    def respond(
        self,
        turn_id: str,
        history: Sequence[Entry],
        tools: Sequence[ToolSpec],
    ) -> ModelResult: ...
