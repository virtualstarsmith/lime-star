"""模型边界：带上系统指令、到此刻为止的全部项和可用的工具发起一次请求，并留下一条请求记录。

覆盖需求 R2.1、R2.2、R3.1 到 R3.3、R12.4，以及 R12.5 里停止等待模型的部分。
线路细节只在这里：项怎样转成接口消息、工具定义怎样交给接口、响应里的工具调用怎样取出来。
"""

import threading
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import assert_never
from uuid import uuid4

from openai import Omit, OpenAI, omit
from openai.types.chat import (
    ChatCompletion,
    ChatCompletionAssistantMessageParam,
    ChatCompletionFunctionToolParam,
    ChatCompletionMessageParam,
    ChatCompletionMessageToolCallParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionToolMessageParam,
    ChatCompletionUserMessageParam,
)
from openai.types.chat.chat_completion_message_function_tool_call_param import (
    Function as CallFunction,
)
from openai.types.shared_params.function_definition import FunctionDefinition

from lime_star.model_provider.config import ModelConfig
from lime_star.model_provider.errors import ErrorKind, Failure, classify
from lime_star.model_provider.prompt import SYSTEM_INSTRUCTION
from lime_star.model_provider.request_log import RequestLog
from lime_star.protocol import (
    Approval,
    Clock,
    Entry,
    Json,
    ModelFailure,
    ModelReply,
    ModelResult,
    ModelText,
    NewId,
    Reasoning,
    ToolCall,
    ToolResult,
    ToolSpec,
    TurnEnd,
    TurnStart,
    UserMessage,
)

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
class Reply:
    """接口的一次完整响应里取出来的东西：文本、工具调用和 token 用量。"""

    text: str
    calls: tuple[ToolCall, ...]
    input_tokens: int
    output_tokens: int


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

    def respond(
        self,
        turn_id: str,
        history: Sequence[Entry],
        tools: Sequence[ToolSpec],
    ) -> ModelResult:
        """发起一次请求并等它结束。

        请求在工作线程里进行。等待期间按 Ctrl+C 会抛出 KeyboardInterrupt；
        已经发出的请求会继续到结束并留下记录，但它的结果不再有人取用。
        进程若在这次请求返回之前就退出，它不会有记录。
        """
        request_id = self._new_id()
        started = time.perf_counter()
        done = threading.Event()
        outcome: list[ModelResult] = []

        def run() -> None:
            try:
                outcome.append(self._send(turn_id, history, tools, request_id, started))
            except Exception as exc:  # 未预料的异常也要让主线程拿到结局
                failure = Failure(ErrorKind.INTERNAL, None, type(exc).__name__)
                outcome.append(ModelFailure(failure.describe()))
            finally:
                done.set()

        threading.Thread(target=run, name="model-request", daemon=True).start()
        while not done.wait(_WAIT_SLICE):
            pass
        return outcome[0]

    def _send(
        self,
        turn_id: str,
        history: Sequence[Entry],
        tools: Sequence[ToolSpec],
        request_id: str,
        started: float,
    ) -> ModelResult:
        reply: Reply | None = None
        failure: Failure | None = None
        try:
            completion = self._client.chat.completions.create(
                model=self._config.model,
                messages=_messages(history),
                tools=_definitions(tools),
            )
            reply = _reply_of(completion)
        except Exception as exc:
            failure = classify(exc)
        if reply is None and failure is None:
            failure = Failure(ErrorKind.BAD_RESPONSE)
        try:
            self._log.append(self._record(turn_id, request_id, started, reply, failure))
        except OSError as exc:
            failure = Failure(ErrorKind.INTERNAL, None, type(exc).__name__)
        if reply is None or failure is not None:
            return ModelFailure((failure or Failure(ErrorKind.BAD_RESPONSE)).describe())
        return ModelReply(text=reply.text, calls=reply.calls)

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


def _definitions(tools: Sequence[ToolSpec]) -> list[ChatCompletionFunctionToolParam] | Omit:
    """把工具说明转成接口里的工具定义。没有工具时不出这个参数，请求与不提供工具时相同。"""
    if not tools:
        return omit
    return [
        ChatCompletionFunctionToolParam(
            type="function",
            function=FunctionDefinition(
                name=tool.name,
                description=tool.description,
                parameters=_parameters(tool.parameters),
            ),
        )
        for tool in tools
    ]


def _parameters(schema: dict[str, Json]) -> dict[str, object]:
    """接口把参数模式当作一般的 JSON 对象；这里复制一份，类型也对得上。"""
    return dict(schema)


def _messages(history: Sequence[Entry]) -> list[ChatCompletionMessageParam]:
    """系统指令只有这一处组装：同一会话的每次请求都带同一份（R2.2）。

    历史是会话记录里的项，按发生顺序转成接口消息。模型文本和紧跟它的工具调用同属一次响应，
    转成同一条 assistant 消息；没有文本的工具调用单独成一条 assistant 消息。
    推理、回合的开始与结局、批准不上线路：用户的决定由工具结果告诉模型。回合结局要不要告诉模型，等仓库所有者决定；
    定下来只改这里。
    """
    messages: list[ChatCompletionMessageParam] = [
        ChatCompletionSystemMessageParam(role="system", content=SYSTEM_INSTRUCTION)
    ]
    speaking: ChatCompletionAssistantMessageParam | None = None
    for entry in history:
        item = entry.item
        match item:
            case UserMessage():
                speaking = None
                messages.append(ChatCompletionUserMessageParam(role="user", content=item.content))
            case Reasoning():
                pass
            case ModelText():
                speaking = ChatCompletionAssistantMessageParam(
                    role="assistant", content=item.content
                )
                messages.append(speaking)
            case ToolCall():
                if speaking is None:
                    speaking = ChatCompletionAssistantMessageParam(role="assistant", content=None)
                    messages.append(speaking)
                speaking["tool_calls"] = [*speaking.get("tool_calls", []), _call_param(item)]
            case ToolResult():
                speaking = None
                messages.append(
                    ChatCompletionToolMessageParam(
                        role="tool", tool_call_id=item.call_id, content=item.content
                    )
                )
            case TurnStart() | TurnEnd() | Approval():
                pass
            case _:
                assert_never(item)
    return messages


def _call_param(call: ToolCall) -> ChatCompletionMessageToolCallParam:
    return ChatCompletionMessageToolCallParam(
        id=call.call_id,
        type="function",
        function=CallFunction(name=call.name, arguments=call.arguments),
    )


def _reply_of(completion: ChatCompletion) -> Reply | None:
    """取出回复文本、工具调用和 token 用量。既没有文本也没有工具调用时返回 None。"""
    choices = completion.choices
    if not choices:
        return None
    message = choices[0].message
    calls: list[ToolCall] = []
    for index, call in enumerate(message.tool_calls or [], start=1):
        if call.type == "function":
            # 接口没有给调用编号时按序号补一个，后面的工具消息才有所指。
            calls.append(
                ToolCall(
                    call_id=call.id or f"call{index}",
                    name=call.function.name,
                    arguments=call.function.arguments,
                )
            )
    text = message.content or ""
    if not text and not calls:
        return None
    usage = completion.usage
    input_tokens = usage.prompt_tokens if usage is not None else 0
    output_tokens = usage.completion_tokens if usage is not None else 0
    return Reply(
        text=text, calls=tuple(calls), input_tokens=input_tokens, output_tokens=output_tokens
    )
