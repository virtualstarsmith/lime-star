"""回合的结局，以及回合循环与模型边界之间的数据形状。

边界以 internal/aiprompts/architecture.md 为准：这里没有运行时逻辑，也不做 I/O。
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from lime_star.protocol.items import Item, ToolCall, ToolSpec


class Outcome(StrEnum):
    """回合的结局（R12.7）。步数上限见 R12.3。"""

    DONE = "done"
    ERROR = "error"
    CANCELLED = "cancelled"
    STEP_LIMIT = "step_limit"


@dataclass(frozen=True)
class TurnResult:
    """一个回合的结局：出错、取消或达到上限时的原因，以及模型的最终回复（没有回复时为空串）。"""

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
        self, turn_id: str, history: Sequence[Item], tools: Sequence[ToolSpec]
    ) -> ModelResult: ...
