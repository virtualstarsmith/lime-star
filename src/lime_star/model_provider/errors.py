"""模型请求失败的归类（需求 R12.4、R3.3）。

只产生类别、接口状态码和给用户看的说明，不带接口返回的错误正文。
"""

from dataclasses import dataclass
from enum import StrEnum

import openai

# 上下文超时，各家 OpenAI 兼容接口的措辞不完全一样，按这几种写法识别。
_OVERFLOW_MARKERS = ("context_length_exceeded", "context length", "context window")


class ErrorKind(StrEnum):
    """模型请求失败的类别。值写进请求日志，label 显示在终端上。"""

    AUTH = "auth"
    RATE_LIMIT = "rate_limit"
    CONTEXT = "context"
    NOT_FOUND = "not_found"
    BAD_REQUEST = "bad_request"
    SERVER = "server"
    REJECTED = "rejected"
    TIMEOUT = "timeout"
    NETWORK = "network"
    BAD_RESPONSE = "bad_response"
    API = "api"
    INTERNAL = "internal"

    @property
    def label(self) -> str:
        return _LABELS[self]


_LABELS = {
    ErrorKind.AUTH: "鉴权失败",
    ErrorKind.RATE_LIMIT: "请求过于频繁",
    ErrorKind.CONTEXT: "上下文超出上限",
    ErrorKind.NOT_FOUND: "接口或模型不存在",
    ErrorKind.BAD_REQUEST: "请求被接口拒绝",
    ErrorKind.SERVER: "模型服务出错",
    ErrorKind.REJECTED: "模型接口返回错误",
    ErrorKind.TIMEOUT: "请求超时",
    ErrorKind.NETWORK: "网络错误",
    ErrorKind.BAD_RESPONSE: "无法解析模型的响应",
    ErrorKind.API: "模型接口调用失败",
    ErrorKind.INTERNAL: "程序内部错误",
}


@dataclass(frozen=True)
class Failure:
    """一次失败的类别和接口状态码。detail 只在未预料的异常里写异常类名。"""

    kind: ErrorKind
    status_code: int | None = None
    detail: str = ""

    def describe(self) -> str:
        text = self.kind.label
        if self.status_code is not None:
            text += f"（HTTP {self.status_code}）"
        if self.detail:
            text += f"：{self.detail}"
        return text


def classify(exc: Exception) -> Failure:
    """把 SDK 抛出的异常归成类别。读异常只在这里，异常文本不往外传。"""
    if isinstance(exc, openai.APITimeoutError):
        return Failure(ErrorKind.TIMEOUT)
    if isinstance(exc, openai.APIConnectionError):
        return Failure(ErrorKind.NETWORK)
    if isinstance(exc, openai.APIStatusError):
        return _classify_status(exc)
    if isinstance(exc, openai.APIResponseValidationError):
        return Failure(ErrorKind.BAD_RESPONSE, exc.response.status_code)
    if isinstance(exc, openai.OpenAIError):
        return Failure(ErrorKind.API)
    return Failure(ErrorKind.INTERNAL, None, type(exc).__name__)


def _classify_status(exc: openai.APIStatusError) -> Failure:
    status = exc.status_code
    if status in (401, 403):
        return Failure(ErrorKind.AUTH, status)
    if status == 429:
        return Failure(ErrorKind.RATE_LIMIT, status)
    if _is_context_overflow(exc):
        return Failure(ErrorKind.CONTEXT, status)
    if status == 404:
        return Failure(ErrorKind.NOT_FOUND, status)
    if status == 400:
        return Failure(ErrorKind.BAD_REQUEST, status)
    if status >= 500:
        return Failure(ErrorKind.SERVER, status)
    return Failure(ErrorKind.REJECTED, status)


def _is_context_overflow(exc: openai.APIStatusError) -> bool:
    body = exc.body
    texts: list[str] = []
    if isinstance(body, dict):
        texts.extend((str(body.get("code", "")), str(body.get("message", ""))))
        inner = body.get("error")
        if isinstance(inner, dict):
            texts.extend((str(inner.get("code", "")), str(inner.get("message", ""))))
    elif body is not None:
        texts.append(str(body))
    text = " ".join(texts).lower()
    return any(marker in text for marker in _OVERFLOW_MARKERS)
