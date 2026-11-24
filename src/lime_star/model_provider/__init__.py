"""模型边界：模型配置、OpenAI 兼容请求、请求日志。

边界以 internal/aiprompts/architecture.md 为准：这里不做回合循环、工具权限和会话持久化。
"""

from lime_star.model_provider.config import (
    API_KEY_VAR,
    BASE_URL_VAR,
    MODEL_VAR,
    ConfigError,
    ModelConfig,
    load_config,
)
from lime_star.model_provider.errors import ErrorKind, Failure, classify
from lime_star.model_provider.provider import (
    Clock,
    Message,
    ModelError,
    NewId,
    Provider,
    Reply,
    new_id,
    utc_now,
)
from lime_star.model_provider.request_log import RequestLog

__all__ = [
    "API_KEY_VAR",
    "BASE_URL_VAR",
    "MODEL_VAR",
    "Clock",
    "ConfigError",
    "ErrorKind",
    "Failure",
    "Message",
    "ModelConfig",
    "ModelError",
    "NewId",
    "Provider",
    "Reply",
    "RequestLog",
    "classify",
    "load_config",
    "new_id",
    "utc_now",
]
