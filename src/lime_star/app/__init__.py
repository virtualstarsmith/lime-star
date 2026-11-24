"""回合入口（唯一边界）：CLI 与测试从这里提交回合、读取会话。

边界以 internal/aiprompts/architecture.md 为准：这里不做第二套执行链，
CLI 不经过这里不得调用模型。这里也是装配点，把循环、模型边界和工具边界接在一起。
"""

from lime_star.app.session import Record, Session, SessionError, open_session
from lime_star.model_provider.config import ConfigError
from lime_star.protocol import Outcome, TurnResult

__all__ = [
    "ConfigError",
    "Outcome",
    "Record",
    "Session",
    "SessionError",
    "TurnResult",
    "open_session",
]
