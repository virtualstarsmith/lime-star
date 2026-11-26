"""回合入口（唯一边界）：CLI 与测试从这里提交回合、读取会话、回应审批、恢复会话。

边界以 internal/aiprompts/architecture.md 为准：这里不做第二套执行链，
CLI 不经过这里不得调用模型。这里也是装配点，把循环、模型边界、工具边界和会话记录接在一起。
危险操作要等用户批准：批准来源在这里绑定，CLI 用 Session.respond_action 交回用户的决定。
恢复会话也只从这里进：resume_session 只凭 thread_store 的会话记录读回历史（需求 R9）。
"""

from lime_star.app.session import (
    Ask,
    NoSession,
    Recap,
    Session,
    SessionError,
    open_session,
    resume_session,
)
from lime_star.model_provider.config import ConfigError
from lime_star.protocol import Outcome, TurnResult

__all__ = [
    "Ask",
    "ConfigError",
    "NoSession",
    "Outcome",
    "Recap",
    "Session",
    "SessionError",
    "TurnResult",
    "open_session",
    "resume_session",
]
