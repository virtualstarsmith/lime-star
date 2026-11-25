"""协议类型：一个会话里流通的数据形状，以及回合循环与三个边界之间的接口。

边界以 internal/aiprompts/architecture.md 为准：这里没有运行时逻辑，也不做 I/O。
protocol 被各层引用，自身不依赖任何一层。会话记录一行的 JSON 形状由仓库根的
protocol/thread-items.schema.json 约定。
"""

from lime_star.protocol.items import (
    ENVELOPE,
    ITEM_KINDS,
    Approval,
    Entry,
    Item,
    Journal,
    Json,
    ModelText,
    Outcome,
    Reasoning,
    ToolCall,
    ToolResult,
    ToolSet,
    ToolSpec,
    TurnEnd,
    TurnStart,
    UserMessage,
)
from lime_star.protocol.turn import (
    Clock,
    Model,
    ModelFailure,
    ModelReply,
    ModelResult,
    NewId,
    TurnResult,
)

__all__ = [
    "ENVELOPE",
    "ITEM_KINDS",
    "Approval",
    "Clock",
    "Entry",
    "Item",
    "Json",
    "Journal",
    "Model",
    "ModelFailure",
    "ModelReply",
    "ModelResult",
    "ModelText",
    "NewId",
    "Outcome",
    "Reasoning",
    "ToolCall",
    "ToolResult",
    "ToolSet",
    "ToolSpec",
    "TurnEnd",
    "TurnResult",
    "TurnStart",
    "UserMessage",
]
