"""模型边界：带上系统指令和到此刻为止的全部历史发起一次请求，并留下一条请求记录。

覆盖需求 R2.1、R2.2、R3.1 到 R3.3、R12.4，以及 R12.5 里停止等待模型的部分。
"""

import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from openai import OpenAI
from openai.types.chat import (
    ChatCompletion,
    ChatCompletionAssistantMessageParam,
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)

from lime_star.model_provider.config import ModelConfig
from lime_star.model_provider.errors import ErrorKind, Failure, classify
from lime_star.model_provider.prompt import SYSTEM_INSTRUCTION
from lime_star.model_provider.request_log import RequestLog

Role = Literal["user", "assistant"]
"""一条消息是谁说的：用户，还是模型。"""

Clock = Callable[[], datetime]
NewId = Callable[[], str]

# 主线程按这个切片反复等待。真实的 Ctrl+C 能直接打断等待，但在 Windows 上，
# CPython 靠一个事件唤醒主线程，解释器版本之间并不一致；挂起的中断则一定会在
# 下一次字节码边界被处理。所以切片要短：中断最多晚一个切片生效。
# 切片不影响回复的延迟，请求一结束等待就返回。
_WAIT_SLICE = 0.1


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return uuid4().hex


@dataclass(frozen=True)
class Message:
    """一条对话消息：用户的，或者模型的。"""

    role: Role
    content: str


@dataclass(frozen=True)
class Reply:
    """模型的一次完整回复。"""

    text: str
    input_tokens: int
    output_tokens: int


class ModelError(Exception):
    """这次模型请求失败。failure 只有类别、接口状态码和说明，没有错误正文。"""

    def __init__(self, failure: Failure) -> None:
        super().__init__(failure.describe())
        self.failure = failure


class Provider:
    """对一个模型发起请求。一个会话用一个实例，session_id 和 thread_id 随每条记录写出。"""

    def __init__(
        self,
        *,
        client: OpenAI,
        config: ModelConfig,
        log: RequestLog,
        session_id: str,
        thread_id: str,
        now: Clock = utc_now,
        new_id: NewId = new_id,
    ) -> None:
        self._client = client
        self._config = config
        self._log = log
        self._session_id = session_id
        self._thread_id = thread_id
        self._now = now
        self._new_id = new_id

    def complete(self, history: Sequence[Message], turn_id: str) -> Reply:
        """发起一次请求并等它结束。

        请求在工作线程里进行。等待期间按 Ctrl+C 会抛出 KeyboardInterrupt；
        已经发出的请求会继续到结束并留下记录，但它的结果不再有人取用。
        进程若在这次请求返回之前就退出，它不会有记录。
        """
        request_id = self._new_id()
        started = time.perf_counter()
        done = threading.Event()
        outcome: list[Reply | ModelError] = []

        def run() -> None:
            try:
                outcome.append(self._send(history, turn_id, request_id, started))
            except Exception as exc:  # 未预料的异常也要让主线程拿到结局
                outcome.append(ModelError(Failure(ErrorKind.INTERNAL, None, type(exc).__name__)))
            finally:
                done.set()

        threading.Thread(target=run, name="model-request", daemon=True).start()
        while not done.wait(_WAIT_SLICE):
            pass
        result = outcome[0]
        if isinstance(result, ModelError):
            raise result
        return result

    def _send(
        self,
        history: Sequence[Message],
        turn_id: str,
        request_id: str,
        started: float,
    ) -> Reply | ModelError:
        reply: Reply | None = None
        failure: Failure | None = None
        try:
            completion = self._client.chat.completions.create(
                model=self._config.model,
                messages=_messages(history),
            )
            reply = _text_of(completion)
        except Exception as exc:
            failure = classify(exc)
        if reply is None and failure is None:
            failure = Failure(ErrorKind.BAD_RESPONSE)
        try:
            self._log.append(self._record(turn_id, request_id, started, reply, failure))
        except OSError as exc:
            return ModelError(Failure(ErrorKind.INTERNAL, None, type(exc).__name__))
        if reply is None or failure is not None:
            return ModelError(failure or Failure(ErrorKind.BAD_RESPONSE))
        return reply

    def _record(
        self,
        turn_id: str,
        request_id: str,
        started: float,
        reply: Reply | None,
        failure: Failure | None,
    ) -> dict[str, object]:
        record: dict[str, object] = {
            "time": self._now().isoformat(),
            "session_id": self._session_id,
            "thread_id": self._thread_id,
            "turn_id": turn_id,
            "request_id": request_id,
            "model": self._config.model,
            "status": "failed" if failure is not None else "ok",
            "elapsed_ms": round((time.perf_counter() - started) * 1000),
            "usage": None,
            "error": None,
        }
        if reply is not None and failure is None:
            record["usage"] = {
                "input": reply.input_tokens,
                "output": reply.output_tokens,
                "total": reply.input_tokens + reply.output_tokens,
            }
        if failure is not None:
            # 只记类别和状态码，不记错误正文（R3.3）。
            record["error"] = {
                "kind": failure.kind.value,
                "status_code": failure.status_code,
                "detail": failure.detail,
            }
        return record


def _messages(history: Sequence[Message]) -> list[ChatCompletionMessageParam]:
    """系统指令只有这一处组装：同一会话的每次请求都带同一份（R2.2）。"""
    messages: list[ChatCompletionMessageParam] = [
        ChatCompletionSystemMessageParam(role="system", content=SYSTEM_INSTRUCTION)
    ]
    for message in history:
        match message.role:
            case "user":
                param: ChatCompletionMessageParam = ChatCompletionUserMessageParam(
                    role="user", content=message.content
                )
            case "assistant":
                param = ChatCompletionAssistantMessageParam(
                    role="assistant", content=message.content
                )
        messages.append(param)
    return messages


def _text_of(completion: ChatCompletion) -> Reply | None:
    """取出回复文本和 token 用量。没有可用文本时返回 None。"""
    choices = completion.choices
    if not choices:
        return None
    content = choices[0].message.content
    if not content:
        return None
    usage = completion.usage
    input_tokens = usage.prompt_tokens if usage is not None else 0
    output_tokens = usage.completion_tokens if usage is not None else 0
    return Reply(text=content, input_tokens=input_tokens, output_tokens=output_tokens)
