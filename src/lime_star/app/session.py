"""回合入口：建立会话、提交回合、读取会话记录。

P1 的会话记录只在内存里。落盘的会话记录属于路线图 P3 的 thread_store。
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from openai import OpenAI

from lime_star.model_provider import (
    Clock,
    Message,
    ModelError,
    NewId,
    Provider,
    RequestLog,
    load_config,
    new_id,
    utc_now,
)
from lime_star.model_provider.client import open_client
from lime_star.model_provider.request_log import LOG_DIR

CANCELLED_BY_USER = "用户按 Ctrl+C 取消"


class SessionError(Exception):
    """会话无法建立。消息可以直接显示给用户。"""


class Outcome(StrEnum):
    """回合结局。步数上限随路线图 P2 加入。"""

    DONE = "done"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class TurnResult:
    """一个回合的结局：出错或取消的原因，以及模型的回复（没有回复时为空串）。"""

    turn_id: str
    outcome: Outcome
    reason: str
    reply: str


@dataclass(frozen=True)
class Record:
    """read_thread 的结果：到此刻为止的消息按发生顺序排列，以及每个回合的结局。"""

    messages: tuple[Message, ...]
    turns: tuple[TurnResult, ...]


class Session:
    """一次会话。状态只由调用 start_turn 的线程改写。"""

    def __init__(self, provider: Provider, new_id: NewId = new_id) -> None:
        self._provider = provider
        self._new_id = new_id
        self._messages: list[Message] = []
        self._turns: list[TurnResult] = []

    def start_turn(self, text: str) -> TurnResult:
        """提交一个回合：记下用户消息，等模型回复，返回这个回合的结局。"""
        turn_id = self._new_id()
        self._messages.append(Message(role="user", content=text))
        result = self._run(turn_id)
        self._turns.append(result)
        return result

    def read_thread(self) -> Record:
        return Record(tuple(self._messages), tuple(self._turns))

    def _run(self, turn_id: str) -> TurnResult:
        try:
            reply = self._provider.complete(tuple(self._messages), turn_id)
        except KeyboardInterrupt:
            # 等待模型时按了 Ctrl+C。回合到此为止，用户消息留在历史里（R12.5、R12.6）。
            return TurnResult(turn_id, Outcome.CANCELLED, CANCELLED_BY_USER, "")
        except ModelError as exc:
            return TurnResult(turn_id, Outcome.ERROR, exc.failure.describe(), "")
        self._messages.append(Message(role="assistant", content=reply.text))
        return TurnResult(turn_id, Outcome.DONE, "", reply.text)


def open_session(
    *,
    env: Mapping[str, str],
    workdir: Path,
    client: OpenAI | None = None,
    now: Clock = utc_now,
    new_id: NewId = new_id,
) -> Session:
    """读取模型配置，建好请求日志和模型边界，返回一个新会话。

    client 留空时按配置构造；测试可以传入指向替身服务的客户端。
    """
    config = load_config(env, workdir)
    try:
        log = RequestLog.at(workdir)
    except OSError as exc:
        raise SessionError(f"无法在工作目录下创建 {LOG_DIR}（{type(exc).__name__}）") from exc
    provider = Provider(
        client=client if client is not None else open_client(config),
        config=config,
        log=log,
        session_id=new_id(),
        thread_id=new_id(),
        now=now,
        new_id=new_id,
    )
    return Session(provider, new_id)
