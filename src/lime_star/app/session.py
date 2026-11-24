"""回合入口：建立会话、提交回合、读取会话记录。

这里把循环、模型边界和工具注册表装配起来，回合本身由 agent_runtime 的循环跑完。
会话记录在路线图 P2 是内存里的项，落盘属于 P3 的 thread_store。
"""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from lime_star.agent_runtime import run_turn
from lime_star.model_provider import (
    Clock,
    NewId,
    Provider,
    RequestLog,
    load_config,
    new_id,
    utc_now,
)
from lime_star.model_provider.client import Client, open_client
from lime_star.model_provider.request_log import LOG_DIR
from lime_star.protocol import Item, Model, ToolSet, TurnResult
from lime_star.tool_runtime import Registry


class SessionError(Exception):
    """会话无法建立。消息可以直接显示给用户。"""


@dataclass(frozen=True)
class Record:
    """read_thread 的结果：到此刻为止的项按发生顺序排列，以及每个回合的结局。"""

    items: tuple[Item, ...]
    turns: tuple[TurnResult, ...]


class Session:
    """一次会话。状态只由调用 start_turn 的线程改写。"""

    def __init__(self, model: Model, tools: ToolSet, new_id: NewId = new_id) -> None:
        self._model = model
        self._tools = tools
        self._new_id = new_id
        self._items: list[Item] = []
        self._turns: list[TurnResult] = []

    def start_turn(self, text: str) -> TurnResult:
        """提交一个回合：跑完它，返回这个回合的结局。"""
        turn_id = self._new_id()
        result = run_turn(
            turn_id,
            tuple(self._items),
            text,
            model=self._model,
            tools=self._tools,
            transcript=self._items,
        )
        self._turns.append(result)
        return result

    def read_thread(self) -> Record:
        return Record(tuple(self._items), tuple(self._turns))


def open_session(
    *,
    env: Mapping[str, str],
    workdir: Path,
    client: Client | None = None,
    now: Clock = utc_now,
    new_id: NewId = new_id,
    tools: ToolSet | None = None,
) -> Session:
    """读取模型配置，建好请求日志、模型边界和工具边界，返回一个新会话。

    client 留空时按配置构造；测试可以传入指向替身服务的客户端。
    tools 留空时注册表是空的：正式命令在路线图 P2 不向模型提供任何工具；
    测试可以传入带工具的注册表。
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
    return Session(provider, tools if tools is not None else Registry(), new_id)
