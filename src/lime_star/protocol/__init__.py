"""协议类型：一个会话里流通的数据形状，以及回合循环与三个边界之间的接口。

边界以 internal/aiprompts/architecture.md 为准：这里没有运行时逻辑，也不做 I/O。
protocol 被各层引用，自身不依赖任何一层。项的 JSON Schema 契约随路线图 P3 登记。
"""

from lime_star.protocol.items import (
    Item,
    Json,
    ModelText,
    Reasoning,
    ToolCall,
    ToolResult,
    ToolSet,
    ToolSpec,
    Transcript,
    UserMessage,
)
from lime_star.protocol.turn import (
    Model,
    ModelFailure,
    ModelReply,
    ModelResult,
    Outcome,
    TurnResult,
)

__all__ = [
    "Item",
    "Json",
    "Model",
    "ModelFailure",
    "ModelReply",
    "ModelResult",
    "ModelText",
    "Outcome",
    "Reasoning",
    "ToolCall",
    "ToolResult",
    "ToolSet",
    "ToolSpec",
    "Transcript",
    "TurnResult",
    "UserMessage",
]
